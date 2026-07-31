
from django import forms
from django.conf import settings
from .widgets import DatePickerInput
from ckeditor.widgets import CKEditorWidget
from .models import Message

        
class MessageForm(forms.ModelForm):
    
    content = forms.CharField(widget=CKEditorWidget())
    
    class Meta:
        model = Message
        fields = ('category', 'location', 'subject', 'content', 'attachment')
        
        widgets = {
            'date': DatePickerInput(),
        }

