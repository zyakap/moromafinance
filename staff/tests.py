from decimal import Decimal

from django.test import TestCase

from admin1.models import AdminSettings
from staff.forms import CreateLoanForm

# Create your tests here.


class CreateLoanFormAmountChoicesTests(TestCase):
    def test_default_minimum_loan_amount_is_k100(self):
        form = CreateLoanForm()

        first_value, _label = list(form.fields['amount'].choices)[0]
        self.assertEqual(Decimal(str(first_value)), Decimal('100'))

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
