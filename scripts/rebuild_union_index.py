"""
Rebuild FAISS Union Index

This script manually triggers a rebuild of the FAISS union index which is required
for semantic_similarity edge enrichment in P03 consolidation.

The union index combines embedding vectors from all 6 truth layers:
- st_epi (episodic)
- st_sem (semantic)
- st_procedural
- st_social
- st_prospective
- st_kg_dom (knowledge graph domains/entities)

This should be run once after initial deployment or when vectors are added to truth layers.
"""

import asyncio
import logging
import os
import sys

# When running in container, k0 is already in path
# No need to modify sys.path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Rebuild the FAISS union index."""
    try:
        from k0.kernel.di_container import get_uow_factory
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        logger.info("Starting FAISS union index rebuild...")

        # Get database connection
        uow_factory = get_uow_factory()
        async with uow_factory() as uow:
            conn = uow.session.connection()

            # Create index manager
            index_dir = os.environ.get("FAISS_UNION_INDEX_DIR", "/data/faiss_union")
            logger.info(f"Index directory: {index_dir}")

            manager = UnionIndexManager(index_dir)

            # Build and save index
            logger.info("Building index from truth layers...")
            searcher = await manager.build_and_save(conn)

            logger.info("✅ FAISS union index rebuild complete!")
            logger.info(f"Total vectors indexed: {searcher.total_vectors}")
            logger.info(f"Layer counts: {searcher.layer_counts}")

            # Test a search
            if searcher.total_vectors > 0:
                import numpy as np

                test_vector = np.random.random(768).astype(np.float32)
                results = searcher.search(test_vector, k=5)
                logger.info(f"Test search returned {len(results)} results")
                for i, r in enumerate(results[:3], 1):
                    logger.info(f"  {i}. {r.layer}:{r.record_id} (score={r.score:.3f})")

            return searcher.total_vectors

    except Exception as e:
        logger.error(f"Failed to rebuild union index: {e}", exc_info=True)
        return None


if __name__ == "__main__":
    result = asyncio.run(main())
    if result is None:
        sys.exit(1)
    sys.exit(0)
