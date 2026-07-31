#for id_generator
import string
import random
from django.template import Template, Context
from django.conf import settings


#FILES UPLOAD
from django.core.files.storage import FileSystemStorage

#sms
from django.core.mail import send_mail

#to send email
from django.conf import settings
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.utils.html import strip_tags

#admin sender email
from admin1.models import AdminSettings
sender = settings.DEFAULT_SENDER_EMAIL

from loan.models import Loan

def send_sms(request, msg=None, phone=None):
    message = msg
    phone_number = phone
    email_address = phone_number + "@example.com"  # this is the email-to-SMS gateway address
    send_mail(
        "SMS Message",
        message,
        "from@example.com",
        [email_address],
        fail_silently=False,
    )

def render_message_content(user, category, content):

    context = {
    'first_name': user.first_name,
    'last_name': user.last_name,
    'job_title': user.job_title,
    'employer': user.employer,
    }

    if category == 'PENDING LOANS' or category == 'APPROVED LOANS' or category == 'FUNDED LOANS' or category == 'RUNNING LOANS' or category == 'DEAFULT LOANS' or category == 'RECOVERY LOANS' or category == 'BAD LOANS':
        
        loans = Loan.objects.filter(owner=user)

        if category == 'PENDING LOANS':
            loan = loans.filter(category='PENDING').order_by('-id')[0]

        elif category == 'APPROVED LOANS':
            loan = loans.filter(category='APPROVED').order_by('-id')[0]

        elif category == 'FUNDED LOANS':
            loan = loans.filter(category='FUNDED').order_by('-id')[0]

        elif category == 'RUNNING LOANS':
            loan = loans.filter(category='FUNDED', status='RUNNING').order_by('-id')[0]

        elif category == 'DEAFULT LOANS':
            loan = loans.filter(category='FUNDED', status='DEFAULTED').order_by('-id')[0]

        elif category == 'RECOVERY LOANS':
            loan = loans.filter(category='FUNDED', status='RECOVERY').order_by('-id')[0]

        elif category == 'BAD LOANS':
            loan = loans.filter(category='FUNDED', status='BAD').order_by('-id')[0]

        context.update({'repayment': loan.repayment_amount,
                        'next_payment_date': loan.next_payment_date,
                        'total_arrears': loan.total_arrears,
                        'balance' : loan.total_outstanding,
                        'amount': loan.amount, })

    template = Template(content)
    return template.render(Context(context))

#to send HTML EMAIL
def send_email(user, sub=None, gr='', msg=None, msg_details='', cta='no', btn_lab='Take Action', b_link='#', msgid=None, attachcheck='no', path='', category=None):
    
    subject = sub
    greeting = gr
    unc_msg= msg
    details = msg_details
    calltoaction = cta
    btn_label = btn_lab
    btn_link = b_link
    msgtrid = msgid

    #contextualized Messagen from WYSIWYG editor
    message = render_message_content(user, category, unc_msg)
  
    email_content = render_to_string('custom/email_temp_general.html', {
        'subject': subject,
        'greeting': greeting,
        'message': message,
        'message_details': details,
        'cta': calltoaction,
        'cta_btn1_label': btn_label,
        'cta_btn1_link' : btn_link,
        'user': user,
        'domain': settings.DOMAIN,
        'msgtrid': msgtrid,
        'unc_msg': unc_msg,

    })

    text_content = strip_tags(email_content)
    email = EmailMultiAlternatives(subject,text_content,sender,(user.email,))
    email.attach_alternative(email_content, "text/html")

    if attachcheck == 'yes':
        email.attach_file(path)

    try: 
        email.send()
        status = 1
    except:
        status = 0

    return status

def send_email_toworkemail(user, sub=None, gr='', msg=None, msg_details='', cta='no', btn_lab='Take Action', b_link='#', msgid=None, attachcheck='no', path='', category=None):
    
    from accounts.functions import work_email_allowed as _wea
    _work_email = _wea(user)
    if not _work_email:
        status = 0
        return status
    subject = sub
    greeting = gr
    unc_msg = msg
    details = msg_details
    calltoaction = cta
    btn_label = btn_lab
    btn_link = b_link
    msgtrid = msgid

    #contextualized Messagen from WYSIWYG editor
    message = render_message_content(user, category, unc_msg)

    email_content = render_to_string('custom/email_temp_general.html', {
        'subject': subject,
        'greeting': greeting,
        'message': message,
        'message_details': details,
        'cta': calltoaction,
        'cta_btn1_label': btn_label,
        'cta_btn1_link' : btn_link,
        'user': user,
        'domain': settings.DOMAIN,
        'msgtrid': msgtrid,
       # 'first_name' : user.first_name,
       # 'last_name' : user.last_name,
       
    })
    text_content = strip_tags(email_content)
    email = EmailMultiAlternatives(subject,text_content,sender,[_work_email])
    email.attach_alternative(email_content, "text/html")

    if attachcheck == 'yes':
        email.attach_file(path)
        
    try: 
        email.send()
        status = 1
    except:
        status = 0

    return status

def email_admin(user, sub=None, gr='', msg=None, msg_details='', cta='no', btnlab='Take Action', btnlink='#', attachcheck='no', path=''):
  
    admin_email_address = settings.SUPPORT_EMAIL
    subject = sub
    message = msg
    details = msg_details
    calltoaction = cta
    btn_label = btnlab
    btn_link = btnlink

    email_content = render_to_string('custom/email_temp_to_admin.html', {
        'subject': subject,
        'message': message,
        'message_details': details,
        'cta': calltoaction,
        'cta_btn1_label': btn_label,
        'cta_btn1_link' : btn_link,
        'user': user,
        'domain': settings.DOMAIN,
        
    })
    text_content = strip_tags(email_content)
    email = EmailMultiAlternatives(subject,text_content,user.email,(admin_email_address,))
    email.attach_alternative(email_content, "text/html")

    if attachcheck == 'yes':
        email.attach_file(path)

    try: 
        email.send()
        status = 1
    except:
        status = 0

    return status


##### FILE UPLOAD HANDLER
def fileuploader(request, file_name, user_profile):
    upload_type = f'{file_name}'.upper()
    fhandle = request.FILES[f'{file_name}']
    fs_instance = FileSystemStorage()
    renamed = f'{user_profile.first_name}_{user_profile.last_name}_{upload_type}_{fhandle.name}'
    filename = fs_instance.save(renamed, fhandle)
    file_url = fs_instance.url(filename)
    db_name = f'{file_name}_url'
    setattr(user_profile, db_name, file_url)
    user_profile.save()
    messages.success(request, f'{upload_type} uploaded successfully...')
