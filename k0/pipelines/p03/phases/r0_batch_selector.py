"""
R0 Phase — Batch Selection (Event Ingestion).

M3 Issue 3.2.1: Implement R0 Phase for Event Ingestion from st_hipp_events.

This phase is the entry point for P03 consolidation:
1. Fetch current offset from st_offsets (via OffsetStore)
2. Query st_hipp_events for eligible events after offset
3. Load embeddings from st_vec for selected events (lazy materialization)
4. Build P03BatchEnvelope with context and events
5. Return envelope for R1-R8 processing

Unlike R1-R8 which receive an envelope, R0 CREATES the envelope.

References:
    - Dossier 4.1: R0 Trigger Detection & Batch Selection
    - P03 Checkpoint: k0/pipelines/p03/checkpoint.py
    - M3 Execution: docs/TEMP_EXECUTION_DOCS/M3_EXECUTION.md Issue 3.2.1
"""

from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from k0.modules.consolidation.gap_auto_resolver import GapAutoResolver
from k0.pipelines.p03.checkpoint import P03_SOURCE_TOPIC, P03_SUBSCRIBER_ID
from k0.pipelines.p03.context import P03CycleContext
from k0.pipelines.p03.envelope import P03BatchEnvelope
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.runner_contract import P03PhaseId

if TYPE_CHECKING:
    from k0.pipelines.p03.phase_interface import P03RunnerContext

logger = logging.getLogger(__name__)


# =============================================================================
# GAP AUTO-RESOLUTION (Uses k0.modules.consolidation.gap_auto_resolver)
# =============================================================================


def _extract_entities_from_events(
    events: List[P03EventState],
) -> tuple[list[dict], list[str]]:
    """
    Extract NER entities and raw texts from P03 events for gap matching.

    Returns (entities_list, event_texts_list).
    """
    import json

    all_entities = []
    event_texts = []

    for event in events:
        # Collect raw text for fallback matching
        if event.content_text:
            event_texts.append(event.content_text)

        if not event.ner_entities_json or event.ner_entities_json == "[]":
            continue

        try:
            ner_data = json.loads(event.ner_entities_json)

            if isinstance(ner_data, dict):
                # UltraBERT format: {"ner_family": {"entities": [...]}, ...}
                for key in ["ner_family", "ner_general"]:
                    ner_section = ner_data.get(key, {})
                    if isinstance(ner_section, dict):
                        entities_list = ner_section.get("entities", [])
                    elif isinstance(ner_section, list):
                        entities_list = ner_section
                    else:
                        entities_list = []

                    for entity in entities_list:
                        if isinstance(entity, dict):
                            all_entities.append(
                                {
                                    "text": entity.get("text", entity.get("value", "")),
                                    "label": entity.get("label", entity.get("type", "UNKNOWN")),
                                    "source_event_id": event.event_id,
                                }
                            )
            elif isinstance(ner_data, list):
                # Simple list format
                for entity in ner_data:
                    if isinstance(entity, dict):
                        all_entities.append(
                            {
                                "text": entity.get("text", entity.get("value", "")),
                                "label": entity.get("label", entity.get("type", "UNKNOWN")),
                                "source_event_id": event.event_id,
                            }
                        )
        except (json.JSONDecodeError, TypeError):
            pass

    return all_entities, event_texts


async def _try_auto_resolve_gaps(
    ctx: "P03RunnerContext",
    events: List[P03EventState],
    tenant_id: str,
    space_id: str,
) -> int:
    """
    Check incoming events for entities that resolve pending gaps.

    Delegates to GapAutoResolver for proper similarity-based matching,
    confidence scoring, label matching, and specificity bonuses.

    Returns number of gaps resolved.
    """
    try:
        all_entities, event_texts = _extract_entities_from_events(events)

        if not all_entities and not event_texts:
            logger.debug("R0: No entities or texts to check for gap resolution")
            return 0

        # Get pool from syscalls using capability-gated access
        try:
            pool = ctx.syscalls.get_pool()
        except (PermissionError, RuntimeError) as e:
            logger.debug(f"R0: No pool access for gap auto-resolution: {e}")
            return 0

        # Use GapAutoResolver for sophisticated matching
        resolver = GapAutoResolver(
            pool=pool,
            tenant_id=tenant_id,
            space_id=space_id,
        )

        resolved_count = await resolver.process_entities(
            entities=all_entities,
            source_event_id=events[0].event_id if events else None,
            event_texts=event_texts,
        )

        if resolved_count > 0:
            stats = resolver.stats
            logger.info(
                "R0: Gap auto-resolution stats: checked=%d, matched=%d, resolved=%d, skipped=%d",
                stats.gaps_checked,
                stats.entities_matched,
                stats.gaps_resolved,
                stats.gaps_skipped_low_confidence,
            )

        return resolved_count

    except Exception as e:
        logger.warning(
            "R0: Gap auto-resolution failed (non-fatal): %s",
            str(e),
            extra={"tenant_id": tenant_id, "space_id": space_id},
        )
        return 0


# =============================================================================
# R0 CONFIGURATION
# =============================================================================


@dataclass
class R0Config:
    """
    R0 phase configuration.

    Attributes:
        batch_size: Maximum events per batch (default: 100)
        require_embedding_ready: Only include events with embedding_status='READY'
        exclude_archived: Exclude events with archival_status set
        max_age_hours: Maximum age of events to consider (0 = no limit)
    """

    batch_size: int = 100
    require_embedding_ready: bool = True
    exclude_archived: bool = True
    max_age_hours: int = 0  # 0 = no limit


# =============================================================================
# R0 BATCH SELECTOR PHASE
# =============================================================================


class R0BatchSelector:
    """
    R0 Phase: Batch Selection (Event Ingestion).

    Responsibilities:
        1. Fetch current offset from st_offsets
        2. Query st_hipp_events for eligible events after offset
        3. Build P03BatchEnvelope with context and events
        4. Return (envelope, result) tuple for R1-R8 processing

    Eligibility Criteria:
        - event_id > last_committed_offset
        - consolidation_status IS NULL or 'PENDING'
        - embedding_status = 'READY' (if config.require_embedding_ready)
        - archival_status IS NULL (if config.exclude_archived)

    Unlike R1-R8:
        - R0 CREATES the envelope (others receive it)
        - R0 signature: run(tenant_id, space_id, ctx) -> (envelope, result)
        - R1-R8 signature: run(envelope, ctx) -> result

    Idempotency:
        - Offset read is idempotent (same offset on retry)
        - Same batch selected if no events processed between retries
        - cycle_id is generated fresh on each call
    """

    PHASE_ID = P03PhaseId.R0_INIT

    def __init__(self, config: Optional[R0Config] = None):
        """
        Initialize R0 phase.

        Args:
            config: Optional configuration (defaults used if not provided)
        """
        self.config = config or R0Config()

    @property
    def phase_id(self) -> P03PhaseId:
        """Return the phase identifier."""
        return self.PHASE_ID

    async def run(
        self,
        tenant_id: str,
        space_id: str,
        ctx: "P03RunnerContext",
    ) -> Tuple[Optional[P03BatchEnvelope], P03PhaseResult]:
        """
        Execute R0 phase: Batch Selection.

        Unlike R1-R8 which receive an envelope, R0 creates it.

        Args:
            tenant_id: Tenant identifier for multi-tenant isolation
            space_id: Space identifier (family/user)
            ctx: Runner context with syscalls, logger, config

        Returns:
            Tuple of:
                - P03BatchEnvelope if events found (None if skip/fail)
                - P03PhaseResult with status, duration, outputs
        """
        start_ms = int(time.time() * 1000)

        logger.info(
            "R0: Starting batch selection phase",
            extra={
                "tenant_id": tenant_id,
                "space_id": space_id,
                "batch_size": self.config.batch_size,
            },
        )

        try:
            # 1. Fetch current offset
            current_offset = await self._fetch_offset(ctx, tenant_id, space_id)

            logger.info(
                "R0: Fetched current offset",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "offset": current_offset,
                },
            )

            # 2. Query eligible events from st_hipp_events
            events = await self._fetch_eligible_events(
                ctx,
                tenant_id,
                space_id,
                current_offset,
            )

            # 3. Handle empty batch (SKIP)
            if not events:
                duration_ms = int(time.time() * 1000) - start_ms
                logger.info(
                    "R0: No eligible events found, skipping",
                    extra={
                        "tenant_id": tenant_id,
                        "space_id": space_id,
                        "offset": current_offset,
                        "duration_ms": duration_ms,
                    },
                )
                return None, P03PhaseResult.skip(
                    phase_id=self.PHASE_ID,
                    reason="No eligible events found",
                    duration_ms=duration_ms,
                )

            # 4. Load embeddings from st_vec for R2 clustering
            embeddings_loaded = await self._load_embeddings_for_events(
                ctx,
                events,
            )
            logger.info(
                "R0: Loaded embeddings from st_vec",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "events_count": len(events),
                    "embeddings_loaded": embeddings_loaded,
                },
            )

            # 4b. Auto-resolve pending gaps from user context (non-blocking)
            # If user mentions "Lincoln Elementary", resolve "Lincoln School" gap
            gaps_resolved = await _try_auto_resolve_gaps(ctx, events, tenant_id, space_id)
            if gaps_resolved > 0:
                logger.info(
                    "R0: Implicitly resolved %d gaps from user context",
                    gaps_resolved,
                    extra={"tenant_id": tenant_id, "space_id": space_id},
                )

            # 5. Filter to events with embeddings (required for R2 clustering)
            events_with_embeddings = [e for e in events if e.embedding_768 is not None]
            if len(events_with_embeddings) < len(events):
                logger.warning(
                    "R0: Excluding events without embeddings",
                    extra={
                        "tenant_id": tenant_id,
                        "space_id": space_id,
                        "total_events": len(events),
                        "events_with_embeddings": len(events_with_embeddings),
                        "excluded": len(events) - len(events_with_embeddings),
                    },
                )
            events = events_with_embeddings

            if not events:
                duration_ms = int(time.time() * 1000) - start_ms
                return None, P03PhaseResult.skip(
                    phase_id=self.PHASE_ID,
                    reason="No events with embeddings",
                    duration_ms=duration_ms,
                )

            # 6. Build envelope
            envelope = self._build_envelope(
                tenant_id,
                space_id,
                events,
                current_offset,
            )

            duration_ms = int(time.time() * 1000) - start_ms

            logger.info(
                "R0: Batch selection complete",
                extra={
                    "cycle_id": envelope.context.cycle_id,
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "events_selected": len(events),
                    "offset_start": current_offset,
                    "batch_watermark": (
                        envelope.context.event_ids[-1] if envelope.context.event_ids else None
                    ),
                    "duration_ms": duration_ms,
                },
            )

            result = P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary={
                    "events_selected": len(events),
                    "offset_start": current_offset,
                    "batch_id": envelope.context.batch_id,
                },
                idempotency_key=f"p03:r0:{envelope.context.cycle_id}",
            )

            return envelope, result

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            logger.exception(
                "R0: Batch selection failed",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            error = P03Error.create(
                phase="R0",
                stage_id="batch_selector",
                error_type="R0_INGESTION_ERROR",
                error_message=str(e),
                recoverable=True,  # R0 failures are retriable
            )

            return None, P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=error,
                duration_ms=duration_ms,
            )

    async def _fetch_offset(
        self,
        ctx: "P03RunnerContext",
        tenant_id: str,
        space_id: str,
    ) -> int:
        """
        Fetch current offset from st_offsets.

        Args:
            ctx: Runner context with syscalls
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            Current offset (0 if no prior offset exists)
        """
        # Use syscalls to get offset store
        offset_store = ctx.syscalls.offset_store

        offset_record = await offset_store.fetch(
            subscriber_id=P03_SUBSCRIBER_ID,
            topic=P03_SOURCE_TOPIC,
            space_id=space_id,
            tenant_id=tenant_id,
        )

        if offset_record is None:
            return 0

        return offset_record.offset

    async def _fetch_eligible_events(
        self,
        ctx: "P03RunnerContext",
        tenant_id: str,
        space_id: str,
        offset: int,
    ) -> List[P03EventState]:
        """
        Query st_hipp_events for eligible events.

        SQL (conceptual):
            SELECT * FROM st_hipp_events
            WHERE tenant_id = $1
              AND space_id = $2
              AND wal_pos > $3
              AND (consolidation_status IS NULL OR consolidation_status = 'PENDING')
              AND embedding_status = 'READY'
              AND (archival_status IS NULL)
            ORDER BY wal_pos ASC
            LIMIT $4

        Args:
            ctx: Runner context with syscalls
            tenant_id: Tenant identifier
            space_id: Space identifier
            offset: Current offset (events with wal_pos > offset are eligible)

        Returns:
            List of P03EventState populated from st_hipp_events rows
        """
        # Build query with proper filters
        conditions: List[str] = []
        params: List[Any] = []
        param_idx = 1

        # Required filters
        conditions.append(f"tenant_id = ${param_idx}")
        params.append(tenant_id)
        param_idx += 1

        conditions.append(f"space_id = ${param_idx}")
        params.append(space_id)
        param_idx += 1

        # Offset filter (wal_pos > last committed offset)
        conditions.append(f"wal_pos > ${param_idx}")
        params.append(offset)
        param_idx += 1

        # Consolidation status filter
        conditions.append("(consolidation_status IS NULL OR consolidation_status = 'PENDING')")

        # Embedding ready filter
        if self.config.require_embedding_ready:
            conditions.append(f"embedding_status = ${param_idx}")
            params.append("READY")
            param_idx += 1

        # Archived filter
        if self.config.exclude_archived:
            conditions.append("(archival_status IS NULL OR archival_status = '')")

        where_clause = " AND ".join(conditions)

        # Build full query
        # Note: content_type doesn't exist in DB schema - use activity_category instead
        # Note: emotions_json renamed to dominant_emotions_json in DB
        query = f"""
            SELECT
                event_id,
                wal_pos,
                cognitive_trace_id,
                tenant_id,
                space_id,
                topic,
                text,
                simhash_hex,
                activity_category as content_type,
                activity_type,
                -- UltraBERT 12-type INGRESS + 8-type INTENT (Issue 0060)
                activity_type_ultrabert,
                activity_type_confidence,
                intent_ultrabert,
                intent_confidence,
                embedding_id,
                embedding_status,
                sentiment_score,
                sentiment_label,
                dominant_emotions_json as emotions_json,
                intent_category,
                ner_entities_json,
                temporal_json,
                salience_score,
                salience_band,
                novelty_score,
                -- Issue 1 Fix: Add affect fields for R1 importance scoring
                affect_valence,
                affect_arousal,
                -- Temporal fields for R2 clustering
                event_time_utc,
                created_at,
                -- Social context fields for R4 social extraction
                participants_json,
                num_participants,
                social_context,
                social_intimacy,
                is_solo_event,
                location_name,
                location_type,
                geohash_6,
                actor_id,
                -- UltraBERT relationship types for R4 relationship inference
                extracted_relations_json,
                -- Issue 7.6: Temporal and modality context for st_observations
                time_of_day_bucket,
                circadian_slot,
                is_weekend,
                day_of_week,
                ingress_channel,
                ingress_source,
                device_kind,
                -- M3 (0073): MW v2 cognitive signal columns
                narrative_thread_id,
                narrative_arc_position,
                narrative_is_goal_event,
                intent_type,
                goal_context,
                source_type,
                novelty,
                elaboration_depth,
                identity_domains_json,
                entity_salience_json,
                k1_signal_version,
                affect_dominance,
                temporal_mentioned_time,
                temporal_resolved_epoch_ms,
                temporal_orientation,
                participant_relationships_json,
                cognitive_trace_id,
                -- M5A (0074): New cognitive signal columns
                surprise_level,
                identity_relevance,
                source_reliability,
                memory_tier,
                temporal_anchor_json
            FROM st_hipp_events
            WHERE {where_clause}
            ORDER BY wal_pos ASC
            LIMIT ${param_idx}
        """
        params.append(self.config.batch_size)

        # Execute query via syscalls
        async with ctx.syscalls.unit_of_work() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            # Debug: Check database info
            db_name = await conn.fetchval("SELECT current_database()")
            table_count = await conn.fetchval(
                "SELECT COUNT(*) FROM st_hipp_events WHERE tenant_id = $1 AND space_id = $2",
                tenant_id,
                space_id,
            )
            logger.info(
                "R0: Database connection info",
                extra={
                    "database": db_name,
                    "total_events_for_tenant_space": table_count,
                    "query_params": [tenant_id, space_id, offset],
                    "batch_size": self.config.batch_size,
                },
            )

            logger.debug(
                "R0: Executing eligible events query",
                extra={
                    "query_params": params,
                    "batch_size": self.config.batch_size,
                },
            )
            rows = await conn.fetch(query, *params)
            logger.info(
                "R0: Query returned rows",
                extra={"row_count": len(rows)},
            )

        # Convert rows to P03EventState
        events: List[P03EventState] = []
        for row in rows:
            event = self._row_to_event_state(row)
            events.append(event)

        return events

    def _row_to_event_state(self, row: Any) -> P03EventState:
        """
        Convert database row to P03EventState.

        Args:
            row: asyncpg Record from st_hipp_events

        Returns:
            P03EventState populated with row data
        """
        # Convert event_time_utc from seconds to milliseconds for P03
        # P03 expects timestamps in milliseconds, but st_hipp_events stores seconds
        event_time_seconds = row.get("event_time_utc") or row.get("created_at") or 0
        event_time_ms = (
            event_time_seconds * 1000 if event_time_seconds < 1e12 else event_time_seconds
        )

        return P03EventState(
            event_id=row["event_id"],
            hipp_event_id=row["event_id"],  # Same in current schema
            content_text=row.get("text") or "",
            content_type=row.get("content_type") or "",
            simhash_hex=row.get("simhash_hex") or "",
            timestamp=event_time_ms,
            channel_id=row.get("topic") or "",
            embedding_id=row.get("embedding_id") or "",
            sentiment_score=float(row.get("sentiment_score") or 0.0),
            sentiment_label=row.get("sentiment_label") or "neutral",
            emotions_json=row.get("emotions_json") or "[]",
            # Use UltraBERT intent classification, fallback to legacy intent_category
            intent_label=row.get("intent_ultrabert") or row.get("intent_category") or "",
            ner_entities_json=row.get("ner_entities_json") or "[]",
            temporal_expressions_json=row.get("temporal_json") or "[]",
            # Issue 1 Fix: Map affect and salience fields for R1 importance scoring
            affect_valence=float(row.get("affect_valence") or 0.0),
            affect_arousal=float(row.get("affect_arousal") or 0.0),
            salience_score=float(row.get("salience_score") or 0.0),
            salience_band=row.get("salience_band") or "",
            novelty_score=float(row.get("novelty_score") or 0.0),
            # Social context fields for R4 social extraction
            participants_json=row.get("participants_json") or "[]",
            num_participants=int(row.get("num_participants") or 0),
            social_context=row.get("social_context") or "",
            social_intimacy=row.get("social_intimacy") or "",
            is_solo_event=row.get("is_solo_event"),
            location_name=row.get("location_name") or "",
            location_type=row.get("location_type") or "",
            geohash_6=row.get("geohash_6") or "",
            activity_type=row.get("activity_type") or "",
            actor_id=row.get("actor_id") or "",
            # UltraBERT 12-type INGRESS + 8-type INTENT (Issue 0060)
            activity_type_ultrabert=row.get("activity_type_ultrabert") or "",
            activity_type_confidence=float(row.get("activity_type_confidence") or 0.0),
            intent_ultrabert=row.get("intent_ultrabert") or "",
            intent_confidence=float(row.get("intent_confidence") or 0.0),
            # UltraBERT relationship types for R4
            extracted_relations_json=row.get("extracted_relations_json") or "[]",
            # Issue 7.6: Temporal and modality context for st_observations
            time_of_day_bucket=row.get("time_of_day_bucket") or "",
            circadian_slot=row.get("circadian_slot") or "",
            is_weekend=row.get("is_weekend"),
            day_of_week=row.get("day_of_week") or "",
            ingress_channel=row.get("ingress_channel") or "",
            ingress_source=row.get("ingress_source") or "",
            device_kind=row.get("device_kind") or "",
            # M3 (0073): MW v2 cognitive signal columns
            narrative_thread_id=row.get("narrative_thread_id") or "",
            narrative_arc_position=row.get("narrative_arc_position") or "",
            narrative_is_goal_event=bool(row.get("narrative_is_goal_event") or False),
            intent_type=row.get("intent_type") or "",
            goal_context=row.get("goal_context") or "",
            source_type=row.get("source_type") or "",
            novelty=row.get("novelty") or "",
            elaboration_depth=row.get("elaboration_depth") or "",
            identity_domains_json=row.get("identity_domains_json") or "[]",
            entity_salience_json=row.get("entity_salience_json") or "{}",
            k1_signal_version=row.get("k1_signal_version") or "2.0",
            affect_dominance=float(row.get("affect_dominance") or 0.0),
            temporal_mentioned_time=row.get("temporal_mentioned_time") or "",
            temporal_resolved_epoch_ms=float(row.get("temporal_resolved_epoch_ms") or 0.0),
            temporal_orientation=row.get("temporal_orientation") or "",
            participant_relationships_json=row.get("participant_relationships_json") or "[]",
            cognitive_trace_id=row.get("cognitive_trace_id") or "",
            # M5A (0074): New cognitive signal columns
            surprise_level=float(row.get("surprise_level") or 0.0),
            identity_relevance=float(row.get("identity_relevance") or 0.0),
            source_reliability=float(row.get("source_reliability") or 1.0),
            memory_tier=row.get("memory_tier") or "routine",
            temporal_anchor_json=row.get("temporal_anchor_json") or "{}",
            # Store wal_pos for offset tracking
            # Note: P03EventState doesn't have wal_pos field directly,
            # but we track via hipp_event_id and context.event_ids
        )

    async def _load_embeddings_for_events(
        self,
        ctx: "P03RunnerContext",
        events: List[P03EventState],
    ) -> int:
        """
        Load embeddings from st_vec and materialize into event states.

        Fetches 768-dim vectors from st_vec for events that have embedding_id,
        then calls materialize_embedding() on each P03EventState.

        This enables R2 episodic clustering to use semantic similarity.

        Args:
            ctx: Runner context with syscalls
            events: List of P03EventState to load embeddings for

        Returns:
            Number of embeddings successfully loaded
        """
        if not events:
            return 0

        # Collect event_ids that have embedding_ids
        event_id_to_state: Dict[str, P03EventState] = {}
        for event in events:
            if event.embedding_id:
                event_id_to_state[event.event_id] = event

        if not event_id_to_state:
            logger.debug("R0: No events with embedding_id to load")
            return 0

        # Query st_vec for vectors by event_id
        # Build IN clause for event_ids
        event_ids = list(event_id_to_state.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(event_ids))])

        query = f"""
            SELECT event_id, vector, vector_dim
            FROM st_vec
            WHERE event_id IN ({placeholders})
              AND status IN ('READY', 'INDEXED')
        """

        loaded_count = 0

        try:
            async with ctx.syscalls.unit_of_work() as uow:
                conn = uow._connection
                if conn is None:
                    raise RuntimeError("UnitOfWork connection not initialized")

                rows = await conn.fetch(query, *event_ids)

                for row in rows:
                    event_id = row["event_id"]
                    vector_bytes = row["vector"]
                    vector_dim = row["vector_dim"]

                    if event_id not in event_id_to_state:
                        continue

                    event = event_id_to_state[event_id]

                    # Validate and decode vector
                    if not vector_bytes:
                        logger.warning(
                            "R0: Empty vector bytes for event",
                            extra={"event_id": event_id},
                        )
                        continue

                    expected_bytes = vector_dim * 4  # 4 bytes per float32
                    if len(vector_bytes) != expected_bytes:
                        logger.warning(
                            "R0: Invalid vector size",
                            extra={
                                "event_id": event_id,
                                "expected_bytes": expected_bytes,
                                "actual_bytes": len(vector_bytes),
                            },
                        )
                        continue

                    try:
                        # Unpack vector from bytes (768 floats x 4 bytes = 3072 bytes)
                        vector = list(struct.unpack(f"{vector_dim}f", vector_bytes))
                        event.materialize_embedding(vector)
                        loaded_count += 1
                    except (struct.error, ValueError) as e:
                        logger.warning(
                            "R0: Failed to decode vector",
                            extra={"event_id": event_id, "error": str(e)},
                        )
                        continue

        except Exception as e:
            logger.warning(
                "R0: Failed to load embeddings from st_vec",
                extra={"error": str(e), "event_count": len(event_ids)},
            )
            # Non-fatal - R2 will skip if no embeddings

        return loaded_count

    def _build_envelope(
        self,
        tenant_id: str,
        space_id: str,
        events: List[P03EventState],
        start_offset: int,
    ) -> P03BatchEnvelope:
        """
        Build P03BatchEnvelope from selected events.

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier
            events: List of selected events
            start_offset: Offset at batch start

        Returns:
            P03BatchEnvelope ready for R1-R8 processing
        """
        # Extract event IDs for context
        event_ids = [e.event_id for e in events]

        # Create immutable cycle context
        context = P03CycleContext.create(
            tenant_id=tenant_id,
            space_id=space_id,
            event_ids=event_ids,
            trigger_type="BATCH",
            trigger_reason=f"R0 selected {len(events)} events after offset {start_offset}",
            pending_before=len(events),  # Simplified - could query actual pending
            qos_band=self.config.batch_size <= 50 and "GREEN" or "AMBER",
        )

        # Create envelope with factory
        envelope = P03BatchEnvelope.create(
            context=context,
            events=events,
        )

        return envelope

    def should_skip(
        self,
        tenant_id: str,
        space_id: str,
        ctx: "P03RunnerContext",
    ) -> Tuple[bool, str]:
        """
        Check if R0 should be skipped.

        R0 is never skipped - it's the entry point.
        This method exists for protocol compliance.

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier
            ctx: Runner context

        Returns:
            Always (False, "")
        """
        return False, ""

    def idempotency_key(
        self,
        tenant_id: str,
        space_id: str,
    ) -> str:
        """
        Generate idempotency key for R0.

        Note: R0 idempotency is based on input parameters,
        not envelope (which doesn't exist yet).

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            Idempotency key string
        """
        return f"p03:r0:{tenant_id}:{space_id}"
        return f"p03:r0:{tenant_id}:{space_id}"
        return f"p03:r0:{tenant_id}:{space_id}"
        return f"p03:r0:{tenant_id}:{space_id}"
        return f"p03:r0:{tenant_id}:{space_id}"
        return f"p03:r0:{tenant_id}:{space_id}"
