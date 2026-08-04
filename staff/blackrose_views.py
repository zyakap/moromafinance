"""Staff screens for migrating loans off Blackrose.

Three steps, deliberately separated so nothing is created from a bad parse:

  upload   one or more statement PDFs are read and held as BlackroseImport rows
  review   staff see exactly what was read — client details, every statement
           line, the loan it would create — and can correct it
  import   the client account, the loan and the whole ledger are written

The parsing and money rules all live in loan/blackrose.py; this module is only
the plumbing around them.
"""
import datetime
import logging

from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.functions import check_staff
from accounts.models import UserProfile, StaffProfile
from admin1.models import Location
from loan import blackrose
from loan.models import BlackroseImport, Loan

logger = logging.getLogger(__name__)


def _staff_profile(request):
    """The StaffProfile of the signed-in user, or None."""
    try:
        return StaffProfile.objects.get(user=UserProfile.objects.get(user=request.user.id))
    except (UserProfile.DoesNotExist, StaffProfile.DoesNotExist):
        return None


def _parse_upload(uploaded, staff):
    """Read one uploaded statement into a BlackroseImport row.

    Never raises: a file that cannot be read is stored as FAILED with the
    reason, so a bad file in a batch does not lose the good ones.
    """
    record = BlackroseImport(file_name=uploaded.name, uploaded_by=staff)
    try:
        record.file_hash = blackrose.file_digest(uploaded)
        statement = blackrose.parse_pdf(uploaded)
        plan = blackrose.derive(statement)
    except blackrose.BlackroseError as exc:
        record.status = 'FAILED'
        record.error = str(exc)
        record.file = uploaded
        record.save()
        return record
    except Exception as exc:  # pragma: no cover - unexpected/corrupt PDFs
        logger.exception('Blackrose parse failed for %s', uploaded.name)
        record.status = 'FAILED'
        record.error = f'Could not read this file: {exc}'
        record.file = uploaded
        record.save()
        return record

    record.file = uploaded
    record.lender_name = statement.lender_name[:255]
    record.client_name = statement.client_name[:255]
    record.client_code = statement.client_code[:50]
    record.employer = statement.employer[:255]
    record.address = statement.address[:255]
    record.phone = statement.phone[:30]
    record.parsed = statement.as_dict()
    record.row_count = plan['row_count']
    record.closing_balance = plan['closing_balance']

    already = BlackroseImport.objects.filter(file_hash=record.file_hash,
                                             status='IMPORTED').first()
    if already:
        record.status = 'SKIPPED'
        record.error = (f'This exact file was already imported on '
                        f'{already.imported_at:%d/%m/%Y} as loan {already.loan}.')
    record.save()
    return record


@check_staff
def blackrose_statements(request):
    """Upload Blackrose statement PDFs and list what is waiting to be imported."""
    if request.method == 'POST':
        uploads = request.FILES.getlist('statements')
        if not uploads:
            messages.error(request, 'Choose at least one statement PDF to upload.',
                           extra_tags='danger')
            return redirect('blackrose_statements')

        staff = _staff_profile(request)
        ok = failed = skipped = 0
        for uploaded in uploads:
            record = _parse_upload(uploaded, staff)
            if record.status == 'FAILED':
                failed += 1
                messages.error(request, f'{record.file_name}: {record.error}', extra_tags='danger')
            elif record.status == 'SKIPPED':
                skipped += 1
                messages.warning(request, f'{record.file_name}: {record.error}', extra_tags='warning')
            else:
                ok += 1

        if ok:
            messages.success(
                request,
                f'{ok} statement{"s" if ok != 1 else ""} read and ready for review. '
                'Check each one before importing.', extra_tags='info')
        if failed and not ok:
            messages.error(request, 'No statements could be read.', extra_tags='danger')
        return redirect('blackrose_statements')

    pending = BlackroseImport.objects.filter(status='PENDING')
    recent = BlackroseImport.objects.exclude(status='PENDING')[:25]
    return render(request, 'blackrose_statements.html', {
        'nav': 'existing_loan_functions',
        'pending': pending,
        'recent': recent,
        'pending_total': sum((r.closing_balance or 0) for r in pending),
    })


def _review_context(record, request=None):
    """Everything the review screen shows for one parsed statement."""
    statement = blackrose.Statement.from_dict(record.parsed or {})
    plan = blackrose.derive(statement)
    existing_client = blackrose.find_client(statement)

    prior_loans = []
    if existing_client:
        prior_loans = list(Loan.objects.filter(owner=existing_client)
                           .exclude(funded_category='COMPLETED')[:5])

    duplicates = BlackroseImport.objects.filter(
        client_code=record.client_code, status='IMPORTED').exclude(pk=record.pk)

    return {
        'record': record,
        'statement': statement,
        'plan': plan,
        'txns': statement.txns,
        'existing_client': existing_client,
        'prior_loans': prior_loans,
        'duplicates': duplicates,
        'locations': Location.objects.all(),
        'officers': StaffProfile.objects.all(),
        'default_officer': _staff_profile(request) if request else None,
    }


@check_staff
def blackrose_review(request, pk):
    """Check a parsed statement and, on confirmation, create the client + loan."""
    record = get_object_or_404(BlackroseImport, pk=pk)

    if record.status == 'IMPORTED':
        messages.info(request, f'This statement was already imported as loan {record.loan}.',
                      extra_tags='info')
        return redirect('view_loan_staff', record.loan.ref) if record.loan \
            else redirect('blackrose_statements')
    if not record.parsed:
        messages.error(request, f'This statement could not be read: {record.error}',
                       extra_tags='danger')
        return redirect('blackrose_statements')

    if request.method == 'POST':
        if request.POST.get('action') == 'skip':
            record.status = 'SKIPPED'
            record.error = 'Skipped by staff.'
            record.save()
            messages.info(request, f'{record.client_name}: statement skipped.', extra_tags='info')
            return redirect('blackrose_statements')
        return _commit(request, record)

    return render(request, 'blackrose_review.html', _review_context(record, request))


def _commit(request, record):
    """Apply the (possibly edited) review form and write the loan."""
    context = _review_context(record, request)
    statement = context['statement']
    plan = context['plan']

    # Staff corrections to what the parser read.
    statement.client_name = (request.POST.get('client_name') or statement.client_name).strip()
    statement.client_code = (request.POST.get('client_code') or statement.client_code).strip()
    statement.employer = (request.POST.get('employer') or '').strip()
    statement.address = (request.POST.get('address') or '').strip()
    statement.phone = (request.POST.get('phone') or '').strip()

    if not statement.client_name:
        messages.error(request, 'A client name is required.', extra_tags='danger')
        return render(request, 'blackrose_review.html', context)

    try:
        repayment_amount = blackrose.to_decimal(request.POST.get('repayment_amount'),
                                                default=plan['repayment_amount'])
        remaining = int(request.POST.get('remaining_fortnights') or plan['remaining_fortnights'])
        next_payment_date = datetime.date.fromisoformat(
            request.POST.get('next_payment_date') or plan['next_payment_date'].isoformat())
    except (TypeError, ValueError):
        messages.error(request, 'Check the repayment amount, term and next payment date.',
                       extra_tags='danger')
        return render(request, 'blackrose_review.html', context)

    if repayment_amount <= 0 and remaining > 0:
        messages.error(request, 'A running loan needs a fortnightly repayment amount above zero.',
                       extra_tags='danger')
        return render(request, 'blackrose_review.html', context)
    if next_payment_date < datetime.date.today() and remaining > 0:
        messages.error(
            request,
            'The next payment date is in the past — the loan would be defaulted the moment it is '
            'imported. Move it to the client\'s next pay date.', extra_tags='danger')
        return render(request, 'blackrose_review.html', context)

    profile = context['existing_client']
    if request.POST.get('client_choice') == 'new':
        profile = None
    elif request.POST.get('client_id'):
        profile = UserProfile.objects.filter(pk=request.POST['client_id']).first()

    # A blank officer select means "none" — only fall back to the signed-in
    # member of staff when the form did not carry the field at all.
    if 'officer' in request.POST:
        officer = StaffProfile.objects.filter(pk=request.POST['officer'] or 0).first()
    else:
        officer = _staff_profile(request)
    location = Location.objects.filter(pk=request.POST.get('location') or 0).first()

    try:
        with transaction.atomic():
            loan, profile, created = blackrose.import_statement(
                statement, plan, officer=officer, location=location, profile=profile,
                repayment_amount=repayment_amount, next_payment_date=next_payment_date,
                remaining_fortnights=remaining,
                notes=(request.POST.get('notes') or '').strip(),
            )
            record.status = 'IMPORTED'
            record.owner = profile
            record.loan = loan
            record.client_created = created
            record.imported_at = timezone.now()
            record.error = None
            record.client_name = statement.client_name[:255]
            record.client_code = statement.client_code[:50]
            record.save()
    except blackrose.BlackroseError as exc:
        messages.error(request, str(exc), extra_tags='danger')
        return render(request, 'blackrose_review.html', context)
    except Exception as exc:  # pragma: no cover - surfaced to staff, not swallowed
        logger.exception('Blackrose import failed for %s', record.pk)
        messages.error(request, f'The import failed and nothing was saved: {exc}',
                       extra_tags='danger')
        return render(request, 'blackrose_review.html', context)

    messages.success(
        request,
        f'{"Created client and loan" if created else "Created loan"} {loan.ref} for '
        f'{profile.first_name} {profile.last_name} — {record.row_count} statement lines, '
        f'balance K{loan.total_outstanding:,.2f}.', extra_tags='info')
    return redirect('view_loan_staff', loan.ref)


@check_staff
def blackrose_discard(request, pk):
    """Drop a parsed statement that is not going to be imported."""
    record = get_object_or_404(BlackroseImport, pk=pk)
    if record.status == 'IMPORTED':
        messages.error(request, 'An imported statement cannot be discarded — it is the audit '
                                'record for the loan it created.', extra_tags='danger')
        return redirect('blackrose_statements')
    name = record.client_name or record.file_name
    record.status = 'SKIPPED'
    record.error = 'Discarded by staff.'
    record.save()
    messages.info(request, f'{name}: statement discarded.', extra_tags='info')
    return redirect('blackrose_statements')
