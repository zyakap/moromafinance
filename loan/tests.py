"""Tests for the loan money logic.

Run against an in-memory SQLite DB so they never touch the production database:

    DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
        python manage.py test loan

The DB-backed tests focus on the regressions fixed in the June 2026 audit:
  * process_default must add default interest to the receivable exactly once.
  * update_defaults must actually select RUNNING/DEFAULTED loans.
"""
import datetime
import json
from decimal import Decimal

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import SimpleTestCase, TestCase, override_settings
from django.test import RequestFactory


# --------------------------------------------------------------------------
# Pure-function tests (no database required)
# --------------------------------------------------------------------------
class CalcDefaultInterestTests(SimpleTestCase):
    def test_percentage_rate(self):
        from admin1.models import calc_default_interest
        self.assertEqual(calc_default_interest(20, 'PERCENTAGE', 100), Decimal('20'))

    def test_fixed_rate(self):
        from admin1.models import calc_default_interest
        self.assertEqual(calc_default_interest(15, 'FIXED', 100), Decimal('15'))

    def test_zero_rate(self):
        from admin1.models import calc_default_interest
        self.assertEqual(calc_default_interest(0, 'PERCENTAGE', 100), Decimal('0'))


class SafeJoinTests(SimpleTestCase):
    """The protected-media path join must never escape MEDIA_ROOT."""
    def test_traversal_is_contained(self):
        from moromafinance.media_views import _safe_join
        root = '/srv/uploads'
        for attack in ['../../etc/passwd', 'a/../../../../etc/passwd', '../secret']:
            result = _safe_join(root, attack)
            self.assertTrue(result == root or result.startswith(root + '/'),
                            f'{attack!r} escaped to {result!r}')

    def test_normal_path(self):
        from moromafinance.media_views import _safe_join
        self.assertEqual(_safe_join('/srv/uploads', 'doc.pdf'), '/srv/uploads/doc.pdf')


# --------------------------------------------------------------------------
# DB-backed regression tests
# --------------------------------------------------------------------------
def _attach_messages(request):
    setattr(request, 'session', {})
    setattr(request, '_messages', FallbackStorage(request))
    return request


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ProcessDefaultTests(TestCase):
    def setUp(self):
        from accounts.models import User, UserProfile
        from admin1.models import AdminSettings
        from loan.models import Loan, Statement

        # default_interest_rate is entered as a percentage (e.g. 20 == 20%) and
        # applied via calc_default_interest (rate/100 * base), consistent with the
        # admin form and the loan engine.
        AdminSettings.objects.create(
            settings_name='setting1',
            default_interest_rate=Decimal('20'),
            default_interest_type='PERCENTAGE',
            default_interest_base='SHORTFALL',
            default_interest_calculation_mercy_days=7,
        )

        user = User.objects.create_user(email='client@example.com', password='x')
        self.profile = UserProfile.objects.create(user=user, first_name='Test', last_name='Client',
                                                  email='client@example.com', uid='U1')
        self.loan = Loan.objects.create(
            ref='L1', uid='U1', owner=self.profile,
            repayment_amount=Decimal('100.00'),
            total_outstanding=Decimal('1000.00'),
            principal_loan_receivable=Decimal('1000.00'),
            ordinary_interest_receivable=Decimal('0.00'),
            default_interest_receivable=Decimal('0.00'),
            total_arrears=Decimal('0.00'),
            number_of_defaults=0,
            status='RUNNING',
            repayment_dates=json.dumps(['2026-12-31', '2027-01-14']),
        )
        self.stat = Statement.objects.create(owner=self.profile, loanref=self.loan,
                                             date=datetime.date(2026, 6, 20), uid='U1')

    def test_default_interest_added_once(self):
        """Regression for the double-add bug: a K100 shortfall at 20% must add
        exactly K20 to default_interest_receivable, not K40."""
        from loan.functions import process_default
        request = _attach_messages(RequestFactory().post('/'))

        process_default(request, self.loan, self.stat, Decimal('0.00'))

        self.loan.refresh_from_db()
        self.assertEqual(self.loan.default_interest_receivable, Decimal('20.00'))
        self.assertEqual(self.loan.number_of_defaults, 1)


class UpdateDefaultsFilterTests(TestCase):
    """Regression for the impossible AND filter: the selection used by
    update_defaults must include RUNNING and DEFAULTED loans, excluding
    COMPLETED ones."""
    def test_filter_selects_active_loans(self):
        from django.db.models import Q
        from loan.models import Loan
        Loan.objects.create(ref='R', status='RUNNING')
        Loan.objects.create(ref='D', status='DEFAULTED')
        Loan.objects.create(ref='C', status='COMPLETED')

        qs = (Loan.objects.filter(Q(status='RUNNING') | Q(status='DEFAULTED'))
              .exclude(status='COMPLETED').exclude(funded_category='COMPLETED'))
        refs = set(qs.values_list('ref', flat=True))
        self.assertEqual(refs, {'R', 'D'})


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class DoubleEntryGuardTests(TestCase):
    """A payment with the same loan+date+amount must be flagged as a duplicate
    and not recorded until confirmed; same date + different amount must ask the
    operator to confirm it is an additional payment."""
    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        from loan.models import Loan, Payment
        su = User.objects.create_user(email='staff@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, first_name='St', last_name='Aff', email='staff@x.com', uid='S1', category='STAFF')
        StaffProfile.objects.create(user=sp)
        cu = User.objects.create_user(email='cli@x.com', password='pw', is_active=True)
        self.cp = UserProfile.objects.create(user=cu, first_name='Cl', last_name='Ient', email='cli@x.com', uid='C1', category='CLIENT')
        self.loan = Loan.objects.create(ref='LMXGUARD1', uid='C1', owner=self.cp, repayment_amount=Decimal('320.69'),
                                        total_outstanding=Decimal('5000'), principal_loan_receivable=Decimal('5000'),
                                        status='RUNNING', repayment_dates=json.dumps(['2026-06-15', '2026-06-29']))
        Payment.objects.create(owner=self.cp, loanref=self.loan, date=datetime.date(2026, 6, 15),
                               amount=Decimal('320.69'), mode='PAYROLL DEDUCTION')
        self.client = Client()
        self.client.force_login(su)

    def _post(self, amount):
        return self.client.post(f'/loan/payment/{self.loan.ref}/',
                                {'date': '2026-06-15', 'amount': amount,
                                 'mode': 'PAYROLL DEDUCTION', 'statement': 'Alesco'})

    def test_duplicate_blocked_until_confirmed(self):
        from loan.models import Payment
        r = self._post('320.69')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Possible Duplicate')
        self.assertEqual(Payment.objects.filter(loanref=self.loan).count(), 1)

    def test_same_date_different_amount_asks_confirmation(self):
        r = self._post('400.00')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Another Payment Exists')


# --------------------------------------------------------------------------
# Phase 2 engine: defaults (earliest-missed, never-future, shortfall, advance)
# --------------------------------------------------------------------------
def _mk_default_settings(base='SHORTFALL', rate='20'):
    from admin1.models import AdminSettings
    AdminSettings.objects.create(
        settings_name='setting1', default_interest_rate=Decimal(rate),
        default_interest_type='PERCENTAGE', default_interest_base=base,
        default_interest_calculation_mercy_days=0)


def _mk_loan(dates, advance='0', amount='320.69'):
    from accounts.models import User, UserProfile
    from loan.models import Loan
    u = User.objects.create_user(email=f'eng{Loan.objects.count()}@x.com', password='x')
    p = UserProfile.objects.create(user=u, first_name='A', last_name='B', uid='U', email='e@x.com')
    return Loan.objects.create(
        ref=f'ENG{Loan.objects.count()}', owner=p, uid='U', repayment_amount=Decimal(amount),
        repayment_start_date=datetime.date(2026, 5, 28), number_of_fortnights=len(dates) or 1,
        total_outstanding=Decimal('5000'), total_arrears=Decimal('0'),
        advance_balance=Decimal(advance), status='RUNNING', repayment_dates=json.dumps(dates))


_TODAY = datetime.date(2026, 6, 20)


class DefaultEngineTests(TestCase):
    def test_refuses_future_dated_default(self):
        _mk_default_settings()
        from loan.engine import create_default_for_loan
        loan = _mk_loan(['2026-06-25', '2026-07-09'])
        stat, ok, msg = create_default_for_loan(loan, today=_TODAY)
        self.assertFalse(ok)
        self.assertIsNone(stat)
        self.assertIn('not yet due', msg)

    def test_earliest_missed_first_then_stops_at_future(self):
        _mk_default_settings()
        from loan.engine import create_default_for_loan
        loan = _mk_loan(['2026-05-28', '2026-06-11', '2026-06-25'])
        s1, ok1, _ = create_default_for_loan(loan, today=_TODAY)
        self.assertEqual(s1.date, datetime.date(2026, 5, 28))
        self.assertEqual(s1.default_interest, Decimal('64.14'))   # 20% of 320.69
        loan.refresh_from_db()
        s2, ok2, _ = create_default_for_loan(loan, today=_TODAY)
        self.assertEqual(s2.date, datetime.date(2026, 6, 11))
        loan.refresh_from_db()
        s3, ok3, _ = create_default_for_loan(loan, today=_TODAY)  # 25 June is future
        self.assertFalse(ok3)
        self.assertEqual(loan.number_of_defaults, 2)

    def test_advance_nets_shortfall(self):
        _mk_default_settings()
        from loan.engine import create_default_for_loan
        loan = _mk_loan(['2026-06-11'], advance='79.31')
        s, ok, _ = create_default_for_loan(loan, today=_TODAY)
        self.assertEqual(s.default_amount, Decimal('241.38'))     # 320.69 - 79.31
        self.assertEqual(s.default_interest, Decimal('48.28'))    # 20% of 241.38
        loan.refresh_from_db()
        self.assertEqual(loan.advance_balance, Decimal('0.00'))

    def test_full_base_ignores_advance(self):
        _mk_default_settings(base='FULL')
        from loan.engine import create_default_for_loan
        loan = _mk_loan(['2026-06-11'], advance='79.31')
        s, ok, _ = create_default_for_loan(loan, today=_TODAY)
        self.assertEqual(s.default_interest, Decimal('64.14'))    # 20% of full 320.69

    def test_mercy_period_delays_batch_default(self):
        # Due 2026-06-11, today 2026-06-20 (9 days past due). With a 14-day
        # mercy period the batch classifier must not default it yet; with the
        # mercy elapsed (7 days) it must.
        _mk_default_settings()
        from loan.engine import create_default_for_loan
        loan = _mk_loan(['2026-06-11'])
        stat, ok, msg = create_default_for_loan(loan, today=_TODAY, mercy_days=14)
        self.assertFalse(ok)
        stat, ok, msg = create_default_for_loan(loan, today=_TODAY, mercy_days=7)
        self.assertTrue(ok)
        self.assertEqual(stat.date, datetime.date(2026, 6, 11))

    def test_mercy_zero_keeps_manual_behaviour(self):
        _mk_default_settings()
        from loan.engine import create_default_for_loan
        loan = _mk_loan(['2026-06-19'])   # 1 day past due
        stat, ok, _ = create_default_for_loan(loan, today=_TODAY)  # manual: no mercy
        self.assertTrue(ok)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AdvancePaymentSplitTests(TestCase):
    def test_overpayment_creates_separate_advance_line(self):
        from accounts.models import User, UserProfile
        from loan.models import Loan, Statement
        from loan.functions import process_advance_payment
        u = User.objects.create_user(email='adv@x.com', password='x')
        p = UserProfile.objects.create(user=u, first_name='A', last_name='B', uid='U', email='a@x.com')
        loan = Loan.objects.create(
            ref='LADV', owner=p, uid='U', repayment_amount=Decimal('320.69'),
            total_outstanding=Decimal('8173.20'), principal_loan_receivable=Decimal('5000'),
            ordinary_interest_receivable=Decimal('3173.20'), total_arrears=Decimal('0'),
            advance_balance=Decimal('0'), status='RUNNING',
            repayment_start_date=datetime.date(2026, 5, 28), number_of_fortnights=26,
            repayment_dates=json.dumps(['2026-05-28', '2026-06-11']))
        stat = Statement.objects.create(owner=p, loanref=loan, date=datetime.date(2026, 5, 28),
                                        debit=Decimal('400.00'), statement='Alesco Pay 11', uid='U')
        request = _attach_messages(RequestFactory().post('/'))
        process_advance_payment(request, loan, stat, Decimal('400.00'))
        loan.refresh_from_db()
        adv = Statement.objects.filter(loanref=loan, statement='Advance Payment').first()
        self.assertIsNotNone(adv)
        self.assertEqual(adv.debit, Decimal('79.31'))
        self.assertEqual(loan.advance_balance, Decimal('79.31'))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class FixLoanDefaultsToolTests(TestCase):
    """The correction tool must reverse a future-dated default, roll back its
    financial effect, and restore its date to the schedule."""
    def test_reverses_future_dated_default(self):
        from django.test import Client
        from accounts.models import User, UserProfile
        from loan.models import Loan, Statement
        admin = User.objects.create_superuser(email='admin@x.com', password='pw') \
            if hasattr(User.objects, 'create_superuser') else User.objects.create_user(email='admin@x.com', password='pw')
        admin.is_superuser = True
        admin.is_active = True
        admin.save()
        UserProfile.objects.create(user=admin, first_name='Ad', last_name='Min', uid='A1', email='admin@x.com', category='STAFF')
        cu = User.objects.create_user(email='c2@x.com', password='pw', is_active=True)
        cp = UserProfile.objects.create(user=cu, first_name='C', last_name='L', uid='C2', email='c2@x.com')
        loan = Loan.objects.create(ref='LMXFIX1', uid='C2', owner=cp, repayment_amount=Decimal('320.69'),
                                   total_outstanding=Decimal('5100'), default_interest_receivable=Decimal('100'),
                                   total_arrears=Decimal('320.69'), number_of_defaults=1, status='DEFAULTED',
                                   repayment_start_date=datetime.date(2026, 5, 28), number_of_fortnights=26,
                                   fortnights_settled=1,
                                   repayment_dates=json.dumps(
                                       [(datetime.date(2026, 5, 28) + datetime.timedelta(days=14 * k)).isoformat()
                                        for k in range(26)]))
        # A future-dated default (the bug): dated after today
        future = datetime.date.today() + datetime.timedelta(days=4)
        Statement.objects.create(owner=cp, loanref=loan, type='DEFAULT', statement='Loan Defaulted',
                                 date=future, default_amount=Decimal('320.69'), default_interest=Decimal('100'),
                                 credit=Decimal('100'), uid='C2')
        c = Client(); c.force_login(admin)
        r = c.post(f'/admin/fix-loan-defaults/{loan.ref}/')
        self.assertEqual(r.status_code, 302)
        loan.refresh_from_db()
        self.assertEqual(Statement.objects.filter(loanref=loan, type='DEFAULT', date__gt=datetime.date.today()).count(), 0)
        self.assertEqual(loan.default_interest_receivable, Decimal('0.00'))
        self.assertEqual(loan.total_outstanding, Decimal('5000.00'))
        # Reversing the default rolls the immutable-schedule cursor back one slot,
        # so the reversed fortnight becomes due again (the schedule is not mutated).
        self.assertEqual(loan.fortnights_settled, 0)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RepaymentStatusSyncTests(TestCase):
    """A repayment that clears arrears must flip a DEFAULTED loan back to RUNNING
    so the loan list and the loan detail page stay consistent."""
    def test_clearing_arrears_sets_running(self):
        from accounts.models import User, UserProfile
        from loan.models import Loan, Statement
        from loan.functions import process_repayment
        u = User.objects.create_user(email='sync@x.com', password='x')
        p = UserProfile.objects.create(user=u, first_name='A', last_name='B', uid='U', email='s@x.com')
        loan = Loan.objects.create(
            ref='LSYNC', owner=p, uid='U', repayment_amount=Decimal('320.69'),
            total_outstanding=Decimal('1000'), principal_loan_receivable=Decimal('1000'),
            ordinary_interest_receivable=Decimal('0'), default_interest_receivable=Decimal('0'),
            total_arrears=Decimal('200'), status='DEFAULTED',
            repayment_dates=json.dumps(['2026-06-15', '2026-06-29']))
        stat = Statement.objects.create(owner=p, loanref=loan, date=datetime.date(2026, 6, 15),
                                        debit=Decimal('320.69'), uid='U')
        process_repayment(_attach_messages(RequestFactory().post('/')), loan, stat, Decimal('320.69'))
        loan.refresh_from_db()
        self.assertEqual(loan.total_arrears, Decimal('0.00'))
        self.assertEqual(loan.status, 'RUNNING')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ShortfallDefaultTests(TestCase):
    """A payment less than the scheduled repayment must default the unpaid
    shortfall (interest on the shortfall + arrears) when the setting is on."""
    def _mk(self, on=True):
        from admin1.models import AdminSettings
        from accounts.models import User, UserProfile
        from loan.models import Loan, Statement
        AdminSettings.objects.create(settings_name='setting1', default_interest_rate=Decimal('20'),
            default_interest_type='PERCENTAGE', default_interest_base='SHORTFALL',
            auto_default_on_shortfall=on, default_interest_calculation_mercy_days=0)
        u = User.objects.create_user(email='sf@x.com', password='x')
        p = UserProfile.objects.create(user=u, first_name='S', last_name='F', uid='U', email='sf@x.com')
        dates = [(datetime.date(2026, 6, 10) + datetime.timedelta(days=14 * k)).isoformat() for k in range(10)]
        loan = Loan.objects.create(ref='LSF', owner=p, uid='U', repayment_amount=Decimal('331.60'),
            total_outstanding=Decimal('3316'), principal_loan_receivable=Decimal('2000'),
            ordinary_interest_receivable=Decimal('1316'), total_arrears=Decimal('0'),
            number_of_fortnights=10, repayment_start_date=datetime.date(2026, 6, 10),
            fortnights_settled=0, status='RUNNING', repayment_dates=json.dumps(dates))
        stat = Statement.objects.create(owner=p, loanref=loan, date=datetime.date(2026, 6, 10),
                                        debit=Decimal('320.69'), uid='U')
        return loan, stat

    def test_shortfall_creates_default(self):
        from loan.functions import process_repayment
        from loan.models import Statement
        loan, stat = self._mk(on=True)
        process_repayment(_attach_messages(RequestFactory().post('/')), loan, stat, Decimal('320.69'))
        loan.refresh_from_db()
        d = Statement.objects.filter(loanref=loan, type='DEFAULT').first()
        self.assertIsNotNone(d)
        self.assertEqual(d.default_amount, Decimal('10.91'))    # 331.60 - 320.69
        self.assertEqual(d.default_interest, Decimal('2.18'))   # 20% of 10.91
        self.assertEqual(loan.total_arrears, Decimal('10.91'))
        self.assertEqual(loan.status, 'DEFAULTED')

    def test_setting_off_no_default(self):
        from loan.functions import process_repayment
        from loan.models import Statement
        loan, stat = self._mk(on=False)
        process_repayment(_attach_messages(RequestFactory().post('/')), loan, stat, Decimal('320.69'))
        self.assertEqual(Statement.objects.filter(loanref=loan, type='DEFAULT').count(), 0)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AlescoRollbackTests(TestCase):
    """confirm_line snapshots the loan; rollback_line restores it exactly and
    removes the payment/statements; later activity on the loan blocks rollback."""

    def setUp(self):
        from accounts.models import User, UserProfile
        from admin1.models import AdminSettings
        from loan.models import Loan, AlescoPayRun, AlescoPayLine

        AdminSettings.objects.create(
            settings_name='setting1',
            default_interest_rate=Decimal('20'), default_interest_type='PERCENTAGE',
            default_interest_base='SHORTFALL', auto_default_on_shortfall=False,
            default_interest_calculation_mercy_days=0,
            send_alesco_pay_update_email=False,
        )
        u = User.objects.create_user(email='al@x.com', password='x')
        self.profile = UserProfile.objects.create(user=u, first_name='Al', last_name='Esco',
                                                  uid='U9', email='al@x.com', has_loan=True)
        dates = [(datetime.date(2026, 6, 10) + datetime.timedelta(days=14 * k)).isoformat() for k in range(10)]
        self.loan = Loan.objects.create(
            ref='ALR1', uid='U9', owner=self.profile,
            repayment_amount=Decimal('320.69'), number_of_fortnights=10,
            repayment_start_date=datetime.date(2026, 6, 10),
            total_outstanding=Decimal('3206.90'),
            principal_loan_receivable=Decimal('2000.00'),
            ordinary_interest_receivable=Decimal('1206.90'),
            default_interest_receivable=Decimal('0.00'),
            total_arrears=Decimal('0.00'), fortnights_settled=0,
            status='RUNNING', category='FUNDED', funded_category='ACTIVE',
            repayment_dates=json.dumps(dates),
        )
        self.run = AlescoPayRun.objects.create(ref='AR1', period_end=datetime.date(2026, 6, 10),
                                               employee_count=1, status='PENDING')
        self.line = AlescoPayLine.objects.create(
            run=self.run, employee_file_number='12345', report_name='ESCO AL',
            this_period=Decimal('320.69'), owner=self.profile, loanref=self.loan,
            expected_repayment=Decimal('320.69'), payment_date=datetime.date(2026, 6, 10),
        )

    def _fields(self):
        self.loan.refresh_from_db()
        from loan.alesco import _SNAPSHOT_FIELDS
        return {f: getattr(self.loan, f) for f in _SNAPSHOT_FIELDS}

    def test_confirm_then_rollback_restores_loan_exactly(self):
        from loan.alesco import confirm_line, rollback_line
        from loan.models import Payment, Statement
        before = self._fields()
        req = _attach_messages(RequestFactory().post('/'))

        ok, msg = confirm_line(req, self.line)
        self.assertTrue(ok, msg)
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, 'CONFIRMED')
        self.assertIsNotNone(self.line.loan_snapshot)
        self.assertEqual(Payment.objects.filter(loanref=self.loan).count(), 1)
        self.assertNotEqual(self._fields(), before)   # balances actually moved

        ok, msg = rollback_line(self.line)
        self.assertTrue(ok, msg)
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, 'PENDING')
        self.assertIsNone(self.line.payment)
        self.assertEqual(Payment.objects.filter(loanref=self.loan).count(), 0)
        self.assertEqual(Statement.objects.filter(loanref=self.loan).count(), 0)
        self.assertEqual(self._fields(), before)      # loan restored exactly
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, 'PENDING')

    def test_rollback_blocked_by_later_activity(self):
        from loan.alesco import confirm_line, rollback_line
        from loan.models import Payment
        req = _attach_messages(RequestFactory().post('/'))
        ok, _ = confirm_line(req, self.line)
        self.assertTrue(ok)
        self.line.refresh_from_db()
        # A manual payment lands AFTER the confirmation…
        Payment.objects.create(owner=self.profile, loanref=self.loan,
                               date=datetime.date(2026, 6, 12), amount=Decimal('50'))
        ok, msg = rollback_line(self.line)
        self.assertFalse(ok)
        self.assertIn('newer', msg)
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, 'CONFIRMED')  # untouched

    def test_cancel_run_rolls_back_and_deletes(self):
        from loan.alesco import confirm_line, cancel_run
        from loan.models import AlescoPayRun, Payment
        req = _attach_messages(RequestFactory().post('/'))
        before = self._fields()
        confirm_line(req, self.line)
        ok, n_rolled, blocked = cancel_run(self.run)
        self.assertTrue(ok)
        self.assertEqual(n_rolled, 1)
        self.assertEqual(blocked, [])
        self.assertFalse(AlescoPayRun.objects.filter(pk=self.run.pk).exists())
        self.assertEqual(Payment.objects.filter(loanref=self.loan).count(), 0)
        self.assertEqual(self._fields(), before)

    def test_rollback_without_snapshot_refused(self):
        from loan.alesco import rollback_line
        from django.utils import timezone as _tz
        self.line.status = 'CONFIRMED'
        self.line.confirmed_at = _tz.now()
        self.line.save()
        ok, msg = rollback_line(self.line)
        self.assertFalse(ok)
        self.assertIn('snapshot', msg)


class AlescoParserTests(SimpleTestCase):
    """Alesco prints zero amounts as '.00' — the parser must not let the columns
    shift left (Last Period masquerading as This Period), and '0.00' rows parse
    as genuine zero deductions."""

    HEADER = "Period End 08-JUL-2026\nPeriod 14 Year 2026\nPaycode: DLMX LoanMasta Limited Paid by\n"

    def _rows(self, body):
        from loan.alesco import parse_alesco_text
        return parse_alesco_text(self.HEADER + body)['rows']

    def test_dot_zero_this_period_does_not_shift_columns(self):
        rows = self._rows("13397412 01 Garry, Naomi                 .00      374.56    -374.56          .00\n")
        r = rows[0]
        self.assertEqual(r['this_period'], Decimal('0.00'))
        self.assertEqual(r['last_period'], Decimal('374.56'))
        self.assertEqual(r['file_variance'], Decimal('-374.56'))
        self.assertEqual(r['arrears'], Decimal('0.00'))

    def test_zero_point_zero_zero_row(self):
        rows = self._rows("13250242 01 Yapao, Jeremiah                       0.00                       0.00\n")
        r = rows[0]
        self.assertEqual(r['this_period'], Decimal('0.00'))

    def test_normal_row_unchanged(self):
        rows = self._rows("10688287 01 YANG, Atta Joanna          374.58      374.58        .00          .00\n")
        r = rows[0]
        self.assertEqual(r['this_period'], Decimal('374.58'))
        self.assertEqual(r['last_period'], Decimal('374.58'))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AdminDeleteReversalTests(TestCase):
    """Deleting a Payment or money Statement in the site admin must reverse the
    whole transaction and restore the loan to its prior state."""

    def setUp(self):
        from accounts.models import User, UserProfile
        from admin1.models import AdminSettings
        from loan.models import Loan
        AdminSettings.objects.create(
            settings_name='setting1',
            default_interest_rate=Decimal('20'), default_interest_type='PERCENTAGE',
            default_interest_base='SHORTFALL', auto_default_on_shortfall=True,
            default_interest_calculation_mercy_days=0, send_alesco_pay_update_email=False)
        u = User.objects.create_user(email='rv@x.com', password='x')
        self.profile = UserProfile.objects.create(user=u, first_name='R', last_name='V',
                                                  uid='U7', email='rv@x.com')
        dates = [(datetime.date(2026, 6, 10) + datetime.timedelta(days=14 * k)).isoformat() for k in range(10)]
        self.loan = Loan.objects.create(
            ref='REV1', uid='U7', owner=self.profile,
            repayment_amount=Decimal('320.69'), number_of_fortnights=10,
            repayment_start_date=datetime.date(2026, 6, 10),
            total_outstanding=Decimal('3206.90'),
            principal_loan_receivable=Decimal('2000.00'),
            ordinary_interest_receivable=Decimal('1206.90'),
            total_arrears=Decimal('0.00'), fortnights_settled=0,
            status='RUNNING', category='FUNDED', funded_category='ACTIVE',
            next_payment_date=datetime.date(2026, 6, 10),
            repayment_dates=json.dumps(dates))

    def _fields(self):
        self.loan.refresh_from_db()
        fields = ['status', 'total_outstanding', 'total_arrears', 'total_paid',
                  'principal_loan_receivable', 'ordinary_interest_receivable',
                  'default_interest_receivable', 'principal_loan_paid', 'interest_paid',
                  'fortnights_settled', 'number_of_repayments', 'advance_balance',
                  'number_of_defaults', 'next_payment_date']
        return {f: getattr(self.loan, f) for f in fields}

    def _post_payment(self, amount, date=datetime.date(2026, 6, 10)):
        """Post a payment the same way the staff flow does."""
        from loan.functions import process_repayment, process_advance_payment
        from loan.models import Payment, Statement
        p = Payment.objects.create(owner=self.profile, loanref=self.loan, date=date,
                                   amount=amount, mode='PAYROLL DEDUCTION')
        s = Statement.objects.create(owner=self.profile, loanref=self.loan, date=date,
                                     debit=amount, type='PAYMENT', uid='U7')
        req = _attach_messages(RequestFactory().post('/'))
        if amount > self.loan.repayment_amount:
            process_advance_payment(req, self.loan, s, amount)
        else:
            process_repayment(req, self.loan, s, amount)
        self.loan.refresh_from_db()
        return p

    def test_delete_payment_reverses_normal_repayment(self):
        from loan.reversal import reverse_payment
        from loan.models import Payment, Statement
        before = self._fields()
        p = self._post_payment(Decimal('320.69'))
        self.assertNotEqual(self._fields(), before)
        reverse_payment(Payment.objects.get(pk=p.pk))
        self.assertEqual(self._fields(), before)
        self.assertEqual(Payment.objects.filter(loanref=self.loan).count(), 0)
        self.assertEqual(Statement.objects.filter(loanref=self.loan).count(), 0)

    def test_delete_statement_reverses_advance_group(self):
        from loan.reversal import reverse_statement
        from loan.models import Payment, Statement
        before = self._fields()
        self._post_payment(Decimal('450.00'))   # advance: SP + SA statements
        sp = Statement.objects.get(loanref=self.loan, type='PAYMENT')
        self.assertTrue(Statement.objects.filter(loanref=self.loan, type='ADVANCE').exists())
        reverse_statement(sp)
        self.assertEqual(self._fields(), before)
        self.assertEqual(Payment.objects.filter(loanref=self.loan).count(), 0)
        self.assertEqual(Statement.objects.filter(loanref=self.loan).count(), 0)

    def test_delete_payment_reverses_shortfall_default_too(self):
        from loan.reversal import reverse_payment
        from loan.models import Payment, Statement
        before = self._fields()
        p = self._post_payment(Decimal('200.00'))   # short: SP + DEFAULT statements
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, 'DEFAULTED')
        self.assertTrue(Statement.objects.filter(loanref=self.loan, type='DEFAULT').exists())
        reverse_payment(Payment.objects.get(pk=p.pk))
        self.assertEqual(self._fields(), before)
        self.assertEqual(Statement.objects.filter(loanref=self.loan).count(), 0)

    def test_structural_statement_refused(self):
        from loan.reversal import reverse_statement, ReversalError
        from loan.models import Statement
        f = Statement.objects.create(owner=self.profile, loanref=self.loan,
                                     date=datetime.date(2026, 6, 4), credit=Decimal('2000'),
                                     type='FUNDING', uid='U7')
        with self.assertRaises(ReversalError):
            reverse_statement(f)
        self.assertTrue(Statement.objects.filter(pk=f.pk).exists())

    def test_orphan_payment_plain_delete(self):
        from loan.reversal import reverse_payment
        from loan.models import Payment
        before = self._fields()
        p = Payment.objects.create(owner=self.profile, loanref=self.loan,
                                   date=datetime.date(2026, 6, 24), amount=Decimal('99'))
        msg = reverse_payment(p)
        self.assertIn('Orphan', msg)
        self.assertEqual(self._fields(), before)
        self.assertEqual(Payment.objects.filter(loanref=self.loan).count(), 0)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AlescoBatchConfirmTests(TestCase):
    """Confirm All runs in small batches (?batch=N&after=<id>) so the request
    always finishes well inside proxy/worker timeouts, walking the FULL pending
    set of the run server-side."""

    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        from admin1.models import AdminSettings
        from loan.models import Loan, AlescoPayRun, AlescoPayLine
        AdminSettings.objects.create(
            settings_name='setting1',
            default_interest_rate=Decimal('20'), default_interest_type='PERCENTAGE',
            default_interest_base='SHORTFALL', auto_default_on_shortfall=False,
            default_interest_calculation_mercy_days=0, send_alesco_pay_update_email=False)
        su = User.objects.create_user(email='st@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, category='STAFF', activation=1, uid='S1',
                                        first_name='S', last_name='T', email='st@x.com')
        StaffProfile.objects.create(user=sp)
        self.client = Client()
        self.client.force_login(su)

        self.run = AlescoPayRun.objects.create(ref='ARB2', period_end=datetime.date(2026, 6, 10),
                                               employee_count=5, status='PENDING')
        dates = [(datetime.date(2026, 6, 10) + datetime.timedelta(days=14 * k)).isoformat() for k in range(10)]
        for i in range(5):
            u = User.objects.create_user(email=f'b{i}@x.com', password='x')
            p = UserProfile.objects.create(user=u, uid=f'B{i}', first_name='B', last_name=str(i), email=f'b{i}@x.com')
            loan = Loan.objects.create(
                ref=f'BAT{i}', uid=f'B{i}', owner=p, repayment_amount=Decimal('320.69'),
                number_of_fortnights=10, repayment_start_date=datetime.date(2026, 6, 10),
                total_outstanding=Decimal('3206.90'), principal_loan_receivable=Decimal('2000.00'),
                ordinary_interest_receivable=Decimal('1206.90'), total_arrears=Decimal('0.00'),
                fortnights_settled=0, status='RUNNING', category='FUNDED', funded_category='ACTIVE',
                next_payment_date=datetime.date(2026, 6, 10), repayment_dates=json.dumps(dates))
            AlescoPayLine.objects.create(
                run=self.run, employee_file_number=f'F{i}', report_name=f'B {i}',
                this_period=Decimal('320.69'), owner=p, loanref=loan,
                expected_repayment=Decimal('320.69'), payment_date=datetime.date(2026, 6, 10))

    def test_batched_confirm_walks_whole_run(self):
        url = f'/staff/alesco/{self.run.pk}/confirm-all/'
        after = 0
        confirmed = 0
        rounds = 0
        while True:
            # the page sends the universal Payment Date with every batch
            r = self.client.post(f'{url}?ajax=1&batch=2&after={after}', {'date': '2026-07-09'})
            self.assertEqual(r.status_code, 200)
            data = r.json()
            if data['done']:
                break
            confirmed += data['confirmed']
            after = data['last']
            rounds += 1
            self.assertLessEqual(rounds, 10, 'batch loop did not terminate')
        self.assertEqual(confirmed, 5)
        self.assertEqual(self.run.lines.filter(status='CONFIRMED').count(), 5)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, 'COMPLETED')
        # every confirmed line got a rollback snapshot
        self.assertEqual(self.run.lines.filter(status='CONFIRMED', loan_snapshot__isnull=False).count(), 5)
        # the chosen Payment Date overrides the file's period end on every
        # payment and statement posted
        from loan.models import Payment, Statement
        self.assertEqual(Payment.objects.filter(date=datetime.date(2026, 7, 9)).count(), 5)
        self.assertEqual(Statement.objects.filter(type='PAYMENT', date=datetime.date(2026, 7, 9)).count(), 5)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AddOnVariedRefinanceTests(TestCase):
    """ADD_ON_VARIED: combined balance like ADD_ON, but staff enter the combined
    term and fortnightly repayment on the funding form (PDF example: old balance
    K4,140.09 + new repayable K3,316.00 = K7,456.09 over 12 fns at K621.34)."""

    def setUp(self):
        from accounts.models import User, UserProfile
        from admin1.models import AdminSettings
        from loan.models import Loan
        AdminSettings.objects.create(settings_name='setting1', refinance_type='ADD_ON_VARIED',
                                     default_interest_rate=Decimal('20'),
                                     default_interest_type='PERCENTAGE')
        u = User.objects.create_user(email='rf@x.com', password='x')
        self.p = UserProfile.objects.create(user=u, uid='R1', first_name='R', last_name='F', email='rf@x.com')
        dates = [(datetime.date(2026, 7, 22) + datetime.timedelta(days=14 * k)).isoformat() for k in range(12)]
        self.running = Loan.objects.create(
            ref='OLD1', uid='R1', owner=self.p, amount=Decimal('3000'),
            repayment_amount=Decimal('376.96'), number_of_fortnights=12,
            repayment_start_date=datetime.date(2026, 7, 22),
            total_outstanding=Decimal('4140.09'), total_loan_amount=Decimal('4522.09'),
            principal_loan_receivable=Decimal('2500.00'), ordinary_interest_receivable=Decimal('1640.09'),
            total_arrears=Decimal('0'), fortnights_settled=0, status='RUNNING',
            category='FUNDED', funded_category='ACTIVE', repayment_dates=json.dumps(dates))
        self.new = Loan.objects.create(
            ref='NEW1', uid='R1', owner=self.p, amount=Decimal('2000'),
            interest=Decimal('1316.00'), total_loan_amount=Decimal('3316.00'),
            repayment_amount=Decimal('331.60'), number_of_fortnights=10,
            repayment_start_date=datetime.date(2026, 7, 22),
            principal_loan_receivable=Decimal('2000'), ordinary_interest_receivable=Decimal('1316.00'),
            total_outstanding=Decimal('3316.00'), status='PENDING', category='PENDING')

    def test_staff_entered_terms_apply(self):
        from loan.refinance import apply_refinance
        req = RequestFactory().post('/', {'combined_fortnights': '12', 'combined_repayment': '621.34'})
        loan = apply_refinance(req, self.running, self.new, notify=False,
                               today=datetime.date(2026, 7, 14))
        self.assertEqual(loan.total_outstanding, Decimal('7456.09'))   # 4140.09 + 3316.00
        self.assertEqual(loan.number_of_fortnights, 12)
        self.assertEqual(loan.repayment_amount, Decimal('621.34'))
        self.assertEqual(len(loan.get_repayment_dates()), 12)
        self.running.refresh_from_db()
        self.assertEqual(self.running.funded_category, 'COMPLETED')
        self.assertEqual(self.running.total_outstanding, Decimal('0'))

    def test_blank_inputs_fall_back_to_add_on_derivation(self):
        from loan.refinance import apply_refinance
        req = RequestFactory().post('/', {})
        loan = apply_refinance(req, self.running, self.new, notify=False,
                               today=datetime.date(2026, 7, 14))
        # remaining 12 + new 10 = 22 fns; 7456.09 / 22 = 338.91
        self.assertEqual(loan.number_of_fortnights, 22)
        self.assertEqual(loan.repayment_amount, Decimal('338.91'))


class AlescoColumnParserTests(SimpleTestCase):
    """Amounts are classified by their position under the report's own column
    headers: a BLANK This Period never steals Last Period/Variance, negatives
    parse as negatives (skipped as payments), trailing status text and lettered
    file numbers don't drop rows. Only This Period > 0 becomes a payment."""

    SAMPLE = (
        "Pay Group PNG Period 14 Year 2026 Period End 08-JUL-2026\n"
        " Paycode: DLMX  LoanMasta Limited  Paid by Cemtex\n"
        " Employee Job Report Name                 This Period      Last Period           Variance             Arrears\n"
        " 10558828 02  Emena, Lucy                     -374.58                             -374.58                0.00\n"
        " 12806973 01  Fore, Peter                                       374.58            -374.58                0.00 Defaulted\n"
        " 10672769 01  Gawi, Cathy                      320.69                              320.69                0.00\n"
        " 11525358 01  Higili, Lilly                                                                              0.00\n"
        " 0092287A 01  Yawi, Donald                     374.58           374.58                                   0.00\n"
        " 10436593 01  Alu, Pitiwin 14150               331.60           331.60                                   0.00\n"
    )

    def _rows(self):
        from loan.alesco import parse_alesco_text
        return {r['report_name']: r for r in parse_alesco_text(self.SAMPLE)['rows']}

    def test_blank_this_period_is_zero_not_last_period(self):
        r = self._rows()['Fore, Peter']
        self.assertEqual(r['this_period'], Decimal('0'))
        self.assertEqual(r['last_period'], Decimal('374.58'))
        self.assertEqual(r['file_variance'], Decimal('-374.58'))

    def test_negative_this_period_parses_negative(self):
        r = self._rows()['Emena, Lucy']
        self.assertEqual(r['this_period'], Decimal('-374.58'))

    def test_lettered_file_number_and_trailing_text_rows_kept(self):
        rows = self._rows()
        self.assertIn('Yawi, Donald', rows)
        self.assertEqual(rows['Yawi, Donald']['employee_file_number'], '0092287A')
        self.assertIn('Fore, Peter', rows)      # 'Defaulted' suffix
        self.assertIn('Alu, Pitiwin 14150', rows)  # digits in name

    def test_only_positive_amounts_become_pending_payments(self):
        # create_pay_run marks this_period <= 0 as SKIPPED — mirror that rule
        for name, r in self._rows().items():
            confirmable = r['this_period'] > 0
            if name in ('Emena, Lucy', 'Fore, Peter', 'Higili, Lilly'):
                self.assertFalse(confirmable, name)
            if name in ('Gawi, Cathy', 'Yawi, Donald'):
                self.assertTrue(confirmable, name)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RegenerateScheduleTests(TestCase):
    """Regenerate Dates: settled history is kept, the unsettled schedule is
    rebuilt from the chosen date at the chosen frequency, and the cursor points
    at the new next repayment date."""

    def setUp(self):
        from accounts.models import User, UserProfile
        from admin1.models import AdminSettings
        from loan.models import Loan
        AdminSettings.objects.create(settings_name='setting1', default_interest_rate=Decimal('20'),
                                     default_interest_type='PERCENTAGE',
                                     default_interest_calculation_mercy_days=0)
        u = User.objects.create_user(email='rg@x.com', password='x')
        p = UserProfile.objects.create(user=u, uid='G1', first_name='R', last_name='G', email='rg@x.com')
        dates = [(datetime.date(2026, 6, 10) + datetime.timedelta(days=14 * k)).isoformat() for k in range(10)]
        self.loan = Loan.objects.create(
            ref='REGEN1', uid='G1', owner=p, repayment_amount=Decimal('320.69'),
            number_of_fortnights=10, repayment_start_date=datetime.date(2026, 6, 10),
            total_outstanding=Decimal('3206.90'), principal_loan_receivable=Decimal('2000'),
            ordinary_interest_receivable=Decimal('1206.90'), total_arrears=Decimal('0'),
            fortnights_settled=3, status='RUNNING', category='FUNDED', funded_category='ACTIVE',
            next_payment_date=datetime.date(2026, 7, 22), repayment_dates=json.dumps(dates))

    def test_fortnightly_regeneration(self):
        from loan import schedule as sched
        dates = sched.regenerate(self.loan, datetime.date(2026, 8, 1), 6, 'FORTNIGHTLY')
        self.loan.save()
        self.assertEqual(len(dates), 9)                       # 3 history + 6 new
        self.assertEqual(dates[:3], [datetime.date(2026, 6, 10) + datetime.timedelta(days=14*k) for k in range(3)])
        self.assertEqual(dates[3], datetime.date(2026, 8, 1))
        self.assertEqual(dates[4], datetime.date(2026, 8, 15))
        self.assertEqual(self.loan.fortnights_settled, 3)     # cursor unchanged
        self.assertEqual(self.loan.next_payment_date, datetime.date(2026, 8, 1))
        self.assertEqual(self.loan.number_of_fortnights, 9)
        self.assertEqual(self.loan.expected_end_date, dates[-1])
        self.assertTrue(self.loan.custom_schedule)
        # build_schedule now returns the stored custom list
        self.assertEqual(sched.build_schedule(self.loan), dates)

    def test_weekly_and_monthly_spacing(self):
        from loan import schedule as sched
        d = sched.regenerate(self.loan, datetime.date(2026, 8, 1), 3, 'WEEKLY')
        self.assertEqual(d[3:], [datetime.date(2026, 8, 1), datetime.date(2026, 8, 8), datetime.date(2026, 8, 15)])
        d = sched.regenerate(self.loan, datetime.date(2026, 1, 31), 3, 'MONTHLY')
        self.assertEqual(d[3:], [datetime.date(2026, 1, 31), datetime.date(2026, 2, 28), datetime.date(2026, 3, 31)])

    def test_engine_defaults_use_regenerated_dates(self):
        from loan import schedule as sched
        from loan.engine import create_default_for_loan
        sched.regenerate(self.loan, datetime.date(2026, 7, 1), 5, 'FORTNIGHTLY')
        self.loan.save()
        stat, ok, msg = create_default_for_loan(self.loan, today=datetime.date(2026, 7, 2))
        self.assertTrue(ok)
        self.assertEqual(stat.date, datetime.date(2026, 7, 1))
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.next_payment_date, datetime.date(2026, 7, 15))

    def test_view_flow_both_portals(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        from loan.models import Statement
        su = User.objects.create_user(email='adm@x.com', password='pw', is_active=True)
        su.active = True; su.staff = True; su.admin = True; su.is_superuser = True; su.save()
        UserProfile.objects.create(user=su, category='ADMIN', activation=1, uid='A1',
                                   first_name='A', last_name='D', email='adm@x.com')
        c = Client(); c.force_login(su)
        r = c.get(f'/admin/loans/{self.loan.ref}/regenerate-dates/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Regenerate')
        r = c.post(f'/admin/loans/{self.loan.ref}/regenerate-dates/',
                   {'next_date': '2026-08-05', 'remaining': '4', 'frequency': 'WEEKLY'}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.next_payment_date, datetime.date(2026, 8, 5))
        self.assertEqual(self.loan.number_of_fortnights, 7)   # 3 history + 4 weekly
        self.assertTrue(Statement.objects.filter(loanref=self.loan, type='OTHER',
                                                 statement__icontains='regenerated').exists())


class SystemDateFormatTests(TestCase):
    """The Date Settings format drives form date entry and display: widgets
    render initial values in the configured format, and typed dd/mm/yyyy input
    parses (alongside ISO)."""

    def setUp(self):
        from admin1.models import AdminSettings
        AdminSettings.objects.create(settings_name='setting1', date_format='d/m/Y')
        from django.core.cache import cache
        cache.clear()   # finance_formats caches the settings for 30s

    def test_widget_renders_setting_format(self):
        from staff.widgets import DatePickerInput
        w = DatePickerInput()
        self.assertEqual(w.format_value(datetime.date(2026, 2, 21)), '21/02/2026')

    def test_flatpickr_format_follows_setting(self):
        from moromafinance.dateformats import flatpickr_format
        self.assertEqual(flatpickr_format(), 'd/m/Y')

    def test_job_form_accepts_ddmmyyyy_and_iso(self):
        from staff.forms import JobInfoUpdateForm
        for raw in ('21/02/2013', '2013-02-21', '21-02-2013'):
            f = JobInfoUpdateForm({'start_date': raw, 'employee_file_number': '123'})
            f.is_valid()
            self.assertEqual(f.cleaned_data.get('start_date'), datetime.date(2013, 2, 21), raw)

    def test_sdate_filter_matches(self):
        from accounts.templatetags.finance_formats import sdate
        self.assertEqual(sdate(datetime.date(2026, 2, 21)), '21/02/2026')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EarlyAdvancePaymentTests(TestCase):
    """A payment made BEFORE the next due date (no arrears) is an ADVANCE
    payment: full amount settles the fortnight early with advance tracking;
    a smaller amount is held entirely as advance credit — never a shortfall
    default, because nothing was due yet."""

    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        from admin1.models import AdminSettings
        from loan.models import Loan
        AdminSettings.objects.create(settings_name='setting1', default_interest_rate=Decimal('20'),
                                     default_interest_type='PERCENTAGE', default_interest_base='SHORTFALL',
                                     auto_default_on_shortfall=True, default_interest_calculation_mercy_days=0,
                                     send_alesco_pay_update_email=False)
        su = User.objects.create_user(email='ea@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, category='STAFF', activation=1, uid='S9',
                                        first_name='S', last_name='T', email='ea@x.com')
        StaffProfile.objects.create(user=sp)
        self.client = Client(); self.client.force_login(su)
        cu = User.objects.create_user(email='ec@x.com', password='pw')
        self.cp = UserProfile.objects.create(user=cu, uid='E1', first_name='E', last_name='C', email='ec@x.com')
        # next due is far in the future relative to the payment date
        dates = [(datetime.date(2026, 12, 24) + datetime.timedelta(days=14 * k)).isoformat() for k in range(10)]
        self.loan = Loan.objects.create(
            ref='EARLY1', uid='E1', owner=self.cp, repayment_amount=Decimal('400.00'),
            number_of_fortnights=10, repayment_start_date=datetime.date(2026, 12, 24),
            total_outstanding=Decimal('6400.00'), principal_loan_receivable=Decimal('4000.00'),
            ordinary_interest_receivable=Decimal('2400.00'), total_arrears=Decimal('0.00'),
            fortnights_settled=0, status='RUNNING', category='FUNDED', funded_category='ACTIVE',
            next_payment_date=datetime.date(2026, 12, 24), repayment_dates=json.dumps(dates))

    def _pay(self, amount, day):
        return self.client.post(f'/loan/payment/{self.loan.ref}/',
                                {'date': day, 'amount': amount, 'mode': 'PAYROLL DEDUCTION',
                                 'statement': 'Early payment'}, follow=True)

    def test_full_amount_early_is_advance(self):
        from loan.models import Payment
        self._pay('400.00', '2026-07-15')
        p = Payment.objects.get(loanref=self.loan)
        self.loan.refresh_from_db()
        self.assertEqual(p.type, 'ADVANCE PAYMENT')
        self.assertEqual(self.loan.number_of_advance_payments, 1)
        self.assertEqual(self.loan.fortnights_settled, 1)     # settled the fortnight early
        self.assertEqual(self.loan.total_arrears, Decimal('0.00'))
        self.assertEqual(self.loan.number_of_defaults, 0)

    def test_partial_early_is_advance_credit_not_default(self):
        from loan.models import Payment, Statement
        self._pay('150.00', '2026-07-15')
        p = Payment.objects.get(loanref=self.loan)
        self.loan.refresh_from_db()
        self.assertEqual(p.type, 'ADVANCE PAYMENT')
        self.assertEqual(self.loan.advance_balance, Decimal('150.00'))
        self.assertEqual(self.loan.fortnights_settled, 0)     # nothing due, nothing settled
        self.assertEqual(self.loan.number_of_defaults, 0)     # NO shortfall default
        self.assertFalse(Statement.objects.filter(loanref=self.loan, type='DEFAULT').exists())
        self.assertTrue(Statement.objects.filter(loanref=self.loan, type='ADVANCE').exists())


# --------------------------------------------------------------------------
# LoanCredit / "Awaiting Refund" overpayment-at-closure workflow
# (July 2026 — Georgina Steven refinance-overpayment bug)
# --------------------------------------------------------------------------
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CloseLoanWithCreditTests(TestCase):
    def setUp(self):
        from accounts.models import User, UserProfile
        from loan.models import Loan, Statement
        u = User.objects.create_user(email='cred@x.com', password='x')
        self.profile = UserProfile.objects.create(user=u, first_name='Cred', last_name='Itor',
                                                  uid='CR1', email='cred@x.com', has_loan=True)
        self.loan = Loan.objects.create(
            ref='CRED1', uid='CR1', owner=self.profile, repayment_amount=Decimal('320.69'),
            total_outstanding=Decimal('1000.00'), total_paid=Decimal('2000.00'),
            principal_loan_receivable=Decimal('700.00'), ordinary_interest_receivable=Decimal('300.00'),
            default_interest_receivable=Decimal('0.00'), status='RUNNING', category='FUNDED',
            funded_category='ACTIVE', repayment_dates=json.dumps(['2026-06-10']),
        )
        self.stat = Statement.objects.create(owner=self.profile, loanref=self.loan,
                                             date=datetime.date(2026, 6, 20), uid='CR1')

    def test_overpayment_creates_credit_and_parks_awaiting_refund(self):
        from loan.functions import close_loan_with_credit
        from loan.models import LoanCredit
        req = _attach_messages(RequestFactory().post('/'))

        close_loan_with_credit(req, self.loan, self.stat, amount=Decimal('1374.58'),
                               balance=Decimal('1000.00'), notify=False)

        self.loan.refresh_from_db()
        self.assertEqual(self.loan.total_paid, Decimal('3374.58'))   # 2000 prior + full 1374.58
        self.assertEqual(self.loan.total_outstanding, Decimal('0'))
        self.assertEqual(self.loan.funded_category, 'AWAITING_REFUND')
        self.assertEqual(self.loan.status, 'COMPLETED')
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.has_loan)

        credit = LoanCredit.objects.get(loan=self.loan)
        self.assertEqual(credit.amount, Decimal('374.58'))
        self.assertEqual(credit.reason, 'OVERPAYMENT_AT_CLOSURE')
        self.assertFalse(credit.refunded)

    def test_exact_payoff_completes_normally_no_credit(self):
        from loan.functions import close_loan_with_credit
        from loan.models import LoanCredit
        req = _attach_messages(RequestFactory().post('/'))

        close_loan_with_credit(req, self.loan, self.stat, amount=Decimal('1000.00'),
                               balance=Decimal('1000.00'), notify=False)

        self.loan.refresh_from_db()
        self.assertEqual(self.loan.total_paid, Decimal('3000.00'))
        self.assertEqual(self.loan.funded_category, 'COMPLETED')
        self.assertFalse(LoanCredit.objects.filter(loan=self.loan).exists())

    def test_finalize_awaiting_refund_completes_and_emails(self):
        from django.core import mail
        from loan.functions import close_loan_with_credit, finalize_awaiting_refund
        req = _attach_messages(RequestFactory().post('/'))
        close_loan_with_credit(req, self.loan, self.stat, amount=Decimal('1200.00'),
                               balance=Decimal('1000.00'), notify=False)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.funded_category, 'AWAITING_REFUND')

        mail.outbox = []
        ok = finalize_awaiting_refund(req, self.loan)
        self.assertTrue(ok)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.funded_category, 'COMPLETED')
        self.assertEqual(len(mail.outbox), 1)

        # No-op the second time (already finalised).
        self.assertFalse(finalize_awaiting_refund(req, self.loan))

    def test_classify_loan_complete_excludes_awaiting_refund(self):
        from custom.functions import classify_loan_complete
        from loan.functions import close_loan_with_credit
        req = _attach_messages(RequestFactory().post('/'))
        close_loan_with_credit(req, self.loan, self.stat, amount=Decimal('1200.00'),
                               balance=Decimal('1000.00'), notify=False)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.funded_category, 'AWAITING_REFUND')

        classify_loan_complete(req)

        self.loan.refresh_from_db()
        self.assertEqual(self.loan.funded_category, 'AWAITING_REFUND')   # untouched


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ClientCreditsRegisterViewTests(TestCase):
    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        from loan.models import Loan, LoanCredit

        su = User.objects.create_user(email='ccstaff@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, first_name='St', last_name='Aff',
                                        email='ccstaff@x.com', uid='CCS1', category='STAFF')
        StaffProfile.objects.create(user=sp)
        self.client = Client(); self.client.force_login(su)

        cu = User.objects.create_user(email='ccclient@x.com', password='pw')
        self.cp = UserProfile.objects.create(user=cu, uid='CCC1', first_name='Cc', last_name='Client',
                                             email='ccclient@x.com', has_loan=True)
        self.loan = Loan.objects.create(
            ref='CCLOAN1', uid='CCC1', owner=self.cp, repayment_amount=Decimal('320.69'),
            total_outstanding=Decimal('0'), status='COMPLETED', category='FUNDED',
            funded_category='AWAITING_REFUND', repayment_dates=json.dumps(['2026-06-10']),
        )
        self.credit = LoanCredit.objects.create(owner=self.cp, loan=self.loan, amount=Decimal('374.58'))

    def test_credits_page_lists_owing_credit(self):
        r = self.client.get('/admin/transactions/client-credits/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'CCLOAN1')
        self.assertContains(r, '374.58')

    def test_mark_refunded_finalizes_loan(self):
        r = self.client.post('/admin/transactions/client-credits/', {
            'action': 'mark_refunded', 'credit_id': self.credit.pk,
            'refunded_at': '2026-07-20', 'refund_note': 'bank transfer',
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.credit.refresh_from_db()
        self.assertTrue(self.credit.refunded)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.funded_category, 'COMPLETED')

    def test_attribute_credit_and_close(self):
        r = self.client.post(f'/admin/loans/{self.loan.ref}/attribute-credit-close/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.funded_category, 'COMPLETED')
        # Credit is untouched — still owing, to be refunded whenever.
        self.credit.refresh_from_db()
        self.assertFalse(self.credit.refunded)


# --------------------------------------------------------------------------
# Categorized Unmatched Alesco Payments (July 2026 — Pay 14/15 unmatched review)
# --------------------------------------------------------------------------
class AlescoUnmatchedCategorizationTests(TestCase):
    def setUp(self):
        from accounts.models import User, UserProfile
        from loan.models import AlescoPayRun, AlescoPayLine
        u = User.objects.create_user(email='catclient@x.com', password='x')
        self.client_profile = UserProfile.objects.create(
            user=u, first_name='Cat', last_name='Client', uid='CAT1',
            email='catclient@x.com', employee_file_number='10301954')
        self.run = AlescoPayRun.objects.create(ref='ALSCAT1', period_end=datetime.date(2026, 6, 10),
                                               pay_period='15', pay_year='2026',
                                               employee_count=1, status='PENDING')

    def _line(self, file_number, owner=None):
        from loan.models import AlescoPayLine
        return AlescoPayLine.objects.create(
            run=self.run, employee_file_number=file_number, report_name='Some, Body',
            this_period=Decimal('100.00'), owner=owner, loanref=None,
            payment_date=datetime.date(2026, 6, 10), status='UNMATCHED',
        )

    def test_no_client_record(self):
        from loan.alesco import classify_unmatched_line
        line = self._line('99999999')
        category, candidates = classify_unmatched_line(line)
        self.assertEqual(category, 'NO_CLIENT_RECORD')
        self.assertEqual(candidates, [])

    def test_possible_typo_suggests_close_match(self):
        from loan.alesco import classify_unmatched_line
        # one digit off from the real client's file number (10301954)
        line = self._line('10301964')
        category, candidates = classify_unmatched_line(line)
        self.assertEqual(category, 'POSSIBLE_TYPO')
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].pk, self.client_profile.pk)

    def test_ambiguous_match_multiple_clients_same_number(self):
        from accounts.models import User, UserProfile
        from loan.alesco import classify_unmatched_line
        u2 = User.objects.create_user(email='dupe@x.com', password='x')
        UserProfile.objects.create(user=u2, first_name='Dup', last_name='E', uid='CAT2',
                                   email='dupe@x.com', employee_file_number='10301954')
        line = self._line('10301954')
        category, candidates = classify_unmatched_line(line)
        self.assertEqual(category, 'AMBIGUOUS_MATCH')
        self.assertEqual(len(candidates), 2)

    def test_client_exists_but_no_loan(self):
        from loan.alesco import classify_unmatched_line
        line = self._line('10301954', owner=self.client_profile)
        category, candidates = classify_unmatched_line(line)
        self.assertEqual(category, 'NO_ACTIVE_LOAN')
        self.assertEqual(candidates, [])

    def test_relink_success_flips_to_pending(self):
        from loan.alesco import relink_unmatched_line
        from loan.models import Loan
        loan = Loan.objects.create(ref='CATLOAN1', uid='CAT1', owner=self.client_profile,
                                   repayment_amount=Decimal('100.00'), total_outstanding=Decimal('500'),
                                   status='RUNNING', category='FUNDED', funded_category='ACTIVE',
                                   repayment_dates=json.dumps(['2026-06-10']))
        line = self._line('10301964')   # the typo'd number

        ok, msg = relink_unmatched_line(line, '10301954')   # corrected to the real client

        self.assertTrue(ok, msg)
        line.refresh_from_db()
        self.assertEqual(line.owner, self.client_profile)
        self.assertEqual(line.loanref, loan)
        self.assertEqual(line.status, 'PENDING')

    def test_relink_no_client_fails_line_unchanged(self):
        from loan.alesco import relink_unmatched_line
        line = self._line('99999999')
        ok, msg = relink_unmatched_line(line, '00000000')
        self.assertFalse(ok)
        line.refresh_from_db()
        self.assertEqual(line.status, 'UNMATCHED')

    def test_relink_client_with_no_loan_fails(self):
        from loan.alesco import relink_unmatched_line
        line = self._line('99999999')
        ok, msg = relink_unmatched_line(line, '10301954')   # real client, but has no loan
        self.assertFalse(ok)
        self.assertIn('no loan', msg)
        line.refresh_from_db()
        self.assertEqual(line.status, 'UNMATCHED')


# --------------------------------------------------------------------------
# "Apply Advance to Missed Payments" (July 2026 — Adolf Bessie Pay 15 report)
# --------------------------------------------------------------------------
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ApplyAdvanceToMissedPaymentTests(TestCase):
    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        from admin1.models import AdminSettings
        from loan.models import Loan

        AdminSettings.objects.create(settings_name='setting1', default_interest_rate=Decimal('20'),
                                     default_interest_type='PERCENTAGE', default_interest_base='SHORTFALL',
                                     default_interest_calculation_mercy_days=0)

        # Non-superuser STAFF login — the regression this covers is the dead
        # inline is_superuser check that blocked staff despite the
        # @staff_or_admin_check decorator letting them through.
        su = User.objects.create_user(email='aastaff@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, first_name='Aa', last_name='Staff',
                                        email='aastaff@x.com', uid='AAS1', category='STAFF')
        StaffProfile.objects.create(user=sp)
        self.client = Client(); self.client.force_login(su)

        cu = User.objects.create_user(email='aaclient@x.com', password='pw')
        self.cp = UserProfile.objects.create(user=cu, uid='AAC1', first_name='Aa', last_name='Client',
                                             email='aaclient@x.com')
        dates = [(datetime.date(2026, 6, 10) + datetime.timedelta(days=14 * k)).isoformat() for k in range(10)]
        self.loan = Loan.objects.create(
            ref='AADV1', uid='AAC1', owner=self.cp, repayment_amount=Decimal('320.69'),
            number_of_fortnights=10, repayment_start_date=datetime.date(2026, 6, 10),
            total_outstanding=Decimal('3206.90'), principal_loan_receivable=Decimal('2000'),
            ordinary_interest_receivable=Decimal('1206.90'), total_arrears=Decimal('0'),
            fortnights_settled=0, status='RUNNING', category='FUNDED', funded_category='ACTIVE',
            advance_balance=Decimal('717.24'), repayment_dates=json.dumps(dates),
        )

    def test_staff_not_blocked_by_dead_superuser_check(self):
        """Regression: staff must be able to actually execute Create Default —
        the leftover inline is_superuser check must be gone."""
        r = self.client.get(f'/admin/create-default/{self.loan.ref}/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'You do not have permission to view this page.')

    def test_create_default_blocked_when_advance_covers_shortfall(self):
        """The advance (717.24) fully covers one repayment (320.69) — Create
        Default must refuse and point at Apply Advance to Missed Payments
        instead of silently netting/defaulting."""
        from loan.models import Statement
        r = self.client.get(f'/admin/create-default/{self.loan.ref}/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Apply Advance to Missed Payments')
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.number_of_defaults, 0)
        self.assertFalse(Statement.objects.filter(loanref=self.loan, type='DEFAULT').exists())

    def test_apply_advance_settles_without_default(self):
        r = self.client.get(f'/admin/apply-advance-to-missed-payment/{self.loan.ref}/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.number_of_defaults, 0)
        self.assertEqual(self.loan.advance_balance, Decimal('396.55'))   # 717.24 - 320.69
        self.assertEqual(self.loan.fortnights_settled, 1)

    def test_apply_advance_noop_when_no_advance(self):
        self.loan.advance_balance = Decimal('0')
        self.loan.save()
        r = self.client.get(f'/admin/apply-advance-to-missed-payment/{self.loan.ref}/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'no advance balance')
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.fortnights_settled, 0)


# --------------------------------------------------------------------------
# Loan-list audit (July 2026 — "go through all loan-lists / rework columns")
# --------------------------------------------------------------------------
class AwaitingRefundLoansListTests(TestCase):
    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile
        from loan.models import Loan, LoanCredit

        su = User.objects.create_user(email='listadmin@x.com', password='pw', is_active=True)
        su.active = True; su.staff = True; su.admin = True; su.is_superuser = True; su.save()
        UserProfile.objects.create(user=su, category='ADMIN', activation=1, uid='LA1',
                                   first_name='List', last_name='Admin', email='listadmin@x.com')
        self.client = Client(); self.client.force_login(su)

        cu = User.objects.create_user(email='arclient@x.com', password='pw')
        self.cp = UserProfile.objects.create(user=cu, uid='AR1', first_name='Ar', last_name='Client',
                                             email='arclient@x.com')
        self.loan = Loan.objects.create(
            ref='ARLIST1', uid='AR1', owner=self.cp, repayment_amount=Decimal('320.69'),
            total_outstanding=Decimal('0'), status='COMPLETED', category='FUNDED',
            funded_category='AWAITING_REFUND', total_paid=Decimal('1200'),
            repayment_dates=json.dumps(['2026-06-10']),
        )
        LoanCredit.objects.create(owner=self.cp, loan=self.loan, amount=Decimal('200.00'))

    def test_dedicated_view_lists_the_loan_and_credit(self):
        r = self.client.get('/admin/loans/awaiting-refund')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ARLIST1')
        self.assertContains(r, '200.00')

    def test_all_loans_tab_bar_shows_count_and_distinct_badge(self):
        r = self.client.get('/admin/loans/all')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ARLIST1')
        self.assertContains(r, 'AWAITING REFUND')

    def test_filter_form_works_on_awaiting_refund_list(self):
        r = self.client.post('/admin/loans/awaiting-refund', {'cuscat': 'MEMBER'})
        self.assertEqual(r.status_code, 200)


class StaffLoansListTemplateRoutingTests(TestCase):
    """Regression: the staff portal's Loans page rendered the ADMIN loans_all.html
    (admin_base.html chrome + admin-only tab URLs) whenever the filter form was
    submitted, instead of its own staff_base-based template — found while
    auditing all loan-lists. A staff (non-superuser) user filtering their Loans
    page must stay on staff chrome, not get bounced toward admin-only URLs."""

    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        su = User.objects.create_user(email='listastaff@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, first_name='Lista', last_name='Ff',
                                        email='listastaff@x.com', uid='LS1', category='STAFF')
        StaffProfile.objects.create(user=sp)
        self.client = Client(); self.client.force_login(su)

    def test_filtered_loans_page_stays_on_staff_chrome(self):
        r = self.client.post('/staff/userloans/', {'loantype': 'PERSONAL'})
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'userloans.html')
        self.assertTemplateUsed(r, 'staff_base.html')
        self.assertTemplateNotUsed(r, 'loans_all.html')
        self.assertTemplateNotUsed(r, 'admin_base.html')


class LoanTypeFilterFieldNameTests(TestCase):
    """Regression: every "filter by Loan Type" branch across every loan list
    (admin + staff) filtered on Loan.type, a field that doesn't exist (the
    real field is loan_type) — any user filtering by Loan Type alone, on any
    loan list, got a 500 (FieldError). Found while auditing all loan-lists;
    fixed by correcting the field name everywhere. Spot-checks the admin and
    staff entry points that share this exact bug pattern."""

    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile

        admin_user = User.objects.create_user(email='typefadmin@x.com', password='pw', is_active=True)
        admin_user.active = True; admin_user.staff = True; admin_user.admin = True
        admin_user.is_superuser = True; admin_user.save()
        UserProfile.objects.create(user=admin_user, category='ADMIN', activation=1, uid='TF1',
                                   first_name='Type', last_name='Fadmin', email='typefadmin@x.com')
        self.admin_client = Client(); self.admin_client.force_login(admin_user)

        staff_user = User.objects.create_user(email='typefstaff@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=staff_user, first_name='Type', last_name='Fstaff',
                                        email='typefstaff@x.com', uid='TF2', category='STAFF')
        StaffProfile.objects.create(user=sp)
        self.staff_client = Client(); self.staff_client.force_login(staff_user)

    def test_admin_all_loans_filter_by_type_alone(self):
        r = self.admin_client.post('/admin/loans/all', {'loantype': 'PERSONAL'})
        self.assertEqual(r.status_code, 200)

    def test_admin_completed_loans_filter_by_type_alone(self):
        r = self.admin_client.post('/admin/loans/completed', {'loantype': 'SME'})
        self.assertEqual(r.status_code, 200)

    def test_staff_userloans_all_filter_by_type_alone(self):
        r = self.staff_client.post('/staff/userloans/all/', {'loantype': 'PERSONAL'})
        self.assertEqual(r.status_code, 200)

    def test_staff_userloans_pending_filter_by_type_alone(self):
        r = self.staff_client.post('/staff/userloans/pending/', {'loantype': 'SME'})
        self.assertEqual(r.status_code, 200)

    def test_transactions_all_filter_by_type_alone(self):
        """Same bug, different view: Statement/Payment filters traversed
        loanref__type (doesn't exist) instead of loanref__loan_type."""
        r = self.admin_client.post('/admin/transactions/all', {'loantype': 'PERSONAL'})
        self.assertEqual(r.status_code, 200)

    def test_locations_loans_filter_by_type_and_dates(self):
        r = self.admin_client.post('/admin/locations/loans', {
            'startdate': '2026-01-01', 'enddate': '2026-12-31', 'loantype': 'PERSONAL',
        })
        self.assertEqual(r.status_code, 200)


# --------------------------------------------------------------------------
# Existing Loan Functions hub, Refinance Not Allowed, loan min/max enforcement
# (July 2026)
# --------------------------------------------------------------------------
class RefinanceNotAllowedTests(TestCase):
    """'Refinance Not Allowed' Refinance Type: a client with an existing loan
    cannot get a new/additional loan at all, staff included, until the
    existing one is fully completed."""

    def setUp(self):
        from accounts.models import User, UserProfile
        from admin1.models import AdminSettings
        from loan.models import Loan
        AdminSettings.objects.create(settings_name='setting1', refinance_type='REFINANCE_NOT_ALLOWED',
                                     default_interest_rate=Decimal('20'), default_interest_type='PERCENTAGE')
        u = User.objects.create_user(email='rna@x.com', password='x')
        self.p = UserProfile.objects.create(user=u, uid='RNA1', first_name='R', last_name='Na', email='rna@x.com')
        dates = [(datetime.date(2026, 7, 22) + datetime.timedelta(days=14 * k)).isoformat() for k in range(12)]
        self.running = Loan.objects.create(
            ref='RNAOLD1', uid='RNA1', owner=self.p, amount=Decimal('3000'),
            repayment_amount=Decimal('376.96'), number_of_fortnights=12,
            repayment_start_date=datetime.date(2026, 7, 22),
            total_outstanding=Decimal('4140.09'), total_loan_amount=Decimal('4522.09'),
            total_arrears=Decimal('0'), fortnights_settled=0, status='RUNNING',
            category='FUNDED', funded_category='ACTIVE', repayment_dates=json.dumps(dates))
        self.new = Loan.objects.create(
            ref='RNANEW1', uid='RNA1', owner=self.p, amount=Decimal('2000'),
            interest=Decimal('1316.00'), total_loan_amount=Decimal('3316.00'),
            repayment_amount=Decimal('331.60'), number_of_fortnights=10,
            repayment_start_date=datetime.date(2026, 7, 22),
            total_outstanding=Decimal('3316.00'), status='PENDING', category='PENDING')

    def test_refinance_allowed_helper(self):
        from loan.refinance import refinance_allowed
        self.assertFalse(refinance_allowed())

    def test_apply_refinance_refuses(self):
        from loan.refinance import apply_refinance
        req = RequestFactory().post('/')
        with self.assertRaises(ValueError):
            apply_refinance(req, self.running, self.new, notify=False, today=datetime.date(2026, 7, 22))
        # Neither loan was mutated by the aborted attempt.
        self.running.refresh_from_db()
        self.assertEqual(self.running.funded_category, 'ACTIVE')

    def test_add_additional_loan_view_blocked(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        from admin1.models import Location
        su = User.objects.create_user(email='rnastaff@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, first_name='Rna', last_name='Staff',
                                        email='rnastaff@x.com', uid='RNAS1', category='STAFF')
        StaffProfile.objects.create(user=sp)
        client = Client(); client.force_login(su)
        loc = Location.objects.create(name='Test Loc', province='NCD')
        self.p.activation = 1
        self.p.save()

        r = client.post('/custom/add-additional-loan/', {
            # LoanMasta's amount choices increase by K200 from K500, so K1100
            # is the nearest valid choice for exercising the refinance guard.
            'owner': self.p.pk, 'location': loc.pk, 'amount': '1100',
            'funding_date': '2026-07-22', 'number_of_fortnights': '10',
            'repayment_start_date': '2026-08-05',
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Refinance Not Allowed')
        # No new loan was created for this attempt (still just running + new).
        from loan.models import Loan
        self.assertEqual(Loan.objects.filter(owner=self.p).count(), 2)


class LoanAmountLimitTests(TestCase):
    """Loan amount is checked against the (per-client-overridable) min/max
    on every creation path — including Add Additional Loan, which previously
    had no amount-limit check at all."""

    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        from admin1.models import AdminSettings, Location
        # The Loan.amount field itself is a fixed dropdown (K500-K5000 in K100
        # steps, from settings.LOAN_MIN_AMOUNT/LOAN_MAX_AMOUNT at process start —
        # see loan.models.generate_amount_choices) — independent of AdminSettings,
        # so the business-rule minimum here must sit ABOVE the dropdown's own
        # floor (K500) for a valid-choice amount to actually trip it.
        AdminSettings.objects.create(settings_name='setting1', refinance_type='OFFSET_BALANCE',
                                     loan_min_amount=Decimal('1000'), loan_max_amount=Decimal('10000'),
                                     default_interest_rate=Decimal('20'), default_interest_type='PERCENTAGE')
        su = User.objects.create_user(email='limstaff@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, first_name='Lim', last_name='Staff',
                                        email='limstaff@x.com', uid='LIMS1', category='STAFF')
        StaffProfile.objects.create(user=sp)
        self.client = Client(); self.client.force_login(su)
        self.loc = Location.objects.create(name='Test Loc', province='NCD')

        cu = User.objects.create_user(email='limclient@x.com', password='pw')
        self.cp = UserProfile.objects.create(user=cu, uid='LIMC1', first_name='Lim', last_name='Client',
                                             email='limclient@x.com', activation=1)

    def test_add_new_loan_below_minimum_rejected(self):
        from loan.models import Loan
        r = self.client.post('/custom/add-new-loan/', {
            'owner': self.cp.pk, 'location': self.loc.pk, 'amount': '500',
            'number_of_fortnights': '10', 'funding_date': '2026-07-22',
            'repayment_start_date': '2026-07-22', 'total_outstanding': '0',
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'must be more than')
        self.assertFalse(Loan.objects.filter(owner=self.cp).exists())

    def test_add_additional_loan_below_minimum_rejected(self):
        from loan.models import Loan
        dates = [(datetime.date(2026, 6, 10) + datetime.timedelta(days=14 * k)).isoformat() for k in range(5)]
        running = Loan.objects.create(
            ref='LIMOLD1', uid='LIMC1', owner=self.cp, amount=Decimal('3000'),
            repayment_amount=Decimal('376.96'), number_of_fortnights=5,
            repayment_start_date=datetime.date(2026, 6, 10),
            total_outstanding=Decimal('1884.80'), total_arrears=Decimal('0'),
            fortnights_settled=0, status='RUNNING', category='FUNDED',
            funded_category='ACTIVE', repayment_dates=json.dumps(dates),
        )
        r = self.client.post('/custom/add-additional-loan/', {
            'owner': self.cp.pk, 'location': self.loc.pk, 'amount': '500',
            'funding_date': '2026-07-22', 'number_of_fortnights': '10',
            'repayment_start_date': '2026-08-05',
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'must be more than')
        # Only the pre-existing running loan — the additional-loan attempt was rejected.
        self.assertEqual(Loan.objects.filter(owner=self.cp).count(), 1)


class ExistingLoanFunctionsHubTests(TestCase):
    """The consolidated staff nav page and the loan-scoped file-upload feature."""

    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        su = User.objects.create_user(email='elfstaff@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, first_name='Elf', last_name='Staff',
                                        email='elfstaff@x.com', uid='ELFS1', category='STAFF')
        StaffProfile.objects.create(user=sp)
        self.client = Client(); self.client.force_login(su)

        cu = User.objects.create_user(email='elfclient@x.com', password='pw')
        self.cp = UserProfile.objects.create(user=cu, uid='ELFC1', first_name='Elf', last_name='Client',
                                             email='elfclient@x.com')
        from loan.models import Loan
        self.loan = Loan.objects.create(ref='ELFLOAN1', uid='ELFC1', owner=self.cp,
                                        repayment_amount=Decimal('100'), category='FUNDED',
                                        funded_category='ACTIVE', status='RUNNING',
                                        repayment_dates=json.dumps(['2026-06-10']))

    def test_hub_page_renders_all_six_buttons(self):
        r = self.client.get('/staff/existing-loan-functions/')
        self.assertEqual(r.status_code, 200)
        for label in ['Add Existing Loan with Details', 'Add Additional Loan',
                      'Upload Files for Existing Loan', 'Add Existing Loans in Bulk',
                      'Add Existing Statements in Bulk', 'Add a Loan Statement']:
            self.assertContains(r, label)

    def test_nav_consolidated_to_one_item(self):
        r = self.client.get('/staff/existing-loan-functions/')
        self.assertContains(r, 'Existing Loan Functions')
        self.assertNotContains(r, 'Add Existing Statements<')

    def test_loan_files_select_lists_loan(self):
        r = self.client.get('/admin/loan-files/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ELFLOAN1')

    def test_loan_files_upload_for_selected_loan(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from loan.models import LoanFile
        r = self.client.get(f'/admin/loan-files/{self.loan.ref}/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Application Form')

        upload = SimpleUploadedFile('app.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        r = self.client.post(f'/admin/loan-files/{self.loan.ref}/', {
            'field': 'application_form', 'file': upload,
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        lf = LoanFile.objects.get(loan=self.loan)
        self.assertTrue(lf.application_form)


class InstructionsPagesRenderTests(TestCase):
    """The admin/staff/user Instructions pages are full of {% url %} tags —
    a renamed or removed URL name would 500 the page. Render each with a
    real logged-in user of the right role to catch that."""

    def test_admin_instructions_renders(self):
        from django.test import Client
        from accounts.models import User, UserProfile
        su = User.objects.create_user(email='instradmin@x.com', password='pw', is_active=True)
        su.active = True; su.staff = True; su.admin = True; su.is_superuser = True; su.save()
        UserProfile.objects.create(user=su, category='ADMIN', activation=1, uid='IA1',
                                   first_name='Instr', last_name='Admin', email='instradmin@x.com')
        c = Client(); c.force_login(su)
        r = c.get('/admin/admin_instructions/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Loan Credits')

    def test_staff_instructions_renders(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        su = User.objects.create_user(email='instrstaff@x.com', password='pw', is_active=True)
        sp = UserProfile.objects.create(user=su, first_name='Instr', last_name='Staff',
                                        email='instrstaff@x.com', uid='IS1', category='STAFF')
        StaffProfile.objects.create(user=sp)
        c = Client(); c.force_login(su)
        r = c.get('/staff/instructions/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Existing Loan Functions')

    def test_user_instructions_renders(self):
        from django.test import Client
        from accounts.models import User, UserProfile
        cu = User.objects.create_user(email='instruser@x.com', password='pw', is_active=True)
        UserProfile.objects.create(user=cu, uid='IU1', first_name='Instr', last_name='User',
                                   email='instruser@x.com', activation=1)
        c = Client(); c.force_login(cu)
        r = c.get('/accounts/instructions/')
        self.assertEqual(r.status_code, 200)


class PaymentStatusRemovalTests(SimpleTestCase):
    def test_payment_model_and_form_have_no_status_field(self):
        from loan.forms import PaymentForm
        from loan.models import Payment

        self.assertNotIn('status', {field.name for field in Payment._meta.get_fields()})
        self.assertNotIn('status', PaymentForm.base_fields)
