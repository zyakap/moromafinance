from django.db import transaction
from django.http import FileResponse, Http404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.models import UserProfile
from loan.models import Loan, Statement
from .permissions import HasAPIKey
from .serializers import (
    PROFILE_UPLOAD_FIELDS, LoanSerializer, UserProfileSerializer, StatementSerializer,
)


# NOTE: These endpoints implement a "pull and mark consumed" contract with the
# external DCC credit-bureau client: each call returns the records not yet sent
# (dcc != 'INDCC'/'DEFAULTED'), and marks the ones returned so they are not
# re-sent next time. The records are serialized BEFORE being marked so a
# serialization error can never silently drop records from the feed.
# Access requires the X-API-KEY header (see api/permissions.py).
#
# The feed is ALWAYS ON. The Admin -> Settings -> DCC switch
# (AdminSettings.dcc_enabled) only controls whether this tenant's staff can
# run billed pay-per-view credit checks — keeping the bureau's database
# up to date is a condition of participating in DCC, so disabling credit
# checks never stops the data feed.


@api_view(['GET'])
@permission_classes([HasAPIKey])
def userprofiles(request):
    users = list(
        UserProfile.objects.filter(credit_consent='YES')
        .exclude(dcc='INDCC', first_name='', last_name='')
    )
    serializer = UserProfileSerializer(users, many=True, context={'request': request})
    data = serializer.data
    with transaction.atomic():
        for user in users:
            user.dcc = 'INDCC'
        UserProfile.objects.bulk_update(users, ['dcc'])
    return Response(data)


@api_view(['GET'])
@permission_classes([HasAPIKey])
def allloans(request):
    loans = list(Loan.objects.exclude(dcc='INDCC'))
    serializer = LoanSerializer(loans, many=True, context={'request': request})
    data = serializer.data
    with transaction.atomic():
        for loan in loans:
            loan.dcc = 'INDCC'
        Loan.objects.bulk_update(loans, ['dcc'])
    return Response(data)


@api_view(['GET'])
@permission_classes([HasAPIKey])
def statements(request):
    stmts = list(Statement.objects.exclude(dcc='INDCC'))
    serializer = StatementSerializer(stmts, many=True, context={'request': request})
    data = serializer.data
    with transaction.atomic():
        for statement in stmts:
            statement.dcc = 'INDCC'
        Statement.objects.bulk_update(stmts, ['dcc'])
    return Response(data)


@api_view(['GET'])
@permission_classes([HasAPIKey])
def upload_file(request, uid, field):
    """Stream one client document to the DCC puller (X-API-KEY protected).

    Only the whitelisted profile upload fields are reachable — arbitrary
    fields/paths cannot be requested."""
    if field not in PROFILE_UPLOAD_FIELDS:
        raise Http404
    user = UserProfile.objects.filter(uid=uid).first()
    if user is None:
        raise Http404
    file_field = getattr(user, field, None)
    if not file_field or not getattr(file_field, 'name', ''):
        raise Http404
    try:
        return FileResponse(file_field.open('rb'), as_attachment=True,
                            filename=file_field.name.rsplit('/', 1)[-1])
    except FileNotFoundError:
        raise Http404
