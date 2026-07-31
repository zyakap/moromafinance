from django.urls import path, re_path

from accounts import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('credit_rating/', views.credit_rating, name='credit_rating'),
    path('terms_credit_consent/', views.terms_credit_consent, name='terms_credit_consent'),
    path('tc_consent/', views.tc_consent, name='tc_consent'),
    path('support/', views.support, name='support'),
    path('login_user/', views.login_user, name='login_user'),
    path('logout/', views.logout_user, name='logout_user'),
    path('profile/', views.profile, name='profile'),
     path('sme_profile/', views.sme_profile, name='sme_profile'),
    path('activate_user/<int:uid>/', views.activate_user, name='activate_user'),
    path('deactivate_user/<int:uid>/', views.deactivate_user, name='deactivate_user'),
    path('suspend_user/<int:uid>/', views.suspend_user, name='suspend_user'),
    path('edit_profile/', views.edit_profile_wizard, name='edit_profile_wizard'),
    path('edit_personalinfo/', views.edit_personalinfo, name='edit_personalinfo'),

    path('edit_bankinfo/', views.edit_bankinfo, name='edit_bankinfo'),
    path('edit_bankinfo2/', views.edit_bankinfo2, name='edit_bankinfo2'),
    path('edit_addressinfo/', views.edit_addressinfo, name='edit_addressinfo'),
    path('edit_useruploads/', views.edit_useruploads, name='edit_useruploads'),
    path('edit_work_uploads/', views.edit_work_uploads, name='edit_work_uploads'),
    path('edit_required_uploads/', views.edit_required_uploads, name='edit_required_uploads'),
    #sme profile
    path('edit_sme_profile/', views.edit_sme_profile, name='edit_sme_profile'),
    path('edit_sme_profile_bank/', views.edit_sme_profile_bank, name='edit_sme_profile_bank'),
    path('edit_sme_profile_uploads/', views.edit_sme_profile_uploads, name='edit_sme_profile_uploads'),
    
    path('edit_loan_statement_uploads/', views.edit_loan_statement_uploads, name='edit_loan_statement_uploads'),
    path('edit_employerinfo/', views.edit_employerinfo, name='edit_employerinfo'),
    path('edit_jobinfo/', views.edit_jobinfo, name='edit_jobinfo'),
    #credit assessment
    path('edit_refereeinfo/', views.edit_refereeinfo, name='edit_refereeinfo'),
    path('edit_previousemployer/', views.edit_previousemployer, name='edit_previousemployer'),
    path('edit_statement_of_position/', views.edit_statement_of_position, name='edit_statement_of_position'),
    path('statement_of_position/', views.statement_of_position, name='statement_of_position'),
    path('activation_sent/', views.activation_sent, name="activation_sent"),
    path('activate/<slug:uidb64>/<slug:token>/', views.activate, name='activate'),
    path('invalid/', views.activation_invalid, name="activation_invalid"),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('instructions/', views.user_instructions, name='user_instructions'),
    path('reset_password/', views.reset_password, name='reset_password'),
    path('reset_link_sent/', views.reset_link_sent, name='reset_link_sent'),
    path('password_reset/<slug:uidb64>/<slug:token>/', views.password_reset, name='password_reset'),
    path('messages_user/', views.messages_user, name='messages_user'),   
]

