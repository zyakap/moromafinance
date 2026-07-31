from django.db import models
from accounts.models import UserProfile

# Create your models here.

class SupportTicket(models.Model):

    CATEGORY  = [
        ('LOAN REQUIREMENTS', 'LOAN REQUIREMENTS'),
        ('PENDING LOAN','PENDING LOAN'),
        ('LOAN REPAYMENT','LOAN REPAYMENT'),
        ('LOAN ISSUE','LOAN ISSUE'),
        ('ACCOUNT ACTIVATION','ACCOUNT ACTIVATION'),
        ('WEB APP USAGE','WEB APP USAGE')
    ]

    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    ref = models.CharField(max_length=15, blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.CharField(max_length=100, choices=CATEGORY)
    subject = models.CharField(max_length=255, blank=True, null=True)
    content = models.CharField(max_length=555, blank=True, null=True)
    threadlog = models.CharField(max_length=1555, blank=True, null=True)
    threadq = models.CharField(max_length=10, blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)
    closed = models.BooleanField(default=False)
    attachment = models.FileField(upload_to='', blank=True, null=True)
    attachment_name = models.CharField(max_length=255, blank=True, null=True)
    attachment_url = models.CharField(max_length=255, blank=True, null=True)

#store every reply as a single entry tied to the ref of SupportTicket
class SupportTicketThread(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    thread = models.CharField(max_length=1555, blank=True, null=True)
    thread_content = models.CharField(max_length=555, blank=True, null=True)
    responder = models.CharField(max_length=55, blank=True, null=True)
    attachment = models.FileField(upload_to='', blank=True, null=True)
    attachment_name = models.CharField(max_length=255, blank=True, null=True)
    attachment_url = models.CharField(max_length=255, blank=True, null=True)
