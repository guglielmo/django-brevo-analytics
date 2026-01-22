from django.core.management.base import BaseCommand
from django.utils import timezone
from brevo_analytics.models import BrevoEmail
import pytz


class Command(BaseCommand):
    help = 'Fix naive datetimes in BrevoEmail model by converting them to UTC'

    def handle(self, *args, **options):
        emails_to_fix = []

        for email in BrevoEmail.objects.all():
            needs_update = False

            # Check and fix sent_at
            if email.sent_at and email.sent_at.tzinfo is None:
                email.sent_at = pytz.UTC.localize(email.sent_at)
                needs_update = True

            # Check and fix event timestamps
            for event in email.events:
                if 'timestamp' in event:
                    # Parse timestamp string
                    from datetime import datetime
                    ts = datetime.fromisoformat(event['timestamp'])
                    if ts.tzinfo is None:
                        # Make timezone-aware
                        ts = pytz.UTC.localize(ts)
                        event['timestamp'] = ts.isoformat()
                        needs_update = True

            if needs_update:
                emails_to_fix.append(email)

        if emails_to_fix:
            self.stdout.write(f"Fixing {len(emails_to_fix)} emails...")
            for email in emails_to_fix:
                email.save(update_fields=['sent_at', 'events', 'updated_at'])
            self.stdout.write(self.style.SUCCESS(f"✓ Fixed {len(emails_to_fix)} emails"))
        else:
            self.stdout.write(self.style.SUCCESS("✓ No emails need fixing"))
