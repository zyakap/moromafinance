# Hand-written: loanmasta engine sync — purpose_of_loan / Payment.status /
# LoanFile.signed_contract (optional fields, opt-in via
# admin1.mainView.OPTIONAL_BY_DEFAULT_FIELDS) and alesco refund tracking for
# the Unmatched Payments register.

import loan.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loan', '0002_alter_loan_amount_alter_loan_number_of_fortnights'),
    ]

    operations = [
        migrations.AddField(
            model_name='loan',
            name='purpose_of_loan',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Purpose of Loan:'),
        ),
        migrations.AddField(
            model_name='loanfile',
            name='signed_contract',
            field=models.FileField(blank=True, null=True, upload_to=loan.models.loan_file_path, verbose_name='Signed Contract:'),
        ),
        migrations.AddField(
            model_name='loanfile',
            name='signed_contract_url',
            field=models.CharField(blank=True, max_length=555, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='status',
            field=models.CharField(blank=True, choices=[('PENDING', 'PENDING'), ('COMMITTED', 'COMMITTED')], default='PENDING', max_length=10),
        ),
        migrations.AddField(
            model_name='alescopayline',
            name='refunded',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='alescopayline',
            name='refunded_at',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='alescopayline',
            name='refund_note',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
