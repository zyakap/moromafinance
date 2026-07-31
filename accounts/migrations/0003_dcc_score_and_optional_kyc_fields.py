# Hand-written: loanmasta engine sync — DCC benchmark score cache, the
# CFS-originated optional KYC fields (disabled by default via
# admin1.mainView.OPTIONAL_BY_DEFAULT_FIELDS), and the manager contract
# signature field.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_userprofile_referred_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='dcc_score',
            field=models.PositiveIntegerField(blank=True, help_text='Last DCC benchmark credit score (0-1000) fetched from the bureau.', null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='dcc_grade',
            field=models.CharField(blank=True, help_text='Letter grade that came with the last DCC score.', max_length=5, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='dcc_score_at',
            field=models.DateTimeField(blank=True, help_text='When the DCC score was last fetched.', null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='years_at_current_residence',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='number_of_dependents',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='ages_of_dependents',
            field=models.TextField(blank=True, help_text='Enter ages separated by commas (e.g., 5, 8, 12)', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='immediate_supervisor',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='bank_bsb',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='bank_account_type',
            field=models.CharField(blank=True, choices=[('SAVINGS', 'SAVINGS'), ('CURRENT', 'CURRENT'), ('TERM DEPOSIT', 'TERM DEPOSIT')], default='SAVINGS', max_length=15, null=True),
        ),
        migrations.AddField(
            model_name='staffprofile',
            name='signature',
            field=models.FileField(blank=True, null=True, upload_to='staff_signatures/'),
        ),
    ]
