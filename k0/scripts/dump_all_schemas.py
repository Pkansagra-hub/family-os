"""Dump complete schema for all tables in k0_kernel_export.db."""

import sqlite3
from pathlib import Path

DB_PATH = Path("D:/familyos/k0_kernel_export.db")


def get_table_info(conn, table_name):
    """Get columns, types, and constraints for a table."""
    cursor = conn.cursor()

    # Get column info
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()

    # Get foreign keys
    cursor.execute(f"PRAGMA foreign_key_list({table_name})")
    fks = cursor.fetchall()

    # Get indexes
    cursor.execute(f"PRAGMA index_list({table_name})")
    indexes = cursor.fetchall()

    return columns, fks, indexes


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all tables
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [r[0] for r in cursor.fetchall()]

    print(f"# Database Schema: {DB_PATH.name}")
    print(f"# Tables: {len(tables)}")
    print()

    for table in tables:
        columns, fks, indexes = get_table_info(conn, table)

        print(f"## {table}")
        print(f"Columns: {len(columns)}")
        print()
        print("| # | Column | Type | NotNull | Default | PK |")
        print("|---|--------|------|---------|---------|-----|")

        for col in columns:
            cid, name, dtype, notnull, default, pk = col
            print(
                f"| {cid} | `{name}` | {dtype or 'TEXT'} | {bool(notnull)} | {default} | {pk if pk else ''} |"
            )

        if fks:
            print()
            print("**Foreign Keys:**")
            for fk in fks:
                print(f"- `{fk[3]}` → `{fk[2]}.{fk[4]}`")

        if indexes:
            print()
            print("**Indexes:**")
            for idx in indexes:
                idx_name = idx[1]
                cursor.execute(f"PRAGMA index_info({idx_name})")
                idx_cols = cursor.fetchall()
                cols = ", ".join([c[2] for c in idx_cols])
                unique = "UNIQUE" if idx[2] else ""
                print(f"- `{idx_name}` ({cols}) {unique}")

        print()
        print("---")
        print()

    conn.close()


if __name__ == "__main__":
    main()
