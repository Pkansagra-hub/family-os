"""Script to extract schema from K0 SQLite database."""

import sqlite3
from pathlib import Path

DB_PATH = Path("D:/familyos/k0_kernel_export.db")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Get all tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()

print("=" * 80)
print("K0 DATABASE SCHEMA")
print("=" * 80)
print(f"\nTotal tables: {len(tables)}\n")

for table in tables:
    table_name = table[0]
    print(f"\n{'='*60}")
    print(f"TABLE: {table_name}")
    print("=" * 60)

    # Get table info
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    print("\nColumns:")
    for col in columns:
        col_id, name, col_type, not_null, default, pk = col
        pk_str = " [PK]" if pk else ""
        nn_str = " NOT NULL" if not_null else ""
        default_str = f" DEFAULT {default}" if default else ""
        print(f"  - {name}: {col_type}{pk_str}{nn_str}{default_str}")

    # Get indexes
    indexes = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    if indexes:
        print("\nIndexes:")
        for idx in indexes:
            idx_name = idx[1]
            unique = "UNIQUE " if idx[2] else ""
            idx_cols = conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
            cols = ", ".join([c[2] for c in idx_cols])
            print(f"  - {unique}{idx_name} ({cols})")

    # Get foreign keys
    fks = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    if fks:
        print("\nForeign Keys:")
        for fk in fks:
            print(f"  - {fk[3]} -> {fk[2]}({fk[4]})")

    # Row count
    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    print(f"\nRow count: {count}")

conn.close()
