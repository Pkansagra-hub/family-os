"""Check intent-based and emotion-based edges in st_kg_edges table."""

import asyncio
import json
import os

import asyncpg


async def check_edges():
    """Check for intent and emotion edges in the knowledge graph."""
    dsn = os.environ.get("K0_POSTGRES_DSN", "postgresql://k0user:changeme@localhost:5432/k0_kernel")
    print(f"Connecting to: {dsn.replace('k0pass', '***')}")

    try:
        conn = await asyncpg.connect(dsn)
        print("✅ Connected to database")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return

    try:
        # Check total edges
        total_edges = await conn.fetchval("SELECT COUNT(*) FROM st_kg_edges")
        print(f"\n📊 Total edges in st_kg_edges: {total_edges}")

        # Check intent-related edges
        intent_edges = await conn.fetch(
            """
            SELECT COUNT(*) as count,
                   AVG(confidence_score) as avg_confidence,
                   AVG(edge_weight) as avg_weight
            FROM st_kg_edges
            WHERE relation_type = 'INTENT_RELATED'
        """
        )

        if intent_edges[0]["count"] > 0:
            print("\n🎯 INTENT_RELATED edges:")
            print(f"   Count: {intent_edges[0]['count']}")
            print(f"   Avg Confidence: {intent_edges[0]['avg_confidence']:.2f}")
            print(f"   Avg Weight: {intent_edges[0]['avg_weight']:.2f}")
        else:
            print("\n❌ No INTENT_RELATED edges found")

        # Check emotion-related edges
        emotion_edges = await conn.fetch(
            """
            SELECT COUNT(*) as count,
                   AVG(confidence_score) as avg_confidence,
                   AVG(edge_weight) as avg_weight
            FROM st_kg_edges
            WHERE relation_type = 'EMOTIONALLY_RELATED'
        """
        )

        if emotion_edges[0]["count"] > 0:
            print("\n😊 EMOTIONALLY_RELATED edges:")
            print(f"   Count: {emotion_edges[0]['count']}")
            print(f"   Avg Confidence: {emotion_edges[0]['avg_confidence']:.2f}")
            print(f"   Avg Weight: {emotion_edges[0]['avg_weight']:.2f}")
        else:
            print("\n❌ No EMOTIONALLY_RELATED edges found")

        # Check by source algorithm
        algorithm_counts = await conn.fetch(
            """
            SELECT source_algorithm, COUNT(*) as count
            FROM st_kg_edges
            WHERE source_algorithm IN ('intent_similarity', 'emotion_similarity')
            GROUP BY source_algorithm
            ORDER BY source_algorithm
        """
        )

        if algorithm_counts:
            print("\n🔍 Edges by source algorithm:")
            for row in algorithm_counts:
                print(f"   {row['source_algorithm']}: {row['count']} edges")
        else:
            print("\n❌ No edges from intent_similarity or emotion_similarity algorithms")

        # Show sample intent edges
        sample_intent = await conn.fetch(
            """
            SELECT edge_id, source_entity_id, target_entity_id,
                   confidence_score, edge_weight, properties_json,
                   evidence_event_ids, created_at
            FROM st_kg_edges
            WHERE relation_type = 'INTENT_RELATED'
            LIMIT 3
        """
        )

        if sample_intent:
            print("\n📋 Sample INTENT_RELATED edges:")
            for edge in sample_intent:
                print(f"   {edge['source_entity_id']} → {edge['target_entity_id']}")
                print(
                    f"     Confidence: {edge['confidence_score']:.2f}, Weight: {edge['edge_weight']:.2f}"
                )
                if edge["properties_json"]:
                    try:
                        props = json.loads(edge["properties_json"])
                        if "complementarity_score" in props:
                            print(f"     Complementarity: {props['complementarity_score']:.2f}")
                        if "intent_profile_a" in props and "intent_profile_b" in props:
                            intent_a = (
                                list(props["intent_profile_a"].keys())[0]
                                if props["intent_profile_a"]
                                else "none"
                            )
                            intent_b = (
                                list(props["intent_profile_b"].keys())[0]
                                if props["intent_profile_b"]
                                else "none"
                            )
                            print(f"     Intents: {intent_a} ↔ {intent_b}")
                    except Exception:
                        print(f"     Properties: {edge['properties_json'][:100]}...")
                print(
                    f"     Evidence events: {len(edge['evidence_event_ids']) if edge['evidence_event_ids'] else 0}"
                )
                print()

        # Show sample emotion edges
        sample_emotion = await conn.fetch(
            """
            SELECT edge_id, source_entity_id, target_entity_id,
                   confidence_score, edge_weight, properties_json,
                   evidence_event_ids, created_at
            FROM st_kg_edges
            WHERE relation_type = 'EMOTIONALLY_RELATED'
            LIMIT 3
        """
        )

        if sample_emotion:
            print("\n😊 Sample EMOTIONALLY_RELATED edges:")
            for edge in sample_emotion:
                print(f"   {edge['source_entity_id']} → {edge['target_entity_id']}")
                print(
                    f"     Confidence: {edge['confidence_score']:.2f}, Weight: {edge['edge_weight']:.2f}"
                )
                if edge["properties_json"]:
                    try:
                        props = json.loads(edge["properties_json"])
                        if "emotion_similarity" in props:
                            print(f"     Similarity: {props['emotion_similarity']:.2f}")
                        if "shared_emotions" in props:
                            print(f"     Shared emotions: {props['shared_emotions']}")
                    except Exception:
                        print(f"     Properties: {edge['properties_json'][:100]}...")
                print(
                    f"     Evidence events: {len(edge['evidence_event_ids']) if edge['evidence_event_ids'] else 0}"
                )
                print()

        # Check recent edges (last 24 hours)
        recent_edges = await conn.fetch(
            """
            SELECT COUNT(*) as recent_count
            FROM st_kg_edges
            WHERE created_at > (EXTRACT(epoch FROM NOW() - INTERVAL '24 hours') * 1000)::bigint
            AND relation_type IN ('INTENT_RELATED', 'EMOTIONALLY_RELATED')
        """
        )

        print(f"🕐 Edges created in last 24h: {recent_edges[0]['recent_count']}")

    except Exception as e:
        print(f"❌ Query error: {e}")
    finally:
        await conn.close()
        print("\n✅ Database connection closed")


if __name__ == "__main__":
    asyncio.run(check_edges())
