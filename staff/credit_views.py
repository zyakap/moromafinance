"""Staff-portal Client Credits entry points (thin wrappers around loan.credit_views)."""

from accounts.functions import check_staff
from loan import credit_views as _cv


@check_staff
def staff_client_credits(request):
    return _cv.client_credits(request, portal='staff')


@check_staff
def staff_attribute_credit_and_close(request, loan_ref):
    return _cv.attribute_credit_and_close(request, loan_ref, portal='staff')
