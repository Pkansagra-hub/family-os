"""
Storage Scanner - Extract table, migration, and index definitions from Alembic migrations.

Scans k0/db/alembic/versions/*.py for:
- Table definitions (op.create_table)
- Index definitions (op.create_index)
- Migration metadata (revision, down_revision)

Usage:
    from governance.k0.scripts.storage_scanner import scan_tables, scan_migrations, scan_indexes
    tables = scan_tables()
    migrations = scan_migrations()
    indexes = scan_indexes()
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StorageTableInfo:
    """Extracted table information from Alembic migration."""

    table_name: str
    migration_id: str  # 0022, 0002, etc.
    migration_file: str
    columns: list[str] = field(default_factory=list)
    primary_key: str | None = None
    status: str = "Active"  # Active, Deprecated, Planning


@dataclass
class MigrationInfo:
    """Extracted migration information."""

    migration_id: str  # 0022
    file_name: str  # 0022_st_hipp_events.py
    revision: str  # "0022"
    down_revision: str | None  # "0021"
    creates_tables: list[str] = field(default_factory=list)
    creates_indexes: list[str] = field(default_factory=list)
    purpose: str = ""  # From docstring
    applied: bool = True  # Assume applied


@dataclass
class IndexInfo:
    """Extracted index information from Alembic migration."""

    index_name: str
    table_name: str
    columns: list[str] = field(default_factory=list)
    index_type: str = "BTREE"  # BTREE, HNSW, GIN
    is_unique: bool = False
    is_partial: bool = False
    migration_id: str = ""
    status: str = "Active"


def _get_repo_root() -> Path:
    """Get repository root from script location."""
    return Path(__file__).parent.parent.parent.parent


def _get_migrations_path() -> Path:
    """Get path to alembic migrations."""
    return _get_repo_root() / "k0" / "db" / "alembic" / "versions"


def _extract_string_arg(node: ast.expr) -> str | None:
    """Extract string value from AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_docstring(tree: ast.Module) -> str:
    """Extract first line of module docstring."""
    docstring = ast.get_docstring(tree)
    if docstring:
        first_line = docstring.split("\n")[0].strip()
        return first_line[:100]
    return ""


def _parse_migration_file(
    file_path: Path,
) -> tuple[MigrationInfo, list[StorageTableInfo], list[IndexInfo]]:
    """Parse a single migration file and extract all info."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    # Extract migration ID from filename (e.g., "0022" from "0022_st_hipp_events.py")
    migration_id = file_path.stem.split("_")[0]

    # Extract revision identifiers from module-level assignments
    revision = ""
    down_revision = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "revision" and isinstance(node.value, ast.Constant):
                        revision = str(node.value.value)
                    elif target.id == "down_revision":
                        if isinstance(node.value, ast.Constant):
                            down_revision = node.value.value
                        elif isinstance(node.value, ast.Name) and node.value.id == "None":
                            down_revision = None

    migration = MigrationInfo(
        migration_id=migration_id,
        file_name=file_path.name,
        revision=revision,
        down_revision=down_revision,
        purpose=_extract_docstring(tree),
    )

    tables: list[StorageTableInfo] = []
    indexes: list[IndexInfo] = []

    # Find upgrade() function and extract create_table/create_index calls
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Call) and isinstance(stmt.func, ast.Attribute):
                    # op.create_table(...)
                    if stmt.func.attr == "create_table" and stmt.args:
                        table_name = _extract_string_arg(stmt.args[0])
                        if table_name:
                            # Extract column names from subsequent sa.Column() calls
                            columns = []
                            primary_key = None
                            for arg in stmt.args[1:]:
                                if isinstance(arg, ast.Call) and isinstance(
                                    arg.func, ast.Attribute
                                ):
                                    if arg.func.attr == "Column" and arg.args:
                                        col_name = _extract_string_arg(arg.args[0])
                                        if col_name:
                                            columns.append(col_name)
                                            # Check if primary_key=True
                                            for kw in arg.keywords:
                                                if kw.arg == "primary_key":
                                                    if (
                                                        isinstance(kw.value, ast.Constant)
                                                        and kw.value.value
                                                    ):
                                                        primary_key = col_name

                            tables.append(
                                StorageTableInfo(
                                    table_name=table_name,
                                    migration_id=migration_id,
                                    migration_file=file_path.name,
                                    columns=columns,
                                    primary_key=primary_key,
                                )
                            )
                            migration.creates_tables.append(table_name)

                    # op.create_index(...)
                    elif stmt.func.attr == "create_index" and len(stmt.args) >= 2:
                        index_name = _extract_string_arg(stmt.args[0])
                        table_name = _extract_string_arg(stmt.args[1])

                        if index_name and table_name:
                            # Extract column names from third arg (list)
                            columns = []
                            if len(stmt.args) >= 3 and isinstance(stmt.args[2], ast.List):
                                for elt in stmt.args[2].elts:
                                    col = _extract_string_arg(elt)
                                    if col:
                                        columns.append(col)
                                    elif isinstance(elt, ast.Call):
                                        # sa.text("col DESC") - extract from string
                                        if elt.args:
                                            text_val = _extract_string_arg(elt.args[0])
                                            if text_val:
                                                columns.append(text_val.split()[0])  # First word

                            # Check for unique=True
                            is_unique = False
                            is_partial = False
                            for kw in stmt.keywords:
                                if kw.arg == "unique" and isinstance(kw.value, ast.Constant):
                                    is_unique = kw.value.value
                                if kw.arg == "postgresql_where":
                                    is_partial = True

                            # Determine index type from name or context
                            index_type = "BTREE"
                            if "hnsw" in index_name.lower():
                                index_type = "HNSW"
                            elif "gin" in index_name.lower():
                                index_type = "GIN"

                            indexes.append(
                                IndexInfo(
                                    index_name=index_name,
                                    table_name=table_name,
                                    columns=columns,
                                    index_type=index_type,
                                    is_unique=is_unique,
                                    is_partial=is_partial,
                                    migration_id=migration_id,
                                )
                            )
                            migration.creates_indexes.append(index_name)

    return migration, tables, indexes


def scan_migrations(migrations_path: Path | None = None) -> list[MigrationInfo]:
    """
    Scan all Alembic migration files.

    Returns:
        List of MigrationInfo ordered by migration ID
    """
    if migrations_path is None:
        migrations_path = _get_migrations_path()

    if not migrations_path.exists():
        return []

    migrations = []
    for py_file in sorted(migrations_path.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        try:
            migration, _, _ = _parse_migration_file(py_file)
            migrations.append(migration)
        except Exception as e:
            print(f"Warning: Failed to parse {py_file.name}: {e}")

    return migrations


def scan_tables(migrations_path: Path | None = None) -> list[StorageTableInfo]:
    """
    Scan all Alembic migrations and extract table definitions.

    Returns:
        List of StorageTableInfo for all created tables
    """
    if migrations_path is None:
        migrations_path = _get_migrations_path()

    if not migrations_path.exists():
        return []

    all_tables = []
    for py_file in sorted(migrations_path.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        try:
            _, tables, _ = _parse_migration_file(py_file)
            all_tables.extend(tables)
        except Exception as e:
            print(f"Warning: Failed to parse {py_file.name}: {e}")

    return all_tables


def scan_indexes(migrations_path: Path | None = None) -> list[IndexInfo]:
    """
    Scan all Alembic migrations and extract index definitions.

    Returns:
        List of IndexInfo for all created indexes
    """
    if migrations_path is None:
        migrations_path = _get_migrations_path()

    if not migrations_path.exists():
        return []

    all_indexes = []
    for py_file in sorted(migrations_path.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        try:
            _, _, indexes = _parse_migration_file(py_file)
            all_indexes.extend(indexes)
        except Exception as e:
            print(f"Warning: Failed to parse {py_file.name}: {e}")

    return all_indexes


def diff_tables_with_master(tables: list[StorageTableInfo], master_path: Path) -> dict[str, Any]:
    """
    Compare scanned tables with Part 6.1 Storage Tables Registry.

    Returns dict with:
        - missing_in_master: tables in code but not in doc
        - missing_in_code: tables in doc but not in code (may be Planning)
        - scanned_count: number of tables found in migrations
        - registered_count: number of tables in master doc
    """
    from governance.k0.scripts.markdown_parser import (
        MarkdownRegistry,
        extract_backtick_value,
    )

    registry = MarkdownRegistry(master_path)

    # Get the storage table from Part 6.1
    table = registry.get_table("6.1", "Storage")
    if not table:
        table = registry.get_table_by_title("Storage Tables Registry")

    registered = set()
    planning_tables = set()
    if table:
        for row in table.rows:
            # First column is Table name in backticks
            table_cell = row.cells[0] if row.cells else ""
            table_name = extract_backtick_value(table_cell)
            if table_name and not table_name.startswith("-"):
                registered.add(table_name)
                # Check status column (last or second-to-last)
                if len(row.cells) >= 6:
                    status_cell = row.cells[-1]
                    if "Planning" in status_cell or "🎯" in status_cell:
                        planning_tables.add(table_name)

    scanned_names = {t.table_name for t in tables}

    # Planning tables are expected to not be in code yet
    missing_in_code = registered - scanned_names - planning_tables

    return {
        "missing_in_master": scanned_names - registered,
        "missing_in_code": missing_in_code,
        "scanned_count": len(tables),
        "registered_count": len(registered),
        "planning_count": len(planning_tables),
    }


def diff_migrations_with_master(
    migrations: list[MigrationInfo], master_path: Path
) -> dict[str, Any]:
    """
    Compare scanned migrations with Part 6.2 Migration Registry.

    Returns dict with:
        - missing_in_master: migrations in code but not in doc
        - missing_in_code: migrations in doc but not in code
        - scanned_count: number of migrations found
        - registered_count: number of migrations in master doc
    """
    from governance.k0.scripts.markdown_parser import MarkdownRegistry

    registry = MarkdownRegistry(master_path)

    # Get the migration table from Part 6.2
    table = registry.get_table("6.2", "Migration")
    if not table:
        table = registry.get_table_by_title("Migration Registry")

    registered = set()
    if table:
        for row in table.rows:
            # First column is Migration ID
            if row.cells:
                migration_id = row.cells[0].strip()
                if migration_id and migration_id.isdigit():
                    registered.add(migration_id.zfill(4))

    scanned_ids = {m.migration_id for m in migrations}

    return {
        "missing_in_master": scanned_ids - registered,
        "missing_in_code": registered - scanned_ids,
        "scanned_count": len(migrations),
        "registered_count": len(registered),
    }


def diff_indexes_with_master(indexes: list[IndexInfo], master_path: Path) -> dict[str, Any]:
    """
    Compare scanned indexes with Part 6.3 Index Registry.

    Returns dict with:
        - missing_in_master: indexes in code but not in doc
        - missing_in_code: indexes in doc but not in code
        - scanned_count: number of indexes found
        - registered_count: number of indexes in master doc
    """
    from governance.k0.scripts.markdown_parser import MarkdownRegistry

    registry = MarkdownRegistry(master_path)

    # Part 6.3 has multiple index tables per table (st_wal, st_hipp_events, etc.)
    # We need to scan all tables in section 6.3
    registered = set()

    # Look for all tables in section 6.3
    for section_id in ["6.3"]:
        # Try getting index tables by searching for "Index Name" column header
        content = master_path.read_text(encoding="utf-8")

        # Pattern to find index tables and extract index names
        # Index names are in backticks in first column
        # Use [a-z0-9_]+ to include numbers (e.g., idx_wal_envelope_sha256)
        index_pattern = re.compile(r"\|\s*`(idx_[a-z0-9_]+)`\s*\|")
        for match in index_pattern.finditer(content):
            registered.add(match.group(1))

        # Also look for unique index patterns
        uq_pattern = re.compile(r"\|\s*`(uq_[a-z0-9_]+)`\s*\|")
        for match in uq_pattern.finditer(content):
            registered.add(match.group(1))

    scanned_names = {i.index_name for i in indexes}

    return {
        "missing_in_master": scanned_names - registered,
        "missing_in_code": registered - scanned_names,
        "scanned_count": len(indexes),
        "registered_count": len(registered),
    }


if __name__ == "__main__":
    # Quick test
    print("=" * 60)
    print("Storage Scanner Test")
    print("=" * 60)

    print("\n[1] Scanning tables...")
    tables = scan_tables()
    print(f"Found {len(tables)} tables:")
    for t in tables:
        print(f"  {t.table_name} (migration {t.migration_id}, {len(t.columns)} cols)")

    print("\n[2] Scanning migrations...")
    migrations = scan_migrations()
    print(f"Found {len(migrations)} migrations:")
    for m in migrations:
        creates = ", ".join(m.creates_tables) if m.creates_tables else "(no tables)"
        print(f"  {m.migration_id}: {m.purpose[:50]}... -> {creates}")

    print("\n[3] Scanning indexes...")
    indexes = scan_indexes()
    print(f"Found {len(indexes)} indexes:")
    for i in indexes[:10]:  # First 10
        cols = ", ".join(i.columns[:2])
        print(f"  {i.index_name} on {i.table_name}({cols})")
    if len(indexes) > 10:
        print(f"  ... and {len(indexes) - 10} more")

    # Test diff
    print("\n[4] Testing diff with master...")
    master_path = _get_repo_root() / "governance" / "k0" / "k0_architecture_master.md"
    if master_path.exists():
        diff = diff_tables_with_master(tables, master_path)
        print(
            f"Tables - Scanned: {diff['scanned_count']}, Registered: {diff['registered_count']}, Planning: {diff['planning_count']}"
        )
        if diff["missing_in_master"]:
            print(f"  Missing in master: {diff['missing_in_master']}")
        if diff["missing_in_code"]:
            print(f"  Missing in code: {diff['missing_in_code']}")
