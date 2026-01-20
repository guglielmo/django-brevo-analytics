# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-20

### Added
- Initial release of django-brevo-analytics
- Django admin integration for Brevo transactional email analytics
- Display email events (delivered, opened, clicked, bounced, etc.) in Django admin
- Supabase/PostgREST client for fetching Brevo analytics data
- Configurable filtering by date range and event types
- Link to view detailed event information in Brevo dashboard
- Comprehensive test suite with 100% coverage
- Full documentation including:
  - Installation guide
  - Configuration instructions
  - Usage examples
  - API reference
  - Development setup

### Technical Details
- Python 3.8+ support
- Django 4.2+ support
- PostgREST client integration
- Type hints throughout codebase
- Comprehensive error handling and logging
