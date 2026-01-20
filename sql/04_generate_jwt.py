#!/usr/bin/env python3
"""
Generate JWT token for Brevo Analytics with client_id claim.

This script creates a JWT token that includes:
- role: service_role (required by Supabase)
- client_id: UUID of the client (for Row Level Security)
- exp: 1 year expiry

Usage:
    python 04_generate_jwt.py

Requirements:
    pip install pyjwt
"""

import jwt
from datetime import datetime, timedelta, timezone
import sys

def generate_jwt(supabase_secret: str, client_id: str, expiry_days: int = 365) -> str:
    """Generate JWT token with client_id claim."""

    # Create payload
    payload = {
        "role": "service_role",
        "client_id": client_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=expiry_days)
    }

    # Generate token
    token = jwt.encode(payload, supabase_secret, algorithm="HS256")

    return token

def main():
    print("=" * 80)
    print("🔑 Brevo Analytics JWT Generator")
    print("=" * 80)
    print()

    # Get Supabase service_role secret
    print("📋 Step 1: Get your Supabase service_role secret")
    print("   1. Go to: https://supabase.com/dashboard/project/YOUR_PROJECT/settings/api")
    print("   2. Copy the 'service_role' secret (NOT the 'anon' key)")
    print()

    supabase_secret = input("Enter your Supabase service_role secret: ").strip()

    if not supabase_secret:
        print("❌ Error: Secret cannot be empty")
        sys.exit(1)

    print()
    print("📋 Step 2: Get your client_id (UUID)")
    print("   Run 03_create_test_data.sql in Supabase SQL Editor")
    print("   Copy the Client ID from the output")
    print()

    client_id = input("Enter your client_id (UUID): ").strip()

    if not client_id:
        print("❌ Error: Client ID cannot be empty")
        sys.exit(1)

    # Validate UUID format (basic check)
    if len(client_id) != 36 or client_id.count('-') != 4:
        print("⚠️  Warning: Client ID doesn't look like a valid UUID")
        confirm = input("Continue anyway? (y/N): ").strip().lower()
        if confirm != 'y':
            sys.exit(1)

    print()
    print("📋 Step 3: Set expiry (optional)")
    expiry_input = input("Token expiry in days (default: 365): ").strip()
    expiry_days = int(expiry_input) if expiry_input else 365

    print()
    print("🔧 Generating JWT token...")

    try:
        token = generate_jwt(supabase_secret, client_id, expiry_days)

        print()
        print("=" * 80)
        print("✅ JWT Token Generated Successfully!")
        print("=" * 80)
        print()
        print("🔑 Your JWT Token:")
        print("-" * 80)
        print(token)
        print("-" * 80)
        print()
        print("📝 Next Steps:")
        print()
        print("1. Copy the token above")
        print()
        print("2. Update your Django .env file:")
        print(f"   BREVO_SUPABASE_URL=https://YOUR_PROJECT.supabase.co")
        print(f"   BREVO_JWT={token}")
        print()
        print("3. Restart your Django server")
        print()
        print("4. Test the connection with:")
        print("   curl https://YOUR_PROJECT.supabase.co/rest/v1/emails?limit=1 \\")
        print(f"     -H 'apikey: {supabase_secret}' \\")
        print(f"     -H 'Authorization: Bearer {token}'")
        print()
        print("⚠️  Security Notes:")
        print("   - Keep this token secure (never commit to git)")
        print("   - Store only in server-side Django settings")
        print(f"   - Token expires in {expiry_days} days")
        print("   - Rotate tokens periodically")
        print()

    except Exception as e:
        print(f"❌ Error generating token: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
