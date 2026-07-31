"""Admin-portal Regenerate Repayment Dates entry point."""

from accounts.functions import admin_check
from loan import regenerate_views as _rv


@admin_check
def regenerate_schedule(request, loan_ref):
    return _rv.regenerate_schedule(request, loan_ref, portal='admin')
