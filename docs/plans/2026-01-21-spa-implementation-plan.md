# Django-Native SPA Implementation Plan
**Date:** 2026-01-21
**Status:** Ready for Implementation
**Architecture:** Django Models + DRF API + Vue.js SPA

## Overview

Complete refactoring from Supabase-based to Django-native architecture with Vue.js SPA frontend.

**Key Changes:**
- Remove Supabase dependency → Django ORM direct database access
- Remove multi-tenant (clients table) → Single client per instance
- Events stored as JSONField in Email model (denormalized)
- Real-time webhook integration (no n8n needed)
- Vue.js SPA with modal-based email details (no page change)
- No temporal filters (show all historical data)

## Step-by-Step Implementation

---

## Phase 1: Django Models & Migrations (2 hours)

### Step 1.1: Create new models

**File:** `brevo_analytics/models.py`

**Action:** Complete rewrite of models

```python
import uuid
from django.db import models
from django.utils import timezone


class BrevoMessage(models.Model):
    """
    Messaggio/Campagna identificato da Subject + Data invio.
    Raggruppa tutte le email inviate con quel subject in quella data.
    """
    # Identificazione univoca: subject + sent_date
    subject = models.TextField()
    sent_date = models.DateField(db_index=True)

    # Statistiche denormalizzate (aggiornate via update_stats())
    total_sent = models.IntegerField(default=0)
    total_delivered = models.IntegerField(default=0)
    total_opened = models.IntegerField(default=0)
    total_clicked = models.IntegerField(default=0)
    total_bounced = models.IntegerField(default=0)
    total_blocked = models.IntegerField(default=0)

    # Rates calcolate
    delivery_rate = models.FloatField(default=0.0)
    open_rate = models.FloatField(default=0.0)
    click_rate = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'brevo_messages'
        ordering = ['-sent_date', 'subject']
        unique_together = [['subject', 'sent_date']]
        indexes = [
            models.Index(fields=['-sent_date']),
            models.Index(fields=['subject', 'sent_date']),
        ]
        verbose_name = 'Brevo Message'
        verbose_name_plural = 'Brevo Messages'

    def __str__(self):
        return f"{self.subject} - {self.sent_date}"

    def update_stats(self):
        """Ricalcola statistiche dalle email associate"""
        from django.db.models import Count, Q

        emails = self.emails.all()
        total = emails.count()

        if total == 0:
            self.total_sent = 0
            self.total_delivered = 0
            self.total_opened = 0
            self.total_clicked = 0
            self.total_bounced = 0
            self.total_blocked = 0
            self.delivery_rate = 0.0
            self.open_rate = 0.0
            self.click_rate = 0.0
            self.save()
            return

        # Conta per status
        stats = emails.aggregate(
            delivered=Count('id', filter=Q(current_status__in=['delivered', 'opened', 'clicked'])),
            opened=Count('id', filter=Q(current_status__in=['opened', 'clicked'])),
            clicked=Count('id', filter=Q(current_status='clicked')),
            bounced=Count('id', filter=Q(current_status='bounced')),
            blocked=Count('id', filter=Q(current_status='blocked')),
        )

        self.total_sent = total
        self.total_delivered = stats['delivered']
        self.total_opened = stats['opened']
        self.total_clicked = stats['clicked']
        self.total_bounced = stats['bounced']
        self.total_blocked = stats['blocked']

        # Calcola rates
        if self.total_sent > 0:
            self.delivery_rate = round(self.total_delivered / self.total_sent * 100, 2)
        if self.total_delivered > 0:
            self.open_rate = round(self.total_opened / self.total_delivered * 100, 2)
            self.click_rate = round(self.total_clicked / self.total_delivered * 100, 2)

        self.save(update_fields=[
            'total_sent', 'total_delivered', 'total_opened', 'total_clicked',
            'total_bounced', 'total_blocked', 'delivery_rate', 'open_rate',
            'click_rate', 'updated_at'
        ])


class Email(models.Model):
    """Singola email inviata a un destinatario"""

    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('opened', 'Opened'),
        ('clicked', 'Clicked'),
        ('bounced', 'Bounced'),
        ('blocked', 'Blocked'),
        ('deferred', 'Deferred'),
        ('unsubscribed', 'Unsubscribed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        BrevoMessage,
        on_delete=models.CASCADE,
        related_name='emails'
    )
    brevo_message_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Brevo's unique message ID (e.g., <123456@smtp-relay.mailin.fr>)"
    )
    recipient_email = models.EmailField(db_index=True)
    sent_at = models.DateTimeField(db_index=True)

    # Eventi come JSONField array
    events = models.JSONField(
        default=list,
        help_text="Array of events: [{type, timestamp, ...extra_data}]"
    )

    # Status cache per query veloci
    current_status = models.CharField(
        max_length=20,
        default='sent',
        db_index=True,
        choices=STATUS_CHOICES
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'brevo_emails'
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['message', '-sent_at']),
            models.Index(fields=['recipient_email']),
            models.Index(fields=['current_status']),
            models.Index(fields=['brevo_message_id']),
        ]
        verbose_name = 'Email'
        verbose_name_plural = 'Emails'

    def __str__(self):
        return f"{self.recipient_email} - {self.message.subject}"

    def add_event(self, event_type, timestamp, **extra_data):
        """
        Aggiunge un evento alla timeline e aggiorna current_status.
        Controlla duplicati prima di aggiungere.
        """
        # Normalizza timestamp
        if hasattr(timestamp, 'isoformat'):
            timestamp_str = timestamp.isoformat()
        else:
            timestamp_str = str(timestamp)

        # Controlla duplicati
        for event in self.events:
            if (event.get('type') == event_type and
                event.get('timestamp') == timestamp_str):
                # Evento già presente, skip
                return False

        # Aggiungi nuovo evento
        event_data = {
            'type': event_type,
            'timestamp': timestamp_str,
            **extra_data
        }
        self.events.append(event_data)

        # Aggiorna status
        self.update_status()

        # Salva
        self.save(update_fields=['events', 'current_status', 'updated_at'])

        # Aggiorna stats del messaggio
        self.message.update_stats()

        return True

    def update_status(self):
        """Calcola current_status dalla gerarchia eventi"""
        event_types = {e['type'] for e in self.events}

        # Gerarchia: clicked > opened > delivered > bounced > blocked > deferred > unsubscribed > sent
        if 'clicked' in event_types:
            self.current_status = 'clicked'
        elif 'opened' in event_types:
            self.current_status = 'opened'
        elif 'delivered' in event_types:
            self.current_status = 'delivered'
        elif 'bounced' in event_types:
            self.current_status = 'bounced'
        elif 'blocked' in event_types:
            self.current_status = 'blocked'
        elif 'deferred' in event_types:
            self.current_status = 'deferred'
        elif 'unsubscribed' in event_types:
            self.current_status = 'unsubscribed'
        else:
            self.current_status = 'sent'
```

### Step 1.2: Remove old code

**Files to delete:**
- `brevo_analytics/supabase.py`
- `brevo_analytics/exceptions.py` (if only contains SupabaseAPIError)
- `sql/` directory (entire)
- `docs/SUPABASE_SETUP.md`
- `docs/n8n-workflow-design.md`

**Command:**
```bash
rm -rf brevo_analytics/supabase.py
rm -rf sql/
rm -f docs/SUPABASE_SETUP.md docs/n8n-workflow-design.md
```

### Step 1.3: Create migrations

**Command:**
```bash
python manage.py makemigrations brevo_analytics
python manage.py migrate brevo_analytics
```

**Expected output:**
```
Migrations for 'brevo_analytics':
  brevo_analytics/migrations/0001_initial.py
    - Create model BrevoMessage
    - Create model Email
```

---

## Phase 2: Django REST Framework API (3 hours)

### Step 2.1: Install dependencies

**File:** `requirements.txt` (add if not present)

```txt
Django>=4.2
djangorestframework>=3.14
django-cors-headers>=4.3
```

**Command:**
```bash
pip install djangorestframework django-cors-headers
```

### Step 2.2: Update settings

**File:** `settings.py` (or your project settings)

**Add to INSTALLED_APPS:**
```python
INSTALLED_APPS = [
    # ...
    'rest_framework',
    'corsheaders',
    'brevo_analytics',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Add at top
    # ... other middleware
]

# DRF settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAdminUser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 100,
}

# CORS (development only - adjust for production)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
]

# Brevo Analytics configuration
BREVO_ANALYTICS = {
    'WEBHOOK_SECRET': 'your-webhook-secret-here',  # From Brevo dashboard
    'CLIENT_UID': 'your-client-uuid',  # For tracking/reporting
}
```

### Step 2.3: Create serializers

**File:** `brevo_analytics/serializers.py` (new file)

```python
from rest_framework import serializers
from .models import BrevoMessage, Email


class BrevoMessageSerializer(serializers.ModelSerializer):
    """Serializer per lista messaggi"""
    class Meta:
        model = BrevoMessage
        fields = [
            'id', 'subject', 'sent_date',
            'total_sent', 'total_delivered', 'total_opened',
            'total_clicked', 'total_bounced', 'total_blocked',
            'delivery_rate', 'open_rate', 'click_rate',
            'updated_at'
        ]


class EmailListSerializer(serializers.ModelSerializer):
    """Serializer per lista email (senza eventi)"""
    class Meta:
        model = Email
        fields = [
            'id', 'recipient_email', 'current_status', 'sent_at'
        ]


class EmailDetailSerializer(serializers.ModelSerializer):
    """Serializer per dettaglio email (con eventi e messaggio)"""
    message = serializers.SerializerMethodField()

    class Meta:
        model = Email
        fields = [
            'id', 'recipient_email', 'current_status',
            'sent_at', 'events', 'message'
        ]

    def get_message(self, obj):
        return {
            'id': obj.message.id,
            'subject': obj.message.subject,
            'sent_date': obj.message.sent_date.isoformat()
        }


class MessageEmailsSerializer(serializers.Serializer):
    """Serializer per risposta /api/messages/:id/emails/"""
    message = BrevoMessageSerializer()
    emails = EmailListSerializer(many=True)


class GlobalEmailsSerializer(serializers.ModelSerializer):
    """Serializer per email globali bounced/blocked (con info messaggio)"""
    message = serializers.SerializerMethodField()

    class Meta:
        model = Email
        fields = [
            'id', 'recipient_email', 'current_status',
            'sent_at', 'message'
        ]

    def get_message(self, obj):
        return {
            'subject': obj.message.subject,
            'sent_date': obj.message.sent_date.isoformat()
        }
```

### Step 2.4: Create API views

**File:** `brevo_analytics/api_views.py` (new file)

```python
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django.db.models import Sum, Avg, Count, Q
from .models import BrevoMessage, Email
from .serializers import (
    BrevoMessageSerializer,
    EmailListSerializer,
    EmailDetailSerializer,
    MessageEmailsSerializer,
    GlobalEmailsSerializer
)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def dashboard_api(request):
    """
    Dashboard KPI + ultimi 20 messaggi.

    GET /api/dashboard/
    """
    # Calcola KPI globali
    all_messages = BrevoMessage.objects.all()

    kpi = all_messages.aggregate(
        total_sent=Sum('total_sent'),
        total_delivered=Sum('total_delivered'),
        total_opened=Sum('total_opened'),
        total_clicked=Sum('total_clicked'),
        total_bounced=Sum('total_bounced'),
        total_blocked=Sum('total_blocked'),
    )

    # Calcola rates globali
    total_sent = kpi['total_sent'] or 0
    total_delivered = kpi['total_delivered'] or 0

    if total_sent > 0:
        delivery_rate = round(total_delivered / total_sent * 100, 2)
    else:
        delivery_rate = 0.0

    if total_delivered > 0:
        open_rate = round((kpi['total_opened'] or 0) / total_delivered * 100, 2)
        click_rate = round((kpi['total_clicked'] or 0) / total_delivered * 100, 2)
    else:
        open_rate = 0.0
        click_rate = 0.0

    kpi_data = {
        'total_sent': total_sent,
        'delivery_rate': delivery_rate,
        'open_rate': open_rate,
        'click_rate': click_rate,
        'total_bounced': kpi['total_bounced'] or 0,
        'total_blocked': kpi['total_blocked'] or 0,
    }

    # Ultimi 20 messaggi
    recent_messages = BrevoMessage.objects.all()[:20]
    messages_data = BrevoMessageSerializer(recent_messages, many=True).data

    return Response({
        'kpi': kpi_data,
        'recent_messages': messages_data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def messages_list_api(request):
    """
    Lista di tutti i messaggi (per "Mostra tutti").

    GET /api/messages/
    """
    messages = BrevoMessage.objects.all()
    serializer = BrevoMessageSerializer(messages, many=True)

    return Response({
        'messages': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def message_emails_api(request, message_id):
    """
    Email per messaggio specifico.

    GET /api/messages/:id/emails/
    """
    try:
        message = BrevoMessage.objects.get(id=message_id)
    except BrevoMessage.DoesNotExist:
        return Response({'error': 'Message not found'}, status=404)

    emails = message.emails.all()

    # Filtro per status se presente query param
    status_filter = request.GET.get('status')
    if status_filter:
        emails = emails.filter(current_status=status_filter)

    message_data = BrevoMessageSerializer(message).data
    emails_data = EmailListSerializer(emails, many=True).data

    return Response({
        'message': message_data,
        'emails': emails_data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def emails_bounced_api(request):
    """
    Tutte le email bounced (cross-message).

    GET /api/emails/bounced/
    """
    emails = Email.objects.filter(current_status='bounced').select_related('message')
    serializer = GlobalEmailsSerializer(emails, many=True)

    return Response({
        'emails': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def emails_blocked_api(request):
    """
    Tutte le email blocked (cross-message).

    GET /api/emails/blocked/
    """
    emails = Email.objects.filter(current_status='blocked').select_related('message')
    serializer = GlobalEmailsSerializer(emails, many=True)

    return Response({
        'emails': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def email_detail_api(request, email_id):
    """
    Dettaglio email singola (per modale).

    GET /api/emails/:id/
    """
    try:
        email = Email.objects.select_related('message').get(id=email_id)
    except Email.DoesNotExist:
        return Response({'error': 'Email not found'}, status=404)

    serializer = EmailDetailSerializer(email)
    return Response(serializer.data)
```

### Step 2.5: Create URL configuration

**File:** `brevo_analytics/urls.py` (update)

```python
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
    path('api/emails/<uuid:email_id>/', api_views.email_detail_api, name='api_email_detail'),

    # Webhook
    path('webhook/', webhooks.brevo_webhook, name='webhook'),
]
```

**Include in main urls.py:**
```python
# your_project/urls.py
urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin/brevo_analytics/', include('brevo_analytics.urls')),
]
```

---

## Phase 3: Brevo Webhook Integration (1 hour)

### Step 3.1: Create webhook handler

**File:** `brevo_analytics/webhooks.py` (new file)

```python
import hmac
import hashlib
import json
import logging
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from .models import BrevoMessage, Email

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def brevo_webhook(request):
    """
    Brevo webhook endpoint for real-time event processing.

    Configure in Brevo dashboard:
    URL: https://your-domain.com/admin/brevo_analytics/webhook/
    Events: All transactional email events
    """
    # Verify webhook signature (if configured)
    config = getattr(settings, 'BREVO_ANALYTICS', {})
    webhook_secret = config.get('WEBHOOK_SECRET')

    if webhook_secret:
        signature = request.headers.get('X-Brevo-Signature', '')
        computed_signature = hmac.new(
            webhook_secret.encode(),
            request.body,
            hashlib.sha256
        ).hexdigest()

        if signature != computed_signature:
            logger.warning("Invalid webhook signature")
            return HttpResponseBadRequest('Invalid signature')

    # Parse webhook payload
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return HttpResponseBadRequest('Invalid JSON')

    # Extract required fields
    event_type = payload.get('event')
    message_id = payload.get('message-id')
    email_address = payload.get('email')
    subject = payload.get('subject', '')
    timestamp_unix = payload.get('ts_event')

    if not all([event_type, message_id, email_address, timestamp_unix]):
        logger.error(f"Missing required fields in webhook: {payload}")
        return HttpResponseBadRequest('Missing required fields')

    # Convert timestamp
    try:
        event_datetime = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
    except (ValueError, OSError):
        logger.error(f"Invalid timestamp: {timestamp_unix}")
        return HttpResponseBadRequest('Invalid timestamp')

    event_date = event_datetime.date()

    # 1. Get or create BrevoMessage (identified by subject + sent_date)
    message, message_created = BrevoMessage.objects.get_or_create(
        subject=subject,
        sent_date=event_date,
        defaults={
            'total_sent': 0,
        }
    )

    if message_created:
        logger.info(f"Created new message: {subject} - {event_date}")

    # 2. Get or create Email
    email, email_created = Email.objects.get_or_create(
        brevo_message_id=message_id,
        defaults={
            'message': message,
            'recipient_email': email_address,
            'sent_at': event_datetime,
            'current_status': 'sent',
            'events': []
        }
    )

    if email_created:
        logger.info(f"Created new email: {message_id} to {email_address}")

    # 3. Map Brevo event name to our event type
    event_mapping = {
        'request': 'sent',
        'delivered': 'delivered',
        'hard_bounce': 'bounced',
        'soft_bounce': 'bounced',
        'blocked': 'blocked',
        'spam': 'spam',
        'unsubscribe': 'unsubscribed',
        'opened': 'opened',
        'click': 'clicked',
        'deferred': 'deferred',
    }

    our_event_type = event_mapping.get(event_type, event_type)

    # 4. Build event data with extra fields
    extra_data = {}

    # Bounce information
    if 'bounce' in event_type:
        extra_data['bounce_type'] = 'hard' if 'hard' in event_type else 'soft'
        extra_data['bounce_reason'] = payload.get('reason', '')

    # Click information
    if event_type == 'click':
        extra_data['url'] = payload.get('link', '')

    # Open information
    if event_type == 'opened':
        extra_data['ip'] = payload.get('ip', '')
        extra_data['user_agent'] = payload.get('user_agent', '')

    # Store raw payload for debugging
    extra_data['raw'] = payload

    # 5. Add event (handles duplicates internally)
    added = email.add_event(our_event_type, event_datetime, **extra_data)

    if added:
        logger.info(f"Added event {our_event_type} for email {message_id}")
    else:
        logger.debug(f"Event {our_event_type} already exists for email {message_id}")

    return JsonResponse({'status': 'ok'})
```

### Step 3.2: Test webhook locally

**Command (using ngrok for local testing):**
```bash
# Terminal 1: Start Django
python manage.py runserver

# Terminal 2: Start ngrok
ngrok http 8000

# Copy ngrok URL and configure in Brevo dashboard:
# https://abc123.ngrok.io/admin/brevo_analytics/webhook/
```

**Test with curl:**
```bash
curl -X POST http://localhost:8000/admin/brevo_analytics/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "event": "delivered",
    "message-id": "<test123@smtp-relay.mailin.fr>",
    "email": "test@example.com",
    "subject": "Test Email",
    "ts_event": 1737468000
  }'
```

---

## Phase 4: Vue.js SPA Frontend (4 hours)

### Step 4.1: Create SPA entry point template

**File:** `brevo_analytics/templates/brevo_analytics/spa.html` (new file)

```html
{% extends "admin/base_site.html" %}
{% load static %}

{% block extrastyle %}
<link rel="stylesheet" href="{% static 'brevo_analytics/css/app.css' %}">
{% endblock %}

{% block content %}
<div id="brevo-app">
  <router-view></router-view>
  <email-detail-modal></email-detail-modal>
</div>

<script src="https://unpkg.com/vue@3.4.15/dist/vue.global.prod.js"></script>
<script src="https://unpkg.com/vue-router@4.2.5/dist/vue-router.global.prod.js"></script>
<script src="{% static 'brevo_analytics/js/app.js' %}" type="module"></script>
{% endblock %}
```

### Step 4.2: Create admin view to serve SPA

**File:** `brevo_analytics/admin.py` (update)

```python
from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from .models import BrevoMessage, Email


@admin.register(BrevoMessage)
class BrevoMessageAdmin(admin.ModelAdmin):
    list_display = ['subject', 'sent_date', 'total_sent', 'delivery_rate', 'open_rate']
    list_filter = ['sent_date']
    search_fields = ['subject']
    readonly_fields = ['total_sent', 'total_delivered', 'total_opened',
                      'total_clicked', 'total_bounced', 'total_blocked',
                      'delivery_rate', 'open_rate', 'click_rate']

    def get_urls(self):
        """Override to serve SPA at changelist URL"""
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_site.admin_view(self.spa_view), name='brevo_spa'),
        ]
        return custom_urls + urls

    def spa_view(self, request):
        """Serve Vue.js SPA"""
        return render(request, 'brevo_analytics/spa.html', {
            'title': 'Brevo Analytics',
            'site_title': admin.site.site_title,
            'site_header': admin.site.site_header,
        })


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ['recipient_email', 'message', 'current_status', 'sent_at']
    list_filter = ['current_status', 'sent_at']
    search_fields = ['recipient_email', 'brevo_message_id']
    readonly_fields = ['brevo_message_id', 'events', 'current_status', 'sent_at']

    def has_add_permission(self, request):
        return False  # No manual creation
```

### Step 4.3: Create CSS

**File:** `brevo_analytics/static/brevo_analytics/css/app.css` (new file)

```css
/* Reset and base styles */
#brevo-app {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.6;
  color: #333;
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

/* Breadcrumb */
.breadcrumb {
  font-size: 14px;
  margin-bottom: 20px;
  color: #666;
}

.breadcrumb a {
  color: #417690;
  text-decoration: none;
}

.breadcrumb a:hover {
  text-decoration: underline;
}

/* KPI Cards */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.kpi-card {
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  transition: transform 0.2s, box-shadow 0.2s;
}

.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.kpi-card.clickable {
  cursor: pointer;
}

.kpi-label {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

.kpi-value {
  font-size: 32px;
  font-weight: bold;
  color: #333;
}

.kpi-value a {
  color: #417690;
  text-decoration: none;
}

.kpi-value a:hover {
  text-decoration: underline;
}

/* KPI Bar (for filtering) */
.kpi-bar {
  display: flex;
  gap: 15px;
  margin-bottom: 30px;
  flex-wrap: wrap;
}

.kpi-bar .kpi-card {
  flex: 1;
  min-width: 150px;
  cursor: pointer;
  border: 2px solid transparent;
}

.kpi-bar .kpi-card.active {
  border-color: #417690;
  background-color: #f0f7fa;
}

.kpi-bar .kpi-value {
  font-size: 24px;
}

/* Section */
.section {
  margin-bottom: 40px;
}

.section h2 {
  font-size: 20px;
  margin-bottom: 15px;
  color: #333;
}

/* Messages list */
.messages-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.btn-link {
  color: #417690;
  text-decoration: none;
  font-size: 14px;
}

.btn-link:hover {
  text-decoration: underline;
}

/* Table */
.data-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.data-table thead {
  background-color: #f5f5f5;
}

.data-table th {
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  font-size: 14px;
  color: #666;
  border-bottom: 2px solid #ddd;
}

.data-table td {
  padding: 12px 16px;
  border-bottom: 1px solid #eee;
  font-size: 14px;
}

.data-table tbody tr {
  cursor: pointer;
  transition: background-color 0.15s;
}

.data-table tbody tr:hover {
  background-color: #f9f9f9;
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

/* Status badge */
.status-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.status-sent {
  background-color: #e0e0e0;
  color: #666;
}

.status-delivered {
  background-color: #e8f5e9;
  color: #2e7d32;
}

.status-opened {
  background-color: #e3f2fd;
  color: #1565c0;
}

.status-clicked {
  background-color: #fff3e0;
  color: #e65100;
}

.status-bounced {
  background-color: #ffebee;
  color: #c62828;
}

.status-blocked {
  background-color: #fce4ec;
  color: #880e4f;
}

.status-deferred {
  background-color: #fff9c4;
  color: #f57f17;
}

.status-unsubscribed {
  background-color: #f5f5f5;
  color: #666;
}

/* Rate badges */
.badge.success {
  background-color: #e8f5e9;
  color: #2e7d32;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
}

.badge.warning {
  background-color: #fff3e0;
  color: #e65100;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
}

.badge.danger {
  background-color: #ffebee;
  color: #c62828;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
}

/* Search box */
.search-box {
  margin-bottom: 20px;
}

.search-box input {
  width: 100%;
  max-width: 400px;
  padding: 10px 16px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

.search-box input:focus {
  outline: none;
  border-color: #417690;
  box-shadow: 0 0 0 3px rgba(65, 118, 144, 0.1);
}

/* Email detail modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 20px;
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 100%;
  max-width: 700px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
  padding: 24px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: start;
}

.modal-header h2 {
  font-size: 20px;
  margin: 0 0 8px 0;
  color: #333;
}

.modal-header p {
  font-size: 14px;
  color: #666;
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  font-size: 28px;
  color: #999;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.15s;
}

.modal-close:hover {
  background-color: #f5f5f5;
  color: #333;
}

.modal-body {
  padding: 24px;
}

/* Timeline */
.timeline {
  position: relative;
  padding-left: 40px;
}

.timeline-event {
  position: relative;
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-left: 2px solid #ddd;
}

.timeline-event:last-child {
  border-left-color: transparent;
  margin-bottom: 0;
  padding-bottom: 0;
}

.timeline-marker {
  position: absolute;
  left: -9px;
  top: 4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background-color: #417690;
  border: 3px solid white;
  box-shadow: 0 0 0 2px #ddd;
}

.timeline-content {
  padding-left: 16px;
}

.event-title {
  font-weight: 600;
  font-size: 15px;
  color: #333;
  margin-bottom: 4px;
}

.event-time {
  font-size: 13px;
  color: #999;
  margin-bottom: 8px;
}

.event-detail {
  font-size: 13px;
  color: #666;
  margin-top: 6px;
}

.event-detail strong {
  color: #333;
}

.event-detail a {
  color: #417690;
  word-break: break-all;
}

/* Event type colors */
.event-sent .timeline-marker {
  background-color: #9e9e9e;
}

.event-delivered .timeline-marker {
  background-color: #4caf50;
}

.event-opened .timeline-marker {
  background-color: #2196f3;
}

.event-clicked .timeline-marker {
  background-color: #ff9800;
}

.event-bounced .timeline-marker {
  background-color: #f44336;
}

.event-blocked .timeline-marker {
  background-color: #c2185b;
}

/* Loading state */
.loading {
  text-align: center;
  padding: 20px;
  color: #999;
}

/* Responsive */
@media (max-width: 768px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }

  .kpi-bar {
    flex-direction: column;
  }

  .data-table {
    font-size: 13px;
  }

  .data-table th,
  .data-table td {
    padding: 10px 12px;
  }
}
```

### Step 4.4: Create Vue.js app

**File:** `brevo_analytics/static/brevo_analytics/js/app.js` (new file)

```javascript
const { createApp, ref, computed, onMounted, watch } = Vue
const { createRouter, createWebHashHistory } = VueRouter

// ========================================
// API Helper
// ========================================
const api = {
  async get(url) {
    const response = await fetch(`/admin/brevo_analytics${url}`)
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`)
    }
    return response.json()
  }
}

// ========================================
// Shared Composables
// ========================================
const emailModal = {
  isOpen: ref(false),
  emailData: ref(null),
  loading: ref(false),

  async open(emailId) {
    this.isOpen.value = true
    this.loading.value = true
    try {
      this.emailData.value = await api.get(`/api/emails/${emailId}/`)
    } catch (error) {
      console.error('Failed to load email details:', error)
      alert('Errore nel caricamento dei dettagli email')
      this.close()
    } finally {
      this.loading.value = false
    }
  },

  close() {
    this.isOpen.value = false
    this.emailData.value = null
  }
}

// ========================================
// Components
// ========================================

// Breadcrumb Component
const Breadcrumb = {
  template: `
    <div class="breadcrumb">
      <router-link to="/">Dashboard</router-link>
      <span v-if="text"> / {{ text }}</span>
    </div>
  `,
  props: ['text']
}

// Email Detail Modal Component
const EmailDetailModal = {
  template: `
    <div v-if="isOpen" class="modal-overlay" @click.self="close">
      <div class="modal-content">
        <div class="modal-header">
          <div>
            <h2>{{ email?.recipient_email }}</h2>
            <p>{{ email?.message.subject }} · {{ formatDate(email?.message.sent_date) }}</p>
          </div>
          <button class="modal-close" @click="close">×</button>
        </div>
        <div class="modal-body">
          <div v-if="loading" class="loading">Caricamento...</div>
          <div v-else-if="email">
            <h3 style="margin-bottom: 20px;">Timeline Eventi</h3>
            <div class="timeline">
              <div
                v-for="(event, index) in email.events"
                :key="index"
                class="timeline-event"
                :class="'event-' + event.type">
                <div class="timeline-marker"></div>
                <div class="timeline-content">
                  <div class="event-title">{{ eventLabel(event.type) }}</div>
                  <div class="event-time">{{ formatDateTime(event.timestamp) }}</div>

                  <div v-if="event.bounce_reason" class="event-detail">
                    <strong>Motivo:</strong> {{ event.bounce_reason }}
                  </div>
                  <div v-if="event.url" class="event-detail">
                    <strong>URL:</strong> <a :href="event.url" target="_blank">{{ event.url }}</a>
                  </div>
                  <div v-if="event.ip" class="event-detail">
                    <strong>IP:</strong> {{ event.ip }}
                  </div>
                  <div v-if="event.user_agent" class="event-detail">
                    <strong>User Agent:</strong> {{ event.user_agent }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,

  setup() {
    const isOpen = emailModal.isOpen
    const email = emailModal.emailData
    const loading = emailModal.loading

    const close = () => emailModal.close()

    const formatDate = (dateStr) => {
      if (!dateStr) return ''
      return new Date(dateStr).toLocaleDateString('it-IT', {
        day: 'numeric',
        month: 'long',
        year: 'numeric'
      })
    }

    const formatDateTime = (dateStr) => {
      if (!dateStr) return ''
      return new Date(dateStr).toLocaleString('it-IT', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    }

    const eventLabel = (type) => {
      const labels = {
        'sent': 'Inviata',
        'delivered': 'Consegnata',
        'opened': 'Aperta',
        'clicked': 'Cliccata',
        'bounced': 'Rimbalzata',
        'blocked': 'Bloccata',
        'deferred': 'Differita',
        'unsubscribed': 'Disiscritto'
      }
      return labels[type] || type
    }

    return {
      isOpen,
      email,
      loading,
      close,
      formatDate,
      formatDateTime,
      eventLabel
    }
  }
}

// Dashboard Component
const Dashboard = {
  template: `
    <div class="dashboard">
      <h1>Brevo Analytics</h1>

      <div v-if="loading" class="loading">Caricamento...</div>

      <div v-else>
        <!-- KPI Cards -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">Email Inviate</div>
            <div class="kpi-value">{{ kpi.total_sent }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Delivery Rate</div>
            <div class="kpi-value">{{ kpi.delivery_rate }}%</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Open Rate</div>
            <div class="kpi-value">{{ kpi.open_rate }}%</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Click Rate</div>
            <div class="kpi-value">{{ kpi.click_rate }}%</div>
          </div>
          <div class="kpi-card clickable">
            <div class="kpi-label">Email Bounced</div>
            <div class="kpi-value">
              <router-link to="/emails/bounced">{{ kpi.total_bounced }}</router-link>
            </div>
          </div>
          <div class="kpi-card clickable">
            <div class="kpi-label">Email Blocked</div>
            <div class="kpi-value">
              <router-link to="/emails/blocked">{{ kpi.total_blocked }}</router-link>
            </div>
          </div>
        </div>

        <!-- Messages List -->
        <div class="section">
          <div class="messages-header">
            <h2>{{ showAll ? 'Tutti i Messaggi' : 'Ultimi Messaggi' }}</h2>
            <a v-if="!showAll" href="#" @click.prevent="showAll = true" class="btn-link">
              Mostra tutti →
            </a>
          </div>

          <table class="data-table">
            <thead>
              <tr>
                <th>Subject</th>
                <th>Data</th>
                <th>Inviati</th>
                <th>Delivery</th>
                <th>Open</th>
                <th>Click</th>
                <th>Bounced</th>
                <th>Blocked</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="msg in displayedMessages"
                :key="msg.id"
                @click="goToMessage(msg.id)">
                <td><strong>{{ msg.subject }}</strong></td>
                <td>{{ formatDate(msg.sent_date) }}</td>
                <td>{{ msg.total_sent }}</td>
                <td>
                  <span class="badge" :class="rateClass(msg.delivery_rate)">
                    {{ msg.delivery_rate }}%
                  </span>
                </td>
                <td>{{ msg.open_rate }}%</td>
                <td>{{ msg.click_rate }}%</td>
                <td>
                  <a v-if="msg.total_bounced > 0"
                     @click.stop
                     :href="'#/messages/' + msg.id + '/emails?status=bounced'">
                    {{ msg.total_bounced }}
                  </a>
                  <span v-else>0</span>
                </td>
                <td>
                  <a v-if="msg.total_blocked > 0"
                     @click.stop
                     :href="'#/messages/' + msg.id + '/emails?status=blocked'">
                    {{ msg.total_blocked }}
                  </a>
                  <span v-else>0</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `,

  setup() {
    const loading = ref(true)
    const kpi = ref({})
    const messages = ref([])
    const allMessages = ref([])
    const showAll = ref(false)

    const displayedMessages = computed(() => {
      return showAll.value ? allMessages.value : messages.value
    })

    onMounted(async () => {
      try {
        const data = await api.get('/api/dashboard/')
        kpi.value = data.kpi
        messages.value = data.recent_messages
      } catch (error) {
        console.error('Failed to load dashboard:', error)
        alert('Errore nel caricamento della dashboard')
      } finally {
        loading.value = false
      }
    })

    watch(showAll, async (value) => {
      if (value && allMessages.value.length === 0) {
        try {
          const data = await api.get('/api/messages/')
          allMessages.value = data.messages
        } catch (error) {
          console.error('Failed to load all messages:', error)
        }
      }
    })

    const formatDate = (dateStr) => {
      return new Date(dateStr).toLocaleDateString('it-IT', {
        day: 'numeric',
        month: 'short'
      })
    }

    const rateClass = (rate) => {
      if (rate >= 95) return 'success'
      if (rate >= 90) return 'warning'
      return 'danger'
    }

    const goToMessage = (messageId) => {
      router.push(`/messages/${messageId}/emails`)
    }

    return {
      loading,
      kpi,
      messages,
      showAll,
      displayedMessages,
      formatDate,
      rateClass,
      goToMessage
    }
  },

  components: {
    Breadcrumb
  }
}

// Message Emails Component
const MessageEmails = {
  template: `
    <div class="message-emails">
      <Breadcrumb :text="breadcrumbText" />

      <div v-if="loading" class="loading">Caricamento...</div>

      <div v-else-if="message">
        <!-- KPI Bar -->
        <div class="kpi-bar">
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'sent' }"
            @click="setFilter('sent')">
            <div class="kpi-label">Sent</div>
            <div class="kpi-value">{{ message.total_sent }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'delivered' }"
            @click="setFilter('delivered')">
            <div class="kpi-label">Delivered</div>
            <div class="kpi-value">{{ message.total_delivered }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'opened' }"
            @click="setFilter('opened')">
            <div class="kpi-label">Opened</div>
            <div class="kpi-value">{{ message.total_opened }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'clicked' }"
            @click="setFilter('clicked')">
            <div class="kpi-label">Clicked</div>
            <div class="kpi-value">{{ message.total_clicked }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'bounced' }"
            @click="setFilter('bounced')">
            <div class="kpi-label">Bounced</div>
            <div class="kpi-value">{{ message.total_bounced }}</div>
          </div>
          <div
            class="kpi-card"
            :class="{ active: activeFilter === 'blocked' }"
            @click="setFilter('blocked')">
            <div class="kpi-label">Blocked</div>
            <div class="kpi-value">{{ message.total_blocked }}</div>
          </div>
        </div>

        <!-- Search -->
        <div class="search-box">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="🔍 Cerca per email..."
            @input="filterEmails">
        </div>

        <!-- Emails Table -->
        <table class="data-table">
          <thead>
            <tr>
              <th>Destinatario</th>
              <th>Inviata</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="email in filteredEmails"
              :key="email.id"
              @click="openEmailDetail(email.id)">
              <td>{{ email.recipient_email }}</td>
              <td>{{ formatDateTime(email.sent_at) }}</td>
              <td>
                <span class="status-badge" :class="'status-' + email.current_status">
                  {{ statusLabel(email.current_status) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,

  setup() {
    const route = useRoute()
    const loading = ref(true)
    const message = ref(null)
    const emails = ref([])
    const searchQuery = ref('')
    const activeFilter = ref(null)
    const filteredEmails = ref([])

    const breadcrumbText = computed(() => {
      if (!message.value) return ''
      return `${message.value.subject} - ${formatDate(message.value.sent_date)}`
    })

    onMounted(async () => {
      const messageId = route.params.messageId
      const statusParam = route.query.status

      try {
        const data = await api.get(`/api/messages/${messageId}/emails/`)
        message.value = data.message
        emails.value = data.emails

        if (statusParam) {
          setFilter(statusParam)
        } else {
          filteredEmails.value = emails.value
        }
      } catch (error) {
        console.error('Failed to load message emails:', error)
        alert('Errore nel caricamento delle email')
      } finally {
        loading.value = false
      }
    })

    const setFilter = (status) => {
      if (activeFilter.value === status) {
        // Toggle off
        activeFilter.value = null
        filterEmails()
      } else {
        activeFilter.value = status
        filterEmails()
      }
    }

    const filterEmails = () => {
      let filtered = emails.value

      // Apply status filter
      if (activeFilter.value) {
        filtered = filtered.filter(e => e.current_status === activeFilter.value)
      }

      // Apply search
      if (searchQuery.value) {
        const query = searchQuery.value.toLowerCase()
        filtered = filtered.filter(e =>
          e.recipient_email.toLowerCase().includes(query)
        )
      }

      filteredEmails.value = filtered
    }

    const formatDate = (dateStr) => {
      return new Date(dateStr).toLocaleDateString('it-IT', {
        day: 'numeric',
        month: 'long',
        year: 'numeric'
      })
    }

    const formatDateTime = (dateStr) => {
      return new Date(dateStr).toLocaleString('it-IT', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit'
      })
    }

    const statusLabel = (status) => {
      const labels = {
        'sent': 'Inviata',
        'delivered': 'Consegnata',
        'opened': 'Aperta',
        'clicked': 'Cliccata',
        'bounced': 'Rimbalzata',
        'blocked': 'Bloccata',
        'deferred': 'Differita'
      }
      return labels[status] || status
    }

    const openEmailDetail = (emailId) => {
      emailModal.open(emailId)
    }

    return {
      loading,
      message,
      searchQuery,
      activeFilter,
      filteredEmails,
      breadcrumbText,
      setFilter,
      filterEmails,
      formatDate,
      formatDateTime,
      statusLabel,
      openEmailDetail
    }
  },

  components: {
    Breadcrumb
  }
}

// Global Emails Component (Bounced/Blocked)
const GlobalEmails = {
  template: `
    <div class="global-emails">
      <Breadcrumb :text="breadcrumbText" />

      <div v-if="loading" class="loading">Caricamento...</div>

      <div v-else>
        <!-- Search -->
        <div class="search-box">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="🔍 Cerca per email..."
            @input="filterEmails">
        </div>

        <!-- Emails Table -->
        <table class="data-table">
          <thead>
            <tr>
              <th>Messaggio</th>
              <th>Destinatario</th>
              <th>Data</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="email in filteredEmails"
              :key="email.id"
              @click="openEmailDetail(email.id)">
              <td>
                <strong>{{ email.message.subject }}</strong><br>
                <small style="color: #999;">{{ formatDate(email.message.sent_date) }}</small>
              </td>
              <td>{{ email.recipient_email }}</td>
              <td>{{ formatDateTime(email.sent_at) }}</td>
              <td>
                <span class="status-badge" :class="'status-' + email.current_status">
                  {{ statusLabel(email.current_status) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,

  props: ['type'],

  setup(props) {
    const loading = ref(true)
    const emails = ref([])
    const searchQuery = ref('')
    const filteredEmails = ref([])

    const breadcrumbText = computed(() => {
      return props.type === 'bounced' ? 'Email Bounced' : 'Email Blocked'
    })

    onMounted(async () => {
      try {
        const data = await api.get(`/api/emails/${props.type}/`)
        emails.value = data.emails
        filteredEmails.value = emails.value
      } catch (error) {
        console.error(`Failed to load ${props.type} emails:`, error)
        alert('Errore nel caricamento delle email')
      } finally {
        loading.value = false
      }
    })

    const filterEmails = () => {
      if (!searchQuery.value) {
        filteredEmails.value = emails.value
        return
      }

      const query = searchQuery.value.toLowerCase()
      filteredEmails.value = emails.value.filter(e =>
        e.recipient_email.toLowerCase().includes(query) ||
        e.message.subject.toLowerCase().includes(query)
      )
    }

    const formatDate = (dateStr) => {
      return new Date(dateStr).toLocaleDateString('it-IT', {
        day: 'numeric',
        month: 'short'
      })
    }

    const formatDateTime = (dateStr) => {
      return new Date(dateStr).toLocaleString('it-IT', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit'
      })
    }

    const statusLabel = (status) => {
      const labels = {
        'bounced': 'Rimbalzata',
        'blocked': 'Bloccata'
      }
      return labels[status] || status
    }

    const openEmailDetail = (emailId) => {
      emailModal.open(emailId)
    }

    return {
      loading,
      searchQuery,
      filteredEmails,
      breadcrumbText,
      filterEmails,
      formatDate,
      formatDateTime,
      statusLabel,
      openEmailDetail
    }
  },

  components: {
    Breadcrumb
  }
}

// ========================================
// Router Setup
// ========================================
const routes = [
  {
    path: '/',
    component: Dashboard
  },
  {
    path: '/messages/:messageId/emails',
    component: MessageEmails
  },
  {
    path: '/emails/bounced',
    component: GlobalEmails,
    props: { type: 'bounced' }
  },
  {
    path: '/emails/blocked',
    component: GlobalEmails,
    props: { type: 'blocked' }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// Make router available globally for components
window.useRoute = () => {
  return router.currentRoute.value
}

// ========================================
// App Setup
// ========================================
const app = createApp({
  components: {
    EmailDetailModal
  }
})

app.use(router)
app.mount('#brevo-app')
```

### Step 4.5: Test SPA

**Access URL:**
```
http://localhost:8000/admin/brevo_analytics/brevomessage/
```

---

## Phase 5: Historical Data Import (1 hour)

### Step 5.1: Create management command

**File:** `brevo_analytics/management/commands/import_brevo_csv.py` (new file)

```python
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
import csv
import uuid
from brevo_analytics.models import BrevoMessage, Email

class Command(BaseCommand):
    help = 'Import historical Brevo data from CSV files'

    def add_arguments(self, parser):
        parser.add_argument('emails_csv', type=str, help='Path to emails_import.csv')
        parser.add_argument('events_csv', type=str, help='Path to email_events_import.csv')

    def handle(self, *args, **options):
        # Import emails
        self.stdout.write("Importing emails...")
        emails_created = 0
        email_id_map = {}  # CSV id -> Django UUID

        with open(options['emails_csv'], 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                csv_id = row['id']
                brevo_message_id = row['brevo_email_id']
                subject = row['subject']
                sent_at = datetime.fromisoformat(row['sent_at'])
                sent_date = sent_at.date()

                # Get or create message
                message, _ = BrevoMessage.objects.get_or_create(
                    subject=subject,
                    sent_date=sent_date
                )

                # Create email
                email, created = Email.objects.get_or_create(
                    brevo_message_id=brevo_message_id,
                    defaults={
                        'message': message,
                        'recipient_email': row['recipient_email'],
                        'sent_at': sent_at,
                        'events': []
                    }
                )

                if created:
                    emails_created += 1
                    email_id_map[csv_id] = str(email.id)

        self.stdout.write(f"✓ Imported {emails_created} emails")

        # Import events
        self.stdout.write("Importing events...")
        events_created = 0

        with open(options['events_csv'], 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                email_csv_id = row['email_id']

                if email_csv_id not in email_id_map:
                    continue

                email_uuid = email_id_map[email_csv_id]

                try:
                    email = Email.objects.get(id=email_uuid)
                except Email.DoesNotExist:
                    continue

                event_type = row['event_type']
                event_timestamp = datetime.fromisoformat(row['event_timestamp'])

                extra_data = {}
                if row.get('bounce_type'):
                    extra_data['bounce_type'] = row['bounce_type']
                if row.get('bounce_reason'):
                    extra_data['bounce_reason'] = row['bounce_reason']
                if row.get('click_url'):
                    extra_data['url'] = row['click_url']

                if email.add_event(event_type, event_timestamp, **extra_data):
                    events_created += 1

        self.stdout.write(f"✓ Imported {events_created} events")

        # Update message stats
        self.stdout.write("Updating message statistics...")
        for message in BrevoMessage.objects.all():
            message.update_stats()

        self.stdout.write(self.style.SUCCESS("✓ Import completed!"))
```

### Step 5.2: Run import

**Command:**
```bash
python manage.py import_brevo_csv emails_import.csv email_events_import.csv
```

---

## Phase 6: Testing & Deployment (1 hour)

### Step 6.1: Run tests

**Create test file:** `brevo_analytics/tests.py`

```python
from django.test import TestCase
from django.utils import timezone
from datetime import datetime
from .models import BrevoMessage, Email

class BrevoModelsTestCase(TestCase):
    def setUp(self):
        self.message = BrevoMessage.objects.create(
            subject="Test Email",
            sent_date=timezone.now().date()
        )

    def test_email_creation(self):
        email = Email.objects.create(
            message=self.message,
            brevo_message_id="<test123@example.com>",
            recipient_email="test@example.com",
            sent_at=timezone.now()
        )
        self.assertEqual(email.current_status, 'sent')

    def test_add_event(self):
        email = Email.objects.create(
            message=self.message,
            brevo_message_id="<test456@example.com>",
            recipient_email="test2@example.com",
            sent_at=timezone.now()
        )

        email.add_event('delivered', timezone.now())
        self.assertEqual(email.current_status, 'delivered')
        self.assertEqual(len(email.events), 1)

    def test_status_hierarchy(self):
        email = Email.objects.create(
            message=self.message,
            brevo_message_id="<test789@example.com>",
            recipient_email="test3@example.com",
            sent_at=timezone.now()
        )

        email.add_event('delivered', timezone.now())
        email.add_event('opened', timezone.now())
        email.add_event('clicked', timezone.now())

        self.assertEqual(email.current_status, 'clicked')
```

**Run tests:**
```bash
python manage.py test brevo_analytics
```

### Step 6.2: Production checklist

- [ ] Set `DEBUG = False` in settings
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Set strong `BREVO_ANALYTICS['WEBHOOK_SECRET']`
- [ ] Configure Brevo webhook URL in dashboard
- [ ] Set up database backups
- [ ] Configure static files serving (collectstatic)
- [ ] Set up SSL/HTTPS
- [ ] Monitor webhook delivery logs

---

## Summary

**Total Implementation Time:** ~12 hours

**Phases:**
1. Models & Migrations: 2 hours
2. Django REST API: 3 hours
3. Brevo Webhook: 1 hour
4. Vue.js SPA: 4 hours
5. Data Import: 1 hour
6. Testing & Deployment: 1 hour

**Key Files Created/Modified:**
- `brevo_analytics/models.py` - Complete rewrite
- `brevo_analytics/serializers.py` - New
- `brevo_analytics/api_views.py` - New
- `brevo_analytics/webhooks.py` - New
- `brevo_analytics/admin.py` - Updated
- `brevo_analytics/urls.py` - Updated
- `brevo_analytics/templates/brevo_analytics/spa.html` - New
- `brevo_analytics/static/brevo_analytics/css/app.css` - New
- `brevo_analytics/static/brevo_analytics/js/app.js` - New
- `brevo_analytics/management/commands/import_brevo_csv.py` - New

**Files Deleted:**
- `brevo_analytics/supabase.py`
- `sql/` directory
- `docs/SUPABASE_SETUP.md`
- `docs/n8n-workflow-design.md`
