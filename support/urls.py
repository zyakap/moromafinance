from django.urls import path
from .views import (
    user_support, create_ticket, view_ticket, close_ticket,
    support_tickets, staff_view_ticket, staff_close_ticket,
)

urlpatterns = [
    # users
    path('user_support/', user_support, name='user_support'),
    path('create/ticket/', create_ticket, name='create_ticket'),
    path('ticket/view/<str:ref>/', view_ticket, name='view_ticket'),
    path('ticket/close/<str:ref>/', close_ticket, name='close_ticket'),

    # staff
    path('tickets/', support_tickets, name='support_tickets'),
    path('tickets/view/<str:ref>/', staff_view_ticket, name='staff_view_ticket'),
    path('tickets/close/<str:ref>/', staff_close_ticket, name='staff_close_ticket'),
]
