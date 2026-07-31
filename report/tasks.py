import json
import logging
from django.conf import settings
from django.db.models import Sum

logger = logging.getLogger(__name__)
from django.shortcuts import render
from time import sleep
from celery import shared_task
from celery.result import AsyncResult

from accounts.models import UserProfile
from loan.models import Loan

from wkhtmltopdf.views import PDFTemplateResponse

#EMAIL SETTINGS
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.utils.html import strip_tags
from django.template import Template, Context
from admin1.models import AdminSettings

#generate pdf on the go
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
import subprocess

def generate_pdf(templatefile, data):
    from moromafinance.pdf import render_pdf
    return render_pdf(templatefile, data, 'report/templates')

domain = settings.DOMAIN


### CODE STARTS HERE


@shared_task
def weekly_report():
    # Resolve admin recipients fresh on each run (not at module import) so a
    # long-running Celery worker picks up changes to AdminSettings.admin_email_addresses
    # without needing a restart.
    try:
        settings1 = AdminSettings.objects.get(settings_name='setting1')
        admin_receiver = settings1.admin_email_addresses or settings.ADMIN_RECEIVER
    except AdminSettings.DoesNotExist:
        admin_receiver = settings.ADMIN_RECEIVER
    recipients = [e.strip() for e in admin_receiver.split(',') if e.strip()]
    if settings.TEST_RECEIVER and settings.TEST_RECEIVER not in recipients:
        recipients.append(settings.TEST_RECEIVER)

    templatefileloc1 = 'weekly_report.html'

    activeloans = Loan.objects.filter(category="FUNDED", funded_category="ACTIVE")
    totalbalance = activeloans.aggregate(Sum('total_outstanding'))['total_outstanding__sum']

    
    pdfddatacontext = {
        'totalbalance': totalbalance,
    }

    pdf_data1 = generate_pdf(templatefileloc1, pdfddatacontext)
    pdf_attachment1 = MIMEApplication(pdf_data1, _subtype='pdf')
    pdf_attachment1.add_header('content-disposition', 'attachment', filename='LoanMasta-WeeklyLoansReport.pdf')

    email_subject=f'WEEKLY REPORT FOR LOANS'
    
    # HTML EMAIL
    html_content = render_to_string("custom/email_temp_general.html", {
        'subject': email_subject,
        'greeting': 'Hi',
        'cta': 'yes',
        'cta_btn1_label': 'Login to Dashboard',
        'cta_btn1_link': f'{settings.DOMAIN}/admin/dashboard/',
        'message': f'Kindly find attached the Weekly Report for your Loans.',
        'message_details': f'Please read through the documents and if you need additional insights, you can login to your dashboard and generate additional reports.',
    })
    
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(email_subject, text_content, settings.EMAIL_HOST_USER, recipients)
    email.attach_alternative(html_content, "text/html")
    
    email.attach(pdf_attachment1)
    
    try:
        email.send()
    except Exception:
        logger.exception("Failed to send weekly report email")


#@shared_task
def monthly_report():
    pass  # TODO: implement monthly report (stub kept to preserve the celery task name)

#@shared_task
def end_of_day_report():
    pass  # TODO: implement end-of-day report (stub kept to preserve the celery task name)
