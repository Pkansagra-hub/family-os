#!/usr/bin/env python3
"""Clear all P03 data tables for clean test."""

import asyncio
import os

import asyncpg


async def clear():
    # Use pgbouncer inside container, localhost outside
    if os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST"):
        dsn = "postgresql://postgres:postgres@pgbouncer:6432/k0_kernel"
    else:
        dsn = "postgresql://k0user:changeme@localhost:5432/k0_kernel"
    conn = await asyncpg.connect(dsn)

    # Clear all P03 output tables (order matters for FK constraints)
    tables = [
        "st_kg_edges",  # Clear edges first (FK to st_kg_dom)
        "st_kg_dom",  # Then entities
        "st_epi",
        "st_sem",  # Semantic memory patterns
        "st_procedural",  # Procedural memory
        "st_prospective",  # Prospective memory
        "st_hipp_events",
        "st_vec",
        "st_social",
        "st_learning_queue",
        "st_outbox",
        "st_offsets",  # Reset offsets for fresh run
    ]

    for table in tables:
        try:
            result = await conn.execute(f"DELETE FROM {table}")
            print(f"  ✓ Cleared {table}")
        except Exception as e:
            print(f"  ✗ {table}: {e}")

    print("\n✅ All tables cleared for fresh test")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(clear())
