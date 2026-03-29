#!/usr/bin/env python3
"""Query st_observations to verify holistic context data - P01 Read queries."""

import asyncio

import asyncpg


async def query():
    conn = await asyncpg.connect("postgresql://k0user:changeme@localhost:5432/k0_kernel")

    # Count total
    count = await conn.fetchval("SELECT COUNT(*) FROM st_observations")
    print(f"Total observations: {count}")
    print("=" * 80)

    # Temporal distribution
    rows = await conn.fetch(
        """
        SELECT time_of_day_bucket, circadian_slot, is_weekend, COUNT(*) as cnt
        FROM st_observations
        GROUP BY time_of_day_bucket, circadian_slot, is_weekend
        ORDER BY cnt DESC
    """
    )
    print("Temporal Context Distribution:")
    print("-" * 50)
    for r in rows:
        bucket = r["time_of_day_bucket"] or "NULL"
        slot = r["circadian_slot"] or "NULL"
        weekend = r["is_weekend"]
        cnt = r["cnt"]
        print(f"  {bucket:10} | {slot:15} | weekend={weekend!s:5} | count={cnt}")

    # ================================================================
    # P01 Read Queries (from temporal_fix.md)
    # ================================================================

    # Query 7: Modality Analysis
    print("\n" + "=" * 80)
    print("MODALITY ANALYSIS: 'What do I say out loud vs type?'")
    print("-" * 50)
    rows = await conn.fetch(
        """
        SELECT
          ingress_channel,
          COUNT(*) AS observation_count,
          AVG(sentiment_score) AS avg_sentiment,
          AVG(salience_score) AS avg_importance
        FROM st_observations
        WHERE ingress_channel IS NOT NULL
        GROUP BY ingress_channel
        ORDER BY observation_count DESC
    """
    )
    for r in rows:
        channel = r["ingress_channel"]
        cnt = r["observation_count"]
        sentiment = r["avg_sentiment"]
        salience = r["avg_importance"]
        print(f"  {channel}: count={cnt}, sentiment={sentiment}, salience={salience}")

    # Query 11: Circadian Pattern Analysis
    print("\n" + "=" * 80)
    print("CIRCADIAN PATTERNS: 'When am I most productive?'")
    print("-" * 50)
    rows = await conn.fetch(
        """
        SELECT
          time_of_day_bucket,
          circadian_slot,
          COUNT(*) as cnt,
          AVG(salience_score) AS avg_importance
        FROM st_observations
        WHERE time_of_day_bucket IS NOT NULL
        GROUP BY time_of_day_bucket, circadian_slot
        ORDER BY cnt DESC
    """
    )
    for r in rows:
        bucket = r["time_of_day_bucket"] or "NULL"
        slot = r["circadian_slot"] or "NULL"
        cnt = r["cnt"]
        salience = r["avg_importance"]
        print(f"  {bucket:10} | {slot:15} | count={cnt} | salience={salience}")

    # Query: Weekend vs Weekday sentiment
    print("\n" + "=" * 80)
    print("WEEKEND VS WEEKDAY: 'Am I happier on weekends?'")
    print("-" * 50)
    rows = await conn.fetch(
        """
        SELECT
          is_weekend,
          COUNT(*) as cnt,
          AVG(sentiment_score) AS avg_sentiment
        FROM st_observations
        WHERE is_weekend IS NOT NULL
        GROUP BY is_weekend
    """
    )
    for r in rows:
        label = "Weekend" if r["is_weekend"] else "Weekday"
        cnt = r["cnt"]
        sentiment = r["avg_sentiment"]
        print(f"  {label}: count={cnt}, avg_sentiment={sentiment}")

    # Query by day_of_week
    print("\n" + "=" * 80)
    print("DAY OF WEEK DISTRIBUTION:")
    print("-" * 50)
    rows = await conn.fetch(
        """
        SELECT
          day_of_week,
          COUNT(*) as cnt
        FROM st_observations
        WHERE day_of_week IS NOT NULL
        GROUP BY day_of_week
        ORDER BY cnt DESC
    """
    )
    for r in rows:
        day = r["day_of_week"]
        cnt = r["cnt"]
        print(f"  {day}: count={cnt}")

    # Query by layer distribution
    print("\n" + "=" * 80)
    print("LAYER DISTRIBUTION:")
    print("-" * 50)
    rows = await conn.fetch(
        """
        SELECT
          layer,
          COUNT(*) as cnt
        FROM st_observations
        GROUP BY layer
        ORDER BY cnt DESC
    """
    )
    for r in rows:
        layer = r["layer"]
        cnt = r["cnt"]
        print(f"  {layer}: count={cnt}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(query())
