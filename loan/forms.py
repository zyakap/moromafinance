
from django import forms
from django.conf import settings
from admin1.models import AdminSettings, get_loan_config, get_effective_max_loan_amount
from loan.models import Loan, LoanFile, Payment, PaymentUploads, generate_amount_choices
from .widgets import DatePickerInput
from .open_repayment import clear_open_repayment, install_open_repayment_handlers, set_open_repayment


class AlescoUploadForm(forms.Form):
    """Upload an Alesco Deduction Variation listing for processing."""
    file = forms.FileField(
        label='Alesco Listing File',
        help_text='Upload the Alesco Deduction Variation Report (.txt).',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.txt,.csv,text/plain'}),
    )


class LoanApplicationForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        user_profile = kwargs.pop('user_profile', None)
        self.user_profile = user_profile
        loan_mode = kwargs.pop('loan_mode', None) or self._resolve_mode(user_profile)
        self.loan_mode = loan_mode
        super().__init__(*args, **kwargs)
        if loan_mode != 'OPEN_REPAYMENT':
            self.fields.pop('repayment_amount', None)
        else:
            self.fields['repayment_amount'].required = True
        try:
            from accounts.forms import apply_form_field_settings
            apply_form_field_settings(self, 'loan_application')
        except Exception:
            pass
        # Rebuild the amount choices so a per-client maximum (higher or lower than
        # the global limit) is honoured in the dropdown/slider.
        if 'amount' in self.fields:
            self._effective_max = get_effective_max_loan_amount(user_profile)
            self.fields['amount'].choices = generate_amount_choices(self._effective_max)

    def _resolve_mode(self, user_profile):
        if user_profile and getattr(user_profile, 'max_loan_amount', None):
            return 'OPEN_REPAYMENT'
        return self.get_loan_mode()

    def get_loan_mode(self):
        try:
            setting = AdminSettings.objects.get(settings_name='setting1')
            return setting.user_loan_application_mode or 'LOCKED'
        except AdminSettings.DoesNotExist:
            return 'LOCKED'

    def clean(self):
        cleaned_data = super().clean()
        self._validate_amount_bounds(cleaned_data)
        if self.loan_mode == 'OPEN_REPAYMENT':
            amount = cleaned_data.get('amount')
            number_of_fortnights = cleaned_data.get('number_of_fortnights')
            repayment_amount = cleaned_data.get('repayment_amount')
            if repayment_amount is None or repayment_amount <= 0:
                self.add_error('repayment_amount', 'Repayment amount must be greater than zero.')
            elif amount is not None and number_of_fortnights is not None and repayment_amount * number_of_fortnights < amount:
                self.add_error('repayment_amount', 'Total repayments must be greater than or equal to the loan amount.')
            else:
                set_open_repayment(repayment_amount)
                self.install_view_handlers()
        else:
            clear_open_repayment()
        return cleaned_data

    def _validate_amount_bounds(self, cleaned_data):
        """Enforce the effective loan-amount range: the global minimum and the
        effective maximum (per-client override if set, else the global limit)."""
        amount = cleaned_data.get('amount')
        if amount is None:
            return
        from decimal import Decimal
        cfg = get_loan_config()
        min_amount = Decimal(str(cfg['loan_min_amount']))
        max_amount = getattr(self, '_effective_max', None) or get_effective_max_loan_amount(self.user_profile)
        amount = Decimal(str(amount))
        if amount < min_amount:
            self.add_error('amount', f'Loan amount must be at least K{min_amount:,.2f}.')
        elif amount > max_amount:
            self.add_error('amount', f'Loan amount cannot exceed K{max_amount:,.2f}.')

    def install_view_handlers(self):
        import sys

        for module_name in ('loan.views',):
            module = sys.modules.get(module_name)
            if module is not None:
                install_open_repayment_handlers(module)

    class Meta:
        model = Loan
        fields = ("amount", "number_of_fortnights", "repayment_amount", "repayment_start_date", "purpose_of_loan")

        widgets = {
            'repayment_start_date' : DatePickerInput(), }
        
class PaymentForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rename statement → Description and make it optional
        if 'statement' in self.fields:
            self.fields['statement'].label = 'Description'
            self.fields['statement'].required = False
        # Apply admin form field settings
        try:
            from accounts.forms import apply_form_field_settings
            apply_form_field_settings(self, 'payment')
        except Exception:
            pass

    class Meta:
        model = Payment
        fields = ('date', 'amount', 'mode', 'statement')
        labels = {
            'statement': 'Description',
        }
        widgets = {
            'date': DatePickerInput(),
        }

class PaymentUploadForm(forms.ModelForm):

    class Meta:
        model = PaymentUploads
        fields = ("payment_proof","type")


class RequiredUploadForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from accounts.forms import apply_form_field_settings
            apply_form_field_settings(self, 'required_uploads')
        except Exception:
            pass

    class Meta:
        model = LoanFile
        fields = ['application_form', 'terms_conditions', 'stat_dec', 'irr_sd_form', 'signed_contract']

class LoanStatementUploadForm(forms.ModelForm):
    
    class Meta:
        model = LoanFile
        fields = ['bank_statement', 'loan_statement1', 'loan_statement2', 'loan_statement3',  'super_statement', 'bank_standing_order']

class WorkUploadForm(forms.ModelForm):
    
    class Meta:
        model = LoanFile
        fields = ['work_confirmation_letter', 'payslip1', 'payslip2',]

class ReceiptUploadForm(forms.ModelForm):
    
    class Meta:
        model = LoanFile
        fields = ['funding_receipt',]
