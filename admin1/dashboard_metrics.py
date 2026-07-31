"""Shared dashboard metrics — single source of truth for the Admin and Staff
dashboards so the two never drift, and so the figures match the reports engine.

All period filters use DateField columns (Payment.date, Loan.funding_date,
Statement.date) with explicit date ranges — never TruncMonth/__date lookups,
because this MySQL server has no timezone tables loaded (those return NULL).
"""
import calendar
import datetime
from decimal import Decimal

from django.db.models import Sum, Count, Q

from accounts.models import UserProfile
from loan.models import Loan, Payment, Statement, PaymentUploads

_D0 = Decimal('0')


def _s(qs, field):
    return qs.aggregate(x=Sum(field))['x'] or _D0


def _pct(n, d):
    return round(float(n) / float(d) * 100, 1) if d else 0.0


def loan_book():
    """Live loan book: funded, not completed/archived."""
    return Loan.objects.filter(category='FUNDED').exclude(funded_category__in=['COMPLETED', 'ARCHIVED'])


# ── Time windows ───────────────────────────────────────────────────────────
def windows(today=None):
    today = today or datetime.date.today()
    month_start = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    month_end = today.replace(day=last_day)
    return {
        'today': today,
        'week_start': today - datetime.timedelta(days=6),
        'week_end': today,
        'month_start': month_start,
        'month_end': month_end,
        'month_to_date_end': today,
    }


def _scheduled_expected(start, end, book=None):
    """(expected amount, number of due fortnights) scheduled in [start, end],
    from the immutable schedule — independent of whether they've been paid."""
    from loan import schedule as sched
    book = book if book is not None else loan_book()
    total = _D0
    count = 0
    for loan in book.select_related(None):
        dates = sched.build_schedule(loan)
        amounts = sched.expected_amounts(loan)
        for i, d in enumerate(dates):
            if start <= d <= end:
                total += amounts[i] if i < len(amounts) else _D0
                count += 1
    return total, count


# ── Portfolio snapshot (as of now) ─────────────────────────────────────────
def portfolio_snapshot():
    book = loan_book()
    funded = Loan.objects.filter(category='FUNDED')
    funded_count = funded.count()
    npl = funded.filter(Q(status='DEFAULTED') | Q(funded_category__in=['RECOVERY', 'BAD', 'WOFF']))
    par30_out = _s(book.filter(days_in_default__gt=30), 'total_outstanding')
    gross = _s(book, 'total_outstanding')
    return {
        'active_loans': book.filter(funded_category='ACTIVE').count(),
        'running': funded.filter(status='RUNNING', funded_category='ACTIVE').count(),
        'defaulted': funded.filter(status='DEFAULTED', funded_category='ACTIVE').count(),
        'recovery': funded.filter(funded_category='RECOVERY').count(),
        'bad': funded.filter(funded_category='BAD').count(),
        'completed': Loan.objects.filter(funded_category='COMPLETED').count(),
        'gross': gross,
        'principal_out': _s(book, 'principal_loan_receivable'),
        'interest_out': _s(book, 'ordinary_interest_receivable') + _s(book, 'default_interest_receivable'),
        'arrears': _s(book, 'total_arrears'),
        'loans_in_arrears': book.filter(total_arrears__gt=0).count(),
        'par30': _pct(par30_out, gross),
        'npl_rate': _pct(npl.count(), funded_count),
        'default_interest_out': _s(book, 'default_interest_receivable'),
        'avg_loan': (float(_s(funded, 'amount')) / funded_count) if funded_count else 0,
    }


def aging_breakdown():
    """Arrears aging buckets (count + outstanding) for loans in arrears."""
    book = loan_book().filter(total_arrears__gt=0)
    buckets = [
        ('0–30', book.filter(days_in_default__gte=0, days_in_default__lte=30)),
        ('31–60', book.filter(days_in_default__gte=31, days_in_default__lte=60)),
        ('61–90', book.filter(days_in_default__gte=61, days_in_default__lte=90)),
        ('90+', book.filter(days_in_default__gt=90)),
    ]
    return [{'label': lbl, 'count': qs.count(), 'arrears': _s(qs, 'total_arrears')} for lbl, qs in buckets]


# ── Period performance ──────────────────────────────────────────────────────
def period_figures(start, end, book=None):
    period_loans = Loan.objects.filter(category='FUNDED', funding_date__gte=start, funding_date__lte=end)
    pmts = Payment.objects.filter(date__gte=start, date__lte=end)
    stmts = Statement.objects.filter(date__gte=start, date__lte=end, type='PAYMENT')
    expected, due_count = _scheduled_expected(start, end, book=book)
    collected = _s(pmts, 'amount')
    return {
        'disbursed_count': period_loans.count(),
        'disbursed_value': _s(period_loans, 'amount'),
        'collected': collected,
        'payments_count': pmts.count(),
        'expected': expected,
        'due_count': due_count,
        'collection_rate': _pct(collected, expected),
        'principal_col': _s(stmts, 'principal_collected'),
        'interest_col': _s(stmts, 'interest_collected'),
        'default_int_col': _s(stmts, 'default_interest_collected'),
        'fee_income': _s(period_loans, 'processing_fee'),
    }


def today_figures(today=None):
    today = today or datetime.date.today()
    due_val, due_count = _scheduled_expected(today, today)
    collected = _s(Payment.objects.filter(date=today), 'amount')
    return {'due_count': due_count, 'due_value': due_val, 'collected': collected}


def expected_upcoming(today=None):
    """Forward-looking expected repayments from the immutable schedule, for a set
    of horizons (all starting today). Single pass over the loan book."""
    from loan import schedule as sched
    today = today or datetime.date.today()
    week_end = today + datetime.timedelta(days=(6 - today.weekday()))   # end of ISO week (Sun)
    d7 = today + datetime.timedelta(days=6)
    d14 = today + datetime.timedelta(days=13)
    month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    order = ['today', 'this_week', 'next_7', 'next_14', 'this_month']
    ends = {'today': today, 'this_week': week_end, 'next_7': d7, 'next_14': d14, 'this_month': month_end}
    horizon = max(ends.values())
    buckets = {k: {'value': _D0, 'count': 0, 'end': ends[k]} for k in order}
    for loan in loan_book():
        dates = sched.build_schedule(loan)
        amounts = sched.expected_amounts(loan)
        for i, d in enumerate(dates):
            if d < today or d > horizon:
                continue
            amt = amounts[i] if i < len(amounts) else _D0
            for b in buckets.values():
                if today <= d <= b['end']:
                    b['value'] += amt
                    b['count'] += 1
    buckets['_order'] = order
    return buckets


# ── Trends (charts) ─────────────────────────────────────────────────────────
def _month_ranges(n, today=None):
    today = today or datetime.date.today()
    ranges = []
    y, m = today.year, today.month
    for _ in range(n):
        start = datetime.date(y, m, 1)
        end = datetime.date(y, m, calendar.monthrange(y, m)[1])
        ranges.append((start, end))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(ranges))


def monthly_trend(n=6):
    """Per-month disbursed vs collected, plus collection rate (collected /
    scheduled-due). Monthly smooths the noise of short windows."""
    labels, disbursed, collected, rate = [], [], [], []
    book = loan_book()
    for start, end in _month_ranges(n):
        labels.append(start.strftime('%b %y'))
        d = float(_s(Loan.objects.filter(category='FUNDED', funding_date__gte=start, funding_date__lte=end), 'amount'))
        c = float(_s(Payment.objects.filter(date__gte=start, date__lte=end), 'amount'))
        exp, _cnt = _scheduled_expected(start, end, book=book)
        disbursed.append(d)
        collected.append(c)
        rate.append(min(_pct(c, exp), 200.0))  # cap for a readable chart
    return {'labels': labels, 'disbursed': disbursed, 'collected': collected, 'rate': rate}


def status_breakdown():
    funded = Loan.objects.filter(category='FUNDED')
    return {
        'Running': funded.filter(status='RUNNING', funded_category='ACTIVE').count(),
        'Defaulted': funded.filter(status='DEFAULTED', funded_category='ACTIVE').count(),
        'Recovery': funded.filter(funded_category='RECOVERY').count(),
        'Bad': funded.filter(funded_category='BAD').count(),
        'Completed': funded.filter(funded_category='COMPLETED').count(),
    }


def pending_breakdown():
    p = Loan.objects.filter(category='PENDING')
    return {
        'Awaiting T&C': p.filter(status='AWAITING T&C').count(),
        'Under Review': p.filter(status='UNDER REVIEW').count(),
        'On Hold': p.filter(status='ON HOLD').count(),
        'Approved': p.filter(status='APPROVED').count(),
    }


# ── Operational / action items ──────────────────────────────────────────────
def _overdue_needing_default_count():
    """Loans with a repayment past its mercy period — i.e. what a defaults
    run (manual or automatic) would actually classify right now."""
    from loan import schedule as sched
    from admin1.models import get_loan_config
    mercy = get_loan_config().get('mercy_days') or 0
    cutoff = datetime.date.today() - datetime.timedelta(days=int(mercy))
    n = 0
    for loan in loan_book().filter(funded_category='ACTIVE'):
        if sched.next_overdue_due_date(loan, cutoff):
            n += 1
    return n


def operational():
    pending = Loan.objects.filter(category='PENDING')
    return {
        'awaiting_funding_qs': pending.filter(status='APPROVED').select_related('owner')[:6],
        'awaiting_funding_count': pending.filter(status='APPROVED').count(),
        'pending_activation_qs': UserProfile.objects.filter(activation=0, category='CLIENT').order_by('-created_at')[:6],
        'pending_activation_count': UserProfile.objects.filter(activation=0, category='CLIENT').count(),
        'uploads_to_reconcile': PaymentUploads.objects.filter(status='UPLOADED').count(),
        'overdue_needing_default': _overdue_needing_default_count(),
        'open_tickets': __ticket_open_count(),
        'awaiting_reply_tickets': __ticket_waiting_count(),
        'in_arrears': loan_book().filter(total_arrears__gt=0).count(),
    }


def __ticket_open_count():
    try:
        from support.models import SupportTicket
        return SupportTicket.objects.exclude(status='closed').count()
    except Exception:
        return 0


def __ticket_waiting_count():
    try:
        from support.models import SupportTicket
        return SupportTicket.objects.filter(status='user_replied').count()
    except Exception:
        return 0


def recent_activity(limit=6):
    payments = Payment.objects.select_related('owner', 'loanref').order_by('-created_at')[:limit]
    applications = Loan.objects.select_related('owner').order_by('-created_at')[:limit]
    return {'recent_payments': payments, 'recent_applications': applications}


# ── Assembled context ───────────────────────────────────────────────────────
def build(scope='admin'):
    """Assemble the full dashboard context (shared by admin & staff)."""
    w = windows()
    book = loan_book()
    status_break = status_breakdown()
    aging = aging_breakdown()
    pending_break = pending_breakdown()
    ctx = {
        'w': w,
        'portfolio': portfolio_snapshot(),
        'aging': aging,
        'month': period_figures(w['month_start'], w['month_to_date_end'], book=book),
        'week': period_figures(w['week_start'], w['week_end'], book=book),
        'today_fig': today_figures(w['today']),
        'trend': monthly_trend(6),
        'status_break': status_break,
        'pending_break': pending_break,
        'pending_total': sum(pending_break.values()),
        'apps_to_review': pending_break.get('Under Review', 0),
        'expected_up': expected_upcoming(w['today']),
        # Plain-number arrays for the charts (json_script-safe — no Decimals).
        'chart_status': {'labels': list(status_break.keys()), 'counts': list(status_break.values())},
        'chart_aging': {'labels': [a['label'] for a in aging], 'counts': [a['count'] for a in aging]},
        'ops': operational(),
        'recent': recent_activity(),
        # created_at is a datetime; use a datetime lower bound (no __date lookup —
        # MySQL here has no tz tables so __date returns NULL).
        'new_clients_month': UserProfile.objects.filter(
            category='CLIENT',
            created_at__gte=datetime.datetime.combine(w['month_start'], datetime.time.min),
        ).count(),
    }
    return ctx
