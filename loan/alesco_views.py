"""Alesco Update views — shared between the admin and staff portals.

The concrete, decorated entry points live in each portal (admin1 / staff) and
delegate here with a ``portal`` key so the same logic renders inside the correct
base template and reverses the correct URL names.
"""

import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import StaffProfile
from loan.models import AlescoPayRun, AlescoPayLine
from loan.alesco import (create_pay_run, confirm_line, confirm_run,
                         rollback_line, rollback_run, cancel_run,
                         classify_unmatched_line, relink_unmatched_line,
                         UNMATCHED_REASON_LABELS)
from loan.forms import AlescoUploadForm


PORTALS = {
    'admin': {
        'base_template': 'admin_base.html',
        'nav': 'alesco_update',
        'url_upload': 'alesco_update',
        'url_confirm': 'alesco_confirm',
        'url_data': 'alesco_data',
        'url_confirm_line': 'alesco_confirm_line',
        'url_confirm_all': 'alesco_confirm_all',
        'url_rollback_line': 'alesco_rollback_line',
        'url_rollback': 'alesco_rollback',
        'url_cancel': 'alesco_cancel',
        'url_unmatched': 'alesco_unmatched',
    },
    'staff': {
        'base_template': 'staff_base.html',
        'nav': 'alesco_update',
        'url_upload': 'staff_alesco_update',
        'url_confirm': 'staff_alesco_confirm',
        'url_data': 'staff_alesco_data',
        'url_confirm_line': 'staff_alesco_confirm_line',
        'url_confirm_all': 'staff_alesco_confirm_all',
        'url_rollback_line': 'staff_alesco_rollback_line',
        'url_rollback': 'staff_alesco_rollback',
        'url_cancel': 'staff_alesco_cancel',
        'url_unmatched': 'staff_alesco_unmatched',
    },
}


def _pay_date(request):
    """Universal Payment Date sent by the confirm page (YYYY-MM-DD), or None."""
    import datetime
    raw = (request.POST.get('date') or '').strip()
    try:
        return datetime.date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _officer(request):
    try:
        return StaffProfile.objects.filter(user__user=request.user).first() \
            or StaffProfile.objects.filter(user=request.user).first()
    except Exception:
        return None


def _money(v):
    try:
        return '{:,.2f}'.format(v or 0)
    except Exception:
        return '0.00'


def upload(request, portal):
    cfg = PORTALS[portal]
    if request.method == 'POST':
        form = AlescoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                run = create_pay_run(form.cleaned_data['file'], _officer(request))
            except Exception as exc:
                messages.error(request, f'Could not process the file: {exc}', extra_tags='danger')
                return redirect(cfg['url_upload'])
            if run.employee_count == 0:
                messages.warning(request, 'No employee deduction rows were found in that file. '
                                          'Please check it is the Alesco Deduction Variation listing.',
                                 extra_tags='warning')
                run.delete()
                return redirect(cfg['url_upload'])
            messages.success(request, f'Loaded {run.employee_count} employees from the listing. '
                                      'Review and confirm the payments below.', extra_tags='info')
            return redirect(cfg['url_confirm'], run_id=run.pk)
        messages.error(request, 'Please attach a valid Alesco listing file.', extra_tags='danger')
    else:
        form = AlescoUploadForm()

    runs = AlescoPayRun.objects.order_by('-created_at')[:25]
    # Run-level rollback is offered only on the MOST RECENT confirmed upload —
    # rolling back an older one while later runs touched the same loans is
    # blocked line-by-line anyway, so don't advertise it.
    latest_confirmed_id = next((r.pk for r in runs if r.status in ('COMPLETED', 'PARTIAL')), None)
    return render(request, 'alesco/alesco_upload.html', {
        'form': form,
        'runs': runs,
        'latest_confirmed_id': latest_confirmed_id,
        'nav': cfg['nav'],
        'base_template': cfg['base_template'],
        'urls': cfg,
    })


def confirm(request, run_id, portal):
    cfg = PORTALS[portal]
    run = get_object_or_404(AlescoPayRun, pk=run_id)
    matched = run.lines.exclude(status='UNMATCHED').count()
    unmatched = run.lines.filter(status='UNMATCHED').count()
    pending = run.lines.filter(status='PENDING').count()
    return render(request, 'alesco/alesco_confirm.html', {
        'run': run,
        'matched': matched,
        'unmatched': unmatched,
        'pending': pending,
        'nav': cfg['nav'],
        'base_template': cfg['base_template'],
        'urls': cfg,
    })


def data(request, run_id):
    """JSON rows for the confirmation DataTable."""
    run = get_object_or_404(AlescoPayRun, pk=run_id)
    rows = []
    for line in run.lines.all():
        rows.append({
            'id': line.pk,
            'employee': f'{line.employee_file_number} ({line.job_number})' if line.job_number else line.employee_file_number,
            'file_number': line.employee_file_number,
            'client': (f'{line.owner.first_name} {line.owner.last_name}'.strip() if line.owner else line.report_name),
            'report_name': line.report_name,
            'loanref': (line.loanref.ref if line.loanref else ''),
            'this_period': _money(line.this_period),
            'expected': _money(line.expected_repayment),
            'variance': _money(line.variance),
            'variance_val': float(line.variance or 0),
            'status': line.status,
        })
    return JsonResponse({
        'period_end': run.period_end.strftime('%Y-%m-%d') if run.period_end else '',
        'employer': run.employer_name or '',
        'paycode': run.paycode or '',
        'pay_period': f"{run.pay_period or ''}/{run.pay_year or ''}",
        'status': run.status,
        'rows': rows,
    })


@require_POST
def confirm_line_view(request, line_id):
    line = get_object_or_404(AlescoPayLine, pk=line_id)
    ok, msg = confirm_line(request, line, officer=_officer(request), pay_date=_pay_date(request))
    line.refresh_from_db()
    return JsonResponse({
        'ok': ok,
        'message': msg,
        'status': line.status,
        'loanref': (line.loanref.ref if line.loanref else ''),
        'run_status': line.run.status,
    })


@require_POST
def confirm_all_view(request, run_id, portal):
    """Confirm pending lines. With ?batch=N the request processes at most N
    lines past the ?after=<line id> cursor and returns progress JSON — the page
    loops these small requests so no proxy/worker timeout is ever hit and a
    progress bar can be shown. Batching always walks the FULL pending set of
    the run (server-side), never just the rows visible in the table.

    Without ?batch it behaves as before (whole run in one request) — only
    suitable for small runs.
    """
    run = get_object_or_404(AlescoPayRun, pk=run_id)
    officer = _officer(request)
    pay_date = _pay_date(request)

    try:
        batch = int(request.GET.get('batch') or 0)
    except (TypeError, ValueError):
        batch = 0
    if batch > 0:
        try:
            after = int(request.GET.get('after') or 0)
        except (TypeError, ValueError):
            after = 0
        lines = list(run.lines.filter(status='PENDING', pk__gt=after).order_by('pk')[:batch])
        n_ok = n_fail = 0
        failures = []
        for line in lines:
            ok, msg = confirm_line(request, line, officer=officer, pay_date=pay_date)
            if ok:
                n_ok += 1
            else:
                n_fail += 1
                failures.append(f'{line.report_name or line.employee_file_number}: {msg}')
        run.refresh_from_db()
        last = lines[-1].pk if lines else after
        remaining = run.lines.filter(status='PENDING', pk__gt=last).count()
        return JsonResponse({
            'ok': True, 'confirmed': n_ok, 'failed': n_fail, 'failures': failures,
            'last': last, 'remaining': remaining, 'done': not lines,
            'run_status': run.status,
        })

    n_ok, n_fail = confirm_run(request, run, officer=officer, pay_date=pay_date)
    run.refresh_from_db()
    payload = {'ok': True, 'confirmed': n_ok, 'failed': n_fail, 'run_status': run.status}
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax'):
        return JsonResponse(payload)
    messages.success(request, f'Confirmed {n_ok} payment(s).'
                              + (f' {n_fail} could not be processed.' if n_fail else ''),
                     extra_tags='info')
    return redirect(PORTALS[portal]['url_confirm'], run_id=run.pk)


@require_POST
def rollback_line_view(request, line_id):
    """Reverse one confirmed line (AJAX from the confirm page)."""
    line = get_object_or_404(AlescoPayLine, pk=line_id)
    ok, msg = rollback_line(line)
    line.refresh_from_db()
    return JsonResponse({
        'ok': ok,
        'message': msg,
        'status': line.status,
        'run_status': line.run.status,
    })


@require_POST
def rollback_run_view(request, run_id, portal):
    """Fully undo an upload: reverse every confirmed payment, discard the
    pending lines, and delete the run — a clean slate to re-upload the file.
    If any confirmed line is blocked (later activity on its loan), nothing is
    deleted so the state stays visible."""
    run = get_object_or_404(AlescoPayRun, pk=run_id)
    ref = run.ref
    ok, n_rolled, blocked = cancel_run(run)
    if ok:
        messages.success(request,
                         f'Upload {ref} rolled back and removed'
                         + (f' — {n_rolled} confirmed payment(s) reversed.' if n_rolled else '.')
                         + ' You can re-upload the file.',
                         extra_tags='info')
        return redirect(PORTALS[portal]['url_upload'])
    for msg in blocked:
        messages.error(request, f'Not rolled back — {msg}', extra_tags='danger')
    messages.warning(request,
                     f'Upload {ref} was NOT removed: some confirmed payments could not be reversed. '
                     'Review the loans above, then retry.',
                     extra_tags='warning')
    return redirect(PORTALS[portal]['url_confirm'], run_id=run.pk)


@require_POST
def cancel_run_view(request, run_id, portal):
    """Cancel the whole upload: roll back confirmed lines, discard pending
    ones, delete the run so the tenant can re-upload the file."""
    run = get_object_or_404(AlescoPayRun, pk=run_id)
    ref = run.ref
    ok, n_rolled, blocked = cancel_run(run)
    if ok:
        messages.success(request,
                         f'Upload {ref} cancelled.'
                         + (f' {n_rolled} confirmed payment(s) rolled back.' if n_rolled else '')
                         + ' You can re-upload the file.',
                         extra_tags='info')
    else:
        for msg in blocked:
            messages.error(request, f'Cannot cancel — {msg}', extra_tags='danger')
        return redirect(PORTALS[portal]['url_confirm'], run_id=run.pk)
    return redirect(PORTALS[portal]['url_upload'])


def unmatched_payments(request, portal):
    """UNMATCHED PAYMENT LISTING — every Alesco deduction received for a person
    who is not a client (unmatched file number, money > 0), across all uploads,
    with refund tracking so it is always clear whom to pay back and how much."""
    import csv
    import datetime as _dt
    from decimal import Decimal
    from django.http import HttpResponse

    cfg = PORTALS[portal]

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'relink':
            line = get_object_or_404(AlescoPayLine, pk=request.POST.get('line_id'), status='UNMATCHED')
            new_fn = (request.POST.get('file_number') or '').strip()
            ok, msg = relink_unmatched_line(line, new_fn)
            if ok:
                messages.success(request, msg, extra_tags='info')
            else:
                messages.error(request, msg, extra_tags='danger')
            return redirect(cfg['url_unmatched'])

        line = get_object_or_404(AlescoPayLine, pk=request.POST.get('line_id'), status='UNMATCHED')
        if action == 'mark_refunded':
            raw = (request.POST.get('refunded_at') or '').strip()
            try:
                line.refunded_at = _dt.date.fromisoformat(raw) if raw else _dt.date.today()
            except ValueError:
                line.refunded_at = _dt.date.today()
            line.refunded = True
            line.refund_note = (request.POST.get('refund_note') or '').strip() or None
            line.save(update_fields=['refunded', 'refunded_at', 'refund_note'])
            messages.success(request, f'{line.report_name} (K{line.this_period}) marked refunded.', extra_tags='info')
        elif action == 'unmark_refunded':
            line.refunded = False
            line.refunded_at = None
            line.refund_note = None
            line.save(update_fields=['refunded', 'refunded_at', 'refund_note'])
            messages.success(request, f'{line.report_name} moved back to the to-refund list.', extra_tags='info')
        return redirect(cfg['url_unmatched'])

    lines = (AlescoPayLine.objects
             .select_related('run', 'owner')
             .filter(status='UNMATCHED', this_period__gt=0)
             .order_by('refunded', 'run__period_end', 'report_name'))

    # Duplicate-upload detector: two or more (non-cancelled) runs claiming the
    # same pay period inflate the unmatched count with repeat lines from the
    # same file uploaded twice.
    from django.db.models import Count as _Count
    dup_periods = (AlescoPayRun.objects.values('pay_period', 'pay_year', 'paycode')
                   .annotate(n=_Count('id')).filter(n__gt=1, pay_period__isnull=False))
    duplicate_runs = []
    for dp in dup_periods:
        runs = list(AlescoPayRun.objects.filter(
            pay_period=dp['pay_period'], pay_year=dp['pay_year'], paycode=dp['paycode']
        ).order_by('id'))
        duplicate_runs.append({'pay_period': dp['pay_period'], 'pay_year': dp['pay_year'], 'runs': runs})

    categorized = []
    for l in lines:
        category, candidates = classify_unmatched_line(l)
        categorized.append({
            'line': l,
            'category': category,
            'category_label': UNMATCHED_REASON_LABELS[category],
            'candidates': candidates,
        })

    if request.GET.get('download') == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="unmatched_payment_listing.csv"'
        w = csv.writer(resp)
        w.writerow(['Employee File #', 'Name', 'Amount (K)', 'Alesco Ref', 'Pay Period', 'Period End',
                    'Employer/Paycode', 'Reason', 'Status', 'Refunded On', 'Note'])
        reason_by_id = {c['line'].pk: c['category_label'] for c in categorized}
        for ln in lines:
            run = ln.run
            w.writerow([ln.employee_file_number, ln.report_name, ln.this_period,
                        run.ref if run else '', f"{run.pay_period or ''}/{run.pay_year or ''}" if run else '',
                        run.period_end if run else '', (run.employer_name or run.paycode or '') if run else '',
                        reason_by_id.get(ln.pk, ''), 'REFUNDED' if ln.refunded else 'TO REFUND',
                        ln.refunded_at or '', ln.refund_note or ''])
        return resp

    to_refund = [c for c in categorized if not c['line'].refunded]
    refunded = [l for l in lines if l.refunded]
    total_out = sum((c['line'].this_period or Decimal('0')) for c in to_refund)
    total_ref = sum((l.this_period or Decimal('0')) for l in refunded)
    return render(request, 'alesco/unmatched_payments.html', {
        'nav': cfg['nav'],
        'base_template': cfg['base_template'],
        'urls': cfg,
        'to_refund': to_refund,
        'refunded': refunded,
        'total_out': total_out,
        'total_ref': total_ref,
        'duplicate_runs': duplicate_runs,
        'portal': portal,
    })
