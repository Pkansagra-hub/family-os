#!/usr/bin/env python3
"""Query all memory layers to see complete memory formation."""

import asyncio

import asyncpg


async def query():
    conn = await asyncpg.connect("postgresql://k0user:changeme@localhost:5432/k0_kernel")

    print("=" * 80)
    print("MEMORY FORMATION SUMMARY")
    print("=" * 80)

    # st_epi - Episodic memories
    epi_count = await conn.fetchval("SELECT COUNT(*) FROM st_epi")
    print(f"Episodic Memories (st_epi): {epi_count}")

    # st_sem - Semantic patterns
    sem_count = await conn.fetchval("SELECT COUNT(*) FROM st_sem")
    print(f"Semantic Patterns (st_sem): {sem_count}")

    # st_kg_dom - Knowledge graph entities
    kg_count = await conn.fetchval("SELECT COUNT(*) FROM st_kg_dom")
    print(f"KG Entities (st_kg_dom): {kg_count}")

    # st_social - Social relationships
    social_count = await conn.fetchval("SELECT COUNT(*) FROM st_social")
    print(f"Social Relationships (st_social): {social_count}")

    # st_prospective - Prospective memories (reminders)
    prosp_count = await conn.fetchval("SELECT COUNT(*) FROM st_prospective")
    print(f"Prospective Memories (st_prospective): {prosp_count}")

    # st_observations - Observations
    obs_count = await conn.fetchval("SELECT COUNT(*) FROM st_observations")
    print(f"Total Observations (st_observations): {obs_count}")

    print("\n" + "=" * 80)
    print("PEOPLE DETECTED (KG Entities)")
    print("=" * 80)
    rows = await conn.fetch(
        """
        SELECT canonical_name
        FROM st_kg_dom
        ORDER BY canonical_name
        LIMIT 20
    """
    )
    for r in rows:
        name = r["canonical_name"] or "NULL"
        print(f"  {name}")

    print("\n" + "=" * 80)
    print("OBSERVATION CONTEXT DISTRIBUTION")
    print("=" * 80)

    # By layer
    rows = await conn.fetch(
        """
        SELECT layer, COUNT(*) as cnt
        FROM st_observations
        GROUP BY layer
        ORDER BY cnt DESC
    """
    )
    print("By Layer:")
    for r in rows:
        print(f"  {r['layer']}: {r['cnt']}")

    # By temporal context
    rows = await conn.fetch(
        """
        SELECT time_of_day_bucket, COUNT(*) as cnt
        FROM st_observations
        WHERE time_of_day_bucket IS NOT NULL
        GROUP BY time_of_day_bucket
        ORDER BY cnt DESC
    """
    )
    print("\nBy Time of Day:")
    for r in rows:
        print(f"  {r['time_of_day_bucket']}: {r['cnt']}")

    # By weekend
    rows = await conn.fetch(
        """
        SELECT is_weekend, COUNT(*) as cnt
        FROM st_observations
        WHERE is_weekend IS NOT NULL
        GROUP BY is_weekend
    """
    )
    print("\nBy Weekend/Weekday:")
    for r in rows:
        label = "Weekend" if r["is_weekend"] else "Weekday"
        print(f"  {label}: {r['cnt']}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(query())
