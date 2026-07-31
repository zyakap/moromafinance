from django.db import models
from accounts.models import UserProfile


class Referrer(models.Model):
    STATUS_CHOICES = [('ACTIVE', 'Active'), ('INACTIVE', 'Inactive')]

    name        = models.CharField(max_length=100)
    phone       = models.CharField(max_length=20, blank=True, null=True)
    email       = models.EmailField(blank=True, null=True)
    bank        = models.CharField(max_length=100, blank=True, null=True)
    bank_branch = models.CharField(max_length=100, blank=True, null=True)
    bank_account_name   = models.CharField(max_length=100, blank=True, null=True)
    bank_account_number = models.CharField(max_length=30,  blank=True, null=True)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    notes       = models.TextField(blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def total_referrals(self):
        return self.referralrecord_set.count()

    @property
    def total_commission_earned(self):
        from django.db.models import Sum
        return self.referralrecord_set.aggregate(t=Sum('commission_amount'))['t'] or 0

    @property
    def total_commission_unpaid(self):
        from django.db.models import Sum
        return self.referralrecord_set.filter(paid=False).aggregate(t=Sum('commission_amount'))['t'] or 0

    @property
    def total_commission_paid(self):
        from django.db.models import Sum
        return self.referralrecord_set.filter(paid=True).aggregate(t=Sum('commission_amount'))['t'] or 0

    class Meta:
        ordering = ['name']


class ReferralRecord(models.Model):
    referrer          = models.ForeignKey(Referrer, on_delete=models.CASCADE)
    client            = models.OneToOneField(UserProfile, on_delete=models.CASCADE)
    commission_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    date_referred     = models.DateField(auto_now_add=True)
    paid              = models.BooleanField(default=False)
    paid_date         = models.DateField(blank=True, null=True)
    paid_by           = models.CharField(max_length=100, blank=True, null=True)
    payment_month     = models.CharField(max_length=30, blank=True, null=True,
                                          help_text='Format: YYYY-MM')

    def __str__(self):
        return f'{self.referrer.name} → {self.client.first_name} {self.client.last_name}'

    class Meta:
        ordering = ['-date_referred']
