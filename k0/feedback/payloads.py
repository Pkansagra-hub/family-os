"""Builtin payload schemas for implemented pipelines.

Issue Tracker Reality Check:
- P02 (Write), P03 (Consolidation), and P08 (Embeddings) implemented.

Stories:
- FEEDBACK-004: Define feedback schemas for P02 and P08 only
- M3 3.2.6: Add P03 feedback payload schema
Related ADR: K020
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class P02UserCorrection(BaseModel):
    """User correction details for P02 write ingestion."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1)
    expected: str | None = None
    actual: str | None = None


class P02FeedbackPayload(BaseModel):
    """Feedback payload schema for P02 (Write).

    Draft from issue tracker (FEEDBACK-issues-tracker.md).
    """

    model_config = ConfigDict(extra="forbid")

    ingested_envelope_id: str | None = None
    extraction_quality: Literal["good", "partial", "poor"] | None = None
    user_correction: P02UserCorrection | None = None


class P08FeedbackPayload(BaseModel):
    """Feedback payload schema for P08 (Embeddings).

    Draft from issue tracker (FEEDBACK-issues-tracker.md).
    """

    model_config = ConfigDict(extra="forbid")

    embedding_id: str | None = None
    retrieval_hit: bool | None = None
    retrieval_rank: int | None = Field(default=None, ge=1)
    user_relevance: Literal["relevant", "irrelevant", "partial"] | None = None


class P03FeedbackPayload(BaseModel):
    """Payload schema for P03 (Consolidation/Salience) feedback signals.

    Issue: M3 3.2.6 — P21 to P03 Feedback Consumer
    Dossier Reference: Section 9.8.5 (P03FeedbackPayload Schema Definition)
    Version: 1.0

    Field Mapping to Learning Formulas:
    - salience_delta: Importance formula (R1) α_imp adjustment
    - decay_lambda_delta: Decay formula (R2/R3) λ adjustment
    - was_retrieved: Hebbian formula (R4) co-activation signal
    - was_helpful: Hebbian formula (R4) success/failure signal
    - confidence: All formulas weighting factor
    """

    model_config = ConfigDict(extra="forbid")

    feedback_type: Literal[
        "SALIENCE_ADJUSTMENT",
        "DECAY_REVERSAL",
        "CLUSTER_CORRECTION",
        "REINFORCEMENT_OUTCOME",
        "NOVELTY_SIGNAL",
        "REGRET_SIGNAL",
    ]

    # Target identification
    wal_positions: list[int] = Field(default_factory=list)
    entity_id: str | None = None
    cluster_id: str | None = None
    episode_cluster_id: str | None = None
    edge_id: str | None = None

    # Adjustments
    salience_delta: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="Salience adjustment (-1.0 to +1.0)",
    )
    importance_override: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Direct importance value override (0.0 to 1.0)",
    )
    decay_lambda_delta: float | None = Field(
        default=None,
        description="Learning rate adjustment for decay",
    )

    # Clustering corrections
    correct_cluster_id: str | None = None
    incorrect_cluster_id: str | None = None

    # Outcomes
    was_retrieved: bool | None = Field(
        default=None,
        description="Whether entity was retrieved in query",
    )
    was_helpful: bool | None = Field(
        default=None,
        description="Whether retrieval was helpful to user",
    )
    user_confirmed: bool | None = Field(
        default=None,
        description="Whether user explicitly confirmed correctness",
    )

    # Context from K1
    retrieval_query: str | None = None
    session_context: dict | None = None
    source_cycle_id: str | None = Field(
        default=None,
        description="Originating P03 consolidation cycle ID",
    )

    # Signal confidence (0.0-1.0)
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in this feedback signal",
    )


__all__ = ["P02FeedbackPayload", "P02UserCorrection", "P03FeedbackPayload", "P08FeedbackPayload"]
