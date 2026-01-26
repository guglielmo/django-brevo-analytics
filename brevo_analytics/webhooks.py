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
from .models import BrevoMessage, BrevoEmail

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def brevo_webhook(request):
    """
    Brevo webhook endpoint for real-time event processing.

    Configure in Brevo dashboard:
    URL: https://your-domain.com/brevo-analytics/webhook/
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

    # Map Brevo event name to our event type
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
    is_sent_event = (our_event_type == 'sent')

    # 1. Try to find existing BrevoEmail
    try:
        email = BrevoEmail.objects.select_related('message').get(
            brevo_message_id=message_id,
            recipient_email=email_address
        )
        message = email.message
        email_created = False
        logger.debug(f"Found existing email: {message_id} to {email_address}")
    except BrevoEmail.DoesNotExist:
        email = None
        email_created = True

    # 2. If email doesn't exist and this is NOT a 'sent' event, ignore it
    #    (same logic as bulk import: only emails with 'sent' event are tracked)
    if email is None and not is_sent_event:
        logger.info(
            f"Ignoring {event_type} event for unknown email {message_id} to {email_address} "
            f"(no 'sent' event received yet)"
        )
        return JsonResponse({'status': 'ignored', 'reason': 'no_sent_event'})

    # 3. If this is a 'sent' event and email doesn't exist, create it
    if email is None and is_sent_event:
        # Get or create BrevoMessage (identified by subject + sent_date from 'sent' event)
        message, message_created = BrevoMessage.objects.get_or_create(
            subject=subject,
            sent_date=event_date,
            defaults={
                'total_sent': 0,
            }
        )

        if message_created:
            logger.info(f"Created new message: {subject} - {event_date}")

        # Create BrevoEmail with sent_at from this 'sent' event
        email = BrevoEmail.objects.create(
            brevo_message_id=message_id,
            message=message,
            recipient_email=email_address,
            sent_at=event_datetime,
            current_status='sent',
            events=[]
        )
        logger.info(f"Created new email: {message_id} to {email_address}")

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
