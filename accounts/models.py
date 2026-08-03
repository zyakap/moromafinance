
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.forms import DecimalField, FileField
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from django.db import models
from admin1.models import Location

# Payroll / deduction categories a client can belong to. The full list is fixed;
# which of these are actually offered at registration is controlled by admin
# settings (see admin1.models.get_enabled_deduction_categories).
DEDUCTION_CATEGORY_CHOICES = [
    ('ALESCO', 'ALESCO Payroll'),
    ('PRIVATE', 'Private Sector Payroll'),
    ('STANDING_ORDER', 'Standing Order Deductions'),
    ('VOLUNTARY', 'Voluntary Deductions'),
]

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, is_active=False, is_staff=False, is_admin=False, is_superuser=False, is_confirmed=False, is_defaulted=False, is_suspended=False, is_dcc_flagged=False, is_cdb_flagged=False):
        """
        Creates and saves a User with the given email and password.
        """
        if not email:
            raise ValueError('Users must have an email address')

        user = self.model(
            email=self.normalize_email(email),
        )

        user.set_password(password)
        user.active = is_active
        user.staff = is_staff
        user.admin = is_admin
        user.is_superuser = is_superuser
        user.confirmed = is_confirmed
        user.defaulted = is_defaulted
        user.suspended = is_suspended
        user.dcc_flagged = is_dcc_flagged
        user.cdb_flagged = is_cdb_flagged
        user.save(using=self._db)
        return user

    def create_staffuser(self, email, password):
        """
        Creates and saves a staff user with the given email and password.
        """
        user = self.create_user(
            email,
            password=password,
        )
        user.staff = True
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password):
        """
        Creates and saves a superuser with the given email and password.
        """
        user = self.create_user(
            email,
            password=password,
        )
        user.staff = True
        user.admin = True
        user.is_superuser = True
        user.save(using=self._db)
        return user

class User(AbstractBaseUser, PermissionsMixin):
    
    email = models.EmailField(
        verbose_name='email address',
        max_length=255,
        unique=True,
    )
    active = models.BooleanField(default=False)
    staff = models.BooleanField(default=False) # a admin user; non super-user
    admin = models.BooleanField(default=False) # a superuser
    updated_at = models.DateTimeField(auto_now=True)
    confirmed = models.BooleanField(default=False)
    defaulted = models.BooleanField(default=False)
    suspended = models.BooleanField(default=False)
    dcc_flagged = models.BooleanField(default=False)
    cdb_flagged = models.BooleanField(default=False)
    
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    
    objects = UserManager()
    
    # notice the absence of a "Password field", that is built in.

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = [] # Email & Password are required by default.

    def __str__(self):
        return self.email
    
    def get_full_name(self):
        # The user is identified by their email address
        return self.email

    def get_short_name(self):
        # The user is identified by their email address
        return self.email

    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission?"
        # Simplest possible answer: Yes, always
        return True

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        # Simplest possible answer: Yes, always
        return True

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        return self.staff

    @property
    def is_admin(self):
        "Is the user a admin member?"
        return self.admin

    @property
    def is_confirmed(self):
        return self.is_confirmed
    
    @property
    def is_defaulted(self):
        return self.defaulted

    @property
    def is_suspended(self):
        return self.suspended
    
    @property
    def is_dcc_flagged(self):
        return self.dcc_flagged

    @property
    def is_cdb_flagged(self):
        return self.cdb_flagged

    def email_user(self, *args, **kwargs):
        send_mail(
        '{}'.format(args[0]),
        '{}'.format(args[1]),
        'dev@webmasta.com.pg',
        [self.email],
        fail_silently=False,
    )

class UserProfile(models.Model):
    PROVINCE = [('AROB','AROB'),('CENTRAL','CENTRAL'),('ENGA','ENGA'),('EAST SEPIK','EAST SEPIK'),('EHP','EHP'),('ENB','ENBP'),
    ('HELA','HELA'), ('JIWAKA','JIWAKA'),('MADANG','MADANG'),('MANUS','MANUS'),('MILNE BAY','MILNE BAY'),('MOROBE', 'MOROBE'),('NCD','NCD'),('NEW IRELAND','NEW IRELAND'),('ORO','ORO'),
    ('SHP','SHP'),('SIMBU','SIMBU'), ('WESTERN','WESTERN'), ('WEST SEPIK','WEST SEPIK'), ('WHP','WHP'), ('WNB','WNBP'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uid = models.CharField(max_length=20,null=True, blank=True)
    luid = models.CharField(max_length=20,null=True, blank=True)
    propic = models.FileField('Profile Photo:',null=True, blank=True)
    propic_url = models.CharField(max_length=555, null=True, blank=True)
    category = models.CharField(max_length=12, choices=[('CLIENT','CLIENT'), ('STAFF','STAFF')], default='CLIENT', null=True, blank=True)
    type_of_client = models.CharField(max_length=12, choices=[('INDIVIDUAL','INDIVIDUAL'),('COMPANY','COMPANY')], default='INDIVIDUAL', null=True, blank=True)
    activation = models.IntegerField(null=True, blank = True, default=0)
    number_of_loans = models.IntegerField(null=True, blank = True, default=0)
    credit_rating = models.DecimalField(max_digits=5, decimal_places=2, null=True, default=100.00)
    alesco_paycode = models.CharField(max_length=20, null=True, blank=True)
    personal_interest_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, default=0.00)
    credit_consent = models.CharField(max_length=3, choices=[('NO','NO'),('YES','YES')], default='NO', null=True, blank=True)
    terms_consent = models.CharField(max_length=3, choices=[('NO','NO'),('YES','YES')], default='NO', null=True, blank=True)

    # DCC benchmark score cache (fetched from the bureau; see dcc.functions)
    dcc_score = models.PositiveIntegerField(null=True, blank=True, help_text='Last DCC benchmark credit score (0-1000) fetched from the bureau.')
    dcc_grade = models.CharField(max_length=5, null=True, blank=True, help_text='Letter grade that came with the last DCC score.')
    dcc_score_at = models.DateTimeField(null=True, blank=True, help_text='When the DCC score was last fetched.')
    # Cross-lender risk signals cached alongside the score, so staff screens and
    # automatic decisions can use them without re-billing a bureau call.
    dcc_dsr_percent = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True, help_text="Debt Service Ratio: what the client repays across ALL lenders as a percentage of verified income, per DCC.")
    dcc_dsr_band = models.CharField(max_length=12, null=True, blank=True, help_text='HEALTHY / CAUTION / OVER_LIMIT / CRITICAL / UNKNOWN, per DCC affordability policy.')
    dcc_headroom = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Additional fortnightly repayment DCC assesses this client can still afford.')
    dcc_velocity_level = models.CharField(max_length=10, null=True, blank=True, help_text='NORMAL / ELEVATED / HIGH — DCC loan-stacking verdict at the last check.')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    login_timestamp =  models.DateTimeField(null=True, blank = True)
    first_name = models.CharField(max_length=20)
    middle_name = models.CharField(max_length=20, null=True, blank=True)
    last_name = models.CharField(max_length=20)
    gender = models.CharField(max_length=6, choices=[('MALE','MALE'),('FEMALE','FEMALE')], default='', null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    marital_status = models.CharField(max_length=10, choices=[('SINGLE','SINGLE'),('MARRIED','MARRIED'),('DE-FACTO','DE-FACTO'),('DIVORCED','DIVORCED'),('WIDOWED','WIDOWED')], default='', null=True, blank=True)
    
    #contact
    email = models.EmailField(null=True, blank=True)
    mobile1 = models.IntegerField(null=True, blank = True)
    mobile2 = models.IntegerField(null=True, blank = True)
    work_phone = models.IntegerField(verbose_name='Work Phone', blank=True, null=True)
    work_email = models.EmailField(verbose_name='Work Email', max_length=50, unique=True, blank=True, null=True)
    payroll_officer_name = models.CharField(verbose_name='Payroll Officer Name', max_length=100, blank=True, null=True)
    payroll_officer_phone = models.IntegerField(verbose_name='Payroll Officer Phone', blank=True, null=True)
    payroll_officer_email = models.EmailField(verbose_name='Payroll Officer Email', max_length=100, blank=True, null=True)
    notify_work_email = models.BooleanField(verbose_name='Enable System Notifications to Work Email', default=True)
    
    #personal_ID
    nid = models.FileField(null=True, blank=True)
    nid_number = models.CharField(max_length=20, null=True, blank=True)
    nid_url = models.CharField(max_length=555, null=True, blank=True)
    passport = models.FileField(null=True, blank=True)
    passport_number = models.CharField(max_length=20, null=True, blank=True)
    passport_url = models.CharField(max_length=555, null=True, blank=True)
    drivers_license = models.FileField(null=True, blank=True)
    drivers_license_number = models.CharField(max_length=20, null=True, blank=True)
    drivers_license_url = models.CharField(max_length=555, null=True, blank=True)
    superid = models.FileField(null=True, blank=True)
    super_member_code = models.CharField(max_length=20, null=True, blank=True)
    super_id_url = models.CharField(max_length=555, null=True, blank=True)
    
    #personal_info
    residential_address = models.TextField(max_length=255, null=True, blank=True)
    residential_province = models.CharField(max_length=20, choices=PROVINCE, null=True, blank=True, default="Not Specified")
    place_of_origin = models.TextField(max_length=255, null=True, blank=True)
    province = models.CharField('Province of Origin', max_length=20, choices=PROVINCE, null=True, blank=True, default="Not Specified")
    resident_owner = models.CharField(max_length=10, choices=[('SELF','SELF'),('RELATIVES','RELATIVES'),('RENTAL','RENTAL')], default='',null=True, blank=True)
    years_at_current_residence = models.IntegerField(null=True, blank=True, default=0)
    number_of_dependents = models.IntegerField(null=True, blank=True, default=0)
    ages_of_dependents = models.TextField(max_length=255, null=True, blank=True, help_text="Enter ages separated by commas (e.g., 5, 8, 12)")

    #referee information (Credit Assessment)
    referee_first_name = models.CharField(max_length=50, null=True, blank=True)
    referee_last_name = models.CharField(max_length=50, null=True, blank=True)
    referee_residential_address = models.TextField(max_length=255, null=True, blank=True)
    referee_employer = models.CharField(max_length=100, null=True, blank=True)
    referee_email = models.EmailField(null=True, blank=True)
    referee_mobile = models.IntegerField(null=True, blank=True)
    referee_is_spouse = models.BooleanField(default=False)

    #previous employer information (Credit Assessment)
    previous_employer = models.CharField(max_length=100, null=True, blank=True)
    number_of_years_with_previous_employer = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, default=0)
    previous_employer_email = models.EmailField(null=True, blank=True)
    previous_employer_phone = models.IntegerField(null=True, blank=True)
    immediate_supervisor = models.CharField(max_length=100, null=True, blank=True)

    #employer information
    # Payroll / deduction category — how this client's repayments are collected.
    # The list of categories that may be selected is controlled by admin settings.
    deduction_category = models.CharField(
        verbose_name="Payroll / Deduction Category:",
        max_length=20, choices=DEDUCTION_CATEGORY_CHOICES, null=True, blank=True,
        help_text="Which payroll/deduction group this client belongs to (used to segment collection reports).",
    )
    sector  = models.CharField(max_length=10, choices=[('PUBLIC','PUBLIC'),('PRIVATE','PRIVATE')], default='NA', null=True, blank=True)
    organisation_type = models.CharField(max_length=10, choices=[('DEPARTMENT','DEPARTMENT'),('SOE','SOE'),('COMPANY','COMPANY'),('MSME','MSME')], null=True, blank=True)
    employer = models.CharField(max_length=50,null=True, blank=True, default='')
    job_title = models.CharField(max_length=255,null=True, blank=True, default='')
    office_address = models.TextField(max_length=255, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    pay_frequency = models.CharField(max_length=2, choices=[('FN','FORTNIGHTLY'),('MN','MONTHLY')], default='FN', null=True, blank=True)
    last_paydate = models.DateField(null=True, blank=True)
    gross_pay = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, default=0)
    net_pay = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, default=0)
    employee_file_number = models.CharField(max_length=20, null=True, blank=True)

    work_id_number = models.CharField(max_length=20, null=True, blank=True)
    work_id = models.FileField(null=True, blank=True)
    work_id_url = models.CharField(max_length=555, null=True, blank=True)
    
    #bankaccount info
    bank = models.CharField(max_length=100, default='', null=True, blank=True)
    bank_account_name =  models.CharField(max_length=100, null=True, blank=True, default='')
    bank_account_number = models.CharField(max_length=30,null=True, blank = True)
    bank_branch = models.CharField(max_length=100,null=True, blank = True, default='')
    bank_bsb = models.CharField(max_length=10, null=True, blank=True)
    bank_account_type = models.CharField(max_length=15, choices=[('SAVINGS','SAVINGS'),('CURRENT','CURRENT'),('TERM DEPOSIT','TERM DEPOSIT')], default='SAVINGS', null=True, blank=True)

    #secondary bank account
    bank2 = models.CharField(max_length=100, default='', null=True, blank=True)
    bank_account_name2 =  models.CharField(max_length=100, null=True, blank=True, default='')
    bank_account_number2 = models.CharField(max_length=30,null=True, blank = True)
    bank_branch2 = models.CharField(max_length=100,null=True, blank = True, default='')
    bank_standing_order2 = models.FileField(null=True, blank=True)
    bank_standing_order2_url = models.CharField(max_length=555, null=True, blank=True)
   
    repayment_limit = models.DecimalField(verbose_name="Borrower's Limit:", max_digits=8, decimal_places=2, null=True, blank=True, default=0)
    max_loan_amount = models.DecimalField(
        verbose_name="Max Loan Amount (K):",
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Per-client maximum loan amount override. Overrides the global maximum when set. Automatically switches the loan form to Open Repayment mode for this client.",
    )
    account_requirements_check = models.CharField(max_length=10, choices=[('COMPLETED', 'COMPLETED'),('INCOMPLETE','INCOMPLETE')], default='INCOMPLETE', null=True, blank=True)
    requirement_check = models.CharField(max_length=10, choices=[('COMPLETED', 'COMPLETED'),('INCOMPLETE','INCOMPLETE')], default='INCOMPLETE', null=True, blank=True)
    
    has_loan = models.BooleanField(default=False)
    has_sme = models.BooleanField(default=False)
    in_recovery = models.BooleanField(default=False)
    location = models.ForeignKey(Location, on_delete=models.CASCADE ,null=True, blank=True)
    
    default_flagged = models.BooleanField(default=False)
    dcc_flagged = models.BooleanField(default=False)
    has_arrears = models.BooleanField(default=False)
    dcc = models.CharField(max_length=255,null=True, blank = True, default='')
    modeofregistration = models.CharField(max_length=10, choices=[('SR', 'SR'),('OTC','OTC'),('PU','PU')], default='SR', null=True, blank=True)
    
    opt1 = models.CharField(max_length=255, blank=True, null=True)
    opt2 = models.CharField(max_length=255, blank=True, null=True)
    opt3 = models.CharField(max_length=255, blank=True, null=True)
    opt4 = models.CharField(max_length=255, blank=True, null=True)
    opt5 = models.CharField(max_length=255, blank=True, null=True)

    referred_by = models.ForeignKey(
        'referral.Referrer',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='referred_clients',
    )

    @staticmethod
    def _years_since(start):
        if not start:
            return None
        import datetime as _dt
        today = _dt.date.today()
        years = today.year - start.year - ((today.month, today.day) < (start.month, start.day))
        return years if years >= 0 else None

    @property
    def age(self):
        """Age in whole years from date_of_birth, or None."""
        return self._years_since(self.date_of_birth)

    @property
    def years_of_service(self):
        """Whole years of service from employment start_date, or None."""
        return self._years_since(self.start_date)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


class StatementOfPosition(models.Model):
    """Client financial position (assets/liabilities/income/expenses) captured
    as part of Credit Assessment (AdminSettings.credit_assessment_enabled)."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    user = models.OneToOneField(UserProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='statement_of_position')

    # Assets
    asset_house_property = models.BooleanField(default=False)
    asset_house_property_section = models.CharField(max_length=20, null=True, blank=True)
    asset_house_property_lot = models.CharField(max_length=20, null=True, blank=True)
    asset_house_property_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)

    asset_vehicle_make = models.CharField(max_length=50, null=True, blank=True)
    asset_vehicle_model = models.CharField(max_length=50, null=True, blank=True)
    asset_vehicle_year = models.IntegerField(null=True, blank=True)
    asset_vehicle_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)

    asset_white_goods_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    asset_superanuation_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    asset_bank_account_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)

    # Liabilities
    liability_home_loan_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    liability_vehicle_loan_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)

    liability_personal_loan_1_bank = models.CharField(max_length=100, null=True, blank=True)
    liability_personal_loan_1_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)

    liability_personal_loan_2_institution = models.CharField(max_length=100, null=True, blank=True)
    liability_personal_loan_2_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    liability_personal_loan_3_institution = models.CharField(max_length=100, null=True, blank=True)
    liability_personal_loan_3_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)

    liability_credit_card_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    liability_other_loans_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    liability_other_debts_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)

    # Income
    income_gross_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    income_sme = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    income_other_1 = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    income_other_2 = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)

    # Expenses
    expense_home_loan = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    expense_vehicle_loan = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    expense_personal_loan = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    expense_rental = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    expense_insurance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    expense_utilities = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    expense_others = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)

    def __str__(self):
        return f'Statement of Position - {self.user.first_name} {self.user.last_name}'

    @property
    def total_assets(self):
        return (
            (self.asset_house_property_value or 0) +
            (self.asset_vehicle_value or 0) +
            (self.asset_white_goods_value or 0) +
            (self.asset_superanuation_value or 0) +
            (self.asset_bank_account_value or 0)
        )

    @property
    def total_liabilities(self):
        return (
            (self.liability_home_loan_value or 0) +
            (self.liability_vehicle_loan_value or 0) +
            (self.liability_personal_loan_1_value or 0) +
            (self.liability_personal_loan_2_value or 0) +
            (self.liability_personal_loan_3_value or 0) +
            (self.liability_credit_card_value or 0) +
            (self.liability_other_loans_value or 0) +
            (self.liability_other_debts_value or 0)
        )

    @property
    def total_income(self):
        return (
            (self.income_gross_salary or 0) +
            (self.income_sme or 0) +
            (self.income_other_1 or 0) +
            (self.income_other_2 or 0)
        )

    @property
    def total_expenses(self):
        return (
            (self.expense_home_loan or 0) +
            (self.expense_vehicle_loan or 0) +
            (self.expense_personal_loan or 0) +
            (self.expense_rental or 0) +
            (self.expense_insurance or 0) +
            (self.expense_utilities or 0) +
            (self.expense_others or 0)
        )

    @property
    def total_personal_loans(self):
        return (
            (self.liability_personal_loan_1_value or 0) +
            (self.liability_personal_loan_2_value or 0) +
            (self.liability_personal_loan_3_value or 0)
        )

    @property
    def total_other_income(self):
        return (
            (self.income_other_1 or 0) +
            (self.income_other_2 or 0)
        )

    @property
    def total_loan_payments(self):
        return (
            (self.expense_home_loan or 0) +
            (self.expense_vehicle_loan or 0) +
            (self.expense_personal_loan or 0)
        )

    @property
    def net_position(self):
        return self.total_assets - self.total_liabilities


class StaffProfile(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)   
    
    user = models.OneToOneField(UserProfile, on_delete=models.CASCADE)
    login_timestamp =  models.DateTimeField(null=True, blank = True)
    sid = models.CharField(max_length=12,null=True, blank=True)
    type_of_staff = models.CharField(max_length=12, choices=[('STAFF','STAFF'),('MANAGER','MANAGER'),('ADMIN','ADMIN'),('DIRECTOR','DIRECTOR')], default='STAFF', null=True, blank=True)
    category = models.CharField(max_length=12, choices=[('FULL-TIME','FULL-TIME'),('PART-TIME','PART-TIME'), ('GRADUATE','GRADUATE'), ('CONTRACTOR','CONTRACTOR')], default='FULL-TIME', null=True, blank=True)
    position_group = models.CharField(max_length=12, choices=[('WORKER','WORKER'),('SUPERVISOR','SUPERVISOR'), ('MANAGER','MANAGER')], default='', null=True, blank=True)
    position = models.CharField(max_length=30, null=True, blank=True)
    # Signature image embedded in manager-approved loan contracts (see manager/contract_utils.py).
    signature = models.FileField(upload_to='staff_signatures/', null=True, blank=True)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class SMEProfile(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    ref = models.CharField(max_length=20, null=True, blank=True, default='')
    owner = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE ,null=True, blank=True)
    category = models.CharField(max_length=20, choices=[('SOLE TRADER','SOLE TRADER'),('SME','SME'),('MSME','MSME')], default='nonmember', null=True, blank=True)
    trading_name =  models.CharField(max_length=255, null=True, blank=True, default='')
    registered_name = models.CharField(max_length=255, null=True, blank=True, default='') 
    
    business_address = models.CharField(max_length=255, null=True, blank=True, default='')
    email = models.EmailField(null=True, blank = True)
    phone = models.CharField(max_length=10, null=True, blank=True, default='')
    website = models.CharField(max_length=100, null=True, blank=True, default='')
    
    ipa_registration_number = models.CharField(max_length=20, null=True, blank=True)
    ipa_certificate = models.FileField(null=True, blank=True)
    ipa_certificate_url = models.CharField(max_length=555, null=True, blank=True)
    tin_number = models.CharField(max_length=20, null=True, blank=True)
    tin_certificate = models.FileField(null=True, blank=True)
    tin_certificate_url = models.CharField(max_length=555, null=True, blank=True)
    cash_flow = models.FileField(null=True, blank=True)
    cash_flow_url = models.CharField(max_length=555, null=True, blank=True)
    sme_bank_statement = models.FileField(null=True, blank=True)
    sme_bank_statement_url = models.CharField(max_length=555, null=True, blank=True)
    location_pic = models.FileField(verbose_name="Picture of Business Location", null=True, blank=True)
    location_pic_url = models.CharField(max_length=555, null=True, blank=True)
        
    #Sme bankaccount info
    bank = models.CharField(max_length=255, choices=[('ANZ', 'ANZ'),('BSP', 'BSP'),('KINA','KINA'),('WESTPAC','WESTPAC')], default='', null=True, blank=True)
    bank_account_name =  models.CharField(max_length=100, null=True, blank =True, default='')
    bank_account_number = models.IntegerField(null=True, blank = True)
    bank_branch = models.CharField(max_length=30,null=True, blank = True, default='')
    bank_standing_order = models.FileField(null=True, blank=True)
    bank_standing_order_url = models.CharField(max_length=555, null=True, blank=True)

    dcc_comment = models.CharField(max_length=255,null=True, blank = True, default='')
    cdb_comment = models.CharField(max_length=255,null=True, blank = True, default='')
    notes = models.TextField(max_length=255, null=True, blank=True)
    
class UserActivityLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.OneToOneField(UserProfile, on_delete=models.CASCADE)
    msgq = models.CharField(max_length=255, blank=True, null=True, default="")
    msglog = models.CharField(max_length=1555, blank=True, null=True, default="")
    msgbyemail = models.CharField(max_length=1555, blank=True, null=True, default="")
    supportq = models.CharField(max_length=255, blank=True, null=True, default="")
    supportlog = models.CharField(max_length=1555, blank=True, null=True, default="")
    notificationq = models.CharField(max_length=255, blank=True, null=True, default="")
    notificationlog = models.CharField(max_length=1555, blank=True, null=True, default="")
    last_login = models.DateTimeField(blank=True, null=True)
    loginlog = models.CharField(max_length=1555, blank=True, null=True, default="")


class Bank(models.Model):
    name = models.CharField(max_length=100, unique=True)
    swift_code = models.CharField(max_length=11, blank=True, null=True)
    bsb_prefix = models.CharField(max_length=10, blank=True, null=True, help_text="Common BSB prefix for this bank")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class BankBranch(models.Model):
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=100)
    bsb_number = models.CharField(max_length=20, blank=True, null=True, help_text="Branch BSB number")
    address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    province = models.CharField(max_length=20, choices=UserProfile.PROVINCE, blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['bank__name', 'name']
        unique_together = [['bank', 'name'], ['bank', 'bsb_number']]

    def __str__(self):
        if self.bsb_number:
            return f"{self.name} (BSB: {self.bsb_number})"
        return self.name