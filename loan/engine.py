"""Loan default / repayment-date engine.

Single source of truth for: which scheduled repayment date is next due, whether
it is actually overdue, and how a default is charged (netting any advance credit
and charging interest on the shortfall or the full amount per admin setting).

Key rules (from the June 2026 redesign):
  * A default is only ever created for a scheduled date that is STRICTLY in the
    past (``due_date < today``). The engine never defaults a future or same-day
    repayment.
  * Clicking "Create Default" processes the EARLIEST unsettled scheduled date
    first; each call advances to the next one.
  * Any advance (prepaid) balance is netted against the missed repayment before
    default interest is computed.
"""
import datetime
import logging
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

_D = lambda v: Decimal(str(v or 0))


def _money(v):
    """Quantize to 2 decimal places (currency)."""
    return _D(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _parse(d):
    if isinstance(d, datetime.datetime):
        return d.date()
    if isinstance(d, datetime.date):
        return d
    return datetime.datetime.strptime(d, '%Y-%m-%d').date()


# The schedule/cursor helpers now live in loan.schedule (immutable schedule +
# derived cursor). These thin wrappers keep the engine's public names stable.
from loan.schedule import (  # noqa: E402
    build_schedule as build_full_schedule,
    remaining_due_dates,
    next_overdue_due_date,
)


def is_overdue(due_date, today=None):
    """True only if the scheduled date is strictly in the past. Today or future
    dates are never overdue, so the engine can never default a future payment."""
    today = today or datetime.date.today()
    return _parse(due_date) < today


def default_interest_for(loan, shortfall, cfg):
    """Kina default interest for a missed repayment, honouring the
    default_interest_base setting (SHORTFALL vs FULL) for PERCENTAGE interest."""
    from admin1.models import calc_default_interest
    rate = cfg.get('default_interest_rate') or 0
    itype = cfg.get('default_interest_type', 'PERCENTAGE')
    if itype == 'FIXED':
        return calc_default_interest(rate, 'FIXED', 0)
    base_mode = cfg.get('default_interest_base', 'SHORTFALL')
    base = shortfall if base_mode == 'SHORTFALL' else _D(loan.repayment_amount)
    if base < 0:
        base = Decimal('0')
    return _money(calc_default_interest(rate, 'PERCENTAGE', base))


def preview_default(loan, today=None, mercy_days=0):
    """Non-mutating preview of what create_default_for_loan would do right now.

    Returns (due, shortfall, advance_applied):
      * due is None            -> nothing overdue; nothing would happen.
      * shortfall <= 0         -> the earliest overdue fortnight would be fully
                                   settled from advance credit, no default.
      * shortfall > 0          -> a default would be created, netting
                                   `advance_applied` of whatever advance exists.

    Used to decide whether "Create Default" should be blocked in favour of the
    explicit "Apply Advance to Missed Payments" action (loans currently
    carrying enough advance credit to fully cover the missed repayment).
    """
    today = today or datetime.date.today()
    cutoff = today - datetime.timedelta(days=int(mercy_days or 0))
    due = next_overdue_due_date(loan, cutoff)
    if due is None:
        return None, None, None

    scheduled = _D(loan.repayment_amount)
    advance = _D(loan.advance_balance)
    advance_applied = min(advance, scheduled)
    shortfall = scheduled - advance_applied
    if shortfall < 0:
        shortfall = Decimal('0')
    return due, shortfall, advance_applied


def create_default_for_loan(loan, today=None, mercy_days=0):
    """Create a default for the loan's earliest overdue scheduled repayment.

    Returns (statement_or_None, ok, message). ``ok`` is False (no statement) when
    there is no overdue repayment — i.e. the next due date is in the future.

    ``mercy_days`` shifts the overdue cutoff back: a repayment only becomes
    eligible once it is more than that many days past due. Batch classifiers
    pass the admin mercy setting; the per-loan "Create Default" action passes 0
    so a deliberate manual default is never blocked by the grace period.

    Caller is responsible for the surrounding transaction and for select_for_update.
    """
    from django.conf import settings
    from admin1.models import get_loan_config
    from loan.models import Statement

    today = today or datetime.date.today()
    cfg = get_loan_config()

    due, shortfall, advance_applied = preview_default(loan, today, mercy_days)
    if due is None:
        nxt = remaining_due_dates(loan)
        nxt_str = nxt[0].isoformat() if nxt else 'n/a'
        return None, False, f'No overdue repayment to default. Next repayment ({nxt_str}) is not yet due.'

    from loan import schedule as _sched

    advance = _D(loan.advance_balance)
    due_str = due.isoformat()
    count = Statement.objects.filter(loanref=loan).count() + 1

    # ── Advance fully covers this due fortnight → apply it, do NOT default ──────
    # The balance was already reduced when the advance (over)payment was made, so
    # applying the advance does not change the balance; it just consumes the
    # prepaid credit and settles the scheduled fortnight.
    if shortfall <= 0:
        loan.advance_balance = advance - advance_applied
        _sched.settle(loan, 1)   # settles the due fortnight; recomputes next_payment_date
        loan.save()
        stat = Statement.objects.create(
            owner=loan.owner, loanref=loan, uid=getattr(loan.owner, 'uid', None), luid=settings.LUID,
            ref=f'{loan.ref}SA{count}', type='ADVANCE',
            statement=f'Repayment settled from advance balance (K{advance_applied:.2f})',
            date=due, debit=0, credit=0,
            arrears=loan.total_arrears, balance=loan.total_outstanding,
        )
        logger.info("ADVANCE-APPLIED loan=%s due=%s applied=%s advance_balance=%s",
                    loan.ref, due, advance_applied, loan.advance_balance)
        msg = (f'Repayment due {due_str} covered by advance balance '
               f'(K{advance_applied:.2f} applied). No default recorded.')
        return stat, True, msg

    # ── Otherwise default on the (advance-netted) shortfall ─────────────────────
    interest = default_interest_for(loan, shortfall, cfg)

    # Ledger updates. Principal/interest of the repayment is already in
    # total_outstanding (charged at funding), so a default only adds the new
    # default interest to the balance and records the shortfall as arrears.
    loan.advance_balance = advance - advance_applied
    loan.total_arrears = _D(loan.total_arrears) + shortfall
    loan.default_interest_receivable = _D(loan.default_interest_receivable) + interest
    loan.total_outstanding = _D(loan.total_outstanding) + interest
    loan.number_of_defaults = (loan.number_of_defaults or 0) + 1
    loan.last_default_date = due
    loan.last_default_amount = shortfall
    loan.status = 'DEFAULTED'

    # Settle the now-defaulted scheduled fortnight (immutable schedule; cursor
    # advances). next_payment_date is derived.
    _sched.settle(loan, 1)
    loan.save()

    note = 'Loan Defaulted'
    if advance_applied > 0:
        note = f'Loan Defaulted (advance K{advance_applied:.2f} applied)'
    stat = Statement.objects.create(
        owner=loan.owner, loanref=loan, uid=getattr(loan.owner, 'uid', None), luid=settings.LUID,
        ref=f'{loan.ref}SD{count}', type='DEFAULT', statement=note, date=due,
        debit=0, credit=interest,
        default_amount=shortfall, default_interest=interest,
        arrears=loan.total_arrears, balance=loan.total_outstanding,
    )
    logger.info("DEFAULT created loan=%s due=%s shortfall=%s advance_applied=%s interest=%s",
                loan.ref, due, shortfall, advance_applied, interest)
    msg = f'Default created for repayment due {due_str}: shortfall K{shortfall:.2f}, default interest K{interest:.2f}.'
    return stat, True, msg


def charge_shortfall(loan, shortfall, date):
    """Charge a default for a partial-payment shortfall: default interest on the
    unpaid portion, the shortfall added to arrears, and a DEFAULT statement line.

    Interest is always charged on the shortfall itself (the client paid the rest),
    independent of the SHORTFALL/FULL setting which governs fully-missed payments.
    The caller must hold the row lock / transaction.
    """
    from django.conf import settings
    from admin1.models import get_loan_config, calc_default_interest
    from loan.models import Statement

    shortfall = _money(shortfall)
    if shortfall <= 0:
        return None
    cfg = get_loan_config()
    interest = _money(calc_default_interest(
        cfg.get('default_interest_rate') or 0,
        cfg.get('default_interest_type', 'PERCENTAGE'),
        shortfall,
    ))

    loan.total_arrears = _D(loan.total_arrears) + shortfall
    loan.default_interest_receivable = _D(loan.default_interest_receivable) + interest
    loan.total_outstanding = _D(loan.total_outstanding) + interest
    loan.number_of_defaults = (loan.number_of_defaults or 0) + 1
    loan.last_default_date = date
    loan.last_default_amount = shortfall
    loan.status = 'DEFAULTED'

    count = Statement.objects.filter(loanref=loan).count() + 1
    stat = Statement.objects.create(
        owner=loan.owner, loanref=loan, uid=getattr(loan.owner, 'uid', None), luid=settings.LUID,
        ref=f'{loan.ref}SD{count}', type='DEFAULT', statement='Repayment Shortfall Default',
        date=date, debit=0, credit=interest,
        default_amount=shortfall, default_interest=interest,
        arrears=loan.total_arrears, balance=loan.total_outstanding,
    )
    logger.info("SHORTFALL-DEFAULT loan=%s shortfall=%s interest=%s", loan.ref, shortfall, interest)
    return stat


def record_advance(loan, surplus, date, owner):
    """Record an over-payment surplus as a separate Advance Payment statement
    line and add it to the loan's running advance balance."""
    from django.conf import settings
    from loan.models import Statement

    surplus = _D(surplus)
    if surplus <= 0:
        return None
    loan.advance_balance = _D(loan.advance_balance) + surplus
    loan.total_advance_payment = _D(loan.total_advance_payment) + surplus
    loan.last_advance_payment_amount = surplus
    loan.last_advance_payment_date = date
    loan.number_of_advance_payments = (loan.number_of_advance_payments or 0) + 1

    count = Statement.objects.filter(loanref=loan).count() + 1
    stat = Statement.objects.create(
        owner=owner, loanref=loan, uid=getattr(owner, 'uid', None), luid=settings.LUID,
        ref=f'{loan.ref}SA{count}', type='ADVANCE', statement='Advance Payment', date=date,
        debit=surplus, credit=0,
        arrears=loan.total_arrears, balance=loan.total_outstanding,
    )
    logger.info("ADVANCE recorded loan=%s surplus=%s advance_balance=%s", loan.ref, surplus, loan.advance_balance)
    return stat
