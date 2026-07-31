from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin1', '0002_dcc_autocredit_settings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminsettings',
            name='refinance_type',
            field=models.CharField(
                choices=[
                    ('OFFSET_BALANCE', 'Offset Balance - The new amount offsets current running loan balance and the rest is paid to client'),
                    ('ADD_ON', 'Add On - The new loan amount + interest is added onto the existing balance and term added to remaining number of fortnights'),
                    ('CONCURRENT', 'Concurrent - The balance is updated with new totals, the repayment is doubled, and once term of first ends, the repayment of the additional loan continues with remaining term of additional loan'),
                    ('ADD_ON_VARIED', 'Add On (Varied) - The new loan total is added onto the existing balance like Add On, but the combined repayment term and fortnightly repayment are entered by staff at funding'),
                    ('REFINANCE_NOT_ALLOWED', 'Refinance Not Allowed - A client with an existing loan (funded or pending) cannot get a new or additional loan at all, for any reason, until it is fully completed. One loan per client.'),
                ],
                default='OFFSET_BALANCE',
                help_text='Select how refinanced loans are structured.',
                max_length=25,
                verbose_name='Refinance Type:',
            ),
        ),
    ]
