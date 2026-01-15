"""
P03EnvelopeSerializer - Serialization for checkpoints, DLQ, and recovery.

This module implements envelope serialization for:
- DLQ storage (failed cycles)
- Debugging snapshots
- Checkpoint recovery
- Audit trails

Spec Reference: docs/pipelines/P03_envelope_fields_discovery.md section 21.2, 24.4

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .context import P03CycleContext, generate_ulid
from .event_state import P03EventState, PruneDecision, ReconciliationAction
from .observability import P03Error, P03ObservabilityContext
from .phase_outputs import P03PhaseOutputs
from .staged_writes import P03StagedWrites, StagedOutboxEvent, StagedWrite

# =============================================================================
# PHASE TRANSITION EXCEPTION
# =============================================================================


class InvalidPhaseTransition(Exception):
    """Raised when attempting invalid phase progression."""

    pass


# =============================================================================
# PHASE CHECKPOINT
# =============================================================================


@dataclass
class PhaseCheckpoint:
    """
    Immutable snapshot at phase boundary.

    Checkpoints are created after each phase completes to enable:
    - Recovery after failure
    - Debugging phase issues
    - Audit trails

    Attributes:
        checkpoint_id: ULID for this checkpoint
        phase: Phase name at checkpoint (R0-R8, COMPLETE, FAILED)
        timestamp_ms: Checkpoint creation time (MILLISECONDS)
        events_count: Number of events in batch
        staged_writes_count: Total staged writes at this point
        errors_count: Accumulated error count
        phase_timings_ms: Phase durations up to this point
        summary: Phase-specific summary data
    """

    checkpoint_id: str
    phase: str
    timestamp_ms: int
    events_count: int
    staged_writes_count: int
    errors_count: int
    phase_timings_ms: Dict[str, int]
    summary: Dict[str, Any]

    @classmethod
    def create(
        cls,
        phase: str,
        events_count: int,
        staged_writes_count: int,
        errors_count: int,
        phase_timings_ms: Dict[str, int],
        summary: Optional[Dict[str, Any]] = None,
    ) -> PhaseCheckpoint:
        """Factory for creating checkpoints."""
        return cls(
            checkpoint_id=generate_ulid(),
            phase=phase,
            timestamp_ms=_now_ms(),
            events_count=events_count,
            staged_writes_count=staged_writes_count,
            errors_count=errors_count,
            phase_timings_ms=dict(phase_timings_ms),
            summary=summary or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "phase": self.phase,
            "timestamp_ms": self.timestamp_ms,
            "events_count": self.events_count,
            "staged_writes_count": self.staged_writes_count,
            "errors_count": self.errors_count,
            "phase_timings_ms": self.phase_timings_ms,
            "summary": self.summary,
        }


# =============================================================================
# P03 ENVELOPE SERIALIZER
# =============================================================================


class P03EnvelopeSerializer:
    """
    Serialize/deserialize P03 envelopes for checkpointing.

    Provides three serialization levels:
    - to_summary_dict(): Minimal summary for logging/metrics
    - to_dict(): Standard serialization for DLQ/debugging
    - to_full_dict(): Complete serialization for recovery

    All methods produce JSON-serializable output.
    """

    # =========================================================================
    # SERIALIZATION METHODS
    # =========================================================================

    @staticmethod
    def to_summary_dict(
        context: P03CycleContext,
        current_phase: str,
        events_count: int,
        staged_writes_count: int,
        errors_count: int,
        observability: Optional[P03ObservabilityContext] = None,
    ) -> Dict[str, Any]:
        """
        Minimal summary for logging/metrics.

        Args:
            context: Cycle context
            current_phase: Current phase name
            events_count: Number of events
            staged_writes_count: Total staged writes
            errors_count: Error count
            observability: Optional observability context

        Returns:
            Compact JSON-serializable dict
        """
        result = {
            "cycle_id": context.cycle_id,
            "batch_id": context.batch_id,
            "trace_id": context.trace_id,
            "current_phase": current_phase,
            "batch_size": context.batch_size,
            "events_count": events_count,
            "staged_writes_count": staged_writes_count,
            "errors_count": errors_count,
        }

        if observability:
            result["phase_durations_ms"] = observability.get_all_phase_durations()
            result["total_duration_ms"] = observability.get_total_duration_ms()

        return result

    @staticmethod
    def to_dict(
        context: P03CycleContext,
        current_phase: str,
        events: List[P03EventState],
        phases: P03PhaseOutputs,
        staged: P03StagedWrites,
        observability: P03ObservabilityContext,
        checkpoints: Optional[List[PhaseCheckpoint]] = None,
    ) -> Dict[str, Any]:
        """
        Standard serialization for DLQ/debugging.

        Includes context, summary metrics, and observability data.
        Events are summarized (not full state).

        Args:
            context: Cycle context
            current_phase: Current phase name
            events: List of event states
            phases: Phase outputs container
            staged: Staged writes container
            observability: Observability context
            checkpoints: Optional list of checkpoints

        Returns:
            JSON-serializable dict
        """
        return {
            "context": P03EnvelopeSerializer._serialize_context(context),
            "current_phase": current_phase,
            "events_count": len(events),
            "events_summary": P03EnvelopeSerializer._summarize_events(events),
            "phases_summary": phases.to_summary_dict(),
            "staged_summary": staged.to_summary_dict(),
            "observability": observability.to_summary_dict(),
            "checkpoints": [cp.to_dict() for cp in (checkpoints or [])],
        }

    @staticmethod
    def to_full_dict(
        context: P03CycleContext,
        current_phase: str,
        events: List[P03EventState],
        phases: P03PhaseOutputs,
        staged: P03StagedWrites,
        observability: P03ObservabilityContext,
        checkpoints: Optional[List[PhaseCheckpoint]] = None,
    ) -> Dict[str, Any]:
        """
        Full serialization for recovery.

        Includes complete event state, all phase outputs, and staged writes.
        Use for checkpoint recovery or deep debugging.

        Args:
            context: Cycle context
            current_phase: Current phase name
            events: List of event states
            phases: Phase outputs container
            staged: Staged writes container
            observability: Observability context
            checkpoints: Optional list of checkpoints

        Returns:
            Complete JSON-serializable dict
        """
        return {
            "context": P03EnvelopeSerializer._serialize_context(context),
            "current_phase": current_phase,
            "events": [P03EnvelopeSerializer._serialize_event(e) for e in events],
            "phases": P03EnvelopeSerializer._serialize_phases(phases),
            "staged": P03EnvelopeSerializer._serialize_staged(staged),
            "observability": P03EnvelopeSerializer._serialize_observability(observability),
            "checkpoints": [cp.to_dict() for cp in (checkpoints or [])],
        }

    # =========================================================================
    # DESERIALIZATION METHODS
    # =========================================================================

    @staticmethod
    def context_from_dict(data: Dict[str, Any]) -> P03CycleContext:
        """
        Deserialize P03CycleContext from dict.

        Args:
            data: Dict from serialized context

        Returns:
            Reconstructed P03CycleContext
        """
        return P03CycleContext(
            cycle_id=data["cycle_id"],
            batch_id=data["batch_id"],
            tenant_id=data["tenant_id"],
            space_id=data["space_id"],
            event_ids=tuple(data["event_ids"]),
            batch_size=data["batch_size"],
            trigger_type=data.get("trigger_type", "UNKNOWN"),
            trigger_reason=data.get("trigger_reason", ""),
            triggered_at=data.get("triggered_at", 0),
            deadline_ms=data.get("deadline_ms", 300000),
            trace_id=data.get("trace_id", ""),
            qos_band=data.get("qos_band", "AMBER"),
            priority=data.get("priority", 50),
            pending_before=data.get("pending_before", 0),
            scheduler_token=data.get("scheduler_token"),
        )

    @staticmethod
    def event_from_dict(data: Dict[str, Any]) -> P03EventState:
        """
        Deserialize P03EventState from dict.

        Args:
            data: Dict from serialized event

        Returns:
            Reconstructed P03EventState
        """
        event = P03EventState(
            event_id=data["event_id"],
            hipp_event_id=data.get("hipp_event_id", ""),
            content_text=data.get("content_text", ""),
            content_type=data.get("content_type", ""),
            content_hash=data.get("content_hash", ""),
            simhash_hex=data.get("simhash_hex", ""),
            timestamp=data.get("timestamp", 0),
            channel_id=data.get("channel_id", ""),
            embedding_id=data.get("embedding_id", ""),
            sentiment_score=data.get("sentiment_score", 0.0),
            sentiment_label=data.get("sentiment_label", "neutral"),
            emotions_json=data.get("emotions_json", "[]"),
            intent_label=data.get("intent_label", ""),
            ner_entities_json=data.get("ner_entities_json", "[]"),
            temporal_expressions_json=data.get("temporal_expressions_json", "[]"),
        )

        # Restore R1 importance fields
        if "importance_score" in data:
            event.importance_score = data["importance_score"]
            event.recency_factor = data.get("recency_factor", 0.0)
            event.affect_factor = data.get("affect_factor", 0.0)
            event.social_factor = data.get("social_factor", 0.0)
            event.novelty_factor = data.get("novelty_factor", 0.0)
            event.importance_computed = data.get("importance_computed", False)

        # Restore R2 cluster fields
        if "cluster_id" in data:
            event.cluster_id = data["cluster_id"]
            event.cluster_label = data.get("cluster_label", -1)
            event.centroid_distance = data.get("centroid_distance", 0.0)
            event.is_noise = data.get("is_noise", False)

        # Restore R3 reconciliation fields
        if "reconciliation_action" in data:
            event.reconciliation_action = ReconciliationAction(data["reconciliation_action"])
            event.best_match_id = data.get("best_match_id")
            event.best_match_layer = data.get("best_match_layer")
            event.similarity_score = data.get("similarity_score", 0.0)
            event.confidence = data.get("confidence", 0.0)
            event.reconciliation_reason = data.get("reconciliation_reason", "")

        # Restore decay fields
        if "decay_score" in data:
            event.decay_score = data["decay_score"]
            event.lambda_decay = data.get("lambda_decay", 0.1)
            event.prune_decision = PruneDecision(data.get("prune_decision", "KEEP"))

        return event

    @staticmethod
    def observability_from_dict(data: Dict[str, Any]) -> P03ObservabilityContext:
        """
        Deserialize P03ObservabilityContext from dict.

        Args:
            data: Dict from serialized observability

        Returns:
            Reconstructed P03ObservabilityContext
        """
        obs = P03ObservabilityContext(
            trace_id=data.get("trace_id", ""),
            root_span_id=data.get("root_span_id", ""),
            current_span_id=data.get("current_span_id", ""),
            span_stack=data.get("span_stack", []),
            phase_start_ts=data.get("phase_start_ts", {}),
            phase_end_ts=data.get("phase_end_ts", {}),
            counters=data.get("counters", {}),
            log_context=data.get("log_context", {}),
        )

        # Restore histograms
        for metric, values in data.get("histograms", {}).items():
            obs.histograms[metric] = values

        # Restore errors
        for err_data in data.get("errors", []):
            error = P03Error(
                error_id=err_data["error_id"],
                phase=err_data["phase"],
                stage_id=err_data["stage_id"],
                error_type=err_data["error_type"],
                error_message=err_data["error_message"],
                event_id=err_data.get("event_id"),
                recoverable=err_data.get("recoverable", True),
                timestamp_ms=err_data.get("timestamp_ms", 0),
                stack_trace=err_data.get("stack_trace"),
                context=err_data.get("context", {}),
            )
            obs.errors.append(error)

        return obs

    @staticmethod
    def checkpoint_from_dict(data: Dict[str, Any]) -> PhaseCheckpoint:
        """
        Deserialize PhaseCheckpoint from dict.

        Args:
            data: Dict from serialized checkpoint

        Returns:
            Reconstructed PhaseCheckpoint
        """
        return PhaseCheckpoint(
            checkpoint_id=data["checkpoint_id"],
            phase=data["phase"],
            timestamp_ms=data["timestamp_ms"],
            events_count=data["events_count"],
            staged_writes_count=data["staged_writes_count"],
            errors_count=data["errors_count"],
            phase_timings_ms=data.get("phase_timings_ms", {}),
            summary=data.get("summary", {}),
        )

    # =========================================================================
    # INTERNAL SERIALIZATION HELPERS
    # =========================================================================

    @staticmethod
    def _serialize_context(context: P03CycleContext) -> Dict[str, Any]:
        """Serialize P03CycleContext to dict."""
        return {
            "cycle_id": context.cycle_id,
            "batch_id": context.batch_id,
            "tenant_id": context.tenant_id,
            "space_id": context.space_id,
            "event_ids": list(context.event_ids),
            "batch_size": context.batch_size,
            "trigger_type": context.trigger_type,
            "trigger_reason": context.trigger_reason,
            "triggered_at": context.triggered_at,
            "deadline_ms": context.deadline_ms,
            "trace_id": context.trace_id,
            "qos_band": context.qos_band,
            "priority": context.priority,
            "pending_before": context.pending_before,
            "scheduler_token": context.scheduler_token,
        }

    @staticmethod
    def _serialize_event(event: P03EventState) -> Dict[str, Any]:
        """Serialize P03EventState to dict."""
        return {
            # Identity
            "event_id": event.event_id,
            "hipp_event_id": event.hipp_event_id,
            # Content
            "content_text": event.content_text,
            "content_type": event.content_type,
            "content_hash": event.content_hash,
            "simhash_hex": event.simhash_hex,
            "timestamp": event.timestamp,
            "channel_id": event.channel_id,
            # Embedding
            "embedding_id": event.embedding_id,
            # NLP enrichment
            "sentiment_score": event.sentiment_score,
            "sentiment_label": event.sentiment_label,
            "emotions_json": event.emotions_json,
            "intent_label": event.intent_label,
            "ner_entities_json": event.ner_entities_json,
            "temporal_expressions_json": event.temporal_expressions_json,
            # R1 importance
            "importance_score": event.importance_score,
            "recency_factor": event.recency_factor,
            "affect_factor": event.affect_factor,
            "social_factor": event.social_factor,
            "novelty_factor": event.novelty_factor,
            "importance_computed": event.importance_computed,
            # R2 clustering
            "cluster_id": event.cluster_id,
            "cluster_label": event.cluster_label,
            "centroid_distance": event.centroid_distance,
            "is_noise": event.is_noise,
            # R3 reconciliation
            "reconciliation_action": event.reconciliation_action.value,
            "best_match_id": event.best_match_id,
            "best_match_layer": event.best_match_layer,
            "similarity_score": event.similarity_score,
            "confidence": event.confidence,
            "reconciliation_reason": event.reconciliation_reason,
            # Decay
            "decay_score": event.decay_score,
            "lambda_decay": event.lambda_decay,
            "prune_decision": event.prune_decision.value,
            # Versioning
            "expected_version": event.expected_version,
            "last_completed_phase": event.last_completed_phase,
        }

    @staticmethod
    def _summarize_events(events: List[P03EventState]) -> Dict[str, Any]:
        """Generate summary statistics for events."""
        if not events:
            return {"count": 0}

        importance_scores = [e.importance_score for e in events if e.importance_computed]
        reconciliation_counts: Dict[str, int] = {}
        for e in events:
            action = e.reconciliation_action.value
            reconciliation_counts[action] = reconciliation_counts.get(action, 0) + 1

        cluster_ids = set(e.cluster_id for e in events if e.cluster_id)
        noise_count = sum(1 for e in events if e.is_noise)

        return {
            "count": len(events),
            "importance_computed": len(importance_scores),
            "avg_importance": (
                sum(importance_scores) / len(importance_scores) if importance_scores else 0
            ),
            "max_importance": max(importance_scores) if importance_scores else 0,
            "cluster_count": len(cluster_ids),
            "noise_count": noise_count,
            "reconciliation_counts": reconciliation_counts,
        }

    @staticmethod
    def _serialize_phases(phases: P03PhaseOutputs) -> Dict[str, Any]:
        """Serialize P03PhaseOutputs to dict."""
        # Use the to_summary_dict as base, add full data where needed
        result = phases.to_summary_dict()

        # Add full cluster data
        result["r2_clusters"] = [
            {
                "cluster_id": c.cluster_id,
                "member_event_ids": c.member_event_ids,
                "centroid_embedding_id": c.centroid_embedding_id,
                "dominant_sentiment": c.dominant_sentiment,
                "temporal_start": c.temporal_start,
                "temporal_end": c.temporal_end,
                "cohesion_score": c.cohesion_score,
            }
            for c in phases.r2_clusters
        ]

        # Add KG entities (new + updated counts)
        result["r4_new_entities"] = [
            {
                "entity_id": e.entity_id,
                "canonical_name": e.canonical_name,
                "entity_type": e.entity_type,
                "aliases_json": e.aliases_json,
                "confidence": e.confidence,
                "embedding_id": e.embedding_id,
                "source_event_ids": e.source_event_ids,
                "is_new": e.is_new,
            }
            for e in phases.r4_new_entities
        ]
        result["r4_entity_update_count"] = len(phases.r4_updated_entities)
        result["r4_new_edge_count"] = len(phases.r4_new_edges)
        result["r4_gap_count"] = len(phases.r4_gap_candidates)

        # Add insights
        result["r5_insights"] = [
            {
                "insight_id": i.insight_id,
                "insight_type": i.insight_type,
                "concept_a_id": i.concept_a_id,
                "concept_b_id": i.concept_b_id,
                "pmi_score": i.pmi_score,
                "novelty_score": i.novelty_score,
                "relevance_score": i.relevance_score,
                "natural_language": i.natural_language,
            }
            for i in phases.r5_insights
        ]

        return result

    @staticmethod
    def _serialize_staged(staged: P03StagedWrites) -> Dict[str, Any]:
        """Serialize P03StagedWrites to dict."""

        def serialize_write(w: StagedWrite) -> Dict[str, Any]:
            return {
                "write_id": w.write_id,
                "layer": w.layer,
                "operation": w.operation.value,
                "record_id": w.record_id,
                "record_data": w.record_data,
                "idempotency_key": w.idempotency_key,
                "source_phase": w.source_phase,
                "source_event_ids": w.source_event_ids,
                "expected_version": w.expected_version,
                "created_at_ms": w.created_at_ms,
            }

        def serialize_outbox(e: StagedOutboxEvent) -> Dict[str, Any]:
            return {
                "event_id": e.event_id,
                "topic": e.topic,
                "payload": e.payload,
                "source_phase": e.source_phase,
                "priority": e.priority,
                "created_at_ms": e.created_at_ms,
            }

        return {
            "summary": staged.to_summary_dict(),
            "st_epi_writes": [serialize_write(w) for w in staged.st_epi_writes],
            "st_sem_writes": [serialize_write(w) for w in staged.st_sem_writes],
            "st_procedural_writes": [serialize_write(w) for w in staged.st_procedural_writes],
            "st_social_writes": [serialize_write(w) for w in staged.st_social_writes],
            "st_prospective_writes": [serialize_write(w) for w in staged.st_prospective_writes],
            "st_kg_dom_writes": [serialize_write(w) for w in staged.st_kg_dom_writes],
            "st_kg_edges_writes": [serialize_write(w) for w in staged.st_kg_edges_writes],
            "st_vec_writes": [serialize_write(w) for w in staged.st_vec_writes],
            "st_hipp_events_updates": [serialize_write(w) for w in staged.st_hipp_events_updates],
            "st_learning_queue_writes": [
                serialize_write(w) for w in staged.st_learning_queue_writes
            ],
            "outbox_events": [serialize_outbox(e) for e in staged.outbox_events],
        }

    @staticmethod
    def _serialize_observability(obs: P03ObservabilityContext) -> Dict[str, Any]:
        """Serialize P03ObservabilityContext to dict."""
        return {
            "trace_id": obs.trace_id,
            "root_span_id": obs.root_span_id,
            "current_span_id": obs.current_span_id,
            "span_stack": obs.span_stack,
            "phase_start_ts": obs.phase_start_ts,
            "phase_end_ts": obs.phase_end_ts,
            "counters": dict(obs.counters),
            "histograms": {k: list(v) for k, v in obs.histograms.items()},
            "log_context": dict(obs.log_context),
            "errors": [e.to_dict() for e in obs.errors],
        }


# =============================================================================
# PHASE SUMMARY GENERATORS
# =============================================================================


def generate_phase_summary(
    phase: str,
    phases: P03PhaseOutputs,
    events: List[P03EventState],
) -> Dict[str, Any]:
    """
    Auto-generate summary based on phase.

    Args:
        phase: Current phase name (R0-R8)
        phases: Phase outputs container
        events: List of event states

    Returns:
        Phase-specific summary dict
    """
    if phase == "R0":
        return {
            "events_loaded": len(events),
        }

    elif phase == "R1":
        computed = [e for e in events if e.importance_computed]
        scores = [e.importance_score for e in computed]
        return {
            "events_scored": len(computed),
            "avg_importance": sum(scores) / len(scores) if scores else 0,
            "max_importance": max(scores) if scores else 0,
            "hebbian_updates": len(phases.r1_hebbian_updates),
        }

    elif phase == "R2":
        return {
            "cluster_count": len(phases.r2_clusters),
            "noise_count": len(phases.r2_noise_event_ids),
            "avg_cluster_size": phases.r2_avg_cluster_size,
        }

    elif phase == "R3":
        reconciliation_counts: Dict[str, int] = {}
        for e in events:
            action = e.reconciliation_action.value
            reconciliation_counts[action] = reconciliation_counts.get(action, 0) + 1
        return {
            "dedup_merges": len(phases.r3_dedup_merges),
            "archive_candidates": len(phases.r3_archive_candidates),
            "prune_candidates": len(phases.r3_prune_candidates),
            "reconciliation_counts": reconciliation_counts,
        }

    elif phase == "R4":
        return {
            "entities_created": len(phases.r4_new_entities),
            "entities_updated": len(phases.r4_updated_entities),
            "edges_created": len(phases.r4_new_edges),
            "edges_updated": len(phases.r4_updated_edges),
            "causal_edges": len(phases.r4_causal_edges),
            "gap_candidates": len(phases.r4_gap_candidates),
        }

    elif phase == "R5":
        return {
            "skipped": phases.r5_skipped,
            "skip_reason": phases.r5_skip_reason,
            "counterfactuals": len(phases.r5_counterfactuals),
            "insights": len(phases.r5_insights),
            "routine_optimizations": len(phases.r5_routine_optimizations),
            "prospective_memories": len(phases.r5_prospective_memories),
        }

    elif phase == "R6":
        summary = phases.r6_summary
        return {
            "reinforce": summary.reinforce_count,
            "extend": summary.extend_count,
            "create": summary.create_count,
            "evolve": summary.evolve_count,
            "skip": summary.skip_count,
            "prune": summary.prune_count,
            "total_processed": summary.total_processed,
        }

    elif phase == "R7":
        manifest = phases.r7_manifest
        if manifest:
            return {
                "records_written": manifest.successful_writes,
                "records_failed": manifest.failed_writes,
                "tables_touched": manifest.tables_touched,
            }
        return {"success": phases.r7_success, "error": phases.r7_error}

    elif phase == "R8":
        return {
            "events_emitted": len(phases.r8_emitted_events),
            "success": phases.r8_success,
        }

    return {}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _now_ms() -> int:
    """Get current time in milliseconds since Unix epoch."""
    import time

    return int(time.time() * 1000)
