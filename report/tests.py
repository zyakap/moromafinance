import datetime
import json
from decimal import Decimal

from django.test import TestCase


class ExpectedVsActualAdvanceArrearsColumnTests(TestCase):
    """'Expected vs Actual' reports (by-client, per-employer drill, and the
    employer-grouped summary) carry an 'Advance / (Arrears)' column showing
    each loan's CURRENT standing — advance_balance minus total_arrears — so a
    defaulting client is flagged even outside the report's date window."""

    def setUp(self):
        from accounts.models import User, UserProfile
        from loan.models import Loan
        today = datetime.date.today()
        dates = [(today - datetime.timedelta(days=3) + datetime.timedelta(days=14 * k)).isoformat()
                 for k in range(10)]

        u1 = User.objects.create_user(email='adv@x.com', password='x')
        p1 = UserProfile.objects.create(user=u1, uid='ADVU', first_name='Adv', last_name='One',
                                        employer='ACME')
        self.adv_loan = Loan.objects.create(
            ref='ADVREF', owner=p1, category='FUNDED', funded_category='ACTIVE', status='RUNNING',
            amount=Decimal('5000'), total_outstanding=Decimal('4000'), repayment_amount=Decimal('353.95'),
            number_of_fortnights=10, repayment_start_date=today - datetime.timedelta(days=3),
            fortnights_settled=1, advance_balance=Decimal('250.00'), total_arrears=Decimal('0'),
            repayment_dates=json.dumps(dates))

        u2 = User.objects.create_user(email='arr@x.com', password='x')
        p2 = UserProfile.objects.create(user=u2, uid='ARRU', first_name='Arr', last_name='Two',
                                        employer='ACME')
        self.arr_loan = Loan.objects.create(
            ref='ARRREF', owner=p2, category='FUNDED', funded_category='ACTIVE', status='DEFAULTED',
            amount=Decimal('5000'), total_outstanding=Decimal('4500'), repayment_amount=Decimal('353.95'),
            number_of_fortnights=10, repayment_start_date=today - datetime.timedelta(days=3),
            fortnights_settled=1, advance_balance=Decimal('0'), total_arrears=Decimal('400.00'),
            repayment_dates=json.dumps(dates))

        self.start = today - datetime.timedelta(days=4)
        self.end = today

    def test_by_client_shows_advance_and_arrears(self):
        from report.advanced_reports import _expected_vs_actual_rows
        columns, rows = _expected_vs_actual_rows(self.start, self.end, by_client=True)
        self.assertIn('Advance / (Arrears)', columns)
        idx = columns.index('Advance / (Arrears)')
        by_ref = {r[0]: r for r in rows}
        self.assertEqual(by_ref['ADVREF'][idx], 'K250.00')
        self.assertEqual(by_ref['ARRREF'][idx], 'K-400.00')

    def test_employer_drill_shows_advance_and_arrears(self):
        from report.advanced_reports import _expected_vs_actual_rows
        columns, rows = _expected_vs_actual_rows(self.start, self.end, employer='ACME')
        idx = columns.index('Advance / (Arrears)')
        by_ref = {r[0]: r for r in rows}
        self.assertEqual(by_ref['ADVREF'][idx], 'K250.00')
        self.assertEqual(by_ref['ARRREF'][idx], 'K-400.00')

    def test_employer_grouped_summary_nets_the_column(self):
        from report.advanced_reports import _expected_vs_actual_rows
        columns, rows = _expected_vs_actual_rows(self.start, self.end)
        idx = columns.index('Advance / (Arrears)')
        acme_row = next(r for r in rows if r[0] == 'ACME')
        # 250.00 advance - 400.00 arrears = -150.00 net for the employer group
        self.assertEqual(acme_row[idx], 'K-150.00')
