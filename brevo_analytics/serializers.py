from django.conf import settings
from rest_framework import serializers
from .models import BrevoMessage, BrevoEmail
from .tracking import is_anonymous_tracking, public_events, public_status, tracking_totals_available

# Campi di BrevoMessage nascosti (None) quando i totali di apertura e clic non
# sono disponibili: in modalità anonima, salvo i totali storici conservati
TRACKING_TOTAL_FIELDS = ('total_opened', 'total_clicked', 'open_rate', 'click_rate')


def _display_subject(raw_subject):
    """Strip tag prefix and ID from subject when in tag grouping mode.

    When MESSAGE_GROUP_BY='tag', subjects look like '{prefix}:{id}:{title}'.
    This returns just the '{title}' portion. In default mode, returns subject unchanged.
    """
    config = getattr(settings, 'BREVO_ANALYTICS', {})
    if config.get('MESSAGE_GROUP_BY') == 'tag':
        prefix = config.get('MESSAGE_TAG_PREFIX', 'digest')
        tag_prefix = f"{prefix}:"
        if raw_subject.startswith(tag_prefix):
            remainder = raw_subject[len(tag_prefix):]
            # Strip the ID portion: "{id}:{display_title}"
            if ':' in remainder:
                return remainder.split(':', 1)[1]
            return remainder
    return raw_subject


class BrevoMessageSerializer(serializers.ModelSerializer):
    """Serializer per lista messaggi"""
    display_subject = serializers.SerializerMethodField()
    # Aperture e clic per destinatario disponibili (filtri "aperte" e "cliccate")
    recipient_tracking = serializers.SerializerMethodField()

    class Meta:
        model = BrevoMessage
        fields = [
            'id', 'subject', 'display_subject', 'sent_date',
            'total_sent', 'total_delivered', 'total_opened',
            'total_clicked', 'total_bounced', 'total_blocked',
            'delivery_rate', 'open_rate', 'click_rate',
            'recipient_tracking', 'updated_at'
        ]

    def get_display_subject(self, obj):
        """Return human-readable subject, stripping tag prefix and ID when in tag grouping mode."""
        return _display_subject(obj.subject)

    def get_recipient_tracking(self, obj):
        return not is_anonymous_tracking()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not tracking_totals_available(instance):
            for field in TRACKING_TOTAL_FIELDS:
                data[field] = None
        return data


class PublicStatusMixin:
    """current_status come lo espongono le API (vedi tracking.public_status)."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['current_status'] = public_status(data['current_status'])
        return data


class BrevoEmailListSerializer(PublicStatusMixin, serializers.ModelSerializer):
    """Serializer per lista email (senza eventi)"""
    class Meta:
        model = BrevoEmail
        fields = [
            'id', 'recipient_email', 'current_status', 'sent_at'
        ]


class BrevoEmailDetailSerializer(PublicStatusMixin, serializers.ModelSerializer):
    """Serializer per dettaglio email (con eventi e messaggio)"""
    message = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()

    class Meta:
        model = BrevoEmail
        fields = [
            'id', 'recipient_email', 'current_status',
            'sent_at', 'events', 'message', 'blacklist_info'
        ]

    def get_events(self, obj):
        return public_events(obj.events)

    def get_message(self, obj):
        return {
            'id': obj.message.id,
            'subject': obj.message.subject,
            'display_subject': _display_subject(obj.message.subject),
            'sent_date': obj.message.sent_date.isoformat()
        }


class MessageBrevoEmailsSerializer(serializers.Serializer):
    """Serializer per risposta /api/messages/:id/emails/"""
    message = BrevoMessageSerializer()
    emails = BrevoEmailListSerializer(many=True)


class GlobalBrevoEmailsSerializer(PublicStatusMixin, serializers.ModelSerializer):
    """Serializer per email globali bounced/blocked (con info messaggio)"""
    message = serializers.SerializerMethodField()

    class Meta:
        model = BrevoEmail
        fields = [
            'id', 'recipient_email', 'current_status',
            'sent_at', 'message'
        ]

    def get_message(self, obj):
        return {
            'subject': obj.message.subject,
            'display_subject': _display_subject(obj.message.subject),
            'sent_date': obj.message.sent_date.isoformat()
        }
