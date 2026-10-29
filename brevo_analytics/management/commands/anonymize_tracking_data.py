"""
Remove per-recipient open/click data already stored (Garante guidelines on
tracking pixels in emails, #20).

For every email:
- deletes the 'opened' and 'clicked' events and recomputes current_status;
- removes the raw Brevo payload and identifying fields (ip, user_agent,
  url, link) from all remaining events. Bounce type and reason are kept.

By default the open/click totals and rates of the affected messages are kept
as aggregate data (tracking_totals_frozen): update_stats() stops recomputing
them. With --discard-totals they are recomputed from the cleaned events (0).

Brevo's "Anonymous email tracking" is not retroactive: run this once after
enabling it, and after any import made with ANONYMOUS_TRACKING=False.
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from brevo_analytics.models import BrevoMessage, BrevoEmail
from brevo_analytics.tracking import TRACKING_EVENT_TYPES, strip_tracking_data

BATCH_SIZE = 500


class Command(BaseCommand):
    help = 'Remove per-recipient open/click data (opens, clicks, IP, user agent, links, raw payloads)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without modifying data'
        )
        parser.add_argument(
            '--discard-totals',
            action='store_true',
            help='Do not keep historical open/click totals and rates (they become 0)'
        )

    def handle(self, *args, **options):
        # Check if blacklist-only mode is enabled
        brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
        if brevo_config.get('BLACKLIST_ONLY_MODE', False):
            self.stdout.write(
                self.style.ERROR(
                    'This command is disabled in BLACKLIST_ONLY_MODE.\n'
                    'Database tables are unused in this mode. '
                    'Use Blacklist Management to access data from Brevo API.'
                )
            )
            return

        dry_run = options['dry_run']
        discard_totals = options['discard_totals']

        # Tutte le email, anche dei domini interni e dei mittenti non autorizzati:
        # i dati da togliere sono ovunque
        emails = BrevoEmail.objects.all_unfiltered().only('id', 'message_id', 'events', 'current_status')

        to_update = []
        affected_message_ids = set()
        for email in emails.iterator(chunk_size=BATCH_SIZE):
            cleaned = strip_tracking_data(email.events)
            if cleaned == email.events:
                continue
            if any(e.get('type') in TRACKING_EVENT_TYPES for e in email.events):
                affected_message_ids.add(email.message_id)
            email.events = cleaned
            to_update.append(email)

        self.stdout.write(f"\n🔒 Emails with tracking data: {len(to_update):,}")
        self.stdout.write(f"   Messages with open/click events: {len(affected_message_ids):,}")
        self.stdout.write(
            "   Open/click totals: "
            + ("discarded (recomputed from cleaned events)" if discard_totals
               else "kept as aggregate data")
        )

        if dry_run:
            self.stdout.write("\n🔍 DRY RUN - No data modified\n")
            return

        if not to_update:
            self.stdout.write(self.style.SUCCESS("\n✅ Nothing to clean\n"))
            return

        with transaction.atomic():
            messages = BrevoMessage.objects.filter(id__in=affected_message_ids)

            if not discard_totals:
                # Totali aggiornati prima di cancellare gli eventi, poi congelati
                for message in messages.filter(tracking_totals_frozen=False):
                    message.update_stats()
                messages.update(tracking_totals_frozen=True)
            else:
                messages.update(tracking_totals_frozen=False)

            for email in to_update:
                email.update_status()
            BrevoEmail.objects.all_unfiltered().bulk_update(
                to_update, ['events', 'current_status'], batch_size=BATCH_SIZE
            )

            for message in messages:
                message.refresh_stats()

        self.stdout.write(f"\n✓ Cleaned {len(to_update):,} emails")
        self.stdout.write(f"✓ Recalculated statistics for {len(affected_message_ids):,} messages")
        self.stdout.write(self.style.SUCCESS("\n✅ Tracking data anonymized!\n"))
