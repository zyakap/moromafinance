import datetime
import random
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.shortcuts import render, redirect
from django.template import Template, Context
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.generic.base import View
from wkhtmltopdf.views import PDFTemplateResponse
from accounts.models import UserProfile, StaffProfile
from loan.models import Loan, LoanFile, Statement, PaymentUploads, Payment
from admin1.models import AdminSettings, get_bank_config, get_document_theme
from .forms import LoanApplicationForm, PaymentUploadForm
from loan.forms import PaymentForm
from .tasks import download_tc
from .tokens import loan_tc_agreement_token

from accounts.functions import login_check, check_staff

from custom.functions import repayment, complete_loan, combination_check

from message.functions import send_email, send_email_toworkemail, email_admin

from .functions import process_advance_payment, process_repayment, process_default

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
import subprocess

User = get_user_model()

try:
    settings1 = AdminSettings.objects.get(settings_name='setting1')
    admin_receiver = settings1.admin_email_addresses
except Exception:
    admin_receiver = settings.ADMIN_RECEIVER
admin_emails = list(admin_receiver.split(','))
test_receiver = settings.TEST_RECEIVER
if test_receiver != '':
    admin_emails.append(test_receiver)

domain = settings.DOMAIN_DNS
domain_full = settings.DOMAIN

from custom.functions import combination_check, fn_limits

def generate_pdf(templatefile, data):
    from moromafinance.pdf import render_pdf
    return render_pdf(templatefile, data, 'custom/templates')


#### GENERAL PAGES #####


class DownloadApplication(View):
    
    template = 'custom/loan_application_gen.html'
    
    def get(self, request, *args, **kwargs):
        
        loan_ref = self.kwargs['loanref']
        ##loan_ref = 'iBX1ZY264'
        loan = Loan.objects.get(ref=loan_ref)
        domain = settings.DOMAIN
        uid = loan.owner_id
        user = UserProfile.objects.get(pk=uid)
        usr = User.objects.get(pk=user.user_id)

        statements = Statement.objects.filter(loanref=loan)
        
        now = datetime.datetime.now()
        today = now.strftime("%d/%m/%Y")
        
        last_name_s = user.last_name[-1]
        
        data = {'loan':loan,
                'user':user,
                'usr': usr,
                'last_name_s':last_name_s,
                'domain': settings.DOMAIN,
                'statements': statements,
                'today':today,
                'bank_config': get_bank_config() }
        
        response = PDFTemplateResponse(
            request=request,
            template = self.template,
            filename = f'{loan.ref}.pdf',
            context = data,
            show_content_in_browser=False,
            cmd_options= {
            
                "zoom":1,
                "viewport-size": "1366 x 513",
                'javascript-delay': 1000,
                'footer-center': '[page]/[topage]',
                "no-stop-slow-scripts": True,
            },
        )
        
        return response

class DownloadStatement(View):

    template = 'custom/client_statement.html'

    def get(self, request, *args, **kwargs):
        loan_ref = self.kwargs['loanref']
        if not request.GET.get('format'):
            return render(request, 'client_document_preview.html', {
                'nav': 'mystatements',
                'doc_title': f'Loan Statement — {loan_ref}',
                'doc_url': request.path,
            })

        loan = Loan.objects.get(ref=loan_ref)
        domain = settings.DOMAIN
        uid = loan.owner_id
        user = UserProfile.objects.get(pk=uid)
        usr = User.objects.get(pk=user.user_id)

        statements = Statement.objects.filter(loanref=loan).order_by('date', 'id')

        now = datetime.datetime.now()
        today = now.strftime("%d %B %Y")

        from loan.functions import statement_summary
        data = {
            'loan': loan,
            'user': user,
            'usr': usr,
            'domain': domain,
            'statements': statements,
            'today': today,
            'bank_config': get_bank_config(),
            'document_theme': get_document_theme(),
        }
        data.update(statement_summary(loan, statements))

        from moromafinance.pdf import django_pdf_response
        return django_pdf_response(
            request, self.template, data, f'Statement_{loan.ref}.pdf',
            inline=(request.GET.get('inline') == '1'),
        )


@login_check
def download_las_user(request, loanref):
    """Preview/download the Loan Amortization Schedule (user-facing)."""
    if not request.GET.get('format'):
        return render(request, 'client_document_preview.html', {
            'nav': 'myloans',
            'doc_title': f'Loan Amortization Schedule — {loanref}',
            'doc_url': request.path,
        })

    from admin1.mainView import _build_las_context
    loan = Loan.objects.get(ref=loanref)
    user = UserProfile.objects.get(id=loan.owner_id)
    context = _build_las_context(loan, user, settings.DOMAIN)
    from moromafinance.pdf import django_pdf_response
    return django_pdf_response(
        request, 'custom/loan_amortization_schedule.html', context,
        f'LAS_{loanref}.pdf', inline=(request.GET.get('inline') == '1'),
    )




@login_check
def loan_requirements(request):

    user = UserProfile.objects.get(user_id=request.user.id)
    now = datetime.date.today()

    
    dob = user.date_of_birth
    start = user.start_date
    
    if dob:
        age = round(((now.month - dob.month + (12 * (now.year - dob.year)))/12),2)
    else:
        age = None
    
    if start:
        yef = round(((now.month - start.month + (12 * (now.year - start.year)))/12),2)
    else:
        yef = None

    from django.db.models import Q
    # Combine the two queries into one
    combined_query = Q(owner=user.id) & Q(category='PENDING') & (Q(status='AWAITING T&C') | Q(status='UNDER REVIEW'))
    # Retrieve loans matching the combined query
    combined_loans = Loan.objects.filter(combined_query)
    # Now combined_loans contains loans that satisfy both conditions
    
    if combined_loans:
        try:
            loan = Loan.objects.get(combined_query)
            loanfile = LoanFile.objects.get(loan=loan)
            return render(request, 'loan_requirements.html', {'nav': 'loan_requirements', 'user':user, 'age':age, 'yef':yef, 'loanfile': loanfile })
        except Exception:
            pass

    if user.account_requirements_check == 'INCOMPLETE':
        if yef is not None and yef > 0.9 and user.terms_consent == 'YES' and user.credit_consent == 'YES' and (user.passport_url or user.nid_url) and user.job_title and user.gross_pay > 0 and age is not None and age < 60:
            user.account_requirements_check = 'COMPLETED'
            user.save()
    
    return render(request, 'loan_requirements.html', {'nav': 'loan_requirements', 'user':user, 'age':age, 'yef':yef})

#########################
#LOAN APPLICATION
#########################
@login_check
def loan_application(request):
    owner = UserProfile.objects.get(user_id=request.user.id)

    # ── Existing Loan Guard (always enforced, regardless of MULTIPLE_LOANS) ──
    _active_funded = Loan.objects.filter(
        owner=owner, category='FUNDED',
        funded_category__in=['ACTIVE', 'RECOVERY', 'BAD', 'WOFF'],
    )
    _active_pending = Loan.objects.filter(
        owner=owner, category='PENDING',
    ).exclude(status__in=['REJECTED', 'CANCELLED'])
    if _active_funded.exists() or _active_pending.exists():
        return render(request, 'loan_exists.html', {
            'active_funded': _active_funded,
            'active_pending': _active_pending,
        })
    # ── End Existing Loan Guard ───────────────────────────────────────────────

    try:
        loan_setting = AdminSettings.objects.get(settings_name='setting1')
    except Exception: 
        messages.error(request, f"Loan Administrator needs to update their settings first. Please contact support@{domain}", extra_tags="danger")
        return redirect('dashboard')
    
    usr = request.user
    uid = usr.id
    loanref_prefix = loan_setting.loanref_prefix
    user = UserProfile.objects.get(user_id=uid)
    upid = user.id
    
    if user.first_name is None or user.first_name == '':
        messages.error(request, f"You need to update your profile with your First Name and Last Name.", extra_tags="warning")
        return redirect('profile')
    if user.last_name is None or user.last_name == '':
        messages.error(request, f"You need to update your profile with your First Name and Last Name.", extra_tags="warning")
        return redirect('profile')
    
    first_name = user.first_name
    last_name = user.last_name
    rand = random.randint(0,9)
    refx = f'{loanref_prefix}{upid}{first_name[0]}{last_name[0]}{rand}'
    repayment_limit = user.repayment_limit
    
    if request.method == 'POST':
        form = LoanApplicationForm(request.POST, user_profile=user)
        if form.is_valid():
            
            if loan_setting.credit_check == 'YES':
                if not usr.active:
                    return redirect('inactive')
                if usr.defaulted:
                    return redirect('defaulted')
                if usr.suspended:
                    return redirect('suspended')
                if usr.dcc_flagged:
                    return redirect('dcc_flagged')
                if usr.cdb_flagged:
                    return redirect('cdb_flagged')
                _thr = loan_setting.approval_credit_threshold
                if _thr is not None and user.credit_rating is not None and user.credit_rating < _thr:
                    messages.error(request, 'Your credit rating does not currently meet the approval threshold. Please contact us for assistance.', extra_tags='danger')
                    return redirect('loan_application')

                # DCC benchmark score automation (Settings -> DCC): fetch the
                # bureau's cross-lender score, optionally auto-scale this
                # client's limits from it, and decline below the minimum.
                # Fails open when the bureau is unreachable or has no record.
                if loan_setting.dcc_autocredit_enabled == 'YES':
                    from dcc.functions import dcc_enabled as _dcc_on, refresh_dcc_score
                    if _dcc_on():
                        _score = refresh_dcc_score(user)
                        if _score is not None:
                            if loan_setting.dcc_autoset_limits == 'YES':
                                from decimal import Decimal as _DD
                                _factor = _DD(_score) / _DD(1000)
                                _changed = []
                                if loan_setting.dcc_limit_max_repayment:
                                    user.repayment_limit = (loan_setting.dcc_limit_max_repayment * _factor).quantize(_DD('0.01'))
                                    _changed.append('repayment_limit')
                                if loan_setting.dcc_limit_max_ceiling:
                                    user.max_loan_amount = (loan_setting.dcc_limit_max_ceiling * _factor).quantize(_DD('0.01'))
                                    _changed.append('max_loan_amount')
                                if _changed:
                                    user.save(update_fields=_changed)
                            if _score < (loan_setting.dcc_min_score or 0):
                                messages.error(request, 'Your application cannot proceed at this time based on your credit bureau assessment. Please contact us for assistance.', extra_tags='danger')
                                return redirect('loan_application')
            
            try:
                from admin1.models import AdminSettings as _AS
                _cs = _AS.objects.get(settings_name='setting1')
                _repayment_limit_check_enabled = _cs.repayment_limit_check_enabled
                _bypass_activation_check = _cs.bypass_activation_check
                _minimum_repayment_limit = _cs.minimum_repayment_limit or 0
            except Exception:
                _repayment_limit_check_enabled = True
                _bypass_activation_check = False
                _minimum_repayment_limit = 0

            if _repayment_limit_check_enabled:
                if user.repayment_limit == 0:
                    messages.error(request, "Your repayment limit is not set. Please contact us by creating a support ticket", extra_tags="danger")
                    return redirect('loan_application')
                if _minimum_repayment_limit and user.repayment_limit < _minimum_repayment_limit:
                    messages.error(request, f"Your repayment limit of K{user.repayment_limit} is below the minimum required of K{_minimum_repayment_limit}. Please contact us.", extra_tags="danger")
                    return redirect('loan_application')
            if not _bypass_activation_check:
                if user.activation == 0:
                    messages.error(request, "Your account is not activated. Please contact us by creating a support ticket", extra_tags="danger")
                    return redirect('loan_application')

            #loan reference
            loan = Loan.objects.create(ref = refx)
            loanfile = LoanFile.objects.create(loan=loan)
            loanfile.save()
            loan_id = loan.id
            str_loan_id = str(loan_id)
            finalref_first_part = refx[:-1]
            final_ref = f'{finalref_first_part}{str_loan_id}'
            loan.ref = final_ref
            loan.save()

            loan.owner_id = upid
            #loan.type = form.cleaned_data['type']
            loan.amount = form.cleaned_data['amount']
            loan.purpose_of_loan = form.cleaned_data.get('purpose_of_loan', '')

            #amount limit check
            _lc = get_loan_config()
            _effective_max = user.max_loan_amount if user.max_loan_amount else _lc["loan_max_amount"]
            if loan.amount < _lc["loan_min_amount"]:
                loan.delete()
                messages.error(request, f'Loan amount must be more than K{_lc["loan_min_amount"]}', extra_tags='danger')
                return redirect('loan_application')
            elif loan.amount > _effective_max:
                loan.delete()
                messages.error(request, f'Loan amount must be less than K{_effective_max}', extra_tags='danger')
                return redirect('loan_application')

            num_fns = form.cleaned_data['number_of_fortnights']

            #COMBINATIONS CHECK — skipped for Open Repayment (custom amounts outside table)
            if form.loan_mode != 'OPEN_REPAYMENT':
                max_fn = combination_check(loan.amount, num_fns)
                if max_fn != 0:
                    loan.delete()
                    messages.error(request, f"Number of fortnights must be between {get_loan_config()['min_fn']} and {max_fn} for an amount of K{loan.amount:,.2f}. Please refer to the repayment table below. Click on 'Show Repayment Table'.", extra_tags='danger')
                    return redirect('loan_application')
            #COMBINATIONS CHECK _END

            if fn_limits(num_fns) != 1:
                loan.delete()
                cfg = get_loan_config()
                messages.error(request, f"Number of fortnights must be between {cfg['min_fn']} and {cfg['max_fn']}.", extra_tags='danger')
                return redirect('loan_application')
            
            loan.number_of_fortnights = num_fns
            start_of_payment = form.cleaned_data['repayment_start_date']
            now = datetime.date.today()
            after_fourteen_days = now + datetime.timedelta(days=14)
            
            if start_of_payment < now:
                loan.delete()
                messages.error(request, "The Start Date can not be in past. The date must be from now and 14 days.", extra_tags='danger')
                return redirect('loan_application')
            
            if start_of_payment > after_fourteen_days:
                loan.delete()
                messages.error(request, "The Start Date can not be after 14 days from now. The date must be between now and 14 days.", extra_tags='danger')
                return redirect('loan_application')
            
            loan.repayment_start_date = start_of_payment
            loan.save()
            
            #calculating_interest
            selected_fns = loan.number_of_fortnights
            amt = float(loan.amount)

            if settings.SYSTEM_TYPE == 'ONE_LOAN_PER_CLIENT':
                
                try:
                #check for existing running loan 
                    running_loan = Loan.objects.filter(owner=owner, category="FUNDED", funded_category__in=["ACTIVE", "DEFAULTED"]).last()
                    if running_loan.total_outstanding > settings.LOAN_COMPLETION_BALANCE:
                        return redirect('propose_new_arrangement', running_loan_id=running_loan.id, new_loan_id=loan.id)
                    else:
                        #need to check
                        complete_loan(request, running_loan) 
                except Exception:
                    pass
                    
            interest_type = settings.INTEREST_TYPE
            fortnightly_repayment = repayment(amt, interest_type, selected_fns)
            total_to_be_paid = fortnightly_repayment * selected_fns
            interest_to_be_paid = total_to_be_paid - amt
            
            rounded_interest = round(interest_to_be_paid,2)
            rounded_repayment_amount = round(fortnightly_repayment,2)     
            rounded_total_to_be_paid = round(total_to_be_paid, 2)
            
            try:
                from admin1.models import AdminSettings as _AS2
                _cs2 = _AS2.objects.get(settings_name='setting1')
                _rl_check = _cs2.repayment_limit_check_enabled
            except Exception:
                _rl_check = True

            if _rl_check:
                if repayment_limit == 0:
                    loan.delete()
                    messages.error(request, 'Your repayment Limit is not set yet. Please make sure your payslip is uploaded.', extra_tags="danger")
                    return redirect('dashboard')

                if fortnightly_repayment > repayment_limit:
                    loan.delete()
                    messages.error(request, f'The repayment amount of K{rounded_repayment_amount} for this loan is greater than your personal repayment limit of K{repayment_limit}. Please apply again within your repayment limit.', extra_tags='danger')
                    return redirect('loan_application')

            loan.interest = rounded_interest
            loan.repayment_frequency = 'FORTNIGHLTY'
            loan.category = 'PENDING'
            loan.status = 'AWAITING T&C'
            loan.location = owner.location
            loan.repayment_amount = rounded_repayment_amount
            loan.total_loan_amount = rounded_total_to_be_paid

            # Record the applicable processing fee tier at application time (if enabled)
            try:
                from admin1.models import ProcessingFeeTier as _PFT, AdminSettings as _ASet
                _fee_on = getattr(_ASet.objects.get(settings_name='setting1'), 'processing_fee', 'NO') == 'YES'
                loan.processing_fee = _PFT.get_fee_for_amount(loan.amount) if _fee_on else 0
            except Exception:
                loan.processing_fee = 0

            if settings.LOAN_TYPES != 1:
                messages.error(request, 'Administrator needs to enable loan type on application forms first. Please raise a support ticket for this.', extra_tags="danger")
                return redirect('loan_application')
            else:
                loan.type = 'PERSONAL'
            
            # DCC IDENTIFIERS
            loan.uid = user.uid
            loan.luid = settings.LUID
            loan.save()
        
            messages.success(request, "Loan application sent successfully. Please check your email to complete the loan application process...")

            # Build the prefilled application documents email honouring admin
            # Loan Settings (enable/disable, recipients, which documents).
            from .functions import build_application_documents_email
            email = build_application_documents_email(
                loan, user, usr, loan_setting,
                uid=urlsafe_base64_encode(force_bytes(usr.pk)),
                token=loan_tc_agreement_token.make_token(usr),
            )

            #clear existing loans that were not agreed to
            loans = Loan.objects.filter(owner=owner, tc_agreement='tct')

            for loanx in loans:
                loanx.delete()

            if email is None:
                # Sending is disabled (or no recipient/document selected) — the
                # application is still recorded; documents just aren't emailed.
                loan.tc_agreement = 'tct'
                loan.save()
                messages.success(request, "Your loan application has been recorded.", extra_tags='info')
                return redirect('dashboard')

            try:
                email.send()
                loan.tc_agreement = 'tct'
                loan.save()
                messages.success(request, "The Terms & Conditions have been emailed to you, Please read, sign if you agree and upload in your requirements section.", extra_tags='info')
            except Exception:
                messages.error(request, "The Terms & Conditions Agreement email could not be sent, make sure you have internet connection and try apply again.", extra_tags='danger')
                loan.delete()
                return redirect('loan_application')

            return redirect('dashboard')
    else:
        form = LoanApplicationForm(user_profile=user)

    # Pass processing fee tiers as JSON for dynamic display in the calculator
    import json as _json
    try:
        from admin1.models import ProcessingFeeTier as _PFT
        fee_tiers = [
            {'min': float(t.min_amount), 'max': float(t.max_amount) if t.max_amount else None, 'fee': float(t.fee)}
            for t in _PFT.objects.filter(active=True).order_by('min_amount')
        ]
    except Exception:
        fee_tiers = []

    from admin1.models import get_loan_config, get_effective_max_loan_amount
    loan_config = get_loan_config()
    effective_max_amount = get_effective_max_loan_amount(user)

    return render(request, 'loan_application_form.html', {
        'nav': 'loan_application',
        'form': form,
        'repayment_limit': repayment_limit,
        'user': user,
        'loan_config': loan_config,
        'effective_max_amount': effective_max_amount,
        'fee_tiers_json': _json.dumps(fee_tiers),
    })


##############
##  CHECK CREDIT HISTORY
##############

def inactive(request):
    messages.error(request, 'Your account is inactive.', extra_tags='danger')
    return render(request, 'inactive.html' )

def defaulted(request):
    messages.error(request, 'Your account is suspended.', extra_tags='danger')
    return render(request, 'defaulted.html')

def suspended(request):
    messages.error(request, 'Your account is suspended.', extra_tags='danger')
    return render(request, 'suspended.html')

def dcc_flagged(request):
    messages.error(request, 'Your account is flagged in DCC.', extra_tags='danger')
    return render(request, 'dcc_flagged.html')

def cdb_flagged(request):
    messages.error(request, 'Your account is flagged in CDB.', extra_tags='danger')
    return render(request, 'cdb_flagged.html')


######################
#### TERMS & CONDTIONS 
#######################


def agree_to_tc(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and loan_tc_agreement_token.check_token(user,token):
        upid = UserProfile.objects.get(user_id=uid).id
        
        try:
            loan = Loan.objects.filter(owner_id=upid, tc_agreement='tct').get()
        except Exception:
            messages.error(request, 'This loan does not exist, Please apply again.', extra_tags="danger")
            return redirect('loan_application')
        
        return redirect('myloans')
    else:
        return render(request, 'loan_expired.html')    
    

@login_check
def cancel_loan(request, loan_ref):

    loan = Loan.objects.get(ref=loan_ref)
    
    if loan.category == 'APPROVED':
        messages.error(request, 'This loan can not be cancelled because it is already approved.', extra_tags='danger')
        return redirect('myloans')
    elif loan.category == 'RUNNING':
        messages.error(request, 'This loan can not be cancelled because it is a running loan.', extra_tags='danger')
        return redirect('myloans')
    else:
        messages.success(request, f'Loan - { loan.ref} has been cancelled.')
        loan.delete()
    
    return redirect('myloans')


    ### LOAN FUNCTIONS ###


@login_check
def myloans(request):

    user = request.user
    user_profile = UserProfile.objects.get(user_id=user.id)
    
    all_loans = Loan.objects.filter(owner_id=user_profile.id).exclude(funded_category='COMPLETED')
    completed_loans = Loan.objects.filter(owner_id=user_profile.id, funded_category="COMPLETED")
    bad_loans = Loan.objects.filter(owner_id=user_profile.id, funded_category="BAD")
    
    statements = Statement.objects.filter(owner_id=user_profile.id).order_by('-date')[:5]
    
    return render(request, 'my_loans.html', { 'nav':'myloans','all_loans': all_loans , 'completed_loans':completed_loans,'bad_loans':bad_loans, 'statements': statements, 'domain': domain_full, 'user': user_profile })

@login_check
def viewmyloan(request, loan_ref):

    loan = Loan.objects.get(ref=loan_ref)
    loanfile = LoanFile.objects.get(loan=loan)
    
    uid = loan.owner.id
    user = UserProfile.objects.get(pk=uid)
    usr = User.objects.get(pk=user.user_id)
    usr_email = usr.email
    
    last_name_s = user.last_name[-1]
    
    stat = Statement.objects.filter(loanref=loan)
    
    if request.method=='POST':
        
        if request.POST.get('subject') and request.POST.get('messageofficer'):

            if loan.officer:
                officer_email = loan.officer.email
            else:
                officer_email = f'support@{domain}'
    
            subject = request.POST.get('subject')
            ''' if header_cta == 'yes' '''
            cta_label = ''
            cta_link = ''

            greeting = 'Hi'
            message = f'Message from website regarding: {loan_ref}'
            message_details = request.POST.get('messageofficer')

            ''' if cta == 'yes' '''
            cta_btn1_label = 'Login into Dashboard'
            cta_btn1_link = f'{settings.DOMAIN}/dashboard/'
            cta_btn2_label = ''
            cta_btn2_link = ''

            ''' if promo == 'yes' '''
            catchphrase = ''
            promo_title = ''
            promo_message = ''
            promo_cta = ''
            promo_cta_link = ''
            
            email_content = render_to_string('custom/email_temp_general.html', {
                'header_cta': 'no',
                'cta': 'no',
                'cta_btn2': 'no',
                'promo': 'no',
                'cta_link': cta_link,
                'cta_label': cta_label,
                'subject': subject,
                'greeting': greeting,
                'message': message,
                'message_details': message_details,
                'cta_btn1_link': cta_btn1_link,
                'cta_btn1_label': cta_btn1_label,
                'cta_btn2_link': cta_btn2_link,
                'cta_btn2_label': cta_btn2_label,
                'catchphrase': catchphrase,
                'promo_title': promo_title,
                'promo_message': promo_message,
                'promo_cta_link': promo_cta_link,
                'promo_cta': promo_cta,
                'user': user,
                'domain': domain,
                
            })
            
            text_content = strip_tags(email_content)
            email = EmailMultiAlternatives(subject,text_content,usr_email,['dev@webmasta.com.pg', officer_email ])
            email.attach_alternative(email_content, "text/html")

            try: 
                email.send()
                messages.success(request, "Message has been forwarded successfully")
                return redirect('pending_loans')
            except Exception:
                messages.error(request, 'Message has not been sent.', extra_tags='danger')
                
            return redirect('view_loan', loan_ref)
        
        else:
            messages.error(request, 'Message has not been sent.', extra_tags='info')
        
    return render(request, 'viewmyloan.html', {'domain': domain_full, 'nav':'myloans','loan':loan, 'user':user, 'usr': usr, 'last_name_s':last_name_s , 'stat': stat, 'loanfile': loanfile })

@login_check
def mystatements(request):

    uid = request.user.id
    user = UserProfile.objects.get(user_id=uid)

    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loanref') and request.POST.get('stattype'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            ref = request.POST.get('loanref')
            stattype = request.POST.get('stattype')

            start_date = start_date_entry 
            end_date = end_date_entry
            loan_ref = ref

            loan = Loan.objects.get(ref=loan_ref) 

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('mystatements')

            statements = Statement.objects.prefetch_related('loanref','owner').filter(owner_id=user.id, type = stattype, loanref = loan, date__gte=start_date, date__lte=end_date).all()
            loans = Loan.objects.filter(owner_id=user.id, category='APPROVED')
            return render(request, 'mystatements.html', { 'nav':'mystatements','user': user, 'statements': statements,'loans': loans})
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loanref'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            ref = request.POST.get('loanref')

            start_date = start_date_entry 
            end_date = end_date_entry
            loan_ref = ref

            loan = Loan.objects.get(ref=loan_ref)

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('mystatements')

            statements = Statement.objects.prefetch_related('loanref','owner').filter(owner_id=user.id, loanref = loan, date__gte=start_date, date__lte=end_date).all()
            loans = Loan.objects.filter(owner_id=user.id, category='APPROVED')
            return render(request, 'mystatements.html', { 'nav':'mystatements','user': user, 'statements': statements,'loans': loans})
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('stattype'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            stattype = request.POST.get('stattype')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('mystatements')

            statements = Statement.objects.prefetch_related('loanref','owner').filter(owner_id=user.id, type = stattype, date__gte=start_date, date__lte=end_date).all()
            loans = Loan.objects.filter(owner_id=user.id, category='APPROVED')
            return render(request, 'mystatements.html', { 'nav':'mystatements','user': user, 'statements': statements,'loans': loans})
        
        elif request.POST.get('startdate') and request.POST.get('enddate'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            
            start_date = start_date_entry
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('mystatements')

            statements = Statement.objects.prefetch_related('loanref','owner').filter(owner_id=user.id, date__gte=start_date, date__lte=end_date).all()
            loans = Loan.objects.filter(owner_id=user.id, category='APPROVED')
            
            return render(request, 'mystatements.html', { 'nav':'mystatements','user': user, 'statements': statements,'loans': loans})
        
        elif request.POST.get('loanref') and request.POST.get('stattype'): 
            ref = request.POST.get('loanref')
            stattype = request.POST.get('stattype')
                
            if stattype == 'OTHER':
                statements = Statement.objects.prefetch_related('loanref','owner').filter(owner_id=user.id,loanref = loan).exclude(type = 'PAYMENT').exclude(type='DEFAULT') 
            else:
                statements = Statement.objects.prefetch_related('loanref','owner').filter(owner_id=user.id, loanref = loan, type = stattype).all()
            loans = Loan.objects.filter(owner_id=user.id, category='APPROVED')
            return render(request, 'mystatements.html', { 'nav':'mystatements','user': user, 'statements': statements,'loans': loans})

        elif request.POST.get('loanref'): 
            ref = request.POST.get('loanref')
            loan = Loan.objects.get(ref=ref)
            statements = Statement.objects.prefetch_related('loanref','owner').filter(owner_id=user.id, loanref = loan).all()
            loans = Loan.objects.filter(owner_id=user.id, category='APPROVED')
            return render(request, 'mystatements.html', { 'nav':'mystatements','user': user, 'statements': statements,'loans': loans})

        elif request.POST.get('stattype'): 
            stattype = request.POST.get('stattype')
            
            if stattype == 'OTHER':
                statements = Statement.objects.prefetch_related('loanref','owner').filter(owner_id=user.id).exclude(type = 'PAYMENT').exclude(type='DEFAULT') 
            else:
                statements = Statement.objects.prefetch_related('loanref','owner').filter(owner_id=user.id, type = stattype).all()
                
            loans = Loan.objects.filter(owner_id=user.id, category='APPROVED')
            return render(request, 'mystatements.html', { 'nav':'mystatements','user': user, 'statements': statements,'loans': loans})

        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('mystatements')

    statements = Statement.objects.prefetch_related('owner','loanref').filter(owner_id=user.id)
    loans = Loan.objects.filter(owner_id=user.id, category='APPROVED')
    return render(request, 'mystatements.html', { 'nav':'mystatements','user': user, 'statements': statements,'loans': loans})

@login_check
def upload_payment(request, loan_ref):
    
    loan = Loan.objects.get(ref=loan_ref)
    
    uid = request.user.id
    user = UserProfile.objects.get(user_id=uid)
    
    if request.method == 'POST':
        uploadform = PaymentUploadForm(request.POST)
        
        if uploadform.is_valid():
    
            if 'payment_proof' in request.FILES:
                date_today = datetime.date.today()
                date_ref = date_today.strftime("%d%m%y")
                payment_upload_ref = f'PU{date_ref}{loan_ref}'
                paymentupload = PaymentUploads.objects.create(ref=payment_upload_ref, owner=user, loan=loan)
                paymentupload.save()

                updated_upload_ref = f'{payment_upload_ref}i{paymentupload.id}'

                payment_proof = request.FILES['payment_proof']
                fspayment_proof = FileSystemStorage()
                newpayment_proof_name = f'{user.first_name}_{user.last_name}_PAYMENT_UPLOAD_{updated_upload_ref}_{payment_proof.name}'
                payment_proof_filename = fspayment_proof.save(newpayment_proof_name, payment_proof)
                payment_url = fspayment_proof.url(payment_proof_filename)
                
                type = uploadform.cleaned_data.get('type')

                paymentupload.file_name=payment_proof_filename
                paymentupload.payment_proof_url=payment_url 
                paymentupload.status='UPLOADED' 
                paymentupload.type=type
                paymentupload.ref = updated_upload_ref
                paymentupload.save()

                messages.success(request, 'Payment Uploaded Successfully...')
                
                #### SEND EMAIL TO ADMIN
                
                subject = f'PAYMENT UPLOADED for {loan_ref}'
                ''' if header_cta == 'yes' '''

                greeting = 'Hello'
                message = f'I just uploaded a payment for my loan - {loan_ref}'
                message_details = 'Please check and update my loan balance accordingly.'

                ''' if cta == 'yes' '''
                cta_btn1_label = 'View Upload'
                cta_btn1_link = f'{settings.DOMAIN}{payment_url}'
                cta_btn2_label = 'Register Payment'
                cta_btn2_link = f'{settings.DOMAIN}/loan/payment/{loan_ref}/'

                email_content = render_to_string('custom/email_temp_general.html', {
                
                    'cta': 'yes',
                    'cta_btn2': 'yes',
                    'subject': subject,
                    'greeting': greeting,
                    'message': message,
                    'message_details': message_details,
                    'cta_btn1_link': cta_btn1_link,
                    'cta_btn1_label': cta_btn1_label,
                    'cta_btn2_link': cta_btn2_link,
                    'cta_btn2_label': cta_btn2_label,
                    'user': user,
                    'domain': domain,  
                })
                text_content = strip_tags(email_content)
                email = EmailMultiAlternatives(subject, text_content, user.email, admin_emails)
                email.attach_alternative(email_content, "text/html")

                try: 
                    email.send()
                    messages.success(request, "Loan Administrator has been notified.")
                except Exception:
                    messages.error(request, 'Admin notification send failed, make sure you are connected to the internet.', extra_tags='danger')
                    
                return redirect('myloans')
   
    else:
        uploadform = PaymentUploadForm()
    return render(request, 'upload_payments.html', { 'nav':'myloans','form': uploadform, 'loan':loan})   

@login_check
def staff_enter_payment(request):
    
    loans = Loan.objects.filter(category='FUNDED').exclude(funded_category='COMPLETED').exclude(funded_category='WOFF')
    return render(request, 'staff_enter_payment.html', { 'nav': 'userstatements', 'loans':loans, 'domain': domain_full })
                  
@check_staff
def payment(request, loan_ref):

    loan = Loan.objects.get(ref=loan_ref)
    loid = loan.owner.id
    
    user = UserProfile.objects.get(pk=loid)
    staffprofile = UserProfile.objects.get(user=request.user.id)
    officer = StaffProfile.objects.get(user=staffprofile)
    
    # Determine default description from admin settings
    try:
        from admin1.models import AdminSettings as _AS
        _default_desc = _AS.objects.get(settings_name='setting1').default_payment_description or 'Fortnightly Salary Deduction'
    except Exception:
        _default_desc = 'Fortnightly Salary Deduction'

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():

            ref = loan
            date = form.cleaned_data['date']
            amount = form.cleaned_data['amount']
            mode = form.cleaned_data['mode']
            # Use default description when field is empty or not present (disabled)
            statement = form.cleaned_data.get('statement') or _default_desc

            # ---- Double-entry guard ----------------------------------------
            # No loan can legitimately be paid the exact same amount on the exact
            # same date twice. Detect that (and the "different amount, same date"
            # case which is likely an additional payment) and make the user
            # explicitly confirm before recording, unless they already have.
            confirm = request.POST.get('confirm', '')
            same_date_qs = Payment.objects.filter(loanref=ref, date=date).order_by('-created_at')
            is_duplicate = same_date_qs.filter(amount=amount).exists()
            is_additional = (not is_duplicate) and same_date_qs.exists()

            if confirm not in ('duplicate', 'additional') and (is_duplicate or is_additional):
                # Re-post the EXACT raw inputs as hidden fields so the form
                # re-validates identically on confirm (avoids date-format issues).
                post_items = {k: v for k, v in request.POST.items()
                              if k not in ('csrfmiddlewaretoken', 'confirm')}
                return render(request, 'payment_confirm.html', {
                    'loan': loan,
                    'loan_ref': loan_ref,
                    'conflict': 'duplicate' if is_duplicate else 'additional',
                    'existing_payments': same_date_qs,
                    'new_amount': amount,
                    'new_date': date,
                    'new_mode': mode,
                    'new_statement': statement,
                    'post_items': post_items,
                    'confirm_value': 'duplicate' if is_duplicate else 'additional',
                })

            payment = Payment.objects.create(owner=user, loanref=ref, date=date, amount=amount, mode=mode, statement=statement, officer=officer)
            stat = Statement.objects.create(owner=user, loanref=ref, date=date, debit=amount, statement=statement, uid=user.uid, luid=settings.LUID)
            
            num_payments = loan.number_of_repayments
            
            p_count = num_payments + 1
            payment.ref = f'{loan_ref}P{p_count}'
            payment.p_count = p_count
            payment.save()
            
            stat.s_count += 1
            stat.ref = f'{loan_ref}SP{stat.s_count}' 
            stat.save()
            
            ramount = loan.repayment_amount
            
            tol_pos = settings.TOTAL_ALLOWABLE_TOEAS
            tol_neg = -settings.TOTAL_ALLOWABLE_TOEAS
            
            tol_neg_amount = ramount + tol_neg
            tol_pos_amount = ramount + tol_pos

            loan.save()
            stat.save()

            # A payment made BEFORE the next due date (with no arrears) is an
            # ADVANCE payment regardless of its size: paid early = paid in
            # advance. At/above the scheduled amount it settles the fortnight
            # early (advance counters + any surplus held as credit); below it,
            # the whole amount is held as advance credit — it must NOT trigger
            # a shortfall default, nothing was due yet.
            from loan import schedule as _sched_v
            from loan.engine import record_advance as _record_advance
            _next_due = _sched_v.next_due_date(loan)
            _early = (_next_due is not None and stat.date < _next_due
                      and (loan.total_arrears or 0) <= 0)

            if _early and amount >= tol_neg_amount:
                payment.type = 'ADVANCE PAYMENT'
                payment.save()
                process_advance_payment(request, loan, stat, amount)
            elif _early:
                payment.type = 'ADVANCE PAYMENT'
                payment.save()
                stat.type = 'PAYMENT'
                stat.balance = loan.total_outstanding
                stat.save()
                _record_advance(loan, amount, stat.date, loan.owner)
                loan.save()
                messages.success(request, f'Early payment of K{amount} held as advance credit '
                                          '(nothing was due yet — it will cover the next fortnight).',
                                 extra_tags='info')
            elif amount < tol_neg_amount:
                # Short payment: the shortfall against the scheduled repayment is
                # recorded as arrears and default interest is charged on it.
                payment.type = 'PARTIAL PAYMENT'
                payment.save()
                process_default(request, loan, stat, amount)
            elif amount>tol_pos_amount:
                payment.type = 'ADVANCE PAYMENT'
                payment.save()
                process_advance_payment(request, loan, stat, amount)
            else:
                payment.type = 'NORMAL REPAYMENT'
                payment.save()
                process_repayment(request, loan, stat, amount)

        else:
            messages.error(request, 'Payment not entered. Please check the form and try again.', extra_tags='danger')
        return redirect('staff_enter_payment')
            
    else:
        form = PaymentForm(initial={
            'date': datetime.date.today(),
            'amount': loan.repayment_amount,
            'mode': 'PAYROLL DEDUCTION',
        })

    return render(request, 'payment.html', {'loan_ref': loan_ref, 'form': form, 'loan': loan})


from django.db import transaction as _db_transaction


@check_staff
@_db_transaction.atomic
def allocate_advance_to_arrears(request, loan_ref):
    """Allocate a client's prepaid advance balance against their outstanding
    arrears to clear (or reduce) the arrears.

    Used when a client overpaid in a later pay (creating an advance balance) while
    an earlier missed/short payment left arrears outstanding — the advance is
    applied to settle the arrears. A statement line records the allocation.
    """
    loan = Loan.objects.select_for_update().get(ref=loan_ref)
    _back = request.META.get('HTTP_REFERER') or f"{settings.DOMAIN}/loan/myloan/{loan.ref}/"

    advance = loan.advance_balance or Decimal('0')
    arrears = loan.total_arrears or Decimal('0')
    allocate = min(advance, arrears)

    if allocate <= 0:
        messages.warning(
            request,
            'Nothing to allocate — the client needs both an advance balance and outstanding arrears.',
            extra_tags='warning',
        )
        return redirect(_back)

    loan.advance_balance = advance - allocate
    loan.total_arrears = arrears - allocate
    if loan.total_arrears <= 0 and loan.status == 'DEFAULTED':
        loan.status = 'RUNNING'
    loan.save()

    user = loan.owner
    s_count = Statement.objects.filter(loanref=loan).count() + 1
    Statement.objects.create(
        owner=user, loanref=loan, uid=getattr(user, 'uid', None), luid=settings.LUID,
        date=datetime.date.today(), type='OTHER',
        statement=f'Advance Payment Allocation to Arrears (K{allocate:.2f})',
        arrears=loan.total_arrears, balance=loan.total_outstanding,
        ref=f'{loan.ref}SAL{s_count}',
    )

    messages.success(
        request,
        f'Allocated K{allocate:.2f} from the advance balance to arrears. '
        f'Remaining arrears: K{loan.total_arrears:.2f}; remaining advance balance: K{loan.advance_balance:.2f}.',
        extra_tags='info',
    )
    return redirect(_back)


##### NEW FUNCTIONS

def repayment_week(request):
    
    import datetime

    date = datetime.date.today()
    weekday = date.weekday()

    if weekday <= 2:

        if weekday == 0:
            day_1 = date
            day_2 = date + datetime.timedelta(days=1)
            day_3 = date + datetime.timedelta(days=2)

        if weekday == 1:
            day_1 = date - datetime.timedelta(days=1)
            day_2 = date 
            day_3 = date + datetime.timedelta(days=1)

        if weekday == 2:
            day_1 = date - datetime.timedelta(days=2)
            day_2 = date - datetime.timedelta(days=1)
            day_3 = date 
        

        loans = Loan.objects.filter(next_payment_date__gte=day_1, next_payment_date__lte=day_3)

    loans = Loan.objects.filter(next_payment_date=date)
    
        

    return render(request, 'repayment_week.html', {'loans':loans})
