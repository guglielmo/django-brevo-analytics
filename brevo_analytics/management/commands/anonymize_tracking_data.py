"""
Remove per-recipient open/click data already stored (Garante guidelines on
tracking pixels in emails, #20).

For every email:
- deletes the 'opened' and 'clicked' events and recomputes current_status;
- removes the raw Brevo payload and identifying fields (ip, user_agent,
  url, link) from all remaining events. Bounce type and reason are kept.

Open/click totals of the affected messages are kept as aggregate data
(tracking_totals_frozen) when the message has at least
MIN_AGGREGATE_RECIPIENTS delivered emails (default 10): below that, a total
would tell who opened. update_stats() stops recomputing kept totals from the
events; rates are still recomputed on current deliveries. Totals are a
snapshot taken the first time a message is cleaned.
With --discard-totals no totals are kept, and totals kept by previous runs
are discarded too.

Emails are processed in batches, each in its own transaction with the rows
locked, so the webhook can keep running: an event added meanwhile is not
overwritten.

Brevo's "Anonymous email tracking" is not retroactive: run this once after
enabling it, and after any import made with ANONYMOUS_TRACKING=False.
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from brevo_analytics.models import BrevoMessage, BrevoEmail
from brevo_analytics.tracking import (
    TRACKING_EVENT_TYPES,
    get_min_aggregate_recipients,
    is_anonymous_tracking,
    strip_tracking_data,
)

BATCH_SIZE = 500


def _has_tracking_events(events):
    return any(e.get('type') in TRACKING_EVENT_TYPES for e in events)


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
            help='Do not keep open/click totals and rates, and discard those kept by previous runs'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Run even with ANONYMOUS_TRACKING = False (per-recipient tracking enabled)'
        )
        parser.add_argument(
            '--no-input', '--noinput',
            action='store_false',
            dest='interactive',
            help='Do not ask for confirmation'
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

        if not is_anonymous_tracking() and not options['force']:
            self.stdout.write(
                self.style.ERROR(
                    'ANONYMOUS_TRACKING is False: per-recipient tracking is enabled and this '
                    'command would delete its data.\nSet ANONYMOUS_TRACKING = True, or pass --force.'
                )
            )
            return

        dry_run = options['dry_run']
        discard_totals = options['discard_totals']
        min_recipients = get_min_aggregate_recipients()

        # Tutte le email, anche dei domini interni e dei mittenti non autorizzati:
        # i dati da togliere sono ovunque
        all_emails = BrevoEmail.objects.all_unfiltered()

        # 1. Ricognizione, in sola lettura: in memoria solo gli id dei messaggi
        emails_to_clean = 0
        tracked_message_ids = set()
        for message_id, events in all_emails.values_list('message_id', 'events').iterator(chunk_size=BATCH_SIZE):
            if strip_tracking_data(events) != events:
                emails_to_clean += 1
                if _has_tracking_events(events):
                    tracked_message_ids.add(message_id)

        previously_kept_ids = set()
        if discard_totals:
            previously_kept_ids = set(
                BrevoMessage.objects.filter(tracking_totals_frozen=True).values_list('id', flat=True)
            )

        self.stdout.write(f"\n🔒 Emails with tracking data: {emails_to_clean:,}")
        self.stdout.write(f"   Messages with open/click events: {len(tracked_message_ids):,}")
        if discard_totals:
            self.stdout.write(
                f"   Open/click totals: discarded (plus {len(previously_kept_ids):,} kept by previous runs)"
            )
        else:
            self.stdout.write(
                f"   Open/click totals: kept as aggregate data for messages with at least "
                f"{min_recipients} delivered emails"
            )

        if dry_run:
            self.stdout.write("\n🔍 DRY RUN - No data modified\n")
            return

        if not emails_to_clean and not previously_kept_ids:
            self.stdout.write(self.style.SUCCESS("\n✅ Nothing to clean\n"))
            return

        if options['interactive']:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  This will permanently remove open/click data from {emails_to_clean:,} emails."
                )
            )
            if input("Type 'yes' to continue: ").lower() != 'yes':
                self.stdout.write(self.style.WARNING("Operation cancelled."))
                return

        # 2. Totali: fotografati prima di cancellare gli eventi. I messaggi già
        #    conservati non si toccano: i loro totali sono quelli della prima volta.
        kept = 0
        for message in BrevoMessage.objects.filter(id__in=tracked_message_ids, tracking_totals_frozen=False):
            with transaction.atomic():
                message.update_stats()
                if not discard_totals and message.total_delivered >= min_recipients:
                    BrevoMessage.objects.filter(pk=message.pk).update(tracking_totals_frozen=True)
                    kept += 1
        if previously_kept_ids:
            BrevoMessage.objects.filter(id__in=previously_kept_ids).update(tracking_totals_frozen=False)

        # 3. Pulizia a blocchi: ogni blocco nella sua transazione, con le righe
        #    bloccate e rilette, così un evento salvato dal webhook nel frattempo
        #    non viene sovrascritto
        cleaned = 0
        changed_message_ids = set(tracked_message_ids) | previously_kept_ids
        last_pk = None
        while True:
            page = all_emails.order_by('pk')
            if last_pk is not None:
                page = page.filter(pk__gt=last_pk)
            pks = list(page.values_list('pk', flat=True)[:BATCH_SIZE])
            if not pks:
                break
            last_pk = pks[-1]

            with transaction.atomic():
                batch = (
                    all_emails.select_for_update()
                    .filter(pk__in=pks)
                    .only('id', 'message_id', 'events', 'current_status', 'updated_at')
                )
                now = timezone.now()
                changed = []
                for email in batch:
                    events = strip_tracking_data(email.events)
                    if events == email.events:
                        continue
                    if _has_tracking_events(email.events):
                        changed_message_ids.add(email.message_id)
                    email.events = events
                    email.update_status()
                    email.updated_at = now  # bulk_update non applica auto_now
                    changed.append(email)
                if changed:
                    all_emails.bulk_update(changed, ['events', 'current_status', 'updated_at'])
                cleaned += len(changed)

        # 4. Statistiche dei messaggi toccati
        for message in BrevoMessage.objects.filter(id__in=changed_message_ids):
            message.refresh_stats()

        self.stdout.write(f"\n✓ Cleaned {cleaned:,} emails")
        if discard_totals:
            self.stdout.write(f"✓ Discarded open/click totals of {len(changed_message_ids):,} messages")
        else:
            self.stdout.write(
                f"✓ Kept open/click totals of {kept:,} messages "
                f"({len(tracked_message_ids) - kept:,} below {min_recipients} delivered emails or already kept)"
            )
        self.stdout.write(f"✓ Recalculated statistics for {len(changed_message_ids):,} messages")
        self.stdout.write(self.style.SUCCESS("\n✅ Tracking data anonymized!\n"))
