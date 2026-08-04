import os
from django.conf import settings
from django.db import models

#pre-delete SIGNALS
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from accounts.models import UserProfile, User, StaffProfile
from admin1.models import Location

import json

def loan_file_path(instance, filename):
    # Determine the upload path for car invoices
    return os.path.join('loanfiles',filename)

def _get_loan_limits():
    """Read loan limits from AdminSettings DB; fall back to settings.py constants."""
    try:
        from admin1.models import AdminSettings
        s = AdminSettings.objects.filter(settings_name='setting1').first()
        if s:
            return (
                int(s.loan_min_amount or settings.LOAN_MIN_AMOUNT),
                int(s.loan_max_amount or settings.LOAN_MAX_AMOUNT),
                int(s.increment_amount or settings.INCREMENT_AMOUNT),
                int(s.min_fn or settings.MIN_FN),
                int(s.max_fn or settings.MAX_FN),
                int(s.increment_fn or settings.INCREMENT_FN),
            )
    except Exception:
        pass
    return (
        int(settings.LOAN_MIN_AMOUNT),
        int(settings.LOAN_MAX_AMOUNT),
        settings.INCREMENT_AMOUNT,
        settings.MIN_FN,
        settings.MAX_FN,
        settings.INCREMENT_FN,
    )


def generate_amount_choices(max_override=None):
    """Loan amount dropdown choices from global loan limits.

    When ``max_override`` is provided (a per-client maximum), it replaces the
    global maximum — so a client whose limit is set lower sees a shorter list,
    and one set higher can select amounts above the global cap.
    """
    min_amount, max_amount, increment, _, _, _ = _get_loan_limits()
    if max_override:
        try:
            max_amount = int(max_override)
        except (TypeError, ValueError):
            pass
    choices = []
    amount = min_amount
    while amount <= max_amount:
        choices.append((amount, amount))
        amount += increment
    # Always include the exact ceiling so a non-increment-aligned per-client
    # limit is still selectable.
    if choices and choices[-1][0] != max_amount and max_amount >= min_amount:
        choices.append((max_amount, max_amount))
    return choices


def generate_fortnight_choices():
    _, _, _, min_fn, max_fn, increment = _get_loan_limits()
    choices = []
    while min_fn <= max_fn:
        choices.append((min_fn, min_fn))
        min_fn += increment
    return choices


# Create your models here.
class Loan(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    ref = models.CharField(max_length=50, blank=True, null=True)
    uid = models.CharField(max_length=30, blank=True, null=True)
    luid = models.CharField(max_length=30, blank=True, null=True)
    existing_code = models.CharField(max_length=30, blank=True, null=True)

    owner = models.ForeignKey(UserProfile, on_delete=models.PROTECT,null=True, blank=True)
    officer = models.ForeignKey(StaffProfile, on_delete=models.PROTECT,null=True, blank=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE ,null=True, blank=True)
    loan_type = models.CharField("Loan Type:", max_length=30, blank=True, null=True,choices=[('PERSONAL', 'PERSONAL'),('SME','SME')], default="PERSONAL")
    classification = models.CharField("Loan Classification:", max_length=30, blank=True, null=True,choices=[('ADDITIONAL', 'ADDITIONAL'),('REFINANCED', 'REFINANCED'),('NEW','NEW')], default="NEW")
    purpose_of_loan = models.CharField("Purpose of Loan:", max_length=255, blank=True, null=True)

    application_date = models.DateField(auto_now=True, null=True)
    amount = models.DecimalField(verbose_name='LOAN AMOUNT:', max_digits=8, decimal_places=2, null=True, choices=generate_amount_choices())
    processing_fee = models.DecimalField(verbose_name='PROCESSING FEE:', max_digits=7, decimal_places=2, blank=True, null=True)
    interest = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    total_loan_amount = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    repayment_frequency = models.CharField(choices=[('FORTNIGHTLY', 'FORTNIGHTLY'),('MONTHLY','MONTHLY')], max_length=30, blank=True, null=True, default='FORTNIGHTLY')
    number_of_fortnights = models.IntegerField(verbose_name='Number of Fortnights:', null=True, choices=generate_fortnight_choices())
    repayment_amount = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
   
    category = models.CharField(max_length=30, blank=True, null=True,choices=[('PENDING','PENDING'),('FUNDED','FUNDED')])
    funded_category = models.CharField(max_length=30, blank=True, null=True,choices=[('ACTIVE','ACTIVE'), ('RECOVERY', 'RECOVERY'), ('BAD','BAD'), ('WOFF','WOFF'), ('COMPLETED','COMPLETED'), ('ARCHIVED','ARCHIVED'), ('AWAITING_REFUND', 'AWAITING REFUND')])
    status = models.CharField(max_length=30, blank=True, null=True,choices=[('AWAITING T&C', 'AWAITING T&C'),('UNDER REVIEW','UNDER REVIEW'),('ON HOLD','ON HOLD'),('APPROVED','APPROVED'),('REJECTED','REJECTED'),('RUNNING','RUNNING'),('DEFAULTED','DEFAULTED'),('COMPLETED','COMPLETED')])
    
    tc_agreement = models.CharField(max_length=3, blank=True, null=True, choices=[('YES', 'YES'),('NO', 'NO')])
    tc_agreement_timestamp = models.DateTimeField(blank=True, null=True)
    funding_date = models.DateField(verbose_name='Funding Date:', blank=True, null=True)
    repayment_start_date = models.DateField(verbose_name='Repayment Start Date:', null=True)
    expected_end_date = models.DateField(verbose_name='Expected end Date:', null=True)
    repayment_dates = models.TextField(null=True, blank=True)  # Store dates as JSON string
    # True when staff regenerated the schedule by hand (custom dates /
    # weekly / monthly spacing) — canonical 14-day rebuild tools must skip it.
    custom_schedule = models.BooleanField(default=False)
    # Optional per-fortnight expected repayment amounts, parallel to repayment_dates
    # (JSON list of decimal strings). Used when the fortnightly deduction is not
    # uniform — e.g. a CONCURRENT refinance where the repayment is higher while two
    # loans overlap, then steps down. Null/empty means the uniform repayment_amount
    # applies to every fortnight (see loan/schedule.py).
    repayment_amounts = models.TextField(null=True, blank=True)
    next_payment_date = models.DateField(blank=True, null=True)
    
    principal_loan_paid = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    interest_paid = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    default_interest_paid = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #total_default_interest_repaid = 
    total_paid = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)

    fortnights_paid = models.IntegerField(verbose_name='Number of Fortnights Paid:', null=True, blank=True, default=0)
    # Immutable-schedule cursor: number of scheduled fortnights accounted for by a
    # cash repayment, a default, or an advance-balance application. The remaining
    # due dates and next_payment_date are derived from this (see loan/schedule.py).
    fortnights_settled = models.IntegerField(verbose_name='Fortnights Settled:', null=True, blank=True, default=0)
    number_of_repayments = models.IntegerField(blank=True, null=True, default=0)
    last_repayment_amount = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    last_repayment_date = models.DateField(blank=True, null=True)
    
    number_of_advance_payments = models.IntegerField(blank=True, null=True, default=0)
    last_advance_payment_date = models.DateField(blank=True, null=True)
    last_advance_payment_amount = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    total_advance_payment = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0.00)
    advance_payment_surplus = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0.00)
    # Running prepaid credit: amount paid ahead of schedule that has not yet been
    # consumed. A default nets this against the shortfall before charging interest.
    advance_balance = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, default=0.00)
    
    number_of_defaults = models.IntegerField(blank=True, null=True, default=0)
    last_default_date = models.DateField(blank=True, null=True)
    last_default_amount = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    days_in_default = models.IntegerField(blank=True, null=True, default=0)
    total_arrears = models.DecimalField(max_digits=8, decimal_places=2, blank=True, default=0.00)

    #trupngfinance
    #optional (beyond finance logic)
    
    principal_loan_receivable = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)  #amount_remaining = 
    ordinary_interest_receivable = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #oridinary_interest_receivable = 
    default_interest_receivable = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #default_interest_receivable = 
    total_outstanding = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #total_receivable_amount 

    turnover_days = models.IntegerField(blank=True, null=True, default=0)
    aging_category = models.CharField(max_length=100, blank=True, null=True, choices=[('30LESS', '30LESS'),('30TO90', '30TO90'),('90TO180', '90TO180'),('180PLUS','180PLUS')])
    aging_amount = models.DecimalField(max_digits=8, decimal_places=2, blank=True, default=0.00)
    considered_unrecoverable = models.DecimalField(max_digits=8, decimal_places=2, blank=True, default=0.00)
    principal_c_unrecoverable = models.DecimalField(max_digits=8, decimal_places=2, blank=True, default=0.00)
    interest_c_unrecoverable = models.DecimalField(max_digits=8, decimal_places=2, blank=True, default=0.00)
    recovery_date = models.DateField(blank=True, null=True)

    opt1 = models.CharField(max_length=255, blank=True, null=True)
    opt2 = models.CharField(max_length=255, blank=True, null=True)
    opt3 = models.CharField(max_length=255, blank=True, null=True)
    opt4 = models.CharField(max_length=255, blank=True, null=True)
    opt5 = models.CharField(max_length=255, blank=True, null=True)

    dcc = models.CharField(max_length=255, blank=True, null=True,default='')
    # When a formal default notice for this loan was filed with the bureau.
    # Set once so the nightly reporting run does not re-file the same default;
    # DCC is idempotent per (tenant, loan ref) too, this just avoids the calls.
    dcc_default_reported_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    # Manager review workflow: contract generation + approval tracking
    # (see the manager app; gated by AdminSettings.role_manager_enabled).
    contract_generated = models.BooleanField(default=False)
    contract_signed = models.BooleanField(default=False)
    contract_signed_date = models.DateTimeField(blank=True, null=True)
    contract_url = models.URLField(blank=True, null=True)
    contract_file_path = models.CharField(max_length=500, blank=True, null=True)
    approval_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, null=True, blank=True, related_name='approved_loans')
    contract_expiry_date = models.DateField(blank=True, null=True)
    contract_email_sent = models.BooleanField(default=False)
    contract_email_sent_date = models.DateTimeField(blank=True, null=True)
    contract_brought_to_office = models.BooleanField(default=False)
    contract_received_date = models.DateField(blank=True, null=True)

    def get_repayment_dates(self):
        if self.repayment_dates:
            return json.loads(self.repayment_dates)
        return []

    def set_repayment_dates(self, dates):
        self.repayment_dates = json.dumps(dates)

    def get_repayment_amounts(self):
        if self.repayment_amounts:
            return json.loads(self.repayment_amounts)
        return []

    def set_repayment_amounts(self, amounts):
        self.repayment_amounts = json.dumps([str(a) for a in amounts])

    def formatted_amount(self):
        return "{:,.2f}".format(self.amount)
    
    def formatted_repayment_amount(self):
        return "{:,.2f}".format(self.repayment_amount)
    
    def __str__(self):
        return f'{self.ref}'
    
    class Meta:
        ordering = ['-funding_date']  # Assuming 'date' is a field in your Loan model
        verbose_name = 'Loan'
        verbose_name_plural = 'Loans'

class LoanFile(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    loan = models.OneToOneField(Loan, related_name='files', on_delete=models.CASCADE)
    
    #required uploads
    application_form = models.FileField('Application Form:', upload_to=loan_file_path, null=True, blank=True)
    application_form_url = models.CharField(max_length=555, null=True, blank=True)
    
    terms_conditions = models.FileField('Terms & Conditions:', upload_to=loan_file_path, null=True, blank=True)
    terms_conditions_url = models.CharField(max_length=555, null=True, blank=True)

    stat_dec = models.FileField('Statutory Declaration:', upload_to=loan_file_path, null=True, blank=True)
    stat_dec_url = models.CharField(max_length=555, null=True, blank=True)
    
    irr_sd_form = models.FileField('Irrevocable Salary Deduction Authority:', upload_to=loan_file_path, null=True, blank=True)
    irr_sd_form_url = models.CharField(max_length=555, null=True, blank=True)

    #work required uploads
    work_confirmation_letter = models.FileField('Work Confirmation Letter:', upload_to=loan_file_path, null=True, blank=True)
    work_confirmation_letter_url = models.CharField(max_length=555, null=True, blank=True)

    payslip1 = models.FileField('Payslip 1:', null=True, upload_to=loan_file_path, blank=True)
    payslip1_url = models.CharField(max_length=555, null=True, blank=True)

    payslip2 = models.FileField('Payslip 2:', null=True, upload_to=loan_file_path, blank=True)
    payslip2_url = models.CharField(max_length=555, null=True, blank=True)

    #statement Uploads

    loan_statement1 = models.FileField('Loan Statement 1:', upload_to=loan_file_path, null=True, blank=True)
    loan_statement1_url = models.CharField(max_length=555, null=True, blank=True)
    
    loan_statement2 = models.FileField('Loan Statement 2:', upload_to=loan_file_path, null=True, blank=True)
    loan_statement2_url = models.CharField(max_length=555, null=True, blank=True)

    loan_statement3 = models.FileField('Loan Statement 3:', upload_to=loan_file_path, null=True, blank=True)
    loan_statement3_url = models.CharField(max_length=555, null=True, blank=True)
    
    bank_statement = models.FileField('Bank Statement:', upload_to=loan_file_path, null=True, blank=True)
    bank_statement_url = models.CharField(max_length=555, null=True, blank=True)

    super_statement = models.FileField('Super Statement:', upload_to=loan_file_path, null=True, blank=True)
    super_statement_url = models.CharField(max_length=555, null=True, blank=True)

    bank_standing_order = models.FileField('Bank Standing Order:', upload_to=loan_file_path, null=True, blank=True)
    bank_standing_order_url = models.CharField(max_length=555, null=True, blank=True)

    #funding 
    funding_receipt = models.FileField('Funding Receipt:', upload_to=loan_file_path, null=True, blank=True)
    funding_receipt_url = models.CharField(max_length=555, null=True, blank=True)

    signed_contract = models.FileField('Signed Contract:', upload_to=loan_file_path, null=True, blank=True)
    signed_contract_url = models.CharField(max_length=555, null=True, blank=True)

class Statement(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    ref = models.CharField(max_length=50, blank=True, null=True)
    uid = models.CharField(max_length=50, blank=True, null=True)
    luid = models.CharField(max_length=50, blank=True, null=True)
    owner = models.ForeignKey(UserProfile, on_delete=models.PROTECT, null=True, blank=True)
    loanref = models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True)
    
    date = models.DateField()
    type = models.CharField(max_length=255, choices=[('PAYMENT','PAYMENT'), ('DEFAULT', 'DEFAULT'), ('OTHER', 'OTHER')], blank=True, null=True)
    s_count = models.IntegerField(blank=True, null=True, default=0)
    
    statement = models.CharField(max_length=255, null=True, blank=True)
    debit = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    credit = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    arrears = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    balance = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)

    default_amount = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    default_interest = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #added to loan total

    #optional for those who seperate loan , interest (beyond finance logic) or for those who want to track interest on default
    principal_collected = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #principal_loan_receipted
    interest_collected = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)  #interest_earned_receipted
    default_interest_collected = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #default_interest_receipted

    dcc = models.CharField(max_length=30, null=True, blank=True)

class PaymentUploads(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ref = models.CharField(max_length=30, null=True, blank=True)
    owner =  models.ForeignKey(UserProfile, on_delete=models.PROTECT, null=True, blank=True)
    loan =  models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True)
    payment_proof = models.FileField(null=True, blank=True)
    
    type = models.CharField(max_length=55, null=True, blank=True, choices=[('NORMAL REPAYMENT','NORMAL REPAYMENT'),('ADVANCE PAYMENT', 'ADVANCE PAYMENT')])
    file_name = models.CharField(max_length=255, null=True)
    payment_proof_url = models.CharField(max_length=255, null=True)
    status = models.CharField(max_length=255, null=True, blank=True)

class Payment(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(UserProfile, on_delete=models.PROTECT, null=True, blank=True)
    ref = models.CharField(max_length=50, blank=True, null=True)
    loanref =  models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True)
    p_count = models.IntegerField(blank=True, null=True, default=0)
    date = models.DateField()
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    type = models.CharField(max_length=55, null=True, blank=True, choices=[('NORMAL REPAYMENT','NORMAL REPAYMENT'),('ADVANCE PAYMENT', 'ADVANCE PAYMENT'),('PARTIAL PAYMENT','PARTIAL PAYMENT')])
    mode = models.CharField(max_length=55, null=True, blank=True, choices=[('PAYROLL DEDUCTION','PAYROLL DEDUCTION'),('BANK DEPOSIT', 'BANK DEPOSIT'),('CASH','CASH')])
    statement = models.CharField(max_length=555, null=True)
    upload_id =  models.ForeignKey(PaymentUploads, on_delete=models.PROTECT, null=True, blank=True)
    officer = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, null=True, blank=True)


class LoanCredit(models.Model):
    """Money owed back to a client after an overpaid loan closure."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    owner = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='loan_credits')
    loan = models.ForeignKey(Loan, on_delete=models.SET_NULL, null=True, blank=True, related_name='credits')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=30, default='OVERPAYMENT_AT_CLOSURE', choices=[
        ('OVERPAYMENT_AT_CLOSURE', 'Overpayment at Loan Closure'),
        ('MANUAL', 'Manual Adjustment'),
    ])
    note = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True)

    refunded = models.BooleanField(default=False)
    refunded_at = models.DateField(null=True, blank=True)
    refund_receipt = models.FileField(upload_to='refund_receipts', null=True, blank=True)
    refund_note = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.owner} - K{self.amount} ({"refunded" if self.refunded else "owing"})'


class AlescoPayRun(models.Model):
    """A single uploaded Alesco Deduction Variation listing (one pay period)."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    ref = models.CharField(max_length=40, blank=True, null=True)
    file = models.FileField(upload_to='alesco', null=True, blank=True)
    file_name = models.CharField(max_length=255, null=True, blank=True)

    # Parsed header values from the listing
    period_end = models.DateField(null=True, blank=True)              # "Period End" date — the payment date
    pay_period = models.CharField(max_length=10, null=True, blank=True)
    pay_year = models.CharField(max_length=10, null=True, blank=True)
    paycode = models.CharField(max_length=30, null=True, blank=True)   # e.g. DLMX
    employer_name = models.CharField(max_length=255, null=True, blank=True)  # e.g. the client's employer / PNG Government
    company_code = models.CharField(max_length=100, null=True, blank=True)

    total_this_period = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    employee_count = models.IntegerField(default=0)

    status = models.CharField(max_length=20, default='PENDING',
                              choices=[('PENDING', 'PENDING'), ('PARTIAL', 'PARTIAL'), ('COMPLETED', 'COMPLETED')])
    uploaded_by = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-period_end', '-created_at']

    def __str__(self):
        return f'{self.ref or self.file_name} ({self.period_end})'


class AlescoPayLine(models.Model):
    """One employee row from an Alesco listing, mapped to a client/loan."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    run = models.ForeignKey(AlescoPayRun, related_name='lines', on_delete=models.CASCADE)

    # As read from the file
    employee_file_number = models.CharField(max_length=30, null=True, blank=True)
    job_number = models.CharField(max_length=10, null=True, blank=True)
    report_name = models.CharField(max_length=255, null=True, blank=True)
    this_period = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    last_period = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    file_variance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    arrears = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Mapping to system records
    owner = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True)
    loanref = models.ForeignKey(Loan, on_delete=models.SET_NULL, null=True, blank=True)
    employer_name = models.CharField(max_length=255, null=True, blank=True)  # client's employer at processing time

    # Reconciliation: expected scheduled repayment vs the actual "This Period" amount
    expected_repayment = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    variance = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # this_period - expected_repayment

    payment_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, default='PENDING',
                              choices=[('PENDING', 'PENDING'), ('CONFIRMED', 'CONFIRMED'),
                                       ('UNMATCHED', 'UNMATCHED'), ('SKIPPED', 'SKIPPED')])
    payment = models.ForeignKey('Payment', on_delete=models.SET_NULL, null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True)
    # Loan state captured immediately before this line was confirmed, so the
    # confirmation can be rolled back (see loan.alesco.rollback_line).
    loan_snapshot = models.JSONField(null=True, blank=True)
    # Refund tracking for UNMATCHED deductions (money received for a person who
    # is not a client — shown on the Unmatched Payments register until refunded).
    refunded = models.BooleanField(default=False)
    refunded_at = models.DateField(null=True, blank=True)
    refund_note = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['report_name']

    def __str__(self):
        return f'{self.employee_file_number} - {self.report_name} ({self.this_period})'


class BlackroseImport(models.Model):
    """One uploaded Blackrose statement PDF, parsed and awaiting import.

    Statements are parsed on upload and held here so staff can check (and
    correct) what was read before any client or loan is created — the parse is
    kept in ``parsed`` so the review screen never has to re-read the PDF, and
    the record stays afterwards as the audit trail linking a migrated loan back
    to the statement it came from. See loan/blackrose.py.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    file = models.FileField(upload_to='blackrose', null=True, blank=True)
    file_name = models.CharField(max_length=255, null=True, blank=True)
    # sha256 of the upload — the same statement loaded twice is caught here.
    file_hash = models.CharField(max_length=64, db_index=True, null=True, blank=True)

    lender_name = models.CharField(max_length=255, null=True, blank=True)
    client_name = models.CharField(max_length=255, null=True, blank=True)
    client_code = models.CharField(max_length=50, null=True, blank=True)
    employer = models.CharField(max_length=255, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)

    # The full parse: client block, every row, and any parser warnings.
    parsed = models.JSONField(null=True, blank=True)
    row_count = models.IntegerField(default=0)
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    status = models.CharField(max_length=20, default='PENDING',
                              choices=[('PENDING', 'PENDING'), ('IMPORTED', 'IMPORTED'),
                                       ('FAILED', 'FAILED'), ('SKIPPED', 'SKIPPED')])
    error = models.TextField(null=True, blank=True)

    owner = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True)
    loan = models.ForeignKey(Loan, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='blackrose_imports')
    client_created = models.BooleanField(default=False)

    uploaded_by = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Blackrose Statement Import'
        verbose_name_plural = 'Blackrose Statement Imports'

    def __str__(self):
        return f'{self.client_name or self.file_name} ({self.status})'


# Define a function to delete associated files when a loan is deleted
@receiver(pre_delete, sender=Loan)
def delete_loan_files(sender, instance, **kwargs):
    """Delete all physical files associated with a Loan when it is deleted."""
    _FILE_FIELDS = [
        'application_form', 'terms_conditions', 'stat_dec', 'irr_sd_form',
        'work_confirmation_letter', 'payslip1', 'payslip2',
        'loan_statement1', 'loan_statement2', 'loan_statement3',
        'bank_statement', 'super_statement', 'bank_standing_order',
    ]
    for loan_file in LoanFile.objects.filter(loan=instance):
        for field_name in _FILE_FIELDS:
            field = getattr(loan_file, field_name, None)
            if field and field.name:
                try:
                    if os.path.exists(field.path):
                        os.remove(field.path)
                except Exception:
                    pass



# Repayments Models
# FOR STATEMENT GENERATION

#repayment_dates = {dictionary}
