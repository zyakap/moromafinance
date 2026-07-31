import datetime
import re
import requests
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db.models import Sum, Q
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.views.generic.base import View
from wkhtmltopdf.views import PDFTemplateResponse
from accounts.models import User, UserProfile, StaffProfile, SMEProfile
from accounts.functions import admin_check, get_field_settings
from admin1.models import AdminSettings, Location
from admin1.forms import AdminSettingsForm
from loan.models import Loan, LoanFile, Statement, Payment, PaymentUploads
from loan.forms import PaymentForm
from dcc.functions import check_client_in_dcc, credit_tab_context, get_loans_for_client, get_transactions_for_client
from dcc.serializers import LoanSerializer, StatementSerializer
sender = settings.DEFAULT_SENDER_EMAIL
domain = settings.DOMAIN

################ 
# START OF CODE
################

@admin_check
def clients(request):
    
    #### DEFINE CLIENT PENDING CKECK REQUIREMENT HERE:
    
    pending_users = UserProfile.objects.exclude(activation=1, requirement_check='COMPLETED')
    
    for user in pending_users:
        if user.repayment_limit != 0:
            user.requirement_check == 'COMPLETED'
            
    
    #### DEFINE CLIENT PENDING: END
    
    
    loans = Loan.objects.prefetch_related('owner').filter(owner__user__staff=0)
    
    clients = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0).all()
    
    clients_all = clients
    clients_withloan = clients.filter(number_of_loans__gt=0).all()
    clients_pending = UserProfile.objects.select_related('user').filter(activation=0, user__staff=0).all()
    clients_flagged = clients.filter(user__dcc_flagged=1).all()
    clients_suspended = clients.filter(user__suspended=1).all()
    
    clients_with_default = clients.filter(user__defaulted=1).all()
    clients_in_recovery = clients.filter(in_recovery=1).all()
    
    
    public_ca = clients.filter(sector='PUBLIC').all()
    public_cwl = clients.filter(number_of_loans__gt=0, sector='PUBLIC').all()
    public_cwd = clients.filter(user__defaulted=1, sector='PUBLIC').all()
    public_cir = clients.filter(in_recovery=1, sector='PUBLIC').all()
    
    private_ca = clients.filter(sector='PRIVATE').all()
    private_cwl = clients.filter(number_of_loans__gt=0, sector='PRIVATE').all()
    private_cwd = clients.filter(user__defaulted=1, sector='PRIVATE').all()
    private_cir = clients.filter(in_recovery=1, sector='PRIVATE').all()
    
    married_clients = clients.filter(marital_status='MARRIED').all()
    single_clients = clients.filter(marital_status='SINGLE').all()
    other_marital_clients = clients.exclude(marital_status='SINGLE').exclude(marital_status='MARRIED').all()
    
    male_clients = clients.filter(gender='MALE').all()
    female_clients = clients.filter(gender='FEMALE').all()
    working_clients = clients.exclude(employer='NA',job_title='NA').all()
    not_working_clients = clients.filter(employer='NA',job_title='NA').all()
    with_sme_clients = clients.filter(has_sme=1).all()
    without_sme_clients = clients.filter(has_sme=0).all()

    
    if clients.count() != 0:
        married = round((married_clients.count()/clients.count())*100.0, 1)
        single = round((single_clients.count()/clients.count())*100.0, 1)
        other_marital = round((other_marital_clients.count()/clients.count())*100.0, 1)
        male = round((male_clients.count()/clients.count())*100.0, 1)
        female = round((female_clients.count()/clients.count())*100.0, 1)
        working = round((working_clients.count()/clients.count())*100.0, 1)
        not_working = round((not_working_clients.count()/clients.count())*100.0, 1)
        with_sme = round((with_sme_clients.count()/clients.count())*100.0, 1)
        without_sme = round((without_sme_clients.count()/clients.count())*100.0, 1)
    else:
        married = 0
        single = 0
        other_marital = 0
        male = 0
        female = 0
        working = 0
        not_working = 0
        with_sme = 0
        without_sme = 0
    
    today = datetime.date.today() 
    
    et18 = today - datetime.timedelta(days=(18*365))
    tf24 = today - datetime.timedelta(days=(365*24))
    tf25 = today - datetime.timedelta(days=(365*24)) - datetime.timedelta(days=1)
    t30 = today - datetime.timedelta(days=(365*30))
    to31 = today - datetime.timedelta(days=(365*30)) - datetime.timedelta(days=1)
    f40 = today - datetime.timedelta(days=(365*40))
    fo41 = today - datetime.timedelta(days=(365*40)) - datetime.timedelta(days=1)
    f50 = today - datetime.timedelta(days=(365*50))
    fo51 = today - datetime.timedelta(days=(365*50)) - datetime.timedelta(days=1)
    h100 = today - datetime.timedelta(days=(365*99))
    
    clients_1824 = clients.filter(date_of_birth__gte=tf24, date_of_birth__lte=et18,)
    clients_2530 = clients.filter(date_of_birth__gte=t30, date_of_birth__lte=tf25,)
    clients_3140 = clients.filter(date_of_birth__gte=f40, date_of_birth__lte=to31,)
    clients_4150 = clients.filter(date_of_birth__gte=f50, date_of_birth__lte=fo41,)
    clients_51100 = clients.filter(date_of_birth__lte=fo51)
    
    if clients.count() != 0:
        clients_1824P = round((clients_1824.count()/clients.count())*100.0, 1)
        clients_2530P = round((clients_2530.count()/clients.count())*100.0, 1)
        clients_3140P = round((clients_3140.count()/clients.count())*100.0, 1)
        clients_4150P = round((clients_4150.count()/clients.count())*100.0, 1)
        clients_51100P = round((clients_51100.count()/clients.count())*100.0, 1) 
    else:
        clients_1824P = 0
        clients_2530P = 0
        clients_3140P = 0
        clients_4150P = 0
        clients_51100P = 0 
    
    clients_1824M = clients_1824.filter(gender="MALE")
    clients_2530M = clients_2530.filter(gender="MALE")
    clients_3140M = clients_3140.filter(gender="MALE")
    clients_4150M = clients_4150.filter(gender="MALE")
    clients_51100M = clients_51100.filter(gender="MALE")
    
    clients_1824FM = clients_1824.filter(gender="FEMALE")
    clients_2530FM = clients_2530.filter(gender="FEMALE")
    clients_3140FM = clients_3140.filter(gender="FEMALE")
    clients_4150FM = clients_4150.filter(gender="FEMALE")
    clients_51100FM = clients_51100.filter(gender="FEMALE")
    
    if clients.count() != 0:
        publicsectorpercent = round((public_ca.count()/clients.count())*100.0, 1) 
        privatesectorpercent = round((private_ca.count()/clients.count())*100.0, 1)
        nasector = 100.0 - publicsectorpercent - privatesectorpercent
    else:
        publicsectorpercent = 0 
        privatesectorpercent = 0
        nasector = 0
    
    userprovinces = clients.exclude(province='Not Specified')
    provinces = {}
    
    for user in userprovinces:
        province = user.province
        if province in provinces:
            provinces[province] += 1
        else:
            provinces[province] = 1
   
    province_label = []
    province_data = []
    province_data_count = len(provinces)
    
    for k,v in provinces.items():
        province_label.append(k)
        province_data.append(v)

    resuserprovinces = clients.exclude(residential_province='Not Specified')
    resprovinces = {}
    
    for user in resuserprovinces:
        resprovince = user.residential_province
        if resprovince in resprovinces:
            resprovinces[resprovince] += 1
        else:
            resprovinces[resprovince] = 1
   
    resprovince_label = []
    resprovince_data = []
    resprovince_data_count = len(resprovinces)
    
    for k,v in resprovinces.items():
        resprovince_label.append(k)
        resprovince_data.append(v)
    
    #clients by location 
    loccuslabel = []
    loccus = []
   
    locations = Location.objects.all()
   
    for location in locations:
        loccuscount = UserProfile.objects.filter(location=location, activation=1).exclude(category='STAFF').count()
        if loccuscount != 0:
            loccus.append(float(loccuscount))
        else:
            loccus.append(0)
            
        loccuslabel.append(f'{location.name}, {loccuscount}')
    
    context = {
        'nav' : 'clients',
        'loans': loans,
        'clients_all' : clients_all,
        'clients_withloan' : clients_withloan,
        'clients_pending': clients_pending,
        'clients_flagged' :  clients_flagged,
        'clients_suspended' : clients_suspended,
        'clients_with_default': clients_with_default,
        'clients_in_recovery':clients_in_recovery,
        'public_ca': public_ca,
        'public_cwl':public_cwl,
        'public_cwd': public_cwd,
        'public_cir':public_cir,
        'private_ca': private_ca,
        'private_cwl':private_cwl,
        'private_cwd': private_cwd,
        'private_cir':private_cir, 
        'married': married,
        'single': single,
        'other_marital': other_marital,
        'male': male,
        'female': female,
        'working': working,
        'not_working': not_working,
        'with_sme': with_sme,
        'without_sme': without_sme,
        
        'clients_1824P':clients_1824P,
        'clients_2530P':clients_2530P,
        'clients_3140P':clients_3140P,
        'clients_4150P':clients_4150P,
        'clients_51100P':clients_51100P,
        
        'clients_1824M':clients_1824M,
        'clients_2530M':clients_2530M,
        'clients_3140M':clients_3140M,
        'clients_4150M':clients_4150M,
        'clients_51100M':clients_51100M,
        
        'clients_1824FM':clients_1824FM,
        'clients_2530FM':clients_2530FM,
        'clients_3140FM':clients_3140FM,
        'clients_4150FM':clients_4150FM,
        'clients_51100FM':clients_51100FM,
        
        'publicsectorpercent': publicsectorpercent,
        'privatesectorpercent': privatesectorpercent,
        'nasector': nasector ,
        
        'province_label':province_label,
        'province_data': province_data, 
        'province_data_count': province_data_count,
        
        'resprovince_label':resprovince_label,
        'resprovince_data': resprovince_data, 
        'resprovince_data_count': resprovince_data_count,
        
        'loccuslabel': loccuslabel,
        'loccus': loccus,
    }
    
    return render(request, 'clients.html', context )


@admin_check
def clients_all(request):
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    clients = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0).all()
    
    clients_all = clients
    clients_withloan = clients.filter(number_of_loans__gt=0).all()
    clients_pending = UserProfile.objects.select_related('user').filter(activation=0, user__staff=0).all()
    clients_flagged = clients.filter(user__dcc_flagged=1).all()
    clients_suspended = clients.filter(user__suspended=1).all()
    
    if request.method=='POST':
        
        if request.POST.get('cuscat') and request.POST.get('sectype') and request.POST.get('loanopt'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')  
            loanopt = request.POST.get('loanopt')  
            
            if sectype == 'PUBLIC':
                
                if loanopt == 'withloan':
                    if cuscat == 'MEMBER':
                        
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0, category='MEMBER')
                        
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_all.html', context )  
                               
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0, category='NON-MEMBER') 
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                                
                            }
                        
                        return render(request, 'clients_all.html', context )  
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0, category='STAFF')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_all.html', context )
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0, category='MEMBER') 
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_all.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_all.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0, category='STAFF')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_all.html', context )
                    
            elif sectype == 'PRIVATE':
                
                if loanopt == 'withloan':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0, category='MEMBER') 
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_all.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_all.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0, category='STAFF')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_all.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0, category='MEMBER')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_all.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_all.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0, category='STAFF')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_all.html', context )

            else:
                
                if loanopt == 'withloan':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0, category='MEMBER') 
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_all.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_all.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0, category='STAFF')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_all.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans=0, category='MEMBER')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_all.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_all.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', number_of_loans=0, category='STAFF')
                        context = {
                                'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_all.html', context )
   
        elif request.POST.get('cuscat') and request.POST.get('sectype'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')    
            
            if sectype == 'PUBLIC':
                
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='MEMBER')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'sectype': sectype,
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    return render(request, 'clients_all.html', context )    
                       
                elif cuscat == 'NON-MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='NON-MEMBER') 
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'sectype': sectype,
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                            
                        }
                    
                    return render(request, 'clients_all.html', context )  
                else:
                    clients_filtered = clients.filter(sector='PUBLIC', category='STAFF')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'sectype': sectype,
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )
            
            elif sectype == 'PRIVATE':
                
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='MEMBER') 
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'sectype': sectype,
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='NON-MEMBER')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'sectype': sectype,
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )   
                else:
                    clients_filtered = clients.filter(sector='PRIVATE', category='STAFF')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'sectype': sectype,
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )
            
            else: 
               
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='MEMBER') 
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'sectype': sectype,
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='NON-MEMBER')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'sectype': sectype,
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )   
                else:
                    clients_filtered = clients.filter(sector='NA', category='STAFF')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'sectype': sectype,
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )
            
        elif request.POST.get('cuscat') and request.POST.get('loanopt'):
            
            cuscat = request.POST.get('cuscat')  
            loanopt = request.POST.get('loanopt')  
             
            if loanopt == 'withloan':
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'loanopt': 'WITH LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_all.html', context )  
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                             'cuscat': cuscat, 'loanopt': 'WITH LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                            
                        }
                    
                    return render(request, 'clients_all.html', context )  
                else:
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                             'cuscat': cuscat, 'loanopt': 'WITH LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_all.html', context )
            else:
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='MEMBER') 
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                             'cuscat': cuscat, 'loanopt': 'WITHOUT LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'loanopt': 'WITHOUT LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )   
                else:
                    clients_filtered = clients.filter(number_of_loans=0, category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'cuscat': cuscat, 'loanopt': 'WITHOUT LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )
        
        elif request.POST.get('sectype') and request.POST.get('loanopt'):

            sectype = request.POST.get('sectype')  
            loanopt = request.POST.get('loanopt')  
            
            if sectype == 'PUBLIC':
                
                if loanopt == 'withloan':
                        
                    clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0)
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'sectype': sectype, 'loanopt': 'WITH LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_all.html', context )  
                               
                else:
                    
                    clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0) 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )                       
                    
            elif sectype == 'PRIVATE':
                
                if loanopt == 'withloan':
                    
                    clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0) 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'sectype': sectype, 'loanopt': 'WITH LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_all.html', context )                       
                
                else:
                   
                    clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0)
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )                        
                    
            else:
                
                if loanopt == 'withloan':
                    
                    clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0) 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'sectype': sectype, 'loanopt': 'WITH LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_all.html', context )                       
                    
                else:
                    
                    clients_filtered = clients.filter(sector='NA', number_of_loans=0)
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                            'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                            'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_all.html', context )                        

        elif request.POST.get('cuscat'):
            
            cuscat = request.POST.get('cuscat')   
                
            if cuscat == 'MEMBER':
                
                clients_filtered = clients.filter(category='MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,
                        'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':clients_filtered,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                return render(request, 'clients_all.html', context )    
                    
            elif cuscat == 'NON-MEMBER':
                
                clients_filtered = clients.filter(category='NON-MEMBER') 
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,
                        'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':clients_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,    
                    }
                
                return render(request, 'clients_all.html', context )  
            
            else:
                clients_filtered = clients.filter(category='STAFF')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                        'cuscat': cuscat,
                        'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_all.html', context )        
          
        elif request.POST.get('sectype'):

            sectype = request.POST.get('sectype')  
            
            if sectype == 'PUBLIC':
                        
                clients_filtered = clients.filter(sector='PUBLIC')
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                        'sectype': sectype,
                        'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':clients_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_all.html', context )                      
                    
            elif sectype == 'PRIVATE':
                    
                clients_filtered = clients.filter(sector='PRIVATE') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                context = {
                        'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                        'sectype': sectype,
                        'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':clients_filtered,
                        'public_filtered':0,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_all.html', context )                                           
                    
            else:
                    
                clients_filtered = clients.filter(sector='NA') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                context = {
                        'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                        'sectype': sectype,
                        'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':0,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_all.html', context )                       
        
        elif request.POST.get('loanopt'):
  
            loanopt = request.POST.get('loanopt')  
                
            if loanopt == 'withloan':
                    
                clients_filtered = clients.filter(number_of_loans__gt=0)
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                        'loanopt': 'WITH LOAN',
                        'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                
                return render(request, 'clients_all.html', context )  
                            
            else:
                
                clients_filtered = clients.filter(number_of_loans=0) 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                context = {
                        'nav' : 'clients_all', 'filter': 'on', 'referrer': referrer,
                        'loanopt': 'WITHOUT LOAN',
                        'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':0,
                        'withoutl_filtered':clients_filtered,
                    }
                
                return render(request, 'clients_all.html', context )                       
                            
    clients_filtered = clients
    members_filtered = clients.filter(category='MEMBER')  
    nonmembers_filtered = clients.filter(category='NON-MEMBER')
    private_filtered = clients.filter(sector='PRIVATE')
    public_filtered = clients.filter(sector='PUBLIC')
    withl_filtered = clients.filter(number_of_loans__gt=0)
    withoutl_filtered = clients.filter(number_of_loans=0)

    context = {
        'nav' : 'clients_all',
        'clients_all' : clients_all,
        'clients_withloan' : clients_withloan,
        'clients_pending': clients_pending,
        'clients_flagged' :  clients_flagged,
        'clients_suspended' : clients_suspended,
        'clients_filtered':clients_filtered,
        'members_filtered':members_filtered,
        'nonmembers_filtered':nonmembers_filtered,
        'private_filtered':private_filtered,
        'public_filtered':public_filtered,
        'withl_filtered':withl_filtered,
        'withoutl_filtered':withoutl_filtered,
        
    }
    
    return render(request, 'clients_all.html', context )
   
@admin_check
def clients_withloan(request):
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    clients = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0, number_of_loans__gt=0).all()
    clients_allx = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0).all()
    
    clients_all = clients_allx
    clients_withloan = clients_allx.filter(number_of_loans__gt=0).all()
    clients_pending = UserProfile.objects.select_related('user').filter(activation=0, user__staff=0).all()
    clients_flagged = clients_allx.filter(user__dcc_flagged=1).all()
    clients_suspended = clients_allx.filter(user__suspended=1).all()
    
    
    if request.method=='POST':
        
        if request.POST.get('cuscat') and request.POST.get('sectype'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')    
            
            if sectype == 'PUBLIC':
                
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='MEMBER')
                    
                    context = {
                            'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_withloan.html', context )  
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='PUBLIC', category='NON-MEMBER') 
                    context = {
                            'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                            
                        }
                    
                    return render(request, 'clients_withloan.html', context )  
                else:
                    clients_filtered = clients.filter(sector='PUBLIC', category='STAFF')
                    context = {
                            'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_withloan.html', context )
            
            elif sectype == 'PRIVATE':
                
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='MEMBER') 
                    context = {
                            'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_withloan.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_withloan.html', context )   
                else:
                    clients_filtered = clients.filter(sector='PRIVATE', category='STAFF')
                    context = {
                            'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_withloan.html', context )
            
            else:
                
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='MEMBER') 
                    context = {
                            'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_withloan.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_withloan.html', context )   
                else:
                    clients_filtered = clients.filter(sector='NA', category='STAFF')
                    context = {
                            'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_withloan.html', context )
             
        elif request.POST.get('cuscat'):
            
            cuscat = request.POST.get('cuscat')   
                
            if cuscat == 'MEMBER':
                
                clients_filtered = clients.filter(category='MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':clients_filtered,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                return render(request, 'clients_withloan.html', context )    
                    
            elif cuscat == 'NON-MEMBER':
                
                clients_filtered = clients.filter(category='NON-MEMBER') 
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':clients_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,    
                    }
                
                return render(request, 'clients_withloan.html', context )  
            
            else:
                clients_filtered = clients.filter(category='STAFF')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                
                return render(request, 'clients_withloan.html', context )        
          
        elif request.POST.get('sectype'):

            sectype = request.POST.get('sectype')  
            
            if sectype == 'PUBLIC':
                        
                clients_filtered = clients.filter(sector='PUBLIC')
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                
                context = {
                        'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':clients_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                
                return render(request, 'clients_withloan.html', context )                      
                    
            elif sectype == 'PRIVATE':
                    
                clients_filtered = clients.filter(sector='PRIVATE') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                
                context = {
                        'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':clients_filtered,
                        'public_filtered':0,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                
                return render(request, 'clients_withloan.html', context )                                           
                    
            else:
                    
                clients_filtered = clients.filter(sector='NA') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                
                context = {
                        'nav' : 'clients_withloan', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':0,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                
                return render(request, 'clients_withloan.html', context )                       
        
                      
    clients_filtered = clients
    members_filtered = clients.filter(category='MEMBER')  
    nonmembers_filtered = clients.filter(category='NON-MEMBER')
    private_filtered = clients.filter(sector='PRIVATE')
    public_filtered = clients.filter(sector='PUBLIC')    

    context = {
        'nav' : 'clients_withloan',
        'clients_all' : clients_all,
        'clients_withloan' : clients_withloan,
        'clients_pending': clients_pending,
        'clients_flagged' :  clients_flagged,
        'clients_suspended' : clients_suspended,
        'clients_filtered':clients_filtered,
        'members_filtered':members_filtered,
        'nonmembers_filtered':nonmembers_filtered,
        'private_filtered':private_filtered,
        'public_filtered':public_filtered,
        'withl_filtered':clients_filtered,
        'withoutl_filtered':0,
        
    }
    
    return render(request, 'clients_withloan.html', context )

@admin_check
def clients_pending(request):
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    clients = UserProfile.objects.select_related('user').filter(activation=0, user__staff=0).all()
    clients_allx = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0).all()
    
    clients_all = clients_allx
    clients_withloan = clients_allx.filter(number_of_loans__gt=0).all()
    clients_pending = UserProfile.objects.select_related('user').filter(activation=0, user__staff=0).all()
    clients_flagged = clients_allx.filter(user__dcc_flagged=1).all()
    clients_suspended = clients_allx.filter(user__suspended=1).all()
    
    
    if request.method=='POST':
        
        if request.POST.get('cuscat') and request.POST.get('sectype') and request.POST.get('reqcheck'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')  
            reqcheck = request.POST.get('reqcheck')  
            
            if sectype == 'PUBLIC':
                
                if reqcheck == 'COMPLETED':
                    if cuscat == 'MEMBER':
                        
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'COMPLETED', category='MEMBER')
                        
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending.html', context )  
                               
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'COMPLETED', category='NON-MEMBER') 
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                                
                            }
                        
                        return render(request, 'clients_pending.html', context )  
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'COMPLETED', category='STAFF')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending.html', context )
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'INCOMPLETE', category='MEMBER') 
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'INCOMPLETE', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'INCOMPLETE', category='STAFF')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending.html', context )
                    
            elif sectype == 'PRIVATE':
                
                if reqcheck == 'COMPLETED':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'COMPLETED', category='MEMBER') 
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'COMPLETED', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'COMPLETED', category='STAFF')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'INCOMPLETE', category='MEMBER')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'INCOMPLETE', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'INCOMPLETE', category='STAFF')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending.html', context )

            else:
                
                if reqcheck == 'COMPLETED':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'COMPLETED', category='MEMBER') 
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'COMPLETED', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'COMPLETED', category='STAFF')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'INCOMPLETE', category='MEMBER')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'INCOMPLETE', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'INCOMPLETE', category='STAFF')
                        context = {
                                'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending.html', context )
   
        elif request.POST.get('cuscat') and request.POST.get('sectype'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')    
            
            if sectype == 'PUBLIC':
                
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='MEMBER')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    return render(request, 'clients_pending.html', context )    
                       
                elif cuscat == 'NON-MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='NON-MEMBER') 
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                            
                        }
                    
                    return render(request, 'clients_pending.html', context )  
                else:
                    clients_filtered = clients.filter(sector='PUBLIC', category='STAFF')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )
            
            elif sectype == 'PRIVATE':
                
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='MEMBER') 
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='NON-MEMBER')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )   
                else:
                    clients_filtered = clients.filter(sector='PRIVATE', category='STAFF')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )
            
            else: 
               
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='MEMBER') 
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='NON-MEMBER')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )   
                else:
                    clients_filtered = clients.filter(sector='NA', category='STAFF')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )
            
        elif request.POST.get('cuscat') and request.POST.get('reqcheck'):
            
            cuscat = request.POST.get('cuscat')  
            reqcheck = request.POST.get('reqcheck')  
             
            if reqcheck == 'COMPLETED':
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(requirement_check = 'COMPLETED', category='MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending.html', context )  
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(requirement_check = 'COMPLETED', category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                            
                        }
                    
                    return render(request, 'clients_pending.html', context )  
                else:
                    clients_filtered = clients.filter(requirement_check = 'COMPLETED', category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending.html', context )
            else:
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(requirement_check = 'INCOMPLETE', category='MEMBER') 
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(requirement_check = 'INCOMPLETE', category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )   
                else:
                    clients_filtered = clients.filter(requirement_check = 'INCOMPLETE', category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )
        
        elif request.POST.get('sectype') and request.POST.get('reqcheck'):

            sectype = request.POST.get('sectype')  
            reqcheck = request.POST.get('reqcheck')  
            
            if sectype == 'PUBLIC':
                
                if reqcheck == 'COMPLETED':
                        
                    clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'COMPLETED')
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending.html', context )  
                               
                else:
                    
                    clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'INCOMPLETE') 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )                       
                    
            elif sectype == 'PRIVATE':
                
                if reqcheck == 'COMPLETED':
                    
                    clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'COMPLETED') 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending.html', context )                       
                
                else:
                   
                    clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'INCOMPLETE')
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )                        
                    
            else:
                
                if reqcheck == 'COMPLETED':
                    
                    clients_filtered = clients.filter(sector='NA', requirement_check = 'COMPLETED') 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending.html', context )                       
                    
                else:
                    
                    clients_filtered = clients.filter(sector='NA', requirement_check = 'INCOMPLETE')
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending.html', context )                        

        elif request.POST.get('cuscat'):
            
            cuscat = request.POST.get('cuscat')   
                
            if cuscat == 'MEMBER':
                
                clients_filtered = clients.filter(category='MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                
                context = {
                        'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':clients_filtered,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                return render(request, 'clients_pending.html', context )    
                    
            elif cuscat == 'NON-MEMBER':
                
                clients_filtered = clients.filter(category='NON-MEMBER') 
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                
                context = {
                        'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':clients_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,    
                    }
                
                return render(request, 'clients_pending.html', context )  
            
            else:
                clients_filtered = clients.filter(category='STAFF')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                
                context = {
                        'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                
                return render(request, 'clients_pending.html', context )        
          
        elif request.POST.get('sectype'):

            sectype = request.POST.get('sectype')  
            
            if sectype == 'PUBLIC':
                        
                clients_filtered = clients.filter(sector='PUBLIC')
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                
                context = {
                        'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                              'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':clients_filtered,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                
                return render(request, 'clients_pending.html', context )                      
                    
            elif sectype == 'PRIVATE':
                    
                clients_filtered = clients.filter(sector='PRIVATE') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                context = {
                        'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':clients_filtered,
                        'public_filtered':0,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                
                return render(request, 'clients_pending.html', context )                                           
                    
            else:
                    
                clients_filtered = clients.filter(sector='NA') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                context = {
                        'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':0,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                
                return render(request, 'clients_pending.html', context )                       
        
        elif request.POST.get('reqcheck'):
  
            reqcheck = request.POST.get('reqcheck')  
                
            if reqcheck == 'COMPLETED':
                    
                clients_filtered = clients.filter(requirement_check = 'COMPLETED')
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                                'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':clients_filtered,
                        'uncheck_filtered':0,
                    }
                
                return render(request, 'clients_pending.html', context )  
                            
            else:
                
                clients_filtered = clients.filter(requirement_check = 'INCOMPLETE') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                context = {
                        'nav' : 'clients_pending', 'filter': 'on', 'referrer': referrer,
                               'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':0,
                        'uncheck_filtered':clients_filtered,
                    }
                
                return render(request, 'clients_pending.html', context )                       
                            
    clients_filtered = clients
    members_filtered = clients.filter(category='MEMBER')  
    nonmembers_filtered = clients.filter(category='NON-MEMBER')
    private_filtered = clients.filter(sector='PRIVATE')
    public_filtered = clients.filter(sector='PUBLIC')
    check_filtered = clients.filter(requirement_check = 'COMPLETED')
    uncheck_filtered = clients.filter(requirement_check = 'INCOMPLETE')

    context = {
        'nav' : 'clients_pending',
        'clients_all' : clients_all,
        'clients_withloan' : clients_withloan,
        'clients_pending': clients_pending,
        'clients_flagged' :  clients_flagged,
        'clients_suspended' : clients_suspended,
        'clients_filtered':clients_filtered,
        'members_filtered':members_filtered,
        'nonmembers_filtered':nonmembers_filtered,
        'private_filtered':private_filtered,
        'public_filtered':public_filtered,
        'check_filtered':check_filtered,
        'uncheck_filtered':uncheck_filtered,
        
    }
    
    return render(request, 'clients_pending.html', context )

@admin_check
def clients_pending_activation(request):
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    clients = UserProfile.objects.select_related('user').filter(activation=0, user__staff=0, account_requirements_check='COMPLETED' ).all()
    clients_allx = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0).all()
    
    clients_all = clients_allx
    clients_withloan = clients_allx.filter(number_of_loans__gt=0).all()
    clients_pending = UserProfile.objects.select_related('user').filter(activation=0, user__staff=0).all()
    clients_flagged = clients_allx.filter(user__dcc_flagged=1).all()
    clients_suspended = clients_allx.filter(user__suspended=1).all()
    
    
    if request.method=='POST':
        
        if request.POST.get('cuscat') and request.POST.get('sectype') and request.POST.get('reqcheck'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')  
            reqcheck = request.POST.get('reqcheck')  
            
            if sectype == 'PUBLIC':
                
                if reqcheck == 'COMPLETED':
                    if cuscat == 'MEMBER':
                        
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'COMPLETED', category='MEMBER')
                        
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )  
                               
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'COMPLETED', category='NON-MEMBER') 
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                                
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )  
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'COMPLETED', category='STAFF')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'INCOMPLETE', category='MEMBER') 
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'INCOMPLETE', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'INCOMPLETE', category='STAFF')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )
                    
            elif sectype == 'PRIVATE':
                
                if reqcheck == 'COMPLETED':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'COMPLETED', category='MEMBER') 
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'COMPLETED', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'COMPLETED', category='STAFF')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'INCOMPLETE', category='MEMBER')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'INCOMPLETE', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'INCOMPLETE', category='STAFF')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )

            else:
                
                if reqcheck == 'COMPLETED':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'COMPLETED', category='MEMBER') 
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'COMPLETED', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'COMPLETED', category='STAFF')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':clients_filtered,
                                'uncheck_filtered':0,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'INCOMPLETE', category='MEMBER')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'INCOMPLETE', category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', requirement_check = 'INCOMPLETE', category='STAFF')
                        context = {
                                'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'check_filtered':0,
                                'uncheck_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_pending_activation.html', context )
   
        elif request.POST.get('cuscat') and request.POST.get('sectype'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')    
            
            if sectype == 'PUBLIC':
                
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='MEMBER')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    return render(request, 'clients_pending_activation.html', context )    
                       
                elif cuscat == 'NON-MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='NON-MEMBER') 
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                            
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )  
                else:
                    clients_filtered = clients.filter(sector='PUBLIC', category='STAFF')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )
            
            elif sectype == 'PRIVATE':
                
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='MEMBER') 
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='NON-MEMBER')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )   
                else:
                    clients_filtered = clients.filter(sector='PRIVATE', category='STAFF')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )
            
            else: 
               
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='MEMBER') 
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='NON-MEMBER')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )   
                else:
                    clients_filtered = clients.filter(sector='NA', category='STAFF')
                    check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                    uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':check_filtered,
                            'uncheck_filtered':uncheck_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )
            
        elif request.POST.get('cuscat') and request.POST.get('reqcheck'):
            
            cuscat = request.POST.get('cuscat')  
            reqcheck = request.POST.get('reqcheck')  
             
            if reqcheck == 'COMPLETED':
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(requirement_check = 'COMPLETED', category='MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )  
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(requirement_check = 'COMPLETED', category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                            
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )  
                else:
                    clients_filtered = clients.filter(requirement_check = 'COMPLETED', category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )
            else:
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(requirement_check = 'INCOMPLETE', category='MEMBER') 
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(requirement_check = 'INCOMPLETE', category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )   
                else:
                    clients_filtered = clients.filter(requirement_check = 'INCOMPLETE', category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )
        
        elif request.POST.get('sectype') and request.POST.get('reqcheck'):

            sectype = request.POST.get('sectype')  
            reqcheck = request.POST.get('reqcheck')  
            
            if sectype == 'PUBLIC':
                
                if reqcheck == 'COMPLETED':
                        
                    clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'COMPLETED')
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )  
                               
                else:
                    
                    clients_filtered = clients.filter(sector='PUBLIC', requirement_check = 'INCOMPLETE') 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )                       
                    
            elif sectype == 'PRIVATE':
                
                if reqcheck == 'COMPLETED':
                    
                    clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'COMPLETED') 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )                       
                
                else:
                   
                    clients_filtered = clients.filter(sector='PRIVATE', requirement_check = 'INCOMPLETE')
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )                        
                    
            else:
                
                if reqcheck == 'COMPLETED':
                    
                    clients_filtered = clients.filter(sector='NA', requirement_check = 'COMPLETED') 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':clients_filtered,
                            'uncheck_filtered':0,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )                       
                    
                else:
                    
                    clients_filtered = clients.filter(sector='NA', requirement_check = 'INCOMPLETE')
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'check_filtered':0,
                            'uncheck_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_pending_activation.html', context )                        

        elif request.POST.get('cuscat'):
            
            cuscat = request.POST.get('cuscat')   
                
            if cuscat == 'MEMBER':
                
                clients_filtered = clients.filter(category='MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                
                context = {
                        'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':clients_filtered,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                return render(request, 'clients_pending_activation.html', context )    
                    
            elif cuscat == 'NON-MEMBER':
                
                clients_filtered = clients.filter(category='NON-MEMBER') 
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                
                context = {
                        'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':clients_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,    
                    }
                
                return render(request, 'clients_pending_activation.html', context )  
            
            else:
                clients_filtered = clients.filter(category='STAFF')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                
                context = {
                        'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                
                return render(request, 'clients_pending_activation.html', context )        
          
        elif request.POST.get('sectype'):

            sectype = request.POST.get('sectype')  
            
            if sectype == 'PUBLIC':
                        
                clients_filtered = clients.filter(sector='PUBLIC')
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                
                context = {
                        'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                              'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':clients_filtered,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                
                return render(request, 'clients_pending_activation.html', context )                      
                    
            elif sectype == 'PRIVATE':
                    
                clients_filtered = clients.filter(sector='PRIVATE') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                context = {
                        'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':clients_filtered,
                        'public_filtered':0,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                
                return render(request, 'clients_pending_activation.html', context )                                           
                    
            else:
                    
                clients_filtered = clients.filter(sector='NA') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                check_filtered = clients_filtered.filter(requirement_check = 'COMPLETED')
                uncheck_filtered = clients_filtered.filter(requirement_check = 'INCOMPLETE')
                context = {
                        'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':0,
                        'check_filtered':check_filtered,
                        'uncheck_filtered':uncheck_filtered,
                    }
                
                return render(request, 'clients_pending_activation.html', context )                       
        
        elif request.POST.get('reqcheck'):
  
            reqcheck = request.POST.get('reqcheck')  
                
            if reqcheck == 'COMPLETED':
                    
                clients_filtered = clients.filter(requirement_check = 'COMPLETED')
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                                'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':clients_filtered,
                        'uncheck_filtered':0,
                    }
                
                return render(request, 'clients_pending_activation.html', context )  
                            
            else:
                
                clients_filtered = clients.filter(requirement_check = 'INCOMPLETE') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                context = {
                        'nav' : 'clients_pending_activation', 'filter': 'on', 'referrer': referrer,
                               'reqcheck': reqcheck,
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'check_filtered':0,
                        'uncheck_filtered':clients_filtered,
                    }
                
                return render(request, 'clients_pending_activation.html', context )                       
                            
    clients_filtered = clients
    members_filtered = clients.filter(category='MEMBER')  
    nonmembers_filtered = clients.filter(category='NON-MEMBER')
    private_filtered = clients.filter(sector='PRIVATE')
    public_filtered = clients.filter(sector='PUBLIC')
    check_filtered = clients.filter(requirement_check = 'COMPLETED')
    uncheck_filtered = clients.filter(requirement_check = 'INCOMPLETE')

    context = {
        'nav' : 'clients_pending_activation',
        'clients_all' : clients_all,
        'clients_withloan' : clients_withloan,
        'clients_pending': clients_pending,
        'clients_flagged' :  clients_flagged,
        'clients_suspended' : clients_suspended,
        'clients_filtered':clients_filtered,
        'members_filtered':members_filtered,
        'nonmembers_filtered':nonmembers_filtered,
        'private_filtered':private_filtered,
        'public_filtered':public_filtered,
        'check_filtered':check_filtered,
        'uncheck_filtered':uncheck_filtered,
        
    }
    
    return render(request, 'clients_pending_activation.html', context )
 

@admin_check
def clients_flagged(request):
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    clients = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0, user__dcc_flagged=True).all()
    clients_allx = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0).all()
    
    clients_all = clients_allx
    clients_withloan = clients_allx.filter(number_of_loans__gt=0).all()
    clients_pending = UserProfile.objects.select_related('user').filter(activation=0, user__staff=0).all()
    clients_flagged = clients_allx.filter(user__dcc_flagged=1).all()
    clients_suspended = clients_allx.filter(user__suspended=1).all()
    
    
    if request.method=='POST':
        
        if request.POST.get('cuscat') and request.POST.get('sectype') and request.POST.get('loanopt'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')  
            loanopt = request.POST.get('loanopt')  
            
            if sectype == 'PUBLIC':
                
                if loanopt == 'withloan':
                    if cuscat == 'MEMBER':
                        
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0, category='MEMBER')
                        
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_flagged.html', context )  
                               
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0, category='NON-MEMBER') 
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                                
                            }
                        
                        return render(request, 'clients_flagged.html', context )  
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0, category='STAFF')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_flagged.html', context )
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0, category='MEMBER') 
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_flagged.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_flagged.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0, category='STAFF')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_flagged.html', context )
                    
            elif sectype == 'PRIVATE':
                
                if loanopt == 'withloan':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0, category='MEMBER') 
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_flagged.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_flagged.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0, category='STAFF')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_flagged.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0, category='MEMBER')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_flagged.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_flagged.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0, category='STAFF')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_flagged.html', context )

            else:
                
                if loanopt == 'withloan':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0, category='MEMBER') 
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_flagged.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_flagged.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0, category='STAFF')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_flagged.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans=0, category='MEMBER')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_flagged.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_flagged.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', number_of_loans=0, category='STAFF')
                        context = {
                                'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_flagged.html', context )
   
        elif request.POST.get('cuscat') and request.POST.get('sectype'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')    
            
            if sectype == 'PUBLIC':
                
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='MEMBER')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    return render(request, 'clients_flagged.html', context )    
                       
                elif cuscat == 'NON-MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='NON-MEMBER') 
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                            
                        }
                    
                    return render(request, 'clients_flagged.html', context )  
                else:
                    clients_filtered = clients.filter(sector='PUBLIC', category='STAFF')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )
            
            elif sectype == 'PRIVATE':
                
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='MEMBER') 
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='NON-MEMBER')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )   
                else:
                    clients_filtered = clients.filter(sector='PRIVATE', category='STAFF')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )
            
            else: 
               
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='MEMBER') 
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='NON-MEMBER')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )   
                else:
                    clients_filtered = clients.filter(sector='NA', category='STAFF')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )
            
        elif request.POST.get('cuscat') and request.POST.get('loanopt'):
            
            cuscat = request.POST.get('cuscat')  
            loanopt = request.POST.get('loanopt')  
             
            if loanopt == 'withloan':
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_flagged.html', context )  
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                            
                        }
                    
                    return render(request, 'clients_flagged.html', context )  
                else:
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_flagged.html', context )
            else:
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='MEMBER') 
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )   
                else:
                    clients_filtered = clients.filter(number_of_loans=0, category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )
        
        elif request.POST.get('sectype') and request.POST.get('loanopt'):

            sectype = request.POST.get('sectype')  
            loanopt = request.POST.get('loanopt')  
            
            if sectype == 'PUBLIC':
                
                if loanopt == 'withloan':
                        
                    clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0)
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_flagged.html', context )  
                               
                else:
                    
                    clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0) 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )                       
                    
            elif sectype == 'PRIVATE':
                
                if loanopt == 'withloan':
                    
                    clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0) 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_flagged.html', context )                       
                
                else:
                   
                    clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0)
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                              'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )                        
                    
            else:
                
                if loanopt == 'withloan':
                    
                    clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0) 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                               'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_flagged.html', context )                       
                    
                else:
                    
                    clients_filtered = clients.filter(sector='NA', number_of_loans=0)
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                               'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_flagged.html', context )                        

        elif request.POST.get('cuscat'):
            
            cuscat = request.POST.get('cuscat')   
                
            if cuscat == 'MEMBER':
                
                clients_filtered = clients.filter(category='MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':clients_filtered,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                return render(request, 'clients_flagged.html', context )    
                    
            elif cuscat == 'NON-MEMBER':
                
                clients_filtered = clients.filter(category='NON-MEMBER') 
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':clients_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,    
                    }
                
                return render(request, 'clients_flagged.html', context )  
            
            else:
                clients_filtered = clients.filter(category='STAFF')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_flagged.html', context )        
          
        elif request.POST.get('sectype'):

            sectype = request.POST.get('sectype')  
            
            if sectype == 'PUBLIC':
                        
                clients_filtered = clients.filter(sector='PUBLIC')
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                               'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':clients_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_flagged.html', context )                      
                    
            elif sectype == 'PRIVATE':
                    
                clients_filtered = clients.filter(sector='PRIVATE') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                context = {
                        'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':clients_filtered,
                        'public_filtered':0,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_flagged.html', context )                                           
                    
            else:
                    
                clients_filtered = clients.filter(sector='NA') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                context = {
                        'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':0,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_flagged.html', context )                       
        
        elif request.POST.get('loanopt'):
  
            loanopt = request.POST.get('loanopt')  
                
            if loanopt == 'withloan':
                    
                clients_filtered = clients.filter(number_of_loans__gt=0)
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                              'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                
                return render(request, 'clients_flagged.html', context )  
                            
            else:
                
                clients_filtered = clients.filter(number_of_loans=0) 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                context = {
                        'nav' : 'clients_flagged', 'filter': 'on', 'referrer': referrer,
                                 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':0,
                        'withoutl_filtered':clients_filtered,
                    }
                
                return render(request, 'clients_flagged.html', context )                       
                            
    clients_filtered = clients
    members_filtered = clients.filter(category='MEMBER')  
    nonmembers_filtered = clients.filter(category='NON-MEMBER')
    private_filtered = clients.filter(sector='PRIVATE')
    public_filtered = clients.filter(sector='PUBLIC')
    withl_filtered = clients.filter(number_of_loans__gt=0)
    withoutl_filtered = clients.filter(number_of_loans=0)

    context = {
        'nav' : 'clients_flagged',
        'clients_all' : clients_all,
        'clients_withloan' : clients_withloan,
        'clients_pending': clients_pending,
        'clients_flagged' :  clients_flagged,
        'clients_suspended' : clients_suspended,
        'clients_filtered':clients_filtered,
        'members_filtered':members_filtered,
        'nonmembers_filtered':nonmembers_filtered,
        'private_filtered':private_filtered,
        'public_filtered':public_filtered,
        'withl_filtered':withl_filtered,
        'withoutl_filtered':withoutl_filtered,
        
    }
    
    return render(request, 'clients_flagged.html', context )

@admin_check
def clients_suspended(request):
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    clients = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0, user__suspended=True).all()
    clients_allx = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0).all()
    
    clients_all = clients_allx
    clients_withloan = clients_allx.filter(number_of_loans__gt=0).all()
    clients_pending = UserProfile.objects.select_related('user').filter(activation=0, user__staff=0).all()
    clients_flagged = clients_allx.filter(user__dcc_flagged=1).all()
    clients_suspended = clients_allx.filter(user__suspended=1).all()
    
    if request.method=='POST':
        
        if request.POST.get('cuscat') and request.POST.get('sectype') and request.POST.get('loanopt'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')  
            loanopt = request.POST.get('loanopt')  
            
            if sectype == 'PUBLIC':
                
                if loanopt == 'withloan':
                    if cuscat == 'MEMBER':
                        
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0, category='MEMBER')
                        
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_suspended.html', context )  
                               
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0, category='NON-MEMBER') 
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                                
                            }
                        
                        return render(request, 'clients_suspended.html', context )  
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0, category='STAFF')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_suspended.html', context )
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0, category='MEMBER') 
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_suspended.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_suspended.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0, category='STAFF')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':clients_filtered,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_suspended.html', context )
                    
            elif sectype == 'PRIVATE':
                
                if loanopt == 'withloan':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0, category='MEMBER') 
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_suspended.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_suspended.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0, category='STAFF')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_suspended.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0, category='MEMBER')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_suspended.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_suspended.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0, category='STAFF')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':clients_filtered,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_suspended.html', context )

            else:
                
                if loanopt == 'withloan':
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0, category='MEMBER') 
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_suspended.html', context )                       
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_suspended.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0, category='STAFF')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':clients_filtered,
                                'withoutl_filtered':0,
                            }
                        
                        return render(request, 'clients_suspended.html', context )
                
                else:
                    if cuscat == 'MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans=0, category='MEMBER')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':clients_filtered,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_suspended.html', context )                        
                    elif cuscat == 'NON-MEMBER':
                        clients_filtered = clients.filter(sector='NA', number_of_loans=0, category='NON-MEMBER')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':clients_filtered,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_suspended.html', context )   
                    else:
                        clients_filtered = clients.filter(sector='NA', number_of_loans=0, category='STAFF')
                        context = {
                                'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                                'clients_withloan' : clients_withloan,
                                'clients_pending': clients_pending,
                                'clients_flagged' :  clients_flagged,
                                'clients_suspended' : clients_suspended,
                                'clients_filtered': clients_filtered,
                                'members_filtered':0,
                                'nonmembers_filtered':0,
                                'private_filtered':0,
                                'public_filtered':0,
                                'withl_filtered':0,
                                'withoutl_filtered':clients_filtered,
                            }
                        
                        return render(request, 'clients_suspended.html', context )
   
        elif request.POST.get('cuscat') and request.POST.get('sectype'):
            
            cuscat = request.POST.get('cuscat') 
            sectype = request.POST.get('sectype')    
            
            if sectype == 'PUBLIC':
                
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='MEMBER')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    return render(request, 'clients_suspended.html', context )    
                       
                elif cuscat == 'NON-MEMBER':
                    
                    clients_filtered = clients.filter(sector='PUBLIC', category='NON-MEMBER') 
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                            
                        }
                    
                    return render(request, 'clients_suspended.html', context )  
                else:
                    clients_filtered = clients.filter(sector='PUBLIC', category='STAFF')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )
            
            elif sectype == 'PRIVATE':
                
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='MEMBER') 
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='PRIVATE', category='NON-MEMBER')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )   
                else:
                    clients_filtered = clients.filter(sector='PRIVATE', category='STAFF')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )
            
            else: 
               
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='MEMBER') 
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype,
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(sector='NA', category='NON-MEMBER')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )   
                else:
                    clients_filtered = clients.filter(sector='NA', category='STAFF')
                    withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                    withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'sectype': sectype, 
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':withl_filtered,
                            'withoutl_filtered':withoutl_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )
            
        elif request.POST.get('cuscat') and request.POST.get('loanopt'):
            
            cuscat = request.POST.get('cuscat')  
            loanopt = request.POST.get('loanopt')  
             
            if loanopt == 'withloan':
                if cuscat == 'MEMBER':
                    
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_suspended.html', context )  
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                            
                        }
                    
                    return render(request, 'clients_suspended.html', context )  
                else:
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_suspended.html', context )
            else:
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='MEMBER') 
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC') 
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':clients_filtered,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )                       
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='NON-MEMBER')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':clients_filtered,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )   
                else:
                    clients_filtered = clients.filter(number_of_loans=0, category='STAFF')
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat,  'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':0,
                            'nonmembers_filtered':0,
                            'private_filtered':private_filtered,
                            'public_filtered':public_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )
        
        elif request.POST.get('sectype') and request.POST.get('loanopt'):

            sectype = request.POST.get('sectype')  
            loanopt = request.POST.get('loanopt')  
            
            if sectype == 'PUBLIC':
                
                if loanopt == 'withloan':
                        
                    clients_filtered = clients.filter(sector='PUBLIC', number_of_loans__gt=0)
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                               'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_suspended.html', context )  
                               
                else:
                    
                    clients_filtered = clients.filter(sector='PUBLIC', number_of_loans=0) 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':clients_filtered,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )                       
                    
            elif sectype == 'PRIVATE':
                
                if loanopt == 'withloan':
                    
                    clients_filtered = clients.filter(sector='PRIVATE', number_of_loans__gt=0) 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                               'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_suspended.html', context )                       
                
                else:
                   
                    clients_filtered = clients.filter(sector='PRIVATE', number_of_loans=0)
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':clients_filtered,
                            'public_filtered':0,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )                        
                    
            else:
                
                if loanopt == 'withloan':
                    
                    clients_filtered = clients.filter(sector='NA', number_of_loans__gt=0) 
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':clients_filtered,
                            'withoutl_filtered':0,
                        }
                    
                    return render(request, 'clients_suspended.html', context )                       
                    
                else:
                    
                    clients_filtered = clients.filter(sector='NA', number_of_loans=0)
                    members_filtered = clients_filtered.filter(category='MEMBER')
                    nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                    context = {
                            'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                 'sectype': sectype, 'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                            'clients_withloan' : clients_withloan,
                            'clients_pending': clients_pending,
                            'clients_flagged' :  clients_flagged,
                            'clients_suspended' : clients_suspended,
                            'clients_filtered': clients_filtered,
                            'members_filtered':members_filtered,
                            'nonmembers_filtered':nonmembers_filtered,
                            'private_filtered':0,
                            'public_filtered':0,
                            'withl_filtered':0,
                            'withoutl_filtered':clients_filtered,
                        }
                    
                    return render(request, 'clients_suspended.html', context )                        

        elif request.POST.get('cuscat'):
            
            cuscat = request.POST.get('cuscat')   
                
            if cuscat == 'MEMBER':
                
                clients_filtered = clients.filter(category='MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':clients_filtered,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                return render(request, 'clients_suspended.html', context )    
                    
            elif cuscat == 'NON-MEMBER':
                
                clients_filtered = clients.filter(category='NON-MEMBER') 
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':clients_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,    
                    }
                
                return render(request, 'clients_suspended.html', context )  
            
            else:
                clients_filtered = clients.filter(category='STAFF')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'cuscat': cuscat, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':0,
                        'nonmembers_filtered':0,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_suspended.html', context )        
          
        elif request.POST.get('sectype'):

            sectype = request.POST.get('sectype')  
            
            if sectype == 'PUBLIC':
                        
                clients_filtered = clients.filter(sector='PUBLIC')
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                
                context = {
                        'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':clients_filtered,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_suspended.html', context )                      
                    
            elif sectype == 'PRIVATE':
                    
                clients_filtered = clients.filter(sector='PRIVATE') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                context = {
                        'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':clients_filtered,
                        'public_filtered':0,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_suspended.html', context )                                           
                    
            else:
                    
                clients_filtered = clients.filter(sector='NA') 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                context = {
                        'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'sectype': sectype, 
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':0,
                        'public_filtered':0,
                        'withl_filtered':withl_filtered,
                        'withoutl_filtered':withoutl_filtered,
                    }
                
                return render(request, 'clients_suspended.html', context )                       
        
        elif request.POST.get('loanopt'):
  
            loanopt = request.POST.get('loanopt')  
                
            if loanopt == 'withloan':
                    
                clients_filtered = clients.filter(number_of_loans__gt=0)
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                
                context = {
                        'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                                'loanopt': 'WITH LOAN',
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':clients_filtered,
                        'withoutl_filtered':0,
                    }
                
                return render(request, 'clients_suspended.html', context )  
                            
            else:
                
                clients_filtered = clients.filter(number_of_loans=0) 
                members_filtered = clients_filtered.filter(category='MEMBER')
                nonmembers_filtered = clients_filtered.filter(category='NON-MEMBER')
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                context = {
                        'nav' : 'clients_suspended', 'filter': 'on', 'referrer': referrer,
                               'loanopt': 'WITHOUT LOAN',
                                'clients_all' : clients_all,
                        'clients_withloan' : clients_withloan,
                        'clients_pending': clients_pending,
                        'clients_flagged' :  clients_flagged,
                        'clients_suspended' : clients_suspended,
                        'clients_filtered': clients_filtered,
                        'members_filtered':members_filtered,
                        'nonmembers_filtered':nonmembers_filtered,
                        'private_filtered':private_filtered,
                        'public_filtered':public_filtered,
                        'withl_filtered':0,
                        'withoutl_filtered':clients_filtered,
                    }
                
                return render(request, 'clients_suspended.html', context )                       
                            
    clients_filtered = clients
    members_filtered = clients.filter(category='MEMBER')  
    nonmembers_filtered = clients.filter(category='NON-MEMBER')
    private_filtered = clients.filter(sector='PRIVATE')
    public_filtered = clients.filter(sector='PUBLIC')
    withl_filtered = clients.filter(number_of_loans__gt=0)
    withoutl_filtered = clients.filter(number_of_loans=0)

    context = {
        'nav' : 'clients_suspended',
        'clients_all' : clients_all,
        'clients_withloan' : clients_withloan,
        'clients_pending': clients_pending,
        'clients_flagged' :  clients_flagged,
        'clients_suspended' : clients_suspended,
        'clients_filtered':clients_filtered,
        'members_filtered':members_filtered,
        'nonmembers_filtered':nonmembers_filtered,
        'private_filtered':private_filtered,
        'public_filtered':public_filtered,
        'withl_filtered':withl_filtered,
        'withoutl_filtered':withoutl_filtered,
        
    }
    
    return render(request, 'clients_suspended.html', context )

@admin_check
def view_client(request, uid): 
    
    
    try:
        referrer = f"{request.META['HTTP_REFERER']}"
    except:
        referrer = f"{request.META['HTTP_HOST']}/admin/clients/"
           
    user = UserProfile.objects.get(pk=uid)
    dccuid = user.uid

    #activation checklist
    now = datetime.date.today()
    dob = user.date_of_birth
    start = user.start_date
    if dob:
        age = round(((now.month - dob.month + (12 * (now.year - dob.year)))/12),2)
    else:
        age = 0
    if start:
        yef = round(((now.month - start.month + (12 * (now.year - start.year)))/12),2)
    else:
        yef = 0
    '''
    #dcc
    #dcc
    client_check = check_client_in_dcc(dccuid)
    if client_check != f'{client_check}':
        client = client_check
        uidresult = client['uid']

        #loans = get_loans_for_client(uidresult)
        dcc_endpoint = settings.DCC_ENDPOINT
        endpoint = f'http://{dcc_endpoint}/API/get_client_loans/{uidresult}/'
        # Make a GET request to the API endpoint
        try:
            response = requests.get(endpoint, verify=False)
            if response.status_code == 404:
                loans_from_dcc = []
            else:
                loans_from_dcc = []
            if response.status_code == 200:
                data = response.json()
                if data:
                    serializer = LoanSerializer(data=data, many=True)
                    if serializer.is_valid():
                        loans_from_dcc = serializer.validated_data
                    else:
                        loans_from_dcc = []
                else:
                    loans_from_dcc = []
            else:
                loans_from_dcc = []
        except:
            messages.error(request, 'NOT WORKING', extra_tags="danger")
            loans_from_dcc = []

        #transactions = get_transactions_for_client(uidresult)
        dcc_endpoint = settings.DCC_ENDPOINT
        transendpoint = f'http://{dcc_endpoint}/API/get_client_transactions/{uidresult}/'
        # Make a GET request to the API endpoint
        try:
            response = requests.get(transendpoint, verify=False)
            if response.status_code == 404:
                statements_from_dcc = []
            if response.status_code == 200:
                data = response.json()
                if data:

                    serializer = StatementSerializer(data=data, many=True)
                    if serializer.is_valid():
                        statements_from_dcc = serializer.validated_data
                else:
                    statements_from_dcc = []

        except:
            messages.error(request, 'NOT WORKING', extra_tags="danger")
            statements_from_dcc = []

        
    else:
        client=[]
        uidresult = []
        loans_from_dcc = []
        statements_from_dcc = []
        if client_check == 'Client is not in DCC Credit Database.':
            messages.error(request, f'{client_check}', extra_tags='info')
        else:
            messages.error(request, f'{client_check}', extra_tags='danger')
    
    
    #print('PRINTING CLIENT UID & LOANS:')
    
    #print(uidresult)
    #print(loans_from_dcc)
    #print(statements_from_dcc)
    '''

    #from django.db.models import Q
    # Combine the two queries into one
    combined_query = Q(owner=user.id) & Q(category='PENDING') & (Q(status='AWAITING T&C') | Q(status='UNDER REVIEW'))
    # Retrieve loans matching the combined query
    combined_loans = Loan.objects.filter(combined_query)
    # Now combined_loans contains loans that satisfy both conditions
    if combined_loans:
        try:
            loan = Loan.objects.get(combined_query)
            loanfile = LoanFile.objects.get(loan=loan)
        except:
            loanfile = []
    else:
        loanfile = []
    suser = User.objects.get(id=user.user_id)
    if user.has_sme == 1:
        smeprofile = SMEProfile.objects.get(owner=user)
    else:
        smeprofile = SMEProfile.objects.filter(owner=user)
   
    all_loans = Loan.objects.filter(owner_id=user).all()
    pending_loans = Loan.objects.filter(owner_id=user,category="PENDING")
    running_loans = Loan.objects.filter(owner_id=user,funded_category="ACTIVE",status="RUNNING")
    defaulted_loans = Loan.objects.filter(owner_id=user,funded_category="ACTIVE",status="DEFAULTED")
    completed_loans = Loan.objects.filter(owner_id=user,funded_category="COMPLETED")
    recovery_loans = Loan.objects.filter(owner_id=user,funded_category="RECOVERY")

    staff_profiles = StaffProfile.objects.all()
    locations = Location.objects.all()

    stafflist = []
    for staff in staff_profiles:
        stafflist.append(f'{staff.user.first_name} {staff.user.last_name}')
    
    locationlist = []
    for location in locations:
        locationlist.append(location.name)

    try:
        officer = StaffProfile.objects.get(id=user.officer)
        officer_fullname = f'{officer.first_name} {officer.last_name}'
    except:
        officer_fullname = "No Officer Assigned"
    
    if request.method == 'POST':
        
        if request.POST.get('subject') and request.POST.get('messageapplicant'):
            
            
    
            subject = request.POST.get('subject')
            ''' if header_cta == 'yes' '''
            cta_label = ''
            cta_link = ''

            greeting = f'Hi {user.first_name}'
            message = f'This is regarding {subject}'
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
                return redirect('view_client', uid)
            except:
                messages.error(request, 'Message has not been sent.', extra_tags='danger')
                
            return redirect('view_client', uid)
        
        
        elif request.POST.get('limit'):
            limit = request.POST.get('limit')
            intlimit = int(limit)
            user.repayment_limit = intlimit
            user.save()
            
                
            subject = 'Deduction Limit Set'

            greeting = f'Hi {user.first_name}'
            message = 'A deduction limit has been set on your account.'
            message_details = 'Everytime you wish to apply for a loan, the amount and fortnights combination must give you a repayment amount below this limit.'

            ''' if cta == 'yes' '''
            cta_btn1_label = f'Limit: K{user.repayment_limit}'
            cta_btn1_link = '#'
            cta_btn2_label = 'APPLY'
            cta_btn2_link = f'{settings.DOMAIN}/loan/apply/'

            ''' if promo == 'yes' '''
            catchphrase = 'TIP:'
            promo_title = 'Need a higher limit?'
            promo_message = 'We can increase your limit if your credit score with us improves.'
            promo_cta = 'Read more about Credit Score'
            promo_cta_link = 'http://www.dcc.com.pg'
            
            email_content = render_to_string('custom/email_temp_general.html', {
                
                'cta': 'yes',
                'cta_btn2': 'yes',
                'promo': 'yes',
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
            email = EmailMultiAlternatives(
                subject,
                text_content,
                sender,
                ['dev@webmasta.com.pg', user.email ]
            )
            email.attach_alternative(email_content, "text/html")

            try: 
                email.send()
                messages.success(request, f'Limit sucessfully set to K{ intlimit } and { user.first_name} has been notified of account deduction limit.')
    
            except:
                messages.error(request, f'Limit sucessfully set to K{ intlimit } but { user.first_name} has NOT been notified of account deduction limit.', extra_tags='info')
                
            return redirect('view_client', uid)
        
        elif 'max_loan_amount' in request.POST:
            from decimal import Decimal as _D, InvalidOperation as _IO
            raw = request.POST.get('max_loan_amount', '').strip()
            try:
                val = _D(raw) if raw else None
                if val is not None and val <= 0:
                    val = None
                user.max_loan_amount = val
                user.save()
                if val:
                    messages.success(request, f'Max loan amount set to K{val:,.2f} for {user.first_name}. Loan form will use Open Repayment mode for this client.')
                else:
                    messages.success(request, f'Max loan amount cleared for {user.first_name}. Global limit applies.')
            except _IO:
                messages.error(request, 'Invalid amount entered.', extra_tags='danger')
            return redirect('view_client', uid)

        elif request.POST.get('assignlocation'):
            location_name = request.POST.get('assignlocation')
            location = Location.objects.get(name=location_name)
            user.location = location
            user.save()
            messages.success(request, f'{user.first_name} {user.last_name} assigned to {location_name}')
            return redirect('view_client', uid)


        elif request.POST.get('assignstaff'):
            staff_name = request.POST.get('assignstaff')
            staff_name_split = staff_name.split(' ')
            first_name = staff_name_split[0]
            last_name = staff_name_split[-1]
            staff = StaffProfile.objects.get(first_name=first_name, last_name=last_name)
            user.officer = staff.id
            user.save()
            messages.success(request, f'{first_name} {last_name} assigned to {user.first_name} {user.last_name} successfully.')
            return redirect('view_client', uid)

        else:
            messages.error(request, 'You did not select anything', extra_tags='warning')
            return redirect('view_client', uid)

    # DCC credit bureau data for the Credit Information tab (pay-per-view:
    # a locked stub until staff click View Data, full report while the paid
    # access window is open). Computed after POST handling so form submits
    # never wait on the bureau.
    dcc_ctx = credit_tab_context(user)

    if pending_loans:

        all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner_id=user).all()
        
        #for pending loans table
        pending = 1
        all_loans_filtered_pending = Loan.objects.prefetch_related('owner').filter(owner_id=user, category="PENDING").all()
        pending_sum = all_loans_filtered_pending.aggregate(sum=Sum('amount'))['sum']
        expected_interests_sum = all_loans_filtered_pending.aggregate(sum=Sum('interest'))['sum']
        expected_repayments_sum = all_loans_filtered_pending.aggregate(sum=Sum('repayment_amount'))['sum']
        
        #for other loans
        others = 1
        all_loans_filtered_withoutpending = Loan.objects.prefetch_related('owner').filter(owner_id=user).exclude(category="PENDING").all()
        funded_sum = all_loans_filtered_withoutpending.aggregate(sum=Sum('amount'))['sum']
        interests_sum = all_loans_filtered_withoutpending.aggregate(sum=Sum('interest'))['sum']
        totalloan_sum = all_loans_filtered_withoutpending.aggregate(sum=Sum('total_loan_amount'))['sum']
        repayments_sum = all_loans_filtered_withoutpending.aggregate(sum=Sum('repayment_amount'))['sum']
        arrears_sum = all_loans_filtered_withoutpending.aggregate(sum=Sum('total_arrears'))['sum']
        defaultinterests_sum = all_loans_filtered_withoutpending.aggregate(sum=Sum('default_interest_receivable'))['sum']
        outstanding_sum = all_loans_filtered_withoutpending.aggregate(sum=Sum('total_outstanding'))['sum']
        
        context = {
                'nav': 'clients',
                'user':user, 
                'smeprofile': smeprofile,
                'pending': pending,
                'others': others,
                'pending_sum': pending_sum,
                'expected_interests_sum': expected_interests_sum,
                'expected_repayments_sum': expected_repayments_sum,
                'all_loans': all_loans,
                'all_loans_filtered': all_loans_filtered,
                'pending_loans': pending_loans,
                'running_loans':running_loans,
                'defaulted_loans': defaulted_loans,
                'completed_loans':completed_loans,
                'recovery_loans':recovery_loans,
                'funded_sum': funded_sum,
                'interests_sum': interests_sum,
                'totalloan_sum': totalloan_sum,
                'repayments_sum': repayments_sum,
                'arrears_sum': arrears_sum,
                'defaultinterests_sum': defaultinterests_sum,
                'outstanding_sum': outstanding_sum,  
                'locationlist': locationlist,
                'stafflist': stafflist, 
                'officer_fullname' : officer_fullname, 
                'loanfile': loanfile,  
                
                'yef': yef,
                'age': age,
                'field_settings': get_field_settings(),
            }
        context.update(dcc_ctx)

        return render(request, 'view_client.html', context)

    else:
        
        pending = 0
        others = 1
        all_loans_filtered = Loan.objects.prefetch_related('owner').filter(owner_id=user).exclude(category="PENDING").all()
        funded_sum = all_loans_filtered.aggregate(sum=Sum('amount'))['sum']
        interests_sum = all_loans_filtered.aggregate(sum=Sum('interest'))['sum']
        totalloan_sum = all_loans_filtered.aggregate(sum=Sum('total_loan_amount'))['sum']
        repayments_sum = all_loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
        arrears_sum = all_loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
        defaultinterests_sum = all_loans_filtered.aggregate(sum=Sum('default_interest_receivable'))['sum']
        outstanding_sum = all_loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
                 
        context = {
                    'nav': 'clients',
                    'suser': suser,
                    'user':user, 
                    'pending': pending,
                    'others': others,
                    'smeprofile': smeprofile,
                    'all_loans': all_loans,
                    'all_loans_filtered': all_loans_filtered,
                    'pending_loans': pending_loans,
                    'running_loans':running_loans,
                    'defaulted_loans': defaulted_loans,
                    'completed_loans':completed_loans,
                    'recovery_loans':recovery_loans,
                    'funded_sum': funded_sum,
                    'interests_sum': interests_sum,
                    'totalloan_sum': totalloan_sum,
                    'repayments_sum': repayments_sum,
                    'arrears_sum': arrears_sum,
                    'defaultinterests_sum': defaultinterests_sum,
                    'outstanding_sum': outstanding_sum,   
                    'locationlist': locationlist,
                    'stafflist': stafflist,
                    'officer_fullname' : officer_fullname,
                    'loanfile': loanfile,
                    
                    'yef': yef,
                    'age': age,
                    'field_settings': get_field_settings(),
                }
        context.update(dcc_ctx)

        return render(request, 'view_client.html', context)

@admin_check
def toggle_work_email_notify(request, uid):
    """Toggle per-client work email notification preference."""
    user = UserProfile.objects.get(pk=uid)
    user.notify_work_email = not user.notify_work_email
    user.save(update_fields=['notify_work_email'])
    state = 'enabled' if user.notify_work_email else 'disabled'
    messages.success(request, f'Work email notifications {state} for {user.first_name} {user.last_name}.', extra_tags='success')
    return redirect('view_client', uid=uid)


@admin_check
def inform_account_activation(request, uid):
    user = UserProfile.objects.get(pk=uid)

    data_needed = []
    if user.date_of_birth:
        data_needed = data_needed
    else: 
        dob = 'DATE OF BIRTH'
        data_needed.append(dob)
    
    if user.start_date:
        data_needed = data_needed
    else:
        start_date = 'WORK START DATE'
        data_needed.append(start_date)
    
    if user.terms_consent == 'YES':
        data_needed = data_needed
    else:
        terms_consent = 'CONSENT TO TERMS AND CONDITIONS'
        data_needed.append(terms_consent)

    if user.credit_consent == 'YES':
        data_needed = data_needed
    else:
        credit_consent = 'CONSENT TO CREDIT DATA'
        data_needed.append(credit_consent)

    if user.passport_url or user.nid_url:
        data_needed = data_needed
    else:
        urlpn = 'UPLOAD PASSPORT OR NID COPY'
        data_needed.append(urlpn)

    if user.job_title:
        data_needed = data_needed
    else:
        jobtitle = 'JOB TITLE'
        data_needed.append(jobtitle)
    if user.gross_pay == 0:
        grosspay = 'GROSS PAY'
        data_needed.append(grosspay)
    else:
        data_needed = data_needed

    message_string = ''
    for i in data_needed:
        message_string = message_string + i + '<br>'

    subject = "More Information required for PROFILE ACTIVATION"
    ''' if header_cta == 'yes' '''
    cta_label = ''
    cta_link = ''

    greeting = f'Hi {user.first_name},'
    message = f'This is regarding your profile activation. You still need to update your profile with the following required information.'
    message_details = message_string

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
        messages.success(request, "Client has been notified of all missing required information")
        return redirect('view_client', uid)
    except:
        messages.error(request, 'Message has not been sent.', extra_tags='danger')
        
    return redirect('view_client', uid)
