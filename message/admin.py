from django.contrib import admin
from .models import Message

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        'category', 'location', 'date', 'subject', 'recipients_personal', 'recipients_work', 'delivery_status'
    )
    list_filter = ('category', 'location', 'delivery_status', 'date')
    search_fields = ('subject', 'content', 'emailto_personal', 'emailto_work')
    readonly_fields = ('date',)
    
    fieldsets = (
        ('Message Details', {
            'fields': ('category', 'location', 'date', 'subject', 'content', 'sender')
        }),
        ('Recipients Info', {
            'fields': (
                'recipients_personal', 'recipients_work',
                'emailto_personal', 'emailto_work'
            )
        }),
        ('Read & Delivery Status', {
            'fields': (
                'read_by_app', 'read_by_personal_email', 'read_by_work_email',
                'email_sent', 'email_not_sent', 'email_sent_work', 'email_not_sent_work',
                'delivery_status'
            )
        }),
        ('Attachments', {
            'fields': ('attachment', 'attachment_name', 'attachment_url')
        }),
    )

    def has_delete_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return True

# Let me know if you want to restrict access or add custom actions! 🚀
