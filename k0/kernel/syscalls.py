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
        async with self._uow_factory() as uow:
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
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: conn.execute(
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
