#!/usr/bin/env python3
"""
Enrich bounce events with bounce_reason from Brevo API.

This script:
1. Uses DuckDB to JOIN emails_import.csv + email_events_import.csv
2. Extracts bounce events with their brevo_email_id
3. Queries Brevo API with messageId filter (targeted, not bulk)
4. Updates bounce_reason in email_events_import.csv

Usage:
    python enrich_bounce_reasons.py <BREVO_API_KEY>

Prerequisites:
    - emails_import.csv and email_events_import.csv must exist
    - Valid Brevo API key with read access
    - duckdb package installed: pip install duckdb

Output:
    - email_events_import.csv (updated with bounce_reason)
"""

import csv
import sys
import time
from typing import List, Tuple, Optional
import requests

try:
    import duckdb
except ImportError:
    print("Error: duckdb package not installed", file=sys.stderr)
    print("Install with: pip install duckdb", file=sys.stderr)
    sys.exit(1)

BREVO_API_BASE = "https://api.brevo.com/v3"

def fetch_bounce_reason(
    api_key: str,
    brevo_message_id: str,
    bounce_type: str,
    event_timestamp: str
) -> Optional[str]:
    """
    Fetch bounce reason from Brevo API for a specific message.

    Args:
        api_key: Brevo API key
        brevo_message_id: Brevo message ID (e.g., <123456@smtp-relay.mailin.fr>)
        bounce_type: 'hard' or 'soft'
        event_timestamp: ISO timestamp of the bounce event

    Returns:
        Bounce reason string or None if not found
    """
    from datetime import datetime, timedelta

    # Map bounce_type to API event name
    api_event = 'hardBounces' if bounce_type == 'hard' else 'softBounces'

    # Parse timestamp to create search window (Brevo requires YYYY-MM-DD)
    try:
        event_dt = datetime.fromisoformat(event_timestamp.replace('Z', '+00:00'))
        # Search window: same day ± 1 day for safety
        start_date = (event_dt - timedelta(days=1)).strftime('%Y-%m-%d')
        end_date = (event_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    except Exception as e:
        print(f"    Warning: Could not parse timestamp {event_timestamp}: {e}", file=sys.stderr)
        # Fallback: January 2026
        start_date = '2026-01-01'
        end_date = '2026-01-31'

    headers = {
        'api-key': api_key,
        'accept': 'application/json'
    }

    # Clean message ID (remove angle brackets if present)
    clean_mid = brevo_message_id.strip('<>').strip()

    params = {
        'event': api_event,
        'messageId': clean_mid,  # TARGETED QUERY - only this message
        'startDate': start_date,
        'endDate': end_date,
        'limit': 10,  # Should only be 1 result
        'sort': 'desc'
    }

    try:
        response = requests.get(
            f"{BREVO_API_BASE}/smtp/statistics/events",
            headers=headers,
            params=params,
            timeout=10
        )

        if response.status_code == 429:
            print(f"    Rate limited (429), waiting 5s...", file=sys.stderr)
            time.sleep(5)
            return fetch_bounce_reason(api_key, brevo_message_id, bounce_type, event_timestamp)

        if response.status_code == 401:
            print(f"    ERROR: Invalid API key (401)", file=sys.stderr)
            sys.exit(1)

        if response.status_code != 200:
            print(f"    API error {response.status_code}: {response.text[:100]}", file=sys.stderr)
            return None

        data = response.json()
        events = data.get('events', [])

        if not events:
            print(f"    No events found for messageId={clean_mid[:40]}...", file=sys.stderr)
            return None

        # Get reason from first matching event
        event = events[0]
        reason = event.get('reason', event.get('error', ''))

        if reason:
            return reason
        else:
            print(f"    No 'reason' field in API response", file=sys.stderr)
            return None

    except requests.exceptions.Timeout:
        print(f"    Timeout fetching from API", file=sys.stderr)
        return None
    except Exception as e:
        print(f"    Error fetching from API: {e}", file=sys.stderr)
        return None

def get_bounce_events_with_message_id(
    emails_csv: str = 'emails_import.csv',
    events_csv: str = 'email_events_import.csv'
) -> List[Tuple[str, str, str, str]]:
    """
    Use DuckDB to JOIN CSVs and extract bounce events.

    Returns:
        List of tuples: (event_id, brevo_message_id, bounce_type, event_timestamp)
    """
    print("Using DuckDB to JOIN CSVs and extract bounce events...")

    try:
        # Create SQL query with JOIN
        query = f"""
        SELECT
            ee.id as event_id,
            e.brevo_email_id,
            ee.bounce_type,
            ee.event_timestamp
        FROM read_csv_auto('{events_csv}') ee
        INNER JOIN read_csv_auto('{emails_csv}') e
            ON ee.email_id = e.id
        WHERE ee.event_type = 'bounced'
          AND (ee.bounce_reason IS NULL OR ee.bounce_reason = '')
        ORDER BY ee.event_timestamp DESC
        """

        # Execute query
        result = duckdb.sql(query).fetchall()

        print(f"  Found {len(result)} bounce events to enrich")
        return result

    except Exception as e:
        print(f"Error executing DuckDB query: {e}", file=sys.stderr)
        sys.exit(1)

def update_events_csv(
    events_csv: str,
    enriched_data: dict
):
    """
    Update email_events_import.csv with enriched bounce_reason data.

    Args:
        events_csv: Path to email_events_import.csv
        enriched_data: Dict {event_id: bounce_reason}
    """
    print(f"\nUpdating {events_csv} with enriched data...")

    # Read all events
    events = []
    with open(events_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        events = list(reader)

    # Update bounce_reason for enriched events
    updated_count = 0
    for event in events:
        event_id = event['id']
        if event_id in enriched_data:
            event['bounce_reason'] = enriched_data[event_id]
            updated_count += 1

    # Write back
    with open(events_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)

    print(f"✓ Updated {updated_count} records in {events_csv}")

def enrich_bounce_events(
    api_key: str,
    emails_csv: str = 'emails_import.csv',
    events_csv: str = 'email_events_import.csv'
):
    """
    Main enrichment logic:
    1. DuckDB JOIN to get bounce events with brevo_message_id
    2. Query Brevo API for each bounce (targeted by messageId)
    3. Update CSV with bounce_reason
    """
    print()

    # Step 1: Get bounce events via DuckDB JOIN
    bounce_events = get_bounce_events_with_message_id(emails_csv, events_csv)
    print()

    if len(bounce_events) == 0:
        print("✓ No bounce events need enrichment. Done!")
        return

    # Step 2: Query Brevo API for each bounce
    print("Querying Brevo API for bounce reasons...")
    print("-" * 60)

    enriched_data = {}  # {event_id: bounce_reason}
    enriched_count = 0
    failed_count = 0

    for i, (event_id, brevo_message_id, bounce_type, event_timestamp) in enumerate(bounce_events, 1):
        print(f"[{i}/{len(bounce_events)}] Bounce {bounce_type} - messageId={brevo_message_id[:50]}...")

        # Fetch reason from API (targeted query by messageId)
        reason = fetch_bounce_reason(
            api_key,
            brevo_message_id,
            bounce_type,
            event_timestamp
        )

        if reason:
            enriched_data[event_id] = reason
            enriched_count += 1
            print(f"    ✓ Reason: {reason[:80]}")
        else:
            failed_count += 1
            print(f"    ✗ Could not fetch reason")

        # Rate limiting: wait 200ms between requests (max 5 req/sec)
        time.sleep(0.2)

    print("-" * 60)

    # Step 3: Update CSV with enriched data
    if enriched_data:
        update_events_csv(events_csv, enriched_data)

    # Summary
    print()
    print("=" * 60)
    print("Enrichment Summary:")
    print(f"  Total bounce events:  {len(bounce_events)}")
    print(f"  Enriched with reason: {enriched_count}")
    print(f"  Failed to fetch:      {failed_count}")
    print("=" * 60)
    print()

    if enriched_count > 0:
        print("✓ Success! You can now import email_events_import.csv to Supabase")
        print("  with bounce_reason populated for bounce events.")
    else:
        print("⚠ Warning: No bounce reasons were fetched.")
        print("  Check your API key and network connection.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python enrich_bounce_reasons.py <BREVO_API_KEY>")
        print()
        print("Get your API key from: https://app.brevo.com/settings/keys/api")
        print()
        print("Prerequisites:")
        print("  1. Run transform_csv_to_supabase.py first")
        print("  2. emails_import.csv and email_events_import.csv must exist")
        print("  3. DuckDB installed: pip install duckdb")
        print()
        print("Example:")
        print("  python enrich_bounce_reasons.py xkeysib-abc123...")
        print()
        sys.exit(1)

    api_key = sys.argv[1]

    print()
    print("=" * 60)
    print("Brevo Bounce Reason Enrichment")
    print("=" * 60)
    print()
    print("Strategy:")
    print("  1. DuckDB JOIN: emails_import.csv + email_events_import.csv")
    print("  2. Query Brevo API with messageId filter (targeted)")
    print("  3. Update bounce_reason in email_events_import.csv")

    enrich_bounce_events(api_key)

if __name__ == '__main__':
    main()
