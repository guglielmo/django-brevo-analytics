from django.contrib import admin
from django.urls import path
from .models import BrevoEmail
from . import views


@admin.register(BrevoEmail)
class BrevoEmailAdmin(admin.ModelAdmin):
    """
    Admin interface for Brevo Analytics.

    Uses virtual model pattern - overrides all URLs to custom views.
    Provides read-only access to Supabase data.
    """

    # Disable all modification permissions
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    # Override URLs to use custom views
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('',
                 self.admin_site.admin_view(views.dashboard_view),
                 name='brevo_analytics_brevoemail_changelist'),  # Match Django admin URL pattern
            path('dashboard/',
                 self.admin_site.admin_view(views.dashboard_view),
                 name='brevo_analytics_dashboard'),
            path('emails/',
                 self.admin_site.admin_view(views.email_list_view),
                 name='brevo_analytics_email_list'),
            path('emails/<uuid:email_id>/',
                 self.admin_site.admin_view(views.email_detail_view),
                 name='brevo_analytics_email_detail'),
        ]
        return custom_urls + urls

    # Customize admin changelist (won't be used, but good for consistency)
    list_display = ('__str__',)
