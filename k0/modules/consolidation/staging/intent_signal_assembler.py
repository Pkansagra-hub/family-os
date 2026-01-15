"""
IntentSignalAssembler - Routes intent signals to appropriate layer writes.

This module converts IntentSignal objects (detected by IntentSignalDetector)
into StagedWrite operations for R7 commit.

Routing Matrix (GAP-001):
    ReminderSignal  → st_prospective INSERT (intention_type='REMINDER')
    DecisionSignal  → st_prospective INSERT (intention_type='DECISION')
    LessonSignal    → st_sem INSERT (pattern_type='LESSON')
    EmotionalSignal → st_sem INSERT (pattern_type='EMOTIONAL_TREND')
    MilestoneSignal → st_kg_dom UPDATE (milestones_json append)
    QueryBoostSignal→ st_kg_dom/st_kg_edges UPDATE (query_count increment)

Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 4
GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import time
from typing import Dict, List, Tuple

from k0.modules.consolidation.dream.intent_signals import (
    DecisionSignal,
    EmotionalSignal,
    IntentSignal,
    IntentSignalType,
    LessonSignal,
    MilestoneSignal,
    QueryBoostSignal,
    ReminderSignal,
)
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    StagedWrite,
)


def _now_ms() -> int:
    """Return current time in milliseconds since epoch."""
    return int(time.time() * 1000)


def _generate_ulid() -> str:
    """Generate ULID for record IDs."""
    from k0.pipelines.p03.context import generate_ulid

    return generate_ulid()


class IntentSignalAssembler:
    """
    Assembles StagedWrites from IntentSignals.

    Called by R6Coordinator to convert intent signals detected by R5
    into staged writes for truth layers.

    Example:
        >>> assembler = IntentSignalAssembler(
        ...     tenant_id="tenant-1",
        ...     space_id="space-1",
        ...     actor_id="user-1",
        ... )
        >>> signals = [ReminderSignal(...), LessonSignal(...)]
        >>> writes_by_layer = assembler.assemble_all(signals)
        >>> # writes_by_layer = {"st_prospective": [...], "st_sem": [...]}
    """

    # Use R6 to match manifest validator's expected format
    SOURCE_PHASE = "R6"

    def __init__(
        self,
        tenant_id: str,
        space_id: str,
        actor_id: str = "",
    ) -> None:
        """
        Initialize assembler with context.

        Args:
            tenant_id: Tenant identifier for multi-tenant isolation
            space_id: Space identifier for family/user isolation
            actor_id: Actor identifier for provenance
        """
        self.tenant_id = tenant_id
        self.space_id = space_id
        self.actor_id = actor_id

    def assemble_all(
        self,
        signals: List[IntentSignal],
    ) -> Dict[str, List[StagedWrite]]:
        """
        Convert all intent signals to staged writes.

        Routes each signal to appropriate layer based on signal_type.
        Deduplicates writes by (layer, record_id) to prevent manifest
        validation failures from duplicate record_ids.

        Args:
            signals: List of IntentSignal objects from R5

        Returns:
            Dict mapping layer name → list of StagedWrite for that layer
        """
        if not signals:
            return {}

        # Collect all writes first
        raw_writes: Dict[str, List[StagedWrite]] = {}

        for signal in signals:
            layer_writes = self._assemble_signal(signal)
            for layer, write in layer_writes:
                if layer not in raw_writes:
                    raw_writes[layer] = []
                raw_writes[layer].append(write)

        # Deduplicate writes by record_id within each layer
        result: Dict[str, List[StagedWrite]] = {}
        for layer, writes in raw_writes.items():
            result[layer] = self._deduplicate_writes(writes)

        return result

    def _deduplicate_writes(
        self,
        writes: List[StagedWrite],
    ) -> List[StagedWrite]:
        """
        Deduplicate writes by record_id, merging data for same record.

        Handles accumulative fields like query_count_increment and
        milestone_append by merging them appropriately.

        Args:
            writes: List of StagedWrite for same layer

        Returns:
            Deduplicated list of StagedWrite
        """
        if not writes:
            return []

        # Group by record_id
        by_record: Dict[str, List[StagedWrite]] = {}
        for write in writes:
            if write.record_id not in by_record:
                by_record[write.record_id] = []
            by_record[write.record_id].append(write)

        # Merge writes with same record_id
        result: List[StagedWrite] = []
        for record_id, record_writes in by_record.items():
            if len(record_writes) == 1:
                result.append(record_writes[0])
            else:
                merged = self._merge_writes(record_writes)
                result.append(merged)

        return result

    def _merge_writes(
        self,
        writes: List[StagedWrite],
    ) -> StagedWrite:
        """
        Merge multiple writes to same record_id into one.

        Handles special fields:
        - query_count_increment: Sum values
        - milestone_append: Collect into milestones_append list
        - source_event_ids: Union all event_ids

        Args:
            writes: List of StagedWrite with same record_id

        Returns:
            Single merged StagedWrite
        """
        if not writes:
            raise ValueError("Cannot merge empty writes list")

        base = writes[0]
        merged_data = dict(base.record_data)
        all_event_ids: List[str] = list(base.source_event_ids) if base.source_event_ids else []

        # Accumulative fields to merge
        total_query_increment = merged_data.get("query_count_increment", 0)
        milestones: List[dict] = []
        if "milestone_append" in merged_data:
            milestones.append(merged_data["milestone_append"])

        for write in writes[1:]:
            # Merge source_event_ids
            if write.source_event_ids:
                all_event_ids.extend(write.source_event_ids)

            # Sum query_count_increment
            if "query_count_increment" in write.record_data:
                total_query_increment += write.record_data["query_count_increment"]

            # Collect milestones
            if "milestone_append" in write.record_data:
                milestones.append(write.record_data["milestone_append"])

            # Keep latest updated_at
            if "updated_at" in write.record_data:
                merged_data["updated_at"] = max(
                    merged_data.get("updated_at", 0),
                    write.record_data["updated_at"],
                )

            # Keep latest last_queried_at
            if "last_queried_at" in write.record_data:
                merged_data["last_queried_at"] = max(
                    merged_data.get("last_queried_at", 0),
                    write.record_data["last_queried_at"],
                )

        # Apply accumulated values
        if total_query_increment > 0:
            merged_data["query_count_increment"] = total_query_increment

        if milestones:
            if len(milestones) == 1:
                merged_data["milestone_append"] = milestones[0]
            else:
                # Multiple milestones - use list
                merged_data["milestones_append"] = milestones
                merged_data.pop("milestone_append", None)

        # Deduplicate event_ids
        unique_event_ids = list(dict.fromkeys(all_event_ids))

        # Create merged write
        return StagedWrite(
            write_id=base.write_id,
            layer=base.layer,
            record_id=base.record_id,
            operation=base.operation,
            record_data=merged_data,
            source_phase=base.source_phase,
            idempotency_key=base.idempotency_key,
            expected_version=base.expected_version,
            source_event_ids=unique_event_ids,
        )

    def _assemble_signal(
        self,
        signal: IntentSignal,
    ) -> List[Tuple[str, StagedWrite]]:
        """
        Route single signal to appropriate writes.

        Args:
            signal: IntentSignal to convert

        Returns:
            List of (layer_name, StagedWrite) tuples
        """
        if signal.signal_type == IntentSignalType.REMINDER:
            return self._assemble_reminder(signal)  # type: ignore
        elif signal.signal_type == IntentSignalType.DECISION:
            return self._assemble_decision(signal)  # type: ignore
        elif signal.signal_type == IntentSignalType.LESSON:
            return self._assemble_lesson(signal)  # type: ignore
        elif signal.signal_type == IntentSignalType.EMOTIONAL_TREND:
            return self._assemble_emotional(signal)  # type: ignore
        elif signal.signal_type == IntentSignalType.MILESTONE:
            return self._assemble_milestone(signal)  # type: ignore
        elif signal.signal_type == IntentSignalType.QUERY_BOOST:
            return self._assemble_query_boost(signal)  # type: ignore
        return []

    # =========================================================================
    # st_prospective — REMINDER writes
    # =========================================================================

    def _assemble_reminder(
        self,
        signal: ReminderSignal,
    ) -> List[Tuple[str, StagedWrite]]:
        """
        Create st_prospective INSERT for REMINDER.

        st_prospective schema expects these fields:
            intention_id, tenant_id, space_id, actor_id, intention_type,
            intention_description, target_date, target_context, status,
            inferred_from_json, confidence_score, archival_status,
            created_at, updated_at, valid_from
        """
        now_ms = _now_ms()
        intention_id = f"reminder_{signal.event_id}"

        # Build target context from source text
        target_context = (
            signal.source_text[:500] if len(signal.source_text) > 500 else signal.source_text
        )

        record_data = {
            "intention_id": intention_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "actor_id": self.actor_id or "system",
            "intention_type": "REMINDER",
            "intention_description": signal.action_description,
            "target_date": signal.target_date,  # Already in ms
            "target_context": target_context,
            "status": "ACTIVE",
            "inferred_from_json": json.dumps([signal.event_id]),
            "inference_confidence": signal.confidence,
            "confidence_score": signal.confidence,
            "archival_status": "ACTIVE",
            "decay_factor": 1.0,
            "created_at": now_ms,
            "updated_at": now_ms,
            "valid_from": now_ms,
        }

        write = StagedWrite.insert(
            layer=LAYER_ST_PROSPECTIVE,
            record_id=intention_id,
            data=record_data,
            phase=self.SOURCE_PHASE,
            event_ids=[signal.event_id],
        )

        return [(LAYER_ST_PROSPECTIVE, write)]

    # =========================================================================
    # st_prospective — DECISION writes
    # =========================================================================

    def _assemble_decision(
        self,
        signal: DecisionSignal,
    ) -> List[Tuple[str, StagedWrite]]:
        """
        Create st_prospective INSERT for DECISION.

        DECISION type represents pending decisions that need resolution.
        Options are stored in inferred_from_json for future reference.

        st_prospective schema expects these fields:
            intention_id, tenant_id, space_id, actor_id, intention_type,
            intention_description, target_context, status,
            inferred_from_json, confidence_score, archival_status,
            created_at, updated_at, valid_from
        """
        now_ms = _now_ms()
        intention_id = f"decision_{signal.event_id}"

        # Build target context from source text
        target_context = (
            signal.source_text[:500] if len(signal.source_text) > 500 else signal.source_text
        )

        # Store decision options in inferred_from_json
        inferred_from = json.dumps(
            {
                "decision_options": signal.options_mentioned,
                "decision_context": signal.decision_context,
                "source_event_ids": [signal.event_id],
            }
        )

        record_data = {
            "intention_id": intention_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "actor_id": self.actor_id or "system",
            "intention_type": "DECISION",
            "intention_description": signal.decision_context,
            "target_context": target_context,
            "status": "ACTIVE",
            "inferred_from_json": inferred_from,
            "inference_confidence": signal.confidence,
            "confidence_score": signal.confidence,
            "archival_status": "ACTIVE",
            "decay_factor": 1.0,
            "created_at": now_ms,
            "updated_at": now_ms,
            "valid_from": now_ms,
        }

        write = StagedWrite.insert(
            layer=LAYER_ST_PROSPECTIVE,
            record_id=intention_id,
            data=record_data,
            phase=self.SOURCE_PHASE,
            event_ids=[signal.event_id],
        )

        return [(LAYER_ST_PROSPECTIVE, write)]

    # =========================================================================
    # st_sem — LESSON writes
    # =========================================================================

    def _assemble_lesson(
        self,
        signal: LessonSignal,
    ) -> List[Tuple[str, StagedWrite]]:
        """
        Create st_sem INSERT for LESSON pattern type.

        LESSON patterns represent insights or lessons learned that
        should be remembered as semantic knowledge.

        st_sem schema expects these fields:
            pattern_id, tenant_id, space_id, pattern_type,
            pattern_name, source_episodes_json, source_episode_count,
            confidence_score, observation_count, last_observed_at,
            first_observed_at, is_canonical, archival_status,
            decay_factor, created_at, updated_at, valid_from
        """
        now_ms = _now_ms()
        pattern_id = f"lesson_{signal.event_id}"

        # Truncate pattern_name to reasonable length
        pattern_name = (
            signal.lesson_description[:200]
            if len(signal.lesson_description) > 200
            else signal.lesson_description
        )

        record_data = {
            "pattern_id": pattern_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "pattern_type": "LESSON",  # Extended CHECK in 0058
            "pattern_name": pattern_name,
            "source_episodes_json": json.dumps([signal.event_id]),
            "source_episode_count": 1,
            "confidence_score": signal.confidence,
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

        write = StagedWrite.insert(
            layer=LAYER_ST_SEM,
            record_id=pattern_id,
            data=record_data,
            phase=self.SOURCE_PHASE,
            event_ids=[signal.event_id],
        )

        return [(LAYER_ST_SEM, write)]

    # =========================================================================
    # st_sem — EMOTIONAL_TREND writes
    # =========================================================================

    def _assemble_emotional(
        self,
        signal: EmotionalSignal,
    ) -> List[Tuple[str, StagedWrite]]:
        """
        Create st_sem INSERT for EMOTIONAL_TREND pattern type.

        EMOTIONAL_TREND patterns track emotional patterns over time.
        Multiple observations build up the trend.

        st_sem schema expects these fields:
            pattern_id, tenant_id, space_id, pattern_type,
            pattern_name, source_episodes_json, source_episode_count,
            confidence_score, observation_count, last_observed_at,
            first_observed_at, is_canonical, archival_status,
            decay_factor, created_at, updated_at, valid_from
        """
        now_ms = _now_ms()
        pattern_id = f"emotion_{signal.event_id}"

        # Create descriptive pattern name
        pattern_name = f"{signal.emotion_label} emotional pattern"

        record_data = {
            "pattern_id": pattern_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "pattern_type": "EMOTIONAL_TREND",  # Extended CHECK in 0058
            "pattern_name": pattern_name,
            "source_episodes_json": json.dumps([signal.event_id]),
            "source_episode_count": 1,
            "confidence_score": signal.confidence,
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

        write = StagedWrite.insert(
            layer=LAYER_ST_SEM,
            record_id=pattern_id,
            data=record_data,
            phase=self.SOURCE_PHASE,
            event_ids=[signal.event_id],
        )

        return [(LAYER_ST_SEM, write)]

    # =========================================================================
    # st_kg_dom — MILESTONE writes
    # =========================================================================

    def _assemble_milestone(
        self,
        signal: MilestoneSignal,
    ) -> List[Tuple[str, StagedWrite]]:
        """
        Create st_kg_dom UPDATE to append milestone to milestones_json.

        Milestones are appended to the entity's milestones_json array.
        If entity doesn't exist, this becomes an INSERT with milestone.
        """
        now_ms = _now_ms()

        # If no entity_id, we can't create a milestone write
        if not signal.entity_id:
            return []

        # Build milestone entry to append
        milestone_entry = {
            "milestone_type": signal.milestone_type.value,
            "description": signal.milestone_description or signal.source_text[:200],
            "source_event_id": signal.event_id,
            "recorded_at_ms": now_ms,
        }

        # Create UPDATE to append milestone
        # R7 layer writer will handle the JSON append logic
        record_data = {
            "entity_id": signal.entity_id,
            "milestone_append": milestone_entry,  # Special field for append
            "updated_at": now_ms,
            "last_queried_at": now_ms,  # Milestone implies relevance
        }

        write = StagedWrite.update(
            layer=LAYER_ST_KG_DOM,
            record_id=signal.entity_id,
            data=record_data,
            phase=self.SOURCE_PHASE,
            expected_version=0,  # Will be resolved by layer writer
            event_ids=[signal.event_id],
        )

        return [(LAYER_ST_KG_DOM, write)]

    # =========================================================================
    # st_kg_dom / st_kg_edges — QUERY_BOOST writes
    # =========================================================================

    def _assemble_query_boost(
        self,
        signal: QueryBoostSignal,
    ) -> List[Tuple[str, StagedWrite]]:
        """
        Create st_kg_dom and st_kg_edges UPDATEs for query_count increment.

        Query boost increments query_count and updates last_queried_at
        for both entities and edges mentioned in the query.
        """
        now_ms = _now_ms()
        writes: List[Tuple[str, StagedWrite]] = []

        # Entity query boosts
        for entity_id in signal.entity_ids:
            record_data = {
                "entity_id": entity_id,
                "query_count_increment": 1,  # Special field for increment
                "last_queried_at": now_ms,
                "updated_at": now_ms,
            }

            write = StagedWrite.update(
                layer=LAYER_ST_KG_DOM,
                record_id=entity_id,
                data=record_data,
                phase=self.SOURCE_PHASE,
                expected_version=0,  # Will be resolved by layer writer
                event_ids=[signal.event_id],
            )
            writes.append((LAYER_ST_KG_DOM, write))

        # Edge query boosts
        for edge_id in signal.edge_ids:
            record_data = {
                "edge_id": edge_id,
                "query_count_increment": 1,  # Special field for increment
                "last_queried_at": now_ms,
                "updated_at": now_ms,
            }

            write = StagedWrite.update(
                layer=LAYER_ST_KG_EDGES,
                record_id=edge_id,
                data=record_data,
                phase=self.SOURCE_PHASE,
                expected_version=0,  # Will be resolved by layer writer
                event_ids=[signal.event_id],
            )
            writes.append((LAYER_ST_KG_EDGES, write))

        return writes


def assemble_intent_signal_writes(
    signals: List[IntentSignal],
    tenant_id: str,
    space_id: str,
    actor_id: str = "",
) -> Dict[str, List[StagedWrite]]:
    """
    Convenience function to assemble intent signal writes.

    Args:
        signals: List of IntentSignal objects from R5
        tenant_id: Tenant identifier
        space_id: Space identifier
        actor_id: Optional actor identifier

    Returns:
        Dict mapping layer name → list of StagedWrite
    """
    assembler = IntentSignalAssembler(
        tenant_id=tenant_id,
        space_id=space_id,
        actor_id=actor_id,
    )
    return assembler.assemble_all(signals)
