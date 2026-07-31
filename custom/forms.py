from django import forms
from accounts.models import UserProfile, SMEProfile
from loan.models import Loan, LoanFile
from .widgets import DatePickerInput



class AddAdditionalLoanForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(AddAdditionalLoanForm, self).__init__(*args, **kwargs)
        self.fields['owner'].queryset = UserProfile.objects.filter(activation=1)
    
    class Meta:
        model = Loan
        fields = ['owner','location', 'amount', 'funding_date', 'number_of_fortnights','repayment_start_date']
        
        widgets = {
            'funding_date' : DatePickerInput(), 
            'repayment_start_date' : DatePickerInput()}

class AddNewLoanForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        loan_mode = kwargs.pop('loan_mode', 'LOCKED')
        super(AddNewLoanForm, self).__init__(*args, **kwargs)
        self.fields['owner'].queryset = UserProfile.objects.filter(activation=1)
        if loan_mode != 'OPEN_REPAYMENT':
            self.fields.pop('repayment_amount', None)
        else:
            self.fields['repayment_amount'].required = True
            self.fields['repayment_amount'].help_text = 'Fortnightly repayment amount paid by the client.'

    class Meta:
        model = Loan
        fields = ['owner', 'location', 'amount', 'number_of_fortnights', 'repayment_amount', 'funding_date', 'repayment_start_date', 'total_outstanding']

        widgets = {
            'funding_date': DatePickerInput(),
            'repayment_start_date': DatePickerInput(),
        }
