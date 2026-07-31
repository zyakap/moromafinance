"""Admin-portal Alesco Update entry points (thin wrappers around loan.alesco_views)."""

from accounts.functions import admin_check
from loan import alesco_views as _av


@admin_check
def alesco_update(request):
    return _av.upload(request, portal='admin')


@admin_check
def alesco_confirm(request, run_id):
    return _av.confirm(request, run_id, portal='admin')


@admin_check
def alesco_data(request, run_id):
    return _av.data(request, run_id)


@admin_check
def alesco_confirm_line(request, line_id):
    return _av.confirm_line_view(request, line_id)


@admin_check
def alesco_confirm_all(request, run_id):
    return _av.confirm_all_view(request, run_id, portal='admin')


@admin_check
def alesco_rollback_line(request, line_id):
    return _av.rollback_line_view(request, line_id)


@admin_check
def alesco_rollback(request, run_id):
    return _av.rollback_run_view(request, run_id, portal='admin')


@admin_check
def alesco_cancel(request, run_id):
    return _av.cancel_run_view(request, run_id, portal='admin')


@admin_check
def alesco_unmatched(request):
    return _av.unmatched_payments(request, portal='admin')
