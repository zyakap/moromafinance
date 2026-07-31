"""Regenerate Repayment Dates — shared between the admin and staff portals.

The form shows the next repayment date, the remaining terms and the frequency
(fortnightly default / weekly / monthly). Regenerating keeps the settled
history, rebuilds the unsettled dates from the chosen start at the chosen
frequency, and leaves the cursor pointing at the new next repayment date.
"""
import datetime
import logging

from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404

from loan.models import Loan, Statement
from loan import schedule as sched

logger = logging.getLogger(__name__)

PORTALS = {
    'admin': {'base_template': 'admin_base.html', 'url_loan': 'view_loan'},
    'staff': {'base_template': 'staff_base.html', 'url_loan': 'view_loan_staff'},
}


def regenerate_schedule(request, loan_ref, portal):
    cfg = PORTALS[portal]
    loan = get_object_or_404(Loan, ref=loan_ref)

    if loan.get_repayment_amounts():
        messages.error(request, f'{loan.ref} has per-fortnight custom amounts (concurrent refinance) — '
                                'its schedule cannot be regenerated with this tool.', extra_tags='danger')
        return redirect(cfg['url_loan'], loan.ref)
    if (loan.funded_category or '') in ('COMPLETED', 'ARCHIVED'):
        messages.error(request, f'{loan.ref} is {loan.funded_category} — nothing to regenerate.', extra_tags='danger')
        return redirect(cfg['url_loan'], loan.ref)

    settled = sched.settled_count(loan)
    remaining_now = max(1, sched.total_fortnights(loan) - settled)

    if request.method == 'POST':
        errors = []
        try:
            next_date = datetime.date.fromisoformat((request.POST.get('next_date') or '').strip())
        except ValueError:
            next_date = None
            errors.append('Enter a valid next repayment date.')
        try:
            remaining = int(request.POST.get('remaining') or 0)
            if remaining < 1:
                errors.append('Remaining terms must be at least 1.')
        except (TypeError, ValueError):
            remaining = 0
            errors.append('Remaining terms must be a whole number.')
        frequency = request.POST.get('frequency') or 'FORTNIGHTLY'
        if frequency not in sched.FREQUENCY_CHOICES:
            errors.append('Choose a valid frequency.')

        if errors:
            for e in errors:
                messages.error(request, e, extra_tags='danger')
        else:
            with transaction.atomic():
                locked = Loan.objects.select_for_update().get(pk=loan.pk)
                old_next = locked.next_payment_date
                dates = sched.regenerate(locked, next_date, remaining, frequency)
                locked.save()
                cnt = Statement.objects.filter(loanref=locked).count() + 1
                Statement.objects.create(
                    owner=locked.owner, loanref=locked, ref=f'{locked.ref}RG{cnt}', type='OTHER',
                    statement=(f'Repayment dates regenerated: {remaining} {frequency.lower()} term(s) '
                               f'from {next_date.isoformat()} (was next due {old_next})'),
                    date=datetime.date.today(), debit=0, credit=0,
                    arrears=locked.total_arrears, balance=locked.total_outstanding,
                    uid=getattr(locked.owner, 'uid', None),
                )
            logger.info('SCHEDULE-REGENERATED loan=%s next=%s remaining=%s freq=%s by=%s',
                        loan.ref, next_date, remaining, frequency,
                        getattr(request.user, 'email', '?'))
            messages.success(request,
                             f'Schedule regenerated: {remaining} {frequency.lower()} repayment(s) from '
                             f'{next_date.strftime("%d/%m/%Y")}; next repayment date is now '
                             f'{next_date.strftime("%d/%m/%Y")}, ending {dates[-1].strftime("%d/%m/%Y")}.',
                             extra_tags='info')
            return redirect(cfg['url_loan'], loan.ref)

    return render(request, 'loan/regenerate_schedule.html', {
        'nav': 'loans',
        'base_template': cfg['base_template'],
        'loan': loan,
        'back_url_name': cfg['url_loan'],
        'settled': settled,
        'initial_next': (loan.next_payment_date or datetime.date.today()).isoformat(),
        'initial_remaining': remaining_now,
        'frequencies': sched.FREQUENCY_CHOICES,
    })
