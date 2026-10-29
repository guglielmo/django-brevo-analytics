import json
import threading
import time
from unittest import mock, skipUnless

from django.core.exceptions import ImproperlyConfigured
from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.core.management import call_command
from datetime import datetime
from io import StringIO
from .models import BrevoMessage, BrevoEmail
from .stats import recalculate_message_stats
from .sender_utils import (
    get_allowed_senders,
    is_sender_allowed,
    build_sender_filter_q,
    build_sender_sql_clause,
)

class BrevoModelsTestCase(TestCase):
    def setUp(self):
        self.message = BrevoMessage.objects.create(
            subject="Test Email",
            sent_date=timezone.now().date()
        )

    def test_email_creation(self):
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<test123@example.com>",
            recipient_email="test@example.com",
            sent_at=timezone.now()
        )
        self.assertEqual(email.current_status, 'sent')

    def test_add_event(self):
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<test456@example.com>",
            recipient_email="test2@example.com",
            sent_at=timezone.now()
        )

        email.add_event('delivered', timezone.now())
        self.assertEqual(email.current_status, 'delivered')
        self.assertEqual(len(email.events), 1)

    def test_status_hierarchy(self):
        email = BrevoEmail.objects.create(
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
            email = BrevoEmail.objects.create(
                message=self.message,
                brevo_message_id=f"<test{i}@example.com>",
                recipient_email=f"test{i}@example.com",
                sent_at=timezone.now()
            )
            # Add 'sent' event first (required for total_sent count)
            email.add_event('sent', timezone.now())
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
        email = BrevoEmail.objects.create(
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

    def test_email_tags_default(self):
        """BrevoEmail.tags should default to an empty list"""
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<test_tags@example.com>",
            recipient_email="tags@example.com",
            sent_at=timezone.now()
        )
        self.assertIsInstance(email.tags, list)
        self.assertEqual(email.tags, [])

    def test_email_tags_stored(self):
        """BrevoEmail.tags should store and retrieve tag arrays"""
        tags = ["digest:42:Esito CDM 2024-09-17", "customer:15:Acme Corp"]
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<test_tags2@example.com>",
            recipient_email="tags2@example.com",
            sent_at=timezone.now(),
            tags=tags
        )
        email.refresh_from_db()
        self.assertEqual(email.tags, tags)


class ClickUrlTestCase(TestCase):
    """Link dei click (#17): `url` dal webhook, `link` (e ora anche `url`) dall'import."""

    def setUp(self):
        self.message = BrevoMessage.objects.create(subject="Click", sent_date=timezone.now().date())
        self.email = BrevoEmail.objects.create(
            message=self.message, brevo_message_id="<click@example.com>",
            recipient_email="click@example.com", sent_at=timezone.now(),
        )

    def test_clicks_on_different_links_in_the_same_second_are_kept(self):
        ts = timezone.now()
        self.assertTrue(self.email.add_event('clicked', ts, url='https://a.example.com'))
        self.assertTrue(self.email.add_event('clicked', ts, url='https://b.example.com'))
        self.assertEqual([e['url'] for e in self.email.events], ['https://a.example.com', 'https://b.example.com'])

    def test_click_resent_by_brevo_is_still_a_duplicate(self):
        ts = timezone.now()
        self.assertTrue(self.email.add_event('clicked', ts, url='https://a.example.com'))
        self.assertFalse(self.email.add_event('clicked', ts, url='https://a.example.com'))
        self.assertEqual(len(self.email.events), 1)

    def test_imported_link_and_webhook_url_are_the_same_click(self):
        ts = timezone.now()
        self.email.events = [{'type': 'clicked', 'timestamp': ts.isoformat(), 'link': 'https://a.example.com'}]
        self.email.save()
        self.assertFalse(self.email.add_event('clicked', ts, url='https://a.example.com'))

    def test_other_events_in_the_same_second_are_still_duplicates(self):
        ts = timezone.now()
        self.assertTrue(self.email.add_event('delivered', ts))
        self.assertFalse(self.email.add_event('delivered', ts, reported_email='other@example.com'))

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'ANONYMOUS_TRACKING': False,
    })
    def test_webhook_click_keeps_url(self):
        """Il webhook continua a salvare il link in `url`: lo leggono i progetti che usano il pacchetto."""
        base = {
            'message-id': '<webhook-click@example.com>', 'email': 'r@example.com',
            'subject': 'Newsletter', 'sender': 'noreply@example.com',
        }
        for extra in ({'event': 'request'}, {'event': 'click', 'link': 'https://a.example.com'}):
            response = self.client.post(
                '/brevo-analytics/webhook/',
                data=json.dumps({**base, **extra, 'ts_event': int(time.time())}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200)
        email = BrevoEmail.objects.get(brevo_message_id='<webhook-click@example.com>')
        click = [e for e in email.events if e['type'] == 'clicked'][0]
        self.assertEqual(click['url'], 'https://a.example.com')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'ANONYMOUS_TRACKING': False,
    })
    def test_import_writes_url_and_keeps_link(self):
        import csv
        import os
        import tempfile
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='')
        writer = csv.DictWriter(f, fieldnames=['st_text', 'ts', 'sub', 'frm', 'email', 'tag', 'mid', 'link'])
        writer.writeheader()
        row = {'sub': 'Newsletter', 'frm': 'noreply@example.com', 'email': 'r@example.com',
               'tag': '', 'mid': '<import-click@example.com>'}
        writer.writerow({**row, 'st_text': 'Inviata', 'ts': '17-09-2024 10:00:00', 'link': ''})
        writer.writerow({**row, 'st_text': 'Cliccata', 'ts': '17-09-2024 10:05:00', 'link': 'https://a.example.com'})
        f.close()
        try:
            call_command('import_brevo_logs', f.name, stdout=StringIO())
        finally:
            os.unlink(f.name)
        email = BrevoEmail.objects.get(brevo_message_id='import-click@example.com')
        click = [e for e in email.events if e['type'] == 'clicked'][0]
        self.assertEqual(click['url'], 'https://a.example.com')
        self.assertEqual(click['link'], 'https://a.example.com')


class BlacklistOnlyModeTestCase(TestCase):
    """Tests for BLACKLIST_ONLY_MODE configuration flag"""

    @override_settings(BREVO_ANALYTICS={'BLACKLIST_ONLY_MODE': True})
    def test_webhook_disabled_in_blacklist_only_mode(self):
        """Webhook should return 404 with message in blacklist-only mode"""
        # Webhook is @csrf_exempt so no CSRF token needed
        response = self.client.post(
            '/brevo-analytics/webhook/',
            data='{"event": "delivered", "email": "test@example.com"}',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data['status'], 'disabled')
        self.assertIn('BLACKLIST_ONLY_MODE', data['message'])

    @override_settings(BREVO_ANALYTICS={'BLACKLIST_ONLY_MODE': True})
    def test_import_disabled_in_blacklist_only_mode(self):
        """Import command should exit with error in blacklist-only mode"""
        out = StringIO()
        call_command('import_brevo_logs', 'test.csv', stdout=out)
        output = out.getvalue()
        self.assertIn('disabled', output.lower())
        self.assertIn('BLACKLIST_ONLY_MODE', output)

    @override_settings(BREVO_ANALYTICS={'BLACKLIST_ONLY_MODE': False})
    def test_webhook_enabled_when_mode_disabled(self):
        """Webhook should work normally when blacklist-only mode is disabled"""
        # Webhook is @csrf_exempt so no CSRF token needed
        # This should not return 404 (will fail for other reasons like missing fields, but not 404)
        response = self.client.post(
            '/brevo-analytics/webhook/',
            data='{}',
            content_type='application/json'
        )
        # Should get 400 (bad request) not 404 (disabled)
        self.assertNotEqual(response.status_code, 404)


class WebhookTagTestCase(TestCase):
    """Tests for tag extraction, storage, and tag-based grouping in webhook"""

    def _post_webhook(self, payload):
        """Helper to post a webhook payload"""
        return self.client.post(
            '/brevo-analytics/webhook/',
            data=json.dumps(payload),
            content_type='application/json'
        )

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_saves_tags_on_email(self):
        """Webhook should save tags from payload onto BrevoEmail.tags"""
        payload = {
            'event': 'request',
            'message-id': '<tag-test-001@example.com>',
            'email': 'recipient@example.com',
            'subject': 'Esito CDM 2024-09-17 - Acme Corp',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:42:Esito CDM 2024-09-17', 'customer:15:Acme Corp'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-test-001@example.com>',
            recipient_email='recipient@example.com'
        )
        self.assertEqual(email.tags, ['digest:42:Esito CDM 2024-09-17', 'customer:15:Acme Corp'])

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_saves_empty_tags_when_absent(self):
        """Webhook should save empty list when no tags in payload"""
        payload = {
            'event': 'request',
            'message-id': '<tag-test-002@example.com>',
            'email': 'recipient2@example.com',
            'subject': 'No tags email',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-test-002@example.com>',
            recipient_email='recipient2@example.com'
        )
        self.assertEqual(email.tags, [])

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_grouping_uses_tag_as_subject(self):
        """When MESSAGE_GROUP_BY='tag', matching tag should be used as BrevoMessage.subject"""
        payload = {
            'event': 'request',
            'message-id': '<tag-group-001@example.com>',
            'email': 'client1@example.com',
            'subject': 'Esito CDM 2024-09-17 - Acme Corp',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:42:Esito CDM 2024-09-17', 'customer:15:Acme Corp'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-group-001@example.com>',
            recipient_email='client1@example.com'
        )
        self.assertEqual(email.message.subject, 'Esito CDM 2024-09-17')
        self.assertEqual(email.message.group_key, 'digest:42')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_grouping_aggregates_recipients(self):
        """Multiple recipients with same tag should share one BrevoMessage"""
        ts = int(time.time())

        for i, client_name in enumerate(['Acme Corp', 'Beta Ltd', 'Gamma Inc']):
            payload = {
                'event': 'request',
                'message-id': f'<tag-agg-{i:03d}@example.com>',
                'email': f'client{i}@example.com',
                'subject': f'Esito CDM 2024-09-17 - {client_name}',
                'ts_event': ts,
                'sender': 'noreply@example.com',
                'tags': ['digest:42:Esito CDM 2024-09-17', f'customer:{i}:{client_name}'],
            }
            self._post_webhook(payload)

        messages = BrevoMessage.objects.filter(group_key='digest:42')
        self.assertEqual(messages.count(), 1)
        msg = messages.first()
        self.assertEqual(msg.subject, 'Esito CDM 2024-09-17')
        self.assertEqual(msg.emails.count(), 3)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_grouping_fallback_to_subject(self):
        """When no tag matches the prefix, fall back to email subject"""
        payload = {
            'event': 'request',
            'message-id': '<tag-fallback-001@example.com>',
            'email': 'nontag@example.com',
            'subject': 'Password reset',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['transactional:password_reset'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-fallback-001@example.com>',
            recipient_email='nontag@example.com'
        )
        self.assertEqual(email.message.subject, 'Password reset')
        self.assertIsNone(email.message.group_key)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_default_subject_grouping_unchanged(self):
        """Default behaviour (no MESSAGE_GROUP_BY) should use email subject"""
        payload = {
            'event': 'request',
            'message-id': '<default-group-001@example.com>',
            'email': 'default@example.com',
            'subject': 'Esito CDM 2024-09-17 - Acme Corp',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:42:Esito CDM 2024-09-17'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<default-group-001@example.com>',
            recipient_email='default@example.com'
        )
        self.assertEqual(email.message.subject, 'Esito CDM 2024-09-17 - Acme Corp')
        self.assertIsNone(email.message.group_key)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_subject_with_colons(self):
        """Tag extraction should handle colons in the subject correctly"""
        payload = {
            'event': 'request',
            'message-id': '<tag-colon-001@example.com>',
            'email': 'colon@example.com',
            'subject': 'Esito CDM: riunione del 18 febbraio - Acme',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:42:Esito CDM: riunione del 18 febbraio', 'customer:15:Acme'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-colon-001@example.com>',
            recipient_email='colon@example.com'
        )
        self.assertEqual(email.message.subject, 'Esito CDM: riunione del 18 febbraio')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_without_id(self):
        """Tag with prefix but no id:subject structure should use remainder as subject"""
        payload = {
            'event': 'request',
            'message-id': '<tag-noid-001@example.com>',
            'email': 'noid@example.com',
            'subject': 'Some email subject',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:Standalone title'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-noid-001@example.com>',
            recipient_email='noid@example.com'
        )
        # No colon after prefix removal → uses the remainder as-is
        self.assertEqual(email.message.subject, 'Standalone title')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_grouping_subject_changes_between_sends(self):
        """Same digest ID with different titles should share one BrevoMessage with updated subject"""
        ts = int(time.time())

        # Primo invio: titolo originale
        payload1 = {
            'event': 'request',
            'message-id': '<title-change-001@example.com>',
            'email': 'client1@example.com',
            'subject': 'Esito CdM n.166 | DL FISCALE - Acme',
            'ts_event': ts,
            'sender': 'noreply@example.com',
            'tags': ['digest:747:Esito CdM n.166 | DL FISCALE', 'customer:1:Acme'],
        }
        self._post_webhook(payload1)

        # Editor modifica title_for_email, secondo invio con titolo diverso
        payload2 = {
            'event': 'request',
            'message-id': '<title-change-002@example.com>',
            'email': 'client2@example.com',
            'subject': 'Esito CdM | Venerdì 27 marzo 2026 - Beta',
            'ts_event': ts,
            'sender': 'noreply@example.com',
            'tags': ['digest:747:Esito CdM | Venerdì 27 marzo 2026', 'customer:2:Beta'],
        }
        self._post_webhook(payload2)

        # Devono essere raggruppati in un solo BrevoMessage
        messages = BrevoMessage.objects.filter(group_key='digest:747')
        self.assertEqual(messages.count(), 1)
        msg = messages.first()
        # Subject aggiornato all'ultimo titolo ricevuto
        self.assertEqual(msg.subject, 'Esito CdM | Venerdì 27 marzo 2026')
        self.assertEqual(msg.emails.count(), 2)


class WebhookNormalizedRecipientTestCase(TestCase):
    """
    Tests for issue #11: events reporting a normalized recipient
    (+tag stripped from the local part) must not create orphan rows.
    """

    SETTINGS = {
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    }

    def _post_webhook(self, payload):
        """Helper to post a webhook payload"""
        return self.client.post(
            '/brevo-analytics/webhook/',
            data=json.dumps(payload),
            content_type='application/json'
        )

    def _base_payload(self, event, message_id, email, ts=None):
        return {
            'event': event,
            'message-id': message_id,
            'email': email,
            'subject': 'Digest quotidiano',
            'ts_event': ts or int(time.time()),
            'sender': 'noreply@example.com',
        }

    @override_settings(BREVO_ANALYTICS=SETTINGS)
    def test_delivered_with_stripped_plus_tag_attaches_to_existing_row(self):
        """A 'delivered' event with the +tag stripped must attach to the
        single existing row with the same message-id, not create an orphan."""
        ts = int(time.time())
        msg_id = '<norm-001@smtp-relay.mailin.fr>'

        self._post_webhook(self._base_payload('request', msg_id, 'user+tag@example.com', ts))
        self._post_webhook(self._base_payload('delivered', msg_id, 'user@example.com', ts + 60))

        emails = BrevoEmail.objects.filter(brevo_message_id=msg_id)
        self.assertEqual(emails.count(), 1)

        email = emails.first()
        # The original (full) address is kept
        self.assertEqual(email.recipient_email, 'user+tag@example.com')
        self.assertEqual(email.current_status, 'delivered')

        # The address reported by the event is stored in the event extra data
        delivered_events = [e for e in email.events if e['type'] == 'delivered']
        self.assertEqual(len(delivered_events), 1)
        self.assertEqual(delivered_events[0].get('reported_email'), 'user@example.com')

        # Stats count a single recipient
        message = email.message
        self.assertEqual(message.total_sent, 1)
        self.assertEqual(message.total_delivered, 1)

    @override_settings(BREVO_ANALYTICS={**SETTINGS, 'ANONYMOUS_TRACKING': False})
    def test_non_creation_event_with_stripped_plus_tag_attaches(self):
        """A non-creation event (unique_opened) with normalized recipient
        must attach to the existing row instead of being ignored."""
        ts = int(time.time())
        msg_id = '<norm-002@smtp-relay.mailin.fr>'

        self._post_webhook(self._base_payload('request', msg_id, 'user+tag@example.com', ts))
        self._post_webhook(self._base_payload('unique_opened', msg_id, 'user@example.com', ts + 120))

        emails = BrevoEmail.objects.filter(brevo_message_id=msg_id)
        self.assertEqual(emails.count(), 1)
        self.assertEqual(emails.first().current_status, 'opened')

    @override_settings(BREVO_ANALYTICS=SETTINGS)
    def test_ambiguous_candidates_create_row_as_before(self):
        """With multiple rows sharing the same message-id (marketing
        campaign semantics), behavior is unchanged: a new row is created."""
        ts = int(time.time())
        msg_id = '<norm-003@smtp-relay.mailin.fr>'

        self._post_webhook(self._base_payload('request', msg_id, 'user+tag@example.com', ts))
        self._post_webhook(self._base_payload('request', msg_id, 'other@example.com', ts))
        self._post_webhook(self._base_payload('delivered', msg_id, 'user@example.com', ts + 60))

        emails = BrevoEmail.objects.filter(brevo_message_id=msg_id)
        self.assertEqual(emails.count(), 3)

    @override_settings(BREVO_ANALYTICS=SETTINGS)
    def test_different_address_creates_row_as_before(self):
        """A single candidate whose canonical form differs must not match:
        a new row is created as today."""
        ts = int(time.time())
        msg_id = '<norm-004@smtp-relay.mailin.fr>'

        self._post_webhook(self._base_payload('request', msg_id, 'user+tag@example.com', ts))
        self._post_webhook(self._base_payload('delivered', msg_id, 'someoneelse@example.com', ts + 60))

        emails = BrevoEmail.objects.filter(brevo_message_id=msg_id)
        self.assertEqual(emails.count(), 2)

    @override_settings(BREVO_ANALYTICS=SETTINGS)
    def test_normalization_is_case_insensitive(self):
        """Canonical comparison must be case-insensitive."""
        ts = int(time.time())
        msg_id = '<norm-005@smtp-relay.mailin.fr>'

        self._post_webhook(self._base_payload('request', msg_id, 'User+Tag@Example.com', ts))
        self._post_webhook(self._base_payload('delivered', msg_id, 'user@example.com', ts + 60))

        emails = BrevoEmail.objects.filter(brevo_message_id=msg_id)
        self.assertEqual(emails.count(), 1)
        self.assertEqual(emails.first().current_status, 'delivered')

    @override_settings(BREVO_ANALYTICS=SETTINGS)
    def test_exact_match_does_not_use_fallback(self):
        """When the exact (message-id, recipient) lookup hits, the event is
        attached without any reported_email annotation."""
        ts = int(time.time())
        msg_id = '<norm-006@smtp-relay.mailin.fr>'

        self._post_webhook(self._base_payload('request', msg_id, 'user+tag@example.com', ts))
        self._post_webhook(self._base_payload('delivered', msg_id, 'user+tag@example.com', ts + 60))

        emails = BrevoEmail.objects.filter(brevo_message_id=msg_id)
        self.assertEqual(emails.count(), 1)
        delivered_events = [e for e in emails.first().events if e['type'] == 'delivered']
        self.assertEqual(len(delivered_events), 1)
        self.assertNotIn('reported_email', delivered_events[0])


class DisplaySubjectTestCase(TestCase):
    """Tests for display_subject computed field in serializers"""

    @override_settings(BREVO_ANALYTICS={
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_display_subject_strips_prefix_and_id(self):
        """display_subject should strip '{prefix}:{id}:' from tag-based subjects"""
        from brevo_analytics.serializers import BrevoMessageSerializer
        message = BrevoMessage.objects.create(
            subject='digest:42:Esito CDM 2024-09-17',
            sent_date=timezone.now().date()
        )
        serializer = BrevoMessageSerializer(message)
        self.assertEqual(serializer.data['display_subject'], 'Esito CDM 2024-09-17')

    @override_settings(BREVO_ANALYTICS={
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_display_subject_non_tag_subject_unchanged(self):
        """display_subject should return subject unchanged if it doesn't match the prefix"""
        from brevo_analytics.serializers import BrevoMessageSerializer
        message = BrevoMessage.objects.create(
            subject='Password reset notification',
            sent_date=timezone.now().date()
        )
        serializer = BrevoMessageSerializer(message)
        self.assertEqual(serializer.data['display_subject'], 'Password reset notification')

    @override_settings(BREVO_ANALYTICS={})
    def test_display_subject_in_default_mode_equals_subject(self):
        """In default subject grouping mode, display_subject == subject"""
        from brevo_analytics.serializers import BrevoMessageSerializer
        message = BrevoMessage.objects.create(
            subject='Normal subject line',
            sent_date=timezone.now().date()
        )
        serializer = BrevoMessageSerializer(message)
        self.assertEqual(serializer.data['display_subject'], 'Normal subject line')

    @override_settings(BREVO_ANALYTICS={
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_display_subject_with_colons_in_title(self):
        """display_subject should handle titles containing colons"""
        from brevo_analytics.serializers import BrevoMessageSerializer
        message = BrevoMessage.objects.create(
            subject='digest:42:Esito CDM: seduta del 17/09',
            sent_date=timezone.now().date()
        )
        serializer = BrevoMessageSerializer(message)
        self.assertEqual(serializer.data['display_subject'], 'Esito CDM: seduta del 17/09')


class ImportTagTestCase(TestCase):
    """Tests for tag support in CSV import command"""

    def _create_csv(self, rows):
        """Create a temporary CSV file with the given rows.

        Each row is a dict with keys: st_text, ts, sub, frm, email, tag, mid, link
        """
        import csv
        import os
        import tempfile
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='')
        writer = csv.DictWriter(f, fieldnames=['st_text', 'ts', 'sub', 'frm', 'email', 'tag', 'mid', 'link'])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        f.close()
        return f.name

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_import_stores_tag_on_email(self):
        """CSV import should store the tag column value in BrevoEmail.tags"""
        import os
        csv_path = self._create_csv([
            {
                'st_text': 'Inviata', 'ts': '17-09-2024 10:00:00',
                'sub': 'Esito CDM - Acme', 'frm': 'noreply@example.com',
                'email': 'acme@example.com', 'tag': 'digest:42:Esito CDM 2024-09-17',
                'mid': '<import-tag-001@example.com>', 'link': '',
            },
        ])
        try:
            call_command('import_brevo_logs', csv_path, stdout=StringIO())
            email = BrevoEmail.objects.get(
                brevo_message_id='import-tag-001@example.com',
                recipient_email='acme@example.com'
            )
            self.assertEqual(email.tags, ['digest:42:Esito CDM 2024-09-17'])
        finally:
            os.unlink(csv_path)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_import_tag_grouping(self):
        """CSV import with MESSAGE_GROUP_BY='tag' should group by matching tag"""
        import os
        csv_path = self._create_csv([
            {
                'st_text': 'Inviata', 'ts': '17-09-2024 10:00:00',
                'sub': 'Esito CDM - Acme', 'frm': 'noreply@example.com',
                'email': 'acme@example.com', 'tag': 'digest:42:Esito CDM 2024-09-17',
                'mid': '<import-grp-001@example.com>', 'link': '',
            },
            {
                'st_text': 'Inviata', 'ts': '17-09-2024 10:01:00',
                'sub': 'Esito CDM - Beta', 'frm': 'noreply@example.com',
                'email': 'beta@example.com', 'tag': 'digest:42:Esito CDM 2024-09-17',
                'mid': '<import-grp-002@example.com>', 'link': '',
            },
        ])
        try:
            call_command('import_brevo_logs', csv_path, stdout=StringIO())
            messages = BrevoMessage.objects.filter(subject='Esito CDM 2024-09-17')
            self.assertEqual(messages.count(), 1)
            self.assertEqual(messages.first().emails.count(), 2)
        finally:
            os.unlink(csv_path)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_import_tag_grouping_fallback(self):
        """CSV import with tag grouping should fall back to subject when no matching tag"""
        import os
        csv_path = self._create_csv([
            {
                'st_text': 'Inviata', 'ts': '17-09-2024 10:00:00',
                'sub': 'Password reset', 'frm': 'noreply@example.com',
                'email': 'user@example.com', 'tag': '',
                'mid': '<import-fb-001@example.com>', 'link': '',
            },
        ])
        try:
            call_command('import_brevo_logs', csv_path, stdout=StringIO())
            email = BrevoEmail.objects.get(
                brevo_message_id='import-fb-001@example.com',
                recipient_email='user@example.com'
            )
            self.assertEqual(email.message.subject, 'Password reset')
        finally:
            os.unlink(csv_path)


class AllowedSenderMatchingTestCase(TestCase):
    """Tests for domain-based and exact ALLOWED_SENDERS matching"""

    # ── Unit: is_sender_allowed ──

    def test_exact_match(self):
        self.assertTrue(is_sender_allowed('info@example.com', ['info@example.com']))

    def test_exact_match_case_insensitive(self):
        self.assertTrue(is_sender_allowed('Info@Example.COM', ['info@example.com']))

    def test_exact_no_match(self):
        self.assertFalse(is_sender_allowed('other@example.com', ['info@example.com']))

    def test_domain_match(self):
        self.assertTrue(is_sender_allowed('alice@company.com', ['@company.com']))

    def test_domain_match_case_insensitive(self):
        self.assertTrue(is_sender_allowed('Alice@COMPANY.COM', ['@company.com']))

    def test_domain_no_match(self):
        self.assertFalse(is_sender_allowed('alice@other.com', ['@company.com']))

    def test_mixed_list_exact_hit(self):
        allowed = ['info@example.com', '@company.com']
        self.assertTrue(is_sender_allowed('info@example.com', allowed))

    def test_mixed_list_domain_hit(self):
        allowed = ['info@example.com', '@company.com']
        self.assertTrue(is_sender_allowed('bob@company.com', allowed))

    def test_mixed_list_no_match(self):
        allowed = ['info@example.com', '@company.com']
        self.assertFalse(is_sender_allowed('bob@other.com', allowed))

    def test_empty_list_allows_all(self):
        self.assertTrue(is_sender_allowed('anyone@anywhere.com', []))

    def test_none_sender_denied(self):
        self.assertFalse(is_sender_allowed(None, ['@company.com']))

    def test_empty_sender_denied(self):
        self.assertFalse(is_sender_allowed('', ['@company.com']))

    # ── Unit: get_allowed_senders ──

    @override_settings(BREVO_ANALYTICS={'ALLOWED_SENDERS': ['a@b.com', '@c.com']})
    def test_get_allowed_senders_list(self):
        self.assertEqual(get_allowed_senders(), ['a@b.com', '@c.com'])

    @override_settings(BREVO_ANALYTICS={'ALLOWED_SENDERS': 'single@b.com'})
    def test_get_allowed_senders_string_wrapped(self):
        self.assertEqual(get_allowed_senders(), ['single@b.com'])

    @override_settings(BREVO_ANALYTICS={})
    def test_get_allowed_senders_empty_default(self):
        self.assertEqual(get_allowed_senders(), [])

    # ── Unit: build_sender_filter_q ──

    def test_filter_q_empty_list(self):
        from django.db.models import Q
        self.assertEqual(str(build_sender_filter_q([])), str(Q()))

    def test_filter_q_exact_email(self):
        q = build_sender_filter_q(['info@example.com'])
        # Should contain iexact lookup and isnull
        q_str = str(q)
        self.assertIn('sender_email__iexact', q_str)
        self.assertIn('sender_email__isnull', q_str)

    def test_filter_q_domain_pattern(self):
        q = build_sender_filter_q(['@company.com'])
        q_str = str(q)
        self.assertIn('sender_email__iendswith', q_str)
        self.assertIn('sender_email__isnull', q_str)

    # ── Unit: build_sender_sql_clause ──

    def test_sql_clause_empty(self):
        self.assertEqual(build_sender_sql_clause([]), '1=1')

    def test_sql_clause_exact(self):
        clause = build_sender_sql_clause(['info@example.com'])
        self.assertEqual(clause, "LOWER(frm) = 'info@example.com'")

    def test_sql_clause_domain(self):
        clause = build_sender_sql_clause(['@company.com'])
        self.assertEqual(clause, "LOWER(frm) LIKE '%@company.com'")

    def test_sql_clause_mixed(self):
        clause = build_sender_sql_clause(['info@example.com', '@company.com'])
        self.assertIn("LOWER(frm) = 'info@example.com'", clause)
        self.assertIn("LOWER(frm) LIKE '%@company.com'", clause)
        self.assertIn(' OR ', clause)

    def test_sql_clause_custom_column(self):
        clause = build_sender_sql_clause(['info@example.com'], column='sender')
        self.assertEqual(clause, "LOWER(sender) = 'info@example.com'")

    # ── Integration: ORM filtering ──

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_orm_domain_filter_includes_matching(self):
        msg = BrevoMessage.objects.create(subject='Test', sent_date=timezone.now().date())
        BrevoEmail.objects.create(
            message=msg, brevo_message_id='<orm1@test>',
            recipient_email='r@example.com', sent_at=timezone.now(),
            sender_email='alice@company.com',
        )
        self.assertEqual(BrevoEmail.objects.count(), 1)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_orm_domain_filter_excludes_non_matching(self):
        msg = BrevoMessage.objects.create(subject='Test', sent_date=timezone.now().date())
        BrevoEmail.objects.create(
            message=msg, brevo_message_id='<orm2@test>',
            recipient_email='r@example.com', sent_at=timezone.now(),
            sender_email='bob@other.com',
        )
        self.assertEqual(BrevoEmail.objects.count(), 0)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_orm_domain_filter_includes_null_sender(self):
        msg = BrevoMessage.objects.create(subject='Test', sent_date=timezone.now().date())
        BrevoEmail.objects.create(
            message=msg, brevo_message_id='<orm3@test>',
            recipient_email='r@example.com', sent_at=timezone.now(),
            sender_email=None,
        )
        self.assertEqual(BrevoEmail.objects.count(), 1)

    # ── Integration: webhook ──

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_domain_match_accepted(self):
        payload = {
            'event': 'request',
            'message-id': '<wh-domain-001@test>',
            'email': 'recipient@example.com',
            'subject': 'Domain Test',
            'ts_event': int(time.time()),
            'sender': 'alice@company.com',
        }
        response = self.client.post(
            '/brevo-analytics/webhook/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_domain_mismatch_rejected(self):
        payload = {
            'event': 'request',
            'message-id': '<wh-domain-002@test>',
            'email': 'recipient@example.com',
            'subject': 'Domain Test',
            'ts_event': int(time.time()),
            'sender': 'bob@other.com',
        }
        response = self.client.post(
            '/brevo-analytics/webhook/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['reason'], 'unauthorized_sender')


@override_settings(BREVO_ANALYTICS={'ANONYMOUS_TRACKING': False})
class StatusFilterApiTestCase(TestCase):
    """Tests for cumulative status filter in message_emails_api (per-recipient tracking)"""

    def setUp(self):
        self.message = BrevoMessage.objects.create(
            subject="Test Campaign",
            sent_date=timezone.now().date()
        )
        self.email_delivered = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<msg-delivered@test.com>",
            recipient_email="delivered@test.com",
            sent_at=timezone.now(),
            current_status='delivered',
        )
        self.email_opened = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<msg-opened@test.com>",
            recipient_email="opened@test.com",
            sent_at=timezone.now(),
            current_status='opened',
        )
        self.email_clicked = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<msg-clicked@test.com>",
            recipient_email="clicked@test.com",
            sent_at=timezone.now(),
            current_status='clicked',
        )
        self.email_bounced = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<msg-bounced@test.com>",
            recipient_email="bounced@test.com",
            sent_at=timezone.now(),
            current_status='bounced',
        )
        from django.contrib.auth.models import User
        self.admin = User.objects.create_superuser('admin', 'admin@test.com', 'password')
        self.client.login(username='admin', password='password')

    def test_filter_delivered_includes_opened_and_clicked(self):
        """Clicking 'Delivered' counter must include opened and clicked emails too"""
        response = self.client.get(
            f'/brevo-analytics/api/messages/{self.message.id}/emails/?status=delivered'
        )
        self.assertEqual(response.status_code, 200)
        emails = response.json()['emails']
        recipients = {e['recipient_email'] for e in emails}
        self.assertIn('delivered@test.com', recipients)
        self.assertIn('opened@test.com', recipients)
        self.assertIn('clicked@test.com', recipients)
        self.assertNotIn('bounced@test.com', recipients)

    def test_filter_opened_includes_clicked(self):
        """Clicking 'Opened' counter must include clicked emails too"""
        response = self.client.get(
            f'/brevo-analytics/api/messages/{self.message.id}/emails/?status=opened'
        )
        self.assertEqual(response.status_code, 200)
        emails = response.json()['emails']
        recipients = {e['recipient_email'] for e in emails}
        self.assertIn('opened@test.com', recipients)
        self.assertIn('clicked@test.com', recipients)
        self.assertNotIn('delivered@test.com', recipients)
        self.assertNotIn('bounced@test.com', recipients)

    def test_filter_clicked_exact(self):
        """Clicking 'Clicked' counter shows only clicked emails"""
        response = self.client.get(
            f'/brevo-analytics/api/messages/{self.message.id}/emails/?status=clicked'
        )
        self.assertEqual(response.status_code, 200)
        emails = response.json()['emails']
        recipients = {e['recipient_email'] for e in emails}
        self.assertEqual(recipients, {'clicked@test.com'})

    def test_filter_bounced_exact(self):
        """Bounced filter shows only bounced emails"""
        response = self.client.get(
            f'/brevo-analytics/api/messages/{self.message.id}/emails/?status=bounced'
        )
        self.assertEqual(response.status_code, 200)
        emails = response.json()['emails']
        recipients = {e['recipient_email'] for e in emails}
        self.assertEqual(recipients, {'bounced@test.com'})

    def test_no_filter_returns_all(self):
        """Without status filter, all emails are returned"""
        response = self.client.get(
            f'/brevo-analytics/api/messages/{self.message.id}/emails/'
        )
        self.assertEqual(response.status_code, 200)
        emails = response.json()['emails']
        self.assertEqual(len(emails), 4)


class BounceSplitStatsTestCase(TestCase):
    def setUp(self):
        self.msg = BrevoMessage.objects.create(subject="S", sent_date=timezone.now().date())

    def _email(self, addr, status, events):
        return BrevoEmail.objects.create(
            message=self.msg, brevo_message_id=f"<{addr}>", recipient_email=addr,
            sent_at=timezone.now(), current_status=status, events=events,
        )

    def test_split_hard_soft_undetermined_deferred(self):
        self._email("h@x.it", "bounced", [{"type": "bounced", "bounce_type": "hard"}])
        self._email("s@x.it", "bounced", [{"type": "bounced", "bounce_type": "soft"}])
        self._email("u@x.it", "bounced", [{"type": "bounced"}])          # invalid_email/error
        self._email("d@x.it", "deferred", [{"type": "deferred"}])
        self.msg.update_stats()
        self.msg.refresh_from_db()
        assert self.msg.total_bounced_hard == 1
        assert self.msg.total_bounced_soft == 1
        assert self.msg.total_bounced_undetermined == 1
        assert self.msg.total_deferred == 1
        # invariante
        assert self.msg.total_bounced_hard + self.msg.total_bounced_soft \
            + self.msg.total_bounced_undetermined == self.msg.total_bounced

    def test_deferred_scende_quando_consegna(self):
        e = self._email("d@x.it", "deferred", [{"type": "deferred"}])
        self.msg.update_stats(); self.msg.refresh_from_db()
        assert self.msg.total_deferred == 1
        e.current_status = "delivered"; e.events = [{"type": "delivered"}]; e.save()
        self.msg.update_stats(); self.msg.refresh_from_db()
        assert self.msg.total_deferred == 0


# --- Costo del ricalcolo delle statistiche (issue #15) ---------------------

STATS_HANDLER_CALLS = []


def _record_stats_handler(message_id):
    """STATS_UPDATE_HANDLER di prova: registra gli id invece di accodare un job."""
    STATS_HANDLER_CALLS.append(message_id)


def _failing_stats_handler(message_id):
    """STATS_UPDATE_HANDLER di prova con la coda irraggiungibile."""
    raise ConnectionError("redis irraggiungibile")


DEFERRED = {
    'STATS_UPDATE': 'deferred',
    'STATS_UPDATE_HANDLER': 'brevo_analytics.tests._record_stats_handler',
}


def _stats_090(message):
    """
    Il calcolo di update_stats() della 0.9.0 per i campi che leggono gli eventi,
    come riferimento: la versione nuova deve dare gli stessi numeri.
    """
    sent = hard = soft = undet = 0
    for email in message.emails.all():
        if any(ev.get('type') == 'sent' for ev in email.events):
            sent += 1
        if email.current_status == 'bounced':
            tipo = None
            for ev in email.events:
                if ev.get('type') == 'bounced':
                    tipo = ev.get('bounce_type') or tipo
            if tipo == 'hard':
                hard += 1
            elif tipo == 'soft':
                soft += 1
            else:
                undet += 1
    return {
        'total_sent': sent,
        'total_bounced_hard': hard,
        'total_bounced_soft': soft,
        'total_bounced_undetermined': undet,
    }


class StatsEquivalenceTestCase(TestCase):
    """update_stats() conta nel database ma dà gli stessi numeri della 0.9.0."""

    def setUp(self):
        self.msg = BrevoMessage.objects.create(subject="Equivalenza", sent_date=timezone.now().date())
        other = BrevoMessage.objects.create(subject="Altro invio", sent_date=timezone.now().date())
        cases = [
            ('delivered', [{'type': 'sent'}, {'type': 'delivered'}]),
            ('delivered', [{'type': 'sent', 'inferred': True}, {'type': 'delivered'}]),
            ('delivered', [{'type': 'delivered'}]),                       # senza 'sent'
            ('sent', []),
            # 'sent' solo dentro il payload grezzo di un altro evento: non conta
            ('delivered', [{'type': 'delivered', 'raw': {'type': 'sent', 'event': 'request'}}]),
            ('opened', [{'timestamp': 'x'}, {'type': 'sent'}, {'type': 'opened'}]),
            ('bounced', [{'type': 'sent'}, {'type': 'bounced', 'bounce_type': 'hard'}]),
            ('bounced', [{'type': 'bounced', 'bounce_type': 'soft'}]),
            ('bounced', [{'type': 'bounced'}]),                           # undetermined
            ('bounced', [{'type': 'bounced', 'bounce_type': 'soft'},
                         {'type': 'bounced', 'bounce_type': 'hard'}]),    # vince l'ultimo
            ('bounced', [{'type': 'bounced', 'bounce_type': 'soft'},
                         {'type': 'bounced'}]),                           # resta soft
            ('bounced', [{'type': 'sent'}]),                              # stato senza evento
            ('delivered', [{'type': 'bounced', 'bounce_type': 'hard'},
                           {'type': 'delivered'}]),                       # non più bounced
            ('deferred', [{'type': 'sent'}, {'type': 'deferred'}]),
        ]
        for i, (status, events) in enumerate(cases):
            BrevoEmail.objects.create(
                message=self.msg, brevo_message_id=f"<eq{i}@x.it>", recipient_email=f"eq{i}@x.it",
                sent_at=timezone.now(), current_status=status, events=events,
            )
        BrevoEmail.objects.create(
            message=other, brevo_message_id="<other@x.it>", recipient_email="other@x.it",
            sent_at=timezone.now(), current_status='bounced',
            events=[{'type': 'sent'}, {'type': 'bounced', 'bounce_type': 'hard'}],
        )

    def test_same_numbers_as_090(self):
        expected = _stats_090(self.msg)
        self.msg.update_stats()
        self.msg.refresh_from_db()
        self.assertEqual(
            {k: getattr(self.msg, k) for k in expected}, expected,
        )
        self.assertEqual(expected, {
            'total_sent': 6, 'total_bounced_hard': 2, 'total_bounced_soft': 2,
            'total_bounced_undetermined': 2,
        })

    @skipUnless(connection.features.supports_json_field_contains,
                "il conteggio nel database serve un backend con JSON contains (PostgreSQL, MySQL)")
    def test_does_not_load_events_of_every_email(self):
        """Gli eventi si leggono solo per le email in stato 'bounced'."""
        with CaptureQueriesContext(connection) as ctx:
            self.msg.update_stats()
        table = BrevoEmail._meta.db_table
        loading_events = [
            q['sql'] for q in ctx.captured_queries
            if q['sql'].startswith('SELECT')
            and f'"{table}"."events"' in q['sql'].split(' FROM ')[0]
        ]
        self.assertEqual(len(loading_events), 1, loading_events)
        self.assertIn('current_status', loading_events[0])


class DeferredStatsUpdateTestCase(TestCase):
    """STATS_UPDATE='deferred': il webhook segna, il ricalcolo avviene fuori."""

    def setUp(self):
        STATS_HANDLER_CALLS.clear()
        self.msg = BrevoMessage.objects.create(subject="Invio", sent_date=timezone.now().date())

    def _email(self, i, message=None):
        return BrevoEmail.objects.create(
            message=message or self.msg, brevo_message_id=f"<d{i}@x.it>",
            recipient_email=f"d{i}@x.it", sent_at=timezone.now(),
            events=[{'type': 'sent', 'timestamp': '2026-10-22T10:00:00+00:00'}],
        )

    def _add_event_queries(self, n):
        msg = BrevoMessage.objects.create(subject=f"Invio da {n}", sent_date=timezone.now().date())
        emails = [self._email(f"{n}-{i}", message=msg) for i in range(n)]
        email = BrevoEmail.objects.get(pk=emails[0].pk)
        with CaptureQueriesContext(connection) as ctx:
            with self.captureOnCommitCallbacks(execute=True):
                email.add_event('delivered', timezone.now())
        return ctx.captured_queries

    @override_settings(BREVO_ANALYTICS={
        'STATS_UPDATE_HANDLER': 'brevo_analytics.tests._record_stats_handler',
    })
    def test_default_is_sync(self):
        """Senza STATS_UPDATE il comportamento è quello di sempre; l'handler non si usa."""
        email = self._email(1)
        with self.captureOnCommitCallbacks(execute=True):
            email.add_event('delivered', timezone.now())
        self.msg.refresh_from_db()
        self.assertEqual(self.msg.total_delivered, 1)
        self.assertFalse(self.msg.stats_dirty)
        self.assertEqual(STATS_HANDLER_CALLS, [])

    @override_settings(BREVO_ANALYTICS=DEFERRED)
    def test_add_event_marks_and_calls_handler_once_per_burst(self):
        e1, e2, e3 = self._email(1), self._email(2), self._email(3)
        with self.captureOnCommitCallbacks(execute=True):
            e1.add_event('delivered', timezone.now())
            e2.add_event('delivered', timezone.now())
            e1.add_event('unique_opened', timezone.now())
        self.assertEqual(STATS_HANDLER_CALLS, [self.msg.pk])
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.stats_dirty)
        self.assertEqual(self.msg.total_delivered, 0)  # non ancora ricalcolato

        recalculate_message_stats(self.msg.pk)
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.stats_dirty)
        self.assertEqual(self.msg.total_sent, 3)
        self.assertEqual(self.msg.total_delivered, 2)

        # il primo evento dopo il ricalcolo ne accoda un altro
        with self.captureOnCommitCallbacks(execute=True):
            e3.add_event('delivered', timezone.now())
        self.assertEqual(STATS_HANDLER_CALLS, [self.msg.pk, self.msg.pk])

    @override_settings(BREVO_ANALYTICS={'STATS_UPDATE': 'deferred'})
    def test_without_handler_only_marks(self):
        email = self._email(1)
        with self.captureOnCommitCallbacks(execute=True):
            email.add_event('delivered', timezone.now())
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.stats_dirty)
        self.assertEqual(self.msg.total_delivered, 0)

    @override_settings(BREVO_ANALYTICS=DEFERRED)
    def test_add_event_cost_does_not_grow_with_emails(self):
        """add_event() non legge le altre email dell'invio: query costanti al crescere di N."""
        small, large = self._add_event_queries(3), self._add_event_queries(60)
        self.assertEqual(len(small), len(large))
        table = BrevoEmail._meta.db_table
        reads = [q['sql'] for q in large if q['sql'].startswith('SELECT') and f'FROM "{table}"' in q['sql']]
        self.assertEqual(reads, [])

    @override_settings(BREVO_ANALYTICS={'STATS_UPDATE': 'later'})
    def test_invalid_mode(self):
        email = self._email(1)
        with self.assertRaises(ImproperlyConfigured):
            email.add_event('delivered', timezone.now())

    @override_settings(BREVO_ANALYTICS={'STATS_UPDATE': 'deferred', 'STATS_UPDATE_HANDLER': 'nowhere.handler'})
    def test_handler_not_importable(self):
        email = self._email(1)
        with self.assertRaises(ImproperlyConfigured):
            email.add_event('delivered', timezone.now())

    @override_settings(BREVO_ANALYTICS={
        'STATS_UPDATE': 'deferred',
        'STATS_UPDATE_HANDLER': 'brevo_analytics.tests._failing_stats_handler',
    })
    def test_handler_failure_does_not_break_add_event(self):
        email = self._email(1)
        with self.assertLogs('brevo_analytics.models', level='ERROR'):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(email.add_event('delivered', timezone.now()))
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.stats_dirty)

    @override_settings(BREVO_ANALYTICS=DEFERRED)
    def test_event_during_recalculation_enqueues_again(self):
        """Un evento salvato mentre il job ricalcola rialza il flag e accoda un altro job."""
        e1, e2 = self._email(1), self._email(2)
        with self.captureOnCommitCallbacks(execute=True):
            e1.add_event('delivered', timezone.now())
        original = BrevoMessage.update_stats

        def update_stats_with_concurrent_event(message):
            BrevoEmail.objects.get(pk=e2.pk).add_event('delivered', timezone.now())
            original(message)

        with self.captureOnCommitCallbacks(execute=True):
            with mock.patch.object(BrevoMessage, 'update_stats', update_stats_with_concurrent_event):
                recalculate_message_stats(self.msg.pk)
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.stats_dirty)
        self.assertEqual(STATS_HANDLER_CALLS, [self.msg.pk, self.msg.pk])

    def test_refresh_failure_leaves_message_dirty(self):
        BrevoMessage.objects.filter(pk=self.msg.pk).update(stats_dirty=True)
        with mock.patch.object(BrevoMessage, 'update_stats', side_effect=RuntimeError("db giù")):
            with self.assertRaises(RuntimeError):
                recalculate_message_stats(self.msg.pk)
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.stats_dirty)

    def test_recalculate_deleted_message_is_ignored(self):
        recalculate_message_stats(self.msg.pk + 1000)

    def test_command_dirty_only(self):
        dirty = self.msg
        self._email(1)
        BrevoMessage.objects.filter(pk=dirty.pk).update(stats_dirty=True)
        clean = BrevoMessage.objects.create(subject="Pulito", sent_date=timezone.now().date(), total_sent=99)

        call_command('recalculate_stats', '--dirty', stdout=StringIO())

        dirty.refresh_from_db()
        clean.refresh_from_db()
        self.assertFalse(dirty.stats_dirty)
        self.assertEqual(dirty.total_sent, 1)
        self.assertEqual(clean.total_sent, 99)  # non toccato

    def test_full_recalculation_clears_flag(self):
        BrevoMessage.objects.filter(pk=self.msg.pk).update(stats_dirty=True)
        call_command('recalculate_stats', stdout=StringIO())
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.stats_dirty)

    @override_settings(BREVO_ANALYTICS={
        **DEFERRED,
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_answers_without_recalculating(self):
        base = {
            'message-id': '<deferred-001@example.com>',
            'email': 'recipient@example.com',
            'subject': 'Newsletter',
            'sender': 'noreply@example.com',
        }
        with self.captureOnCommitCallbacks(execute=True):
            for event in ('request', 'delivered'):
                response = self.client.post(
                    '/brevo-analytics/webhook/',
                    data=json.dumps({**base, 'event': event, 'ts_event': int(time.time())}),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 200)
        message = BrevoMessage.objects.get(subject='Newsletter')
        self.assertTrue(message.stats_dirty)
        self.assertEqual(message.total_delivered, 0)
        self.assertEqual(STATS_HANDLER_CALLS, [message.pk])


@skipUnless(connection.vendor == 'postgresql',
            "serve un database con transazioni concorrenti vere (TEST_DB=postgres)")
class DeferredStatsConcurrencyTestCase(TransactionTestCase):
    """Ordinamenti fra webhook in transazione (ATOMIC_REQUESTS) e job, su connessioni distinte."""

    def setUp(self):
        STATS_HANDLER_CALLS.clear()
        self.msg = BrevoMessage.objects.create(subject="Concorrenza", sent_date=timezone.now().date())
        self.emails = [
            BrevoEmail.objects.create(
                message=self.msg, brevo_message_id=f"<c{i}@x.it>", recipient_email=f"c{i}@x.it",
                sent_at=timezone.now(), events=[{'type': 'sent', 'timestamp': 't0'}],
            )
            for i in range(2)
        ]

    @override_settings(BREVO_ANALYTICS=DEFERRED)
    def test_job_running_before_event_commit_does_not_lose_it(self):
        """
        E1 segna il messaggio e accoda J1; E2 salva il suo evento in una
        transazione ancora aperta quando J1 ricalcola. Al commit di E2 il
        messaggio deve tornare da ricalcolare, con un secondo job accodato.
        """
        self.emails[0].add_event('delivered', 't1')
        self.assertEqual(STATS_HANDLER_CALLS, [self.msg.pk])

        saved, may_commit = threading.Event(), threading.Event()

        def atomic_request():
            try:
                with transaction.atomic():
                    BrevoEmail.objects.get(pk=self.emails[1].pk).add_event('delivered', 't2')
                    saved.set()
                    may_commit.wait(10)
            finally:
                connections.close_all()

        request = threading.Thread(target=atomic_request)
        request.start()
        try:
            self.assertTrue(saved.wait(10))
            recalculate_message_stats(self.msg.pk)  # J1, con E2 non ancora committato
        finally:
            may_commit.set()
            request.join(10)

        self.msg.refresh_from_db()
        self.assertEqual(self.msg.total_delivered, 1)  # J1 non ha visto E2
        self.assertTrue(self.msg.stats_dirty)
        self.assertEqual(STATS_HANDLER_CALLS, [self.msg.pk, self.msg.pk])

        recalculate_message_stats(self.msg.pk)  # J2
        self.msg.refresh_from_db()
        self.assertEqual(self.msg.total_delivered, 2)
        self.assertFalse(self.msg.stats_dirty)

    @override_settings(BREVO_ANALYTICS=DEFERRED)
    def test_concurrent_recalculations_run_one_after_the_other(self):
        """Un secondo ricalcolo attende il primo: nessuno salva numeri più vecchi dell'altro."""
        in_first, release_first = threading.Event(), threading.Event()
        original = BrevoMessage.update_stats
        order = []

        def slow_update_stats(message):
            if threading.current_thread() is first:
                in_first.set()
                release_first.wait(10)
            original(message)
            order.append(threading.current_thread().name)

        def job():
            try:
                recalculate_message_stats(self.msg.pk)
            finally:
                connections.close_all()

        first = threading.Thread(target=job, name='J1')
        second = threading.Thread(target=job, name='J2')
        with mock.patch.object(BrevoMessage, 'update_stats', slow_update_stats):
            try:
                first.start()
                self.assertTrue(in_first.wait(10))
                second.start()
                second.join(0.5)
                self.assertTrue(second.is_alive())  # in attesa del lock di J1
            finally:
                # anche se il test fallisce: i thread non devono restare con la
                # connessione aperta, o il database di test non si cancella
                release_first.set()
                first.join(10)
                second.join(10)
        self.assertEqual(order, ['J1', 'J2'])


def _write_logs_csv(rows):
    """CSV di log Brevo per import_brevo_logs; restituisce il path (da cancellare)."""
    import csv
    import tempfile
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='')
    writer = csv.DictWriter(f, fieldnames=['st_text', 'ts', 'sub', 'frm', 'email', 'tag', 'mid', 'link'])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    f.close()
    return f.name


ANONYMOUS = {'ALLOWED_SENDERS': ['noreply@example.com'], 'EXCLUDED_RECIPIENT_DOMAINS': []}
PER_RECIPIENT = {**ANONYMOUS, 'ANONYMOUS_TRACKING': False}


class AnonymousTrackingWebhookTestCase(TestCase):
    """Linee guida del Garante sui tracking pixel (#20): webhook."""

    BASE = {
        'message-id': '<anon@example.com>', 'email': 'r@example.com',
        'subject': 'Newsletter', 'sender': 'noreply@example.com',
    }

    def _post(self, **payload):
        return self.client.post(
            '/brevo-analytics/webhook/',
            data=json.dumps({**self.BASE, 'ts_event': int(time.time()), **payload}),
            content_type='application/json',
        )

    def _email(self):
        return BrevoEmail.objects.get(brevo_message_id='<anon@example.com>')

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_opens_and_clicks_are_ignored_by_default(self):
        self.assertEqual(self._post(event='request').status_code, 200)
        self.assertEqual(self._post(event='delivered').status_code, 200)
        for event in ('unique_opened', 'opened', 'unique_proxy_open', 'proxy_open', 'click'):
            response = self._post(event=event, ip='1.2.3.4', user_agent='UA', link='https://a.example.com')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'status': 'ignored', 'reason': 'anonymous_tracking'})
        email = self._email()
        self.assertEqual(email.current_status, 'delivered')
        self.assertEqual([e['type'] for e in email.events], ['sent', 'delivered'])

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_hard_bounce_is_still_recorded(self):
        self._post(event='request')
        response = self._post(event='hard_bounce', reason='mailbox does not exist')
        self.assertEqual(response.status_code, 200)
        bounce = [e for e in self._email().events if e['type'] == 'bounced'][0]
        self.assertEqual(bounce['bounce_type'], 'hard')
        self.assertEqual(bounce['bounce_reason'], 'mailbox does not exist')

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_raw_payload_is_not_stored(self):
        self._post(event='request')
        self._post(event='delivered')
        self.assertTrue(all('raw' not in e for e in self._email().events))

    @override_settings(BREVO_ANALYTICS=PER_RECIPIENT)
    def test_anonymized_events_are_ignored_without_errors(self):
        """Eventi anonimizzati da Brevo, in qualunque forma arrivino: 200 e nessuna modifica."""
        self._post(event='request')
        for missing in ({'message-id': None, 'email': None},
                        {'message-id': 'Anonymized', 'email': 'Anonymized'},
                        {'email': 'Anonymized contact'}):
            for event in ('unique_opened', 'click'):
                with self.assertNoLogs('brevo_analytics.webhooks', level='ERROR'):
                    response = self._post(event=event, **missing)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['reason'], 'anonymized_event')
        self.assertEqual(self._email().current_status, 'sent')

    @override_settings(BREVO_ANALYTICS=PER_RECIPIENT)
    def test_per_recipient_tracking_when_disabled(self):
        self._post(event='request')
        self._post(event='unique_opened', ip='1.2.3.4', user_agent='UA')
        email = self._email()
        self.assertEqual(email.current_status, 'opened')
        opened = [e for e in email.events if e['type'] == 'opened'][0]
        self.assertEqual(opened['ip'], '1.2.3.4')
        self.assertNotIn('raw', opened)

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_anonymized_delivery_does_not_create_a_row(self):
        """Se Brevo anonimizzasse anche una consegna: nessuna email fittizia."""
        response = self._post(event='delivered', **{'message-id': 'Anonymized', 'email': 'Anonymized contact'})
        self.assertEqual(response.json()['reason'], 'anonymized_event')
        self.assertFalse(BrevoEmail.objects.all_unfiltered().exists())

    @override_settings(BREVO_ANALYTICS=PER_RECIPIENT)
    def test_real_address_starting_with_anonymized_is_kept(self):
        self._post(event='request', email='anonymized.smith@example.com')
        self._post(event='unique_opened', email='anonymized.smith@example.com')
        email = BrevoEmail.objects.get(recipient_email='anonymized.smith@example.com')
        self.assertEqual(email.current_status, 'opened')

    @override_settings(BREVO_ANALYTICS=PER_RECIPIENT)
    def test_unknown_event_types_are_ignored(self):
        self._post(event='request')
        response = self._post(event='unique_click', link='https://a.example.com')
        self.assertEqual(response.json(), {'status': 'ignored', 'reason': 'unknown_event_type'})
        self.assertEqual([e['type'] for e in self._email().events], ['sent'])

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_unsubscribe_alias_is_mapped(self):
        self._post(event='request')
        self._post(event='unsubscribe')
        self.assertEqual([e['type'] for e in self._email().events], ['sent', 'unsubscribed'])


class AnonymousTrackingImportTestCase(TestCase):
    """Linee guida del Garante sui tracking pixel (#20): import da CSV."""

    ROW = {'sub': 'Newsletter', 'frm': 'noreply@example.com', 'email': 'r@example.com',
           'tag': '', 'mid': '<imp-anon@example.com>', 'link': ''}

    def _import(self, extra_rows):
        import os
        path = _write_logs_csv([
            {**self.ROW, 'st_text': 'Inviata', 'ts': '17-09-2024 10:00:00'},
            {**self.ROW, 'st_text': 'Consegnata', 'ts': '17-09-2024 10:00:05'},
            *extra_rows,
        ])
        out = StringIO()
        try:
            call_command('import_brevo_logs', path, stdout=out)
        finally:
            os.unlink(path)
        return BrevoEmail.objects.get(brevo_message_id='imp-anon@example.com'), out.getvalue()

    TRACKING_ROWS = [
        {**ROW, 'st_text': 'Prima apertura', 'ts': '17-09-2024 10:01:00'},
        {**ROW, 'st_text': 'Caricata per procura', 'ts': '17-09-2024 10:01:30'},
        {**ROW, 'st_text': 'Cliccata', 'ts': '17-09-2024 10:02:00', 'link': 'https://a.example.com'},
        {**ROW, 'st_text': 'Cliccata', 'ts': '17-09-2024 10:03:00',
         'mid': 'Anonymized', 'email': 'Anonymized', 'link': 'Anonymized data'},
    ]

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_opens_and_clicks_are_skipped_and_counted(self):
        email, output = self._import(self.TRACKING_ROWS)
        self.assertEqual(email.current_status, 'delivered')
        self.assertEqual([e['type'] for e in email.events], ['sent', 'delivered'])
        self.assertIn('Skipped 3 open/click events', output)
        self.assertIn('Skipped 1 anonymized log entries', output)

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_dry_run_reports_skipped_rows(self):
        import os
        path = _write_logs_csv([
            {**self.ROW, 'st_text': 'Inviata', 'ts': '17-09-2024 10:00:00'},
            *self.TRACKING_ROWS,
        ])
        out = StringIO()
        try:
            call_command('import_brevo_logs', path, '--dry-run', stdout=out)
        finally:
            os.unlink(path)
        self.assertIn('Open/click events will be skipped', out.getvalue())
        self.assertIn('Anonymized log entries skipped: 1', out.getvalue())
        self.assertFalse(BrevoEmail.objects.all_unfiltered().exists())

    @override_settings(BREVO_ANALYTICS=PER_RECIPIENT)
    def test_loaded_by_proxy_is_an_open(self):
        email, _ = self._import([{**self.ROW, 'st_text': 'Caricata per procura', 'ts': '17-09-2024 10:01:30'}])
        self.assertEqual(email.current_status, 'opened')


class TrackingTotalsFrozenTestCase(TestCase):
    """Totali storici conservati da anonymize_tracking_data: i totali restano, i tassi si ricalcolano."""

    def _frozen_message(self, delivered):
        msg = BrevoMessage.objects.create(
            subject="Storico", sent_date=timezone.now().date(), tracking_totals_frozen=True,
            total_opened=7, total_clicked=3, open_rate=70.0, click_rate=30.0,
        )
        for i in range(delivered):
            BrevoEmail.objects.create(
                message=msg, brevo_message_id=f"<f{i}@x.it>", recipient_email=f"f{i}@x.it",
                sent_at=timezone.now(), current_status='delivered',
                events=[{'type': 'sent'}, {'type': 'delivered'}],
            )
        msg.update_stats()
        msg.refresh_from_db()
        return msg

    def test_update_stats_keeps_frozen_open_and_click_totals(self):
        msg = self._frozen_message(10)
        self.assertEqual((msg.total_sent, msg.total_delivered), (10, 10))
        self.assertEqual((msg.total_opened, msg.total_clicked, msg.open_rate, msg.click_rate),
                         (7, 3, 70.0, 30.0))

    def test_rates_follow_current_deliveries(self):
        """Nuove consegne dopo la conservazione: i totali restano, i tassi scendono."""
        msg = self._frozen_message(14)
        self.assertEqual((msg.total_opened, msg.open_rate, msg.click_rate), (7, 50.0, 21.43))

    def test_totals_never_exceed_deliveries(self):
        """Email cancellate dopo la conservazione (es. clean_internal_emails)."""
        msg = self._frozen_message(5)
        self.assertEqual((msg.total_opened, msg.total_clicked, msg.open_rate), (5, 3, 100.0))

    def test_message_without_emails_has_zero_rates(self):
        msg = self._frozen_message(0)
        self.assertEqual((msg.total_delivered, msg.open_rate, msg.click_rate), (0, 0.0, 0.0))


@override_settings(BREVO_ANALYTICS={'MIN_AGGREGATE_RECIPIENTS': 1})
class AnonymizeTrackingDataCommandTestCase(TestCase):
    """Comando anonymize_tracking_data: pulizia dei dati storici (soglia a 1 destinatario)."""

    def setUp(self):
        self.msg = BrevoMessage.objects.create(subject="Storico", sent_date=timezone.now().date())
        self.opened = BrevoEmail.objects.create(
            message=self.msg, brevo_message_id="<o@x.it>", recipient_email="o@x.it",
            sent_at=timezone.now(), current_status='clicked',
            events=[
                {'type': 'sent', 'timestamp': 't0', 'raw': {'email': 'o@x.it'}},
                {'type': 'delivered', 'timestamp': 't1'},
                {'type': 'opened', 'timestamp': 't2', 'ip': '1.2.3.4', 'user_agent': 'UA'},
                {'type': 'clicked', 'timestamp': 't3', 'url': 'https://a.it', 'link': 'https://a.it'},
            ],
        )
        self.bounced = BrevoEmail.objects.create(
            message=self.msg, brevo_message_id="<b@x.it>", recipient_email="b@x.it",
            sent_at=timezone.now(), current_status='bounced',
            events=[
                {'type': 'sent', 'timestamp': 't0'},
                {'type': 'bounced', 'timestamp': 't1', 'bounce_type': 'hard',
                 'bounce_reason': 'no such user', 'raw': {'email': 'b@x.it', 'ip': '5.6.7.8'}},
            ],
        )
        self.msg.update_stats()

    def _run(self, *args):
        out = StringIO()
        call_command('anonymize_tracking_data', '--no-input', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        output = self._run('--dry-run')
        self.assertIn('DRY RUN', output)
        self.opened.refresh_from_db()
        self.assertEqual(self.opened.current_status, 'clicked')
        self.assertEqual(len(self.opened.events), 4)

    def test_strips_tracking_data_and_keeps_bounces(self):
        self._run()
        self.opened.refresh_from_db()
        self.bounced.refresh_from_db()
        self.assertEqual(self.opened.current_status, 'delivered')
        self.assertEqual(self.opened.events, [
            {'type': 'sent', 'timestamp': 't0'},
            {'type': 'delivered', 'timestamp': 't1'},
        ])
        self.assertEqual(self.bounced.current_status, 'bounced')
        self.assertEqual(self.bounced.events[1], {
            'type': 'bounced', 'timestamp': 't1', 'bounce_type': 'hard', 'bounce_reason': 'no such user',
        })

    def test_keeps_aggregate_totals_by_default(self):
        self._run()
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.tracking_totals_frozen)
        self.assertEqual((self.msg.total_opened, self.msg.total_clicked), (1, 1))
        self.assertEqual((self.msg.total_delivered, self.msg.total_bounced), (1, 1))

    def test_discard_totals(self):
        self._run('--discard-totals')
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.tracking_totals_frozen)
        self.assertEqual((self.msg.total_opened, self.msg.total_clicked), (0, 0))

    def test_second_run_finds_nothing(self):
        self._run()
        output = self._run()
        self.assertIn('Emails with tracking data: 0', output)

    @override_settings(BREVO_ANALYTICS={'BLACKLIST_ONLY_MODE': True})
    def test_disabled_in_blacklist_only_mode(self):
        output = self._run()
        self.assertIn('disabled in BLACKLIST_ONLY_MODE', output)
        self.opened.refresh_from_db()
        self.assertEqual(self.opened.current_status, 'clicked')

    def test_discard_totals_after_keeping_them(self):
        """--discard-totals funziona anche dopo una prima esecuzione che li ha conservati."""
        self._run()
        output = self._run('--discard-totals')
        self.assertNotIn('Nothing to clean', output)
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.tracking_totals_frozen)
        self.assertEqual((self.msg.total_opened, self.msg.open_rate), (0, 0.0))

    @override_settings(BREVO_ANALYTICS={'MIN_AGGREGATE_RECIPIENTS': 10})
    def test_totals_below_threshold_are_not_kept(self):
        """Un messaggio con un solo destinatario consegnato: il totale direbbe chi ha aperto."""
        self._run()
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.tracking_totals_frozen)
        self.assertEqual((self.msg.total_opened, self.msg.total_clicked), (0, 0))

    def test_kept_totals_are_a_first_run_snapshot(self):
        """Aperture arrivate dopo la prima esecuzione si cancellano senza entrare nei totali."""
        self._run()
        late = BrevoEmail.objects.create(
            message=self.msg, brevo_message_id="<late@x.it>", recipient_email="late@x.it",
            sent_at=timezone.now(), current_status='opened',
            events=[{'type': 'sent'}, {'type': 'delivered'}, {'type': 'opened', 'ip': '9.9.9.9'}],
        )
        self._run()
        late.refresh_from_db()
        self.msg.refresh_from_db()
        self.assertEqual(late.current_status, 'delivered')
        self.assertEqual((self.msg.total_opened, self.msg.total_delivered, self.msg.open_rate), (1, 2, 50.0))

    @override_settings(BREVO_ANALYTICS={'ANONYMOUS_TRACKING': False})
    def test_refused_with_per_recipient_tracking(self):
        output = self._run()
        self.assertIn('ANONYMOUS_TRACKING is False', output)
        self.opened.refresh_from_db()
        self.assertEqual(self.opened.current_status, 'clicked')

    @override_settings(BREVO_ANALYTICS={'ANONYMOUS_TRACKING': False, 'MIN_AGGREGATE_RECIPIENTS': 1})
    def test_force_with_per_recipient_tracking(self):
        self._run('--force')
        self.opened.refresh_from_db()
        self.assertEqual(self.opened.current_status, 'delivered')

    def test_asks_for_confirmation(self):
        out = StringIO()
        with mock.patch('builtins.input', return_value='no'):
            call_command('anonymize_tracking_data', stdout=out)
        self.assertIn('Operation cancelled', out.getvalue())
        self.opened.refresh_from_db()
        self.assertEqual(self.opened.current_status, 'clicked')

    @override_settings(BREVO_ANALYTICS={'STATS_UPDATE': 'deferred', 'MIN_AGGREGATE_RECIPIENTS': 1})
    def test_deferred_mode_clears_dirty_and_keeps_totals(self):
        BrevoMessage.objects.filter(pk=self.msg.pk).update(stats_dirty=True)
        self._run()
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.stats_dirty)
        self.assertTrue(self.msg.tracking_totals_frozen)
        self.assertEqual(self.msg.total_opened, 1)


class AnonymousTrackingApiTestCase(TestCase):
    """API in modalità anonima: niente dati per destinatario, tassi non disponibili."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.msg = BrevoMessage.objects.create(subject="Api", sent_date=timezone.now().date())
        self.email = BrevoEmail.objects.create(
            message=self.msg, brevo_message_id="<api@x.it>", recipient_email="api@x.it",
            sent_at=timezone.now(), current_status='opened',
            events=[
                {'type': 'sent', 'timestamp': 't0', 'raw': {'email': 'api@x.it'}},
                {'type': 'delivered', 'timestamp': 't1'},
                {'type': 'opened', 'timestamp': 't2', 'ip': '1.2.3.4', 'user_agent': 'UA'},
            ],
        )
        self.msg.update_stats()
        User.objects.create_superuser('admin', 'admin@test.com', 'password')
        self.client.login(username='admin', password='password')

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_rates_are_not_available(self):
        data = self.client.get('/brevo-analytics/api/dashboard/').json()
        self.assertIsNone(data['kpi']['open_rate'])
        self.assertIsNone(data['kpi']['click_rate'])
        msg = data['recent_messages'][0]
        self.assertIsNone(msg['open_rate'])
        self.assertIsNone(msg['total_opened'])
        self.assertFalse(msg['recipient_tracking'])

    @override_settings(BREVO_ANALYTICS={**ANONYMOUS, 'MIN_AGGREGATE_RECIPIENTS': 1})
    def test_frozen_totals_are_shown(self):
        BrevoMessage.objects.filter(pk=self.msg.pk).update(tracking_totals_frozen=True)
        msg = self.client.get('/brevo-analytics/api/messages/').json()['messages'][0]
        self.assertEqual(msg['total_opened'], 1)
        self.assertEqual(msg['open_rate'], 100.0)

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_frozen_totals_below_threshold_are_hidden(self):
        BrevoMessage.objects.filter(pk=self.msg.pk).update(tracking_totals_frozen=True)
        msg = self.client.get('/brevo-analytics/api/messages/').json()['messages'][0]
        self.assertIsNone(msg['total_opened'])
        self.assertIsNone(msg['open_rate'])

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_delivered_filter_includes_previously_opened(self):
        for status in ('delivered', 'sent'):
            listed = self.client.get(
                f'/brevo-analytics/api/messages/{self.msg.id}/emails/?status={status}'
            ).json()['emails']
            self.assertEqual([(e['recipient_email'], e['current_status']) for e in listed],
                             [('api@x.it', 'delivered')])

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_open_and_click_filters_are_refused(self):
        for status in ('opened', 'clicked'):
            response = self.client.get(f'/brevo-analytics/api/messages/{self.msg.id}/emails/?status={status}')
            self.assertEqual(response.status_code, 400)

    @override_settings(BREVO_ANALYTICS=ANONYMOUS)
    def test_email_detail_hides_opens_and_raw(self):
        data = self.client.get(f'/brevo-analytics/api/emails/{self.email.id}/').json()
        self.assertEqual(data['current_status'], 'delivered')
        self.assertEqual(data['events'], [
            {'type': 'sent', 'timestamp': 't0'},
            {'type': 'delivered', 'timestamp': 't1'},
        ])
        listed = self.client.get(f'/brevo-analytics/api/messages/{self.msg.id}/emails/').json()['emails']
        self.assertEqual(listed[0]['current_status'], 'delivered')

    @override_settings(BREVO_ANALYTICS=PER_RECIPIENT)
    def test_per_recipient_mode_unchanged(self):
        data = self.client.get('/brevo-analytics/api/dashboard/').json()
        self.assertEqual(data['kpi']['open_rate'], 100.0)
        self.assertTrue(data['recent_messages'][0]['recipient_tracking'])
        detail = self.client.get(f'/brevo-analytics/api/emails/{self.email.id}/').json()
        self.assertEqual(detail['current_status'], 'opened')
        self.assertEqual(detail['events'][2]['ip'], '1.2.3.4')
        self.assertNotIn('raw', detail['events'][0])


def _brevo_report(delivered, unique_opens, unique_clicks):
    """Risposta di /smtp/statistics/aggregatedReport (solo i campi usati)."""
    response = mock.Mock(status_code=200)
    response.json.return_value = {
        'delivered': delivered, 'uniqueOpens': unique_opens, 'uniqueClicks': unique_clicks,
    }
    return response


RATES = {'API_KEY': 'test-key', 'MESSAGE_GROUP_BY': 'tag', 'MESSAGE_TAG_PREFIX': 'invio'}


@override_settings(BREVO_ANALYTICS=RATES)
class FetchBrevoRatesTestCase(TestCase):
    """Comando fetch_brevo_rates: tassi aggregati di apertura e clic dall'API di Brevo (#22)."""

    TAG = 'invio:newsletter-7:Monitoraggio del 29 Ottobre'

    def _message(self, delivered, sent_date=None, tag=TAG):
        sent_date = sent_date or timezone.now().date()
        msg = BrevoMessage.objects.create(
            subject="Monitoraggio del 29 Ottobre", group_key='invio:newsletter-7', sent_date=sent_date,
        )
        for i in range(delivered):
            BrevoEmail.objects.create(
                message=msg, brevo_message_id=f"<r{i}@x.it>", recipient_email=f"r{i}@x.it",
                sent_at=timezone.now(), current_status='delivered',
                events=[{'type': 'sent'}, {'type': 'delivered'}], tags=[tag] if tag else [],
            )
        msg.update_stats()
        return msg

    def _run(self, *args, report=None):
        out = StringIO()
        with mock.patch('brevo_analytics.brevo_rates.requests.get', return_value=report) as get:
            call_command('fetch_brevo_rates', *args, stdout=out)
        return out.getvalue(), get

    def test_stores_aggregate_totals_scaled_to_local_deliveries(self):
        """Brevo conta anche i destinatari esclusi dal pacchetto: i totali si riportano in proporzione."""
        msg = self._message(20)
        _, get = self._run(report=_brevo_report(delivered=40, unique_opens=18, unique_clicks=6))
        params = get.call_args.kwargs['params']
        self.assertEqual(params['tag'], self.TAG)
        self.assertEqual(params['startDate'], msg.sent_date.isoformat())
        self.assertEqual(get.call_args.kwargs['headers']['api-key'], 'test-key')
        msg.refresh_from_db()
        self.assertTrue(msg.tracking_totals_frozen)
        self.assertIsNotNone(msg.tracking_totals_fetched_at)
        self.assertEqual((msg.total_opened, msg.total_clicked), (9, 3))
        self.assertEqual((msg.open_rate, msg.click_rate), (45.0, 15.0))

    def test_end_date_is_capped_at_90_days(self):
        old = timezone.now().date() - timezone.timedelta(days=100)
        self._message(10, sent_date=old)
        _, get = self._run('--days', '120', report=_brevo_report(10, 1, 0))
        params = get.call_args.kwargs['params']
        self.assertEqual(params['endDate'], (old + timezone.timedelta(days=89)).isoformat())

    def test_messages_without_tag_are_skipped(self):
        msg = BrevoMessage.objects.create(subject="Senza tag", sent_date=timezone.now().date())
        output, get = self._run(report=_brevo_report(10, 5, 1))
        get.assert_not_called()
        msg.refresh_from_db()
        self.assertFalse(msg.tracking_totals_frozen)

    def test_messages_older_than_window_are_skipped(self):
        self._message(10, sent_date=timezone.now().date() - timezone.timedelta(days=200))
        _, get = self._run(report=_brevo_report(10, 5, 1))
        get.assert_not_called()

    def test_api_error_leaves_message_unchanged(self):
        msg = self._message(10)
        error = mock.Mock(status_code=400, text='{"code":"invalid_parameter"}')
        output, _ = self._run(report=error)
        self.assertIn('1 failed', output)
        msg.refresh_from_db()
        self.assertFalse(msg.tracking_totals_frozen)

    def test_dry_run_changes_nothing(self):
        msg = self._message(10)
        output, _ = self._run('--dry-run', report=_brevo_report(10, 5, 1))
        self.assertIn('DRY RUN', output)
        msg.refresh_from_db()
        self.assertFalse(msg.tracking_totals_frozen)

    @override_settings(BREVO_ANALYTICS={**RATES, 'API_KEY': ''})
    def test_requires_api_key(self):
        output, get = self._run(report=_brevo_report(10, 5, 1))
        self.assertIn('API_KEY', output)
        get.assert_not_called()

    @override_settings(BREVO_ANALYTICS={**RATES, 'ANONYMOUS_TRACKING': False})
    def test_refused_with_per_recipient_tracking(self):
        output, get = self._run(report=_brevo_report(10, 5, 1))
        self.assertIn('ANONYMOUS_TRACKING is False', output)
        get.assert_not_called()

    def test_dashboard_rates_use_messages_with_totals(self):
        """I riquadri globali si calcolano sui soli messaggi con totali aggregati."""
        from django.contrib.auth.models import User
        self._message(20)
        BrevoMessage.objects.create(subject="Senza dati", sent_date=timezone.now().date(),
                                    total_sent=30, total_delivered=30)
        self._run(report=_brevo_report(delivered=20, unique_opens=10, unique_clicks=4))
        User.objects.create_superuser('admin', 'admin@test.com', 'password')
        self.client.login(username='admin', password='password')
        kpi = self.client.get('/brevo-analytics/api/dashboard/').json()['kpi']
        self.assertEqual((kpi['open_rate'], kpi['click_rate']), (50.0, 20.0))
