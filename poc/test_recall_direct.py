#!/usr/bin/env python3
"""
Test recall module directly against live PostgreSQL data.

This script tests the ContextExpander recall module without going through
the HTTP API, bypassing policy enforcement for development testing.

Usage:
    python poc/test_recall_direct.py
    python poc/test_recall_direct.py --build-index
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set FAISS index directory before importing
os.environ["FAISS_UNION_INDEX_DIR"] = str(Path(__file__).parent.parent / "data" / "faiss_union")

from k0.modules.embedding.union_index_manager import get_manager
from k0.modules.recall.context_expander import ContextExpander


async def build_faiss_index(conn):
    """Build FAISS index from database vectors."""
    print("\n=== Building FAISS Union Index ===")

    manager = get_manager()
    print(f"  Index directory: {manager.index_dir}")

    # Build and save the index
    searcher = await manager.build_and_save(conn, tenant_id="tenant-test")

    print(f"  Total vectors: {manager._metadata.total_vectors if manager._metadata else 0}")
    print(f"  Layer counts: {manager._metadata.layer_counts if manager._metadata else {}}")
    print("  Index built successfully!")

    return searcher


async def test_recall(build_index: bool = False, custom_query: str | None = None, top_k: int = 5):
    """Test the recall module against live data."""

    # Connect to PostgreSQL via pgbouncer
    print("Connecting to PostgreSQL via pgbouncer...")
    conn = await asyncpg.connect(
        host="localhost",
        port=6432,
        user="k0",
        password="k0pass",
        database="k0_kernel",
        statement_cache_size=0,  # Required for pgbouncer transaction mode
    )

    try:
        # Check what data we have
        print("\n=== Memory Layer Summary ===")

        layers = [
            ("st_hipp_events", "Hippocampus Events"),
            ("st_sem", "Semantic Memory"),
            ("st_prospective", "Prospective Memory"),
            ("st_social", "Social Memory"),
            ("st_vec", "Embedding Vectors"),
        ]

        for table, name in layers:
            try:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                print(f"  {name}: {count} records")
            except Exception:
                print(f"  {name}: (table not found)")

        # Sample some semantic patterns
        print("\n=== Sample Semantic Patterns (st_sem) ===")
        rows = await conn.fetch(
            """
            SELECT pattern_type, pattern_name, confidence_score
            FROM st_sem
            ORDER BY created_at DESC
            LIMIT 10
        """
        )
        for row in rows:
            print(
                f"  [{row['pattern_type']}] {row['pattern_name'][:60]}... (conf={row['confidence_score']:.2f})"
            )

        # Sample prospective memory
        print("\n=== Prospective Memory (st_prospective) ===")
        rows = await conn.fetch(
            """
            SELECT intention_type, intention_description, target_context
            FROM st_prospective
            ORDER BY created_at DESC
            LIMIT 5
        """
        )
        for row in rows:
            desc = row["intention_description"][:50] if row["intention_description"] else ""
            ctx = row["target_context"][:30] if row["target_context"] else ""
            print(f"  [{row['intention_type']}] {desc}... (ctx: {ctx})")

        # Try to use the recall module
        print("\n=== Testing ContextExpander ===")

        # Get the union index manager
        manager = get_manager()

        # Build index if requested
        if build_index:
            searcher = await build_faiss_index(conn)
        else:
            searcher = manager.get_searcher()

        if searcher is None:
            print("  WARNING: No searcher available (FAISS index not loaded)")
            print("  The recall module requires embeddings to be indexed.")
            print("  Run the embedding pipeline to populate the union index.")
            return

        # Create expander
        expander = ContextExpander(
            top_k=top_k + 5,  # Fetch extra for filtering
            max_hops=1,
            min_edge_weight=0.5,
        )

        # Test query - use UltraBERT for real embedding
        test_query = custom_query or "What did Mom do?"
        print(f"\n  Query: '{test_query}'")

        # Get real embedding from UltraBERT
        try:
            from k0.runtime.ultrabert_adapter import get_embedding as ultrabert_embed

            query_embedding = ultrabert_embed(test_query)
            if query_embedding is None:
                raise RuntimeError("UltraBERT returned None")
            print(f"  Got UltraBERT embedding: {len(query_embedding)} dimensions")
        except Exception as e:
            print(f"  WARNING: UltraBERT not available ({e}), using random embedding")
            import numpy as np

            query_embedding = np.random.randn(768).astype(np.float32).tolist()

        # Pre-fetch records for entity extraction (this is what enables graph expansion!)
        # First, do a preliminary vector search to get record IDs
        import numpy as np

        preliminary_results = searcher.search(
            query_vector=np.array(query_embedding, dtype=np.float32),
            k=top_k + 5,
            tenant_id="tenant-test",
        )

        # Fetch actual records for entity extraction
        records_by_id: dict[str, dict] = {}
        for r in preliminary_results:
            record_data, _ = await fetch_record_content(conn, r.layer, r.record_id)
            if record_data and "error" not in record_data:
                records_by_id[r.record_id] = record_data

        print(f"  Pre-fetched {len(records_by_id)} records for entity extraction")

        # Try expansion with records_by_id for entity extraction
        result = await expander.expand(
            query=test_query,
            embedding=query_embedding,
            conn=conn,
            tenant_id="tenant-test",
            searcher=searcher,
            records_by_id=records_by_id,
        )

        # Debug: show extracted entities
        if result.expanded_entities:
            print(f"  Extracted entity IDs: {result.expanded_entities}")

        print(f"  Direct results: {len(result.direct_results)}")
        print(f"  Expanded entities: {len(result.expanded_entities)}")
        print(
            f"  Related records: {result.related_context.total_records if result.related_context else 0}"
        )
        print(f"  Timing: {result.timing_ms}")

        # Fetch full context for top results
        print("\n" + "=" * 80)
        print(f"CONTEXT ENVELOPE - Top {top_k} Search Results with Full Structured Content")
        print("=" * 80)

        for i, r in enumerate(result.direct_results[:top_k]):
            print(f"\n{'─' * 80}")
            print(f"Result #{i+1}")
            print(f"{'─' * 80}")
            print(f"  Layer:     {r.layer}")
            print(f"  Record ID: {r.record_id}")
            print(f"  Score:     {r.score:.4f}")
            print(f"  Tenant:    {r.tenant_id}")
            print(f"  Space:     {r.space_id}")

            # Fetch actual record content based on layer
            record_data, display_order = await fetch_record_content(conn, r.layer, r.record_id)
            if record_data:
                print("\n  ┌─ Record Content ─────────────────────────────────")
                if display_order:
                    # Use structured display order for clean output
                    for label, field_name in display_order:
                        value = record_data.get(field_name)
                        if value is not None:
                            val_str = str(value)
                            if len(val_str) > 300:
                                val_str = val_str[:300] + "..."
                            print(f"  │ {label}: {val_str}")
                else:
                    # Fallback to raw key/value pairs
                    for key, value in record_data.items():
                        if value is not None and key != "embedding_vector":
                            val_str = str(value)
                            if len(val_str) > 300:
                                val_str = val_str[:300] + "..."
                            print(f"  │ {key}: {val_str}")
                print("  └────────────────────────────────────────────────────")

        # Summary context envelope
        print("\n" + "=" * 80)
        print("CONTEXT ENVELOPE SUMMARY")
        print("=" * 80)
        context_envelope = build_context_envelope(result, test_query)
        import json

        print(json.dumps(context_envelope, indent=2, default=str))

    finally:
        await conn.close()
        print("\nConnection closed.")


async def fetch_record_content(conn, layer: str, record_id: str) -> tuple[dict, list]:
    """Fetch full record content from the appropriate table.

    Returns:
        Tuple of (record_data dict, display_order list of (label, field) tuples)
    """

    # Map layer to table, primary key, and ALL structured fields
    layer_configs = {
        "st_epi": {
            "table": "st_epi",
            "pk": "episode_id",
            "fields": [
                "episode_id",
                "episode_summary",
                "episode_type",
                "primary_location",
                "location_type",
                "participants_json",
                "participant_count",
                "start_time_utc",
                "end_time_utc",
                "duration_minutes",
                "source_event_count",
                "is_recurring",
                "recurrence_pattern",
                "embedding_text",
                "confidence_score",
                "observation_count",
                "created_at",
            ],
            "display_order": [
                ("Episode Summary", "episode_summary"),
                ("Episode Type", "episode_type"),
                ("Location", "primary_location"),
                ("Location Type", "location_type"),
                ("Participants", "participants_json"),
                ("Participant Count", "participant_count"),
                ("Source Events", "source_event_count"),
                ("Recurring", "is_recurring"),
                ("Pattern", "recurrence_pattern"),
                ("Confidence", "confidence_score"),
                ("Embedding Text", "embedding_text"),
            ],
        },
        "st_sem": {
            "table": "st_sem",
            "pk": "pattern_id",
            "fields": [
                "pattern_id",
                "pattern_type",
                "pattern_name",
                "observation_count",
                "embedding_text",
                "confidence_score",
                "source_episodes_json",
                "created_at",
            ],
            "display_order": [
                ("Pattern Type", "pattern_type"),
                ("Pattern Name", "pattern_name"),
                ("Observations", "observation_count"),
                ("Confidence", "confidence_score"),
                ("Source Episodes", "source_episodes_json"),
                ("Embedding Text", "embedding_text"),
            ],
        },
        "st_social": {
            "table": "st_social",
            "pk": "relationship_id",
            "fields": [
                "relationship_id",
                "actor_a_id",
                "actor_b_id",
                "relationship_type",
                "relationship_subtype",
                "relationship_label",
                "relationship_strength",
                "intimacy_level",
                "interaction_count",
                "avg_sentiment",
                "first_interaction_at",
                "last_interaction_at",
                "embedding_text",
                "confidence_score",
                "created_at",
            ],
            "display_order": [
                ("Relationship", "relationship_label"),
                ("Type", "relationship_type"),
                ("Subtype", "relationship_subtype"),
                ("Actor A", "actor_a_id"),
                ("Actor B", "actor_b_id"),
                ("Strength", "relationship_strength"),
                ("Intimacy", "intimacy_level"),
                ("Interactions", "interaction_count"),
                ("Avg Sentiment", "avg_sentiment"),
                ("Confidence", "confidence_score"),
                ("Embedding Text", "embedding_text"),
            ],
        },
        "st_prospective": {
            "table": "st_prospective",
            "pk": "intention_id",
            "fields": [
                "intention_id",
                "intention_type",
                "intention_description",
                "target_date",
                "target_context",
                "status",
                "inference_confidence",
                "inferred_from_json",
                "embedding_text",
                "confidence_score",
                "created_at",
            ],
            "display_order": [
                ("Type", "intention_type"),
                ("Description", "intention_description"),
                ("Target Date", "target_date"),
                ("Context", "target_context"),
                ("Status", "status"),
                ("Inference Confidence", "inference_confidence"),
                ("Inferred From", "inferred_from_json"),
                ("Confidence", "confidence_score"),
                ("Embedding Text", "embedding_text"),
            ],
        },
        "st_kg_dom": {
            "table": "st_kg_dom",
            "pk": "entity_id",
            "fields": [
                "entity_id",
                "entity_type",
                "entity_subtype",
                "canonical_name",
                "aliases_json",
                "attributes_json",
                "observation_count",
                "source_episodes_json",
                "milestones_json",
                "embedding_text",
                "confidence_score",
                "created_at",
            ],
            "display_order": [
                ("Entity Type", "entity_type"),
                ("Subtype", "entity_subtype"),
                ("Canonical Name", "canonical_name"),
                ("Aliases", "aliases_json"),
                ("Attributes", "attributes_json"),
                ("Observations", "observation_count"),
                ("Source Episodes", "source_episodes_json"),
                ("Milestones", "milestones_json"),
                ("Confidence", "confidence_score"),
                ("Embedding Text", "embedding_text"),
            ],
        },
        "st_procedural": {
            "table": "st_procedural",
            "pk": "routine_id",
            "fields": [
                "routine_id",
                "routine_name",
                "action_sequence_json",
                "regularity_score",
                "day_pattern",
                "frequency",
                "source_episodes_json",
                "embedding_text",
                "confidence_score",
                "created_at",
            ],
            "display_order": [
                ("Routine Name", "routine_name"),
                ("Actions", "action_sequence_json"),
                ("Regularity", "regularity_score"),
                ("Day Pattern", "day_pattern"),
                ("Frequency", "frequency"),
                ("Source Episodes", "source_episodes_json"),
                ("Confidence", "confidence_score"),
                ("Embedding Text", "embedding_text"),
            ],
        },
    }

    config = layer_configs.get(layer)
    if not config:
        return {"error": f"Unknown layer: {layer}"}, []

    try:
        fields_str = ", ".join(config["fields"])
        query = f"SELECT {fields_str} FROM {config['table']} WHERE {config['pk']} = $1"
        row = await conn.fetchrow(query, record_id)

        if row:
            return dict(row), config.get("display_order", [])
        return {"error": "Record not found"}, []
    except Exception as e:
        return {"error": str(e)}, []


def build_context_envelope(result, query: str) -> dict:
    """Build a structured context envelope for LLM consumption."""

    envelope = {
        "query": query,
        "search_summary": {
            "total_results": len(result.direct_results),
            "expanded_entities": len(result.expanded_entities),
            "related_records": (
                result.related_context.total_records if result.related_context else 0
            ),
            "timing_ms": result.timing_ms,
        },
        "layer_distribution": {},
        "top_results": [],
    }

    # Count by layer
    for r in result.direct_results:
        envelope["layer_distribution"][r.layer] = envelope["layer_distribution"].get(r.layer, 0) + 1

    # Add top results summary
    for r in result.direct_results[:5]:
        envelope["top_results"].append(
            {
                "layer": r.layer,
                "record_id": r.record_id,
                "score": round(r.score, 4),
                "tenant_id": r.tenant_id,
                "space_id": r.space_id,
            }
        )

    return envelope


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test recall module against live data")
    parser.add_argument(
        "--build-index", action="store_true", help="Build FAISS index from database vectors"
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        default=None,
        help="Custom query to test (default: 'What did Mom do?')",
    )
    parser.add_argument(
        "--top-k", "-k", type=int, default=5, help="Number of results to show (default: 5)"
    )
    args = parser.parse_args()

    asyncio.run(
        test_recall(build_index=args.build_index, custom_query=args.query, top_k=args.top_k)
    )
