from django.conf import settings
from django.db import models

class AdminSettings(models.Model):
    DATE_FORMAT_CHOICES = [
        ('Y-m-d', 'YYYY-MM-DD'),
        ('d/m/Y', 'DD/MM/YYYY'),
        ('m/d/Y', 'MM/DD/YYYY'),
        ('d-m-Y', 'DD-MM-YYYY'),
        ('M d, Y', 'Jan 31, 2026'),
    ]
    
    settings_name = models.CharField(max_length=30, blank=True, null=True)
    loanref_prefix = models.CharField(verbose_name="Loan Reference Prefix:", max_length=5, help_text="Short code placed in front of every loan reference, e.g. 'MFX'.", blank=True, null=True)
    admin_email_addresses = models.CharField(verbose_name="Admin Email Addresses:", max_length=250, help_text="Email Addresses that will receive system admin notifications. Enter email addresses separated by a comma. Eg: info@moromafinance.com.pg,admin@moromafinance.com.pg. Make sure there are no spaces after the comma", blank=True, default=settings.EMAIL_HOST_USER)
    default_from_email = models.CharField(verbose_name="Default From Email:", max_length=100, help_text="Email Address that will send all notifications to the user.", blank=True, default=settings.DEFAULT_FROM_EMAIL)
    support_email = models.CharField(verbose_name="Support Email:", max_length=100, help_text="Email Address that will receive all support requests.", blank=True, default=settings.SUPPORT_EMAIL)
    credit_check = models.CharField(verbose_name="Automatic Credit Check:", max_length=255, choices=[('NO','NO - We will decide'),('YES','YES - Automatic')], null=True, blank=True, help_text="If you set this to yes, Loan Application Decision will be made automatically based on your client credit threshold setting.")
    dcc_enabled = models.CharField(verbose_name="DCC Credit Bureau:", max_length=3, choices=[('YES','YES - Enable billed pay-per-view credit checks'),('NO','NO - Disable credit checks (searches are not billed)')], null=True, blank=True, default='YES', help_text="When enabled, staff can unlock DCC credit reports from the client screen — each unlocked view is billed by DCC and stays open for the access window set by DCC. When disabled, no credit checks run and nothing is billed. NOTE: the data feed to DCC always stays on; keeping the bureau current is a condition of the DCC service.")

    # ── DCC benchmark-rating automation ─────────────────────────────────────
    dcc_autocredit_enabled = models.CharField(verbose_name="Use DCC Benchmark Score in Automatic Credit Check:", max_length=3, choices=[('YES','YES - Check the DCC benchmark score automatically'),('NO','NO - Use local credit rating only')], null=True, blank=True, default='NO', help_text="When Automatic Credit Check runs, also fetch the client's DCC benchmark score (0-1000, computed by the bureau from all lenders' data) and block applications below the minimum score. Each check is billed at the DCC rating-check price.")
    dcc_min_score = models.PositiveIntegerField(verbose_name="Minimum DCC Score:", default=400, help_text="Loan applications from clients whose DCC benchmark score (0-1000) is below this are automatically declined.")
    dcc_autoset_limits = models.CharField(verbose_name="Auto-Set Limits from DCC Score:", max_length=3, choices=[('YES','YES - Scale limits by DCC score'),('NO','NO - Set limits manually')], null=True, blank=True, default='NO', help_text="When enabled, the client's repayment limit and loan ceiling are set automatically in proportion to their DCC score (score/1000 x the maximums below) each time the score is fetched.")
    dcc_limit_max_repayment = models.DecimalField(verbose_name="Repayment Limit at Score 1000 (K):", max_digits=10, decimal_places=2, null=True, blank=True, help_text="A client with a perfect DCC score of 1000 gets this repayment limit; lower scores scale down proportionally.")
    dcc_limit_max_ceiling = models.DecimalField(verbose_name="Loan Ceiling at Score 1000 (K):", max_digits=10, decimal_places=2, null=True, blank=True, help_text="A client with a perfect DCC score of 1000 gets this maximum loan amount; lower scores scale down proportionally.")

    # Roles & Access: which account roles/portals are active for this tenant.
    role_user_enabled = models.CharField(verbose_name="Client Self-Registration:", max_length=3, choices=[('YES','YES - Allow new clients to register online'),('NO','NO - Staff must create client accounts')], null=True, blank=True, default='YES')
    role_staff_enabled = models.CharField(verbose_name="Staff Portal:", max_length=3, choices=[('YES','YES - Staff portal enabled'),('NO','NO - Staff portal disabled')], null=True, blank=True, default='YES')
    role_manager_enabled = models.CharField(verbose_name="Manager Role:", max_length=3, choices=[('YES','YES - Enable manager review workflow'),('NO','NO - Managers behave as regular staff')], null=True, blank=True, default='NO', help_text="When enabled, staff assigned the Manager role get a review portal for approving/rejecting/holding pending loans and payment uploads, with optional auto-generated loan contracts.")

    # Manager review workflow: loan-approval contract generation.
    contract_generation_enabled = models.CharField(verbose_name="Auto-Generate Loan Contract on Approval:", max_length=3, choices=[('YES','YES'),('NO','NO')], null=True, blank=True, default='NO', help_text="When a manager approves a pending loan, automatically generate a contract PDF and email it to the client and lending officer.")
    contract_default_fee = models.DecimalField(verbose_name="Contract Default Fee (K):", max_digits=8, decimal_places=2, null=True, blank=True, default=20.00, help_text="Default fee disclosed in the loan contract for late/missed payments.")
    contract_default_interest_rate = models.DecimalField(verbose_name="Contract Default Interest Rate (% p.a.):", max_digits=5, decimal_places=2, null=True, blank=True, default=10.00, help_text="Annual default interest rate disclosed in the loan contract.")

    # Credit Assessment: client financial-position capture used to support
    # lending decisions (Statement of Position, referee & previous-employer info).
    credit_assessment_enabled = models.CharField(verbose_name="Credit Assessment:", max_length=3, choices=[('YES','YES - Enable Statement of Position, referee & previous-employer capture'),('NO','NO - Disabled')], null=True, blank=True, default='NO', help_text="When enabled, clients and staff can record a Statement of Position (assets/liabilities/income/expenses), a referee, and previous-employer details to support credit decisions.")

    approval_credit_threshold = models.DecimalField(verbose_name="Approval Credit Threshold:", max_digits=5, decimal_places=3, blank=True, null=True, help_text="User's with credit rating above this will have loan applications allowed if credit check is set to automatic.")
    percentage_of_gross = models.DecimalField(verbose_name="Percentage of Gross allowable:", max_digits=5, decimal_places=3, blank=True, null=True)
    interest_type = models.CharField(verbose_name="Interest Type:", max_length=255, choices=[('FIXED','FIXED'),('VARIABLE','VARIABLE'),('CUSTOM','CUSTOM')], null=True, blank=True)
    interest_rate = models.DecimalField(verbose_name="Interest Rate in Percentage:", max_digits=5, decimal_places=3, blank=True, null=True, help_text="If interest is fixed, enter standard interest, eg: 30%. If Interest is variable, enter per term interest. Eg, 1.25% per fortnight")
    processing_fee = models.CharField(verbose_name="Processing Fee:", max_length=255, choices=[('YES','YES'),('NO','NO')], null=True, blank=True, default='NO')
    processing_fee_collection_mode = models.CharField(
        verbose_name="Processing Fee Collection Mode:",
        max_length=10,
        choices=[('CASH', 'Cash'), ('WITHHELD', 'Withheld')],
        default='CASH',
        help_text="Cash: client pays the processing fee separately in cash. Withheld: the fee is deducted from the loan amount paid to the client.",
    )
    processing_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    DEFAULT_INTEREST_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage of Repayment Amount (%)'),
        ('FIXED', 'Fixed Amount (K)'),
    ]
    default_interest_type = models.CharField(
        verbose_name="Default Interest Type:",
        max_length=10,
        choices=DEFAULT_INTEREST_TYPE_CHOICES,
        default='PERCENTAGE',
        help_text="PERCENTAGE: charges a percentage of the missed repayment as default interest. FIXED: charges a flat kina amount regardless of repayment size.",
    )
    default_interest_rate = models.DecimalField(
        verbose_name="Default Interest Rate / Amount:",
        max_digits=8, decimal_places=2, blank=True, null=True,
        help_text="If PERCENTAGE: enter the percentage, e.g. 20 for 20% of the repayment amount. If FIXED: enter the kina amount, e.g. 50 for K50.00 per default.",
    )
    DEFAULT_INTEREST_BASE_CHOICES = [
        ('SHORTFALL', 'Shortfall (unpaid portion after netting any advance)'),
        ('FULL', 'Full scheduled repayment amount'),
    ]
    default_interest_base = models.CharField(
        verbose_name="Charge Default Interest On:",
        max_length=10, choices=DEFAULT_INTEREST_BASE_CHOICES, default='SHORTFALL',
        help_text="SHORTFALL: percentage default interest is charged only on the unpaid portion of the repayment (after subtracting any advance balance). FULL: charged on the entire scheduled repayment amount. Only affects PERCENTAGE default interest.",
    )
    auto_default_on_shortfall = models.BooleanField(
        verbose_name="Auto-Default on Repayment Shortfall:",
        default=True,
        help_text="When a client pays LESS than the scheduled repayment, automatically treat the unpaid shortfall as a default: charge default interest on the shortfall and add the shortfall to arrears. Turn off if partial payments should not be defaulted automatically.",
    )
    # ── Payroll / deduction categories offered at client registration ──────────
    dc_alesco_enabled = models.BooleanField(verbose_name="Offer ALESCO Payroll", default=True)
    dc_private_enabled = models.BooleanField(verbose_name="Offer Private Sector Payroll", default=True)
    dc_standing_order_enabled = models.BooleanField(verbose_name="Offer Standing Order Deductions", default=True)
    dc_voluntary_enabled = models.BooleanField(verbose_name="Offer Voluntary Deductions", default=True)
    date_format = models.CharField(verbose_name="System Date Format:", max_length=20, choices=DATE_FORMAT_CHOICES, default='Y-m-d', help_text="Systemwide display/input date format for date pickers and date fields.")
    employer_preregistration_required = models.BooleanField(default=False, help_text="If enabled, clients can only select from pre-registered employers.")
    email_system_to_work_email = models.BooleanField(
        verbose_name="Enable System Emails to Client Work Email:",
        default=True,
        help_text="Global switch. When ON, system notification emails (loan funding, CDN, amortization, etc.) are sent to clients' work email addresses. Individual client overrides still apply. When OFF, no system email goes to any work email regardless of per-client setting.",
    )
    
    LOAN_MODE_CHOICES = [
        ('LOCKED', 'Locked - Select amount & number of fortnights'),
        ('OPEN_REPAYMENT', 'Open Repayment - Enter amount, fortnights, and repayment'),
    ]
    
    user_loan_application_mode = models.CharField(verbose_name="User Loan Application Mode:", max_length=20, choices=LOAN_MODE_CHOICES, default='LOCKED', help_text="Controls how the user loan application form behaves.")
    staff_loan_creation_mode = models.CharField(verbose_name="Staff Loan Creation Mode:", max_length=20, choices=LOAN_MODE_CHOICES, default='LOCKED', help_text="Controls how the staff loan creation form behaves.")

    REFINANCE_TYPE_CHOICES = [
        ('OFFSET_BALANCE', 'Offset Balance - The new amount offsets current running loan balance and the rest is paid to client'),
        ('ADD_ON', 'Add On - The new loan amount + interest is added onto the existing balance and term added to remaining number of fortnights'),
        ('CONCURRENT', 'Concurrent - The balance is updated with new totals, the repayment is doubled, and once term of first ends, the repayment of the additional loan continues with remaining term of additional loan'),
        ('ADD_ON_VARIED', 'Add On (Varied) - The new loan total is added onto the existing balance like Add On, but the combined repayment term and fortnightly repayment are entered by staff at funding'),
        ('REFINANCE_NOT_ALLOWED', 'Refinance Not Allowed - A client with an existing loan (funded or pending) cannot get a new or additional loan at all, for any reason, until it is fully completed. One loan per client.'),
    ]
    refinance_type = models.CharField(
        verbose_name="Refinance Type:",
        max_length=25,
        choices=REFINANCE_TYPE_CHOICES,
        default='OFFSET_BALANCE',
        help_text="Select how refinanced loans are structured.",
    )

    send_cash_disbursement_notice = models.BooleanField(verbose_name="Send Cash Disbursement Notice (CDN):", default=True, help_text="When enabled, a Cash Disbursement Notice PDF is generated and emailed at the time the loan is funded.")

    # Loan Amortization Schedule column visibility
    las_col_period = models.BooleanField(verbose_name="LAS: Show Period column", default=True)
    las_col_date = models.BooleanField(verbose_name="LAS: Show Repayment Date column", default=True)
    las_col_opening = models.BooleanField(verbose_name="LAS: Show Opening Balance column", default=True)
    las_col_interest = models.BooleanField(verbose_name="LAS: Show Interest column", default=True)
    las_col_principal = models.BooleanField(verbose_name="LAS: Show Principal column", default=True)
    las_col_repayment = models.BooleanField(verbose_name="LAS: Show Repayment column", default=True)
    las_col_closing = models.BooleanField(verbose_name="LAS: Show Closing Balance column", default=True)
    cdn_send_to_payroll_officer = models.BooleanField(verbose_name="Send CDN to Client's Payroll Officer Email:", default=True, help_text="When enabled, the CDN is sent directly to the client's Payroll Officer email (with admin CC). When disabled, the CDN is sent to admin only.")
    display_referrer_on_loan = models.BooleanField(verbose_name="Display Referrer on Loan Information:", default=True, help_text="When enabled, the client's referrer is shown on the loan information page (for the referral commission system). Turn off for companies that do not run a referral/commission program.")
    send_loan_amortization_schedule = models.BooleanField(verbose_name="Send Loan Amortization Schedule:", default=True, help_text="When enabled, the loan amortization/repayment schedule is emailed to the client when the loan is funded.")

    minimum_repayment_limit = models.DecimalField(verbose_name="Minimum Repayment Limit:", max_digits=10, decimal_places=2, blank=True, null=True, help_text="Global minimum repayment limit that all users must have set before applying for a loan. Leave blank to use 0.")
    repayment_limit_check_enabled = models.BooleanField(verbose_name="Enable Repayment Limit Check:", default=True, help_text="If enabled, the repayment limit is checked when a client applies for a loan. Disable to bypass the repayment limit check entirely.")
    bypass_activation_check = models.BooleanField(verbose_name="Bypass Account Activation Check:", default=False, help_text="If enabled, the account activation field (activation) is NOT checked when a client applies for a loan. Useful for testing or for systems that do not require activation.")
    default_repayment_limit = models.DecimalField(verbose_name="Default Repayment Limit on Activation:", max_digits=10, decimal_places=2, blank=True, null=True, help_text="This repayment limit is automatically assigned to a client when their account is activated. Leave blank to keep existing limit unchanged.")
    default_payment_description = models.CharField(verbose_name="Default Payment Description:", max_length=255, blank=True, null=True, default="Fortnightly Salary Deduction", help_text="Used as the payment description when the Description field is disabled or left empty on the payment form.")

    # ── General / Company Settings ─────────────────────────────────────────────
    alesco_dc = models.CharField(
        verbose_name="Alesco Deduction Code:",
        max_length=20, blank=True, null=True,
        help_text="Government payroll deduction code for public servant employees (Alesco system).",
        default='',
    )
    swift = models.CharField(
        verbose_name="SWIFT Code:",
        max_length=20, blank=True, null=True, default='',
    )

    # ── Company Bank Account (for IRSDA / CDN) ─────────────────────────────────
    bank1 = models.CharField(verbose_name="Company Bank:", max_length=100, blank=True, null=True, default='')
    bank1_acc_name = models.CharField(verbose_name="Account Name:", max_length=150, blank=True, null=True, default='')
    bank1_acc_num = models.CharField(verbose_name="Account Number:", max_length=30, blank=True, null=True, default='')
    bank1_branch = models.CharField(verbose_name="Branch:", max_length=100, blank=True, null=True, default='')
    bank1_bsb = models.CharField(verbose_name="BSB / Sort Code:", max_length=20, blank=True, null=True, default='')

    # ── Loan Amount & Fortnight Limits ────────────────────────────────────────
    loan_min_amount = models.DecimalField(
        verbose_name="Minimum Loan Amount (K):",
        max_digits=10, decimal_places=2, blank=True, null=True,
        default=100.00,
        help_text="Minimum loan amount a client can apply for.",
    )
    loan_max_amount = models.DecimalField(
        verbose_name="Maximum Loan Amount (K):",
        max_digits=10, decimal_places=2, blank=True, null=True,
        default=5000.00,
        help_text="Maximum loan amount a client can apply for.",
    )
    increment_amount = models.IntegerField(
        verbose_name="Loan Amount Increment (K):",
        blank=True, null=True, default=100,
        help_text="Step size for the loan amount dropdown (e.g. 100 = K300, K400, K500 …).",
    )
    min_fn = models.IntegerField(
        verbose_name="Minimum Fortnights:",
        blank=True, null=True, default=1,
        help_text="Minimum number of fortnights a loan can be repaid over.",
    )
    max_fn = models.IntegerField(
        verbose_name="Maximum Fortnights:",
        blank=True, null=True, default=30,
        help_text="Maximum number of fortnights a loan can be repaid over.",
    )
    increment_fn = models.IntegerField(
        verbose_name="Fortnight Increment:",
        blank=True, null=True, default=1,
        help_text="Step size for the fortnight dropdown (usually 1).",
    )
    default_interest_calculation_mercy_days = models.IntegerField(
        verbose_name="Default Mercy Period (days):",
        blank=True, null=True, default=7,
        help_text="Number of days after a missed payment date before the automatic classifier runs and applies default interest. E.g. 7 means the system waits 7 days after the due date before classifying the loan as defaulted.",
    )
    auto_classify_default = models.BooleanField(
        verbose_name="Enable Automatic Default Classification:",
        default=False,
        help_text="When ON, the Celery scheduled task automatically calculates default interest, updates loan balances, creates a statement entry, and notifies the client once the mercy period has elapsed with no payment recorded. When OFF, defaults must be registered manually.",
    )

    # ── Appearance / White-label branding (per tenant) ─────────────────────────
    FONT_CHOICES = [
        ('Roboto', 'Roboto (default)'),
        ('Open Sans', 'Open Sans'),
        ('Lato', 'Lato'),
        ('Poppins', 'Poppins'),
        ('Inter', 'Inter'),
        ('Montserrat', 'Montserrat'),
        ('Nunito', 'Nunito'),
        ('Source Sans Pro', 'Source Sans Pro'),
    ]
    brand_name = models.CharField(verbose_name="Brand / Company Name:", max_length=100, blank=True, null=True,
                                  help_text="Shown in the sidebar, page titles and emails. Leave blank to use the system default.")
    brand_logo = models.FileField(verbose_name="Brand Logo (sidebar / header):", upload_to='branding/', blank=True, null=True,
                                  help_text="PNG/SVG logo shown in the sidebar. Leave blank to use the default logo.")
    login_logo = models.FileField(verbose_name="Login Page Logo:", upload_to='branding/', blank=True, null=True,
                                  help_text="Optional separate logo for the login page. Falls back to the brand logo.")
    favicon = models.FileField(verbose_name="Favicon:", upload_to='branding/', blank=True, null=True,
                               help_text="Optional browser tab icon (32x32 PNG).")
    primary_color = models.CharField(verbose_name="Primary / Brand Colour:", max_length=9, blank=True, null=True, default='#6bb10d',
                                     help_text="Hex colour for buttons, links and active menu items, e.g. #6bb10d.")
    sidebar_bg_color = models.CharField(verbose_name="Sidebar Background Colour:", max_length=9, blank=True, null=True, default='#1f2a44',
                                        help_text="Hex background colour of the left sidebar.")
    sidebar_light_text = models.BooleanField(verbose_name="Light Sidebar Text:", default=True,
                                             help_text="Use light (white) text/icons in the sidebar. Turn off for a light sidebar background.")
    topbar_color = models.CharField(verbose_name="Report/Header Strip Colour:", max_length=9, blank=True, null=True, default='#344767',
                                    help_text="Hex colour for report header strips and dark headers.")
    font_family = models.CharField(verbose_name="Font:", max_length=30, choices=FONT_CHOICES, default='Roboto', blank=True, null=True)

    # ── Loan Application Document Sending ──────────────────────────────────────
    # When a loan application is generated the system produces the prefilled
    # application PDFs (Loan Application, Terms & Conditions, Statutory
    # Declaration, IR Salary Deduction Authority). These settings control whether
    # those documents are emailed, to whom, and which documents are attached.
    send_application_documents = models.BooleanField(
        verbose_name="Send Loan Application Documents:",
        default=True,
        help_text="Master switch. When ON, the prefilled application PDFs are emailed when a loan application is generated. When OFF, no application documents are sent.",
    )
    appdoc_send_to_user = models.BooleanField(
        verbose_name="Send to Client:", default=True,
        help_text="Include the client (applicant) as a recipient of the application documents.",
    )
    appdoc_send_to_staff = models.BooleanField(
        verbose_name="Send to Staff:", default=False,
        help_text="Include the staff member who created the application (and the application-form email list) as recipients.",
    )
    appdoc_bcc_admin = models.BooleanField(
        verbose_name="BCC Admin:", default=False,
        help_text="Blind-copy the admin notification addresses on the application documents email.",
    )
    appdoc_include_application = models.BooleanField(
        verbose_name="Attach Loan Application Form:", default=True,
    )
    appdoc_include_terms = models.BooleanField(
        verbose_name="Attach Terms & Conditions:", default=True,
    )
    appdoc_include_stat_dec = models.BooleanField(
        verbose_name="Attach Statutory Declaration:", default=True,
    )
    appdoc_include_irsda = models.BooleanField(
        verbose_name="Attach Irrevocable Salary Deduction Authority:", default=True,
    )

    # ── Alesco Payroll Update ──────────────────────────────────────────────────
    send_alesco_pay_update_email = models.BooleanField(
        verbose_name="Send Alesco Pay Update Email to Client:", default=True,
        help_text="When ON, confirming an Alesco payroll update line emails the client a payment/balance update (the same notice sent when a normal pay is recorded). When OFF, balances are still updated and statements created, but no client email is sent for Alesco updates.",
    )

    # Referral settings
    referral_commission = models.DecimalField(
        verbose_name="Referral Commission (K):",
        max_digits=8, decimal_places=2, blank=True, null=True, default=50.00,
        help_text="Fixed kina amount paid to a referrer for each client they refer who registers."
    )
    referral_enabled = models.BooleanField(
        verbose_name="Enable Referral Programme:",
        default=True,
        help_text="Master switch. When OFF, all referrer menus, forms, fields, reports and pages are hidden — only this settings page stays reachable so it can be switched back on.",
    )
    referral_payment_day = models.IntegerField(
        verbose_name="Referral Payment Day:",
        default=31,
        help_text="Day of the month when referral commissions are paid out (e.g. 31 = last day of month)."
    )

    # Display / formatting settings
    DECIMAL_PLACES_CHOICES = [
        (0, '0 — Whole numbers only'),
        (1, '1 decimal place'),
        (2, '2 decimal places (default)'),
    ]
    ROUNDING_CHOICES = [
        ('HALF_UP', 'Half Up (standard rounding)'),
        ('CEILING', 'Round Up (ceiling — always round up)'),
        ('FLOOR', 'Round Down (floor — always round down)'),
    ]
    display_decimal_places = models.IntegerField(
        verbose_name="Currency Decimal Places:",
        choices=DECIMAL_PLACES_CHOICES,
        default=2,
        help_text="Number of decimal places to show for all currency amounts throughout the system. Default is 2.",
    )
    decimal_rounding = models.CharField(
        verbose_name="Decimal Rounding Method:",
        max_length=10,
        choices=ROUNDING_CHOICES,
        default='HALF_UP',
        help_text="Only applies when 0 or 1 decimal places is selected. HALF_UP is standard rounding; CEILING always rounds up; FLOOR always rounds down.",
    )

_ALL_DEDUCTION_CATEGORIES = [
    ('ALESCO', 'ALESCO Payroll', 'dc_alesco_enabled'),
    ('PRIVATE', 'Private Sector Payroll', 'dc_private_enabled'),
    ('STANDING_ORDER', 'Standing Order Deductions', 'dc_standing_order_enabled'),
    ('VOLUNTARY', 'Voluntary Deductions', 'dc_voluntary_enabled'),
]


def get_enabled_deduction_categories():
    """Return [(value, label), ...] for the deduction categories the admin has
    enabled. Defaults to all four when settings are unavailable."""
    try:
        s = AdminSettings.objects.filter(settings_name='setting1').first()
    except Exception:
        s = None
    result = []
    for value, label, flag in _ALL_DEDUCTION_CATEGORIES:
        if s is None or getattr(s, flag, True):
            result.append((value, label))
    return result or [(v, l) for v, l, _f in _ALL_DEDUCTION_CATEGORIES]


def deduction_category_label(value):
    for v, l, _f in _ALL_DEDUCTION_CATEGORIES:
        if v == value:
            return l
    return value or '—'


def get_appearance():
    """Resolved appearance/branding config for the current tenant, with sensible
    fallbacks. Consumed by the appearance context processor so every page can
    theme itself."""
    from django.conf import settings as dj_settings
    s = None
    try:
        s = AdminSettings.objects.filter(settings_name='setting1').first()
    except Exception:
        s = None

    def _v(attr, default):
        val = getattr(s, attr, None) if s else None
        return val if val not in (None, '') else default

    def _url(attr):
        f = getattr(s, attr, None) if s else None
        try:
            return f.url if f else ''
        except Exception:
            return ''

    return {
        'brand_name': _v('brand_name', getattr(dj_settings, 'SITE_NAME', 'Moroma Finance')),
        'brand_logo_url': _url('brand_logo'),
        'login_logo_url': _url('login_logo') or _url('brand_logo'),
        'favicon_url': _url('favicon'),
        'primary_color': _v('primary_color', getattr(dj_settings, 'MAIN_COLOR', '#6bb10d')),
        'sidebar_bg_color': _v('sidebar_bg_color', '#1f2a44'),
        'sidebar_light_text': (getattr(s, 'sidebar_light_text', True) if s else True),
        'topbar_color': _v('topbar_color', '#344767'),
        'font_family': _v('font_family', 'Roboto'),
        'font_family_url': _v('font_family', 'Roboto').replace(' ', '+'),
        'credit_assessment_enabled': bool(s and s.credit_assessment_enabled == 'YES'),
    }


def get_document_theme():
    """Return tenant branding that is safe to use in generated documents.

    PDF renderers do not necessarily share the authenticated browser session
    needed to read uploaded media. Embed the configured brand logo so statement,
    LAS and CDN output remains tenant-specific in previews, downloads and email.
    """
    import base64
    import mimetypes

    theme = get_appearance()
    theme['brand_logo_data_uri'] = ''
    try:
        s = AdminSettings.objects.filter(settings_name='setting1').first()
        logo = getattr(s, 'brand_logo', None) if s else None
        if logo:
            mime_type = mimetypes.guess_type(logo.name)[0] or 'image/png'
            with logo.open('rb') as logo_file:
                encoded = base64.b64encode(logo_file.read()).decode('ascii')
            theme['brand_logo_data_uri'] = f'data:{mime_type};base64,{encoded}'
    except Exception:
        # A missing/unavailable upload must not prevent a financial document
        # from being generated; the template falls back to the tenant name.
        pass
    return theme


def credit_assessment_enabled():
    """Master switch for the Credit Assessment module (Statement of Position,
    referee & previous-employer capture)."""
    try:
        s = AdminSettings.objects.filter(settings_name='setting1').first()
        return bool(s and s.credit_assessment_enabled == 'YES')
    except Exception:
        return False


def get_loan_config():
    """Return loan limits/rates from AdminSettings, falling back to settings.py."""
    from decimal import Decimal
    try:
        s = AdminSettings.objects.filter(settings_name='setting1').first()
        if s:
            raw_rate = s.default_interest_rate or settings.DEFAULT_INTEREST_RATE
            interest_type = s.default_interest_type or 'PERCENTAGE'
            return {
                'loan_min_amount': s.loan_min_amount   or settings.LOAN_MIN_AMOUNT,
                'loan_max_amount': s.loan_max_amount   or settings.LOAN_MAX_AMOUNT,
                'increment_amount': s.increment_amount or settings.INCREMENT_AMOUNT,
                'min_fn':           s.min_fn           or settings.MIN_FN,
                'max_fn':           s.max_fn           or settings.MAX_FN,
                'increment_fn':     s.increment_fn     or settings.INCREMENT_FN,
                'default_interest_rate': raw_rate,
                'default_interest_type': interest_type,
                'default_interest_base': getattr(s, 'default_interest_base', 'SHORTFALL') or 'SHORTFALL',
                'auto_default_on_shortfall': getattr(s, 'auto_default_on_shortfall', True),
                'mercy_days': s.default_interest_calculation_mercy_days or settings.DEFAULT_INTEREST_CALCULATION_MERCY_DAYS,
                'auto_classify_default': s.auto_classify_default,
            }
    except Exception:
        pass
    return {
        'loan_min_amount':  settings.LOAN_MIN_AMOUNT,
        'loan_max_amount':  settings.LOAN_MAX_AMOUNT,
        'increment_amount': settings.INCREMENT_AMOUNT,
        'min_fn':           settings.MIN_FN,
        'max_fn':           settings.MAX_FN,
        'increment_fn':     settings.INCREMENT_FN,
        'default_interest_rate': settings.DEFAULT_INTEREST_RATE,
        'default_interest_type': 'PERCENTAGE',
        'default_interest_base': 'SHORTFALL',
        'auto_default_on_shortfall': True,
        'mercy_days': settings.DEFAULT_INTEREST_CALCULATION_MERCY_DAYS,
        'auto_classify_default': False,
    }


def get_effective_max_loan_amount(user):
    """Return the maximum loan amount that applies to ``user``.

    A per-client override (UserProfile.max_loan_amount) takes precedence over the
    system-wide maximum whenever it is set — whether it is lower or higher. When
    no override is set, the global maximum from loan settings applies.
    """
    from decimal import Decimal
    global_max = Decimal(str(get_loan_config()['loan_max_amount']))
    override = getattr(user, 'max_loan_amount', None) if user is not None else None
    if override:
        try:
            return Decimal(str(override))
        except Exception:
            return global_max
    return global_max


def calc_default_interest(rate, interest_type, repayment_amount):
    """Return the default interest kina amount based on type and rate."""
    from decimal import Decimal
    rate = Decimal(str(rate or 0))
    repayment_amount = Decimal(str(repayment_amount or 0))
    if interest_type == 'FIXED':
        return rate
    # PERCENTAGE: rate is entered as %, e.g. 20 = 20%
    return (rate / Decimal('100')) * repayment_amount


def referral_program_enabled():
    """Master switch for the whole referral engine (Referral Settings)."""
    try:
        s = AdminSettings.objects.filter(settings_name='setting1').first()
        return bool(s.referral_enabled) if s else True
    except Exception:
        return True


def get_bank_config():
    """Return company bank info from AdminSettings, falling back to settings.py."""
    try:
        s = AdminSettings.objects.filter(settings_name='setting1').first()
        if s:
            return {
                'bank':          s.bank1         or settings.BANK1,
                'bank_acc_name': s.bank1_acc_name or settings.BANK1_ACC_NAME,
                'bank_acc_num':  s.bank1_acc_num  or settings.BANK1_ACC_NUM,
                'bank_branch':   s.bank1_branch   or settings.BANK1_BRANCH,
                'bank_bsb':      s.bank1_bsb      or getattr(settings, 'BANK1_BSB', ''),
                'swift':         s.swift          or getattr(settings, 'SWIFT', ''),
                # This is tenant-owned data. When the General Settings row
                # exists, even a blank value is authoritative and must never be
                # replaced by another deployment's environment fallback.
                'alesco_dc':     s.alesco_dc      or '',
                'support_email': s.support_email  or s.admin_email_addresses or settings.EMAIL_HOST_USER,
            }
    except Exception:
        pass
    return {
        'bank':          settings.BANK1,
        'bank_acc_name': settings.BANK1_ACC_NAME,
        'bank_acc_num':  settings.BANK1_ACC_NUM,
        'bank_branch':   settings.BANK1_BRANCH,
        'bank_bsb':      getattr(settings, 'BANK1_BSB', ''),
        'swift':         getattr(settings, 'SWIFT', ''),
        'alesco_dc':     settings.ALESCO_DC,
        'support_email': settings.EMAIL_HOST_USER,
    }


class FormFieldSetting(models.Model):
    
    form_name = models.CharField(max_length=100)
    field_name = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    required = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('form_name', 'field_name')
        ordering = ('form_name', 'id')
    
    def __str__(self):
        return f'{self.form_name} - {self.field_name}'

class ProcessingFeeTier(models.Model):
    """Tiered processing fee: loan amounts within [min_amount, max_amount] attract this fee."""
    min_amount = models.DecimalField(verbose_name='Min Loan Amount (K)', max_digits=10, decimal_places=2)
    max_amount = models.DecimalField(verbose_name='Max Loan Amount (K)', max_digits=10, decimal_places=2, null=True, blank=True, help_text='Leave blank for no upper limit.')
    fee = models.DecimalField(verbose_name='Processing Fee (K)', max_digits=8, decimal_places=2)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['min_amount']

    def __str__(self):
        upper = f'K{self.max_amount}' if self.max_amount else '∞'
        return f'K{self.min_amount} – {upper}  →  K{self.fee}'

    @classmethod
    def get_fee_for_amount(cls, amount):
        """Return the applicable processing fee for the given loan amount, or Decimal('0')."""
        from decimal import Decimal
        try:
            amount = Decimal(str(amount))
            for tier in cls.objects.filter(active=True).order_by('min_amount'):
                if amount >= tier.min_amount:
                    if tier.max_amount is None or amount <= tier.max_amount:
                        return tier.fee
        except Exception:
            pass
        return Decimal('0')


class Employer(models.Model):
    
    SECTOR_CHOICES = [
        ('PUBLIC', 'PUBLIC'),
        ('PRIVATE', 'PRIVATE'),
        ('SOE', 'SOE'),
        ('SME', 'SME'),
    ]
    
    ORGANISATION_TYPE_CHOICES = [
        ('DEPARTMENT', 'DEPARTMENT'),
        ('SOE', 'SOE'),
        ('COMPANY', 'COMPANY'),
        ('MSME', 'MSME'),
    ]

    name = models.CharField(max_length=255, unique=True)
    sector = models.CharField(max_length=10, choices=SECTOR_CHOICES, default='PRIVATE', null=True, blank=True)
    organisation_type = models.CharField(max_length=15, choices=ORGANISATION_TYPE_CHOICES, null=True, blank=True)
    office_address = models.TextField(max_length=255, null=True, blank=True)
    payroll_officer_name = models.CharField(verbose_name='Payroll Officer Name', max_length=150, null=True, blank=True)
    work_phone = models.IntegerField(verbose_name='Payroll Officer Phone', null=True, blank=True)
    work_email = models.EmailField(verbose_name='Payroll Officer Email', max_length=50, null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name

class Location(models.Model):
    
    PROVINCE = [('AROB','AROB'),('CENTRAL','CENTRAL'),('ENGA','ENGA'),('EAST SEPIK','EAST SEPIK'),('EHP','EHP'),('ENB','ENBP'),
    ('HELA','HELA'), ('JIWAKA','JIWAKA'),('MADANG','MADANG'),('MANUS','MANUS'),('MILNE BAY','MILNE BAY'), ('MOROBE', 'MOROBE'),('NCD','NCD'),('NEW IRELAND','NEW IRELAND'),('ORO','ORO'),
    ('SHP','SHP'),('SIMBU','SIMBU'), ('WESTERN','WESTERN'), ('WEST SEPIK','WEST SEPIK'), ('WHP','WHP'), ('WNB','WNBP'),
    ]  
    
    name = models.CharField(max_length=255, blank=True, null=True)
    province = models.CharField(max_length=20, choices=PROVINCE)
    address = models.CharField(max_length=255, blank=True, null=True)
    email= models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.IntegerField(null=True, blank=True)
    
    loans = models.IntegerField(null=True, blank=True, default=0)
    loans_in_default = models.IntegerField(null=True, blank=True, default=0)
    
    funded = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    interest = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    repayment = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    arrears = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    outstanding = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    in_recovery = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    
    clients = models.IntegerField(null=True, blank=True, default=0)
    clients_with_loan = models.IntegerField(null=True, blank=True, default=0)
    clients_in_recovery = models.IntegerField(null=True, blank=True, default=0)
    
    def __str__(self):
        return self.name
    
    
