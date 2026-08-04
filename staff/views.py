import datetime
import decimal
import logging
import random
from django.conf import settings
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.core.files.storage import FileSystemStorage
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db.models import Sum, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from message.models import Message, MessageLog
from loan.models import Loan, LoanFile, Statement, Payment, PaymentUploads
from loan.forms import PaymentForm
from loan.functions import request_approval
from admin1.forms import AdminSettingsForm
from admin1.models import AdminSettings, Location, get_bank_config, get_document_theme
from accounts.models import User, UserProfile, StaffProfile, SMEProfile
from accounts.functions import check_staff, fileuploader, loanfileuploader, testloanfileuploader, get_field_settings
from staff.forms import ( MemberInfoForm, PersonalInfoForm, ContactInfoForm, AddressInfoForm, UserUploadForm,
    WorkUploadForm, BankAccountInfoForm, BankAccountInfo2Form, EmployerInfoUpdateForm, JobInfoUpdateForm, UploadRequirementsByStaffForm,
    LoanStatementUploadForm, SMEProfileForm, SMEUploadsForm, SMEBankInfoForm, RequiredUploadForm, CreateSMEProfileForm, CreateLoanForm
)
from accounts.forms import RefereeInfoForm, PreviousEmployerInfoForm, StatementOfPositionForm
from .tokens import loan_tc_agreement_token
from .functions import id_generator

logger = logging.getLogger(__name__)
sender = settings.DEFAULT_SENDER_EMAIL

domain = settings.DOMAIN
domain_dns = settings.DOMAIN_DNS

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
import subprocess

import pandas as pd

def generate_pdf(templatefile, data):
    from moromafinance.pdf import render_pdf
    return render_pdf(templatefile, data, 'custom/templates')

from custom.functions import repayment, combination_check, fn_limits, term_range, upload_existing_loans, upload_existing_statement


############### 
# START OF CODE
###############

# DASHBOARD FUNCTIONS
 

@check_staff
def staff_instructions(request):
    return render(request, 'staff_instructions.html', {'nav': 'staff_instructions'})


@check_staff
def staff_dashboard(request):
    """Daily-operations dashboard — collections progress, action queues and
    quick actions, from the shared metrics module."""
    from admin1 import dashboard_metrics
    context = dashboard_metrics.build('staff')
    context['nav'] = 'staff_dashboard'
    return render(request, 'staff_dashboard.html', context)

###### LOAN FUNCTIONS
# LOANS LOANS
###### LOANS ###################

@check_staff
def userloans(request):

    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.filter(category='FUNDED', funded_category='ACTIVE').all()
    pending_loans = Loan.objects.filter(category="PENDING")
    unfinished_loans = Loan.objects.filter(category="PENDING", status="AWAITING T&C", officer=request.user.id)
    review_loans = Loan.objects.filter(category="PENDING", status="UNDER REVIEW", officer=request.user.id)
 

    
    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry 

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).filter(category='FUNDED', funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
               
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }
            
            return render(request, 'userloans.html', context)
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).filter(category='FUNDED', funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum, 
                    }     

            return render(request, 'userloans.html', context)

        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))

            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).filter(category='FUNDED', funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,  
                    }
  
            return render(request, 'userloans.html', context)
        
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
                return redirect('userloans')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(funding_date__gte = start_date, funding_date__lte = end_date).filter(category='FUNDED', funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }

            return render(request, 'userloans.html', context)

        elif request.POST.get('loantype') and request.POST.get('cuscat'):

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat).filter(category='FUNDED', funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'loantype': loantype,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }

            return render(request, 'userloans.html', context)

        elif request.POST.get('loantype'):

            loantype = request.POST.get('loantype')
            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype).filter(category='FUNDED',funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'loantype': loantype, 
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,  
                    }  

            return render(request, 'userloans.html', context)

        elif request.POST.get('cuscat'):
            cuscat = request.POST.get('cuscat')
            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat).filter(category='FUNDED',funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }          

            return render(request, 'userloans.html', context)

        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('userloans')

    all_loans_filtered = Loan.objects.filter(category="FUNDED", funded_category="ACTIVE", officer=request.user.id).all()
    funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                'nav': 'userloans', 
                'all_loans': all_loans,
                'all_loans_filtered': all_loans_filtered,
                'pending_loans': pending_loans,
                'unfinished_loans':unfinished_loans,
                'review_loans': review_loans,
                'funded_sum': funded_sum,
                'interests_sum': interests_sum,
                'totalloan_sum': totalloan_sum,
                'repayments_sum': repayments_sum,
                'arrears_sum': arrears_sum,
                'defaultinterests_sum': defaultinterests_sum,
                'outstanding_sum': outstanding_sum,
            }

    return render(request, 'userloans.html', context)

@check_staff
def userloans_unfinished(request):

    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category='PENDING').all()
    pending_loans = Loan.objects.filter(category="PENDING")
    unfinished_loans = Loan.objects.filter(category="PENDING", status="AWAITING T&C", officer=request.user.id)
    review_loans = Loan.objects.filter(category="PENDING", status="UNDER REVIEW", officer=request.user.id)

    if request.method=="POST":

        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry 

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_unfinished')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date, category="PENDING",status="AWAITING T&C", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }
            
            return render(request, 'userloans_unfinished.html', context)

        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))

            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_unfinished')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date, category="PENDING",status="AWAITING T&C", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }   

            return render(request, 'userloans_unfinished.html', context)

        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_unfinished')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date, category="PENDING",status="AWAITING T&C", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
                        
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }         
                        
            return render(request, 'userloans_unfinished.html', context)
        
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
                return redirect('userloans_unfinished')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(funding_date__gte = start_date, funding_date__lte = end_date, category="PENDING",status="AWAITING T&C", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
                        
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }      
            
            return render(request, 'userloans_unfinished.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat, category="PENDING",status="AWAITING T&C", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'loantype': loantype,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
                        
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }        
            
            return render(request, 'userloans_unfinished.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')
            

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, category="PENDING",status="AWAITING T&C", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'loantype': loantype, 
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
                        
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }  
            
            return render(request, 'userloans_unfinished.html', context)
        
        elif request.POST.get('cuscat'): 
            
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat, category="PENDING",status="AWAITING T&C", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
                        
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }
            
            return render(request, 'userloans_unfinished.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('userloans_unfinished')

    all_loans_filtered = Loan.objects.filter(category="PENDING",status="AWAITING T&C", officer=request.user.id).all()
    funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                'nav': 'userloans', 
                'all_loans': all_loans,
                'all_loans_filtered': all_loans_filtered,
                'pending_loans': pending_loans,
                'unfinished_loans':unfinished_loans,
                'review_loans': review_loans,
                'funded_sum': funded_sum,
                'interests_sum': interests_sum,
                'totalloan_sum': totalloan_sum,
                'repayments_sum': repayments_sum,
                'arrears_sum': arrears_sum,
                'defaultinterests_sum': defaultinterests_sum,
                'outstanding_sum': outstanding_sum,
                
            }  
    
    return render(request, 'userloans_unfinished.html', context)

@check_staff
def userloans_review(request):

    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category='PENDING').all()
    pending_loans = Loan.objects.filter(category="PENDING")
    unfinished_loans = Loan.objects.filter(category="PENDING", status="AWAITING T&C", officer=request.user.id)
    review_loans = Loan.objects.filter(category="PENDING", status="UNDER REVIEW", officer=request.user.id)
    
    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry 

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_review')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date, category="PENDING", status="UNDER REVIEW", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
               
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }  
            
            return render(request, 'userloans_review.html', context)
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_review')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date, category="PENDING", status="UNDER REVIEW", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
               
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }
            
            return render(request, 'userloans_review.html', context)
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_review')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date, category="PENDING", status="UNDER REVIEW", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
               
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }         
                        
            return render(request, 'userloans_review.html', context)
        
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
                return redirect('userloans_review')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(funding_date__gte = start_date, funding_date__lte = end_date, category="PENDING", status="UNDER REVIEW", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
               
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }      
            
            return render(request, 'userloans_review.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat, category="PENDING", status="UNDER REVIEW", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'loantype': loantype,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
               
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }        
            
            return render(request, 'userloans_review.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')
            

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, category="PENDING", status="UNDER REVIEW", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'loantype': loantype, 
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
               
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }  
            
            return render(request, 'userloans_review.html', context)
        
        elif request.POST.get('cuscat'): 
            
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat, category="PENDING", status="UNDER REVIEW", officer=request.user.id).all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        
               
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }
            
            return render(request, 'userloans_review.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('userloans_review')

    all_loans_filtered = Loan.objects.filter(category="PENDING", status="UNDER REVIEW", officer=request.user.id).all()
    funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                'nav': 'userloans', 
                'all_loans': all_loans,
                'all_loans_filtered': all_loans_filtered,
                'pending_loans': pending_loans,
                'unfinished_loans':unfinished_loans,
                'review_loans': review_loans,
                
                'funded_sum': funded_sum,
                'interests_sum': interests_sum,
                'totalloan_sum': totalloan_sum,
                'repayments_sum': repayments_sum,
                'arrears_sum': arrears_sum,
                'defaultinterests_sum': defaultinterests_sum,
                'outstanding_sum': outstanding_sum,
                
            }  
    
    return render(request, 'userloans_review.html', context)

@check_staff
def userloans_pending(request):

    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category='PENDING').all()
    pending_loans = Loan.objects.filter(category="PENDING")
    unfinished_loans = Loan.objects.filter(category="PENDING", status="AWAITING T&C", officer=request.user.id)
    review_loans = Loan.objects.filter(category="PENDING", status="UNDER REVIEW", officer=request.user.id)

    all_loans_filtered = Loan.objects.filter(category="PENDING").all()
    funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                'nav': 'userloans',
                'referrer': referrer,
                'domain':domain, 
                'all_loans': all_loans,
                'all_loans_filtered': all_loans_filtered,
                'pending_loans': pending_loans,
                'unfinished_loans':unfinished_loans,
                'review_loans': review_loans,
                'funded_sum': funded_sum,
                'interests_sum': interests_sum,
                'totalloan_sum': totalloan_sum,
                'repayments_sum': repayments_sum,
                'arrears_sum': arrears_sum,
                'defaultinterests_sum': defaultinterests_sum,
                'outstanding_sum': outstanding_sum,
                
            }  
    
    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry 

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_pending')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).filter(category="PENDING")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context.update({'filter': 'on', 'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date})

            return render(request, 'userloans_pending.html', context)
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_pending')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).filter(category="PENDING")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context.update({'filter': 'on', 'loantype': loantype, 'startdate': start_date, 'enddate': end_date})
            return render(request, 'userloans_pending.html', context)
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_pending')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).filter(category="PENDING")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context.update({'filter': 'on', 'cuscat': cuscat, 'startdate': start_date, 'enddate': end_date})
            return render(request, 'userloans_pending.html', context)
        
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
                return redirect('userloans_pending')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(funding_date__gte = start_date, funding_date__lte = end_date).filter(category="PENDING")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context.update({'filter': 'on', 'startdate': start_date, 'enddate': end_date})
            return render(request, 'userloans_pending.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat).filter(category="PENDING")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context.update({'filter': 'on', 'cuscat': cuscat, 'loantype': loantype})
            return render(request, 'userloans_pending.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')
            
            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype).filter(category="PENDING")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context.update({'filter': 'on', 'loantype': loantype})
            return render(request, 'userloans_pending.html', context)
        
        elif request.POST.get('cuscat'): 
            
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat).filter(category="PENDING")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context.update({'filter': 'on', 'cuscat': cuscat})
            return render(request, 'userloans_pending.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('userloans_pending')
    
    return render(request, 'userloans_pending.html', context)

@check_staff
def userloans_all(request):

    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category='PENDING').all()
    pending_loans = Loan.objects.filter(category="PENDING")
    unfinished_loans = Loan.objects.filter(category="PENDING", status="AWAITING T&C", officer=request.user.id)
    review_loans = Loan.objects.filter(category="PENDING", status="UNDER REVIEW", officer=request.user.id)
    
    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry 

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_all')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).filter(category="FUNDED", funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }  
            
            return render(request,  'userloans_all.html', context)
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_all')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).filter(category="FUNDED",funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }
            
            return render(request,  'userloans_all.html', context)
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('cuscat'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            cuscat = request.POST.get('cuscat')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('userloans_all')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).filter(category="FUNDED", funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }         
                        
            return render(request,  'userloans_all.html', context)
        
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
                return redirect('userloans_all')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(funding_date__gte = start_date, funding_date__lte = end_date).filter(category="FUNDED", funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }      
            
            return render(request,  'userloans_all.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat).filter(category="FUNDED", funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat, 'loantype': loantype,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                        
                    }        
            
            return render(request,  'userloans_all.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')
            

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype).filter(category="FUNDED", funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'loantype': loantype, 
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }

            return render(request,  'userloans_all.html', context)

        elif request.POST.get('cuscat'):

            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat).filter(category="FUNDED", funded_category="ACTIVE")
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

            context = {
                        'nav' : 'loans', 'filter': 'on', 'referrer': referrer, 'domain':domain,
                        'cuscat': cuscat,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'unfinished_loans':unfinished_loans,
                        'review_loans': review_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,
                    }
            
            return render(request,  'userloans_all.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('userloans_all')

    all_loans_filtered = Loan.objects.filter(category="FUNDED", funded_category="ACTIVE").all()
    funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                'nav': 'userloans', 
                'all_loans': all_loans,
                'all_loans_filtered': all_loans_filtered,
                'pending_loans': pending_loans,
                'unfinished_loans':unfinished_loans,
                'review_loans': review_loans,
                'funded_sum': funded_sum,
                'interests_sum': interests_sum,
                'totalloan_sum': totalloan_sum,
                'repayments_sum': repayments_sum,
                'arrears_sum': arrears_sum,
                'defaultinterests_sum': defaultinterests_sum,
                'outstanding_sum': outstanding_sum,
            }

    return render(request, 'userloans_all.html', context)

def _get_client_active_loans(owner):
    """Return (active_funded, active_pending) querysets for a UserProfile owner."""
    active_funded = Loan.objects.filter(
        owner=owner,
        category='FUNDED',
        funded_category__in=['ACTIVE', 'RECOVERY', 'BAD', 'WOFF'],
    ).select_related('owner')
    active_pending = Loan.objects.filter(
        owner=owner,
        category='PENDING',
    ).exclude(status__in=['REJECTED', 'CANCELLED']).select_related('owner')
    return active_funded, active_pending


@check_staff
def client_loan_status_api(request, uid):
    """AJAX endpoint — returns JSON summary of a client's active loans."""
    from django.http import JsonResponse
    try:
        owner = UserProfile.objects.get(pk=uid)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)

    funded, pending = _get_client_active_loans(owner)

    running = []
    for l in funded:
        running.append({
            'ref': l.ref,
            'amount': str(l.amount),
            'outstanding': str(l.total_outstanding or 0),
            'status': l.status,
            'funded_category': l.funded_category,
        })
    pend = []
    for l in pending:
        pend.append({
            'ref': l.ref,
            'amount': str(l.amount),
            'status': l.status,
        })

    return JsonResponse({
        'client_name': f'{owner.first_name} {owner.last_name}',
        'has_active': funded.exists() or pending.exists(),
        'funded_loans': running,
        'pending_loans': pend,
    })


@check_staff
def client_has_loan(request, uid):
    """Guard page shown when staff tries to create a loan for a client who already has one."""
    try:
        owner = UserProfile.objects.get(pk=uid)
    except UserProfile.DoesNotExist:
        messages.error(request, 'Client not found.', extra_tags='danger')
        return redirect('create_loan')
    active_funded, active_pending = _get_client_active_loans(owner)
    from loan.refinance import refinance_allowed
    return render(request, 'client_has_loan.html', {
        'nav': 'userloans',
        'client_name': f'{owner.first_name} {owner.last_name}',
        'owner': owner,
        'active_funded': active_funded,
        'active_pending': active_pending,
        'refinance_allowed': refinance_allowed(),
    })


def create_loan(request):
    
    try:
        loan_setting = AdminSettings.objects.get(settings_name='setting1')
    except: 
        messages.error(request, f"Loan Administrator needs to update their settings first. Please contact issues@{domain}.com", extra_tags="danger")
        return redirect('dashboard')

    if request.method == 'POST':
        _owner_pk = request.POST.get('owner')
        _user_profile_for_mode = None
        if _owner_pk:
            try:
                _user_profile_for_mode = UserProfile.objects.get(pk=_owner_pk)
            except Exception:
                pass
        form = CreateLoanForm(request.POST, user_profile=_user_profile_for_mode)
        if form.is_valid():

            owner = form.cleaned_data['owner']
            location = form.cleaned_data['location']
            amount = form.cleaned_data['amount']

            # ── Existing Loan Guard ───────────────────────────────────────────
            _funded_loans, _pending_loans = _get_client_active_loans(owner)
            if _funded_loans.exists() or _pending_loans.exists():
                return redirect('client_has_loan', uid=owner.id)
            # ── End Existing Loan Guard ───────────────────────────────────────

            if settings.MULTIPLE_LOANS == 'NO':

                if Loan.objects.filter(owner=owner, category="FUNDED", funded_category="ACTIVE"):
                    messages.error(request, f"Client already has an active loan. Please contact {settings.SUPPORT_EMAIL}", extra_tags="warning")
                    return redirect('create_loan')
                if Loan.objects.filter(owner=owner, category="FUNDED", funded_category="RECOVERY"):
                    messages.error(request, f"Client already has a loan in recovery. Please contact {settings.SUPPORT_EMAIL}", extra_tags="danger")
                    return redirect('create_loan')
                if Loan.objects.filter(owner=owner, category="FUNDED", funded_category="BAD"):
                    messages.error(request, f"Client already has a bad loan with us. Please contact {settings.SUPPORT_EMAIL}", extra_tags="danger")
                    return redirect('create_loan')
                if Loan.objects.filter(owner=owner, category="FUNDED", funded_category="WOFF"):
                    messages.error(request, f"Client already has a written-off loan with us. Please contact {settings.SUPPORT_EMAIL}", extra_tags="danger")
                    return redirect('create_loan')
                if Loan.objects.filter(owner=owner, category="PENDING", status="AWAITING T&C"):
                    messages.error(request, f"Client already has a pending loan awaiting Clientr action. Cancel that if Client wish to apply for a new one.", extra_tags="warning")
                    return redirect('create_loan')
                if Loan.objects.filter(owner=owner, category="PENDING", status="UNDER REVIEW"):
                    messages.error(request, f"Client already has a pending loan under review. Cancel that if Client wish to apply for a new one.", extra_tags="warning")
                    return redirect('create_loan')
                if Loan.objects.filter(owner=owner, category="PENDING", status="APPROVED"):
                    messages.error(request, f"You already has a pending loan approved. Cancel that if you wish to apply for a new one.", extra_tags="warning")
                    return redirect('create_loan')
        
            num_fns = form.cleaned_data['number_of_fortnights']

            repayment_start_date = form.cleaned_data['repayment_start_date']
            user = owner
            loanref_prefix = loan_setting.loanref_prefix
            upid = user.id
            first_name = user.first_name
            last_name = user.last_name
            rand = random.randint(0,9)
            refx = f'{loanref_prefix}{upid}{first_name[0]}{last_name[0]}{rand}'
            repayment_limit = user.repayment_limit

            usr = User.objects.get(pk=user.user_id)
            
            if repayment_limit == 0.0:
                messages.error(request, 'Repayment limit for this user is not set yet, please view user and set it from profile action.', extra_tags='info')
                return redirect('userloans')
            
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
                    messages.error(request, f"Client's credit rating ({user.credit_rating}) is below the approval threshold ({_thr}). Loan not created.", extra_tags='danger')
                    return redirect('userloans')
            #with loan types 
            #loan = Loan.objects.create(ref = refx, officer=request.user, owner=owner, location=location, type=loantype, amount=amount)
            
            staff_profile = UserProfile.objects.get(user=request.user)
            staff = StaffProfile.objects.get(user=staff_profile)

            loan = Loan.objects.create(ref = refx, officer=staff, owner=owner, location=location, amount=amount)
            loanfile = LoanFile.objects.create(loan=loan)
            loanfile.save()
            loan_id = loan.id
            str_loan_id = str(loan_id)
            finalref_first_part = refx[:-1]
            final_ref = f'{finalref_first_part}{str_loan_id}'

            loan.ref = final_ref
            loan.uid = user.uid
            loan.luid = settings.LUID
            loan.save()

        
            #COMBINATIONS CHECK — skipped for Open Repayment (custom amounts outside table)
            if form.loan_mode != 'OPEN_REPAYMENT':
                max_fn = combination_check(amount, num_fns)
                if max_fn != 0:
                    loan.delete()
                    _range = term_range(amount)
                    _low, _high = _range if _range else (get_loan_config()['min_fn'], max_fn)
                    messages.error(request, f"Number of fortnights must be between {_low} and {_high} for an amount of K{amount:,.2f}. Please refer to the repayment table below. Click on 'Show Repayment Table'.", extra_tags='danger')
                    return redirect('userloans_unfinished')
            #COMBINATIONS CHECK _END

            #amount limit check
            _lc = get_loan_config()
            _effective_max = user.max_loan_amount if user.max_loan_amount else _lc["loan_max_amount"]
            if amount < _lc["loan_min_amount"]:
                loan.delete()
                messages.error(request, f'Loan amount must be more than {_lc["loan_min_amount"]}', extra_tags='danger')
                return redirect('create_loan')
            elif amount > _effective_max:
                loan.delete()
                messages.error(request, f'Loan amount must be less than {_effective_max}', extra_tags='danger')
                return redirect('create_loan')

            # Bounds come from Loan Settings, not a literal: a hardcoded 1-30
            # here refused 31-36 even though both the settings and the printed
            # schedule allow them.
            if fn_limits(num_fns) != 1:
                loan.delete()
                _cfg = get_loan_config()
                messages.error(request, f"Number of fortnights must be between {_cfg['min_fn']} and {_cfg['max_fn']}.", extra_tags='danger')
                return redirect('userloans_unfinished')
            
            loan.number_of_fortnights = num_fns
            start_of_payment = repayment_start_date
        
            now = datetime.date.today()
            after_fourteen_days = now + datetime.timedelta(days=28)
            
            if start_of_payment < now:
                loan.delete()
                messages.error(request, "The Start Date can not be in past. The date must be from now and 14 days.", extra_tags='danger')
                return redirect('userloans_unfinished')
            
            if start_of_payment > after_fourteen_days:
                loan.delete()
                messages.error(request, "The Start Date can not be after 14 days from now. The date must be between now and 14 days.", extra_tags='danger')
                return redirect('userloans_unfinished')
            
            loan.repayment_start_date = start_of_payment
            loan.save()

            #calculating_interest
            selected_fns = loan.number_of_fortnights
            amt = float(loan.amount)

            interest_type = settings.INTEREST_TYPE
            
            fortnightly_repayment = repayment(amt, interest_type, selected_fns)
            total_to_be_paid = fortnightly_repayment * selected_fns
            interest_to_be_paid = total_to_be_paid - amt
            
            rounded_interest = round(interest_to_be_paid,2)
            rounded_repayment_amount = round(fortnightly_repayment,2)     
            rounded_total_to_be_paid = round(total_to_be_paid, 2)

            if repayment_limit is None:
                loan.delete()
                messages.error(request, 'Repayment Limit is not set yet. Please advise admin to set that first.', extra_tags="danger")
                return redirect('userloans')

            if fortnightly_repayment > repayment_limit:
                loan.delete()
                messages.error(request, f'The repayment amount of K{rounded_repayment_amount} for this loan is greater than the user\'s personal repayment limit of K{repayment_limit}. Please apply again within repayment limit.', extra_tags='danger')
                return redirect('userloans') 

            loan.interest = rounded_interest
            loan.repayment_frequency = 'FORTNIGHLTY'
            loan.category = 'PENDING'
            loan.status = 'AWAITING T&C'
            loan.repayment_amount = rounded_repayment_amount
            loan.application_fee = settings.LOAN_APPLICATION_FEE
            loan.total_loan_amount = rounded_total_to_be_paid

            # Record the applicable processing fee tier at creation time (if enabled)
            try:
                from admin1.models import ProcessingFeeTier as _PFT, AdminSettings as _ASet
                _fee_on = getattr(_ASet.objects.get(settings_name='setting1'), 'processing_fee', 'NO') == 'YES'
                loan.processing_fee = _PFT.get_fee_for_amount(loan.amount) if _fee_on else 0
            except Exception:
                loan.processing_fee = 0

            if settings.LOAN_TYPES != 1:
                messages.error(request, 'Administrator needs to enable loan type on application forms first. Please raise a support ticket for this.', extra_tags="danger")
                return redirect('userloans_unfinished')
            else:
                loan.type = 'PERSONAL'

            loan.save()

            messages.success(request, "Loan application has been created successfully.")

            # Build the prefilled application documents email honouring admin
            # Loan Settings (enable/disable, recipients, which documents).
            from loan.functions import build_application_documents_email
            email = build_application_documents_email(
                loan, user, usr, loan_setting,
                uid=urlsafe_base64_encode(force_bytes(usr.pk)),
                token=loan_tc_agreement_token.make_token(usr),
                staff_email=request.user.email,
            )

            #clear existing loans that were not agreed to
            loans = Loan.objects.filter(owner=owner, tc_agreement='tct')

            for loanx in loans:
                loanx.delete()

            if email is None:
                loan.tc_agreement = 'tct'
                loan.save()
                messages.success(request, "The loan application has been recorded.", extra_tags='info')
                return redirect('userloans_unfinished')

            try:
                email.send()
                loan.tc_agreement = 'tct'
                loan.save()
                messages.success(request, "The Terms & Conditions have been emailed to you, Please read, sign if you agree and upload in your requirements section.", extra_tags='info')
            except:
                messages.error(request, "The Terms & Conditions Agreement email could not be sent, make sure you have internet connection and try apply again.", extra_tags='danger')
                loan.delete()

            return redirect('userloans_unfinished')
    else:
        form = CreateLoanForm()
        
    return render(request, 'create_loan.html', { 'nav':'loans', 'form': form })        
   

@check_staff
def review_loan(request, loan_ref):

    loan = Loan.objects.get(ref=loan_ref)
    user = UserProfile.objects.get(pk=loan.owner.id)
    
    user.application_form_url = loan.application_form_url
    user.terms_conditions_url = loan.terms_conditions_url
    user.stat_dec_url = loan.stat_dec_url
    user.irr_sd_form_url = loan.irr_sd_form_url
    user.super_statement_url = loan.super_statement_url
    user.bank_statement_url = loan.bank_statement_url
    user.bank_standing_order_url = loan.bank_standing_order_url
    
    loan.officer = request.user
    loan.status = 'UNDER REVIEW'
    loan.save()
    
    return redirect('view_loan_staff', loan_ref)
    
@check_staff
def view_loan_staff(request, loan_ref):

    
    loan = Loan.objects.select_related('owner').get(ref=loan_ref)
    uid = loan.owner_id
    user = UserProfile.objects.get(pk=uid)
    usr = User.objects.get(pk=user.user_id)
    last_name_s = user.last_name[-1]
    stat = Statement.objects.filter(loanref=loan)
    try:
        loanfile = LoanFile.objects.get(loan=loan)
    except:
        loanfile = []
    
    if request.method=='POST':
        
        if request.POST.get('subject') and request.POST.get('messageapplicant'):
            
            
            subject = request.POST.get('subject')
            ''' if header_cta == 'yes' '''
            cta_label = ''
            cta_link = ''

            greeting = f'Hi {user.first_name}'
            message = f'This is regarding your pending loan application of ref: {loan_ref}'
            message_details = request.POST.get('messageapplicant')

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
            email = EmailMultiAlternatives(subject,text_content,sender,['dev@webmasta.com.pg', user.email ])
            email.attach_alternative(email_content, "text/html")

            try: 
                email.send()
                messages.success(request, "Message has been forwarded successfully")
                return redirect('pending_loans')
            except:
                messages.error(request, 'Message has not been sent.', extra_tags='danger')
 
            return redirect('view_loan', loan_ref)

    try:
        _show_referrer = AdminSettings.objects.get(settings_name='setting1').display_referrer_on_loan
        from admin1.models import referral_program_enabled as _rpe
        _show_referrer = _show_referrer and _rpe()
    except Exception:
        _show_referrer = True
    # Newest statement line the "Reverse Last Statement" button can undo
    # (funding / interest / refinance lines are structural and never reversible).
    from loan.reversal import REVERSIBLE_TYPES as _REV_TYPES
    _last = Statement.objects.filter(loanref=loan).order_by('-pk').first()
    reversal_info = _last if (_last is not None and _last.type in _REV_TYPES) else None
    return render(request, 'view_loan_staff.html', {'nav': 'userloans', 'loan':loan, 'user':user, 'usr': usr, 'last_name_s':last_name_s , 'stat': stat, 'domain': domain, 'loanfile':loanfile, 'show_referrer': _show_referrer, 'referrer': getattr(user, 'referred_by', None), 'reversal_info': reversal_info })


@check_staff
def download_las_staff(request, loan_ref):
    from admin1.mainView import _build_las_context
    loan = Loan.objects.get(ref=loan_ref)
    user = UserProfile.objects.get(id=loan.owner_id)
    context = _build_las_context(loan, user, settings.DOMAIN)
    from moromafinance.pdf import django_pdf_response
    return django_pdf_response(
        request, 'custom/loan_amortization_schedule.html', context,
        f'LAS_{loan_ref}.pdf', inline=(request.GET.get('inline') == '1'),
    )


@check_staff
def download_cdn_staff(request, loan_ref):
    import datetime
    from decimal import Decimal as _D
    loan = Loan.objects.get(ref=loan_ref)
    user = UserProfile.objects.get(id=loan.owner_id)
    funding_date = loan.funding_date.strftime('%d/%m/%Y') if loan.funding_date else datetime.date.today().strftime('%d/%m/%Y')
    first_repayment_date = loan.next_payment_date.strftime('%d %B %Y') if loan.next_payment_date else ''
    bank_config = get_bank_config()
    fee = _D(str(loan.processing_fee or 0))
    loan_amount = _D(str(loan.amount or 0))
    try:
        fee_mode = AdminSettings.objects.get(settings_name='setting1').processing_fee_collection_mode
    except Exception:
        fee_mode = 'CASH'
    context = {
        'loan': loan, 'user': user,
        'today': datetime.date.today().strftime('%d %B %Y'),
        'funding_date': funding_date,
        'first_repayment_date': first_repayment_date,
        'domain': settings.DOMAIN,
        'disbursed_amount': loan_amount - fee if fee_mode == 'WITHHELD' and fee > 0 else loan_amount,
        'fee_collection_mode': fee_mode,
        'bank_name': bank_config["bank"],
        'bank_account_name': bank_config["bank_acc_name"].title(),
        'bank_account_number': bank_config["bank_acc_num"],
        'bank_branch': bank_config["bank_branch"].title(),
        'deduction_code': bank_config["alesco_dc"],
        'document_theme': get_document_theme(),
    }
    from moromafinance.pdf import django_pdf_response
    return django_pdf_response(
        request, 'custom/cash_disbursement_notice.html', context,
        f'CDN_{loan_ref}.pdf', inline=(request.GET.get('inline') == '1'),
    )


@check_staff
def tc_upload(request, loan_ref):

    loan = Loan.objects.get(ref=loan_ref)
    user = UserProfile.objects.get(pk=loan.owner.id)

    if request.method == 'POST':
        uploadform = UploadRequirementsByStaffForm(request.POST)
        
        if user.first_name == '' and user.last_name == '':
            return redirect('edit_personalinfo')
        
        if uploadform.is_valid():

            if Loan.objects.filter(owner=user.id, category='PENDING', status='AWAITING T&C'):
                try:
                    loan = Loan.objects.get(owner=user.id, category='PENDING', status='AWAITING T&C')
                except:
                    messages.error(request, "You probably have more than one pending loans 'Awaiting T&C'. Always make sure there is ONLY ONE pending loan under review before uploading the required documents.", extra_tags='warning')
                    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
                    return redirect(referrer)
            else:
                try:
                    loan = Loan.objects.get(owner=user.id, category='PENDING', status='UNDER REVIEW')
                except:
                    messages.error(request, "You probably have NO pending loan. Apply for a new loan", extra_tags='warning')
                    return redirect('loan_application')

            if 'application_form' in request.FILES:
                loanfileuploader(request,'application_form', user, loan)
            
            if 'terms_conditions' in request.FILES:
                loanfileuploader(request,'terms_conditions', user, loan)
                
            if 'stat_dec' in request.FILES:
                loanfileuploader(request,'stat_dec', user, loan)

            if 'irr_sd_form' in request.FILES:
                loanfileuploader(request,'irr_sd_form', user, loan)
            
            if 'work_confirmation_letter' in request.FILES:
                loanfileuploader(request,'work_confirmation_letter', user, loan)
                
            if 'payslip1' in request.FILES:
                loanfileuploader(request,'payslip1', user, loan)
            
            if 'payslip2' in request.FILES:
                loanfileuploader(request,'payslip2', user, loan)

            if 'loan_statement1' in request.FILES:
                loanfileuploader(request,'loan_statement1', user, loan)
            
            if 'loan_statement2' in request.FILES:
                loanfileuploader(request,'loan_statement2', user, loan)
                
            if 'loan_statement3' in request.FILES:
                loanfileuploader(request,'loan_statement3', user, loan)
                
            if 'bank_statement' in request.FILES:
                loanfileuploader(request,'bank_statement', user, loan)
            
            if 'super_statement' in request.FILES:
                loanfileuploader(request,'super_statement', user, loan)

            if 'bank_standing_order' in request.FILES:
                loanfileuploader(request,'bank_standing_order', user, loan)

            if LoanFile.objects.get(loan=loan):
                    loanfile = LoanFile.objects.get(loan=loan)
                    if loanfile.application_form_url and loanfile.terms_conditions_url and loanfile.stat_dec_url and loanfile.irr_sd_form_url and loanfile.bank_statement_url and loanfile.payslip1_url and loanfile.payslip2_url and loanfile.work_confirmation_letter_url:
                        request_approval(loan)

                        messages.success(request, 'Loan updated and classified as "Under Review"', extra_tags='info')
  
            return redirect('view_loan_staff', loan.ref)
    else:
        uploadform = UploadRequirementsByStaffForm()  
    
    return render(request, 'tc_upload.html', {'nav':'userloans', 'loan': loan, 'form': uploadform })

@check_staff
def loan_req_matrix(request):
 
    pending_loans = Loan.objects.filter(category='PENDING')
    
    return render(request, 'loan_req_matrix.html', {'nav':'loan_requirements', 'pending_loans': pending_loans})       

@check_staff
def usercredit(request):
    return render(request, 'credit_rating_staff.html', {'nav': 'usercredit'})  


#######################
# USERS
#######################

@check_staff
def usermembers(request):

    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    profiles = UserProfile.objects.all()
    unfinished = profiles.filter(activation=0)
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    locations = Location.objects.all()
    loc_count = locations.count()
    
    clients = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0)
    
    if request.method=='POST':
        
        if request.POST.get('cuscat') and request.POST.get('locationx') and request.POST.get('loanopt'):
            
            cuscat = request.POST.get('cuscat') 
            loanopt = request.POST.get('loanopt')  
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)
            
            if loanopt == 'withloan':
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='MEMBER', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav': 'usermembers', 'filter': 'on', 'referrer': referrer, 'profiles':profiles,'unfinished':unfinished,
                        'locations': locations,
                        'location': location,
                        'loc_count': loc_count,
                        'loanopt': 'WITH LOAN',
                        'cuscat': cuscat,
                        'clients_filtered':clients_filtered,
                        'members_filtered':clients_filtered,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                     
                    return render(request, 'usermembers.html', context) 
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='NON-MEMBER', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav': 'usermembers', 'filter': 'on', 'referrer': referrer, 'profiles':profiles,'unfinished':unfinished,
                        'locations': locations,
                        'location': location,
                        'loc_count': loc_count,
                        'loanopt': 'WITH LOAN',
                        'cuscat': cuscat,
                        'clients_filtered':clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':clients_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                     
                    return render(request, 'usermembers.html', context) 
                 
                else:
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='STAFF', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav': 'usermembers', 'filter': 'on', 'referrer': referrer, 'profiles':profiles,'unfinished':unfinished,
                        'locations': locations,
                        'location': location,
                        'loc_count': loc_count,
                        'loanopt': 'WITH LOAN',
                        'cuscat': cuscat,
                        'clients_filtered':clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                     
                    return render(request, 'usermembers.html', context) 
            else:
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='MEMBER', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav': 'usermembers', 'filter': 'on', 'referrer': referrer, 'profiles':profiles,'unfinished':unfinished,
                        'locations': locations,
                        'location': location,
                        'loc_count': loc_count,
                        'loanopt': 'WITHOUT LOAN',
                        'cuscat': cuscat,
                        'clients_filtered':clients_filtered,
                        'members_filtered':clients_filtered,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':0,
                        'withoutl_filtered':clients_filtered,
                    }
                     
                    return render(request, 'usermembers.html', context) 
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='NON-MEMBER', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav': 'usermembers', 'filter': 'on', 'referrer': referrer, 'profiles':profiles,'unfinished':unfinished,
                        'locations': locations,
                        'location': location,
                        'loc_count': loc_count,
                        'loanopt': 'WITHOUT LOAN',
                        'cuscat': cuscat,
                        'clients_filtered':clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':clients_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':0,
                        'withoutl_filtered':clients_filtered,
                    }
                     
                    return render(request, 'usermembers.html', context) 
                 
                else:
                    clients_filtered = clients.filter(number_of_loans=0, category='STAFF', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav': 'usermembers', 'filter': 'on', 'referrer': referrer, 'profiles':profiles,'unfinished':unfinished,
                        'locations': locations,
                        'location': location,
                        'loc_count': loc_count,
                        'loanopt': 'WITHOUT LOAN',
                        'cuscat': cuscat,
                        'clients_filtered':clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':0,
                        'withoutl_filtered':clients_filtered, 
                    }
                     
                    return render(request, 'usermembers.html', context) 
            
        elif request.POST.get('cuscat') and request.POST.get('locationx'):
            
            cuscat = request.POST.get('cuscat') 
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)  
            
            if cuscat == 'MEMBER':
                clients_filtered = clients.filter(category='MEMBER', location=location)
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                

                context = {
                    'nav': 'usermembers', 'filter': 'on', 'referrer': referrer, 'profiles':profiles,'unfinished':unfinished,
                        'locations': locations,
                    'location': location,
                    'loc_count': loc_count,
                    'cuscat': cuscat,
                    'clients_filtered':clients_filtered,
                    'members_filtered':clients_filtered,
                    'nonmembers_filtered':0,
                    'private_filtered':private_filtered,
                    'public_filtered':public_filtered,
                    'withl_filtered':withl_filtered,
                    'withoutl_filtered':withoutl_filtered,
                    
                }
                    
                return render(request, 'usermembers.html', context) 
                            
            elif cuscat == 'NON-MEMBER':
                clients_filtered = clients.filter(category='NON-MEMBER', location=location)
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                

                context = {
                    'nav': 'usermembers', 'filter': 'on', 'referrer': referrer, 'profiles':profiles,'unfinished':unfinished,
                        'locations': locations,
                    'location': location,
                    'loc_count': loc_count,
                    'cuscat': cuscat,
                    'clients_filtered':clients_filtered,
                    'members_filtered':0,
                    'nonmembers_filtered':clients_filtered,
                    'private_filtered':private_filtered,
                    'public_filtered':public_filtered,
                    'withl_filtered':withl_filtered,
                    'withoutl_filtered':withoutl_filtered,
                    
                }
                    
                return render(request, 'usermembers.html', context)  
                 
            else:
                clients_filtered = clients.filter(category='STAFF', location=location)
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                

                context = {
                    'nav': 'usermembers', 'filter': 'on', 'referrer': referrer, 'profiles':profiles,'unfinished':unfinished,
                        'locations': locations,
                    'location': location,
                    'loc_count': loc_count,
                    'cuscat': cuscat,
                    'clients_filtered':clients_filtered,
                    'members_filtered':0,
                    'nonmembers_filtered':0,
                    'private_filtered':private_filtered,
                    'public_filtered':public_filtered,
                    'withl_filtered':withl_filtered,
                    'withoutl_filtered':withoutl_filtered,
                    
                }
                    
                return render(request, 'usermembers.html', context) 
                
        elif request.POST.get('cuscat') and request.POST.get('loanopt'):
            
            cuscat = request.POST.get('cuscat')  
            loanopt = request.POST.get('loanopt')  
             
            if loanopt == 'withloan':
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='MEMBER')
                    
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    
                    context = {
                            'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                            'locations': locations,
                            'cuscat': cuscat,
                            'loanopt': 'WITH LOAN',
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'usermembers.html', context)  
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                            'locations': locations,
                            'cuscat': cuscat,
                            'loanopt': 'WITH LOAN',
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                            
                        }
                    
                    return render(request, 'usermembers.html', context)  
                else:
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                            'locations': locations,
                            'cuscat': cuscat,
                            'loanopt': 'WITH LOAN',
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'usermembers.html', context)
            else:
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='MEMBER') 
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                            'locations': locations,
                            'cuscat': cuscat,
                            'loanopt': 'WITHOUT LOAN',
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'usermembers.html', context)                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                            'locations': locations,
                            'cuscat': cuscat,
                            'loanopt': 'WITHOUT LOAN',
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'usermembers.html', context)   
                else:
                    clients_filtered = clients.filter(number_of_loans=0, category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                            'locations': locations,
                            'cuscat': cuscat,
                            'loanopt': 'WITHOUT LOAN',
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'usermembers.html', context)
        
        elif request.POST.get('locationx') and request.POST.get('loanopt'):
 
            loanopt = request.POST.get('loanopt')  
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)
              
            if loanopt == 'withloan':
                    
                clients_filtered = clients.filter(number_of_loans__gt=0, location=location)
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                        'locations': locations,
                        'location': location,
                        'loanopt': 'WITH LOAN',
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                
                return render(request, 'usermembers.html', context)  
                            
            else:
                
                clients_filtered = clients.filter(number_of_loans=0, location=location) 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                        'locations': locations,
                        'location': location,
                        'loanopt': 'WITHOUT LOAN',
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':0,
                        'withoutl_filtered':clients_filtered,
                    }
                
                return render(request, 'usermembers.html', context)                         
                
            
        elif request.POST.get('cuscat'):
            
            cuscat = request.POST.get('cuscat')   
                
            if cuscat == 'MEMBER':
                
                clients_filtered = clients.filter(category='MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                        'locations': locations,
                        'cuscat': cuscat,
                        'clients_filtered': clients_filtered,
                        'members_filtered':clients_filtered,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                return render(request, 'usermembers.html', context)    
                    
            elif cuscat == 'NON-MEMBER':
                
                clients_filtered = clients.filter(category='NON-MEMBER') 
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                        'locations': locations,
                        'cuscat': cuscat,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':clients_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,    
                    }
                
                return render(request, 'usermembers.html', context)  
            
            else:
                clients_filtered = clients.filter(category='STAFF')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                        'locations': locations,
                        'cuscat': cuscat,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'usermembers.html', context)        
          
        elif request.POST.get('locationx'):

            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx) 
                        
            clients_filtered = clients.filter(location=location)
            members_filtered = clients_filtered.filter(category='MEMBER')
            nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
            private_filtered = clients_filtered.filter(sector='PRIVATE')
            public_filtered = clients_filtered.filter(sector='PUBLIC')
            withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
            withoutl_filtered = clients_filtered.filter(number_of_loans=0)
            
            
            context = {
                    'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                    'locations': locations,
                    'location': location,
                    'clients_filtered': clients_filtered,
                    'members_filtered':members_filtered,
                    'nonmembers_filtered':nonmembers_filtered,
                    'private_filtered':private_filtered,
                    'public_filtered':public_filtered,
                    'withl_filtered':withl_filtered,
                    'withoutl_filtered':withoutl_filtered,
                }
            
            return render(request, 'usermembers.html', context)                      
            
        elif request.POST.get('loanopt'):
  
            loanopt = request.POST.get('loanopt')  
                
            if loanopt == 'withloan':
                    
                clients_filtered = clients.filter(number_of_loans__gt=0)
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                        'locations': locations,
                        'loanopt': 'WITH LOAN',
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                
                return render(request, 'usermembers.html', context)  
                            
            else:
                
                clients_filtered = clients.filter(number_of_loans=0) 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'locations', 'filter': 'on', 'referrer': referrer,
                        'locations': locations,
                       'loanopt': 'WITHOUT LOAN',
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':0,
                        'withoutl_filtered':clients_filtered,
                    }
                
                return render(request, 'usermembers.html', context)                       
                            
    clients_filtered = clients
    members_filtered = clients.filter(category='MEMBER')  
    nonmembers_filtered = clients.filter(category='NON-MEMBER')
    private_filtered = clients.filter(sector='PRIVATE')
    public_filtered = clients.filter(sector='PUBLIC')
    withl_filtered = clients.filter(number_of_loans__gt=0)
    withoutl_filtered = clients.filter(number_of_loans=0)

    context = {
        'nav': 'usermembers',
        'locations': locations,
        'loc_count': loc_count,
        'clients_filtered':clients_filtered,
        'members_filtered':members_filtered,
        'nonmembers_filtered':nonmembers_filtered,
        'private_filtered':private_filtered,
        'public_filtered':public_filtered,
        'withl_filtered':withl_filtered,
        'withoutl_filtered':withoutl_filtered,
        
    }
    
    
    
    return render(request, 'usermembers.html', context )

from accounts.functions import staff_or_admin_check as _staff_or_admin
@_staff_or_admin
def add_user(request):
    
    if request.method == 'POST':
        memberinfoform = MemberInfoForm(request.POST)
        if  memberinfoform.is_valid():
            
            first_name = memberinfoform.cleaned_data['first_name']
            middle_name = memberinfoform.cleaned_data['middle_name']
            last_name = memberinfoform.cleaned_data['last_name']
            gender = memberinfoform.cleaned_data['gender']
            date_of_birth = memberinfoform.cleaned_data['date_of_birth']
            email = memberinfoform.cleaned_data['email']
            phone = memberinfoform.cleaned_data['mobile1']

            # ── Duplicate client guard ────────────────────────────────────────
            # Block creating a client that already exists. A duplicate is the same
            # first + last name with the same date of birth, OR the same mobile
            # number, OR the same email — matched case-insensitively.
            from django.db.models import Q as _Q
            _dupe_q = _Q()
            if first_name and last_name and date_of_birth:
                _dupe_q |= _Q(first_name__iexact=first_name.strip(),
                              last_name__iexact=last_name.strip(),
                              date_of_birth=date_of_birth)
            if phone:
                _dupe_q |= _Q(mobile1=phone)
            if email:
                _dupe_q |= _Q(email__iexact=email.strip())
            _existing = UserProfile.objects.filter(_dupe_q).first() if _dupe_q else None
            if _existing:
                messages.error(
                    request,
                    f'A client that matches these details already exists: '
                    f'{_existing.first_name} {_existing.last_name} '
                    f'(DOB {_existing.date_of_birth}, mobile {_existing.mobile1 or "—"}). '
                    f'Please search for and use the existing client instead of creating a duplicate.',
                    extra_tags='danger',
                )
                return redirect('view_client', _existing.id)

            randomid = id_generator(3).lower()
            random_num = random.randint(1000,9999)

            random_email = f'{first_name[0]}{last_name[0]}{random_num}'.lower()
            
            password = f'{random_email}{randomid}'

            if email:
                existing_user = User.objects.filter(email=email)
                if existing_user:
                    messages.error(request, "A user with this email address already exists", extra_tags='danger')
                    return redirect('add_user')
                else:
                    user = User.objects.create_user(email=email, password=password)
                    user.active=True
                    user.confirmed=True
                    user.save()

            else:
                
                email = f'{random_email}@{settings.DOMAIN_DNS}'
                user = User.objects.create_user(email=email, is_active=True, is_confirmed=True, password=password)
                user.active=True
                user.confirmed=True
                user.save()
                
                
            referred_by = memberinfoform.cleaned_data.get('referred_by')
            user_profile = UserProfile.objects.create(user=user, first_name=first_name, middle_name=middle_name, last_name=last_name, gender=gender, date_of_birth=date_of_birth, email=email, mobile1=phone, referred_by=referred_by)
            
             
            try:
                prefix = AdminSettings.objects.get(name='settings1').loanref_prefix
            except:
                prefix = settings.PREFIX
            
            user_profile.uid = f'{prefix}{random_num}'
            user_profile.modeofregistration = 'OTC'
            user_profile.luid = settings.LUID
            # Signed up over the counter: the client agreed to the terms and to
            # the credit check on the paper form in front of the staff member,
            # so there is no online consent step left for them to complete.
            user_profile.terms_consent = 'YES'
            user_profile.credit_consent = 'YES'
            user_profile.save()

            #activate user and apply admin-configured default repayment limit
            user_profile.activation = 1
            from accounts.functions import get_default_repayment_limit as _get_limit
            _default_limit = _get_limit()
            if _default_limit is not None:
                user_profile.repayment_limit = _default_limit
            elif not user_profile.repayment_limit:
                user_profile.repayment_limit = 500  # fallback if no setting configured

            user_profile.save()
            
            try:
                MessageLog.objects.create(user=user)
            except:
                pass

            # Auto-create referral record if a referrer was selected
            from admin1.models import referral_program_enabled as _rpe2
            if referred_by and _rpe2():
                try:
                    from referral.models import ReferralRecord
                    commission = 0
                    try:
                        commission = AdminSettings.objects.get(settings_name='setting1').referral_commission or 0
                    except Exception:
                        pass
                    ReferralRecord.objects.create(
                        referrer=referred_by,
                        client=user_profile,
                        commission_amount=commission,
                    )
                    messages.success(request, f'Referral commission of K{commission} recorded for {referred_by.name}.', extra_tags='info')
                except Exception:
                    pass

            messages.success(request, f'Member Profile for {user_profile.first_name} {user_profile.last_name} created successfully!')
            
            if email:
                #to send email
                # HTML EMAIL
                #send email to user
                
                
                subject = 'Member Profile Created'
                ''' if header_cta == 'yes' '''
                cta_label = ''
                cta_link = ''

                greeting = f'Hi {first_name}'
                message = 'Your member profile has been created <b>successfully</b>.'
                message_details = f'You can supply more information for us to assist you with obtaining a loan or You can login to your dasboard to update your own profile. <br> Login Details:<br><br> Username: <span style="color: #0000FF">{email}</span><br>Password: <span style="color: #0000FF">{password}</span>'

                ''' if cta == 'yes' '''
                cta_btn1_label = 'Visit Dashboard'
                cta_btn1_link = f'{settings.DOMAIN}/accounts/dashboard/'
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
                    'cta': 'yes',
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
                email = EmailMultiAlternatives(subject,text_content,sender,['dev@webmasta.com.pg', user.email ])
                email.attach_alternative(email_content, "text/html")

                try: 
                    email.send()
                    messages.success(request, "Member Profile Creation notice sent to user's email address.", extra_tags='info')
                except:
                    messages.error(request, 'Member Profile Creation notice could not be sent.', extra_tags='danger')
                    
                return redirect('view_member', user_profile.id)
                        
        return redirect('usermembers')
    else:
        memberinfoform = MemberInfoForm()
    
    return render(request, 'adduser.html', {'nav': 'usermembers', 'form': memberinfoform})

@check_staff
def view_member(request, uid):

    user_profile = UserProfile.objects.get(id=uid)
    try:
        smeprofile = SMEProfile.objects.get(owner_id=uid)
    except:
        smeprofile = 0

    #from django.db.models import Q
    # Combine the two queries into one
    combined_query = Q(owner=user_profile.id) & Q(category='PENDING') & (Q(status='AWAITING T&C') | Q(status='UNDER REVIEW'))
    # Retrieve loans matching the combined query
    combined_loans = Loan.objects.filter(combined_query)
    # Now combined_loans contains loans that satisfy both conditions
    field_settings = get_field_settings()
    loanfile = None
    if combined_loans:
        try:
            loan = Loan.objects.get(combined_query)
            loanfile = LoanFile.objects.get(loan=loan)
        except Exception:
            pass
    return render(request, 'view_member.html', {'nav': 'usermembers', 'user': user_profile, 'smeprofile': smeprofile, 'loanfile': loanfile, 'field_settings': field_settings})

##### EDIT PROFILE 

@check_staff
def edit_personalinfo_staff(request, uid):
    
    user_profile = UserProfile.objects.get(id=uid)
        
    initial_data = {
        'first_name': user_profile.first_name,
        'middle_name': user_profile.middle_name,
        'last_name': user_profile.last_name,
        'gender': user_profile.gender,
        'date_of_birth': user_profile.date_of_birth,
        'marital_status': user_profile.marital_status,
    }

    if request.method == 'POST':
        personalinfoUpdateForm = PersonalInfoForm(request.POST)
        if  personalinfoUpdateForm.is_valid():
            
            user_profile.first_name = personalinfoUpdateForm.cleaned_data.get('first_name', user_profile.first_name)
            user_profile.save()
            user_profile.middle_name = personalinfoUpdateForm.cleaned_data.get('middle_name', user_profile.middle_name)
            user_profile.save()
            user_profile.last_name = personalinfoUpdateForm.cleaned_data.get('last_name', user_profile.last_name)
            user_profile.save()
            user_profile.gender = personalinfoUpdateForm.cleaned_data.get('gender', user_profile.gender)
            user_profile.save()
            user_profile.date_of_birth = personalinfoUpdateForm.cleaned_data.get('date_of_birth', user_profile.date_of_birth)
            user_profile.save()
            user_profile.marital_status = personalinfoUpdateForm.cleaned_data.get('marital_status', user_profile.marital_status)
            user_profile.save()

            if 'propic' in request.FILES:
                fileuploader(request,'propic', user_profile)
            
            messages.success(request, 'Personal information updated successfully!')
            
        return redirect('view_member', uid)
    else:
        personalinfoUpdateForm = PersonalInfoForm(initial=initial_data)
        
    return render(request, 'edit_personalinfo_staff.html', { 'nav':'profile','form':personalinfoUpdateForm, 'user_profile': user_profile })

@check_staff
def edit_required_uploads_staff(request, uid):
    
    user = UserProfile.objects.get(id=uid)
    
    if request.method == 'POST':
        uploadform = RequiredUploadForm(request.POST)
        
        if user.first_name == '' and user.last_name == '':
            return redirect('edit_personalinfo_staff')
        
        if uploadform.is_valid():

            if Loan.objects.filter(owner=user.id, category='PENDING', status='AWAITING T&C'):
                try:
                    loan = Loan.objects.get(owner=user.id, category='PENDING', status='AWAITING T&C')
                except:
                    messages.error(request, "You probably have more than one pending loans 'Awaiting T&C'. Always make sure there is ONLY ONE pending loan under review before uploading the required documents.", extra_tags='warning')
                    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
                    return redirect(referrer)
            else:
                try:
                    loan = Loan.objects.get(owner=user.id, category='PENDING', status='UNDER REVIEW')
                except:
                    messages.error(request, "You probably have NO pending loan. Apply for a new loan", extra_tags='warning')
                    return redirect('loan_application')

            if 'application_form' in request.FILES:
                loanfileuploader(request,'application_form', user, loan)
            
            if 'terms_conditions' in request.FILES:
                loanfileuploader(request,'terms_conditions', user, loan)
                
            if 'stat_dec' in request.FILES:
                loanfileuploader(request,'stat_dec', user, loan)

            if 'irr_sd_form' in request.FILES:
                loanfileuploader(request,'irr_sd_form', user, loan)
            

            if LoanFile.objects.get(loan=loan):
                    loanfile = LoanFile.objects.get(loan=loan)
                    if loanfile.application_form_url and loanfile.terms_conditions_url and loanfile.stat_dec_url and loanfile.irr_sd_form_url and loanfile.bank_statement_url and loanfile.payslip1_url and loanfile.payslip2_url and loanfile.work_confirmation_letter_url:
                        request_approval(loan)

            messages.success(request, 'Required documents uploaded successfully...')

            return redirect('view_member', uid)
    else:
        uploadform = RequiredUploadForm()        
    return render(request, 'edit_required_uploads_staff.html', { 'form': uploadform, })     

@check_staff
def edit_addressinfo_staff(request, uid):
    
    user_profile = UserProfile.objects.get(id=uid)
    
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
        return redirect('view_member', uid)
    else:
        addressinfoUpdateForm = AddressInfoForm(initial=initial_data)
    return render(request, 'edit_addressinfo_staff.html', {'nav':'profile','form':addressinfoUpdateForm, 'user_profile': user_profile })
   
@check_staff
def edit_bankinfo_staff(request, uid):
    
    user_profile = UserProfile.objects.get(id=uid)
    
    initial_data = {
        'bank': user_profile.bank,
        'bank_account_name': user_profile.bank_account_name,
        'bank_account_number': user_profile.bank_account_number,
        'bank_branch': user_profile.bank_branch,
    }

    if request.method == 'POST':
        
        if user_profile.first_name == '' and user_profile.last_name == '':
            return redirect('edit_personalinfo_staff')
        
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
            
            
            messages.success(request, 'Primary Bank Account information Updated Successfully!') 
        
        return redirect('view_member', uid)
    
    else:
        bankinfoUpdateForm = BankAccountInfoForm(initial=initial_data)
    return render(request, 'edit_bankinfo_staff.html', {'nav':'profile','form':bankinfoUpdateForm, 'user_profile': user_profile})

@check_staff
def edit_bankinfo2_staff(request, uid):
    
    user_profile = UserProfile.objects.get(id=uid)
    
    initial_data = {
        'bank2': user_profile.bank2,
        'bank_account_name2': user_profile.bank_account_name2,
        'bank_account_number2': user_profile.bank_account_number2,
        'bank_branch2': user_profile.bank_branch2,
        'bank_standing_order2_url': user_profile.bank_standing_order2_url
    }

    if request.method == 'POST':
        
        if user_profile.first_name == '' and user_profile.last_name == '':
            return redirect('edit_personalinfo_staff')
        
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
                fileuploader(request,'bank_standing_order2', user_profile)
            
            messages.success(request, 'Secondary Bank Account information Updated Successfully!') 
        return redirect('view_member', uid)
    
    else:
        bankinfoUpdate2Form = BankAccountInfo2Form(initial=initial_data)
    return render(request, 'edit_bankinfo2_staff.html', {'nav':'profile','form':bankinfoUpdate2Form,'user_profile': user_profile  })

@check_staff
def edit_useruploads_staff(request, uid):
    
    user = UserProfile.objects.get(id=uid)
   
    initial_data = {
        'nid_number': user.nid_number,
        'passport_number': user.passport_number,
        'drivers_license_number': user.drivers_license_number,
        'super_member_code': user.super_member_code
    }
    
    if request.method == 'POST':
        uploadform = UserUploadForm(request.POST)
        
        if user.first_name == '' and user.last_name == '':
            messages.error(request, "You need to update client's First Name and Last Name first...",extra_tags="warning")
            return redirect('edit_personalinfo')
        
        if uploadform.is_valid():
            
            if 'nid' in request.FILES:
                fileuploader(request,'nid', user)
                
            if 'passport' in request.FILES:
                fileuploader(request,'nid', user)
            
            if 'drivers_license' in request.FILES:
                fileuploader(request,'passport', user)
            
            if 'superid' in request.FILES:
                fileuploader(request,'superid', user)
            
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
                
            messages.success(request, 'Personal ID information Updated Successfully!') 
            return redirect('view_member', uid)
    else:
        uploadform = UserUploadForm(initial=initial_data)        
    return render(request, 'edit_useruploads_staff.html', { 'form': uploadform, 'user_profile': user })   
                
@check_staff
def edit_work_uploads_staff(request, uid):
    
    user = UserProfile.objects.get(id=uid)
    
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
                    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
                    return redirect(referrer)
            else:
                try:
                    loan = Loan.objects.get(owner=user.id, category='PENDING', status='UNDER REVIEW')
                except:
                    messages.error(request, "You probably have NO pending loan. Apply for a new loan", extra_tags='warning')
                    return redirect('loan_application')
                   
            if 'work_confirmation_letter' in request.FILES:
                loanfileuploader(request,'work_confirmation_letter', user, loan)
                
            if 'payslip1' in request.FILES:
                loanfileuploader(request,'payslip1', user, loan)
            
            if 'payslip2' in request.FILES:
                loanfileuploader(request,'payslip2', user, loan)

            if LoanFile.objects.get(loan=loan):
                    loanfile = LoanFile.objects.get(loan=loan)
                    if loanfile.application_form_url and loanfile.terms_conditions_url and loanfile.stat_dec_url and loanfile.irr_sd_form_url and loanfile.bank_statement_url and loanfile.payslip1_url and loanfile.payslip2_url and loanfile.work_confirmation_letter_url:
                        request_approval(loan)
            
            messages.success(request, 'Work uploads updated Successfully!')
                
            return redirect('view_member', uid)
    else:
        uploadform = WorkUploadForm()        
    return render(request, 'edit_work_uploads_staff.html', { 'form': uploadform, 'user_profile': user})   

@check_staff
def edit_loan_statement_uploads_staff(request, uid):
    
    user = UserProfile.objects.get(id=uid)
    
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
                    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
                    return redirect(referrer)
            else:
                try:
                    loan = Loan.objects.get(owner=user.id, category='PENDING', status='UNDER REVIEW')
                except:
                    messages.error(request, "You probably have NO pending loan. Apply for a new loan", extra_tags='warning')
                    return redirect('loan_application')
                
            if 'loan_statement1' in request.FILES:
                loanfileuploader(request,'loan_statement1', user, loan)
            
            if 'loan_statement2' in request.FILES:
                loanfileuploader(request,'loan_statement2', user, loan)
                
            if 'loan_statement3' in request.FILES:
                loanfileuploader(request,'loan_statement3', user, loan)
                
            if 'bank_statement' in request.FILES:
                loanfileuploader(request,'bank_statement', user, loan)
            
            if 'super_statement' in request.FILES:
                loanfileuploader(request,'super_statement', user, loan)

            if 'bank_standing_order' in request.FILES:
                loanfileuploader(request,'bank_standing_order', user, loan)

            if LoanFile.objects.get(loan=loan):
                    loanfile = LoanFile.objects.get(loan=loan)
                    if loanfile.application_form_url and loanfile.terms_conditions_url and loanfile.stat_dec_url and loanfile.irr_sd_form_url and loanfile.bank_statement_url and loanfile.payslip1_url and loanfile.payslip2_url and loanfile.work_confirmation_letter_url:
                        request_approval(loan)

            messages.success(request, 'Required documents uploaded successfully...')
                
            return redirect('view_member', uid)
    else:
        uploadform = LoanStatementUploadForm()        
    return render(request, 'edit_loan_statement_uploads_staff.html', { 'form': uploadform, 'user_profile': user})   

@check_staff
def edit_jobinfo_staff(request, uid):
    
    user_profile = UserProfile.objects.get(id=uid)
    
    initial_data = {
        'job_title': user_profile.job_title,
        'start_date': user_profile.start_date,
        'pay_frequency': user_profile.pay_frequency,
        'last_paydate': user_profile.last_paydate,
        'gross_pay': user_profile.gross_pay,
        'work_id_number' : user_profile.work_id_number,
    }
    
    if request.method == 'POST':
        jobinfoUpdateForm = JobInfoUpdateForm(request.POST)
        if  jobinfoUpdateForm.is_valid():
            
            if 'work_id' in request.FILES:
                fileuploader(request,'work_id', user_profile)
            
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
            user_profile.work_id_number = jobinfoUpdateForm.cleaned_data.get('work_id_number', user_profile.work_id_number)
            user_profile.save()
            
           
            try:
                percent_of_gross = AdminSettings.objects.get(settings_name='setting1').percentage_of_gross
            except:
                percent_of_gross = 0.0

            user_profile.repayment_limit = (decimal.Decimal(percent_of_gross)/decimal.Decimal(100.0)) * user_profile.gross_pay 
                
            messages.success(request, 'Job information updated successfully!')
        return redirect('view_member', uid)
    else:
        jobinfoUpdateForm = JobInfoUpdateForm(initial=initial_data)
    return render(request, 'edit_jobinfo_staff.html', {'nav':'profile','form':jobinfoUpdateForm, 'user_profile': user_profile })

@check_staff
def edit_employerinfo_staff(request, uid):
    
    user_profile = UserProfile.objects.get(id=uid)
    
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
                for f in ['sector', 'organisation_type', 'office_address', 'payroll_officer_name', 'payroll_officer_phone', 'payroll_officer_email']:
                    val = cd.get(f)
                    if val is not None:
                        setattr(user_profile, f, val)

            user_profile.save()
            messages.success(request, 'Employer information updated successfully!')
        return redirect('view_member', uid)
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
    return render(request, 'edit_employerinfo_staff.html', {'nav': 'profile', 'form': employerinfoUpdateForm, 'user_profile': user_profile, 'employer_data_json': _json.dumps(_emp_data)})

############################################
# CREDIT ASSESSMENT (Statement of Position, referee & previous employer)
############################################

def _credit_assessment_enabled():
    setting = AdminSettings.objects.filter(settings_name='setting1').first()
    return bool(setting and setting.credit_assessment_enabled == 'YES')

@check_staff
def edit_refereeinfo_staff(request, uid):
    if not _credit_assessment_enabled():
        messages.error(request, "Credit Assessment is not enabled for this account.", extra_tags="danger")
        return redirect('view_member', uid)
    user = get_object_or_404(UserProfile, id=uid)
    if request.method == 'POST':
        form = RefereeInfoForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Referee information updated successfully', extra_tags="info")
            return redirect('view_member', uid=user.id)
    else:
        form = RefereeInfoForm(instance=user)
    return render(request, 'edit_refereeinfo_staff.html', {'nav': 'usermembers', 'form': form, 'user': user})

@check_staff
def edit_previousemployer_staff(request, uid):
    if not _credit_assessment_enabled():
        messages.error(request, "Credit Assessment is not enabled for this account.", extra_tags="danger")
        return redirect('view_member', uid)
    user = get_object_or_404(UserProfile, id=uid)
    if request.method == 'POST':
        form = PreviousEmployerInfoForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Previous employer information updated successfully', extra_tags="info")
            return redirect('view_member', uid=user.id)
    else:
        form = PreviousEmployerInfoForm(instance=user)
    return render(request, 'edit_previousemployer_staff.html', {'nav': 'usermembers', 'form': form, 'user': user})

@check_staff
def add_statement_of_position_staff(request, uid):
    if not _credit_assessment_enabled():
        messages.error(request, "Credit Assessment is not enabled for this account.", extra_tags="danger")
        return redirect('view_member', uid)
    user = get_object_or_404(UserProfile, id=uid)
    if getattr(user, 'statement_of_position', None) is not None:
        return redirect('edit_statement_of_position_staff', uid=user.id)
    if request.method == 'POST':
        form = StatementOfPositionForm(request.POST)
        if form.is_valid():
            sop = form.save(commit=False)
            sop.user = user
            sop.save()
            messages.success(request, 'Statement of Position created successfully.', extra_tags="info")
            return redirect('view_member', uid=user.id)
    else:
        form = StatementOfPositionForm()
    return render(request, 'staff/add_statement_of_position.html', {'nav': 'usermembers', 'form': form, 'user': user})

@check_staff
def edit_statement_of_position_staff(request, uid):
    if not _credit_assessment_enabled():
        messages.error(request, "Credit Assessment is not enabled for this account.", extra_tags="danger")
        return redirect('view_member', uid)
    user = get_object_or_404(UserProfile, id=uid)
    sop = getattr(user, 'statement_of_position', None)
    if not sop:
        return redirect('add_statement_of_position_staff', uid=user.id)
    if request.method == 'POST':
        form = StatementOfPositionForm(request.POST, instance=sop)
        if form.is_valid():
            form.save()
            messages.success(request, 'Statement of Position updated successfully.', extra_tags="info")
            return redirect('view_member', uid=user.id)
    else:
        form = StatementOfPositionForm(instance=sop)
    return render(request, 'staff/edit_statement_of_position.html', {'nav': 'usermembers', 'form': form, 'user': user})

############################################
# PROFILE WIZARD (Staff/Admin)
############################################

@check_staff
def edit_profile_wizard_staff(request, uid):
    """Unified multi-tab profile editor for staff/admin. No lock — staff can always edit."""
    from decimal import Decimal as _D
    user = UserProfile.objects.get(id=uid)

    active_tab = request.GET.get('tab', 'personal')

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
                    from admin1.models import AdminSettings as _AS
                    percent_of_gross = _AS.objects.get(settings_name='setting1').percentage_of_gross
                    if user.gross_pay:
                        user.repayment_limit = (_D(str(percent_of_gross)) / _D('100.0')) * _D(str(user.gross_pay))
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
            _emp_data = {e.name: {'sector': e.sector or '', 'organisation_type': e.organisation_type or '', 'office_address': e.office_address or '', 'payroll_officer_phone': str(e.work_phone) if e.work_phone else '', 'payroll_officer_email': e.work_email or ''} for e in _Emp.objects.filter(active=True)}
        else:
            _emp_data = {}
    except Exception:
        _emp_data = {}
    context = {
        'nav': 'usermembers',
        'user': user,
        'profile_locked': user.has_loan,
        'active_tab': active_tab,
        'personal_form': personal_form,
        'contact_form': contact_form,
        'employer_form': employer_form,
        'job_form': job_form,
        'bank_form': bank_form,
        'uploads_form': uploads_form,
        'employer_data_json': _json.dumps(_emp_data),
    }
    return render(request, 'edit_profile_wizard_staff.html', context)


############################################
# SME
############################################

@check_staff
def usersmes(request):
    smes = SMEProfile.objects.select_related('owner').all()
    return render(request, 'usersmes.html', { 'nav': 'usersmes', 'smes': smes})  

##### SME PROFILE MANAGEMENT ####

@check_staff
def view_sme_profile_staff(request, smid):
    smeprofile = SMEProfile.objects.get(pk=smid)
    return render(request, 'view_sme_profile.html', {'nav': 'usersmes', 'smeprofile': smeprofile })

@check_staff
def add_sme_profile(request):

    if request.method == 'POST': 
        createSmeForm = CreateSMEProfileForm(request.POST)
        if createSmeForm.is_valid():
            user = createSmeForm.cleaned_data['owner']
            smeprofile = SMEProfile.objects.create(owner=user)
            
            smeprofile.category = createSmeForm.cleaned_data['category']
            smeprofile.trading_name = createSmeForm.cleaned_data['trading_name']
            smeprofile.registered_name = createSmeForm.cleaned_data['registered_name']
            smeprofile.business_address = createSmeForm.cleaned_data['business_address']
            smeprofile.email = createSmeForm.cleaned_data['email']
            smeprofile.phone = createSmeForm.cleaned_data['phone']
            smeprofile.website = createSmeForm.cleaned_data['website']
            smeprofile.ipa_registration_number = createSmeForm.cleaned_data['ipa_registration_number']
            smeprofile.tin_number = createSmeForm.cleaned_data['tin_number']
            smeprofile.save()
            user.has_sme = 1
            user.save()
        
            messages.success(request, 'SME Profile Created successfully.')
            return redirect('view_sme_profile_staff', smeprofile.id) 
    else:
        createSmeForm = CreateSMEProfileForm()

    return render(request, 'add_sme_profile.html', {'nav':'usersmes', 'form': createSmeForm})

@check_staff
def edit_sme_profile_staff(request, uid):
    user = UserProfile.objects.get(id=uid)
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
            return redirect('edit_personalinfo_staff')

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

            return redirect('view_sme_profile_staff', smeprofile.id)

    else:
        profileform = SMEProfileForm(initial=initial_profile_data)
       
    return render(request, 'edit_sme_profile_staff.html', { 'nav': 'usersmes', 'profileform': profileform, })   

@check_staff
def edit_sme_profile_uploads_staff(request, uid):
    user = UserProfile.objects.get(id=uid)
    if request.method == 'POST':
        smeuploadsform = SMEUploadsForm(request.POST)
        if user.first_name == '' and user.last_name == '':
            messages.info(request, 'You need to update your personal information first.', extra_tags='info')
            return redirect('edit_personalinfo_staff')

        if smeuploadsform.is_valid():
            try:
                smeprofile = SMEProfile.objects.get(owner_id=user)

            except:
                messages.error(request, "You need to update business information first.", extra_tags="info")
                return redirect('edit_sme_profile_staff', user.id)

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
            return redirect('view_sme_profile_staff', smeprofile.id)

    else:
        smeuploadsform = SMEUploadsForm()
       
    return render(request, 'edit_sme_profile_uploads_staff.html', { 'nav': 'usersmes', 'smeuploadsform': smeuploadsform})   

@check_staff
def edit_sme_profile_bank_staff(request, uid):

    user = UserProfile.objects.get(id=uid)

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
            return redirect('edit_personalinfo_staff')           
        
        if smebankinfoform.is_valid():
            try:
                smeprofile = SMEProfile.objects.get(owner_id=user)
                
            except:
                messages.error(request, "You need to update business information first.", extra_tags="info")
                return redirect('edit_sme_profile_staff', user.id)
            
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
            return redirect('view_sme_profile_staff', smeprofile.id)

    else:
        smebankinfoform = SMEBankInfoForm(initial=initial_bank_data)
                
    return render(request, 'edit_sme_profile_bank_staff.html', { 'nav':'usersmes', 'smebankinfoform':smebankinfoform })   

####################################
# STATEMENTS
####################################

@check_staff
def userstatements(request):

    if request.method=="POST":
  
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype') and request.POST.get('transtype'):
  
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')
            transtype = request.POST.get('transtype')
            start_date = start_date_entry 
            end_date = end_date_entry 
            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')
            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))

            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('transactions_all')

            all_trans_filtered = Statement.objects.prefetch_related('owner','loanref').filter(loanref__loan_type=loantype, type = transtype, date__gte = start_date, date__lte = end_date).all()
            if transtype=='PAYMENT':
                all_payments = all_trans_filtered
                payments_sum = all_trans_filtered.aggregate(sum=Sum('debit'))['sum']

                context = {
                        'nav' : 'transactions', 'filter': 'on', 
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,     
                    }  

            elif transtype=='DEFAULT':
                all_defaults = all_trans_filtered
                defaults_sum = all_trans_filtered.aggregate(sum=Sum('default_amount'))['sum']
                context = {
                        'nav' : 'transactions', 'filter': 'on', 
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,   
                    }  
            else:
                all_credits = all_trans_filtered
                credits_sum = all_trans_filtered.aggregate(sum=Sum('credit'))['sum']
                context = {
                        'nav' : 'transactions', 'filter': 'on',  
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,  
                    }

            return render(request, 'userstatements.html', context)

        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))

            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('transactions_all')

            all_trans_filtered = Statement.objects.prefetch_related('owner','loanref').filter(loanref__loan_type=loantype, date__gte = start_date, date__lte = end_date).all()

            all_payments = all_trans_filtered.filter(type='PAYMENT')
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']

            all_defaults = all_trans_filtered.filter(type='DEFAULT')
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']

            all_credits = all_trans_filtered.filter(type='OTHERS')
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']

            context = {
                        'nav' : 'transactions', 'filter': 'on',
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                    }

            return render(request, 'userstatements.html', context)
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('transtype'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            transtype = request.POST.get('transtype')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('transactions_all')

            all_trans_filtered = Statement.objects.prefetch_related('owner','loanref').filter(type = transtype, date__gte = start_date, date__lte = end_date).all()
            if transtype=='PAYMENT':
                all_payments = all_trans_filtered
                payments_sum = all_trans_filtered.aggregate(sum=Sum('debit'))['sum']
                
                context = {
                        'nav' : 'transactions', 'filter': 'on',  
                        'startdate': start_date, 'enddate': end_date, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,     
                    }  
                
            elif transtype=='DEFAULT':
                all_defaults = all_trans_filtered
                defaults_sum = all_trans_filtered.aggregate(sum=Sum('default_amount'))['sum']
                context = {
                        'nav' : 'transactions', 'filter': 'on',  
                        'startdate': start_date, 'enddate': end_date, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,   
                    }  
            else:
                all_credits = all_trans_filtered
                credits_sum = all_trans_filtered.aggregate(sum=Sum('credit'))['sum']
                context = {
                        'nav' : 'transactions', 'filter': 'on',  
                        'startdate': start_date, 'enddate': end_date, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,  
                    }  
            
            return render(request, 'userstatements.html', context)
        
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
                return redirect('transactions_all')

            all_trans_filtered = Statement.objects.prefetch_related('owner','loanref').filter(date__gte = start_date, date__lte = end_date).all()
            
            all_payments = all_trans_filtered.filter(type='PAYMENT')
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
           
            all_defaults = all_trans_filtered.filter(type='DEFAULT')
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
            
            all_credits = all_trans_filtered.filter(type='OTHERS')
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
            
            
            context = {
                        'nav' : 'transactions', 'filter': 'on', 
                        'startdate': start_date, 'enddate': end_date, 
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'userstatements.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('transtype'): 

            loantype = request.POST.get('loantype')
            transtype = request.POST.get('transtype')

            all_trans_filtered = Statement.objects.prefetch_related('owner','loanref').filter(loanref__loan_type=loantype, type = transtype).all()
            if transtype=='PAYMENT':
                all_payments = all_trans_filtered
                payments_sum = all_trans_filtered.aggregate(sum=Sum('debit'))['sum']
                
                context = {
                        'nav' : 'transactions', 'filter': 'on', 
                         'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,     
                    }  
                
            elif transtype=='DEFAULT':
                all_defaults = all_trans_filtered
                defaults_sum = all_trans_filtered.aggregate(sum=Sum('default_amount'))['sum']
                context = {
                        'nav' : 'transactions', 'filter': 'on', 
                         'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,   
                    }  
            else:
                all_credits = all_trans_filtered
                credits_sum = all_trans_filtered.aggregate(sum=Sum('credit'))['sum']
                context = {
                        'nav' : 'transactions', 'filter': 'on', 
                        'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,  
                    }  
            
            return render(request, 'userstatements.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')

            all_trans_filtered = Statement.objects.prefetch_related('owner','loanref').filter(loanref__loan_type=loantype).all()
            
            all_payments = all_trans_filtered.filter(type='PAYMENT')
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
           
            all_defaults = all_trans_filtered.filter(type='DEFAULT')
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
            
            all_credits = all_trans_filtered.filter(type='OTHERS')
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
            
            
            context = {
                        'nav' : 'transactions', 'filter': 'on', 
                        'loantype': loantype, 
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'userstatements.html', context)
        
        elif request.POST.get('transtype'): 
            
            transtype = request.POST.get('transtype')

            all_trans_filtered = Statement.objects.prefetch_related('owner','loanref').filter(type = transtype).all()
            if transtype=='PAYMENT':
                all_payments = all_trans_filtered
                payments_sum = all_trans_filtered.aggregate(sum=Sum('debit'))['sum']
                
                context = {
                        'nav' : 'transactions', 'filter': 'on', 
                         'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,     
                    }  
                
            elif transtype=='DEFAULT':
                all_defaults = all_trans_filtered
                defaults_sum = all_trans_filtered.aggregate(sum=Sum('default_amount'))['sum']
                context = {
                        'nav' : 'transactions', 'filter': 'on', 
                         'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,   
                    }  
            else:
                all_credits = all_trans_filtered
                credits_sum = all_trans_filtered.aggregate(sum=Sum('credit'))['sum']
                context = {
                        'nav' : 'transactions', 'filter': 'on', 
                         'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,  
                    }  
            
            return render(request, 'userstatements.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('transactions_all')

    all_trans_filtered = Statement.objects.order_by('-date')
    all_payments = Statement.objects.filter(type="PAYMENT").all()
    payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
    all_defaults = Statement.objects.filter(type="DEFAULT").all()
    defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
    all_credits = Statement.objects.filter(type="OTHER").all()
    credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
    
    
    context = {
                'nav': 'userstatements', 
                'all_trans_filtered': all_trans_filtered,
                'all_payments': all_payments,
                'payments_sum':payments_sum,
                'all_defaults': all_defaults,
                'defaults_sum':defaults_sum,
                'all_credits':all_credits,
                'credits_sum': credits_sum,   
            } 
    
    return render(request, 'userstatements.html',context)  

#uploads

@check_staff
def existing_loan_functions(request):
    """Hub page for every 'existing loan' data-entry function — replaces the
    three separate nav items (Add Existing Loan / Add Existing Statements /
    Add a Loan Statement) with one page so staff have a single place to find
    all of them, plus the loan-creation and document-upload functions that
    used to live only on the Custom Functions page."""
    return render(request, 'existing_loan_functions.html', {'nav': 'existing_loan_functions'})


@check_staff
def add_existing_loan(request):

    try:
        loan_setting = AdminSettings.objects.get(settings_name='setting1')
    except: 
        messages.error(request, f"Loan Administrator needs to update their settings first. Please contact issues@{domain}.com", extra_tags="danger")
        return redirect('staff_dashboard')

    if request.method == 'POST':
        uploadedloans = request.FILES.get('uploadedloans')
        if not uploadedloans:
            messages.error(request, 'Choose a spreadsheet to upload.', extra_tags='danger')
            return render(request, 'import_existing_loans.html', {'nav': 'add_existing_loan'})
        try:
            # Read the upload directly. Saving it and re-fetching it from
            # settings.DOMAIN + MEDIA_URL cannot work: /media/ is behind the
            # authentication gate (see moromafinance/media_views).
            loanexceldata = pd.read_excel(uploadedloans)
        except Exception as exc:
            messages.error(request, f'That file could not be read as a spreadsheet ({exc}).',
                           extra_tags='danger')
            return render(request, 'import_existing_loans.html', {'nav': 'add_existing_loan'})
        upload_existing_loans(request, loanexceldata)
        messages.success(request, f"DONE", extra_tags="info")

    return render(request, 'import_existing_loans.html',{'nav': 'add_existing_loan'})


@check_staff
def add_existing_loan_statement(request):
    loans = Loan.objects.filter(category='FUNDED', classification='OLD')
    return render(request, 'existing_loans.html',{'nav': 'add_existing_loan_statement', 'loans': loans})

@check_staff
def upload_statement(request, loanref):
    """Replay one loan's historical statement from an uploaded spreadsheet.

    Every row is applied inside a single transaction: either the whole
    statement lands or none of it does, so a bad row halfway down never leaves
    the loan half-updated.
    """
    from django.db import transaction
    from loan.functions import (StatementUploadError, apply_statement_row,
                                read_statement_upload, reconcile_receivables)

    loan = get_object_or_404(Loan, ref=loanref)
    context = {'nav': 'add_existing_loan_statement', 'loan': loan}

    if request.method != 'POST':
        return render(request, 'upload_statement.html', context)

    uploaded = request.FILES.get('uploadedstatement')
    if not uploaded:
        messages.error(request, 'Choose a statement spreadsheet to upload.', extra_tags='danger')
        return render(request, 'upload_statement.html', context)

    try:
        rows = read_statement_upload(uploaded)
    except StatementUploadError as exc:
        messages.error(request, str(exc), extra_tags='danger')
        return render(request, 'upload_statement.html', context)

    try:
        with transaction.atomic():
            locked = Loan.objects.select_for_update().get(pk=loan.pk)
            officer = _officer_for(request)
            for row in rows:
                try:
                    apply_statement_row(locked, row['date'], row['comment'], row['mode'],
                                        row['debit'], row['credit'], officer=officer)
                except StatementUploadError as exc:
                    raise StatementUploadError(f"Row {row['row_number']}: {exc}.") from exc
            reconcile_receivables(locked)
            locked.save()
    except StatementUploadError as exc:
        messages.error(request, f'{exc} Nothing was imported — fix the file and upload it again.',
                       extra_tags='danger')
        return render(request, 'upload_statement.html', context)
    except Exception as exc:
        logger.exception('Statement upload failed for %s', loanref)
        messages.error(request, f'The statement could not be imported and nothing was saved: {exc}',
                       extra_tags='danger')
        return render(request, 'upload_statement.html', context)

    loan.refresh_from_db()
    messages.success(
        request,
        f'{len(rows)} statement line(s) imported for {loanref}. '
        f'Balance is now K{loan.total_outstanding:,.2f}.', extra_tags='info')
    return render(request, 'upload_statement.html', {**context, 'loan': loan})


def _officer_for(request):
    """The StaffProfile of the signed-in user, or None."""
    try:
        return StaffProfile.objects.get(user=UserProfile.objects.get(user=request.user.id))
    except (UserProfile.DoesNotExist, StaffProfile.DoesNotExist):
        return None

@check_staff
def send_repayment_reminder(request):
    currentdatetime = datetime.datetime.now()
    currentdate = currentdatetime.date()
    loans = Loan.objects.filter(category='FUNDED', funded_category='ACTIVE', next_payment_date=currentdate)
    if loans:
        for loan in loans:
            subject = 'LOAN REPAYMENT REMINDER'
            ''' if header_cta == 'yes' '''
            cta_label = ''
            cta_link = ''

            greeting = f'Hi {loan.owner.first_name},'
            message = f'We are kindly reminding you that:'
            message_details = f'Your next repayment of K{round(loan.repayment_amount,2)} is due today. Please make sure to pay on time to avoid a default which will affect your personal credit rating.'

            ''' if cta == 'yes' '''
            cta_btn1_label = 'UPLOAD PAYMENT PROOF'
            cta_btn1_link = f'{settings.DOMAIN}/loan/upload_payment/{loan.ref}/'
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
                'cta': 'yes',
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
                'user': loan.owner,
                'domain': domain,
                
            })
            
            text_content = strip_tags(email_content)
            email = EmailMultiAlternatives(subject,text_content,sender, ['dev@webmasta.com.pg',loan.owner.email])
            email.attach_alternative(email_content, "text/html")
           
            try: 
                email.send()
                messages.success(request, f"Reminder for {loan.ref} sent successfully to {loan.owner.first_name} {loan.owner.last_name}.")
            except:
                messages.error(request, f'Message has not been sent for {loan.ref} to {loan.owner.first_name}.', extra_tags='danger')
    
    else:
        messages.error(request, f"No active loans to send reminder to...", extra_tags="info")

    return redirect('staff_dashboard')

@check_staff
def send_loan_repayment_reminder(request, loanref):
    loan = Loan.objects.get(ref=loanref)

    #email start
    subject = 'LOAN REPAYMENT REMINDER'
    ''' if header_cta == 'yes' '''
    cta_label = ''
    cta_link = ''

    greeting = f'Hi {loan.owner.first_name},'
    message = f'We are kindly reminding you that:'
    message_details = f'Your next repayment of K{round(loan.repayment_amount,2)} is due. Please make sure to pay on time to avoid a default which will affect your personal credit rating.'

    ''' if cta == 'yes' '''
    cta_btn1_label = 'UPLOAD PAYMENT PROOF'
    cta_btn1_link = f'{settings.DOMAIN}/loan/upload_payment/{loan.ref}/'
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
        'cta': 'yes',
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
        'user': loan.owner,
        'domain': domain,
        
    })
    
    text_content = strip_tags(email_content)
    email = EmailMultiAlternatives(subject,text_content,sender, ['dev@webmasta.com.pg',loan.owner.email])
    email.attach_alternative(email_content, "text/html")
    
    try: 
        email.send()
        messages.success(request, f"Reminder for {loan.ref} sent successfully to {loan.owner.first_name} {loan.owner.last_name}.")
    except:
        messages.error(request, f'Message has not been sent for {loan.ref} to {loan.owner.first_name}.', extra_tags='danger')

    return redirect('userloans_all')

@check_staff
def run_defaults(request):
    """Batch-process overdue defaults using the loan engine: for each active
    loan, catch up every repayment that is genuinely overdue (the engine refuses
    future-dated ones), netting advances and charging on the shortfall."""
    from django.db import transaction
    from django.db.models import Q
    from loan.engine import create_default_for_loan

    from admin1.models import get_loan_config as _glc
    mercy = _glc().get('mercy_days') or 0
    loans = (Loan.objects.filter(Q(status='RUNNING') | Q(status='DEFAULTED'), category='FUNDED')
             .exclude(funded_category='COMPLETED'))
    created = 0
    affected = 0
    for loan in loans:
        loan_defaulted = False
        while True:
            with transaction.atomic():
                locked = Loan.objects.select_for_update().get(pk=loan.pk)
                stat, ok, msg = create_default_for_loan(locked, mercy_days=mercy)
            if not ok:
                break
            created += 1
            loan_defaulted = True
        if loan_defaulted:
            affected += 1

    if created:
        messages.success(request, f'Created {created} default(s) across {affected} loan(s).', extra_tags='info')
    else:
        messages.info(request, 'No overdue repayments found to default.', extra_tags='info')
    return redirect('staff_dashboard')

@check_staff
def add_existing_statements(request):

    if request.method == 'POST':
        uploadedstatement = request.FILES.get('uploadedstatementsfile')
        if not uploadedstatement:
            messages.error(request, 'Choose a spreadsheet to upload.', extra_tags='danger')
            return render(request, 'import_existing_statements.html',
                          {'nav': 'add_existing_statements'})
        try:
            # Read the upload directly — see the note in add_existing_loan.
            statementexceldata = pd.read_excel(uploadedstatement)
        except Exception as exc:
            messages.error(request, f'That file could not be read as a spreadsheet ({exc}).',
                           extra_tags='danger')
            return render(request, 'import_existing_statements.html',
                          {'nav': 'add_existing_statements'})
        upload_existing_statement(request, statementexceldata)
        messages.success(request, f"DONE", extra_tags="info")

    return render(request, 'import_existing_statements.html',{'nav': 'add_existing_statements'})
