# Django-Native Refactoring Plan
**Date:** 2026-01-21
**Status:** Planning

## Overview

Complete architectural refactoring to remove Supabase dependency and use native Django models with direct database storage. This simplifies the architecture, reduces costs, and enables real-time webhook integration.

## Key Changes

### Architecture Before (Supabase-based)
```
Brevo API → n8n → Supabase → PostgREST API → Django Views → Templates
                    ↓
                 RLS Policies (multi-tenant)
                 JWT Authentication
                 Cache Layer
```

### Architecture After (Django-native)
```
Brevo Webhooks → Django Webhook Endpoint → Django Models → Django Views → Templates
                                              ↓
                                         ORM Queries
                                         Direct Database Access
```

## Benefits

1. **Simplicity**: No external API, no JWT, no RLS, no n8n
2. **Cost**: Zero Supabase costs
3. **Performance**: Direct database queries via Django ORM
4. **Real-time**: Brevo webhooks deliver events instantly
5. **Isolation**: Each Django instance has its own database
6. **Development**: Standard Django patterns, easier to maintain

## Implementation Plan

### Phase 1: New Django Models (managed=True)

**File:** `brevo_analytics/models.py`

```python
from django.db import models

class Email(models.Model):
    """Transactional email sent via Brevo"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    brevo_message_id = models.CharField(max_length=255, unique=True, db_index=True)
    recipient_email = models.EmailField(db_index=True)
    subject = models.TextField(blank=True)
    sent_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'brevo_emails'
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['-sent_at']),
            models.Index(fields=['recipient_email']),
        ]

    def __str__(self):
        return f"{self.recipient_email} - {self.subject[:50]}"

    @property
    def current_status(self):
        """Calculate current status from events"""
        events = self.events.values_list('event_type', flat=True)

        if 'clicked' in events:
            return 'clicked'
        elif 'opened' in events:
            return 'opened'
        elif 'delivered' in events:
            return 'delivered'
        elif 'bounced' in events:
            return 'bounced'
        elif 'blocked' in events:
            return 'blocked'
        elif 'deferred' in events:
            return 'deferred'
        elif 'unsubscribed' in events:
            return 'unsubscribed'
        else:
            return 'sent'


class EmailEvent(models.Model):
    """Events for each email (delivered, opened, clicked, etc.)"""
    EVENT_TYPES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('opened', 'Opened'),
        ('clicked', 'Clicked'),
        ('bounced', 'Bounced'),
        ('blocked', 'Blocked'),
        ('deferred', 'Deferred'),
        ('unsubscribed', 'Unsubscribed'),
        ('spam', 'Spam'),
    ]

    BOUNCE_TYPES = [
        ('hard', 'Hard Bounce'),
        ('soft', 'Soft Bounce'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    email = models.ForeignKey(Email, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, db_index=True)
    event_timestamp = models.DateTimeField(db_index=True)

    # Bounce information
    bounce_type = models.CharField(max_length=10, choices=BOUNCE_TYPES, null=True, blank=True)
    bounce_reason = models.TextField(null=True, blank=True)

    # Link click information
    click_url = models.URLField(null=True, blank=True, max_length=2000)

    # Raw webhook payload
    raw_data = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'brevo_email_events'
        ordering = ['event_timestamp']
        indexes = [
            models.Index(fields=['email', 'event_timestamp']),
            models.Index(fields=['event_type']),
        ]

    def __str__(self):
        return f"{self.email.recipient_email} - {self.event_type} - {self.event_timestamp}"
```

**Migrations:**
```bash
python manage.py makemigrations brevo_analytics
python manage.py migrate brevo_analytics
```

### Phase 2: Configuration

**File:** `settings.py`

```python
BREVO_ANALYTICS = {
    'API_KEY': 'xkeysib-...',  # For historical data import (optional)
    'CLIENT_UID': 'your-client-uuid',  # For tracking/reporting only
    'WEBHOOK_SECRET': 'your-webhook-secret',  # For webhook validation
    'RETENTION_DAYS': 60,  # Optional: auto-delete old data
}
```

### Phase 3: Webhook Endpoint

**File:** `brevo_analytics/webhooks.py`

```python
import hmac
import hashlib
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from .models import Email, EmailEvent

@csrf_exempt
@require_POST
def brevo_webhook(request):
    """
    Brevo webhook endpoint for real-time event processing.

    URL to configure in Brevo dashboard:
    https://your-domain.com/admin/brevo-analytics/webhook/

    Events: sent, delivered, opened, clicked, bounced, blocked, etc.
    """
    # Verify webhook signature
    config = getattr(settings, 'BREVO_ANALYTICS', {})
    webhook_secret = config.get('WEBHOOK_SECRET')

    if webhook_secret:
        signature = request.headers.get('X-Brevo-Signature')
        computed_signature = hmac.new(
            webhook_secret.encode(),
            request.body,
            hashlib.sha256
        ).hexdigest()

        if signature != computed_signature:
            return HttpResponseBadRequest('Invalid signature')

    # Parse webhook payload
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid JSON')

    event_type = payload.get('event')
    message_id = payload.get('message-id')
    email_address = payload.get('email')
    timestamp = payload.get('ts_event')  # Unix timestamp

    if not all([event_type, message_id, email_address, timestamp]):
        return HttpResponseBadRequest('Missing required fields')

    # Convert timestamp
    event_datetime = datetime.fromtimestamp(timestamp, tz=timezone.utc)

    # Get or create email record
    email, created = Email.objects.get_or_create(
        brevo_message_id=message_id,
        defaults={
            'recipient_email': email_address,
            'subject': payload.get('subject', ''),
            'sent_at': event_datetime if event_type == 'request' else timezone.now(),
        }
    )

    # Map Brevo event names to our event types
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

    # Create event record (avoid duplicates)
    event_data = {
        'email': email,
        'event_type': our_event_type,
        'event_timestamp': event_datetime,
        'raw_data': payload,
    }

    # Add bounce information
    if 'hard_bounce' in event_type or 'soft_bounce' in event_type:
        event_data['bounce_type'] = 'hard' if 'hard' in event_type else 'soft'
        event_data['bounce_reason'] = payload.get('reason', '')

    # Add click URL
    if event_type == 'click':
        event_data['click_url'] = payload.get('link', '')

    # Check for duplicate events (same email + event_type + timestamp)
    if not EmailEvent.objects.filter(
        email=email,
        event_type=our_event_type,
        event_timestamp=event_datetime
    ).exists():
        EmailEvent.objects.create(**event_data)

    return JsonResponse({'status': 'ok'})
```

**URL Configuration:**

**File:** `brevo_analytics/urls.py`

```python
from django.urls import path
from . import webhooks

urlpatterns = [
    path('webhook/', webhooks.brevo_webhook, name='brevo_webhook'),
]
```

### Phase 4: Simplified Views with Django ORM

**File:** `brevo_analytics/views.py`

```python
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q, Avg, F, ExpressionWrapper, DurationField
from django.utils import timezone
from datetime import timedelta
from .models import Email, EmailEvent

@staff_member_required
def dashboard_view(request):
    """Dashboard with email delivery statistics"""
    date_range = request.GET.get('range', '7d')

    # Calculate date filter
    range_map = {
        '24h': timedelta(hours=24),
        '7d': timedelta(days=7),
        '30d': timedelta(days=30),
    }
    from_date = timezone.now() - range_map.get(date_range, timedelta(days=7))

    # Get all emails in range
    emails = Email.objects.filter(sent_at__gte=from_date)
    total_sent = emails.count()

    if total_sent == 0:
        stats = {
            'total_sent': 0,
            'delivery_rate': 0.0,
            'bounce_rate': 0.0,
            'open_rate': 0.0,
            'click_rate': 0.0,
        }
    else:
        # Count emails by status using subqueries
        delivered = emails.filter(events__event_type='delivered').distinct().count()
        bounced = emails.filter(events__event_type='bounced').distinct().count()
        opened = emails.filter(events__event_type='opened').distinct().count()
        clicked = emails.filter(events__event_type='clicked').distinct().count()

        stats = {
            'total_sent': total_sent,
            'delivery_rate': (delivered / total_sent * 100) if total_sent > 0 else 0.0,
            'bounce_rate': (bounced / total_sent * 100) if total_sent > 0 else 0.0,
            'open_rate': (opened / delivered * 100) if delivered > 0 else 0.0,
            'click_rate': (clicked / delivered * 100) if delivered > 0 else 0.0,
        }

    context = {
        'title': 'Brevo Analytics Dashboard',
        'date_range': date_range,
        'stats': stats,
    }

    return render(request, 'admin/brevo_analytics/dashboard.html', context)


@staff_member_required
def email_list_view(request):
    """List all emails with filters"""
    date_range = request.GET.get('range', '7d')
    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')

    # Calculate date filter
    range_map = {
        '24h': timedelta(hours=24),
        '7d': timedelta(days=7),
        '30d': timedelta(days=30),
    }
    from_date = timezone.now() - range_map.get(date_range, timedelta(days=7))

    # Base query
    emails = Email.objects.filter(sent_at__gte=from_date).prefetch_related('events')

    # Apply search
    if search:
        emails = emails.filter(
            Q(recipient_email__icontains=search) |
            Q(subject__icontains=search)
        )

    # Apply status filter
    if status_filter != 'all':
        emails = emails.filter(events__event_type=status_filter).distinct()

    # Add current_status annotation using property (computed in Python)
    # For better performance, could denormalize this into Email model
    emails_list = list(emails)

    context = {
        'title': 'Email List',
        'date_range': date_range,
        'search': search,
        'status_filter': status_filter,
        'emails': emails_list,
        'total': len(emails_list),
    }

    return render(request, 'admin/brevo_analytics/email_list.html', context)


@staff_member_required
def email_detail_view(request, email_id):
    """Detail view for single email with event timeline"""
    email = get_object_or_404(Email, pk=email_id)
    events = email.events.all().order_by('event_timestamp')

    context = {
        'title': f'Email: {email.recipient_email}',
        'email': email,
        'events': events,
    }

    return render(request, 'admin/brevo_analytics/email_detail.html', context)
```

### Phase 5: Historical Data Import

**File:** `brevo_analytics/management/commands/import_brevo_data.py`

```python
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
import csv
from brevo_analytics.models import Email, EmailEvent

class Command(BaseCommand):
    help = 'Import historical Brevo data from CSV files'

    def add_arguments(self, parser):
        parser.add_argument('emails_csv', type=str, help='Path to emails CSV')
        parser.add_argument('events_csv', type=str, help='Path to events CSV')

    def handle(self, *args, **options):
        # Import emails
        with open(options['emails_csv'], 'r') as f:
            reader = csv.DictReader(f)
            emails_created = 0
            for row in reader:
                email, created = Email.objects.get_or_create(
                    brevo_message_id=row['brevo_email_id'],
                    defaults={
                        'recipient_email': row['recipient_email'],
                        'subject': row['subject'],
                        'sent_at': datetime.fromisoformat(row['sent_at']),
                    }
                )
                if created:
                    emails_created += 1

        self.stdout.write(f"Imported {emails_created} emails")

        # Import events
        with open(options['events_csv'], 'r') as f:
            reader = csv.DictReader(f)
            events_created = 0
            for row in reader:
                try:
                    email = Email.objects.get(id=row['email_id'])
                    event, created = EmailEvent.objects.get_or_create(
                        email=email,
                        event_type=row['event_type'],
                        event_timestamp=datetime.fromisoformat(row['event_timestamp']),
                        defaults={
                            'bounce_type': row.get('bounce_type') or None,
                            'bounce_reason': row.get('bounce_reason') or None,
                            'click_url': row.get('click_url') or None,
                        }
                    )
                    if created:
                        events_created += 1
                except Email.DoesNotExist:
                    self.stderr.write(f"Email not found: {row['email_id']}")

        self.stdout.write(f"Imported {events_created} events")
```

### Phase 6: Performance Optimization

**Option A: Denormalize current_status**

Add `current_status` field to Email model and update via signals:

```python
# In models.py
class Email(models.Model):
    # ... existing fields ...
    current_status = models.CharField(max_length=20, default='sent', db_index=True)

    def update_status(self):
        """Update current_status based on events"""
        events = self.events.values_list('event_type', flat=True)

        if 'clicked' in events:
            self.current_status = 'clicked'
        elif 'opened' in events:
            self.current_status = 'opened'
        elif 'delivered' in events:
            self.current_status = 'delivered'
        elif 'bounced' in events:
            self.current_status = 'bounced'
        elif 'blocked' in events:
            self.current_status = 'blocked'
        elif 'deferred' in events:
            self.current_status = 'deferred'
        elif 'unsubscribed' in events:
            self.current_status = 'unsubscribed'
        else:
            self.current_status = 'sent'

        self.save(update_fields=['current_status'])

# In webhooks.py, after creating event:
email.update_status()
```

**Option B: Database View (PostgreSQL)**

Create a materialized view for fast status calculation:

```sql
CREATE MATERIALIZED VIEW brevo_emails_with_status AS
SELECT
  e.*,
  CASE
    WHEN MAX(CASE WHEN ev.event_type = 'clicked' THEN 1 ELSE 0 END) = 1 THEN 'clicked'
    WHEN MAX(CASE WHEN ev.event_type = 'opened' THEN 1 ELSE 0 END) = 1 THEN 'opened'
    WHEN MAX(CASE WHEN ev.event_type = 'delivered' THEN 1 ELSE 0 END) = 1 THEN 'delivered'
    WHEN MAX(CASE WHEN ev.event_type = 'bounced' THEN 1 ELSE 0 END) = 1 THEN 'bounced'
    WHEN MAX(CASE WHEN ev.event_type = 'blocked' THEN 1 ELSE 0 END) = 1 THEN 'blocked'
    WHEN MAX(CASE WHEN ev.event_type = 'deferred' THEN 1 ELSE 0 END) = 1 THEN 'deferred'
    WHEN MAX(CASE WHEN ev.event_type = 'unsubscribed' THEN 1 ELSE 0 END) = 1 THEN 'unsubscribed'
    ELSE 'sent'
  END AS current_status
FROM brevo_emails e
LEFT JOIN brevo_email_events ev ON ev.email_id = e.id
GROUP BY e.id;

-- Refresh periodically
REFRESH MATERIALIZED VIEW brevo_emails_with_status;
```

### Phase 7: Admin Integration

**File:** `brevo_analytics/admin.py`

```python
from django.contrib import admin
from django.urls import path, reverse
from django.shortcuts import redirect
from django.utils.html import format_html
from .models import Email, EmailEvent
from . import views

class EmailEventInline(admin.TabularInline):
    model = EmailEvent
    extra = 0
    readonly_fields = ['event_type', 'event_timestamp', 'bounce_type', 'bounce_reason', 'click_url']
    can_delete = False

@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ['recipient_email', 'subject_short', 'sent_at', 'status_badge']
    list_filter = ['sent_at']
    search_fields = ['recipient_email', 'subject', 'brevo_message_id']
    readonly_fields = ['brevo_message_id', 'sent_at', 'created_at', 'updated_at']
    inlines = [EmailEventInline]

    def subject_short(self, obj):
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    subject_short.short_description = 'Subject'

    def status_badge(self, obj):
        status = obj.current_status
        colors = {
            'sent': 'gray',
            'delivered': 'green',
            'opened': 'blue',
            'clicked': 'orange',
            'bounced': 'red',
            'blocked': 'darkred',
            'deferred': 'yellow',
            'unsubscribed': 'gray',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            colors.get(status, 'gray'),
            status.upper()
        )
    status_badge.short_description = 'Status'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_site.admin_view(views.dashboard_view), name='brevo_analytics_dashboard'),
            path('emails/', self.admin_site.admin_view(views.email_list_view), name='brevo_analytics_email_list'),
            path('emails/<uuid:email_id>/', self.admin_site.admin_view(views.email_detail_view), name='brevo_analytics_email_detail'),
        ]
        return custom_urls + urls

@admin.register(EmailEvent)
class EmailEventAdmin(admin.ModelAdmin):
    list_display = ['email', 'event_type', 'event_timestamp']
    list_filter = ['event_type', 'event_timestamp']
    readonly_fields = ['email', 'event_type', 'event_timestamp', 'raw_data']
```

## Migration Strategy

### Step 1: Create new models
```bash
python manage.py makemigrations brevo_analytics
python manage.py migrate brevo_analytics
```

### Step 2: Import historical data
```bash
python manage.py import_brevo_data emails_import.csv email_events_import.csv
```

### Step 3: Configure Brevo webhook
1. Go to Brevo Dashboard → Transactional → Settings → Webhooks
2. Add webhook URL: `https://your-domain.com/admin/brevo-analytics/webhook/`
3. Select events: sent, delivered, opened, clicked, bounced, blocked, etc.
4. Save webhook secret in settings.py

### Step 4: Test webhook
```bash
curl -X POST https://your-domain.com/admin/brevo-analytics/webhook/ \
  -H "Content-Type: application/json" \
  -d '{"event":"delivered","message-id":"test123","email":"test@example.com","ts_event":1234567890}'
```

### Step 5: Remove old code
- Delete `brevo_analytics/supabase.py`
- Delete all SQL migration files in `sql/`
- Update documentation

## Files to Remove

- `sql/` directory (entire)
- `brevo_analytics/supabase.py`
- `brevo_analytics/exceptions.py` (SupabaseAPIError)
- `docs/SUPABASE_SETUP.md`
- `docs/n8n-workflow-design.md`

## Files to Update

- `brevo_analytics/models.py` - Complete rewrite
- `brevo_analytics/views.py` - Use Django ORM
- `brevo_analytics/admin.py` - Register models
- `brevo_analytics/urls.py` - Add webhook endpoint
- `README.md` - Update installation instructions
- `docs/INSTALLATION.md` - Simplify setup

## Testing Plan

1. **Unit Tests**: Model methods and webhook parsing
2. **Integration Tests**: Webhook → Model creation flow
3. **Performance Tests**: Query performance with 10k+ emails
4. **Manual Tests**:
   - Send test email via Brevo
   - Verify webhook received
   - Check email appears in dashboard
   - Verify events appear in timeline

## Rollout Checklist

- [ ] Create new models
- [ ] Run migrations
- [ ] Create webhook endpoint
- [ ] Update views to use ORM
- [ ] Update templates (minimal changes)
- [ ] Import historical data
- [ ] Configure Brevo webhook
- [ ] Test webhook with real event
- [ ] Update documentation
- [ ] Remove old Supabase code
- [ ] Deploy to production

## Estimated Timeline

- **Phase 1-2**: 2 hours (Models + Configuration)
- **Phase 3**: 1 hour (Webhook endpoint)
- **Phase 4**: 1 hour (Views with ORM)
- **Phase 5**: 30 minutes (Import command)
- **Phase 6**: 1 hour (Performance optimization)
- **Phase 7**: 30 minutes (Admin integration)
- **Testing**: 1 hour
- **Documentation**: 1 hour

**Total**: ~8 hours

## Post-Implementation

### Monitoring
- Monitor webhook delivery rate
- Set up alerts for webhook failures
- Track database growth
- Monitor query performance

### Maintenance
- Implement data retention policy (auto-delete old emails)
- Regular database vacuum/analyze
- Monitor bounce rates
- Export reports

### Future Enhancements
- Email templates tracking
- Campaign grouping
- A/B testing support
- Advanced analytics (by time of day, day of week, etc.)
