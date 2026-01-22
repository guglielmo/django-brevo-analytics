from rest_framework import serializers
from .models import BrevoMessage, BrevoEmail


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


class BrevoEmailListSerializer(serializers.ModelSerializer):
    """Serializer per lista email (senza eventi)"""
    class Meta:
        model = BrevoEmail
        fields = [
            'id', 'recipient_email', 'current_status', 'sent_at'
        ]


class BrevoEmailDetailSerializer(serializers.ModelSerializer):
    """Serializer per dettaglio email (con eventi e messaggio)"""
    message = serializers.SerializerMethodField()

    class Meta:
        model = BrevoEmail
        fields = [
            'id', 'recipient_email', 'current_status',
            'sent_at', 'events', 'message', 'blacklist_info'
        ]

    def get_message(self, obj):
        return {
            'id': obj.message.id,
            'subject': obj.message.subject,
            'sent_date': obj.message.sent_date.isoformat()
        }


class MessageBrevoEmailsSerializer(serializers.Serializer):
    """Serializer per risposta /api/messages/:id/emails/"""
    message = BrevoMessageSerializer()
    emails = BrevoEmailListSerializer(many=True)


class GlobalBrevoEmailsSerializer(serializers.ModelSerializer):
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
            'sent_date': obj.message.sent_date.isoformat()
        }
