import json
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages

from django.conf import settings

from accounts.models import UserProfile, UserActivityLog
from loan.models import Loan
from .forms import MessageForm
from .models import Message, MessageLog
from .tasks import create_message_asc, dispatch_task
from admin1.models import Location
from accounts.functions import check_staff, login_check, admin_check

#FILES UPLOAD
from django.core.files.storage import FileSystemStorage

domain = settings.DOMAIN


# Create your views here.
@check_staff
def create_message(request):
    staff_profile = UserProfile.objects.get(user_id=request.user.id)
    
    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():

            category = form.cleaned_data['category']
            location = form.cleaned_data['location']
            subject = form.cleaned_data['subject']
            content = form.cleaned_data['content']
            
            if not location is None:
                locationx = Location.objects.get(name=location)
                loans = Loan.objects.prefetch_related('owner').filter(location=locationx)
                users = UserProfile.objects.filter(location=locationx).exclude(category="STAFF")
            else:
                loans = Loan.objects.prefetch_related('owner').all()
                users = UserProfile.objects.exclude(category="STAFF")
            
            user_list = []

            if category == 'ALL USERS':
                user_list = users

            elif category == 'PENDING USERS':
                user_list = users.filter(activation=0)

            elif category == 'PENDING LOANS':
                filtered_loans = loans.filter(category='PENDING')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'APPROVED LOANS':
                filtered_loans = loans.filter(category='PENDING', status='APPROVED')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'FUNDED LOANS':
                filtered_loans = loans.filter(category='FUNDED')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'RUNNING LOANS':
                filtered_loans = loans.filter(category='FUNDED', status='RUNNING')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'DEAFULT LOANS':
                filtered_loans = loans.filter(category='FUNDED', status='DEFAULTED')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'RECOVERY LOANS':
                filtered_loans = loans.filter(category='FUNDED', status='RECOVERY')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'BAD LOANS':
                filtered_loans = loans.filter(category='FUNDED', status='BAD')
                for loan in filtered_loans:
                    user_list.append(loan.owner)
            
            if len(user_list) == 0:
                messages.error(request, f'There are no users matching the selections. Please change category or location where there are existing clients.', extra_tags='info')
                return render(request, 'create.html', {'nav': 'usermessages', 'form': form})
            else:
                user_id_list = []
                for user in user_list:
                    user_id_list.append(user.id)
                user_id_list_dict = {'user_id_list': user_id_list}
                userid_list_json = json.dumps(user_id_list_dict)

            message = Message.objects.create(subject=subject, content=content, category=category, sender=staff_profile, location=location)
            mid = message.id

            if 'attachment' in request.FILES:
                attachment = request.FILES['attachment']
                fsattachment = FileSystemStorage()
                newattachment_name = f'{mid}-MSG-ATTACHMENT-{attachment.name}'
                attachment_filename = fsattachment.save(newattachment_name, attachment)
                attachment_url = fsattachment.url(attachment_filename)
                message.attachment_url = attachment_url
                message.attachment_name = attachment_filename
                message.save()
                messages.success(request, 'Attachment uploaded successfully...')
                attachment_check = 1
                attachmentpath = f'media/{attachment_filename}'
            else:
                attachment_check = 0
                attachmentpath = ''    

            dispatch_task(create_message_asc, userid_list_json, subject, content, mid, attach=attachment_check, attachpath=attachmentpath, category=category)

            mid = message.id

            return redirect('delivering_message', mid)
    else:
        form = MessageForm()
    
    context = {

        'nav': 'usermessages',
        'form': form,
    }

    return render(request, 'create.html', context )

@admin_check
def create_message_admin(request):
    staff_profile = UserProfile.objects.get(user_id=request.user.id)
    
    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():

            category = form.cleaned_data['category']
            location = form.cleaned_data['location']
            subject = form.cleaned_data['subject']
            content = form.cleaned_data['content']
            
            if not location is None:
                locationx = Location.objects.get(name=location)
                loans = Loan.objects.prefetch_related('owner').filter(location=locationx)
                users = UserProfile.objects.filter(location=locationx).exclude(category="STAFF")
            else:
                loans = Loan.objects.prefetch_related('owner').all()
                users = UserProfile.objects.exclude(category="STAFF")
            
            user_list = []

            if category == 'ALL USERS':
                user_list = users

            elif category == 'PENDING USERS':
                user_list = users.filter(activation=0)

            elif category == 'PENDING LOANS':
                filtered_loans = loans.filter(category='PENDING')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'APPROVED LOANS':
                filtered_loans = loans.filter(category='PENDING', status='APPROVED')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'FUNDED LOANS':
                filtered_loans = loans.filter(category='FUNDED')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'RUNNING LOANS':
                filtered_loans = loans.filter(category='FUNDED', status='RUNNING')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'DEAFULT LOANS':
                filtered_loans = loans.filter(category='FUNDED', status='DEFAULTED')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'RECOVERY LOANS':
                filtered_loans = loans.filter(category='FUNDED', status='RECOVERY')
                for loan in filtered_loans:
                    user_list.append(loan.owner)

            elif category == 'BAD LOANS':
                filtered_loans = loans.filter(category='FUNDED', status='BAD')
                for loan in filtered_loans:
                    user_list.append(loan.owner)
            
            if len(user_list) == 0:
                messages.error(request, f'There are no users matching the selections. Please change category or location where there are existing clients.', extra_tags='info')
                return render(request, 'admin_create.html', {'nav': 'usermessages', 'form': form})
            else:
                user_id_list = []
                for user in user_list:
                    user_id_list.append(user.id)
                user_id_list_dict = {'user_id_list': user_id_list}
                userid_list_json = json.dumps(user_id_list_dict)

            message = Message.objects.create(subject=subject, content=content, category=category, sender=staff_profile, location=location)
            mid = message.id

            if 'attachment' in request.FILES:
                attachment = request.FILES['attachment']
                fsattachment = FileSystemStorage()
                newattachment_name = f'{mid}-MSG-ATTACHMENT-{attachment.name}'
                attachment_filename = fsattachment.save(newattachment_name, attachment)
                attachment_url = fsattachment.url(attachment_filename)
                message.attachment_url = attachment_url
                message.attachment_name = attachment_filename
                message.save()
                messages.success(request, 'Attachment uploaded successfully...')
                attachment_check = 1
                attachmentpath = f'media/{attachment_filename}'
            else:
                attachment_check = 0
                attachmentpath = ''    

            dispatch_task(create_message_asc, userid_list_json, subject, content, mid, attach=attachment_check, attachpath=attachmentpath)

            mid = message.id

            return redirect('delivering_message', mid)
    else:
        form = MessageForm()
    
    context = {

        'nav': 'create_message_admin',
        'form': form,
    }

    return render(request, 'admin_create.html', context )


@check_staff
def delivering_message(request, mid):
    message = Message.objects.get(id=mid)
    return render(request, 'delivering.html', {'nav': 'usermessages', 'message': message})

def track_email_open(request, message_id):
    
    if 'U' in message_id:
        strlist = message_id.split('U')
        user_id = int(strlist[0])
        msg_id = int(strlist[1])

        message_log = MessageLog.objects.get(user_id=user_id)
        message = Message.objects.get(id=msg_id)
    
        if message_log.reademail == '':
            message_log.reademail = f'{str(message.id)}'
        else: 
            message_log.reademail += f',{str(message.id)}'
        message_log.save()

        if message.read_by_personal_email == '':
            message.read_by_personal_email += f'{str(user_id)}'
        else:
            message.read_by_personal_email += f',{str(user_id)}'
        message.save()

    if 'W' in message_id:
        strlist = message_id.split('W')
        user_id = int(strlist[0])
        msg_id = int(strlist[1])

        message_log = MessageLog.objects.get(user_id=user_id)
        message = Message.objects.get(id=msg_id)
    
        if message_log.reademail == '':
            message_log.reademail = f'{str(message.id)}'
        else: 
            message_log.reademail += f',{str(message.id)}'
        message_log.save()

        if message.read_by_work_email == '':
            message.read_by_work_email += f'{str(user_id)}'
        else:
            message.read_by_work_email += f',{str(user_id)}'
        message.save()
    
    return HttpResponse(open(f'{settings.DOMAIN}/static/img/messagetransparent.png', 'rb').read(), content_type='image/png')

@check_staff
def delivery_report(request, mid):
    message = Message.objects.get(id=mid)

    email_sent = message.email_sent
    email_sent_list = list(email_sent.split(','))
    email_sent_total = len(email_sent_list)

    email_not_sent = message.email_not_sent
    email_not_sent_list = list(email_not_sent.split(','))
    email_not_sent_total = len(email_not_sent_list)
    
    email_sent_work = message.email_sent_work
    email_sent_work_list = list(email_sent_work.split(','))
    email_sent_work_total = len(email_sent_work_list)

    email_not_sent_work = message.email_not_sent_work
    email_not_sent_work_list = list(email_not_sent_work.split(','))
    email_not_sent_work_total = len(email_not_sent_work_list)

    emailto_personal = message.emailto_personal
    emailto_work = message.emailto_work

    recipients_personal = message.recipients_personal
    recipients_work = message.recipients_work
    
    if message.read_by_personal_email != '':

        read_by_personal_email = message.read_by_personal_email
        read_personal = list(read_by_personal_email.split(','))
        set_read_personal = set(read_personal)
        read_personal_total = len(set_read_personal)
    else:
        read_personal_total = 0
    
    if message.read_by_work_email != '':
        read_by_work_email = message.read_by_work_email
        read_work = list(read_by_work_email.split(','))
        set_read_work = set(read_work)
        read_work_total = len(set_read_work)
    else:
        read_work_total = 0
    
    read_by_app = message.read_by_app

    recepient_count = recipients_personal + recipients_work
    if recepient_count == 0:
        recepient_count = 1
    
    sent_email_count = email_sent_total + email_sent_work_total
    if sent_email_count == 0:
        sent_email_count = 1
    delivery_ratio = round(((email_sent_total + email_sent_work_total) / recepient_count ) * 100, 1)
    email_read_ratio = round(((read_personal_total + read_work_total) / sent_email_count ) * 100, 1)

    context = {
        'nav': 'usermessages',
        'message': message,
        'email_sent_total': email_sent_total,
        'email_not_sent_total': email_not_sent_total,
        'email_sent_work_total': email_sent_work_total,
        'email_not_sent_work_total': email_not_sent_work_total,
        'delivery_ratio': delivery_ratio,
        'email_read_ratio': email_read_ratio,
    }

    return render(request, 'delivery_report.html', context)

@check_staff
def delivery_status(request, mid):
    message = Message.objects.get(id=mid)
    if message.email_sent == '' and message.email_not_sent == '':
        messages.error(request, f'Delivery results are not ready. Please reload after a minute.', extra_tags='primary')

    if message.delivery_status != 'done':
        messages.error(request, f'The delivery status report is incomplete. Keep refreshing.', extra_tags='warning')
    if message.delivery_status == 'done':
        messages.success(request, f'The delivery status report is complete.')

    email_sent = []
    if message.email_sent != '':
        email_sent_list = list(map(int, message.email_sent.split(',')))
        for id in email_sent_list:
            user = UserProfile.objects.get(id=id)
            email_sent.append(user)
    
    email_not_sent = []
    if message.email_not_sent != '':
        email_not_sent_list = list(map(int, message.email_not_sent.split(',')))
        for id in email_not_sent_list:
            user = UserProfile.objects.get(id=id)
            email_not_sent.append(user)

    email_sent_work = []
    if message.email_sent_work != '':
        email_sent_work_list = list(map(int, message.email_sent_work.split(',')))
        for id in email_sent_work_list:
            user = UserProfile.objects.get(id=id)
            email_sent_work.append(user)

    email_not_sent_work = []
    if message.email_not_sent_work != '':
        email_not_sent_work_list = list(map(int, message.email_not_sent_work.split(',')))
        for id in email_not_sent_work_list:
            user = UserProfile.objects.get(id=id)
            email_not_sent_work.append(user)

    context = {
        'nav': 'usermessages', 
        'message': message,
        'email_sent': email_sent,
        'email_not_sent': email_not_sent,
        'email_sent_work': email_sent_work,
        'email_not_sent_work': email_not_sent_work
    }
    return render(request, 'delivery_status.html', context)

@check_staff
def view_message(request, mid):
    message = Message.objects.get(id=mid)
    return render(request, 'view_message.html', {'nav': 'usermessages', 'message': message})

@login_check
def user_view_message(request, mid):    
    user_profile = UserProfile.objects.get(user_id=request.user.id)
    message = Message.objects.get(id=mid)

    try:
        logmsgq = UserActivityLog.objects.get(user=user_profile)
        unread_messages_log = list(logmsgq.msgq.split(','))
        msgid_str = str(mid)
        unread_messages_log.remove(msgid_str)
        delimiter = ','
        msgq = delimiter.join(unread_messages_log)
        logmsgq.msgq = msgq
        logmsgq.save()
    except:
        unread_messages_log = []

    recent_messages = []
    read_messages = []

    try:
        userlogmsgs = list(UserActivityLog.objects.get(user=user_profile).msgq.split(','))
        for mid in userlogmsgs:
            msgmid = Message.objects.get(id=int(mid))
            recent_messages.append(msgmid)
    except:
        pass

    read_messages = Message.objects.order_by('-date')[:5]
    recent_message_count = len(recent_messages)
    read_message_count = len(read_messages)

    context = {
        'nav': 'messages_user',
        'message': message,
        'recent_messages': recent_messages,
        'read_messages': read_messages,
        'recent_message_count': recent_message_count,
        'read_message_count': read_message_count
    }

    return render(request, 'user_view_message.html', context)

@check_staff
def usermessages(request):
    all_filtered_messages = Message.objects.all().order_by('-date')
    locations = Location.objects.all()
    referrer = request.META['HTTP_REFERER']

    # count of messages 
    all_users = Message.objects.all().count()
    pending_users = Message.objects.filter(category='PENDING USERS').count()
    pending_loans = Message.objects.filter(category='PENDING LOANS').count()
    approved_loans = Message.objects.filter(category='APPROVED LOANS').count()
    funded_loans = Message.objects.filter(category='FUNDED LOANS').count()
    running_loans = Message.objects.filter(category='RUNNING LOANS').count()
    defaulted_loans = Message.objects.filter(category='DEAFULT LOANS').count()
    recovery_loans = Message.objects.filter(category='RECOVERY LOANS').count()
    bad_loans = Message.objects.filter(category='BAD LOANS').count()

    context = {
                'nav': 'usermessages',
                'all_filtered_messages': all_filtered_messages,
                'referrer': referrer,
                'locations': locations,
                'all_users': all_users,
                'pending_users': pending_users,
                'pending_loans': pending_loans,
                'approved_loans': approved_loans,
                'funded_loans': funded_loans,
                'running_loans': running_loans,
                'defaulted_loans': defaulted_loans,
                'recovery_loans': recovery_loans,
                'bad_loans': bad_loans,
            }

    if request.method=="POST":

        if request.POST.get('cuscat') and request.POST.get('locationx'):
            cuscat = request.POST.get('cuscat')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location, category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'cuscat':cuscat,'filter':'on' })
            return render(request, 'messages.html', context)

        elif request.POST.get('cuscat'):
            cuscat = request.POST.get('cuscat')
            all_filtered_messages = all_filtered_messages.filter(category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'cuscat':cuscat,'filter':'on' })
            return render(request, 'messages.html', context)

        elif request.POST.get('locationx'):
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'filter':'on' })
            return render(request, 'messages.html', context)

        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('usermessages')

    return render(request, 'messages.html', context)

@admin_check
def messages_admin(request):
    all_filtered_messages = Message.objects.all().order_by('-date')
    locations = Location.objects.all()
    referrer = request.META['HTTP_REFERER']

    # count of messages 
    all_users = Message.objects.all().count()
    pending_users = Message.objects.filter(category='PENDING USERS').count()
    pending_loans = Message.objects.filter(category='PENDING LOANS').count()
    approved_loans = Message.objects.filter(category='APPROVED LOANS').count()
    funded_loans = Message.objects.filter(category='FUNDED LOANS').count()
    running_loans = Message.objects.filter(category='RUNNING LOANS').count()
    defaulted_loans = Message.objects.filter(category='DEFAULT LOANS').count()
    recovery_loans = Message.objects.filter(category='RECOVERY LOANS').count()
    bad_loans = Message.objects.filter(category='BAD LOANS').count()

    context = {
                'nav': 'messages_admin',
                'all_filtered_messages': all_filtered_messages,
                'referrer': referrer,
                'locations': locations,
                'all_users': all_users,
                'pending_users': pending_users,
                'pending_loans': pending_loans,
                'approved_loans': approved_loans,
                'funded_loans': funded_loans,
                'running_loans': running_loans,
                'defaulted_loans': defaulted_loans,
                'recovery_loans': recovery_loans,
                'bad_loans': bad_loans,
            }

    if request.method=="POST":

        if request.POST.get('cuscat') and request.POST.get('locationx'):
            cuscat = request.POST.get('cuscat')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location, category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'cuscat':cuscat,'filter':'on' })
            return render(request, 'messages_admin.html', context)

        elif request.POST.get('cuscat'):
            cuscat = request.POST.get('cuscat')
            all_filtered_messages = all_filtered_messages.filter(category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'cuscat':cuscat,'filter':'on' })
            return render(request, 'messages_admin.html', context)

        elif request.POST.get('locationx'):
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'filter':'on' })
            return render(request, 'messages_admin.html', context)

        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('messages_admin')

    return render(request, 'messages_admin.html', context)

@admin_check
def message_drafts_admin(request):
    all_filtered_messages = Message.objects.all().order_by('-date')
    locations = Location.objects.all()
    referrer = request.META['HTTP_REFERER']

    # count of messages 
    all_users = Message.objects.all().count()
    pending_users = Message.objects.filter(category='PENDING USERS').count()
    pending_loans = Message.objects.filter(category='PENDING LOANS').count()
    approved_loans = Message.objects.filter(category='APPROVED LOANS').count()
    funded_loans = Message.objects.filter(category='FUNDED LOANS').count()
    running_loans = Message.objects.filter(category='RUNNING LOANS').count()
    defaulted_loans = Message.objects.filter(category='DEFAULT LOANS').count()
    recovery_loans = Message.objects.filter(category='RECOVERY LOANS').count()
    bad_loans = Message.objects.filter(category='BAD LOANS').count()

    context = {
                'nav': 'message_drafts_admin',
                'all_filtered_messages': all_filtered_messages,
                'referrer': referrer,
                'locations': locations,
                'all_users': all_users,
                'pending_users': pending_users,
                'pending_loans': pending_loans,
                'approved_loans': approved_loans,
                'funded_loans': funded_loans,
                'running_loans': running_loans,
                'defaulted_loans': defaulted_loans,
                'recovery_loans': recovery_loans,
                'bad_loans': bad_loans,
            }

    if request.method=="POST":

        if request.POST.get('cuscat') and request.POST.get('locationx'):
            cuscat = request.POST.get('cuscat')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location, category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'cuscat':cuscat,'filter':'on' })
            return render(request, 'message_drafts_admin.html', context)

        elif request.POST.get('cuscat'):
            cuscat = request.POST.get('cuscat')
            all_filtered_messages = all_filtered_messages.filter(category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'cuscat':cuscat,'filter':'on' })
            return render(request, 'message_drafts_admin.html', context)

        elif request.POST.get('locationx'):
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'filter':'on' })
            return render(request, 'message_drafts_admin.html', context)

        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('message_drafts_admin')

    return render(request, 'message_drafts_admin.html', context)

@admin_check
def delivery_reports_admin(request):
    all_filtered_messages = Message.objects.all().order_by('-date')
    locations = Location.objects.all()
    referrer = request.META['HTTP_REFERER']

    # count of messages 
    all_users = Message.objects.all().count()
    pending_users = Message.objects.filter(category='PENDING USERS').count()
    pending_loans = Message.objects.filter(category='PENDING LOANS').count()
    approved_loans = Message.objects.filter(category='APPROVED LOANS').count()
    funded_loans = Message.objects.filter(category='FUNDED LOANS').count()
    running_loans = Message.objects.filter(category='RUNNING LOANS').count()
    defaulted_loans = Message.objects.filter(category='DEFAULT LOANS').count()
    recovery_loans = Message.objects.filter(category='RECOVERY LOANS').count()
    bad_loans = Message.objects.filter(category='BAD LOANS').count()

    context = {
                'nav': 'delivery_reports_admin',
                'all_filtered_messages': all_filtered_messages,
                'referrer': referrer,
                'locations': locations,
                'all_users': all_users,
                'pending_users': pending_users,
                'pending_loans': pending_loans,
                'approved_loans': approved_loans,
                'funded_loans': funded_loans,
                'running_loans': running_loans,
                'defaulted_loans': defaulted_loans,
                'recovery_loans': recovery_loans,
                'bad_loans': bad_loans,
            }

    if request.method=="POST":

        if request.POST.get('cuscat') and request.POST.get('locationx'):
            cuscat = request.POST.get('cuscat')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location, category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'cuscat':cuscat,'filter':'on' })
            return render(request, 'delivery_reports_admin.html', context)

        elif request.POST.get('cuscat'):
            cuscat = request.POST.get('cuscat')
            all_filtered_messages = all_filtered_messages.filter(category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'cuscat':cuscat,'filter':'on' })
            return render(request, 'delivery_reports_admin.html', context)

        elif request.POST.get('locationx'):
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'filter':'on' })
            return render(request, 'delivery_reports_admin.html', context)

        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('delivery_reports_admin')

    return render(request, 'delivery_reports_admin.html', context)

@admin_check
def delivery_statuses_admin(request):
    all_filtered_messages = Message.objects.all().order_by('-date')
    locations = Location.objects.all()
    referrer = request.META['HTTP_REFERER']

    # count of messages 
    all_users = Message.objects.all().count()
    pending_users = Message.objects.filter(category='PENDING USERS').count()
    pending_loans = Message.objects.filter(category='PENDING LOANS').count()
    approved_loans = Message.objects.filter(category='APPROVED LOANS').count()
    funded_loans = Message.objects.filter(category='FUNDED LOANS').count()
    running_loans = Message.objects.filter(category='RUNNING LOANS').count()
    defaulted_loans = Message.objects.filter(category='DEFAULT LOANS').count()
    recovery_loans = Message.objects.filter(category='RECOVERY LOANS').count()
    bad_loans = Message.objects.filter(category='BAD LOANS').count()

    context = {
                'nav': 'delivery_statuses_admin',
                'all_filtered_messages': all_filtered_messages,
                'referrer': referrer,
                'locations': locations,
                'all_users': all_users,
                'pending_users': pending_users,
                'pending_loans': pending_loans,
                'approved_loans': approved_loans,
                'funded_loans': funded_loans,
                'running_loans': running_loans,
                'defaulted_loans': defaulted_loans,
                'recovery_loans': recovery_loans,
                'bad_loans': bad_loans,
            }

    if request.method=="POST":

        if request.POST.get('cuscat') and request.POST.get('locationx'):
            cuscat = request.POST.get('cuscat')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location, category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'cuscat':cuscat,'filter':'on' })
            return render(request, 'delivery_statuses_admin.html', context)

        elif request.POST.get('cuscat'):
            cuscat = request.POST.get('cuscat')
            all_filtered_messages = all_filtered_messages.filter(category=cuscat)
            context.update({'all_filtered_messages':all_filtered_messages,'cuscat':cuscat,'filter':'on' })
            return render(request, 'delivery_statuses_admin.html', context)

        elif request.POST.get('locationx'):
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            all_filtered_messages = all_filtered_messages.filter(location=location)
            context.update({'all_filtered_messages':all_filtered_messages,'location':location,'filter':'on' })
            return render(request, 'delivery_statuses_admin.html', context)

        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('delivery_statuses_admin')

    return render(request, 'delivery_statuses_admin.html', context)

@admin_check
def delete_message(request, mid):
    message = Message.objects.get(id=mid)
    message.delete()
    messages.success(request, 'Message deleted successfully', extra_tags='success')
    return redirect('messages_admin')