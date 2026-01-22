#!/usr/bin/env python3
"""
Test Brevo API with a hard bounce from January 5, 2026.
Try different query variations to find what works.
"""

import sys
import requests
import json

if len(sys.argv) < 2:
    print("Usage: python test_jan5_bounce.py <BREVO_API_KEY>")
    sys.exit(1)

api_key = sys.argv[1]

# Hard bounce from January 5, 2026
message_id = "202601050823.76883290496@smtp-relay.mailin.fr"
email = "mattei@consiglionazionale-giovani.it"

headers = {
    'api-key': api_key,
    'accept': 'application/json'
}

print("=" * 70)
print("Testing Brevo API with Hard Bounce from January 5, 2026")
print("=" * 70)
print(f"messageId: {message_id}")
print(f"email: {email}")
print()

# Test 1: Query by messageId only
print("Test 1: Query by messageId (no email filter)")
print("-" * 70)

params1 = {
    'event': 'hardBounces',
    'messageId': message_id,
    'startDate': '2026-01-04',
    'endDate': '2026-01-06',
    'limit': 10
}

response1 = requests.get(
    "https://api.brevo.com/v3/smtp/statistics/events",
    headers=headers,
    params=params1
)

print(f"URL: https://api.brevo.com/v3/smtp/statistics/events?{requests.compat.urlencode(params1)}")
print(f"Status: {response1.status_code}")

if response1.status_code == 200:
    data1 = response1.json()
    events1 = data1.get('events', [])
    print(f"Found: {len(events1)} events")
    if events1:
        print(f"  First event reason: {events1[0].get('reason', 'N/A')[:100]}...")
else:
    print(f"Error: {response1.text}")

print()

# Test 2: Query by email only (no messageId)
print("Test 2: Query by email only (no messageId)")
print("-" * 70)

params2 = {
    'event': 'hardBounces',
    'email': email,
    'startDate': '2026-01-04',
    'endDate': '2026-01-06',
    'limit': 10
}

response2 = requests.get(
    "https://api.brevo.com/v3/smtp/statistics/events",
    headers=headers,
    params=params2
)

print(f"URL: https://api.brevo.com/v3/smtp/statistics/events?{requests.compat.urlencode(params2)}")
print(f"Status: {response2.status_code}")

if response2.status_code == 200:
    data2 = response2.json()
    events2 = data2.get('events', [])
    print(f"Found: {len(events2)} events")
    if events2:
        for i, event in enumerate(events2[:3], 1):
            print(f"  Event {i}:")
            print(f"    messageId: {event.get('messageId', 'N/A')}")
            print(f"    reason: {event.get('reason', 'N/A')[:80]}...")
else:
    print(f"Error: {response2.text}")

print()

# Test 3: Query with messageId WITH angle brackets
print("Test 3: Query with messageId including angle brackets")
print("-" * 70)

params3 = {
    'event': 'hardBounces',
    'messageId': f"<{message_id}>",  # WITH brackets
    'startDate': '2026-01-04',
    'endDate': '2026-01-06',
    'limit': 10
}

response3 = requests.get(
    "https://api.brevo.com/v3/smtp/statistics/events",
    headers=headers,
    params=params3
)

print(f"URL: https://api.brevo.com/v3/smtp/statistics/events?{requests.compat.urlencode(params3)}")
print(f"Status: {response3.status_code}")

if response3.status_code == 200:
    data3 = response3.json()
    events3 = data3.get('events', [])
    print(f"Found: {len(events3)} events")
    if events3:
        print(f"  First event reason: {events3[0].get('reason', 'N/A')[:100]}...")
else:
    print(f"Error: {response3.text}")

print()

# Test 4: Query by date range only (no filters)
print("Test 4: Query by date range only (no email/messageId filters)")
print("-" * 70)

params4 = {
    'event': 'hardBounces',
    'startDate': '2026-01-05',
    'endDate': '2026-01-05',
    'limit': 5
}

response4 = requests.get(
    "https://api.brevo.com/v3/smtp/statistics/events",
    headers=headers,
    params=params4
)

print(f"URL: https://api.brevo.com/v3/smtp/statistics/events?{requests.compat.urlencode(params4)}")
print(f"Status: {response4.status_code}")

if response4.status_code == 200:
    data4 = response4.json()
    events4 = data4.get('events', [])
    print(f"Found: {len(events4)} events")
    if events4:
        print("  Checking if our messageId is in these events...")
        for event in events4:
            if message_id in event.get('messageId', ''):
                print(f"  ✓ Found our message!")
                print(f"    reason: {event.get('reason', 'N/A')[:100]}...")
                break
        else:
            print(f"  ✗ Our messageId not in first {len(events4)} events")
else:
    print(f"Error: {response4.text}")

print()
print("=" * 70)
print("Summary:")
print("  If Test 2 (email filter) or Test 4 (date only) worked,")
print("  then the data is in the API but messageId filtering doesn't work.")
print("=" * 70)
