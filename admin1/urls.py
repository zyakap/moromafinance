from django.urls import path, re_path

from admin1.mainView import (admin_settings_general, admin_settings_appearance, admin_settings_form, admin_settings_date, admin_settings_loans, admin_settings_banks, admin_settings_employers, admin_settings_credit, admin_settings_dcc, admin_settings_roles, admin_settings_tc_contracts, admin_settings_credit_assessment, admin_dashboard, statements,
                          defaults, DownloadApplicationByAdmin, create_default, reverse_last_statement, apply_advance_to_missed_payment, fix_loan_defaults, DownloadLoanStatement, reports,
                          payment_uploads, support_system_admin, admin_instructions, admin_run_defaults, process_upload,
                          download_las, download_cdn, global_search,
                        )

from admin1.views.loansView import ( loans, pending_loans, running_loans, defaulted_loans,
                          all_loans, completed_loans, recovery_loans, awaiting_refund_loans, view_loan, approve, decline, funding_list, fund_loan, cancel_funding, funding_receipt_upload

                        )

from admin1.views.transactionsView import ( transactions, transactions_all, transactions_defaults, transactions_expected, transactions_payments)

from admin1.views.clientsView import (clients, clients_all, clients_withloan,clients_pending, clients_flagged, clients_suspended, view_client, inform_account_activation, clients_pending_activation, toggle_work_email_notify)
from admin1.views.clientFilesView import client_files, loan_files
from admin1.views.employerView import (employer_overview, loans_by_employer, loans_by_employer_excel,
                          loans_by_employer_txt, loans_by_employer_pdf,
                          payroll_contacts, payroll_contacts_excel, payroll_contacts_pdf)

from admin1.views.locationsView import (locations, locations_clients, locations_loans, locations_transactions)
from message.views import messages_admin, create_message_admin, message_drafts_admin, delivery_reports_admin, delivery_statuses_admin
from support.views import admin_view_ticket, admin_close_ticket, admin_reopen_ticket, support_tickets_admin, closed_tickets_admin, open_tickets_admin, pending_tickets_admin
from report.advanced_reports import report_catalog
from admin1.views.alescoView import (alesco_update, alesco_confirm, alesco_data, alesco_confirm_line, alesco_confirm_all,
                                      alesco_rollback_line, alesco_rollback, alesco_cancel, alesco_unmatched)
from admin1.views.creditsView import client_credits, attribute_credit_and_close
from admin1.views.staffSettingsView import admin_settings_staff
from admin1.views.regenerateView import regenerate_schedule
from admin1.views.sendDocView import send_doc_to_client

urlpatterns = [
    
    path('settings/', admin_settings_general, name='admin_settings'),
    path('settings/general/', admin_settings_general, name='admin_settings_general'),
    path('settings/appearance/', admin_settings_appearance, name='admin_settings_appearance'),
    path('settings/form/', admin_settings_form, name='admin_settings_form'),
    path('settings/date/', admin_settings_date, name='admin_settings_date'),
    path('settings/loans/', admin_settings_loans, name='admin_settings_loans'),
    path('settings/banks/', admin_settings_banks, name='admin_settings_banks'),
    path('settings/employers/', admin_settings_employers, name='admin_settings_employers'),
    path('settings/credit/', admin_settings_credit, name='admin_settings_credit'),
    path('settings/dcc/', admin_settings_dcc, name='admin_settings_dcc'),
    path('settings/roles/', admin_settings_roles, name='admin_settings_roles'),
    path('settings/staff/', admin_settings_staff, name='admin_settings_staff'),
    path('settings/tc-contracts/', admin_settings_tc_contracts, name='admin_settings_tc_contracts'),
    path('settings/credit-assessment/', admin_settings_credit_assessment, name='admin_settings_credit_assessment'),
    path('dashboard/', admin_dashboard, name='admin_dashboard'),
    path('loans/', loans, name='loans'),
    path('loans/all', all_loans, name='all_loans'),
    path('loans/pending', pending_loans, name='pending_loans'),
    path('loans/running', running_loans, name='running_loans'),
    path('loans/defaulted', defaulted_loans, name='defaulted_loans'),
    path('loans/completed', completed_loans, name='completed_loans'),
    path('loans/recovery', recovery_loans, name='recovery_loans'),
    path('loans/awaiting-refund', awaiting_refund_loans, name='awaiting_refund_loans'),
    path('loans/funding_list', funding_list, name='funding_list'),
    path('loans/fund_loan/<str:loanref>/', fund_loan, name='fund_loan'),
    path('loans/cancel_funding/<str:loanref>/', cancel_funding, name='cancel_funding'),

    path('admin_run_defaults/', admin_run_defaults, name="admin_run_defaults"),
   
    # from transactions view
    path('transactions/', transactions, name='transactions'),
    path('transactions/all', transactions_all, name='transactions_all'),
    path('transactions/payments', transactions_payments, name='transactions_payments'),
    path('transactions/defaults', transactions_defaults, name='transactions_defaults'),
    path('transactions/expected', transactions_expected, name='transactions_expected'),

    # Alesco payroll update
    path('transactions/alesco/', alesco_update, name='alesco_update'),
    path('transactions/alesco/<int:run_id>/confirm/', alesco_confirm, name='alesco_confirm'),
    path('transactions/alesco/<int:run_id>/data/', alesco_data, name='alesco_data'),
    path('transactions/alesco/line/<int:line_id>/confirm/', alesco_confirm_line, name='alesco_confirm_line'),
    path('transactions/alesco/<int:run_id>/confirm-all/', alesco_confirm_all, name='alesco_confirm_all'),
    path('transactions/alesco/line/<int:line_id>/rollback/', alesco_rollback_line, name='alesco_rollback_line'),
    path('transactions/alesco/<int:run_id>/rollback/', alesco_rollback, name='alesco_rollback'),
    path('transactions/alesco/<int:run_id>/cancel/', alesco_cancel, name='alesco_cancel'),
    path('transactions/alesco/unmatched/', alesco_unmatched, name='alesco_unmatched'),
    path('transactions/client-credits/', client_credits, name='client_credits'),
    path('loans/<str:loan_ref>/attribute-credit-close/', attribute_credit_and_close, name='attribute_credit_and_close'),

    path('statements/', statements, name='statements'),
    path('defaults/', defaults, name='defaults'),
    path('messages/', messages_admin, name='messages_admin'),
    path('message/create/', create_message_admin, name='create_message_admin'),
    path('message/drafts/', message_drafts_admin, name='message_drafts_admin'),
    path('message/delivery_reports/', delivery_reports_admin, name='delivery_reports_admin'),
    path('message/delivery_statuses/', delivery_statuses_admin, name='delivery_statuses_admin'),

    path('support/tickets/', support_tickets_admin, name='support_tickets_admin'),
    path('support/tickets/pending/', pending_tickets_admin, name='pending_tickets_admin'),
    path('support/tickets/open/', open_tickets_admin, name='open_tickets_admin'),
    path('support/tickets/closed/', closed_tickets_admin, name='closed_tickets_admin'),
    path('support/tickets/view/<str:ref>/', admin_view_ticket, name='admin_view_ticket'),
    path('support/tickets/close/<str:ref>/', admin_close_ticket, name='admin_close_ticket'),
    path('support/tickets/reopen/<str:ref>/', admin_reopen_ticket, name='admin_reopen_ticket'),


    path('admin_instructions/', admin_instructions, name='admin_instructions'),
    path('search/', global_search, name='global_search'),
    path('process-payment/<str:ref>/', process_upload, name='process_upload'),
    
    
    
    #from locations view
    path('locations/', locations, name='locations'),
    path('locations/clients', locations_clients, name='locations_clients'),
    path('locations/loans', locations_loans, name='locations_loans'),
    path('locations/transactions', locations_transactions, name='locations_transactions'),
    
    
    #from clients view
    path('clients/', clients, name='clients'),
    path('clients/inform_client/<int:uid>/', inform_account_activation, name='inform_account_activation'),
    path('clients/all', clients_all, name='clients_all'),
    path('clients/withloan', clients_withloan, name='clients_withloan'),
    path('clients/pending', clients_pending, name='clients_pending'),
    path('clients/pending_activation', clients_pending_activation, name='clients_pending_activation'),
    
    path('clients/flagged', clients_flagged, name='clients_flagged'),
    path('clients/suspended', clients_suspended, name='clients_suspended'),
    re_path(r'clients/view_client/(?P<uid>[0-9]+)/$', view_client, name='view_client'),
    path('clients/<int:uid>/toggle-work-email/', toggle_work_email_notify, name='toggle_work_email_notify'),
    
    path('loans/<str:loan_ref>/', view_loan, name='view_loan'),
    path('loans/<str:loan_ref>/regenerate-dates/', regenerate_schedule, name='regenerate_schedule'),
    path('loans/<str:loan_ref>/send/<str:doc>/', send_doc_to_client, name='send_doc_client'),
    re_path(r'^approve/([a-zA-Z]+[0-9]+[A-Z]+[0-9]+)/$', approve, name='approve'),
    path('decline/<str:loan_ref>/', decline, name='decline'),
    re_path(r'download/(?P<loanref>[a-zA-Z]+[0-9]+[A-Z]+[0-9]+)/$', DownloadApplicationByAdmin.as_view(), name="download_loan_application"),
    
    path('create-default/<str:loan_ref>/', create_default, name="create_default"),
    path('reverse-last-statement/<str:loan_ref>/', reverse_last_statement, name="reverse_last_statement"),
    path('apply-advance-to-missed-payment/<str:loan_ref>/', apply_advance_to_missed_payment, name="apply_advance_to_missed_payment"),
    path('fix-loan-defaults/<str:loan_ref>/', fix_loan_defaults, name="fix_loan_defaults"),
    path('client-files/<int:uid>/', client_files, name="client_files"),
    path('loan-files/', loan_files, name="loan_files"),
    path('loan-files/<str:loan_ref>/', loan_files, name="loan_files"),
    path('dls/<str:loanref>/', DownloadLoanStatement.as_view(), name="download_loan_statement_admin"),
    path('loans/<str:loan_ref>/las/', download_las, name='download_las'),
    path('loans/<str:loan_ref>/cdn/', download_cdn, name='download_cdn'),
    
    path('payment_uploads/', payment_uploads, name='payment_uploads'),
    path('reports/', report_catalog, name='reports'),
    path('loan/funding_receipt_upload/<str:loanref>/', funding_receipt_upload, name='funding_receipt_upload'),
    
    #employerView
    path('employer-overview/', employer_overview, name='employer_overview'),
    path('employer/loans/', loans_by_employer, name='loans_by_employer'),
    path('employer/loans/export/excel/', loans_by_employer_excel, name='loans_by_employer_excel'),
    path('employer/loans/export/txt/', loans_by_employer_txt, name='loans_by_employer_txt'),
    path('employer/loans/export/pdf/', loans_by_employer_pdf, name='loans_by_employer_pdf'),
    path('employer/payroll-contacts/', payroll_contacts, name='payroll_contacts'),
    path('employer/payroll-contacts/export/excel/', payroll_contacts_excel, name='payroll_contacts_excel'),
    path('employer/payroll-contacts/export/pdf/', payroll_contacts_pdf, name='payroll_contacts_pdf'),

]
