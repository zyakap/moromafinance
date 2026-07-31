"""Reverse a confirmed-before-snapshot-support Alesco pay run from the ledger.

For lines confirmed BEFORE AlescoPayLine.loan_snapshot existed, rollback_line()
refuses (no snapshot). This command reconstructs the reversal from the ledger
itself: the payment statement records the principal/interest/default splits,
the advance statement records the surplus, and the default statement records
the shortfall + default interest. It refuses any loan with activity after the
confirmation.

Dry-run by default; pass --execute to write. Optionally --delete-run to remove
the run afterwards (clean slate for re-upload).

    python manage.py reverse_alesco_run ALS6 --execute --delete-run
"""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from loan.models import AlescoPayRun, Payment, Statement


D = lambda v: Decimal(str(v or 0))


class Command(BaseCommand):
    help = 'Reverse all confirmed lines of an Alesco pay run using ledger records (pre-snapshot runs).'

    def add_arguments(self, parser):
        parser.add_argument('run_ref', help='AlescoPayRun ref, e.g. ALS6')
        parser.add_argument('--execute', action='store_true', help='Apply the changes (default is dry-run).')
        parser.add_argument('--delete-run', action='store_true', help='Delete the run after reversing (clean slate).')

    def handle(self, *args, **opts):
        run = AlescoPayRun.objects.filter(ref=opts['run_ref']).first()
        if not run:
            raise CommandError(f"No AlescoPayRun with ref {opts['run_ref']}")
        execute = opts['execute']
        self.stdout.write(f"Run {run.ref} (id={run.pk}) status={run.status} — "
                          f"{run.lines.filter(status='CONFIRMED').count()} confirmed line(s). "
                          f"{'EXECUTING' if execute else 'DRY-RUN'}")

        blocked = []
        plans = []
        for line in run.lines.filter(status='CONFIRMED').select_related('loanref', 'payment'):
            loan = line.loanref
            payment = line.payment
            if loan is None or payment is None:
                blocked.append(f'line {line.pk}: missing loan or payment record')
                continue
            # Guard: nothing may have happened on the loan after this confirm.
            if Payment.objects.filter(loanref=loan, created_at__gt=line.confirmed_at).exclude(pk=payment.pk).exists() or \
               Statement.objects.filter(loanref=loan, created_at__gt=line.confirmed_at).exists():
                blocked.append(f'line {line.pk} ({loan.ref}): later payments/statements exist')
                continue

            # Statements this confirmation created: same loan, created within
            # the confirm window (from just before payment.created_at up to
            # confirmed_at).
            window_start = payment.created_at - datetime.timedelta(seconds=30)
            stmts = list(Statement.objects.filter(
                loanref=loan,
                created_at__gte=window_start,
                created_at__lte=line.confirmed_at + datetime.timedelta(seconds=5),
            ).order_by('pk'))
            sp = [s for s in stmts if s.type == 'PAYMENT']
            sa = [s for s in stmts if s.type == 'ADVANCE']
            sd = [s for s in stmts if s.type == 'DEFAULT']
            if len(sp) != 1 or len(sa) > 1 or len(sd) > 1 or len(stmts) != len(sp) + len(sa) + len(sd):
                blocked.append(f'line {line.pk} ({loan.ref}): unexpected statement set '
                               f'{[(s.pk, s.type) for s in stmts]} — reverse manually')
                continue
            plans.append((line, loan, payment, sp[0], sa[0] if sa else None, sd[0] if sd else None))

        if blocked:
            for b in blocked:
                self.stdout.write(self.style.ERROR(f'BLOCKED: {b}'))
            raise CommandError('Aborting — nothing was changed.')

        for line, loan, payment, sp, sa, sd in plans:
            self._reverse(line, loan, payment, sp, sa, sd, execute)

        if execute:
            if opts['delete_run']:
                run.delete()
                self.stdout.write(self.style.SUCCESS(f'Run {opts["run_ref"]} deleted — clean slate.'))
            else:
                from loan.alesco import _refresh_run_status
                _refresh_run_status(run)
                self.stdout.write(self.style.SUCCESS(f'Run kept; status now {run.status}.'))
        else:
            self.stdout.write('Dry-run complete. Re-run with --execute to apply'
                              + (' and --delete-run to remove the run.' if not opts['delete_run'] else '.'))

    def _reverse(self, line, loan, payment, sp, sa, sd, execute):
        w = self.stdout.write
        w(f'\n=== {loan.ref} (line {line.pk}) payment {payment.pk} K{payment.amount} [{payment.type}]')

        def show(field, before, after):
            w(f'    {field:32s} {before} -> {after}')

        amount = D(payment.amount)
        new = {}
        # 1) Reverse the payment statement splits.
        new['principal_loan_receivable'] = D(loan.principal_loan_receivable) + D(sp.principal_collected)
        new['principal_loan_paid'] = D(loan.principal_loan_paid) - D(sp.principal_collected)
        new['ordinary_interest_receivable'] = D(loan.ordinary_interest_receivable) + D(sp.interest_collected)
        new['interest_paid'] = D(loan.interest_paid) - D(sp.interest_collected)
        new['default_interest_receivable'] = D(loan.default_interest_receivable) + D(sp.default_interest_collected)
        new['default_interest_paid'] = D(loan.default_interest_paid) - D(sp.default_interest_collected)
        new['total_paid'] = D(loan.total_paid) - amount
        new['total_outstanding'] = D(loan.total_outstanding) + amount
        new['number_of_repayments'] = (loan.number_of_repayments or 1) - 1
        new['fortnights_settled'] = (loan.fortnights_settled or 1) - 1

        # 2) Reverse the advance surplus, if any.
        if sa is not None:
            surplus = D(sa.debit)
            new['advance_balance'] = D(loan.advance_balance) - surplus
            new['total_advance_payment'] = D(loan.total_advance_payment) - surplus
            new['number_of_advance_payments'] = (loan.number_of_advance_payments or 1) - 1

        # 3) Reverse the shortfall default, if any.
        if sd is not None:
            new['total_arrears'] = D(loan.total_arrears) - D(sd.default_amount)
            new['default_interest_receivable'] = new['default_interest_receivable'] - D(sd.default_interest)
            new['total_outstanding'] = new['total_outstanding'] - D(sd.default_interest)
            new['number_of_defaults'] = (loan.number_of_defaults or 1) - 1
        else:
            # A plain repayment may have consumed arrears: prior statement's
            # arrears column is the authoritative pre-confirm value.
            prev = Statement.objects.filter(loanref=loan, pk__lt=sp.pk).order_by('-pk').first()
            prev_arrears = D(prev.arrears) if prev else D(loan.total_arrears)
            if prev_arrears != D(loan.total_arrears):
                new['total_arrears'] = prev_arrears

        # 4) Cosmetic "last …" fields from the remaining history.
        prev_pay = Payment.objects.filter(loanref=loan).exclude(pk=payment.pk).order_by('-pk').first()
        new['last_repayment_amount'] = D(prev_pay.amount) if prev_pay else D(0)
        new['last_repayment_date'] = prev_pay.date if prev_pay else None
        if sa is not None:
            prev_sa = Statement.objects.filter(loanref=loan, type='ADVANCE', pk__lt=sa.pk).order_by('-pk').first()
            new['advance_payment_surplus'] = D(prev_sa.debit) if prev_sa else D(0)
            prev_adv_pay = Payment.objects.filter(loanref=loan, type='ADVANCE PAYMENT').exclude(pk=payment.pk).order_by('-pk').first()
            new['last_advance_payment_amount'] = D(prev_adv_pay.amount) if prev_adv_pay else D(0)
            new['last_advance_payment_date'] = prev_adv_pay.date if prev_adv_pay else None
        if sd is not None:
            prev_sd = Statement.objects.filter(loanref=loan, type='DEFAULT', pk__lt=sd.pk).order_by('-pk').first()
            new['last_default_amount'] = D(prev_sd.default_amount) if prev_sd else D(0)
            new['last_default_date'] = prev_sd.date if prev_sd else None

        # 5) Status follows the restored arrears.
        arrears_after = new.get('total_arrears', D(loan.total_arrears))
        new['status'] = 'DEFAULTED' if arrears_after > 0 else 'RUNNING'
        if arrears_after <= 0:
            new['days_in_default'] = 0

        for f in sorted(new):
            show(f, getattr(loan, f), new[f])
        dels = [f'stmt {sp.pk} (PAYMENT)'] \
             + ([f'stmt {sa.pk} (ADVANCE)'] if sa else []) \
             + ([f'stmt {sd.pk} (DEFAULT)'] if sd else []) \
             + [f'payment {payment.pk}']
        w(f'    DELETE: {", ".join(dels)}')

        if not execute:
            return
        from loan import schedule as _sched
        with transaction.atomic():
            locked = type(loan).objects.select_for_update().get(pk=loan.pk)
            fs = new.pop('fortnights_settled')
            for f, v in new.items():
                setattr(locked, f, v)
            locked.save()
            # unsettle recomputes next_payment_date from the immutable schedule.
            _sched.unsettle(locked, (locked.fortnights_settled or 0) - fs)
            locked.save()
            sp.delete()
            if sa is not None:
                sa.delete()
            if sd is not None:
                sd.delete()
            payment.delete()
            line.payment = None
            line.status = 'PENDING'
            line.confirmed_at = None
            line.confirmed_by = None
            line.save(update_fields=['payment', 'status', 'confirmed_at', 'confirmed_by'])
        self.stdout.write(self.style.SUCCESS(f'    REVERSED {loan.ref}'))
