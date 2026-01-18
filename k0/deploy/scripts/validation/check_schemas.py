"""Check schemas of all memory tables"""

import asyncio

import asyncpg


async def check_schemas():
    conn = await asyncpg.connect("postgresql://k0user:changeme@localhost:5432/k0_kernel")

    tables = ["st_epi", "st_sem", "st_kg_dom", "st_social", "st_prospective", "st_observations"]

    for table in tables:
        print(f"\n=== {table} COLUMNS ===")
        rows = await conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position
        """,
            table,
        )
        for r in rows:
            print(f"  {r['column_name']}: {r['data_type']}")

    await conn.close()


asyncio.run(check_schemas())
