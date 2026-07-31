"""Loan contract generation + delivery for the manager approval action.

Gated by AdminSettings.contract_generation_enabled (see manager/views.py).
The contract text is generalized across tenants — it pulls the company name
from settings.COMPANY_NAME and the disclosed fee/rate from AdminSettings
(contract_default_fee / contract_default_interest_rate) rather than hardcoding
one tenant's wording.
"""
import datetime
import os

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from admin1.models import AdminSettings


def _contract_settings():
    setting = AdminSettings.objects.filter(settings_name='setting1').first()
    return {
        'default_fee': (setting.contract_default_fee if setting else None) or 20,
        'default_interest_rate': (setting.contract_default_interest_rate if setting else None) or 10,
    }


def save_contract_file(loan):
    """Render the contract (custom/contract_gen.html) to PDF and save it under
    MEDIA_ROOT/contracts/<uid>/. Updates the loan's contract fields. Returns
    the absolute file path."""
    from loan.views import generate_pdf

    filename = f"loan_contract_{loan.ref}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    file_path = f"contracts/{loan.owner.uid}/{filename}"
    full_dir = os.path.join(settings.MEDIA_ROOT, f"contracts/{loan.owner.uid}")
    os.makedirs(full_dir, exist_ok=True)

    context = {
        'loan': loan,
        'user': loan.owner,
        'officer': loan.officer,
        'domain': settings.DOMAIN,
        'settings': settings,
        **_contract_settings(),
    }
    pdf_data = generate_pdf('custom/contract_gen.html', context)
    file_full_path = os.path.join(settings.MEDIA_ROOT, file_path)
    with open(file_full_path, 'wb') as fh:
        fh.write(pdf_data)

    loan.contract_file_path = file_path
    loan.contract_url = f"{settings.MEDIA_URL}{file_path}"
    loan.contract_generated = True
    loan.save()
    return file_full_path


def send_approval_email(loan, contract_path):
    """Email the approval notice + attached contract to the client and the
    lending officer, using the site-wide HTML notification template."""
    subject = f'{loan.ref} is APPROVED'
    cta_link = f'{settings.DOMAIN}/loan/myloan/{loan.ref}/'
    user = loan.owner

    email_content = render_to_string('custom/email_temp_general.html', {
        'header_cta': 'no',
        'cta': 'yes',
        'cta_btn2': 'no',
        'promo': 'yes',
        'cta_link': cta_link,
        'cta_label': 'View Loan',
        'subject': subject,
        'greeting': f'Hi {user.first_name}',
        'message': 'Your pending loan has been Approved.',
        'message_details': (f'Amount: K{round(loan.amount, 2)}<br>'
                            f'Repayment: K{round(loan.repayment_amount, 2)}<br>'
                            f'Repayment Start Date: {loan.repayment_start_date}'),
        'cta_btn1_link': cta_link,
        'cta_btn1_label': 'View Loan',
        'cta_btn2_link': '',
        'cta_btn2_label': '',
        'catchphrase': 'FUNDING?',
        'promo_title': 'YOU WILL GET A FUNDING ALERT',
        'promo_message': 'Once the loan is funded, you will get a funding notice in your email.',
        'promo_cta_link': '',
        'promo_cta': '',
        'user': user,
        'domain': settings.DOMAIN,
    })

    recipients = [user.email]
    if loan.officer and loan.officer.user.email:
        recipients.append(loan.officer.user.email)

    text_content = strip_tags(email_content)
    email = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, recipients)
    email.attach_alternative(email_content, "text/html")

    try:
        with open(contract_path, 'rb') as fh:
            email.attach(f'loan_contract_{loan.ref}.pdf', fh.read(), 'application/pdf')
    except Exception:
        pass

    # Optionally attach the statutory declaration too (same toggle/template
    # used for the loan-application document bundle — see loan/functions.py).
    setting = AdminSettings.objects.filter(settings_name='setting1').first()
    if setting is None or setting.appdoc_include_stat_dec:
        try:
            from moromafinance.pdf import render_pdf
            stat_dec_pdf = render_pdf('custom/stat_dec_gen.html', {
                'domain': settings.DOMAIN,
                'loan': loan,
                'user': user,
                'settings': settings,
            }, 'custom/templates')
            email.attach(f'Statutory_Declaration_{loan.ref}.pdf', stat_dec_pdf, 'application/pdf')
        except Exception:
            pass

    try:
        email.send()
        return True
    except Exception:
        return False


def send_rejection_email(loan, comments):
    subject = f'Loan Application - {loan.ref}'
    message = (f"Dear {loan.owner.first_name} {loan.owner.last_name},\n\n"
              f"We regret to inform you that your loan application (Reference: {loan.ref}) has been declined.\n\n"
              + (f'Reason: {comments}\n\n' if comments else '')
              + "You may contact us for further clarification or reapply after addressing the issues.\n\n"
              f"Best regards,\n{settings.COMPANY_NAME} Team")
    try:
        EmailMessage(subject, message, settings.DEFAULT_FROM_EMAIL, [loan.owner.email]).send()
        return True
    except Exception:
        return False


def send_hold_email(loan, comments):
    subject = f'Loan Application - {loan.ref}'
    message = (f"Dear {loan.owner.first_name} {loan.owner.last_name},\n\n"
              f"Your loan application (Reference: {loan.ref}) has been put on hold.\n\n"
              + (f'Reason: {comments}\n\n' if comments else '')
              + "We will contact you once we have reviewed your application further.\n\n"
              f"Best regards,\n{settings.COMPANY_NAME} Team")
    try:
        EmailMessage(subject, message, settings.DEFAULT_FROM_EMAIL, [loan.owner.email]).send()
        return True
    except Exception:
        return False
