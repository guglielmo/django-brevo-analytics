"""
Gestione blacklist Brevo da CLI.

Comandi disponibili:
- check <email>: Verifica se un'email è in blacklist
- remove <email>: Rimuove un'email dalla blacklist
- list: Lista tutte le email in blacklist Brevo
- enrich: Arricchisce email blocked nel DB con info da Brevo API
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
import requests
from urllib.parse import quote
from brevo_analytics.models import BrevoEmail


class Command(BaseCommand):
    help = 'Manage Brevo blacklist (check, remove, list, enrich)'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=['check', 'remove', 'list', 'enrich'],
            help='Action to perform'
        )
        parser.add_argument(
            'email',
            nargs='?',
            type=str,
            help='Email address (required for check/remove)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-check even if blacklist_info is cached (for enrich)'
        )

    def handle(self, *args, **options):
        action = options['action']
        email = options['email']

        # Get API key
        brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
        api_key = brevo_config.get('API_KEY', '')

        if not api_key:
            self.stderr.write(self.style.ERROR('Brevo API key not configured in settings'))
            return

        if action == 'check':
            if not email:
                self.stderr.write(self.style.ERROR('Email address required for check'))
                return
            self.check_blacklist(api_key, email)

        elif action == 'remove':
            if not email:
                self.stderr.write(self.style.ERROR('Email address required for remove'))
                return
            self.remove_from_blacklist(api_key, email)

        elif action == 'list':
            self.list_blacklist(api_key)

        elif action == 'enrich':
            force = options['force']
            self.enrich_blocked_emails(api_key, force)

    def check_blacklist(self, api_key, email_address):
        """Verifica se un'email è in blacklist"""
        self.stdout.write(f"\n🔍 Checking blacklist status for: {email_address}\n")

        headers = {
            'api-key': api_key,
            'accept': 'application/json'
        }

        try:
            response = requests.get(
                "https://api.brevo.com/v3/smtp/blockedContacts",
                headers=headers,
                params={
                    'email': email_address,
                    'limit': 50
                },
                timeout=10
            )

            if response.status_code != 200:
                self.stderr.write(f"API error: {response.status_code}")
                self.stderr.write(response.text[:200])
                return

            data = response.json()
            contacts = data.get('contacts', [])

            # Find matching contact
            matching = None
            for contact in contacts:
                if contact.get('email', '').lower() == email_address.lower():
                    matching = contact
                    break

            if not matching:
                self.stdout.write(self.style.SUCCESS(
                    f"✅ {email_address} is NOT in blacklist"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  {email_address} IS in blacklist"
                ))
                self.stdout.write(f"   Reason: {matching.get('reason', 'unknown')}")
                self.stdout.write(f"   Blocked at: {matching.get('blockedAt', 'unknown')}")
                senders = matching.get('senderEmail', [])
                if senders:
                    self.stdout.write(f"   Blocked senders: {', '.join(senders)}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))

    def remove_from_blacklist(self, api_key, email_address):
        """Rimuove un'email dalla blacklist"""
        self.stdout.write(f"\n🗑️  Removing {email_address} from blacklist...\n")

        # Confirm action
        confirm = input(f"Are you sure you want to remove {email_address} from blacklist? (yes/no): ")
        if confirm.lower() != 'yes':
            self.stdout.write("Cancelled.")
            return

        headers = {
            'api-key': api_key,
            'accept': 'application/json'
        }

        try:
            encoded_email = quote(email_address, safe='')

            response = requests.delete(
                f"https://api.brevo.com/v3/smtp/blockedContacts/{encoded_email}",
                headers=headers,
                timeout=10
            )

            if response.status_code in [200, 204]:
                self.stdout.write(self.style.SUCCESS(
                    f"✅ {email_address} removed from blacklist successfully"
                ))

                # Clear cached blacklist_info in DB
                updated = BrevoEmail.objects.filter(
                    recipient_email__iexact=email_address
                ).update(blacklist_info=None)

                if updated:
                    self.stdout.write(f"   Cleared cached blacklist info from {updated} DB records")

            elif response.status_code == 404:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  {email_address} not found in blacklist"
                ))
            else:
                self.stderr.write(f"API error: {response.status_code}")
                self.stderr.write(response.text[:200])

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))

    def list_blacklist(self, api_key):
        """Lista tutte le email in blacklist"""
        self.stdout.write("\n📋 Fetching blacklist from Brevo API...\n")

        headers = {
            'api-key': api_key,
            'accept': 'application/json'
        }

        try:
            all_contacts = []
            offset = 0
            limit = 50

            # Paginate through all contacts
            while True:
                response = requests.get(
                    "https://api.brevo.com/v3/smtp/blockedContacts",
                    headers=headers,
                    params={
                        'limit': limit,
                        'offset': offset
                    },
                    timeout=10
                )

                if response.status_code != 200:
                    self.stderr.write(f"API error: {response.status_code}")
                    self.stderr.write(response.text[:200])
                    return

                data = response.json()
                contacts = data.get('contacts', [])

                if not contacts:
                    break

                all_contacts.extend(contacts)
                offset += limit

                # Safety limit
                if len(all_contacts) >= 1000:
                    self.stdout.write("⚠️  Reached 1000 contacts limit, stopping pagination")
                    break

            self.stdout.write(f"Found {len(all_contacts)} blocked contacts:\n")

            # Group by reason
            by_reason = {}
            for contact in all_contacts:
                reason = contact.get('reason', 'unknown')
                by_reason.setdefault(reason, []).append(contact)

            for reason, contacts in sorted(by_reason.items()):
                self.stdout.write(f"\n{reason.upper()} ({len(contacts)} contacts):")
                for contact in contacts[:10]:  # Show first 10
                    email = contact.get('email', 'unknown')
                    blocked_at = contact.get('blockedAt', '')
                    self.stdout.write(f"  - {email} (blocked: {blocked_at})")

                if len(contacts) > 10:
                    self.stdout.write(f"  ... and {len(contacts) - 10} more")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))

    def enrich_blocked_emails(self, api_key, force=False):
        """Arricchisce email blocked nel DB con info da Brevo API"""
        self.stdout.write("\n🔄 Enriching blocked emails in database...\n")

        # Get all blocked emails
        if force:
            blocked_emails = BrevoEmail.objects.filter(current_status='blocked')
            self.stdout.write(f"Force mode: processing all {blocked_emails.count()} blocked emails")
        else:
            blocked_emails = BrevoEmail.objects.filter(
                current_status='blocked',
                blacklist_info__isnull=True
            )
            self.stdout.write(f"Processing {blocked_emails.count()} blocked emails without cached info")

        if not blocked_emails.exists():
            self.stdout.write(self.style.SUCCESS("✅ All blocked emails already have blacklist info"))
            return

        headers = {
            'api-key': api_key,
            'accept': 'application/json'
        }

        enriched = 0
        not_found = 0

        for email_obj in blocked_emails:
            email_address = email_obj.recipient_email

            try:
                response = requests.get(
                    "https://api.brevo.com/v3/smtp/blockedContacts",
                    headers=headers,
                    params={
                        'email': email_address,
                        'limit': 50
                    },
                    timeout=5
                )

                if response.status_code == 200:
                    data = response.json()
                    contacts = data.get('contacts', [])

                    # Find matching contact
                    matching = None
                    for contact in contacts:
                        if contact.get('email', '').lower() == email_address.lower():
                            matching = contact
                            break

                    if matching:
                        email_obj.blacklist_info = {
                            'reason': matching.get('reason', 'unknown'),
                            'blocked_at': matching.get('blockedAt', ''),
                            'senders': matching.get('senderEmail', []),
                            'checked_at': timezone.now().isoformat()
                        }
                        email_obj.save(update_fields=['blacklist_info', 'updated_at'])
                        enriched += 1
                        self.stdout.write(f"  ✓ {email_address}", ending='\r')
                    else:
                        not_found += 1

                elif response.status_code == 429:
                    self.stdout.write("\n⚠️  Rate limited, waiting 5 seconds...")
                    import time
                    time.sleep(5)
                    continue

            except Exception as e:
                self.stderr.write(f"\n  Error processing {email_address}: {e}")

        self.stdout.write(f"\n\n✅ Enriched {enriched} emails")
        if not_found > 0:
            self.stdout.write(f"⚠️  {not_found} emails blocked in DB but not found in Brevo blacklist")
