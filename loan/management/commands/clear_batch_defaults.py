"""Reverse DEFAULT statements that were auto-created in a given local-date window
and recompute the affected loans' balances.

Built for the 2026-06-21 incident where the old (buggy) auto_run_defaults batch
created ~50 defaults across ~49 loans. Reversing a default:
  * subtracts its default interest from total_outstanding and
    default_interest_receivable,
  * subtracts its default amount (shortfall) from total_arrears,
  * restores its repayment date to the schedule,
  * deletes the statement,
and then recomputes per-loan default count / status / next payment date.

Defaults to DRY RUN. Pass --execute to apply. Writes a JSON restore manifest to
backups/ when executing.

    python manage.py clear_batch_defaults --date 2026-06-21            # dry run
    python manage.py clear_batch_defaults --date 2026-06-21 --execute  # apply
"""
import datetime
import json
import os
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

_D = lambda v: Decimal(str(v or 0))
_LOAN_FIELDS = [
    'total_outstanding', 'default_interest_receivable', 'total_arrears',
    'number_of_defaults', 'status', 'last_default_date', 'last_default_amount',
    'next_payment_date', 'repayment_dates',
]


class Command(BaseCommand):
    help = 'Reverse auto-created DEFAULT statements from a local-date window and recompute loan balances.'

    def add_arguments(self, parser):
        parser.add_argument('--date', default='2026-06-21', help='Local date (YYYY-MM-DD) the defaults were created.')
        parser.add_argument('--execute', action='store_true', help='Apply changes (otherwise dry run).')

    def handle(self, *args, **opts):
        from loan.models import Statement, Loan

        y, m, d = map(int, opts['date'].split('-'))
        tz = timezone.get_default_timezone()
        start = timezone.make_aware(datetime.datetime(y, m, d, 0, 0, 0), tz)
        end = start + datetime.timedelta(days=1)

        batch = Statement.objects.filter(type='DEFAULT', created_at__gte=start, created_at__lt=end)
        loan_ids = sorted(set(batch.values_list('loanref', flat=True)))
        total = batch.count()

        self.stdout.write(self.style.WARNING(
            f'{total} DEFAULT statements created on {opts["date"]} (local) across {len(loan_ids)} loan(s).'))

        if total == 0:
            return

        if not opts['execute']:
            self.stdout.write('--- DRY RUN (no changes). Per-loan plan: ---')
            for lid in loan_ids:
                loan = Loan.objects.get(pk=lid)
                bad = batch.filter(loanref=loan)
                di = sum((_D(s.default_interest if s.default_interest is not None else s.credit) for s in bad), Decimal('0'))
                sf = sum((_D(s.default_amount) for s in bad), Decimal('0'))
                self.stdout.write(
                    f'  {loan.ref}: reverse {bad.count()} default(s) | -interest {di} | -arrears {sf} '
                    f'| outstanding {loan.total_outstanding} -> {_D(loan.total_outstanding) - di} '
                    f'| defaults {loan.number_of_defaults} -> {max(0, (loan.number_of_defaults or 0) - bad.count())}')
            self.stdout.write(self.style.NOTICE('Pass --execute to apply.'))
            return

        manifest = {'date': opts['date'], 'reversed_statements': [], 'loans_before': {}, 'loans_after': {}}
        reversed_count = 0

        with transaction.atomic():
            for lid in loan_ids:
                loan = Loan.objects.select_for_update().get(pk=lid)
                manifest['loans_before'][loan.ref] = {f: str(getattr(loan, f)) for f in _LOAN_FIELDS}

                bad = list(Statement.objects.filter(
                    type='DEFAULT', created_at__gte=start, created_at__lt=end, loanref=loan))
                readded = []
                for s in bad:
                    di = _D(s.default_interest if s.default_interest is not None else s.credit)
                    sf = _D(s.default_amount)
                    loan.total_outstanding = _D(loan.total_outstanding) - di
                    loan.default_interest_receivable = max(Decimal('0'), _D(loan.default_interest_receivable) - di)
                    loan.total_arrears = _D(loan.total_arrears) - sf
                    if s.date:
                        readded.append(s.date.isoformat())
                    manifest['reversed_statements'].append({
                        'loan': loan.ref, 'ref': s.ref, 'date': s.date.isoformat() if s.date else None,
                        'default_interest': str(di), 'default_amount': str(sf),
                        'created_at': s.created_at.isoformat() if s.created_at else None,
                    })
                    s.delete()
                    reversed_count += 1

                # Roll the immutable-schedule cursor back one slot per reversed
                # default so those fortnights become due again (the schedule
                # itself is not mutated); next_payment_date is re-derived.
                from loan import schedule as _sched
                _sched.unsettle(loan, len(bad))

                if _D(loan.total_arrears) < 0:
                    loan.total_arrears = Decimal('0')

                remaining_defs = Statement.objects.filter(loanref=loan, type='DEFAULT')
                if not remaining_defs.exists():
                    # No defaults left at all -> clean reset.
                    loan.number_of_defaults = 0
                    loan.total_arrears = Decimal('0')
                    loan.default_interest_receivable = Decimal('0')
                    loan.last_default_date = None
                    loan.last_default_amount = 0
                    if loan.status == 'DEFAULTED':
                        loan.status = 'RUNNING'
                else:
                    last = remaining_defs.order_by('-date').first()
                    loan.number_of_defaults = remaining_defs.count()
                    loan.last_default_date = last.date

                loan.save()
                manifest['loans_after'][loan.ref] = {f: str(getattr(loan, f)) for f in _LOAN_FIELDS}

            os.makedirs(settings.BASE_DIR / 'backups', exist_ok=True)
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            path = settings.BASE_DIR / 'backups' / f'default_cleanup_manifest_{ts}.json'
            with open(path, 'w') as fh:
                json.dump(manifest, fh, indent=2)

        self.stdout.write(self.style.SUCCESS(
            f'Reversed {reversed_count} default(s) across {len(loan_ids)} loan(s). Manifest: {path}'))
