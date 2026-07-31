# Hand-written: loanmasta engine sync — DCC benchmark-rating automation
# settings (automatic credit check against the bureau's score, and
# auto-scaling client limits from it).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin1', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='adminsettings',
            name='dcc_autocredit_enabled',
            field=models.CharField(blank=True, choices=[('YES', 'YES - Check the DCC benchmark score automatically'), ('NO', 'NO - Use local credit rating only')], default='NO', help_text="When Automatic Credit Check runs, also fetch the client's DCC benchmark score (0-1000, computed by the bureau from all lenders' data) and block applications below the minimum score. Each check is billed at the DCC rating-check price.", max_length=3, null=True, verbose_name='Use DCC Benchmark Score in Automatic Credit Check:'),
        ),
        migrations.AddField(
            model_name='adminsettings',
            name='dcc_min_score',
            field=models.PositiveIntegerField(default=400, help_text='Loan applications from clients whose DCC benchmark score (0-1000) is below this are automatically declined.', verbose_name='Minimum DCC Score:'),
        ),
        migrations.AddField(
            model_name='adminsettings',
            name='dcc_autoset_limits',
            field=models.CharField(blank=True, choices=[('YES', 'YES - Scale limits by DCC score'), ('NO', 'NO - Set limits manually')], default='NO', help_text="When enabled, the client's repayment limit and loan ceiling are set automatically in proportion to their DCC score (score/1000 x the maximums below) each time the score is fetched.", max_length=3, null=True, verbose_name='Auto-Set Limits from DCC Score:'),
        ),
        migrations.AddField(
            model_name='adminsettings',
            name='dcc_limit_max_repayment',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='A client with a perfect DCC score of 1000 gets this repayment limit; lower scores scale down proportionally.', max_digits=10, null=True, verbose_name='Repayment Limit at Score 1000 (K):'),
        ),
        migrations.AddField(
            model_name='adminsettings',
            name='dcc_limit_max_ceiling',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='A client with a perfect DCC score of 1000 gets this maximum loan amount; lower scores scale down proportionally.', max_digits=10, null=True, verbose_name='Loan Ceiling at Score 1000 (K):'),
        ),
    ]
