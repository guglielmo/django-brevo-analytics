from django.urls import path
from . import api_views, webhooks

app_name = 'brevo_analytics'

urlpatterns = [
    # API endpoints
    path('api/dashboard/', api_views.dashboard_api, name='api_dashboard'),
    path('api/messages/', api_views.messages_list_api, name='api_messages'),
    path('api/messages/<int:message_id>/emails/', api_views.message_emails_api, name='api_message_emails'),
    path('api/emails/bounced/', api_views.emails_bounced_api, name='api_emails_bounced'),
    path('api/emails/blocked/', api_views.emails_blocked_api, name='api_emails_blocked'),

    # Blacklist management
    path('api/blacklist/', api_views.list_blacklist_api, name='api_list_blacklist'),
    path('api/blacklist/enrich/', api_views.enrich_blocked_emails_api, name='api_enrich_blacklist'),
    path('api/blacklist/<str:email_address>/', api_views.check_blacklist_status_api, name='api_check_blacklist'),
    path('api/blacklist/<str:email_address>/remove/', api_views.remove_from_blacklist_api, name='api_remove_blacklist'),
    path('api/bounce-details/<str:email_address>/', api_views.get_bounce_details_api, name='api_bounce_details'),

    path('api/emails/<uuid:email_id>/', api_views.email_detail_api, name='api_email_detail'),

    # Webhook
    path('webhook/', webhooks.brevo_webhook, name='webhook'),
]
