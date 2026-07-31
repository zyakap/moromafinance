from django.db import models
#from ckeditor.fields import RichTextField
from accounts.models import UserProfile
from admin1.models import Location

# Create your models here.

class Message(models.Model):
    
    CATEGORY  = [
        ('ALL USERS', 'ALL USERS'),
        ('PENDING USERS','PENDING USERS'),
        ('PENDING LOANS','PENDING LOANS'),
        ('APPROVED LOANS','APPROVED LOANS'),
        ('FUNDED LOANS', 'FUNDED LOANS'),
        ('RUNNING LOANS','RUNNING LOANS'),
        ('DEAFULT LOANS','DEAFULT LOANS'),
        ('RECOVERY LOANS','RECOVERY LOANS'),
        ('BAD LOANS','BAD LOANS')      
        ]
    
    category = models.CharField(max_length=100, choices=CATEGORY)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    subject = models.CharField(max_length=100)
    content = models.TextField(blank=True, null=True)
    recipients_personal = models.PositiveIntegerField(blank=True, null=True, default=0)
    recipients_work = models.PositiveIntegerField(blank=True, null=True, default=0)
    emailto_personal = models.CharField(max_length=1555, blank=True, null=True, default="")
    emailto_work = models.CharField(max_length=1555, blank=True, null=True, default="")
    read_by_app = models.CharField(max_length=1555, blank=True, null=True, default="")
    read_by_personal_email = models.CharField(max_length=1555, blank=True, null=True, default="")
    read_by_work_email = models.CharField(max_length=1555, blank=True, null=True, default="")
    email_sent = models.CharField(max_length=1555, blank=True, null=True, default="")
    email_not_sent = models.CharField(max_length=1555, blank=True, null=True, default="")
    email_sent_work = models.CharField(max_length=1555, blank=True, null=True, default="")
    email_not_sent_work = models.CharField(max_length=1555, blank=True, null=True, default="")
    delivery_status = models.CharField(max_length=10, blank=True, null=True, default="")
    attachment = models.FileField(upload_to='', blank=True, null=True)
    attachment_name = models.CharField(max_length=255, blank=True, null=True)
    attachment_url = models.CharField(max_length=255, blank=True, null=True, default="")

    sender = models.ForeignKey(UserProfile, on_delete=models.CASCADE)

class MessageLog(models.Model):
    user = models.OneToOneField(UserProfile, on_delete=models.CASCADE)
    msgq = models.CharField(max_length=255, blank=True, null=True, default="")
    msglog = models.CharField(max_length=1555, blank=True, null=True, default="")
    msgbyemail = models.CharField(max_length=1555, blank=True, null=True, default="")
    msg_not_emailed = models.CharField(max_length=1555, blank=True, null=True, default="")
    msgbyemail_work = models.CharField(max_length=1555, blank=True, null=True, default="")
    msg_not_emailed_work = models.CharField(max_length=1555, blank=True, null=True, default="")
    readonline = models.CharField(max_length=1555, blank=True, null=True, default="")
    reademail = models.CharField(max_length=1555, blank=True, null=True, default="")