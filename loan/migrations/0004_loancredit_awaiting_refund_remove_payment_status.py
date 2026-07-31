import django.db.models.deletion
from django.db import migrations, models


def remove_payment_status_setting(apps, schema_editor):
    FormFieldSetting = apps.get_model('admin1', 'FormFieldSetting')
    FormFieldSetting.objects.filter(form_name='payment', field_name='status').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('loan', '0003_manager_workflow_and_optional_fields'),
        ('admin1', '0003_alter_adminsettings_refinance_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='loan',
            name='funded_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ACTIVE', 'ACTIVE'),
                    ('RECOVERY', 'RECOVERY'),
                    ('BAD', 'BAD'),
                    ('WOFF', 'WOFF'),
                    ('COMPLETED', 'COMPLETED'),
                    ('ARCHIVED', 'ARCHIVED'),
                    ('AWAITING_REFUND', 'AWAITING REFUND'),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name='LoanCredit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('reason', models.CharField(choices=[('OVERPAYMENT_AT_CLOSURE', 'Overpayment at Loan Closure'), ('MANUAL', 'Manual Adjustment')], default='OVERPAYMENT_AT_CLOSURE', max_length=30)),
                ('note', models.CharField(blank=True, max_length=255, null=True)),
                ('refunded', models.BooleanField(default=False)),
                ('refunded_at', models.DateField(blank=True, null=True)),
                ('refund_receipt', models.FileField(blank=True, null=True, upload_to='refund_receipts')),
                ('refund_note', models.CharField(blank=True, max_length=255, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.staffprofile')),
                ('loan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='credits', to='loan.loan')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='loan_credits', to='accounts.userprofile')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.RemoveField(
            model_name='payment',
            name='status',
        ),
        migrations.RunPython(remove_payment_status_setting, migrations.RunPython.noop),
    ]
