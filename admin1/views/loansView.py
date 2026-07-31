import datetime
import re
import json
import subprocess
import requests
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.views.generic.base import View
from wkhtmltopdf.views import PDFTemplateResponse
from accounts.models import User, UserProfile, StaffProfile
from accounts.functions import admin_check, loanfileuploader
from admin1.models import AdminSettings, Location, get_loan_config, get_bank_config, get_document_theme
from admin1.forms import AdminSettingsForm
from loan.models import Loan, LoanFile, Statement, Payment, PaymentUploads
from loan.forms import PaymentForm, ReceiptUploadForm
from custom.functions import fund_additional_loan
sender = settings.DEFAULT_SENDER_EMAIL

domain = settings.DOMAIN

from django.db.models import Q

############### 
# START OF CODE
###############

@admin_check
def loans(request):
    
    all_loans = Loan.objects.exclude(category="PENDING", funded_category='COMPLETED').all()
    pending_loans = Loan.objects.filter(status='UNDER REVIEW')
    approved_loans = Loan.objects.filter(status='APPROVED')
    running_loans = Loan.objects.filter(category='FUNDED', status = 'RUNNING')
    defaulted_loans = Loan.objects.filter(category='FUNDED', status = 'DEFAULTED')
    funded_loans = Loan.objects.filter(category='FUNDED').exclude(funded_category="COMPLETED")
    personal_loans = Loan.objects.filter(category='FUNDED', funded_category="ACTIVE", loan_type="PERSONAL")
    sme_loans = Loan.objects.filter(category='FUNDED', funded_category="ACTIVE", loan_type="SME")
    
    # loan overview
    total_funded = 0
    expected_interest = 0
    system_balance = 0
    repayments_total = 0
    total_arrears = 0
    default_interest_receivable = 0
    total_outstanding = 0
        
    for loan in funded_loans:
        total_funded += loan.amount
        expected_interest += loan.interest
        system_balance += loan.total_loan_amount
        repayments_total += loan.repayment_amount
        total_arrears += loan.total_arrears
        default_interest_receivable += loan.default_interest_receivable
        total_outstanding += loan.total_outstanding
        
    # personal loan overview
    p_total_funded = 0
    p_expected_interest = 0
    p_system_balance = 0
    
    for loan in personal_loans:
        p_total_funded += loan.amount
        p_expected_interest += loan.interest
        p_system_balance += loan.total_loan_amount
    
     # sme loan overview
    sme_total_funded = 0
    sme_expected_interest = 0
    sme_system_balance = 0
    
    for loan in sme_loans:
        sme_total_funded += loan.amount
        sme_expected_interest += loan.interest
        sme_system_balance += loan.total_loan_amount

    totalapprovedloans = Loan.objects.filter(category='FUNDED')
    
    approvedtotal = Loan.objects.filter(category='FUNDED', funded_category="ACTIVE").aggregate(totalsum=Sum('amount'))
    if approvedtotal['totalsum'] is None:
        approvedtotal['totalsum'] = 0.000000000001
    approvedtotal_d = Decimal(approvedtotal['totalsum'])
    totalapproved = totalapprovedloans.count()
    
    # 0-1K
    approved1Kloans = Loan.objects.filter(category='FUNDED', funded_category="ACTIVE", amount__gt=0, amount__lte=1000)
    approved1Ktotal = approved1Kloans.aggregate(totalsum=Sum('amount'))
    if approved1Ktotal['totalsum'] is None:
        approved1Ktotal['totalsum'] = 0.000000000001
    approved1Ktotal_d = Decimal(approved1Ktotal['totalsum'])  
    onekcount = approved1Kloans.count()
    # 1.1K - 5K
    approved5Kloans = Loan.objects.filter(category='FUNDED',funded_category="ACTIVE", amount__gt=1000, amount__lte=5000)
    approved5Ktotal = approved5Kloans.aggregate(totalsum=Sum('amount'))
    if approved5Ktotal['totalsum'] is None:
        approved5Ktotal['totalsum'] = 0.000000000001
    approved5Ktotal_d = Decimal(approved5Ktotal['totalsum'])
    fivekcount = approved5Kloans.count()
    # 5.1K - 10K 
    approved10Kloans = Loan.objects.filter(category='FUNDED',funded_category="ACTIVE", amount__gt=5000, amount__lte=10000)
    approved10Ktotal = approved10Kloans.aggregate(totalsum=Sum('amount'))
    if approved10Ktotal['totalsum'] is None:
        approved10Ktotal['totalsum'] = Decimal(0.000000000001)
    approved10Ktotal_d = Decimal(approved10Ktotal['totalsum'])
    tenkcount = approved10Kloans.count()
    #10+K
    approved15Kloans = Loan.objects.filter(category='FUNDED',funded_category="ACTIVE", amount__gt=10000)
    approved15Ktotal = approved15Kloans.aggregate(totalsum=Sum('amount'))
    if approved15Ktotal['totalsum'] is None:
        approved15Ktotal['totalsum'] = Decimal(0.0000000000001)
    approved15Ktotal_d = Decimal(approved15Ktotal['totalsum'])
    fteenkcount = approved15Kloans.count()
    
    hundred = Decimal(100.00)

    onekpercent = round((approved1Ktotal_d/approvedtotal_d)*hundred, 2)
    fivekpercent = round((approved5Ktotal_d/approvedtotal_d)*hundred, 2)
    tenkpercent = round((approved10Ktotal_d/approvedtotal_d)*hundred, 2)
    fteenkpercent = round((approved15Ktotal_d/approvedtotal_d)*hundred, 2)
    
    onektotalamount = round(approved1Ktotal['totalsum'],2)
    fivektotalamount = round(approved5Ktotal['totalsum'], 2)
    tenktotalamount = round(approved10Ktotal['totalsum'], 2)
    fteenktotalamount = round(approved15Ktotal['totalsum'], 2)
    

    oneklabel = f'0-1K, {onekpercent}%'
    fiveklabel = f'1-5K, {fivekpercent}%'
    tenklabel = f'5-10K, {tenkpercent}%'
    fteenklabel = f'10+K, {fteenkpercent}%'

    loanlabels =[oneklabel,
                fiveklabel,
                tenklabel,
                fteenklabel,
            ]

    loandata = [onekpercent,
            fivekpercent,
            tenkpercent,
            fteenkpercent,
            ]
    
    #loans by status
    gpending_loans = Loan.objects.filter(category="PENDING").count()
    grunning_loans = Loan.objects.filter(category="FUNDED", funded_category="ACTIVE", status="RUNNING").count()
    gdefaulted_loans = Loan.objects.filter(category="FUNDED", funded_category="ACTIVE", status="DEFAULTED").count()
    gloans_in_recovery = Loan.objects.filter(category="FUNDED", funded_category="RECOVERY").count()
    gbad_loans = Loan.objects.filter(category="FUNDED", funded_category="BAD").count()
    
    loansbystatus = [gpending_loans,grunning_loans,gdefaulted_loans,gloans_in_recovery,gbad_loans]
   
    #loans by branch
   
    loclabel = []
    locloan = []
   
    locations = Location.objects.all()
   
    for location in locations:
        locloanqs = Loan.objects.filter(location=location.id, category="FUNDED", funded_category='ACTIVE')
        
        locloancount = locloanqs.count()
        if locloancount != 0:
            locloan.append(float(locloanqs.aggregate(sum=Sum('amount'))['sum']))
        else:
            locloan.append(0)
            
        loclabel.append(f'{location.name}, {locloancount}')
    
    
    context = {
        'nav': 'loans', 
        'all_loans': all_loans,
        'pending_loans': pending_loans,
        'approved_loans': approved_loans,
        'running_loans': running_loans,
        'defaulted_loans': defaulted_loans,
        'funded_loans' : funded_loans,
        'personal_loans' : personal_loans,
        'sme_loans' : sme_loans,
        'total_funded': total_funded,
        'expected_interest' : expected_interest,
        'system_balance' : system_balance,
        'onekcount': onekcount,
        'onektotalamount' : onektotalamount,
        'fivekcount': fivekcount,
        'fivektotalamount' : fivektotalamount,
        'tenkcount': tenkcount,
        'tenktotalamount' : tenktotalamount,
        'fteenkcount': fteenkcount,
        'fteenktotalamount' : fteenktotalamount,
        
        'repayments_total' : repayments_total,
        'total_arrears' : total_arrears,
        'default_interest_receivable' : default_interest_receivable,
        'total_outstanding' : total_outstanding,
        
        'p_total_funded': p_total_funded,
        'p_expected_interest' : p_expected_interest,
        'p_system_balance' : p_system_balance,
        'sme_total_funded': sme_total_funded,
        'sme_expected_interest' : sme_expected_interest,
        'sme_system_balance' : sme_system_balance,  
        'loanlabels': loanlabels,
        'loandata': loandata, 
        'loansbystatus':loansbystatus,
        'loclabel':loclabel,
        'locloan': locloan,
       
    }
    
    return render(request, 'loans.html', context)

@admin_check
def all_loans(request):
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category='PENDING', funded_category="COMPLETED").all()
    pending_loans = Loan.objects.filter(category="PENDING")
    running_loans = Loan.objects.filter(funded_category="ACTIVE",status="RUNNING")
    defaulted_loans = Loan.objects.filter(funded_category="ACTIVE",status="DEFAULTED")
    completed_loans = Loan.objects.filter(funded_category="COMPLETED")
    recovery_loans = Loan.objects.filter(funded_category="RECOVERY")
    awaiting_refund_loans = Loan.objects.filter(funded_category="AWAITING_REFUND")
    
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
                return redirect('all_loans')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).exclude(category='PENDING', funded_category="COMPLETED").all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'all_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }            
            
            return render(request, 'loans_all.html', context)
        
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
                return redirect('all_loans')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).exclude(category='PENDING', funded_category="COMPLETED").all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'all_loans', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_all.html', context)
        
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
                return redirect('all_loans')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).exclude(category='PENDING', funded_category="COMPLETED").all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'all_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }         
                        
            return render(request, 'loans_all.html', context)
        
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
                return redirect('all_loans')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(funding_date__gte = start_date, funding_date__lte = end_date).exclude(category='PENDING', funded_category="COMPLETED").all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'all_loans', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }      
            
            return render(request, 'loans_all.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype, owner__category = cuscat).exclude(category='PENDING', funded_category="COMPLETED").all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'all_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }        
            
            return render(request, 'loans_all.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')
            

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(loan_type=loantype).exclude(category='PENDING', funded_category="COMPLETED").all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'all_loans', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
            
            return render(request, 'loans_all.html', context)
        
        elif request.POST.get('cuscat'): 
            
            cuscat = request.POST.get('cuscat')

            all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner__category = cuscat).exclude(category='PENDING', funded_category="COMPLETED").all()
            funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'all_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,
                        'all_loans': all_loans,
                        'all_loans_filtered': all_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_all.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('all_loans')

    all_loans_filtered = Loan.objects.filter(category="FUNDED").exclude(funded_category="COMPLETED")
    funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                'nav' : 'all_loans', 
                'all_loans': all_loans,
                'all_loans_filtered': all_loans_filtered,
                'pending_loans': pending_loans,
                'running_loans':running_loans,
                'defaulted_loans': defaulted_loans,
                'completed_loans':completed_loans,
                'recovery_loans':recovery_loans,
                'awaiting_refund_loans': awaiting_refund_loans,
                'funded_sum': funded_sum,
                'interests_sum': interests_sum,
                'totalloan_sum': totalloan_sum,
                'repayments_sum': repayments_sum,
                'arrears_sum': arrears_sum,
                'defaultinterests_sum': defaultinterests_sum,
                'outstanding_sum': outstanding_sum,       
                
            }  
    
    return render(request, 'loans_all.html', context)

@admin_check
def pending_loans(request):
    
    
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category="PENDING").all()
    pending_loans = Loan.objects.filter(category="PENDING").all()
    running_loans = Loan.objects.filter(funded_category="ACTIVE",status="RUNNING").all()
    defaulted_loans = Loan.objects.filter(funded_category="ACTIVE",status="DEFAULTED").all()
    completed_loans = Loan.objects.filter(funded_category="COMPLETED").all()
    recovery_loans = Loan.objects.filter(funded_category="RECOVERY").all()
    awaiting_refund_loans = Loan.objects.filter(funded_category="AWAITING_REFUND").all()
    
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
                return redirect('pending_loans')

            pending_loans_filtered = Loan.objects.prefetch_related('owner').filter(category='PENDING', loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).exclude(status='APPROVED').all()
            funded_sum = pending_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = pending_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = pending_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = pending_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = pending_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = pending_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = pending_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'pending_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'pending_loans_filtered': pending_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }            
            
            return render(request, 'loans_pending.html', context)
        
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
                return redirect('pending_loans')

            pending_loans_filtered = Loan.objects.prefetch_related('owner').filter(category='PENDING',loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).exclude(status='APPROVED').all()
            funded_sum = pending_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = pending_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = pending_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = pending_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = pending_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = pending_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = pending_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'pending_loans', 'filter': 'on', 'referrer': referrer,
                         'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'pending_loans_filtered': pending_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_pending.html', context)
        
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
                return redirect('pending_loans')

            pending_loans_filtered = Loan.objects.prefetch_related('owner').filter(category='PENDING',owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).exclude(status='APPROVED').all()
            funded_sum = pending_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = pending_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = pending_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = pending_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = pending_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = pending_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = pending_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'pending_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'pending_loans_filtered': pending_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }         
                        
            return render(request, 'loans_pending.html', context)
        
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
                return redirect('pending_loans')

            pending_loans_filtered = Loan.objects.prefetch_related('owner').filter(category='PENDING',funding_date__gte = start_date, funding_date__lte = end_date).exclude(status='APPROVED').all()
            funded_sum = pending_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = pending_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = pending_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = pending_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = pending_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = pending_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = pending_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'pending_loans', 'filter': 'on', 'referrer': referrer,
                     'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'pending_loans_filtered': pending_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }      
            
            return render(request, 'loans_pending.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            pending_loans_filtered = Loan.objects.prefetch_related('owner').filter(category='PENDING',loan_type=loantype, owner__category = cuscat).exclude(status='APPROVED').all()
            funded_sum = pending_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = pending_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = pending_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = pending_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = pending_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = pending_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = pending_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'pending_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype,
                        'all_loans': all_loans,
                        'pending_loans_filtered': pending_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }        
            
            return render(request, 'loans_pending.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')

            pending_loans_filtered = Loan.objects.prefetch_related('owner').filter(category='PENDING',loan_type=loantype).exclude(status='APPROVED').all()
            funded_sum = pending_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = pending_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = pending_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = pending_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = pending_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = pending_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = pending_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'pending_loans', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype,
                        'all_loans': all_loans,
                        'pending_loans_filtered': pending_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
            
            return render(request, 'loans_pending.html', context)
        
        elif request.POST.get('cuscat'): 
            
            cuscat = request.POST.get('cuscat')

            pending_loans_filtered = Loan.objects.prefetch_related('owner').filter(category='PENDING',owner__category = cuscat).exclude(status='APPROVED').all()
            funded_sum = pending_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = pending_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = pending_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = pending_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = pending_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = pending_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = pending_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'pending_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,
                        'all_loans': all_loans,
                        'pending_loans_filtered': pending_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_pending.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('pending_loans')

    pending_loans_filtered = Loan.objects.filter(category="PENDING").exclude(status='APPROVED').all()
    funded_sum = pending_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = pending_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = pending_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = pending_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = pending_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = pending_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = pending_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                        'nav' : 'pending_loans',
                        
                        'all_loans': all_loans,
                        'pending_loans_filtered': pending_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
    
    return render(request, 'loans_pending.html', context)

@admin_check
def running_loans(request):

    
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category="PENDING", funded_category="COMPLETED").all()
    pending_loans = Loan.objects.filter(category="PENDING").all()
    running_loans = Loan.objects.filter(funded_category="ACTIVE",status="RUNNING").all()
    defaulted_loans = Loan.objects.filter(funded_category="ACTIVE",status="DEFAULTED").all()
    completed_loans = Loan.objects.filter(funded_category="COMPLETED").all()
    recovery_loans = Loan.objects.filter(funded_category="RECOVERY").all()
    awaiting_refund_loans = Loan.objects.filter(funded_category="AWAITING_REFUND").all()
    
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
                return redirect('running_loans')

            running_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="RUNNING",loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = running_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = running_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = running_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = running_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = running_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = running_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = running_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'running_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'running_loans_filtered': running_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }            
            
            return render(request, 'loans_running.html', context)
        
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
                return redirect('running_loans')

            running_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="RUNNING",loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = running_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = running_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = running_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = running_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = running_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = running_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = running_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'running_loans', 'filter': 'on', 'referrer': referrer,
                         'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'running_loans_filtered': running_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_running.html', context)
        
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
                return redirect('running_loans')

            running_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="RUNNING",owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = running_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = running_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = running_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = running_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = running_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = running_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = running_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'running_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'running_loans_filtered': running_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }         
                        
            return render(request, 'loans_running.html', context)
        
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
                return redirect('running_loans')

            running_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="RUNNING",funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = running_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = running_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = running_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = running_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = running_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = running_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = running_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'running_loans', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'running_loans_filtered': running_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }      
            
            return render(request, 'loans_running.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            running_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="RUNNING",loan_type=loantype, owner__category = cuscat).all()
            funded_sum = running_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = running_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = running_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = running_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = running_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = running_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = running_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'running_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 
                        'all_loans': all_loans,
                        'running_loans_filtered': running_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }        
            
            return render(request, 'loans_running.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')

            running_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="RUNNING",loan_type=loantype).all()
            funded_sum = running_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = running_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = running_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = running_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = running_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = running_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = running_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'running_loans', 'filter': 'on', 'referrer': referrer,
                       'loantype': loantype,
                        'all_loans': all_loans,
                        'running_loans_filtered': running_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
            
            return render(request, 'loans_running.html', context)
        
        elif request.POST.get('cuscat'): 
            
            cuscat = request.POST.get('cuscat')

            running_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="RUNNING",owner__category = cuscat).all()
            funded_sum = running_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = running_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = running_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = running_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = running_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = running_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = running_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'running_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,
                        'all_loans': all_loans,
                        'running_loans_filtered': running_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_running.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('running_loans')

    running_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="RUNNING").all()
    funded_sum = running_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = running_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = running_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = running_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = running_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = running_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = running_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                        'nav' : 'running_loans', 
                        'all_loans': all_loans,
                        'running_loans_filtered': running_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
    
    return render(request, 'loans_running.html', context)

@admin_check
def defaulted_loans(request):

    
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category="PENDING").all()
    pending_loans = Loan.objects.filter(category="PENDING").all()
    running_loans = Loan.objects.filter(funded_category="ACTIVE",status="RUNNING").all()
    defaulted_loans = Loan.objects.filter(funded_category="ACTIVE",status="DEFAULTED").all()
    completed_loans = Loan.objects.filter(funded_category="COMPLETED").all()
    recovery_loans = Loan.objects.filter(funded_category="RECOVERY").all()
    awaiting_refund_loans = Loan.objects.filter(funded_category="AWAITING_REFUND").all()
    
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
                return redirect('defaulted_loans')

            defaulted_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="DEFAULTED",loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = defaulted_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = defaulted_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = defaulted_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = defaulted_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'defaulted_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'defaulted_loans_filtered': defaulted_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }            
            
            return render(request, 'loans_defaulted.html', context)
        
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
                return redirect('defaulted_loans')

            defaulted_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="DEFAULTED",loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = defaulted_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = defaulted_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = defaulted_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = defaulted_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'defaulted_loans', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'defaulted_loans_filtered': defaulted_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_defaulted.html', context)
        
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
                return redirect('defaulted_loans')

            defaulted_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="DEFAULTED",owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = defaulted_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = defaulted_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = defaulted_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = defaulted_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'defaulted_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,  'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'defaulted_loans_filtered': defaulted_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }         
                        
            return render(request, 'loans_defaulted.html', context)
        
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
                return redirect('defaulted_loans')

            defaulted_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="DEFAULTED",funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = defaulted_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = defaulted_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = defaulted_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = defaulted_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'defaulted_loans', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'defaulted_loans_filtered': defaulted_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }      
            
            return render(request, 'loans_defaulted.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            defaulted_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="DEFAULTED",loan_type=loantype, owner__category = cuscat).all()
            funded_sum = defaulted_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = defaulted_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = defaulted_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = defaulted_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'defaulted_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 
                        'all_loans': all_loans,
                        'defaulted_loans_filtered': defaulted_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }        
            
            return render(request, 'loans_defaulted.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')
           

            defaulted_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="DEFAULTED",loan_type=loantype).all()
            funded_sum = defaulted_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = defaulted_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = defaulted_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = defaulted_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'defaulted_loans', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 
                        'all_loans': all_loans,
                        'defaulted_loans_filtered': defaulted_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
            
            return render(request, 'loans_defaulted.html', context)
        
        elif request.POST.get('cuscat'): 
            
            cuscat = request.POST.get('cuscat')

            defaulted_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="DEFAULTED",owner__category = cuscat).all()
            funded_sum = defaulted_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = defaulted_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = defaulted_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = defaulted_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'defaulted_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,
                        'all_loans': all_loans,
                        'defaulted_loans_filtered': defaulted_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_defaulted.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('defaulted_loans')

    defaulted_loans_filtered = Loan.objects.filter(category="FUNDED", funded_category="ACTIVE",status="DEFAULTED").all()
    funded_sum = defaulted_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = defaulted_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = defaulted_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = defaulted_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = defaulted_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                'nav': 'defaulted_loans', 
                'all_loans': all_loans,
                'defaulted_loans_filtered': defaulted_loans_filtered,
                'pending_loans': pending_loans,
                'running_loans':running_loans,
                'defaulted_loans': defaulted_loans,
                'completed_loans':completed_loans,
                'recovery_loans':recovery_loans,
                'awaiting_refund_loans': awaiting_refund_loans,
                'funded_sum': funded_sum,
                'interests_sum': interests_sum,
                'totalloan_sum': totalloan_sum,
                'repayments_sum': repayments_sum,
                'arrears_sum': arrears_sum,
                'defaultinterests_sum': defaultinterests_sum,
                'outstanding_sum': outstanding_sum,       
                
            }  
    
    return render(request, 'loans_defaulted.html', context)
   
@admin_check
def recovery_loans(request):

    
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category="PENDING").all()
    pending_loans = Loan.objects.filter(category="PENDING").all()
    running_loans = Loan.objects.filter(funded_category="ACTIVE",status="RUNNING").all()
    defaulted_loans = Loan.objects.filter(funded_category="ACTIVE",status="DEFAULTED").all()
    completed_loans = Loan.objects.filter(funded_category="COMPLETED").all()
    recovery_loans = Loan.objects.filter(funded_category="RECOVERY").all()
    awaiting_refund_loans = Loan.objects.filter(funded_category="AWAITING_REFUND").all()
    
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
                return redirect('recovery_loans')

            recovery_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="ACTIVE",status="DEFAULTED",loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = recovery_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = recovery_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = recovery_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = recovery_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = recovery_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = recovery_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = recovery_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'recovery_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'recovery_loans_filtered': recovery_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }            
            
            return render(request, 'loans_recovery.html', context)
        
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
                return redirect('recovery_loans')

            recovery_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="RECOVERY",loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = recovery_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = recovery_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = recovery_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = recovery_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = recovery_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = recovery_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = recovery_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'recovery_loans', 'filter': 'on', 'referrer': referrer,
                       'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'recovery_loans_filtered': recovery_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_recovery.html', context)
        
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
                return redirect('recovery_loans')

            recovery_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="RECOVERY",owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = recovery_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = recovery_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = recovery_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = recovery_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = recovery_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = recovery_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = recovery_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'recovery_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,  'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'recovery_loans_filtered': recovery_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }         
                        
            return render(request, 'loans_recovery.html', context)
        
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
                return redirect('recovery_loans')

            recovery_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="RECOVERY",funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = recovery_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = recovery_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = recovery_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = recovery_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = recovery_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = recovery_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = recovery_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'recovery_loans', 'filter': 'on', 'referrer': referrer,
                       'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'recovery_loans_filtered': recovery_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }      
            
            return render(request, 'loans_recovery.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            recovery_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="RECOVERY",loan_type=loantype, owner__category = cuscat).all()
            funded_sum = recovery_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = recovery_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = recovery_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = recovery_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = recovery_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = recovery_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = recovery_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'recovery_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 
                        'all_loans': all_loans,
                        'recovery_loans_filtered': recovery_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }        
            
            return render(request, 'loans_recovery.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')
            

            recovery_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="RECOVERY",loan_type=loantype).all()
            funded_sum = recovery_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = recovery_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = recovery_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = recovery_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = recovery_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = recovery_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = recovery_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'recovery_loans', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 
                        'all_loans': all_loans,
                        'recovery_loans_filtered': recovery_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
            
            return render(request, 'loans_recovery.html', context)
        
        elif request.POST.get('cuscat'): 
            
            cuscat = request.POST.get('cuscat')

            recovery_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="RECOVERY",owner__category = cuscat).all()
            funded_sum = recovery_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = recovery_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = recovery_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = recovery_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = recovery_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = recovery_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = recovery_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'recovery_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 
                        'all_loans': all_loans,
                        'recovery_loans_filtered': recovery_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_recovery.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('recovery_loans')

    recovery_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="RECOVERY").all()
    funded_sum = recovery_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = recovery_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = recovery_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = recovery_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = recovery_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = recovery_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = recovery_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                        'nav' : 'recovery_loans', 
                        'all_loans': all_loans,
                        'recovery_loans_filtered': recovery_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
    
    return render(request, 'loans_recovery.html', context)

@admin_check
def completed_loans(request):

    
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    all_loans = Loan.objects.exclude(category="PENDING").all()
    pending_loans = Loan.objects.filter(category="PENDING").all()
    running_loans = Loan.objects.filter(funded_category="ACTIVE",status="RUNNING").all()
    defaulted_loans = Loan.objects.filter(funded_category="ACTIVE",status="DEFAULTED").all()
    completed_loans = Loan.objects.filter(funded_category="COMPLETED").all()
    recovery_loans = Loan.objects.filter(funded_category="RECOVERY").all()
    awaiting_refund_loans = Loan.objects.filter(funded_category="AWAITING_REFUND").all()
    
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
                return redirect('completed_loans')

            completed_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="COMPLETED",loan_type=loantype, owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = completed_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = completed_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = completed_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = completed_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = completed_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = completed_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = completed_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                        'nav' : 'completed_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'completed_loans_filtered': completed_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }            
            
            return render(request, 'loans_completed.html', context)
        
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
                return redirect('completed_loans')

            completed_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="COMPLETED",loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = completed_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = completed_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = completed_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = completed_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = completed_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = completed_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = completed_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'completed_loans', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'completed_loans_filtered': completed_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_completed.html', context)
        
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
                return redirect('completed_loans')

            completed_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="COMPLETED",owner__category = cuscat, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = completed_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = completed_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = completed_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = completed_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = completed_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = completed_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = completed_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'completed_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,  'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'completed_loans_filtered': completed_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }         
                        
            return render(request, 'loans_completed.html', context)
        
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
                return redirect('completed_loans')

            completed_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="COMPLETED",funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_sum = completed_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = completed_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = completed_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = completed_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = completed_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = completed_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = completed_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'completed_loans', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date,
                        'all_loans': all_loans,
                        'completed_loans_filtered': completed_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }      
            
            return render(request, 'loans_completed.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('cuscat'): 

            loantype = request.POST.get('loantype')
            cuscat = request.POST.get('cuscat')

            completed_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="COMPLETED",loan_type=loantype, owner__category = cuscat).all()
            funded_sum = completed_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = completed_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = completed_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = completed_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = completed_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = completed_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = completed_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'completed_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 'loantype': loantype, 
                        'all_loans': all_loans,
                        'completed_loans_filtered': completed_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }        
            
            return render(request, 'loans_completed.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')

            completed_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="COMPLETED",loan_type=loantype).all()
            funded_sum = completed_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = completed_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = completed_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = completed_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = completed_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = completed_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = completed_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'completed_loans', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 
                        'all_loans': all_loans,
                        'completed_loans_filtered': completed_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
            
            return render(request, 'loans_completed.html', context)
        
        elif request.POST.get('cuscat'): 
            
            cuscat = request.POST.get('cuscat')

            completed_loans_filtered = Loan.objects.prefetch_related('owner').filter(category="FUNDED", funded_category="COMPLETED",owner__category = cuscat).all()
            funded_sum = completed_loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interests_sum = completed_loans_filtered.aggregate(sum=Sum('interest'))['sum']
            totalloan_sum = completed_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
            repayments_sum = completed_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_sum = completed_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            defaultinterests_sum = completed_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
            outstanding_sum = completed_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            
            context = {
                        'nav' : 'completed_loans', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat, 
                        'all_loans': all_loans,
                        'completed_loans_filtered': completed_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }          
            
            return render(request, 'loans_completed.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('completed_loans')

    completed_loans_filtered = Loan.objects.filter(category="FUNDED", funded_category="COMPLETED").all()
    funded_sum = completed_loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = completed_loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = completed_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = completed_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = completed_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = completed_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = completed_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
                        'nav' : 'completed_loans', 
                        'all_loans': all_loans,
                        'completed_loans_filtered': completed_loans_filtered,
                        'pending_loans': pending_loans,
                        'running_loans':running_loans,
                        'defaulted_loans': defaulted_loans,
                        'completed_loans':completed_loans,
                        'recovery_loans':recovery_loans,
                        'awaiting_refund_loans': awaiting_refund_loans,
                        'funded_sum': funded_sum,
                        'interests_sum': interests_sum,
                        'totalloan_sum': totalloan_sum,
                        'repayments_sum': repayments_sum,
                        'arrears_sum': arrears_sum,
                        'defaultinterests_sum': defaultinterests_sum,
                        'outstanding_sum': outstanding_sum,       
                        
                    }  
    
    return render(request, 'loans_completed.html', context)


@admin_check
def awaiting_refund_loans(request):
    """Loans settled in full where the closing payment overpaid the balance —
    the excess is tracked as a LoanCredit and the loan stays here (out of
    Completed) until it's refunded or explicitly attributed. See
    loan.functions.close_loan_with_credit."""
    referrer = request.META.get('HTTP_REFERER', request.build_absolute_uri())

    all_loans = Loan.objects.exclude(category='PENDING', funded_category='COMPLETED').all()
    pending_loans = Loan.objects.filter(category='PENDING')
    running_loans = Loan.objects.filter(funded_category='ACTIVE', status='RUNNING')
    defaulted_loans = Loan.objects.filter(funded_category='ACTIVE', status='DEFAULTED')
    completed_loans = Loan.objects.filter(funded_category='COMPLETED')
    recovery_loans = Loan.objects.filter(funded_category='RECOVERY')
    awaiting_refund_loans = Loan.objects.filter(funded_category='AWAITING_REFUND').select_related('owner').prefetch_related('credits')

    loans_filtered = awaiting_refund_loans
    loantype = cuscat = startdate = enddate = None
    filter_on = False

    if request.method == 'POST':
        loantype = (request.POST.get('loantype') or '').strip() or None
        cuscat = (request.POST.get('cuscat') or '').strip() or None
        startdate = (request.POST.get('startdate') or '').strip() or None
        enddate = (request.POST.get('enddate') or '').strip() or None

        if not any([loantype, cuscat, startdate, enddate]):
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('awaiting_refund_loans')

        if bool(startdate) != bool(enddate):
            messages.error(request, 'Select both a start and an end date, or neither.', extra_tags='warning')
            return redirect('awaiting_refund_loans')

        if startdate and enddate:
            date_start = datetime.date(*[int(x) for x in startdate.split('-')])
            date_end = datetime.date(*[int(x) for x in enddate.split('-')])
            if date_start > date_end:
                messages.error(request, 'End date must be after Start date!')
                return redirect('awaiting_refund_loans')
            loans_filtered = loans_filtered.filter(funding_date__gte=date_start, funding_date__lte=date_end)

        if loantype:
            loans_filtered = loans_filtered.filter(loan_type=loantype)
        if cuscat:
            loans_filtered = loans_filtered.filter(owner__category=cuscat)
        filter_on = True

    credit_owed_sum = sum((l.credits.first().amount for l in loans_filtered if l.credits.first()), Decimal('0'))
    funded_sum = loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interests_sum = loans_filtered.aggregate(sum=Sum('interest'))['sum']
    totalloan_sum = loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
    repayments_sum = loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_sum = loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    defaultinterests_sum = loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
    outstanding_sum = loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']

    context = {
        'nav': 'awaiting_refund_loans', 'filter': 'on' if filter_on else None, 'referrer': referrer,
        'cuscat': cuscat, 'loantype': loantype, 'startdate': startdate, 'enddate': enddate,
        'all_loans': all_loans,
        'awaiting_refund_loans_filtered': loans_filtered,
        'pending_loans': pending_loans,
        'running_loans': running_loans,
        'defaulted_loans': defaulted_loans,
        'completed_loans': completed_loans,
        'recovery_loans': recovery_loans,
        'awaiting_refund_loans': awaiting_refund_loans,
        'credit_owed_sum': credit_owed_sum,
        'funded_sum': funded_sum,
        'interests_sum': interests_sum,
        'totalloan_sum': totalloan_sum,
        'repayments_sum': repayments_sum,
        'arrears_sum': arrears_sum,
        'defaultinterests_sum': defaultinterests_sum,
        'outstanding_sum': outstanding_sum,
    }
    return render(request, 'loans_awaiting_refund.html', context)


@admin_check
def view_loan(request, loan_ref):

    domainx = settings.DOMAIN
    
    loan = Loan.objects.get(ref=loan_ref)
    try:
        loanfile = LoanFile.objects.get(loan=loan)
    except:
        loanfile = []
    uid = loan.owner_id
    user = UserProfile.objects.get(pk=uid)
    usr = User.objects.get(pk=user.user_id)
    
    last_name_s = user.last_name[-1]
    
    stat = Statement.objects.filter(loanref=loan)
    
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

    # Newest statement line that the "Reverse Last Statement" button can undo
    # (funding / interest / refinance lines are structural and never reversible).
    from loan.reversal import REVERSIBLE_TYPES as _REV_TYPES
    _last = Statement.objects.filter(loanref=loan).order_by('-pk').first()
    reversal_info = _last if (_last is not None and _last.type in _REV_TYPES) else None

    return render(request, 'view_loan.html', {'loan':loan, 'user':user, 'usr': usr, 'last_name_s':last_name_s , 'stat': stat, 'domainx':domainx, 'loanfile':loanfile, 'show_referrer': _show_referrer, 'referrer': getattr(user, 'referred_by', None), 'reversal_info': reversal_info })

@admin_check
def approve(request, loan_ref):

    loan = Loan.objects.get(ref=loan_ref)
    loid = loan.owner.id
    
    user = UserProfile.objects.get(pk=loid)

    staff_profile = UserProfile.objects.get(user=request.user)
    staff = StaffProfile.objects.get(user=staff_profile)
    
    startdate = loan.repayment_start_date
    duration_days = loan.number_of_fortnights * 14
    
    expected_end_date = startdate + datetime.timedelta(days=duration_days)
    fourteendays = datetime.timedelta(days=14)
    
    startdate_str = startdate.strftime('%Y-%m-%d')

    repayment_dates_list = [startdate_str]
    last_date = startdate
    fns = loan.number_of_fortnights
    while fns > 1:
        new_date = last_date + fourteendays
        new_date_str = new_date.strftime('%Y-%m-%d')
        repayment_dates_list.append(new_date_str)
        last_date = new_date
        fns -= 1
    # Serialize the list to a JSON string
    loan.set_repayment_dates(repayment_dates_list)
    
    loan.expected_end_date = expected_end_date
    loan.category = "PENDING"
    loan.last_repayment_amount = 0.00
    loan.number_of_repayments = 0
    loan.total_paid = 0
    loan.total_arrears = 0
    loan.advance_payments = 0
    loan.last_default_amount = 0
    loan.number_of_defaults = 0
    loan.default_interest_paid = 0
    loan.status = 'APPROVED'
    loan.tc_agreement = 'YES'
    loan.officer = staff

    loan.principal_loan_receivable = loan.amount
    loan.ordinary_interest_receivable = loan.interest
    loan.default_interest_receivable = 0

    approval_total = loan.principal_loan_receivable + loan.ordinary_interest_receivable + loan.default_interest_receivable
    existing_total_outstanding = loan.total_outstanding
    
    if existing_total_outstanding > approval_total:
        loan.total_outstanding = existing_total_outstanding
    else:
        loan.total_outstanding = approval_total

    loan.save()

    user.has_loan = 1
    user.save()
    
   #send email to user
    
    subject = f'{loan_ref} is APPROVED'
    ''' if header_cta == 'yes' '''
    cta_label = 'View Loan'
    cta_link = f'{settings.DOMAIN}/loan/myloan/{loan.ref}/'

    greeting = f'Hi {loan.owner.first_name}'
    message = 'Your pending loan has been Approved.'
    message_details = f'Amount: K{round(loan.amount,2)}<br>\
                        Repayment: K{round(loan.repayment_amount,2)}<br>\
                        Repayment Start Date: {startdate}'

    ''' if cta == 'yes' '''
    cta_btn1_label = 'View Loan'
    cta_btn1_link = f'{settings.DOMAIN}/loan/myloan/{loan_ref}/'
    cta_btn2_label = ''
    cta_btn2_link = ''

    ''' if promo == 'yes' '''
    catchphrase = 'FUNDING?'
    promo_title = 'YOU WILL GET A FUNDING ALERT'
    promo_message = 'Once the loan is funded, you will get a funding notice in your email.'
    promo_cta = ''
    promo_cta_link = ''
    
    email_content = render_to_string('custom/email_temp_general.html', {
        'header_cta': 'no',
        'cta': 'yes',
        'cta_btn2': 'no',
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
    email = EmailMultiAlternatives(subject,text_content,sender,[user.email, 'dev@webmasta.com.pg'])
    email.attach_alternative(email_content, "text/html")

    try: 
        email.send()
        messages.success(request, f'Loan was approved and Approval Email was sent to {loan.owner.first_name} {loan.owner.last_name} successfully.')
    except:
        messages.error(request, 'Loan status is updated as "Approved" and moved to the "Funding List".', extra_tags='info')
        messages.error(request, 'Loan approval notice email was NOT sent, please advise the client by other means.', extra_tags='danger')
    
    return redirect('pending_loans')


@admin_check
def decline(request, loan_ref):
   
    loan = Loan.objects.get(ref=loan_ref)
    loid = loan.owner.id
    
    user = UserProfile.objects.get(pk=loid)
    usr = User.objects.get(pk=user.user_id)
    
    #send email to user
    
    
    subject = f'{loan_ref} DECLINED'
    ''' if header_cta == 'yes' '''
    cta_label = ''
    cta_link = ''

    greeting = f'Hi {loan.owner.first_name}'
    message = 'We regret to advise you that your loan has been declined'
    message_details = 'You can visit your dashboard to find out the reason(s) for this decline.'

    ''' if cta == 'yes' '''
    cta_btn1_label = 'Go to Dashboard'
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
        messages.success(request, f'Loan is declined and Decline notice was sent to {loan.owner.first_name} {loan.owner.last_name} successfully.')
        loan.delete()
    except:
        messages.error(request, "Loan was Declined and deleted from the system.", extra_tags='info')
        messages.error(request, "Loan decline notice could not be sent to the client, make sure you let the client know by phone.", extra_tags='danger')
        loan.delete()
        return redirect('loans')
    
    return redirect('pending_loans')

@admin_check
def funding_list(request):
    
    loans = Loan.objects.filter(category='PENDING', status='APPROVED')
    funding_list_count = loans.count
    pending_sum = loans.aggregate(sum=Sum('amount'))['sum']
    expected_interests_sum = loans.aggregate(sum=Sum('interest'))['sum']
    expected_repayments_sum = loans.aggregate(sum=Sum('repayment_amount'))['sum']
    
    context = {
        'domain': domain,
        'nav': 'funding_list', 
        'loans': loans,
        'pending_sum': pending_sum,
        'expected_interests_sum' : expected_interests_sum,
        'expected_repayments_sum' : expected_repayments_sum   
    }
    
    return render(request, 'funding_list.html', context)
def _generate_cdn_pdf(loan, user, first_repayment_date, today_str):
    """Generate the Cash Disbursement Notice as a PDF bytes object using wkhtmltopdf."""
    from django.template.loader import render_to_string
    from decimal import Decimal as _D

    funding_date = loan.funding_date.strftime('%d/%m/%Y') if loan.funding_date else today_str

    try:
        _ls = AdminSettings.objects.get(settings_name='setting1')
        _fee_mode = getattr(_ls, 'processing_fee_collection_mode', 'CASH')
    except Exception:
        _fee_mode = 'CASH'
    _fee = _D(str(loan.processing_fee or 0))
    _disbursed_amount = (loan.amount - _fee) if (_fee_mode == 'WITHHELD' and _fee > 0) else loan.amount

    bank_config = get_bank_config()
    context = {
        'loan': loan,
        'user': user,
        'today': datetime.date.today().strftime('%d %B %Y'),
        'funding_date': funding_date,
        'first_repayment_date': first_repayment_date.strftime('%d %B %Y') if hasattr(first_repayment_date, 'strftime') else first_repayment_date,
        'domain': settings.DOMAIN,
        'disbursed_amount': _disbursed_amount,
        'fee_collection_mode': _fee_mode,
        'bank_name': bank_config["bank"],
        'bank_account_name': bank_config["bank_acc_name"].title(),
        'bank_account_number': bank_config["bank_acc_num"],
        'bank_branch': bank_config["bank_branch"].title(),
        'deduction_code': bank_config["alesco_dc"],
        'document_theme': get_document_theme(),
    }

    html = render_to_string('custom/cash_disbursement_notice.html', context)
    try:
        from moromafinance.pdf import render_html_pdf
        return render_html_pdf(html)
    except Exception:
        return None


def _send_cdn_email(request, loan, user, pdf_bytes):
    """Email the CDN PDF.

    Routing is controlled by the AdminSettings.cdn_send_to_payroll_officer flag:
      - True  → To: payroll officer email, CC: admin
      - False → To: admin only (no payroll officer)
    """
    from django.core.mail import EmailMultiAlternatives

    # Read the routing setting
    try:
        _ls = AdminSettings.objects.get(settings_name='setting1')
        send_to_payroll = _ls.cdn_send_to_payroll_officer
    except Exception:
        send_to_payroll = True

    admin_emails = settings.ADMIN_EMAILS
    sender = settings.DEFAULT_SENDER_EMAIL
    payroll_email = user.payroll_officer_email

    subject = f'Loan Disbursement Notification – {user.first_name} {user.last_name} – {loan.ref}'
    filename = f'CDN_{loan.ref}_{user.last_name}_{user.first_name}.pdf'

    if send_to_payroll:
        if not payroll_email:
            messages.warning(
                request,
                f'CDN payroll routing is on but no Payroll Officer Email is set for '
                f'{user.first_name} {user.last_name}. Sending to admin only.'
            )
            to_list = admin_emails
            cc_list = []
        else:
            to_list = [payroll_email]
            cc_list = admin_emails

        body = (
            f'Dear {user.payroll_officer_name or "HR/Payroll Officer"},\n\n'
            f'Please find attached the Cash Disbursement Notice for {user.first_name} {user.last_name} '
            f'(Employee File No: {user.employee_file_number or "N/A"}).\n\n'
            f'Loan Reference: {loan.ref}\n'
            f'Amount Disbursed: K{loan.amount:,.2f}\n'
            f'Repayment Per Fortnight: K{loan.repayment_amount:,.2f}\n'
            f'Number of Fortnights: {loan.number_of_fortnights}\n\n'
            f'Please effect salary deductions as per the notice.\n\n'
            f'Best regards,\n{settings.COMPANY_NAME}'
        )
        success_msg = f'Cash Disbursement Notice sent to {", ".join(to_list)}.'
    else:
        # Admin-only mode
        to_list = admin_emails
        cc_list = []
        body = (
            f'[Admin Copy – Payroll Officer routing is disabled]\n\n'
            f'Cash Disbursement Notice for {user.first_name} {user.last_name} '
            f'(Employer: {user.employer or "N/A"}, '
            f'Payroll Officer: {user.payroll_officer_name or "N/A"}, '
            f'Payroll Email: {payroll_email or "not set"}).\n\n'
            f'Loan Reference: {loan.ref}\n'
            f'Amount Disbursed: K{loan.amount:,.2f}\n'
            f'Repayment Per Fortnight: K{loan.repayment_amount:,.2f}\n'
            f'Number of Fortnights: {loan.number_of_fortnights}\n\n'
            f'Best regards,\n{settings.COMPANY_NAME}'
        )
        success_msg = f'Cash Disbursement Notice sent to admin only (payroll routing disabled).'

    email = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=sender,
        to=to_list,
        cc=cc_list,
    )

    if pdf_bytes:
        email.attach(filename, pdf_bytes, 'application/pdf')

    try:
        email.send()
        messages.success(request, success_msg)
    except Exception as e:
        messages.error(request, f'CDN email could not be sent: {e}', extra_tags='danger')


def _send_amortization_email(request, loan, user, repayment_dates_list):
    """Email the full amortization schedule to the client, using the same table as the LAS PDF."""
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags
    from admin1.mainView import _build_las_context

    # Build the same schedule context used by the LAS PDF
    las = _build_las_context(loan, user, settings.DOMAIN)
    schedule = las['schedule']
    cols = las['cols']

    # Helper to build a styled header cell
    th = lambda txt: f'<th style="padding:4px 10px;border:1px solid #7030a0;background:#7030a0;color:#fff;font-size:12px;">{txt}</th>'
    # Helper to build a styled data cell
    td = lambda txt: f'<td style="padding:3px 8px;border:1px solid #ddd;font-size:12px;text-align:right;">{txt}</td>'
    td_c = lambda txt: f'<td style="padding:3px 8px;border:1px solid #ddd;font-size:12px;text-align:center;">{txt}</td>'

    # Build header
    headers = ''
    if cols.get('period'):    headers += th('#')
    if cols.get('date'):      headers += th('Repayment Date')
    if cols.get('opening'):   headers += th('Opening Balance')
    if cols.get('interest'):  headers += th('Interest')
    if cols.get('principal'): headers += th('Principal')
    if cols.get('repayment'): headers += th('Repayment')
    if cols.get('closing'):   headers += th('Closing Balance')

    # Build rows
    rows = ''
    for idx, row in enumerate(schedule):
        bg = '#f9f4ff' if idx % 2 == 1 else '#fff'
        cells = ''
        if cols.get('period'):    cells += td_c(row['period'])
        if cols.get('date'):      cells += td(row['date'])
        if cols.get('opening'):   cells += td(f"{row['opening']:,.2f}")
        if cols.get('interest'):  cells += td(f"{row['interest']:,.2f}")
        if cols.get('principal'): cells += td(f"{row['principal']:,.2f}")
        if cols.get('repayment'): cells += td(f"{row['repayment']:,.2f}")
        if cols.get('closing'):   cells += td(f"{row['closing']:,.2f}")
        rows += f'<tr style="background:{bg};">{cells}</tr>'

    # Build totals row
    total_cells = ''
    if cols.get('period'):    total_cells += td_c('<strong>Total</strong>')
    if cols.get('date'):      total_cells += td('')
    if cols.get('opening'):   total_cells += td('')
    if cols.get('interest'):  total_cells += td(f"<strong>{las['total_interest']:,.2f}</strong>")
    if cols.get('principal'): total_cells += td(f"<strong>{las['total_principal']:,.2f}</strong>")
    if cols.get('repayment'): total_cells += td(f"<strong>{las['total_repayment']:,.2f}</strong>")
    if cols.get('closing'):   total_cells += td('<strong>0.00</strong>')
    totals_row = f'<tr style="background:#7030a0;color:#fff;">{total_cells}</tr>'

    schedule_html = (
        f'<table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:12px;width:100%;">'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'<tfoot>{totals_row}</tfoot>'
        f'</table>'
    )

    subject = f'Loan Amortization Schedule – {loan.ref}'
    message = 'Your full loan amortization schedule is shown below.'
    message_details = (
        f'<strong>Loan Ref:</strong> {loan.ref}<br>'
        f'<strong>Loan Amount:</strong> K{loan.amount:,.2f}<br>'
        f'<strong>Repayment Per Fortnight:</strong> K{loan.repayment_amount:,.2f}<br>'
        f'<strong>Number of Fortnights:</strong> {loan.number_of_fortnights}<br>'
        f'<strong>Total Loan Incl. Interest:</strong> K{loan.total_loan_amount:,.2f}<br><br>'
        f'<strong>Amortization Schedule:</strong><br><br>'
        f'{schedule_html}'
    )

    email_content = render_to_string('custom/email_temp_general.html', {
        'header_cta': 'no', 'cta': 'no', 'cta_btn2': 'no', 'promo': 'no',
        'cta_link': '', 'cta_label': '',
        'subject': subject,
        'greeting': f'Hi {user.first_name}',
        'message': message,
        'message_details': message_details,
        'cta_btn1_link': '', 'cta_btn1_label': '',
        'cta_btn2_link': '', 'cta_btn2_label': '',
        'catchphrase': '', 'promo_title': '', 'promo_message': '',
        'promo_cta_link': '', 'promo_cta': '',
        'user': user,
        'domain': settings.DOMAIN,
    })

    text_content = strip_tags(email_content)
    sender = settings.DEFAULT_SENDER_EMAIL

    email_msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=sender,
        to=[user.email],
        cc=settings.CC_EMAILS,
        bcc=settings.BCC_EMAILS,
    )
    email_msg.attach_alternative(email_content, 'text/html')

    try:
        email_msg.send()
        messages.success(request, f'Amortization schedule sent to {user.email}.')
    except Exception as e:
        messages.error(request, f'Amortization schedule email could not be sent: {e}', extra_tags='danger')


@admin_check
def fund_loan(request, loanref):

    loan = Loan.objects.select_related('owner').get(ref=loanref)
    owner = loan.owner
    
    today = datetime.date.today()
    fourteendays = datetime.timedelta(days=14)

    repayment_start_date = loan.repayment_start_date

    next_payment_date = repayment_start_date + fourteendays
    next_next = next_payment_date + fourteendays

    if today < repayment_start_date:
        first_repayment_date = repayment_start_date
    elif repayment_start_date < today < next_payment_date:
        first_repayment_date = next_payment_date
    elif next_payment_date < today < next_next:
        first_repayment_date = next_next
    else:
        first_repayment_date = next_next + fourteendays

    first_repayment_date_str = first_repayment_date.strftime('%Y-%m-%d')

    repayment_dates_list = [first_repayment_date_str]
    last_date = first_repayment_date
    fns = loan.number_of_fortnights
    while fns > 1:
        new_date = last_date + fourteendays
        new_date_str = new_date.strftime('%Y-%m-%d')
        repayment_dates_list.append(new_date_str)
        last_date = new_date
        fns -= 1

    if settings.SYSTEM_TYPE == 'ONE_LOAN_PER_CLIENT':
        try:
            #check for existing running loan

            running_loan = Loan.objects.filter(owner=owner, category="FUNDED", funded_category__in=["ACTIVE", "DEFAULTED"]).last()
            if running_loan.total_outstanding > settings.LOAN_COMPLETION_BALANCE:
                from loan.refinance import refinance_allowed
                if not refinance_allowed():
                    messages.error(
                        request,
                        f'{owner.first_name} {owner.last_name} still has an active loan ({running_loan.ref}) and '
                        'refinancing is currently disabled (Refinance Type = Refinance Not Allowed). This loan '
                        'cannot be funded until the existing loan is fully completed.',
                        extra_tags='danger',
                    )
                    return redirect('view_loan', loanref)
                fund_additional_loan(request, running_loan_id=running_loan.id, new_loan_id=loan.id)
                # Send CDN and Amortization after additional loan funding
                _user = UserProfile.objects.get(id=loan.owner.id)
                try:
                    _loan_setting = AdminSettings.objects.get(settings_name='setting1')
                    _send_cdn = _loan_setting.send_cash_disbursement_notice
                    _send_amort = _loan_setting.send_loan_amortization_schedule
                except Exception:
                    _send_cdn = True
                    _send_amort = True
                # Reload loan to get updated repayment_amount etc.
                loan.refresh_from_db()
                if _send_cdn:
                    _cdn_pdf = _generate_cdn_pdf(loan, _user, first_repayment_date, today.strftime('%d/%m/%Y'))
                    _send_cdn_email(request, loan, _user, _cdn_pdf)
                if _send_amort:
                    _send_amortization_email(request, loan, _user, repayment_dates_list)
                return redirect('funding_receipt_upload', loan.ref)
            else:
                #need to check
                complete_loan(request, running_loan)
        except:
            pass
      
    # Serialize the list to a JSON string
    loan.set_repayment_dates(repayment_dates_list)
    loan.category = 'FUNDED'
    loan.funded_category = 'ACTIVE'
    loan.status = 'RUNNING'
    loan.tc_agreement = 'YES'
    loan.funding_date = today
    loan.next_payment_date = first_repayment_date
    loan.save()
    
    user = UserProfile.objects.get(id=loan.owner.id)
    user.number_of_loans += 1
    # A funded loan implies signed terms + credit-check consent.
    user.credit_consent = 'YES'
    user.terms_consent = 'YES'
    user.save()

    # Tiered processing fee (only applied when processing_fee is enabled in loan settings)
    from admin1.models import ProcessingFeeTier
    from decimal import Decimal as _D
    try:
        _ls = AdminSettings.objects.get(settings_name='setting1')
        _fee_enabled = getattr(_ls, 'processing_fee', 'NO') == 'YES'
        _fee_mode = getattr(_ls, 'processing_fee_collection_mode', 'CASH')
    except Exception:
        _fee_enabled = False
        _fee_mode = 'CASH'
    _processing_fee = ProcessingFeeTier.get_fee_for_amount(loan.amount) if _fee_enabled else 0
    if _fee_enabled and _processing_fee > 0:
        loan.processing_fee = _processing_fee
    else:
        loan.processing_fee = 0
    loan.save()

    _amount    = _D(str(loan.amount or 0))
    _interest  = _D(str(loan.interest or 0))
    _fee       = _D(str(loan.processing_fee or 0))

    # Line 1: Loan Funded – principal advanced
    Statement.objects.create(
        owner=user, ref=f'{loanref}F', loanref=loan, type="OTHER",
        statement="Loan Funded",
        credit=_amount, balance=_amount,
        date=today, uid=user.uid, luid=settings.LUID,
    )
    # Line 2: Interest charged upfront
    Statement.objects.create(
        owner=user, ref=f'{loanref}F', loanref=loan, type="OTHER",
        statement="Loan Interest Charged",
        credit=_interest, balance=_amount + _interest,
        date=today, uid=user.uid, luid=settings.LUID,
    )
    # Processing fee is collected separately (cash or withheld from payout) — not a loan statement line

    # Construct the repayment dates HTML string
    repayment_dates_html = ''.join([f'<div>{date}</div>' for date in repayment_dates_list])
    #send email to user
    
    subject = f'{loanref} FUNDED'
    ''' if header_cta == 'yes' '''
    cta_label = ''
    cta_link = ''

    greeting = f'Hi {loan.owner.first_name}'
    message = 'Your approved loan has been funded'
    _email_amount = round(loan.amount - (_processing_fee or 0), 2) if _fee_mode == 'WITHHELD' else round(loan.amount, 2)
    _fee_note = f'Processing Fee: K{round(_processing_fee or 0, 2)} (withheld from funding amount)<br>' if (_fee_mode == 'WITHHELD' and (_processing_fee or 0) > 0) else (f'Processing Fee: K{round(_processing_fee or 0, 2)} (payable in cash)<br>' if (_processing_fee or 0) > 0 else '')
    message_details = f'Amount Disbursed: K{_email_amount}<br>\
                        {_fee_note}\
                        Total Loan: K{round(loan.total_loan_amount,2)}<br>\
                        Repayment: K{round(loan.repayment_amount,2)}<br>\
                        Repayment Start Date: {loan.next_payment_date}<br>\
                        Your repayment dates are listed here in order for your reference:</br>\
                        {repayment_dates_html}'

    ''' if cta == 'yes' '''
    cta_btn1_label = 'View Loan'
    cta_btn1_link = f'{settings.DOMAIN}/loan/myloan/{loan.ref}/'
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
        messages.success(request, f'Loan funding notice was sent to {loan.owner.first_name} {loan.owner.last_name} successfully.')
    except:
        messages.error(request, 'Loan has been categorized as "FUNDED" and status updated to "RUNNING".', extra_tags='info')
        messages.error(request, 'Loan funding notice was NOT sent, please advise the client by email or phone.".', extra_tags='danger')
       
       

    # ── CDN & Amortization Schedule ──────────────────────────────────────────
    try:
        _loan_setting = AdminSettings.objects.get(settings_name='setting1')
        _send_cdn = _loan_setting.send_cash_disbursement_notice
        _send_amort = _loan_setting.send_loan_amortization_schedule
    except Exception:
        _send_cdn = True
        _send_amort = True

    if _send_cdn:
        _cdn_pdf = _generate_cdn_pdf(loan, user, first_repayment_date, today.strftime('%d/%m/%Y'))
        _send_cdn_email(request, loan, user, _cdn_pdf)

    if _send_amort:
        _send_amortization_email(request, loan, user, repayment_dates_list)
    # ─────────────────────────────────────────────────────────────────────────

    return redirect('funding_receipt_upload', loanref)
#email send end

@admin_check
def funding_receipt_upload(request, loanref):
    loan = Loan.objects.get(ref=loanref)

    user = UserProfile.objects.get(id=loan.owner.id)
    
    if request.method == 'POST':
        uploadform = ReceiptUploadForm(request.POST)
        
        if uploadform.is_valid():

            try:
                loanfile = LoanFile.objects.get(loan=loan)
            except:
                messages.error(request, "There is no Loan File for this Loan.", extra_tags='warning')
                referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
                return redirect(referrer)
            
            if 'funding_receipt' in request.FILES:
                loanfileuploader(request,'funding_receipt', user, loan)

                loan.save()
                loan.files.save()
                loanfile.save()
                
                funding_receipt_url = loan.files.funding_receipt_url
                funding_receipt_url_full_file_path = f'{settings.DOMAIN}{funding_receipt_url}'

                response = requests.get(funding_receipt_url_full_file_path, verify=False)

                
                
                subject = f'Funding Receipt-{loanref}'
                ''' if header_cta == 'yes' '''
                cta_label = ''
                cta_link = ''

                greeting = f'Hi {loan.owner.first_name}'
                message = 'You can view and download the funding receipt for your reference.'
                message_details = f'We thank you for borrowing from us and we look forward to a \
                successful loan term. One or two defaults will affect your credit rating and may \
                affect your ability to borrow in the future. Please ensure you make your repayments \
                on time to avoid any inconveniences.'

                ''' if cta == 'yes' '''
                cta_btn1_label = 'View Receipt'
                cta_btn1_link = f'{settings.DOMAIN}{funding_receipt_url}/'
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

                #recipients
                reply_to_email = settings.REPLY_TO_EMAIL
                from accounts.functions import work_email_allowed as _wea
                email_list_one = [e for e in [user.email, _wea(user)] if e]
                email_list_two = settings.ADMIN_EMAILS
                email_list  = email_list_one + email_list_two
                cc_list = settings.CC_EMAILS
                bcc_list = settings.BCC_EMAILS
                
                text_content = strip_tags(email_content)
                email = EmailMultiAlternatives(subject,text_content,sender,email_list, bcc=bcc_list, cc=cc_list, reply_to=[reply_to_email])
                email.attach_alternative(email_content, "text/html")

                #email.attach_file(settings.DOMAIN+funding_receipt_url)

                # Attach the downloaded file
                if response.status_code == 200:
                    file_name = funding_receipt_url.split('/')[-1]
                    email.attach(file_name, response.content, 'application/pdf')

                try: 
                    email.send()
                    messages.success(request, f'Loan funding receipt was sent to {loan.owner.first_name} {loan.owner.last_name} successfully.')
                except:
                    messages.error(request, 'Loan has been categorized as "FUNDED" and status updated to "RUNNING".', extra_tags='info')
                    messages.error(request, 'Loan funding notice was NOT sent, please advise the client by email or phone.".', extra_tags='danger')
                
            
            return redirect('funding_list')

        else:
            messages.error(request, "Form is Not Valid", extra_tags='warning')
            return redirect('funding_list')      
            
    else:
        uploadform = ReceiptUploadForm()        
    return render(request, 'funding_receipt_upload.html', { 'form': uploadform})  


@admin_check
def cancel_funding(request, loanref):

    loan = Loan.objects.get(ref=loanref)
    loid = loan.owner.id
    
    user = UserProfile.objects.get(pk=loid)
    usr = User.objects.get(pk=user.user_id)
    
    #send email to user
    
    
    subject = f'{loanref} FUNDING <span style="color: orange;">CANCELLED</span>'
    ''' if header_cta == 'yes' '''
    cta_label = ''
    cta_link = ''

    greeting = f'Hi {loan.owner.first_name}'
    message = 'We regret to advise you that funding was cacelled.'
    message_details = 'You can visit your dashboard to find out the reason(s) for this decline.'

    ''' if cta == 'yes' '''
    cta_btn1_label = 'Go to Dashboard'
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
        messages.success(request, f'Loan funding is cancelled and notice was sent to {loan.owner.first_name} {loan.owner.last_name} successfully.')
        loan.delete()
    except:
        messages.error(request, "Loan was Cancelled and deleted from the system.", extra_tags='info')
        messages.error(request, "Loan cancellation notice could not be sent to the client, make sure you let the client know by phone.", extra_tags='danger')
        loan.delete()
        return redirect('loans')
    
    return redirect('funding_list')

  
