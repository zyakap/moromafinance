"""Repayment schedule as an immutable list of due dates plus a settled cursor.

The schedule is ``repayment_start_date`` + 14-day steps for ``number_of_fortnights``
and never changes once the loan is funded. How far the loan has progressed is a
single counter, ``Loan.fortnights_settled`` — the number of scheduled fortnights
that have been accounted for by one of:

  * a cash repayment (normal / partial),
  * a default (missed repayment), or
  * an advance-balance application (a prepaid surplus covering a due fortnight).

Every other schedule value — the remaining due dates, the next payment date and
whether anything is overdue — is *derived* from the immutable schedule and the
cursor, so a single helper is the source of truth and no code path mutates the
list directly. Overpayment surplus does NOT advance the cursor: the balance is
reduced when the payment is made and the surplus is held as ``advance_balance``
until it is applied to a later due fortnight (see loan.engine.create_default_for_loan).
"""

import datetime
from decimal import Decimal


def _parse(d):
    if isinstance(d, datetime.datetime):
        return d.date()
    if isinstance(d, datetime.date):
        return d
    return datetime.datetime.strptime(str(d)[:10], '%Y-%m-%d').date()


def _canonical_from_start(loan):
    """The schedule computed from repayment_start_date + 14-day steps."""
    start = loan.repayment_start_date
    n = int(loan.number_of_fortnights or 0)
    if not start or n <= 0:
        return []
    start = _parse(start)
    return [start + datetime.timedelta(days=14 * k) for k in range(n)]


def build_schedule(loan):
    """Immutable schedule (list of date objects), earliest first.

    The full schedule (length == number_of_fortnights) is stored in
    ``repayment_dates`` at funding and never mutated, so that is the source of
    truth. If it is missing/short, fall back to computing it from
    ``repayment_start_date``.
    """
    n = int(loan.number_of_fortnights or 0)
    stored = loan.get_repayment_dates() or []
    if n > 0 and len(stored) == n:
        try:
            return [_parse(d) for d in stored]
        except (ValueError, TypeError):
            pass
    return _canonical_from_start(loan)


def total_fortnights(loan):
    return len(build_schedule(loan))


def settled_count(loan):
    """Number of scheduled fortnights already accounted for (clamped to [0, n])."""
    n = total_fortnights(loan)
    settled = int(loan.fortnights_settled or 0)
    return max(0, min(settled, n))


def remaining_due_dates(loan):
    """Unsettled scheduled due dates, earliest first (date objects)."""
    return build_schedule(loan)[settled_count(loan):]


def next_due_date(loan):
    """The earliest unsettled scheduled date, or None once the term is complete."""
    rem = remaining_due_dates(loan)
    return rem[0] if rem else None


def next_overdue_due_date(loan, today=None):
    """Earliest unsettled scheduled date strictly in the past, or None. A future
    (or today's) due date is never overdue, so a future fortnight is never
    defaulted."""
    today = today or datetime.date.today()
    for d in remaining_due_dates(loan):
        if d < today:
            return d
        break  # ascending — the first non-overdue means none are overdue
    return None


def recompute_next_payment_date(loan):
    """Set loan.next_payment_date from the schedule/cursor (None when complete)."""
    loan.next_payment_date = next_due_date(loan)
    return loan.next_payment_date


def expected_amounts(loan):
    """Per-fortnight expected repayment amounts (Decimals), earliest first.

    When the loan stores an explicit amounts list (a non-uniform schedule, e.g. a
    CONCURRENT refinance) that list is used; otherwise the uniform
    ``repayment_amount`` is repeated for every scheduled fortnight."""
    stored = loan.get_repayment_amounts() or []
    n = total_fortnights(loan)
    if stored and len(stored) == n:
        try:
            return [Decimal(str(a)) for a in stored]
        except (ValueError, TypeError):
            pass
    return [Decimal(str(loan.repayment_amount or 0))] * n


def current_expected_amount(loan):
    """The repayment expected for the current (next unsettled) fortnight, or 0 once
    the term is complete."""
    amounts = expected_amounts(loan)
    idx = settled_count(loan)
    return amounts[idx] if idx < len(amounts) else Decimal('0')


def _refresh_repayment_amount(loan):
    """Keep loan.repayment_amount pointed at the current fortnight's expected amount
    for non-uniform schedules. Uniform loans (no stored amounts list) are left
    untouched so existing behaviour is preserved."""
    if loan.get_repayment_amounts():
        amt = current_expected_amount(loan)
        if amt > 0:
            loan.repayment_amount = amt


def settle(loan, n=1):
    """Advance the settled cursor by ``n`` fortnights (capped at the term) and
    recompute next_payment_date. Returns the new settled count."""
    total = total_fortnights(loan)
    loan.fortnights_settled = min(total, settled_count(loan) + max(0, int(n)))
    recompute_next_payment_date(loan)
    _refresh_repayment_amount(loan)
    return loan.fortnights_settled


def unsettle(loan, n=1):
    """Reverse the settled cursor by ``n`` (used by the Fix Defaults correction)."""
    loan.fortnights_settled = max(0, settled_count(loan) - max(0, int(n)))
    recompute_next_payment_date(loan)
    _refresh_repayment_amount(loan)
    return loan.fortnights_settled


def build_concurrent(old_remaining_m, r_old, n_new, r_new, start_date):
    """Build a CONCURRENT refinance schedule.

    Two loans run in parallel: for the first ``min(m, n)`` fortnights the client
    pays ``r_old + r_new``; after the shorter loan's term ends only the longer
    loan's repayment continues. Returns ``(dates, amounts, term_L)`` where the term
    is ``max(m, n)`` fortnights, all 14 days apart starting at ``start_date``.
    """
    m = max(0, int(old_remaining_m))
    n = max(0, int(n_new))
    r_old = Decimal(str(r_old or 0))
    r_new = Decimal(str(r_new or 0))
    start = _parse(start_date)
    length = max(m, n)
    dates = [start + datetime.timedelta(days=14 * k) for k in range(length)]
    amounts = [
        (r_old if k < m else Decimal('0')) + (r_new if k < n else Decimal('0'))
        for k in range(length)
    ]
    return dates, amounts, length


def is_fully_scheduled(loan):
    """True when every scheduled fortnight has been accounted for."""
    return settled_count(loan) >= total_fortnights(loan)


def ensure_full_schedule_stored(loan):
    """Persist the canonical (start-anchored) schedule into repayment_dates (for
    LAS / display). Does not touch the cursor."""
    loan.set_repayment_dates([d.isoformat() for d in _canonical_from_start(loan)])


# ── Schedule regeneration (staff/admin "Regenerate Dates" tool) ──────────────

FREQUENCY_CHOICES = ('FORTNIGHTLY', 'WEEKLY', 'MONTHLY')


def _add_months(d, months):
    """Add calendar months, clamping the day to the target month's length."""
    import calendar
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def regenerate(loan, next_date, remaining, frequency='FORTNIGHTLY'):
    """Rebuild the UNSETTLED portion of the schedule: the already-settled dates
    are kept as history, then ``remaining`` new due dates run from ``next_date``
    at the chosen frequency. The cursor stays where it is, so the loan's next
    payment date becomes ``next_date``.

    Returns the full new schedule (list of dates). The caller saves the loan.
    """
    next_date = _parse(next_date)
    remaining = int(remaining)
    if remaining < 1:
        raise ValueError('Remaining terms must be at least 1.')
    if frequency not in FREQUENCY_CHOICES:
        raise ValueError(f'Unknown frequency {frequency!r}.')

    settled = settled_count(loan)
    history = build_schedule(loan)[:settled]
    if frequency == 'MONTHLY':
        future = [_add_months(next_date, k) for k in range(remaining)]
    elif frequency == 'WEEKLY':
        future = [next_date + datetime.timedelta(days=7 * k) for k in range(remaining)]
    else:
        future = [next_date + datetime.timedelta(days=14 * k) for k in range(remaining)]

    dates = history + future
    loan.set_repayment_dates([d.isoformat() for d in dates])
    # build_schedule() only trusts the stored list when its length matches the
    # term counter, so keep them in lockstep.
    loan.number_of_fortnights = len(dates)
    loan.fortnights_settled = settled
    loan.expected_end_date = dates[-1]
    if not history:
        loan.repayment_start_date = dates[0]
    # Mark the schedule as hand-regenerated so canonical-rebuild tools
    # (reconcile_schedule_cursor) never overwrite the custom spacing.
    loan.custom_schedule = True
    recompute_next_payment_date(loan)
    _refresh_repayment_amount(loan)
    return dates
