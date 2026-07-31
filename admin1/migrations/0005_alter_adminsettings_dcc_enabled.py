from django.db import migrations, models


class Migration(migrations.Migration):
    """Restore the canonical wording of the DCC switch.

    The label previously told admins that turning this off would "stop feeding
    client/loan data to DCC". That is not what it does, and not what it may do:
    the feed in api/views.py is unconditional by design, because keeping the
    bureau's database current is a condition of participating in DCC. The
    switch only governs billed pay-per-view credit checks.

    Labels/help text only — no database schema change.
    """

    dependencies = [
        ('admin1', '0004_alter_adminsettings_loan_min_amount'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminsettings',
            name='dcc_enabled',
            field=models.CharField(
                blank=True,
                choices=[
                    ('YES', 'YES - Enable billed pay-per-view credit checks'),
                    ('NO', 'NO - Disable credit checks (searches are not billed)'),
                ],
                default='YES',
                help_text='When enabled, staff can unlock DCC credit reports from the client screen — each unlocked view is billed by DCC and stays open for the access window set by DCC. When disabled, no credit checks run and nothing is billed. NOTE: the data feed to DCC always stays on; keeping the bureau current is a condition of the DCC service.',
                max_length=3,
                null=True,
                verbose_name='DCC Credit Bureau:',
            ),
        ),
    ]
