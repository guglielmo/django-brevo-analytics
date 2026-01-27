# Release Notes - v0.2.0

## Summary

This release fixes critical statistics calculation issues and adds internal domain filtering to prevent test/error emails from skewing production analytics.

## Issues Fixed

### 1. Incorrect `total_sent` Calculation
**Problem**: The `BrevoMessage.update_stats()` method was counting ALL emails associated with a message, regardless of whether they actually had a 'sent' event in their timeline.

**Impact**: Dashboard KPI "Emails Sent" showed inflated numbers, including emails that were only tracked for other events (bounced, blocked, etc.) but never actually sent.

**Solution**: Modified `update_stats()` to iterate through email events and count only those with `type='sent'` in their event array.

**Code Changed**:
- `brevo_analytics/models.py` - `BrevoMessage.update_stats()` method

### 2. Internal Domain Contamination
**Problem**: Emails sent to internal domains (openpolis.it, deppsviluppo.org) were included in statistics. These are typically error notifications and test emails that confuse production metrics.

**Impact**: Analytics included irrelevant internal communications, making it difficult to assess actual campaign performance.

**Solution**: Implemented three-level filtering system:
1. **Import-time filtering**: `import_brevo_logs` command excludes internal domains
2. **Runtime filtering**: Custom Django manager excludes internal domains from all queries
3. **Webhook filtering**: Real-time events for internal domains are ignored

**Code Changed**:
- `brevo_analytics/models.py` - Added `BrevoEmailQuerySet` and `BrevoEmailManager`
- `brevo_analytics/webhooks.py` - Added domain check before processing events
- `brevo_analytics/management/commands/import_brevo_logs.py` - Added exclusion clause

## New Features

### Management Commands

**`clean_internal_emails`**
- Removes existing emails sent to excluded domains
- Recalculates statistics for affected messages
- Removes empty messages after cleanup
- Supports `--dry-run` for preview

**`recalculate_stats`**
- Recalculates statistics for all messages with new logic
- Shows before/after comparison
- Supports `--message-id` for single message recalculation
- Identifies messages with zero sent emails

### Configuration

New `BREVO_ANALYTICS` settings:

```python
BREVO_ANALYTICS = {
    # ... existing settings ...
    'EXCLUDED_RECIPIENT_DOMAINS': ['openpolis.it', 'deppsviluppo.org'],
}
```

## Migration Guide

### For Existing Installations

1. **Update configuration** in `settings.py`:
   ```python
   BREVO_ANALYTICS = {
       'EXCLUDED_RECIPIENT_DOMAINS': ['openpolis.it', 'deppsviluppo.org'],
   }
   ```

2. **Clean existing internal emails**:
   ```bash
   python manage.py clean_internal_emails --dry-run  # Preview
   python manage.py clean_internal_emails             # Execute
   ```

3. **Recalculate all statistics**:
   ```bash
   python manage.py recalculate_stats
   ```

### For New Installations

No migration needed. Import will automatically exclude internal domains.

## Breaking Changes

**None** - All changes are backward compatible. Existing code will continue to work, but statistics will be more accurate after running migration commands.

## Technical Details

### Model Changes

- `BrevoEmail` now uses custom manager that filters internal domains by default
- `BrevoEmail.objects.all_including_internal()` available for debugging
- `BrevoMessage.update_stats()` now accurately counts sent events

### Performance Impact

- Minimal: Domain filtering adds negligible overhead (indexed field)
- Statistics recalculation is one-time operation after upgrade

## Files Changed

- `brevo_analytics/models.py` - Manager, queryset, and stats calculation
- `brevo_analytics/webhooks.py` - Domain filtering for real-time events
- `brevo_analytics/management/commands/import_brevo_logs.py` - Import filtering
- `brevo_analytics/management/commands/clean_internal_emails.py` - New command
- `brevo_analytics/management/commands/recalculate_stats.py` - New command
- `CLAUDE.md` - Documentation updates

## Testing

To verify the fix works correctly:

1. Check current stats:
   ```python
   msg = BrevoMessage.objects.first()
   print(f"Total sent: {msg.total_sent}")
   print(f"Emails count: {msg.emails.count()}")
   ```

2. Run recalculation and verify numbers match expected sent events

3. Import new data and verify internal domains are excluded

## Credits

- Fixed calculation logic in `update_stats()`
- Implemented domain filtering system
- Created cleanup and recalculation utilities
- Updated documentation
