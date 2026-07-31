from django.urls import path
from . import views

urlpatterns = [
    path('profiles/', views.userprofiles, name='userprofiles'),
    path('loans/', views.allloans, name='allloans'),
    path('statements/', views.statements, name='statements'),
    path('upload/<str:uid>/<str:field>/', views.upload_file, name='api_upload_file'),
]
