"""Generic reversal of a posted loan transaction (payment / advance / default).

Used by the Django site-administration delete hooks (loan/admin.py): deleting a
Payment or a PAYMENT/ADVANCE/DEFAULT Statement reverses the WHOLE transaction —
the payment row, its sibling statement rows, and every loan-field effect — so
the loan account returns to its state before that transaction was posted.

The reversal is reconstructed from the ledger itself (the same approach as
``manage.py reverse_alesco_run``): the PAYMENT statement records how the amount
was split (principal/interest/default collected), the ADVANCE statement records
the surplus, and the DEFAULT statement records the shortfall and default
interest. The schedule cursor is then re-derived from the remaining statement
history (the ``reconcile_schedule_cursor`` rule) so the next payment date is
always consistent with what is left.
"""
import datetime
import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)

_D = lambda v: Decimal(str(v or 0))

# Statement types that represent money-movement transactions this module can
# reverse. FUNDING / OTHER / REFINANCE statements are structural and are NOT
# reversed (plain delete applies to them).
REVERSIBLE_TYPES = ('PAYMENT', 'ADVANCE', 'DEFAULT')

# How close together (in time) rows must have been written to count as one
# transaction group. All posting flows write their rows in a single request.
_GROUP_WINDOW = datetime.timedelta(minutes=10)


class ReversalError(Exception):
    """Raised when a transaction cannot be safely reversed."""


def _sibling_statements(loan, date, anchor_created, exclude_pk=None):
    from loan.models import Statement
    qs = Statement.objects.filter(loanref=loan, date=date, type__in=REVERSIBLE_TYPES)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    out = []
    for s in qs:
        if anchor_created and s.created_at and abs(s.created_at - anchor_created) > _GROUP_WINDOW:
            continue
        out.append(s)
    return out


def resolve_group(payment=None, statement=None):
    """Resolve the full transaction group (payment, [sp], [sa], [sd]) from
    either side. Returns dict with keys loan/payment/sp/sa/sd."""
    from loan.models import Payment

    if payment is None and statement is None:
        raise ReversalError('Nothing to reverse.')

    if statement is not None and statement.type not in REVERSIBLE_TYPES:
        if statement.type == 'COMPLETE PAYMENT':
            raise ReversalError('Completion payments cannot be auto-reversed (the payoff wiped the '
                                'receivable split). Correct this loan manually.')
        raise ReversalError(f'{statement.type} statements are structural and are not auto-reversed; '
                            'delete refused. Remove the row manually if you are sure.')

    loan = (payment.loanref if payment is not None else statement.loanref)
    if loan is None:
        return {'loan': None, 'payment': payment, 'sp': None, 'sa': None,
                'sd': statement if statement is not None else None}

    if payment is not None:
        anchor_date, anchor_created = payment.date, payment.created_at
        stmts = _sibling_statements(loan, anchor_date, anchor_created)
    else:
        anchor_date, anchor_created = statement.date, statement.created_at
        stmts = [statement] + _sibling_statements(loan, anchor_date, anchor_created,
                                                  exclude_pk=statement.pk)
        # find the payment row written in the same window
        payment = None
        for p in Payment.objects.filter(loanref=loan, date=anchor_date):
            if anchor_created and p.created_at and abs(p.created_at - anchor_created) > _GROUP_WINDOW:
                continue
            payment = p
            break

    sp = next((s for s in stmts if s.type == 'PAYMENT'), None)
    sa = next((s for s in stmts if s.type == 'ADVANCE'), None)
    sd = next((s for s in stmts if s.type == 'DEFAULT'), None)
    return {'loan': loan, 'payment': payment, 'sp': sp, 'sa': sa, 'sd': sd}


def _has_imported_history(loan):
    """Refinanced / imported-history loans: cursor cannot be derived by
    counting statement dates (they carry the predecessor's rows)."""
    from loan.models import Statement
    if Statement.objects.filter(loanref=loan, type='REFINANCE').exists():
        return True
    earliest = Statement.objects.filter(
        loanref=loan, type__in=['PAYMENT', 'DEFAULT']).order_by('date').values_list('date', flat=True).first()
    return bool(earliest and loan.repayment_start_date
                and earliest < loan.repayment_start_date - datetime.timedelta(days=21))


def reverse_group(group):
    """Reverse the transaction group and delete its rows. Returns a summary
    string. Caller gets a ReversalError when it cannot be done safely."""
    from loan.models import Payment, Statement
    from loan import schedule as _sched

    loan, payment, sp, sa, sd = (group['loan'], group['payment'],
                                 group['sp'], group['sa'], group['sd'])

    # Orphan rows (no loan, or a payment that never produced statements):
    # nothing was posted to a ledger, plain delete is the correct "reversal".
    if loan is None or (sp is None and sa is None and sd is None):
        if payment is not None:
            payment.delete()
        for s in (sp, sa, sd):
            if s is not None:
                s.delete()
        return 'Orphan record removed (no ledger effect existed).'

    if (loan.funded_category or '') == 'COMPLETED':
        raise ReversalError(f'{loan.ref} is COMPLETED — reversing entries on a completed loan '
                            'must be done manually.')

    with transaction.atomic():
        locked = type(loan).objects.select_for_update().get(pk=loan.pk)
        settle_events = 0

        if sp is not None:
            amount = _D(payment.amount) if payment is not None else _D(sp.debit) + _D(sa.debit if sa else 0)
            locked.principal_loan_receivable = _D(locked.principal_loan_receivable) + _D(sp.principal_collected)
            locked.principal_loan_paid = _D(locked.principal_loan_paid) - _D(sp.principal_collected)
            locked.ordinary_interest_receivable = _D(locked.ordinary_interest_receivable) + _D(sp.interest_collected)
            locked.interest_paid = _D(locked.interest_paid) - _D(sp.interest_collected)
            locked.default_interest_receivable = _D(locked.default_interest_receivable) + _D(sp.default_interest_collected)
            locked.default_interest_paid = _D(locked.default_interest_paid) - _D(sp.default_interest_collected)
            locked.total_paid = _D(locked.total_paid) - amount
            locked.total_outstanding = _D(locked.total_outstanding) + amount
            locked.number_of_repayments = max(0, (locked.number_of_repayments or 0) - 1)
            settle_events += 1
            # a plain repayment may have consumed arrears — the previous
            # statement's arrears column is the authoritative prior value
            if sd is None:
                prev = Statement.objects.filter(loanref=locked, pk__lt=sp.pk).order_by('-pk').first()
                if prev is not None and _D(prev.arrears) != _D(locked.total_arrears):
                    locked.total_arrears = _D(prev.arrears)

        if sa is not None:
            surplus = _D(sa.debit)
            locked.advance_balance = _D(locked.advance_balance) - surplus
            locked.total_advance_payment = _D(locked.total_advance_payment) - surplus
            locked.number_of_advance_payments = max(0, (locked.number_of_advance_payments or 0) - 1)
            if locked.advance_balance < 0:
                locked.advance_balance = Decimal('0')

        if sd is not None:
            locked.total_arrears = _D(locked.total_arrears) - _D(sd.default_amount)
            if locked.total_arrears < 0:
                locked.total_arrears = Decimal('0')
            locked.default_interest_receivable = _D(locked.default_interest_receivable) - _D(sd.default_interest)
            locked.total_outstanding = _D(locked.total_outstanding) - _D(sd.default_interest)
            locked.number_of_defaults = max(0, (locked.number_of_defaults or 0) - 1)
            if sp is None:
                settle_events += 1  # engine missed-payment default settles one fortnight

        # delete the group rows first, then re-derive the cursor from what is left
        refs = []
        for s in (sp, sa, sd):
            if s is not None:
                refs.append(f'{s.type} stmt {s.pk}')
                s.delete()
        if payment is not None:
            refs.append(f'payment {payment.pk}')
            payment.delete()

        if _has_imported_history(locked):
            _sched.unsettle(locked, settle_events)
        else:
            n = int(locked.number_of_fortnights or 0)
            dates = Statement.objects.filter(
                loanref=locked, type__in=['PAYMENT', 'DEFAULT']).values_list('date', flat=True)
            locked.fortnights_settled = min(len({d for d in dates if d}), n) if n else 0
            _sched.recompute_next_payment_date(locked)

        # cosmetic "last …" fields from the remaining history
        prev_pay = Payment.objects.filter(loanref=locked).order_by('-pk').first()
        locked.last_repayment_amount = _D(prev_pay.amount) if prev_pay else Decimal('0')
        locked.last_repayment_date = prev_pay.date if prev_pay else None
        if sa is not None:
            prev_adv = Payment.objects.filter(loanref=locked, type='ADVANCE PAYMENT').order_by('-pk').first()
            locked.last_advance_payment_amount = _D(prev_adv.amount) if prev_adv else Decimal('0')
            locked.last_advance_payment_date = prev_adv.date if prev_adv else None
        if sd is not None:
            prev_sd = Statement.objects.filter(loanref=locked, type='DEFAULT').order_by('-pk').first()
            locked.last_default_amount = _D(prev_sd.default_amount) if prev_sd else Decimal('0')
            locked.last_default_date = prev_sd.date if prev_sd else None

        locked.status = 'DEFAULTED' if _D(locked.total_arrears) > 0 else 'RUNNING'
        if _D(locked.total_arrears) <= 0:
            locked.days_in_default = 0
        locked.save()

    logger.info("ADMIN-REVERSAL loan=%s removed=%s", locked.ref, ', '.join(refs))
    return (f'{locked.ref}: transaction reversed ({", ".join(refs)}); '
            f'outstanding K{locked.total_outstanding}, arrears K{locked.total_arrears}, '
            f'next payment {locked.next_payment_date}.')


def reverse_payment(payment):
    return reverse_group(resolve_group(payment=payment))


def reverse_statement(statement):
    return reverse_group(resolve_group(statement=statement))
