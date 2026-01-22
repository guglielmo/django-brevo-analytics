from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
import csv
import uuid
from brevo_analytics.models import BrevoMessage, BrevoEmail
import pytz

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
                sent_at_str = row['sent_at']

                # Parse datetime and make it timezone-aware
                sent_at = datetime.fromisoformat(sent_at_str)
                if sent_at.tzinfo is None:
                    # If naive, assume UTC
                    sent_at = pytz.UTC.localize(sent_at)

                sent_date = sent_at.date()

                # Get or create message
                message, _ = BrevoMessage.objects.get_or_create(
                    subject=subject,
                    sent_date=sent_date
                )

                # Create email
                email, created = BrevoEmail.objects.get_or_create(
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
                    email = BrevoEmail.objects.get(id=email_uuid)
                except BrevoEmail.DoesNotExist:
                    continue

                event_type = row['event_type']
                event_timestamp_str = row['event_timestamp']

                # Parse datetime and make it timezone-aware
                event_timestamp = datetime.fromisoformat(event_timestamp_str)
                if event_timestamp.tzinfo is None:
                    # If naive, assume UTC
                    event_timestamp = pytz.UTC.localize(event_timestamp)

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
