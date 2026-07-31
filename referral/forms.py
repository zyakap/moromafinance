from django import forms
from .models import Referrer


class ReferrerForm(forms.ModelForm):
    class Meta:
        model = Referrer
        fields = [
            'name', 'phone', 'email',
            'bank', 'bank_branch', 'bank_account_name', 'bank_account_number',
            'status', 'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
