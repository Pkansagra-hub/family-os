# Archived Scripts

These scripts were used during the SQLite → PostgreSQL migration and are no longer needed for production use.

## Archived Files

| Script | Purpose | Archived Date |
|--------|---------|---------------|
| `sqlite_migration_audit.py` | Audit SQLite usage across codebase | 2025-12-23 |
| `filter_production_files.py` | Filter production files for migration analysis | 2025-12-23 |
| `find_sync_wrappers.py` | Find synchronous wrapper patterns for conversion | 2025-12-23 |
| `generate_migration_doc.py` | Generate migration documentation | 2025-12-23 |

## Reason for Archive

These scripts were one-time utilities for the PostgreSQL migration project (Milestone 5.3.2).
They reference SQLite patterns that are no longer present in the codebase.

**Do not use these scripts** - the migration is complete and the codebase now uses PostgreSQL with asyncpg.
