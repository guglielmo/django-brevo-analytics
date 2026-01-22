# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
