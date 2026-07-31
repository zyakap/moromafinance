import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'moromafinance.settings')

celery = Celery('moromafinance')
celery.config_from_object('django.conf:settings', namespace='CELERY')
celery.autodiscover_tasks()

'''
### IMPORTANT

In Celery, scheduled tasks must be callable without arguments because they are invoked automatically by Celery's scheduler (Celery beat). Here's how you can modify your task to work correctly with Celery's scheduler:

Adjusting the Task Definition
Remove the request Argument:

Scheduled tasks in Celery should not require any arguments. If you need data or context within the task, it should be passed directly or retrieved within the task itself.

'''
