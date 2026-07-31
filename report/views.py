import datetime
from django.shortcuts import render, redirect

from django.contrib import messages

from accounts.models import UserProfile
from loan.models import Loan, Statement

from django.db.models import Sum

# Create your views here.

def view_reports(request):
    return render(request, 'view_reports.html', {'nav':'reports'})

def report_overview(request):

    #clients logic
    clients = UserProfile.objects.all()
    loans = Loan.objects.all()

    total_registered = clients.count()
    active_clients = clients.filter(activation=1)
    active_clients_count = active_clients.count()
    inactive_clients_count = total_registered-active_clients_count
    active_clients_with_loan = active_clients.filter(has_loan = 1).count()
    inactive_clients_without_loan = active_clients_count - active_clients_with_loan
    active_percent = active_clients_with_loan / active_clients_count * 100
    inactive_percent = inactive_clients_without_loan / active_clients_count * 100               

    #loans logic

    #repayments
    loans = Loan.objects.select_related('owner').filter(category='FUNDED', funded_category='ACTIVE')
    repayments = loans.aggregate(sum=Sum('repayment_amount'))['sum']
    pri_sec_rpay = loans.filter(owner__sector='PRIVATE').aggregate(sum=Sum('repayment_amount'))['sum']
    pub_sec_rpay = loans.filter(owner__sector='PUBLIC').aggregate(sum=Sum('repayment_amount'))['sum']

    if repayments is not None:
        if pri_sec_rpay is not None:
            pri_sec_percent = pri_sec_rpay/repayments*100
        else:
            pri_sec_percent = 0
        if pub_sec_rpay is not None:
            pub_sec_percent = pub_sec_rpay/repayments*100
        else:
            pub_sec_percent = 0
    else:
        repayments = 0
        pri_sec_rpay = 0
        pub_sec_rpay = 0
        pri_sec_percent = 0
        pub_sec_percent = 0 

    #loans totals
    loans_total = loans.aggregate(sum=Sum('total_outstanding'))['sum']
    active_loans_total = loans.filter(funded_category='ACTIVE').aggregate(sum=Sum('total_outstanding'))['sum']
    recovery_loans_total = loans.exclude(funded_category='ACTIVE').aggregate(sum=Sum('total_outstanding'))['sum']
    #system balance 
    loans_capital = loans.aggregate(sum=Sum('amount'))['sum']

    #INTEREST BREAKUP
    default_interest_receivable = loans.aggregate(sum=Sum('default_interest_receivable'))['sum']
    

    if loans_total is not None:
        if active_loans_total is not None:
            active_loans_total_percent = active_loans_total/loans_total*100
        else:
            active_loans_total_percent = 0
        if recovery_loans_total is not None:
            recovery_loans_total_percent = recovery_loans_total/loans_total*100
        else:
            recovery_loans_total_percent = 0
        #system balance 
        if loans_capital is not None:
            interest_generated = loans_total - loans_capital
            loans_capital_percent = loans_capital/loans_total*100
            interest_generated_percent = 100-loans_capital_percent

            #interest
            if default_interest_receivable is not None:
                generated_interest = loans_total - loans_capital - default_interest_receivable
            else:
                generated_interest = loans_total - loans_capital - 0
        else:
            interest_generated = 0
            loans_capital_percent = 0
            interest_generated_percent = 0
            generated_interest = 0
        
    else:
        loans_total = 0
        active_loans_total = 0
        recovery_loans_total = 0
        active_loans_total_percent = 0
        recovery_loans_total_percent = 0
        
        loans_capital = 0
        interest_generated = 0
        loans_capital_percent = 0
        interest_generated_percent = 0

        default_interest_receivable = 0
        generated_interest = 0


    #for graphs 
    #for new dashboard
    loans_pending_funding = Loan.objects.filter(category='PENDING', status='APPROVED')
    loans_pending = Loan.objects.filter(category='PENDING')
    pending_loans = loans_pending_funding[:3]
    pending_loans_count = loans_pending_funding.count()
    awaiting_tc_loans = loans_pending.filter(status='AWAITING T&C').count()
    under_review_loans = loans_pending.filter(status='UNDER REVIEW').count()
    on_hold_loans = loans_pending.filter(status='ON HOLD').count()
    approved_loans = loans_pending.filter(status='APPROVED').count()
   
  

    atcllabel = f'Awaiting T&C'
    urllabel = f'Under Review'
    ohllabel = f'On Hold'
    allabel = f'Approved'
 
    
    

    pendingloanlabels =[atcllabel,
                urllabel,
                ohllabel,
                allabel,
         
                ]

    pendingloansdata = [awaiting_tc_loans,
            under_review_loans,
            on_hold_loans,
            approved_loans,
      
            ]

    #funded loans breakup
    fundedloans = Loan.objects.filter(category='FUNDED')
    arfloans = fundedloans.filter(funded_category='ACTIVE', status="RUNNING").count()
    adfloans = fundedloans.filter(funded_category='ACTIVE', status="DEFAULTED").count()
    rfloans = fundedloans.filter(funded_category='RECOVERY').count()
    bfloans = fundedloans.filter(funded_category='BAD').count()

    arfloansl = f'Running'
    adfloansl = f'Defaulted'
    rfloansl = f'In Recovery'
    bfloansl = f'Bad'
    
    arfloanslabels =[arfloansl,
                adfloansl,
                rfloansl,
                bfloansl,
                ]

    arfloansdata =[arfloans,
                adfloans,
                rfloans,
                bfloans,
                ]
    

    


    
    

    context = {

        'nav' : 'reports',
        'total_registered' : total_registered,
        'active_clients_count' : active_clients_count,
        'inactive_clients_count' : inactive_clients_count,
        'active_clients_with_loan' : active_clients_with_loan,
        'inactive_clients_without_loan' : inactive_clients_without_loan,
        'active_percent' : active_percent,
        'inactive_percent' : inactive_percent,

        'repayments':repayments,
        'pri_sec_rpay':pri_sec_rpay,
        'pub_sec_rpay':pub_sec_rpay,
        'pri_sec_percent':pri_sec_percent,
        'pub_sec_percent':pub_sec_percent,

        'loans_total': loans_total,
        'active_loans_total' : active_loans_total,
        'recovery_loans_total': recovery_loans_total,
        'active_loans_total_percent': active_loans_total_percent,
        'recovery_loans_total_percent': recovery_loans_total_percent,

        'loans_capital': loans_capital,
        'interest_generated': interest_generated,
        'loans_capital_percent': loans_capital_percent,
        'interest_generated_percent': interest_generated_percent,

        #for graphs

        'pending_loans': pending_loans,
        'pendingloanlabels': pendingloanlabels,
        'pendingloansdata' : pendingloansdata,

        'arfloanslabels': arfloanslabels,
        'arfloansdata' : arfloansdata,
        'pending_loans_count': pending_loans_count,
     
        'default_interest_receivable': default_interest_receivable,
        'generated_interest': generated_interest,

  

    }

    return render(request, 'report_overview.html', context )



def monthly_collections_report(request):

    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            
            start_date = start_date_entry
            end_date = end_date_entry
        
        else:
            messages.error(request, 'No date interval selected.')
            return redirect('monthly_collections_report')
        
        strip_start_date = start_date.split('-')
        strip_end_date = end_date.split('-')

        date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
        date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
        
        if date_start_date > date_end_date:
            messages.error(request, 'End date must be after Start date!')
            return redirect('monthly_collections_report')
            
        statements = Statement.objects.prefetch_related('loanref','owner').filter(date__gte=start_date, date__lte=end_date).all()
        
        userslist = [(e["loanref__ref"], e["loanref__owner__first_name"], e["loanref__owner__last_name"], e["loanref__total_outstanding"], e["loanref__total_arrears"], e["loanref__default_interest_receivable"], 
                    e["loanref__days_in_default"], e["loan"], e["interest"], e['dic']) for e in statements
                    .values("loanref__ref","loanref__owner__first_name", "loanref__owner__last_name", "loanref__total_outstanding", "loanref__total_arrears", "loanref__default_interest_receivable", "loanref__days_in_default")
                    .annotate(loan=Sum("loan_amount"), interest=Sum('interest'), dic=Sum('default_interest_collected'))]
        
        sum_debits = statements.aggregate(Sum('debit'))['debit__sum']
        sum_credits = statements.aggregate(Sum('credit'))['credit__sum']
        sum_defaults = statements.aggregate(Sum('default_amount'))
        sum_default_interests = statements.aggregate(Sum('interest_on_default'))['interest_on_default__sum']
        sum_loan_amount = statements.aggregate(Sum('loan_amount'))['loan_amount__sum']
        
        sum_interest = statements.aggregate(Sum('interest'))
        
        sum_arrears = 0
        sum_balance = 0 
        
        for userdata in userslist:
            
            sum_balance += userdata[3]
            sum_arrears += userdata[4]
        
        count = 0
        itemcount = len(userslist)
        context = {
            'nav': 'collections_report',
            'date_start_date': date_start_date,
            'date_end_date': date_end_date,
            'count': count,
            'itemcount': itemcount,
            'userslist': userslist,
            'statements': statements,
            'sum_debits': sum_debits,
            'sum_credits': sum_credits,
            'sum_defaults': sum_defaults,
            'sum_default_interests': sum_default_interests,
            'sum_loan_amount': sum_loan_amount,
         
            'sum_interest' : sum_interest,
            'sum_arrears': sum_arrears,
            'sum_balance': sum_balance,
        }
         
    else:
        
        date = datetime.date.today()
        year = date.year
        month = date.month
        start_date = f'{year}-{month}-1'

        import calendar
        last_day = calendar.monthrange(year, month)[1]
        end_date = f'{year}-{month}-{last_day}'
    
        strip_start_date = start_date.split('-')
        strip_end_date = end_date.split('-')

        date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
        date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
        
        if date_start_date > date_end_date:
            messages.error(request, 'End date must be after Start date!', extra_tags='danger')
            return redirect('monthly_collections_report')
            
        statements = Statement.objects.prefetch_related('loanref','owner').filter(date__gte=start_date, date__lte=end_date).all()
        
        userslist = [(e["loanref__ref"], e["loanref__owner__first_name"], e["loanref__owner__last_name"], e["loanref__total_outstanding"], e["loanref__total_arrears"], e["loanref__default_interest_receivable"], 
                    e["loanref__days_in_default"], e["loan"], e["interest"], e['dic']) for e in statements
                    .values("loanref__ref","loanref__owner__first_name", "loanref__owner__last_name", "loanref__total_outstanding", "loanref__total_arrears", "loanref__default_interest_receivable", "loanref__days_in_default")
                    .annotate(loan=Sum("loan_amount"), interest=Sum('interest'), dic=Sum('default_interest_collected'))]
        
        sum_debits = statements.aggregate(Sum('debit'))['debit__sum']
        sum_credits = statements.aggregate(Sum('credit'))['credit__sum']
        sum_defaults = statements.aggregate(Sum('default_amount'))
        sum_default_interests = statements.aggregate(Sum('interest_on_default'))['interest_on_default__sum']
        sum_loan_amount = statements.aggregate(Sum('loan_amount'))['loan_amount__sum']
        
        sum_interest = statements.aggregate(Sum('interest'))
        
        sum_arrears = 0
        sum_balance = 0 
        
        for userdata in userslist:
            
            sum_balance += userdata[3]
            sum_arrears += userdata[4]
        
        count = 0
        itemcount = len(userslist)
        context = {
            'nav': 'collections_report',
            'date': date,
            'date_start_date': date_start_date,
            'date_end_date': date_end_date,
            'count': count,
            'itemcount': itemcount,
            'userslist': userslist,
            'statements': statements,
            'sum_debits': sum_debits,
            'sum_credits': sum_credits,
            'sum_defaults': sum_defaults,
            'sum_default_interests': sum_default_interests,
            'sum_loan_amount': sum_loan_amount,
           
            'sum_interest' : sum_interest,
            'sum_arrears': sum_arrears,
            'sum_balance': sum_balance,
        }
 
    return render(request, 'reports_monthly_collections.html', context)

def cash_flow(request):
    '''
    total_principal_loan_repaid = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    total_interest_repaid = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    total_default_interest_paid = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #total_default_interest_repaid = 
    total_repaid = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)
    
    advance_payment_surplus = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0.00)
    
    principal_loan_receivable = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0)  #amount_remaining = 
    ordinary_interest_receivable = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #oridinary_interest_receivable = 
    default_interest_receivable = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #default_interest_receivable = 
    total_outstanding = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, default=0) #total_receivable_amount 
    '''

    # Cash flow calculations
    loans = Loan.objects.filter(category='FUNDED')
    total_principal_loan_repaid = loans.aggregate(sum=Sum('principal_loan_paid'))['sum'] or 0
    total_interest_repaid = loans.aggregate(sum=Sum('interest_paid'))['sum'] or 0
    total_default_interest_paid = loans.aggregate(sum=Sum('default_interest_paid'))['sum'] or 0
    total_repaid = total_principal_loan_repaid + total_interest_repaid + total_default_interest_paid

    total_cash_inflow = total_repaid
    total_cash_outflow = loans.aggregate(sum=Sum('amount'))['sum'] or 0
    net_cash_flow = total_cash_inflow - total_cash_outflow

    # Account equations
    principal_loan_receivable = loans.aggregate(sum=Sum('principal_loan_receivable'))['sum'] or 0
    ordinary_interest_receivable = loans.aggregate(sum=Sum('ordinary_interest_receivable'))['sum'] or 0
    default_interest_receivable = loans.aggregate(sum=Sum('default_interest_receivable'))['sum'] or 0
    total_assets = principal_loan_receivable + ordinary_interest_receivable + default_interest_receivable

    total_liabilities = loans.aggregate(sum=Sum('advance_payment_surplus'))['sum'] or 0
    equity = total_assets - total_liabilities

    context = {
        'nav': 'cash_flow',
        'total_principal_loan_repaid':total_principal_loan_repaid,
        'total_interest_repaid': total_interest_repaid,
        'total_default_interest_paid': total_default_interest_paid,
        'total_cash_inflow': total_cash_inflow,
        'total_cash_outflow': total_cash_outflow,
        'net_cash_flow': net_cash_flow,

        'principal_loan_receivable': principal_loan_receivable,
        'ordinary_interest_receivable': ordinary_interest_receivable,
        'default_interest_receivable' : default_interest_receivable,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'equity': equity,
    }

    return render(request, 'cash_flow.html', context)


def dcc_report(request):
    """DCC Credit Bureau report: month selector, running cost total from the
    bureau's billing summary, and the local pay-per-view log (which staff
    member unlocked which client, when, and until when). Only reachable when
    DCC is enabled in Settings -> DCC."""
    from dcc.functions import dcc_enabled, get_billing_summary
    from dcc.models import DccViewLog

    if not dcc_enabled():
        messages.error(request, 'DCC is disabled in Settings → DCC, so there is no DCC report.', extra_tags='info')
        return redirect('reports')

    today = datetime.date.today()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except (TypeError, ValueError):
        year, month = today.year, today.month

    billing = get_billing_summary(year, month)

    view_logs = (DccViewLog.objects
                 .select_related('client', 'viewed_by')
                 .filter(unlocked_at__year=year, unlocked_at__month=month)
                 .order_by('-unlocked_at'))
    local_cost = view_logs.aggregate(sum=Sum('cost'))['sum'] or 0

    context = {
        'nav': 'reports',
        'billing': billing,
        'view_logs': view_logs[:300],
        'views_count': view_logs.count(),
        'local_cost': local_cost,
        'year': year,
        'month': month,
        'months': [(m, datetime.date(2000, m, 1).strftime('%B')) for m in range(1, 13)],
        'years': list(range(today.year - 3, today.year + 1)),
    }
    return render(request, 'dcc_report.html', context)