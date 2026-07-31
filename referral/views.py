import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.conf import settings

from accounts.functions import admin_check
from admin1.models import AdminSettings
from .models import Referrer, ReferralRecord
from .forms import ReferrerForm


def _require_referrals(view):
    """Block every referral page while the programme is switched off — except
    the settings page itself, which hosts the switch."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        from admin1.models import referral_program_enabled
        if not referral_program_enabled():
            messages.error(request, 'The referral programme is switched OFF. '
                                    'Enable it under Referrers → Settings first.', extra_tags='warning')
            return redirect('referral_settings')
        return view(request, *args, **kwargs)
    return wrapper


def _get_commission():
    try:
        return AdminSettings.objects.get(settings_name='setting1').referral_commission or 0
    except Exception:
        return 0

def _get_payment_day():
    """Day of month commissions are paid, from Referral Settings."""
    try:
        from admin1.models import AdminSettings
        return AdminSettings.objects.get(settings_name='setting1').referral_payment_day or None
    except Exception:
        return None



@admin_check
@_require_referrals
def referrers_list(request):
    referrers = Referrer.objects.annotate(
        ref_count=Count('referralrecord'),
        unpaid_total=Sum('referralrecord__commission_amount',
                         filter=Q(referralrecord__paid=False)),
    ).order_by('name')

    total_referrals = ReferralRecord.objects.count()
    total_unpaid    = ReferralRecord.objects.filter(paid=False).aggregate(t=Sum('commission_amount'))['t'] or 0
    total_paid      = ReferralRecord.objects.filter(paid=True).aggregate(t=Sum('commission_amount'))['t'] or 0

    return render(request, 'referrers_list.html', {
        'nav': 'referrers',
        'referrers': referrers,
        'active_referrers': referrers.filter(status='ACTIVE').count(),
        'total_referrals': total_referrals,
        'total_unpaid': total_unpaid,
        'total_paid': total_paid,
        'commission_rate': _get_commission(),
    })


@admin_check
@_require_referrals
def add_referrer(request):
    if request.method == 'POST':
        form = ReferrerForm(request.POST)
        if form.is_valid():
            referrer = form.save()
            messages.success(request, f'Referrer "{referrer.name}" added successfully.')
            return redirect('view_referrer', rid=referrer.id)
    else:
        form = ReferrerForm()
    return render(request, 'referrer_form.html', {
        'nav': 'referrers', 'form': form, 'action': 'Add',
    })


@admin_check
@_require_referrals
def edit_referrer(request, rid):
    referrer = get_object_or_404(Referrer, id=rid)
    if request.method == 'POST':
        form = ReferrerForm(request.POST, instance=referrer)
        if form.is_valid():
            form.save()
            messages.success(request, f'Referrer "{referrer.name}" updated.')
            return redirect('view_referrer', rid=referrer.id)
    else:
        form = ReferrerForm(instance=referrer)
    return render(request, 'referrer_form.html', {
        'nav': 'referrers', 'form': form, 'referrer': referrer, 'action': 'Edit',
    })


@admin_check
@_require_referrals
def view_referrer(request, rid):
    referrer = get_object_or_404(Referrer, id=rid)
    records = ReferralRecord.objects.filter(referrer=referrer).select_related('client').order_by('-date_referred')

    monthly = {}
    for r in records:
        key = r.date_referred.strftime('%Y-%m')
        if key not in monthly:
            monthly[key] = {
                'key': key,
                'month': r.date_referred.strftime('%B %Y'),
                'records': [],
                'total': 0,
                'all_paid': True,
            }
        monthly[key]['records'].append(r)
        monthly[key]['total'] += r.commission_amount
        if not r.paid:
            monthly[key]['all_paid'] = False

    return render(request, 'view_referrer.html', {
        'nav': 'referrers',
        'referrer': referrer,
        'records': records,
        'monthly': list(monthly.values()),
        'commission_rate': _get_commission(),
    })


@admin_check
@_require_referrals
def toggle_referrer_status(request, rid):
    referrer = get_object_or_404(Referrer, id=rid)
    referrer.status = 'INACTIVE' if referrer.status == 'ACTIVE' else 'ACTIVE'
    referrer.save()
    messages.success(request, f'{referrer.name} set to {referrer.status}.')
    return redirect('view_referrer', rid=referrer.id)


@admin_check
@_require_referrals
def commission_overview(request):
    import calendar as _cal
    today = datetime.date.today()
    # Date-range window (defaults to the current month) so the full referral
    # history can be tracked, not just one month at a time.
    def _parse(name, fallback):
        try:
            return datetime.date.fromisoformat((request.GET.get(name) or '').strip())
        except ValueError:
            return fallback
    start = _parse('start', today.replace(day=1))
    end = _parse('end', today.replace(day=_cal.monthrange(today.year, today.month)[1]))
    if end < start:
        start, end = end, start

    records = ReferralRecord.objects.filter(
        date_referred__gte=start, date_referred__lte=end,
    ).select_related('referrer', 'client').order_by('referrer__name')

    grouped = {}
    for r in records:
        rid = r.referrer_id
        if rid not in grouped:
            grouped[rid] = {
                'referrer': r.referrer,
                'records': [],
                'total': 0,
                'unpaid_count': 0,
                'all_paid': True,
            }
        grouped[rid]['records'].append(r)
        grouped[rid]['total'] += r.commission_amount
        if not r.paid:
            grouped[rid]['unpaid_count'] += 1
            grouped[rid]['all_paid'] = False

    total_month  = records.aggregate(t=Sum('commission_amount'))['t'] or 0
    unpaid_month = records.filter(paid=False).aggregate(t=Sum('commission_amount'))['t'] or 0

    label = (start.strftime('%d %b %Y') + ' — ' + end.strftime('%d %b %Y'))

    return render(request, 'commission_overview.html', {
        'nav': 'referrers',
        'start': start,
        'end': end,
        'range_key': f'{start.isoformat()}_{end.isoformat()}',
        'month_label': label,
        'grouped': list(grouped.values()),
        'total_month': total_month,
        'unpaid_month': unpaid_month,
        'paid_count': records.filter(paid=True).count(),
        'unpaid_count': records.filter(paid=False).count(),
        'commission_rate': _get_commission(),
        'payment_day': _get_payment_day(),
    })


@admin_check
@_require_referrals
def mark_month_paid(request, rid, month_str):
    referrer = get_object_or_404(Referrer, id=rid)
    # month_str carries either a YYYY-MM month (legacy) or a
    # YYYY-MM-DD_YYYY-MM-DD range from the overview's date-range selector.
    try:
        if '_' in month_str:
            s_raw, e_raw = month_str.split('_', 1)
            r_start = datetime.date.fromisoformat(s_raw)
            r_end = datetime.date.fromisoformat(e_raw)
        else:
            month_date = datetime.datetime.strptime(month_str, '%Y-%m').date()
            import calendar as _cal
            r_start = month_date.replace(day=1)
            r_end = month_date.replace(day=_cal.monthrange(month_date.year, month_date.month)[1])
    except ValueError:
        messages.error(request, 'Invalid period.', extra_tags='danger')
        return redirect('commission_overview')

    records = ReferralRecord.objects.filter(
        referrer=referrer, paid=False,
        date_referred__gte=r_start, date_referred__lte=r_end,
    )
    count = records.count()
    if count == 0:
        messages.info(request, 'No unpaid referrals found for this period.')
        return redirect('commission_overview')

    try:
        from accounts.models import UserProfile
        admin_profile = UserProfile.objects.get(user=request.user)
        paid_by = f'{admin_profile.first_name} {admin_profile.last_name}'
    except Exception:
        paid_by = request.user.email

    total = records.aggregate(t=Sum('commission_amount'))['t'] or 0
    records.update(
        paid=True,
        paid_date=datetime.date.today(),
        paid_by=paid_by,
        payment_month=month_str,
    )
    messages.success(
        request,
        f'Marked {count} referral(s) for {referrer.name} as paid for '
        f'{r_start.strftime("%d %b %Y")} — {r_end.strftime("%d %b %Y")}. Total: K{total:,.2f}',
    )
    return redirect('commission_overview')


@admin_check
@_require_referrals
def allocate_clients(request, rid):
    """Search existing clients and bulk-assign them to a referrer."""
    referrer = get_object_or_404(Referrer, id=rid)
    commission = _get_commission()

    query = request.GET.get('q', '').strip()
    show_all = request.GET.get('all') == '1'

    if request.method == 'POST':
        selected_ids = request.POST.getlist('client_ids')
        if not selected_ids:
            messages.error(request, 'No clients selected.', extra_tags='danger')
            return redirect(request.get_full_path())

        allocated = 0
        skipped = 0
        for cid in selected_ids:
            try:
                from accounts.models import UserProfile
                client = UserProfile.objects.get(pk=cid)

                # If already allocated to someone else, skip (or update)
                force = request.POST.get('force_reassign') == '1'
                if client.referred_by and client.referred_by != referrer and not force:
                    skipped += 1
                    continue

                # If they already have a record with this referrer, skip
                if ReferralRecord.objects.filter(client=client, referrer=referrer).exists():
                    skipped += 1
                    continue

                # Remove any old referral record from a different referrer
                ReferralRecord.objects.filter(client=client).delete()

                # Assign
                client.referred_by = referrer
                client.save(update_fields=['referred_by'])

                ReferralRecord.objects.create(
                    referrer=referrer,
                    client=client,
                    commission_amount=commission,
                )
                allocated += 1
            except Exception:
                pass

        if allocated:
            messages.success(request, f'{allocated} client(s) allocated to {referrer.name}. '
                                       f'Commission of K{commission} each recorded.')
        if skipped:
            messages.warning(request, f'{skipped} client(s) skipped (already assigned elsewhere).',
                             extra_tags='info')
        return redirect('view_referrer', rid=rid)

    # Build search queryset — clients not yet assigned to THIS referrer
    from accounts.models import UserProfile
    already_assigned_ids = ReferralRecord.objects.filter(
        referrer=referrer).values_list('client_id', flat=True)

    clients_qs = UserProfile.objects.exclude(id__in=already_assigned_ids)

    if query:
        clients_qs = clients_qs.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(nid_number__icontains=query)
        )
    elif not show_all:
        # Default: show only unallocated (no referrer at all)
        clients_qs = clients_qs.filter(referred_by__isnull=True)

    clients_qs = clients_qs.select_related('user', 'referred_by').order_by('last_name', 'first_name')[:100]

    return render(request, 'allocate_clients.html', {
        'nav': 'referrers',
        'referrer': referrer,
        'clients': clients_qs,
        'query': query,
        'show_all': show_all,
        'commission': commission,
    })


@admin_check
@_require_referrals
def remove_allocation(request, rid, record_id):
    """Remove a client allocation from a referrer."""
    referrer = get_object_or_404(Referrer, id=rid)
    record = get_object_or_404(ReferralRecord, id=record_id, referrer=referrer)
    client = record.client
    client_name = f'{client.first_name} {client.last_name}'

    if record.paid:
        messages.error(request, f'Cannot remove {client_name} — commission has already been paid.',
                       extra_tags='danger')
        return redirect('view_referrer', rid=rid)

    # Clear referred_by on the profile and delete the record
    client.referred_by = None
    client.save(update_fields=['referred_by'])
    record.delete()
    messages.success(request, f'{client_name} removed from {referrer.name}\'s referral list.')
    return redirect('view_referrer', rid=rid)


@admin_check
@_require_referrals
def pay_all_outstanding(request, rid):
    """Mark ALL unpaid referral records for a referrer as paid in one action."""
    referrer = get_object_or_404(Referrer, id=rid)
    records = ReferralRecord.objects.filter(referrer=referrer, paid=False)
    count = records.count()

    if count == 0:
        messages.info(request, f'No outstanding commissions for {referrer.name}.')
        return redirect('view_referrer', rid=rid)

    try:
        from accounts.models import UserProfile
        admin_profile = UserProfile.objects.get(user=request.user)
        paid_by = f'{admin_profile.first_name} {admin_profile.last_name}'
    except Exception:
        paid_by = request.user.email

    total = records.aggregate(t=Sum('commission_amount'))['t'] or 0
    today = datetime.date.today()
    month_str = today.strftime('%Y-%m')

    records.update(
        paid=True,
        paid_date=today,
        paid_by=paid_by,
        payment_month=month_str,
    )
    messages.success(
        request,
        f'All {count} outstanding commission(s) for {referrer.name} marked as paid. '
        f'Total: K{total:,.2f}. Recorded by {paid_by}.'
    )
    return redirect('view_referrer', rid=rid)


@admin_check
@_require_referrals
def payment_run(request):
    """
    Payment run page — shows ALL referrers with outstanding commissions,
    their bank details, and the total due. Allows marking all as paid at once
    or exporting a payment list.
    """
    import csv
    from django.http import HttpResponse

    referrers_with_outstanding = Referrer.objects.filter(
        status='ACTIVE',
        referralrecord__paid=False,
    ).annotate(
        outstanding=Sum('referralrecord__commission_amount',
                        filter=Q(referralrecord__paid=False)),
        unpaid_count=Count('referralrecord',
                           filter=Q(referralrecord__paid=False)),
    ).filter(outstanding__gt=0).order_by('name')

    grand_total = referrers_with_outstanding.aggregate(
        t=Sum('outstanding'))['t'] or 0

    # CSV export
    if request.GET.get('download') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="referral_payment_run_{datetime.date.today()}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(['Name', 'Phone', 'Email', 'Bank', 'Branch',
                         'Account Name', 'Account Number', 'Amount Due (K)'])
        for r in referrers_with_outstanding:
            writer.writerow([
                r.name, r.phone or '', r.email or '',
                r.bank or '', r.bank_branch or '',
                r.bank_account_name or '', r.bank_account_number or '',
                f'{r.outstanding:.2f}',
            ])
        return response

    # Mark all as paid
    if request.method == 'POST' and request.POST.get('action') == 'pay_all':
        try:
            from accounts.models import UserProfile
            admin_profile = UserProfile.objects.get(user=request.user)
            paid_by = f'{admin_profile.first_name} {admin_profile.last_name}'
        except Exception:
            paid_by = request.user.email

        today = datetime.date.today()
        month_str = today.strftime('%Y-%m')
        total_records = ReferralRecord.objects.filter(paid=False)
        count = total_records.count()
        total = total_records.aggregate(t=Sum('commission_amount'))['t'] or 0
        total_records.update(
            paid=True, paid_date=today,
            paid_by=paid_by, payment_month=month_str,
        )
        messages.success(
            request,
            f'Payment run complete — {count} referral record(s) across '
            f'{referrers_with_outstanding.count()} referrer(s) marked as paid. '
            f'Grand total: K{total:,.2f}.'
        )
        return redirect('payment_run')

    return render(request, 'payment_run.html', {
        'nav': 'referrers',
        'referrers': referrers_with_outstanding,
        'grand_total': grand_total,
        'today': datetime.date.today(),
    })


@admin_check
def referral_settings(request):
    from admin1.forms import ReferralSettingsForm
    try:
        obj = AdminSettings.objects.get(settings_name='setting1')
    except AdminSettings.DoesNotExist:
        obj = None

    if request.method == 'POST':
        form = ReferralSettingsForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Referral settings updated.')
            return redirect('referral_settings')
    else:
        form = ReferralSettingsForm(instance=obj)

    return render(request, 'settings_referral.html', {
        'nav': 'referral_settings',
        'form': form,
    })


def assign_referrer(request):
    """AJAX: allocate a referrer to a client (from the Loans by Referrer report's
    no-referrer listing). Mirrors allocate_clients: sets referred_by, replaces
    any old referral record, and records the commission."""
    from django.http import JsonResponse
    from django.views.decorators.http import require_POST
    from accounts.models import UserProfile

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'message': 'POST required.'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'message': 'Not signed in.'}, status=403)
    profile = UserProfile.objects.filter(user_id=request.user.id).first()
    if not (request.user.is_superuser or (profile and profile.category in ('STAFF', 'ADMIN'))):
        return JsonResponse({'ok': False, 'message': 'No permission.'}, status=403)
    from admin1.models import referral_program_enabled
    if not referral_program_enabled():
        return JsonResponse({'ok': False, 'message': 'Referral programme is switched OFF.'}, status=400)

    try:
        client = UserProfile.objects.get(pk=request.POST.get('profile_id'))
        referrer = Referrer.objects.get(pk=request.POST.get('referrer_id'), status='ACTIVE')
    except (UserProfile.DoesNotExist, Referrer.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'ok': False, 'message': 'Client or referrer not found.'}, status=404)

    if client.referred_by and client.referred_by != referrer:
        return JsonResponse({'ok': False,
                             'message': f'{client.first_name} {client.last_name} is already allocated to '
                                        f'{client.referred_by.name}.'}, status=400)

    ReferralRecord.objects.filter(client=client).delete()
    client.referred_by = referrer
    client.save(update_fields=['referred_by'])
    ReferralRecord.objects.create(referrer=referrer, client=client,
                                  commission_amount=_get_commission())
    return JsonResponse({'ok': True,
                         'message': f'{client.first_name} {client.last_name} allocated to {referrer.name}.',
                         'referrer': referrer.name})
