from django.conf import settings
from rest_framework import serializers

from accounts.models import UserProfile
from loan.models import Loan, Statement

# File-type uploads on the client profile that are shared with the DCC credit
# bureau, mapped to DCC's ClientUpload types. The feed lists a download URL for
# each; DCC fetches them through /API/upload/<uid>/<field>/ with its API key.
PROFILE_UPLOAD_FIELDS = {
    'propic': 'PROFILE_PIC',
    'nid': 'NID',
    'passport': 'PASSPORT',
    'drivers_license': 'DRIVERS_LICENSE',
    'superid': 'SUPER_ID',
    'work_id': 'WORK_ID',
    'bank_standing_order2': 'BANK_STANDING_ORDER',
}


class UserProfileSerializer(serializers.ModelSerializer):
    uploads = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'uid', 'luid', 'type_of_client',
            'number_of_loans', 'credit_rating',
            # identity
            'first_name', 'middle_name', 'last_name', 'gender',
            'date_of_birth', 'marital_status',
            # contact
            'email', 'mobile1',
            # personal ids
            'nid_number', 'passport_number', 'drivers_license_number',
            'super_member_code',
            # address / origin
            'residential_address', 'place_of_origin',
            # employment
            'sector', 'employer', 'job_title', 'work_id_number',
            'start_date', 'pay_frequency', 'last_paydate',
            # banking
            'bank', 'bank_account_name', 'bank_account_number', 'bank_branch',
            'bank2', 'bank_account_name2', 'bank_account_number2', 'bank_branch2',
            # credit standing
            'repayment_limit', 'has_loan', 'dcc_flagged',
            # documents
            'uploads',
        ]

    def get_uploads(self, obj):
        uploads = []
        for field, upload_type in PROFILE_UPLOAD_FIELDS.items():
            file_field = getattr(obj, field, None)
            if not file_field or not getattr(file_field, 'name', ''):
                continue
            uploads.append({
                'upload_type': upload_type,
                'name': file_field.name,
                'url': f'{settings.DOMAIN}/API/upload/{obj.uid}/{field}/',
            })
        return uploads


class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = [
            'ref', 'uid', 'luid', 'loan_type', 'classification',
            'application_date', 'amount', 'processing_fee', 'interest',
            'total_loan_amount', 'repayment_frequency', 'number_of_fortnights',
            'repayment_amount', 'category', 'funded_category', 'status',
            'funding_date', 'repayment_start_date', 'expected_end_date',
            'next_payment_date', 'principal_loan_paid', 'interest_paid',
            'total_paid', 'fortnights_paid', 'number_of_repayments',
            'last_repayment_amount', 'last_repayment_date',
            'number_of_defaults', 'last_default_date', 'last_default_amount',
            'days_in_default', 'total_arrears', 'total_outstanding',
            'aging_category',
        ]


class StatementSerializer(serializers.ModelSerializer):
    # send the loan's ref (globally meaningful) instead of the local pk
    loanref = serializers.SlugRelatedField(slug_field='ref', read_only=True)

    class Meta:
        model = Statement
        fields = [
            'ref', 'uid', 'luid', 'loanref', 'date', 'type', 'statement',
            'credit', 'debit', 'arrears', 'balance',
        ]
