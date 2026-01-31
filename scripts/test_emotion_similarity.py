import asyncio
import json
from collections import Counter

import asyncpg


async def test_emotion_similarity():
    dsn = 'postgresql://k0user:changeme@localhost:5432/k0_kernel'
    conn = await asyncpg.connect(dsn)

    # Get sample emotion data
    emotion_data = await conn.fetch('''
        SELECT event_id, dominant_emotions_json, affect_valence, affect_arousal
        FROM st_hipp_events
        WHERE dominant_emotions_json IS NOT NULL
        LIMIT 10
    ''')

    print("Sample Emotion Data:")
    for row in emotion_data:
        print(f"Event {row['event_id'][:8]}: emotions={row['dominant_emotions_json']}, valence={row['affect_valence']}, arousal={row['affect_arousal']}")

    # Build emotion vectors like the enricher does
    emotion_vectors = {}
    for row in emotion_data:
        entity_id = f"entity_{row['event_id'][:8]}"  # Mock entity ID
        emotions = json.loads(row['dominant_emotions_json'])
        emotion_counter = Counter(emotions)
        total_emotions = sum(emotion_counter.values())
        vector = {emotion: count / total_emotions for emotion, count in emotion_counter.items()}

        # Add arousal intensity
        avg_arousal = row['affect_arousal'] or 0.0
        vector["_arousal_intensity"] = avg_arousal * 0.3  # arousal_weight = 0.3

        emotion_vectors[entity_id] = vector

    print("\nEmotion Vectors:")
    for entity_id, vector in emotion_vectors.items():
        print(f"{entity_id}: {vector}")

    # Test similarity computation
    def compute_similarity(vec_a, vec_b):
        all_emotions = set(vec_a.keys()) | set(vec_b.keys())
        vec_a_aligned = [vec_a.get(emotion, 0.0) for emotion in all_emotions]
        vec_b_aligned = [vec_b.get(emotion, 0.0) for emotion in all_emotions]

        dot_product = sum(a * b for a, b in zip(vec_a_aligned, vec_b_aligned))
        norm_a = sum(a * a for a in vec_a_aligned) ** 0.5
        norm_b = sum(b * b for b in vec_b_aligned) ** 0.5

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    print("\nSimilarity Matrix (threshold = 0.6):")
    entity_ids = list(emotion_vectors.keys())
    for i, entity_a in enumerate(entity_ids):
        for entity_b in entity_ids[i+1:]:
            vec_a = emotion_vectors[entity_a]
            vec_b = emotion_vectors[entity_b]
            similarity = compute_similarity(vec_a, vec_b)
            meets_threshold = similarity >= 0.6
            status = "✓" if meets_threshold else "✗"
            print(f"{entity_a} ↔ {entity_b}: {similarity:.3f} {status}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(test_emotion_similarity())if __name__ == "__main__":
    asyncio.run(test_emotion_similarity())
