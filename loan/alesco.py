"""Alesco payroll deduction listing — parsing, matching and processing.

The Alesco "Deduction Variation Report" is a fixed-layout text listing produced
by the government payroll (Alesco HRMS). Each detail line carries an employee
file number, the employee name, and the amount deducted "This Period" (plus the
prior period, variance and arrears columns).

This module:
  * parses the listing (header + detail rows),
  * maps each employee file number to a client (UserProfile.employee_file_number)
    and their active loan,
  * on confirmation, records the "This Period" amount as a repayment dated to the
    listing's Period End date — updating balances, creating a statement and
    (optionally) notifying the client, exactly as a normal pay update does.
"""

import datetime
import logging
import re
from decimal import Decimal

logger = logging.getLogger(__name__)

from django.conf import settings
from django.utils import timezone

from accounts.models import UserProfile, StaffProfile
from admin1.models import AdminSettings
from loan.models import Loan, Payment, Statement, AlescoPayRun, AlescoPayLine


# A detail line looks like:
#  10301954 01  Adolf, Bessie                    700.00                              700.00                0.00
#  00764744 02  Ohue, Shirley S                  152.44           272.44            -120.00                0.00
#  12806973 01  Fore, Peter                                      374.58            -374.58                0.00 Defaulted
# The This Period column can be BLANK, so numbers cannot be assigned by
# counting tokens — they are classified by their character position under the
# report's own column headers (values are right-aligned to each header).
# File numbers may carry a trailing letter (e.g. 0092287A) and lines may end
# with status text like "Defaulted".
_DETAIL_RE = re.compile(
    r'^\s*(?P<file>\d{5,}[A-Z]?)\s+(?P<job>\d{1,3})\s+(?P<rest>.+)$'
)
# Alesco prints zero amounts as ".00" (no leading digit) — the leading part
# must therefore be optional, or zero columns vanish entirely.
_NUM_RE = re.compile(r'-?(?:\d[\d,]*)?\.\d{2}')

_COLUMNS = ('this_period', 'last_period', 'variance', 'arrears')
_HEADERS = {'this_period': 'This Period', 'last_period': 'Last Period',
            'variance': 'Variance', 'arrears': 'Arrears'}


def _column_edges(text):
    """Right edge (character index) of each amount column, taken from the
    listing's own header row. Values are right-aligned to these headers."""
    for line in text.splitlines():
        if all(h in line for h in _HEADERS.values()):
            return {c: line.index(h) + len(h) for c, h in _HEADERS.items()}
    return None


def _classify_amounts(line, edges):
    """Map each number on the line to the column whose right edge is nearest
    the number's right edge. Blank columns simply produce no number."""
    out = {}
    for m in _NUM_RE.finditer(line):
        col = min(_COLUMNS, key=lambda c: abs(m.end() - edges[c]))
        out.setdefault(col, m.group())
    return out


def _to_decimal(text):
    try:
        return Decimal(str(text).replace(',', '').strip())
    except Exception:
        return Decimal('0')


def _parse_period_end(text):
    """Parse a date like '27-MAY-2026' → date, or None."""
    m = re.search(r'Period End\s+(\d{1,2})-([A-Za-z]{3})-(\d{4})', text)
    if not m:
        return None
    day, mon, year = m.groups()
    for fmt_mon in (mon.title(), mon.upper(), mon.lower()):
        try:
            return datetime.datetime.strptime(f'{day}-{fmt_mon}-{year}', '%d-%b-%Y').date()
        except ValueError:
            continue
    return None


def parse_alesco_text(text):
    """Parse the raw listing text. Returns a dict with header fields and rows."""
    header = {
        'period_end': _parse_period_end(text),
        'pay_period': None,
        'pay_year': None,
        'paycode': None,
        'employer_name': None,
        'company_code': None,
    }

    m = re.search(r'Period\s+(\d+)\s+Year\s+(\d+)', text)
    if m:
        header['pay_period'], header['pay_year'] = m.group(1), m.group(2)

    m = re.search(r'Paycode:\s+(\S+)\s+(.+?)\s+Paid by', text)
    if m:
        header['paycode'] = m.group(1).strip()
        header['employer_name'] = m.group(2).strip()
    else:
        m = re.search(r'Paycode:\s+(\S+)\s+(.+)', text)
        if m:
            header['paycode'] = m.group(1).strip()
            header['employer_name'] = m.group(2).strip()

    m = re.search(r'Company Code:\s+(.+)', text)
    if m:
        header['company_code'] = m.group(1).strip()

    edges = _column_edges(text)
    rows = []
    for line in text.splitlines():
        match = _DETAIL_RE.match(line)
        if not match:
            continue
        first_num = _NUM_RE.search(line, match.start('rest'))
        name = line[match.start('rest'):(first_num.start() if first_num else None)].strip()
        if not name:
            continue

        if edges:
            amounts = _classify_amounts(line, edges)
        else:
            # no header row found — fall back to the old token-count heuristic
            nums = _NUM_RE.findall(line[match.start('rest'):])
            amounts = {}
            if len(nums) >= 4:
                amounts = dict(zip(_COLUMNS, nums))
            elif len(nums) == 3:
                amounts = {'this_period': nums[0], 'variance': nums[1], 'arrears': nums[2]}
            elif len(nums) == 2:
                amounts = {'this_period': nums[0], 'arrears': nums[1]}
            elif len(nums) == 1:
                amounts = {'this_period': nums[0]}

        rows.append({
            'employee_file_number': match.group('file').strip(),
            'job_number': match.group('job').strip(),
            'report_name': name,
            'this_period': _to_decimal(amounts.get('this_period', '0')),
            'last_period': _to_decimal(amounts.get('last_period', '0')),
            'file_variance': _to_decimal(amounts.get('variance', '0')),
            'arrears': _to_decimal(amounts.get('arrears', '0')),
        })
    return {'header': header, 'rows': rows}


def find_client_for_file_number(file_number):
    """Return the UserProfile whose employee_file_number matches, or None.

    Matches exactly first, then falls back to a leading-zero-insensitive match
    (the listing zero-pads file numbers, client records may not)."""
    if not file_number:
        return None
    fn = str(file_number).strip()
    qs = UserProfile.objects.filter(employee_file_number=fn)
    owner = qs.first()
    if owner:
        return owner
    stripped = fn.lstrip('0')
    if stripped and stripped != fn:
        owner = UserProfile.objects.filter(employee_file_number=stripped).first()
        if owner:
            return owner
    # last resort: compare with leading zeros stripped on both sides
    for up in UserProfile.objects.exclude(employee_file_number__isnull=True).exclude(employee_file_number=''):
        if str(up.employee_file_number).strip().lstrip('0') == stripped:
            return up
    return None


def _levenshtein_le(a, b, max_dist):
    """True if edit distance between a and b is <= max_dist (small strings only —
    file numbers are a handful of characters, so the naive O(n*m) table is fine)."""
    if abs(len(a) - len(b)) > max_dist:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1] <= max_dist


def find_typo_candidates(file_number, max_dist=1, limit=5):
    """Clients whose employee_file_number is a near-miss (small edit distance)
    of ``file_number`` — used to suggest a fix when a payroll file number does
    not match any client exactly (a likely data-entry typo on either side)."""
    fn = str(file_number or '').strip()
    if not fn:
        return []
    out = []
    for up in UserProfile.objects.exclude(employee_file_number__isnull=True).exclude(employee_file_number=''):
        efn = str(up.employee_file_number).strip()
        if efn == fn:
            continue
        if _levenshtein_le(fn, efn, max_dist) or _levenshtein_le(fn.lstrip('0'), efn.lstrip('0'), max_dist):
            out.append(up)
            if len(out) >= limit:
                break
    return out


# Unmatched-line reason categories, in the order they should be checked/shown.
UNMATCHED_NO_CLIENT = 'NO_CLIENT_RECORD'
UNMATCHED_NO_LOAN = 'NO_ACTIVE_LOAN'
UNMATCHED_AMBIGUOUS = 'AMBIGUOUS_MATCH'
UNMATCHED_TYPO = 'POSSIBLE_TYPO'

UNMATCHED_REASON_LABELS = {
    UNMATCHED_NO_CLIENT: 'No client record for this file number',
    UNMATCHED_NO_LOAN: 'Client on file, but has no loan to apply this to',
    UNMATCHED_AMBIGUOUS: 'File number matches more than one client',
    UNMATCHED_TYPO: 'Likely typo — a close file-number match exists',
}


def classify_unmatched_line(line):
    """Categorise WHY an UNMATCHED AlescoPayLine has no loan to post to.

    Returns (category, candidates) — candidates is a list of UserProfile
    suggestions for AMBIGUOUS_MATCH / POSSIBLE_TYPO, else [].
    """
    if line.owner_id:
        # A client record was found at upload time but they have no Loan row
        # at all (find_target_loan came back empty) — nothing to "link", the
        # file number itself isn't the problem.
        return UNMATCHED_NO_LOAN, []

    fn = str(line.employee_file_number or '').strip()
    exact = list(UserProfile.objects.filter(employee_file_number=fn)) if fn else []
    if not exact:
        stripped = fn.lstrip('0')
        if stripped and stripped != fn:
            exact = list(UserProfile.objects.filter(employee_file_number=stripped))
    if len(exact) > 1:
        return UNMATCHED_AMBIGUOUS, exact[:5]

    candidates = find_typo_candidates(fn)
    if candidates:
        return UNMATCHED_TYPO, candidates
    return UNMATCHED_NO_CLIENT, []


def relink_unmatched_line(line, new_file_number):
    """Re-match an UNMATCHED line against a (corrected) employee file number.

    Returns (ok, message). On success the line's owner/loanref/employer/expected
    figures are updated and its status flips to PENDING (payable) — it then
    appears normally on the Alesco Confirm page and disappears from Unmatched,
    since both read the same AlescoPayLine row.
    """
    if line.status != 'UNMATCHED':
        return False, 'Line is not unmatched.'

    owner = find_client_for_file_number(new_file_number)
    if not owner:
        return False, f'No client found with file number "{new_file_number}".'

    loan = find_target_loan(owner)
    if not loan:
        return False, f'{owner} has no loan on record to apply this payment to.'

    line.owner = owner
    line.loanref = loan
    line.employer_name = owner.employer
    line.expected_repayment = expected_repayment_for(loan)
    line.variance = (line.this_period or Decimal('0')) - line.expected_repayment
    line.status = 'PENDING' if (line.this_period or Decimal('0')) > 0 else 'SKIPPED'
    line.save(update_fields=['owner', 'loanref', 'employer_name', 'expected_repayment',
                              'variance', 'status'])
    logger.info("ALESCO-RELINK line=%s file_number=%s -> owner=%s loan=%s",
                line.pk, new_file_number, owner, loan.ref)
    return True, f'Linked to {owner} ({loan.ref}) — now pending confirmation.'


def find_target_loan(owner):
    """Return the loan an Alesco deduction should be applied to for this client.

    Prefers a funded, still-outstanding loan (most recently funded)."""
    if not owner:
        return None
    base = Loan.objects.filter(owner=owner, category='FUNDED')
    loan = base.filter(total_outstanding__gt=0).exclude(
        funded_category__in=['COMPLETED', 'ARCHIVED']
    ).order_by('-funding_date').first()
    if loan:
        return loan
    return base.order_by('-funding_date').first()


def expected_repayment_for(loan):
    return (loan.repayment_amount or Decimal('0')) if loan else Decimal('0')


def create_pay_run(uploaded_file, staff_profile=None):
    """Parse an uploaded listing and persist an AlescoPayRun with its lines."""
    raw = uploaded_file.read()
    if isinstance(raw, bytes):
        text = raw.decode('utf-8', errors='replace')
    else:
        text = raw
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    parsed = parse_alesco_text(text)
    header = parsed['header']
    rows = parsed['rows']

    total = sum((r['this_period'] for r in rows), Decimal('0'))

    run = AlescoPayRun.objects.create(
        file=uploaded_file,
        file_name=getattr(uploaded_file, 'name', 'alesco.txt'),
        period_end=header['period_end'],
        pay_period=header['pay_period'],
        pay_year=header['pay_year'],
        paycode=header['paycode'],
        employer_name=header['employer_name'],
        company_code=header['company_code'],
        total_this_period=total,
        employee_count=len(rows),
        uploaded_by=staff_profile,
        status='PENDING',
    )
    run.ref = f'ALS{run.pk}'
    run.save(update_fields=['ref'])

    for r in rows:
        owner = find_client_for_file_number(r['employee_file_number'])
        loan = find_target_loan(owner) if owner else None
        expected = expected_repayment_for(loan)
        AlescoPayLine.objects.create(
            run=run,
            employee_file_number=r['employee_file_number'],
            job_number=r['job_number'],
            report_name=r['report_name'],
            this_period=r['this_period'],
            last_period=r['last_period'],
            file_variance=r['file_variance'],
            arrears=r['arrears'],
            owner=owner,
            loanref=loan,
            employer_name=(owner.employer if owner else None),
            expected_repayment=expected,
            variance=(r['this_period'] - expected),
            payment_date=header['period_end'],
            # Zero deduction = nothing came in this pay — mark SKIPPED so it
            # can't be confirmed as a payment. Otherwise PENDING when matched.
            status=('SKIPPED' if r['this_period'] <= 0 else ('PENDING' if loan else 'UNMATCHED')),
        )
    return run


def _alesco_notify_enabled():
    try:
        s = AdminSettings.objects.get(settings_name='setting1')
        return bool(s.send_alesco_pay_update_email)
    except AdminSettings.DoesNotExist:
        return True


# Every Loan field any of the payment-application paths can mutate
# (process_repayment / process_advance_payment / process_default,
# engine.charge_shortfall, schedule.settle, complete_loan).
_SNAPSHOT_FIELDS = (
    'category', 'funded_category', 'status', 'next_payment_date',
    'principal_loan_paid', 'interest_paid', 'default_interest_paid', 'total_paid',
    'fortnights_paid', 'fortnights_settled', 'number_of_repayments',
    'last_repayment_amount', 'last_repayment_date',
    'number_of_advance_payments', 'last_advance_payment_date',
    'last_advance_payment_amount', 'total_advance_payment',
    'advance_payment_surplus', 'advance_balance',
    'number_of_defaults', 'last_default_date', 'last_default_amount',
    'days_in_default', 'total_arrears', 'principal_loan_receivable',
    'ordinary_interest_receivable', 'default_interest_receivable',
    'total_outstanding',
)


def _loan_snapshot(loan):
    """JSON-safe snapshot of the loan state before a line is applied."""
    import datetime as _dt
    snap = {}
    for f in _SNAPSHOT_FIELDS:
        v = getattr(loan, f)
        if isinstance(v, Decimal):
            v = str(v)
        elif isinstance(v, (_dt.date, _dt.datetime)):
            v = v.isoformat()
        snap[f] = v
    last_stmt = Statement.objects.filter(loanref=loan).order_by('-pk').values_list('pk', flat=True).first()
    snap['_stmt_max_id'] = last_stmt or 0
    snap['_owner_has_loan'] = bool(getattr(loan.owner, 'has_loan', True)) if loan.owner else True
    return snap


def _restore_snapshot(loan, snap):
    import datetime as _dt
    from django.db import models as _m
    for f in _SNAPSHOT_FIELDS:
        v = snap.get(f)
        field = loan._meta.get_field(f)
        if v is not None:
            if isinstance(field, _m.DecimalField):
                v = Decimal(str(v))
            elif isinstance(field, _m.DateField) and not isinstance(field, _m.DateTimeField):
                v = _dt.date.fromisoformat(v)
            elif isinstance(field, _m.DateTimeField):
                v = _dt.datetime.fromisoformat(v)
        setattr(loan, f, v)
    loan.save()


def confirm_line(request, line, officer=None, pay_date=None):
    """Apply one Alesco line as a repayment — updating balances, creating a
    statement and (per Loan Settings) notifying the client. Mirrors the staff
    payment entry flow. ``pay_date`` (the confirm page's universal Payment Date)
    overrides the line/run date when given. Returns (ok, message)."""
    from loan.functions import process_repayment, process_advance_payment, process_default

    if line.status == 'CONFIRMED':
        return False, 'Already confirmed.'
    loan = line.loanref
    if loan is None:
        line.status = 'UNMATCHED'
        line.save(update_fields=['status'])
        return False, 'No matching client/loan for this file number.'

    user = loan.owner
    amount = line.this_period or Decimal('0')
    if amount <= 0:
        return False, 'No amount to post for this employee.'

    # Snapshot the loan state first so this confirmation can be rolled back.
    line.loan_snapshot = _loan_snapshot(loan)
    line.save(update_fields=['loan_snapshot'])
    date = pay_date or line.payment_date or (line.run.period_end if line.run else timezone.localdate())
    desc = f'ALESCO Payroll Deduction — Period {line.run.pay_period or ""}/{line.run.pay_year or ""}'.strip()
    notify = _alesco_notify_enabled()

    payment = Payment.objects.create(
        owner=user, loanref=loan, date=date, amount=amount,
        mode='PAYROLL DEDUCTION', statement=desc, officer=officer,
    )
    stat = Statement.objects.create(
        owner=user, loanref=loan, date=date, debit=amount, statement=desc,
        type='PAYMENT', uid=user.uid, luid=settings.LUID,
    )
    p_count = (loan.number_of_repayments or 0) + 1
    payment.ref = f'{loan.ref}P{p_count}'
    payment.p_count = p_count
    payment.save()
    stat.s_count = (stat.s_count or 0) + 1
    stat.ref = f'{loan.ref}SP{stat.s_count}'
    stat.save()

    ramount = loan.repayment_amount or Decimal('0')
    tol_pos = settings.TOTAL_ALLOWABLE_TOEAS
    tol_neg = -settings.TOTAL_ALLOWABLE_TOEAS
    tol_neg_amount = ramount + tol_neg
    tol_pos_amount = ramount + tol_pos

    # Paid before the next due date with no arrears = an ADVANCE payment.
    from loan import schedule as _sched
    _next_due = _sched.next_due_date(loan)
    _early = (_next_due is not None and date < _next_due and (loan.total_arrears or 0) <= 0)

    if _early and amount >= tol_neg_amount:
        payment.type = 'ADVANCE PAYMENT'
        payment.save()
        process_advance_payment(request, loan, stat, amount, notify=notify)
    elif _early:
        from loan.engine import record_advance as _record_advance
        payment.type = 'ADVANCE PAYMENT'
        payment.save()
        stat.type = 'PAYMENT'
        stat.balance = loan.total_outstanding
        stat.save()
        _record_advance(loan, amount, date, user)
        loan.save()
    elif amount < tol_neg_amount:
        # Short deduction: charge default interest on the shortfall and record arrears.
        payment.type = 'PARTIAL PAYMENT'
        payment.save()
        process_default(request, loan, stat, amount, notify=notify)
    elif amount > tol_pos_amount:
        payment.type = 'ADVANCE PAYMENT'
        payment.save()
        process_advance_payment(request, loan, stat, amount, notify=notify)
    else:
        payment.type = 'NORMAL REPAYMENT'
        payment.save()
        process_repayment(request, loan, stat, amount, notify=notify)

    line.payment = payment
    line.status = 'CONFIRMED'
    line.confirmed_at = timezone.now()
    line.confirmed_by = officer
    line.save(update_fields=['payment', 'status', 'confirmed_at', 'confirmed_by'])

    _refresh_run_status(line.run)
    return True, 'Confirmed.'


def _refresh_run_status(run):
    lines = run.lines.all()
    total = lines.count()
    confirmed = lines.filter(status='CONFIRMED').count()
    pending = lines.filter(status='PENDING').count()
    if confirmed == 0:
        run.status = 'PENDING'
    elif pending == 0:
        run.status = 'COMPLETED'
    else:
        run.status = 'PARTIAL'
    run.save(update_fields=['status'])


def confirm_run(request, run, officer=None, pay_date=None):
    """Confirm every still-pending, matched line in a run. Returns (n_ok, n_fail)."""
    n_ok = 0
    n_fail = 0
    for line in run.lines.filter(status='PENDING'):
        ok, _msg = confirm_line(request, line, officer=officer, pay_date=pay_date)
        if ok:
            n_ok += 1
        else:
            n_fail += 1
    _refresh_run_status(run)
    return n_ok, n_fail


def rollback_line(line):
    """Reverse a confirmed Alesco line: restore the loan to its pre-confirmation
    snapshot, delete the payment and the statement lines the confirmation
    created, and reset the line to PENDING. Returns (ok, message).

    Refused when there has been ANY later activity on the loan (a newer payment
    or statement) — restoring the snapshot would silently wipe that work.
    """
    from django.db import transaction

    if line.status != 'CONFIRMED':
        return False, 'Line is not confirmed.'
    snap = line.loan_snapshot
    if not snap:
        return False, 'No pre-confirmation snapshot exists for this line (confirmed before rollback support); reverse it manually.'
    loan = line.loanref
    if loan is None:
        return False, 'The loan this line was applied to no longer exists.'

    # Block if anything happened on this loan after the confirmation.
    if line.confirmed_at:
        if Payment.objects.filter(loanref=loan, created_at__gt=line.confirmed_at).exists() or \
           Statement.objects.filter(loanref=loan, created_at__gt=line.confirmed_at).exists():
            return False, (f'{loan.ref}: newer payments/statements exist on this loan — '
                           'rollback would erase them. Reverse manually.')

    with transaction.atomic():
        locked = type(loan).objects.select_for_update().get(pk=loan.pk)
        # Delete everything this confirmation wrote to the ledger.
        Statement.objects.filter(loanref=locked, pk__gt=snap.get('_stmt_max_id', 0)).delete()
        if line.payment_id:
            Payment.objects.filter(pk=line.payment_id).delete()
        _restore_snapshot(locked, snap)
        # complete_loan() flips the client's has_loan flag — restore it too.
        if locked.owner and snap.get('_owner_has_loan') is not None:
            if bool(getattr(locked.owner, 'has_loan', None)) != bool(snap['_owner_has_loan']):
                locked.owner.has_loan = bool(snap['_owner_has_loan'])
                locked.owner.save(update_fields=['has_loan'])
        line.payment = None
        line.status = 'PENDING'
        line.confirmed_at = None
        line.confirmed_by = None
        line.loan_snapshot = None
        line.save(update_fields=['payment', 'status', 'confirmed_at', 'confirmed_by', 'loan_snapshot'])
        _refresh_run_status(line.run)
    logger.info("ALESCO-ROLLBACK line=%s loan=%s", line.pk, loan.ref)
    return True, f'{loan.ref}: confirmation rolled back.'


def rollback_run(run):
    """Roll back every confirmed line in a run (newest first). Returns
    (n_rolled, blocked) where blocked is a list of per-line failure messages."""
    n_rolled = 0
    blocked = []
    for line in run.lines.filter(status='CONFIRMED').order_by('-confirmed_at', '-pk'):
        ok, msg = rollback_line(line)
        if ok:
            n_rolled += 1
        else:
            blocked.append(msg)
    _refresh_run_status(run)
    return n_rolled, blocked


def cancel_run(run):
    """Cancel an upload entirely: roll back whatever was confirmed, drop the
    pending lines, and delete the run so the file can be re-uploaded.
    Returns (ok, n_rolled, blocked). The run is only deleted when every
    confirmed line rolled back cleanly."""
    n_rolled, blocked = rollback_run(run)
    if blocked:
        return False, n_rolled, blocked
    run.delete()
    return True, n_rolled, []
