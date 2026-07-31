"""Client Files — one place to view every document uploaded for a client
(personal/KYC docs + each loan's documents) and add or replace any of them.
"""
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.db.models import Q
from django.shortcuts import redirect, render

from accounts.models import UserProfile
from loan.models import Loan, LoanFile


# Personal / KYC documents that live on the client's UserProfile.
PROFILE_DOCS = [
    ('propic', 'Profile Photo'),
    ('nid', 'National ID'),
    ('passport', 'Passport'),
    ('drivers_license', "Driver's License"),
    ('superid', 'Super ID'),
    ('work_id', 'Work ID'),
    ('bank_standing_order', 'Bank Standing Order'),
]

# Documents that live on each of the client's LoanFile records.
LOANFILE_DOCS = [
    ('application_form', 'Application Form'),
    ('terms_conditions', 'Terms & Conditions'),
    ('stat_dec', 'Statutory Declaration'),
    ('irr_sd_form', 'Salary Deduction Authority (IRSDA)'),
    ('work_confirmation_letter', 'Work Confirmation Letter'),
    ('payslip1', 'Payslip 1'),
    ('payslip2', 'Payslip 2'),
    ('bank_statement', 'Bank Statement'),
    ('super_statement', 'Super Statement'),
    ('funding_receipt', 'Funding Receipt'),
]


def _allowed(request):
    if not request.user.is_authenticated:
        return False
    if request.user.is_superuser:
        return True
    prof = UserProfile.objects.filter(user_id=request.user.id).first()
    return bool(prof and prof.category == 'STAFF')


def _doc_view(instance, field, label):
    file_field = getattr(instance, field, None)
    url = ''
    try:
        if file_field:
            url = file_field.url
    except Exception:
        url = ''
    if not url:
        url = getattr(instance, f'{field}_url', '') or ''
    return {'field': field, 'label': label, 'url': url, 'has': bool(url)}


def client_files(request, uid):
    if not _allowed(request):
        messages.error(request, "You do not have permission to view this page.", extra_tags='danger')
        return redirect('dashboard')

    client = UserProfile.objects.get(id=uid)

    if request.method == 'POST':
        scope = request.POST.get('scope')
        field = request.POST.get('field')
        fhandle = request.FILES.get('file')
        # Validate upload (type/size) using the shared validator.
        from accounts.functions import validate_upload
        valid_profile_fields = {f for f, _ in PROFILE_DOCS}
        valid_loan_fields = {f for f, _ in LOANFILE_DOCS}

        if fhandle and validate_upload(request, fhandle):
            if scope == 'profile' and field in valid_profile_fields:
                _save(client, field, fhandle, f'{client.first_name}_{client.last_name}_{field}')
                messages.success(request, f'{field.replace("_", " ").title()} uploaded for {client.first_name}.', extra_tags='info')
            elif scope == 'loan' and field in valid_loan_fields:
                loan = Loan.objects.get(id=request.POST.get('loan_id'), owner=client)
                loanfile, _ = LoanFile.objects.get_or_create(loan=loan)
                _save(loanfile, field, fhandle, f'{client.first_name}_{client.last_name}_{loan.ref}_{field}')
                messages.success(request, f'{field.replace("_", " ").title()} uploaded for {loan.ref}.', extra_tags='info')
        return redirect('client_files', uid=uid)

    profile_docs = [_doc_view(client, f, label) for f, label in PROFILE_DOCS]

    loans = Loan.objects.filter(owner=client).order_by('-created_at')
    loan_blocks = []
    for loan in loans:
        loanfile = LoanFile.objects.filter(loan=loan).first()
        docs = [_doc_view(loanfile, f, label) if loanfile else {'field': f, 'label': label, 'url': '', 'has': False}
                for f, label in LOANFILE_DOCS]
        loan_blocks.append({'loan': loan, 'docs': docs})

    return render(request, 'client_files.html', {
        'nav': 'clients',
        'client': client,
        'profile_docs': profile_docs,
        'loan_blocks': loan_blocks,
    })


def _save(instance, field, fhandle, base_name):
    fs = FileSystemStorage()
    renamed = f'{base_name}_{fhandle.name}'
    filename = fs.save(renamed, fhandle)
    setattr(instance, field, filename)
    if hasattr(instance, f'{field}_url'):
        setattr(instance, f'{field}_url', fs.url(filename))
    instance.save()


def loan_files(request, loan_ref=None):
    """Upload Files for Existing Loan — pick any loan from a list (not a
    specific client), then add/replace its LoanFile documents. Same document
    set and upload mechanism as the per-client Client Files page, just entered
    from the loan side instead of the client side."""
    if not _allowed(request):
        messages.error(request, "You do not have permission to view this page.", extra_tags='danger')
        return redirect('dashboard')

    if not loan_ref:
        q = (request.GET.get('q') or '').strip()
        loans = Loan.objects.exclude(category='PENDING').select_related('owner').order_by('-created_at')
        if q:
            loans = loans.filter(Q(ref__icontains=q) | Q(owner__first_name__icontains=q) |
                                  Q(owner__last_name__icontains=q))
        return render(request, 'loan_files_select.html', {
            'nav': 'existing_loan_functions', 'loans': loans[:200], 'q': q,
        })

    loan = Loan.objects.select_related('owner').get(ref=loan_ref)

    if request.method == 'POST':
        field = request.POST.get('field')
        fhandle = request.FILES.get('file')
        from accounts.functions import validate_upload
        valid_loan_fields = {f for f, _ in LOANFILE_DOCS}
        if fhandle and field in valid_loan_fields and validate_upload(request, fhandle):
            loanfile, _ = LoanFile.objects.get_or_create(loan=loan)
            _save(loanfile, field, fhandle, f'{loan.owner.first_name}_{loan.owner.last_name}_{loan.ref}_{field}')
            messages.success(request, f'{field.replace("_", " ").title()} uploaded for {loan.ref}.', extra_tags='info')
        return redirect('loan_files', loan_ref=loan_ref)

    loanfile = LoanFile.objects.filter(loan=loan).first()
    docs = [_doc_view(loanfile, f, label) if loanfile else {'field': f, 'label': label, 'url': '', 'has': False}
            for f, label in LOANFILE_DOCS]

    return render(request, 'loan_files_upload.html', {
        'nav': 'existing_loan_functions', 'loan': loan, 'docs': docs,
    })
