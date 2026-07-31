from django.contrib import admin
from .models import SupportTicket, SupportTicketThread


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ref', 'user', 'category', 'subject', 'status', 'closed', 'date', 'updated_at')
    list_filter = ('category', 'status', 'closed', 'date')
    search_fields = ('ref', 'user__first_name', 'user__last_name', 'subject', 'content')
    readonly_fields = ('date', 'updated_at')
    fieldsets = (
        ('Ticket Info', {
            'fields': ('ref', 'user', 'category', 'subject', 'content', 'status', 'closed')
        }),
        ('Thread & Logs', {
            'fields': ('threadlog', 'threadq')
        }),
        ('Attachments', {
            'fields': ('attachment', 'attachment_name', 'attachment_url')
        }),
        ('Timestamps', {
            'fields': ('date', 'updated_at')
        }),
    )


@admin.register(SupportTicketThread)
class SupportTicketThreadAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'responder', 'date')
    list_filter = ('ticket', 'responder', 'date')
    search_fields = ('ticket__ref', 'responder', 'thread', 'thread_content')
    readonly_fields = ('date',)
    fieldsets = (
        ('Thread Info', {
            'fields': ('ticket', 'responder', 'thread', 'thread_content')
        }),
        ('Attachments', {
            'fields': ('attachment', 'attachment_name', 'attachment_url')
        }),
        ('Timestamps', {
            'fields': ('date',)
        }),
    )

# This setup makes ticket and thread management smooth and organized in the admin panel! 🚀
