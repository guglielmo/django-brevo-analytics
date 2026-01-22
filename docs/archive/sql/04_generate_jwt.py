#!/usr/bin/env python3
"""
Generate JWT token for Brevo Analytics with client_id claim.

This script creates a JWT token that includes:
- role: authenticated (standard Supabase role)
- client_id: UUID of the client (for Row Level Security)
- exp: 10 years expiry

The JWT must be signed with the Supabase JWT Secret (not service_role key).

Usage:
    python 04_generate_jwt.py

Requirements:
    pip install pyjwt
"""

import jwt
from datetime import datetime, timedelta, timezone
import sys

def generate_jwt(jwt_secret: str, client_id: str, expiry_days: int = 3650) -> str:
    """Generate JWT token with client_id claim."""

    # Create payload
    payload = {
        "role": "authenticated",
        "client_id": client_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=expiry_days)
    }

    # Generate token
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")

    return token

def main():
    print("=" * 80)
    print("🔑 Brevo Analytics JWT Generator (Modern Supabase API)")
    print("=" * 80)
    print()

    # Get Supabase JWT secret
    print("📋 Step 1: Get your Supabase JWT Secret")
    print("   1. Go to: https://supabase.com/dashboard/project/fvuhpocdeckmbdgiebfy/settings/api")
    print("   2. Scroll to 'JWT Settings' section")
    print("   3. Copy the 'JWT Secret' (long random string)")
    print("   ⚠️  This is DIFFERENT from the service_role key!")
    print()

    jwt_secret = input("Enter your Supabase JWT Secret: ").strip()

    if not jwt_secret:
        print("❌ Error: JWT Secret cannot be empty")
        sys.exit(1)

    print()
    print("📋 Step 2: Get your client_id (UUID)")
    print("   Run this SQL in Supabase SQL Editor:")
    print("   SELECT id FROM brevo_analytics.clients WHERE slug = 'infoparlamento';")
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
    expiry_input = input("Token expiry in days (default: 3650 = 10 years): ").strip()
    expiry_days = int(expiry_input) if expiry_input else 3650

    print()
    print("🔧 Generating JWT token...")

    try:
        token = generate_jwt(jwt_secret, client_id, expiry_days)

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
        print("1. Get your Supabase anon key from:")
        print("   https://supabase.com/dashboard/project/fvuhpocdeckmbdgiebfy/settings/api")
        print("   (Section: 'Project API keys' -> 'anon public')")
        print()
        print("2. Update your Django .env file:")
        print(f"   BREVO_SUPABASE_URL=https://fvuhpocdeckmbdgiebfy.supabase.co")
        print(f"   BREVO_SUPABASE_ANON_KEY=<your-anon-key>")
        print(f"   BREVO_JWT={token}")
        print()
        print("3. Restart your Django server")
        print()
        print("4. Test the connection with:")
        print(f"   curl https://fvuhpocdeckmbdgiebfy.supabase.co/rest/v1/emails?limit=1 \\")
        print(f"     -H 'apikey: <your-anon-key>' \\")
        print(f"     -H 'Authorization: Bearer {token}' \\")
        print(f"     -H 'Accept-Profile: brevo_analytics'")
        print()
        print("⚠️  Security Notes:")
        print("   - anon key is public (safe to commit)")
        print("   - JWT token is private (never commit to git)")
        print(f"   - Token expires in {expiry_days} days")
        print("   - RLS policies filter data by client_id automatically")
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
