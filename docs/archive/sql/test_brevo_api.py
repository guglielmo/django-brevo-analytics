#!/usr/bin/env python3
"""
Test Brevo API to see what bounce events are available.
"""

import sys
import requests
from datetime import datetime, timedelta

if len(sys.argv) < 2:
    print("Usage: python test_brevo_api.py <BREVO_API_KEY>")
    sys.exit(1)

api_key = sys.argv[1]

headers = {
    'api-key': api_key,
    'accept': 'application/json'
}

# Query soft bounces from last 7 days
today = datetime.now()
start_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
end_date = today.strftime('%Y-%m-%d')

params = {
    'event': 'softBounces',
    'startDate': start_date,
    'endDate': end_date,
    'limit': 5,
    'sort': 'desc'
}

print(f"Testing Brevo API: GET /smtp/statistics/events")
print(f"  Event: softBounces")
print(f"  Date range: {start_date} to {end_date}")
print(f"  Limit: 5")
print()

response = requests.get(
    "https://api.brevo.com/v3/smtp/statistics/events",
    headers=headers,
    params=params
)

print(f"Status: {response.status_code}")
print()

if response.status_code == 200:
    data = response.json()
    events = data.get('events', [])

    print(f"Found {len(events)} soft bounce events:")
    print()

    for i, event in enumerate(events, 1):
        print(f"Event {i}:")
        print(f"  messageId: {event.get('messageId', 'N/A')}")
        print(f"  email: {event.get('email', 'N/A')}")
        print(f"  date: {event.get('date', 'N/A')}")
        print(f"  reason: {event.get('reason', 'N/A')}")
        print()

    if len(events) == 0:
        print("No soft bounce events found in the last 7 days.")
        print("This could mean:")
        print("  1. No soft bounces occurred recently")
        print("  2. Events have been cleaned up (retention period)")
        print("  3. API key doesn't have access to this data")
else:
    print(f"Error: {response.text}")
