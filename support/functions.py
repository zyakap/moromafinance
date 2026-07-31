#for id_generator
import string
import random

from django.conf import settings

#to send email
from django.conf import settings
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.utils.html import strip_tags

#admin sender email
from admin1.models import AdminSettings
try:
    sender = AdminSettings.objects.get(settings_name='setting1').default_from_email
    support_email = AdminSettings.objects.get(settings_name='setting1').support_email
except:
    sender = settings.DEFAULT_FROM_EMAIL
    support_email = settings.SUPPORT_EMAIL

from django.conf import settings
sender = settings.DEFAULT_SENDER_EMAIL

# id_generator
def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

#to send HTML EMAIL
def send_email(user, sub=None, gr='Hi', msg=None, msg_details='', cta='no', btnlab='Take Action', btnlink='#'):
   
    subject = sub
    greeting = gr
    message = msg
    details = msg_details
    calltoaction = cta
    btn_label = btnlab
    btn_link = btnlink
    
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
        
    })
    text_content = strip_tags(email_content)
    from accounts.functions import work_email_allowed as _wea
    _recipients = [e for e in [settings.ADMIN_RECEIVER, user.email, _wea(user)] if e]
    email = EmailMultiAlternatives(subject,text_content,sender,_recipients)
    email.attach_alternative(email_content, "text/html")

    try: 
        email.send()
        status = 1
    except:
        status = 0

    return status

def email_admin(user, sub=None, msg=None, msg_details='', cta='no', btnlab='Take Action', btnlink='#', attachcheck='no', path=''):
  
    support = support_email
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
    email = EmailMultiAlternatives(subject,text_content,user.email,(support,))
    email.attach_alternative(email_content, "text/html")

    if attachcheck == 'yes':
        email.attach_file(path)

    try: 
        email.send()
        status = 1
    except:
        status = 0

    return status
  