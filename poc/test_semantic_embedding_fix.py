#!/usr/bin/env python3
"""
Test that SemanticLayerWriter correctly generates embeddings for
LESSON/EMOTIONAL_TREND patterns that have event_ids in source_episodes_json.

This validates the fix: detecting event UUIDs vs episode IDs and calling
the appropriate coordinator method.

Usage:
    python poc/test_semantic_embedding_fix.py
"""

import asyncio
import json
import sys
from pathlib import Path

import asyncpg

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from k0.modules.consolidation.truth_writer.layers.semantic import SemanticLayerWriter
from k0.pipelines.p03.staged_writes import StagedWrite


async def test_embedding_fix():
    """Test that LESSON patterns get proper embeddings."""

    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="k0user",
        password="changeme",
        database="k0_kernel",
    )

    try:
        # 1. Get a sample event_id from st_hipp_events
        print("\n=== Finding test event ===")
        event_row = await conn.fetchrow(
            """
            SELECT event_id, text
            FROM st_hipp_events
            WHERE text IS NOT NULL AND text != ''
            LIMIT 1
            """
        )

        if not event_row:
            print("ERROR: No events found in st_hipp_events")
            return

        event_id = event_row["event_id"]
        event_text = event_row["text"][:100]
        print(f"  Event ID: {event_id}")
        print(f"  Text: {event_text}...")

        # 2. Create a test LESSON staged write (like IntentSignalAssembler does)
        print("\n=== Creating test LESSON write ===")

        import time

        now_ms = int(time.time() * 1000)
        pattern_id = f"test_lesson_{now_ms}"

        record_data = {
            "pattern_id": pattern_id,
            "tenant_id": "tenant-test",
            "space_id": "space-test",
            "pattern_type": "LESSON",
            "pattern_name": "Test lesson for embedding fix verification",
            "source_episodes_json": json.dumps([event_id]),  # EVENT UUID, not episode ID
            "source_episode_count": 1,
            "confidence_score": 0.8,
            "observation_count": 1,
            "last_observed_at": now_ms,
            "first_observed_at": now_ms,
            "is_canonical": True,
            "archival_status": "ACTIVE",
            "decay_factor": 1.0,
            "created_at": now_ms,
            "updated_at": now_ms,
            "valid_from": now_ms,
        }

        staged_write = StagedWrite.insert(
            layer="st_sem",
            record_id=pattern_id,
            data=record_data,
            phase="R5",
        )

        print(f"  Pattern ID: {pattern_id}")
        print(f"  source_episodes_json: {record_data['source_episodes_json']}")

        # 3. Write using SemanticLayerWriter
        print("\n=== Writing via SemanticLayerWriter ===")

        writer = SemanticLayerWriter()

        # Create UoW-like wrapper (minimal for test)
        class TestUoW:
            def __init__(self, conn):
                self.connection = conn

        uow = TestUoW(conn)

        result = await writer.write([staged_write], uow)  # type: ignore

        print(f"  Writes attempted: {result.writes_attempted}")
        print(f"  Writes succeeded: {result.writes_succeeded}")
        print(f"  Writes failed: {result.writes_failed}")
        if result.error_message:
            print(f"  Error: {result.error_message}")

        # 4. Check if embedding was generated
        print("\n=== Verifying embedding ===")

        row = await conn.fetchrow(
            """
            SELECT pattern_id, pattern_name,
                   source_texts_json,
                   embedding_text,
                   embedding_vector IS NOT NULL AS has_embedding,
                   embedding_model
            FROM st_sem
            WHERE pattern_id = $1
            """,
            pattern_id,
        )

        if not row:
            print("ERROR: Pattern not found in st_sem!")
            return

        print(f"  pattern_id: {row['pattern_id']}")
        print(
            f"  source_texts_json: {row['source_texts_json'][:100] if row['source_texts_json'] else 'NULL'}..."
        )
        print(
            f"  embedding_text: {row['embedding_text'][:100] if row['embedding_text'] else 'NULL'}..."
        )
        print(f"  has_embedding: {row['has_embedding']}")
        print(f"  embedding_model: {row['embedding_model']}")

        if row["has_embedding"] and row["source_texts_json"]:
            print("\n✅ SUCCESS: Embedding generated correctly from event texts!")
        else:
            print("\n❌ FAILURE: Embedding not generated or texts missing")

        # 5. Cleanup
        print("\n=== Cleanup ===")
        await conn.execute("DELETE FROM st_sem WHERE pattern_id = $1", pattern_id)
        print(f"  Deleted test pattern: {pattern_id}")

    finally:
        await conn.close()
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(test_embedding_fix())
