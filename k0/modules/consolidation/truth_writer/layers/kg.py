"""
KGLayerWriter — Issue 5.2.8

Writer for st_kg_dom (entities) and st_kg_edges (relationships) layers.
Handles knowledge graph persistence from M21 KGConsolidator.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.8 — st_kg_dom / st_kg_edges layer writer)
    - Dossier §4.8.7 (st_kg_dom / st_kg_edges Writes)

Operations for st_kg_dom (entities):
    INSERT: Create new entity
    UPDATE with Actions:
        - EXTEND: Update attributes, boost confidence
        - EVOLVE: Mark old entity invalid (temporal versioning)
    ARCHIVE: Soft-delete low-confidence entity

Operations for st_kg_edges (edges):
    INSERT: Create new edge
    UPDATE: Update confidence/attributes
    ARCHIVE: Soft-delete low-confidence edge

Supports:
    - Entity merge tracking in st_entity_merges
    - Granger causality CAUSES edges with precedence_ratio
    - Temporal validity (valid_from/valid_to)
    - Binary embedding vectors

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.modules.consolidation.truth_writer.observation_recorder import (
    ObservationRecorder,
    get_observation_recorder,
)
from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.modules.consolidation.truth_writer.text_vector_coordinator import (
    TextVectorCoordinator,
    get_coordinator,
)
from k0.pipelines.p03.phases.r7_truth_writer import OptimisticLockError
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    StagedWrite,
    WriteOperation,
)

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


def _normalize_json(value: Any, default: str = "[]") -> str:
    """Normalize a value to a valid JSON string.

    Handles cases where a Python dict/list was accidentally passed instead of
    a JSON-serialized string. PostgreSQL JSON columns require valid JSON strings.

    Args:
        value: The value to normalize (str, dict, list, or None)
        default: Default JSON string if value is None or empty

    Returns:
        A valid JSON string
    """
    if value is None:
        return default
    if isinstance(value, str):
        # Already a string - verify it's valid JSON or return as-is
        if not value or value in ("[]", "{}"):
            return value
        # Try to parse to validate, if invalid return default
        try:
            json.loads(value)
            return value
        except (json.JSONDecodeError, TypeError):
            # Invalid JSON string - log and return default
            logger.warning(f"Invalid JSON string detected, using default: {value!r}")
            return default
    if isinstance(value, (dict, list)):
        # Convert Python object to JSON string
        return json.dumps(value)
    # Fallback: convert to string and wrap
    return json.dumps(str(value))


class EntityAction(str, Enum):
    """
    Actions for entity updates.

    EXTEND: Update attributes, boost confidence
    EVOLVE: Mark old entity invalid for temporal versioning
    """

    EXTEND = "EXTEND"
    EVOLVE = "EVOLVE"


@dataclass
class EntityWriteData:
    """
    Data structure for st_kg_dom (entity) writes.

    Represents a knowledge graph entity.

    Attributes:
        entity_id: Unique entity identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        entity_type: Type (PERSON, LOCATION, EVENT, etc.)
        canonical_name: Canonical entity name
        attributes_json: JSON object with entity attributes
        embedding: Binary embedding vector (optional)
        confidence: Confidence score [0.0, 1.0]
        valid_from_ms: Temporal validity start (MILLISECONDS)
        valid_to_ms: Temporal validity end (MILLISECONDS, optional)
        source_events_json: JSON array of contributing event IDs
    """

    entity_id: str
    tenant_id: str
    space_id: str
    entity_type: str = "UNKNOWN"
    canonical_name: str = ""
    attributes_json: str = "{}"
    embedding: Optional[bytes] = None
    confidence: float = 1.0
    valid_from_ms: int = 0
    valid_to_ms: Optional[int] = None
    source_events_json: str = "[]"

    # GAP-001: Inline vector and text preservation fields
    source_texts_json: Optional[str] = None  # JSON array of source event texts
    embedding_text: Optional[str] = None  # Generated text for UltraBERT embedding
    embedding_vector: Optional[bytes] = None  # 768-dim float32 as BYTEA (3072 bytes)
    embedding_model: Optional[str] = None  # Model version (e.g., "ultrabert-v2.1.0")


@dataclass
class EdgeWriteData:
    """
    Data structure for st_kg_edges (edge) writes.

    Represents a knowledge graph edge (relationship).

    Attributes:
        edge_id: Unique edge identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        source_entity_id: Source entity ID
        target_entity_id: Target entity ID
        relation_type: Type (KNOWS, LOCATED_AT, CAUSES, etc.)
        confidence: Confidence score [0.0, 1.0]
        valid_from_ms: Temporal validity start (MILLISECONDS)
        valid_to_ms: Temporal validity end (MILLISECONDS, optional)
        precedence_ratio: For Granger causality CAUSES edges (optional)
        attributes_json: JSON object with edge attributes
        source_algorithm: Algorithm that created this edge (GAP-007)
        evidence_event_ids: Array of source event IDs (GAP-007)
        evidence_episode_ids: Array of source episode IDs (GAP-007)
        algorithm_params_json: Algorithm-specific parameters (GAP-007)
        inference_chain_json: For transitive closure - path taken (GAP-007)
    """

    edge_id: str
    tenant_id: str
    space_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str = "RELATED_TO"
    confidence: float = 1.0
    valid_from_ms: int = 0
    valid_to_ms: Optional[int] = None
    precedence_ratio: Optional[float] = None  # For CAUSES edges
    attributes_json: str = "{}"
    # GAP-007: Edge provenance tracking
    source_algorithm: str = "co_occurrence"
    evidence_event_ids: Optional[List[str]] = None
    evidence_episode_ids: Optional[List[str]] = None
    algorithm_params_json: Optional[str] = None
    inference_chain_json: Optional[str] = None


class KGLayerWriter:
    """
    Writer for st_kg_dom (entities) and st_kg_edges (relationships) layers.

    This is a dual-layer writer that handles both entity and edge tables.

    Tables:
        st_kg_dom: Entity table (PK: entity_id)
        st_kg_edges: Edge table (PK: edge_id)
        st_entity_merges: Merge tracking table

    Version Column: version (for optimistic locking)

    Action-Based Entity Updates:
        EXTEND: Merge attributes, boost confidence
        EVOLVE: Mark entity as superseded (set valid_to)

    Edge Updates:
        Direct confidence and attribute updates

    Usage:
        writer = KGLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    # Layers handled by this writer
    LAYERS = (LAYER_ST_KG_DOM, LAYER_ST_KG_EDGES)

    # Confidence boost factor for EXTEND (multiplicative, capped at 1.0)
    EXTEND_BOOST = 1.1

    def __init__(
        self,
        coordinator: Optional[TextVectorCoordinator] = None,
        observation_recorder: Optional[ObservationRecorder] = None,
    ) -> None:
        """
        Initialize KGLayerWriter.

        Args:
            coordinator: Optional TextVectorCoordinator for GAP-001 embedding generation.
                        If not provided, uses singleton via get_coordinator().
            observation_recorder: ObservationRecorder for holistic context (uses singleton if None)
        """
        self._coordinator = coordinator
        self._observation_recorder = observation_recorder

    def _get_coordinator(self) -> TextVectorCoordinator:
        """Get coordinator, initializing singleton if needed."""
        if self._coordinator is None:
            self._coordinator = get_coordinator()
        return self._coordinator

    def _get_recorder(self) -> ObservationRecorder:
        """Get observation recorder, using singleton if not injected."""
        if self._observation_recorder is None:
            self._observation_recorder = get_observation_recorder()
        return self._observation_recorder

    def _extract_context(self, write: StagedWrite) -> Optional[ObservationContext]:
        """
        Extract observation context from StagedWrite.

        Returns the attached observation_context if present, otherwise
        builds a minimal context from record_data.
        """
        if write.observation_context is not None:
            return write.observation_context

        data = write.record_data
        observed_at = data.get("created_at") or data.get("valid_from_ms") or _now_ms()

        return ObservationContext(
            observed_at=observed_at,
            source_event_id=write.source_event_ids[0] if write.source_event_ids else None,
        )

    @property
    def layers(self) -> tuple[str, str]:
        """Target layer names (entities and edges)."""
        return self.LAYERS

    async def write(
        self,
        writes: List[StagedWrite],
        uow: UnitOfWork,
    ) -> LayerWriteResult:
        """
        Execute KG layer writes (both entities and edges).

        Routes writes to entity or edge handlers based on layer.
        Continues processing on failure to maximize partial success.

        Args:
            writes: List of StagedWrite objects for KG layers
            uow: UnitOfWork providing database connection

        Returns:
            LayerWriteResult with combined success/failure counts
        """
        succeeded = 0
        failed_ids: List[str] = []
        error_messages: List[str] = []

        for write in writes:
            try:
                if write.layer == LAYER_ST_KG_DOM:
                    await self._write_entity(uow, write)
                    succeeded += 1
                elif write.layer == LAYER_ST_KG_EDGES:
                    await self._write_edge(uow, write)
                    succeeded += 1
                # Ignore writes for other layers
            except OptimisticLockError:
                failed_ids.append(write.record_id)
                error_messages.append(f"Version conflict for KG record {write.record_id}")
            except Exception as e:
                failed_ids.append(write.record_id)
                error_messages.append(f"Failed to write {write.record_id}: {e}")

        # Count writes for this writer's layers
        kg_writes = [w for w in writes if w.layer in self.LAYERS]

        return LayerWriteResult(
            layer="kg",  # Combined layer name for dual-table writer
            writes_attempted=len(kg_writes),
            writes_succeeded=succeeded,
            writes_failed=len(failed_ids),
            failed_ids=failed_ids,
            error_message="; ".join(error_messages) if error_messages else None,
        )

    # ─────────────────────────────────────────────────────────────────
    # Entity (st_kg_dom) Operations
    # ─────────────────────────────────────────────────────────────────

    async def _write_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """Route entity write to appropriate handler."""
        if write.operation == WriteOperation.INSERT:
            await self._insert_entity(uow, write)
        elif write.operation == WriteOperation.UPDATE:
            await self._update_entity(uow, write)
        elif write.operation == WriteOperation.ARCHIVE:
            await self._archive_entity(uow, write)
        elif write.operation == WriteOperation.TOMBSTONE:
            await self._tombstone_entity(uow, write)

    async def _insert_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        INSERT new entity into st_kg_dom.

        Creates a new entity record with initial values.
        Uses ON CONFLICT DO NOTHING for idempotency.

        GAP-001: Fetches source texts from source_events_json and generates embedding.
        """

        data = write.record_data
        now = _now_ms()
        last_observed_at = data.get("last_observed_at") or data.get("valid_from_ms", now)

        # GAP-001: Fetch source texts and generate embedding
        # st_kg_dom uses source_episodes_json (or source_events_json legacy)
        source_texts_json: Optional[str] = None
        embedding_text: Optional[str] = None
        embedding_vector: Optional[bytes] = None
        embedding_model: Optional[str] = None

        try:
            # Support both source_episodes_json (new) and source_events_json (legacy)
            source_episodes = data.get("source_episodes_json") or data.get(
                "source_events_json", "[]"
            )
            if isinstance(source_episodes, list):
                event_ids = [str(eid) for eid in source_episodes]
            elif source_episodes and source_episodes != "[]":
                parsed = json.loads(source_episodes)
                event_ids = [str(eid) for eid in parsed] if isinstance(parsed, list) else []
            else:
                event_ids = []

            if event_ids:
                coordinator = self._get_coordinator()
                tv_result = await coordinator.process(
                    layer="st_kg_dom",
                    record_data=data,
                    source_event_ids=event_ids,
                    conn=uow.connection,
                )
                source_texts_json = tv_result.source_texts_json
                embedding_text = tv_result.embedding_text
                embedding_vector = tv_result.embedding_vector
                embedding_model = tv_result.embedding_model
            elif data.get("canonical_name"):
                # Fallback: use canonical_name if no source episodes
                coordinator = self._get_coordinator()
                tv_result = await coordinator.process_without_fetch(
                    layer="st_kg_dom",
                    record_data=data,
                    source_texts=[data["canonical_name"]],
                )
                embedding_text = tv_result.embedding_text
                embedding_vector = tv_result.embedding_vector
                embedding_model = tv_result.embedding_model
        except Exception:
            # Non-fatal: log but continue with INSERT
            pass

        await uow.connection.execute(
            """
            INSERT INTO st_kg_dom (
                entity_id, tenant_id, space_id, entity_type, entity_subtype,
                canonical_name, aliases_json, attributes_json, embedding_id,
                confidence_score, observation_count, valid_from, valid_to,
                source_episodes_json, first_mentioned_event_id, last_observed_at, decay_factor,
                created_at, updated_at, version,
                archival_status,
                -- GAP-001: Inline vector and text preservation columns
                source_texts_json, embedding_text, embedding_vector, embedding_model
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $18, 1,
                      'ACTIVE',
                      $19, $20, $21, $22)
            ON CONFLICT (entity_id) DO NOTHING
            """,
            data["entity_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("entity_type", "UNKNOWN"),
            data.get("entity_subtype"),  # GAP-005: Fine-grained subtype
            data.get("canonical_name", ""),
            _normalize_json(data.get("aliases_json"), "[]"),
            _normalize_json(data.get("attributes_json"), "{}"),
            data.get("embedding_id"),
            data.get("confidence_score", data.get("confidence", 1.0)),
            data.get("observation_count", 1),
            data.get("valid_from_ms", now),
            data.get("valid_to_ms"),
            _normalize_json(data.get("source_episodes_json", data.get("source_events_json")), "[]"),
            data.get("first_mentioned_event_id"),
            last_observed_at,
            data.get("decay_factor", 1.0),
            now,
            # GAP-001 fields
            source_texts_json,
            embedding_text,
            embedding_vector,
            embedding_model,
        )

        # Issue 7.5: Record observation with FIRST_SEEN type
        context = self._extract_context(write)
        if context is not None:
            context.observation_type = "FIRST_SEEN"
            try:
                await self._get_recorder().record(
                    uow=uow,
                    layer=LAYER_ST_KG_DOM,
                    record_id=write.record_id,
                    context=context,
                    tenant_id=data["tenant_id"],
                )
            except Exception as e:
                logger.warning(
                    "Failed to record observation for %s: %s",
                    write.record_id,
                    e,
                )

    async def _update_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        UPDATE existing entity.

        Handles:
            - query_count_increment: Increment query_count and update last_queried_at
            - milestone_append: Append milestone to milestones_json
            - observation_count_increment: REINFORCE existing entity (Issue 3 Fix)
            - _action EXTEND: Update attributes, boost confidence
            - _action EVOLVE: Mark old entity invalid

        Raises OptimisticLockError if version mismatch (for EVOLVE).
        """
        data = write.record_data

        # Handle special intent signal fields first
        if "query_count_increment" in data:
            await self._update_entity_query_boost(uow, write)
            return

        if "milestone_append" in data:
            await self._update_entity_milestone(uow, write)
            return

        # Issue 3 Fix: Handle REINFORCE operations (entity matching)
        if "observation_count_increment" in data:
            await self._update_entity_reinforce(uow, write)
            return

        # Standard action-based handling
        action = data.get("_action", "EXTEND")

        if action == EntityAction.EVOLVE or action == "EVOLVE":
            await self._update_entity_evolve(uow, write)
        else:
            # Default to EXTEND for unknown actions
            await self._update_entity_extend(uow, write)

    async def _update_entity_query_boost(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        QUERY_BOOST: Increment query_count and update last_queried_at.

        Used by IntentSignalAssembler for QUERY_BOOST signals.
        Skips version check since this is a low-priority update.
        """
        data = write.record_data
        increment = data.get("query_count_increment", 1)
        last_queried_at = data.get("last_queried_at", _now_ms())

        await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET query_count = COALESCE(query_count, 0) + $1,
                last_queried_at = $2
            WHERE entity_id = $3
            """,
            increment,
            last_queried_at,
            write.record_id,
        )

    async def _update_entity_milestone(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        MILESTONE: Append milestone entry to milestones_json.

        Used by IntentSignalAssembler for MILESTONE signals.
        Uses jsonb_insert to append to existing array.
        """
        data = write.record_data
        milestone_entry = data.get("milestone_append", {})

        milestone_json = json.dumps(milestone_entry)

        # Append milestone to milestones_json array
        # Initialize array if null
        await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET milestones_json = COALESCE(milestones_json::jsonb, '[]'::jsonb) || $1::jsonb,
                updated_at = $2
            WHERE entity_id = $3
            """,
            milestone_json,
            _now_ms(),
            write.record_id,
        )

    async def _update_entity_reinforce(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        REINFORCE: Increment observation_count and merge new source events.

        Issue 3 Fix: When R4 detects an entity already exists in st_kg_dom,
        it generates an UPDATE with observation_count_increment to reinforce
        the entity instead of creating a duplicate.

        This is the same pattern as Issue 2 fix for st_epi episodes.

        Updates:
            - observation_count: Incremented by observation_count_increment
            - source_episodes_json: Appends new event IDs (deduped via DISTINCT)
            - aliases_json: Merges new aliases
            - updated_at: Current timestamp
            - version: Incremented for consistency
        """

        data = write.record_data
        increment = data.get("observation_count_increment", 1)
        now = _now_ms()

        # Parse additional source event IDs
        additional_event_ids = data.get("additional_source_event_ids", "[]")
        if isinstance(additional_event_ids, str):
            try:
                additional_event_ids = json.loads(additional_event_ids)
            except json.JSONDecodeError:
                additional_event_ids = []

        # Parse new aliases
        new_aliases = data.get("new_aliases_json", "[]")
        if isinstance(new_aliases, str):
            try:
                new_aliases = json.loads(new_aliases)
            except json.JSONDecodeError:
                new_aliases = []

        # Build JSON arrays for PostgreSQL
        additional_events_json = json.dumps(additional_event_ids)
        new_aliases_json = json.dumps(new_aliases)
        last_observed_at = data.get("last_observed_at", now)
        decay_factor = data.get("decay_factor", 1.0)

        await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET observation_count = COALESCE(observation_count, 0) + $1,
                -- Merge source episodes (dedupe via DISTINCT)
                source_episodes_json = (
                    SELECT jsonb_agg(DISTINCT elem)::text
                    FROM (
                        SELECT jsonb_array_elements(COALESCE(source_episodes_json::jsonb, '[]'::jsonb)) AS elem
                        UNION ALL
                        SELECT jsonb_array_elements($2::jsonb)
                    ) AS combined(elem)
                ),
                -- Merge aliases (dedupe via DISTINCT)
                aliases_json = (
                    SELECT jsonb_agg(DISTINCT elem)::text
                    FROM (
                        SELECT jsonb_array_elements(COALESCE(aliases_json::jsonb, '[]'::jsonb)) AS elem
                        UNION ALL
                        SELECT jsonb_array_elements($3::jsonb)
                    ) AS combined(elem)
                ),
                last_observed_at = COALESCE($4, last_observed_at),
                decay_factor = COALESCE($5, decay_factor),
                updated_at = $6,
                version = version + 1
            WHERE entity_id = $7
            """,
            increment,
            additional_events_json,
            new_aliases_json,
            last_observed_at,
            decay_factor,
            now,
            write.record_id,
        )
        # Issue 7.5: Record observation with REINFORCEMENT type
        context = self._extract_context(write)
        if context is not None:
            context.observation_type = "REINFORCEMENT"
            try:
                await self._get_recorder().record(
                    uow=uow,
                    layer=LAYER_ST_KG_DOM,
                    record_id=write.record_id,
                    context=context,
                    tenant_id=data.get("tenant_id", "unknown"),
                )
            except Exception as e:
                logger.warning(
                    "Failed to record reinforcement observation for %s: %s",
                    write.record_id,
                    e,
                )

    async def _update_entity_extend(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """EXTEND: Update attributes, merge events, boost confidence."""
        data = write.record_data
        now = _now_ms()
        result = await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET attributes_json = COALESCE(attributes_json, '{}')::jsonb || COALESCE($1::jsonb, '{}'::jsonb),
                source_episodes_json = COALESCE(source_episodes_json, '[]')::jsonb || COALESCE($2::jsonb, '[]'::jsonb),
                confidence_score = LEAST(COALESCE(confidence_score, 0.5) * $3, 1.0),
                last_observed_at = COALESCE($4, last_observed_at),
                decay_factor = COALESCE($5, decay_factor),
                updated_at = $6,
                version = version + 1
            WHERE entity_id = $7
            """,
            data.get("new_attributes_json", "{}"),
            data.get("new_events_json", data.get("new_episodes_json", "[]")),
            self.EXTEND_BOOST,
            data.get("last_observed_at"),
            data.get("decay_factor"),
            now,
            write.record_id,
        )

        if result == "UPDATE 0":
            # Entity doesn't exist - this is a data consistency issue but not fatal
            # The entity may have been merged/archived during consolidation
            pass

    async def _update_entity_evolve(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """EVOLVE: Mark old entity as superseded (set valid_to)."""
        now = _now_ms()
        result = await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET valid_to = $1,
                is_canonical = FALSE,
                updated_at = $2,
                version = version + 1
            WHERE entity_id = $3 AND version = $4
            """,
            now,
            now,
            write.record_id,
            write.expected_version,
        )

        if result == "UPDATE 0":
            raise OptimisticLockError(f"Version conflict evolving entity {write.record_id}")

    async def _archive_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """ARCHIVE low-confidence entity."""
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET archival_status = 'ARCHIVED',
                                updated_at = $1,
                                valid_to = $1
            WHERE entity_id = $2
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
            """,
            now,
            write.record_id,
        )

    async def _tombstone_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """TOMBSTONE entity for GDPR deletion."""
        now = _now_ms()
        await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET canonical_name = '',
                attributes_json = '{}',
                embedding_vector = NULL,
                embedding_text = NULL,
                source_episodes_json = '[]',
                archival_status = 'TOMBSTONE',
                updated_at = $1,
                valid_to = $1
            WHERE entity_id = $2
            """,
            now,
            write.record_id,
        )

    # ─────────────────────────────────────────────────────────────────
    # Edge (st_kg_edges) Operations
    # ─────────────────────────────────────────────────────────────────

    async def _write_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """Route edge write to appropriate handler."""
        if write.operation == WriteOperation.INSERT:
            await self._insert_edge(uow, write)
        elif write.operation == WriteOperation.UPDATE:
            await self._update_edge(uow, write)
        elif write.operation == WriteOperation.ARCHIVE:
            await self._archive_edge(uow, write)
        elif write.operation == WriteOperation.TOMBSTONE:
            await self._tombstone_edge(uow, write)

    async def _insert_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        INSERT new edge into st_kg_edges.

        Creates a new edge record. Supports Granger causality edges
        with precedence_ratio for CAUSES relation type.
        Uses ON CONFLICT DO NOTHING for idempotency.

        GAP-007: Now includes source_algorithm, evidence_event_ids,
                 evidence_episode_ids, algorithm_params_json, inference_chain_json.
        """
        data = write.record_data
        now = _now_ms()

        await uow.connection.execute(
            """
            INSERT INTO st_kg_edges (
                edge_id, tenant_id, space_id,
                source_entity_id, target_entity_id, relation_type, relation_subtype,
                properties_json,
                edge_weight, confidence_score,
                source_episodes_json, co_occurrence_count, observation_count,
                last_observed_at, decay_factor,
                valid_from, valid_to,
                source_algorithm, evidence_event_ids, evidence_episode_ids,
                algorithm_params_json, inference_chain_json,
                created_at, updated_at, version,
                archival_status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, 1, 'ACTIVE')
            ON CONFLICT (edge_id) DO NOTHING
            """,
            data["edge_id"],
            data["tenant_id"],
            data["space_id"],
            data["source_entity_id"],
            data["target_entity_id"],
            data.get("relation_type", "RELATED_TO"),
            data.get("relation_subtype"),
            data.get("properties_json", data.get("attributes_json", "{}")),
            data.get("edge_weight", data.get("weight", 1.0)),
            data.get("confidence_score", data.get("confidence", 1.0)),
            data.get("source_episodes_json", "[]"),
            data.get("co_occurrence_count", data.get("observation_count", 1)),
            data.get("observation_count", 1),
            data.get("last_observed_at", data.get("valid_from_ms", now)),
            data.get("decay_factor", 1.0),
            data.get("valid_from_ms", now),
            data.get("valid_to_ms"),
            data.get("source_algorithm", "co_occurrence"),
            data.get("evidence_event_ids"),  # TEXT[] - can be None
            data.get("evidence_episode_ids"),  # TEXT[] - can be None
            data.get("algorithm_params_json"),
            data.get("inference_chain_json"),
            now,
            now,
        )

        # Issue 7.5: Record observation with FIRST_SEEN type
        context = self._extract_context(write)
        if context is not None:
            context.observation_type = "FIRST_SEEN"
            try:
                await self._get_recorder().record(
                    uow=uow,
                    layer=LAYER_ST_KG_EDGES,
                    record_id=write.record_id,
                    context=context,
                    tenant_id=data.get("tenant_id", "unknown"),
                )
            except Exception as e:
                logger.warning(
                    "Failed to record edge observation for %s: %s",
                    write.record_id,
                    e,
                )

    async def _update_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        UPDATE edge confidence/attributes or handle special fields.

        Handles:
            - query_count_increment: Increment query_count and update last_queried_at
            - observation_count_increment: Increment observation_count (GAP-001 M9)
            - new_weight: Absolute weight update (GAP-007 weight_normalization)
            - new_evidence_event_ids: Evidence array append (GAP-007)
            - Standard confidence/attributes update

        Raises OptimisticLockError if version mismatch.
        """

        data = write.record_data

        # Handle special intent signal fields
        if "query_count_increment" in data:
            await self._update_edge_query_boost(uow, write)
            return

        # GAP-001 M9: Handle observation_count increment for Granger causality
        if "observation_count_increment" in data:
            await self._update_edge_observation_count(uow, write)
            return

        # GAP-007: Handle absolute weight updates (e.g., from weight_normalization)
        if "new_weight" in data:
            await self._update_edge_weight_absolute(uow, write)
            return

        # Standard edge update - no version check for same-cycle consolidation
        # GAP-007: Include new evidence arrays and source_algorithm
        updates = []
        params = []
        param_idx = 1

        # Confidence update
        if data.get("confidence_score") is not None or data.get("confidence") is not None:
            updates.append(f"confidence_score = COALESCE(${param_idx}, confidence_score)")
            params.append(data.get("confidence_score", data.get("confidence")))
            param_idx += 1

        # Properties/attributes merge
        if data.get("properties_json") or data.get("new_attributes_json"):
            updates.append(
                f"properties_json = COALESCE(properties_json, '{{}}')::jsonb || COALESCE(${param_idx}::jsonb, '{{}}'::jsonb)"
            )
            params.append(data.get("properties_json", data.get("new_attributes_json", "{}")))
            param_idx += 1

        # Append evidence to source_episodes_json (event IDs)
        evidence_json = data.get("new_evidence_ids_json")
        if evidence_json is None and data.get("new_evidence_event_ids") is not None:
            evidence_json = json.dumps(data.get("new_evidence_event_ids"))
        if evidence_json is not None:
            updates.append(
                f"source_episodes_json = COALESCE(source_episodes_json, '[]')::jsonb || COALESCE(${param_idx}::jsonb, '[]'::jsonb)"
            )
            params.append(evidence_json)
            param_idx += 1

        # GAP-007: Append new evidence event IDs
        if data.get("new_evidence_event_ids"):
            updates.append(
                f"evidence_event_ids = COALESCE(evidence_event_ids, ARRAY[]::TEXT[]) || ${param_idx}::TEXT[]"
            )
            params.append(data["new_evidence_event_ids"])
            param_idx += 1

        # GAP-007: Append new evidence episode IDs
        if data.get("new_evidence_episode_ids"):
            updates.append(
                f"evidence_episode_ids = COALESCE(evidence_episode_ids, ARRAY[]::TEXT[]) || ${param_idx}::TEXT[]"
            )
            params.append(data["new_evidence_episode_ids"])
            param_idx += 1

        # Temporal updates
        if data.get("last_observed_at") is not None:
            updates.append(f"last_observed_at = COALESCE(${param_idx}, last_observed_at)")
            params.append(data.get("last_observed_at"))
            param_idx += 1

        if data.get("decay_factor") is not None:
            updates.append(f"decay_factor = COALESCE(${param_idx}, decay_factor)")
            params.append(data.get("decay_factor"))
            param_idx += 1

        # GAP-007: Update source_algorithm (for enrichment attribution)
        if data.get("source_algorithm"):
            updates.append(f"source_algorithm = ${param_idx}")
            params.append(data["source_algorithm"])
            param_idx += 1

        # Always update timestamp and version
        updates.append(f"updated_at = ${param_idx}")
        params.append(_now_ms())
        param_idx += 1

        updates.append("version = version + 1")

        # Add WHERE clause
        params.append(write.record_id)
        where_clause = f"WHERE edge_id = ${param_idx}"

        if not updates:
            # No fields to update
            return

        sql = f"UPDATE st_kg_edges SET {', '.join(updates)} {where_clause}"
        result = await uow.connection.execute(sql, *params)

        if result == "UPDATE 0":
            # Edge doesn't exist - not fatal, may have been merged
            pass

    async def _update_edge_observation_count(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        GAP-001 M9: Increment observation_count and co_occurrence_count for edge.

        Used by R4 KG consolidator when edge already exists. This enables
        Granger causality to trigger once observation_count reaches threshold (5+).

        Also updates confidence and updated_at timestamp.
        Skips version check for simplicity (observation increment is additive).
        """

        data = write.record_data
        increment = data.get("observation_count_increment", 1)
        new_confidence = data.get("confidence")
        now = _now_ms()
        evidence_json = data.get("new_evidence_ids_json")
        if evidence_json is None and data.get("new_evidence_event_ids") is not None:
            evidence_json = json.dumps(data.get("new_evidence_event_ids"))
        evidence_json = evidence_json or "[]"
        last_observed_at = data.get("last_observed_at", now)
        decay_factor = data.get("decay_factor")

        await uow.connection.execute(
            """
            UPDATE st_kg_edges
            SET observation_count = COALESCE(observation_count, 0) + $1,
                co_occurrence_count = COALESCE(co_occurrence_count, 0) + $1,
                confidence_score = COALESCE($2, confidence_score),
                source_episodes_json = COALESCE(source_episodes_json, '[]')::jsonb || COALESCE($3::jsonb, '[]'::jsonb),
                last_observed_at = COALESCE($4, last_observed_at),
                decay_factor = COALESCE($5, decay_factor),
                updated_at = $6
            WHERE edge_id = $7
            """,
            increment,
            new_confidence,
            evidence_json,
            last_observed_at,
            decay_factor,
            now,
            write.record_id,
        )

        # Issue 7.5: Record observation with REINFORCEMENT type
        context = self._extract_context(write)
        if context is not None:
            context.observation_type = "REINFORCEMENT"
            try:
                await self._get_recorder().record(
                    uow=uow,
                    layer=LAYER_ST_KG_EDGES,
                    record_id=write.record_id,
                    context=context,
                    tenant_id=data.get("tenant_id", "unknown"),
                )
            except Exception as e:
                logger.warning(
                    "Failed to record edge reinforcement observation for %s: %s",
                    write.record_id,
                    e,
                )

    async def _update_edge_weight_absolute(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        GAP-007: Set absolute weight (e.g., from weight_normalization algorithm).

        Unlike standard updates which append evidence, this replaces the weight
        with a normalized value. Used by weight_normalization enricher.

        Also updates source_algorithm to track the normalizing algorithm.
        Skips version check for same-cycle consolidation.
        """
        data = write.record_data
        new_weight = data["new_weight"]
        source_algorithm = data.get("source_algorithm", "weight_normalization")
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_kg_edges
            SET edge_weight = $1,
                source_algorithm = $2,
                updated_at = $3,
                version = version + 1
            WHERE edge_id = $4
            """,
            new_weight,
            source_algorithm,
            now,
            write.record_id,
        )

        # Issue 7.5: Record observation with REINFORCEMENT type
        context = self._extract_context(write)
        if context is not None:
            context.observation_type = "REINFORCEMENT"
            try:
                await self._get_recorder().record(
                    uow=uow,
                    layer=LAYER_ST_KG_EDGES,
                    record_id=write.record_id,
                    context=context,
                    tenant_id=data.get("tenant_id", "unknown"),
                )
            except Exception as e:
                logger.warning(
                    "Failed to record weight normalization observation for %s: %s",
                    write.record_id,
                    e,
                )

    async def _update_edge_query_boost(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        QUERY_BOOST: Increment query_count and update last_queried_at for edge.

        Used by IntentSignalAssembler for QUERY_BOOST signals.
        Skips version check since this is a low-priority update.
        """
        data = write.record_data
        increment = data.get("query_count_increment", 1)
        last_queried_at = data.get("last_queried_at", _now_ms())

        await uow.connection.execute(
            """
            UPDATE st_kg_edges
            SET query_count = COALESCE(query_count, 0) + $1,
                last_queried_at = $2
            WHERE edge_id = $3
            """,
            increment,
            last_queried_at,
            write.record_id,
        )

    async def _archive_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """ARCHIVE low-confidence edge."""
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_kg_edges
            SET archival_status = 'ARCHIVED',
                updated_at = $1,
                valid_to = $1
            WHERE edge_id = $2
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
            """,
            now,
            write.record_id,
        )

    async def _tombstone_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """TOMBSTONE edge for GDPR deletion."""
        now = _now_ms()
        await uow.connection.execute(
            """
            UPDATE st_kg_edges
            SET properties_json = '{}',
                archival_status = 'TOMBSTONE',
                updated_at = $1,
                valid_to = $1
            WHERE edge_id = $2
            """,
            now,
            write.record_id,
        )

    # ─────────────────────────────────────────────────────────────────
    # Merge Tracking
    # ─────────────────────────────────────────────────────────────────

    async def track_merge(
        self,
        uow: UnitOfWork,
        source_id: str,
        target_id: str,
        merge_reason: str,
    ) -> None:
        """
        Track entity merge in st_entity_merges for undo support.

        Records that source_id was merged into target_id.
        Used by R4 EntityMerger cascade and supports future undo.

        Args:
            uow: UnitOfWork providing database connection
            source_id: Entity ID that was merged (now obsolete)
            target_id: Entity ID that absorbed the merge
            merge_reason: Reason for merge (e.g., "duplicate", "alias")
        """
        now = _now_ms()
        await uow.connection.execute(
            """
            INSERT INTO st_entity_merges (
                source_entity_id, target_entity_id,
                merge_reason, merged_at
            ) VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_entity_id, target_entity_id) DO NOTHING
            """,
            source_id,
            target_id,
            merge_reason,
            now,
        )


def create_kg_writer() -> KGLayerWriter:
    """Factory function to create KGLayerWriter instance."""
    return KGLayerWriter()
