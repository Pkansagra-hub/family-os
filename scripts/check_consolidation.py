import asyncio

import asyncpg


async def check():
    dsn = "postgresql://k0user:changeme@localhost:5432/k0_kernel"
    conn = await asyncpg.connect(dsn)

    # Check if consolidation audit table exists and has data
    try:
        count = await conn.fetchval("SELECT COUNT(*) FROM st_consolidation_audit")
        print(f"Consolidation audit records: {count}")

        if count > 0:
            last = await conn.fetchrow(
                "SELECT created_at, status, phase FROM st_consolidation_audit ORDER BY created_at DESC LIMIT 1"
            )
            print(f"Last consolidation: {last}")
    except Exception as e:
        print(f"Error checking consolidation: {e}")

    # Check all relation types
    rel_types = await conn.fetch(
        "SELECT relation_type, COUNT(*) as count FROM st_kg_edges GROUP BY relation_type"
    )
    print("\nRelation types in KG edges:")
    for rt in rel_types:
        print(f'  {rt["relation_type"]}: {rt["count"]}')

    await conn.close()


asyncio.run(check())
asyncio.run(check())
