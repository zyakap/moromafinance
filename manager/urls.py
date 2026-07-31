from django.urls import path
from . import views

app_name = 'manager'

urlpatterns = [
    path('dashboard/', views.manager_dashboard, name='dashboard'),
    path('pending-loans/', views.pending_loans, name='pending_loans'),
    path('loan-approval/<int:loan_id>/', views.loan_approval, name='loan_approval'),
    path('pending-payments/', views.pending_payments, name='pending_payments'),
    path('payment-approval/<int:payment_id>/', views.payment_approval, name='payment_approval'),
    path('reports/', views.reports, name='reports'),
]
