# Hand-written: DCC pay-per-view unlock log, ported from loanmasta. Index is
# created directly under its final name (loanmasta's later rename migration
# is folded in here since moromafinance starts fresh on this app).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0003_dcc_score_and_optional_kyc_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DccViewLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cuid', models.CharField(help_text="The client's DCC lookup id (UserProfile.uid) at unlock time.", max_length=20)),
                ('unlocked_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(blank=True, help_text='End of the paid access window reported by DCC.', null=True)),
                ('cost', models.DecimalField(blank=True, decimal_places=2, help_text='Amount DCC charged for this view (0.00 when re-opened within a window).', max_digits=8, null=True)),
                ('currency', models.CharField(blank=True, default='', max_length=10)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dcc_views', to='accounts.userprofile')),
                ('viewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dcc_views_made', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-unlocked_at'],
            },
        ),
        migrations.AddIndex(
            model_name='dccviewlog',
            index=models.Index(fields=['client', '-unlocked_at'], name='dcc_dccview_client__b5a09a_idx'),
        ),
    ]
