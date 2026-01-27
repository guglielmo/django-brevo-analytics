# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
