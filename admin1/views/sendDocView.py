"""Send a loan document (Statement / CDN / LAS) to the client by email.

POSTed from the on-screen document preview (document_preview.html). Each
document is generated with exactly the same context/template as its download
view, then attached to an email to the client.
"""
import datetime
import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.conf import settings

from accounts.functions import admin_check, staff_or_admin_check
from accounts.models import UserProfile, User
from loan.models import Loan, Statement

logger = logging.getLogger(__name__)

_DOCS = {
    'statement': 'Statement of Account',
    'cdn': 'Cash Disbursement Notice',
    'las': 'Loan Amortization Schedule',
}


def _statement_pdf(request, loan, user):
    from loan.functions import statement_summary
    from admin1.models import get_bank_config, get_document_theme
    usr = User.objects.get(pk=user.user_id)
    statements = Statement.objects.filter(loanref=loan)
    data = {'loan': loan, 'user': user, 'usr': usr, 'last_name_s': user.last_name[-1],
            'statements': statements, 'domain': settings.DOMAIN,
            'today': datetime.date.today().strftime('%x'), 'bank_config': get_bank_config(),
            'document_theme': get_document_theme()}
    data.update(statement_summary(loan, statements))
    from moromafinance.pdf import django_pdf_response
    response = django_pdf_response(
        request, 'custom/client_statement.html', data, f'{loan.ref}-Statement.pdf'
    )
    return response.content, f'{loan.ref}-Statement.pdf'


def _las_pdf(request, loan, user):
    from admin1.mainView import _build_las_context
    context = _build_las_context(loan, user, settings.DOMAIN)
    from moromafinance.pdf import django_pdf_response
    response = django_pdf_response(
        request, 'custom/loan_amortization_schedule.html', context, f'LAS_{loan.ref}.pdf'
    )
    return response.content, f'LAS_{loan.ref}.pdf'


def _cdn_pdf(request, loan, user):
    from admin1.views.loansView import _generate_cdn_pdf
    first_repayment = loan.next_payment_date.strftime('%d %B %Y') if loan.next_payment_date else ''
    today_str = datetime.date.today().strftime('%d/%m/%Y')
    return _generate_cdn_pdf(loan, user, first_repayment, today_str), f'CDN_{loan.ref}.pdf'


_BUILDERS = {'statement': _statement_pdf, 'las': _las_pdf, 'cdn': _cdn_pdf}


@staff_or_admin_check
@require_POST
def send_doc_to_client(request, loan_ref, doc):
    back = request.META.get('HTTP_REFERER') or f'/admin/loans/{loan_ref}/'
    if doc not in _DOCS:
        messages.error(request, 'Unknown document type.', extra_tags='danger')
        return redirect(back)

    loan = Loan.objects.filter(ref=loan_ref).first()
    if not loan:
        messages.error(request, f'Loan {loan_ref} not found.', extra_tags='danger')
        return redirect(back)
    user = UserProfile.objects.get(id=loan.owner_id)
    to_email = (user.email or '').strip()
    if not to_email:
        messages.error(request, f'{user.first_name} {user.last_name} has no email address on file.',
                       extra_tags='danger')
        return redirect(back)

    try:
        pdf_bytes, filename = _BUILDERS[doc](request, loan, user)
    except Exception as exc:
        logger.exception('SEND-DOC generate failed loan=%s doc=%s', loan_ref, doc)
        messages.error(request, f'Could not generate the {_DOCS[doc]}: {exc}', extra_tags='danger')
        return redirect(back)

    from django.core.mail import EmailMultiAlternatives
    title = _DOCS[doc]
    subject = f'{title} — {loan.ref}'
    body = (f'Dear {user.first_name},\n\n'
            f'Please find attached your {title} for loan {loan.ref}.\n\n'
            f'If you have any questions, contact us at {settings.REPLY_TO_EMAIL}.\n\n'
            f'Regards,\n{settings.COMPANY_NAME}')
    # The mail server occasionally drops the first connection mid-send
    # ("Connection unexpectedly closed") — retry once on a fresh connection
    # before reporting failure.
    last_exc = None
    for attempt in (1, 2):
        try:
            email = EmailMultiAlternatives(subject, body, settings.DEFAULT_SENDER_EMAIL, [to_email])
            email.attach(filename, pdf_bytes, 'application/pdf')
            email.send()
            logger.info('SEND-DOC sent loan=%s doc=%s to=%s attempt=%s', loan_ref, doc, to_email, attempt)
            messages.success(request, f'{title} for {loan.ref} sent to {to_email}.', extra_tags='info')
            return redirect(back)
        except Exception as exc:
            last_exc = exc
            logger.warning('SEND-DOC attempt %s failed loan=%s doc=%s: %s', attempt, loan_ref, doc, exc)
    logger.exception('SEND-DOC email failed loan=%s doc=%s', loan_ref, doc)
    messages.error(request, f'Email could not be sent after 2 attempts: {last_exc}. '
                            'Please try again in a moment.', extra_tags='danger')
    return redirect(back)
