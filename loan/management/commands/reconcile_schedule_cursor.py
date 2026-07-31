"""Reconcile each active loan's immutable-schedule cursor with its real payment
history and rebuild its canonical schedule.

Why: the old pop-based schedule mutated ``repayment_dates`` in place and, when two
deductions landed close together, sometimes advanced only once — leaving
``next_payment_date`` a fortnight (or more) behind. The immutable-schedule
migration (0008) then derived ``fortnights_settled`` from that already-stale
``next_payment_date``, so the drift was preserved. The counter fields
(``number_of_repayments`` / statements) always tracked reality, so the true
progress is recoverable.

This command, for every FUNDED ACTIVE/DEFAULTED loan:
  * counts the fortnights actually accounted for = the number of distinct dates
    that carry a PAYMENT or DEFAULT statement (a short-payment default posts both
    on the same date, so it counts once; a pure missed-payment default counts once),
  * rebuilds ``repayment_dates`` as the canonical schedule from
    ``repayment_start_date`` (+14-day steps for ``number_of_fortnights``), and
  * sets ``fortnights_settled`` to that count and re-derives ``next_payment_date``.

Only loans whose cursor / next date / schedule actually change are written. Defaults
to DRY RUN; pass --execute to apply (a JSON restore manifest is written to backups/).

    python manage.py reconcile_schedule_cursor            # dry run
    python manage.py reconcile_schedule_cursor --execute  # apply
"""
import datetime
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from loan import schedule as _sched

_RESTORE_FIELDS = ['fortnights_settled', 'next_payment_date', 'repayment_dates']


def _settled_from_history(loan, Statement):
    dates = Statement.objects.filter(
        loanref=loan, type__in=['PAYMENT', 'DEFAULT']).values_list('date', flat=True)
    return len({d for d in dates if d})


def _canonical(loan):
    rs = loan.repayment_start_date
    n = int(loan.number_of_fortnights or 0)
    if not rs or n <= 0:
        return []
    return [rs + datetime.timedelta(days=14 * k) for k in range(n)]


class Command(BaseCommand):
    help = "Reconcile loan schedule cursors (fortnights_settled / next_payment_date) with actual payment history."

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true', help='Apply changes (otherwise dry run).')

    def handle(self, *args, **opts):
        from loan.models import Loan, Statement

        loans = Loan.objects.filter(
            category='FUNDED', funded_category__in=['ACTIVE', 'DEFAULTED']
        ).exclude(repayment_start_date__isnull=True).exclude(number_of_fortnights__isnull=True)

        planned = []          # (loan, new_settled, new_dates, new_next)
        advanced = behind = 0
        skipped_refi = []
        for loan in loans.iterator():
            n = int(loan.number_of_fortnights or 0)
            if n <= 0:
                continue
            # Refinanced loans carry the predecessor's statement history, so
            # counting PAYMENT/DEFAULT dates would advance the NEW schedule's
            # cursor for fortnights that belong to the old loan. Skip and list
            # them for manual review.
            earliest = Statement.objects.filter(
                loanref=loan, type__in=['PAYMENT', 'DEFAULT']).order_by('date').values_list('date', flat=True).first()
            if getattr(loan, 'custom_schedule', False):
                skipped_refi.append(loan.ref + ' (custom schedule)')
                continue
            if Statement.objects.filter(loanref=loan, type='REFINANCE').exists() or (
                earliest and loan.repayment_start_date
                and earliest < loan.repayment_start_date - datetime.timedelta(days=21)
            ):
                skipped_refi.append(loan.ref)
                continue
            new_settled = min(_settled_from_history(loan, Statement), n)
            new_dates = _canonical(loan)
            if not new_dates:
                continue
            new_next = new_dates[new_settled] if new_settled < n else None

            old_settled = int(loan.fortnights_settled or 0)
            old_next = loan.next_payment_date
            old_dates = loan.get_repayment_dates() or []
            new_dates_iso = [d.isoformat() for d in new_dates]
            if new_settled == old_settled and new_next == old_next and new_dates_iso == old_dates:
                continue
            if new_settled > old_settled:
                advanced += 1
            elif new_settled < old_settled:
                behind += 1
            planned.append((loan, new_settled, new_dates_iso, new_next))

        self.stdout.write(self.style.WARNING(
            f'{loans.count()} active/defaulted loans scanned; {len(planned)} need reconciliation '
            f'({advanced} cursor forward, {behind} cursor back).'))
        if skipped_refi:
            self.stdout.write(self.style.NOTICE(
                f'Skipped {len(skipped_refi)} refinanced loan(s) with imported history '
                f'(review manually): {", ".join(skipped_refi)}'))

        if not opts['execute']:
            for loan, ns, _, nn in planned[:60]:
                self.stdout.write(
                    f'  {loan.ref}: settled {loan.fortnights_settled}->{ns} | '
                    f'next {loan.next_payment_date}->{nn}')
            if len(planned) > 60:
                self.stdout.write(f'  ... and {len(planned) - 60} more.')
            self.stdout.write(self.style.NOTICE('Pass --execute to apply.'))
            return

        manifest = {'generated': datetime.datetime.now().isoformat(), 'loans_before': {}, 'loans_after': {}}
        with transaction.atomic():
            for loan, ns, nd_iso, nn in planned:
                locked = Loan.objects.select_for_update().get(pk=loan.pk)
                manifest['loans_before'][locked.ref] = {f: str(getattr(locked, f)) for f in _RESTORE_FIELDS}
                locked.repayment_dates = json.dumps(nd_iso)
                locked.fortnights_settled = ns
                _sched.recompute_next_payment_date(locked)
                locked.save(update_fields=['repayment_dates', 'fortnights_settled', 'next_payment_date'])
                manifest['loans_after'][locked.ref] = {f: str(getattr(locked, f)) for f in _RESTORE_FIELDS}

            os.makedirs(settings.BASE_DIR / 'backups', exist_ok=True)
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            path = settings.BASE_DIR / 'backups' / f'reconcile_schedule_cursor_{ts}.json'
            with open(path, 'w') as fh:
                json.dump(manifest, fh, indent=2)

        self.stdout.write(self.style.SUCCESS(
            f'Reconciled {len(planned)} loan(s). Restore manifest: {path}'))
