"""Rebuild loan money fields from the statement ledger (replay).

Why: DEFAULT/PAYMENT statements deleted in the site admin BEFORE the
delete-reversal hooks were live left loans carrying arrears / default interest /
default counts / cursor positions for entries that no longer exist. The
remaining statements are the source of truth, so every affected field can be
re-derived by replaying them in order:

    PAYMENT / ADVANCE / COMPLETE PAYMENT  arrears = max(0, arrears - debit)
    DEFAULT                               arrears += default_amount,
                                          interest += default_interest, count += 1

The schedule cursor is re-derived with the reconcile rule (distinct dates
carrying a PAYMENT/DEFAULT statement) and next_payment_date recomputed.
Outstanding is checked against the identity
``total_loan_amount - total_paid + total default interest`` and only corrected
when the loan has no structural debit rows (REFINANCE / OTHER debits) that
would break the identity.

Dry-run by default; --execute applies (restore manifest written to backups/).
Refinanced / imported-history loans are skipped and listed (their ledgers carry
the predecessor's rows and cannot be replayed).
"""
import datetime
import json
import os
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

D = lambda v: Decimal(str(v or 0))

_FIELDS = ['total_arrears', 'default_interest_receivable', 'number_of_defaults',
           'last_default_date', 'last_default_amount', 'status', 'days_in_default',
           'fortnights_settled', 'next_payment_date', 'total_outstanding']


class Command(BaseCommand):
    help = 'Rebuild loan arrears/default/cursor fields by replaying the statement ledger.'

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true', help='Apply changes (default: dry run).')
        parser.add_argument('--ref', help='Limit to a single loan ref.')

    def handle(self, *args, **opts):
        from loan.models import Loan, Statement
        from loan import schedule as _sched

        loans = Loan.objects.filter(category='FUNDED', funded_category__in=['ACTIVE', 'DEFAULTED'])
        if opts.get('ref'):
            loans = loans.filter(ref=opts['ref'])

        from loan.models import Payment
        planned = []
        skipped = []
        for loan in loans.iterator():
            stmts = list(Statement.objects.filter(loanref=loan).order_by('pk'))
            # partial payments (process_default flow) do NOT consume arrears —
            # identify them by the linked Payment row's type
            partial_dates = set(Payment.objects.filter(
                loanref=loan, type='PARTIAL PAYMENT').values_list('date', flat=True))
            if not stmts:
                continue
            # refinance / imported history → replay invalid
            earliest = min((s.date for s in stmts if s.type in ('PAYMENT', 'DEFAULT') and s.date),
                           default=None)
            if any(s.type == 'REFINANCE' for s in stmts) or (
                earliest and loan.repayment_start_date
                and earliest < loan.repayment_start_date - datetime.timedelta(days=21)
            ):
                skipped.append(loan.ref)
                continue

            arrears = Decimal('0')
            d_total = Decimal('0')
            ndef = 0
            paid = Decimal('0')
            last_sd = None
            structural_debits = False
            for s in stmts:
                if s.type in ('PAYMENT', 'ADVANCE', 'COMPLETE PAYMENT'):
                    if not (s.type == 'PAYMENT' and s.date in partial_dates):
                        arrears = max(Decimal('0'), arrears - D(s.debit))
                    paid += D(s.debit)
                elif s.type == 'DEFAULT':
                    arrears += D(s.default_amount)
                    d_total += D(s.default_interest)
                    ndef += 1
                    last_sd = s
                elif D(s.debit) > 0:   # OTHER/adjustment debits break the identity
                    structural_debits = True

            new = {
                'total_arrears': arrears,
                'default_interest_receivable': max(Decimal('0'), d_total - D(loan.default_interest_paid)),
                'number_of_defaults': ndef,
                'last_default_date': last_sd.date if last_sd else None,
                'last_default_amount': D(last_sd.default_amount) if last_sd else Decimal('0'),
                'status': 'DEFAULTED' if arrears > 0 else 'RUNNING',
            }
            if arrears <= 0:
                new['days_in_default'] = 0
            # cursor: distinct PAYMENT/DEFAULT dates (reconcile rule)
            n = int(loan.number_of_fortnights or 0)
            dates = {s.date for s in stmts if s.type in ('PAYMENT', 'DEFAULT') and s.date}
            if n:
                new['fortnights_settled'] = min(len(dates), n)
            # outstanding: only correct when the discrepancy is EXACTLY the
            # default-interest leftover being removed here — a deleted PAYMENT
            # statement also breaks the identity and that case is ambiguous
            # (report-only via the summary at the end).
            if not structural_debits and D(loan.total_loan_amount) > 0:
                ident = D(loan.total_loan_amount) - paid + d_total
                out_gap = D(loan.total_outstanding) - ident
                dint_gap = D(loan.default_interest_receivable) - new['default_interest_receivable']
                if abs(out_gap) > Decimal('0.05'):
                    if abs(out_gap - dint_gap) <= Decimal('0.05'):
                        new['total_outstanding'] = ident
                    else:
                        new.setdefault('_report_only', {})['outstanding_gap'] = str(out_gap)

            report_only = new.pop('_report_only', None)
            changes = {f: (getattr(loan, f), v) for f, v in new.items()
                       if getattr(loan, f) != v and not (getattr(loan, f) is None and v is None)}
            # drop no-op numeric equalities (Decimal('0') vs 0 etc.)
            changes = {f: (a, b) for f, (a, b) in changes.items()
                       if not (isinstance(b, Decimal) and D(a) == b) and a != b}
            if not changes:
                # still verify next_payment_date derivation
                probe = _sched.build_schedule(loan)
                fs = new.get('fortnights_settled', loan.fortnights_settled or 0)
                want_next = probe[fs] if probe and fs < len(probe) else None
                if loan.next_payment_date == want_next:
                    continue
                changes = {'next_payment_date': (loan.next_payment_date, want_next)}
            planned.append((loan, new, changes, report_only))

        self.stdout.write(self.style.WARNING(
            f'{loans.count()} loans scanned; {len(planned)} need rebuilding; '
            f'{len(skipped)} refinance/imported skipped'
            + (f' ({", ".join(skipped)})' if skipped else '') + '.'))
        for loan, new, changes, report_only in planned:
            self.stdout.write(f'\n{loan.ref} [{loan.status}]')
            for f, (a, b) in sorted(changes.items()):
                self.stdout.write(f'    {f:30s} {a} -> {b}')
            if report_only:
                self.stdout.write(self.style.NOTICE(
                    f'    REVIEW MANUALLY: outstanding differs from ledger identity by '
                    f'K{report_only["outstanding_gap"]} (possible deleted PAYMENT statement) — not auto-fixed'))

        if not opts['execute']:
            self.stdout.write(self.style.NOTICE('Dry-run. Pass --execute to apply.'))
            return

        manifest = {'generated': datetime.datetime.now().isoformat(), 'before': {}, 'after': {}}
        from loan.models import Loan as _L
        with transaction.atomic():
            for loan, new, changes, _ro in planned:
                locked = _L.objects.select_for_update().get(pk=loan.pk)
                manifest['before'][locked.ref] = {f: str(getattr(locked, f)) for f in _FIELDS}
                for f, v in new.items():
                    setattr(locked, f, v)
                _sched.recompute_next_payment_date(locked)
                locked.save()
                manifest['after'][locked.ref] = {f: str(getattr(locked, f)) for f in _FIELDS}
        os.makedirs(settings.BASE_DIR / 'backups', exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = settings.BASE_DIR / 'backups' / f'rebuild_loan_fields_{ts}.json'
        with open(path, 'w') as fh:
            json.dump(manifest, fh, indent=2)
        self.stdout.write(self.style.SUCCESS(f'Rebuilt {len(planned)} loan(s). Manifest: {path}'))
