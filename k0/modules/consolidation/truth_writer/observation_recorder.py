"""
ObservationRecorder - Records observations with holistic context to st_observations.

Issue: 7.4
Spec Reference: docs/plans/temporal_fix.md

Purpose:
Every INSERT or MERGE to a truth layer (st_epi, st_sem, etc.) should record
an observation to st_observations. This preserves the full context of WHEN
and WITH WHAT CONTEXT each observation happened.

Architecture:
    Truth Writer (episodic.py, semantic.py, etc.)
        ↓ _insert() or _reinforce()
    ObservationRecorder.record()
        ↓
    INSERT INTO st_observations (...)

The ObservationRecorder is a simple INSERT wrapper - no business logic.
It takes an ObservationContext and persists it to st_observations.

TIMESTAMP CONVENTION (LOCKED):
    All `*_at` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, List, Optional

from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.context import generate_ulid

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    """Return current time in milliseconds since epoch."""
    return int(time.time() * 1000)


# Valid truth layers for observations
VALID_LAYERS = frozenset({"st_epi", "st_sem", "st_kg_dom", "st_social", "st_prospective"})


class ObservationRecorder:
    """
    Records observations with full holistic context to st_observations.

    This service is called by truth layer writers after each INSERT or MERGE
    operation to preserve per-observation context that would otherwise be lost.

    Features:
        - Single observation recording
        - Batch recording for efficiency
        - ULID generation for observation_id
        - NULL handling for optional fields

    Usage:
        recorder = ObservationRecorder()

        # Single observation
        obs_id = await recorder.record(
            uow=uow,
            layer="st_sem",
            record_id="pattern_abc123",
            context=ObservationContext.from_event(event),
            tenant_id="tenant_1",
        )

        # Batch recording
        obs_ids = await recorder.record_batch(
            uow=uow,
            observations=[
                ("st_epi", "episode_1", context1, "tenant_1"),
                ("st_epi", "episode_2", context2, "tenant_1"),
            ],
        )
    """

    # SQL for single INSERT
    _INSERT_SQL = """
        INSERT INTO st_observations (
            observation_id,
            tenant_id,
            layer,
            record_id,
            observed_at,
            observation_type,
            source_event_id,
            observation_weight,
            sentiment_score,
            sentiment_label,
            affect_valence,
            affect_arousal,
            dominant_emotion,
            salience_score,
            novelty_score,
            salience_band,
            ingress_channel,
            ingress_source,
            device_kind,
            location_name,
            location_type,
            geohash_6,
            social_context,
            social_intimacy,
            is_solo_event,
            num_participants,
            time_of_day_bucket,
            circadian_slot,
            is_weekend,
            day_of_week,
            anchor_time_utc,
            original_temporal_expr
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
            $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
            $31, $32
        )
    """

    async def record(
        self,
        uow: "UnitOfWork",
        layer: str,
        record_id: str,
        context: ObservationContext,
        tenant_id: str,
    ) -> str:
        """
        Record a single observation with full context.

        Args:
            uow: Unit of work for transaction
            layer: Truth layer ('st_epi', 'st_sem', 'st_kg_dom', 'st_social', 'st_prospective')
            record_id: Primary key of the truth layer record
            context: Full observation context (temporal, emotional, etc.)
            tenant_id: Tenant identifier

        Returns:
            observation_id (ULID)

        Raises:
            ValueError: If layer is not valid
        """
        if layer not in VALID_LAYERS:
            raise ValueError(f"Invalid layer: {layer}. Must be one of {VALID_LAYERS}")

        observation_id = generate_ulid()

        await uow.connection.execute(
            self._INSERT_SQL,
            observation_id,
            tenant_id,
            layer,
            record_id,
            context.observed_at,
            context.observation_type,
            context.source_event_id,
            context.confidence,  # Maps to observation_weight
            context.sentiment_score,
            context.sentiment_label,
            context.affect_valence,
            context.affect_arousal,
            context.dominant_emotion,
            context.salience_score,
            context.novelty_score,
            context.salience_band,
            context.ingress_channel,
            context.ingress_source,
            context.device_kind,
            context.location_name,
            context.location_type,
            context.geohash_6,
            context.social_context,
            context.social_intimacy,
            context.is_solo_event,
            context.num_participants,
            context.time_of_day_bucket,
            context.circadian_slot,
            context.is_weekend,
            context.day_of_week,
            context.anchor_time_utc,
            context.original_temporal_expr,
        )

        logger.debug(
            "Recorded observation %s for %s.%s",
            observation_id,
            layer,
            record_id,
        )

        return observation_id

    async def record_batch(
        self,
        uow: "UnitOfWork",
        observations: List[tuple],
    ) -> List[str]:
        """
        Record multiple observations efficiently.

        Args:
            uow: Unit of work for transaction
            observations: List of (layer, record_id, context, tenant_id) tuples

        Returns:
            List of observation_ids in same order as input

        Note:
            Uses executemany for batch efficiency when available.
            Falls back to sequential inserts if needed.
        """
        observation_ids: List[str] = []

        for layer, record_id, context, tenant_id in observations:
            obs_id = await self.record(
                uow=uow,
                layer=layer,
                record_id=record_id,
                context=context,
                tenant_id=tenant_id,
            )
            observation_ids.append(obs_id)

        logger.debug("Recorded batch of %d observations", len(observation_ids))

        return observation_ids

    async def record_for_insert(
        self,
        uow: "UnitOfWork",
        layer: str,
        record_id: str,
        context: ObservationContext,
        tenant_id: str,
    ) -> str:
        """
        Record observation for a FIRST_SEEN (INSERT) operation.

        Convenience method that ensures observation_type is FIRST_SEEN.

        Args:
            uow: Unit of work for transaction
            layer: Truth layer
            record_id: Primary key of the new truth layer record
            context: Observation context
            tenant_id: Tenant identifier

        Returns:
            observation_id (ULID)
        """
        ctx = context.with_type("FIRST_SEEN")
        return await self.record(uow, layer, record_id, ctx, tenant_id)

    async def record_for_merge(
        self,
        uow: "UnitOfWork",
        layer: str,
        record_id: str,
        context: ObservationContext,
        tenant_id: str,
    ) -> str:
        """
        Record observation for a REINFORCEMENT (MERGE) operation.

        Convenience method that ensures observation_type is REINFORCEMENT.

        Args:
            uow: Unit of work for transaction
            layer: Truth layer
            record_id: Primary key of the existing truth layer record
            context: Observation context
            tenant_id: Tenant identifier

        Returns:
            observation_id (ULID)
        """
        ctx = context.with_type("REINFORCEMENT")
        return await self.record(uow, layer, record_id, ctx, tenant_id)


# Singleton instance for convenience
_recorder: Optional[ObservationRecorder] = None


def get_observation_recorder() -> ObservationRecorder:
    """
    Get the singleton ObservationRecorder instance.

    Returns:
        ObservationRecorder instance
    """
    global _recorder
    if _recorder is None:
        _recorder = ObservationRecorder()
    return _recorder
