"""
Enhanced Query Port - Reads from backend storage

This extends K0QueryClient to query what writers stored via MockCommandPort.

Flow:
1. Writers write via WriterCommandPort → batched → MockCommandPort
2. MockCommandPort stores to BackendStorage
3. Other agents query via this QueryPort (reads from BackendStorage)

This completes the loop: Writers → Storage → Readers
"""

from typing import Any, Dict, List, Optional

import structlog

from .mock_command_port import BackendStorage, StoredDelta

logger = structlog.get_logger(__name__)


class QueryPort:
    """
    Query Port - Queries stored deltas from backend storage.

    Provides backend queries to access what writers stored.
    """

    def __init__(self, backend: BackendStorage):
        """
        Initialize query port.

        Args:
            backend: BackendStorage to query
        """
        self.backend = backend
        self.queries_executed = 0
        self.total_results_returned = 0

    async def query_deltas(
        self,
        delta_type: Optional[str] = None,
        writer_type: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 100,
        offset: int = 0,
    ) -> List[StoredDelta]:
        """
        Query deltas from backend storage.

        Args:
            delta_type: Filter by delta type (episodic, prospective, learning, semantic)
            writer_type: Filter by writer type (memory, learning, semantic)
            min_confidence: Minimum confidence threshold
            limit: Max results to return
            offset: Offset for pagination

        Returns:
            List of StoredDeltas matching filters
        """
        try:
            self.queries_executed += 1

            results = await self.backend.query_deltas(
                delta_type=delta_type,
                writer_type=writer_type,
                min_confidence=min_confidence,
                limit=limit,
                offset=offset,
            )

            self.total_results_returned += len(results)

            logger.debug(
                "query_deltas_executed",
                delta_type=delta_type,
                writer_type=writer_type,
                results_count=len(results),
            )

            return results

        except Exception as e:
            logger.error("query_deltas_error", error=str(e))
            return []

    async def query_episodic_memories(
        self,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query episodic memories (P02).

        Args:
            min_confidence: Minimum confidence threshold
            limit: Max results

        Returns:
            List of episodic memory dicts
        """
        deltas = await self.query_deltas(
            delta_type="episodic",
            writer_type="memory",
            min_confidence=min_confidence,
            limit=limit,
        )

        return [{"delta": d.to_dict(), "memory": d.content} for d in deltas]

    async def query_prospective_memories(
        self,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query prospective memories (P05).

        Args:
            min_confidence: Minimum confidence threshold
            limit: Max results

        Returns:
            List of prospective memory dicts
        """
        deltas = await self.query_deltas(
            delta_type="prospective",
            writer_type="memory",
            min_confidence=min_confidence,
            limit=limit,
        )

        return [{"delta": d.to_dict(), "memory": d.content} for d in deltas]

    async def query_learning_signals(
        self,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query learning signals (P06).

        Args:
            min_confidence: Minimum confidence threshold
            limit: Max results

        Returns:
            List of learning signal dicts
        """
        deltas = await self.query_deltas(
            delta_type="learning",
            writer_type="learning",
            min_confidence=min_confidence,
            limit=limit,
        )

        return [{"delta": d.to_dict(), "signal": d.content} for d in deltas]

    async def query_semantic_extractions(
        self,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query semantic extractions (User KG updates).

        Args:
            min_confidence: Minimum confidence threshold
            limit: Max results

        Returns:
            List of semantic extraction dicts
        """
        deltas = await self.query_deltas(
            delta_type="semantic",
            writer_type="semantic",
            min_confidence=min_confidence,
            limit=limit,
        )

        return [
            {
                "delta": d.to_dict(),
                "entities": d.content.get("entities", []),
                "relationships": d.content.get("relationships", []),
                "topics": d.content.get("topics", []),
            }
            for d in deltas
        ]

    async def query_by_trace_id(self, trace_id: str) -> List[StoredDelta]:
        """
        Query all deltas for a specific trace_id.

        Useful for tracing an operation through all writers.

        Args:
            trace_id: Trace ID to search

        Returns:
            All deltas with this trace_id
        """
        try:
            all_deltas = []

            # Search all delta types
            for delta_type in ["episodic", "prospective", "learning", "semantic"]:
                deltas = await self.query_deltas(delta_type=delta_type, limit=10000)

                # Filter by trace_id
                matching = [d for d in deltas if d.trace_id == trace_id]
                all_deltas.extend(matching)

            return all_deltas

        except Exception as e:
            logger.error("query_by_trace_id_error", trace_id=trace_id, error=str(e))
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get query port statistics."""
        return {
            "queries_executed": self.queries_executed,
            "total_results_returned": self.total_results_returned,
            "avg_results_per_query": (self.total_results_returned / max(self.queries_executed, 1)),
            "backend_stats": self.backend.get_stats(),
        }
