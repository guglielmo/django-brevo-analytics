"""
Fetch aggregate open/click totals from Brevo's statistics API (#22).

With ANONYMOUS_TRACKING the package no longer records opens and clicks, but
Brevo still counts them in aggregate. For every tag-grouped message sent in the
last --days days (default 90, the API limit), this command asks Brevo for the
unique opens and clicks of the message's tag, from the sending date to today,
scales them to the deliveries counted by the package, and stores them as the
message's aggregate totals (tracking_totals_frozen + tracking_totals_fetched_at).
The usual threshold applies: totals are shown only for messages with at least
MIN_AGGREGATE_RECIPIENTS delivered emails.

Opens keep arriving for days after a send: schedule this command (e.g. hourly
or daily) rather than running it once. Messages without a tag (subject
grouping) cannot be queried and are skipped.
"""

import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from brevo_analytics.brevo_rates import (
    MAX_REPORT_DAYS,
    BrevoReportError,
    fetch_aggregated_report,
    message_tag,
    report_range,
    scaled_totals,
)
from brevo_analytics.models import BrevoMessage
from brevo_analytics.tracking import is_anonymous_tracking

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fetch aggregate open/click totals from Brevo's statistics API for tag-grouped messages"

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=MAX_REPORT_DAYS,
            help=f'Messages sent in the last N days (default {MAX_REPORT_DAYS})'
        )
        parser.add_argument(
            '--message-id',
            type=int,
            help='Only this message'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Query Brevo and show the totals without saving them'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Run even with ANONYMOUS_TRACKING = False (would overwrite totals computed from events)'
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

        api_key = brevo_config.get('API_KEY', '')
        if not api_key:
            self.stdout.write(self.style.ERROR('BREVO_ANALYTICS["API_KEY"] is not set.'))
            return

        if not is_anonymous_tracking() and not options['force']:
            self.stdout.write(
                self.style.ERROR(
                    'ANONYMOUS_TRACKING is False: open/click totals come from the events and '
                    'this command would overwrite them.\nSet ANONYMOUS_TRACKING = True, or pass --force.'
                )
            )
            return

        dry_run = options['dry_run']
        today = timezone.now().date()
        messages = BrevoMessage.objects.filter(group_key__isnull=False)
        if options['message_id']:
            messages = messages.filter(id=options['message_id'])
        else:
            since = today - timezone.timedelta(days=options['days'] - 1)
            messages = messages.filter(sent_date__gte=since, sent_date__lte=today)

        updated = skipped = failed = 0
        for message in messages.order_by('-sent_date'):
            tag = message_tag(message)
            if tag is None:
                skipped += 1
                continue

            start, end = report_range(message.sent_date, today)
            try:
                report = fetch_aggregated_report(api_key, tag, start, end)
            except (BrevoReportError, requests.RequestException, ValueError) as exc:
                # HTTP diverso da 200, rete/timeout, JSON non valido
                failed += 1
                logger.warning("Brevo aggregated report failed for %s: %s", tag, exc)
                self.stdout.write(self.style.WARNING(f"  ✗ {message.subject[:60]}: {exc}"))
                continue

            opened, clicked = scaled_totals(report, message.total_delivered)
            self.stdout.write(
                f"  {message.sent_date} {message.subject[:60]:<60} | "
                f"Brevo: {report.get('delivered', 0)} delivered, "
                f"{report.get('uniqueOpens', 0)} opens, {report.get('uniqueClicks', 0)} clicks "
                f"→ {opened}/{clicked} on {message.total_delivered}"
            )
            if dry_run:
                continue

            message.total_opened = opened
            message.total_clicked = clicked
            message.tracking_totals_frozen = True
            message.tracking_totals_fetched_at = timezone.now()
            message.save(update_fields=[
                'total_opened', 'total_clicked', 'tracking_totals_frozen',
                'tracking_totals_fetched_at', 'updated_at',
            ])
            message.refresh_stats()  # tassi ricalcolati sulle consegne attuali
            updated += 1

        if dry_run:
            self.stdout.write("\n🔍 DRY RUN - No data modified")
        self.stdout.write(
            f"\n✓ {updated} updated, {skipped} skipped (no tag), {failed} failed"
        )
