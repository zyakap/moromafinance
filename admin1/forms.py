from django import forms
from admin1.models import AdminSettings, Employer, ProcessingFeeTier
from accounts.models import Bank, BankBranch

class AdminSettingsForm(forms.ModelForm):
    """General / company settings — email, prefix, bank account, Alesco code."""
    class Meta:
        model = AdminSettings
        fields = (
            "loanref_prefix",
            "admin_email_addresses",
            "default_from_email",
            "support_email",
            "email_system_to_work_email",
            # Display / formatting
            "display_decimal_places",
            "decimal_rounding",
            # Deduction categories offered at client registration
            "dc_alesco_enabled",
            "dc_private_enabled",
            "dc_standing_order_enabled",
            "dc_voluntary_enabled",
            # Company bank account
            "bank1",
            "bank1_acc_name",
            "bank1_acc_num",
            "bank1_branch",
            "bank1_bsb",
            "swift",
            # Public-service deduction code
            "alesco_dc",
        )

class AppearanceSettingsForm(forms.ModelForm):
    """Per-tenant white-label appearance: logo, colours, font."""
    class Meta:
        model = AdminSettings
        fields = (
            'brand_name',
            'brand_logo',
            'login_logo',
            'favicon',
            'primary_color',
            'sidebar_bg_color',
            'sidebar_light_text',
            'topbar_color',
            'font_family',
        )
        widgets = {
            'primary_color': forms.TextInput(attrs={'type': 'color'}),
            'sidebar_bg_color': forms.TextInput(attrs={'type': 'color'}),
            'topbar_color': forms.TextInput(attrs={'type': 'color'}),
        }


class DateSettingsForm(forms.ModelForm):

    class Meta:
        model = AdminSettings
        fields = ("date_format",)

class BankForm(forms.ModelForm):
    class Meta:
        model = Bank
        fields = ['name', 'swift_code', 'bsb_prefix', 'active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'swift_code': forms.TextInput(attrs={'class': 'form-control'}),
            'bsb_prefix': forms.TextInput(attrs={'class': 'form-control'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class BankBranchForm(forms.ModelForm):
    class Meta:
        model = BankBranch
        fields = ['bank', 'name', 'bsb_number', 'address', 'city', 'province', 'active']
        widgets = {
            'bank': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'bsb_number': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'province': forms.Select(attrs={'class': 'form-select'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class EmployerForm(forms.ModelForm):
    class Meta:
        model = Employer
        fields = ['name', 'sector', 'organisation_type', 'office_address', 'payroll_officer_name', 'work_phone', 'work_email', 'active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sector': forms.Select(attrs={'class': 'form-select'}),
            'organisation_type': forms.Select(attrs={'class': 'form-select'}),
            'office_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'payroll_officer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'work_phone': forms.NumberInput(attrs={'class': 'form-control'}),
            'work_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class LoanSettingsForm(forms.ModelForm):
    class Meta:
        model = AdminSettings
        fields = (
            # Interest
            'interest_type',
            'interest_rate',
            # Loan amount limits
            'loan_min_amount',
            'loan_max_amount',
            'increment_amount',
            # Fortnight limits
            'min_fn',
            'max_fn',
            'increment_fn',
            # Processing & modes
            'processing_fee',
            'processing_fee_collection_mode',
            'user_loan_application_mode',
            'staff_loan_creation_mode',
            'refinance_type',
            'send_cash_disbursement_notice',
            'cdn_send_to_payroll_officer',
            'send_loan_amortization_schedule',
            'display_referrer_on_loan',
            # Loan application document sending
            'send_application_documents',
            'appdoc_send_to_user',
            'appdoc_send_to_staff',
            'appdoc_bcc_admin',
            'appdoc_include_application',
            'appdoc_include_terms',
            'appdoc_include_stat_dec',
            'appdoc_include_irsda',
            # Alesco payroll update notification
            'send_alesco_pay_update_email',
            'las_col_period', 'las_col_date', 'las_col_opening',
            'las_col_interest', 'las_col_principal', 'las_col_repayment', 'las_col_closing',
        )

class CreditCheckSettingsForm(forms.ModelForm):
    class Meta:
        model = AdminSettings
        fields = (
            'credit_check',
            'approval_credit_threshold',
            'percentage_of_gross',
            'default_repayment_limit',
            'minimum_repayment_limit',
            'repayment_limit_check_enabled',
            'bypass_activation_check',
            # Default interest
            'default_interest_type',
            'default_interest_rate',
            'default_interest_base',
            'auto_default_on_shortfall',
            'default_interest_calculation_mercy_days',
            # Automatic default classification
            'auto_classify_default',
        )


class DccSettingsForm(forms.ModelForm):
    """DCC credit-bureau settings: the pay-per-view master switch and the
    automation driven by the bureau's benchmark score. The data feed to DCC
    is not configurable here — it is always on."""
    class Meta:
        model = AdminSettings
        fields = (
            'dcc_enabled',
            'dcc_autocredit_enabled',
            'dcc_min_score',
            # Affordability & stacking
            'dcc_affordability_enabled',
            'dcc_max_dsr_percent',
            'dcc_block_on_no_income',
            'dcc_stacking_action',
            # Registration screening
            'dcc_screen_registration',
            'dcc_registration_min_score',
            # Default reporting
            'dcc_auto_report_defaults',
            'dcc_default_report_after_days',
            'dcc_autoset_limits',
            'dcc_limit_max_repayment',
            'dcc_limit_max_ceiling',
        )


class RolesSettingsForm(forms.ModelForm):
    class Meta:
        model = AdminSettings
        fields = (
            'role_user_enabled',
            'role_staff_enabled',
            'role_manager_enabled',
        )


class TermsAndContractsSettingsForm(forms.ModelForm):
    class Meta:
        model = AdminSettings
        fields = (
            'appdoc_include_terms',
            'contract_generation_enabled',
            'contract_default_fee',
            'contract_default_interest_rate',
        )


class CreditAssessmentSettingsForm(forms.ModelForm):
    class Meta:
        model = AdminSettings
        fields = ('credit_assessment_enabled',)


class ReferralSettingsForm(forms.ModelForm):
    class Meta:
        model = AdminSettings
        fields = ('referral_enabled', 'referral_commission', 'referral_payment_day')
        widgets = {
            'referral_commission': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 50.00'}),
            'referral_payment_day': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31}),
        }


class ProcessingFeeTierForm(forms.ModelForm):
    class Meta:
        model = ProcessingFeeTier
        fields = ['min_amount', 'max_amount', 'fee']
        widgets = {
            'min_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 0', 'step': '0.01'}),
            'max_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank for no limit', 'step': '0.01'}),
            'fee':        forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 50.00', 'step': '0.01'}),
        }
