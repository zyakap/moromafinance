from django.urls import path, re_path
from custom.views import home, about, contact, dcc, demo
from . import views
from .functions import register_additional_loan, trupng_payment, register_default, register_loan_holiday, set_repayment_dates, add_2_set_repayment_dates, classify_loan_complete,consolidate_loans, targeted_consolidate_loans


urlpatterns = [
    #functions
    path('direct_loan_update/', views.direct_loan_update, name='direct_loan_update'),
    path('upload_new_loan/', views.upload_new_loan, name='upload_new_loan'),
    path('upload_payments/', views.upload_payments, name='upload_payments'),
    path('cf/', views.custom_functions, name='custom_functions'),
    path('set_repayment_dates/', set_repayment_dates, name='set_repayment_dates'),
    path('add_2_set_repayment_dates/', add_2_set_repayment_dates, name='add_2_set_repayment_dates'),
    path('classify_loan_complete/', classify_loan_complete, name='classify_loan_complete'),
    path('consolidate_loans/', consolidate_loans, name='consolidate_loans'),
    path('t_consolidate_loans/<str:first_name_part>/<str:last_name_part>/', targeted_consolidate_loans, name='consolidate_loans'),
    path('register-loan-holiday/', register_loan_holiday, name='register_loan_holiday'),
    path('register-default/', register_default, name='register_default'),
    path('register-payment/<str:loan_ref>/', trupng_payment, name='trupng_payment'),
    path('register-additional-loan/', register_additional_loan, name='register_additional_loan'),
    
    #from loanmasta futher development
    path('propose-new-arrangement/<int:running_loan_id>/<int:new_loan_id>/', views.propose_new_arrangement, name='propose_new_arrangement'),
    path('propose-new-arrangement-staff/<int:running_loan_id>/<int:new_loan_id>/', views.propose_new_arrangement_staff, name='propose_new_arrangement_staff'),
    path('pnat/', views.propose_new_arrangement_test, name='propose_new_arrangement_test'),
    #path('fund-additional-loan/', views.fund_additional_loan, name='fund_additional_loan'),

    path('add-additional-loan/', views.add_additional_loan, name='add_additional_loan'),
    path('add-new-loan/', views.add_new_loan, name='add_new_loan'),
    path('end-loan/', views.end_loan, name='end_loan'),

    
]