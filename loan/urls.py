from django.urls import path, re_path
from loan.views import (loan_requirements, loan_application, DownloadApplication,DownloadStatement,
                        inactive, suspended, defaulted,
                        dcc_flagged, cdb_flagged,
                        agree_to_tc, cancel_loan, myloans, viewmyloan, mystatements, upload_payment, payment, repayment_week,
                        download_las_user, allocate_advance_to_arrears,
                        )

from loan.functions import update_defaults

urlpatterns = [
    path("apply/", loan_application, name="loan_application"),
    path('inactive/', inactive, name='inactive'),
    path('suspended/', suspended, name='suspended'),
    path('defaulted/', defaulted, name='defaulted'),
    path('dcc_flagged/', dcc_flagged, name='dcc_flagged'),
    path('cdb_flagged/', cdb_flagged, name='cdb_flagged'),
    path('myloans/', myloans, name='myloans'),
    path('mystatements/', mystatements, name='mystatements'),
    path('loan_requirements/', loan_requirements, name='loan_requirements'),
    
    path('agree_to_tc/<slug:uidb64>/<slug:token>/', agree_to_tc, name='agree_to_tc'),
    re_path(r'^cancel_loan/([a-zA-Z]+[0-9]+[A-Z]+[0-9]+)/$', cancel_loan, name='cancel_loan'),
    re_path(r'^myloan/([a-zA-Z]+[0-9]+[A-Z]+[0-9]+)/$', viewmyloan, name='viewmyloan'),
    path('upload-payment/<str:loan_ref>/', upload_payment, name='upload_payment'),
    path('payment/<str:loan_ref>/', payment, name="payment"),
    path('allocate-advance/<str:loan_ref>/', allocate_advance_to_arrears, name="allocate_advance_to_arrears"),

    #new functions

    path('repayment_week/', repayment_week, name='repayment_week'),
    path('update-defaults/', update_defaults, name="update_defaults"),

    #download functions
    path(r'dla/<str:loanref>/', DownloadApplication.as_view(), name="download_loan_application"),
    path(r'dls/<str:loanref>/', DownloadStatement.as_view(), name="download_loan_statement"),
    path(r'las/<str:loanref>/', download_las_user, name="download_las_user"),
]