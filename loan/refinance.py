"""Refinance handlers: structure a newly funded loan against a client's running
loan according to the global ``AdminSettings.refinance_type``.

Four strategies (see ``AdminSettings.REFINANCE_TYPE_CHOICES``):

  OFFSET_BALANCE  The new loan's principal pays off (offsets) the running loan's
                  balance and the client receives the difference in cash. The new
                  loan then runs on its own terms.
  ADD_ON          The new loan's total (principal + interest) is added to the
                  running balance and the term is extended (old remaining + new
                  fortnights); a single uniform repayment over the combined term.
  CONCURRENT      The two loans run in parallel: the fortnightly repayment is the
                  sum of both until the running loan's term ends, then it steps
                  down to the new loan's repayment for its remaining term.
  ADD_ON_VARIED   Like ADD_ON, but the combined repayment term and fortnightly
                  repayment are entered by staff on the funding form
                  (combined_fortnights / combined_repayment) instead of derived.

Every strategy routes the resulting schedule through :mod:`loan.schedule` so the
immutable-schedule cursor (``fortnights_settled``) and ``next_payment_date`` stay
correct, and — per the agreed behaviour — the combined loan is deducted on the
running loan's *next due date* so the payroll cadence is continuous, with the
running loan's arrears/default state carried forward.
"""
import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction

from loan import schedule as _sched
from loan.models import Statement


_D = lambda v: Decimal(str(v or 0))
_q = lambda v: _D(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _refinance_type():
    from admin1.models import AdminSettings
    try:
        return AdminSettings.objects.get(settings_name='setting1').refinance_type or 'OFFSET_BALANCE'
    except Exception:
        return 'OFFSET_BALANCE'


def refinance_allowed():
    """False when the admin has set Refinance Type to 'Refinance Not Allowed' —
    callers that create an additional/refinanced loan for a client who already
    has one must refuse outright rather than structuring it (there is no
    handler for REFINANCE_NOT_ALLOWED in _HANDLERS; this must be checked
    BEFORE any loan/statement work is done, not left to apply_refinance)."""
    return _refinance_type() != 'REFINANCE_NOT_ALLOWED'


def _statement_count(loan):
    return Statement.objects.filter(loanref=loan).count()


def _copy_statements(running_loan, new_loan):
    """Move a copy of every running-loan statement onto the new loan so the new
    loan carries the full history."""
    for s in Statement.objects.filter(loanref=running_loan).order_by('date', 'id'):
        s.pk = None
        s.loanref = new_loan
        s.save()


def _close_old_loan(running_loan, new_loan, note, today):
    """Copy history to the new loan, write the closing REFINANCE statement, and
    mark the running loan completed with a zero balance."""
    _copy_statements(running_loan, new_loan)
    Statement.objects.create(
        owner=running_loan.owner, ref=f'{running_loan.ref}LE', loanref=running_loan,
        type='REFINANCE', statement=note, debit=_D(running_loan.total_outstanding),
        balance=Decimal('0'), date=today,
        uid=running_loan.owner.uid, luid=settings.LUID,
    )
    running_loan.status = 'COMPLETED'
    running_loan.funded_category = 'COMPLETED'
    running_loan.total_outstanding = Decimal('0')
    running_loan.next_payment_date = None
    running_loan.save()


def _carry_arrears(running_loan, new_loan, was_defaulted):
    """Carry the running loan's arrears / default state onto the new loan.

    ``was_defaulted`` must be captured *before* the running loan is closed, since
    _close_old_loan overwrites its status with COMPLETED."""
    new_loan.total_arrears = _D(running_loan.total_arrears)
    new_loan.number_of_defaults = running_loan.number_of_defaults or 0
    new_loan.last_default_date = running_loan.last_default_date
    new_loan.last_default_amount = running_loan.last_default_amount or 0
    new_loan.default_interest_receivable = (
        _D(new_loan.default_interest_receivable) + _D(running_loan.default_interest_receivable))
    if was_defaulted:
        new_loan.status = 'DEFAULTED'


def _finalize_schedule(new_loan, dates, amounts, today):
    """Store the schedule (and optional per-fortnight amounts), reset the cursor,
    and activate the new loan."""
    new_loan.set_repayment_dates([d.isoformat() for d in dates])
    if amounts is not None:
        new_loan.set_repayment_amounts([str(a) for a in amounts])
        new_loan.repayment_amount = amounts[0] if amounts else new_loan.repayment_amount
    new_loan.number_of_fortnights = len(dates)
    new_loan.fortnights_settled = 0
    if dates:
        new_loan.repayment_start_date = dates[0]
        new_loan.expected_end_date = dates[-1]
    new_loan.next_payment_date = dates[0] if dates else None
    new_loan.category = 'FUNDED'
    new_loan.funded_category = 'ACTIVE'
    if new_loan.status != 'DEFAULTED':
        new_loan.status = 'RUNNING'
    new_loan.funding_date = new_loan.funding_date or today
    new_loan.save()


def _start_date(running_loan, new_loan, today):
    """Combined schedule anchor: the running loan's next due date (continuous
    payroll cadence), falling back to the new loan's own start."""
    return _sched.next_due_date(running_loan) or new_loan.repayment_start_date or today


# ── Strategies ──────────────────────────────────────────────────────────────

def _offset_balance(request, running_loan, new_loan, notify, today):
    b_old = _D(running_loan.total_outstanding)
    p_new = _D(new_loan.amount)
    t_new = _D(new_loan.total_loan_amount)
    n = int(new_loan.number_of_fortnights or 0)
    r_new = _q(t_new / n) if n else Decimal('0')
    start = _start_date(running_loan, new_loan, today)

    _close_old_loan(running_loan, new_loan, f'Balance offset by new loan {new_loan.ref}', today)

    # The new loan runs on its own terms; part of its principal cleared the old
    # balance, so the client receives the difference in cash.
    new_loan.total_outstanding = t_new
    new_loan.total_loan_amount = t_new
    new_loan.repayment_amount = r_new
    # The offset settles the old balance (incl. any arrears), so only the default
    # history counters are carried for reporting continuity.
    new_loan.number_of_defaults = running_loan.number_of_defaults or 0
    new_loan.last_default_date = running_loan.last_default_date
    new_loan.last_default_amount = running_loan.last_default_amount or 0

    dates = [start + datetime.timedelta(days=14 * k) for k in range(n)]
    _finalize_schedule(new_loan, dates, None, today)

    net_cash = p_new - b_old - _D(settings.PROCESSING_FEE)
    cnt = _statement_count(new_loan) + 1
    Statement.objects.create(
        owner=new_loan.owner, ref=f'{new_loan.ref}OF{cnt}', loanref=new_loan, type='REFINANCE',
        statement=(f'Offset K{b_old:.2f} against prior loan {running_loan.ref}; '
                   f'net cash disbursed K{max(Decimal("0"), net_cash):.2f}'),
        debit=Decimal('0'), credit=Decimal('0'), balance=t_new, date=today,
        uid=new_loan.owner.uid, luid=settings.LUID,
    )
    return new_loan


def _add_on(request, running_loan, new_loan, notify, today):
    b_old = _D(running_loan.total_outstanding)
    p_new = _D(new_loan.amount)
    i_new = _D(new_loan.interest)
    t_new = _D(new_loan.total_loan_amount)
    n = int(new_loan.number_of_fortnights or 0)
    m = len(_sched.remaining_due_dates(running_loan))
    start = _start_date(running_loan, new_loan, today)
    was_defaulted = running_loan.status == 'DEFAULTED'

    old_principal_recv = _D(running_loan.principal_loan_receivable)
    old_interest_recv = _D(running_loan.ordinary_interest_receivable)

    _close_old_loan(running_loan, new_loan, f'Balance added onto new loan {new_loan.ref}', today)

    combined = b_old + t_new
    L = m + n
    r = _q(combined / L) if L else Decimal('0')

    new_loan.total_outstanding = combined
    new_loan.total_loan_amount = combined
    new_loan.repayment_amount = r
    new_loan.principal_loan_receivable = p_new + old_principal_recv
    new_loan.ordinary_interest_receivable = i_new + old_interest_recv
    new_loan.interest = i_new + old_interest_recv
    _carry_arrears(running_loan, new_loan, was_defaulted)

    dates = [start + datetime.timedelta(days=14 * k) for k in range(L)]
    _finalize_schedule(new_loan, dates, None, today)

    cnt = _statement_count(new_loan) + 1
    Statement.objects.create(
        owner=new_loan.owner, ref=f'{new_loan.ref}AO{cnt}', loanref=new_loan, type='REFINANCE',
        statement=(f'Add-on refinance: K{t_new:.2f} added to prior balance K{b_old:.2f}; '
                   f'term extended to {L} fortnights'),
        credit=p_new, debit=Decimal('0'), balance=combined, date=today,
        uid=new_loan.owner.uid, luid=settings.LUID,
    )
    return new_loan


def _concurrent(request, running_loan, new_loan, notify, today):
    b_old = _D(running_loan.total_outstanding)
    r_old = _D(running_loan.repayment_amount)
    p_new = _D(new_loan.amount)
    i_new = _D(new_loan.interest)
    t_new = _D(new_loan.total_loan_amount)
    n = int(new_loan.number_of_fortnights or 0)
    r_new = _q(t_new / n) if n else Decimal('0')
    m = len(_sched.remaining_due_dates(running_loan))
    start = _start_date(running_loan, new_loan, today)
    was_defaulted = running_loan.status == 'DEFAULTED'

    old_principal_recv = _D(running_loan.principal_loan_receivable)
    old_interest_recv = _D(running_loan.ordinary_interest_receivable)

    _close_old_loan(running_loan, new_loan, f'Loan moved to new loan {new_loan.ref}', today)

    dates, amounts, L = _sched.build_concurrent(m, r_old, n, r_new, start)
    combined = b_old + t_new

    new_loan.total_outstanding = combined
    new_loan.total_loan_amount = combined
    new_loan.principal_loan_receivable = p_new + old_principal_recv
    new_loan.ordinary_interest_receivable = i_new + old_interest_recv
    new_loan.interest = i_new + old_interest_recv
    _carry_arrears(running_loan, new_loan, was_defaulted)

    _finalize_schedule(new_loan, dates, amounts, today)

    overlap = min(m, n)
    cnt = _statement_count(new_loan) + 1
    Statement.objects.create(
        owner=new_loan.owner, ref=f'{new_loan.ref}CN{cnt}', loanref=new_loan, type='REFINANCE',
        statement=(f'Concurrent refinance: new loan K{t_new:.2f} (interest K{i_new:.2f}) added; '
                   f'repayment K{amounts[0]:.2f} for {overlap} fortnight(s), then K{r_new:.2f}'),
        credit=p_new, debit=Decimal('0'), balance=combined, date=today,
        uid=new_loan.owner.uid, luid=settings.LUID,
    )
    return new_loan


def _add_on_varied(request, running_loan, new_loan, notify, today):
    """Add-on with staff-entered terms: the combined balance is the same as
    ADD_ON (old outstanding + new loan total), but the repayment term and the
    fortnightly repayment are entered at funding (``combined_fortnights`` /
    ``combined_repayment`` on the funding form) instead of being derived.
    Blank inputs fall back to the ADD_ON derivation."""
    b_old = _D(running_loan.total_outstanding)
    p_new = _D(new_loan.amount)
    i_new = _D(new_loan.interest)
    t_new = _D(new_loan.total_loan_amount)
    n = int(new_loan.number_of_fortnights or 0)
    m = len(_sched.remaining_due_dates(running_loan))
    start = _start_date(running_loan, new_loan, today)
    was_defaulted = running_loan.status == 'DEFAULTED'

    combined = b_old + t_new
    # staff-entered combined term / repayment (the "varied" part)
    post = getattr(request, 'POST', {}) or {}
    try:
        L = int(post.get('combined_fortnights') or 0)
    except (TypeError, ValueError):
        L = 0
    if L <= 0:
        L = m + n
    try:
        r = _q(Decimal(str(post.get('combined_repayment'))))
    except Exception:
        r = Decimal('0')
    if r <= 0:
        r = _q(combined / L) if L else Decimal('0')

    old_principal_recv = _D(running_loan.principal_loan_receivable)
    old_interest_recv = _D(running_loan.ordinary_interest_receivable)

    _close_old_loan(running_loan, new_loan, f'Balance added onto new loan {new_loan.ref}', today)

    new_loan.total_outstanding = combined
    new_loan.total_loan_amount = combined
    new_loan.repayment_amount = r
    new_loan.principal_loan_receivable = p_new + old_principal_recv
    new_loan.ordinary_interest_receivable = i_new + old_interest_recv
    new_loan.interest = i_new + old_interest_recv
    _carry_arrears(running_loan, new_loan, was_defaulted)

    dates = [start + datetime.timedelta(days=14 * k) for k in range(L)]
    _finalize_schedule(new_loan, dates, None, today)
    # _finalize_schedule leaves repayment_amount untouched when amounts is None,
    # so the staff-entered repayment above stands.

    cnt = _statement_count(new_loan) + 1
    Statement.objects.create(
        owner=new_loan.owner, ref=f'{new_loan.ref}AV{cnt}', loanref=new_loan, type='REFINANCE',
        statement=(f'Add-on (varied) refinance: K{t_new:.2f} added to prior balance K{b_old:.2f}; '
                   f'term {L} fortnights at K{r:.2f} per fortnight'),
        credit=p_new, debit=Decimal('0'), balance=combined, date=today,
        uid=new_loan.owner.uid, luid=settings.LUID,
    )
    return new_loan


_HANDLERS = {
    'OFFSET_BALANCE': _offset_balance,
    'ADD_ON': _add_on,
    'CONCURRENT': _concurrent,
    'ADD_ON_VARIED': _add_on_varied,
}


def apply_refinance(request, running_loan, new_loan, notify=True, today=None):
    """Structure ``new_loan`` against ``running_loan`` using the configured
    refinance type. ``new_loan`` must already carry its own base terms (amount,
    interest, total_loan_amount, number_of_fortnights). Returns the new loan."""
    today = today or datetime.date.today()
    rtype = _refinance_type()
    if rtype == 'REFINANCE_NOT_ALLOWED':
        # Callers must check refinance_allowed() up front (before creating any
        # loan/statement rows) so they can show a clean error message — this is
        # a hard backstop, not the primary guard.
        raise ValueError('Refinancing is disabled (Refinance Type = Refinance Not Allowed).')
    handler = _HANDLERS.get(rtype, _offset_balance)
    with transaction.atomic():
        return handler(request, running_loan, new_loan, notify, today)
