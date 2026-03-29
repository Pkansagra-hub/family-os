#!/usr/bin/env python3
"""Export full schema samples from all memory tables."""

import asyncio

import asyncpg


async def export_samples():
    conn = await asyncpg.connect("postgresql://k0user:changeme@localhost:5432/k0_kernel")

    tables = [
        "st_hipp_events",
        "st_epi",
        "st_sem",
        "st_social",
        "st_kg_dom",
        "st_prospective",
    ]

    for table in tables:
        print("=" * 100)
        print(f"TABLE: {table}")
        print("=" * 100)

        # Get column names
        cols = await conn.fetch(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position
            """,
            table,
        )
        col_names = [c["column_name"] for c in cols]

        # Get 3 sample rows
        rows = await conn.fetch(f"SELECT * FROM {table} LIMIT 3")

        if not rows:
            print("  (no data)")
            print()
            continue

        for i, row in enumerate(rows):
            print(f"--- Row {i + 1} ---")
            for col in col_names:
                val = row[col]
                # Truncate long values
                if val is None:
                    display = "NULL"
                elif isinstance(val, bytes):
                    display = f"<bytes len={len(val)}>"
                elif isinstance(val, str) and len(val) > 100:
                    display = val[:100] + "..."
                else:
                    display = str(val)
                print(f"  {col:40} = {display}")
            print()
        print()

    await conn.close()
    print("Export complete!")


if __name__ == "__main__":
    asyncio.run(export_samples())
