from decimal import Decimal

from django.conf import settings
from django.test import TestCase

from admin1.models import AdminSettings
from staff.forms import CreateLoanForm


class CreateLoanFormAmountChoicesTests(TestCase):
    def test_default_minimum_loan_amount_falls_back_to_settings(self):
        # With no AdminSettings row the form falls back to LOAN_MIN_AMOUNT.
        # Assert against the setting rather than a literal: each tenant's
        # published schedule starts at its own minimum (drams K100, moroma K500).
        form = CreateLoanForm()

        first_value, _label = list(form.fields['amount'].choices)[0]
        self.assertEqual(
            Decimal(str(first_value)),
            Decimal(str(settings.LOAN_MIN_AMOUNT)),
        )


class CreateLoanFormChoiceRefreshTests(TestCase):
    """Loan.amount / Loan.number_of_fortnights declare their choices at
    model-import time, so the forms must rebuild them per request. Without
    that, an admin who changes Loan Settings sees no effect until the process
    restarts — the bug this guards against."""

    def test_initial_form_uses_current_configured_loan_amount_limits(self):
        AdminSettings.objects.create(
            settings_name='setting1',
            loan_min_amount=Decimal('750'),
            loan_max_amount=Decimal('1150'),
            increment_amount=Decimal('200'),
        )

        form = CreateLoanForm()

        self.assertEqual(
            [Decimal(str(value)) for value, _label in form.fields['amount'].choices],
            [Decimal('750'), Decimal('950'), Decimal('1150')],
        )

    def test_initial_form_uses_current_configured_fortnight_limits(self):
        AdminSettings.objects.create(
            settings_name='setting1',
            min_fn=4,
            max_fn=10,
            increment_fn=2,
        )

        form = CreateLoanForm()

        self.assertEqual(
            [value for value, _label in form.fields['number_of_fortnights'].choices],
            [4, 6, 8, 10],
        )
