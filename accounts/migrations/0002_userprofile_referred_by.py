import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds UserProfile.referred_by.

    accounts.UserProfile and referral.* reference each other (UserProfile has an
    FK to referral.Referrer, while referral.ReferralRecord has an FK back to
    accounts.UserProfile). Declaring the FK inside accounts.0001_initial makes
    accounts.0001 depend on referral.0001 and vice versa, which Django rejects as
    a CircularDependencyError. Breaking the loop the standard way: both apps'
    initial migrations create their own tables first, then this migration adds
    the crossing FK once referral.Referrer exists.
    """

    dependencies = [
        ('referral', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='referred_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='referred_clients', to='referral.referrer'),
        ),
    ]
