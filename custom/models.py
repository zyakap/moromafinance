from django.db import models
from loan.models import Loan

# Create your models here.

class LoanHoliday(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True, related_name='loan_holiday')
    date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    statement = models.TextField(blank=True, null=True)
