"""Core types for the Universal Reconciliation Engine (M9.2+).

Defines the universal data structures used across all reconciliation
milestones: identity strategies, framework, merge planner, and truth writer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class K1SignalBundle:
    """K1 correction/contradiction signals carried per-event."""

    correction_signal: bool = False
    contradiction_signal: bool = False
    supersedes_concept: str = ""
    correction_source: str = ""
    session_context_id: str = ""


@dataclass(frozen=True)
class ReconciliationCandidate:
    """Universal input to identity strategies and the reconciliation framework.

    Built from phase outputs (R2 EpisodeCandidate, R3 PatternCandidate,
    R4 EntityCandidate/EdgeCandidate, R5 InsightCandidate).
    """

    # Identity
    candidate_id: str
    layer: str
    source_phase: str

    # Embedding (768-dim, L2-normalized)
    embedding: list[float] | None = None

    # Metadata (layer-specific, read by IdentityStrategy)
    metadata: dict[str, Any] = field(default_factory=dict)

    # K1 signals (Tier 1 override)
    k1_signals: K1SignalBundle = field(default_factory=K1SignalBundle)

    # Provenance
    source_event_ids: tuple[str, ...] = ()
    cycle_id: str = ""
    tenant_id: str = ""
    space_id: str = ""


@dataclass(frozen=True)
class TruthRecord:
    """Existing record from a truth table (output of truth_candidates_query).

    Wraps the raw DB row with typed access to common fields.
    """

    record_id: str
    layer: str
    embedding: list[float] | None = None
    confidence: float = 0.0
    version: int = 0
    observation_count: int = 0
    last_observed_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IdentityResult:
    """Output from ``IdentityStrategy.score_identity()``.

    Contains the identity score and probability distribution
    over reconciliation actions.
    """

    score: float

    p_create: float
    p_extend: float
    p_reinforce: float

    recommended_action: str

    features: dict[str, float] = field(default_factory=dict)

    key_matched: bool | None = None
