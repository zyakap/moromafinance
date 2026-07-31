import datetime
import re
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
from accounts.models import User, UserProfile
from accounts.functions import admin_check
from admin1.models import AdminSettings, Location
from admin1.forms import AdminSettingsForm
from loan.models import Loan, Statement, Payment, PaymentUploads
from loan.forms import PaymentForm
sender = settings.DEFAULT_SENDER_EMAIL

############### 
# START OF CODE
###############

@admin_check
def transactions(request):

    transactions = Statement.objects.prefetch_related('loanref','owner').order_by('-date')
    
    fundedsum = Statement.objects.aggregate(fundedsum=Sum('credit'))
    payments_sum = Payment.objects.aggregate(paymentsum=Sum('amount'))
    default_ic = Statement.objects.aggregate(dicsum = Sum('default_interest_collected'))
    inrecovery = Loan.objects.filter(funded_category='RECOVERY').aggregate(recoverysum=Sum('total_outstanding'))
    
    pl_fundedsum = Statement.objects.filter(loanref__loan_type="PERSONAL").aggregate(fundedsum=Sum('credit'))
    pl_payments_sum = Payment.objects.filter(loanref__loan_type="PERSONAL").aggregate(paymentsum=Sum('amount'))
    pl_default_ic = Statement.objects.filter(loanref__loan_type="PERSONAL").aggregate(dicsum = Sum('default_interest_collected'))
    pl_inrecovery = Loan.objects.filter(funded_category='RECOVERY', loan_type="PERSONAL").aggregate(recoverysum=Sum('total_outstanding'))
    
    sme_fundedsum = Statement.objects.filter(loanref__loan_type="SME").aggregate(fundedsum=Sum('credit'))
    sme_payments_sum = Payment.objects.filter(loanref__loan_type="SME").aggregate(paymentsum=Sum('amount'))
    sme_default_ic = Statement.objects.filter(loanref__loan_type="SME").aggregate(dicsum = Sum('default_interest_collected'))
    sme_inrecovery = Loan.objects.filter(funded_category='RECOVERY', loan_type="SME").aggregate(recoverysum=Sum('total_outstanding'))
    
    total_expected = Loan.objects.filter(category='FUNDED').exclude(funded_category='COMPLETED').aggregate(sum = Sum('total_loan_amount'))
    total_arrears = Loan.objects.filter(category='FUNDED').exclude(funded_category='COMPLETED').aggregate(sum = Sum('total_arrears'))
    total_outstanding = Loan.objects.filter(category='FUNDED').exclude(funded_category='COMPLETED').aggregate(sum = Sum('total_outstanding'))
    
    
    #payments & defaults by week
    month = datetime.datetime.now().month
    year = datetime.datetime.now().year
    format = '%Y-%m-%d'
    
    week1start = f'{year}-{month}-1'
    week1end = f'{year}-{month}-7'
    week2start = f'{year}-{month}-8'
    week2end = f'{year}-{month}-14'
    week3start = f'{year}-{month}-15'
    week3end = f'{year}-{month}-21'
    
    
    if month in (1,3,5,7,8,10,12):
        week4start = f'{year}-{month}-22'
        week4end = f'{year}-{month}-31'
    elif month == 2:
        week4start = f'{year}-{month}-22'
        week4end = f'{year}-{month}-28'
    else:
        week4start = f'{year}-{month}-22'
        week4end = f'{year}-{month}-30'
    
    week1_start = datetime.datetime.strptime(week1start, format)
    week1_end = datetime.datetime.strptime(week1end, format)
    week2_start = datetime.datetime.strptime(week2start, format)
    week2_end = datetime.datetime.strptime(week2end, format)
    week3_start = datetime.datetime.strptime(week3start, format)
    week3_end = datetime.datetime.strptime(week3end, format)
    week4_start = datetime.datetime.strptime(week4start, format)
    week4_end = datetime.datetime.strptime(week4end, format)
    
    wk1payments = Payment.objects.filter(date__gte=week1_start, date__lte=week1_end).aggregate(sum=Sum('amount'))['sum']
    if not wk1payments:
       wk1payments = 0
    wk2payments = Payment.objects.filter(date__gte=week2_start, date__lte=week2_end).aggregate(sum=Sum('amount'))['sum']
    if not wk2payments:
       wk2payments = 0
    wk3payments = Payment.objects.filter(date__gte=week3_start, date__lte=week3_end).aggregate(sum=Sum('amount'))['sum']
    if not wk3payments:
       wk3payments = 0
    wk4payments = Payment.objects.filter(date__gte=week4_start, date__lte=week4_end).aggregate(sum=Sum('amount'))['sum']
    if not wk4payments:
       wk4payments = 0
       
    wk1defaults = Statement.objects.filter(date__gte=week1_start, date__lte=week1_end, default_amount__gt=0).aggregate(sum=Sum('default_amount'))['sum']
    if not wk1defaults:
        wk1defaults = 0
    wk2defaults = Statement.objects.filter(date__gte=week2_start, date__lte=week2_end, default_amount__gt=0).aggregate(sum=Sum('default_amount'))['sum']
    if not wk2defaults:
        wk2defaults = 0
    wk3defaults = Statement.objects.filter(date__gte=week3_start, date__lte=week3_end, default_amount__gt=0).aggregate(sum=Sum('default_amount'))['sum']
    if not wk3defaults:
        wk3defaults = 0
    wk4defaults = Statement.objects.filter(date__gte=week4_start, date__lte=week4_end, default_amount__gt=0).aggregate(sum=Sum('default_amount'))['sum']
    if not wk4defaults:
        wk4defaults = 0
        
    weekpayments = [float(wk1payments),float(wk2payments),float(wk3payments),float(wk4payments)]
    weekdefaults = [float(wk1defaults),float(wk2defaults),float(wk3defaults),float(wk4defaults)]
    
    
    monthpayments = Payment.objects.filter(date__gte=week1_start, date__lte=week4_end).aggregate(sum=Sum('amount'))['sum']
    if not monthpayments:
       monthpayments = 0
    
    monthdefaults = Statement.objects.filter(date__gte=week1_start, date__lte=week4_end, default_amount__gt=0).aggregate(sum=Sum('default_amount'))['sum']
    if not monthdefaults:
        monthdefaults = 0
    
    locpaylabel = []
    locpay = []
   
    locations = Location.objects.all()
   
    for location in locations:
        locpayqs = Payment.objects.select_related('loanref').filter(loanref__location=location, date__gte=week1_start, date__lte=week4_end)
        locpaycount = locpayqs.count()
        if locpaycount != 0:
            locpay.append(float(locpayqs.aggregate(sum=Sum('amount'))['sum']))
        else:
            locpay.append(0)
            
        locpaylabel.append(f'{location.name}, {locpaycount}')
    
    
    context = { 
               'nav': 'transactions', 
               'fundedsum': fundedsum,
               'payments_sum': payments_sum,
               'default_ic': default_ic,
               'inrecovery': inrecovery,
               
               'pl_fundedsum': pl_fundedsum,
               'pl_payments_sum': pl_payments_sum,
               'pl_default_ic': pl_default_ic,
               'pl_inrecovery': pl_inrecovery,
               
               'sme_fundedsum': sme_fundedsum,
               'sme_payments_sum': sme_payments_sum,
               'sme_default_ic': sme_default_ic,
               'sme_inrecovery': sme_inrecovery,
               
               'total_expected': total_expected,
               'total_arrears': total_arrears,
               'total_outstanding': total_outstanding,
               
               'transactions': transactions, 
               'weekpayments': weekpayments,
               'weekdefaults': weekdefaults,
               'monthpayments': monthpayments,
               'monthdefaults':monthdefaults,
               
               'locpaylabel':locpaylabel,
               'locpay':locpay,
               }
   
    return render(request, 'transactions.html', context)


@admin_check
def transactions_all(request):

    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
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
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,     
                    }  
                
            elif transtype=='DEFAULT':
                all_defaults = all_trans_filtered
                defaults_sum = all_trans_filtered.aggregate(sum=Sum('default_amount'))['sum']
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,   
                    }  
            else:
                all_credits = all_trans_filtered
                credits_sum = all_trans_filtered.aggregate(sum=Sum('credit'))['sum']
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer, 
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,  
                    }  
            
            return render(request, 'transactions_all.html', context)
        
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
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer, 
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'transactions_all.html', context)
        
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
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer, 
                        'startdate': start_date, 'enddate': end_date, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,     
                    }  
                
            elif transtype=='DEFAULT':
                all_defaults = all_trans_filtered
                defaults_sum = all_trans_filtered.aggregate(sum=Sum('default_amount'))['sum']
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer, 
                        'startdate': start_date, 'enddate': end_date, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,   
                    }  
            else:
                all_credits = all_trans_filtered
                credits_sum = all_trans_filtered.aggregate(sum=Sum('credit'))['sum']
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer, 
                        'startdate': start_date, 'enddate': end_date, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,  
                    }  
            
            return render(request, 'transactions_all.html', context)
        
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
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'transactions_all.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('transtype'): 

            loantype = request.POST.get('loantype')
            transtype = request.POST.get('transtype')

            all_trans_filtered = Statement.objects.prefetch_related('owner','loanref').filter(loanref__loan_type=loantype, type = transtype).all()
            if transtype=='PAYMENT':
                all_payments = all_trans_filtered
                payments_sum = all_trans_filtered.aggregate(sum=Sum('debit'))['sum']
                
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                         'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,     
                    }  
                
            elif transtype=='DEFAULT':
                all_defaults = all_trans_filtered
                defaults_sum = all_trans_filtered.aggregate(sum=Sum('default_amount'))['sum']
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                         'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,   
                    }  
            else:
                all_credits = all_trans_filtered
                credits_sum = all_trans_filtered.aggregate(sum=Sum('credit'))['sum']
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,  
                    }  
            
            return render(request, 'transactions_all.html', context)
        
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
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'transactions_all.html', context)
        
        elif request.POST.get('transtype'): 
            
            transtype = request.POST.get('transtype')

            all_trans_filtered = Statement.objects.prefetch_related('owner','loanref').filter(type = transtype).all()
            if transtype=='PAYMENT':
                all_payments = all_trans_filtered
                payments_sum = all_trans_filtered.aggregate(sum=Sum('debit'))['sum']
                
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                         'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,     
                    }  
                
            elif transtype=='DEFAULT':
                all_defaults = all_trans_filtered
                defaults_sum = all_trans_filtered.aggregate(sum=Sum('default_amount'))['sum']
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                         'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,   
                    }  
            else:
                all_credits = all_trans_filtered
                credits_sum = all_trans_filtered.aggregate(sum=Sum('credit'))['sum']
                context = {
                        'nav' : 'transactions_all', 'filter': 'on', 'referrer': referrer,
                         'transtype': transtype,
                        'all_trans_filtered': all_trans_filtered,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,  
                    }  
            
            return render(request, 'transactions_all.html', context)
        
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
                'nav' : 'transactions_all', 
                'all_trans_filtered': all_trans_filtered,
                'all_payments': all_payments,
                'payments_sum':payments_sum,
                'all_defaults': all_defaults,
                'defaults_sum':defaults_sum,
                'all_credits':all_credits,
                'credits_sum': credits_sum,
                
            }  
    
    return render(request, 'transactions_all.html', context)


@admin_check
def transactions_payments(request):

    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype') and request.POST.get('modeofpayment'):
            
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')
            modeofpayment = request.POST.get('modeofpayment')

            start_date = start_date_entry 
            end_date = end_date_entry 

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('transactions_all')

            all_payments_filtered = Payment.objects.prefetch_related('owner','loanref').filter(loanref__loan_type=loantype, mode = modeofpayment, date__gte = start_date, date__lte = end_date).all()
            if modeofpayment=='PAYROLL DEDUCTION':
                all_fn_deductions = all_payments_filtered
                deductions_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_fn_deductions': all_fn_deductions,
                        'deductions_sum':deductions_sum,     
                    }  
                
            elif modeofpayment=='BANK DEPOSIT':
                all_bdeposits = all_payments_filtered
                deposits_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_bdeposits': all_bdeposits,
                        'deposits_sum':deposits_sum,   
                    }  
            else:
                all_cash = all_payments_filtered
                cash_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype, 'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_cash':all_cash,
                        'cash_sum': cash_sum,  
                    }  
            
            return render(request, 'transactions_payments.html', context)
        
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
                return redirect('transactions_payments')

            all_payments_filtered = Payment.objects.prefetch_related('owner','loanref').filter(loanref__loan_type=loantype, date__gte = start_date, date__lte = end_date).all()
            
            all_fn_deductions = all_payments_filtered.filter(type='PAYMENT')
            deductions_sum = all_fn_deductions.aggregate(sum=Sum('amount'))['sum']
           
            all_bdeposits = all_payments_filtered.filter(type='DEFAULT')
            deposits_sum = all_bdeposits.aggregate(sum=Sum('amount'))['sum']
            
            all_cash = all_payments_filtered.filter(type='OTHERS')
            cash_sum = all_cash.aggregate(sum=Sum('amount'))['sum']
            
            
            context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype,
                        'all_payments_filtered': all_payments_filtered,
                        'all_fn_deductions': all_fn_deductions,
                        'deductions_sum':deductions_sum,
                        'all_bdeposits': all_bdeposits,
                        'deposits_sum':deposits_sum,
                        'all_cash':all_cash,
                        'cash_sum': cash_sum,
                        
                    }  
            
            return render(request, 'transactions_payments.html', context)
        
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('modeofpayment'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            modeofpayment = request.POST.get('modeofpayment')

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('transactions_payments')

            all_payments_filtered = Payment.objects.prefetch_related('owner','loanref').filter(mode = modeofpayment, date__gte = start_date, date__lte = end_date).all()
            if modeofpayment=='PAYROLL DEDUCTION':
                all_fn_deductions = all_payments_filtered
                deductions_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_fn_deductions': all_fn_deductions,
                        'deductions_sum':deductions_sum,     
                    }  
                
            elif modeofpayment=='BANK DEPOSIT':
                all_bdeposits = all_payments_filtered
                deposits_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date,  'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_bdeposits': all_bdeposits,
                        'deposits_sum':deposits_sum,   
                    }  
            else:
                all_cash = all_payments_filtered
                cash_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_cash':all_cash,
                        'cash_sum': cash_sum,  
                    }  
            
            return render(request, 'transactions_payments.html', context)
        
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
                return redirect('transactions_payments')

            all_payments_filtered = Payment.objects.prefetch_related('owner','loanref').filter(date__gte = start_date, date__lte = end_date).all()
            
            all_fn_deductions = all_payments_filtered.filter(type='PAYMENT')
            deductions_sum = all_fn_deductions.aggregate(sum=Sum('amount'))['sum']
           
            all_bdeposits = all_payments_filtered.filter(type='DEFAULT')
            deposits_sum = all_bdeposits.aggregate(sum=Sum('amount'))['sum']
            
            all_cash = all_payments_filtered.filter(type='OTHERS')
            cash_sum = all_cash.aggregate(sum=Sum('amount'))['sum']
            
            
            context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 
                        'all_payments_filtered': all_payments_filtered,
                        'all_fn_deductions': all_fn_deductions,
                        'deductions_sum':deductions_sum,
                        'all_bdeposits': all_bdeposits,
                        'deposits_sum':deposits_sum,
                        'all_cash':all_cash,
                        'cash_sum': cash_sum,
                        
                    }  
            
            return render(request, 'transactions_payments.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('modeofpayment'): 

            loantype = request.POST.get('loantype')
            modeofpayment = request.POST.get('modeofpayment')

            all_payments_filtered = Payment.objects.prefetch_related('owner','loanref').filter(loanref__loan_type=loantype, mode = modeofpayment).all()
            if modeofpayment=='PAYROLL DEDUCTION':
                all_fn_deductions = all_payments_filtered
                deductions_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_fn_deductions': all_fn_deductions,
                        'deductions_sum':deductions_sum,     
                    }  
                
            elif modeofpayment=='BANK DEPOSIT':
                all_bdeposits = all_payments_filtered
                deposits_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_bdeposits': all_bdeposits,
                        'deposits_sum':deposits_sum,   
                    }  
            else:
                all_cash = all_payments_filtered
                cash_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_cash':all_cash,
                        'cash_sum': cash_sum,  
                    }  
            
            return render(request, 'transactions_payments.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')

            all_payments_filtered = Payment.objects.prefetch_related('owner','loanref').filter(loanref__loan_type=loantype).all()
            
            all_fn_deductions = all_payments_filtered.filter(mode='PAYROLL DEDUCTION')
            deductions_sum = all_fn_deductions.aggregate(sum=Sum('amount'))['sum']
           
            all_bdeposits = all_payments_filtered.filter(mode='BANK DEPOSIT')
            deposits_sum = all_bdeposits.aggregate(sum=Sum('amount'))['sum']
            
            all_cash = all_payments_filtered.filter(mode='CASH')
            cash_sum = all_cash.aggregate(sum=Sum('amount'))['sum']
            
            
            context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype, 
                        'all_payments_filtered': all_payments_filtered,
                        'all_fn_deductions': all_fn_deductions,
                        'deductions_sum':deductions_sum,
                        'all_bdeposits': all_bdeposits,
                        'deposits_sum':deposits_sum,
                        'all_cash':all_cash,
                        'cash_sum': cash_sum,
                        
                    }  
            
            return render(request, 'transactions_payments.html', context)
        
        elif request.POST.get('modeofpayment'): 
            
            modeofpayment = request.POST.get('modeofpayment')

            all_payments_filtered = Payment.objects.prefetch_related('owner','loanref').filter(mode = modeofpayment).all()
            if modeofpayment=='PAYROLL DEDUCTION':
                all_fn_deductions = all_payments_filtered
                deductions_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_fn_deductions': all_fn_deductions,
                        'deductions_sum':deductions_sum,     
                    }  
                
            elif modeofpayment=='BANK DEPOSIT':
                all_bdeposits = all_payments_filtered
                deposits_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_bdeposits': all_bdeposits,
                        'deposits_sum':deposits_sum,   
                    }  
            else:
                all_cash = all_payments_filtered
                cash_sum = all_payments_filtered.aggregate(sum=Sum('amount'))['sum']
                context = {
                        'nav' : 'transactions_payments', 'filter': 'on', 'referrer': referrer,
                        'modeofpayment': modeofpayment,
                        'all_payments_filtered': all_payments_filtered,
                        'all_cash':all_cash,
                        'cash_sum': cash_sum,  
                    }  
            
            return render(request, 'transactions_payments.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('transactions_payments')

    all_payments_filtered = Payment.objects.order_by('-date')
    all_fn_deductions = Payment.objects.filter(mode="PAYMENT").all()
    deductions_sum = all_fn_deductions.aggregate(sum=Sum('amount'))['sum']
    all_bdeposits = Payment.objects.filter(mode="DEFAULT").all()
    deposits_sum = all_bdeposits.aggregate(sum=Sum('amount'))['sum']
    all_cash = Payment.objects.filter(mode="OTHER").all()
    cash_sum = all_cash.aggregate(sum=Sum('amount'))['sum']
    
    
    context = {
                'nav' : 'transactions_payments',
                'all_payments_filtered': all_payments_filtered,
                'all_fn_deductions': all_fn_deductions,
                'deductions_sum':deductions_sum,
                'all_bdeposits': all_bdeposits,
                'deposits_sum':deposits_sum,
                'all_cash':all_cash,
                'cash_sum': cash_sum,
                
            }  
    
    return render(request, 'transactions_payments.html', context)

@admin_check
def transactions_defaults(request):

    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype'):
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
                return redirect('transactions_defaults')

            all_defaults_filtered = Statement.objects.prefetch_related('owner','loanref').filter(type='DEFAULT', loanref__loan_type=loantype, date__gte = start_date, date__lte = end_date).all()
            
            defaults_amount = all_defaults_filtered.aggregate(sum=Sum('default_amount'))['sum']
            defaults_interest = all_defaults_filtered.aggregate(sum=Sum('interest_on_default'))['sum']
            defaults_interest_collected = all_defaults_filtered.aggregate(sum=Sum('default_interest_collected'))['sum']
            
            context = {
                        'nav' : 'transactions_defaults', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 'loantype': loantype,
                        'all_defaults_filtered': all_defaults_filtered,
                        'defaults_amount': defaults_amount,
                        'defaults_interest':defaults_interest,
                        'defaults_interest_collected': defaults_interest_collected,                        
                    }  
            
            return render(request, 'transactions_defaults.html', context)
        
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
                return redirect('transactions_payments')

            all_defaults_filtered = Statement.objects.prefetch_related('owner','loanref').filter(type='DEFAULT', date__gte = start_date, date__lte = end_date).all()
            
            defaults_amount = all_defaults_filtered.aggregate(sum=Sum('default_amount'))['sum']
            defaults_interest = all_defaults_filtered.aggregate(sum=Sum('interest_on_default'))['sum']
            defaults_interest_collected = all_defaults_filtered.aggregate(sum=Sum('default_interest_collected'))['sum']
            
            context = {
                        'nav' : 'transactions_defaults', 'filter': 'on', 'referrer': referrer,
                        'startdate': start_date, 'enddate': end_date, 
                        'all_defaults_filtered': all_defaults_filtered,
                        'defaults_amount': defaults_amount,
                        'defaults_interest':defaults_interest,
                        'defaults_interest_collected': defaults_interest_collected,                        
                    }  
            
            return render(request, 'transactions_defaults.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')

            all_defaults_filtered = Statement.objects.prefetch_related('owner','loanref').filter(type='DEFAULT', loanref__loan_type=loantype).all()
            
            defaults_amount = all_defaults_filtered.aggregate(sum=Sum('default_amount'))['sum']
            defaults_interest = all_defaults_filtered.aggregate(sum=Sum('interest_on_default'))['sum']
            defaults_interest_collected = all_defaults_filtered.aggregate(sum=Sum('default_interest_collected'))['sum']
            
            context = {
                        'nav' : 'transactions_defaults', 'filter': 'on', 'referrer': referrer,
                        'loantype': loantype,
                        'all_defaults_filtered': all_defaults_filtered,
                        'defaults_amount': defaults_amount,
                        'defaults_interest':defaults_interest,
                        'defaults_interest_collected': defaults_interest_collected,                        
                    }  
            
            return render(request, 'transactions_defaults.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('transactions_defaults')

    all_defaults_filtered = Statement.objects.prefetch_related('owner','loanref').filter(type='DEFAULT').all()
            
    defaults_amount = all_defaults_filtered.aggregate(sum=Sum('default_amount'))['sum']
    defaults_interest = all_defaults_filtered.aggregate(sum=Sum('interest_on_default'))['sum']
    defaults_interest_collected = all_defaults_filtered.aggregate(sum=Sum('default_interest_collected'))['sum']
    
    context = {
                'nav' : 'transactions_defaults', 
                'all_defaults_filtered': all_defaults_filtered,
                'defaults_amount': defaults_amount,
                'defaults_interest':defaults_interest,
                'defaults_interest_collected': defaults_interest_collected,                        
            }  
    
    return render(request, 'transactions_defaults.html', context)


@admin_check
def transactions_expected(request):

    domain = settings.DOMAIN
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    today = datetime.date.today()
    
    if request.method=='POST':
        
        if request.POST.get('loantype') and request.POST.get('period'):
            
            loantype = request.POST.get('loantype')
            period = request.POST.get('period')
            
            today = datetime.date.today()
            nextseven = today + datetime.timedelta(days=7)
            nextfourteen = today + datetime.timedelta(days=14)
            nextthirty = today + datetime.timedelta(days=30)
            
            if period == 'seven':
                
                if loantype == "PERSONAL":
                    payments_due_today = Loan.objects.prefetch_related('owner').filter(type='PERSONAL', next_payment_date__gte=today, next_payment_date__lte=nextseven).all()
                    payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                    
                    context = { 
                        'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                        
                        'type': 'personal',
                        'period': 'NEXT 7 DAYS',
                        'payments_due_today': payments_due_today,
                        'payments_total': payments_total, 
                        'personal_payments_due_today': payments_due_today,
                        'personal_payments_total': payments_total,
                        
                        }
                    
                    return render(request, 'transactions_expected.html', context)
                    
                elif loantype == 'SME':
                    payments_due_today = Loan.objects.prefetch_related('owner').filter(type='SME',next_payment_date__gte=today, next_payment_date__lte=nextseven).all()
                    payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                    
                    context = { 
                        'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                        'type': 'sme',
                        'period': 'NEXT 7 DAYS',
                        'payments_due_today': payments_due_today,
                        'payments_total': payments_total, 
                        
                        'sme_payments_due_today': payments_due_today,
                        'sme_payments_total': payments_total,
                        }
                    return render(request, 'transactions_expected.html', context)
            
            elif period == 'fourteen':
                
                if loantype == "PERSONAL":
                    payments_due_today = Loan.objects.prefetch_related('owner').filter(type='PERSONAL', next_payment_date__gte=today, next_payment_date__lte=nextfourteen).all()
                    payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                    
                    context = { 
                        'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                        'type': 'personal',
                        'period': 'NEXT 14 DAYS',
                        'payments_due_today': payments_due_today,
                        'payments_total': payments_total, 
                        'personal_payments_due_today': payments_due_today,
                        'personal_payments_total': payments_total,
                        
                        }
                    
                    return render(request, 'transactions_expected.html', context)
                    
                elif loantype == 'SME':
                    payments_due_today = Loan.objects.prefetch_related('owner').filter(type='SME',next_payment_date__gte=today, next_payment_date__lte=nextfourteen).all()
                    payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                    
                    context = { 
                        'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                        'type': 'sme',
                        'period': 'NEXT 14 DAYS',
                        'payments_due_today': payments_due_today,
                        'payments_total': payments_total, 
                        
                        'sme_payments_due_today': payments_due_today,
                        'sme_payments_total': payments_total,
                        }
                    return render(request, 'transactions_expected.html', context)
            
            elif period == 'thirty':
                
                if loantype == "PERSONAL":
                    payments_due_today = Loan.objects.prefetch_related('owner').filter(type='PERSONAL', next_payment_date__gte=today, next_payment_date__lte=nextthirty).all()
                    payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                    
                    context = { 
                        'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                        'type': 'personal',
                        'period': 'NEXT 30 DAYS',
                        'payments_due_today': payments_due_today,
                        'payments_total': payments_total, 
                        'personal_payments_due_today': payments_due_today,
                        'personal_payments_total': payments_total,
                        
                        }
                    
                    return render(request, 'transactions_expected.html', context)
                    
                elif loantype == 'SME':
                    payments_due_today = Loan.objects.prefetch_related('owner').filter(type='SME',next_payment_date__gte=today, next_payment_date__lte=nextthirty).all()
                    payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                    
                    context = { 
                        'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                        'type': 'sme',
                        'period': 'NEXT 30 DAYS',
                        'payments_due_today': payments_due_today,
                        'payments_total': payments_total, 
                        
                        'sme_payments_due_today': payments_due_today,
                        'sme_payments_total': payments_total,
                        }
                    return render(request, 'transactions_expected.html', context)
            
        elif request.POST.get('loantype'):
            
            loantype = request.POST.get('loantype')
            
            if loantype == "PERSONAL":
                payments_due_today = Loan.objects.prefetch_related('owner').filter(next_payment_date=today, type='PERSONAL').all()
                payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                context = { 
                    'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                    'type': 'personal',
                    'period': 'TODAY',
                    'payments_due_today': payments_due_today,
                    'payments_total': payments_total, 
                    'personal_payments_due_today': payments_due_today,
                    'personal_payments_total': payments_total,
                    
                    }
                
                return render(request, 'transactions_expected.html', context)
                
            elif loantype == 'SME':
                payments_due_today = Loan.objects.prefetch_related('owner').filter(next_payment_date=today, type='SME').all()
                payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                context = { 
                    'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                    'type': 'sme',
                    'period': 'TODAY',
                    'payments_due_today': payments_due_today,
                    'payments_total': payments_total, 
                    
                    'sme_payments_due_today': payments_due_today,
                    'sme_payments_total': payments_total,
                    }
                return render(request, 'transactions_expected.html', context)
        
        elif request.POST.get('period'):
            
            period = request.POST.get('period')
            
            today = datetime.date.today()
            nextseven = today + datetime.timedelta(days=7)
            nextfourteen = today + datetime.timedelta(days=14)
            nextthirty = today + datetime.timedelta(days=30)
            
            if period == 'seven':
                
                payments_due_today = Loan.objects.prefetch_related('owner').filter(next_payment_date__gte=today, next_payment_date__lte=nextseven).all()
                payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                personal_payments_due_today = Loan.objects.prefetch_related('owner').filter(loan_type="PERSONAL",next_payment_date__gte=today, next_payment_date__lte=nextseven).all()
                personal_payments_total = personal_payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                sme_payments_due_today = Loan.objects.prefetch_related('owner').filter(loan_type="SME",next_payment_date__gte=today, next_payment_date__lte=nextseven).all()
                sme_payments_total = sme_payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                context = { 
                        'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                        'period': 'NEXT 7 DAYS',
                        'payments_due_today': payments_due_today,
                        'payments_total': payments_total, 
                        'personal_payments_due_today': personal_payments_due_today,
                        'personal_payments_total': personal_payments_total,
                        'sme_payments_due_today': sme_payments_due_today,
                        'sme_payments_total': sme_payments_total,
                        }      
                
                return render(request, 'transactions_expected.html', context)
            
            elif period == 'fourteen':
               
                payments_due_today = Loan.objects.prefetch_related('owner').filter(next_payment_date__gte=today, next_payment_date__lte=nextfourteen).all()
                payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                personal_payments_due_today = Loan.objects.prefetch_related('owner').filter(loan_type="PERSONAL",next_payment_date__gte=today, next_payment_date__lte=nextfourteen).all()
                personal_payments_total = personal_payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                sme_payments_due_today = Loan.objects.prefetch_related('owner').filter(loan_type="SME",next_payment_date__gte=today, next_payment_date__lte=nextfourteen).all()
                sme_payments_total = sme_payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                context = { 
                        'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                        'period': 'NEXT 14 DAYS',
                        'payments_due_today': payments_due_today,
                        'payments_total': payments_total, 
                        'personal_payments_due_today': personal_payments_due_today,
                        'personal_payments_total': personal_payments_total,
                        'sme_payments_due_today': sme_payments_due_today,
                        'sme_payments_total': sme_payments_total,
                        }      
                
                return render(request, 'transactions_expected.html', context)
            
            elif period == 'thirty':
              
                payments_due_today = Loan.objects.prefetch_related('owner').filter(next_payment_date__gte=today, next_payment_date__lte=nextthirty).all()
                payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                personal_payments_due_today = Loan.objects.prefetch_related('owner').filter(loan_type="PERSONAL",next_payment_date__gte=today, next_payment_date__lte=nextthirty).all()
                personal_payments_total = personal_payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                sme_payments_due_today = Loan.objects.prefetch_related('owner').filter(loan_type="SME",next_payment_date__gte=today, next_payment_date__lte=nextthirty).all()
                sme_payments_total = sme_payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
                
                context = { 
                        'nav': 'transactions_expected', 'filter': 'on', 'domain':domain,
                        'period': 'NEXT 30 DAYS',
                        'payments_due_today': payments_due_today,
                        'payments_total': payments_total, 
                        'personal_payments_due_today': personal_payments_due_today,
                        'personal_payments_total': personal_payments_total,
                        'sme_payments_due_today': sme_payments_due_today,
                        'sme_payments_total': sme_payments_total,
                        }      
                return render(request, 'transactions_expected.html', context)
            
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('transactions_expected')
            
    payments_due_today = Loan.objects.prefetch_related('owner').filter(next_payment_date = today).all()
    payments_total = payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
    
    personal_payments_due_today = Loan.objects.prefetch_related('owner').filter(next_payment_date = today, loan_type="PERSONAL").all()
    personal_payments_total = personal_payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
    
    sme_payments_due_today = Loan.objects.prefetch_related('owner').filter(next_payment_date = today, loan_type="SME").all()
    sme_payments_total = sme_payments_due_today.aggregate(sum=Sum('repayment_amount'))['sum']
    
    context = { 
               'nav': 'transactions_expected', 
               'period': 'TODAY',
               'payments_due_today': payments_due_today,
               'payments_total': payments_total, 
               'personal_payments_due_today': personal_payments_due_today,
               'personal_payments_total': personal_payments_total,
               'sme_payments_due_today': sme_payments_due_today,
               'sme_payments_total': sme_payments_total,
               }
   
    return render(request, 'transactions_expected.html', context)
