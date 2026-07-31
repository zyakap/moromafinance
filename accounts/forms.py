from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from accounts.models import UserProfile, SMEProfile, Bank, BankBranch, StatementOfPosition

from .widgets import DatePickerInput

User = get_user_model()

def apply_form_field_settings(form, form_name):
    try:
        from admin1.models import FormFieldSetting
        settings_by_field = {
            setting.field_name: setting
            for setting in FormFieldSetting.objects.filter(form_name=form_name)
        }
    except:
        settings_by_field = {}

    for field_name in list(form.fields.keys()):
        setting = settings_by_field.get(field_name)
        if setting:
            if not setting.enabled:
                form.fields.pop(field_name)
                continue
            form.fields[field_name].required = setting.required

from django_recaptcha.fields import ReCaptchaField


class BankBranchSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        bank_name = getattr(self, 'bank_by_value', {}).get(str(value))
        if bank_name:
            option['attrs']['data-bank'] = bank_name
        return option


class RegisterForm(forms.ModelForm):
    
    """
    The default
    
    """
    

    password1 = forms.CharField(label='Password',widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput)
    captcha = ReCaptchaField()
    
    class Meta:
        model = User
        fields = ['email',]
        
    def clean_email(self):
        '''
        Verify email is available.
        '''
        
        email = self.cleaned_data.get('email')
        qs = User.objects.filter(email=email)
        if qs.exists():
            raise forms.ValidationError('Email already exists!')
        return email
    
    def clean(self):
        '''
        Verify both passwords match.
    
        '''
        
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        
        if password1 is not None and password1 != password2:
            self.add_error("password2", "Your passwords must match")
        return cleaned_data

    def save(self, commit=True):
        #save the provided password in hashed format
        
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user
    
class UserAdminCreationForm(forms.ModelForm):
    """ 
    A form for creating. Includes all the required fields, plus a repeated password.
    """
    
    password1 = forms.CharField(label='Password',widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['email','active', 'admin', 'confirmed', 'defaulted', 'suspended','dcc_flagged', 'cdb_flagged']
    
    
    def clean(self):
        '''
        Verify both passwords match.
        '''
        
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        
        if password1 is not None and password1 != password2:
            self.add_error("password2", "Your passwords must match")
        return cleaned_data
    
    def save(self, commit=True):
        #save the provided password in hashed format
        
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user
        
class UserAdminChangeForm(forms.ModelForm):
    
    """
    A form for updating users. Includes all the fields on
    the user, but replaces the password field with admin's
    password hash display field.
    """
    
    password = ReadOnlyPasswordHashField()
    
    class Meta:
        model = User
        fields = ['email', 'password', 'active', 'admin', 'confirmed', 'defaulted', 'suspended','dcc_flagged', 'cdb_flagged']
        
    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        
        return self.initial["password"]
    
    
class LoginForm(forms.Form):
    
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),)
    

class PasswordResetForm(forms.Form):
    
    email = forms.EmailField()
        
class UserProfileForm(forms.ModelForm):
    
    class Meta:
        model = UserProfile
        fields = '__all__'
        exclude = ['user', 'id', 'referred_by']
        
class PersonalInfoForm(forms.ModelForm):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_settings(self, 'personal_info')
    
    class Meta:
        model = UserProfile
        fields =['first_name','middle_name', 'last_name', 'gender', 'date_of_birth', 'marital_status','propic', 'number_of_dependents', 'ages_of_dependents']
        
        widgets = {
            'date_of_birth' : DatePickerInput(), }

class AddressInfoForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_settings(self, 'address_info')

    class Meta:
        model = UserProfile
        fields = ['mobile1', 'mobile2', 'resident_owner', 'residential_address', 'residential_province', 'place_of_origin', 'province', 'years_at_current_residence']


    
class RefereeInfoForm(forms.ModelForm):

    class Meta:
        model = UserProfile
        fields = ['referee_first_name', 'referee_last_name', 'referee_residential_address', 'referee_employer', 'referee_email', 'referee_mobile', 'referee_is_spouse']

        widgets = {
            'referee_residential_address': forms.Textarea(attrs={'rows': 3}),
        }


class PreviousEmployerInfoForm(forms.ModelForm):

    class Meta:
        model = UserProfile
        fields = ['previous_employer', 'number_of_years_with_previous_employer', 'previous_employer_email', 'previous_employer_phone']


class StatementOfPositionForm(forms.ModelForm):

    class Meta:
        model = StatementOfPosition
        exclude = ['user', 'id', 'created_at', 'updated_at']

        widgets = {
            'asset_house_property_section': forms.TextInput(attrs={'placeholder': 'e.g., Section 245'}),
            'asset_house_property_lot': forms.TextInput(attrs={'placeholder': 'e.g., Lot 12'}),
        }


class JobInfoUpdateForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_settings(self, 'job_info')

    class Meta:
        model = UserProfile
        fields = ['job_title', 'start_date', 'pay_frequency', 'last_paydate', 'gross_pay', 'net_pay', 'employee_file_number']

        widgets = {
            'start_date' : DatePickerInput(),
            'last_paydate' : DatePickerInput(),}
    
        
class ContactInfoForm(forms.ModelForm):
    
    class Meta:
        model = UserProfile
        fields = ['mobile1', 'mobile2']
      
class BankAccountInfoMixin:
    bank_field_name = 'bank'
    branch_field_name = 'bank_branch'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bank_value = self.initial.get(self.bank_field_name) or self.data.get(self.bank_field_name)
        branch_value = self.initial.get(self.branch_field_name) or self.data.get(self.branch_field_name)
        bank_choices = [('', '---------')]
        branch_choices = [('', '---------')]
        bank_by_branch_value = {}

        for bank in Bank.objects.filter(active=True):
            bank_choices.append((bank.name, bank.name))

        for branch in BankBranch.objects.filter(active=True).select_related('bank'):
            label = branch.name
            value = branch.name
            if branch.bsb_number:
                label = f'{branch.name} - {branch.bsb_number}'
                value = f'{branch.name} - {branch.bsb_number}'
            branch_choices.append((value, label))
            bank_by_branch_value[value] = branch.bank.name

        if bank_value and not any(choice[0] == bank_value for choice in bank_choices):
            bank_choices.append((bank_value, bank_value))

        if branch_value and not any(choice[0] == branch_value for choice in branch_choices):
            branch_choices.append((branch_value, branch_value))

        self.fields[self.bank_field_name] = forms.ChoiceField(
            choices=bank_choices,
            required=False,
            label=self.fields[self.bank_field_name].label or 'Bank',
            widget=forms.Select(attrs={'class': 'bank-select'})
        )
        branch_widget = BankBranchSelect(attrs={'class': 'bank-branch-select'})
        branch_widget.bank_by_value = bank_by_branch_value
        self.fields[self.branch_field_name] = forms.ChoiceField(
            choices=branch_choices,
            required=False,
            label=self.fields[self.branch_field_name].label or 'Bank branch',
            widget=branch_widget
        )

    def clean(self):
        cleaned_data = super().clean()
        bank_name = cleaned_data.get(self.bank_field_name)
        branch_value = cleaned_data.get(self.branch_field_name)

        if bank_name and branch_value:
            branch_name = branch_value.split(' - ')[0]
            if not BankBranch.objects.filter(bank__name=bank_name, name=branch_name, active=True).exists():
                self.add_error(self.branch_field_name, 'Select a valid branch for the selected bank.')

        return cleaned_data


class BankAccountInfoForm(BankAccountInfoMixin, forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_settings(self, 'bank_info')

    class Meta:
        model = UserProfile
        fields = ['bank','bank_account_name','bank_account_number','bank_branch', 'bank_bsb', 'bank_account_type']

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

class SMEUploadsForm(forms.ModelForm):
    
    class Meta:
        model = SMEProfile
        fields = ['ipa_certificate', 'tin_certificate', 'cash_flow', 'sme_bank_statement', 'location_pic' ]

class SMEBankInfoForm(BankAccountInfoMixin, forms.ModelForm):
    
    class Meta:
        model = SMEProfile
        fields = ['bank','bank_account_name','bank_account_number','bank_branch','bank_standing_order']


        
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
        # Only validate sector/org_type when they are present (preregistration OFF)
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
        fields = ['employer', 'deduction_category', 'sector', 'organisation_type', 'office_address', 'payroll_officer_name', 'payroll_officer_phone', 'payroll_officer_email', 'immediate_supervisor']
        