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

import asyncio
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
        >>> syscalls = Syscalls("P02", {"st_hipp_events.write"}, uow_factory)
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
        "<table>.<operation>" (e.g., "st_hipp_events.write", "embeddings.read")

    Example Usage:
        >>> # In loader.py (M2 R2.2)
        >>> granted_caps = set(pipeline_class.required_caps)
        >>> syscalls = Syscalls("P02", granted_caps, uow_factory)
        >>> ctx = PipelineContext(syscalls=syscalls, config={}, logger=logger)
        >>> await pipeline.on_startup(ctx)
        >>>
        >>> # In pipeline.handle()
        >>> row = {"event_id": "evt_123", "wal_pos": 42, "embedding_id": "emb_1", "policy_band": "GREEN", "cognitive_trace_id": "trace_xyz"}
        >>> await ctx.syscalls.hipp_events_upsert(**row)

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
            ...     granted_caps={"st_hipp_events.write"},
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
        Deprecated: legacy st_hipp_store staging write.

        The st_hipp_store table was deprecated (migration 0021) and dropped (migration 0022).
        The canonical staging/enriched event write path is st_hipp_events via hipp_events_upsert
        (requires "st_hipp_events.write").

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
            RuntimeError: Always, because st_hipp_store is no longer part of the active schema

        Example:
            >>> row = {"event_id": "evt_123", "wal_pos": 42, "embedding_id": "emb_1", "policy_band": "GREEN", "cognitive_trace_id": "trace_xyz"}
            >>> await syscalls.hipp_events_upsert(**row)

        Performance:
            - Target: <50ms P95 (single UPSERT)
            - Uses UPSERT (INSERT OR REPLACE) for idempotency
            - Indexed on event_id (primary key)

        Related:
            - hipp_events_upsert: canonical event upsert syscall
            - st_hipp_events table: Migration 0024
        """
        logger.error(
            "hipp_store_upsert called but st_hipp_store is deprecated",
            extra={
                "pipeline_id": self._pipeline_id,
                "space_id": space_id,
                "event_id": event_id,
                "trace_id": cognitive_trace_id,
                "operation": "hipp_store_upsert",
                "deprecated": True,
            },
        )
        raise RuntimeError(
            "hipp_store_upsert is deprecated because st_hipp_store was dropped (migrations 0021/0022). "
            "Use hipp_events_upsert (requires st_hipp_events.write)."
        )

    async def hipp_events_upsert(self, **row: Any) -> dict[str, Any]:
        """
        Insert/update st_hipp_events (requires st_hipp_events.write cap).

        Accepts complete row with all 70+ columns from M13 (builders.hipp_events_row).
        See migration 0024_p02_episodic_write_tables.sql for full schema.

        Capability Required: "st_hipp_events.write"

        Storage Table: st_hipp_events
        - Purpose: Enriched episodic memory events (post-pipeline processing)
        - Lifecycle: Permanent storage (no TTL)
        - Primary Key: event_id (unique across all spaces)
        - Indexes: 6 (tenant_time, space_time, simhash, embedding_id, band_time, cluster_id)

        Args:
            **row: Complete row dict from M13 with all st_hipp_events columns:
                - Identity & Trace (9): event_id, wal_pos, cognitive_trace_id, tenant_id, space_id, etc.
                - Integrity & Audit (6): envelope_sha256, sig_alg, sig_kid, idem_key, ingested_at, clock_skew_ms
                - Policy & Visibility (10): policy_decision, policy_band, owner_id, retention_policy_id, etc.
                - Actor & Device (6): actor_id, actor_role, device_id, device_kind, device_os, ingress_channel
                - Temporal (11): event_time_utc, write_time_utc, local_date, day_of_week, circadian_slot, etc.
                - Spatial & Place (5): location_name, location_type, geohash_6, geo_precision_external, etc.
                - Social & Relationships (8): participants_json, num_participants, has_partner_present, etc.
                - Semantic & Activity (10): text, text_normalized, char_count, activity_type, language, etc.
                - Hippocampus (8): simhash_hex, minhash32, novelty_score, episode_cluster_id, etc.
                - Embeddings & KG (4): embedding_id, embedding_status, entities_json, kg_triples_json
                - Affect & Salience (9): sentiment_score, affect_valence, affect_arousal, salience_score, etc.
                - Metadata (4): hippocampus_api_version, space_resolver_version, schema_uri, updated_at

        Returns:
            Dictionary with:
            - inserted: bool (True if inserted, False if duplicate skipped)
            - event_id: str
            - status: str ('INSERTED' or 'SKIPPED_DUPLICATE')

        Raises:
            PermissionError: If pipeline lacks "st_hipp_events.write" capability
            ValueError: If required fields missing or invalid

        Example:
            >>> row = {"event_id": "evt_123", "wal_pos": 42, ...}  # All 70+ columns from M13
            >>> result = await syscalls.hipp_events_upsert(**row)
            >>> result["inserted"]
            True

        Performance:
            - Target: <15ms P95 (single INSERT with 6 B-tree indexes)
            - Uses INSERT OR IGNORE for idempotency
            - Connection pooling via UnitOfWork

        Related:
            - M13 (builders.hipp_events_row): Assembles complete row
            - M16 (core.hipp_events_writer): Invokes this syscall
            - P02 pipeline: Orchestrates enrichment flow
            - Migration 0024: Defines st_hipp_events schema
        """
        self._require_cap("st_hipp_events.write")

        # Extract and validate required fields
        event_id = row.get("event_id")
        embedding_id = row.get("embedding_id")
        wal_pos = row.get("wal_pos")
        policy_band = row.get("policy_band")
        cognitive_trace_id = row.get("cognitive_trace_id")

        if not event_id:
            raise ValueError("event_id required for hipp_events_upsert")
        if not embedding_id:
            raise ValueError("embedding_id required for hipp_events_upsert")
        if wal_pos is None:
            raise ValueError("wal_pos required for hipp_events_upsert")
        if policy_band not in ("GREEN", "AMBER", "RED"):
            raise ValueError(f"Invalid policy_band: {policy_band}")

        # Audit: Log storage operation (only on errors or debug level)
        start_time = time.perf_counter()

        # Execute storage operation in UnitOfWork transaction
        async with self._uow_factory() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            # Use all columns from row (database will handle NULLs with DEFAULT constraints)
            columns = list(row.keys())
            placeholders = ", ".join(["?"] * len(columns))
            column_names = ", ".join(columns)
            values = tuple(row[k] for k in columns)

            try:
                # Use INSERT OR IGNORE for idempotency (faster than INSERT OR REPLACE)
                # event_id is PRIMARY KEY, so duplicates will be silently skipped
                loop = asyncio.get_running_loop()
                cursor = await loop.run_in_executor(
                    None,
                    lambda: conn.execute(
                        f"""
                        INSERT OR IGNORE INTO st_hipp_events ({column_names})
                        VALUES ({placeholders})
                        """,
                        values,
                    ),
                )

                inserted = cursor.rowcount > 0

                # UnitOfWork context manager will auto-commit on successful exit

                return {
                    "inserted": inserted,
                    "event_id": event_id,
                    "status": "INSERTED" if inserted else "SKIPPED_DUPLICATE",
                }

            except Exception as e:
                logger.error(
                    f"hipp_events_upsert failed: {event_id}",
                    exc_info=True,
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "event_id": event_id,
                        "error": str(e),
                        "trace_id": cognitive_trace_id,
                    },
                )
                raise

    async def pipeline_processed_upsert(
        self,
        pipeline_id: str,
        wal_pos: int,
        tenant_id: str,
        space_id: str,
        status: str,
        processed_at: int | None = None,
    ) -> dict[str, Any]:
        """
        Record pipeline processing completion (requires st_pipeline_processed.write cap).

        Idempotency tracking table for pipeline execution. Used by all P02 modules
        to prevent duplicate processing of same WAL position.

        Capability Required: "st_pipeline_processed.write"

        Storage Table: st_pipeline_processed
        - Purpose: Pipeline execution tracking for idempotency
        - Lifecycle: Permanent (audit trail)
        - Primary Key: (pipeline_id, tenant_id, space_id, wal_pos)
        - Index: (pipeline_id, space_id, processed_at)

        Args:
            pipeline_id: Pipeline identifier (e.g., "P02_WRITE")
            wal_pos: WAL position that was processed
            tenant_id: Tenant isolation boundary
            space_id: Memory space identifier
            status: Processing status ("OK", "ERROR", "SKIPPED")
            processed_at: Unix timestamp (defaults to current time)

        Returns:
            Dictionary with:
            - inserted: bool (True if inserted, False if duplicate skipped)
            - pipeline_id: str
            - wal_pos: int
            - status: str

        Raises:
            PermissionError: If pipeline lacks "st_pipeline_processed.write" capability
            ValueError: If required fields missing or invalid

        Example:
            >>> result = await syscalls.pipeline_processed_upsert(
            ...     pipeline_id="P02_WRITE",
            ...     wal_pos=42,
            ...     tenant_id="tenant_abc",
            ...     space_id="space_xyz",
            ...     status="OK"
            ... )
            >>> result["inserted"]
            True

        Performance:
            - Target: <10ms P95 (single INSERT with composite index)
            - Uses INSERT OR REPLACE for upsert semantics
            - Connection pooling via UnitOfWork

        Related:
            - M16 (core.hipp_events_writer): Records P02_WRITE completion
            - All P02 modules: Check this table for idempotency before processing
            - docs/pipelines/P02_data_schema.md: Schema definition (lines 511-569)
        """
        self._require_cap("st_pipeline_processed.write")

        # Validation
        if not pipeline_id:
            raise ValueError("pipeline_id required for pipeline_processed_upsert")
        if status not in ("OK", "ERROR", "SKIPPED"):
            raise ValueError(f"Invalid status: {status} (expected OK/ERROR/SKIPPED)")

        # Audit: Log storage operation
        start_time = time.perf_counter()
        logger.debug(
            f"pipeline_processed_upsert: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "target_pipeline": pipeline_id,
                "wal_pos": wal_pos,
                "space_id": space_id,
                "status": status,
                "operation": "pipeline_processed_upsert",
            },
        )

        # Execute storage operation in UnitOfWork transaction
        async with self._uow_factory() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            processed_at = processed_at or int(time.time())

            try:
                loop = asyncio.get_running_loop()
                cursor = await loop.run_in_executor(
                    None,
                    lambda: conn.execute(
                        """
                        INSERT OR REPLACE INTO st_pipeline_processed (
                            pipeline_id, space_id, wal_pos, processed_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            pipeline_id,
                            space_id,
                            wal_pos,
                            processed_at,
                        ),
                    ),
                )

                inserted = cursor.rowcount > 0

                # UnitOfWork context manager will auto-commit on successful exit

                # Audit: Log operation completion
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(
                    f"pipeline_processed_upsert complete: {pipeline_id}@{wal_pos}",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "target_pipeline": pipeline_id,
                        "wal_pos": wal_pos,
                        "inserted": inserted,
                        "duration_ms": duration_ms,
                    },
                )

                return {
                    "inserted": inserted,
                    "pipeline_id": pipeline_id,
                    "wal_pos": wal_pos,
                    "status": status,
                }

            except Exception as e:
                logger.error(
                    f"pipeline_processed_upsert failed: {pipeline_id}@{wal_pos}",
                    exc_info=True,
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "target_pipeline": pipeline_id,
                        "wal_pos": wal_pos,
                        "error": str(e),
                    },
                )
                raise

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

    async def relationships_query(
        self,
        actor_id: str,
        cognitive_trace_id: str | None = None,
    ) -> list[tuple[str, str]]:
        """
        Query st_relationships for actor's family relationships (requires st_relationships.read cap).

        Used by M07 (social.family_graph_resolve) to resolve family context for episodic
        memories. Returns all relationships where person_id = actor_id.

        Capability Required: "st_relationships.read"

        Storage Table: st_relationships
        - Purpose: Family graph cache (5 relationship types)
        - Lifecycle: Seeded in migration 0018/0024, TTL-based refresh
        - Columns: person_id, related_person_id, relationship_type

        Relationship Types:
        - SPOUSE_OF: Married/partner relationship (bidirectional)
        - PARENT_OF: Parent-child relationship (actor is parent)
        - CHILD_OF: Child-parent relationship (actor is child)
        - CARETAKER_OF: Guardian/caregiver relationship
        - SIBLING_OF: Brother/sister relationship

        Args:
            actor_id: Person identifier to lookup relationships for
            cognitive_trace_id: Optional trace ID for observability

        Returns:
            List of (related_person_id, relationship_type) tuples.
            Empty list if actor has no relationships.

        Raises:
            PermissionError: If pipeline lacks "st_relationships.read" capability

        Example:
            >>> relationships = await syscalls.relationships_query(
            ...     actor_id="person_prince_001",
            ...     cognitive_trace_id="trace_xyz"
            ... )
            >>> relationships
            [("person_jeel_001", "SPOUSE_OF"), ("person_sharvi_001", "PARENT_OF")]

        Performance:
            - Target: <5ms P95 (indexed query on person_id)
            - Uses idx_relationships_person index
            - Connection pooling via UnitOfWork

        Related:
            - M07 (social.family_graph_resolve): Primary user of this syscall
            - P02 pipeline: Stage 20 calls M07 for social context
            - Migration 0024: Table schema and seed data
            - ADR K008.1: Family Graph Resolver architecture
        """
        self._require_cap("st_relationships.read")

        # Audit: Log storage operation
        start_time = time.perf_counter()
        logger.debug(
            f"relationships_query: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "actor_id": actor_id,
                "cognitive_trace_id": cognitive_trace_id,
                "operation": "relationships_query",
            },
        )

        # Execute storage operation in UnitOfWork transaction
        async with self._uow_factory() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            # Query st_relationships for actor's relationships
            query = """
                SELECT related_person_id, relationship_type
                FROM st_relationships
                WHERE person_id = ?
            """

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: conn.execute(query, (actor_id,)).fetchall(),
            )

            # Convert rows to list of tuples
            relationships = [(row[0], row[1]) for row in result]

            # Audit: Log completion
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                f"relationships_query completed: {self._pipeline_id}",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "actor_id": actor_id,
                    "relationship_count": len(relationships),
                    "elapsed_ms": elapsed_ms,
                    "cognitive_trace_id": cognitive_trace_id,
                    "operation": "relationships_query",
                    "status": "success",
                },
            )

            return relationships

    async def embedding_enqueue(
        self,
        embedding_id: str,
        event_id: str,
        wal_pos: int,
        tenant_id: str,
        space_id: str,
        vector_kind: str = "memory.body.text",
        model_id: str = "embed-mini-001",
        priority: str = "NORMAL",
        cognitive_trace_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Enqueue embedding job to st_embedding_queue (requires st_embedding_queue.write cap).

        Used by M14 (builders.embedding_queue_write) to create background jobs for
        P08 vector generation pipeline. Decouples fast memory writes (P02) from
        slow vector computation (P08).

        Capability Required: "st_embedding_queue.write"

        Storage Table: st_embedding_queue
        - Purpose: Job queue for background vector embedding generation
        - Lifecycle: PENDING → IN_PROGRESS → READY (or FAILED)
        - Primary Key: embedding_id (unique, idempotent)
        - Indexes: (status, priority, created_at) for P08 claim queries

        Status Lifecycle (P08 updates):
        1. PENDING: Initial state (written by P02 via M14)
        2. IN_PROGRESS: Claimed by P08 worker
        3. READY: Vector computed and stored in st_embeddings
        4. FAILED_RETRYABLE: Computation failed, will retry
        5. FAILED_PERMANENT: Max retries exceeded (5 attempts)

        Args:
            embedding_id: Unique embedding identifier (UUID, idempotency key)
            event_id: Source event identifier (FK to st_hipp_events)
            wal_pos: WAL position for traceability
            tenant_id: Tenant isolation boundary
            space_id: Memory space identifier
            vector_kind: Type of embedding (default: "memory.body.text")
            model_id: Embedding model to use (default: "embed-mini-001")
            priority: Job priority (NORMAL, HIGH, LOW)
            cognitive_trace_id: Optional trace ID for observability

        Returns:
            Dictionary with:
            - inserted: bool (True if inserted, False if duplicate skipped)
            - embedding_id: str
            - status: str ('INSERTED' or 'SKIPPED_DUPLICATE')

        Raises:
            PermissionError: If pipeline lacks "st_embedding_queue.write" capability
            ValueError: If required fields missing or invalid

        Example:
            >>> result = await syscalls.embedding_enqueue(
            ...     embedding_id="emb_uuid_abc123",
            ...     event_id="evt_123",
            ...     wal_pos=1001,
            ...     tenant_id="tenant_abc",
            ...     space_id="space_xyz",
            ...     vector_kind="memory.body.text",
            ...     model_id="embed-mini-001",
            ...     priority="NORMAL"
            ... )
            >>> result["inserted"]
            True

        Performance:
            - Target: <5ms P95 (single INSERT with B-tree index)
            - Uses INSERT OR IGNORE for idempotency
            - Connection pooling via UnitOfWork

        Related:
            - M14 (builders.embedding_queue_write): Primary user of this syscall
            - P08 pipeline: Processes jobs from this queue
            - docs/pipelines/P02_data_schema.md: Schema definition (lines 275-355)
        """
        self._require_cap("st_embedding_queue.write")

        # Validation
        if not embedding_id:
            raise ValueError("embedding_id required for embedding_enqueue")
        if not event_id:
            raise ValueError("event_id required for embedding_enqueue")
        if priority not in ("NORMAL", "HIGH", "LOW"):
            raise ValueError(f"Invalid priority: {priority} (expected NORMAL/HIGH/LOW)")

        # Audit: Log storage operation
        start_time = time.perf_counter()
        logger.debug(
            f"embedding_enqueue: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "embedding_id": embedding_id,
                "event_id": event_id,
                "wal_pos": wal_pos,
                "space_id": space_id,
                "trace_id": cognitive_trace_id,
                "operation": "embedding_enqueue",
            },
        )

        # Execute storage operation in UnitOfWork transaction
        async with self._uow_factory() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            created_at = int(time.time())

            try:
                # Use INSERT OR IGNORE for idempotency
                loop = asyncio.get_running_loop()
                cursor = await loop.run_in_executor(
                    None,
                    lambda: conn.execute(
                        """
                        INSERT OR IGNORE INTO st_embedding_queue (
                            embedding_id, event_id, wal_pos,
                            tenant_id, space_id, vector_kind,
                            model_id, priority, status,
                            attempt_count, max_attempts,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            embedding_id,
                            event_id,
                            wal_pos,
                            tenant_id,
                            space_id,
                            vector_kind,
                            model_id,
                            priority,
                            "PENDING",  # Initial status
                            0,  # Initial attempt_count
                            5,  # max_attempts (default retry limit)
                            created_at,
                            created_at,  # updated_at = created_at initially
                        ),
                    ),
                )

                inserted = cursor.rowcount > 0

                # UnitOfWork context manager will auto-commit on successful exit

                # Audit: Log operation completion
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    f"embedding_enqueue complete: {embedding_id}",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "embedding_id": embedding_id,
                        "event_id": event_id,
                        "inserted": inserted,
                        "duration_ms": duration_ms,
                        "trace_id": cognitive_trace_id,
                    },
                )

                return {
                    "inserted": inserted,
                    "embedding_id": embedding_id,
                    "status": "INSERTED" if inserted else "SKIPPED_DUPLICATE",
                }

            except Exception as e:
                logger.error(
                    f"embedding_enqueue failed: {embedding_id}",
                    exc_info=True,
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "embedding_id": embedding_id,
                        "event_id": event_id,
                        "error": str(e),
                        "trace_id": cognitive_trace_id,
                    },
                )
                raise

    async def outbox_emit_batch(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Emit batch of events to st_outbox (requires st_outbox.write cap).

        **Transactional Outbox Pattern**

        Writes events to st_outbox within a single transaction for atomic
        batch processing. Used by P02 (Write) pipeline to emit completion
        events after storage commit (M17: core.event_emitter).

        Capability Required: "st_outbox.write"

        Storage Table: st_outbox
        - Purpose: Transactional outbox for async event delivery
        - Idempotency: fingerprint + requeue_seq uniqueness constraint
        - Typical Usage: P02 event emission, cross-pipeline communication

        Args:
            events: List of event dicts, each containing:
                - tenant_id: Tenant identifier (isolation boundary)
                - space_id: Space identifier (routing key)
                - driver: Event topic (e.g., "workspace.wm.updated")
                - op_kind: Operation type (e.g., "EVENT_EMIT")
                - payload: Event data (JSON-serializable dict)
                - fingerprint: Idempotency key (unique per event)
                - wal_pos: Optional WAL position reference (0 if not applicable)

        Returns:
            Dict with operation summary:
                {
                    "events_inserted": <count>,
                    "batch_size": <count>,
                    "operation": "outbox_emit_batch",
                    "status": "success"
                }

        Raises:
            PermissionError: If capability not granted
            sqlite3.IntegrityError: If fingerprint collision (idempotency violation)
            ValueError: If event structure invalid

        Performance Characteristics:
            - Latency Budget: <5ms P95 for 6-event batch (M17 requirement)
            - Single transaction: All events succeed or all rollback
            - Bulk INSERT: Uses executemany for efficiency

        Audit Logging:
            - All operations logged at DEBUG level
            - Errors logged at ERROR level with pipeline_id
            - Includes event count, topics, space_id for observability

        Example:
            >>> events = [
            ...     {
            ...         "tenant_id": "tenant_123",
            ...         "space_id": "space_456",
            ...         "driver": "workspace.wm.updated",
            ...         "op_kind": "EVENT_EMIT",
            ...         "payload": {"working_memory": {...}},
            ...         "fingerprint": "wm_update_abc123",
            ...         "wal_pos": 0,
            ...     },
            ...     # ... more events
            ... ]
            >>> result = await syscalls.outbox_emit_batch(events)
            >>> print(result["events_inserted"])  # 6

        Security Implications:
            - Capability enforcement: Prevents unauthorized event emission
            - Tenant/space isolation: Events routed per authorization
            - Fingerprint uniqueness: Prevents duplicate processing
            - Audit trail: All emissions logged

        Related:
            - M17 (core.event_emitter): Primary consumer
            - k0/contracts/modules/core.event_emitter.v1.yaml: Event schema
            - Section 7.3 of P02_write_dossier.md: Transactional outbox pattern
            - ADR-022: Event-driven architecture
        """
        self._require_cap("st_outbox.write")

        # Validate input
        if not events:
            logger.warning(
                f"outbox_emit_batch called with empty event list: {self._pipeline_id}",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "operation": "outbox_emit_batch",
                    "status": "skipped",
                },
            )
            return {
                "events_inserted": 0,
                "batch_size": 0,
                "operation": "outbox_emit_batch",
                "status": "skipped_empty",
            }

        # Validate event structure
        required_fields = ["tenant_id", "space_id", "driver", "op_kind", "payload", "fingerprint"]
        for idx, event in enumerate(events):
            missing = [f for f in required_fields if f not in event]
            if missing:
                logger.error(
                    f"outbox_emit_batch: Invalid event structure at index {idx}",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "event_index": idx,
                        "missing_fields": missing,
                        "operation": "outbox_emit_batch",
                        "status": "validation_failed",
                    },
                )
                raise ValueError(
                    f"Event at index {idx} missing required fields: {missing}. "
                    f"Required: {required_fields}"
                )

        # Extract topics for logging
        topics = [e["driver"] for e in events]
        space_ids = list(set(e["space_id"] for e in events))

        # Audit: Log operation start
        logger.debug(
            f"outbox_emit_batch starting: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "event_count": len(events),
                "topics": topics,
                "space_ids": space_ids,
                "operation": "outbox_emit_batch",
                "status": "starting",
            },
        )

        # Begin transaction
        async with self._uow_factory() as uow:
            try:
                # Prepare INSERT statements
                insert_sql = """
                    INSERT INTO st_outbox (
                        wal_pos, tenant_id, space_id, driver, op_kind,
                        payload, fingerprint, requeue_seq, retries
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                # Build parameter tuples
                records = []
                for event in events:
                    import json

                    # Serialize payload
                    payload_blob = json.dumps(event["payload"]).encode("utf-8")

                    # Get optional fields
                    wal_pos = event.get("wal_pos", 0)
                    requeue_seq = event.get("requeue_seq", 0)
                    retries = event.get("retries", 0)

                    records.append(
                        (
                            wal_pos,
                            event["tenant_id"],
                            event["space_id"],
                            event["driver"],
                            event["op_kind"],
                            payload_blob,
                            event["fingerprint"],
                            requeue_seq,
                            retries,
                        )
                    )

                # Execute batch insert
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, uow.connection.executemany, insert_sql, records)

                # Transaction will be committed automatically by __aexit__

                # Audit: Log success
                logger.debug(
                    f"outbox_emit_batch success: {self._pipeline_id}",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "events_inserted": len(events),
                        "topics": topics,
                        "space_ids": space_ids,
                        "operation": "outbox_emit_batch",
                        "status": "success",
                    },
                )

                return {
                    "events_inserted": len(events),
                    "batch_size": len(events),
                    "operation": "outbox_emit_batch",
                    "status": "success",
                }

            except Exception as e:
                # Audit: Log failure
                logger.error(
                    f"outbox_emit_batch failed: {self._pipeline_id}",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "event_count": len(events),
                        "topics": topics,
                        "space_ids": space_ids,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "operation": "outbox_emit_batch",
                        "status": "failed",
                    },
                    exc_info=True,
                )
                raise

    async def vec_write(
        self,
        embedding_id: str,
        event_id: str,
        tenant_id: str,
        space_id: str,
        vector: bytes,
        vector_dim: int = 768,
        model_id: str = "ultrabert_v2.1.0",
        status: str = "READY",
        cognitive_trace_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Write embedding vector to st_vec table (requires st_vec.write cap).

        Used by M23 (builders.embedding_write) to store 768-dim UltraBERT embeddings
        inline during P02 processing. Replaces async P08 queue pattern (ADR-K003).

        Capability Required: "st_vec.write"

        Storage Table: st_vec
        - Purpose: Primary storage for 768-dim embeddings (inline with P02)
        - Lifecycle: Permanent (tied to st_hipp_events via FK)
        - Primary Key: embedding_id (unique, idempotent)
        - Foreign Key: event_id → st_hipp_events.event_id (ON DELETE CASCADE)
        - Indexes: 4 (event_id, tenant_space, model_id, status_created)

        Status Values:
        - READY: Embedding stored, available for use
        - INDEXED: Also added to FAISS search index (P08 M24)
        - FAILED: Generation failed

        Args:
            embedding_id: Unique embedding identifier (UUID, idempotency key)
            event_id: Source event identifier (FK to st_hipp_events)
            tenant_id: Tenant isolation boundary
            space_id: Memory space identifier
            vector: 768-dim float32 embedding as bytes (3072 bytes)
            vector_dim: Dimensionality of vector (default: 768)
            model_id: Embedding model identifier (default: "ultrabert_v2.1.0")
            status: Embedding status (default: "READY")
            cognitive_trace_id: Optional trace ID for observability

        Returns:
            Dictionary with:
            - inserted: bool (True if inserted, False if duplicate skipped)
            - embedding_id: str
            - status: str ('INSERTED' or 'SKIPPED_DUPLICATE')

        Raises:
            PermissionError: If pipeline lacks "st_vec.write" capability
            ValueError: If required fields missing or invalid

        Example:
            >>> import struct
            >>> embedding = [0.1] * 768  # 768-dim vector
            >>> vector_bytes = struct.pack('768f', *embedding)
            >>> result = await syscalls.vec_write(
            ...     embedding_id="emb_uuid_abc123",
            ...     event_id="evt_123",
            ...     tenant_id="tenant_abc",
            ...     space_id="space_xyz",
            ...     vector=vector_bytes,
            ...     vector_dim=768,
            ...     model_id="ultrabert_v2.1.0",
            ...     status="READY"
            ... )
            >>> result["inserted"]
            True

        Performance:
            - Target: <5ms P95 (single INSERT with 3KB blob + 4 indexes)
            - Uses INSERT OR IGNORE for idempotency
            - Connection pooling via UnitOfWork

        Related:
            - M23 (builders.embedding_write): Primary user of this syscall
            - M22 (embedding.extract_from_cache): Extracts vector from UltraBERT cache
            - ADR-K003: Inline embedding architecture decision
            - Migration 0026: st_vec table definition
        """
        self._require_cap("st_vec.write")

        # Validation
        if not embedding_id:
            raise ValueError("embedding_id required for vec_write")
        if not event_id:
            raise ValueError("event_id required for vec_write")
        if not tenant_id:
            raise ValueError("tenant_id required for vec_write")
        if not space_id:
            raise ValueError("space_id required for vec_write")
        if not vector:
            raise ValueError("vector required for vec_write")
        if status not in ("READY", "INDEXED", "FAILED"):
            raise ValueError(f"Invalid status: {status} (expected READY/INDEXED/FAILED)")
        if vector_dim != 768:
            raise ValueError(f"Invalid vector_dim: {vector_dim} (expected 768)")
        if len(vector) != 3072:  # 768 floats * 4 bytes
            raise ValueError(f"Invalid vector size: {len(vector)} bytes (expected 3072)")

        # Audit: Log storage operation
        start_time = time.perf_counter()
        logger.debug(
            f"vec_write: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "embedding_id": embedding_id,
                "event_id": event_id,
                "space_id": space_id,
                "vector_dim": vector_dim,
                "model_id": model_id,
                "status": status,
                "trace_id": cognitive_trace_id,
                "operation": "vec_write",
            },
        )

        # Execute storage operation in UnitOfWork transaction
        async with self._uow_factory() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            created_at = int(time.time())
            updated_at = created_at

            try:
                # Use INSERT OR IGNORE for idempotency
                loop = asyncio.get_running_loop()
                cursor = await loop.run_in_executor(
                    None,
                    lambda: conn.execute(
                        """
                        INSERT OR IGNORE INTO st_vec (
                            embedding_id, event_id, tenant_id, space_id,
                            vector, vector_dim, model_id, status,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            embedding_id,
                            event_id,
                            tenant_id,
                            space_id,
                            vector,
                            vector_dim,
                            model_id,
                            status,
                            created_at,
                            updated_at,
                        ),
                    ),
                )

                inserted = cursor.rowcount > 0

                # Audit: Log performance
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(
                    f"vec_write completed: {embedding_id}",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "embedding_id": embedding_id,
                        "inserted": inserted,
                        "latency_ms": elapsed_ms,
                        "operation": "vec_write",
                    },
                )

                return {
                    "inserted": inserted,
                    "embedding_id": embedding_id,
                    "status": "INSERTED" if inserted else "SKIPPED_DUPLICATE",
                }

            except Exception as e:
                logger.error(
                    f"vec_write failed: {embedding_id}",
                    exc_info=True,
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "embedding_id": embedding_id,
                        "event_id": event_id,
                        "error": str(e),
                        "trace_id": cognitive_trace_id,
                    },
                )
                raise

    async def vec_query(
        self,
        status: str | None = None,
        tenant_id: str | None = None,
        space_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Query st_vec table for embeddings by status (requires st_vec.read cap).

        Used by P08 M24 (faiss_indexer) to find READY embeddings for indexing.
        Replaces event-driven model with query-based batch processing (ADR-K003 v1.2).

        Capability Required: "st_vec.read"

        Storage Table: st_vec
        - Query by status, tenant, space
        - Ordered by created_at ASC (oldest first)
        - Paginated for batch processing

        Args:
            status: Filter by status (READY, INDEXED, FAILED)
            tenant_id: Optional tenant filter
            space_id: Optional space filter
            limit: Max records to return (default: 100)
            offset: Pagination offset (default: 0)

        Returns:
            Dictionary with:
            - embeddings: list[dict] with embedding_id, event_id, vector, etc.
            - count: int (number of records returned)
            - total: int (total matching records)

        Raises:
            PermissionError: If pipeline lacks "st_vec.read" capability
            ValueError: If invalid status provided

        Example:
            >>> result = await syscalls.vec_query(status="READY", limit=100)
            >>> for emb in result["embeddings"]:
            ...     await process_embedding(emb)

        Performance:
            - Target: <20ms P95 (paginated query with status index)
            - Uses status_created index for efficient filtering
            - Limit+offset pagination for batch control

        Related:
            - M24 (embedding.faiss_indexer): Primary user of this syscall
            - P08 scheduled mode: Uses this instead of event subscription
            - ADR-K003 v1.2: Query-based P08 architecture
        """
        self._require_cap("st_vec.read")

        # Validate status if provided
        if status and status not in ("READY", "INDEXED", "FAILED"):
            raise ValueError(f"Invalid status: {status} (expected READY/INDEXED/FAILED)")

        # Build query with optional filters
        conditions = []
        params: list[Any] = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if space_id:
            conditions.append("space_id = ?")
            params.append(space_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Audit: Log query operation
        start_time = time.perf_counter()
        logger.debug(
            f"vec_query: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "status_filter": status,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "limit": limit,
                "offset": offset,
                "operation": "vec_query",
            },
        )

        async with self._uow_factory() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            try:
                loop = asyncio.get_running_loop()

                # Get total count
                count_sql = f"SELECT COUNT(*) FROM st_vec WHERE {where_clause}"
                total_result = await loop.run_in_executor(
                    None,
                    lambda: conn.execute(count_sql, params).fetchone(),
                )
                total = total_result[0] if total_result else 0

                # Get paginated results
                query_sql = f"""
                    SELECT embedding_id, event_id, tenant_id, space_id,
                           vector, vector_dim, model_id, status, created_at
                    FROM st_vec
                    WHERE {where_clause}
                    ORDER BY created_at ASC
                    LIMIT ? OFFSET ?
                """
                cursor = await loop.run_in_executor(
                    None,
                    lambda: conn.execute(query_sql, params + [limit, offset]),
                )
                rows = cursor.fetchall()

                embeddings = [
                    {
                        "embedding_id": row[0],
                        "event_id": row[1],
                        "tenant_id": row[2],
                        "space_id": row[3],
                        "vector": row[4],  # bytes (3072 for 768 floats)
                        "vector_dim": row[5],
                        "model_id": row[6],
                        "status": row[7],
                        "created_at": row[8],
                    }
                    for row in rows
                ]

                # Audit: Log query performance
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(
                    f"vec_query completed: {len(embeddings)} results",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "count": len(embeddings),
                        "total": total,
                        "latency_ms": elapsed_ms,
                        "operation": "vec_query",
                    },
                )

                return {
                    "embeddings": embeddings,
                    "count": len(embeddings),
                    "total": total,
                }

            except Exception as e:
                logger.error(
                    "vec_query failed",
                    exc_info=True,
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "status_filter": status,
                        "error": str(e),
                    },
                )
                raise

    async def vec_update_status(
        self,
        embedding_id: str,
        status: str,
        indexed_at: int | None = None,
    ) -> dict[str, Any]:
        """
        Update st_vec status (requires st_vec.write cap).

        Used by P08 M24 after adding to FAISS index to mark embedding as INDEXED.
        Also used for error handling (marking FAILED status).

        Capability Required: "st_vec.write"

        Status Transitions:
        - READY → INDEXED: After successful FAISS indexing
        - READY → FAILED: If FAISS indexing fails
        - FAILED → READY: For retry (via backfill)

        Args:
            embedding_id: Embedding to update
            status: New status (READY, INDEXED, FAILED)
            indexed_at: Optional timestamp when indexed (epoch seconds)

        Returns:
            Dictionary with:
            - updated: bool (True if row updated)
            - embedding_id: str
            - status: str

        Raises:
            PermissionError: If pipeline lacks "st_vec.write" capability
            ValueError: If invalid status provided

        Example:
            >>> await syscalls.vec_update_status(
            ...     embedding_id="emb_uuid_abc123",
            ...     status="INDEXED",
            ...     indexed_at=int(time.time())
            ... )

        Performance:
            - Target: <5ms P95 (single UPDATE by primary key)
            - Uses embedding_id primary key for fast lookup

        Related:
            - M24 (embedding.faiss_indexer): Primary user of this syscall
            - vec_query: Finds READY embeddings to index
            - ADR-K003 v1.2: P08 scheduled architecture
        """
        self._require_cap("st_vec.write")

        # Validation
        if not embedding_id:
            raise ValueError("embedding_id required for vec_update_status")
        if status not in ("READY", "INDEXED", "FAILED"):
            raise ValueError(f"Invalid status: {status} (expected READY/INDEXED/FAILED)")

        # Audit: Log update operation
        start_time = time.perf_counter()
        logger.debug(
            f"vec_update_status: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "embedding_id": embedding_id,
                "new_status": status,
                "indexed_at": indexed_at,
                "operation": "vec_update_status",
            },
        )

        async with self._uow_factory() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            updated_at = int(time.time())

            try:
                loop = asyncio.get_running_loop()

                if indexed_at:
                    cursor = await loop.run_in_executor(
                        None,
                        lambda: conn.execute(
                            "UPDATE st_vec SET status = ?, indexed_at = ?, updated_at = ? WHERE embedding_id = ?",
                            (status, indexed_at, updated_at, embedding_id),
                        ),
                    )
                else:
                    cursor = await loop.run_in_executor(
                        None,
                        lambda: conn.execute(
                            "UPDATE st_vec SET status = ?, updated_at = ? WHERE embedding_id = ?",
                            (status, updated_at, embedding_id),
                        ),
                    )

                updated = cursor.rowcount > 0

                # Audit: Log update performance
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(
                    f"vec_update_status completed: {embedding_id}",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "embedding_id": embedding_id,
                        "updated": updated,
                        "new_status": status,
                        "latency_ms": elapsed_ms,
                        "operation": "vec_update_status",
                    },
                )

                return {
                    "updated": updated,
                    "embedding_id": embedding_id,
                    "status": status,
                }

            except Exception as e:
                logger.error(
                    f"vec_update_status failed: {embedding_id}",
                    exc_info=True,
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "embedding_id": embedding_id,
                        "error": str(e),
                    },
                )
                raise

    async def faiss_add(
        self,
        embedding_id: str,
        vector: list[float],
        index_id: str = "ultrabert_v2.1.0_ivf256_pq64",
    ) -> dict[str, Any]:
        """
        Add single vector to FAISS similarity search index (requires faiss.write cap).

        Used by P08 M24 (embedding.faiss_indexer) to add 768-dim embeddings to
        FAISS IVF256,PQ64 index for semantic search.

        Capability Required: "faiss.write"

        FAISS Index Configuration:
        - Index Type: IVF256,PQ64 (Inverted File with Product Quantization)
        - Vector Dimension: 768
        - Compression Ratio: 8:1 (768 * 4 bytes → 384 bytes)
        - Search Parameter: nprobe=16 (cells to probe)
        - Distance Metric: L2 (Euclidean distance)

        Args:
            embedding_id: Unique embedding identifier (used as FAISS ID)
            vector: 768-dim float32 embedding
            index_id: FAISS index identifier (default: ultrabert_v2.1.0_ivf256_pq64)

        Returns:
            Dictionary with:
            - added: bool (True if added successfully)
            - embedding_id: str
            - index_id: str
            - total_vectors: int (total vectors in index after addition)

        Raises:
            PermissionError: If pipeline lacks "faiss.write" capability
            ValueError: If vector dimension invalid
            NotImplementedError: FAISS integration not yet implemented

        Example:
            >>> embedding = [0.1] * 768  # 768-dim vector
            >>> result = await syscalls.faiss_add(
            ...     embedding_id="emb_uuid_abc123",
            ...     vector=embedding,
            ...     index_id="ultrabert_v2.1.0_ivf256_pq64"
            ... )
            >>> result["added"]
            True

        Performance:
            - Target: <50ms P95 (single vector addition)
            - Batch operations preferred (use faiss_add_batch)

        Related:
            - M24 (embedding.faiss_indexer): Primary user of this syscall
            - ADR-K003: FAISS indexing for P08 v2
        """
        self._require_cap("faiss.write")

        # Validation
        if not embedding_id:
            raise ValueError("embedding_id required for faiss_add")
        if not vector:
            raise ValueError("vector required for faiss_add")
        if len(vector) != 768:
            raise ValueError(f"Invalid vector dimension: {len(vector)} (expected 768)")

        # Get FAISS manager instance
        from k0.runtime.faiss_manager import FaissIndexManager

        faiss_mgr = FaissIndexManager.get_instance()

        # Add vector to FAISS index
        try:
            result = await faiss_mgr.add(embedding_id, vector, index_id)

            logger.info(
                "faiss_add completed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "embedding_id": embedding_id,
                    "index_id": index_id,
                    "total_vectors": result["total_vectors"],
                },
            )

            return result

        except ValueError as e:
            logger.error(
                "faiss_add validation failed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "embedding_id": embedding_id,
                    "error": str(e),
                },
            )
            raise

        except Exception as e:
            logger.error(
                "faiss_add failed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "embedding_id": embedding_id,
                    "error": str(e),
                },
            )
            raise RuntimeError(f"Failed to add vector to FAISS: {e}") from e

    async def faiss_add_batch(
        self,
        records: list[dict[str, Any]],
        index_id: str = "ultrabert_v2.1.0_ivf256_pq64",
    ) -> dict[str, Any]:
        """
        Add batch of vectors to FAISS index (requires faiss.write cap).

        Batch addition is ~5-10x faster than individual adds due to reduced
        index update overhead.

        Capability Required: "faiss.write"

        Args:
            records: List of dicts with:
                - embedding_id: str (unique identifier)
                - vector: list[float] (768-dim embedding)
            index_id: FAISS index identifier

        Returns:
            Dictionary with:
            - added_count: int (number of vectors added)
            - batch_size: int (size of input batch)
            - index_id: str
            - total_vectors: int (total vectors in index after addition)

        Raises:
            PermissionError: If pipeline lacks "faiss.write" capability
            ValueError: If records invalid
            NotImplementedError: FAISS integration not yet implemented

        Example:
            >>> records = [
            ...     {"embedding_id": "emb_1", "vector": [0.1] * 768},
            ...     {"embedding_id": "emb_2", "vector": [0.2] * 768},
            ... ]
            >>> result = await syscalls.faiss_add_batch(
            ...     records=records,
            ...     index_id="ultrabert_v2.1.0_ivf256_pq64"
            ... )
            >>> result["added_count"]
            2

        Performance:
            - Target: 200 vectors/sec (5ms per vector in batch)
            - Prefer batches of 50-200 vectors for optimal performance

        Related:
            - M24 (embedding.faiss_indexer): Uses this for batch indexing
            - ADR-K003: FAISS batch indexing strategy
        """
        self._require_cap("faiss.write")

        # Validation
        if not records:
            raise ValueError("records required for faiss_add_batch (empty list)")
        for i, record in enumerate(records):
            if "embedding_id" not in record:
                raise ValueError(f"Record {i} missing embedding_id")
            if "vector" not in record:
                raise ValueError(f"Record {i} missing vector")
            if len(record["vector"]) != 768:
                raise ValueError(
                    f"Record {i} invalid vector dimension: {len(record['vector'])} (expected 768)"
                )

        # Get FAISS manager instance
        from k0.runtime.faiss_manager import FaissIndexManager

        faiss_mgr = FaissIndexManager.get_instance()

        # Convert records to (embedding_id, vector) tuples
        embeddings = [(rec["embedding_id"], rec["vector"]) for rec in records]

        # Batch add to FAISS index
        try:
            result = await faiss_mgr.add_batch(embeddings, index_id)

            logger.info(
                "faiss_add_batch completed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "batch_size": len(records),
                    "added_count": result["added"],
                    "index_id": index_id,
                    "total_vectors": result["total_vectors"],
                },
            )

            return {
                "added_count": result["added"],
                "batch_size": len(records),
                "index_id": result["index_id"],
                "total_vectors": result["total_vectors"],
            }

        except ValueError as e:
            logger.error(
                "faiss_add_batch validation failed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "batch_size": len(records),
                    "error": str(e),
                },
            )
            raise

        except Exception as e:
            logger.error(
                "faiss_add_batch failed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "batch_size": len(records),
                    "error": str(e),
                },
            )
            raise RuntimeError(f"Failed to batch add vectors to FAISS: {e}") from e

    async def faiss_search(
        self,
        query_vector: list[float],
        k: int = 10,
        index_id: str = "ultrabert_v2.1.0_ivf256_pq64",
        nprobe: int = 16,
    ) -> dict[str, Any]:
        """
        Search FAISS index for k nearest neighbors (requires faiss.read cap).

        Returns top-k most similar embeddings based on L2 distance.

        Capability Required: "faiss.read"

        Args:
            query_vector: 768-dim query embedding
            k: Number of nearest neighbors to return (default: 10)
            index_id: FAISS index identifier
            nprobe: Number of IVF cells to probe (default: 16)

        Returns:
            Dictionary with:
            - embedding_ids: list[str] (k nearest neighbor IDs)
            - distances: list[float] (L2 distances)
            - k: int (number of results)

        Raises:
            PermissionError: If pipeline lacks "faiss.read" capability
            ValueError: If query_vector invalid
            NotImplementedError: FAISS integration not yet implemented

        Example:
            >>> query = [0.1] * 768  # 768-dim query vector
            >>> result = await syscalls.faiss_search(
            ...     query_vector=query,
            ...     k=10,
            ...     nprobe=16
            ... )
            >>> result["embedding_ids"]
            ['emb_1', 'emb_2', ...]

        Performance:
            - Target: <50ms P95 for k=10, nprobe=16
            - Higher nprobe = better recall but slower search

        Related:
            - P03 consolidation: Uses this for similarity search
            - ADR-K003: FAISS search configuration
        """
        self._require_cap("faiss.read")

        # Validation
        if not query_vector:
            raise ValueError("query_vector required for faiss_search")
        if len(query_vector) != 768:
            raise ValueError(f"Invalid query_vector dimension: {len(query_vector)} (expected 768)")
        if k < 1:
            raise ValueError(f"Invalid k: {k} (must be >= 1)")
        if nprobe < 1 or nprobe > 256:
            raise ValueError(f"Invalid nprobe: {nprobe} (expected 1-256)")

        # Get FAISS manager instance
        from k0.runtime.faiss_manager import FaissIndexManager

        faiss_mgr = FaissIndexManager.get_instance()

        # Search FAISS index
        try:
            results = await faiss_mgr.search(query_vector, k, index_id)

            # Extract IDs and distances for return format
            embedding_ids = [r["embedding_id"] for r in results]
            distances = [r["distance"] for r in results]

            logger.info(
                "faiss_search completed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "k": k,
                    "nprobe": nprobe,
                    "results_found": len(results),
                    "index_id": index_id,
                },
            )

            return {
                "embedding_ids": embedding_ids,
                "distances": distances,
                "k": len(results),
            }

        except ValueError as e:
            logger.error(
                "faiss_search validation failed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "k": k,
                    "error": str(e),
                },
            )
            raise

        except Exception as e:
            logger.error(
                "faiss_search failed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "k": k,
                    "error": str(e),
                },
            )
            raise RuntimeError(f"Failed to search FAISS index: {e}") from e

    async def faiss_remove_batch(
        self,
        embedding_ids: list[str],
        index_id: str = "ultrabert_v2.1.0_ivf256_pq64",
    ) -> dict[str, Any]:
        """
        Remove batch of vectors from FAISS index (requires faiss.write cap).

        Used by P08 M27 (embedding.cleanup) to remove orphaned embeddings.

        Capability Required: "faiss.write"

        Args:
            embedding_ids: List of embedding IDs to remove
            index_id: FAISS index identifier

        Returns:
            Dictionary with:
            - removed_count: int (number of vectors removed)
            - batch_size: int (size of input batch)
            - index_id: str
            - total_vectors: int (remaining vectors in index)

        Raises:
            PermissionError: If pipeline lacks "faiss.write" capability
            ValueError: If embedding_ids invalid
            NotImplementedError: FAISS integration not yet implemented

        Example:
            >>> ids = ["emb_1", "emb_2", "emb_3"]
            >>> result = await syscalls.faiss_remove_batch(
            ...     embedding_ids=ids,
            ...     index_id="ultrabert_v2.1.0_ivf256_pq64"
            ... )
            >>> result["removed_count"]
            3

        Performance:
            - Target: 2000 embeddings/sec (0.5ms per embedding in batch)
            - Batch operations preferred for bulk cleanup

        Related:
            - M27 (embedding.cleanup): Uses this for orphan removal
            - ADR-K003: FAISS cleanup strategy
        """
        self._require_cap("faiss.write")

        # Validation
        if not embedding_ids:
            raise ValueError("embedding_ids required for faiss_remove_batch (empty list)")

        # Get FAISS manager instance
        from k0.runtime.faiss_manager import FaissIndexManager

        faiss_mgr = FaissIndexManager.get_instance()

        # Remove from FAISS index
        try:
            result = await faiss_mgr.remove_batch(embedding_ids)

            logger.info(
                "faiss_remove_batch completed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "batch_size": len(embedding_ids),
                    "removed_count": result["removed"],
                    "index_id": index_id,
                    "note": result.get("note"),
                },
            )

            return {
                "removed_count": result["removed"],
                "batch_size": len(embedding_ids),
                "index_id": index_id,
                "total_vectors": result["total_vectors"],
            }

        except Exception as e:
            logger.error(
                "faiss_remove_batch failed",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "batch_size": len(embedding_ids),
                    "error": str(e),
                },
            )
            raise RuntimeError(f"Failed to remove vectors from FAISS: {e}") from e

    # =========================================================================
    # Phase 3: Backfill Syscalls (ADR-K003 v1.2)
    # =========================================================================

    async def hipp_events_query(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
        embedding_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Query st_hipp_events by filters (requires st_hipp_events.read cap).

        Used by M25 backfill to find PENDING embeddings that need reprocessing.
        Returns events matching the specified filters, ordered by created_at.

        Capability Required: "st_hipp_events.read"

        Storage Table: st_hipp_events
        - Query by tenant, space, embedding_status
        - Ordered by created_at ASC (oldest first)
        - Paginated for batch processing

        Args:
            tenant_id: Optional tenant filter
            space_id: Optional space filter
            embedding_status: Filter by status (PENDING, READY, INDEXED, FAILED)
            limit: Max records to return (default: 100)
            offset: Pagination offset (default: 0)

        Returns:
            Dictionary with:
            - events: list[dict] with event_id, tenant_id, space_id, text, embedding_status
            - count: int (number of records returned)
            - total: int (total matching records)

        Raises:
            PermissionError: If pipeline lacks "st_hipp_events.read" capability
            ValueError: If invalid embedding_status provided

        Example:
            >>> result = await syscalls.hipp_events_query(
            ...     embedding_status="PENDING",
            ...     limit=100
            ... )
            >>> for event in result["events"]:
            ...     await backfill_embedding(event)

        Performance:
            - Target: <30ms P95 (paginated query with embedding_status index)
            - Uses embedding_status index for efficient filtering

        Related:
            - M25 (embedding.backfill): Primary user of this syscall
            - P08 backfill mode: Uses this to find PENDING events
            - ADR-K003 v1.2: Backfill architecture
        """
        self._require_cap("st_hipp_events.read")

        # Validate embedding_status if provided
        if embedding_status and embedding_status not in ("PENDING", "READY", "INDEXED", "FAILED"):
            raise ValueError(f"Invalid embedding_status: {embedding_status}")

        # Build query with optional filters
        conditions: list[str] = []
        params: list[Any] = []

        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if space_id:
            conditions.append("space_id = ?")
            params.append(space_id)
        if embedding_status:
            conditions.append("embedding_status = ?")
            params.append(embedding_status)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Audit: Log query operation
        start_time = time.perf_counter()
        logger.debug(
            f"hipp_events_query: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "embedding_status": embedding_status,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "limit": limit,
                "offset": offset,
                "operation": "hipp_events_query",
            },
        )

        async with self._uow_factory() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            try:
                loop = asyncio.get_running_loop()

                # Get total count
                count_sql = f"SELECT COUNT(*) FROM st_hipp_events WHERE {where_clause}"
                total_result = await loop.run_in_executor(
                    None,
                    lambda: conn.execute(count_sql, params).fetchone(),
                )
                total = total_result[0] if total_result else 0

                # Get paginated results
                query_sql = f"""
                    SELECT event_id, tenant_id, space_id, text, embedding_status,
                           embedding_id, created_at
                    FROM st_hipp_events
                    WHERE {where_clause}
                    ORDER BY created_at ASC
                    LIMIT ? OFFSET ?
                """
                cursor = await loop.run_in_executor(
                    None,
                    lambda: conn.execute(query_sql, params + [limit, offset]),
                )
                rows = cursor.fetchall()

                events = [
                    {
                        "event_id": row[0],
                        "tenant_id": row[1],
                        "space_id": row[2],
                        "event_text": row[3],
                        "embedding_status": row[4],
                        "embedding_id": row[5],
                        "created_at": row[6],
                    }
                    for row in rows
                ]

                # Audit: Log query performance
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(
                    f"hipp_events_query completed: {len(events)} results",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "count": len(events),
                        "total": total,
                        "latency_ms": elapsed_ms,
                        "operation": "hipp_events_query",
                    },
                )

                return {
                    "events": events,
                    "count": len(events),
                    "total": total,
                }

            except Exception as e:
                logger.error(
                    "hipp_events_query failed",
                    exc_info=True,
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "embedding_status": embedding_status,
                        "error": str(e),
                    },
                )
                raise

    async def hipp_events_update_embedding_status(
        self,
        event_id: str,
        embedding_status: str,
        embedding_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Update st_hipp_events.embedding_status (requires st_hipp_events.write cap).

        Used by M25 backfill after computing embeddings for PENDING events.
        Can also update embedding_id if a new embedding was generated.

        Capability Required: "st_hipp_events.write"

        Status Transitions:
        - PENDING -> READY: After embedding computed and stored
        - PENDING -> FAILED: If embedding computation failed
        - FAILED -> READY: After retry succeeds

        Args:
            event_id: Event to update
            embedding_status: New status (PENDING, READY, INDEXED, FAILED)
            embedding_id: Optional new embedding_id (for backfill)

        Returns:
            Dictionary with:
            - updated: bool (True if row updated)
            - event_id: str
            - embedding_status: str

        Raises:
            PermissionError: If pipeline lacks "st_hipp_events.write" capability
            ValueError: If invalid embedding_status provided

        Example:
            >>> await syscalls.hipp_events_update_embedding_status(
            ...     event_id="evt_123",
            ...     embedding_status="READY",
            ...     embedding_id="emb_new_456"
            ... )

        Performance:
            - Target: <5ms P95 (single UPDATE by primary key)

        Related:
            - M25 (embedding.backfill): Primary user of this syscall
            - hipp_events_query: Finds PENDING events
            - ADR-K003 v1.2: Backfill architecture
        """
        self._require_cap("st_hipp_events.write")

        # Validation
        if not event_id:
            raise ValueError("event_id required for hipp_events_update_embedding_status")
        if embedding_status not in ("PENDING", "READY", "INDEXED", "FAILED"):
            raise ValueError(f"Invalid embedding_status: {embedding_status}")

        # Audit: Log update operation
        start_time = time.perf_counter()
        logger.debug(
            f"hipp_events_update_embedding_status: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "event_id": event_id,
                "new_status": embedding_status,
                "embedding_id": embedding_id,
                "operation": "hipp_events_update_embedding_status",
            },
        )

        async with self._uow_factory() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            updated_at = int(time.time())

            try:
                loop = asyncio.get_running_loop()

                if embedding_id:
                    cursor = await loop.run_in_executor(
                        None,
                        lambda: conn.execute(
                            "UPDATE st_hipp_events SET embedding_status = ?, embedding_id = ?, updated_at = ? WHERE event_id = ?",
                            (embedding_status, embedding_id, updated_at, event_id),
                        ),
                    )
                else:
                    cursor = await loop.run_in_executor(
                        None,
                        lambda: conn.execute(
                            "UPDATE st_hipp_events SET embedding_status = ?, updated_at = ? WHERE event_id = ?",
                            (embedding_status, updated_at, event_id),
                        ),
                    )

                updated = cursor.rowcount > 0

                # Audit: Log update performance
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(
                    f"hipp_events_update_embedding_status completed: {event_id}",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "event_id": event_id,
                        "updated": updated,
                        "new_status": embedding_status,
                        "latency_ms": elapsed_ms,
                        "operation": "hipp_events_update_embedding_status",
                    },
                )

                return {
                    "updated": updated,
                    "event_id": event_id,
                    "embedding_status": embedding_status,
                }

            except Exception as e:
                logger.error(
                    f"hipp_events_update_embedding_status failed: {event_id}",
                    exc_info=True,
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "event_id": event_id,
                        "error": str(e),
                    },
                )
                raise

    async def ultrabert_embed(
        self,
        text: str,
        model_id: str = "ultrabert_v2.1.0",
    ) -> dict[str, Any]:
        """
        Generate embedding via UltraBERT (requires ultrabert.embed cap).

        Used by M25 backfill to compute embeddings for PENDING events.
        Returns a 768-dim embedding vector and generated embedding_id.

        Capability Required: "ultrabert.embed"

        Model Configuration:
        - Model: UltraBERT v2.1.0
        - Vector Dimension: 768
        - Max Input Length: 512 tokens

        Args:
            text: Text to embed (will be truncated if > 512 tokens)
            model_id: Embedding model identifier (default: "ultrabert_v2.1.0")

        Returns:
            Dictionary with:
            - embedding: list[float] (768-dim vector) or None if failed
            - embedding_id: str (UUID) or None if failed
            - vector_dim: int (768)
            - model_id: str
            - error: str (only if failed)

        Raises:
            PermissionError: If pipeline lacks "ultrabert.embed" capability
            ValueError: If text is empty

        Example:
            >>> result = await syscalls.ultrabert_embed(text="Hello world")
            >>> if result["embedding"]:
            ...     vector = result["embedding"]  # 768-dim list
            ...     emb_id = result["embedding_id"]

        Performance:
            - Target: <50ms P95 (single embedding, GPU accelerated)
            - Batch operations preferred for bulk embedding

        Related:
            - M25 (embedding.backfill): Primary user of this syscall
            - M22 (embedding.extract_from_cache): Uses same UltraBERT model
            - ADR-K003: UltraBERT architecture
        """
        self._require_cap("ultrabert.embed")

        # Validation
        if not text or not text.strip():
            raise ValueError("text required for ultrabert_embed (empty or whitespace-only)")

        import uuid

        # Audit: Log embed operation
        start_time = time.perf_counter()
        logger.debug(
            f"ultrabert_embed: {self._pipeline_id}",
            extra={
                "pipeline_id": self._pipeline_id,
                "text_length": len(text),
                "model_id": model_id,
                "operation": "ultrabert_embed",
            },
        )

        try:
            # Import UltraBERT adapter
            from k0.runtime.ultrabert_adapter import get_embedding

            # Generate embedding
            embedding = get_embedding(text)

            if not embedding:
                logger.warning(
                    "ultrabert_embed: UltraBERT unavailable or returned None",
                    extra={
                        "pipeline_id": self._pipeline_id,
                        "text_length": len(text),
                    },
                )
                return {
                    "embedding": None,
                    "embedding_id": None,
                    "vector_dim": 0,
                    "model_id": model_id,
                    "error": "UltraBERT unavailable or returned None",
                }

            # Generate embedding_id
            embedding_id = str(uuid.uuid4())

            # Audit: Log embed performance
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                f"ultrabert_embed completed: {embedding_id}",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "embedding_id": embedding_id,
                    "vector_dim": len(embedding),
                    "latency_ms": elapsed_ms,
                    "operation": "ultrabert_embed",
                },
            )

            return {
                "embedding": embedding,
                "embedding_id": embedding_id,
                "vector_dim": len(embedding),
                "model_id": model_id,
            }

        except ImportError as e:
            logger.error(
                "ultrabert_embed: Failed to import ultrabert_adapter",
                extra={
                    "pipeline_id": self._pipeline_id,
                    "error": str(e),
                },
            )
            return {
                "embedding": None,
                "embedding_id": None,
                "vector_dim": 0,
                "model_id": model_id,
                "error": f"UltraBERT adapter import failed: {e}",
            }

        except Exception as e:
            logger.error(
                "ultrabert_embed failed",
                exc_info=True,
                extra={
                    "pipeline_id": self._pipeline_id,
                    "text_length": len(text),
                    "error": str(e),
                },
            )
            return {
                "embedding": None,
                "embedding_id": None,
                "vector_dim": 0,
                "model_id": model_id,
                "error": str(e),
            }

    def _require_cap(self, capability: str) -> None:
        """
        Check capability, raise PermissionError if not granted.

        Implements fail-closed security: if capability not in granted set,
        operation is denied and logged as potential security violation.

        Args:
            capability: Required capability (e.g., "st_hipp_events.write")

        Raises:
            PermissionError: If capability not in self._granted_caps

        Audit Logging:
            - All capability checks logged at DEBUG level
            - Violations logged at ERROR level with pipeline_id
            - Can be used for security monitoring and alerting

        Example:
            >>> self._require_cap("st_hipp_events.write")
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
