from django import forms
from accounts.models import UserProfile, SMEProfile
from accounts.forms import BankAccountInfoMixin, apply_form_field_settings
from admin1.models import AdminSettings, get_loan_config, get_effective_max_loan_amount
from loan.models import Loan, LoanFile, generate_amount_choices
from loan.open_repayment import clear_open_repayment, install_open_repayment_handlers, set_open_repayment
from .widgets import DatePickerInput

class MemberInfoForm(forms.ModelForm):

    referred_by = forms.ModelChoiceField(queryset=None, required=False, empty_label='— Not referred —')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from referral.models import Referrer
        from admin1.models import referral_program_enabled
        if referral_program_enabled():
            self.fields['referred_by'].queryset = Referrer.objects.filter(status='ACTIVE').order_by('name')
        else:
            self.fields.pop('referred_by', None)

    class Meta:
        model = UserProfile
        fields = ['first_name', 'middle_name', 'last_name', 'gender', 'date_of_birth', 'email', 'mobile1', 'referred_by']

        widgets = {
            'date_of_birth': DatePickerInput(),
        }
   
class PersonalInfoForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_settings(self, 'personal_info')

    class Meta:
        model = UserProfile
        fields =['first_name','middle_name', 'last_name', 'gender', 'date_of_birth', 'marital_status', 'propic']

        widgets = {
            'date_of_birth' : DatePickerInput(), }
      
class ContactInfoForm(forms.ModelForm):
    
    class Meta:
        model = UserProfile
        fields = ['email', 'mobile1', 'mobile2']
      
class BankAccountInfoForm(BankAccountInfoMixin, forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_settings(self, 'bank_info')

    class Meta:
        model = UserProfile
        fields = ['bank','bank_account_name','bank_account_number','bank_branch',]

class BankAccountInfo2Form(BankAccountInfoMixin, forms.ModelForm):
    bank_field_name = 'bank2'
    branch_field_name = 'bank_branch2'

    class Meta:
        model = UserProfile
        fields = ['bank2','bank_account_name2','bank_account_number2','bank_branch2',]
        
class UserUploadForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_settings(self, 'user_uploads')

    class Meta:
        model = UserProfile
        fields = ['nid', 'nid_number', 'passport','passport_number', 'drivers_license', 'drivers_license_number', 'superid', 'super_member_code', 'work_id', 'work_id_number']
        
class SMEProfileForm(forms.ModelForm):
    
    class Meta:
        model = SMEProfile
        fields = ['category','trading_name','registered_name', 'business_address', 'email', 'phone', 'website' ,'ipa_registration_number', 'tin_number' ]

class CreateSMEProfileForm(forms.ModelForm):
    
    def __init__(self, *args, **kwargs):
        super(CreateSMEProfileForm, self).__init__(*args, **kwargs)
        self.fields['owner'].queryset = UserProfile.objects.filter(activation=1)

    class Meta:
        model = SMEProfile
        fields = ['owner', 'category','trading_name','registered_name', 'business_address', 'email', 'phone', 'website' ,'ipa_registration_number', 'tin_number' ]

class SMEUploadsForm(forms.ModelForm):
    
    class Meta:
        model = SMEProfile
        fields = ['ipa_certificate', 'tin_certificate', 'cash_flow', 'sme_bank_statement', 'location_pic' ]

class SMEBankInfoForm(BankAccountInfoMixin, forms.ModelForm):
    
    class Meta:
        model = SMEProfile
        fields = ['bank','bank_account_name','bank_account_number','bank_branch','bank_standing_order']

class LoanStatementUploadForm(forms.ModelForm):
    
    class Meta:
        model = LoanFile
        fields = ['loan_statement1', 'loan_statement2', 'loan_statement3', 'bank_statement', 'super_statement', 'bank_standing_order' ]

        
class EmployerInfoUpdateForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._preregistration = False
        try:
            from admin1.models import AdminSettings, Employer
            setting = AdminSettings.objects.get(settings_name='setting1')
            self._preregistration = bool(setting.employer_preregistration_required)
            if self._preregistration and 'employer' in self.fields:
                employer_choices = [('', '---------')]
                for emp in Employer.objects.filter(active=True).order_by('name'):
                    employer_choices.append((emp.name, emp.name))
                self.fields['employer'] = forms.ChoiceField(
                    choices=employer_choices,
                    required=self.fields['employer'].required,
                    label='Employer'
                )
                # All details come from the registered employer — only the selection is shown
                for f in ['sector', 'organisation_type', 'office_address', 'payroll_officer_name', 'payroll_officer_phone', 'payroll_officer_email']:
                    self.fields.pop(f, None)
        except Exception:
            pass

        if 'deduction_category' in self.fields:
            from admin1.models import get_enabled_deduction_categories
            self.fields['deduction_category'].choices = \
                [('', '— Select payroll category —')] + list(get_enabled_deduction_categories())
            self.fields['deduction_category'].required = False
            self.fields['deduction_category'].label = 'Payroll / Deduction Category'
            self.fields['deduction_category'].help_text = \
                'Which payroll/deduction group this client belongs to (used to segment collection reports).'

        apply_form_field_settings(self, 'employer_info')

        if 'employer' in self.fields:
            order = ['employer'] + (['deduction_category'] if 'deduction_category' in self.fields else [])
            self.fields = {k: self.fields[k] for k in order + [k for k in self.fields if k not in order]}

    def clean(self):
        cleaned_data = super().clean()
        sector = cleaned_data.get('sector')
        organisation_type = cleaned_data.get('organisation_type')
        if sector and organisation_type:
            if sector == 'PUBLIC' and organisation_type not in ['DEPARTMENT', 'SOE']:
                self.add_error('organisation_type', 'For Public sector, Organisation Type must be Department or SOE.')
            elif sector == 'PRIVATE' and organisation_type not in ['COMPANY', 'MSME']:
                self.add_error('organisation_type', 'For Private sector, Organisation Type must be Company or MSME.')
        return cleaned_data

    class Meta:
        model = UserProfile
        fields = ['employer', 'deduction_category', 'sector', 'organisation_type', 'office_address', 'payroll_officer_name', 'payroll_officer_phone', 'payroll_officer_email']

class AddressInfoForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_settings(self, 'address_info')

    class Meta:
        model = UserProfile
        fields = ['mobile1', 'mobile2', 'resident_owner', 'residential_address', 'residential_province', 'place_of_origin', 'province']

class RequiredUploadForm(forms.ModelForm):
    
    class Meta:
        model = LoanFile
        fields = ['application_form' , 'terms_conditions', 'stat_dec', 'irr_sd_form']
           
class WorkUploadForm(forms.ModelForm):
    
    class Meta:
        model = LoanFile
        fields = ['work_confirmation_letter', 'payslip1', 'payslip2', ]
    
class JobInfoUpdateForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_settings(self, 'job_info')

    class Meta:
        model = UserProfile
        fields = ['job_title', 'start_date', 'pay_frequency', 'last_paydate', 'gross_pay', 'net_pay', 'employee_file_number', 'work_id_number', 'work_id',]

        widgets = {
            'start_date' : DatePickerInput(),
            'last_paydate' : DatePickerInput(),}

class CreateLoanForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        user_profile = kwargs.pop('user_profile', None)
        self.user_profile = user_profile
        loan_mode = kwargs.pop('loan_mode', None) or self._resolve_mode(user_profile)
        self.loan_mode = loan_mode
        super(CreateLoanForm, self).__init__(*args, **kwargs)
        self.fields['owner'].queryset = UserProfile.objects.filter(activation=1)
        if loan_mode != 'OPEN_REPAYMENT':
            self.fields.pop('repayment_amount', None)
        else:
            self.fields['repayment_amount'].required = True
        # Rebuild the choices from the current loan settings on every request.
        # The choices declared on Loan.amount are evaluated when Django starts,
        # so using them on the initial GET leaves the form showing stale limits.
        # Once a client is selected, get_effective_max_loan_amount also applies
        # that client's optional maximum override.
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
            return setting.staff_loan_creation_mode or 'LOCKED'
        except AdminSettings.DoesNotExist:
            return 'LOCKED'

    def _validate_amount_bounds(self, cleaned_data):
        """Enforce the global minimum and the effective maximum for the selected
        client (per-client override if set, else the global limit)."""
        amount = cleaned_data.get('amount')
        owner = cleaned_data.get('owner') or self.user_profile
        if amount is None:
            return
        from decimal import Decimal
        cfg = get_loan_config()
        min_amount = Decimal(str(cfg['loan_min_amount']))
        max_amount = get_effective_max_loan_amount(owner)
        amount = Decimal(str(amount))
        if amount < min_amount:
            self.add_error('amount', f'Loan amount must be at least K{min_amount:,.2f}.')
        elif amount > max_amount:
            self.add_error('amount', f'Loan amount cannot exceed K{max_amount:,.2f} for this client.')

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

    def install_view_handlers(self):
        import sys

        for module_name in ('staff.views',):
            module = sys.modules.get(module_name)
            if module is not None:
                install_open_repayment_handlers(module)
    
    class Meta:
        model = Loan
        fields = ['owner','location', 'amount','number_of_fortnights','repayment_amount','repayment_start_date']
        
        widgets = {
            'repayment_start_date' : DatePickerInput(), }
        
class UploadRequirementsByStaffForm(forms.ModelForm):
    
    class Meta:
        model = LoanFile
        fields = ['application_form' , 'terms_conditions', 'stat_dec', 'irr_sd_form', 'work_confirmation_letter', 'payslip1', 'payslip2', 'loan_statement1', 'loan_statement2', 'loan_statement3', 'bank_statement', 'super_statement', 'bank_standing_order',]


class ReceiptUploadForm(forms.ModelForm):
    
    class Meta:
        model = LoanFile
        fields = ['funding_receipt', ]
