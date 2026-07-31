from django.urls import path
from . import views

urlpatterns = [
    path('', views.referrers_list, name='referrers_list'),
    path('add/', views.add_referrer, name='add_referrer'),
    path('<int:rid>/', views.view_referrer, name='view_referrer'),
    path('<int:rid>/edit/', views.edit_referrer, name='edit_referrer'),
    path('<int:rid>/toggle/', views.toggle_referrer_status, name='toggle_referrer_status'),
    path('<int:rid>/allocate/', views.allocate_clients, name='allocate_clients'),
    path('<int:rid>/remove/<int:record_id>/', views.remove_allocation, name='remove_allocation'),
    path('<int:rid>/pay-all/', views.pay_all_outstanding, name='pay_all_outstanding'),
    path('commissions/', views.commission_overview, name='commission_overview'),
    path('commissions/pay/<int:rid>/<str:month_str>/', views.mark_month_paid, name='mark_month_paid'),
    path('payment-run/', views.payment_run, name='payment_run'),
    path('settings/', views.referral_settings, name='referral_settings'),
    path('assign/', views.assign_referrer, name='assign_referrer'),
]
