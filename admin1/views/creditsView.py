"""Admin-portal Client Credits entry points (thin wrappers around loan.credit_views)."""

from accounts.functions import staff_or_admin_check
from loan import credit_views as _cv


@staff_or_admin_check
def client_credits(request):
    return _cv.client_credits(request, portal='admin')


@staff_or_admin_check
def attribute_credit_and_close(request, loan_ref):
    return _cv.attribute_credit_and_close(request, loan_ref, portal='admin')
