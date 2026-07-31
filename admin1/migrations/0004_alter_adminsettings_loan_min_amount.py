from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin1', '0003_alter_adminsettings_refinance_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminsettings',
            name='loan_min_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=100.0,
                help_text='Minimum loan amount a client can apply for.',
                max_digits=10,
                null=True,
                verbose_name='Minimum Loan Amount (K):',
            ),
        ),
    ]
