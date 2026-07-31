# Hand-written: loanmasta engine sync — widen payment_month so it can carry
# either a YYYY-MM month (legacy) or a YYYY-MM-DD_YYYY-MM-DD date-range key
# from the overview's date-range selector.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referral', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='referralrecord',
            name='payment_month',
            field=models.CharField(blank=True, help_text='Format: YYYY-MM', max_length=30, null=True),
        ),
    ]
