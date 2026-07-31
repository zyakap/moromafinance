import datetime
import re
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from accounts.models import User, UserProfile
from loan.models import Loan, Statement, Payment, PaymentUploads
from loan.forms import PaymentForm
from admin1.forms import AdminSettingsForm
from admin1.models import AdminSettings, Location

from django.contrib.sites.shortcuts import get_current_site

#EMAIL SETTINGS
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.utils.html import strip_tags
#admin sender email
from admin1.models import AdminSettings
sender = settings.DEFAULT_SENDER_EMAIL

#Class Based Views
from django.views.generic.base import View
from wkhtmltopdf.views import PDFTemplateResponse

from django.db.models import Sum, Value

from django.conf import settings
from accounts.functions import admin_check


############### 
# START OF CODE
###############

@admin_check
def locations(request):

    locations = Location.objects.all()
    
    for location in locations:
        
        loans = Loan.objects.filter(location=location, category='FUNDED', funded_category="ACTIVE")
        clients = UserProfile.objects.select_related('user').filter(activation=1, user__staff=0, location=location)
        clients_with_loan = clients.filter(number_of_loans__gt=0)
        clients_in_recovery = clients.filter(in_recovery=1)
        
        location.loans = loans.count()
        location.funded = loans.aggregate(sum=Sum('amount'))['sum']
        location.interest = loans.aggregate(sum=Sum('interest'))['sum']
        location.repayment = loans.aggregate(sum=Sum('repayment_amount'))['sum']
        location.arrears = loans.aggregate(sum=Sum('total_arrears'))['sum']
        location.outstanding = loans.aggregate(sum=Sum('total_outstanding'))['sum']
        location.in_recovery = Loan.objects.filter(location=location, category='FUNDED',funded_category="RECOVERY").aggregate(sum=Sum('amount'))['sum']
        location.loans_in_default = Loan.objects.filter(location=location, category='FUNDED',funded_category="ACTIVE", status="DEFAULTED").count()
        
        location.clients = clients.count()
        location.clients_with_loan = clients_with_loan.count()
        location.clients_in_recovery = clients_in_recovery.count()
        
        location.save()
    
    locations = Location.objects.all()
    loc_count = locations.count()
     
    bloc_label = []
    obloc_data = []
    abloc_data = []
    cbloc_data = []
    lbloc_data = []
    
    for location in locations:
        bloc_label.append(location.name)
        if location.outstanding is not None:
            obloc_data.append(float(location.outstanding))
        else:
            obloc_data.append(0)
            
        if location.arrears is not None:
            abloc_data.append(float(location.arrears))
        else:
            abloc_data.append(0)
       
        cbloc_data.append(location.clients)
        lbloc_data.append(location.loans)
    
  
    
    context = {
        'nav': 'locations',
        
        'locations': locations,
        'loc_count': loc_count,
        
        'bloc_label':bloc_label,
        'obloc_data': obloc_data,
        'abloc_data': abloc_data,
        'cbloc_data': cbloc_data,
        'lbloc_data': lbloc_data, 
    }
    
    return render(request, 'locations.html', context)

@admin_check
def locations_clients(request):

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
                        'nav' : 'locations_clients', 'filter': 'on', 'referrer': referrer,
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
                     
                    return render(request, 'locations_clients.html', context) 
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='NON-MEMBER', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav' : 'locations_clients', 'filter': 'on', 'referrer': referrer,
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
                     
                    return render(request, 'locations_clients.html', context) 
                 
                else:
                    clients_filtered = clients.filter(number_of_loans__gt=0, category='STAFF', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav' : 'locations_clients', 'filter': 'on', 'referrer': referrer,
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
                     
                    return render(request, 'locations_clients.html', context) 
            else:
                if cuscat == 'MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='MEMBER', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav' : 'locations_clients', 'filter': 'on', 'referrer': referrer,
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
                     
                    return render(request, 'locations_clients.html', context) 
                            
                elif cuscat == 'NON-MEMBER':
                    clients_filtered = clients.filter(number_of_loans=0, category='NON-MEMBER', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav' : 'locations_clients', 'filter': 'on', 'referrer': referrer,
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
                     
                    return render(request, 'locations_clients.html', context) 
                 
                else:
                    clients_filtered = clients.filter(number_of_loans=0, category='STAFF', location=location)
                    private_filtered = clients_filtered.filter(sector='PRIVATE')
                    public_filtered = clients_filtered.filter(sector='PUBLIC')

                    context = {
                        'nav' : 'locations_clients', 'filter': 'on', 'referrer': referrer,
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
                     
                    return render(request, 'locations_clients.html', context) 
            
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
                    'nav' : 'locations_clients', 'filter': 'on', 'referrer': referrer,
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
                    
                return render(request, 'locations_clients.html', context) 
                            
            elif cuscat == 'NON-MEMBER':
                clients_filtered = clients.filter(category='NON-MEMBER', location=location)
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                

                context = {
                    'nav' : 'locations_clients', 'filter': 'on', 'referrer': referrer,
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
                    
                return render(request, 'locations_clients.html', context)  
                 
            else:
                clients_filtered = clients.filter(category='STAFF', location=location)
                private_filtered = clients_filtered.filter(sector='PRIVATE')
                public_filtered = clients_filtered.filter(sector='PUBLIC')
                withl_filtered = clients_filtered.filter(number_of_loans__gt=0)
                withoutl_filtered = clients_filtered.filter(number_of_loans=0)
                

                context = {
                    'nav' : 'locations_clients', 'filter': 'on', 'referrer': referrer,
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
                    
                return render(request, 'locations_clients.html', context) 
                
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
                    
                    return render(request, 'locations_clients.html', context)  
                            
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
                    
                    return render(request, 'locations_clients.html', context)  
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
                    
                    return render(request, 'locations_clients.html', context)
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
                    
                    return render(request, 'locations_clients.html', context)                       
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
                    
                    return render(request, 'locations_clients.html', context)   
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
                    
                    return render(request, 'locations_clients.html', context)
        
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
                
                return render(request, 'locations_clients.html', context)  
                            
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
                
                return render(request, 'locations_clients.html', context)                         
                
            
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
                return render(request, 'locations_clients.html', context)    
                    
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
                
                return render(request, 'locations_clients.html', context)  
            
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
                
                return render(request, 'locations_clients.html', context)        
          
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
            
            return render(request, 'locations_clients.html', context)                      
            
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
                
                return render(request, 'locations_clients.html', context)  
                            
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
                
                return render(request, 'locations_clients.html', context)                       
                            
    clients_filtered = clients
    members_filtered = clients.filter(category='MEMBER')  
    nonmembers_filtered = clients.filter(category='NON-MEMBER')
    private_filtered = clients.filter(sector='PRIVATE')
    public_filtered = clients.filter(sector='PUBLIC')
    withl_filtered = clients.filter(number_of_loans__gt=0)
    withoutl_filtered = clients.filter(number_of_loans=0)

    context = {
        'nav' : 'locations_clients',
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
    
    return render(request, 'locations_clients.html', context)

@admin_check
def locations_loans(request):

    domain = settings.DOMAIN
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    locations = Location.objects.all()
    loc_count = locations.count()
    
    loans = Loan.objects.prefetch_related('owner').filter(category="FUNDED").exclude(funded_category="COMPLETED").exclude(funded_category="ARCHIEVED")
    
    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('loantype') and request.POST.get('locationx'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            loantype = request.POST.get('loantype')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            start_date = start_date_entry 
            end_date = end_date_entry 

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('locations_loans')

            loans_filtered = loans.filter(loan_type=loantype, location = location, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_filtered = loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interest_filtered = loans_filtered.aggregate(sum=Sum('interest'))['sum']
            repayments_filtered = loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_filtered = loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            outstanding_filtered = loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                'nav' : 'locations_loans', 'filter':'on', 'referrer':referrer,'domain':domain,
                'location': location,
                'locations': locations,
                'loc_count': loc_count,
                
                'loans_filtered': loans_filtered,
                'funded_filtered': funded_filtered,
                'interest_filtered': interest_filtered,
                'repayments_filtered':repayments_filtered,
                'arrears_filtered':arrears_filtered,
                'outstanding_filtered':outstanding_filtered,        
            }
            
            return render(request, 'locations_loans.html', context)
        
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
                return redirect('locations_loans')

            loans_filtered = loans.filter(loan_type=loantype, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_filtered = loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interest_filtered = loans_filtered.aggregate(sum=Sum('interest'))['sum']
            repayments_filtered = loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_filtered = loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            outstanding_filtered = loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                'nav' : 'locations_loans', 'filter':'on', 'referrer':referrer,'domain':domain,
                'locations': locations,
                'loc_count': loc_count,
                
                'loans_filtered': loans_filtered,
                'funded_filtered': funded_filtered,
                'interest_filtered': interest_filtered,
                'repayments_filtered':repayments_filtered,
                'arrears_filtered':arrears_filtered,
                'outstanding_filtered':outstanding_filtered,        
            }
            
            return render(request, 'locations_loans.html', context)
            
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('locationx'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('running_loans')

            loans_filtered = loans.filter(location = location, funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_filtered = loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interest_filtered = loans_filtered.aggregate(sum=Sum('interest'))['sum']
            repayments_filtered = loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_filtered = loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            outstanding_filtered = loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                'nav' : 'locations_loans', 'filter':'on', 'referrer':referrer,'domain':domain,
                'location': location,
                'locations': locations,
                'loc_count': loc_count,
                
                'loans_filtered': loans_filtered,
                'funded_filtered': funded_filtered,
                'interest_filtered': interest_filtered,
                'repayments_filtered':repayments_filtered,
                'arrears_filtered':arrears_filtered,
                'outstanding_filtered':outstanding_filtered,        
            }
            
            return render(request, 'locations_loans.html', context)
        
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
                return redirect('locations_loans')

            loans_filtered = loans.filter(funding_date__gte = start_date, funding_date__lte = end_date).all()
            funded_filtered = loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interest_filtered = loans_filtered.aggregate(sum=Sum('interest'))['sum']
            repayments_filtered = loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_filtered = loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            outstanding_filtered = loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                'nav' : 'locations_loans', 'filter':'on', 'referrer':referrer,'domain':domain,
                'locations': locations,
                'loc_count': loc_count,
                
                'loans_filtered': loans_filtered,
                'funded_filtered': funded_filtered,
                'interest_filtered': interest_filtered,
                'repayments_filtered':repayments_filtered,
                'arrears_filtered':arrears_filtered,
                'outstanding_filtered':outstanding_filtered,        
            }
            
            return render(request, 'locations_loans.html', context)
        
        elif request.POST.get('loantype') and request.POST.get('locationx'): 

            loantype = request.POST.get('loantype')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            loans_filtered = loans.filter(loan_type=loantype, location = location).all()
            funded_filtered = loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interest_filtered = loans_filtered.aggregate(sum=Sum('interest'))['sum']
            repayments_filtered = loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_filtered = loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            outstanding_filtered = loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                'nav' : 'locations_loans', 'filter':'on', 'referrer':referrer,'domain':domain,
                'location': location,
                'locations': locations,
                'loc_count': loc_count,
                
                'loans_filtered': loans_filtered,
                'funded_filtered': funded_filtered,
                'interest_filtered': interest_filtered,
                'repayments_filtered':repayments_filtered,
                'arrears_filtered':arrears_filtered,
                'outstanding_filtered':outstanding_filtered,        
            }
            
            return render(request, 'locations_loans.html', context)
        
        elif request.POST.get('loantype'): 
            
            loantype = request.POST.get('loantype')

            loans_filtered = loans.filter(loan_type=loantype).all()
            funded_filtered = loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interest_filtered = loans_filtered.aggregate(sum=Sum('interest'))['sum']
            repayments_filtered = loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_filtered = loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            outstanding_filtered = loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                'nav' : 'locations_loans', 'filter':'on', 'referrer':referrer,'domain':domain,
                'locations': locations,
                'loc_count': loc_count,
                
                'loans_filtered': loans_filtered,
                'funded_filtered': funded_filtered,
                'interest_filtered': interest_filtered,
                'repayments_filtered':repayments_filtered,
                'arrears_filtered':arrears_filtered,
                'outstanding_filtered':outstanding_filtered,        
            }
            
            return render(request, 'locations_loans.html', context)
        
        elif request.POST.get('locationx'): 
            
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            loans_filtered = loans.filter(location = location).all()
            funded_filtered = loans_filtered.aggregate(sum=Sum('amount'))['sum']
            interest_filtered = loans_filtered.aggregate(sum=Sum('interest'))['sum']
            repayments_filtered = loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
            arrears_filtered = loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
            outstanding_filtered = loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
            
            context = {
                'nav' : 'locations_loans', 'filter':'on', 'referrer':referrer,'domain':domain,
                'location': location,
                'locations': locations,
                'loc_count': loc_count,
                
                'loans_filtered': loans_filtered,
                'funded_filtered': funded_filtered,
                'interest_filtered': interest_filtered,
                'repayments_filtered':repayments_filtered,
                'arrears_filtered':arrears_filtered,
                'outstanding_filtered':outstanding_filtered,        
            }
            
            return render(request, 'locations_loans.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('locations_loans')

    
    loans_filtered = Loan.objects.filter(category="FUNDED").exclude(funded_category="COMPLETED").exclude(funded_category="ARCHIEVED")
    funded_filtered = loans_filtered.aggregate(sum=Sum('amount'))['sum']
    interest_filtered = loans_filtered.aggregate(sum=Sum('interest'))['sum']
    repayments_filtered = loans_filtered.aggregate(sum=Sum('repayment_amount'))['sum']
    arrears_filtered = loans_filtered.aggregate(sum=Sum('total_arrears'))['sum']
    outstanding_filtered = loans_filtered.aggregate(sum=Sum('total_outstanding'))['sum']
    
    context = {
        'nav' : 'locations_loans',
        'locations': locations,
        'loc_count': loc_count,
        
        'loans_filtered': loans_filtered,
        'funded_filtered': funded_filtered,
        'interest_filtered': interest_filtered,
        'repayments_filtered':repayments_filtered,
        'arrears_filtered':arrears_filtered,
        'outstanding_filtered':outstanding_filtered,        
    }
    
    return render(request, 'locations_loans.html', context)

@admin_check
def locations_transactions(request):
    
    referrer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
    
    locations = Location.objects.all()
    loc_count = locations.count()
    
    transactions = Statement.objects.prefetch_related('loanref').all()
    
    if request.method=="POST":
        
        if request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('transtype') and request.POST.get('locationx'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            transtype = request.POST.get('transtype')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            start_date = start_date_entry 
            end_date = end_date_entry 

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('locations_transactions')

            trans_filtered = transactions.filter(type=transtype, loanref__location = location, date__gte = start_date, date__lte = end_date).order_by('-date')
            all_payments = trans_filtered.filter(type="PAYMENT")
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
            all_defaults = trans_filtered.filter(type="DEFAULT")
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
            all_credits = trans_filtered.filter(type="OTHER").all()
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
            
            context = {
                         'nav' : 'locations_transactions', 'filter':'on','referrer':referrer, 
                         'locations': locations,
                         'location': location,
                        'trans_filtered': trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'locations_transactions.html', context)
        
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
                return redirect('locations_transactions')

            trans_filtered = transactions.filter(type=transtype, date__gte = start_date, date__lte = end_date).order_by('-date')
            all_payments = trans_filtered.filter(type="PAYMENT")
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
            all_defaults = trans_filtered.filter(type="DEFAULT")
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
            all_credits = trans_filtered.filter(type="OTHER").all()
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
            
            context = {
                         'nav' : 'locations_transactions', 'filter':'on','referrer':referrer, 
                         'locations': locations,
                         
                        'trans_filtered': trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'locations_transactions.html', context)
            
        elif request.POST.get('startdate') and request.POST.get('enddate') and request.POST.get('locationx'):
            start_date_entry = request.POST.get('startdate')
            end_date_entry = request.POST.get('enddate')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            start_date = start_date_entry 
            end_date = end_date_entry

            strip_start_date = start_date.split('-')
            strip_end_date = end_date.split('-')

            date_start_date = datetime.date(int(strip_start_date[0]), int(strip_start_date[1]), int(strip_start_date[2]))
            date_end_date = datetime.date(int(strip_end_date[0]), int(strip_end_date[1]), int(strip_end_date[2]))
            
            if date_start_date > date_end_date:
                messages.error(request, 'End date must be after Start date!')
                return redirect('locations_transactions')

            trans_filtered = transactions.filter(loanref__location = location, date__gte = start_date, date__lte = end_date).order_by('-date')
            all_payments = trans_filtered.filter(type="PAYMENT")
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
            all_defaults = trans_filtered.filter(type="DEFAULT")
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
            all_credits = trans_filtered.filter(type="OTHER").all()
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
            
            context = {
                         'nav' : 'locations_transactions', 'filter':'on','referrer':referrer, 
                         'locations': locations,
                         'location': location,
                        'trans_filtered': trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum, 
                    }  
            
            return render(request, 'locations_transactions.html', context)
        
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
                return redirect('locations_transactions')

            trans_filtered = transactions.filter(date__gte = start_date, date__lte = end_date).order_by('-date')
            all_payments = trans_filtered.filter(type="PAYMENT")
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
            all_defaults = trans_filtered.filter(type="DEFAULT")
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
            all_credits = trans_filtered.filter(type="OTHER").all()
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
            
            context = {
                         'nav' : 'locations_transactions', 'filter':'on','referrer':referrer, 
                         'locations': locations,
                       
                        'trans_filtered': trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'locations_transactions.html', context)
        
        elif request.POST.get('transtype') and request.POST.get('locationx'): 

            transtype = request.POST.get('transtype')
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            trans_filtered = transactions.filter(type=transtype, loanref__location = location).order_by('-date')
            all_payments = trans_filtered.filter(type="PAYMENT")
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
            all_defaults = trans_filtered.filter(type="DEFAULT")
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
            all_credits = trans_filtered.filter(type="OTHER").all()
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
            
            context = {
                         'nav' : 'locations_transactions', 'filter':'on','referrer':referrer, 
                         'locations': locations,
                         'location': location,
                        'trans_filtered': trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'locations_transactions.html', context)
        
        elif request.POST.get('transtype'): 
            
            transtype = request.POST.get('transtype')

            trans_filtered = transactions.filter(type=transtype).order_by('-date')
            all_payments = trans_filtered.filter(type="PAYMENT")
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
            all_defaults = trans_filtered.filter(type="DEFAULT")
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
            all_credits = trans_filtered.filter(type="OTHER").all()
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
            
            context = {
                         'nav' : 'locations_transactions', 'filter':'on','referrer':referrer,
                         'locations': locations,
                        
                        'trans_filtered': trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'locations_transactions.html', context)
        
        elif request.POST.get('locationx'): 
            
            locationx = request.POST.get('locationx')
            location = Location.objects.get(name=locationx)

            trans_filtered = transactions.filter(loanref__location = location).order_by('-date')
            all_payments = trans_filtered.filter(type="PAYMENT")
            payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
            all_defaults = trans_filtered.filter(type="DEFAULT")
            defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
            all_credits = trans_filtered.filter(type="OTHER").all()
            credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
            
            context = {
                         'nav' : 'locations_transactions', 'filter':'on','referrer':referrer, 
                         'locations': locations,
                         'location': location,
                        'trans_filtered': trans_filtered,
                        'all_payments': all_payments,
                        'payments_sum':payments_sum,
                        'all_defaults': all_defaults,
                        'defaults_sum':defaults_sum,
                        'all_credits':all_credits,
                        'credits_sum': credits_sum,
                        
                    }  
            
            return render(request, 'locations_transactions.html', context)
        
        else:
            messages.error(request, 'You did not select any filter', extra_tags='warning')
            return redirect('locations_loans')

    
    trans_filtered = transactions.order_by('-date')
    all_payments = trans_filtered.filter(type="PAYMENT")
    payments_sum = all_payments.aggregate(sum=Sum('debit'))['sum']
    all_defaults = trans_filtered.filter(type="DEFAULT")
    defaults_sum = all_defaults.aggregate(sum=Sum('default_amount'))['sum']
    all_credits = trans_filtered.filter(type="OTHER").all()
    credits_sum = all_credits.aggregate(sum=Sum('credit'))['sum']
    
    context = {
                'nav' : 'locations_transactions', 
                'locations': locations,
                
                'trans_filtered': trans_filtered,
                'all_payments': all_payments,
                'payments_sum':payments_sum,
                'all_defaults': all_defaults,
                'defaults_sum':defaults_sum,
                'all_credits':all_credits,
                'credits_sum': credits_sum,
                
            }  
    
    return render(request, 'locations_transactions.html', context)
