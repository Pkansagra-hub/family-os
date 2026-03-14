#!/usr/bin/env python3
"""Clear PostgreSQL tables for a true clean-slate test run.

Default behavior truncates all user tables in the `public` schema while preserving
migration metadata (`alembic_version`).
"""

import asyncio
import os
from typing import List

import asyncpg

EXCLUDED_TABLES = {
    "alembic_version",
}


def _dsn() -> str:
    # Use pgbouncer inside container, localhost outside.
    if os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST"):
        return "postgresql://postgres:postgres@pgbouncer:6432/k0_kernel"
    return "postgresql://k0user:changeme@localhost:5432/k0_kernel"


def _quote_ident(identifier: str) -> str:
    # Basic SQL identifier quoting for dynamic table names.
    return '"' + identifier.replace('"', '""') + '"'


async def _discover_public_tables(conn: asyncpg.Connection) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = 'public'
          AND tablename <> ALL($1::text[])
        ORDER BY tablename
        """,
        list(EXCLUDED_TABLES),
    )
    return [row["tablename"] for row in rows]


async def clear() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        tables = await _discover_public_tables(conn)

        if not tables:
            print("No user tables found in public schema. Nothing to clear.")
            return

        qualified_tables = [f"public.{_quote_ident(table)}" for table in tables]
        truncate_sql = "TRUNCATE TABLE " + ", ".join(qualified_tables) + " RESTART IDENTITY CASCADE"

        async with conn.transaction():
            await conn.execute(truncate_sql)

        print("\n✅ Clean slate complete")
        print(f"  ✓ Truncated {len(tables)} table(s) in public schema")
        print(f"  ✓ Preserved metadata table(s): {', '.join(sorted(EXCLUDED_TABLES))}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(clear())
