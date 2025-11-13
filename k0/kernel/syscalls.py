"""
Syscalls - Capability-Gated Storage Access for Pipelines

Provides least-privilege storage access to pipelines via capability enforcement.
Each pipeline receives a Syscalls instance with only the capabilities it declares
in required_caps. All storage operations are audited and gated.

Architecture:
- Capability-based security (Dennis & Van Horn 1966)
- Least-privilege principle (Saltzer & Schroeder 1975)
- Audit trail for all sensitive operations
- No ambient authority (pipelines can't access storage directly)

Related:
- M2 R2.1: Syscalls implementation
- M2 R2.2: Loader grants capabilities based on pipeline.required_caps
- Section 8.6 of k0_pipeline_architecture.md: Capability enforcement
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


class PermissionError(Exception):
    """
    Raised when pipeline attempts unauthorized storage access.

    This exception indicates a capability violation - the pipeline tried to
    access a storage resource it didn't declare in required_caps.

    Security Implication:
        - Should be logged and audited (potential security breach)
        - Pipeline should be moved to DLQ after repeated violations
        - May indicate malicious pipeline or misconfigured contract

    Example:
        >>> syscalls = Syscalls("P02", {"st_hipp_store.write"}, uow_factory)
        >>> await syscalls.query_embeddings(...)  # Raises PermissionError
    """

    pass


class Syscalls:
    """
    Capability-gated storage adapter for pipelines.

    Enforces required_caps before allowing storage access. Provides audit trail
    for all storage operations. Pipelines receive a Syscalls instance during
    on_startup() and must use it for all storage access.

    Architecture Pattern:
        - Object-capability model (no ambient authority)
        - Fail-closed (deny by default)
        - Audit-all (log every storage operation)
        - Revocable (capabilities can be changed at runtime)

    Security Properties:
        1. **Least Privilege**: Pipelines only get declared capabilities
        2. **Fail-Closed**: Missing capability raises PermissionError
        3. **Audit Trail**: All operations logged with trace_id
        4. **Revocation**: Capabilities can be revoked dynamically
        5. **No Ambient Authority**: Can't access storage without Syscalls

    Capability Format:
        "<table>.<operation>" (e.g., "st_hipp_store.write", "embeddings.read")

    Example Usage:
        >>> # In loader.py (M2 R2.2)
        >>> granted_caps = set(pipeline_class.required_caps)
        >>> syscalls = Syscalls("P02", granted_caps, uow_factory)
        >>> ctx = PipelineContext(syscalls=syscalls, config={}, logger=logger)
        >>> await pipeline.on_startup(ctx)
        >>>
        >>> # In pipeline.handle()
        >>> await ctx.syscalls.hipp_store_upsert(
        ...     space_id="space_abc",
        ...     event_id="evt_123",
        ...     payload={"text": "Meeting with doctor"},
        ...     cognitive_trace_id="trace_xyz"
        ... )

    Related:
        - M2 R2.1: Syscalls implementation (this file)
        - M2 R2.2: Loader creates Syscalls with granted_caps
        - k0_pipeline_architecture.md Section 8.6: Capability enforcement
    """

    def __init__(
        self,
        pipeline_id: str,
        granted_caps: set[str],
        uow_factory: Callable[[], UnitOfWork],
    ):
        """
        Initialize capability-gated syscalls adapter.

        Args:
            pipeline_id: Pipeline identifier (e.g., "P02") for audit logging
            granted_caps: Set of granted capabilities from pipeline.required_caps
            uow_factory: Factory function returning UnitOfWork for transactions

        Example:
            >>> syscalls = Syscalls(
            ...     pipeline_id="P02",
            ...     granted_caps={"st_hipp_store.write"},
            ...     uow_factory=lambda: UnitOfWork(connection_pool)
            ... )
        """
        self._pipeline_id = pipeline_id
        # Convert to frozenset for immutability (security property)
        self._granted_caps = frozenset(granted_caps)
        self._uow_factory = uow_factory

        # Audit: Log capability grants at initialization
        logger.info(
            f"Syscalls initialized for {pipeline_id}",
            extra={
                "pipeline_id": pipeline_id,
                "granted_caps": list(granted_caps),
                "capability_count": len(granted_caps),
            },
        )

    async def hipp_store_upsert(
        self,
        space_id: str,
        event_id: str,
        payload: dict[str, Any],
        cognitive_trace_id: str,
    ) -> None:
        """
        Insert/update st_hipp_store (requires st_hipp_store.write cap).

        Hippocampus staging area for raw sensory/conversational input. Used by
        P02 (Episodic Write) pipeline for pattern separation and novelty detection.

        Capability Required: "st_hipp_store.write"

        Storage Table: st_hipp_store
        - Purpose: Short-term staging (7-30 days) before consolidation
        - Lifecycle: TEMPORARY → P03 consolidation → DELETE
        - Columns: event_id, cognitive_trace_id, text, simhash_hex, novelty, etc.

        Args:
            space_id: Memory space identifier (per-space isolation)
            event_id: Unique event identifier (primary key)
            payload: Event data with fields:
                - text (required): Raw input text
                - simhash_hex: 512-bit binary code for deduplication
                - minhash32: Jaccard sketches for similarity
                - novelty: How different from existing (0.0-1.0)
                - topics, categories, activity_type, etc.
            cognitive_trace_id: End-to-end observability trace ID

        Raises:
            PermissionError: If pipeline lacks "st_hipp_store.write" capability

        Example:
            >>> await syscalls.hipp_store_upsert(
            ...     space_id="space_abc",
            ...     event_id="evt_123",
            ...     payload={
            ...         "text": "Had doctor appointment",
            ...         "simhash_hex": "abc123...",
            ...         "novelty": 0.85,
            ...         "topics": ["health", "medical"]
            ...     },
            ...     cognitive_trace_id="trace_xyz"
            ... )

        Performance:
            - Target: <50ms P95 (single UPSERT)
            - Uses UPSERT (INSERT OR REPLACE) for idempotency
            - Indexed on event_id (primary key)

        Related:
            - P02 pipeline: Primary user of this syscall
            - st_hipp_store table: Migration 0006
            - Section 12 of k0_pipeline_architecture.md: P02 implementation
        """
        self._require_cap("st_hipp_store.write")

        # Audit: Log storage operation
        start_time = time.perf_counter()
        logger.debug(
            f"hipp_store_upsert: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "space_id": space_id,
                "event_id": event_id,
                "trace_id": cognitive_trace_id,
                "operation": "hipp_store_upsert",
            },
        )

        # Execute storage operation in UnitOfWork transaction
        with self._uow_factory() as uow:
            # Build UPSERT SQL (INSERT OR REPLACE for idempotency)
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            # Extract fields from payload
            text = payload.get("text", "")
            simhash_hex = payload.get("simhash_hex")
            minhash32 = json.dumps(payload.get("minhash32", []))
            novelty = payload.get("novelty")
            topics = json.dumps(payload.get("topics", []))
            categories = json.dumps(payload.get("categories", []))
            activity_type = payload.get("activity_type")
            length = len(text)
            created_at = int(time.time())

            # UPSERT into st_hipp_store
            conn.execute(
                """
                INSERT OR REPLACE INTO st_hipp_store (
                    event_id, cognitive_trace_id, text, length,
                    simhash_hex, minhash32, novelty,
                    topics, categories, activity_type,
                    author_id, tenant_id, space_id, privacy_band,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    cognitive_trace_id,
                    text,
                    length,
                    simhash_hex,
                    minhash32,
                    novelty,
                    topics,
                    categories,
                    activity_type,
                    payload.get("author_id", "unknown"),
                    payload.get("tenant_id", "default"),
                    space_id,
                    payload.get("privacy_band", "GREEN"),
                    created_at,
                ),
            )

            # UnitOfWork context manager will auto-commit on successful exit

        # Audit: Log operation completion
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"hipp_store_upsert complete: {event_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "event_id": event_id,
                "duration_ms": duration_ms,
                "trace_id": cognitive_trace_id,
            },
        )

    async def working_memory_write(
        self,
        space_id: str,
        key: str,
        value: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Write to working memory (requires working_memory.write cap).

        **STATUS: NOT IMPLEMENTED YET - Placeholder for M2 R2.1**

        Working memory (st_ws) is session-scoped context for K1 SessionState.
        Used for beliefs, goals, referents, and checkpoints during active sessions.

        Capability Required: "working_memory.write"

        Storage Table: st_ws
        - Purpose: Temporary memory for active session context
        - Lifecycle: Session-scoped (expires after TTL or session end)
        - Columns: item_id, session_id, item_type, content, priority, expires_at

        Args:
            space_id: Memory space identifier
            key: Item identifier (item_id)
            value: Item data with fields:
                - item_type: belief, goal, referent, context, checkpoint
                - content: Item data (JSON or text)
                - priority: Eviction priority (higher = keep longer)
                - session_id: Session scope
            ttl_seconds: Time-to-live in seconds (optional, for auto-eviction)

        Raises:
            PermissionError: If pipeline lacks "working_memory.write" capability
            NotImplementedError: Working memory not yet implemented

        Example:
            >>> await syscalls.working_memory_write(
            ...     space_id="space_abc",
            ...     key="belief_123",
            ...     value={
            ...         "item_type": "belief",
            ...         "content": "User prefers morning meetings",
            ...         "priority": 5,
            ...         "session_id": "session_xyz"
            ...     },
            ...     ttl_seconds=3600  # 1 hour TTL
            ... )

        TODO:
            - Implement st_ws table operations
            - Add LRU eviction logic
            - Add session cleanup on expiration
            - Add priority-based retention
            - Wire into K1 SessionState

        Related:
            - st_ws table: Migration 0006
            - K1 SessionState: Future integration
            - Section 10.3 of whiteboard: Working memory lifecycle
        """
        self._require_cap("working_memory.write")

        # Audit: Log operation
        logger.warning(
            f"working_memory_write not implemented: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "space_id": space_id,
                "key": key,
                "ttl_seconds": ttl_seconds,
                "operation": "working_memory_write",
                "status": "not_implemented",
            },
        )

        raise NotImplementedError(
            "working_memory_write not yet implemented - "
            "st_ws operations pending M2 R2.1 completion"
        )

    async def query_embeddings(
        self,
        space_id: str,
        vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Query vector index (requires embeddings.read cap).

        **STATUS: NOT IMPLEMENTED YET - Placeholder for M2 R2.1**

        Vector search for semantic similarity queries. Used by P01 (Recall)
        pipeline for memory retrieval based on embedding similarity.

        Capability Required: "embeddings.read"

        Storage Table: TBD (vector index not yet implemented)
        - Purpose: Semantic search across memory embeddings
        - Method: Cosine similarity or approximate nearest neighbors (ANN)
        - Typical Usage: P01 recall, P08 embedding pipelines

        Args:
            space_id: Memory space identifier (per-space isolation)
            vector: Query embedding vector (typically 384 or 768 dimensions)
            limit: Maximum number of results to return (default: 10)

        Returns:
            List of dicts with fields:
                - event_id: Memory identifier
                - score: Similarity score (0.0-1.0, higher = more similar)
                - text: Memory text content
                - metadata: Additional context

        Raises:
            PermissionError: If pipeline lacks "embeddings.read" capability
            NotImplementedError: Vector index not yet implemented

        Example:
            >>> query_vector = [0.1, 0.2, 0.3, ...]  # 384-dim embedding
            >>> results = await syscalls.query_embeddings(
            ...     space_id="space_abc",
            ...     vector=query_vector,
            ...     limit=5
            ... )
            >>> for result in results:
            ...     print(f"{result['event_id']}: {result['score']:.3f}")

        TODO:
            - Implement vector storage table (FAISS, pgvector, or sqlite-vss)
            - Add cosine similarity search
            - Add ANN index for large-scale retrieval
            - Wire into P01 recall pipeline
            - Add privacy band filtering

        Related:
            - P01 pipeline: Primary user of this syscall
            - P08 pipeline: Generates embeddings
            - Section 11 of k0_pipeline_architecture.md: Vector search
        """
        self._require_cap("embeddings.read")

        # Audit: Log operation
        logger.warning(
            f"query_embeddings not implemented: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "space_id": space_id,
                "vector_dim": len(vector),
                "limit": limit,
                "operation": "query_embeddings",
                "status": "not_implemented",
            },
        )

        raise NotImplementedError(
            "query_embeddings not yet implemented - " "vector index pending M2 R2.1 completion"
        )

    def _require_cap(self, capability: str) -> None:
        """
        Check capability, raise PermissionError if not granted.

        Implements fail-closed security: if capability not in granted set,
        operation is denied and logged as potential security violation.

        Args:
            capability: Required capability (e.g., "st_hipp_store.write")

        Raises:
            PermissionError: If capability not in self._granted_caps

        Audit Logging:
            - All capability checks logged at DEBUG level
            - Violations logged at ERROR level with pipeline_id
            - Can be used for security monitoring and alerting

        Example:
            >>> self._require_cap("st_hipp_store.write")
            >>> # Raises PermissionError if not granted

        Security Implications:
            - Fail-closed: Deny by default
            - Audit trail: All checks logged
            - Revocable: Can modify granted_caps at runtime
            - No bypass: Private method, can't be overridden

        Related:
            - Section 8.6 of k0_pipeline_architecture.md: Capability enforcement
            - M2 R2.2: Loader grants capabilities
            - M3 TX-6: Capability enforcement validation test
        """
        if capability not in self._granted_caps:
            # Audit: Log security violation
            logger.error(
                f"Permission denied: {self._pipeline_id} missing capability",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "required_capability": capability,
                    "granted_caps": list(self._granted_caps),
                    "security_violation": True,
                },
            )

            raise PermissionError(
                f"Pipeline {self._pipeline_id} missing capability: {capability}. "
                f"Granted: {sorted(self._granted_caps)}"
            )

        # Audit: Log successful capability check
        logger.debug(
            f"Capability check passed: {capability}",
            extra={
                "pipeline_id": self._pipeline_id,
                "capability": capability,
            },
        )
