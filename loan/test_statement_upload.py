"""Tests for the historical statement upload (staff "Add a Loan Statement").

This path was dead: it called an undefined ``create_payment`` and passed a
non-existent ``interest_on_default`` field to Statement, both inside a bare
``except:`` that swallowed the error and reported "You did not upload any
file". It also re-fetched the saved upload over HTTP from /media/, which is
behind the auth gate. These tests pin down the behaviour it should have had.

    DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
        python manage.py test loan.test_statement_upload
"""
import datetime
import io
import json
from decimal import Decimal

from django.test import TestCase

from loan.functions import (StatementUploadError, apply_statement_row,
                            read_statement_upload, reconcile_receivables)
from loan.models import Loan, Payment, Statement


def _spreadsheet(rows, columns=('date', 'comment', 'mode', 'debit', 'credit')):
    """An in-memory .xlsx of the statement-upload shape."""
    import pandas as pd
    buffer = io.BytesIO()
    pd.DataFrame(rows, columns=list(columns)).to_excel(buffer, index=False)
    buffer.seek(0)
    buffer.name = 'statement.xlsx'
    return buffer


class StatementUploadTestCase(TestCase):
    """A K1,000 loan repayable at K1,200 over 6 fortnights, 3 still to run."""

    def setUp(self):
        from accounts.models import User, UserProfile, StaffProfile
        staff_user = User.objects.create_user(email='su@x.com', password='pw', is_active=True)
        staff_profile = UserProfile.objects.create(user=staff_user, first_name='Up', last_name='Staff',
                                                   email='su@x.com', uid='UPS1', category='STAFF')
        self.officer = StaffProfile.objects.create(user=staff_profile)
        self.staff_user = staff_user

        client_user = User.objects.create_user(email='uc@x.com', password='pw')
        self.owner = UserProfile.objects.create(user=client_user, first_name='Up', last_name='Client',
                                                email='uc@x.com', uid='UPC1')
        dates = ['2026-01-07', '2026-01-21', '2026-02-04',
                 '2026-02-18', '2026-03-04', '2026-03-18']
        self.loan = Loan.objects.create(
            ref='UPL1', uid='UPC1', owner=self.owner, category='FUNDED',
            funded_category='ACTIVE', status='RUNNING',
            amount=Decimal('1000.00'), interest=Decimal('200.00'),
            total_loan_amount=Decimal('1200.00'), repayment_amount=Decimal('200.00'),
            number_of_fortnights=6, fortnights_settled=3,
            repayment_start_date=datetime.date(2026, 1, 7),
            repayment_dates=json.dumps(dates),
            principal_loan_receivable=Decimal('500.00'),
            ordinary_interest_receivable=Decimal('100.00'),
            default_interest_receivable=Decimal('0.00'),
            total_outstanding=Decimal('600.00'),
        )

    def reload(self):
        self.loan.refresh_from_db()
        return self.loan


class ApplyRowTests(StatementUploadTestCase):
    def test_repayment_reduces_the_balance_and_records_a_payment(self):
        apply_statement_row(self.loan, datetime.date(2026, 2, 18), 'Deduction',
                            'PAYROLL DEDUCTION', Decimal('200'), Decimal('0'),
                            officer=self.officer)
        loan = self.reload()
        self.assertEqual(loan.total_outstanding, Decimal('400.00'))
        self.assertEqual(loan.total_paid, Decimal('200.00'))
        self.assertEqual(loan.number_of_repayments, 1)
        self.assertEqual(loan.last_repayment_date, datetime.date(2026, 2, 18))

        payment = Payment.objects.get(loanref=loan)
        self.assertEqual(payment.amount, Decimal('200.00'))
        self.assertEqual(payment.mode, 'PAYROLL DEDUCTION')
        self.assertEqual(payment.officer, self.officer)

    def test_repayment_splits_pro_rata_across_the_receivables(self):
        """K200 against a 500/100 principal/interest balance of 600."""
        apply_statement_row(self.loan, datetime.date(2026, 2, 18), '', '',
                            Decimal('200'), Decimal('0'))
        loan = self.reload()
        self.assertEqual(loan.principal_loan_paid, Decimal('166.67'))
        self.assertEqual(loan.interest_paid, Decimal('33.33'))
        self.assertEqual(loan.principal_loan_receivable, Decimal('333.33'))
        self.assertEqual(loan.ordinary_interest_receivable, Decimal('66.67'))

    def test_repayment_advances_the_schedule_cursor(self):
        from loan import schedule as sched
        apply_statement_row(self.loan, datetime.date(2026, 2, 18), '', '',
                            Decimal('200'), Decimal('0'))
        loan = self.reload()
        self.assertEqual(sched.settled_count(loan), 4)
        self.assertEqual(loan.next_payment_date, datetime.date(2026, 3, 4))

    def test_missed_repayment_charges_default_interest(self):
        from admin1.models import AdminSettings
        AdminSettings.objects.create(settings_name='setting1', default_interest_rate=20,
                                     default_interest_type='PERCENTAGE')
        apply_statement_row(self.loan, datetime.date(2026, 2, 18), 'Missed', '',
                            Decimal('0'), Decimal('0'))
        loan = self.reload()
        # 20% of the K200 scheduled repayment.
        self.assertEqual(loan.total_outstanding, Decimal('640.00'))
        self.assertEqual(loan.default_interest_receivable, Decimal('40.00'))
        self.assertEqual(loan.total_arrears, Decimal('200.00'))
        self.assertEqual(loan.number_of_defaults, 1)
        self.assertEqual(loan.status, 'DEFAULTED')

    def test_default_line_uses_the_real_statement_fields(self):
        """The old code passed ``interest_on_default``, which is not a field on
        Statement — every default row raised TypeError."""
        apply_statement_row(self.loan, datetime.date(2026, 2, 18), 'Missed', '',
                            Decimal('0'), Decimal('0'))
        line = Statement.objects.get(loanref=self.loan, type='DEFAULT')
        self.assertEqual(line.default_amount, Decimal('200.00'))
        self.assertEqual(line.default_interest, line.credit)
        self.assertEqual(line.balance, self.reload().total_outstanding)

    def test_arrears_never_exceed_the_outstanding_balance(self):
        for _ in range(6):
            apply_statement_row(self.loan, datetime.date(2026, 2, 18), '', '',
                                Decimal('0'), Decimal('0'))
        loan = self.reload()
        self.assertLessEqual(loan.total_arrears, loan.total_outstanding)

    def test_credit_row_increases_the_balance_and_the_receivable(self):
        apply_statement_row(self.loan, datetime.date(2026, 2, 18), 'Fee', '',
                            Decimal('0'), Decimal('50'))
        loan = self.reload()
        self.assertEqual(loan.total_outstanding, Decimal('650.00'))
        self.assertEqual(loan.principal_loan_receivable, Decimal('550.00'))
        line = Statement.objects.get(loanref=loan, type='OTHER')
        self.assertEqual(line.credit, Decimal('50.00'))

    def test_repayment_clearing_arrears_returns_the_loan_to_running(self):
        apply_statement_row(self.loan, datetime.date(2026, 2, 18), '', '',
                            Decimal('0'), Decimal('0'))
        self.assertEqual(self.reload().status, 'DEFAULTED')
        apply_statement_row(self.loan, datetime.date(2026, 3, 4), '', '',
                            Decimal('300'), Decimal('0'))
        loan = self.reload()
        self.assertEqual(loan.total_arrears, Decimal('0.00'))
        self.assertEqual(loan.status, 'RUNNING')

    def test_final_repayment_completes_the_loan(self):
        apply_statement_row(self.loan, datetime.date(2026, 3, 18), 'Payout', '',
                            Decimal('600'), Decimal('0'))
        loan = self.reload()
        self.assertEqual(loan.total_outstanding, Decimal('0.00'))
        self.assertEqual(loan.status, 'COMPLETED')
        self.assertEqual(loan.funded_category, 'COMPLETED')

    def test_a_row_with_both_a_debit_and_a_credit_is_rejected(self):
        with self.assertRaises(StatementUploadError):
            apply_statement_row(self.loan, datetime.date(2026, 2, 18), '', '',
                                Decimal('100'), Decimal('100'))

    def test_a_negative_amount_is_rejected(self):
        with self.assertRaises(StatementUploadError):
            apply_statement_row(self.loan, datetime.date(2026, 2, 18), '', '',
                                Decimal('-100'), Decimal('0'))

    def test_a_missing_date_is_rejected(self):
        with self.assertRaises(StatementUploadError):
            apply_statement_row(self.loan, None, '', '', Decimal('100'), Decimal('0'))

    def test_reconcile_snaps_receivables_onto_the_balance(self):
        self.loan.total_outstanding = Decimal('600.00')
        self.loan.principal_loan_receivable = Decimal('499.99')
        self.loan.ordinary_interest_receivable = Decimal('100.00')
        self.loan.default_interest_receivable = Decimal('0.00')
        reconcile_receivables(self.loan)
        total = (self.loan.principal_loan_receivable + self.loan.ordinary_interest_receivable
                 + self.loan.default_interest_receivable)
        self.assertEqual(total, Decimal('600.00'))
        self.assertEqual(self.loan.principal_loan_receivable, Decimal('500.00'))


class ReadSpreadsheetTests(StatementUploadTestCase):
    def test_rows_are_normalised(self):
        rows = read_statement_upload(_spreadsheet([
            ['2026-02-18', 'Deduction', 'PAYROLL DEDUCTION', 200, 0],
        ]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['date'], datetime.date(2026, 2, 18))
        self.assertEqual(rows[0]['comment'], 'Deduction')
        self.assertEqual(rows[0]['debit'], Decimal('200'))
        self.assertEqual(rows[0]['row_number'], 2)

    def test_a_text_date_column_is_parsed_day_first(self):
        """PNG spreadsheets are typed dd/mm/yyyy — 05/03 is 5 March."""
        rows = read_statement_upload(_spreadsheet([['05/03/2026', 'x', '', 200, 0]]))
        self.assertEqual(rows[0]['date'], datetime.date(2026, 3, 5))

    def test_an_unparseable_date_names_the_row(self):
        with self.assertRaises(StatementUploadError) as caught:
            read_statement_upload(_spreadsheet([['not a date', 'x', '', 200, 0]]))
        self.assertIn('Row 2', str(caught.exception))

    def test_headers_are_matched_case_insensitively(self):
        rows = read_statement_upload(_spreadsheet(
            [['2026-02-18', 'x', 'CASH', 200, 0]],
            columns=('Date', 'Comment', 'Mode', 'Debit', 'Credit')))
        self.assertEqual(len(rows), 1)

    def test_a_missing_column_is_named_in_the_error(self):
        with self.assertRaises(StatementUploadError) as caught:
            read_statement_upload(_spreadsheet([['2026-02-18', 200]],
                                               columns=('date', 'debit')))
        self.assertIn('comment', str(caught.exception))
        self.assertIn('credit', str(caught.exception))

    def test_blank_trailing_rows_are_skipped(self):
        rows = read_statement_upload(_spreadsheet([
            ['2026-02-18', 'x', '', 200, 0],
            [None, None, None, None, None],
        ]))
        self.assertEqual(len(rows), 1)

    def test_a_file_that_is_not_a_spreadsheet_is_reported(self):
        junk = io.BytesIO(b'this is not a spreadsheet')
        junk.name = 'notes.txt'
        with self.assertRaises(StatementUploadError):
            read_statement_upload(junk)

    def test_a_spreadsheet_with_no_dated_rows_is_reported(self):
        with self.assertRaises(StatementUploadError):
            read_statement_upload(_spreadsheet([[None, None, None, None, None]]))


class UploadStatementViewTests(StatementUploadTestCase):
    def setUp(self):
        super().setUp()
        from django.test import Client
        self.client = Client()
        self.client.force_login(self.staff_user)
        self.url = f'/staff/uploadstatement/loan/{self.loan.ref}/'

    def test_page_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.loan.ref)

    def test_uploading_nothing_is_reported(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Statement.objects.filter(loanref=self.loan).count(), 0)

    def test_a_whole_statement_is_imported(self):
        response = self.client.post(self.url, {'uploadedstatement': _spreadsheet([
            ['2026-02-18', 'Deduction 4', 'PAYROLL DEDUCTION', 200, 0],
            ['2026-03-04', 'Deduction 5', 'PAYROLL DEDUCTION', 200, 0],
            ['2026-03-18', 'Deduction 6', 'PAYROLL DEDUCTION', 200, 0],
        ])})
        self.assertEqual(response.status_code, 200)
        loan = self.reload()
        self.assertEqual(Statement.objects.filter(loanref=loan).count(), 3)
        self.assertEqual(Payment.objects.filter(loanref=loan).count(), 3)
        self.assertEqual(loan.total_outstanding, Decimal('0.00'))
        self.assertEqual(loan.status, 'COMPLETED')

    def test_a_mixed_statement_imports_every_row_type(self):
        self.client.post(self.url, {'uploadedstatement': _spreadsheet([
            ['2026-02-18', 'Deduction', 'PAYROLL DEDUCTION', 200, 0],
            ['2026-03-04', 'Missed', '', 0, 0],
            ['2026-03-18', 'Fee', '', 0, 25],
        ])})
        loan = self.reload()
        types = sorted(Statement.objects.filter(loanref=loan).values_list('type', flat=True))
        self.assertEqual(types, ['DEFAULT', 'OTHER', 'PAYMENT'])
        self.assertEqual(loan.number_of_repayments, 1)
        self.assertEqual(loan.number_of_defaults, 1)

    def test_a_bad_row_rolls_the_whole_upload_back(self):
        """Row 3 is invalid — rows 1 and 2 must not survive."""
        response = self.client.post(self.url, {'uploadedstatement': _spreadsheet([
            ['2026-02-18', 'Deduction 4', 'PAYROLL DEDUCTION', 200, 0],
            ['2026-03-04', 'Deduction 5', 'PAYROLL DEDUCTION', 200, 0],
            ['2026-03-18', 'Broken', '', 100, 100],
        ])})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Row 4')
        loan = self.reload()
        self.assertEqual(Statement.objects.filter(loanref=loan).count(), 0)
        self.assertEqual(Payment.objects.filter(loanref=loan).count(), 0)
        self.assertEqual(loan.total_outstanding, Decimal('600.00'))
        self.assertEqual(loan.fortnights_settled, 3)

    def test_a_missing_column_does_not_touch_the_loan(self):
        response = self.client.post(self.url, {'uploadedstatement': _spreadsheet(
            [['2026-02-18', 200]], columns=('date', 'debit'))})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Statement.objects.filter(loanref=self.loan).count(), 0)

    def test_receivables_still_add_up_after_a_long_statement(self):
        self.client.post(self.url, {'uploadedstatement': _spreadsheet(
            [['2026-02-18', f'Deduction {i}', 'CASH', 33.33, 0] for i in range(10)])})
        loan = self.reload()
        total = (loan.principal_loan_receivable + loan.ordinary_interest_receivable
                 + loan.default_interest_receivable)
        self.assertEqual(total, loan.total_outstanding)

    def test_an_unknown_loan_is_a_404(self):
        self.assertEqual(self.client.get('/staff/uploadstatement/loan/NOPE/').status_code, 404)


class BulkUploadReadTests(StatementUploadTestCase):
    """The two sibling bulk uploads read the posted file the same broken way —
    saving it to MEDIA_ROOT and re-fetching it from settings.DOMAIN + /media/,
    which cannot work now that /media/ requires a logged-in user. They now read
    the upload directly, so at minimum a bad or missing file is reported instead
    of raising."""

    def setUp(self):
        super().setUp()
        from django.test import Client
        from admin1.models import AdminSettings
        AdminSettings.objects.get_or_create(settings_name='setting1')
        self.client = Client()
        self.client.force_login(self.staff_user)

    def test_existing_loans_upload_reports_a_missing_file(self):
        response = self.client.post('/staff/addexistingloan/', {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Loan.objects.count(), 1)  # only the fixture loan

    def test_existing_loans_upload_reports_an_unreadable_file(self):
        junk = io.BytesIO(b'not a spreadsheet')
        junk.name = 'junk.xlsx'
        response = self.client.post('/staff/addexistingloan/', {'uploadedloans': junk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Loan.objects.count(), 1)

    def test_existing_statements_upload_reports_a_missing_file(self):
        response = self.client.post('/staff/upload-statements/', {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Statement.objects.count(), 0)

    def test_existing_statements_upload_reports_an_unreadable_file(self):
        junk = io.BytesIO(b'not a spreadsheet')
        junk.name = 'junk.xlsx'
        response = self.client.post('/staff/upload-statements/', {'uploadedstatementsfile': junk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Statement.objects.count(), 0)
