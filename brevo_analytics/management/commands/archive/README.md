# Archived Management Commands

These management commands are no longer needed after the 2026-01-21 refactoring from Supabase to Django-native architecture.

## Archived Commands

### `import_brevo_csv.py`
**Replaced by:** `import_brevo_logs.py`

**Why archived:** This command imported data from intermediate CSV files (`emails_import.csv` and `email_events_import.csv`). The new approach uses DuckDB to process raw Brevo logs directly, eliminating the need for intermediate CSVs.

**Old workflow:**
```
Raw logs → transform_csv_to_supabase.py → emails_import.csv + email_events_import.csv → import_brevo_csv.py
```

**New workflow:**
```
Raw logs → import_brevo_logs.py (with DuckDB)
```

### `fix_naive_datetimes.py`
**Purpose:** One-time migration to fix naive datetimes in the database.

**Why archived:** This was a one-time data fix. All new data is now properly timezone-aware from import. No longer needed in normal operations.

### `sync_brevo_sent_at.py`
**Purpose:** One-time sync to populate `sent_at` field in BrevoMessage from related emails.

**Why archived:** The new import command (`import_brevo_logs.py`) correctly populates `sent_at` during initial import. This sync is no longer needed.

## Active Commands

The following commands are still active and should be used:

- **`import_brevo_logs.py`** - Primary import command using DuckDB
  - Imports from raw Brevo logs CSV
  - Optional `--enrich-bounces` to add bounce reasons from API
  - Replaces all old import workflows

- **`verify_brevo_stats.py`** - Verification tool
  - Compares local statistics with Brevo API
  - Useful for debugging discrepancies
  - Still active and useful

---

**Archived:** 2026-01-22
**Reason:** Refactoring from Supabase to Django-native architecture
