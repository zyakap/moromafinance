import json
import logging
from django.shortcuts import render
from time import sleep
from celery import shared_task
from celery.result import AsyncResult
from .functions import send_email, send_email_toworkemail
from .models import Message, MessageLog
from accounts.models import UserProfile

logger = logging.getLogger(__name__)


def dispatch_task(task, *args, **kwargs):
    """Queue a Celery task, but if the broker is unreachable (no worker/redis),
    fall back to running it synchronously so the request still succeeds instead
    of raising a 500. Returns True if it was queued, False if run inline."""
    try:
        task.delay(*args, **kwargs)
        return True
    except Exception:
        logger.warning("Celery broker unavailable; running %s synchronously.", getattr(task, 'name', task), exc_info=True)
        task(*args, **kwargs)
        return False

@shared_task
def notify_clients(msg):
    
    sleep(20)
   


@shared_task
def create_message_asc(userid_list, subject, content, message_id, attach=0, attachpath='', category=None):

    message = Message.objects.get(id=message_id)
    if attach == 1:
        attachcheck = 'yes'
        path = attachpath
    else:
        attachcheck = 'no'
        path = ''
    
    email_sent = []
    email_not_sent = []
    email_sent_work = []
    email_not_sent_work = []
    recipients_personal = 0
    recipients_work = 0

    my_dict = json.loads(userid_list)
    userids = my_dict["user_id_list"]

    user_list = []
    for uid in userids:
        user = UserProfile.objects.get(id=uid)
        user_list.append(user)

    for user in user_list:
        
        try:
            message_log = MessageLog.objects.get(user=user)
        except:
            message_log = MessageLog(user=user)

        if message_log.msgq == '':
            message_log.msgq = f'{str(message.id)}'
        else:
            message_log.msgq += f',{str(message.id)}'
        
        if message_log.msglog == '':
            message_log.msglog = f'{str(message.id)}'
        else:
            message_log.msglog += f',{str(message.id)}'
        
        message_log.save()
        msgtrid = f'{user.id}U{message.id}'
        status = send_email(user, sub=subject, msg=content, msgid=msgtrid, attachcheck=attachcheck, path=path, category=category)
        if status == 1:
            recipients_personal += 1
            email_sent.append(user.id)
            if message.emailto_personal == '':
                message.emailto_personal += f'{str(user.id)}'
            else:
                message.emailto_personal += f',{str(user.id)}'
            message.save()
            
            if message_log.msgbyemail == '':
                message_log.msgbyemail = f'{str(message.id)}'
            else:
                message_log.msgbyemail += f',{str(message.id)}'
            message_log.save()
            
        else:
            recipients_personal += 1
            email_not_sent.append(user.id)
            if message_log.msg_not_emailed == '':
                message_log.msg_not_emailed = f'{str(message.id)}'
            else:
                message_log.msg_not_emailed += f',{str(message.id)}'
            message_log.save()
            
        msgtridw = f'{user.id}W{message.id}'
        status_work = send_email_toworkemail(user, sub=subject, msg=content, msgid=msgtridw, attachcheck=attachcheck, path=path, category=category)
        if status_work == 1:
            recipients_work += 1
            email_sent_work.append(user.id)
            if message.emailto_work == '':
                message.emailto_work += f'{str(user.id)}'
            else:
                message.emailto_work += f',{str(user.id)}'
            message.save()
            
            if message_log.msgbyemail_work == '':
                message_log.msgbyemail_work = f'{str(message.id)}'
            else:
                message_log.msgbyemail_work += f',{str(message.id)}'
            message_log.save()
            
        else:
            from accounts.functions import work_email_allowed as _wea
            if _wea(user) is None:
                recipients_work += 0
            else:
                recipients_work += 1
            email_not_sent_work.append(user.id)
            if message_log.msg_not_emailed_work == '':
                message_log.msg_not_emailed_work = f'{str(message.id)}'
            else:
                message_log.msg_not_emailed_work += f',{str(message.id)}'
            message_log.save()
            
        
        message.recipients_personal = recipients_personal
        message.recipients_work = recipients_work

        email_sent_str = ','.join(str(e) for e in email_sent)
        email_not_sent_str = ','.join(str(e) for e in email_not_sent)
        email_sent_work_str = ','.join(str(e) for e in email_sent_work)
        email_not_sent_work_str = ','.join(str(e) for e in email_not_sent_work)

        message.email_sent = email_sent_str
        message.email_not_sent = email_not_sent_str
        message.email_sent_work = email_sent_work_str
        message.email_not_sent_work = email_not_sent_work_str
        message.save()

    message.delivery_status = 'done'
    message.save()