
from rest_framework import serializers
from accounts.models import UserProfile
from loan.models import Loan, Statement

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['luid','uid','first_name','last_name','date_of_birth','nid_number','credit_rating','has_loan','in_recovery','default_flagged','dcc_flagged','has_arrears' ]

class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = ['ref', 'uid', 'luid', 'amount','repayment_amount', 'funded_category']

class StatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Statement
        fields = ['uid', 'luid', 'ref', 'statement']