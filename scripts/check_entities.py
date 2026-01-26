"""Check entity quality in st_sem table."""

import asyncio
import os

import asyncpg


async def check():
    dsn = os.environ.get("K0_POSTGRES_DSN", "postgresql://k0:k0pass@localhost:5432/k0_kernel")
    conn = await asyncpg.connect(dsn)

    # Count entities
    count = await conn.fetchval("SELECT COUNT(*) FROM st_sem")
    print(f"Total entities in st_sem: {count}")
    print()

    # Get all entities sorted
    rows = await conn.fetch(
        "SELECT canonical_name, entity_type, confidence FROM st_sem ORDER BY canonical_name"
    )

    print("Entity Quality Report:")
    print("-" * 70)
    print(f"{'Name':35} | {'Type':15} | Conf")
    print("-" * 70)
    for row in rows:
        name = row["canonical_name"] or "NULL"
        etype = row["entity_type"] or "NULL"
        conf = row["confidence"] if row["confidence"] else 0.0
        print(f"{name[:35]:35} | {etype:15} | {conf:.2f}")

    await conn.close()


asyncio.run(check())

asyncio.run(check())

asyncio.run(check())

asyncio.run(check())

asyncio.run(check())
