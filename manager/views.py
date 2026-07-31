import datetime
from decimal import Decimal

from django.contrib import messages
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.functions import manager_check
from accounts.models import UserProfile
from admin1.models import AdminSettings
from loan.models import Loan, Payment, PaymentUploads

from .contract_utils import save_contract_file, send_approval_email, send_hold_email, send_rejection_email


def _contract_enabled():
    setting = AdminSettings.objects.filter(settings_name='setting1').first()
    return bool(setting and setting.contract_generation_enabled == 'YES')


@manager_check
def manager_dashboard(request):
    """Manager Dashboard with key metrics and pending approvals."""
    today = datetime.date.today()
    current_month_start = today.replace(day=1)

    pending_loans = Loan.objects.filter(
        category='PENDING', status='UNDER REVIEW'
    ).order_by('-application_date')

    pending_payments = PaymentUploads.objects.filter(
        status='UPLOADED'
    ).order_by('-created_at')

    approved_loans = Loan.objects.filter(
        category='PENDING', status='APPROVED', updated_at__gte=current_month_start
    )
    funded_loans = Loan.objects.filter(
        category='FUNDED', funding_date__gte=current_month_start
    )
    payments_this_month = Payment.objects.filter(date__gte=current_month_start)
    defaulted_loans = Loan.objects.filter(
        category='FUNDED', status='DEFAULTED', funded_category='ACTIVE'
    )

    stats = {
        'pending_loans_count': pending_loans.count(),
        'pending_payments_count': pending_payments.count(),
        'approved_loans_count': approved_loans.count(),
        'approved_loans_amount': approved_loans.aggregate(Sum('amount'))['amount__sum'] or 0,
        'funded_loans_count': funded_loans.count(),
        'funded_loans_amount': funded_loans.aggregate(Sum('amount'))['amount__sum'] or 0,
        'payments_count': payments_this_month.count(),
        'payments_amount': payments_this_month.aggregate(Sum('amount'))['amount__sum'] or 0,
        'defaulted_loans_count': defaulted_loans.count(),
        'defaulted_loans_amount': defaulted_loans.aggregate(Sum('total_outstanding'))['total_outstanding__sum'] or 0,
    }

    context = {
        'nav': 'manager_dashboard',
        'stats': stats,
        'recent_pending_loans': pending_loans[:10],
        'recent_payment_uploads': pending_payments[:10],
        'defaulted_loans': defaulted_loans[:10],
    }
    return render(request, 'manager/dashboard.html', context)


@manager_check
def pending_loans(request):
    """All pending loans awaiting manager approval."""
    loans_list = Loan.objects.filter(
        category='PENDING', status='UNDER REVIEW'
    ).select_related('owner').order_by('-application_date')

    search_query = request.GET.get('search', '')
    if search_query:
        loans_list = loans_list.filter(
            Q(ref__icontains=search_query) |
            Q(owner__first_name__icontains=search_query) |
            Q(owner__last_name__icontains=search_query) |
            Q(owner__email__icontains=search_query)
        )

    loan_type = request.GET.get('type', '')
    if loan_type:
        loans_list = loans_list.filter(loan_type=loan_type)

    paginator = Paginator(loans_list, 25)
    loans = paginator.get_page(request.GET.get('page'))

    context = {
        'nav': 'pending_loans',
        'loans': loans,
        'search_query': search_query,
        'loan_type': loan_type,
        'total_amount': loans_list.aggregate(Sum('amount'))['amount__sum'] or 0,
        'total_count': loans_list.count(),
        'loan_types': [('PERSONAL', 'Personal'), ('SME', 'SME')],
    }
    return render(request, 'manager/pending_loans.html', context)


@manager_check
def loan_approval(request, loan_id):
    """Approve, reject or hold a pending loan. Approval optionally generates
    a contract and emails it to the client and lending officer (per the
    Manager Review & Contracts setting)."""
    loan = get_object_or_404(Loan, id=loan_id, category='PENDING', status='UNDER REVIEW')
    staff = loan.officer
    user = loan.owner

    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '')
        user_profile = UserProfile.objects.filter(user=request.user).first()
        approver = getattr(user_profile, 'staffprofile', None) if user_profile else None

        if action == 'approve':
            loan.status = 'APPROVED'
            loan.approval_date = timezone.now()
            loan.approved_by = approver
            if _contract_enabled():
                try:
                    contract_path = save_contract_file(loan)
                    email_sent = send_approval_email(loan, contract_path)
                    loan.contract_email_sent = email_sent
                    loan.contract_email_sent_date = timezone.now()
                    loan.save()
                    if email_sent:
                        messages.success(request, f'Loan {loan.ref} has been approved and the contract sent to the applicant.')
                    else:
                        messages.warning(request, f'Loan {loan.ref} approved but the contract email failed to send.')
                except Exception as exc:
                    loan.save()
                    messages.warning(request, f'Loan {loan.ref} approved, but the contract could not be generated: {exc}')
            else:
                loan.save()
                messages.success(request, f'Loan {loan.ref} has been approved.')
            return redirect('manager:pending_loans')

        elif action == 'reject':
            loan.status = 'REJECTED'
            loan.save()
            if staff and staff.user.email:
                subject = f"Loan {loan.ref} Rejected by Manager"
                message = (f"Dear {staff.user.first_name},\n\nThe loan application for "
                          f"{user.first_name} {user.last_name} (Ref: {loan.ref}) has been "
                          f"rejected by the manager.\n\nComments: {comments}\n\n"
                          "Please review and take necessary action.")
                EmailMessage(subject, message, to=[staff.user.email]).send(fail_silently=True)
            send_rejection_email(loan, comments)
            messages.info(request, f'Loan {loan.ref} has been rejected and sent back to staff for review.')
            return redirect('manager:pending_loans')

        elif action == 'hold':
            loan.status = 'ON HOLD'
            loan.save()
            send_hold_email(loan, comments)
            messages.info(request, f'Loan {loan.ref} has been put on hold.')
            return redirect('manager:pending_loans')

    loan_details = {
        'monthly_income': user.gross_pay or 0,
        'existing_loans': Loan.objects.filter(owner=user, category='FUNDED', funded_category='ACTIVE').count(),
        'total_outstanding': Loan.objects.filter(
            owner=user, category='FUNDED', funded_category='ACTIVE'
        ).aggregate(Sum('total_outstanding'))['total_outstanding__sum'] or 0,
        'payment_history': Payment.objects.filter(owner=user).order_by('-date')[:5],
    }
    context = {
        'nav': 'pending_loans',
        'loan': loan,
        'loan_details': loan_details,
        'contract_enabled': _contract_enabled(),
    }
    return render(request, 'manager/loan_approval.html', context)


@manager_check
def pending_payments(request):
    """All pending payment uploads awaiting manager review."""
    payments_list = PaymentUploads.objects.filter(
        status='UPLOADED'
    ).select_related('owner', 'loan').order_by('-created_at')

    search_query = request.GET.get('search', '')
    if search_query:
        payments_list = payments_list.filter(
            Q(loan__ref__icontains=search_query) |
            Q(owner__first_name__icontains=search_query) |
            Q(owner__last_name__icontains=search_query) |
            Q(ref__icontains=search_query)
        )

    paginator = Paginator(payments_list, 25)
    payments = paginator.get_page(request.GET.get('page'))

    context = {
        'nav': 'pending_payments',
        'payments': payments,
        'search_query': search_query,
        'total_count': payments_list.count(),
    }
    return render(request, 'manager/pending_payments.html', context)


@manager_check
def payment_approval(request, payment_id):
    """Approve or reject an uploaded payment proof.

    NOTE: this only marks the upload reviewed (PROCESSED/REJECTED) — same as
    the existing admin Payment Uploads screen. It does not itself create the
    Payment/Statement record; staff still record the actual repayment (via
    the normal Enter Payment flow, or Alesco/bulk upload) once the proof has
    been verified. Extending this to fully post the payment is future work.
    """
    payment_upload = get_object_or_404(PaymentUploads, id=payment_id, status='UPLOADED')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            payment_upload.status = 'PROCESSED'
            payment_upload.save()
            messages.success(request, f'Payment upload {payment_upload.ref} has been marked processed.')
        elif action == 'reject':
            payment_upload.status = 'REJECTED'
            payment_upload.save()
            messages.success(request, f'Payment upload {payment_upload.ref} has been rejected.')
        return redirect('manager:pending_payments')

    context = {
        'nav': 'pending_payments',
        'payment_upload': payment_upload,
    }
    return render(request, 'manager/payment_approval.html', context)


@manager_check
def reports(request):
    """Manager reports and analytics."""
    today = datetime.date.today()
    current_month_start = today.replace(day=1)

    monthly_stats = {
        'loans_approved': Loan.objects.filter(
            status='APPROVED', updated_at__gte=current_month_start
        ).count(),
        'loans_approved_amount': Loan.objects.filter(
            status='APPROVED', updated_at__gte=current_month_start
        ).aggregate(Sum('amount'))['amount__sum'] or 0,
        'loans_rejected': Loan.objects.filter(
            status='REJECTED', updated_at__gte=current_month_start
        ).count(),
        'payments_approved': PaymentUploads.objects.filter(
            status='PROCESSED', updated_at__gte=current_month_start
        ).count(),
    }
    pending_stats = {
        'pending_loans': Loan.objects.filter(category='PENDING', status='UNDER REVIEW').count(),
        'pending_payments': PaymentUploads.objects.filter(status='UPLOADED').count(),
        'on_hold_loans': Loan.objects.filter(category='PENDING', status='ON HOLD').count(),
    }

    context = {
        'nav': 'manager_reports',
        'monthly_stats': monthly_stats,
        'pending_stats': pending_stats,
    }
    return render(request, 'manager/reports.html', context)
