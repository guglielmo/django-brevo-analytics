"""Custom template filters for Brevo Analytics."""
from django import template
from django.utils import timezone
from datetime import datetime, timedelta

register = template.Library()


@register.filter
def format_seconds(seconds):
    """
    Convert seconds to human-readable duration.

    Args:
        seconds: Number of seconds (can be int, float, or string)

    Returns:
        Formatted string like "2h 30m" or "45s"
    """
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "N/A"

    if seconds < 0:
        return "N/A"

    if seconds < 60:
        return f"{int(seconds)}s"

    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"

    hours = int(minutes // 60)
    remaining_minutes = minutes % 60

    if remaining_minutes == 0:
        return f"{hours}h"

    return f"{hours}h {remaining_minutes}m"


@register.filter
def event_icon(event_type):
    """
    Return an emoji icon for the given event type.

    Args:
        event_type: String representing the event type

    Returns:
        Emoji string
    """
    icons = {
        'delivered': '✅',
        'opened': '👁️',
        'clicked': '🖱️',
        'soft_bounce': '⚠️',
        'hard_bounce': '❌',
        'spam': '🚫',
        'blocked': '🛑',
        'unsubscribed': '📭',
        'error': '⚠️',
        'deferred': '⏸️',
        'complaint': '🚨',
    }

    if not event_type:
        return '📧'

    return icons.get(str(event_type).lower(), '📧')


@register.filter
def status_color(status):
    """
    Return a CSS class for styling based on status.

    Args:
        status: String representing the status

    Returns:
        CSS class string
    """
    color_map = {
        'delivered': 'text-green-600 bg-green-100',
        'opened': 'text-blue-600 bg-blue-100',
        'clicked': 'text-purple-600 bg-purple-100',
        'soft_bounce': 'text-yellow-600 bg-yellow-100',
        'hard_bounce': 'text-red-600 bg-red-100',
        'spam': 'text-red-700 bg-red-200',
        'blocked': 'text-red-800 bg-red-200',
        'unsubscribed': 'text-gray-600 bg-gray-100',
        'error': 'text-orange-600 bg-orange-100',
        'deferred': 'text-yellow-500 bg-yellow-50',
        'complaint': 'text-red-900 bg-red-300',
    }

    if not status:
        return 'text-gray-500 bg-gray-50'

    return color_map.get(str(status).lower(), 'text-gray-500 bg-gray-50')


@register.filter
def time_since_sent(sent_time):
    """
    Calculate time elapsed since email was sent.

    Args:
        sent_time: datetime object or ISO format string

    Returns:
        Human-readable string like "2 hours ago" or "3 days ago"
    """
    if not sent_time:
        return "N/A"

    # Convert string to datetime if needed
    if isinstance(sent_time, str):
        try:
            sent_time = datetime.fromisoformat(sent_time.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return "N/A"

    # Make sure we have a timezone-aware datetime
    if sent_time.tzinfo is None:
        sent_time = timezone.make_aware(sent_time)

    now = timezone.now()
    delta = now - sent_time

    # Handle future dates
    if delta.total_seconds() < 0:
        return "just now"

    seconds = int(delta.total_seconds())

    if seconds < 60:
        return f"{seconds}s ago"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"

    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"

    days = hours // 24
    if days < 7:
        return f"{days}d ago"

    weeks = days // 7
    if weeks < 4:
        return f"{weeks}w ago"

    months = days // 30
    if months < 12:
        return f"{months}mo ago"

    years = days // 365
    return f"{years}y ago"
