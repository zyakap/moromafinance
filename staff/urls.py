from django.urls import path, re_path
from . import views
from loan.views import staff_enter_payment
from staff.alesco_views import (staff_alesco_update, staff_alesco_confirm, staff_alesco_data,
                                staff_alesco_confirm_line, staff_alesco_confirm_all,
                                staff_alesco_rollback_line, staff_alesco_rollback, staff_alesco_cancel,
                                staff_regenerate_schedule, staff_alesco_unmatched)
from staff.credit_views import staff_client_credits, staff_attribute_credit_and_close
from staff.blackrose_views import (blackrose_statements, blackrose_review, blackrose_discard,
                                   blackrose_import_all)

urlpatterns = [
    
    path('dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('instructions/', views.staff_instructions, name='staff_instructions'),
    path('api/client-loans/<int:uid>/', views.client_loan_status_api, name='client_loan_status_api'),
    path('adduser/', views.add_user, name='add_user'),
    path('userloans/', views.userloans, name='userloans'),
    path('userstatements/', views.userstatements, name='userstatements'),
    path('usermembers/', views.usermembers, name='usermembers'),
    path('usersmes/', views.usersmes, name='usersmes'),
    path('add_sme_profile/', views.add_sme_profile, name='add_sme_profile'),
    path('view_member/<int:uid>/', views.view_member, name='view_member'),
    path('edit_profile/<int:uid>/', views.edit_profile_wizard_staff, name='edit_profile_wizard_staff'),
    path('edit_personalinfo_staff/<int:uid>/', views.edit_personalinfo_staff, name='edit_personalinfo_staff'),
    path('edit_bankinfo_staff/<int:uid>/', views.edit_bankinfo_staff, name='edit_bankinfo_staff'),
    path('edit_bankinfo2_staff/<int:uid>/', views.edit_bankinfo2_staff, name='edit_bankinfo2_staff'),
    path('edit_addressinfo_staff/<int:uid>/', views.edit_addressinfo_staff, name='edit_addressinfo_staff'),
    path('edit_useruploads_staff/<int:uid>/', views.edit_useruploads_staff, name='edit_useruploads_staff'),
    path('edit_work_uploads_staff/<int:uid>/', views.edit_work_uploads_staff, name='edit_work_uploads_staff'),
    path('edit_required_uploads_staff/<int:uid>/', views.edit_required_uploads_staff, name='edit_required_uploads_staff'),
    #sme profile
    #sme profile
    path('view_sme_profile_staff/<int:smid>/', views.view_sme_profile_staff, name='view_sme_profile_staff'),
    path('edit_sme_profile_staff/<int:uid>/', views.edit_sme_profile_staff, name='edit_sme_profile_staff'),
    path('edit_sme_profile_bank_staff/<int:uid>/', views.edit_sme_profile_bank_staff, name='edit_sme_profile_bank_staff'),
    path('edit_sme_profile_uploads_staff/<int:uid>/', views.edit_sme_profile_uploads_staff, name='edit_sme_profile_uploads_staff'),
    path('edit_loan_statement_uploads_staff/<int:uid>/', views.edit_loan_statement_uploads_staff, name='edit_loan_statement_uploads_staff'),
    path('edit_employerinfo_staff/<int:uid>/', views.edit_employerinfo_staff, name='edit_employerinfo_staff'),
    path('edit_jobinfo_staff/<int:uid>/', views.edit_jobinfo_staff, name='edit_jobinfo_staff'),
    #credit assessment
    path('edit_refereeinfo_staff/<int:uid>/', views.edit_refereeinfo_staff, name='edit_refereeinfo_staff'),
    path('edit_previousemployer_staff/<int:uid>/', views.edit_previousemployer_staff, name='edit_previousemployer_staff'),
    path('add_statement_of_position_staff/<int:uid>/', views.add_statement_of_position_staff, name='add_statement_of_position_staff'),
    path('edit_statement_of_position_staff/<int:uid>/', views.edit_statement_of_position_staff, name='edit_statement_of_position_staff'),
   
   #loan functions
   
    path('userloans/unfinished/', views.userloans_unfinished, name='userloans_unfinished'),
    path('userloans/under_review/', views.userloans_review, name='userloans_review'),
    path('userloans/pending/', views.userloans_pending, name='userloans_pending'),
    path('userloans/all/', views.userloans_all, name='userloans_all'),
    path('userloans/create/', views.create_loan, name='create_loan'),
    path('userloans/client-has-loan/<int:uid>/', views.client_has_loan, name='client_has_loan'),
    path('userloans/view_loan/<str:loan_ref>/', views.view_loan_staff, name='view_loan_staff'),
    path('userloans/regenerate-dates/<str:loan_ref>/', staff_regenerate_schedule, name='staff_regenerate_schedule'),
    path('userloans/<str:loan_ref>/las/', views.download_las_staff, name='download_las_staff'),
    path('userloans/<str:loan_ref>/cdn/', views.download_cdn_staff, name='download_cdn_staff'),
    path('userloans/review_loan/<str:loan_ref>/', views.review_loan, name='review_loan'),
    path('userloans/tc_upload/<str:loan_ref>/', views.tc_upload, name='tc_upload'),
    path('userloans/loan_req_matrix/', views.loan_req_matrix, name='loan_req_matrix'),
    path('usercredit/', views.usercredit, name='usercredit'),
    path('enter_payment/', staff_enter_payment, name='staff_enter_payment'),

    #imports
    path('existing-loan-functions/', views.existing_loan_functions, name='existing_loan_functions'),
    path('addexistingloan/', views.add_existing_loan, name='add_existing_loan' ),
    path('addexistingstatement/', views.add_existing_loan_statement, name='add_existing_loan_statement' ),
    path('uploadstatement/loan/<str:loanref>/', views.upload_statement, name='upload_statement' ),
    path('send_repayment_reminder/', views.send_repayment_reminder, name='send_repayment_reminder'),
    path('send_loan_repayment_reminder/<str:loanref>/', views.send_loan_repayment_reminder, name='send_loan_repayment_reminder'),

    path('run_defaults/', views.run_defaults, name='run_defaults'),
    path('upload-statements/', views.add_existing_statements, name='add_existing_statements'),

    # Blackrose LMS migration
    path('blackrose/', blackrose_statements, name='blackrose_statements'),
    path('blackrose/import-all/', blackrose_import_all, name='blackrose_import_all'),
    path('blackrose/<int:pk>/', blackrose_review, name='blackrose_review'),
    path('blackrose/<int:pk>/discard/', blackrose_discard, name='blackrose_discard'),

    # Alesco payroll update
    path('alesco/', staff_alesco_update, name='staff_alesco_update'),
    path('alesco/<int:run_id>/confirm/', staff_alesco_confirm, name='staff_alesco_confirm'),
    path('alesco/<int:run_id>/data/', staff_alesco_data, name='staff_alesco_data'),
    path('alesco/line/<int:line_id>/confirm/', staff_alesco_confirm_line, name='staff_alesco_confirm_line'),
    path('alesco/<int:run_id>/confirm-all/', staff_alesco_confirm_all, name='staff_alesco_confirm_all'),
    path('alesco/line/<int:line_id>/rollback/', staff_alesco_rollback_line, name='staff_alesco_rollback_line'),
    path('alesco/<int:run_id>/rollback/', staff_alesco_rollback, name='staff_alesco_rollback'),
    path('alesco/<int:run_id>/cancel/', staff_alesco_cancel, name='staff_alesco_cancel'),
    path('alesco/unmatched/', staff_alesco_unmatched, name='staff_alesco_unmatched'),
    path('client-credits/', staff_client_credits, name='staff_client_credits'),
    path('userloans/view_loan/<str:loan_ref>/attribute-credit-close/', staff_attribute_credit_and_close, name='staff_attribute_credit_and_close'),

    
    
]
