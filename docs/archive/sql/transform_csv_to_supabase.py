#!/usr/bin/env python3
"""
Transform Brevo CSV logs to Supabase-compatible CSV format.

Usage:
    python transform_csv_to_supabase.py brevo_logs_infoparlamento.csv

Output:
    - emails_import.csv (for brevo_analytics.emails table)
    - email_events_import.csv (for brevo_analytics.email_events table)
"""

import csv
import sys
from datetime import datetime
from typing import Dict, List, Set
import uuid

# Event type mapping: Brevo Italian → Our schema
EVENT_MAPPING = {
    'Inviata': 'sent',
    'Consegnata': 'delivered',
    'Aperta': 'opened',
    'Prima apertura': 'opened',  # Also map to opened
    'Cliccata': 'clicked',
    'Bloccata': 'blocked',
    'Rinviata': 'deferred',
    'Soft bounce': 'bounced',
    'Hard bounce': 'bounced',
    'Caricata per procura': 'opened',  # Proxy open → opened
}

def parse_timestamp(ts_str: str) -> str:
    """Convert '21-01-2026 10:22:05' to ISO format."""
    try:
        dt = datetime.strptime(ts_str, '%d-%m-%Y %H:%M:%S')
        return dt.isoformat()
    except Exception as e:
        print(f"Error parsing timestamp '{ts_str}': {e}", file=sys.stderr)
        return ts_str

def determine_bounce_type(st_text: str) -> str:
    """Determine bounce type from status text."""
    if st_text == 'Hard bounce':
        return 'hard'
    elif st_text == 'Soft bounce':
        return 'soft'
    return ''

def extract_emails(input_csv: str, client_id: str) -> Dict[str, Dict]:
    """
    Extract unique emails from ALL events (not just 'Inviata').

    For each unique message_id, we:
    1. Prefer 'Inviata' event for sent_at timestamp
    2. Fall back to earliest event timestamp if 'Inviata' not present

    Returns dict: {message_id: email_data}
    """
    # First pass: collect all events per message_id
    emails_events = {}

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            mid = row['mid']

            if mid not in emails_events:
                emails_events[mid] = []

            emails_events[mid].append(row)

    # Second pass: create email records
    emails = {}

    for mid, events in emails_events.items():
        # Find 'Inviata' event for sent_at
        sent_event = next((e for e in events if e['st_text'] == 'Inviata'), None)

        # If no 'Inviata', use earliest event
        if not sent_event:
            sent_event = min(events, key=lambda e: e['ts'])

        emails[mid] = {
            'id': str(uuid.uuid4()),
            'client_id': client_id,
            'brevo_email_id': mid,
            'recipient_email': sent_event['email'],
            'subject': sent_event['sub'],
            'sent_at': parse_timestamp(sent_event['ts'])
        }

    return emails

def extract_events(input_csv: str, emails: Dict[str, Dict]) -> List[Dict]:
    """
    Extract all events and link them to emails via message_id.

    Returns list of event dicts.
    """
    events = []

    # Create reverse lookup: message_id → email.id
    mid_to_email_id = {mid: data['id'] for mid, data in emails.items()}

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            mid = row['mid']
            st_text = row['st_text']

            # Skip if email doesn't exist (shouldn't happen, but defensive)
            if mid not in mid_to_email_id:
                print(f"Warning: Event for unknown email {mid}, skipping", file=sys.stderr)
                continue

            # Map event type
            event_type = EVENT_MAPPING.get(st_text)
            if not event_type:
                print(f"Warning: Unknown event type '{st_text}', skipping", file=sys.stderr)
                continue

            # Determine bounce type if applicable
            bounce_type = determine_bounce_type(st_text)

            # Extract click URL if available
            click_url = None
            if st_text == 'Cliccata' and row['link'] != 'NA':
                click_url = row['link']

            events.append({
                'id': str(uuid.uuid4()),
                'email_id': mid_to_email_id[mid],
                'event_type': event_type,
                'event_timestamp': parse_timestamp(row['ts']),
                'bounce_type': bounce_type or None,
                'bounce_reason': None,  # Not available in CSV
                'click_url': click_url
            })

    return events

def write_emails_csv(emails: Dict[str, Dict], output_file: str):
    """Write emails to CSV file."""
    fieldnames = [
        'id', 'client_id', 'brevo_email_id', 'recipient_email',
        'subject', 'sent_at'
    ]

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(emails.values())

    print(f"✓ Wrote {len(emails)} emails to {output_file}")

def write_events_csv(events: List[Dict], output_file: str):
    """Write events to CSV file."""
    fieldnames = [
        'id', 'email_id', 'event_type', 'event_timestamp',
        'bounce_type', 'bounce_reason', 'click_url'
    ]

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)

    print(f"✓ Wrote {len(events)} events to {output_file}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python transform_csv_to_supabase.py <input_csv> [client_id]")
        print("Example: python transform_csv_to_supabase.py brevo_logs.csv abc-123-def-456")
        sys.exit(1)

    input_csv = sys.argv[1]

    # Get client_id from command line or use placeholder
    client_id = sys.argv[2] if len(sys.argv) > 2 else 'REPLACE_WITH_CLIENT_UUID'

    if client_id == 'REPLACE_WITH_CLIENT_UUID':
        print("⚠️  Warning: Using placeholder client_id. Replace before importing!")
        print("    Run with: python transform_csv_to_supabase.py input.csv <your-client-uuid>")
        print()

    print(f"Processing {input_csv}...")
    print(f"Client ID: {client_id}")
    print()

    # Extract emails (from all events, preferring "Inviata" for sent_at)
    print("Step 1: Extracting unique emails from all events...")
    emails = extract_emails(input_csv, client_id)
    print(f"  Found {len(emails)} unique emails")
    print()

    # Extract all events
    print("Step 2: Extracting all events...")
    events = extract_events(input_csv, emails)
    print(f"  Found {len(events)} events")
    print()

    # Write output CSVs
    print("Step 3: Writing output CSVs...")
    write_emails_csv(emails, 'emails_import.csv')
    write_events_csv(events, 'email_events_import.csv')
    print()

    # Summary
    print("=" * 60)
    print("Summary:")
    print(f"  Emails:      {len(emails):,}")
    print(f"  Events:      {len(events):,}")
    print()
    print("Event type distribution:")
    event_counts = {}
    for event in events:
        et = event['event_type']
        event_counts[et] = event_counts.get(et, 0) + 1

    for event_type in sorted(event_counts.keys()):
        count = event_counts[event_type]
        pct = count * 100.0 / len(events)
        print(f"  {event_type:12s} {count:6,d} ({pct:5.2f}%)")
    print()

    print("Next steps:")
    print("  1. Review emails_import.csv and email_events_import.csv")
    print("  2. If using placeholder client_id, replace it in emails_import.csv")
    print("  3. Import to Supabase using SQL COPY or dashboard import")
    print("=" * 60)

if __name__ == '__main__':
    main()
