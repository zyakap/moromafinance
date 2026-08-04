"""Record terms + credit consent for every client who already has a loan.

Holding a loan means the client signed the terms and agreed to the credit check
before it was advanced -- on paper for loans that predate the portal, and for
migrated ones before they ever reached this system. The flags simply had no way
of being set for those clients, so screens that gate on consent treated
long-standing borrowers as if they had never agreed to anything.

Funding a loan through the normal route already sets both (see
admin1/views/loansView.py), and consent cannot be revoked while a loan is
outstanding (accounts/views.py) -- this backfills the clients who never passed
through either.
"""
from django.db import migrations


def grant_consent(apps, schema_editor):
    UserProfile = apps.get_model('accounts', 'UserProfile')
    UserProfile.objects.filter(loan__isnull=False).distinct().update(
        terms_consent='YES', credit_consent='YES',
    )


def noop(apps, schema_editor):
    """Deliberately not reversed.

    Rolling this back would withdraw a consent the client did give, which is
    worse than leaving it recorded. Clear it by hand if a specific client's
    consent turns out to be wrong.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_userprofile_dcc_risk_signals'),
        ('loan', '0009_merge_20260804_1810'),
    ]

    operations = [
        migrations.RunPython(grant_consent, noop),
    ]
