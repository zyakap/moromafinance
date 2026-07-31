from django.contrib import admin, messages
from .models import Loan, Statement, Payment
from .reversal import reverse_payment, reverse_statement, ReversalError


class _ReversingDeleteMixin:
    """Deleting a Payment or a money Statement in the site admin reverses the
    whole transaction (payment + sibling statements + loan-field effects) so the
    loan account returns to its state before the entry was posted."""

    def _reverse(self, obj):
        raise NotImplementedError

    def delete_model(self, request, obj):
        try:
            summary = self._reverse(obj)
            messages.success(request, f'Reversed: {summary}')
        except ReversalError as exc:
            messages.error(request, f'NOT deleted — {exc}')
            request._reversal_refused = True

    def response_delete(self, request, obj_display, obj_id):
        # Suppress Django's own "deleted successfully" toast when the reversal
        # refused and nothing was actually removed.
        if getattr(request, '_reversal_refused', False):
            from django.http import HttpResponseRedirect
            from django.urls import reverse as _r
            opts = self.model._meta
            return HttpResponseRedirect(_r(f'admin:{opts.app_label}_{opts.model_name}_changelist'))
        return super().response_delete(request, obj_display, obj_id)

    def delete_queryset(self, request, queryset):
        # Rows of one transaction group delete together; re-check existence so
        # a sibling already removed by a previous reversal is skipped cleanly.
        for obj in list(queryset):
            if not type(obj).objects.filter(pk=obj.pk).exists():
                continue
            self.delete_model(request, obj)


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        'ref', 'owner', 'officer', 'loan_type', 'classification', 'amount', 'status', 'funding_date', 'repayment_start_date', 'expected_end_date',
    )
    list_filter = (
        'loan_type', 'classification', 'category', 'funded_category', 'status', 'repayment_frequency', 'aging_category',
    )
    search_fields = (
        'ref', 'uid', 'luid',
        'owner__first_name', 'owner__last_name', 'owner__user__email',
        'officer__user__first_name', 'officer__user__last_name',
        'location__name',
    )
    date_hierarchy = 'funding_date'
    readonly_fields = ('created_at', 'updated_at','application_date', 'amount')

    fieldsets = (
        ('Loan Details', {
            'fields': ('ref', 'uid', 'luid', 'existing_code', 'owner', 'officer', 'location', 'loan_type', 'classification', 'application_date')
        }),
        ('Financial Details', {
            'fields': ('amount', 'processing_fee', 'interest', 'total_loan_amount', 'repayment_frequency', 'number_of_fortnights', 'repayment_amount')
        }),
        ('Funding & Repayment', {
            'fields': ('funding_date', 'repayment_start_date', 'expected_end_date', 'repayment_dates', 'next_payment_date')
        }),
        ('Payment Tracking', {
            'fields': ('principal_loan_paid', 'interest_paid', 'default_interest_paid', 'total_paid', 'fortnights_paid', 'number_of_repayments',
                      'last_repayment_amount', 'last_repayment_date', 'number_of_advance_payments', 'last_advance_payment_date',
                      'last_advance_payment_amount', 'total_advance_payment', 'advance_payment_surplus')
        }),
        ('Default & Arrears', {
            'fields': ('number_of_defaults', 'last_default_date', 'last_default_amount', 'days_in_default', 'total_arrears')
        }),
        ('Receivables & Aging', {
            'fields': ('principal_loan_receivable', 'ordinary_interest_receivable', 'default_interest_receivable', 'total_outstanding',
                      'turnover_days', 'aging_category', 'aging_amount', 'considered_unrecoverable',
                      'principal_c_unrecoverable', 'interest_c_unrecoverable', 'recovery_date')
        }),
        ('Status & Notes', {
            'fields': ('category', 'funded_category', 'status', 'tc_agreement', 'tc_agreement_timestamp', 'dcc', 'notes')
        }),
        ('Optional Fields', {
            'fields': ('opt1', 'opt2', 'opt3', 'opt4', 'opt5')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('owner', 'officer', 'location')


# Let me know if you want any adjustments or added features! 🚀


@admin.register(Statement)
class StatementAdmin(_ReversingDeleteMixin, admin.ModelAdmin):
    def _reverse(self, obj):
        return reverse_statement(obj)

    list_display = (
        'ref', 'uid', 'luid', 'owner', 'loanref', 'date', 'type', 
        'debit', 'credit', 'arrears', 'balance', 
        'default_amount', 'default_interest',
        'principal_collected', 'interest_collected', 'default_interest_collected',
        'created_at', 'updated_at'
    )
    list_filter = ('type', 'date', 'owner', 'loanref')
    search_fields = ('ref', 'uid', 'luid', 'statement', 'dcc')
    date_hierarchy = 'date'
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Info', {
            'fields': ('ref', 'uid', 'luid', 'owner', 'loanref', 'date', 'type', 's_count')
        }),
        ('Transaction Details', {
            'fields': ('statement', 'debit', 'credit', 'arrears', 'balance')
        }),
        ('Default & Collections', {
            'fields': (
                'default_amount', 'default_interest', 
                'principal_collected', 'interest_collected', 'default_interest_collected'
            )
        }),
        ('Metadata', {
            'fields': ('dcc', 'created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        # Optimize query performance
        qs = super().get_queryset(request)
        return qs.select_related('owner', 'loanref')


# Let me know if you’d like any adjustments or custom actions! 🚀


class PaymentAdmin(_ReversingDeleteMixin, admin.ModelAdmin):
    def _reverse(self, obj):
        return reverse_payment(obj)

    list_display = (
        'ref', 'owner', 'loanref', 'p_count', 'date', 'amount', 'type', 'mode', 'officer', 'created_at', 'updated_at'
    )
    list_filter = ('type', 'mode', 'date', 'officer')
    search_fields = ('ref', 'loanref__ref', 'owner__user__username', 'statement')
    date_hierarchy = 'date'
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Payment Details', {
            'fields': ('ref', 'loanref', 'owner', 'officer', 'p_count', 'date', 'amount', 'type', 'mode')
        }),
        ('Additional Info', {
            'fields': ('statement', 'upload_id')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

admin.site.register(Payment, PaymentAdmin)

# Let me know if you want to add any custom actions or improve something! 🚀
