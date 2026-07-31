"""Client Credits register — shared between the admin and staff portals.

Tracks money owed BACK to a client (LoanCredit), created automatically when a
closing payment overpays a loan's outstanding balance (see
loan.functions.close_loan_with_credit). Staff either mark a credit refunded
here (with an uploaded receipt) — which also finalises the loan if it is still
parked AWAITING_REFUND — or use the loan page's own "Attribute to Client
Credit & Close Now" action to close the loan immediately while leaving the
credit outstanding to be refunded whenever.
"""
import csv
import datetime as _dt
from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from loan.models import LoanCredit
from loan.functions import finalize_awaiting_refund


PORTALS = {
    'admin': {
        'base_template': 'admin_base.html',
        'nav': 'client_credits',
        'url_credits': 'client_credits',
    },
    'staff': {
        'base_template': 'staff_base.html',
        'nav': 'client_credits',
        'url_credits': 'staff_client_credits',
    },
}


def client_credits(request, portal):
    cfg = PORTALS[portal]

    if request.method == 'POST':
        credit = get_object_or_404(LoanCredit, pk=request.POST.get('credit_id'))
        action = request.POST.get('action')
        if action == 'mark_refunded':
            raw = (request.POST.get('refunded_at') or '').strip()
            try:
                credit.refunded_at = _dt.date.fromisoformat(raw) if raw else _dt.date.today()
            except ValueError:
                credit.refunded_at = _dt.date.today()
            credit.refunded = True
            credit.refund_note = (request.POST.get('refund_note') or '').strip() or None
            receipt = request.FILES.get('refund_receipt')
            if receipt:
                credit.refund_receipt = receipt
            credit.save()
            finalized = finalize_awaiting_refund(request, credit.loan) if credit.loan else False
            msg = f'{credit.owner} — K{credit.amount} marked refunded.'
            if finalized:
                msg += f' {credit.loan.ref} finalised to Completed.'
            messages.success(request, msg, extra_tags='info')
        elif action == 'unmark_refunded':
            credit.refunded = False
            credit.refunded_at = None
            credit.refund_note = None
            credit.refund_receipt = None
            credit.save()
            messages.success(request, f'{credit.owner} — K{credit.amount} moved back to owing.', extra_tags='info')
        return redirect(cfg['url_credits'])

    credits_qs = LoanCredit.objects.select_related('owner', 'loan').order_by('refunded', '-created_at')

    if request.GET.get('download') == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="client_credits.csv"'
        w = csv.writer(resp)
        w.writerow(['Client', 'Loan Ref', 'Amount (K)', 'Reason', 'Note', 'Created',
                    'Status', 'Refunded On', 'Refund Note'])
        for c in credits_qs:
            w.writerow([str(c.owner), c.loan.ref if c.loan else '', c.amount, c.get_reason_display(),
                        c.note or '', c.created_at.date(), 'REFUNDED' if c.refunded else 'OWING',
                        c.refunded_at or '', c.refund_note or ''])
        return resp

    owing = [c for c in credits_qs if not c.refunded]
    refunded = [c for c in credits_qs if c.refunded]
    total_owing = sum((c.amount or Decimal('0')) for c in owing)
    total_refunded = sum((c.amount or Decimal('0')) for c in refunded)
    return render(request, 'credits/client_credits.html', {
        'nav': cfg['nav'],
        'base_template': cfg['base_template'],
        'urls': cfg,
        'portal': portal,
        'owing': owing,
        'refunded': refunded,
        'total_owing': total_owing,
        'total_refunded': total_refunded,
    })


def attribute_credit_and_close(request, loan_ref, portal):
    """'Attribute to Client Credit & Close Now' — finalise an AWAITING_REFUND
    loan immediately, leaving its LoanCredit outstanding to be refunded later
    via the Client Credits register."""
    from django.shortcuts import get_object_or_404 as _god
    from loan.models import Loan

    loan = _god(Loan, ref=loan_ref)
    if loan.funded_category != 'AWAITING_REFUND':
        messages.warning(request, f'{loan.ref} is not awaiting a refund.', extra_tags='warning')
    else:
        finalize_awaiting_refund(request, loan)
        messages.success(
            request,
            f'{loan.ref} closed. The excess remains recorded as a client credit — refund it whenever from the Client Credits register.',
            extra_tags='info',
        )
    view_name = 'view_loan' if portal == 'admin' else 'view_loan_staff'
    return redirect(view_name, loan.ref)
