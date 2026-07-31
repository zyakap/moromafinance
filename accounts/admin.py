
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from accounts.models import StaffProfile, UserProfile, SMEProfile, Bank, BankBranch

from .forms import UserAdminCreationForm, UserAdminChangeForm

User = get_user_model()

# Remove Group Model from admin. We're not using it.

#admin.site.unregister(Group)

class UserAdmin(BaseUserAdmin):
    # The forms to add and change user instances
    
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    
    # The fields to be used in displaying the User model.
    # These override the definitions on the base UserAdmin
    # that reference specific fields on auth.User.
    
    list_display = ['email', 'profile_name', 'active','admin','confirmed', 'defaulted', 'suspended', 'dcc_flagged', 'cdb_flagged']
    list_filter = ['active','admin','confirmed', 'defaulted', 'suspended', 'dcc_flagged', 'cdb_flagged']
    
    fieldsets = (
        (None, {'fields': ('email','password')}),
        ('Personal Info', {'fields': ()}),
         ('Permissions', {'fields': ('active','admin','confirmed', 'defaulted', 'suspended','dcc_flagged', 'cdb_flagged','groups','user_permissions')}),
         (("Important dates"), {"fields": ('last_login','date_joined')})
    )
    
    # add_fieldsets is not a standard ModelAdmin attribute. UserAdmin
    # overrides get_fieldsets to use this attribute when creating a user.
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
            
        }),
        ('Permissions', {'fields': ('active','admin','confirmed', 'defaulted', 'suspended','dcc_flagged', 'cdb_flagged','groups','user_permissions')}),
    )
    
    search_fields = ['email', 'userprofile__first_name', 'userprofile__middle_name', 'userprofile__last_name']
    ordering = ['id','email']
    filter_horizontal = ('groups','user_permissions')

    @admin.display(description='User profile name', ordering='userprofile__first_name')
    def profile_name(self, obj):
        try:
            profile = obj.userprofile
        except UserProfile.DoesNotExist:
            return 'No user profile'

        return ' '.join(filter(None, (
            profile.first_name,
            profile.middle_name,
            profile.last_name,
        )))

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('userprofile')
    
admin.site.register(User, UserAdmin)
#admin.site.register(StaffProfile)
#admin.site.register(UserProfile)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'category', 'first_name', 'last_name', 'email', 'mobile1', 'category', 'type_of_client', 
        'credit_rating', 'number_of_loans', 'has_loan', 'has_arrears', 'dcc_flagged', 'created_at'
    )
    list_filter = ('category', 'type_of_client', 'province', 'has_loan', 'has_arrears', 'dcc_flagged')
    search_fields = ('first_name', 'last_name', 'email', 'nid_number', 'passport_number', 'drivers_license_number', '=mobile1')
    ordering = ('-created_at',)

    fieldsets = (
        ('Personal Information', {
            'fields': ('user', 'category', 'first_name', 'middle_name', 'last_name', 'gender', 'date_of_birth', 'marital_status')
        }),
        ('Contact Details', {
            'fields': ('email', 'mobile1', 'mobile2', 'work_phone', 'work_email')
        }),
        ('Identification', {
            'fields': ('nid_number', 'passport_number', 'drivers_license_number', 'super_member_code')
        }),
        ('Residential Details', {
            'fields': ('residential_address', 'residential_province', 'place_of_origin', 'province', 'resident_owner')
        }),
        ('Employer & Job Details', {
            'fields': ('employer', 'sector', 'job_title', 'office_address', 'start_date', 'pay_frequency', 'last_paydate', 'gross_pay')
        }),
        ('Bank Account Info', {
            'fields': ('bank', 'bank_account_name', 'bank_account_number', 'bank_branch')
        }),
        ('Loan & Financials', {
            'fields': ('number_of_loans', 'credit_rating', 'repayment_limit', 'personal_interest_rate', 'has_loan', 'has_arrears', 'in_recovery')
        }),
        ('Account Management', {
            'fields': ('account_requirements_check', 'requirement_check', 'credit_consent', 'terms_consent')
        }),
        ('Status Flags', {
            'fields': ('default_flagged', 'dcc_flagged')
        }),
        ('Other Info', {
            'fields': ('dcc', 'modeofregistration', 'opt1', 'opt2', 'opt3', 'opt4', 'opt5')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'login_timestamp')
        }),
    )
    readonly_fields = ('created_at', 'updated_at', 'login_timestamp')


# Let me know if you want to refine anything or add inline displays for related models! 🚀

@admin.register(SMEProfile)
class SMEProfileAdmin(admin.ModelAdmin):
    list_display = (
        'trading_name', 'owner', 'category', 'location', 'email', 'phone', 'created_at', 'updated_at'
    )
    list_filter = ('category', 'bank', 'created_at')
    search_fields = ('trading_name', 'registered_name', 'email', 'phone', 'ipa_registration_number', 'tin_number')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'trading_name', 'registered_name', 'category', 'ref', 'location')
        }),
        ('Contact Details', {
            'fields': ('business_address', 'email', 'phone', 'website')
        }),
        ('Business Documents', {
            'fields': (
                'ipa_registration_number', 'ipa_certificate', 'ipa_certificate_url',
                'tin_number', 'tin_certificate', 'tin_certificate_url',
                'cash_flow', 'cash_flow_url',
                'sme_bank_statement', 'sme_bank_statement_url',
                'location_pic', 'location_pic_url'
            )
        }),
        ('Bank Account Info', {
            'fields': ('bank', 'bank_account_name', 'bank_account_number', 'bank_branch',
                      'bank_standing_order', 'bank_standing_order_url')
        }),
        ('Internal Notes & Comments', {
            'fields': ('dcc_comment', 'cdb_comment', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('owner',)
        return self.readonly_fields


# Let me know if you want to refine anything or add inline displays for related models! 🚀

@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user','sid','type_of_staff','category','position_group','position'
    )
    list_filter = ('user','sid','type_of_staff','category','position_group','position')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'sid', 'type_of_staff', 'position')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('user','sid','type_of_staff','category','position_group','position')
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('user',)
        return self.readonly_fields

class BankBranchInline(admin.TabularInline):
    model = BankBranch
    extra = 1
    fields = ('name', 'bsb_number', 'city', 'province', 'active')


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ('name', 'swift_code', 'bsb_prefix', 'active', 'updated_at')
    list_filter = ('active',)
    search_fields = ('name', 'swift_code', 'bsb_prefix')
    ordering = ('name',)
    inlines = (BankBranchInline,)


@admin.register(BankBranch)
class BankBranchAdmin(admin.ModelAdmin):
    list_display = ('bank', 'name', 'bsb_number', 'city', 'province', 'active')
    list_filter = ('bank', 'active', 'province')
    search_fields = ('bank__name', 'name', 'bsb_number', 'city')
    ordering = ('bank__name', 'name')

# Let me know if you’d like me to adjust anything — happy to refine this! 🚀
