from django.conf import settings
from accounts.models import UserProfile
from loan.models import Loan, LoanFile
from message.functions import email_admin, send_email

import datetime
from decimal import Decimal
import string
import random
import logging
import pandas as pd
from django.conf import settings
from django.db import transaction
from django.db.models import Q

logger = logging.getLogger(__name__)
from django.contrib import messages
from django.shortcuts import render, redirect

#read excel
from http.client import HTTPResponse
#import pandas as pd

from admin1.models import AdminSettings, Location, get_loan_config
from accounts.models import User, UserProfile, StaffProfile
from message.models import Message, MessageLog
from loan.models import Loan, LoanFile, Statement

#EMAIL SETTINGS
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.utils.html import strip_tags
#admin sender email
from admin1.models import AdminSettings
sender = settings.DEFAULT_SENDER_EMAIL




from django.contrib import messages


def _generate_pdf(templatefile, data):
    from moromafinance.pdf import render_pdf
    return render_pdf(templatefile, data, 'custom/templates')


def statement_summary(loan, statements):
    """Summary figures for the Statement of Account header/footer, shared by every
    view that renders custom/client_statement.html so the totals never go missing.

    Identity: opening_balance + extra_debits - total_credits == closing_balance.
    """
    def _fmt(d):
        return d.strftime('%d %B %Y') if d else '—'

    opening_balance = Decimal(str(loan.total_loan_amount or 0))
    extra_debits = (Decimal(str(loan.default_interest_receivable or 0))
                    + Decimal(str(loan.default_interest_paid or 0)))
    total_credits = Decimal(str(loan.total_paid or 0))
    closing_balance = Decimal(str(loan.total_outstanding or 0))

    ordered = statements.order_by('date', 'id') if hasattr(statements, 'order_by') else statements
    first_stmt = ordered.first() if hasattr(ordered, 'first') else (ordered[0] if ordered else None)
    last_stmt = ordered.last() if hasattr(ordered, 'last') else (ordered[-1] if ordered else None)

    return {
        'opening_balance': opening_balance,
        'extra_debits': extra_debits,
        'total_credits': total_credits,
        'closing_balance': closing_balance,
        'stmt_start': _fmt(first_stmt.date if first_stmt else loan.repayment_start_date),
        'stmt_end': _fmt(last_stmt.date if last_stmt else loan.expected_end_date),
        'loan_started': _fmt(loan.funding_date or getattr(loan, 'created_at', None)),
    }


def build_application_documents_email(loan, user, usr, loan_setting, uid, token, staff_email=None):
    """Build the prefilled loan-application documents email, honouring the admin
    Loan Settings (master switch, recipients, and which documents to attach).

    Returns a configured EmailMultiAlternatives ready to .send(), or None when
    sending is disabled, no recipient is selected, or no document is selected.
    """
    from email.mime.application import MIMEApplication
    from django.utils.html import strip_tags

    try:
        s = AdminSettings.objects.get(settings_name='setting1')
    except AdminSettings.DoesNotExist:
        s = None

    # Master switch — default ON when no settings row exists (preserves old behaviour)
    if s is not None and not s.send_application_documents:
        return None

    def _flag(name, default=True):
        return getattr(s, name, default) if s is not None else default

    # ---- Recipients ---------------------------------------------------------
    to_list = []
    if _flag('appdoc_send_to_user', True) and usr and usr.email:
        to_list.append(usr.email)
    if _flag('appdoc_send_to_staff', False):
        if staff_email:
            to_list.append(staff_email)
        to_list += list(getattr(settings, 'APPLICATION_FORM_EMAIL', []) or [])

    bcc_list = []
    if _flag('appdoc_bcc_admin', False):
        try:
            admin_addrs = (s.admin_email_addresses if s else '') or settings.EMAIL_HOST_USER
            bcc_list += [a.strip() for a in str(admin_addrs).split(',') if a.strip()]
        except Exception:
            pass

    # De-dupe while preserving order; nothing to send to → skip
    to_list = list(dict.fromkeys([a for a in to_list if a]))
    bcc_list = list(dict.fromkeys([a for a in bcc_list if a and a not in to_list]))
    if not to_list and not bcc_list:
        return None

    # ---- Documents ----------------------------------------------------------
    pdfcontext = {
        'domain': settings.DOMAIN,
        'loan': loan,
        'interest_rate': getattr(loan_setting, 'interest_rate', None),
        'user': user,
        'settings': settings,
    }
    doc_specs = [
        ('appdoc_include_application', 'custom/loan_application_gen.html', 'Loan_Application.pdf'),
        ('appdoc_include_terms',       'custom/terms_conditions_gen.html', 'Terms_&_Conditions.pdf'),
        ('appdoc_include_stat_dec',    'custom/stat_dec_gen.html',         'Statutory_Declaration.pdf'),
        ('appdoc_include_irsda',       'custom/irsda_gen.html',            'IR_Salary_Deduction_Authority.pdf'),
    ]
    attachments = []
    for flag_name, template, filename in doc_specs:
        if not _flag(flag_name, True):
            continue
        pdf_data = _generate_pdf(template, pdfcontext)
        att = MIMEApplication(pdf_data, _subtype='pdf')
        att.add_header('content-disposition', 'attachment', filename=filename)
        attachments.append(att)

    if not attachments:
        return None

    # ---- Email --------------------------------------------------------------
    email_subject = f'Sign Required Documents for Loan - {loan.ref}'
    html_content = render_to_string("custom/email_temp_general.html", {
        'subject': email_subject,
        'greeting': f'Hi {user.first_name}',
        'cta': 'yes',
        'cta_btn1_label': 'UPLOAD SIGNED DOCUMENTS',
        'cta_btn1_link': f'{settings.DOMAIN}/loan/myloan/{loan.ref}/',
        'message': 'Kindly find attached the prefilled loan application documents for your loan application.',
        'message_details': 'Please read through the documents and sign them. Once signed, please scan each signed document and upload them to complete your loan application. Loan decision will only be made once all these documents are signed and uploaded.',
        'user': usr,
        'userprofile': user,
        'loan': loan,
        'domain': settings.DOMAIN,
        'uid': uid,
        'token': token,
    })
    text_content = strip_tags(html_content)

    email = EmailMultiAlternatives(email_subject, text_content, settings.EMAIL_HOST_USER, to_list, bcc=bcc_list or None)
    email.attach_alternative(html_content, "text/html")
    for att in attachments:
        email.attach(att)
    return email


def request_approval(loan):
    loanfile = LoanFile.objects.get(loan=loan)
    userprofile = loan.owner
    domain = settings.DOMAIN

    if loanfile.application_form_url and loanfile.terms_conditions_url and loanfile.stat_dec_url and loanfile.irr_sd_form_url and loanfile.bank_statement_url and loanfile.payslip1_url and loanfile.payslip2_url and loanfile.work_confirmation_letter_url:
        loan.status = 'UNDER REVIEW'
        loan.save()
        email_admin(userprofile, sub=f'Loan Application - {loan.ref} - READY FOR APPROVAL', gr='Hi,',msg='Loan application is ready for Approval. Please review the application and make a decision.', cta='yes', btnlab='View Loan', btnlink=f'{settings.DOMAIN}/admin/loans/{loan.ref}/')
        send_email(userprofile, sub=f'Loan Application {loan.ref} - UNDER REVIEW', gr=f'Hi {userprofile.first_name},', msg='Your loan application is now under review for approval.', cta='yes', btn_lab='View Loan', b_link=f'{settings.DOMAIN}/loan/myloan/{loan.ref}/')
        return True


def default_calculator():

    default_amount = settings.DEFAULT_INTEREST

    return default_amount


def complete_loan(request, loan):

    userprofile = UserProfile.objects.get(pk=loan.owner.id)
    userprofile.has_loan = False
    userprofile.save()

    loan.funded_category = 'COMPLETED'
    loan.status = 'COMPLETED'
    loan.total_outstanding = 0
    loan.principal_loan_receivable = 0
    loan.ordinary_interest_receivable = 0
    loan.default_interest_receivable = 0
    loan.save()

    return _send_loan_completion_email(request, loan)


def _send_loan_completion_email(request, loan):
    """Send the 'loan is complete' notice. Split out of complete_loan() so
    close_loan_with_credit() (below) can reuse it for the no-excess case
    without duplicating the email-building code."""
    #send email to user
    subject = f'Congratulations! {loan.ref} is COMPLETE'
    ''' if header_cta == 'yes' '''
    cta_label = 'View Loan'
    cta_link = f'{settings.DOMAIN}/loan/myloan/{loan.ref}/'

    greeting = f'Hi {loan.owner.first_name}'
    message = 'We are glad to advise you that your loan is now completed.'
    message_details = f'We thank you for borrowing from us. You have been a good client\
                        and we look forward to lend to you again whenever you need our services.'

    ''' if cta == 'yes' '''
    cta_btn1_label = 'View Loan'
    cta_btn1_link = f'{settings.DOMAIN}/loan/myloan/{loan.ref}/'
    cta_btn2_label = ''
    cta_btn2_link = ''

    ''' if promo == 'yes' '''
    catchphrase = 'FUNDING?'
    promo_title = 'YOU WILL GET A FUNDING ALERT'
    promo_message = 'Once the loan is funded, you will get a funding notice in your email.'
    promo_cta = ''
    promo_cta_link = ''
    
    email_content = render_to_string('custom/email_temp_general.html', {
        'header_cta': 'no',
        'cta': 'yes',
        'cta_btn2': 'no',
        'promo': 'no',
        'cta_link': cta_link,
        'cta_label': cta_label,
        'subject': subject,
        'greeting': greeting,
        'message': message,
        'message_details': message_details,
        'cta_btn1_link': cta_btn1_link,
        'cta_btn1_label': cta_btn1_label,
        'cta_btn2_link': cta_btn2_link,
        'cta_btn2_label': cta_btn2_label,
        'catchphrase': catchphrase,
        'promo_title': promo_title,
        'promo_message': promo_message,
        'promo_cta_link': promo_cta_link,
        'promo_cta': promo_cta,
        'user': loan.owner,
        'domain': settings.DOMAIN,
    })

    #recipients
    email_list_one = [loan.owner.email, settings.ADMIN_RECEIVER]
    email_list_two = settings.ADMIN_EMAILS
    email_list  = email_list_one + email_list_two

    text_content = strip_tags(email_content)
    email = EmailMultiAlternatives(subject,text_content,sender,email_list)
    email.attach_alternative(email_content, "text/html")
    
    try:
        email.send()
        messages.success(request, f'Loan Completion Note sent to {loan.owner.first_name} {loan.owner.last_name} successfully.')
    except Exception:
        logger.exception("Failed to send loan completion email for loan %s", loan.ref)
        messages.error(request, 'Loan Completion notice not sent.', extra_tags='danger')

    return 1


def close_loan_with_credit(request, loan, stat, amount, balance, notify=True):
    """Complete a loan at a payment that clears (>=) its outstanding balance.

    Records the FULL amount paid against total_paid (a prior bug silently
    dropped this whenever a payment happened to close the loan out). If the
    payment OVERPAYS the balance — e.g. an external refinance payoff that
    exceeds what was actually owed — the excess is NEVER discarded: it is
    captured as a LoanCredit owed back to the client, and the loan is parked
    in the AWAITING_REFUND bucket (kept OUT of Completed, kept visible in the
    loans list) until staff either:
      * mark the credit refunded (Client Credits register, receipt upload)
        -> the loan then finalises to COMPLETED automatically, or
      * explicitly choose "Attribute to Client Credit & Close Now" on the
        loan page -> the loan completes immediately, the credit stays
        outstanding on the client's account to be refunded whenever.

    A payment that exactly clears the balance (no excess, within the normal
    LOAN_COMPLETION_BALANCE tolerance) completes normally — unchanged from
    the previous behaviour.

    Returns True — the caller should stop processing (mirrors the old
    ``if completion_response == 1: ...; return`` shortcut).
    """
    from loan.models import LoanCredit

    user = loan.owner
    officer = None
    try:
        officer = StaffProfile.objects.filter(user__user=request.user).first()
    except Exception:
        pass

    overpayment = amount - balance
    if overpayment < 0:
        overpayment = Decimal('0')

    loan.total_paid = (loan.total_paid or Decimal('0')) + amount
    loan.total_outstanding = Decimal('0')
    loan.principal_loan_receivable = Decimal('0')
    loan.ordinary_interest_receivable = Decimal('0')
    loan.default_interest_receivable = Decimal('0')
    loan.number_of_repayments = (loan.number_of_repayments or 0) + 1
    loan.last_repayment_amount = amount
    loan.last_repayment_date = stat.date

    stat.type = 'COMPLETE PAYMENT'
    stat.debit = amount
    stat.credit = 0
    stat.balance = Decimal('0')

    if overpayment > settings.LOAN_COMPLETION_BALANCE:
        userprofile = UserProfile.objects.get(pk=user.id)
        userprofile.has_loan = False
        userprofile.save()

        loan.funded_category = 'AWAITING_REFUND'
        loan.status = 'COMPLETED'
        loan.save()

        stat.statement = (stat.statement or 'Loan Payment') + \
            f' — settled in full; K{overpayment:.2f} excess held as client credit.'
        stat.save()

        LoanCredit.objects.create(
            owner=user, loan=loan, amount=overpayment,
            reason='OVERPAYMENT_AT_CLOSURE',
            note=f'Excess from closing payment of K{amount:.2f} against outstanding K{balance:.2f} on {loan.ref}.',
            created_by=officer,
        )
        logger.info("LOAN-AWAITING-REFUND loan=%s amount=%s balance=%s overpayment=%s",
                    loan.ref, amount, balance, overpayment)
        messages.success(
            request,
            f'{loan.ref} settled in full. K{overpayment:.2f} excess recorded as a client credit — '
            'the loan is parked as Awaiting Refund until the excess is refunded or attributed.',
            extra_tags='info',
        )
    else:
        stat.save()
        complete_loan(request, loan)

    return True


def finalize_awaiting_refund(request, loan):
    """Finalize a loan parked AWAITING_REFUND once its excess has been dealt
    with — either the client was actually refunded (Client Credits register)
    or staff explicitly chose to attribute the excess to the client's credit
    balance and close the loan now. Flips the loan to COMPLETED and sends the
    loan-complete notice (held back until now, since the loan wasn't really
    "done" while a refund was still owed). No-op if not AWAITING_REFUND."""
    if loan.funded_category != 'AWAITING_REFUND':
        return False
    loan.funded_category = 'COMPLETED'
    loan.save(update_fields=['funded_category'])
    _send_loan_completion_email(request, loan)
    logger.info("LOAN-AWAITING-REFUND-FINALIZED loan=%s", loan.ref)
    return True


@transaction.atomic
def process_advance_payment(request,loan,stat,amount,notify=True):
    loan = Loan.objects.select_for_update().get(pk=loan.pk)
    user = loan.owner
    logger.info("ADVANCE-PAYMENT loan=%s amount=%s by=%s opening_balance=%s",
                loan.ref, amount, getattr(getattr(request, 'user', None), 'email', '?'), loan.total_outstanding)

    arrears = loan.total_arrears
    balance = loan.total_outstanding
    date = stat.date

    if arrears < amount:
        stat.arrears = 0
        loan.total_arrears = 0
    else:
        stat.arrears = arrears - amount
        loan.total_arrears -= amount
    
    #complete loan
    closing_balance = balance - settings.LOAN_COMPLETION_BALANCE
    if closing_balance < amount:
        if close_loan_with_credit(request, loan, stat, amount, balance, notify=notify):
            return redirect('staff_dashboard')

    stat.balance = balance - amount
    stat.type = 'PAYMENT'
    stat.save()

    if loan.default_interest_receivable > 0:

        principal_repayment_percentage = (loan.principal_loan_receivable / loan.total_outstanding)
        interest_repayment_percentage = (loan.ordinary_interest_receivable / loan.total_outstanding)
        default_repayment_percentage = (loan.default_interest_receivable / loan.total_outstanding)
        
        principal_repayment = amount * principal_repayment_percentage
        interest_repayment = amount * interest_repayment_percentage
        default_repayment = amount * default_repayment_percentage
        
        loan.principal_loan_receivable -= principal_repayment
        loan.ordinary_interest_receivable -= interest_repayment
        loan.default_interest_receivable -= default_repayment
        
        loan.principal_loan_paid += principal_repayment
        loan.interest_paid += interest_repayment
        loan.default_interest_paid += default_repayment
        loan.save()

        stat.principal_collected = principal_repayment
        stat.interest_collected = interest_repayment
        stat.default_interest_collected = default_repayment
        stat.save()

    else:
        principal_repayment_percentage = (loan.principal_loan_receivable / loan.total_outstanding)
        interest_repayment_percentage = (loan.ordinary_interest_receivable / loan.total_outstanding)
        
        principal_repayment = amount * principal_repayment_percentage
        interest_repayment = amount * interest_repayment_percentage
        
        loan.principal_loan_receivable -= principal_repayment
        loan.ordinary_interest_receivable -= interest_repayment

        loan.principal_loan_paid += principal_repayment
        loan.interest_paid += interest_repayment
        loan.save()

        stat.principal_collected = principal_repayment
        stat.interest_collected = interest_repayment
        stat.save()
    
    loan.last_repayment_amount = amount
    loan.last_repayment_date = date
    loan.number_of_repayments += 1
    loan.total_paid += amount
    loan.total_outstanding -= amount

    # Settle exactly one scheduled fortnight. The surplus does NOT advance the
    # schedule — it is held as advance_balance and applied to a later due
    # fortnight instead of a default (see engine.create_default_for_loan).
    from loan import schedule as _sched
    _sched.settle(loan, 1)
    loan.save()

    #extra
    loan.status = "RUNNING"
    loan.last_advance_payment_date = date
    loan.last_advance_payment_amount = amount
    loan.number_of_advance_payments += 1
    #loan.total_arrears -= amount

    scheduled = loan.repayment_amount or 0
    surplus = (amount - scheduled) if amount > scheduled else 0
    loan.advance_payment_surplus = surplus
    # total_advance_payment tracks the cumulative ADVANCE (surplus) only — not the
    # full payment. (Adding the full amount over-stated it, e.g. 3x K700/400/450 =
    # K1,550 instead of the true advance of K587.93.)
    loan.total_advance_payment = (loan.total_advance_payment or 0) + surplus
    if surplus and surplus > 0:
        # Running prepaid credit — applied to a later due fortnight instead of a
        # default (see loan/engine.create_default_for_loan).
        loan.advance_balance = (loan.advance_balance or 0) + surplus
        # Show the scheduled repayment and the surplus as two separate statement
        # lines: the Alesco/repayment line, then an "Advance Payment" line.
        stat.debit = scheduled
        stat.balance = balance - scheduled
        stat.save()
        _cnt = Statement.objects.filter(loanref=loan).count() + 1
        Statement.objects.create(
            owner=user, loanref=loan, uid=user.uid, luid=settings.LUID,
            ref=f'{loan.ref}SA{_cnt}', type='ADVANCE', statement='Advance Payment',
            date=date, debit=surplus, credit=0,
            arrears=loan.total_arrears, balance=balance - amount,
        )

    loan.save()
    
    #send email to client
    if notify:
        subject=f'Payment updated for Loan - {loan.ref}'
        message = f'Thank you for Advance Payment of K{round(amount,2)}.'
        message_details = f'Total Outstanding Balance: K{round(loan.total_outstanding, 2)}<br>\
                            Total Arrears: K{round(loan.total_arrears, 2)}'
        status = send_email(user, sub=subject, gr=f'Hi {user.first_name}', msg=message, msg_details=message_details, cta='no', btn_lab='View Statement', b_link=f'{settings.DOMAIN}/loan/mystatements/', msgid=None, attachcheck='no', path='')
        if status == 1:
            messages.success(request, 'Advance payment registered.', extra_tags='info')
        else:
            messages.error(request, 'Payment advise email not sent.', extra_tags='warning')
    else:
        messages.success(request, 'Advance payment registered.', extra_tags='info')

    return redirect('staff_enter_payment')

@transaction.atomic
def process_repayment(request,loan,stat,amount,notify=True):
    # Lock the loan row so two concurrent payment submissions can't both read
    # the same balance and double-apply (lost update). All mutations below now
    # commit atomically — a failure midway rolls the whole repayment back.
    loan = Loan.objects.select_for_update().get(pk=loan.pk)
    user = loan.owner
    arrears = loan.total_arrears
    balance = loan.total_outstanding
    date = stat.date
    # Capture the amount expected for the fortnight being paid, BEFORE the cursor
    # advances, so a shortfall (partial payment) can be defaulted below.
    from loan import schedule as _sched
    expected_this_fn = _sched.current_expected_amount(loan)
    logger.info("REPAYMENT loan=%s amount=%s by=%s opening_balance=%s arrears=%s",
                loan.ref, amount, getattr(getattr(request, 'user', None), 'email', '?'), balance, arrears)

    if arrears < amount:
        stat.arrears = 0
        loan.total_arrears = 0
    else:
        stat.arrears = arrears - amount
        loan.total_arrears -= amount

    # Keep the loan status in sync: once arrears are cleared, a previously
    # DEFAULTED loan is current again. (Prevents the list showing DEFAULTED while
    # the detail page shows Good Loan.)
    if loan.total_arrears <= 0 and loan.status == 'DEFAULTED':
        loan.status = 'RUNNING'

    #complete loan
    closing_balance = balance - settings.LOAN_COMPLETION_BALANCE
    if closing_balance < amount:
        if close_loan_with_credit(request, loan, stat, amount, balance, notify=notify):
            return redirect('staff_dashboard')
    
    stat.balance = balance - amount
    stat.type = 'PAYMENT'
    stat.save()

    if loan.default_interest_receivable > 0:

        principal_repayment_percentage = (loan.principal_loan_receivable / loan.total_outstanding)
        interest_repayment_percentage = (loan.ordinary_interest_receivable / loan.total_outstanding)
        default_repayment_percentage = (loan.default_interest_receivable / loan.total_outstanding)
        
        principal_repayment = amount * principal_repayment_percentage
        interest_repayment = amount * interest_repayment_percentage
        default_repayment = amount * default_repayment_percentage
        
        loan.principal_loan_receivable -= principal_repayment
        loan.ordinary_interest_receivable -= interest_repayment
        loan.default_interest_receivable -= default_repayment
        
        loan.principal_loan_paid += principal_repayment
        loan.interest_paid += interest_repayment
        loan.default_interest_paid += default_repayment
        loan.save()

        stat.principal_collected = principal_repayment
        stat.interest_collected = interest_repayment
        stat.default_interest_collected = default_repayment
        stat.save()

    else:
        principal_repayment_percentage = (loan.principal_loan_receivable / loan.total_outstanding)
        interest_repayment_percentage = (loan.ordinary_interest_receivable / loan.total_outstanding)
        
        principal_repayment = amount * principal_repayment_percentage
        interest_repayment = amount * interest_repayment_percentage
        
        loan.principal_loan_receivable -= principal_repayment
        loan.ordinary_interest_receivable -= interest_repayment

        loan.principal_loan_paid += principal_repayment
        loan.interest_paid += interest_repayment
        loan.save()

        stat.principal_collected = principal_repayment
        stat.interest_collected = interest_repayment
        stat.save()

    loan.last_repayment_amount = amount
    loan.last_repayment_date = date
    loan.number_of_repayments += 1
    loan.total_paid += amount
    loan.total_outstanding -= amount

    # Settle one scheduled fortnight (the schedule is immutable; the cursor
    # advances). next_payment_date is derived.
    _sched.settle(loan, 1)
    loan.save()

    # ── Shortfall auto-default ──────────────────────────────────────────────
    # If the client paid LESS than the fortnight's expected repayment, treat the
    # unpaid shortfall as a default (default interest on the shortfall + arrears),
    # when the admin setting allows it.
    _cfg = get_loan_config()
    _shortfall = (expected_this_fn or 0) - (amount or 0)
    if _cfg.get('auto_default_on_shortfall', True) and _shortfall > settings.TOTAL_ALLOWABLE_TOEAS:
        from loan.engine import charge_shortfall
        charge_shortfall(loan, _shortfall, date)
        loan.save()

    #send email to client
    if notify:
        subject=f'Payment updated for Loan - {loan.ref}'
        message = f'Thank you for Payment of K{round(amount,2)}.'
        message_details = f'Total Outstanding Balance: K{round(loan.total_outstanding, 2)}<br>\
                            Total Arrears: K{round(loan.total_arrears, 2)}'
        status = send_email(user, sub=subject, gr=f'Hi {user.first_name}', msg=message, msg_details=message_details, cta='no', btn_lab='View Statement', b_link=f'{settings.DOMAIN}/loan/mystatements/', msgid=None, attachcheck='no', path='')
        if status == 1:
            messages.success(request, 'Payment registered.', extra_tags='info')
        else:
            messages.error(request, 'Payment advise email not sent.', extra_tags='warning')
    else:
        messages.success(request, 'Payment registered.', extra_tags='info')

    return redirect('staff_enter_payment')

@transaction.atomic
def process_default(request,loan,stat,amount,notify=True):
    loan = Loan.objects.select_for_update().get(pk=loan.pk)
    logger.info("DEFAULT-PAYMENT loan=%s amount=%s by=%s opening_balance=%s",
                loan.ref, amount, getattr(getattr(request, 'user', None), 'email', '?'), loan.total_outstanding)
    shortfall = loan.repayment_amount - amount
    if shortfall < 0:
        shortfall = Decimal('0')

    # Default interest on the shortfall, honouring the admin settings
    # (rate as a percentage, base = shortfall or full per default_interest_base).
    from loan.engine import default_interest_for
    default_interest = default_interest_for(loan, shortfall, get_loan_config())
    user = loan.owner
    date = stat.date
    arrears = loan.total_arrears
    balance = loan.total_outstanding

    #complete loan
    closing_balance = balance - settings.LOAN_COMPLETION_BALANCE
    if closing_balance < amount:
        if close_loan_with_credit(request, loan, stat, amount, balance, notify=notify):
            return redirect('staff_dashboard')

    #save part payment statement
    stat.arrears = arrears + shortfall
    stat.balance = balance - amount
    stat.type = 'PAYMENT'
    stat.save()

    if loan.default_interest_receivable > 0:

        principal_repayment_percentage = (loan.principal_loan_receivable / loan.total_outstanding)
        interest_repayment_percentage = (loan.ordinary_interest_receivable / loan.total_outstanding)
        default_repayment_percentage = (loan.default_interest_receivable / loan.total_outstanding)
        
        principal_repayment = amount * principal_repayment_percentage
        interest_repayment = amount * interest_repayment_percentage
        default_repayment = amount * default_repayment_percentage
        
        loan.principal_loan_receivable -= principal_repayment
        loan.ordinary_interest_receivable -= interest_repayment
        loan.default_interest_receivable -= default_repayment
        
        loan.principal_loan_paid += principal_repayment
        loan.interest_paid += interest_repayment
        loan.default_interest_paid += default_repayment
        loan.save()

        stat.principal_collected = principal_repayment
        stat.interest_collected = interest_repayment
        stat.default_interest_collected = default_repayment
        stat.save()

    else:
        principal_repayment_percentage = (loan.principal_loan_receivable / loan.total_outstanding)
        interest_repayment_percentage = (loan.ordinary_interest_receivable / loan.total_outstanding)
        
        principal_repayment = amount * principal_repayment_percentage
        interest_repayment = amount * interest_repayment_percentage
        
        loan.principal_loan_receivable -= principal_repayment
        loan.ordinary_interest_receivable -= interest_repayment

        loan.principal_loan_paid += principal_repayment
        loan.interest_paid += interest_repayment
        loan.save()

        stat.principal_collected = principal_repayment
        stat.interest_collected = interest_repayment
        stat.save()

    loan.last_repayment_amount = amount
    loan.last_repayment_date = date
    loan.number_of_repayments += 1
    loan.total_paid += amount
    loan.total_outstanding = balance - amount + default_interest
    loan.total_arrears += shortfall
    loan.last_default_date = date

    # A short payment settles the current scheduled fortnight (the shortfall is
    # charged as a default). One slot only, even though it counts as both a
    # repayment and a default. The schedule is immutable; the cursor advances.
    from loan import schedule as _sched
    _sched.settle(loan, 1)
    loan.save()

    loan.last_default_amount = shortfall
    loan.number_of_defaults += 1
    # default_interest is added to the receivable exactly once (the earlier
    # duplicate add here was double-counting the default interest).
    loan.default_interest_receivable += default_interest
    loan.save()

    default_int_stat = Statement.objects.create(owner=user, type="DEFAULT", loanref=loan, date=date, credit=default_interest, statement="Default Interest",  uid=user.uid, luid=settings.LUID)
    default_int_stat.arrears = stat.arrears
    default_int_stat.balance = stat.balance + default_interest

    default_int_stat.default_amount = shortfall
    default_int_stat.default_interest = default_interest
    default_int_stat.dcc = 'DEFAULTED'
    default_int_stat.save()

    loan.status = 'DEFAULTED'
    loan.save()

    #send email to client
    if notify:
        subject=f'Payment updated for Loan - {loan.ref}'
        message = f'Thank you for the Payment of K{round(amount,2)}.'
        message_details = f'Total Outstanding Balance: K{round(loan.total_outstanding, 2)}<br>\
                            Total Arrears: K{round(loan.total_arrears, 2)}<br>\
                            <p style="color: red;">Loan classified as DEFAULT</p>.'
        status = send_email(user, sub=subject, gr=f'Hi {user.first_name}', msg=message, msg_details=message_details, cta='no', btn_lab='View Statement', b_link=f'{settings.DOMAIN}/loan/mystatements/', msgid=None, attachcheck='no', path='')
        if status == 1:
            messages.error(request, 'AMOUNT IS LESS THAN REPAYMENT AMOUNT, so loan classified as default with default interest added and user notified', extra_tags='warning')
        else:
            messages.error(request, 'Payment advise email not sent.', extra_tags='warning')
    else:
        messages.error(request, 'Amount is less than the repayment amount — loan classified as DEFAULT with default interest charged on the shortfall.', extra_tags='warning')

    return redirect('staff_enter_payment')
    
def update_defaults(request):
    """Catch up overdue defaults via the loan engine (earliest-missed only,
    never future, nets advances, charges on shortfall per setting)."""
    from django.db import transaction
    from django.db.models import Q
    from loan.engine import create_default_for_loan

    loans = (Loan.objects.filter(Q(status='RUNNING') | Q(status='DEFAULTED'), category='FUNDED')
             .exclude(funded_category='COMPLETED'))
    created = 0
    for loan in loans:
        while True:
            with transaction.atomic():
                locked = Loan.objects.select_for_update().get(pk=loan.pk)
                stat, ok, msg = create_default_for_loan(locked)
            if not ok:
                break
            created += 1
    messages.success(request, f'Processed {created} overdue default(s).', extra_tags='info')
    return redirect('staff_dashboard')
