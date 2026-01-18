"""
UnionIndexManager - GAP-001 Milestone 4 (Issue 4.4)

Manages FAISS union index lifecycle:
- Build from database
- Persist to disk
- Load from disk
- Scheduled rebuild

GAP Reference: GAP_001 Section 7 (Batch rebuild every 6 hours)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from .union_index_builder import UnionIndexBuilder
from .union_index_metadata import UnionIndexMetadata
from .union_index_searcher import UnionIndexSearcher

logger = logging.getLogger(__name__)


# Singleton instance for shared access
_manager_instance: Optional[UnionIndexManager] = None


class UnionIndexManager:
    """
    Manages FAISS union index lifecycle.

    Handles building, persisting, and loading the union index.
    Supports scheduled rebuilds and provides a singleton searcher instance.

    The index is persisted to disk as two files:
    - union_index.faiss: The FAISS index itself
    - union_index_metadata.json: Layer/record mapping metadata

    Usage:
        manager = UnionIndexManager("/data/faiss_union")

        # Build and save
        async with connection_scope() as conn:
            searcher = await manager.build_and_save(conn)

        # Or load existing
        searcher = manager.load()

        # Search
        results = searcher.search(query_vector, k=10)
    """

    INDEX_FILENAME = "union_index.faiss"
    METADATA_FILENAME = "union_index_metadata.json"
    DEFAULT_REBUILD_HOURS = 6

    def __init__(
        self,
        index_dir: str,
        rebuild_interval_hours: int = DEFAULT_REBUILD_HOURS,
    ):
        """
        Initialize manager.

        Args:
            index_dir: Directory to store index files
            rebuild_interval_hours: Rebuild interval (default 6 hours)
        """
        self.index_dir = Path(index_dir)
        self.rebuild_interval_ms = rebuild_interval_hours * 60 * 60 * 1000
        self._index: Optional[Any] = None
        self._metadata: Optional[UnionIndexMetadata] = None
        self._searcher: Optional[UnionIndexSearcher] = None
        self._builder = UnionIndexBuilder()

    @property
    def is_loaded(self) -> bool:
        """Check if index is loaded in memory."""
        return self._index is not None and self._metadata is not None

    @property
    def needs_rebuild(self) -> bool:
        """
        Check if index needs rebuild based on age.

        Returns True if:
        - No metadata exists (never built)
        - Index is older than rebuild_interval_ms
        """
        if not self._metadata:
            # Try to load metadata to check age
            metadata_path = self.index_dir / self.METADATA_FILENAME
            if metadata_path.exists():
                try:
                    self._metadata = UnionIndexMetadata.from_json(metadata_path.read_text())
                except Exception:
                    return True
            else:
                return True

        if not self._metadata:
            return True

        age_ms = int(time.time() * 1000) - self._metadata.build_timestamp
        return age_ms > self.rebuild_interval_ms

    @property
    def index_age_hours(self) -> float:
        """Get age of current index in hours."""
        if not self._metadata:
            return float("inf")
        age_ms = int(time.time() * 1000) - self._metadata.build_timestamp
        return age_ms / (1000 * 60 * 60)

    async def build_and_save(
        self,
        conn: Any,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
    ) -> UnionIndexSearcher:
        """
        Build index from database and persist to disk.

        Args:
            conn: asyncpg connection
            tenant_id: Optional filter
            space_id: Optional filter

        Returns:
            UnionIndexSearcher ready for queries
        """

        logger.info("UnionIndexManager: building FAISS union index...")
        start = time.time()

        # Build index
        self._index, self._metadata = await self._builder.build(conn, tenant_id, space_id)

        # Persist to disk
        self._save_to_disk()

        duration_ms = int((time.time() - start) * 1000)
        logger.info(
            "UnionIndexManager: index built and saved",
            extra={
                "total_vectors": self._metadata.total_vectors,
                "layer_counts": self._metadata.layer_counts,
                "duration_ms": duration_ms,
                "index_path": str(self.index_dir),
            },
        )

        self._searcher = UnionIndexSearcher(self._index, self._metadata)
        return self._searcher

    def _save_to_disk(self) -> None:
        """Save index and metadata to disk."""
        import faiss

        self.index_dir.mkdir(parents=True, exist_ok=True)

        index_path = self.index_dir / self.INDEX_FILENAME
        metadata_path = self.index_dir / self.METADATA_FILENAME

        # Save FAISS index
        faiss.write_index(self._index, str(index_path))

        # Save metadata JSON
        metadata_path.write_text(self._metadata.to_json())

        logger.debug(
            "UnionIndexManager: saved to disk",
            extra={
                "index_path": str(index_path),
                "metadata_path": str(metadata_path),
            },
        )

    def load(self) -> Optional[UnionIndexSearcher]:
        """
        Load index from disk.

        Returns:
            UnionIndexSearcher if loaded, None if files don't exist
        """
        import faiss

        index_path = self.index_dir / self.INDEX_FILENAME
        metadata_path = self.index_dir / self.METADATA_FILENAME

        if not index_path.exists() or not metadata_path.exists():
            logger.warning(
                "UnionIndexManager: no index found on disk",
                extra={"index_dir": str(self.index_dir)},
            )
            return None

        try:
            self._index = faiss.read_index(str(index_path))
            self._metadata = UnionIndexMetadata.from_json(metadata_path.read_text())
            self._searcher = UnionIndexSearcher(self._index, self._metadata)

            logger.info(
                "UnionIndexManager: index loaded from disk",
                extra={
                    "total_vectors": self._metadata.total_vectors,
                    "build_timestamp": self._metadata.build_timestamp,
                    "age_hours": self.index_age_hours,
                },
            )

            return self._searcher

        except Exception as e:
            logger.error(
                "UnionIndexManager: failed to load index",
                extra={"error": str(e), "index_dir": str(self.index_dir)},
            )
            return None

    def get_searcher(self) -> Optional[UnionIndexSearcher]:
        """
        Get searcher instance (load from disk if needed).

        Returns:
            UnionIndexSearcher if available, None otherwise
        """
        if self._searcher:
            return self._searcher

        return self.load()

    async def rebuild_if_needed(
        self,
        conn: Any,
        force: bool = False,
    ) -> Optional[UnionIndexSearcher]:
        """
        Rebuild index if needed (based on age or force flag).

        Args:
            conn: asyncpg connection
            force: Force rebuild regardless of age

        Returns:
            UnionIndexSearcher if rebuilt, None if skipped
        """
        if not force and not self.needs_rebuild:
            logger.info(
                "UnionIndexManager: index is fresh, skipping rebuild",
                extra={"age_hours": self.index_age_hours},
            )
            return None

        return await self.build_and_save(conn)

    def delete_index(self) -> bool:
        """
        Delete index files from disk.

        Returns:
            True if deleted, False if files didn't exist
        """
        index_path = self.index_dir / self.INDEX_FILENAME
        metadata_path = self.index_dir / self.METADATA_FILENAME

        deleted = False

        if index_path.exists():
            index_path.unlink()
            deleted = True

        if metadata_path.exists():
            metadata_path.unlink()
            deleted = True

        self._index = None
        self._metadata = None
        self._searcher = None

        if deleted:
            logger.info("UnionIndexManager: deleted index files")

        return deleted

    def get_stats(self) -> dict:
        """
        Get manager statistics.

        Returns:
            Dictionary with manager/index stats
        """
        stats = {
            "is_loaded": self.is_loaded,
            "needs_rebuild": self.needs_rebuild,
            "index_dir": str(self.index_dir),
            "rebuild_interval_hours": self.rebuild_interval_ms / (1000 * 60 * 60),
        }

        if self._metadata:
            stats.update(
                {
                    "total_vectors": self._metadata.total_vectors,
                    "layer_counts": self._metadata.layer_counts,
                    "build_timestamp": self._metadata.build_timestamp,
                    "model_version": self._metadata.model_version,
                    "age_hours": self.index_age_hours,
                }
            )

        return stats


def get_manager(
    index_dir: Optional[str] = None,
    rebuild_interval_hours: int = 6,
) -> UnionIndexManager:
    """
    Get singleton UnionIndexManager instance.

    Args:
        index_dir: Directory for index files (default: /data/faiss_union)
        rebuild_interval_hours: Rebuild interval

    Returns:
        Shared UnionIndexManager instance
    """
    global _manager_instance

    if _manager_instance is None:
        _index_dir = index_dir or os.environ.get("FAISS_UNION_INDEX_DIR", "/data/faiss_union")
        _manager_instance = UnionIndexManager(_index_dir, rebuild_interval_hours)

    return _manager_instance


def reset_manager() -> None:
    """Reset singleton manager (for testing)."""
    global _manager_instance
    _manager_instance = None
