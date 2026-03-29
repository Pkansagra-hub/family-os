#!/usr/bin/env python3
"""Query learning gaps from st_learning_queue."""

import asyncio

import asyncpg


async def query():
    dsn = "postgresql://k0user:changeme@postgres:5432/k0_kernel"
    conn = await asyncpg.connect(dsn)

    # Get columns first
    cols = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'st_learning_queue'"
    )
    print("=== st_learning_queue COLUMNS ===")
    print([r["column_name"] for r in cols])
    print()

    # Count by gap type
    counts = await conn.fetch(
        """
        SELECT gap_type, status, COUNT(*) as cnt
        FROM st_learning_queue
        GROUP BY gap_type, status
        ORDER BY cnt DESC
    """
    )
    print("=== GAP TYPE DISTRIBUTION ===")
    for r in counts:
        print(f"  {r['gap_type']:<25} {r['status']:<10} {r['cnt']:>5}")
    print()

    # Sample gaps - use actual columns: id, entity_id, gap_type, context_json, importance_score, status
    rows = await conn.fetch(
        """
        SELECT id, entity_id, gap_type, context_json, importance_score, status
        FROM st_learning_queue
        ORDER BY importance_score DESC
        LIMIT 15
    """
    )

    print("=== TOP 15 LEARNING GAPS (by importance) ===")
    for i, r in enumerate(rows, 1):
        entity = str(r["entity_id"])[:50] if r["entity_id"] else "N/A"
        gap_type = r["gap_type"] or "N/A"
        importance = r["importance_score"] or 0.0
        status = r["status"] or "N/A"
        context = r["context_json"] or {}

        print(f"\n{i:2}. [{gap_type}] (importance: {importance:.2f}, status: {status})")
        print(f"    Entity: {entity}")
        if context:
            # Show first 100 chars of context
            ctx_str = str(context)[:100]
            print(f"    Context: {ctx_str}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(query())
    asyncio.run(query())
    asyncio.run(query())
    asyncio.run(query())
    asyncio.run(query())
    asyncio.run(query())
