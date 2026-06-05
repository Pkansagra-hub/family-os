"""
Explore all memory layers and their relationship with st_observations
to understand how we can build a holistic view of a person's life.

This script shows REAL EXAMPLES from the memories that were formed.
"""

import asyncio
import builtins
import json

import asyncpg


_OUTPUT_MIRROR = None


def ascii_print(*args, **kwargs):
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    file = kwargs.get("file", None)
    flush = kwargs.get("flush", False)

    if args:
        text = sep.join(str(a) for a in args)
        replacements = {
            "═": "=",
            "─": "-",
            "━": "-",
            "┌": "+",
            "┐": "+",
            "└": "+",
            "┘": "+",
            "┬": "+",
            "┴": "+",
            "┼": "+",
            "│": "|",
            "→": "->",
            "←": "<-",
            "↔": "<->",
            "⇒": "=>",
            "⋯": "...",
            "•": "*",
            "✓": "[OK]",
            "✅": "[OK]",
            "⚠️": "[WARN]",
            "❌": "[X]",
            "🔴": "[RED]",
            "🟢": "[GREEN]",
            "🟡": "[YELLOW]",
            "⚪": "[WHITE]",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = text.encode("ascii", errors="ignore").decode("ascii")
        builtins.print(text, sep=sep, end=end, file=file, flush=flush)
        if _OUTPUT_MIRROR is not None and file is None:
            builtins.print(text, sep=sep, end=end, file=_OUTPUT_MIRROR, flush=flush)
    else:
        builtins.print("", sep=sep, end=end, file=file, flush=flush)
        if _OUTPUT_MIRROR is not None and file is None:
            builtins.print("", sep=sep, end=end, file=_OUTPUT_MIRROR, flush=flush)


print = ascii_print


async def explore_all_layers():
    global _OUTPUT_MIRROR

    conn = await asyncpg.connect("postgresql://k0user:changeme@localhost:5432/k0_kernel")
    output_path = "explore_memory_layers_output.md"
    _OUTPUT_MIRROR = open(output_path, "w", encoding="utf-8")

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

    rows = await conn.fetch("""
        SELECT pattern_id, pattern_name, pattern_description, pattern_type,
               pattern_subtype, source_texts_json, confidence_score
        FROM st_sem
        ORDER BY created_at DESC
        LIMIT 5
    """)

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
            except Exception:
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
    type_counts = await conn.fetch("""
        SELECT entity_type, COUNT(*) as cnt,
               array_agg(canonical_name ORDER BY observation_count DESC) as examples
        FROM st_kg_dom
        GROUP BY entity_type
        ORDER BY cnt DESC
    """)

    for r in type_counts:
        examples = r["examples"][:5] if r["examples"] else []
        examples_str = ", ".join(examples)
        print(f"      {r['entity_type']}: {r['cnt']} entities")
        print(f"         Examples: {examples_str}")

    print("\n   🔍 REAL ENTITIES FROM YOUR LIFE:")
    print("   " + "─" * 90)

    rows = await conn.fetch("""
        SELECT canonical_name, entity_type, source_texts_json, attributes_json
        FROM st_kg_dom
        WHERE entity_type = 'PERSON'
        ORDER BY observation_count DESC
        LIMIT 5
    """)

    for i, r in enumerate(rows, 1):
        print(f"\n   👤 Person {i}: {r['canonical_name']}")
        if r["source_texts_json"]:
            try:
                texts = json.loads(r["source_texts_json"])
                if texts:
                    print("      📝 Mentioned in:")
                    for text in texts[:2]:
                        print(f"         \"{text[:100]}{'...' if len(text) > 100 else ''}\"")
            except Exception:
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

    print("\n   🔍 YOUR KEY RELATIONSHIPS (with computed sentiment from observations):")
    print("   " + "─" * 90)

    # FIX A: Compute sentiment from observations of episodes involving each person
    rows = await conn.fetch("""
        WITH person_sentiment AS (
            SELECT
                s.relationship_id,
                s.relationship_label,
                -- Get sentiment from episodes where this person is a participant
                COALESCE(
                    (SELECT AVG(o.sentiment_score)
                     FROM st_epi e
                     JOIN st_observations o ON o.layer = 'st_epi' AND o.record_id = e.episode_id
                     WHERE e.participants_json ILIKE '%' || s.relationship_label || '%'
                       AND o.sentiment_score IS NOT NULL),
                    0
                ) as computed_sentiment,
                -- Get dominant emotion from episodes
                (SELECT o.dominant_emotion
                 FROM st_epi e
                 JOIN st_observations o ON o.layer = 'st_epi' AND o.record_id = e.episode_id
                 WHERE e.participants_json ILIKE '%' || s.relationship_label || '%'
                   AND o.dominant_emotion IS NOT NULL
                 GROUP BY o.dominant_emotion
                 ORDER BY COUNT(*) DESC
                 LIMIT 1) as computed_emotion
            FROM st_social s
        )
        SELECT
            s.relationship_label,
            s.relationship_type,
            s.interaction_count,
            s.source_texts_json,
            COALESCE(ps.computed_sentiment, s.avg_sentiment, 0) as computed_sentiment,
            COALESCE(ps.computed_emotion, s.dominant_emotion, 'neutral') as computed_emotion
        FROM st_social s
        LEFT JOIN person_sentiment ps ON ps.relationship_id = s.relationship_id
        ORDER BY s.interaction_count DESC
        LIMIT 6
    """)

    for i, r in enumerate(rows, 1):
        sent = r["computed_sentiment"] if r["computed_sentiment"] else 0
        emotion = r["computed_emotion"] if r["computed_emotion"] else "neutral"
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
            except Exception:
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

    rows = await conn.fetch("""
        SELECT intention_description, intention_type, status,
               source_texts_json, confidence_score
        FROM st_prospective
        ORDER BY created_at DESC
        LIMIT 6
    """)

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
            except Exception:
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
    layer_counts = await conn.fetch("""
        SELECT layer, COUNT(*) as cnt,
               AVG(sentiment_score) as avg_sent
        FROM st_observations
        GROUP BY layer
        ORDER BY cnt DESC
    """)

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

    rows = await conn.fetch("""
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
    """)

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
            except Exception:
                pass

    # Query 2: Relationships with emotional context
    print("\n\n   📊 QUERY 2: Relationships - Who Brings Joy?")
    print("   " + "─" * 90)

    rows = await conn.fetch("""
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
    """)

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
            except Exception:
                pass

    # Query 3: Emotional patterns by time of day
    print("\n\n   📊 QUERY 3: When Are You Happiest? (Time-of-Day Analysis)")
    print("   " + "─" * 90)

    rows = await conn.fetch("""
        SELECT
            circadian_slot,
            AVG(sentiment_score) as avg_sentiment,
            COUNT(*) as memory_count,
            array_agg(DISTINCT dominant_emotion) FILTER (WHERE dominant_emotion IS NOT NULL) as emotions
        FROM st_observations
        WHERE circadian_slot IS NOT NULL AND circadian_slot != ''
        GROUP BY circadian_slot
        ORDER BY avg_sentiment DESC
    """)

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
    people = await conn.fetch("""
        SELECT relationship_label, relationship_type, interaction_count
        FROM st_social
        ORDER BY interaction_count DESC
        LIMIT 5
    """)

    # Get key places
    places = await conn.fetch("""
        SELECT canonical_name, observation_count
        FROM st_kg_dom
        WHERE entity_type = 'LOCATION'
        ORDER BY observation_count DESC
        LIMIT 5
    """)

    # Get emotional summary
    emotions = await conn.fetch("""
        SELECT dominant_emotion, COUNT(*) as cnt
        FROM st_observations
        WHERE dominant_emotion IS NOT NULL AND dominant_emotion != ''
        GROUP BY dominant_emotion
        ORDER BY cnt DESC
        LIMIT 5
    """)

    # Get pending reminders
    reminders = await conn.fetch("""
        SELECT intention_description, intention_type
        FROM st_prospective
        WHERE status = 'ACTIVE'
        LIMIT 3
    """)

    print("""
   Based on your memories, here's what the system knows about your life:
    """)

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

    print("""
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
    """)

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. KNOWLEDGE GRAPH EDGES (st_kg_edges) - GAP-007 Edge Enrichment Algorithms
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("7. KNOWLEDGE GRAPH EDGES (st_kg_edges) - GAP-007 EDGE ENRICHMENT")
    print("   Purpose: Relationships between entities discovered by 6 AI algorithms")
    print("═" * 100)

    total_edges = await conn.fetchval("SELECT COUNT(*) FROM st_kg_edges")
    print(f"\n   📊 Total KG Edges: {total_edges}")

    # Show algorithm distribution
    print("\n   🔬 EDGES BY ENRICHMENT ALGORITHM:")
    print("   " + "─" * 90)

    algo_stats = await conn.fetch("""
        SELECT
            source_algorithm,
            COUNT(*) as edge_count,
            ROUND(AVG(edge_weight)::numeric, 3) as avg_weight,
            ROUND(MIN(edge_weight)::numeric, 3) as min_weight,
            ROUND(MAX(edge_weight)::numeric, 3) as max_weight,
            COUNT(DISTINCT relation_type) as relation_types
        FROM st_kg_edges
        GROUP BY source_algorithm
        ORDER BY edge_count DESC
    """)

    algo_descriptions = {
        "semantic_similarity": "🧠 Entities with similar meaning/context (cosine similarity of embeddings)",
        "contextual": "🔗 Entities that appear in similar contexts or share attributes",
        "co_occurrence": "👥 Entities frequently mentioned together in the same events",
        "temporal_proximity": "⏰ Entities that occur close together in time",
        "bayesian_causal": "📈 Entities where one likely causes/influences another",
        "transitive_closure": "🔄 Inferred relationships through intermediate entities",
    }

    for r in algo_stats:
        algo = r["source_algorithm"] or "unknown"
        desc = algo_descriptions.get(algo, "Unknown algorithm")
        print(f"\n   {desc}")
        print(f"      Algorithm: {algo}")
        print(f"      Edges: {r['edge_count']} | Relations: {r['relation_types']}")
        print(f"      Weight Range: {r['min_weight']} - {r['max_weight']} (avg: {r['avg_weight']})")

    # ═══════════════════════════════════════════════════════════════════════════
    # 7.1 SEMANTIC SIMILARITY EDGES
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n   " + "━" * 94)
    print("   🧠 7.1 SEMANTIC SIMILARITY - 'These concepts mean similar things'")
    print("   " + "━" * 94)

    # FIX D: Add same-type gate for semantic similarity to avoid nonsense edges
    # Only show edges where entities share the same type OR have co-occurrence evidence
    sem_edges = await conn.fetch("""
        WITH cooccurrence_pairs AS (
            -- Get pairs that have co-occurrence evidence
            SELECT source_entity_id, target_entity_id
            FROM st_kg_edges
            WHERE source_algorithm = 'co_occurrence'
        )
        SELECT
            s.canonical_name as source_name,
            s.entity_type as source_type,
            t.canonical_name as target_name,
            t.entity_type as target_type,
            e.edge_weight,
            e.confidence_score,
            e.properties_json,
            CASE
                WHEN s.entity_type = t.entity_type THEN true
                WHEN EXISTS (SELECT 1 FROM cooccurrence_pairs c
                             WHERE (c.source_entity_id = e.source_entity_id AND c.target_entity_id = e.target_entity_id)
                                OR (c.source_entity_id = e.target_entity_id AND c.target_entity_id = e.source_entity_id))
                THEN true
                ELSE false
            END as is_valid_pair
        FROM st_kg_edges e
        JOIN st_kg_dom s ON e.source_entity_id = s.entity_id
        JOIN st_kg_dom t ON e.target_entity_id = t.entity_id
        WHERE e.source_algorithm = 'semantic_similarity'
        ORDER BY e.edge_weight DESC
        LIMIT 20
    """)

    if sem_edges:
        print("\n   💡 How it works: Compares vector embeddings of entity descriptions")
        print("      using cosine similarity. High score = semantically related concepts.")
        print(
            "\n   ⚠️ QUALITY GATE: Only showing edges where entities share type OR have co-occurrence evidence."
        )
        print("      (Cross-type edges like 'Brooklyn ↔ James Clear' are filtered out as noise)\n")

        # Filter to only valid pairs (same type or co-occurrence)
        valid_edges = [e for e in sem_edges if e["is_valid_pair"]]
        noise_edges = [e for e in sem_edges if not e["is_valid_pair"]]

        for i, e in enumerate(valid_edges[:5], 1):
            weight = e["edge_weight"] or 0
            sim_score = None
            if e["properties_json"]:
                try:
                    props = json.loads(e["properties_json"])
                    sim_score = props.get("similarity_score")
                except Exception:
                    pass

            print(
                f"   {i}. {e['source_name']} ({e['source_type']}) ←→ {e['target_name']} ({e['target_type']})"
            )
            if sim_score:
                print(f"      Similarity: {sim_score:.2%} | Weight: {weight:.3f}")
            else:
                print(f"      Weight: {weight:.3f} | Confidence: {e['confidence_score']:.3f}")

        # Show noise stats
        if noise_edges:
            print(
                f"\n   🔇 Filtered as noise: {len(noise_edges)} cross-type edges without co-occurrence evidence"
            )
            print("      Examples of filtered noise:")
            for e in noise_edges[:2]:
                print(
                    f"         ❌ {e['source_name']} ({e['source_type']}) ↔ {e['target_name']} ({e['target_type']})"
                )
    else:
        print("\n   ⚠️ No semantic similarity edges found")

    # ═══════════════════════════════════════════════════════════════════════════
    # 7.2 CONTEXTUAL EDGES
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n   " + "━" * 94)
    print("   🔗 7.2 CONTEXTUAL RELATIONSHIPS - 'These appear in similar contexts'")
    print("   " + "━" * 94)

    ctx_edges = await conn.fetch("""
        SELECT
            s.canonical_name as source_name,
            t.canonical_name as target_name,
            e.relation_type,
            e.edge_weight,
            e.properties_json
        FROM st_kg_edges e
        JOIN st_kg_dom s ON e.source_entity_id = s.entity_id
        JOIN st_kg_dom t ON e.target_entity_id = t.entity_id
        WHERE e.source_algorithm = 'contextual'
        ORDER BY e.edge_weight DESC
        LIMIT 8
    """)

    if ctx_edges:
        print("\n   💡 How it works: Identifies entities that share contextual attributes,")
        print("      episode types, locations, or appear in similar emotional contexts.\n")

        # Group by relation type
        by_type = {}
        for e in ctx_edges:
            rt = e["relation_type"] or "RELATED"
            if rt not in by_type:
                by_type[rt] = []
            by_type[rt].append(e)

        for rel_type, edges in list(by_type.items())[:4]:
            print(f"   📌 {rel_type}:")
            for e in edges[:2]:
                print(
                    f"      • {e['source_name']} → {e['target_name']} (weight: {e['edge_weight']:.2f})"
                )
    else:
        print("\n   ⚠️ No contextual edges found")

    # ═══════════════════════════════════════════════════════════════════════════
    # 7.3 CO-OCCURRENCE EDGES
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n   " + "━" * 94)
    print("   👥 7.3 CO-OCCURRENCE - 'These are mentioned together frequently'")
    print("   " + "━" * 94)

    cooc_edges = await conn.fetch("""
        SELECT
            s.canonical_name as source_name,
            t.canonical_name as target_name,
            e.relation_type,
            e.edge_weight,
            e.observation_count,
            e.properties_json
        FROM st_kg_edges e
        JOIN st_kg_dom s ON e.source_entity_id = s.entity_id
        JOIN st_kg_dom t ON e.target_entity_id = t.entity_id
        WHERE e.source_algorithm = 'co_occurrence'
        ORDER BY e.edge_weight DESC
        LIMIT 8
    """)

    if cooc_edges:
        print("\n   💡 How it works: Counts how often two entities appear in the same")
        print("      events or episodes. More co-occurrences = stronger relationship.\n")

        for i, e in enumerate(cooc_edges[:5], 1):
            obs = e["observation_count"] or 1
            print(f"   {i}. {e['source_name']} + {e['target_name']}")
            print(
                f"      Co-occurrences: {obs} | Weight: {e['edge_weight']:.2f} | Type: {e['relation_type']}"
            )
    else:
        print("\n   ⚠️ No co-occurrence edges found")

    # ═══════════════════════════════════════════════════════════════════════════
    # 7.4 TEMPORAL PROXIMITY EDGES
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n   " + "━" * 94)
    print("   ⏰ 7.4 TEMPORAL PROXIMITY - 'These happen close together in time'")
    print("   " + "━" * 94)

    temp_edges = await conn.fetch("""
        SELECT
            s.canonical_name as source_name,
            t.canonical_name as target_name,
            e.relation_type,
            e.edge_weight,
            e.properties_json
        FROM st_kg_edges e
        JOIN st_kg_dom s ON e.source_entity_id = s.entity_id
        JOIN st_kg_dom t ON e.target_entity_id = t.entity_id
        WHERE e.source_algorithm = 'temporal_proximity'
        ORDER BY e.edge_weight DESC
        LIMIT 8
    """)

    if temp_edges:
        print("\n   💡 How it works: Measures time gap between entity mentions.")
        print("      Closer in time = higher temporal association score.\n")

        for i, e in enumerate(temp_edges[:5], 1):
            rel = e["relation_type"] or "TEMPORALLY_ASSOCIATED"
            time_gap = None
            if e["properties_json"]:
                try:
                    props = json.loads(e["properties_json"])
                    time_gap = props.get("time_gap_hours") or props.get("temporal_distance_ms")
                except Exception:
                    pass

            print(f"   {i}. {e['source_name']} → {e['target_name']} ({rel})")
            if time_gap:
                print(f"      Time Gap: {time_gap} | Weight: {e['edge_weight']:.3f}")
            else:
                print(f"      Weight: {e['edge_weight']:.3f}")
    else:
        print("\n   ⚠️ No temporal proximity edges found")

    # ═══════════════════════════════════════════════════════════════════════════
    # 7.5 BAYESIAN CAUSAL EDGES
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n   " + "━" * 94)
    print("   📈 7.5 BAYESIAN CAUSAL - 'A likely causes or influences B'")
    print("   " + "━" * 94)

    # FIX C: Query causal edges ONLY from bayesian_causal algorithm, deduplicate, group by family
    causal_edges = await conn.fetch("""
        SELECT DISTINCT ON (s.canonical_name, t.canonical_name)
            s.canonical_name as source_name,
            t.canonical_name as target_name,
            e.relation_type,
            e.edge_weight,
            e.confidence_score,
            e.observation_count,
            e.properties_json,
            e.source_algorithm
        FROM st_kg_edges e
        JOIN st_kg_dom s ON e.source_entity_id = s.entity_id
        JOIN st_kg_dom t ON e.target_entity_id = t.entity_id
        WHERE e.source_algorithm = 'bayesian_causal'
        ORDER BY s.canonical_name, t.canonical_name, e.confidence_score DESC
    """)

    if causal_edges:
        print("\n   💡 How it works: Uses Granger causality and Bayesian inference to")
        print("      determine if one entity's occurrence predicts another's.")
        print("\n   📊 CAUSAL RELATIONSHIPS (deduplicated):")

        # Group by relation family
        causal_family = []  # CAUSES, INFLUENCES

        for e in causal_edges:
            rel = e["relation_type"] or "CAUSES"
            conf = e["confidence_score"] or 0
            obs = e["observation_count"] or 1

            # Extract evidence count from properties
            evidence = obs
            if e["properties_json"]:
                try:
                    props = json.loads(e["properties_json"])
                    evidence = props.get("evidence_count", props.get("observation_count", obs))
                except Exception:
                    pass

            causal_family.append(
                {
                    "source": e["source_name"],
                    "target": e["target_name"],
                    "rel": rel,
                    "conf": conf,
                    "weight": e["edge_weight"],
                    "evidence": evidence,
                }
            )

        print(f"\n   🔗 CAUSES/INFLUENCES ({len(causal_family)} edges):")
        for i, edge in enumerate(sorted(causal_family, key=lambda x: -x["conf"])[:5], 1):
            print(f"      {i}. {edge['source']} → {edge['target']}")
            print(
                f"         Confidence: {edge['conf']:.2f} | Evidence: {edge['evidence']} | Weight: {edge['weight']:.3f}"
            )
    else:
        print("\n   ⚠️ No bayesian causal edges found")

    # Separate section for temporal edges (PRECEDES/FOLLOWS)
    temporal_causal = await conn.fetch("""
        SELECT DISTINCT ON (s.canonical_name, t.canonical_name)
            s.canonical_name as source_name,
            t.canonical_name as target_name,
            e.relation_type,
            e.edge_weight,
            e.confidence_score,
            e.observation_count
        FROM st_kg_edges e
        JOIN st_kg_dom s ON e.source_entity_id = s.entity_id
        JOIN st_kg_dom t ON e.target_entity_id = t.entity_id
        WHERE e.relation_type IN ('PRECEDES', 'FOLLOWS')
          AND e.source_algorithm != 'bayesian_causal'
        ORDER BY s.canonical_name, t.canonical_name, e.confidence_score DESC
        LIMIT 5
    """)

    if temporal_causal:
        print("\n   ⏱️ TEMPORAL ORDERING (PRECEDES/FOLLOWS):")
        for i, e in enumerate(temporal_causal[:3], 1):
            arrow = "→→" if e["relation_type"] == "PRECEDES" else "←←"
            print(
                f"      {i}. {e['source_name']} {arrow} {e['target_name']} ({e['relation_type']})"
            )
            print(
                f"         Weight: {e['edge_weight']:.3f} | Evidence: {e['observation_count'] or 1}"
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # 7.6 TRANSITIVE CLOSURE EDGES (if any)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n   " + "━" * 94)
    print("   🔄 7.6 TRANSITIVE CLOSURE - 'Inferred through intermediate entities'")
    print("   " + "━" * 94)

    trans_edges = await conn.fetch("""
        SELECT
            s.canonical_name as source_name,
            t.canonical_name as target_name,
            e.relation_type,
            e.edge_weight,
            e.properties_json
        FROM st_kg_edges e
        JOIN st_kg_dom s ON e.source_entity_id = s.entity_id
        JOIN st_kg_dom t ON e.target_entity_id = t.entity_id
        WHERE e.source_algorithm = 'transitive_closure'
        ORDER BY e.edge_weight DESC
        LIMIT 5
    """)

    if trans_edges:
        print("\n   💡 How it works: If A→B and B→C, then infer A→C with reduced weight.")
        print("      Discovers implicit relationships through graph traversal.\n")

        for i, e in enumerate(trans_edges[:5], 1):
            path = None
            if e["properties_json"]:
                try:
                    props = json.loads(e["properties_json"])
                    path = props.get("inference_path") or props.get("path")
                except Exception:
                    pass

            print(f"   {i}. {e['source_name']} ⋯→ {e['target_name']} ({e['relation_type']})")
            if path:
                print(f"      Path: {' → '.join(path)}")
            print(f"      Weight: {e['edge_weight']:.3f}")
    else:
        print("\n   ⚠️ No transitive closure edges found (requires multiple consolidation cycles)")

    # ═══════════════════════════════════════════════════════════════════════════
    # 7.7 RELATIONSHIP TYPE DISTRIBUTION
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n   " + "━" * 94)
    print("   📊 7.7 RELATIONSHIP TYPE DISTRIBUTION")
    print("   " + "━" * 94)

    rel_types = await conn.fetch("""
        SELECT
            relation_type,
            source_algorithm,
            COUNT(*) as cnt,
            ROUND(AVG(edge_weight)::numeric, 2) as avg_weight
        FROM st_kg_edges
        GROUP BY relation_type, source_algorithm
        ORDER BY cnt DESC
        LIMIT 15
    """)

    print("\n   Relation Type             | Algorithm           | Count | Avg Weight")
    print("   " + "─" * 75)
    for r in rel_types:
        rel = (r["relation_type"] or "UNKNOWN")[:24].ljust(24)
        algo = (r["source_algorithm"] or "unknown")[:18].ljust(18)
        print(f"   {rel} | {algo} | {r['cnt']:5} | {r['avg_weight']:.2f}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 7.8 GRAPH INSIGHTS - Most Connected Entities
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n   " + "━" * 94)
    print("   🌐 7.8 GRAPH INSIGHTS - Hub Entities (Most Connected)")
    print("   " + "━" * 94)

    hubs = await conn.fetch("""
        WITH edge_counts AS (
            SELECT source_entity_id as entity_id, COUNT(*) as out_degree FROM st_kg_edges GROUP BY source_entity_id
            UNION ALL
            SELECT target_entity_id as entity_id, COUNT(*) as in_degree FROM st_kg_edges GROUP BY target_entity_id
        )
        SELECT
            d.canonical_name,
            d.entity_type,
            SUM(ec.out_degree) as total_connections
        FROM edge_counts ec
        JOIN st_kg_dom d ON ec.entity_id = d.entity_id
        GROUP BY d.canonical_name, d.entity_type
        ORDER BY total_connections DESC
        LIMIT 10
    """)

    print(
        "\n   💡 Hub entities are central to your life story - they connect many other entities.\n"
    )

    for i, h in enumerate(hubs[:8], 1):
        type_emoji = {"PERSON": "👤", "LOCATION": "📍", "ORGANIZATION": "🏢"}.get(
            h["entity_type"], "📌"
        )
        bar_len = min(int(h["total_connections"]) // 2, 30)
        bar = "█" * bar_len
        print(f"   {i}. {type_emoji} {h['canonical_name']} ({h['entity_type']})")
        print(f"      Connections: {h['total_connections']} {bar}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 8. RELATIONSHIP DEEP DIVE - Co-occurrence & Emotional Trajectory
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("8. RELATIONSHIP DEEP DIVE - Who Appears Together?")
    print("═" * 100)

    # Co-occurrence analysis from episodes
    print("\n   📊 CO-OCCURRENCE MATRIX (Who appears together in episodes?):")
    print("   " + "─" * 90)

    rows = await conn.fetch("""
        SELECT participants_json, episode_summary, source_texts_json
        FROM st_epi
        WHERE participant_count > 1
        ORDER BY participant_count DESC
        LIMIT 8
    """)

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

    rows = await conn.fetch("""
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
    """)

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
    # 9. EMOTIONAL JOURNEY - Emotional Arc
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("9. EMOTIONAL JOURNEY - Your Emotional Arc")
    print("═" * 100)

    # Get emotions by category from events
    rows = await conn.fetch("""
        SELECT
            dominant_emotion,
            sentiment_score,
            layer,
            COUNT(*) as count
        FROM st_observations
        WHERE dominant_emotion IS NOT NULL AND dominant_emotion != ''
        GROUP BY dominant_emotion, sentiment_score, layer
        ORDER BY count DESC
    """)

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

    print(f"""
   📊 EMOTIONAL DISTRIBUTION:

   Positive Emotions: {pos_count} memories ({pos_count*100//total if total else 0}%)
   {pos_bar}
   (joy, love, excitement, gratitude, pride, contentment)

   Neutral Emotions: {neutral_count} memories ({neutral_count*100//total if total else 0}%)
   {neu_bar}

   Negative Emotions: {neg_count} memories ({neg_count*100//total if total else 0}%)
   {neg_bar}
   (sadness, anxiety, frustration, nervousness)
    """)

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
    # 10. P01 RECALL QUERY EXAMPLES - Practical Use Cases
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("10. P01 RECALL QUERY EXAMPLES - Practical Use Cases")
    print("═" * 100)

    # Query 1: "Tell me everything about Emma"
    print("\n   📋 QUERY: 'Tell me everything about Emma'")
    print("   " + "─" * 90)

    # Get relationship
    emma_rel = await conn.fetchrow("""
        SELECT relationship_label, relationship_type, interaction_count,
               dominant_emotion, source_texts_json
        FROM st_social WHERE relationship_label ILIKE '%Emma%' LIMIT 1
    """)

    if emma_rel:
        print(f"\n   👧 EMMA ({emma_rel['relationship_type']})")
        print(f"      Total Interactions: {emma_rel['interaction_count']}")
        print(f"      Dominant Emotion: {emma_rel['dominant_emotion']}")

    # Get episodes with Emma
    emma_episodes = await conn.fetch("""
        SELECT episode_summary, primary_location, source_texts_json
        FROM st_epi
        WHERE participants_json ILIKE '%Emma%'
        LIMIT 5
    """)

    print(f"\n      📍 Episodes together ({len(emma_episodes)} found):")
    for ep in emma_episodes:
        print(f"         • {ep['episode_summary']} at {ep['primary_location']}")

    # Query 2: "What happened at work this week?"
    print("\n\n   📋 QUERY: 'What happened at work?'")
    print("   " + "─" * 90)

    work_episodes = await conn.fetch("""
        SELECT episode_summary, participants_json, source_texts_json
        FROM st_epi
        WHERE episode_type = 'work'
        LIMIT 5
    """)

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

    happiest = await conn.fetch("""
        SELECT e.episode_summary, e.source_texts_json, o.sentiment_score,
               o.dominant_emotion, o.circadian_slot
        FROM st_epi e
        JOIN st_observations o ON o.layer = 'st_epi' AND o.record_id = e.episode_id
        WHERE o.sentiment_score IS NOT NULL
        ORDER BY o.sentiment_score DESC
        LIMIT 5
    """)

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

    decisions = await conn.fetch("""
        SELECT intention_description, source_texts_json
        FROM st_prospective
        WHERE intention_type = 'DECISION' AND status = 'ACTIVE'
        LIMIT 5
    """)

    print("\n   🤔 PENDING DECISIONS:")
    for d in decisions:
        print(f"      • {d['intention_description']}")

    # Query 5: "Who are my colleagues?"
    print("\n\n   📋 QUERY: 'Who are my colleagues?'")
    print("   " + "─" * 90)

    colleagues = await conn.fetch("""
        SELECT relationship_label, interaction_count, source_texts_json
        FROM st_social
        WHERE relationship_type = 'COLLEAGUE'
        ORDER BY interaction_count DESC
        LIMIT 5
    """)

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
    # 11. LIFE BALANCE ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("11. LIFE BALANCE ANALYSIS - Where Is Your Attention?")
    print("═" * 100)

    # Analyze episodes by type
    episode_types = await conn.fetch("""
        SELECT episode_type, COUNT(*) as count
        FROM st_epi
        GROUP BY episode_type
        ORDER BY count DESC
    """)

    # Analyze relationships by type
    relationship_types = await conn.fetch("""
        SELECT relationship_type, COUNT(*) as count, SUM(interaction_count) as total_interactions
        FROM st_social
        GROUP BY relationship_type
        ORDER BY total_interactions DESC
    """)

    # Map to life categories
    life_categories = {
        "FAMILY": {"episodes": 0, "relationships": 0, "interactions": 0},
        "WORK": {"episodes": 0, "relationships": 0, "interactions": 0},
        "SOCIAL": {"episodes": 0, "relationships": 0, "interactions": 0},
        "HEALTH": {"episodes": 0, "relationships": 0, "interactions": 0},
        "LEARNING": {"episodes": 0, "relationships": 0, "interactions": 0},
        "OTHER": {"episodes": 0, "relationships": 0, "interactions": 0},
    }

    # FIX B: Properly map episode_type to life_area
    # episode_type values: work, social, routine, milestone, etc.
    episode_to_life_area = {
        "work": "WORK",
        "social": "SOCIAL",
        "routine": "OTHER",
        "milestone": "OTHER",
        "family": "FAMILY",
        "health": "HEALTH",
        "learning": "LEARNING",
        "leisure": "SOCIAL",
    }

    for r in episode_types:
        ep_type = (r["episode_type"] or "other").lower()
        life_area = episode_to_life_area.get(ep_type, "OTHER")
        life_categories[life_area]["episodes"] += r["count"]

    # Also check participants to identify FAMILY episodes
    # Episodes with family relationship participants should be counted as FAMILY
    family_participants = await conn.fetch("""
        SELECT COUNT(*) as cnt
        FROM st_epi e
        WHERE EXISTS (
            SELECT 1 FROM st_social s
            WHERE s.relationship_type = 'FAMILY'
            AND e.participants_json ILIKE '%' || s.relationship_label || '%'
        )
    """)
    if family_participants and family_participants[0]["cnt"]:
        life_categories["FAMILY"]["episodes"] = family_participants[0]["cnt"]

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
    health_patterns = await conn.fetchval("""
        SELECT COUNT(*) FROM st_sem
        WHERE pattern_subtype ILIKE '%health%' OR pattern_name ILIKE '%workout%'
              OR pattern_name ILIKE '%exercise%' OR pattern_name ILIKE '%doctor%'
    """)

    learning_patterns = await conn.fetchval("""
        SELECT COUNT(*) FROM st_sem
        WHERE pattern_type = 'LESSON' OR pattern_subtype ILIKE '%learning%'
              OR pattern_name ILIKE '%learned%' OR pattern_name ILIKE '%book%'
    """)

    life_categories["HEALTH"]["episodes"] = health_patterns or 0
    life_categories["LEARNING"]["episodes"] = learning_patterns or 0

    # Calculate totals
    total_episodes = sum(c["episodes"] for c in life_categories.values())
    total_interactions = sum(c["interactions"] for c in life_categories.values())

    print("""
   📊 LIFE AREA DISTRIBUTION:
   """)
    print(
        f"   Total Episodes: {int(total_episodes)} | Total Interactions: {int(total_interactions)}"
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
    # 12. DEEP PERSONALIZED INSIGHTS - Data-Driven Analysis
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("12. DEEP PERSONALIZED INSIGHTS - What Your Memories Reveal")
    print("═" * 100)

    # --- HEALTH PATTERNS ---
    print("\n   🏥 HEALTH PATTERN ANALYSIS:")
    print("   " + "─" * 90)

    gerd_mentions = await conn.fetch("""
        SELECT source_texts_json, dominant_emotion
        FROM st_observations o
        JOIN st_sem s ON o.record_id::text = s.pattern_id::text AND o.layer = 'st_sem'
        WHERE s.pattern_name ILIKE '%GERD%' OR s.pattern_description ILIKE '%GERD%'
        LIMIT 10
    """)

    # Also check episodes for GERD
    gerd_episodes = await conn.fetch("""
        SELECT episode_summary, source_texts_json
        FROM st_epi
        WHERE episode_summary ILIKE '%GERD%' OR episode_summary ILIKE '%stomach%'
              OR episode_summary ILIKE '%acid%' OR episode_summary ILIKE '%digestion%'
        LIMIT 5
    """)

    # Check raw events for GERD patterns
    gerd_events = await conn.fetch("""
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%GERD%' OR text ILIKE '%stomach%'
              OR text ILIKE '%spicy%' OR text ILIKE '%acid%'
        ORDER BY created_at DESC
        LIMIT 8
    """)

    gerd_semantic_count = len(gerd_mentions) if gerd_mentions else 0
    gerd_episode_count = len(gerd_episodes) if gerd_episodes else 0
    print(
        f"\n   GERD signal counts: {gerd_semantic_count} semantic patterns, {gerd_episode_count} episodes"
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

    sleep_events = await conn.fetch("""
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%sleep%' OR text ILIKE '%tired%'
              OR text ILIKE '%energy%' OR text ILIKE '%rest%'
        ORDER BY created_at DESC
        LIMIT 8
    """)

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

    project_events = await conn.fetch("""
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%K0%' OR text ILIKE '%K1%'
              OR text ILIKE '%FamilyOS%' OR text ILIKE '%pipeline%'
              OR text ILIKE '%P02%' OR text ILIKE '%P03%'
        ORDER BY created_at DESC
        LIMIT 15
    """)

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
    panda_events = await conn.fetch("""
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%Panda%'
        ORDER BY created_at DESC
        LIMIT 10
    """)

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
    family_events = await conn.fetch("""
        SELECT text, created_at
        FROM st_hipp_events
        WHERE text ILIKE '%Mom%' OR text ILIKE '%Dad%'
              OR text ILIKE '%Maya%' OR text ILIKE '%parents%'
        ORDER BY created_at DESC
        LIMIT 10
    """)

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
    recurring = await conn.fetch("""
        SELECT intention_description, COUNT(*) as mentions
        FROM st_prospective
        WHERE intention_type = 'DECISION' AND status = 'ACTIVE'
        GROUP BY intention_description
        HAVING COUNT(*) > 1
        ORDER BY mentions DESC
        LIMIT 5
    """)

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
                status_icon = (
                    "✅"
                    if issue["status"] == "RESOLVED"
                    else "🔄" if issue["status"] == "RECURRING" else "🔴"
                )
                cat_emoji = {
                    "TECH": "💻",
                    "HEALTH": "🏥",
                    "ADMIN": "📋",
                    "FAMILY": "👨‍👩‍👧",
                    "WORK": "💼",
                    "FINANCE": "💰",
                }.get(issue["issue_category"], "📌")

                print(f"\n   {status_icon} {cat_emoji} {issue['canonical_title']}")
                print(
                    f"      Status: {issue['status']} | Evidence: {issue['evidence_count']} events"
                )
                if issue["resolution_note"]:
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

    morning_work = await conn.fetch("""
        SELECT o.sentiment_score, e.episode_summary
        FROM st_observations o
        JOIN st_epi e ON o.record_id::text = e.episode_id::text AND o.layer = 'st_epi'
        WHERE o.circadian_slot = 'breakfast_window' AND e.episode_type = 'work'
        LIMIT 5
    """)

    night_work = await conn.fetch("""
        SELECT o.sentiment_score, e.episode_summary
        FROM st_observations o
        JOIN st_epi e ON o.record_id::text = e.episode_id::text AND o.layer = 'st_epi'
        WHERE o.circadian_slot = 'sleep_window' AND e.episode_type = 'work'
        LIMIT 5
    """)

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
                "HEALTH": "🏥 HEALTH",
                "TECH": "💻 TECH",
                "ADMIN": "📋 ADMIN",
                "FAMILY": "💒 FAMILY",
                "WORK": "💼 WORK",
                "FINANCE": "💰 FINANCE",
            }
            action_map = {
                "GERD/Digestive Issues": "Track meals before gym sessions - heavy squats seem to trigger symptoms",
                "H1B Visa/Immigration Paperwork": "Set a specific date to complete paperwork - unresolved admin creates background stress",
                "Wedding Planning": "Consider delegating - Mom and Panda's Mom both want to help",
                "Asus ProArt Overheating/Fan Noise": "Cooling pad should arrive soon - monitor temps after",
            }
            recommendations.append(
                {
                    "category": cat_map.get(issue["issue_category"], "📌 OTHER"),
                    "issue": f"{issue['canonical_title']} ({issue['evidence_count']} evidence events)",
                    "action": action_map.get(
                        issue["canonical_title"], "Review and address this recurring issue"
                    ),
                    "evidence": f"Status: {issue['status']} - tracked in st_issues",
                }
            )
    except Exception:
        # Fallback to GERD if st_issues doesn't exist
        if gerd_events and len(gerd_events) > 3:
            recommendations.append(
                {
                    "category": "🏥 HEALTH",
                    "issue": f"GERD mentioned {len(gerd_events)} times in 10 days",
                    "action": "Track meals before gym sessions - heavy squats seem to trigger symptoms",
                    "evidence": "Pattern: GERD flares after spicy food and heavy exercise",
                }
            )

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

    # ═══════════════════════════════════════════════════════════════════════════
    # 13. CAUSAL INTELLIGENCE - "Why did this happen?"
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("13. CAUSAL INTELLIGENCE - What Causes What?")
    print("    FamilyOS Demo 5-8: Causal Understanding & Adaptive Suggestions")
    print("═" * 100)

    # Query causal edges directly
    causal_chains = await conn.fetch("""
        SELECT
            s.canonical_name as cause,
            s.entity_type as cause_type,
            t.canonical_name as effect,
            t.entity_type as effect_type,
            e.edge_weight,
            e.confidence_score,
            e.observation_count
        FROM st_kg_edges e
        JOIN st_kg_dom s ON e.source_entity_id = s.entity_id
        JOIN st_kg_dom t ON e.target_entity_id = t.entity_id
        WHERE e.source_algorithm = 'bayesian_causal'
           OR e.relation_type = 'CAUSES'
        ORDER BY e.confidence_score DESC
        LIMIT 10
    """)

    print("\n   🔬 DISCOVERED CAUSAL RELATIONSHIPS:")
    print("   " + "─" * 90)

    if causal_chains:
        for i, c in enumerate(causal_chains, 1):
            conf = c["confidence_score"] or 0
            obs = c["observation_count"] or 1
            print(f"\n   {i}. {c['cause']} → {c['effect']}")
            print(f"      Cause Type: {c['cause_type']} | Effect Type: {c['effect_type']}")
            print(f"      Confidence: {conf:.2f} | Observations: {obs}")
    else:
        print("   No causal edges discovered yet. Need more events to detect patterns.")

    # Find patterns where X caused Y from raw text
    print("\n\n   📝 EXPLICIT CAUSAL STATEMENTS FROM YOUR MEMORIES:")
    print("   " + "─" * 90)

    causal_texts = await conn.fetch("""
        SELECT text FROM st_hipp_events
        WHERE text ILIKE '%because%'
           OR text ILIKE '%caused%'
           OR text ILIKE '%led to%'
           OR text ILIKE '%resulted in%'
           OR text ILIKE '%this is why%'
           OR text ILIKE '%which explains%'
        ORDER BY created_at DESC
        LIMIT 10
    """)

    if causal_texts:
        for i, t in enumerate(causal_texts[:8], 1):
            print(f"   {i}. \"{t['text'][:100]}{'...' if len(t['text']) > 100 else ''}\"")
    else:
        print("   No explicit causal statements found in events.")

    # Health causality
    print("\n\n   🏥 HEALTH CAUSAL CHAINS:")
    print("   " + "─" * 90)

    health_causal = await conn.fetch("""
        SELECT text FROM st_hipp_events
        WHERE (text ILIKE '%headache%' AND (text ILIKE '%because%' OR text ILIKE '%when%'))
           OR (text ILIKE '%GERD%' AND (text ILIKE '%because%' OR text ILIKE '%when%'))
           OR (text ILIKE '%sleep%' AND (text ILIKE '%because%' OR text ILIKE '%when%'))
           OR (text ILIKE '%tired%' AND (text ILIKE '%because%' OR text ILIKE '%when%'))
        ORDER BY created_at DESC
        LIMIT 8
    """)

    if health_causal:
        # Parse health patterns
        health_chains = []
        for h in health_causal:
            text = h["text"].lower()
            if "headache" in text:
                if "sleep" in text:
                    health_chains.append(("Poor sleep", "Headache"))
                if "screen" in text or "monitor" in text:
                    health_chains.append(("Screen time", "Headache"))
                if "dryness" in text or "dry" in text:
                    health_chains.append(("Nasal dryness", "Headache"))
                if "hydrate" in text:
                    health_chains.append(("Dehydration", "Headache"))
            if "gerd" in text:
                if "spicy" in text:
                    health_chains.append(("Spicy food", "GERD flare"))
                if "late" in text:
                    health_chains.append(("Late night eating", "GERD flare"))
                if "stress" in text:
                    health_chains.append(("Stress", "GERD flare"))
                if "coffee" in text:
                    health_chains.append(("Coffee", "GERD flare"))
            if "tired" in text or "energy" in text:
                if "skip" in text and "breakfast" in text:
                    health_chains.append(("Skipping breakfast", "Low energy"))
                if "late" in text and "code" in text:
                    health_chains.append(("Late night coding", "Fatigue"))

        # Dedupe and show
        health_chains = list(set(health_chains))
        if health_chains:
            print("\n   Discovered Health Cause-Effect Relationships:")
            for cause, effect in health_chains:
                print(f"      {cause} ──causes──▶ {effect}")
        else:
            print("   Analyzing raw mentions...")
            for h in health_causal[:5]:
                print(f"      • \"{h['text'][:90]}...\"")
    else:
        print("   No health causal patterns found yet.")

    # ═══════════════════════════════════════════════════════════════════════════
    # 14. CROSS-LAYER INTELLIGENCE - Connecting the Dots
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("14. CROSS-LAYER INTELLIGENCE - Connecting the Dots")
    print("    FamilyOS Demo 2: Associative Context Recall")
    print("═" * 100)

    # Example: "What do I know about display issues?"
    print("\n   📋 DEMO: 'Tell me everything about display/monitor issues'")
    print("   " + "─" * 90)

    # From episodic memory
    display_episodes = await conn.fetch("""
        SELECT episode_summary, source_texts_json, primary_location
        FROM st_epi
        WHERE episode_summary ILIKE '%display%' OR episode_summary ILIKE '%monitor%'
              OR episode_summary ILIKE '%flicker%' OR episode_summary ILIKE '%dock%'
        LIMIT 5
    """)

    # From semantic memory (patterns learned)
    display_patterns = await conn.fetch("""
        SELECT pattern_name, pattern_description, confidence_score
        FROM st_sem
        WHERE pattern_name ILIKE '%display%' OR pattern_name ILIKE '%monitor%'
              OR pattern_name ILIKE '%dock%' OR pattern_name ILIKE '%flicker%'
              OR pattern_description ILIKE '%display%'
        LIMIT 5
    """)

    # From KG entities
    display_entities = await conn.fetch("""
        SELECT canonical_name, entity_type, observation_count
        FROM st_kg_dom
        WHERE canonical_name ILIKE '%monitor%' OR canonical_name ILIKE '%dock%'
              OR canonical_name ILIKE '%OLED%' OR canonical_name ILIKE '%display%'
        LIMIT 5
    """)

    # From prospective (decisions/reminders)
    display_decisions = await conn.fetch("""
        SELECT intention_description, intention_type, status
        FROM st_prospective
        WHERE intention_description ILIKE '%monitor%' OR intention_description ILIKE '%display%'
              OR intention_description ILIKE '%dock%'
        LIMIT 3
    """)

    # From raw events
    display_events = await conn.fetch("""
        SELECT text FROM st_hipp_events
        WHERE text ILIKE '%dock%' OR text ILIKE '%flicker%'
              OR text ILIKE '%display%' OR text ILIKE '%OLED%'
        ORDER BY created_at DESC
        LIMIT 8
    """)

    print("\n   📚 EPISODIC MEMORY (What happened):")
    if display_episodes:
        for ep in display_episodes[:3]:
            print(f"      • {ep['episode_summary']} @ {ep['primary_location']}")
    else:
        print("      (No display-related episodes consolidated yet)")

    print("\n   🧠 SEMANTIC MEMORY (What I learned):")
    if display_patterns:
        for p in display_patterns[:3]:
            desc = p["pattern_description"] or "No description"
            print(f"      • {p['pattern_name']}: {desc[:60]}...")
    else:
        print("      (No display-related patterns extracted yet)")

    print("\n   🔗 KNOWLEDGE GRAPH (Entities involved):")
    if display_entities:
        for e in display_entities[:3]:
            print(
                f"      • {e['canonical_name']} ({e['entity_type']}) - {e['observation_count']} mentions"
            )
    else:
        print("      (No display-related entities found)")

    print("\n   ⏰ PROSPECTIVE MEMORY (Decisions pending):")
    if display_decisions:
        for d in display_decisions:
            print(f"      • [{d['intention_type']}] {d['intention_description']}")
    else:
        print("      (No display-related decisions pending)")

    print("\n   📝 RAW MEMORIES (Original events):")
    if display_events:
        for e in display_events[:4]:
            print(f"      • \"{e['text'][:80]}...\"")

    # Show the resolution story
    print("\n   💡 RESOLUTION STORY:")
    resolution_events = await conn.fetch("""
        SELECT text FROM st_hipp_events
        WHERE text ILIKE '%switching docks%' OR text ILIKE '%flicker stopped%'
        LIMIT 3
    """)
    if resolution_events:
        print("      After investigating display flicker issues:")
        print(f"      ✅ \"{resolution_events[0]['text']}\"")
        print("      → The old USB-C dock was the culprit. Problem solved by switching docks.")
    else:
        print("      (Resolution story not yet available)")

    # ═══════════════════════════════════════════════════════════════════════════
    # 15. DECISION SUPPORT - What Should I Do?
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("15. DECISION SUPPORT - Informed Recommendations")
    print("    FamilyOS Demo 16: Decision Support & Context Weaving")
    print("═" * 100)

    # Get active decisions
    active_decisions = await conn.fetch("""
        SELECT intention_description, source_texts_json, confidence_score
        FROM st_prospective
        WHERE intention_type = 'DECISION' AND status = 'ACTIVE'
        ORDER BY created_at DESC
        LIMIT 5
    """)

    print("\n   🤔 YOUR ACTIVE DECISIONS:")
    print("   " + "─" * 90)

    for i, d in enumerate(active_decisions, 1):
        print(f"\n   {i}. {d['intention_description']}")

        # Find related context
        keywords = d["intention_description"].lower().split()[:3]
        related_context = []

        for kw in keywords:
            if len(kw) > 3:  # Skip small words
                related = await conn.fetch(
                    """
                    SELECT text FROM st_hipp_events
                    WHERE text ILIKE $1
                    LIMIT 3
                """,
                    f"%{kw}%",
                )
                for r in related:
                    if r["text"] not in [rc["text"] for rc in related_context]:
                        related_context.append(r)

        if related_context:
            print("      📝 Related context from your memories:")
            for rc in related_context[:2]:
                print(f"         • \"{rc['text'][:70]}...\"")

    # ═══════════════════════════════════════════════════════════════════════════
    # 16. RELATIONSHIP INTELLIGENCE - Social Network Analysis
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("16. RELATIONSHIP INTELLIGENCE - Your Social Network")
    print("    FamilyOS Demo 13-15: Emotional & Conflict Mediation Support")
    print("═" * 100)

    # Get all relationships with context
    relationships = await conn.fetch("""
        SELECT
            relationship_label,
            relationship_type,
            interaction_count,
            avg_sentiment,
            dominant_emotion,
            source_texts_json
        FROM st_social
        ORDER BY interaction_count DESC
        LIMIT 10
    """)

    print("\n   👥 YOUR RELATIONSHIP MAP:")
    print("   " + "─" * 90)

    # Group by relationship type
    by_type = {}
    for r in relationships:
        rtype = r["relationship_type"] or "OTHER"
        if rtype not in by_type:
            by_type[rtype] = []
        by_type[rtype].append(r)

    for rtype, people in by_type.items():
        type_emoji = {
            "FAMILY": "👨‍👩‍👧",
            "PARTNER": "💑",
            "FRIEND": "🤝",
            "COLLEAGUE": "💼",
        }.get(rtype, "👤")

        print(f"\n   {type_emoji} {rtype}:")
        for p in people:
            sent = p["avg_sentiment"] or 0
            emotion = p["dominant_emotion"] or "neutral"
            sentiment_bar = "🟢" if sent > 0.3 else "🟡" if sent > -0.1 else "🔴"
            print(
                f"      {sentiment_bar} {p['relationship_label']}: {p['interaction_count']} interactions"
            )
            print(f"         Sentiment: {sent:.2f} | Emotion: {emotion}")

    # Co-occurrence network
    print("\n\n   🔗 WHO APPEARS TOGETHER?")
    print("   " + "─" * 90)

    # Find episodes with multiple participants
    multi_participant = await conn.fetch("""
        SELECT participants_json, episode_summary
        FROM st_epi
        WHERE participant_count >= 2
        ORDER BY participant_count DESC
        LIMIT 8
    """)

    if multi_participant:
        pair_counts = {}
        for m in multi_participant:
            if m["participants_json"]:
                try:
                    participants = json.loads(m["participants_json"])
                    for i, p1 in enumerate(participants):
                        for p2 in participants[i + 1 :]:
                            pair = tuple(sorted([p1, p2]))
                            pair_counts[pair] = pair_counts.get(pair, 0) + 1
                except Exception:
                    pass

        for pair, count in sorted(pair_counts.items(), key=lambda x: -x[1])[:5]:
            print(f"      {pair[0]} + {pair[1]}: {count} times together")
    else:
        print("      (No multi-participant episodes found)")

    # ═══════════════════════════════════════════════════════════════════════════
    # 17. TEMPORAL PATTERNS - When Does What Happen?
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("17. TEMPORAL PATTERNS - Your Daily Rhythm")
    print("    FamilyOS Demo 17: Preference Learning & Routine Detection")
    print("═" * 100)

    # Analyze by circadian slot
    circadian_analysis = await conn.fetch("""
        SELECT
            circadian_slot,
            COUNT(*) as event_count,
            AVG(sentiment_score) as avg_sentiment,
            array_agg(DISTINCT dominant_emotion) FILTER (WHERE dominant_emotion IS NOT NULL AND dominant_emotion != '') as emotions
        FROM st_observations
        WHERE circadian_slot IS NOT NULL AND circadian_slot != ''
        GROUP BY circadian_slot
        ORDER BY
            CASE circadian_slot
                WHEN 'breakfast_window' THEN 1
                WHEN 'morning_focus' THEN 2
                WHEN 'midday_window' THEN 3
                WHEN 'afternoon_focus' THEN 4
                WHEN 'evening_wind_down' THEN 5
                WHEN 'sleep_window' THEN 6
                ELSE 7
            END
    """)

    print("\n   ⏰ YOUR DAILY RHYTHM:")
    print("   " + "─" * 90)

    slot_emoji = {
        "breakfast_window": "🌅",
        "morning_focus": "☀️",
        "midday_window": "🌞",
        "afternoon_focus": "🌤️",
        "evening_wind_down": "🌆",
        "sleep_window": "🌙",
    }

    for c in circadian_analysis:
        emoji = slot_emoji.get(c["circadian_slot"], "⏰")
        sent = c["avg_sentiment"] or 0
        emotions = c["emotions"][:3] if c["emotions"] else []
        bar_len = min(c["event_count"] // 5, 20)
        bar = "█" * bar_len

        print(f"\n   {emoji} {c['circadian_slot'].replace('_', ' ').title()}")
        print(f"      Events: {c['event_count']} | Avg Sentiment: {sent:.2f}")
        print(f"      Emotions: {', '.join(emotions)}")
        print(f"      {bar}")

    # Weekend vs Weekday
    print("\n\n   📅 WEEKEND vs WEEKDAY:")
    print("   " + "─" * 90)

    weekend_stats = await conn.fetch("""
        SELECT
            is_weekend,
            COUNT(*) as count,
            AVG(sentiment_score) as avg_sent,
            array_agg(DISTINCT dominant_emotion) FILTER (WHERE dominant_emotion IS NOT NULL AND dominant_emotion != '') as emotions
        FROM st_observations
        GROUP BY is_weekend
    """)

    for w in weekend_stats:
        label = "Weekend 🎉" if w["is_weekend"] else "Weekday 💼"
        sent = w["avg_sent"] or 0
        emotions = w["emotions"][:4] if w["emotions"] else []
        print(f"\n   {label}")
        print(f"      Events: {w['count']} | Avg Sentiment: {sent:.2f}")
        print(f"      Common Emotions: {', '.join(emotions)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 18. LOCATION INTELLIGENCE - Where Does What Happen?
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("18. LOCATION INTELLIGENCE - Your Spatial Patterns")
    print("    FamilyOS Demo 9-12: Adaptive Home Intelligence")
    print("═" * 100)

    # Location-based analysis
    location_stats = await conn.fetch("""
        SELECT
            e.primary_location,
            COUNT(*) as episode_count,
            AVG(o.sentiment_score) as avg_sentiment,
            array_agg(DISTINCT e.episode_type) as episode_types
        FROM st_epi e
        JOIN st_observations o ON o.layer = 'st_epi' AND o.record_id = e.episode_id
        WHERE e.primary_location IS NOT NULL AND e.primary_location != ''
        GROUP BY e.primary_location
        ORDER BY episode_count DESC
        LIMIT 8
    """)

    print("\n   📍 YOUR LOCATIONS:")
    print("   " + "─" * 90)

    loc_emoji = {
        "home": "🏠",
        "office": "🏢",
        "gym": "🏋️",
        "starbucks": "☕",
        "micro center": "🛒",
    }

    for loc in location_stats:
        loc_name = loc["primary_location"] or "Unknown"
        emoji = loc_emoji.get(loc_name.lower(), "📍")
        sent = loc["avg_sentiment"] or 0
        types = loc["episode_types"][:3] if loc["episode_types"] else []

        sentiment_indicator = "😊" if sent > 0.3 else "😐" if sent > -0.1 else "😔"

        print(f"\n   {emoji} {loc_name}")
        print(
            f"      Episodes: {loc['episode_count']} | Sentiment: {sent:.2f} {sentiment_indicator}"
        )
        print(f"      Activities: {', '.join(types)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 19. REMINDER INTELLIGENCE - What's on Your Mind?
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("19. REMINDER INTELLIGENCE - Your Mental Load")
    print("    FamilyOS Demo 19: Project Orchestration & Task Tracking")
    print("═" * 100)

    # All reminders grouped by category
    reminders_by_type = await conn.fetch("""
        SELECT
            intention_type,
            status,
            COUNT(*) as count,
            array_agg(intention_description) as descriptions
        FROM st_prospective
        GROUP BY intention_type, status
        ORDER BY
            CASE intention_type
                WHEN 'REMINDER' THEN 1
                WHEN 'DECISION' THEN 2
                WHEN 'REFLECTION' THEN 3
                ELSE 4
            END,
            CASE status
                WHEN 'ACTIVE' THEN 1
                WHEN 'PENDING' THEN 2
                ELSE 3
            END
    """)

    print("\n   🧠 YOUR MENTAL LOAD:")
    print("   " + "─" * 90)

    type_emoji = {
        "REMINDER": "⏰",
        "DECISION": "🤔",
        "REFLECTION": "💭",
        "GOAL": "🎯",
    }

    for r in reminders_by_type:
        emoji = type_emoji.get(r["intention_type"], "📌")
        status_emoji = (
            "🟢" if r["status"] == "ACTIVE" else "🟡" if r["status"] == "PENDING" else "⚪"
        )
        print(f"\n   {emoji} {r['intention_type']} ({r['status']}) - {r['count']} items")

        if r["descriptions"]:
            for desc in r["descriptions"][:3]:
                print(f"      {status_emoji} {desc[:70]}...")

    # ═══════════════════════════════════════════════════════════════════════════
    # 20. HOLISTIC LIFE VIEW - Everything Connected
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n" + "═" * 100)
    print("20. HOLISTIC LIFE VIEW - Everything Connected")
    print("    FamilyOS Vision: Context-Aware Family Intelligence")
    print("═" * 100)

    # Get overall stats
    stats = {}
    stats["events"] = await conn.fetchval("SELECT COUNT(*) FROM st_hipp_events")
    stats["episodes"] = await conn.fetchval("SELECT COUNT(*) FROM st_epi")
    stats["patterns"] = await conn.fetchval("SELECT COUNT(*) FROM st_sem")
    stats["entities"] = await conn.fetchval("SELECT COUNT(*) FROM st_kg_dom")
    stats["edges"] = await conn.fetchval("SELECT COUNT(*) FROM st_kg_edges")
    stats["relationships"] = await conn.fetchval("SELECT COUNT(*) FROM st_social")
    stats["intentions"] = await conn.fetchval("SELECT COUNT(*) FROM st_prospective")
    stats["observations"] = await conn.fetchval("SELECT COUNT(*) FROM st_observations")

    print(f"""
   ╔══════════════════════════════════════════════════════════════════════════════╗
   ║                         YOUR LIFE IN NUMBERS                                  ║
   ╠══════════════════════════════════════════════════════════════════════════════╣
   ║  📥 Raw Events Ingested:        {stats['events']:>6}                                    ║
   ║  📖 Episodic Memories:          {stats['episodes']:>6}  (What happened)                 ║
   ║  🧠 Semantic Patterns:          {stats['patterns']:>6}  (What you learned)              ║
   ║  🔗 Knowledge Entities:         {stats['entities']:>6}  (People, places, things)        ║
   ║  ↔️  Knowledge Edges:            {stats['edges']:>6}  (How things connect)             ║
   ║  💕 Social Relationships:       {stats['relationships']:>6}  (Who matters)                   ║
   ║  ⏰ Prospective Intentions:     {stats['intentions']:>6}  (What's on your mind)           ║
   ║  👁️  Contextual Observations:   {stats['observations']:>6}  (Holistic context layer)        ║
   ╚══════════════════════════════════════════════════════════════════════════════╝
    """)

    # Show how layers connect
    print("\n   🔗 HOW LAYERS INTERCONNECT:")
    print("   " + "─" * 90)

    # Find an example that spans multiple layers
    cross_layer_example = await conn.fetch("""
        SELECT DISTINCT
            e.episode_summary,
            e.participants_json,
            e.primary_location,
            o.sentiment_score,
            o.dominant_emotion,
            o.circadian_slot
        FROM st_epi e
        JOIN st_observations o ON o.layer = 'st_epi' AND o.record_id = e.episode_id
        WHERE e.participant_count > 0
          AND o.sentiment_score IS NOT NULL
        LIMIT 1
    """)

    if cross_layer_example:
        ex = cross_layer_example[0]
        participants = []
        if ex["participants_json"]:
            try:
                participants = json.loads(ex["participants_json"])
            except Exception:
                pass

        print(f"""
   EXAMPLE: A Single Memory's Multi-Layer Presence

   📖 EPISODIC: "{ex['episode_summary']}"
      └── Location: {ex['primary_location']}
      └── Participants: {participants}

   👁️ OBSERVATION:
      └── Sentiment: {ex['sentiment_score']:.2f}
      └── Emotion: {ex['dominant_emotion']}
      └── Time: {ex['circadian_slot']}
        """)

        # Check if participants have social entries
        if participants:
            person = participants[0] if participants else None
            if person:
                social_entry = await conn.fetchrow(
                    """
                    SELECT relationship_label, relationship_type, interaction_count
                    FROM st_social
                    WHERE relationship_label ILIKE $1
                    LIMIT 1
                """,
                    f"%{person}%",
                )

                if social_entry:
                    print(f"""   💕 SOCIAL: {social_entry['relationship_label']}
      └── Type: {social_entry['relationship_type']}
      └── Total Interactions: {social_entry['interaction_count']}
                    """)

                # Check KG entity
                kg_entry = await conn.fetchrow(
                    """
                    SELECT canonical_name, entity_type, observation_count
                    FROM st_kg_dom
                    WHERE canonical_name ILIKE $1
                    LIMIT 1
                """,
                    f"%{person}%",
                )

                if kg_entry:
                    print(f"""   🔗 KNOWLEDGE GRAPH: {kg_entry['canonical_name']}
      └── Type: {kg_entry['entity_type']}
      └── Observations: {kg_entry['observation_count']}
                    """)

    print("\n" + "═" * 100)
    print("🎯 THIS IS THE FAMILYOS VISION:")
    print("═" * 100)
    print("""
   Every life event creates ripples across ALL memory layers:

   Event: "Called Panda, promised to plan our trip to Chicago"
                    │
         ┌─────────┴─────────────────────────────────────────┐
         │                                                   │
         ▼                                                   ▼
   ┌──────────────┐                                   ┌──────────────┐
   │  EPISODIC    │                                   │ PROSPECTIVE  │
   │  "Call with  │                                   │ "Plan trip   │
   │   Panda"     │                                   │  to Chicago" │
   └──────┬───────┘                                   └──────────────┘
          │
          ├──────────────────┬──────────────────┐
          ▼                  ▼                  ▼
   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │   SOCIAL     │   │  KNOWLEDGE   │   │ OBSERVATION  │
   │   "Panda:    │   │  "Chicago:   │   │ "Evening,    │
   │   Partner"   │   │   Location"  │   │  Positive"   │
   └──────────────┘   └──────────────┘   └──────────────┘

   This interconnected structure enables:
   ✓ "Who should I call about the Chicago trip?" → SOCIAL layer
   ✓ "What did we discuss about Chicago?" → EPISODIC layer
   ✓ "When was I happiest planning trips?" → OBSERVATION layer
   ✓ "What cities have we discussed visiting?" → KNOWLEDGE layer
   ✓ "What travel plans are pending?" → PROSPECTIVE layer

   THIS IS THE HOLISTIC VIEW THAT ONLY FAMILYOS CAN PROVIDE.
    """)

    print("\n" + "═" * 100)
    print("✅ MEMORY LAYER EXPLORATION COMPLETE")
    print("═" * 100)

    await conn.close()
    _OUTPUT_MIRROR.close()
    _OUTPUT_MIRROR = None


if __name__ == "__main__":
    asyncio.run(explore_all_layers())
