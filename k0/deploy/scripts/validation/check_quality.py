#!/usr/bin/env python3
"""Check quality of pattern_name and episode_summary after fixes."""

import asyncio

import asyncpg


async def check():
    dsn = "postgresql://k0user:changeme@localhost:5432/k0_kernel"
    conn = await asyncpg.connect(dsn)

    print("=" * 70)
    print("st_sem: pattern_name quality check")
    print("=" * 70)
    rows = await conn.fetch("SELECT pattern_name, pattern_type FROM st_sem LIMIT 15")
    for r in rows:
        ptype = r["pattern_type"] or "NULL"
        pname = r["pattern_name"] or "NULL"
        print(f"  {ptype:15} | {pname[:60]}")

    print("\n" + "=" * 70)
    print("st_epi: episode_summary quality check")
    print("=" * 70)
    rows = await conn.fetch(
        "SELECT episode_summary, episode_type, primary_location FROM st_epi LIMIT 10"
    )
    for r in rows:
        etype = r["episode_type"] or "NULL"
        summary = r["episode_summary"] or "NULL"
        loc = r["primary_location"] or "NULL"
        print(f"  {etype:12} @ {loc:20} | {summary[:50]}")

    print("\n" + "=" * 70)
    print("st_social: relationship info check")
    print("=" * 70)
    rows = await conn.fetch("SELECT person_a, relationship_type, person_b FROM st_social LIMIT 10")
    for r in rows:
        a = r["person_a"] or "?"
        b = r["person_b"] or "?"
        rtype = r["relationship_type"] or "NULL"
        print(f"  {a:15} --[{rtype:15}]--> {b}")

    print("\n" + "=" * 70)
    print("st_kg_dom: entity_subtype check")
    print("=" * 70)
    rows = await conn.fetch(
        "SELECT canonical_name, entity_type, entity_subtype FROM st_kg_dom LIMIT 10"
    )
    for r in rows:
        name = r["canonical_name"] or "?"
        etype = r["entity_type"] or "NULL"
        subtype = r["entity_subtype"] or "NULL"
        print(f"  {name:20} | {etype:10} | {subtype}")

    await conn.close()
    print("\n✅ Quality check complete")


if __name__ == "__main__":
    asyncio.run(check())
