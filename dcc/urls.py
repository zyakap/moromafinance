from django.urls import path
from . import views

urlpatterns = [
    path('credit-check/<int:uid>/', views.client_credit_check, name='dcc_credit_check'),
    path('unlock/<int:uid>/', views.unlock_client_credit, name='dcc_unlock'),
    path('reset-indcc/', views.reset_indcc, name='reset_indcc'),
]
