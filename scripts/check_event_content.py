import asyncio

import asyncpg


async def check_actual_event_content():
    dsn = "postgresql://k0user:changeme@localhost:5432/k0_kernel"
    conn = await asyncpg.connect(dsn)

    # Get events with actual emotions and their content
    events = await conn.fetch(
        """
        SELECT event_id, text, dominant_emotions_json, affect_valence, affect_arousal, sentiment_score
        FROM st_hipp_events
        WHERE dominant_emotions_json IS NOT NULL
        AND dominant_emotions_json != '["neutral"]'
        ORDER BY created_at DESC
        LIMIT 10
    """
    )

    print("Events with non-neutral emotions:")
    for row in events:
        print(f'Event {row["event_id"][:8]}...')
        print(f'  Content: {row["text"][:100]}...')
        print(f'  Emotions: {row["dominant_emotions_json"]}')
        print(f'  Valence: {row["affect_valence"]}')
        print(f'  Arousal: {row["affect_arousal"]}')
        print(f'  Sentiment Score: {row["sentiment_score"]}')
        print()

    await conn.close()


if __name__ == "__main__":
    asyncio.run(check_actual_event_content())
if __name__ == "__main__":
    asyncio.run(check_actual_event_content())
