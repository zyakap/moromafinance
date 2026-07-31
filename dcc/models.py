from django.conf import settings
from django.db import models
from django.utils import timezone


class DccViewLog(models.Model):
    """Local record of every billed DCC pay-per-view unlock made from this
    tenant. DCC is the billing source of truth; this log powers the admin
    dashboard running-cost card and Reports -> DCC Report, and records WHICH
    staff member unlocked a client (DCC only knows the tenant)."""
    client = models.ForeignKey('accounts.UserProfile', on_delete=models.CASCADE, related_name='dcc_views')
    viewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='dcc_views_made')
    cuid = models.CharField(max_length=20, help_text="The client's DCC lookup id (UserProfile.uid) at unlock time.")
    unlocked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text='End of the paid access window reported by DCC.')
    cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text='Amount DCC charged for this view (0.00 when re-opened within a window).')
    currency = models.CharField(max_length=10, blank=True, default='')

    class Meta:
        ordering = ['-unlocked_at']
        indexes = [models.Index(fields=['client', '-unlocked_at'])]

    def __str__(self):
        return f'{self.client} unlocked {self.unlocked_at:%Y-%m-%d %H:%M}'

    @property
    def is_active(self):
        return self.expires_at is not None and self.expires_at > timezone.now()
