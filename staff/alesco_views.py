"""Staff-portal Alesco Update entry points (thin wrappers around loan.alesco_views)."""

from accounts.functions import check_staff
from loan import alesco_views as _av


@check_staff
def staff_alesco_update(request):
    return _av.upload(request, portal='staff')


@check_staff
def staff_alesco_confirm(request, run_id):
    return _av.confirm(request, run_id, portal='staff')


@check_staff
def staff_alesco_data(request, run_id):
    return _av.data(request, run_id)


@check_staff
def staff_alesco_confirm_line(request, line_id):
    return _av.confirm_line_view(request, line_id)


@check_staff
def staff_alesco_confirm_all(request, run_id):
    return _av.confirm_all_view(request, run_id, portal='staff')


@check_staff
def staff_alesco_rollback_line(request, line_id):
    return _av.rollback_line_view(request, line_id)


@check_staff
def staff_alesco_rollback(request, run_id):
    return _av.rollback_run_view(request, run_id, portal='staff')


@check_staff
def staff_alesco_cancel(request, run_id):
    return _av.cancel_run_view(request, run_id, portal='staff')


@check_staff
def staff_regenerate_schedule(request, loan_ref):
    from loan import regenerate_views as _rv
    return _rv.regenerate_schedule(request, loan_ref, portal='staff')


@check_staff
def staff_alesco_unmatched(request):
    from loan import alesco_views as _av2
    return _av2.unmatched_payments(request, portal='staff')
