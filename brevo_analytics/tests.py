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

    def test_message_stats_update(self):
        # Create multiple emails for the message
        for i in range(5):
            email = Email.objects.create(
                message=self.message,
                brevo_message_id=f"<test{i}@example.com>",
                recipient_email=f"test{i}@example.com",
                sent_at=timezone.now()
            )
            if i < 3:
                email.add_event('delivered', timezone.now())
            if i < 2:
                email.add_event('opened', timezone.now())

        # Manually update stats after all emails created
        self.message.update_stats()

        # Refresh message from DB
        self.message.refresh_from_db()

        self.assertEqual(self.message.total_sent, 5)
        self.assertEqual(self.message.total_delivered, 3)
        self.assertEqual(self.message.total_opened, 2)
        self.assertEqual(self.message.delivery_rate, 60.0)

    def test_duplicate_event_prevention(self):
        email = Email.objects.create(
            message=self.message,
            brevo_message_id="<testdup@example.com>",
            recipient_email="testdup@example.com",
            sent_at=timezone.now()
        )

        timestamp = timezone.now()
        added1 = email.add_event('delivered', timestamp)
        added2 = email.add_event('delivered', timestamp)

        self.assertTrue(added1)
        self.assertFalse(added2)  # Should not add duplicate
        self.assertEqual(len(email.events), 1)
