#for id_generator
import string
import random

#to send email
from django.conf import settings

from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.utils.html import strip_tags


from urllib import request
from django.shortcuts import render, redirect
from accounts.models import UserProfile, StaffProfile
from loan.models import LoanFile
from django.contrib import messages

#admin sender email
from admin1.models import AdminSettings
sender = settings.DEFAULT_SENDER_EMAIL

from django.conf import settings

# id_generator
def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

#FILES UPLOAD
from django.core.files.storage import FileSystemStorage


######################
#START OF FUNCTIONS
######################

#to send email
def send_email(self, *content):
    """
    Sends user email with specified parameters
    """
    econtent = []
    for arg in content:
        econtent.append(arg)
        
    subject,greeting,message,details, btn_label, btn_link = econtent[0], econtent[1], econtent[2], econtent[3],  econtent[4], econtent[5]
    domain = settings.DOMAIN
    user = self.user
    subject = econtent[0]
    #email content
    greeting = econtent[1]
    message = econtent[2]
    details = econtent[3]
    btn_label = econtent[4]
    btn_link = econtent[5]

    email_content = render_to_string('custom/email_temp_general.html', {
        'email_subject': subject,
        'greeting': greeting,
        'message': message,
        'message_details': details,
        'action_btn_1': btn_label,
        'action_btn_1_link' : btn_link,
        'user': user,
        'domain': domain,
        
    })
    text_content = strip_tags(email_content)
    email = EmailMultiAlternatives(subject,text_content,sender,['zyakap@outlook.com', 'support@webmasta.com.pg', user.email ])
    email.attach_alternative(email_content, "text/html")

    try: 
        email.send()
        status = 1
    except Exception:
        status = 0

    return status

def email_compilation(request):
    
    #send email to user
    domain = settings.DOMAIN
    
    subject = ''
    ''' if header_cta == 'yes' '''
    cta_label = ''
    cta_link = ''

    greeting = ''
    message = ''
    message_details = ''

    ''' if cta == 'yes' '''
    cta_btn1_label = ''
    cta_btn1_link = ''
    cta_btn2_label = ''
    cta_btn2_link = ''

    ''' if promo == 'yes' '''
    catchphrase = ''
    promo_title = ''
    promo_message = ''
    promo_cta = ''
    promo_cta_link = ''
    
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
    email = EmailMultiAlternatives(subject,text_content,sender,['zyakap@outlook.com', 'support@webmasta.com.pg', user.email ])
    email.attach_alternative(email_content, "text/html")

    try: 
        email.send()
        messages.success(request, "Success Message")
    except Exception:
        messages.error(request, 'Error Message', extra_tags='danger')
        
    return redirect('view_client', uid)

##### CHECK STAFF DECORATOR
def staff_or_admin_check(func):
    """Allow staff members AND admins (superusers). Used for shared surfaces
    like the Loan Reports engine."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_user')
        if request.user.is_superuser:
            return func(request, *args, **kwargs)
        profile = UserProfile.objects.filter(user_id=request.user.id).first()
        if profile is not None and profile.category in ('STAFF', 'ADMIN'):
            return func(request, *args, **kwargs)
        messages.error(request, "You do not have permission to view this page.", extra_tags="danger")
        return redirect('dashboard')
    return wrapper


def check_staff(func):
    
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_user')

        # A logged-in user without a profile must not 500 the page.
        staffuser = UserProfile.objects.filter(user_id=request.user.id).first()
        if staffuser is None or staffuser.category != 'STAFF':
            messages.error(request, "You do not have permission to view this page.", extra_tags="danger")
            return redirect('dashboard')

        rv = func(request, *args, **kwargs)
        return rv

    return wrapper

##### CHECK STAFF DECORATOR
def admin_check(func):
    
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_user')
    
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to view this page.", extra_tags="danger")

            return redirect( 'dashboard')
        
        rv = func(request, *args, **kwargs)
        return rv

    return wrapper

##### MANAGER REVIEW DECORATOR
def manager_check(func):
    """Gate manager-portal views: requires the Manager Role setting to be on
    (AdminSettings.role_manager_enabled) and the logged-in staff member's
    type_of_staff to be MANAGER, ADMIN or DIRECTOR."""

    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_user')

        setting = AdminSettings.objects.filter(settings_name='setting1').first()
        if setting is None or setting.role_manager_enabled != 'YES':
            messages.error(request, "The manager role is not enabled for this account.", extra_tags="danger")
            return redirect('dashboard')

        user_profile = UserProfile.objects.filter(user=request.user).first()
        staff_profile = StaffProfile.objects.filter(user=user_profile).first() if user_profile else None
        if staff_profile is None or staff_profile.type_of_staff not in ('MANAGER', 'ADMIN', 'DIRECTOR'):
            messages.error(request, "You do not have manager permissions.", extra_tags="danger")
            return redirect('dashboard')

        rv = func(request, *args, **kwargs)
        return rv

    return wrapper


def credit_assessment_check(func):
    """Gate Credit Assessment views (Statement of Position, referee &
    previous-employer capture) behind AdminSettings.credit_assessment_enabled."""

    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_user')

        setting = AdminSettings.objects.filter(settings_name='setting1').first()
        if setting is None or setting.credit_assessment_enabled != 'YES':
            messages.error(request, "Credit Assessment is not enabled for this account.", extra_tags="danger")
            return redirect('profile')

        rv = func(request, *args, **kwargs)
        return rv

    return wrapper

##### RATE LIMIT DECORATOR
def _client_ip(request):
    fwd = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def rate_limit(max_attempts=10, window_seconds=300, methods=('POST',)):
    """Throttle a view by client IP using the shared cache. Defaults to 10
    POST requests per 5 minutes. Intended for login / public form endpoints to
    blunt brute-force and spam. Relies on a cross-worker cache (see CACHES)."""
    def decorator(func):
        def wrapper(request, *args, **kwargs):
            if request.method in methods:
                from django.core.cache import cache
                key = f'ratelimit:{func.__name__}:{_client_ip(request)}'
                attempts = cache.get(key, 0)
                if attempts >= max_attempts:
                    messages.error(
                        request,
                        'Too many attempts. Please wait a few minutes and try again.',
                        extra_tags='danger',
                    )
                    return redirect(request.path)
                # add() seeds the counter with a TTL; incr() bumps it within the window.
                cache.add(key, 0, timeout=window_seconds)
                try:
                    cache.incr(key)
                except ValueError:
                    cache.set(key, 1, timeout=window_seconds)
            return func(request, *args, **kwargs)
        return wrapper
    return decorator


##### Login DECORATOR
def login_check(func):
    
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect('login_user')

        rv = func(request, *args, **kwargs)
        return rv

    return wrapper

##### UPLOAD VALIDATION
# Allowed document types for KYC / payment uploads, and a hard size cap.
ALLOWED_UPLOAD_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB


def validate_upload(request, fhandle):
    """Reject oversized files and disallowed extensions. Returns True if OK,
    otherwise flashes an error message and returns False."""
    import os as _os
    if fhandle is None:
        return False
    ext = _os.path.splitext(fhandle.name)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        messages.error(request, f'File type "{ext or "unknown"}" is not allowed.', extra_tags='danger')
        return False
    if fhandle.size and fhandle.size > MAX_UPLOAD_BYTES:
        messages.error(request, 'File is too large (max 15 MB).', extra_tags='danger')
        return False
    return True


##### FILE UPLOAD HANDLER
def fileuploader(request, file_name, user_profile):
    upload_type = f'{file_name}'.upper()
    fhandle = request.FILES[f'{file_name}']
    if not validate_upload(request, fhandle):
        return
    fs_instance = FileSystemStorage()
    renamed = f'{user_profile.first_name}_{user_profile.last_name}_{upload_type}_{fhandle.name}'
    filename = fs_instance.save(renamed, fhandle)
    file_url = fs_instance.url(filename)
    db_name = f'{file_name}_url'
    setattr(user_profile, db_name, file_url)
    user_profile.save()
    messages.success(request, f'{upload_type} uploaded successfully...')

##### FILE UPLOAD HANDLER
def loanfileuploader(request, file_name, user_profile, loan):
    
    try:
        loanfile = LoanFile.objects.get(loan=loan)
    except Exception:
        loanfile = LoanFile.objects.create(loan=loan)

    upload_type = f'{file_name}'.upper()
    fhandle = request.FILES[f'{file_name}']
    if not validate_upload(request, fhandle):
        return
    fs_instance = FileSystemStorage()
    renamed = f'{user_profile.first_name}_{user_profile.last_name}_{loan.ref}_{upload_type}_{fhandle.name}'
    filename = fs_instance.save(renamed, fhandle)
    file_url = fs_instance.url(filename)
    db_name = f'{file_name}_url'
    # Set both file field and URL field
    setattr(loanfile, file_name, filename)  # Assuming file_name corresponds to application_form
    setattr(loanfile, db_name, file_url)
    loanfile.save()
    messages.success(request, f'{upload_type} uploaded successfully...')


def testloanfileuploader(request, file_name, user_profile, loan):
    try:
        loanfile = LoanFile.objects.get(loan=loan)
    except LoanFile.DoesNotExist:
        loanfile = LoanFile.objects.create(loan=loan)

    upload_type = file_name.upper()
    fhandle = request.FILES.get(file_name)

    if fhandle and validate_upload(request, fhandle):
        fs_instance = FileSystemStorage()
        renamed = f'{user_profile.first_name}_{user_profile.last_name}_{loan.ref}_{upload_type}_{fhandle.name}'
        filename = fs_instance.save(renamed, fhandle)
        file_url = fs_instance.url(filename)
        
        # Set both file field and URL field
        setattr(loanfile, file_name, filename)  # Assuming file_name corresponds to application_form
        setattr(loanfile, f'{file_name}_url', file_url)
        loanfile.save()
        
        messages.success(request, f'{upload_type} uploaded successfully...')
    else:
        messages.error(request, f'No {upload_type} uploaded')


def get_default_repayment_limit():
    """Return the admin-configured default repayment limit, or None if not set."""
    try:
        from admin1.models import AdminSettings
        setting = AdminSettings.objects.get(settings_name='setting1')
        return setting.default_repayment_limit
    except Exception:
        return None


def get_field_settings():
    try:
        from admin1.models import FormFieldSetting
        result = {}
        for setting in FormFieldSetting.objects.all():
            if setting.form_name not in result:
                result[setting.form_name] = {}
            result[setting.form_name][setting.field_name] = setting.enabled
        return result
    except Exception:
        return {}


def work_email_allowed(user):
    """
    Return the work_email to include in system email lists, or None if suppressed.

    Rules (applied in order):
      1. Global setting (AdminSettings.email_system_to_work_email) must be True.
      2. Per-client setting (UserProfile.notify_work_email) must be True.
      3. The user must actually have a work_email set.
    """
    try:
        from admin1.models import AdminSettings
        setting = AdminSettings.objects.get(settings_name='setting1')
        if not setting.email_system_to_work_email:
            return None
    except Exception:
        pass
    if not getattr(user, 'notify_work_email', True):
        return None
    return getattr(user, 'work_email', None) or None