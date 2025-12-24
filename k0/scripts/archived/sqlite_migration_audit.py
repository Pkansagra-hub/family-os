"""
Comprehensive SQLite usage audit across the entire FamilyOS repository.
Identifies all SQLite-specific patterns that need PostgreSQL migration.
"""

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Use absolute path to avoid resolution issues
REPO_PATH = Path("D:/familyos")
OUTPUT_FILE = REPO_PATH / "k0" / "docs" / "sync_wrapper_audit.md"

# Categories of SQLite usage to detect
CATEGORIES = {
    "python_imports": [
        (r"^import sqlite3", "import sqlite3"),
        (r"^from sqlite3 import", "from sqlite3 import"),
    ],
    "connection_creation": [
        (r"sqlite3\.connect\s*\(", "sqlite3.connect()"),
        (r"aiosqlite\.connect\s*\(", "aiosqlite.connect()"),
    ],
    "file_references": [
        (r"\.sqlite3", ".sqlite3 file"),
        (r"\.sqlite", ".sqlite file"),
        (r"k0_runtime\.sqlite", "k0_runtime.sqlite"),
        (r"\.db['\"]", ".db file"),
    ],
    "pragma_commands": [
        (r"PRAGMA\s+journal_mode", "PRAGMA journal_mode"),
        (r"PRAGMA\s+synchronous", "PRAGMA synchronous"),
        (r"PRAGMA\s+foreign_keys", "PRAGMA foreign_keys"),
        (r"PRAGMA\s+temp_store", "PRAGMA temp_store"),
        (r"PRAGMA\s+busy_timeout", "PRAGMA busy_timeout"),
        (r"PRAGMA\s+wal_checkpoint", "PRAGMA wal_checkpoint"),
        (r"PRAGMA\s+wal_autocheckpoint", "PRAGMA wal_autocheckpoint"),
        (r"PRAGMA\s+table_info", "PRAGMA table_info"),
        (r"PRAGMA\s+database_list", "PRAGMA database_list"),
    ],
    "sqlite_specific_sql": [
        (r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "AUTOINCREMENT (use SERIAL)"),
        (r"CREATE\s+VIRTUAL\s+TABLE.*fts5", "FTS5 (use tsvector)"),
        (r"USING\s+fts5", "FTS5 usage"),
        (r"INSERT\s+OR\s+REPLACE", "INSERT OR REPLACE (use ON CONFLICT)"),
        (r"INSERT\s+OR\s+IGNORE", "INSERT OR IGNORE (use ON CONFLICT DO NOTHING)"),
        (r"GLOB\s+", "GLOB (use LIKE or ~)"),
        (r"IFNULL\s*\(", "IFNULL (use COALESCE)"),
        (r"executescript\s*\(", "executescript() (not in asyncpg)"),
    ],
    "cursor_operations": [
        (r"\.fetchone\s*\(\)", "fetchone()"),
        (r"\.fetchall\s*\(\)", "fetchall()"),
        (r"\.fetchmany\s*\(", "fetchmany()"),
        (r"cursor\.lastrowid", "lastrowid (use RETURNING)"),
        (r"\.rowcount", "rowcount"),
    ],
    "connection_types": [
        (r"sqlite3\.Connection", "sqlite3.Connection type"),
        (r"sqlite3\.Cursor", "sqlite3.Cursor type"),
        (r"sqlite3\.Row", "sqlite3.Row"),
        (r"row_factory", "row_factory"),
    ],
    "wal_operations": [
        (r"WAL", "WAL mode reference"),
        (r"-wal", "WAL file"),
        (r"-shm", "SHM file"),
        (r"fsync", "fsync operation"),
    ],
}

SKIP_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "wheels",
    ".pytest_cache",
    ".mypy_cache",
}

FILE_EXTENSIONS = {
    ".py",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".md",
    ".txt",
    ".sh",
    ".ps1",
}


def find_function_context(lines, line_idx):
    """Walk backwards to find the containing function/class."""
    current_class = None
    current_func = None

    for i in range(line_idx - 1, -1, -1):
        line = lines[i]

        func_match = re.match(r"^(\s*)(?:async\s+)?def\s+(\w+)", line)
        if func_match and current_func is None:
            indent = len(func_match.group(1))
            current_func = func_match.group(2)
            if indent == 0:
                break
            continue

        class_match = re.match(r"^class\s+(\w+)", line)
        if class_match:
            current_class = class_match.group(1)
            break

    if current_class and current_func:
        return f"{current_class}.{current_func}"
    elif current_func:
        return current_func
    elif current_class:
        return f"{current_class}.<class-level>"
    return "<module-level>"


def scan_repository():
    """Scan entire repository for SQLite patterns."""
    results = defaultdict(lambda: defaultdict(list))
    file_count = 0

    for file_path in REPO_PATH.rglob("*"):
        if file_path.is_dir():
            continue
        if any(skip in file_path.parts for skip in SKIP_DIRS):
            continue

        is_dockerfile = file_path.name.lower() in ["dockerfile", "dockerfile.gpu"]
        if file_path.suffix.lower() not in FILE_EXTENSIONS and not is_dockerfile:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
            rel_path = file_path.relative_to(REPO_PATH)
            file_count += 1

            for line_num, line in enumerate(lines, 1):
                for category, patterns in CATEGORIES.items():
                    for pattern, name in patterns:
                        if re.search(pattern, line, re.IGNORECASE):
                            context = (
                                find_function_context(lines, line_num - 1)
                                if file_path.suffix == ".py"
                                else "<file>"
                            )
                            results[category][str(rel_path)].append(
                                {
                                    "line": line_num,
                                    "pattern": name,
                                    "context": context,
                                    "code": line.strip()[:100],
                                }
                            )
        except Exception:
            pass

    return results, file_count


def get_component_breakdown(results):
    """Categorize files by component/folder."""
    components = defaultdict(lambda: defaultdict(int))

    all_files = set()
    for category_data in results.values():
        all_files.update(category_data.keys())

    for file_path in all_files:
        parts = Path(file_path).parts
        if len(parts) >= 1:
            top_level = parts[0]
            if len(parts) >= 2:
                second_level = parts[1]
                component = f"{top_level}/{second_level}"
            else:
                component = top_level
        else:
            component = "root"

        total_matches = sum(len(results[cat].get(file_path, [])) for cat in results)
        components[component][file_path] = total_matches

    return components


def generate_migration_section():
    """Generate the SQLite to PostgreSQL migration section."""
    results, file_count = scan_repository()
    components = get_component_breakdown(results)

    lines = []
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("# SQLite → PostgreSQL Migration Audit")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().isoformat()}")
    lines.append("")
    lines.append(
        "This section identifies ALL SQLite usage across the repository for complete PostgreSQL migration."
    )
    lines.append("")

    # Overall summary
    total_occurrences = sum(
        len(matches) for cat_data in results.values() for matches in cat_data.values()
    )
    total_files = len(set(fp for cat_data in results.values() for fp in cat_data.keys()))

    lines.append("## Migration Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Total files scanned | {file_count} |")
    lines.append(f"| Files with SQLite usage | {total_files} |")
    lines.append(f"| Total SQLite patterns found | {total_occurrences} |")
    lines.append("")

    # Category breakdown
    lines.append("### Pattern Categories")
    lines.append("")
    lines.append("| Category | Files | Occurrences | PostgreSQL Replacement |")
    lines.append("|----------|-------|-------------|------------------------|")

    replacements = {
        "python_imports": "`asyncpg` or `psycopg[async]`",
        "connection_creation": "`asyncpg.connect()` / `asyncpg.create_pool()`",
        "file_references": "PostgreSQL connection string",
        "pragma_commands": "PostgreSQL config / SET commands",
        "sqlite_specific_sql": "See SQL migration table below",
        "cursor_operations": "`asyncpg.Record` / `fetch()` / `fetchrow()`",
        "connection_types": "`asyncpg.Connection` / `asyncpg.Pool`",
        "wal_operations": "PostgreSQL native WAL (automatic)",
    }

    for category in CATEGORIES.keys():
        cat_data = results[category]
        file_count = len(cat_data)
        occurrence_count = sum(len(v) for v in cat_data.values())
        replacement = replacements.get(category, "Manual review")
        cat_display = category.replace("_", " ").title()
        lines.append(f"| {cat_display} | {file_count} | {occurrence_count} | {replacement} |")
    lines.append("")

    # Component breakdown
    lines.append("---")
    lines.append("")
    lines.append("## Component Breakdown")
    lines.append("")
    lines.append("### By Directory")
    lines.append("")
    lines.append("| Component | Files Affected | Total Patterns |")
    lines.append("|-----------|----------------|----------------|")

    component_totals = []
    for component, files in sorted(components.items()):
        total = sum(files.values())
        component_totals.append((component, len(files), total))

    for component, file_count, total in sorted(component_totals, key=lambda x: x[2], reverse=True):
        lines.append(f"| `{component}` | {file_count} | {total} |")
    lines.append("")

    # SQL Syntax Migration Table
    lines.append("---")
    lines.append("")
    lines.append("## SQL Syntax Migration Reference")
    lines.append("")
    lines.append("| SQLite Syntax | PostgreSQL Equivalent | Notes |")
    lines.append("|---------------|----------------------|-------|")
    lines.append(
        "| `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` or `BIGSERIAL` | PostgreSQL sequences |"
    )
    lines.append(
        "| `CREATE VIRTUAL TABLE ... USING fts5` | `tsvector` + `GIN` index | Full-text search |"
    )
    lines.append("| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT DO UPDATE` | Upsert |")
    lines.append("| `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` | Skip duplicates |")
    lines.append("| `GLOB pattern` | `LIKE pattern` or `~ regex` | Pattern matching |")
    lines.append("| `IFNULL(a, b)` | `COALESCE(a, b)` | Null handling |")
    lines.append("| `datetime('now')` | `NOW()` or `CURRENT_TIMESTAMP` | Current time |")
    lines.append("| `PRAGMA journal_mode=WAL` | N/A (native) | PostgreSQL uses WAL by default |")
    lines.append("| `PRAGMA busy_timeout` | Connection pool timeout | Pool-level config |")
    lines.append("| `PRAGMA foreign_keys=ON` | Default ON in PostgreSQL | No action needed |")
    lines.append("| `cursor.lastrowid` | `RETURNING id` clause | Return inserted ID |")
    lines.append("| `executescript()` | Multiple `execute()` calls | No batch script |")
    lines.append("| `TEXT` | `TEXT` | Same |")
    lines.append("| `BLOB` | `BYTEA` | Binary data |")
    lines.append("| `REAL` | `DOUBLE PRECISION` or `NUMERIC` | Floating point |")
    lines.append("")

    # Detailed file listing by category
    lines.append("---")
    lines.append("")
    lines.append("## Detailed File Listings")
    lines.append("")

    priority_order = [
        "python_imports",
        "connection_creation",
        "pragma_commands",
        "sqlite_specific_sql",
        "cursor_operations",
        "connection_types",
        "file_references",
        "wal_operations",
    ]

    for category in priority_order:
        cat_data = results[category]
        if not cat_data:
            continue

        cat_display = category.replace("_", " ").title()
        total = sum(len(v) for v in cat_data.values())
        lines.append(f"### {cat_display} ({len(cat_data)} files, {total} occurrences)")
        lines.append("")

        # Group by component
        for file_path in sorted(cat_data.keys()):
            matches = cat_data[file_path]
            lines.append(f"#### `{file_path}`")
            lines.append("")
            lines.append("| Line | Context | Pattern | Code |")
            lines.append("|------|---------|---------|------|")
            for m in matches[:20]:  # Limit to 20 per file
                code = m["code"].replace("|", "\\|")[:60]
                lines.append(f"| {m['line']} | `{m['context']}` | {m['pattern']} | `{code}` |")
            if len(matches) > 20:
                lines.append(f"| ... | ... | *{len(matches) - 20} more* | ... |")
            lines.append("")

    # Migration checklist
    lines.append("---")
    lines.append("")
    lines.append("## Migration Checklist")
    lines.append("")
    lines.append("### Phase 1: Infrastructure")
    lines.append("")
    lines.append("- [ ] Add `asyncpg` to requirements")
    lines.append("- [ ] Create PostgreSQL connection pool module")
    lines.append("- [ ] Update `DatabaseSettings` in config.py")
    lines.append("- [ ] Create Docker Compose with PostgreSQL")
    lines.append("- [ ] Convert SQLite migrations to Alembic/PostgreSQL")
    lines.append("")
    lines.append("### Phase 2: Core Storage Layer")
    lines.append("")
    lines.append("- [ ] Convert `k0/uow/connection_pool.py`")
    lines.append("- [ ] Convert `k0/uow/unit_of_work.py`")
    lines.append("- [ ] Convert `k0/storage/wal.py`")
    lines.append("- [ ] Convert `k0/storage/outbox.py`")
    lines.append("- [ ] Convert `k0/storage/receipts.py`")
    lines.append("- [ ] Convert `k0/storage/offsets.py`")
    lines.append("")
    lines.append("### Phase 3: FTS5 → PostgreSQL Full-Text Search")
    lines.append("")
    lines.append("- [ ] Replace `st_epi_fts` FTS5 table with `tsvector` column + GIN index")
    lines.append("- [ ] Replace `st_hipp_fts` FTS5 table with `tsvector` column + GIN index")
    lines.append("- [ ] Update `k0/storage/fts5_indexer.py` → `k0/storage/fts_indexer.py`")
    lines.append("- [ ] Update `k0/drivers/fts5.py` → `k0/drivers/fts.py`")
    lines.append("")
    lines.append("### Phase 4: Remaining Modules")
    lines.append("")
    lines.append("- [ ] Convert `k0/kernel/syscalls.py` (53 occurrences)")
    lines.append("- [ ] Convert `k0/gate/schema_registry.py`")
    lines.append("- [ ] Convert `k0/gate/minimal_gate.py`")
    lines.append("- [ ] Convert `k0/idem/ledger.py`")
    lines.append("- [ ] Convert `k0/policy/*.py`")
    lines.append("- [ ] Convert `k0/drivers/*.py`")
    lines.append("")
    lines.append("### Phase 5: Tests & Scripts")
    lines.append("")
    lines.append("- [ ] Update test fixtures for PostgreSQL")
    lines.append("- [ ] Update `k0/scripts/*.py`")
    lines.append("- [ ] Update `k0/deploy/*.py`")
    lines.append("- [ ] Update CI/CD pipeline")
    lines.append("")

    # Required dependencies
    lines.append("---")
    lines.append("")
    lines.append("## Required Dependencies")
    lines.append("")
    lines.append("```toml")
    lines.append("# Add to pyproject.toml or requirements.txt")
    lines.append("asyncpg>=0.29.0        # Async PostgreSQL driver")
    lines.append("psycopg[binary]>=3.1.0 # Sync PostgreSQL (for migrations)")
    lines.append("alembic>=1.13.0        # Database migrations")
    lines.append("sqlalchemy>=2.0.0      # Optional: ORM layer")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point."""
    print(f"Scanning repository at: {REPO_PATH}")

    # Generate new section
    migration_section = generate_migration_section()

    # Read existing file
    existing_content = OUTPUT_FILE.read_text(encoding="utf-8")

    # Check if migration section already exists
    marker = "# SQLite → PostgreSQL Migration Audit"
    if marker in existing_content:
        # Replace existing section
        parts = existing_content.split("---\n\n" + marker)
        new_content = parts[0].rstrip() + migration_section
    else:
        # Append new section
        new_content = existing_content.rstrip() + migration_section

    # Write updated file
    OUTPUT_FILE.write_text(new_content, encoding="utf-8")

    print(f"Updated: {OUTPUT_FILE}")
    print("\nMigration audit added to sync_wrapper_audit.md")


if __name__ == "__main__":
    main()
