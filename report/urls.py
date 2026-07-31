from django.urls import path
from . import views
from . import advanced_reports

urlpatterns = [
    path('view_report/', views.view_reports, name='view_reports'),
    path('overview/', views.report_overview, name='report_overview'),
    path('all/', advanced_reports.report_catalog, name='report_catalog'),
    path('monthly_collections_report/', views.monthly_collections_report, name='monthly_collections_report'),
    path('cash-flow/', views.cash_flow, name='cash_flow'),
    path('dcc/', views.dcc_report, name='dcc_report'),
    path('<slug:slug>/', advanced_reports.report_detail, name='report_detail'),
]
