"""Reset stale loan statuses: funded loans marked DEFAULTED that have no current
default indicator (no arrears, no defaults, no default interest) are set back to
RUNNING, so the loan list and loan detail page agree.

Defaults to DRY RUN. Pass --execute to apply.

    python manage.py sync_loan_status            # dry run
    python manage.py sync_loan_status --execute  # apply
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Reset funded loans wrongly marked DEFAULTED (no arrears/defaults/default interest) back to RUNNING.'

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true', help='Apply changes (otherwise dry run).')

    def handle(self, *args, **opts):
        from loan.models import Loan
        stale = Loan.objects.filter(
            category='FUNDED', status='DEFAULTED',
            total_arrears__lte=0, number_of_defaults=0, default_interest_receivable__lte=0,
        )
        refs = list(stale.values_list('ref', flat=True))
        self.stdout.write(self.style.WARNING(f'{len(refs)} stale DEFAULTED loan(s): {", ".join(refs) or "none"}'))
        if not refs:
            return
        if not opts['execute']:
            self.stdout.write(self.style.NOTICE('DRY RUN — pass --execute to set these to RUNNING.'))
            return
        updated = stale.update(status='RUNNING')
        self.stdout.write(self.style.SUCCESS(f'Set {updated} loan(s) to RUNNING.'))
