from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('loan', '0007_loan_dcc_default_reported_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='BlackroseImport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('file', models.FileField(blank=True, null=True, upload_to='blackrose')),
                ('file_name', models.CharField(blank=True, max_length=255, null=True)),
                ('file_hash', models.CharField(blank=True, db_index=True, max_length=64, null=True)),
                ('lender_name', models.CharField(blank=True, max_length=255, null=True)),
                ('client_name', models.CharField(blank=True, max_length=255, null=True)),
                ('client_code', models.CharField(blank=True, max_length=50, null=True)),
                ('employer', models.CharField(blank=True, max_length=255, null=True)),
                ('address', models.CharField(blank=True, max_length=255, null=True)),
                ('phone', models.CharField(blank=True, max_length=30, null=True)),
                ('parsed', models.JSONField(blank=True, null=True)),
                ('row_count', models.IntegerField(default=0)),
                ('closing_balance', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('status', models.CharField(choices=[('PENDING', 'PENDING'), ('IMPORTED', 'IMPORTED'), ('FAILED', 'FAILED'), ('SKIPPED', 'SKIPPED')], default='PENDING', max_length=20)),
                ('error', models.TextField(blank=True, null=True)),
                ('client_created', models.BooleanField(default=False)),
                ('imported_at', models.DateTimeField(blank=True, null=True)),
                ('loan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='blackrose_imports', to='loan.loan')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.userprofile')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.staffprofile')),
            ],
            options={
                'verbose_name': 'Blackrose Statement Import',
                'verbose_name_plural': 'Blackrose Statement Imports',
                'ordering': ['-created_at'],
            },
        ),
    ]
