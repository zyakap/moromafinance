"""The 'Review & Import ALL' button on /staff/blackrose/.

Bulk import is a shortcut past the reading, not past the judgement: a statement
that the review screen would have made someone correct by hand is left in the
waiting list rather than guessed at, and one bad statement must not stop or roll
back the others.
"""
import datetime
import os
import unittest
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile, StaffProfile
from loan import blackrose
from loan.models import BlackroseImport, Loan, Statement as StatementLine

SAMPLE_PDF = os.path.join(settings.BASE_DIR, 'client_documents',
                          'Joe_Kakole_Statement1.pdf')


def _parsed_statement():
    with open(SAMPLE_PDF, 'rb') as fh:
        return blackrose.parse_pdf(fh)


@unittest.skipUnless(os.path.exists(SAMPLE_PDF), 'sample statement PDF not present')
class ImportAllTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='officer@example.com', password='pw12345!')
        # is_staff is a read-only property over this field; check_staff then
        # looks at the profile's category.
        self.user.staff = True
        self.user.save()
        profile = UserProfile.objects.create(user=self.user, first_name='Ann',
                                             last_name='Officer', activation=1,
                                             category='STAFF')
        StaffProfile.objects.create(user=profile)
        self.client.force_login(self.user)

    def _pending(self, name='Joe Kakole', code='12780532', mutate=None):
        statement = _parsed_statement()
        statement.client_name = name
        statement.client_code = code
        if mutate:
            mutate(statement)
        data = statement.as_dict()
        return BlackroseImport.objects.create(
            file_name=f'{code}.pdf', file_hash=code, status='PENDING',
            client_name=name, client_code=code, parsed=data,
            row_count=len(statement.txns),
            closing_balance=statement.txns[-1].balance,
        )

    def test_button_imports_every_clean_statement(self):
        a = self._pending('Joe Kakole', '12780532')
        b = self._pending('Mary Wari', '12780533')

        response = self.client.post(reverse('blackrose_import_all'), follow=True)
        self.assertEqual(response.status_code, 200)

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.status, 'IMPORTED')
        self.assertEqual(b.status, 'IMPORTED')
        self.assertEqual(Loan.objects.count(), 2)
        self.assertEqual(UserProfile.objects.filter(last_name='Kakole').count(), 1)
        self.assertEqual(UserProfile.objects.filter(last_name='Wari').count(), 1)
        # the whole ledger, not just the loan header
        for record in (a, b):
            self.assertGreaterEqual(
                StatementLine.objects.filter(loanref=record.loan).count(), 21)
            self.assertEqual(record.loan.total_outstanding, Decimal('1629.26'))

    def test_a_statement_needing_a_human_is_left_behind(self):
        clean = self._pending('Joe Kakole', '12780532')

        def blank_the_name(statement):
            statement.client_name = ''
        unnamed = self._pending('', '12780534', mutate=blank_the_name)

        self.client.post(reverse('blackrose_import_all'), follow=True)

        clean.refresh_from_db()
        unnamed.refresh_from_db()
        self.assertEqual(clean.status, 'IMPORTED')
        self.assertEqual(unnamed.status, 'PENDING', 'should stay for manual review')
        self.assertEqual(Loan.objects.count(), 1)

    def test_ocr_warnings_are_not_bulk_imported(self):
        def add_warning(statement):
            statement.warnings.append('Page 1 had no text layer and was read with OCR.')
        flagged = self._pending('Joe Kakole', '12780532', mutate=add_warning)

        self.client.post(reverse('blackrose_import_all'), follow=True)

        flagged.refresh_from_db()
        self.assertEqual(flagged.status, 'PENDING')
        self.assertEqual(Loan.objects.count(), 0)

    def test_get_does_not_import_anything(self):
        record = self._pending()
        self.client.get(reverse('blackrose_import_all'))
        record.refresh_from_db()
        self.assertEqual(record.status, 'PENDING')
        self.assertEqual(Loan.objects.count(), 0)

    def test_nothing_waiting_is_harmless(self):
        response = self.client.post(reverse('blackrose_import_all'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Loan.objects.count(), 0)

    def test_button_is_on_the_page_only_when_something_is_waiting(self):
        empty = self.client.get(reverse('blackrose_statements'))
        self.assertNotContains(empty, 'Review &amp; Import ALL')

        self._pending()
        listed = self.client.get(reverse('blackrose_statements'))
        self.assertContains(listed, 'Review &amp; Import ALL')
        self.assertContains(listed, reverse('blackrose_import_all'))
