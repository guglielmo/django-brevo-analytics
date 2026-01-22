"""
Management command to sync sent_at timestamps from Brevo API.

This command queries Brevo's BrevoEmail Campaign API to get the exact timestamp
of when each campaign was first sent, and updates the sent_at field accordingly.

Usage:
    python manage.py sync_brevo_sent_at --api-key YOUR_API_KEY [--dry-run]
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from brevo_analytics.models import BrevoMessage
import requests
from datetime import datetime
import pytz


class Command(BaseCommand):
    help = 'Sync sent_at timestamps from Brevo API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--api-key',
            type=str,
            help='Brevo API Key (or set BREVO_API_KEY env variable)',
            default=None
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of messages to process'
        )

    def handle(self, *args, **options):
        api_key = options['api_key'] or settings.BREVO_ANALYTICS.get('API_KEY', '')

        if not api_key:
            self.stderr.write(self.style.ERROR(
                'Brevo API Key required. Use --api-key or set BREVO_API_KEY in settings'
            ))
            return

        dry_run = options['dry_run']
        limit = options['limit']

        headers = {
            'accept': 'application/json',
            'api-key': api_key
        }

        # Get messages without sent_at or with sent_at only from CSV
        messages_to_sync = BrevoMessage.objects.filter(
            sent_at__isnull=False  # We'll sync all that have data
        ).order_by('-sent_date')

        if limit:
            messages_to_sync = messages_to_sync[:limit]

        total = messages_to_sync.count()
        self.stdout.write(f"Found {total} messages to sync")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        updated_count = 0
        skipped_count = 0

        for i, message in enumerate(messages_to_sync, 1):
            self.stdout.write(f"[{i}/{total}] Processing: {message.subject} ({message.sent_date})")

            try:
                # Get first email from this message to query by email address
                first_email = message.emails.order_by('sent_at').first()
                if not first_email:
                    self.stdout.write(self.style.WARNING(
                        f"  → No emails found for this message"
                    ))
                    skipped_count += 1
                    continue

                # Query Brevo API by email address (required parameter)
                # API endpoint: GET /smtp/emails
                params = {
                    'limit': 100,
                    'sort': 'asc',
                    'email': first_email.recipient_email,
                    'startDate': str(message.sent_date),
                    'endDate': str(message.sent_date),
                }

                self.stdout.write(f"  → Querying by email: {first_email.recipient_email}")

                response = requests.get(
                    'https://api.brevo.com/v3/smtp/emails',
                    headers=headers,
                    params=params,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    emails = data.get('transactionalEmails', [])

                    # Find first email matching our subject
                    matched_email = None
                    for email in emails:
                        if email.get('subject') == message.subject:
                            matched_email = email
                            break

                    if matched_email:
                        # Get the sent timestamp
                        sent_date_str = matched_email.get('date')
                        if sent_date_str:
                            # Parse ISO format: "2026-01-08T12:02:47.000Z"
                            sent_datetime = datetime.fromisoformat(sent_date_str.replace('Z', '+00:00'))

                            if not dry_run:
                                message.sent_at = sent_datetime
                                message.save(update_fields=['sent_at', 'updated_at'])

                            self.stdout.write(self.style.SUCCESS(
                                f"  → Updated sent_at: {sent_datetime}"
                            ))
                            updated_count += 1
                        else:
                            self.stdout.write(self.style.WARNING(
                                f"  → No date in API response"
                            ))
                            skipped_count += 1
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"  → No matching email found in API"
                        ))
                        skipped_count += 1

                elif response.status_code == 401:
                    self.stderr.write(self.style.ERROR(
                        "API Key authentication failed"
                    ))
                    return
                elif response.status_code == 400:
                    try:
                        error_detail = response.json()
                        self.stdout.write(self.style.WARNING(
                            f"  → API error 400: {error_detail}"
                        ))
                    except:
                        self.stdout.write(self.style.WARNING(
                            f"  → API error 400: {response.text}"
                        ))
                    skipped_count += 1
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  → API error: {response.status_code} - {response.text[:200]}"
                    ))
                    skipped_count += 1

            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  → Error: {str(e)}"
                ))
                skipped_count += 1
                continue

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"✓ Completed: {updated_count} updated, {skipped_count} skipped"
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY RUN - Run without --dry-run to apply changes"
            ))
