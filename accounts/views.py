import datetime
import random
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash, get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.core.files.storage import FileSystemStorage
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db import ProgrammingError
from django.db.models import Q
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from .forms import (
    ContactInfoForm, RegisterForm, LoginForm, PersonalInfoForm, AddressInfoForm, UserUploadForm, BankAccountInfoForm, BankAccountInfo2Form,
    EmployerInfoUpdateForm, JobInfoUpdateForm, PasswordResetForm, SMEProfileForm, SMEUploadsForm, SMEBankInfoForm,
    RefereeInfoForm, PreviousEmployerInfoForm, StatementOfPositionForm,
)
from loan.forms import RequiredUploadForm, WorkUploadForm, LoanStatementUploadForm
from .models import UserProfile, SMEProfile, UserActivityLog
from admin1.models import credit_assessment_enabled
from loan.models import Loan, LoanFile, Statement
from .tokens import account_activation_token
from admin1.models import AdminSettings
from .functions import id_generator, send_email, login_check, admin_check, fileuploader, loanfileuploader, get_field_settings, get_default_repayment_limit, rate_limit, credit_assessment_check
from message.models import Message, MessageLog
from support.models import SupportTicket, SupportTicketThread
from loan.functions import request_approval

User = get_user_model()
sender = settings.DEFAULT_SENDER_EMAIL
domain = settings.DOMAIN


##############
##  PAGES
##############

def messages_user(request):
    uid = request.user.id
    user_profile = UserProfile.objects.get(user_id=uid)
    all_messages = []
    try:
        mylog = UserActivityLog.objects.get(user=user_profile)
        mymsglogs = mylog.msglog
        msgids = list(mymsglogs.split(','))
        for mid in msgids:
            message = Message.objects.get(id=int(mid))
            all_messages.append(message)
    except:
        all_messages = []
    messages_count = len(all_messages)
    return render(request, 'messages_user.html', {'nav':'messages_user', 'all_messages': all_messages, 'messages_count': messages_count, 'user': user_profile })

@login_check
def tc_consent(request, tcc):

    uid = request.user.id
    user = UserProfile.objects.get(user_id=uid)

    
    
    if request.method == 'POST':
        if tcc == "YES, I AGREE":
            user.terms_consent = 'YES'
            user.save()
            messages.success(request, 'You have consented to be bound by our terms and conditions', extra_tags="info")
            return redirect('terms_credit_consent')
        
        if tcc == "NO":
            
            loans = Loan.objects.filter(owner=user).exclude(status="COMPLETED")
            if loans.count() != 0:
                messages.success(request, 'You CAN NOT revoke your consent to be bound by our terms and conditions because you have an existing loan with us. You need to settle all your loans before you revoke your consent.', extra_tags="danger")
                return redirect('terms_credit_consent')  
                
            user.terms_consent = 'NO'
            user.save()
            
            messages.success(request, 'You have revoked your consent to be bound by our terms and conditions', extra_tags="info")
            return redirect('terms_credit_consent')  
    
def credit_rating(request):
    user = UserProfile.objects.get(user_id=request.user.id)
    return render(request, 'credit_rating.html', {'nav': 'credit_rating', 'user':user})

@login_check
def terms_credit_consent(request):

    uid = request.user.id
    user = UserProfile.objects.get(user_id=uid)
    
    tc_consent = user.terms_consent
    cd_consent = user.credit_consent
    company = settings.COMPANY_NAME
    domain = settings.DOMAIN
    
    if request.method == 'POST':
        
        tcc = request.POST.get('tcc')
        cdc = request.POST.get('cdc')
        
        if tcc == "YES, I AGREE":
            user.terms_consent = 'YES'
            user.save()
            messages.success(request, 'You have consented to be bound by our terms and conditions', extra_tags="info")
            return redirect('terms_credit_consent')
        
        if tcc == "REVOKE CONSENT":
            
            loans = Loan.objects.filter(owner=user).exclude(status="COMPLETED")
            if loans.count() != 0:
                messages.success(request, 'You CAN NOT revoke your consent to be bound by our terms and conditions because you have an existing loan with us. You need to settle all your loans before you revoke your consent.', extra_tags="danger")
                return redirect('terms_credit_consent')  
                
            user.terms_consent = 'NO'
            user.save()
            
            messages.success(request, 'You have revoked your consent to be bound by our terms and conditions', extra_tags="info")
            return redirect('terms_credit_consent')  
        
        if cdc == "YES, I AGREE":
            user.credit_consent = 'YES'
            user.save()
            messages.success(request, 'You have consented to our Credit Data Policy', extra_tags="info")
            return redirect('terms_credit_consent')
        
        if cdc == "REVOKE CONSENT":
            
            loans = Loan.objects.filter(owner=user).exclude(status="COMPLETED")
            if loans.count() != 0:
                messages.success(request, 'You CAN NOT revoke your consent to our Credit Data Policy because you have an existing loan with us. You need to settle all your loans before you revoke your consent.', extra_tags="danger")
                return redirect('terms_credit_consent')  
                
            user.credit_consent = 'NO'
            user.save()
            
            messages.success(request, 'You have revoked your consent to our Credit Data Policy', extra_tags="info")
            return redirect('terms_credit_consent') 
    
    
    return render(request, 'terms_credit_consent.html', {'nav': 'terms_credit_consent', 'tcc': tc_consent, 'cdc': cd_consent, 'company': company, 'domain': domain, 'user':user })

def support(request):
    return render(request, 'support.html', {'nav': 'support',})

def activation_sent(request):
    return render(request, 'activation_sent.html')

def activation_invalid(request):
    return render(request, 'activation_invalid.html')

@login_check
def dashboard(request):
    
    user = request.user
    uid = user.id
    user_profile = UserProfile.objects.get(user_id=uid)
    
    all_funded_loans = Loan.objects.filter(owner_id=user_profile.id, category = 'FUNDED')
    all_active_loans = Loan.objects.filter(owner_id=user_profile.id, funded_category = 'ACTIVE')
    all_loans = Loan.objects.filter(owner_id=user_profile.id).all()
    
    repaid = 0
    outstanding = 0
    arrears = 0
    app_fee = 0
    default_interest = 0
    interest = 0
    loan_amount = 0 
    
    for loan in all_funded_loans:
        repaid += loan.total_paid
        outstanding += loan.total_outstanding
        arrears += loan.total_arrears
    try:
        next_payment = all_active_loans[0].next_payment_date
        active_loan_ref = all_active_loans[0].ref
        surplus = all_active_loans[0].advance_payment_surplus
    except: 
        next_payment = 0
        active_loan_ref = 'None'
        surplus = 0
    
    #pending_loans = Loan.objects.filter(Q(status='AWAITING T&C') | Q(status='UNDER REVIEW'), owner_id=user.id).all()
    pending_loans = Loan.objects.filter(category="PENDING", owner_id=user_profile.id).all()
    if pending_loans.count() == 0:
        status_updates = 'no_loan'
    else:
        status_updates = {}
        for ploan in pending_loans:
            loan_dict = { f'{ploan.ref}': f'{ploan.status}' }
            status_updates.update(loan_dict)

    statements = Statement.objects.filter(owner_id=user_profile.id).order_by('-date')[:4]

    #recent messages display
    recent_messages = []
    try:
        userlog = UserActivityLog.objects.all()
        userlogmsgs = list(UserActivityLog.objects.get(user=user_profile).msgq.split(','))
    except:
        userlogmsgs = []

    try:
        for mid in userlogmsgs:
            message = Message.objects.get(id=int(mid))
            recent_messages.append(message)
    except:
        pass
    message_count = len(recent_messages)

    ticket = SupportTicket.objects.filter(user=user_profile).last()
    try:
        ticketthread = SupportTicketThread.objects.filter(ticket=ticket).last()
    except:
        ticketthread = None

    if ticket == None:
        tickets = 0
    else:
        tickets = 1

    try:
        all_active_loans[0]
        loan_check = 'YES' 
    except:
        loan_check = 'NO'


    context = {
        'domain':domain,
        'nav':'dashboard',
        'repaid': repaid,
        'outstanding': outstanding,
        'arrears':arrears,
        'next_payment': next_payment,
        'status_updates':status_updates,
        'all_loans': all_loans,
        'statements': statements,
        'user':user_profile,
        'active_loan_ref': active_loan_ref,
        'recent_messages': recent_messages,
        'message_count':message_count,
        'ticketthread':ticketthread,
        'ticket':ticket,
        'tickets': tickets,
        'surplus':surplus,
        'loan_check': loan_check
    }

    return render(request, 'dashboard.html', context)


@login_check
def user_instructions(request):
    """Client-facing how-to-use guide and FAQ."""
    return render(request, 'user_instructions.html', {'nav': 'user_instructions'})


def reset_link_sent(request):
    return render(request, 'reset_link_sent.html')

##### ACCOUNT CONTROL #####

@admin_check
def suspend_user(request, uid):
    
    user = User.objects.get(pk=uid)
    user.suspended = True
    user.save()

    
    
    subject = 'LOAN ACCOUNT DEACTIVATED'
    ''' if header_cta == 'yes' '''
    cta_link = 'http://www.webmasta.com.pg'
    cta_label = 'Request Activation'

    greeting = f'Hello {user.email}'
    message = 'You loan account was deactivated due to a lot of defaults.'
    message_details = 'This will have a negative impact on your credit rating \
        which is used by a lot of local organisation to decide on loan products. \
            You should fix this with us to maintain good credit rating.'

    ''' if cta == 'yes' '''
    cta_btn1_link = 'http://dcc.com.pg'
    cta_btn1_label = 'REQUEST ACTIVATION'
    cta_btn2_link = 'http://dcc.com.pg/cancel/'
    cta_btn2_label = 'Cancel'

    ''' if promo == 'yes' '''
    catchphrase = 'TIP:'
    promo_title = 'CREDIT RATING AFFECTS EVERYTHING'
    promo_message = 'A Low credit rating will prevent borrowing and good business opportunities.'
    promo_cta_link = 'http://dcc.com.pg/fix/'
    promo_cta = 'Fix Credit Rating'
    
    email_content = render_to_string('custom/email_temp_general.html', {
        'header_cta': 'yes',
        'cta': 'yes',
        'cta_btn2': 'yes',
        'promo': 'yes',
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
    email = EmailMultiAlternatives(subject,text_content,sender,['dev@webmasta.com.pg', user.email ])
    email.attach_alternative(email_content, "text/html")

    try: 
        email.send()
        messages.success(request, "Success Message")
    except:
        messages.error(request, 'Error Message', extra_tags='danger')
        
    return redirect('view_client', uid)

@admin_check
def activate_user(request, uid):

    user = UserProfile.objects.get(pk=uid)

    # Screen against the credit bureau before activating (Settings -> DCC).
    # This is the door: catching a known-bad borrower here costs far less than
    # discovering them at loan application. A client below the minimum is HELD
    # for manual review, never auto-rejected — staff can still activate them
    # deliberately by re-running this action once they have reviewed the file.
    from dcc.decisions import screen_registration
    screening = screen_registration(user)
    if not screening.allowed and not request.GET.get('override'):
        messages.warning(
            request,
            f'{user.first_name} {user.last_name} was NOT activated — {screening.reason} '
            f'Review their DCC credit report, then use Activate (Override) to proceed anyway.',
            extra_tags='warning')
        return redirect('view_client', uid)
    for flag in screening.flags:
        messages.info(request, f'DCC: {flag}', extra_tags='info')

    user.activation = 1
    # Apply the admin-configured default repayment limit if set (and only if not already set)
    _default_limit = get_default_repayment_limit()
    if _default_limit is not None and (user.repayment_limit is None or user.repayment_limit == 0):
        user.repayment_limit = _default_limit
    user.save()

    #create user's activity log
  
    try:
        MessageLog.objects.create(user=user)
    except:
        pass

    
    subject = 'LOAN ACCOUNT ACTIVATED'
    greeting = 'Hello'
    message = 'Your loan account has been activated.'
    details = 'Now you can start applying for loans. Remember, more information on your profile will help us make loan decisons faster so please do upload as much information as you can.'
    btn_label = 'APPLY'
    btn_link = f'{settings.DOMAIN}/loan/apply/'

    email_content = render_to_string('custom/email_temp_general.html', {
        'subject': subject,
        'greeting': greeting,
        'message': message,
        'message_details': details,
        'action_btn_1': btn_label,
        'action_btn_1_link' : btn_link,
        'user': user,
        'domain': domain,  
    })

    text_content = strip_tags(email_content)
    email = EmailMultiAlternatives(subject,text_content,sender,['dev@webmasta.com.pg', user.email ])
    email.attach_alternative(email_content, "text/html")

    try: 
        email.send()
        messages.success(request, "User Loan Account was activated and Email was sent to notify user.")
    except:
        messages.error(request, 'User account is activated BUT user email notification was not sent.', extra_tags='danger')
        
    return redirect('view_client', uid)

@admin_check
def deactivate_user(request, uid):

    user = UserProfile.objects.get(pk=uid)
    user.activation = 0
    user.save()

    #create user's activity log
  
    
    subject = 'LOAN ACCOUNT DE-ACTIVATED'
    greeting = 'Hello'
    message = 'Your loan account has been deactivated.'
    details = 'Now you can NOT apply for loans.'
    btn_label = 'REACTIVATE'
    btn_link = f'#'

    email_content = render_to_string('custom/email_temp_general.html', {
        'subject': subject,
        'greeting': greeting,
        'message': message,
        'message_details': details,
        'action_btn_1': btn_label,
        'action_btn_1_link' : btn_link,
        'user': user,
        'domain': domain,  
    })

    text_content = strip_tags(email_content)
    email = EmailMultiAlternatives(subject,text_content,sender,['dev@webmasta.com.pg', user.email ])
    email.attach_alternative(email_content, "text/html")

    try: 
        email.send()
        messages.success(request, "User Loan Account was Deactivated and Email was sent to notify user.")
    except:
        messages.error(request, 'User account is deactivated BUT user email notification was not sent.', extra_tags='danger')
        
    return redirect('view_client', uid)

##############
##  AUTHENTICATION
##############

def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user,token):
        user.active = True
        user.confirmed = True
        user.save()

        userprofile = UserProfile.objects.create(user_id=uid)

        userprofile.email = user.email
        userprofile.modeofregistration = 'SR'
        userprofile.save()
        
        try:
            prefix = AdminSettings.objects.get(name='settings1').loanref_prefix
        except:
            prefix = settings.PREFIX
        
        random_num = random.randint(1000,9999)
        
        userprofile.uid = f'{prefix}{random_num}'
        userprofile.modeofregistration = 'SR'
        userprofile.luid = settings.LUID
        userprofile.save()
        
        login(request, user)
        #messages.success(request, 'Make sure to switch to admin and click on instructions to learn on basics of how to use the app.', extra_tags="info")
        return redirect('profile')
    else:
        #user.delete()
        return render(request, 'activation_invalid.html')        

def password_reset(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user,token):
        
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)  # Important!
                messages.success(request, 'Your password was successfully reset!')
                return redirect('login_user')
            else:
                messages.error(request, 'Please correct the error below.', extra_tags='danger')
        else:
            form = SetPasswordForm(user)
            
        return render(request, 'reset_password_form.html', {'form': form})
    else:
        return render(request, 'activation_invalid.html')
      
@rate_limit(max_attempts=15, window_seconds=600)
def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():

            # Validate the reCAPTCHA response
            captcha_response = request.POST.get(settings.RECAPTCHA_RESPONSE_KEY)
            if not captcha_response:
                form.add_error('captcha', 'Please complete the reCAPTCHA')
                return render(request, 'register.html', {'form': form})
        
            user = form.save()
            user.is_active=False

            #to send email
            # HTML EMAIL
            
            email_subject = 'Activate your Loan Account'
            token_message = render_to_string('activation_request.html', {
                'user': user,
                'domain': domain,
                'cta': 'yes',
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': account_activation_token.make_token(user),
            })
            text_content = strip_tags(token_message)
            email = EmailMultiAlternatives(
                email_subject,
                text_content,
                settings.EMAIL_HOST_USER,
                ['dev@webmasta.com.pg', user.email ]
            )
            email.attach_alternative(token_message, "text/html")

            try:
                email.send()
                return redirect('activation_sent')
            except:
                messages.error(request, "The activation token email could not be sent, make sure you have internet connection and try again.", extra_tags='danger')
                uid = user.id
                User.objects.get(pk=uid).delete()

    else: 
        form = RegisterForm()
    return render(request, 'register.html', {'form': form})

def reset_password(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
            except:
                messages.error(request, 'User does not exist!', extra_tags="danger")
                return redirect('reset_password')
            
            current_user = User.objects.get(email=email)
            
            #to send email
            current_site = settings.DOMAIN
            subject='Reset your account\'s Password'
            token_message = render_to_string('password_reset.html', {
                'user': current_user,
                'cta': 'yes',
                'domain': current_site,
                'uid': urlsafe_base64_encode(force_bytes(current_user.pk)),
                'token': account_activation_token.make_token(current_user),
            })
            text_content = strip_tags(token_message)
            email = EmailMultiAlternatives(
                subject,
                text_content,
                settings.EMAIL_HOST_USER,
                ['dev@webmasta.com.pg', user.email ]
            )
            email.attach_alternative(token_message, "text/html")
            try:
                email.send()
                return redirect('reset_link_sent')
            except:
                messages.error(request, "The reset token email could not be sent, make sure you have internet connection and try again.", extra_tags='danger')
                return redirect('reset_password')
    else: 
        form = PasswordResetForm()
    return render(request, 'reset_password.html', {'form': form})            
            
@rate_limit(max_attempts=10, window_seconds=300)
def login_user(request):

    if request.user.is_authenticated:
        return redirect( 'dashboard' )
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, email=email, password=password)
            if user is not None:
                # Suspended accounts (Settings → Staff, or client suspension)
                # must not get a session. The custom User model does not map
                # is_active to the `active` field, so the backend won't block
                # them — enforce it here.
                if getattr(user, 'suspended', False):
                    messages.error(request, 'This account has been suspended. Please contact your administrator.', extra_tags='danger')
                    return redirect('login_user')
                login(request, user)
                messages.success(request, 'Welcome to your dashboard...')
                if user.id == 1:
                    messages.success(request, 'Make sure to switch to admin and click on instructions to learn on basics of how to use the app.', extra_tags="info")
                try:
                    user_profile = UserProfile.objects.get(user_id=user.id)
                except:
                    messages.error(request, "You did not activate your profile yet using the activation link sent to your email.", extra_tags="warning")
                    messages.error(request, "We are deleting this account, please register again.", extra_tags="info")
                    user.delete()
                    return redirect('register')
                user_profile.login_timestamp = datetime.datetime.now()
                user_profile.save()
                
                return redirect('dashboard')
            else:
                messages.error(request, 'User does not exist.', extra_tags='danger')
                return redirect('login_user')
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form':form})

def logout_user(request):
    logout(request)
    messages.success(request, 'You have logged out...')
    return redirect('login_user')

##############
##  PROFILE MANAGEMENT
##############

def profile(request):
    
    if request.user.is_authenticated:
        current_user = request.user
        uid = current_user.id
        try:
            user = UserProfile.objects.get(user_id=uid)
            
        except:
            messages.error(request,f'Profile for this user does not exist. Register new account or Contact { settings.SUPPORT_EMAIL }', extra_tags='danger')
            return redirect('register')
        if user is None:
            return redirect('edit_profile')
        
        #from django.db.models import Q
        # Combine the two queries into one
        combined_query = Q(owner=user.id) & Q(category='PENDING') & (Q(status='AWAITING T&C') | Q(status='UNDER REVIEW'))
        # Retrieve loans matching the combined query
        combined_loans = Loan.objects.filter(combined_query)
        # Now combined_loans contains loans that satisfy both conditions
        
        field_settings = get_field_settings()
        if combined_loans:
            try:
                loan = Loan.objects.get(combined_query)
                loanfile = LoanFile.objects.get(loan=loan)
                return render(request, 'profile.html', { 'nav':'profile','current_user': current_user, 'user': user, 'loanfile': loanfile, 'field_settings': field_settings })
            except:
                pass
        else:
            return render(request, 'profile.html', { 'nav':'profile','current_user': current_user, 'user': user, 'field_settings': field_settings })
        
    return redirect('login_user')

def edit_personalinfo(request):
    if request.user.is_authenticated:
        ca_user = request.user.id
        user_profile = UserProfile.objects.get(user_id=ca_user)
        if user_profile.has_loan:
            messages.error(request, 'Profile editing is locked while you have an active loan.', extra_tags='danger')
            return redirect('profile')
        uid = user_profile.id
        user = UserProfile.objects.get(pk=uid)

        initial_data = {
            'first_name': user.first_name,
            'middle_name': user.middle_name,
            'last_name': user.last_name,
            'gender': user.gender,
            'date_of_birth': user.date_of_birth,
            'marital_status': user.marital_status,
        }
       
        if request.method == 'POST':
            personalinfoUpdateForm = PersonalInfoForm(request.POST)
            if  personalinfoUpdateForm.is_valid():
                
                user.first_name = personalinfoUpdateForm.cleaned_data.get('first_name', user.first_name)
                user.save()
                user.middle_name = personalinfoUpdateForm.cleaned_data.get('middle_name', user.middle_name)
                user.save()
                user.last_name = personalinfoUpdateForm.cleaned_data.get('last_name', user.last_name)
                user.save()
                user.gender = personalinfoUpdateForm.cleaned_data.get('gender', user.gender)
                user.save()
                user.date_of_birth = personalinfoUpdateForm.cleaned_data.get('date_of_birth', user.date_of_birth)
                user.save()
                user.marital_status = personalinfoUpdateForm.cleaned_data.get('marital_status', user.marital_status)
                user.save()

                try:
                    prefix = AdminSettings.objects.get(name='settings1').loanref_prefix
                except:
                    prefix = settings.PREFIX
     
                random_num= random.randint(1111, 9999)

                existing_uid = user.uid
                #new userprofile.uid
                user.uid = f'{existing_uid}{user.first_name[0]}{user.last_name[0]}'
                user.save()
                
                if 'propic' in request.FILES:
                    fileuploader(request, 'propic', user)

                messages.success(request, 'Personal information updated successfully!')
            return redirect('profile')
        else:
            personalinfoUpdateForm = PersonalInfoForm(initial=initial_data)
        return render(request, 'edit_personalinfo.html', {'nav':'profile','form':personalinfoUpdateForm, 'cau': ca_user , 'user':user})
    return redirect('login_user')


def edit_addressinfo(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user_profile = UserProfile.objects.get(user_id=uid)
        if user_profile.has_loan:
            messages.error(request, 'Profile editing is locked while you have an active loan.', extra_tags='danger')
            return redirect('profile')
        initial_data = {
            'mobile1': user_profile.mobile1,
            'mobile2': user_profile.mobile2,
            'resident_owner': user_profile.resident_owner,
            'residential_address': user_profile.residential_address,
            'residential_province': user_profile.residential_province,
            'place_of_origin': user_profile.place_of_origin,
            'province': user_profile.province 
        }
        if request.method == 'POST':
            addressinfoUpdateForm = AddressInfoForm(request.POST)
            if  addressinfoUpdateForm.is_valid():
                user_profile.mobile1 = addressinfoUpdateForm.cleaned_data['mobile1']
                user_profile.save()
                user_profile.mobile2 = addressinfoUpdateForm.cleaned_data['mobile2']
                user_profile.save()  
                user_profile.resident_owner = addressinfoUpdateForm.cleaned_data['resident_owner']
                user_profile.save()
                user_profile.residential_address = addressinfoUpdateForm.cleaned_data['residential_address']
                user_profile.save()
                user_profile.residential_province = addressinfoUpdateForm.cleaned_data['residential_province']
                user_profile.save()
                user_profile.place_of_origin = addressinfoUpdateForm.cleaned_data['place_of_origin']
                user_profile.save()
                user_profile.province = addressinfoUpdateForm.cleaned_data['province']
                user_profile.save()
                messages.success(request, 'Address information updated successfully!')
            return redirect('profile')
        else:
            addressinfoUpdateForm = AddressInfoForm(initial=initial_data)
        return render(request, 'edit_addressinfo.html', {'nav':'profile','form':addressinfoUpdateForm, })
    return redirect('login_user')

def edit_bankinfo(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user_profile = UserProfile.objects.get(user_id=uid)
        if user_profile.has_loan:
            messages.error(request, 'Profile editing is locked while you have an active loan.', extra_tags='danger')
            return redirect('profile')
        initial_data = {
            'bank': user_profile.bank,
            'bank_account_name': user_profile.bank_account_name,
            'bank_account_number': user_profile.bank_account_number,
            'bank_branch': user_profile.bank_branch,
            
        }
    
        if request.method == 'POST':
            
            if user_profile.first_name == '' and user_profile.last_name == '':
                return redirect('edit_personalinfo')
            
            bankinfoUpdateForm = BankAccountInfoForm(request.POST)
            if  bankinfoUpdateForm.is_valid():
                
                user_profile.bank = bankinfoUpdateForm.cleaned_data['bank']
                user_profile.save()
                user_profile.bank_account_name = bankinfoUpdateForm.cleaned_data['bank_account_name']
                user_profile.save()
                user_profile.bank_account_number = bankinfoUpdateForm.cleaned_data['bank_account_number']
                user_profile.save()
                user_profile.bank_branch = bankinfoUpdateForm.cleaned_data['bank_branch']
                user_profile.save()
                
                if 'bank_standing_order' in request.FILES:
                    fileuploader(request, 'bank_standing_order', user_profile)

                messages.success(request, 'Primary Bank Account information Updated Successfully!')
            
            return redirect('profile')

        else:
            bankinfoUpdateForm = BankAccountInfoForm(initial=initial_data)
        return render(request, 'edit_bankinfo.html', {'nav':'profile','form':bankinfoUpdateForm, 'user':user_profile })
    return redirect('login_user')

def edit_bankinfo2(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user_profile = UserProfile.objects.get(user_id=uid)
        if user_profile.has_loan:
            messages.error(request, 'Profile editing is locked while you have an active loan.', extra_tags='danger')
            return redirect('profile')
        initial_data = {
            'bank2': user_profile.bank2,
            'bank_account_name2': user_profile.bank_account_name2,
            'bank_account_number2': user_profile.bank_account_number2,
            'bank_branch2': user_profile.bank_branch2,
            'bank_standing_order2_url': user_profile.bank_standing_order2_url
        }
    
        if request.method == 'POST':
            
            if user_profile.first_name == '' and user_profile.last_name == '':
                return redirect('edit_personalinfo')
            
            bankinfoUpdate2Form = BankAccountInfo2Form(request.POST)
            if  bankinfoUpdate2Form.is_valid():
                
                user_profile.bank2 = bankinfoUpdate2Form.cleaned_data['bank2']
                user_profile.save()
                user_profile.bank_account_name2 = bankinfoUpdate2Form.cleaned_data['bank_account_name2']
                user_profile.save()
                user_profile.bank_account_number2 = bankinfoUpdate2Form.cleaned_data['bank_account_number2']
                user_profile.save()
                user_profile.bank_branch2 = bankinfoUpdate2Form.cleaned_data['bank_branch2']
                user_profile.save()
                
                if 'bank_standing_order2' in request.FILES:
                    fileuploader(request, 'bank_standing_order2', user_profile)
                
                messages.success(request, 'Secondary Bank Account information Updated Successfully!') 
            return redirect('profile')
        
        else:
            bankinfoUpdate2Form = BankAccountInfo2Form(initial=initial_data)
        return render(request, 'edit_bankinfo2.html', {'nav':'profile','form':bankinfoUpdate2Form, 'user':user_profile })
    return redirect('login_user')

def edit_useruploads(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user = UserProfile.objects.get(user_id=uid)
        if user.has_loan:
            messages.error(request, 'Profile editing is locked while you have an active loan.', extra_tags='danger')
            return redirect('profile')
        initial_data = {
            'nid_number': user.nid_number,
            'passport_number': user.passport_number,
            'drivers_license_number': user.drivers_license_number,
            'super_member_code': user.super_member_code,
            'work_id_number': user.work_id_number,
        }
        
        if request.method == 'POST':
            uploadform = UserUploadForm(request.POST)
            
            if user.first_name == '' and user.last_name == '':
                messages.error(request, 'You need to update your First Name and Last Name first...', extra_tags="warning")
                return redirect('edit_personalinfo')
            
            if uploadform.is_valid():
                
                if 'nid' in request.FILES:
                    fileuploader(request, 'nid', user)
                    
                if 'passport' in request.FILES:
                    fileuploader(request, 'passport', user)
                
                if 'drivers_license' in request.FILES:
                    fileuploader(request, 'drivers_license', user)
                
                if 'superid' in request.FILES:
                    fileuploader(request, 'superid', user)
                
                if 'work_id' in request.FILES:
                    fileuploader(request, 'work_id', user)
                
                if uploadform.cleaned_data.get('nid_number'):
                    user.nid_number = uploadform.cleaned_data['nid_number']
                    user.save()

                if uploadform.cleaned_data.get('passport_number'):
                    user.passport_number = uploadform.cleaned_data['passport_number']
                    user.save()
                if uploadform.cleaned_data.get('drivers_license_number'):
                    user.drivers_license_number = uploadform.cleaned_data['drivers_license_number']
                    user.save()
                if uploadform.cleaned_data.get('super_member_code'):
                    user.super_member_code = uploadform.cleaned_data['super_member_code']
                    user.save()
                if uploadform.cleaned_data.get('work_id_number'):
                    user.work_id_number = uploadform.cleaned_data['work_id_number']
                    user.save()
                   
                messages.success(request, 'Personal ID information Updated Successfully!') 
                return redirect('profile')
        else:
            uploadform = UserUploadForm(initial=initial_data)        
        return render(request, 'edit_useruploads.html', { 'form': uploadform, 'user':user })   
                
    return redirect('login_user')

def edit_work_uploads(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user = UserProfile.objects.get(user_id=uid)
        
        if request.method == 'POST':
            uploadform = WorkUploadForm(request.POST)
            
            if user.first_name == '' and user.last_name == '':
                return redirect('edit_personalinfo')
            
            if uploadform.is_valid():
                
                if Loan.objects.filter(owner=user.id, category='PENDING', status='AWAITING T&C'):
                    try:
                        loan = Loan.objects.get(owner=user.id, category='PENDING', status='AWAITING T&C')
                    except:
                        messages.error(request, "You probably have more than one pending loans 'Awaiting T&C'. Always make sure there is ONLY ONE pending loan under review before uploading the required documents.", extra_tags='warning')
                        referrer = request.META['HTTP_REFERER']
                        return redirect(referrer)
                
                    if 'work_confirmation_letter' in request.FILES:
                        loanfileuploader(request, 'work_confirmation_letter', user, loan)
                        
                    if 'payslip1' in request.FILES:
                        loanfileuploader(request, 'payslip1', user, loan)
                    
                    if 'payslip2' in request.FILES:
                        loanfileuploader(request, 'payslip2', user, loan)

                    if LoanFile.objects.get(loan=loan):
                        loanfile = LoanFile.objects.get(loan=loan)
                        if loanfile.application_form_url and loanfile.terms_conditions_url and loanfile.stat_dec_url and loanfile.irr_sd_form_url and loanfile.bank_statement_url and loanfile.payslip1_url and loanfile.payslip2_url and loanfile.work_confirmation_letter_url:
                            request_approval(loan)

                    messages.success(request, 'Required documents uploaded successfully...')

                else:
                    messages.error(request, "You probably have more than one pending loans 'Awaiting T&C'. Always make sure there is ONLY ONE pending loan under review before uploading the required documents.", extra_tags='warning')
                    return redirect('dashboard')

                return redirect('profile')
        else:
            uploadform = WorkUploadForm()        
        return render(request, 'edit_work_uploads.html', { 'form': uploadform, 'user': user })   
                
    return redirect('login_user')

def edit_required_uploads(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user = UserProfile.objects.get(user_id=uid)
        
        if request.method == 'POST':
            uploadform = RequiredUploadForm(request.POST)
            
            if user.first_name == '' and user.last_name == '':
                return redirect('edit_personalinfo')
            
            if uploadform.is_valid():
                
                if Loan.objects.filter(owner=user.id, category='PENDING', status='AWAITING T&C'):
                    try:
                        loan = Loan.objects.get(owner=user.id, category='PENDING', status='AWAITING T&C')
                    except:
                        messages.error(request, "You probably have more than one pending loans 'Awaiting T&C'. Always make sure there is ONLY ONE pending loan under review before uploading the required documents.", extra_tags='warning')
                        referrer = request.META['HTTP_REFERER']
                        return redirect(referrer)
                else:
                    try:
                        loan = Loan.objects.get(owner=user.id, category='PENDING', status='UNDER REVIEW')
                    except:
                        messages.error(request, "You probably have NO pending loan. Apply for a new loan", extra_tags='warning')
                        return redirect('loan_application')

                if 'application_form' in request.FILES:
                    loanfileuploader(request, 'application_form', user, loan)

                if 'terms_conditions' in request.FILES:
                    loanfileuploader(request, 'terms_conditions', user, loan)
                    loan.tc_agreement_timestamp = datetime.datetime.now()
                    loan.tc_agreement = 'YES'
                    loan.save()
                    
                if 'stat_dec' in request.FILES:
                    loanfileuploader(request, 'stat_dec', user, loan)
                
                if 'irr_sd_form' in request.FILES:
                    loanfileuploader(request, 'irr_sd_form', user, loan)

                if 'signed_contract' in request.FILES:
                    loanfileuploader(request, 'signed_contract', user, loan)

                if LoanFile.objects.get(loan=loan):
                    loanfile = LoanFile.objects.get(loan=loan)
                    if loanfile.application_form_url and loanfile.terms_conditions_url and loanfile.stat_dec_url and loanfile.irr_sd_form_url and loanfile.bank_statement_url and loanfile.payslip1_url and loanfile.payslip2_url and loanfile.work_confirmation_letter_url:
                        request_approval(loan)

                messages.success(request, 'Required documents uploaded successfully...')

                
                return redirect('profile')
        else:
            uploadform = RequiredUploadForm()        
        return render(request, 'edit_required_uploads.html', { 'form': uploadform, 'user':user })   
                
    return redirect('login_user')

def edit_loan_statement_uploads(request):
    
    if request.user.is_authenticated:
        uid = request.user.id
        user = UserProfile.objects.get(user_id=uid)
        
        if request.method == 'POST':
            uploadform = LoanStatementUploadForm(request.POST)
            
            if user.first_name == '' and user.last_name == '':
                return redirect('edit_personalinfo')
            
            if uploadform.is_valid():

                if Loan.objects.filter(owner=user.id, category='PENDING', status='AWAITING T&C'):
                    try:
                        loan = Loan.objects.get(owner=user.id, category='PENDING', status='AWAITING T&C')
                    except:
                        messages.error(request, "You probably have more than one pending loans 'Awaiting T&C'. Always make sure there is ONLY ONE pending loan under review before uploading the required documents.", extra_tags='warning')
                        referrer = request.META['HTTP_REFERER']
                        return redirect(referrer)
                else:
                    try:
                        loan = Loan.objects.get(owner=user.id, category='PENDING', status='UNDER REVIEW')
                    except:
                        messages.error(request, "You probably have NO pending loan. Apply for a new loan", extra_tags='warning')
                        return redirect('loan_application')
                    
                if 'loan_statement1' in request.FILES:
                    loanfileuploader(request, 'loan_statement1', user, loan)
                
                if 'loan_statement2' in request.FILES:
                    loanfileuploader(request, 'loan_statement2', user, loan)
                    
                if 'loan_statement3' in request.FILES:
                    loanfileuploader(request, 'loan_statement3', user, loan)
                
                if 'bank_statement' in request.FILES:
                    loanfileuploader(request, 'bank_statement', user, loan)
                
                if 'super_statement' in request.FILES:
                    loanfileuploader(request, 'super_statement', user, loan)

                if 'bank_standing_order' in request.FILES:
                    loanfileuploader(request, 'bank_standing_order', user, loan)

                if LoanFile.objects.get(loan=loan):
                    loanfile = LoanFile.objects.get(loan=loan)
                    if loanfile.application_form_url and loanfile.terms_conditions_url and loanfile.stat_dec_url and loanfile.irr_sd_form_url and loanfile.bank_statement_url and loanfile.payslip1_url and loanfile.payslip2_url and loanfile.work_confirmation_letter_url:
                        request_approval(loan)

                messages.success(request, 'Required documents uploaded successfully...')

                return redirect('profile')
        else:
            uploadform = LoanStatementUploadForm() 

        messages.error(request, 'Please upload all statements that you can upload.', extra_tags='info')       
        return render(request, 'edit_loan_statement_uploads.html', { 'form': uploadform, 'user':user })   
                
    return redirect('login_user')

def edit_jobinfo(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user_profile = UserProfile.objects.get(user_id=uid)
        if user_profile.has_loan:
            messages.error(request, 'Profile editing is locked while you have an active loan.', extra_tags='danger')
            return redirect('profile')
        initial_data = {
            'job_title': user_profile.job_title,
            'start_date': user_profile.start_date,
            'pay_frequency': user_profile.pay_frequency,
            'last_paydate': user_profile.last_paydate,
            'gross_pay': user_profile.gross_pay,
            'net_pay': user_profile.net_pay,
            'employee_file_number': user_profile.employee_file_number,
        }
        
        if request.method == 'POST':
            jobinfoUpdateForm = JobInfoUpdateForm(request.POST)
            if  jobinfoUpdateForm.is_valid():
                
                user_profile.job_title = jobinfoUpdateForm.cleaned_data.get('job_title', user_profile.job_title)
                user_profile.save()
                user_profile.start_date = jobinfoUpdateForm.cleaned_data.get('start_date', user_profile.start_date)
                user_profile.save()
                user_profile.pay_frequency = jobinfoUpdateForm.cleaned_data.get('pay_frequency', user_profile.pay_frequency)
                user_profile.save()
                user_profile.last_paydate = jobinfoUpdateForm.cleaned_data.get('last_paydate', user_profile.last_paydate)
                user_profile.save()
                user_profile.gross_pay = jobinfoUpdateForm.cleaned_data.get('gross_pay', user_profile.gross_pay)
                user_profile.save()
                user_profile.net_pay = jobinfoUpdateForm.cleaned_data.get('net_pay', user_profile.net_pay)
                user_profile.save()
                user_profile.employee_file_number = jobinfoUpdateForm.cleaned_data.get('employee_file_number', user_profile.employee_file_number)
                user_profile.save()
                
                from admin1.models import AdminSettings
                try:
                    percent_of_gross = AdminSettings.objects.get(settings_name='setting1').percentage_of_gross
                    user_profile.repayment_limit = (Decimal(percent_of_gross)/Decimal(100.0)) * Decimal(user_profile.gross_pay)
                except:
                    percent_of_gross = 0.0
                
                messages.success(request, 'Job information updated successfully!')
            return redirect('profile')
        else:
            jobinfoUpdateForm = JobInfoUpdateForm(initial=initial_data)
        return render(request, 'edit_jobinfo.html', {'nav':'profile','form':jobinfoUpdateForm, 'user':user_profile })
    return redirect('login_user')

def edit_employerinfo(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user_profile = UserProfile.objects.get(user_id=uid)
        if user_profile.has_loan:
            messages.error(request, 'Profile editing is locked while you have an active loan.', extra_tags='danger')
            return redirect('profile')
        initial_data = {
            'sector': user_profile.sector,
            'employer': user_profile.employer,
            'organisation_type': user_profile.organisation_type,
            'office_address': user_profile.office_address,
            'payroll_officer_name': user_profile.payroll_officer_name,
            'payroll_officer_phone': user_profile.payroll_officer_phone,
            'payroll_officer_email': user_profile.payroll_officer_email, 'deduction_category': user_profile.deduction_category,
        }

        if request.method == 'POST':
            employerinfoUpdateForm = EmployerInfoUpdateForm(request.POST)
            if employerinfoUpdateForm.is_valid():
                cd = employerinfoUpdateForm.cleaned_data
                selected_employer_name = cd.get('employer') or user_profile.employer
                user_profile.employer = selected_employer_name
                if 'deduction_category' in cd:
                    user_profile.deduction_category = cd.get('deduction_category') or None

                if employerinfoUpdateForm._preregistration and selected_employer_name:
                    # Preregistration ON: auto-fill all employer details from the registered record
                    try:
                        from admin1.models import Employer as _Emp
                        emp = _Emp.objects.get(name=selected_employer_name, active=True)
                        user_profile.sector = emp.sector or user_profile.sector
                        user_profile.organisation_type = emp.organisation_type or user_profile.organisation_type
                        user_profile.office_address = emp.office_address or user_profile.office_address
                        user_profile.payroll_officer_name = emp.payroll_officer_name or user_profile.payroll_officer_name
                        user_profile.payroll_officer_phone = emp.work_phone or user_profile.payroll_officer_phone
                        user_profile.payroll_officer_email = emp.work_email or user_profile.payroll_officer_email
                    except Exception:
                        pass
                else:
                    # Preregistration OFF: use whatever the user entered
                    for f in ['sector', 'organisation_type', 'office_address', 'payroll_officer_name', 'payroll_officer_phone', 'payroll_officer_email']:
                        val = cd.get(f)
                        if val is not None:
                            setattr(user_profile, f, val)

                user_profile.save()
                messages.success(request, 'Employer information updated successfully!')
            return redirect('profile')
        else:
            employerinfoUpdateForm = EmployerInfoUpdateForm(initial=initial_data)
        import json as _json
        try:
            from admin1.models import Employer as _Emp, AdminSettings as _AS
            _s = _AS.objects.get(settings_name='setting1')
            if _s.employer_preregistration_required:
                _emp_data = {e.name: {'sector': e.sector or '', 'organisation_type': e.organisation_type or '', 'office_address': e.office_address or '', 'payroll_officer_phone': str(e.work_phone) if e.work_phone else '', 'payroll_officer_email': e.work_email or ''} for e in _Emp.objects.filter(active=True)}
            else:
                _emp_data = {}
        except Exception:
            _emp_data = {}
        return render(request, 'edit_employerinfo.html', {'nav': 'profile', 'form': employerinfoUpdateForm, 'user': user_profile, 'employer_data_json': _json.dumps(_emp_data)})
    return redirect('login_user')

##### PROFILE WIZARD ####

def edit_profile_wizard(request):
    """Unified multi-tab profile editor. Locked when user has an active loan."""
    if not request.user.is_authenticated:
        return redirect('login_user')

    uid = request.user.id
    user = UserProfile.objects.get(user_id=uid)
    profile_locked = bool(user.has_loan)

    # Which tab to show (default: personal)
    active_tab = request.GET.get('tab', 'personal')

    # Build all forms with current data as initial
    personal_form = PersonalInfoForm(initial={
        'first_name': user.first_name, 'middle_name': user.middle_name,
        'last_name': user.last_name, 'gender': user.gender,
        'date_of_birth': user.date_of_birth, 'marital_status': user.marital_status,
    })
    contact_form = AddressInfoForm(initial={
        'mobile1': user.mobile1, 'mobile2': user.mobile2,
        'resident_owner': user.resident_owner, 'residential_address': user.residential_address,
        'residential_province': user.residential_province, 'place_of_origin': user.place_of_origin,
        'province': user.province,
    })
    employer_form = EmployerInfoUpdateForm(initial={
        'sector': user.sector, 'employer': user.employer,
        'organisation_type': user.organisation_type, 'office_address': user.office_address,
        'payroll_officer_name': user.payroll_officer_name,
        'payroll_officer_phone': user.payroll_officer_phone,
        'payroll_officer_email': user.payroll_officer_email, 'deduction_category': user.deduction_category,
    })
    job_form = JobInfoUpdateForm(initial={
        'job_title': user.job_title, 'start_date': user.start_date,
        'pay_frequency': user.pay_frequency, 'last_paydate': user.last_paydate,
        'gross_pay': user.gross_pay, 'net_pay': user.net_pay,
        'employee_file_number': user.employee_file_number,
    })
    bank_form = BankAccountInfoForm(initial={
        'bank': user.bank, 'bank_account_name': user.bank_account_name,
        'bank_account_number': user.bank_account_number, 'bank_branch': user.bank_branch,
    })
    uploads_form = UserUploadForm(initial={
        'nid_number': user.nid_number, 'passport_number': user.passport_number,
        'drivers_license_number': user.drivers_license_number,
        'super_member_code': user.super_member_code, 'work_id_number': user.work_id_number,
    })

    if request.method == 'POST':
        if profile_locked:
            messages.error(request, 'Profile editing is locked while you have an active loan. Contact support if you need to make changes.', extra_tags='danger')
            return redirect('edit_profile_wizard')

        section = request.POST.get('section', 'personal')
        active_tab = section

        if section == 'personal':
            personal_form = PersonalInfoForm(request.POST, request.FILES)
            if personal_form.is_valid():
                for field in ['first_name', 'middle_name', 'last_name', 'gender', 'date_of_birth', 'marital_status']:
                    val = personal_form.cleaned_data.get(field)
                    if val is not None:
                        setattr(user, field, val)
                if 'propic' in request.FILES:
                    fileuploader(request, 'propic', user)
                user.save()
                messages.success(request, 'Personal information updated successfully!')
            return redirect(f"{request.path}?tab=personal")

        elif section == 'contact':
            contact_form = AddressInfoForm(request.POST)
            if contact_form.is_valid():
                for field in ['mobile1', 'mobile2', 'resident_owner', 'residential_address',
                               'residential_province', 'place_of_origin', 'province']:
                    val = contact_form.cleaned_data.get(field)
                    if val is not None:
                        setattr(user, field, val)
                user.save()
                messages.success(request, 'Contact & Address updated successfully!')
            return redirect(f"{request.path}?tab=contact")

        elif section == 'employer':
            employer_form = EmployerInfoUpdateForm(request.POST)
            if employer_form.is_valid():
                cd = employer_form.cleaned_data
                selected_employer_name = cd.get('employer') or user.employer
                user.employer = selected_employer_name
                if 'deduction_category' in cd:
                    user.deduction_category = cd.get('deduction_category') or None

                if employer_form._preregistration and selected_employer_name:
                    try:
                        from admin1.models import Employer as _Emp
                        emp = _Emp.objects.get(name=selected_employer_name, active=True)
                        user.sector = emp.sector or user.sector
                        user.organisation_type = emp.organisation_type or user.organisation_type
                        user.office_address = emp.office_address or user.office_address
                        user.payroll_officer_name = emp.payroll_officer_name or user.payroll_officer_name
                        user.payroll_officer_phone = emp.work_phone or user.payroll_officer_phone
                        user.payroll_officer_email = emp.work_email or user.payroll_officer_email
                    except Exception:
                        pass
                else:
                    for f in ['sector', 'organisation_type', 'office_address', 'payroll_officer_name', 'payroll_officer_phone', 'payroll_officer_email']:
                        val = cd.get(f)
                        if val is not None:
                            setattr(user, f, val)

                user.save()
                messages.success(request, 'Employer information updated successfully!')
            return redirect(f"{request.path}?tab=employer")

        elif section == 'job':
            job_form = JobInfoUpdateForm(request.POST)
            if job_form.is_valid():
                for field in ['job_title', 'start_date', 'pay_frequency', 'last_paydate',
                               'gross_pay', 'net_pay', 'employee_file_number']:
                    val = job_form.cleaned_data.get(field)
                    if val is not None:
                        setattr(user, field, val)
                user.save()
                try:
                    percent_of_gross = AdminSettings.objects.get(settings_name='setting1').percentage_of_gross
                    if user.gross_pay:
                        user.repayment_limit = (Decimal(percent_of_gross) / Decimal(100.0)) * Decimal(user.gross_pay)
                        user.save()
                except Exception:
                    pass
                messages.success(request, 'Job details updated successfully!')
            return redirect(f"{request.path}?tab=job")

        elif section == 'bank':
            bank_form = BankAccountInfoForm(request.POST)
            if bank_form.is_valid():
                for field in ['bank', 'bank_account_name', 'bank_account_number', 'bank_branch']:
                    val = bank_form.cleaned_data.get(field)
                    if val is not None:
                        setattr(user, field, val)
                if 'bank_standing_order' in request.FILES:
                    fileuploader(request, 'bank_standing_order', user)
                user.save()
                messages.success(request, 'Bank account updated successfully!')
            return redirect(f"{request.path}?tab=bank")

        elif section == 'uploads':
            uploads_form = UserUploadForm(request.POST, request.FILES)
            if uploads_form.is_valid():
                for file_field in ['nid', 'passport', 'drivers_license', 'superid', 'work_id']:
                    if file_field in request.FILES:
                        fileuploader(request, file_field, user)
                for field in ['nid_number', 'passport_number', 'drivers_license_number',
                               'super_member_code', 'work_id_number']:
                    val = uploads_form.cleaned_data.get(field)
                    if val:
                        setattr(user, field, val)
                user.save()
                messages.success(request, 'Personal ID documents updated successfully!')
            return redirect(f"{request.path}?tab=uploads")

    import json as _json
    try:
        from admin1.models import Employer as _Emp, AdminSettings as _AS
        _s = _AS.objects.get(settings_name='setting1')
        if _s.employer_preregistration_required:
            _emp_data = {e.name: {'sector': e.sector or '', 'organisation_type': e.organisation_type or '', 'office_address': e.office_address or '', 'work_phone': str(e.work_phone) if e.work_phone else '', 'work_email': e.work_email or ''} for e in _Emp.objects.filter(active=True)}
        else:
            _emp_data = {}
    except Exception:
        _emp_data = {}
    context = {
        'nav': 'profile',
        'user': user,
        'profile_locked': profile_locked,
        'active_tab': active_tab,
        'personal_form': personal_form,
        'contact_form': contact_form,
        'employer_form': employer_form,
        'job_form': job_form,
        'bank_form': bank_form,
        'uploads_form': uploads_form,
        'employer_data_json': _json.dumps(_emp_data),
    }
    return render(request, 'edit_profile_wizard.html', context)


##### SME PROFILE MANAGEMENT ####

def sme_profile(request):
    
    if request.user.is_authenticated:
        current_user = request.user
        uid = request.user.id
        user = UserProfile.objects.get(user_id=uid)
        
        try:
            smeprofile = SMEProfile.objects.get(owner_id=user.id)
        except:
            messages.info(request,'You can add your sme details by submitting the form', extra_tags='info')
            return redirect('edit_sme_profile')  
        return render(request, 'sme_profile.html', { 'nav':'sme_profile','current_user': current_user, 'user': user, 'smeprofile': smeprofile })
    return redirect('login_user')

def edit_sme_profile(request):
    
    if request.user.is_authenticated:
        uid = request.user.id
        user = UserProfile.objects.get(user_id=uid)
        
        try:
            smeprofile = SMEProfile.objects.get(owner_id=user)
            initial_profile_data = {
                'category' : smeprofile.category,
                'trading_name': smeprofile.trading_name,
                'registered_name': smeprofile.registered_name,
                'business_address': smeprofile.business_address,
                'email': smeprofile.email,
                'phone': smeprofile.phone,
                'website': smeprofile.website,
                'ipa_registration_number': smeprofile.ipa_registration_number,
                'tin_number': smeprofile.tin_number,
            }

        except:
            initial_profile_data = {}

        if request.method == 'POST':
            profileform = SMEProfileForm(request.POST)

            if user.first_name == '' and user.last_name == '':
                messages.info(request, 'You need to update your personal information first.', extra_tags='info')
                return redirect('edit_personalinfo')

            if profileform.is_valid():
                try:
                    smeprofile = SMEProfile.objects.get(owner_id=user.id)
                    existence = 1
                except:
                    smeprofile = SMEProfile.objects.create(owner_id=user.id)
                    existence = 0

                smeprofile.category = profileform.cleaned_data['category']
                smeprofile.save()
                smeprofile.trading_name = profileform.cleaned_data['trading_name']
                smeprofile.save()
                smeprofile.registered_name = profileform.cleaned_data['registered_name']
                smeprofile.save()
                smeprofile.business_address = profileform.cleaned_data['business_address']
                smeprofile.save()
                smeprofile.email = profileform.cleaned_data['email']
                smeprofile.save()
                smeprofile.phone = profileform.cleaned_data['phone']
                smeprofile.save()
                smeprofile.website = profileform.cleaned_data['website']
                smeprofile.save()
                smeprofile.ipa_registration_number = profileform.cleaned_data['ipa_registration_number']
                smeprofile.save()
                smeprofile.tin_number = profileform.cleaned_data['tin_number']
                smeprofile.save()
                user.has_sme = 1
                user.save()
                
                if existence == 1:
                    messages.success(request, 'SME Profile updated successfully.')
                else:
                    messages.success(request, 'SME Profile Created successfully.')
                return redirect('sme_profile')
        else:
            profileform = SMEProfileForm(initial=initial_profile_data)
            
        return render(request, 'edit_sme_profile.html', { 'nav': 'sme_profile', 'profileform': profileform, 'user':user })   
                
    return redirect('login_user')

def edit_sme_profile_uploads(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user = UserProfile.objects.get(user_id=uid)
        
        if request.method == 'POST':
            
            smeuploadsform = SMEUploadsForm(request.POST)
            
            if user.first_name == '' and user.last_name == '':
                messages.info(request, 'You need to update your personal information first.', extra_tags='info')
                return redirect('edit_personalinfo')
            
            if smeuploadsform.is_valid():
                try:
                    smeprofile = SMEProfile.objects.get(owner_id=user.id)
                    
                except:
                    messages.error(request, "You need to update business information first.", extra_tags="info")
                    return redirect('edit_sme_profile')
                
                if 'ipa_certificate' in request.FILES:
                    ipa_certificate = request.FILES['ipa_certificate']
                    fsipa_certificate = FileSystemStorage()
                    newipa_certificate_name = f'{user.first_name}_{user.last_name}_IPA_CERTIFICATE_{ipa_certificate.name}'
                    ipa_certificate_filename = fsipa_certificate.save(newipa_certificate_name, ipa_certificate)
                    ipa_certificate_url = fsipa_certificate.url(ipa_certificate_filename)
                    smeprofile.ipa_certificate_url = ipa_certificate_url
                    smeprofile.save()
                    messages.success(request, 'IPA Certificate uploaded successfully...')
                    
                if 'tin_certificate' in request.FILES:
                    tin_certificate = request.FILES['tin_certificate']
                    fstin_certificate = FileSystemStorage()
                    newtin_certificate_name = f'{user.first_name}_{user.last_name}_TIN_CERTIFICATE_{tin_certificate.name}'
                    tin_certificate_filename = fstin_certificate.save(newtin_certificate_name, tin_certificate)
                    tin_certificate_url = fstin_certificate.url(tin_certificate_filename)
                    smeprofile.tin_certificate_url = tin_certificate_url
                    smeprofile.save()
                    messages.success(request, 'TIN Certificate uploaded successfully...')
                
                if 'cash_flow' in request.FILES:
                    cash_flow = request.FILES['cash_flow']
                    fscash_flow = FileSystemStorage()
                    newcash_flow_name = f'{user.first_name}_{user.last_name}_CASH_FLOW_{cash_flow.name}'
                    cash_flow_filename = fscash_flow.save(newcash_flow_name, cash_flow)
                    cash_flow_url = fscash_flow.url(cash_flow_filename)
                    smeprofile.cash_flow_url = cash_flow_url
                    smeprofile.save()
                    messages.success(request, 'Cash Flow uploaded successfully...')
                
                if 'sme_bank_statement' in request.FILES:
                    sme_bank_statement = request.FILES['sme_bank_statement']
                    fssme_bank_statement = FileSystemStorage()
                    newsme_bank_statement_name = f'{user.first_name}_{user.last_name}_SME_BANK_STATEMENT_{sme_bank_statement.name}'
                    sme_bank_statement_filename = fssme_bank_statement.save(newsme_bank_statement_name, sme_bank_statement)
                    sme_bank_statement_url = fssme_bank_statement.url(sme_bank_statement_filename)
                    smeprofile.sme_bank_statement_url = sme_bank_statement_url
                    smeprofile.save()
                    messages.success(request, 'SME Bank Statement uploaded successfully...')
                    
                if 'location_pic' in request.FILES:
                    location_pic = request.FILES['location_pic']
                    fslocation_pic = FileSystemStorage()
                    newlocation_pic_name = f'{user.first_name}_{user.last_name}_location_pic_{location_pic.name}'
                    location_pic_filename = fslocation_pic.save(newlocation_pic_name, location_pic)
                    location_pic_url = fslocation_pic.url(location_pic_filename)
                    smeprofile.location_pic_url = location_pic_url
                    smeprofile.save()
                    messages.success(request, 'Location Picture uploaded successfully...')
                
                messages.success(request, 'SME Profile Uploads updated Successfully!')
                return redirect('sme_profile')
            
        else:
            smeuploadsform = SMEUploadsForm()
                    
        return render(request, 'edit_sme_profile_uploads.html', { 'nav': 'sme_profile', 'smeuploadsform': smeuploadsform, 'user':user})   
                
    return redirect('login_user')

def edit_sme_profile_bank(request):
    if request.user.is_authenticated:
        uid = request.user.id
        user = UserProfile.objects.get(user_id=uid)
        
        try:
            smeprofile = SMEProfile.objects.get(owner_id=user)
            
            initial_bank_data = {
                'bank': smeprofile.bank,
                'bank_account_name': smeprofile.bank_account_name,
                'bank_account_number': smeprofile.bank_account_number,
                'bank_branch': smeprofile.bank_branch,
                'bank_standing_order_url': smeprofile.bank_standing_order_url
            }
            
        except:
            initial_bank_data = {}
        
        if request.method == 'POST':
            smebankinfoform = SMEBankInfoForm(request.POST)
            
            if user.first_name == '' and user.last_name == '':
                messages.info(request, 'You need to update your personal information first.', extra_tags='info')
                return redirect('edit_personalinfo')           
            
            if smebankinfoform.is_valid():
                try:
                    smeprofile = SMEProfile.objects.get(owner_id=user.id)
                   
                except:
                    messages.error(request, "You need to update business information first.", extra_tags="info")
                    return redirect('edit_sme_profile')
                
                smeprofile.bank = smebankinfoform.cleaned_data['bank']
                smeprofile.save()
                smeprofile.bank_account_name = smebankinfoform.cleaned_data['bank_account_name']
                smeprofile.save()
                smeprofile.bank_account_number = smebankinfoform.cleaned_data['bank_account_number']
                smeprofile.save()
                smeprofile.bank_branch = smebankinfoform.cleaned_data['bank_branch']
                smeprofile.save()
                
                if 'bank_standing_order' in request.FILES:
                    bank_standing_order = request.FILES['bank_standing_order']
                    fsbank_standing_order = FileSystemStorage()
                    bank_standing_order_name = f'{smeprofile.bank_account_name}_SME_BANK_STANDING_ORDER_{bank_standing_order.name}'
                    bank_standing_order_filename = fsbank_standing_order.save(bank_standing_order_name, bank_standing_order)
                    bank_standing_order_url = fsbank_standing_order.url(bank_standing_order_filename)
                    smeprofile.bank_standing_order_url = bank_standing_order_url
                    smeprofile.save()
                    messages.success(request, 'SME Bank Account Standing Order uploaded successfully...')
                
                messages.success(request, 'SME Bank Account Information updated Successfully!')
                return redirect('sme_profile')

        else:
            smebankinfoform = SMEBankInfoForm(initial=initial_bank_data)
                    
        return render(request, 'edit_sme_profile_bank.html', { 'nav':'sme_profile', 'smebankinfoform':smebankinfoform, 'user':user })

    return redirect('login_user')

##############
##  CREDIT ASSESSMENT (Statement of Position, referee & previous employer)
##############

@login_check
@credit_assessment_check
def edit_refereeinfo(request):
    uid = request.user.id
    user = UserProfile.objects.get(user_id=uid)
    form = RefereeInfoForm(instance=user)

    if request.method == 'POST':
        form = RefereeInfoForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Referee information updated successfully', extra_tags="info")
            return redirect('profile')

    return render(request, 'edit_refereeinfo.html', {'nav': 'profile', 'form': form, 'user': user})

@login_check
@credit_assessment_check
def edit_previousemployer(request):
    uid = request.user.id
    user = UserProfile.objects.get(user_id=uid)
    form = PreviousEmployerInfoForm(instance=user)

    if request.method == 'POST':
        form = PreviousEmployerInfoForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Previous employer information updated successfully', extra_tags="info")
            return redirect('profile')

    return render(request, 'edit_previousemployer.html', {'nav': 'profile', 'form': form, 'user': user})

@login_check
@credit_assessment_check
def edit_statement_of_position(request):
    uid = request.user.id
    user = UserProfile.objects.get(user_id=uid)
    statement = getattr(user, 'statement_of_position', None)

    form = StatementOfPositionForm(instance=statement)

    if request.method == 'POST':
        form = StatementOfPositionForm(request.POST, instance=statement)
        if form.is_valid():
            statement = form.save(commit=False)
            statement.user = user
            statement.save()
            messages.success(request, 'Statement of Position updated successfully', extra_tags="info")
            return redirect('statement_of_position')

    return render(request, 'edit_statement_of_position.html', {'nav': 'statement_of_position', 'form': form, 'user': user})

@login_check
@credit_assessment_check
def statement_of_position(request):
    uid = request.user.id
    user = UserProfile.objects.get(user_id=uid)
    statement = getattr(user, 'statement_of_position', None)

    return render(request, 'statement_of_position.html', {'nav': 'statement_of_position', 'user': user, 'statement_of_position': statement})
