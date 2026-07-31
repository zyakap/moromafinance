from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.functions import admin_check
from accounts.models import UserProfile

from .functions import (
    credit_tab_context, dcc_enabled, parse_expiry, unlock_credit_report,
)
from .models import DccViewLog


@admin_check
def client_credit_check(request, uid):
    """Standalone DCC credit report page for one client. Uses the same
    pay-per-view gating as the Credit Information tab: locked reports show
    the View Data overlay, unlocked reports show in full until the access
    window expires."""
    user = UserProfile.objects.get(pk=uid)
    context = credit_tab_context(user)
    context.update({
        'nav': 'clients_all',
        'client': user,
        'result': context['dcc_result'],
        'report': None if context['dcc_locked'] else context['dcc_report'],
    })
    return render(request, 'dcc_credit_report.html', context)


@admin_check
@require_POST
def unlock_client_credit(request, uid):
    """The 'View Data' button target: bills one pay-per-view unlock at DCC,
    logs it locally (who viewed, cost, window), then returns to the screen
    the staff member came from."""
    user = UserProfile.objects.get(pk=uid)
    next_url = request.POST.get('next') or ''
    # only ever bounce back to a local path
    if not next_url.startswith('/'):
        next_url = f"/admin/clients/view_client/{uid}/#credit"

    if not dcc_enabled():
        messages.error(request, 'DCC is disabled in Settings → DCC.', extra_tags='warning')
        return redirect(next_url)

    result = unlock_credit_report(user.uid)

    if result.get('error'):
        messages.error(request, f"DCC: {result['error']}", extra_tags='danger')
        return redirect(next_url)
    if result.get('not_found'):
        messages.error(request, f'{user.first_name} {user.last_name} has no record in the DCC Credit Database. Nothing was billed.', extra_tags='info')
        return redirect(next_url)

    report = result.get('report') or {}
    access = report.get('access') or {}
    charged = report.get('charged')
    DccViewLog.objects.create(
        client=user,
        viewed_by=request.user,
        cuid=str(user.uid or ''),
        expires_at=parse_expiry(report),
        cost=charged,
        currency=access.get('currency') or '',
    )

    hours = access.get('window_hours') or 12
    if charged and float(charged) > 0:
        messages.success(request, f'DCC credit data unlocked for {user.first_name} {user.last_name} — billed {access.get("currency", "")} {charged}. Access stays open for {hours} hours.')
    else:
        messages.success(request, f'DCC credit data for {user.first_name} {user.last_name} is open (existing paid window).')
    return redirect(next_url)


@admin_check
def reset_indcc(request):
    """Clear the 'sent to DCC' marker so the next feed pull re-sends everything."""
    UserProfile.objects.update(dcc='')
    return render(request, 'reset_indcc.html', {'message': 'All users have been reset.'})
