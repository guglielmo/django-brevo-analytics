# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-01-27

### Security

**CRITICAL SECURITY PATCH - IMMEDIATE UPDATE REQUIRED**

- **Multi-Tenant Data Contamination Vulnerability**: Fixed critical security flaw where webhook accepted events from ANY sender on shared Brevo account
  - **Impact**: Before this fix, webhook processed events from all clients sharing the same Brevo account, mixing data from different organizations into the same database
  - **Severity**: CRITICAL - Potential for unauthorized access to analytics data from other tenants
  - **Resolution**: Webhook now validates sender email against `ALLOWED_SENDERS` configuration before processing any events

### Added

- **Sender Email Tracking**: New `sender_email` field in `BrevoEmail` model
  - Captures sender address from every Brevo event
  - Enables sender-based filtering and data isolation
  - Indexed for fast queries
- **Sender Validation**: Automatic sender verification in webhook processing
  - Only events from senders in `BREVO_ANALYTICS['ALLOWED_SENDERS']` are processed
  - Unauthorized sender events are logged and rejected
  - Prevents data contamination from other tenants on shared Brevo accounts
- **ORM-Level Sender Filtering**: Enhanced `BrevoEmailManager` with automatic sender filtering
  - All database queries automatically exclude unauthorized senders
  - Transparent filtering - no code changes required in existing applications
  - Works with all Django ORM methods (filter, exclude, annotate, etc.)
- **Management Command**: `verify_senders` - Identify potentially contaminated data
  - Scans database for emails from unauthorized senders
  - Reports statistics on data contamination
  - Supports dry-run mode to preview issues before cleanup
  - Helps assess impact of vulnerability on existing installations

### Changed

- **Database Schema**: Added `sender_email` field to `BrevoEmail` model
  - **Migration Required**: Run `python manage.py migrate brevo_analytics` after update
  - Nullable field for backward compatibility with existing data
  - Future webhook events will populate this field automatically
- **Configuration Requirement**: `ALLOWED_SENDERS` setting is now MANDATORY
  - Must be configured in `BREVO_ANALYTICS['ALLOWED_SENDERS']` setting
  - List of authorized sender email addresses for your organization
  - Events from unlisted senders will be rejected
  - Example: `ALLOWED_SENDERS = ['noreply@example.com', 'alerts@example.com']`
- **Webhook Behavior**: Enhanced event processing with sender validation
  - Extracts sender email from `from` or `sender` webhook fields
  - Validates against ALLOWED_SENDERS before database operations
  - Logs rejection of unauthorized sender events for audit trail

### Migration Guide

**CRITICAL - Action Required for All Installations:**

1. **Update Package**:
   ```bash
   pip install --upgrade django-brevo-analytics==0.2.1
   ```

2. **Configure ALLOWED_SENDERS** in Django settings:
   ```python
   BREVO_ANALYTICS = {
       'WEBHOOK_SECRET': 'your-webhook-secret',
       'CLIENT_UID': 'your-client-uuid',
       'ALLOWED_SENDERS': [
           'noreply@yourcompany.com',
           'alerts@yourcompany.com',
           # Add all legitimate sender addresses for your organization
       ],
   }
   ```

3. **Run Database Migration**:
   ```bash
   python manage.py migrate brevo_analytics
   ```

4. **Verify Existing Data** (optional but recommended):
   ```bash
   # Check for potentially contaminated data
   python manage.py verify_senders
   ```

5. **Re-import Historical Data** (recommended):
   ```bash
   # Clear and reimport to populate sender_email field
   python manage.py import_brevo_logs /path/to/logs.csv --clear
   ```

### Impact Assessment

**Before Fix:**
- Webhook accepted events from ANY sender on shared Brevo account
- Analytics data could include emails from other organizations
- No sender validation or isolation between tenants
- Potential for data leakage in multi-tenant Brevo accounts

**After Fix:**
- Only authorized senders (configured in ALLOWED_SENDERS) are processed
- Automatic sender validation on all webhook events
- ORM-level filtering ensures unauthorized data never appears in queries
- Complete data isolation for multi-tenant environments

**Affected Versions**: All versions prior to 0.2.1

**Recommended Action**: Immediate update for all installations, especially those on shared Brevo accounts

## [0.2.0] - 2026-01-27

### Added
- **Internal Domain Filtering System**: Comprehensive three-level filtering to exclude internal/test emails from analytics
  - Configure excluded domains via `BREVO_ANALYTICS['EXCLUDED_RECIPIENT_DOMAINS']` setting
  - Automatic filtering during CSV import prevents internal emails from entering the database
  - Real-time webhook filtering blocks internal domain events before processing
  - Model-level query filtering ensures internal emails never appear in analytics views or API responses
- **Management Command**: `clean_internal_emails` - Remove existing internal emails from database
  - Supports dry-run mode to preview deletions before applying
  - Automatically recalculates message statistics after cleanup
  - Useful for cleaning up data imported before domain filtering was configured
- **Management Command**: `recalculate_stats` - Recalculate statistics for all messages
  - Rebuild denormalized statistics from event data
  - Useful after data cleanup or manual database changes
  - Ensures dashboard metrics remain accurate

### Fixed
- **Statistics Accuracy**: Fixed critical bug in `BrevoMessage.update_stats()` that was counting all emails in the database instead of only emails with 'sent' events for the specific message
  - Delivery rate, open rate, and click rate calculations now correctly reflect actual sent emails
  - Prevents inflated or incorrect percentage metrics in dashboard
- **Webhook Event Processing**: Webhook now correctly ignores events that arrive without a prior 'sent' event in the database
  - Prevents orphaned events from creating incomplete email records
  - Ensures all tracked emails have complete event history starting from 'sent'

### Changed
- **Email Model**: Added custom `BrevoEmailQuerySet` and `BrevoEmailManager` for automatic domain filtering at the ORM level
  - All queries automatically exclude internal domains without manual filtering
  - Transparent to existing code - filtering happens automatically
- **Import Command**: Enhanced `import_brevo_logs` to filter internal domains during CSV processing
  - Reduces database size by excluding test/internal emails from the start
  - Improves import performance by skipping unnecessary records
- **Webhook Processing**: Updated webhook handler to filter internal domains in real-time
  - Prevents test emails from affecting production analytics
  - Reduces database writes for non-production events

### Technical Details
- All changes are backward compatible with existing configurations
- Domain filtering is optional - package works without `EXCLUDED_RECIPIENT_DOMAINS` configuration
- Custom manager ensures filtering works with all Django ORM query methods (filter, exclude, annotate, etc.)
- Statistics recalculation is automatically triggered after cleanup operations

## [0.1.1] - 2026-01-22

### Changed
- Updated README.md to remove all Supabase references
- Updated documentation to reflect Django-native architecture
- Added comprehensive setup instructions for DRF and CORS
- Added management commands documentation
- Updated troubleshooting section for current architecture

### Fixed
- Multi-client blacklist filtering: now correctly filters by ALLOWED_SENDERS and local database
- Emails with empty senderEmail (hard bounces) now properly included when in local DB
- Prevents showing blacklisted emails from other clients on shared Brevo accounts

## [0.1.0] - 2026-01-22

### Added
- Initial release of django-brevo-analytics
- Django-native architecture with models stored in PostgreSQL
- Django REST Framework API endpoints for analytics data
- Vue.js Single Page Application (SPA) for interactive analytics viewing
- Real-time webhook integration for Brevo events
- Dashboard with KPI metrics:
  - Total emails sent, delivery rate, open rate, click rate
  - Bounced and blocked emails count
  - Recent messages list
- Message-level email tracking with status filtering
- Email detail modal with complete event timeline
- Blacklist management interface:
  - Check individual emails for blacklist status
  - View and manage all blacklisted emails
  - Integration with Brevo API for real-time blacklist data
  - Remove emails from blacklist directly from UI
- Internationalization (i18n) support:
  - English and Italian translations
  - JavaScript-based UI localization
  - Django model verbose names localization
- Historical data import from raw Brevo logs (CSV)
- Automatic bounce reason enrichment via Brevo API
- Statistics verification command against Brevo API
- DuckDB-based CSV import for efficient data processing
- JSONField-based event storage for optimal performance

### Technical Details
- Python 3.8+ support
- Django 4.2+ support
- Django REST Framework integration
- Vue.js 3 with Composition API
- Hash-based routing (Vue Router in-memory)
- HMAC signature validation for webhooks
- Denormalized statistics for fast queries
- Cached status fields for efficient filtering
- Multi-client filtering via ALLOWED_SENDERS configuration
- Modal-based UI for seamless navigation
- Comprehensive management commands:
  - `import_brevo_logs`: Import historical data from CSV
  - `verify_brevo_stats`: Verify statistics against Brevo API
