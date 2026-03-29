#!/usr/bin/env python3
"""Test multiple recall queries with full context."""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set FAISS index directory
os.environ["FAISS_UNION_INDEX_DIR"] = str(Path(__file__).parent.parent / "data" / "faiss_union")


async def test_queries():
    """Test multiple recall queries with context."""
    conn = await asyncpg.connect(
        host="localhost",
        port=6432,
        user="k0",
        password="k0pass",
        database="k0_kernel",
        statement_cache_size=0,
    )

    from k0.modules.embedding.union_index_manager import get_manager
    from k0.runtime.ultrabert_adapter import get_embedding

    manager = get_manager()
    searcher = manager.get_searcher()

    if not searcher:
        print("No searcher available - run test_recall_direct.py --build-index first")
        await conn.close()
        return

    queries = [
        "Where is Emma?",
        "work meetings with team",
        "doctor appointment health",
        "birthday party celebration",
        "travel to San Francisco",
        "financial planning retirement",
    ]

    for query in queries:
        emb = get_embedding(query)
        vec = np.array(emb, dtype=np.float32)
        results = searcher.search(vec, k=3)

        print(f'\n{"=" * 70}')
        print(f'Query: "{query}"')
        print("=" * 70)

        for i, r in enumerate(results):
            # Fetch content based on layer
            layer_queries = {
                "st_epi": ("st_epi", "episode_id"),
                "st_sem": ("st_sem", "pattern_id"),
                "st_social": ("st_social", "relationship_id"),
                "st_prospective": ("st_prospective", "intention_id"),
                "st_kg_dom": ("st_kg_dom", "entity_id"),
                "st_procedural": ("st_procedural", "routine_id"),
            }

            if r.layer in layer_queries:
                table, pk = layer_queries[r.layer]
                row = await conn.fetchrow(
                    f"SELECT embedding_text FROM {table} WHERE {pk} = $1", r.record_id
                )
                text = row["embedding_text"][:100] if row and row["embedding_text"] else "(no text)"
            else:
                text = "(unknown layer)"

            print(f"  [{i + 1}] {r.layer:15} score={r.score:.4f}")
            print(f"      Content: {text}...")

    await conn.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(test_queries())
