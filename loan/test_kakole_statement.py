"""End-to-end import of a real Blackrose statement (Joe Kakole, 12780532).

Guards the whole upload path on a statement taken verbatim from a client
printout: two advances, twenty repayments, and a closing balance the replayed
ledger has to land on exactly. The interesting shapes here are the second
advance part-way through the schedule and the two rows dated 2/3/2026 whose
PNOs (4/26 then 3/26) are printed out of order.

This statement prints its dates month-first, unlike the day-first fixtures in
``test_blackrose``. Read the wrong way round, '10/31/2025' is not a wrong date
but no date at all, and the row is dropped in silence -- which cost eleven of
these twenty-one rows, and two thirds of the balance, until ``to_date`` learned
to sniff the order per statement.
"""
import datetime
import os
import unittest
from decimal import Decimal

from django.conf import settings
from django.test import TestCase

from loan import blackrose
from loan.models import Loan, Statement as StatementLine, Payment
from accounts.models import UserProfile


#: Verbatim transaction rows from the printed statement.
STATEMENT_ROWS = """\
10/31/2025 Lon 1,000.00 2,080.00 0.00 0.00 0.00 2,080.00
11/11/2025 Rep 0.00 0.00 23/25 11/12/2025 78.46 0.00 0.00 2,001.54
11/25/2025 Rep 0.00 0.00 24/25 11/26/2025 78.46 0.00 0.00 1,923.08
12/9/2025 Rep 0.00 0.00 25/25 12/10/2025 78.46 0.00 0.00 1,844.62
12/23/2025 Rep 0.00 0.00 26/25 12/24/2025 78.46 0.00 0.00 1,766.16
1/6/2026 Rep 0.00 0.00 1/26 1/7/2026 78.46 0.00 0.00 1,687.70
1/20/2026 Rep 0.00 0.00 2/26 1/21/2026 78.46 0.00 0.00 1,609.24
2/3/2026 Rep 0.00 0.00 4/26 2/18/2026 78.46 0.00 0.00 1,530.78
2/3/2026 Rep 0.00 0.00 3/26 2/4/2026 78.46 0.00 0.00 1,452.32
2/10/2026 Lon 500.00 1,040.00 0.00 0.00 0.00 2,492.32
3/3/2026 Rep 0.00 0.00 5/26 3/4/2026 78.46 0.00 0.00 2,413.86
3/17/2026 Rep 0.00 0.00 6/26 3/18/2026 78.46 0.00 0.00 2,335.40
3/31/2026 Rep 0.00 0.00 7/26 4/1/2026 78.46 0.00 0.00 2,256.94
4/14/2026 Rep 0.00 0.00 8/26 4/15/2026 78.46 0.00 0.00 2,178.48
4/28/2026 Rep 0.00 0.00 9/26 4/29/2026 78.46 0.00 0.00 2,100.02
5/12/2026 Rep 0.00 0.00 10/26 5/13/2026 78.46 0.00 0.00 2,021.56
5/26/2026 Rep 0.00 0.00 11/26 5/27/2026 78.46 0.00 0.00 1,943.10
6/9/2026 Rep 0.00 0.00 12/26 6/10/2026 78.46 0.00 0.00 1,864.64
6/23/2026 Rep 0.00 0.00 13/26 6/24/2026 78.46 0.00 0.00 1,786.18
7/7/2026 Rep 0.00 0.00 14/26 7/8/2026 78.46 0.00 0.00 1,707.72
7/21/2026 Rep 0.00 0.00 15/26 7/22/2026 78.46 0.00 0.00 1,629.26
"""

CLOSING_BALANCE = Decimal('1629.26')

#: The statement these rows were copied from. Kept optional so the suite still
#: runs on a checkout that does not carry client paperwork.
SAMPLE_PDF = os.path.join(settings.BASE_DIR, 'client_documents',
                          'Joe_Kakole_Statement1.pdf')


class KakoleStatementTests(TestCase):

    def _statement(self):
        statement = blackrose.parse_text(STATEMENT_ROWS)
        # parse_text cannot split the header block, so supply what staff would
        # type on the review screen.
        statement.client_name = 'Joe Kakole'
        statement.client_code = '12780532'
        statement.employer = 'Eastern Highlands Provincial Health Authority'
        statement.address = 'P.O Box 392 Goroka, EHP, PNG'
        return statement

    def test_every_printed_row_is_read(self):
        statement = self._statement()
        self.assertEqual(len(statement.txns), 21)
        advances = [t for t in statement.txns if t.kind == 'ADVANCE']
        repayments = [t for t in statement.txns if t.kind == 'REPAYMENT']
        self.assertEqual(len(advances), 2)
        self.assertEqual(len(repayments), 19)
        self.assertEqual(statement.txns[-1].balance, CLOSING_BALANCE)

    def test_totals_match_the_printout(self):
        plan = blackrose.derive(self._statement())
        self.assertEqual(plan['total_advanced'], Decimal('1500.00'))
        self.assertEqual(plan['total_repayable'], Decimal('3120.00'))
        self.assertEqual(plan['repayment_amount'], Decimal('78.46'))
        self.assertEqual(plan['first_date'], datetime.date(2025, 10, 31))

    def test_import_creates_client_loan_and_statement_lines(self):
        statement = self._statement()
        plan = blackrose.derive(statement)

        before = UserProfile.objects.count()
        loan, profile, created = blackrose.import_statement(statement, plan)

        # client
        self.assertTrue(created)
        self.assertEqual(UserProfile.objects.count(), before + 1)
        self.assertEqual(profile.first_name, 'Joe')
        self.assertEqual(profile.last_name, 'Kakole')

        # loan
        self.assertIsNotNone(loan.pk)
        self.assertEqual(Loan.objects.filter(pk=loan.pk).count(), 1)
        self.assertEqual(loan.existing_code, '12780532')
        self.assertEqual(loan.classification, 'OLD')
        self.assertEqual(loan.amount, Decimal('1500.00'))
        self.assertEqual(loan.total_loan_amount, Decimal('3120.00'))
        self.assertEqual(loan.repayment_amount, Decimal('78.46'))

        # the replayed ledger has to land on the printed closing balance
        self.assertEqual(loan.total_outstanding, CLOSING_BALANCE)

        # statement lines + payments
        lines = StatementLine.objects.filter(loanref=loan)
        payments = Payment.objects.filter(loanref=loan)
        self.assertGreaterEqual(lines.count(), 21)
        self.assertEqual(payments.count(), 19)

    def test_import_records_terms_and_credit_consent(self):
        """A migrated loan was signed for on paper before it ever reached here."""
        statement = self._statement()
        plan = blackrose.derive(statement)
        _loan, profile, _created = blackrose.import_statement(statement, plan)
        profile.refresh_from_db()
        self.assertEqual(profile.terms_consent, 'YES')
        self.assertEqual(profile.credit_consent, 'YES')

    def test_consent_is_recorded_on_an_existing_client_too(self):
        from accounts.models import User
        user = User.objects.create_user(email='joe.k@example.com', password='pw12345!')
        existing = UserProfile.objects.create(
            user=user, first_name='Joe', last_name='Kakole', activation=1,
            terms_consent='NO', credit_consent='NO')

        statement = self._statement()
        plan = blackrose.derive(statement)
        _loan, profile, created = blackrose.import_statement(
            statement, plan, profile=existing)

        self.assertFalse(created)
        self.assertEqual(profile.pk, existing.pk)
        existing.refresh_from_db()
        self.assertEqual(existing.terms_consent, 'YES')
        self.assertEqual(existing.credit_consent, 'YES')


@unittest.skipUnless(os.path.exists(SAMPLE_PDF), 'sample statement PDF not present')
class KakolePdfTests(TestCase):
    """The same statement through the real upload path, PDF and all."""

    def _parse(self):
        with open(SAMPLE_PDF, 'rb') as fh:
            return blackrose.parse_pdf(fh)

    def test_client_block_is_read_off_the_header(self):
        statement = self._parse()
        self.assertEqual(statement.client_name, 'Joe Kakole')
        self.assertEqual(statement.client_code, '12780532')
        self.assertEqual(statement.employer,
                         'Eastern Highlands Provincial Health Authority')
        self.assertIn('Goroka', statement.address)
        self.assertEqual(statement.lender_name, 'Moroma Finance Ltd')
        self.assertEqual(statement.warnings, [])

    def test_month_first_dates_are_read_the_right_way_round(self):
        statement = self._parse()
        self.assertEqual(len(statement.txns), 21)
        # The row that used to disappear: 10/31/2025 is 31 October, not day 10
        # of a 31st month.
        first = statement.txns[0]
        self.assertEqual(first.date, datetime.date(2025, 10, 31))
        self.assertEqual(first.loan, Decimal('1000.00'))
        self.assertEqual(statement.txns[-1].balance, CLOSING_BALANCE)

    def test_upload_creates_client_loan_and_statements(self):
        statement = self._parse()
        plan = blackrose.derive(statement)
        loan, profile, created = blackrose.import_statement(statement, plan)

        self.assertTrue(created)
        self.assertEqual(profile.first_name, 'Joe')
        self.assertEqual(profile.last_name, 'Kakole')
        self.assertEqual(loan.existing_code, '12780532')
        self.assertEqual(loan.amount, Decimal('1500.00'))
        self.assertEqual(loan.total_loan_amount, Decimal('3120.00'))
        self.assertEqual(loan.total_outstanding, CLOSING_BALANCE)
        self.assertGreaterEqual(StatementLine.objects.filter(loanref=loan).count(), 21)
        self.assertEqual(Payment.objects.filter(loanref=loan).count(), 19)


def _tesseract_available():
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


@unittest.skipUnless(os.path.exists(SAMPLE_PDF), 'sample statement PDF not present')
@unittest.skipUnless(_tesseract_available(), 'tesseract OCR engine not installed')
class KakoleScannedTests(TestCase):
    """The same statement again, but scanned -- no text layer, OCR only.

    The scan is made by rendering the real statement to images and rebuilding a
    PDF from them, which is what a statement that has been through a photocopier
    looks like to pdfplumber: zero words.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import io
        import pypdfium2
        with open(SAMPLE_PDF, 'rb') as fh:
            document = pypdfium2.PdfDocument(fh.read())
        try:
            images = [document[i].render(scale=300 / 72).to_pil().convert('RGB')
                      for i in range(len(document))]
        finally:
            document.close()
        buffer = io.BytesIO()
        images[0].save(buffer, format='PDF', save_all=True,
                       append_images=images[1:], resolution=300.0)
        cls.scanned = buffer.getvalue()

    def _parse(self):
        import io
        return blackrose.parse_pdf(io.BytesIO(self.scanned))

    def test_the_scan_really_has_no_text_layer(self):
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(self.scanned)) as pdf:
            self.assertEqual(sum(len(p.extract_words()) for p in pdf.pages), 0)

    def test_ocr_recovers_the_same_statement(self):
        statement = self._parse()
        self.assertEqual(statement.client_name, 'Joe Kakole')
        self.assertEqual(statement.client_code, '12780532')
        self.assertEqual(len(statement.txns), 21)
        self.assertEqual(statement.txns[0].date, datetime.date(2025, 10, 31))
        self.assertEqual(statement.txns[-1].balance, CLOSING_BALANCE)

    def test_staff_are_told_the_page_was_ocrd(self):
        statement = self._parse()
        self.assertTrue(any('OCR' in w for w in statement.warnings),
                        f'expected an OCR warning, got {statement.warnings}')

    def test_scanned_import_matches_the_clean_one(self):
        statement = self._parse()
        plan = blackrose.derive(statement)
        loan, profile, created = blackrose.import_statement(statement, plan)
        self.assertTrue(created)
        self.assertEqual(profile.last_name, 'Kakole')
        self.assertEqual(loan.amount, Decimal('1500.00'))
        self.assertEqual(loan.total_outstanding, CLOSING_BALANCE)
        self.assertEqual(Payment.objects.filter(loanref=loan).count(), 19)
