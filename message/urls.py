from django.urls import path
from .views import create_message, view_message, delete_message, user_view_message, track_email_open, usermessages, delivery_report, delivery_status, delivering_message

urlpatterns = [

    #user urls
    path('view/<int:mid>/', user_view_message, name='user_view_message'),
    
    #staff urls
    path('usermessages/', usermessages, name='usermessages'),
    path('view_message/<int:mid>/', view_message, name='view_message'),
    path('delete/<int:mid>/', delete_message, name='delete_message'),
    path('create/', create_message, name='create_message'),
    path('delivering/message/<int:mid>/', delivering_message, name='delivering_message'),
    path('delivery/report/<int:mid>/', delivery_report, name='delivery_report'),
    path('delivery/status/<int:mid>/', delivery_status, name='delivery_status'),
    
    #admin urls

    #other urls

    path('track_email_open/<str:message_id>/', track_email_open, name='track_email_open'),

]
