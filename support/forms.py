
from django import forms
#from django.conf import settings
from .widgets import DatePickerInput
from ckeditor.widgets import CKEditorWidget
from .models import SupportTicket

        
class CreateTicketForm(forms.ModelForm):
    
    content = forms.CharField(widget=CKEditorWidget())
    
    class Meta:
        model = SupportTicket
        fields = ('category', 'subject', 'content', 'attachment')
        
        widgets = {
            'date': DatePickerInput(),
        }