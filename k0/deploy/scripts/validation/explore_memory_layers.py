"""
Explore all memory layers and their relationship with st_observations
to understand how we can build a holistic view of a person's life.

This script shows REAL EXAMPLES from the memories that were formed.
"""

import asyncio
import json

import asyncpg


async def explore_all_layers():
    conn = await asyncpg.connect("postgresql://k0user:changeme@localhost:5432/k0_kernel")

    print("=" * 100)
    print("🧠 MEMORY LAYERS DEEP DIVE - REAL EXAMPLES FROM YOUR LIFE")
    print("=" * 100)

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. EPISODIC MEMORIES (st_epi) - "What happened in my life?"
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 100)
    print("1. EPISODIC MEMORIES (st_epi)")
    print("   Purpose: Stores autobiographical events - 'What happened, when, where, with whom'")
    print("═" * 100)

    # Show count
    count = await conn.fetchval("SELECT COUNT(*) FROM st_epi")
    print(f"\n   📊 Total Episodes: {count}")

    # Show real examples with source texts
    print("\n   🔍 REAL EXAMPLES FROM YOUR LIFE:")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT episode_id, episode_summary, episode_type,
               primary_location, participants_json, source_texts_json,
               source_event_count
        FROM st_epi
        ORDER BY created_at DESC
        LIMIT 5
    """
    )

    for i, r in enumerate(rows, 1):
        print(f"\n   📌 Episode {i}: {r['episode_summary']}")
        print(f"      Type: {r['episode_type']} | Location: {r['primary_location']}")
        print(f"      Participants: {r['participants_json']}")

        # Parse and show source texts (the actual memory content)
        if r["source_texts_json"]:
            try:
                texts = json.loads(r["source_texts_json"])
                if texts:
                    print("      📝 Original Memory:")
                    # Show first unique text
                    shown = set()
                    for text in texts[:2]:
                        if text not in shown:
                            shown.add(text)
                            print(f"         \"{text[:100]}{'...' if len(text) > 100 else ''}\"")
            except:
                pass

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. SEMANTIC MEMORY (st_sem) - "What patterns have I learned?"
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("2. SEMANTIC MEMORY (st_sem)")
    print("   Purpose: Stores facts, patterns, and generalizations extracted from experiences")
    print("═" * 100)

    count = await conn.fetchval("SELECT COUNT(*) FROM st_sem")
    print(f"\n   📊 Total Patterns: {count}")

    print("\n   🔍 REAL PATTERNS FROM YOUR EXPERIENCES:")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT pattern_id, pattern_name, pattern_description, pattern_type,
               pattern_subtype, source_texts_json, confidence_score
        FROM st_sem
        ORDER BY created_at DESC
        LIMIT 5
    """
    )

    for i, r in enumerate(rows, 1):
        print(f"\n   🧩 Pattern {i}: {r['pattern_name']}")
        print(f"      Type: {r['pattern_type']}/{r['pattern_subtype']}")
        print(f"      Confidence: {r['confidence_score']:.2f}")

        if r["source_texts_json"]:
            try:
                texts = json.loads(r["source_texts_json"])
                if texts:
                    print("      📝 Learned from:")
                    shown = set()
                    for text in texts[:2]:
                        if text not in shown:
                            shown.add(text)
                            print(f"         \"{text[:100]}{'...' if len(text) > 100 else ''}\"")
            except:
                pass

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. KNOWLEDGE GRAPH (st_kg_dom) - "What entities exist in my world?"
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("3. KNOWLEDGE GRAPH ENTITIES (st_kg_dom)")
    print("   Purpose: Stores entities (people, places, things) and their attributes")
    print("═" * 100)

    count = await conn.fetchval("SELECT COUNT(*) FROM st_kg_dom")
    print(f"\n   📊 Total Entities: {count}")

    # Group by type
    print("\n   📋 ENTITIES BY TYPE:")
    type_counts = await conn.fetch(
        """
        SELECT entity_type, COUNT(*) as cnt,
               array_agg(canonical_name ORDER BY observation_count DESC) as examples
        FROM st_kg_dom
        GROUP BY entity_type
        ORDER BY cnt DESC
    """
    )

    for r in type_counts:
        examples = r["examples"][:5] if r["examples"] else []
        examples_str = ", ".join(examples)
        print(f"      {r['entity_type']}: {r['cnt']} entities")
        print(f"         Examples: {examples_str}")

    print("\n   🔍 REAL ENTITIES FROM YOUR LIFE:")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT canonical_name, entity_type, source_texts_json, attributes_json
        FROM st_kg_dom
        WHERE entity_type = 'PERSON'
        ORDER BY observation_count DESC
        LIMIT 5
    """
    )

    for i, r in enumerate(rows, 1):
        print(f"\n   👤 Person {i}: {r['canonical_name']}")
        if r["source_texts_json"]:
            try:
                texts = json.loads(r["source_texts_json"])
                if texts:
                    print("      📝 Mentioned in:")
                    for text in texts[:2]:
                        print(f"         \"{text[:100]}{'...' if len(text) > 100 else ''}\"")
            except:
                pass

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. SOCIAL RELATIONSHIPS (st_social) - "Who matters to me?"
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("4. SOCIAL RELATIONSHIPS (st_social)")
    print("   Purpose: Stores relationships between the person and others")
    print("═" * 100)

    count = await conn.fetchval("SELECT COUNT(*) FROM st_social")
    print(f"\n   📊 Total Relationships: {count}")

    print("\n   🔍 YOUR KEY RELATIONSHIPS:")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT relationship_label, relationship_type, interaction_count,
               source_texts_json, avg_sentiment, dominant_emotion
        FROM st_social
        ORDER BY interaction_count DESC
        LIMIT 6
    """
    )

    for i, r in enumerate(rows, 1):
        sent = r["avg_sentiment"] if r["avg_sentiment"] else 0
        emotion = r["dominant_emotion"] if r["dominant_emotion"] else "neutral"
        print(f"\n   💛 {r['relationship_label']} ({r['relationship_type']})")
        print(
            f"      Interactions: {r['interaction_count']} | Sentiment: {sent:.2f} | Emotion: {emotion}"
        )

        if r["source_texts_json"]:
            try:
                texts = json.loads(r["source_texts_json"])
                if texts:
                    print("      📝 Memories together:")
                    shown = set()
                    for text in texts[:3]:
                        if text not in shown:
                            shown.add(text)
                            print(f"         \"{text[:90]}{'...' if len(text) > 90 else ''}\"")
            except:
                pass

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. PROSPECTIVE MEMORY (st_prospective) - "What do I need to do?"
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("5. PROSPECTIVE MEMORY (st_prospective)")
    print("   Purpose: Stores future intentions, reminders, and planned actions")
    print("═" * 100)

    count = await conn.fetchval("SELECT COUNT(*) FROM st_prospective")
    print(f"\n   📊 Total Intentions/Reminders: {count}")

    print("\n   🔍 YOUR REMINDERS & DECISIONS:")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT intention_description, intention_type, status,
               source_texts_json, confidence_score
        FROM st_prospective
        ORDER BY created_at DESC
        LIMIT 6
    """
    )

    for i, r in enumerate(rows, 1):
        icon = "⏰" if r["intention_type"] == "REMINDER" else "🤔"
        print(f"\n   {icon} {r['intention_type']}: {r['intention_description']}")
        conf = r["confidence_score"] if r["confidence_score"] else 0
        print(f"      Status: {r['status']} | Confidence: {conf:.2f}")

        if r["source_texts_json"]:
            try:
                texts = json.loads(r["source_texts_json"])
                if texts:
                    print("      📝 From:")
                    for text in texts[:1]:
                        print(f"         \"{text[:100]}{'...' if len(text) > 100 else ''}\"")
            except:
                pass

    # ═══════════════════════════════════════════════════════════════════════════
    # 6. ST_OBSERVATIONS - "The Holistic Context Layer"
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("6. ST_OBSERVATIONS - THE HOLISTIC CONTEXT LAYER")
    print("   Purpose: Links every memory write to its full contextual situation")
    print("═" * 100)

    count = await conn.fetchval("SELECT COUNT(*) FROM st_observations")
    print(f"\n   📊 Total Observations: {count}")

    # Distribution by layer
    print("\n   📋 OBSERVATIONS BY MEMORY LAYER:")
    layer_counts = await conn.fetch(
        """
        SELECT layer, COUNT(*) as cnt,
               AVG(sentiment_score) as avg_sent
        FROM st_observations
        GROUP BY layer
        ORDER BY cnt DESC
    """
    )

    for r in layer_counts:
        sent = r["avg_sent"] if r["avg_sent"] else 0
        print(f"      {r['layer']}: {r['cnt']} observations (avg sentiment: {sent:.2f})")

    # ═══════════════════════════════════════════════════════════════════════════
    # HOLISTIC QUERIES - Combining Memories with Context
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("🔗 HOLISTIC QUERIES - MEMORIES WITH FULL CONTEXT")
    print("═" * 100)

    # Query 1: Most TRULY joyful episodes (emotion-based, not just high sentiment)
    print("\n   📊 QUERY 1: Most Joyful Episodes (emotion = joy/love/gratitude)")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT
            e.episode_summary,
            e.primary_location,
            e.participants_json,
            e.source_texts_json,
            o.sentiment_score,
            o.dominant_emotion,
            o.time_of_day_bucket,
            o.circadian_slot,
            o.is_weekend,
            o.social_context
        FROM st_epi e
        JOIN st_observations o ON o.layer = 'st_epi' AND o.record_id = e.episode_id
        WHERE o.dominant_emotion IN ('joy', 'love', 'gratitude', 'pride', 'caring')
          AND o.sentiment_score >= 0.6
          AND e.episode_type NOT IN ('work', 'routine')  -- Focus on personal moments
        ORDER BY o.sentiment_score DESC, o.dominant_emotion
        LIMIT 3
    """
    )

    for i, r in enumerate(rows, 1):
        print(f"\n   🌟 #{i} {r['episode_summary']}")
        print(f"      📍 Location: {r['primary_location']} | 👥 With: {r['participants_json']}")
        print(
            f"      ⏰ Time: {r['time_of_day_bucket']}/{r['circadian_slot']} | Weekend: {r['is_weekend']}"
        )
        print(f"      💚 Sentiment: {r['sentiment_score']:.2f} | Emotion: {r['dominant_emotion']}")

        if r["source_texts_json"]:
            try:
                texts = json.loads(r["source_texts_json"])
                if texts:
                    shown = set()
                    for text in texts[:1]:
                        if text not in shown:
                            shown.add(text)
                            print(f"      📝 \"{text[:100]}{'...' if len(text) > 100 else ''}\"")
            except:
                pass

    # Query 2: Relationships with emotional context
    print("\n\n   📊 QUERY 2: Relationships - Who Brings Joy?")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT
            s.relationship_label,
            s.relationship_type,
            s.interaction_count,
            s.source_texts_json,
            AVG(o.sentiment_score) as avg_sentiment,
            array_agg(DISTINCT o.dominant_emotion) FILTER (WHERE o.dominant_emotion IS NOT NULL) as emotions
        FROM st_social s
        LEFT JOIN st_observations o ON o.layer = 'st_social' AND o.record_id = s.relationship_id
        GROUP BY s.relationship_label, s.relationship_type, s.interaction_count, s.source_texts_json
        ORDER BY s.interaction_count DESC
        LIMIT 4
    """
    )

    for r in rows:
        sent = r["avg_sentiment"] if r["avg_sentiment"] else 0
        emotions = r["emotions"] if r["emotions"] else ["neutral"]
        print(f"\n   👤 {r['relationship_label']} ({r['relationship_type']})")
        print(f"      Interactions: {r['interaction_count']} | Avg Sentiment: {sent:.2f}")
        print(f"      Emotions: {emotions}")

        if r["source_texts_json"]:
            try:
                texts = json.loads(r["source_texts_json"])
                if texts:
                    print("      📝 Sample memories:")
                    shown = set()
                    for text in texts[:2]:
                        if text not in shown:
                            shown.add(text)
                            print(f"         \"{text[:80]}{'...' if len(text) > 80 else ''}\"")
            except:
                pass

    # Query 3: Emotional patterns by time of day
    print("\n\n   📊 QUERY 3: When Are You Happiest? (Time-of-Day Analysis)")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT
            circadian_slot,
            AVG(sentiment_score) as avg_sentiment,
            COUNT(*) as memory_count,
            array_agg(DISTINCT dominant_emotion) FILTER (WHERE dominant_emotion IS NOT NULL) as emotions
        FROM st_observations
        WHERE circadian_slot IS NOT NULL AND circadian_slot != ''
        GROUP BY circadian_slot
        ORDER BY avg_sentiment DESC
    """
    )

    for r in rows:
        sent = r["avg_sentiment"] if r["avg_sentiment"] else 0
        emotions = r["emotions"][:3] if r["emotions"] else []
        print(f"\n   ⏰ {r['circadian_slot']}")
        print(f"      Avg Sentiment: {sent:.3f} | Memories: {r['memory_count']}")
        print(f"      Common Emotions: {emotions}")

    # ═══════════════════════════════════════════════════════════════════════════
    # LIFE STORY SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("📖 YOUR LIFE STORY - A HOLISTIC VIEW")
    print("═" * 100)

    # Get key people
    people = await conn.fetch(
        """
        SELECT relationship_label, relationship_type, interaction_count
        FROM st_social
        ORDER BY interaction_count DESC
        LIMIT 5
    """
    )

    # Get key places
    places = await conn.fetch(
        """
        SELECT canonical_name, observation_count
        FROM st_kg_dom
        WHERE entity_type = 'LOCATION'
        ORDER BY observation_count DESC
        LIMIT 5
    """
    )

    # Get emotional summary
    emotions = await conn.fetch(
        """
        SELECT dominant_emotion, COUNT(*) as cnt
        FROM st_observations
        WHERE dominant_emotion IS NOT NULL AND dominant_emotion != ''
        GROUP BY dominant_emotion
        ORDER BY cnt DESC
        LIMIT 5
    """
    )

    # Get pending reminders
    reminders = await conn.fetch(
        """
        SELECT intention_description, intention_type
        FROM st_prospective
        WHERE status = 'ACTIVE'
        LIMIT 3
    """
    )

    print(
        """
   Based on your memories, here's what the system knows about your life:
    """
    )

    print("   👥 KEY PEOPLE IN YOUR LIFE:")
    for p in people:
        print(
            f"      • {p['relationship_label']} ({p['relationship_type']}) - {p['interaction_count']} interactions"
        )

    print("\n   📍 PLACES YOU FREQUENT:")
    for p in places:
        print(f"      • {p['canonical_name']}")

    print("\n   💚 YOUR EMOTIONAL LANDSCAPE:")
    for e in emotions:
        print(f"      • {e['dominant_emotion']}: {e['cnt']} memories")

    print("\n   ⏰ THINGS ON YOUR MIND:")
    for r in reminders:
        icon = "⏰" if r["intention_type"] == "REMINDER" else "🤔"
        print(f"      {icon} {r['intention_description'][:70]}...")

    # ═══════════════════════════════════════════════════════════════════════════
    # HOW THIS CREATES A HOLISTIC VIEW
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("🧠 HOW ST_OBSERVATIONS ENABLES A HOLISTIC VIEW")
    print("═" * 100)

    print(
        """
   ST_OBSERVATIONS acts as a universal context layer that:

   1. LINKS ALL MEMORY LAYERS
      ┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
      │  st_epi     │────▶│ st_observations  │◀────│  st_social  │
      │  Episodes   │     │  Context Layer   │     │ Relationships│
      └─────────────┘     └────────┬─────────┘     └─────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
               ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
               │ st_sem  │   │st_kg_dom│   │st_prosp │
               │Patterns │   │Entities │   │Reminders│
               └─────────┘   └─────────┘   └─────────┘

   2. CAPTURES HOLISTIC CONTEXT FOR EACH MEMORY:
      • TEMPORAL: When did this happen? (morning/evening, weekend/weekday)
      • SOCIAL: Who was involved? Solo or with others?
      • EMOTIONAL: How did you feel? What was the dominant emotion?
      • SALIENCE: How important was this moment?

   3. ENABLES POWERFUL RECALL QUERIES:
      • "How do I feel on weekends?" → Filter by is_weekend
      • "Happiest memories with Emma" → Join social + filter sentiment
      • "What happens in evenings?" → Filter by circadian_slot
      • "Most important memories" → Sort by salience_score

   ┌─────────────────────────────────────────────────────────────────────────┐
   │  THE HOLISTIC VIEW FORMULA:                                             │
   │                                                                         │
   │  Memory Content + Temporal Context + Social Context + Emotional State   │
   │                                                                         │
   │  = A Complete Picture of How, When, Where, and Why Memories Form        │
   └─────────────────────────────────────────────────────────────────────────┘
    """
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. RELATIONSHIP DEEP DIVE - Co-occurrence & Emotional Trajectory
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("💑 RELATIONSHIP DEEP DIVE - Who Appears Together?")
    print("═" * 100)

    # Co-occurrence analysis from episodes
    print("\n   📊 CO-OCCURRENCE MATRIX (Who appears together in episodes?):")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT participants_json, episode_summary, source_texts_json
        FROM st_epi
        WHERE participant_count > 1
        ORDER BY participant_count DESC
        LIMIT 8
    """
    )

    co_occurrences = {}
    for r in rows:
        if r["participants_json"]:
            try:
                participants = json.loads(r["participants_json"])
                if len(participants) > 1:
                    # Create pairs
                    for i, p1 in enumerate(participants):
                        for p2 in participants[i + 1 :]:
                            pair = tuple(sorted([p1, p2]))
                            if pair not in co_occurrences:
                                co_occurrences[pair] = []
                            texts = (
                                json.loads(r["source_texts_json"]) if r["source_texts_json"] else []
                            )
                            co_occurrences[pair].append(texts[0] if texts else r["episode_summary"])
            except Exception:
                pass

    for pair, memories in sorted(co_occurrences.items(), key=lambda x: -len(x[1]))[:6]:
        print(f"\n   👥 {pair[0]} + {pair[1]} ({len(memories)} memories together)")
        for mem in memories[:2]:
            print(f"      📝 \"{mem[:80]}{'...' if len(mem) > 80 else ''}\"")

    # Emotional trajectory per person
    print("\n\n   📊 EMOTIONAL TRAJECTORY BY PERSON:")
    print("   " + "─" * 90)

    rows = await conn.fetch(
        """
        SELECT
            s.relationship_label as person,
            s.relationship_type,
            s.dominant_emotion,
            s.avg_sentiment,
            s.interaction_count,
            s.source_texts_json
        FROM st_social s
        ORDER BY s.interaction_count DESC
        LIMIT 6
    """
    )

    for r in rows:
        sent = r["avg_sentiment"] if r["avg_sentiment"] else 0
        emotion = r["dominant_emotion"] if r["dominant_emotion"] else "neutral"
        emoji = (
            "😊"
            if emotion in ["joy", "love", "excitement"]
            else "😐" if emotion == "neutral" else "😔"
        )
        print(f"\n   {emoji} {r['person']} ({r['relationship_type']})")
        print(f"      Interactions: {r['interaction_count']} | Dominant Emotion: {emotion}")
        print(f"      Sentiment Score: {sent:.2f}")

        if r["source_texts_json"]:
            try:
                texts = json.loads(r["source_texts_json"])
                if texts:
                    print("      📝 Sample memories:")
                    shown = set()
                    for text in texts[:2]:
                        if text not in shown:
                            shown.add(text)
                            print(f"         \"{text[:70]}{'...' if len(text) > 70 else ''}\"")
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════════════════════
    # 8. EMOTIONAL JOURNEY - 3-Day Arc
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("🎭 EMOTIONAL JOURNEY - Your 3-Day Emotional Arc")
    print("═" * 100)

    # Get emotions by category from events
    rows = await conn.fetch(
        """
        SELECT
            dominant_emotion,
            sentiment_score,
            layer,
            COUNT(*) as count
        FROM st_observations
        WHERE dominant_emotion IS NOT NULL AND dominant_emotion != ''
        GROUP BY dominant_emotion, sentiment_score, layer
        ORDER BY count DESC
    """
    )

    # Categorize emotions
    positive_emotions = [
        "joy",
        "love",
        "excitement",
        "gratitude",
        "pride",
        "contentment",
        "relief",
        "hope",
    ]
    negative_emotions = [
        "sadness",
        "anger",
        "fear",
        "anxiety",
        "frustration",
        "annoyance",
        "nervousness",
    ]

    pos_count = 0
    neg_count = 0
    neutral_count = 0

    for r in rows:
        if r["dominant_emotion"].lower() in positive_emotions:
            pos_count += r["count"]
        elif r["dominant_emotion"].lower() in negative_emotions:
            neg_count += r["count"]
        else:
            neutral_count += r["count"]

    total = pos_count + neg_count + neutral_count

    pos_bar = "█" * (pos_count * 30 // total if total else 0)
    neu_bar = "█" * (neutral_count * 30 // total if total else 0)
    neg_bar = "█" * (neg_count * 30 // total if total else 0)

    print(
        f"""
   📊 EMOTIONAL DISTRIBUTION:

   Positive Emotions: {pos_count} memories ({pos_count*100//total if total else 0}%)
   {pos_bar}
   (joy, love, excitement, gratitude, pride, contentment)

   Neutral Emotions: {neutral_count} memories ({neutral_count*100//total if total else 0}%)
   {neu_bar}

   Negative Emotions: {neg_count} memories ({neg_count*100//total if total else 0}%)
   {neg_bar}
   (sadness, anxiety, frustration, nervousness)
    """
    )

    # Emotion triggers
    print("\n   🎯 EMOTION TRIGGERS - What Causes Each Emotion?")
    print("   " + "─" * 90)

    emotions_to_analyze = ["joy", "love", "nervousness", "sadness", "pride"]

    for emotion in emotions_to_analyze:
        rows = await conn.fetch(
            """
            SELECT e.source_texts_json, e.episode_summary
            FROM st_epi e
            JOIN st_observations o ON o.layer = 'st_epi' AND o.record_id = e.episode_id
            WHERE o.dominant_emotion = $1
            LIMIT 2
        """,
            emotion,
        )

        if rows:
            emoji = (
                "😊"
                if emotion in ["joy", "love", "pride"]
                else "😰" if emotion == "nervousness" else "😢"
            )
            print(f"\n   {emoji} {emotion.upper()}:")
            for r in rows:
                if r["source_texts_json"]:
                    try:
                        texts = json.loads(r["source_texts_json"])
                        if texts:
                            print(
                                f"      • \"{texts[0][:80]}{'...' if len(texts[0]) > 80 else ''}\""
                            )
                    except Exception:
                        print(f"      • {r['episode_summary']}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 9. P01 RECALL QUERY EXAMPLES - Practical Use Cases
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("🔍 P01 RECALL QUERY EXAMPLES - Practical Use Cases")
    print("═" * 100)

    # Query 1: "Tell me everything about Emma"
    print("\n   📋 QUERY: 'Tell me everything about Emma'")
    print("   " + "─" * 90)

    # Get relationship
    emma_rel = await conn.fetchrow(
        """
        SELECT relationship_label, relationship_type, interaction_count,
               dominant_emotion, source_texts_json
        FROM st_social WHERE relationship_label ILIKE '%Emma%' LIMIT 1
    """
    )

    if emma_rel:
        print(f"\n   👧 EMMA ({emma_rel['relationship_type']})")
        print(f"      Total Interactions: {emma_rel['interaction_count']}")
        print(f"      Dominant Emotion: {emma_rel['dominant_emotion']}")

    # Get episodes with Emma
    emma_episodes = await conn.fetch(
        """
        SELECT episode_summary, primary_location, source_texts_json
        FROM st_epi
        WHERE participants_json ILIKE '%Emma%'
        LIMIT 5
    """
    )

    print(f"\n      📍 Episodes together ({len(emma_episodes)} found):")
    for ep in emma_episodes:
        print(f"         • {ep['episode_summary']} at {ep['primary_location']}")

    # Query 2: "What happened at work this week?"
    print("\n\n   📋 QUERY: 'What happened at work?'")
    print("   " + "─" * 90)

    work_episodes = await conn.fetch(
        """
        SELECT episode_summary, participants_json, source_texts_json
        FROM st_epi
        WHERE episode_type = 'work'
        LIMIT 5
    """
    )

    print(f"\n   💼 WORK EPISODES ({len(work_episodes)} found):")
    for ep in work_episodes:
        if ep["source_texts_json"]:
            try:
                texts = json.loads(ep["source_texts_json"])
                if texts:
                    print(f"      • \"{texts[0][:80]}{'...' if len(texts[0]) > 80 else ''}\"")
            except Exception:
                print(f"      • {ep['episode_summary']}")

    # Query 3: "When was I happiest?"
    print("\n\n   📋 QUERY: 'When was I happiest?'")
    print("   " + "─" * 90)

    happiest = await conn.fetch(
        """
        SELECT e.episode_summary, e.source_texts_json, o.sentiment_score,
               o.dominant_emotion, o.circadian_slot
        FROM st_epi e
        JOIN st_observations o ON o.layer = 'st_epi' AND o.record_id = e.episode_id
        WHERE o.sentiment_score IS NOT NULL
        ORDER BY o.sentiment_score DESC
        LIMIT 5
    """
    )

    print("\n   🌟 YOUR HAPPIEST MOMENTS:")
    for i, h in enumerate(happiest, 1):
        sent = h["sentiment_score"] if h["sentiment_score"] else 0
        if h["source_texts_json"]:
            try:
                texts = json.loads(h["source_texts_json"])
                if texts:
                    print(f"      {i}. (Sentiment: {sent:.2f}, Emotion: {h['dominant_emotion']})")
                    print(f"         \"{texts[0][:80]}{'...' if len(texts[0]) > 80 else ''}\"")
            except Exception:
                print(f"      {i}. {h['episode_summary']} (Sentiment: {sent:.2f})")

    # Query 4: "What are my pending decisions?"
    print("\n\n   📋 QUERY: 'What decisions do I need to make?'")
    print("   " + "─" * 90)

    decisions = await conn.fetch(
        """
        SELECT intention_description, source_texts_json
        FROM st_prospective
        WHERE intention_type = 'DECISION' AND status = 'ACTIVE'
        LIMIT 5
    """
    )

    print("\n   🤔 PENDING DECISIONS:")
    for d in decisions:
        print(f"      • {d['intention_description']}")

    # Query 5: "Who are my colleagues?"
    print("\n\n   📋 QUERY: 'Who are my colleagues?'")
    print("   " + "─" * 90)

    colleagues = await conn.fetch(
        """
        SELECT relationship_label, interaction_count, source_texts_json
        FROM st_social
        WHERE relationship_type = 'COLLEAGUE'
        ORDER BY interaction_count DESC
        LIMIT 5
    """
    )

    print("\n   👔 YOUR COLLEAGUES:")
    for c in colleagues:
        print(f"      • {c['relationship_label']} ({c['interaction_count']} interactions)")
        if c["source_texts_json"]:
            try:
                texts = json.loads(c["source_texts_json"])
                if texts:
                    print(f'        Last context: "{texts[0][:60]}..."')
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════════════════════
    # 10. LIFE BALANCE ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("⚖️ LIFE BALANCE ANALYSIS - Where Is Your Attention?")
    print("═" * 100)

    # Analyze episodes by type
    episode_types = await conn.fetch(
        """
        SELECT episode_type, COUNT(*) as count
        FROM st_epi
        GROUP BY episode_type
        ORDER BY count DESC
    """
    )

    # Analyze relationships by type
    relationship_types = await conn.fetch(
        """
        SELECT relationship_type, COUNT(*) as count, SUM(interaction_count) as total_interactions
        FROM st_social
        GROUP BY relationship_type
        ORDER BY total_interactions DESC
    """
    )

    # Map to life categories
    life_categories = {
        "FAMILY": {"episodes": 0, "relationships": 0, "interactions": 0},
        "WORK": {"episodes": 0, "relationships": 0, "interactions": 0},
        "SOCIAL": {"episodes": 0, "relationships": 0, "interactions": 0},
        "HEALTH": {"episodes": 0, "relationships": 0, "interactions": 0},
        "LEARNING": {"episodes": 0, "relationships": 0, "interactions": 0},
        "OTHER": {"episodes": 0, "relationships": 0, "interactions": 0},
    }

    # Map episode types
    for r in episode_types:
        ep_type = r["episode_type"].upper() if r["episode_type"] else "OTHER"
        if ep_type in life_categories:
            life_categories[ep_type]["episodes"] = r["count"]
        elif ep_type == "SOCIAL":
            life_categories["SOCIAL"]["episodes"] += r["count"]
        else:
            life_categories["OTHER"]["episodes"] += r["count"]

    # Map relationship types
    for r in relationship_types:
        rel_type = r["relationship_type"].upper() if r["relationship_type"] else "OTHER"
        if rel_type == "FAMILY":
            life_categories["FAMILY"]["relationships"] = r["count"]
            life_categories["FAMILY"]["interactions"] = r["total_interactions"]
        elif rel_type == "COLLEAGUE":
            life_categories["WORK"]["relationships"] = r["count"]
            life_categories["WORK"]["interactions"] = r["total_interactions"]
        elif rel_type == "FRIEND":
            life_categories["SOCIAL"]["relationships"] = r["count"]
            life_categories["SOCIAL"]["interactions"] = r["total_interactions"]

    # Count health/learning from semantic patterns
    health_patterns = await conn.fetchval(
        """
        SELECT COUNT(*) FROM st_sem
        WHERE pattern_subtype ILIKE '%health%' OR pattern_name ILIKE '%workout%'
              OR pattern_name ILIKE '%exercise%' OR pattern_name ILIKE '%doctor%'
    """
    )

    learning_patterns = await conn.fetchval(
        """
        SELECT COUNT(*) FROM st_sem
        WHERE pattern_type = 'LESSON' OR pattern_subtype ILIKE '%learning%'
              OR pattern_name ILIKE '%learned%' OR pattern_name ILIKE '%book%'
    """
    )

    life_categories["HEALTH"]["episodes"] = health_patterns or 0
    life_categories["LEARNING"]["episodes"] = learning_patterns or 0

    # Calculate totals
    total_episodes = sum(c["episodes"] for c in life_categories.values())
    total_interactions = sum(c["interactions"] for c in life_categories.values())

    print(
        """
   📊 LIFE AREA DISTRIBUTION:
   """
    )

    for category, data in sorted(
        life_categories.items(), key=lambda x: -x[1]["interactions"] - x[1]["episodes"]
    ):
        if data["episodes"] > 0 or data["interactions"] > 0:
            emoji = {
                "FAMILY": "👨‍👩‍👧",
                "WORK": "💼",
                "SOCIAL": "🎉",
                "HEALTH": "🏃",
                "LEARNING": "📚",
                "OTHER": "📌",
            }.get(category, "📌")

            bar_len = max(1, (data["episodes"] + data["interactions"] // 3) * 2)
            bar = "█" * min(bar_len, 30)

            print(f"   {emoji} {category}:")
            print(
                f"      Episodes: {data['episodes']} | Relationships: {data['relationships']} | Interactions: {data['interactions']}"
            )
            print(f"      {bar}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 11. DEEP PERSONALIZED INSIGHTS - Data-Driven Analysis
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("🔬 DEEP PERSONALIZED INSIGHTS - What Your Memories Reveal")
    print("═" * 100)

    # --- HEALTH PATTERNS ---
    print("\n   🏥 HEALTH PATTERN ANALYSIS:")
    print("   " + "─" * 90)

    gerd_mentions = await conn.fetch(
        """
        SELECT source_texts_json, dominant_emotion
        FROM st_observations o
        JOIN st_sem s ON o.record_id::text = s.pattern_id::text AND o.layer = 'st_sem'
        WHERE s.pattern_name ILIKE '%GERD%' OR s.pattern_description ILIKE '%GERD%'
        LIMIT 10
    """
    )

    # Also check episodes for GERD
    gerd_episodes = await conn.fetch(
        """
        SELECT episode_summary, source_texts_json
        FROM st_epi
        WHERE episode_summary ILIKE '%GERD%' OR episode_summary ILIKE '%stomach%'
              OR episode_summary ILIKE '%acid%' OR episode_summary ILIKE '%digestion%'
        LIMIT 5
    """
    )

    # Check raw events for GERD patterns
    gerd_events = await conn.fetch(
        """
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%GERD%' OR text ILIKE '%stomach%'
              OR text ILIKE '%spicy%' OR text ILIKE '%acid%'
        ORDER BY created_at DESC
        LIMIT 8
    """
    )

    if gerd_events:
        print(f"\n   📊 GERD/Digestive Health: {len(gerd_events)} mentions detected")
        print("\n   🔍 GERD Triggers Identified:")
        triggers = []
        remedies = []
        for g in gerd_events:
            text = g["text"].lower()
            if "spicy" in text:
                triggers.append("Spicy food")
            if "coffee" in text:
                triggers.append("Coffee")
            if "stress" in text:
                triggers.append("Stress")
            if "squat" in text or "gym" in text:
                triggers.append("Heavy exercise (squats)")
            if "late" in text and ("eat" in text or "night" in text):
                triggers.append("Late night eating")
            if "avoid" in text or "skip" in text:
                remedies.append("Avoiding triggers")
            if "small" in text and "meal" in text:
                remedies.append("Smaller meals")

        triggers = list(set(triggers))[:4]
        remedies = list(set(remedies))[:3]

        if triggers:
            for t in triggers:
                print(f"      ⚠️ {t}")
        else:
            print("      • Monitoring pattern, no clear triggers identified yet")

        if remedies:
            print("\n   ✅ What's Working:")
            for r in remedies:
                print(f"      • {r}")
    else:
        print("   No digestive health mentions found")

    # --- SLEEP PATTERNS ---
    print("\n\n   😴 SLEEP & ENERGY PATTERNS:")
    print("   " + "─" * 90)

    sleep_events = await conn.fetch(
        """
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%sleep%' OR text ILIKE '%tired%'
              OR text ILIKE '%energy%' OR text ILIKE '%rest%'
        ORDER BY created_at DESC
        LIMIT 8
    """
    )

    if sleep_events:
        good_sleep = sum(
            1
            for s in sleep_events
            if "good" in s["text"].lower()
            or "7" in s["text"]
            or "productivity" in s["text"].lower()
        )
        bad_sleep = sum(
            1
            for s in sleep_events
            if "tired" in s["text"].lower() or "exhausted" in s["text"].lower()
        )

        print(f"\n   📊 Sleep Quality: {good_sleep} positive, {bad_sleep} negative mentions")

        # Find sleep insights
        for s in sleep_events[:3]:
            text = s["text"]
            if "when i sleep" in text.lower() or "because" in text.lower():
                print(
                    f'\n   💡 Insight: "{text[:100]}..."'
                    if len(text) > 100
                    else f'\n   💡 Insight: "{text}"'
                )
                break
    else:
        print("   No sleep pattern data found")

    # --- WORK/FAMILYOS PROJECT INSIGHTS ---
    print("\n\n   💻 PROJECT PROGRESS (FamilyOS/K0/K1):")
    print("   " + "─" * 90)

    project_events = await conn.fetch(
        """
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%K0%' OR text ILIKE '%K1%'
              OR text ILIKE '%FamilyOS%' OR text ILIKE '%pipeline%'
              OR text ILIKE '%P02%' OR text ILIKE '%P03%'
        ORDER BY created_at DESC
        LIMIT 15
    """
    )

    if project_events:
        wins = []
        blockers = []
        for p in project_events:
            text = p["text"].lower()
            if any(
                word in text
                for word in ["fixed", "stable", "faster", "working", "smooth", "success"]
            ):
                wins.append(p["text"][:80])
            if any(word in text for word in ["slow", "bug", "issue", "leak", "problem", "fail"]):
                blockers.append(p["text"][:80])

        wins = list(set(wins))[:3]
        blockers = list(set(blockers))[:3]

        print(f"\n   📊 Project Mentions: {len(project_events)}")

        if wins:
            print("\n   🎉 RECENT WINS:")
            for w in wins:
                print(f"      ✓ {w}...")

        if blockers:
            print("\n   ⚠️ CURRENT BLOCKERS:")
            for b in blockers:
                print(f"      • {b}...")
    else:
        print("   No project data found")

    # --- RELATIONSHIP QUALITY ANALYSIS ---
    print("\n\n   💕 RELATIONSHIP QUALITY ANALYSIS:")
    print("   " + "─" * 90)

    # Get Panda relationship details
    panda_events = await conn.fetch(
        """
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%Panda%'
        ORDER BY created_at DESC
        LIMIT 10
    """
    )

    if panda_events:
        positive_panda = sum(
            1
            for p in panda_events
            if any(
                word in p["text"].lower()
                for word in ["love", "happy", "great", "amazing", "support", "best"]
            )
        )

        print(f"\n   👫 Panda (Partner): {len(panda_events)} mentions, {positive_panda} positive")

        # Show recent Panda memories
        print("   📝 Recent moments together:")
        for p in panda_events[:3]:
            print(
                f"      • \"{p['text'][:70]}...\""
                if len(p["text"]) > 70
                else f"      • \"{p['text']}\""
            )

    # Family analysis
    family_events = await conn.fetch(
        """
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%Mom%' OR text ILIKE '%Dad%'
              OR text ILIKE '%Maya%' OR text ILIKE '%parents%'
        ORDER BY created_at DESC
        LIMIT 10
    """
    )

    if family_events:
        print(f"\n   👨‍👩‍👧 Family: {len(family_events)} mentions")
        print("   📝 Family highlights:")
        shown = set()
        for f in family_events[:4]:
            text = f["text"][:70]
            if text not in shown:
                shown.add(text)
                print(f'      • "{text}..."' if len(f["text"]) > 70 else f"      • \"{f['text']}\"")

    # --- RECURRING CONCERNS (Unresolved Items) ---
    print("\n\n   🔄 RECURRING THEMES (Items on Your Mind):")
    print("   " + "─" * 90)

    # Find frequently mentioned topics
    recurring = await conn.fetch(
        """
        SELECT intention_description, COUNT(*) as mentions
        FROM st_prospective
        WHERE intention_type = 'DECISION' AND status = 'ACTIVE'
        GROUP BY intention_description
        HAVING COUNT(*) > 1
        ORDER BY mentions DESC
        LIMIT 5
    """
    )

    if recurring:
        print("\n   🤔 Decisions that keep coming up:")
        for r in recurring:
            print(f"      • {r['intention_description'][:60]}... (mentioned {r['mentions']}x)")

    # ═══════════════════════════════════════════════════════════════════════════
    # Use CANONICAL ISSUES instead of raw topic frequency (Bug 4 fix)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n   📋 CANONICAL ISSUES (from st_issues):")
    print("   " + "─" * 90)

    # Check if st_issues exists and has data
    try:
        issues = await conn.fetch("""
            SELECT 
                canonical_title, 
                issue_category, 
                status, 
                evidence_count,
                resolution_note
            FROM st_issues
            ORDER BY 
                CASE status 
                    WHEN 'OPEN' THEN 1 
                    WHEN 'RECURRING' THEN 2 
                    WHEN 'RESOLVED' THEN 3 
                END,
                evidence_count DESC
        """)

        if issues:
            for issue in issues:
                status_icon = '✅' if issue['status'] == 'RESOLVED' else '🔄' if issue['status'] == 'RECURRING' else '🔴'
                cat_emoji = {
                    'TECH': '💻', 'HEALTH': '🏥', 'ADMIN': '📋', 
                    'FAMILY': '👨‍👩‍👧', 'WORK': '💼', 'FINANCE': '💰'
                }.get(issue['issue_category'], '📌')
                
                print(f"\n   {status_icon} {cat_emoji} {issue['canonical_title']}")
                print(f"      Status: {issue['status']} | Evidence: {issue['evidence_count']} events")
                if issue['resolution_note']:
                    print(f"      ✨ Resolution: {issue['resolution_note'][:70]}...")
        else:
            print("   No canonical issues found. Run fix_data_quality_bugs.py first.")
    except Exception:
        # Fallback to old topic counting if st_issues doesn't exist
        print("   ⚠️ st_issues table not found - showing raw topic counts")
        
        monitor_mentions = await conn.fetchval("""
            SELECT COUNT(*) FROM st_hipp_events
            WHERE text ILIKE '%monitor%' OR text ILIKE '%flicker%'
        """)
        
        print(f"      🔴 Monitor/Display issues: {monitor_mentions} mentions")

    # --- PRODUCTIVITY PATTERNS ---
    print("\n\n   ⚡ PRODUCTIVITY INSIGHTS:")
    print("   " + "─" * 90)

    morning_work = await conn.fetch(
        """
        SELECT o.sentiment_score, e.episode_summary
        FROM st_observations o
        JOIN st_epi e ON o.record_id::text = e.episode_id::text AND o.layer = 'st_epi'
        WHERE o.circadian_slot = 'breakfast_window' AND e.episode_type = 'work'
        LIMIT 5
    """
    )

    night_work = await conn.fetch(
        """
        SELECT o.sentiment_score, e.episode_summary
        FROM st_observations o
        JOIN st_epi e ON o.record_id::text = e.episode_id::text AND o.layer = 'st_epi'
        WHERE o.circadian_slot = 'sleep_window' AND e.episode_type = 'work'
        LIMIT 5
    """
    )

    morning_avg = (
        sum(m["sentiment_score"] or 0 for m in morning_work) / len(morning_work)
        if morning_work
        else 0
    )
    night_avg = (
        sum(n["sentiment_score"] or 0 for n in night_work) / len(night_work) if night_work else 0
    )

    if morning_work or night_work:
        print("\n   📊 Work Session Quality:")
        print(
            f"      • Morning work: {len(morning_work)} sessions, avg sentiment {morning_avg:.2f}"
        )
        print(f"      • Late night work: {len(night_work)} sessions, avg sentiment {night_avg:.2f}")

        if morning_avg > night_avg and morning_work:
            print(
                "\n   💡 Insight: Your morning work sessions have higher sentiment - consider frontloading deep work"
            )
        elif night_avg > morning_avg and night_work:
            print(
                "\n   💡 Insight: You seem more satisfied with late-night work - you may be a night owl"
            )

    # --- ACTIONABLE RECOMMENDATIONS ---
    print("\n\n" + "═" * 100)
    print("🎯 PERSONALIZED RECOMMENDATIONS (Based on Your Data)")
    print("═" * 100)

    recommendations = []

    # Get recommendations from canonical issues table
    try:
        open_issues = await conn.fetch("""
            SELECT canonical_title, issue_category, evidence_count, status
            FROM st_issues
            WHERE status IN ('OPEN', 'RECURRING')
            ORDER BY evidence_count DESC
        """)
        
        for issue in open_issues:
            cat_map = {
                'HEALTH': '🏥 HEALTH',
                'TECH': '💻 TECH',
                'ADMIN': '📋 ADMIN',
                'FAMILY': '💒 FAMILY',
                'WORK': '💼 WORK',
                'FINANCE': '💰 FINANCE'
            }
            action_map = {
                'GERD/Digestive Issues': 'Track meals before gym sessions - heavy squats seem to trigger symptoms',
                'H1B Visa/Immigration Paperwork': 'Set a specific date to complete paperwork - unresolved admin creates background stress',
                'Wedding Planning': 'Consider delegating - Mom and Panda\'s Mom both want to help',
                'Asus ProArt Overheating/Fan Noise': 'Cooling pad should arrive soon - monitor temps after',
            }
            recommendations.append({
                "category": cat_map.get(issue['issue_category'], '📌 OTHER'),
                "issue": f"{issue['canonical_title']} ({issue['evidence_count']} evidence events)",
                "action": action_map.get(issue['canonical_title'], 'Review and address this recurring issue'),
                "evidence": f"Status: {issue['status']} - tracked in st_issues"
            })
    except Exception:
        # Fallback to GERD if st_issues doesn't exist
        if gerd_events and len(gerd_events) > 3:
            recommendations.append({
                "category": "🏥 HEALTH",
                "issue": f"GERD mentioned {len(gerd_events)} times in 10 days",
                "action": "Track meals before gym sessions - heavy squats seem to trigger symptoms",
                "evidence": "Pattern: GERD flares after spicy food and heavy exercise",
            })

    # Sleep/productivity
    if morning_avg > night_avg + 0.1:
        recommendations.append(
            {
                "category": "⚡ PRODUCTIVITY",
                "issue": "Late night coding sessions have lower satisfaction",
                "action": "Shift FamilyOS work to mornings when energy is higher",
                "evidence": f"Morning sentiment: {morning_avg:.2f} vs Night: {night_avg:.2f}",
            }
        )

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            print(f"\n   {i}. {rec['category']}")
            print(f"      📍 Issue: {rec['issue']}")
            print(f"      ✨ Action: {rec['action']}")
            print(f"      📊 Evidence: {rec['evidence']}")
    else:
        print("\n   ✨ No urgent recommendations - you're on track!")

    # Final summary
    print("\n\n   " + "─" * 90)
    print("   📈 10-DAY SUMMARY:")
    total_events = await conn.fetchval("SELECT COUNT(*) FROM st_hipp_events")
    total_decisions = await conn.fetchval(
        "SELECT COUNT(*) FROM st_prospective WHERE intention_type = 'DECISION'"
    )
    total_reminders = await conn.fetchval(
        "SELECT COUNT(*) FROM st_prospective WHERE intention_type = 'REMINDER'"
    )

    print(f"      • {total_events} life events processed")
    print(f"      • {total_decisions} decisions pending")
    print(f"      • {total_reminders} reminders active")
    print("      • Top focus areas: FamilyOS, Wedding, Family, Health")
    print("   " + "─" * 90)

    await conn.close()


if __name__ == "__main__":
    asyncio.run(explore_all_layers())
