# Critical Security Fix - Version 0.2.1

## Severity: HIGH

**Issue**: Multi-tenant data contamination vulnerability

## Problem Description

The webhook handler was accepting events from **ANY sender** on the Brevo account, not just authorized senders. In a shared Brevo account scenario, this allowed:

1. **Data Contamination**: Webhook events from other clients/projects on the same Brevo account were being saved to your database
2. **Incorrect Statistics**: Analytics included emails from unauthorized campaigns
3. **Privacy Concerns**: You could see email data from other clients using the same Brevo account

## Root Cause

The webhook in `brevo_analytics/webhooks.py` was only:
- Verifying HMAC signature (if configured)
- Filtering internal recipient domains
- **NOT checking if the sender was authorized**

## Solution Implemented

### 1. Webhook Sender Filtering (Critical)

**File**: `brevo_analytics/webhooks.py`

Added sender verification before processing any event:

```python
# Extract sender from payload
sender = payload.get('sender') or payload.get('from', '')

# CRITICAL: Verify sender is authorized
allowed_senders = config.get('ALLOWED_SENDERS', ['info@infoparlamento.it'])

if allowed_senders and sender:
    if sender not in allowed_senders:
        logger.warning(f"Ignoring webhook event from unauthorized sender: {sender}")
        return JsonResponse({'status': 'ignored', 'reason': 'unauthorized_sender'})
```

### 2. Database Model Update

**File**: `brevo_analytics/models.py`

Added `sender_email` field to BrevoEmail model:

```python
sender_email = models.EmailField(
    db_index=True,
    null=True,
    blank=True,
    help_text="Sender email address (for multi-tenant filtering)"
)
```

### 3. ORM-Level Sender Filtering

**File**: `brevo_analytics/models.py`

Updated custom QuerySet and Manager to automatically filter by authorized senders:

```python
def filter_by_allowed_senders(self):
    """Filter to include only emails from authorized senders"""
    allowed_senders = config.get('ALLOWED_SENDERS', [])

    # Include emails with sender_email in allowed list OR NULL (backward compatibility)
    filter_q = Q(sender_email__isnull=True)
    for sender in allowed_senders:
        filter_q |= Q(sender_email__iexact=sender)

    return self.filter(filter_q)
```

All `BrevoEmail.objects` queries now automatically exclude unauthorized senders.

### 4. Import Command Update

**File**: `brevo_analytics/management/commands/import_brevo_logs.py`

Updated CSV import to:
- Extract sender from 'frm' column
- Populate `sender_email` field during import
- Existing `ALLOWED_SENDERS` filtering continues to work

### 5. Verification Command

**File**: `brevo_analytics/management/commands/verify_senders.py`

New command to:
- Identify potentially unauthorized emails in existing database
- Show statistics and suspicious patterns
- Guide manual cleanup

## Impact

### Before Fix
- Webhook accepted ALL events from Brevo, regardless of sender
- Database could contain emails from other clients' campaigns
- Statistics were contaminated with unauthorized data
- No way to distinguish your emails from others'

### After Fix
- Webhook rejects events from unauthorized senders
- New emails are tagged with sender_email
- All queries automatically filter by ALLOWED_SENDERS
- Clean separation of multi-tenant data

## Migration Steps

### Required Configuration

```python
BREVO_ANALYTICS = {
    # CRITICAL: Define your authorized sender(s)
    'ALLOWED_SENDERS': ['info@infoparlamento.it'],  # REQUIRED
    # ... other settings
}
```

### Database Migration

```bash
# Create migration for new sender_email field
python manage.py makemigrations brevo_analytics

# Apply migration
python manage.py migrate brevo_analytics
```

### Verify Existing Data

```bash
# Check for potentially unauthorized emails
python manage.py verify_senders

# If contaminated data found, review and clean manually
# Option 1: Re-import from CSV (recommended - rebuilds with sender filtering)
python manage.py import_brevo_logs file.csv --clear

# Option 2: Manual cleanup via Django shell
```

## Backward Compatibility

- `sender_email` field is nullable - existing records remain valid
- Queries include `sender_email IS NULL` for compatibility
- Webhook logs warning if no sender info in payload
- Import works with or without sender data

## Security Recommendations

1. **Always configure ALLOWED_SENDERS** - Never rely on default
2. **Re-import historical data** after applying fix to tag sender_email
3. **Review existing data** with `verify_senders` command
4. **Monitor webhook logs** for rejected unauthorized events

## Testing

### Verify Webhook Filtering

```bash
# Test with unauthorized sender
curl -X POST http://localhost:8000/admin/brevo_analytics/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "event": "delivered",
    "message-id": "test123",
    "email": "test@example.com",
    "sender": "unauthorized@other-client.com",
    "ts_event": 1737468000
  }'

# Should return: {"status": "ignored", "reason": "unauthorized_sender"}
```

### Verify ORM Filtering

```python
from brevo_analytics.models import BrevoEmail

# Should only show your emails (sender_email = info@infoparlamento.it or NULL)
BrevoEmail.objects.count()

# Should show ALL emails (including unauthorized)
BrevoEmail.objects.all_unfiltered().count()
```

## Files Changed

- `brevo_analytics/models.py` - Added sender_email field and filtering
- `brevo_analytics/webhooks.py` - Added sender verification
- `brevo_analytics/management/commands/import_brevo_logs.py` - Populate sender_email
- `brevo_analytics/management/commands/verify_senders.py` - New verification tool
- `CLAUDE.md` - Updated documentation with security notes

## Credits

Fixed critical multi-tenant security vulnerability in webhook processing and data storage.

---

**Version**: 0.2.1
**Date**: 2026-01-27
**Severity**: HIGH
**Status**: FIXED
