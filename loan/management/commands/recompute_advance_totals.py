"""Recompute each loan's total_advance_payment from its actual "Advance Payment"
statement lines. Fixes loans where the old code added the FULL payment (e.g.
K1,550) instead of the advance surplus (e.g. K587.93).

advance_balance (the live refundable credit) is left as-is — it was already
tracked correctly from the surplus.

Defaults to DRY RUN; pass --execute to apply.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum


class Command(BaseCommand):
    help = "Recompute total_advance_payment from the Advance Payment statement lines."

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true')

    def handle(self, *args, **opts):
        from loan.models import Loan, Statement

        changed = []
        loan_ids = Statement.objects.filter(statement='Advance Payment').values_list('loanref', flat=True).distinct()
        for loan in Loan.objects.filter(pk__in=list(loan_ids)):
            correct = Statement.objects.filter(loanref=loan, statement='Advance Payment').aggregate(
                s=Sum('debit'))['s'] or Decimal('0.00')
            current = loan.total_advance_payment or Decimal('0.00')
            if correct != current:
                changed.append((loan.ref, current, correct))

        self.stdout.write(self.style.WARNING(f'{len(changed)} loan(s) with an incorrect total_advance_payment.'))
        for ref, cur, cor in changed[:60]:
            self.stdout.write(f'  {ref}: {cur} -> {cor}')

        if not opts['execute']:
            self.stdout.write(self.style.NOTICE('DRY RUN — pass --execute to apply.'))
            return

        for ref, cur, cor in changed:
            Loan.objects.filter(ref=ref).update(total_advance_payment=cor)
        self.stdout.write(self.style.SUCCESS(f'Updated {len(changed)} loan(s).'))
