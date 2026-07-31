import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings

from .forms import CreateTicketForm
from .models import SupportTicket, SupportTicketThread

from .functions import send_email, email_admin
from accounts.functions import check_staff, login_check, admin_check
from accounts.models import UserProfile
from admin1.models import AdminSettings

try:
    prefix = AdminSettings.objects.get(settings_name='setting1').loanref_prefix
except:
    prefix = settings.PREFIX

from django.core.files.storage import FileSystemStorage

domain = settings.DOMAIN


# ─── User views ───────────────────────────────────────────────────────────────

@login_check
def user_support(request):
    user = UserProfile.objects.get(user_id=request.user.id)
    upid = user.id
    supporttickets = SupportTicket.objects.filter(user_id=upid).order_by('-date')
    stats = {
        'total':   supporttickets.count(),
        'waiting': supporttickets.filter(status='user_replied').count(),
        'replied': supporttickets.filter(status='staff_replied').count(),
        'closed':  supporttickets.filter(status='closed').count(),
    }
    return render(request, 'user_support.html', {
        'nav': 'user_support',
        'supporttickets': supporttickets,
        'user': user,
        'stats': stats,
    })


@login_check
def create_ticket(request):
    uid = request.user.id
    user_profile = UserProfile.objects.get(user_id=uid)
    upid = user_profile.id

    if user_profile.first_name == '' or user_profile.last_name == '':
        messages.error(request, "Please update your profile with your first and last name.", extra_tags='danger')
        return redirect('profile')

    if request.method == 'POST':
        form = CreateTicketForm(request.POST)
        if form.is_valid():
            temp_ref = f'{user_profile.first_name[0]}{user_profile.last_name[0]}{upid}'
            category = form.cleaned_data['category']
            subject = form.cleaned_data['subject']
            content = form.cleaned_data['content']
            ticket = SupportTicket.objects.create(
                user_id=upid, category=category, subject=subject,
                content=content, ref=temp_ref
            )
            ticket.save()
            ref = f'{ticket.ref}T{ticket.id}'
            ticket.ref = ref
            ticket.save()

            thread_id = f'{ticket.id}U'
            ticketthread = SupportTicketThread.objects.create(
                ticket=ticket, thread=thread_id, thread_content=content
            )
            ticketthread.save()

            ticket.threadlog = f'{ticketthread.id}U'
            ticket.threadq = f'{ticketthread.id}U'
            ticket.status = 'user_replied'
            ticket.save()

            if 'attachment' in request.FILES:
                attachment = request.FILES['attachment']
                fsattachment = FileSystemStorage()
                newattachment_name = f'{ref}-MSG-ATTACHMENT-{attachment.name}'
                attachment_filename = fsattachment.save(newattachment_name, attachment)
                attachment_url = fsattachment.url(attachment_filename)
                ticket.attachment_url = attachment_url
                ticket.attachment_name = attachment_filename
                ticket.save()
                ticketthread.attachment_name = attachment_filename
                ticketthread.attachment_url = attachment_url
                ticketthread.save()
                attachment_check = 'yes'
                attachmentpath = f'media/{attachment_filename}'
            else:
                attachment_check = 'no'
                attachmentpath = ''

            email_admin(
                user_profile,
                sub=f'{user_profile.first_name} {user_profile.last_name} opened support ticket: {ref}',
                msg=subject.upper(),
                msg_details=content,
                cta='yes',
                btnlab='View Ticket',
                btnlink=f'{settings.DOMAIN}/admin/support/tickets/view/{ref}/',
                attachcheck=attachment_check,
                path=attachmentpath,
            )
            messages.success(request, f"Ticket {ref} created. We will get back to you shortly.")
            return redirect('view_ticket', ref=ref)
    else:
        form = CreateTicketForm()
    return render(request, 'create_ticket.html', {'nav': 'user_support', 'form': form, 'user': user_profile})


@login_check
def view_ticket(request, ref):
    ticket = SupportTicket.objects.get(ref=ref)
    ticketthread = SupportTicketThread.objects.filter(ticket=ticket).order_by('date')
    user = UserProfile.objects.get(id=ticket.user.id)

    if request.method == 'POST':
        content = request.POST.get('thread_content', '').strip()
        if not content:
            messages.error(request, "Reply cannot be empty.", extra_tags='danger')
            return redirect('view_ticket', ref=ref)

        thread_id = f'{ticket.id}U'
        new_thread = SupportTicketThread.objects.create(
            ticket=ticket, thread=thread_id, thread_content=content
        )
        ticket.threadlog = (ticket.threadlog or '') + f',{new_thread.id}U'
        ticket.threadq = f'{new_thread.id}U'
        ticket.status = 'user_replied'
        ticket.save()

        if 'attachment' in request.FILES:
            attachment = request.FILES['attachment']
            fs = FileSystemStorage()
            fname = fs.save(f'{ref}-REPLY-{attachment.name}', attachment)
            new_thread.attachment_name = fname
            new_thread.attachment_url = fs.url(fname)
            new_thread.save()

        email_admin(
            user,
            sub=f'{user.first_name} {user.last_name} replied to ticket: {ticket.ref}',
            msg=ticket.subject.upper(),
            msg_details=content,
            cta='yes',
            btnlab='View Ticket',
            btnlink=f'{settings.DOMAIN}/admin/support/tickets/view/{ref}/',
        )
        messages.success(request, "Reply sent.")
        return redirect('view_ticket', ref=ref)

    return render(request, 'view_ticket.html', {
        'nav': 'user_support',
        'ticket': ticket,
        'ticketthread': ticketthread,
        'user': user,
        'domain': domain,
    })


@login_check
def close_ticket(request, ref):
    user = UserProfile.objects.get(user_id=request.user.id)
    ticket = SupportTicket.objects.get(ref=ref)
    ticket.status = 'closed'
    ticket.closed = True
    ticket.save()

    thread = f'{ticket.id}U'
    t = SupportTicketThread.objects.create(
        ticket=ticket, thread_content="Ticket closed by client.", thread=thread
    )
    ticket.threadlog = (ticket.threadlog or '') + f',{t.id}U'
    ticket.threadq = f'{t.id}U'
    ticket.save()

    email_admin(
        user,
        sub=f'{user.first_name} {user.last_name} closed ticket: {ticket.ref}',
        msg="TICKET CLOSED BY CLIENT",
        msg_details="The client has marked this ticket as resolved.",
        cta='yes',
        btnlab='View Ticket',
        btnlink=f'{settings.DOMAIN}/admin/support/tickets/view/{ref}/',
    )
    messages.success(request, f"Ticket {ref} has been closed.")
    return redirect('view_ticket', ref=ref)


# ─── Staff views ──────────────────────────────────────────────────────────────

@check_staff
def support_tickets(request):
    supporttickets = SupportTicket.objects.all().order_by('-date')
    return render(request, 'supporttickets.html', {
        'nav': 'usersupport',
        'supporttickets': supporttickets,
    })


@login_check
def staff_view_ticket(request, ref):
    ticket = SupportTicket.objects.get(ref=ref)
    ticketthread = SupportTicketThread.objects.filter(ticket=ticket).order_by('date')
    user = UserProfile.objects.get(id=ticket.user.id)

    if request.method == 'POST':
        uid = request.user.id
        staff_profile = UserProfile.objects.get(user_id=uid)
        staff = f'{staff_profile.first_name} {staff_profile.last_name}'
        content = request.POST.get('thread_content', '').strip()
        if not content:
            messages.error(request, "Reply cannot be empty.", extra_tags='danger')
            return redirect('staff_view_ticket', ref=ref)

        thread_id = f'{ticket.id}R'
        new_thread = SupportTicketThread.objects.create(
            ticket=ticket, thread=thread_id, thread_content=content, responder=staff
        )
        ticket.threadlog = (ticket.threadlog or '') + f',{new_thread.id}R'
        ticket.threadq = f'{new_thread.id}R'
        ticket.status = 'staff_replied'
        ticket.save()

        send_email(
            user,
            sub=f'Reply to your support ticket: {ticket.ref}',
            msg=ticket.subject.upper(),
            msg_details=content,
            cta='yes',
            btnlab='View Ticket',
            btnlink=f'{settings.DOMAIN}/support/ticket/view/{ref}/',
        )
        messages.success(request, "Reply sent.")
        return redirect('staff_view_ticket', ref=ref)

    return render(request, 'staff_view_ticket.html', {
        'nav': 'user_support',
        'ticket': ticket,
        'ticketthread': ticketthread,
        'user': user,
        'domain': domain,
    })


@check_staff
def staff_close_ticket(request, ref):
    staff_profile = UserProfile.objects.get(user_id=request.user.id)
    staff = f'{staff_profile.first_name} {staff_profile.last_name}'
    ticket = SupportTicket.objects.get(ref=ref)
    ticket.status = 'closed'
    ticket.closed = True
    ticket.save()

    thread = f'{ticket.id}R'
    t = SupportTicketThread.objects.create(
        ticket=ticket, thread_content=f"Ticket closed by {staff}.", thread=thread, responder=staff
    )
    ticket.threadlog = (ticket.threadlog or '') + f',{t.id}R'
    ticket.threadq = f'{t.id}R'
    ticket.save()

    user = UserProfile.objects.get(id=ticket.user.id)
    send_email(
        user,
        sub=f'Your support ticket {ticket.ref} has been closed',
        msg="TICKET CLOSED",
        msg_details=f"Your ticket has been resolved and closed by {staff}.",
        cta='yes',
        btnlab='View Ticket',
        btnlink=f'{settings.DOMAIN}/support/ticket/view/{ref}/',
    )
    messages.success(request, f"Ticket {ref} closed.")
    return redirect('staff_view_ticket', ref=ref)


# ─── Admin views ──────────────────────────────────────────────────────────────

def _ticket_stats(qs):
    return {
        'total':   qs.count(),
        'waiting': qs.filter(status='user_replied').count(),
        'replied': qs.filter(status='staff_replied').count(),
        'closed':  qs.filter(status='closed').count(),
        'open':    qs.exclude(status='closed').count(),
    }


@admin_check
def support_tickets_admin(request):
    all_tickets = SupportTicket.objects.all().order_by('-date')
    status_filter = request.GET.get('status', 'all')

    if status_filter == 'waiting':
        tickets = all_tickets.filter(status='user_replied')
    elif status_filter == 'replied':
        tickets = all_tickets.filter(status='staff_replied')
    elif status_filter == 'closed':
        tickets = all_tickets.filter(status='closed')
    elif status_filter == 'open':
        tickets = all_tickets.exclude(status='closed')
    else:
        tickets = all_tickets

    return render(request, 'supporttickets_admin.html', {
        'nav': 'support_tickets_admin',
        'supporttickets': tickets,
        'status_filter': status_filter,
        'stats': _ticket_stats(all_tickets),
    })


@admin_check
def admin_view_ticket(request, ref):
    ticket = SupportTicket.objects.get(ref=ref)
    ticketthread = SupportTicketThread.objects.filter(ticket=ticket).order_by('date')
    user = UserProfile.objects.get(id=ticket.user.id)

    if request.method == 'POST':
        uid = request.user.id
        admin_profile = UserProfile.objects.get(user_id=uid)
        responder = f'{admin_profile.first_name} {admin_profile.last_name}'
        content = request.POST.get('thread_content', '').strip()
        if not content:
            messages.error(request, "Reply cannot be empty.", extra_tags='danger')
            return redirect('admin_view_ticket', ref=ref)

        thread_id = f'{ticket.id}R'
        new_thread = SupportTicketThread.objects.create(
            ticket=ticket, thread=thread_id, thread_content=content, responder=responder
        )

        if 'attachment' in request.FILES:
            attachment = request.FILES['attachment']
            fs = FileSystemStorage()
            fname = fs.save(f'{ref}-ADMIN-REPLY-{attachment.name}', attachment)
            new_thread.attachment_name = fname
            new_thread.attachment_url = fs.url(fname)
            new_thread.save()

        ticket.threadlog = (ticket.threadlog or '') + f',{new_thread.id}R'
        ticket.threadq = f'{new_thread.id}R'
        ticket.status = 'staff_replied'
        ticket.save()

        send_email(
            user,
            sub=f'Reply to your support ticket: {ticket.ref}',
            msg=ticket.subject.upper(),
            msg_details=content,
            cta='yes',
            btnlab='View Ticket',
            btnlink=f'{settings.DOMAIN}/support/ticket/view/{ref}/',
        )
        messages.success(request, "Reply sent to client.")
        return redirect('admin_view_ticket', ref=ref)

    return render(request, 'admin_view_ticket.html', {
        'nav': 'support_tickets_admin',
        'ticket': ticket,
        'ticketthread': ticketthread,
        'user': user,
        'domain': domain,
    })


@admin_check
def admin_close_ticket(request, ref):
    admin_profile = UserProfile.objects.get(user_id=request.user.id)
    admin_name = f'{admin_profile.first_name} {admin_profile.last_name}'
    ticket = SupportTicket.objects.get(ref=ref)
    ticket.status = 'closed'
    ticket.closed = True
    ticket.save()

    thread = f'{ticket.id}R'
    t = SupportTicketThread.objects.create(
        ticket=ticket,
        thread_content=f"Ticket resolved and closed by admin ({admin_name}).",
        thread=thread,
        responder=admin_name,
    )
    ticket.threadlog = (ticket.threadlog or '') + f',{t.id}R'
    ticket.threadq = f'{t.id}R'
    ticket.save()

    user = UserProfile.objects.get(id=ticket.user.id)
    send_email(
        user,
        sub=f'Your support ticket {ticket.ref} has been resolved',
        msg="TICKET RESOLVED & CLOSED",
        msg_details=f"Your support request has been resolved and closed by our team. If you need further assistance, please open a new ticket.",
        cta='yes',
        btnlab='View Ticket',
        btnlink=f'{settings.DOMAIN}/support/ticket/view/{ref}/',
    )
    messages.success(request, f"Ticket {ref} closed and client notified.")
    return redirect('admin_view_ticket', ref=ref)


@admin_check
def admin_reopen_ticket(request, ref):
    ticket = SupportTicket.objects.get(ref=ref)
    ticket.status = 'staff_replied'
    ticket.closed = False
    ticket.save()
    messages.success(request, f"Ticket {ref} reopened.")
    return redirect('admin_view_ticket', ref=ref)


@admin_check
def pending_tickets_admin(request):
    tickets = SupportTicket.objects.filter(status='user_replied').order_by('-date')
    all_tickets = SupportTicket.objects.all()
    return render(request, 'pending_tickets_admin.html', {
        'nav': 'pending_tickets_admin',
        'supporttickets': tickets,
        'stats': _ticket_stats(all_tickets),
    })


@admin_check
def closed_tickets_admin(request):
    tickets = SupportTicket.objects.filter(status='closed').order_by('-date')
    all_tickets = SupportTicket.objects.all()
    return render(request, 'supporttickets_closed_admin.html', {
        'nav': 'closed_tickets_admin',
        'supporttickets': tickets,
        'stats': _ticket_stats(all_tickets),
    })


@admin_check
def open_tickets_admin(request):
    tickets = SupportTicket.objects.exclude(status='closed').order_by('-date')
    all_tickets = SupportTicket.objects.all()
    return render(request, 'supporttickets_open_admin.html', {
        'nav': 'open_tickets_admin',
        'supporttickets': tickets,
        'stats': _ticket_stats(all_tickets),
    })
