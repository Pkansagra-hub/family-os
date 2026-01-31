import asyncio

import asyncpg


async def check_emotions():
    dsn = 'postgresql://k0user:changeme@localhost:5432/k0_kernel'
    conn = await asyncpg.connect(dsn)

    # Check emotion-related columns in st_hipp_events
    emotion_cols = await conn.fetch('''
        SELECT
            COUNT(*) as total_events,
            COUNT(dominant_emotions_json) as has_emotions,
            COUNT(affect_valence) as has_valence,
            COUNT(affect_arousal) as has_arousal,
            COUNT(sentiment_score) as has_sentiment,
            COUNT(sentiment_label) as has_sentiment_label
        FROM st_hipp_events
    ''')

    print('Emotion Data Population:')
    print(f'  Total events: {emotion_cols[0]["total_events"]}')
    print(f'  With dominant_emotions_json: {emotion_cols[0]["has_emotions"]}')
    print(f'  With affect_valence: {emotion_cols[0]["has_valence"]}')
    print(f'  With affect_arousal: {emotion_cols[0]["has_arousal"]}')
    print(f'  With sentiment_score: {emotion_cols[0]["has_sentiment"]}')
    print(f'  With sentiment_label: {emotion_cols[0]["has_sentiment_label"]}')

    # Sample emotion data
    sample = await conn.fetch('''
        SELECT event_id, dominant_emotions_json, affect_valence, affect_arousal,
               sentiment_score, sentiment_label
        FROM st_hipp_events
        WHERE dominant_emotions_json IS NOT NULL
        LIMIT 5
    ''')

    print('\nSample Emotion Data:')
    for row in sample:
        print(f'  Event {row["event_id"][:8]}...')
        print(f'    Emotions: {row["dominant_emotions_json"]}')
        print(f'    Valence: {row["affect_valence"]}')
        print(f'    Arousal: {row["affect_arousal"]}')
        print(f'    Sentiment Score: {row["sentiment_score"]}')
        print(f'    Sentiment Label: {row["sentiment_label"]}')
        print()

    # Check value distributions
    valence_stats = await conn.fetch('''
        SELECT
            MIN(affect_valence) as min_valence,
            MAX(affect_valence) as max_valence,
            AVG(affect_valence) as avg_valence,
            COUNT(CASE WHEN affect_valence > 0 THEN 1 END) as positive_valence,
            COUNT(CASE WHEN affect_valence < 0 THEN 1 END) as negative_valence
        FROM st_hipp_events
        WHERE affect_valence IS NOT NULL
    ''')

    arousal_stats = await conn.fetch('''
        SELECT
            MIN(affect_arousal) as min_arousal,
            MAX(affect_arousal) as max_arousal,
            AVG(affect_arousal) as avg_arousal,
            COUNT(CASE WHEN affect_arousal > 0.5 THEN 1 END) as high_arousal,
            COUNT(CASE WHEN affect_arousal <= 0.5 THEN 1 END) as low_arousal
        FROM st_hipp_events
        WHERE affect_arousal IS NOT NULL
    ''')

    print('Valence Statistics:')
    if valence_stats[0]['min_valence'] is not None:
        print(f'  Range: {valence_stats[0]["min_valence"]:.3f} to {valence_stats[0]["max_valence"]:.3f}')
        print(f'  Average: {valence_stats[0]["avg_valence"]:.3f}')
        print(f'  Positive: {valence_stats[0]["positive_valence"]}, Negative: {valence_stats[0]["negative_valence"]}')
    else:
        print('  No valence data')

    print('Arousal Statistics:')
    if arousal_stats[0]['min_arousal'] is not None:
        print(f'  Range: {arousal_stats[0]["min_arousal"]:.3f} to {arousal_stats[0]["max_arousal"]:.3f}')
        print(f'  Average: {arousal_stats[0]["avg_arousal"]:.3f}')
        print(f'  High (>0.5): {arousal_stats[0]["high_arousal"]}, Low (<=0.5): {arousal_stats[0]["low_arousal"]}')
    else:
        print('  No arousal data')

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_emotions())if __name__ == "__main__":
    asyncio.run(check_emotions())
