"""IKernelObsPort — K1→K0 observability: telemetry + feedback.

One-way emission of:
  - Metrics (prometheus-style snapshots)
  - Logs (structured entries)
  - Feedback (FeedbackEnvelope for System 2 learning loop)

Offline behaviour:
    LOW priority emissions are dropped.
    NORMAL/HIGH are queued to LocalOutbox.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


class ObsKind(enum.Enum):
    """Observability emission kinds."""

    METRICS = "metrics"
    LOGS = "logs"
    FEEDBACK = "feedback"


class ObsPriority(enum.Enum):
    """Priority for offline queueing decisions.

    LOW      — dropped when offline (telemetry).
    NORMAL   — queued to LocalOutbox when offline.
    HIGH     — queued with priority when offline (feedback).
    """

    LOW = 0
    NORMAL = 1
    HIGH = 2


@dataclass(frozen=True, slots=True)
class FeedbackEnvelope:
    """Feedback signal for K0 System 2 learning loop.

    Carries correction/validation/implicit signals that feed into
    K0 pipelines P02 (memory refinement) and P08 (model tuning).

    Attributes:
        feedback_id: Unique identifier for this feedback signal.
        pipeline_id: Target K0 pipeline (e.g. ``"P02"``, ``"P08"``).
        signal_class: One of CORRECTION, VALIDATION, IMPLICIT,
                      EXPLICIT, OUTCOME.
        correlation: Links to originating session/events.
        provenance: Source message and context hashes.
        payload: Pipeline-specific feedback data.
        trace_id: Cognitive trace ID for distributed tracing.
    """

    feedback_id: str = ""
    pipeline_id: str = ""
    signal_class: str = ""
    correlation: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IKernelObsPort(Protocol):
    """K1→K0 observability emission port.

    Fire-and-forget for metrics and logs.
    Feedback envelopes are higher priority and queued when offline.
    """

    async def emit(
        self,
        kind: str,
        body: dict[str, Any],
        *,
        priority: str = "NORMAL",
        trace_id: str = "",
    ) -> None:
        """Emit a single observability payload to K0.

        Args:
            kind: One of ``"metrics"``, ``"logs"``, ``"feedback"``.
            body: Payload data (structure depends on kind).
            priority: ``"LOW"`` (drop offline), ``"NORMAL"`` (queue),
                      ``"HIGH"`` (queue with priority).
            trace_id: Cognitive trace ID.
        """
        ...  # pragma: no cover

    async def emit_feedback(
        self,
        envelope: FeedbackEnvelope,
    ) -> None:
        """Emit a structured feedback envelope to K0 System 2.

        Always HIGH priority — queued when offline.

        Args:
            envelope: FeedbackEnvelope with correlation and provenance.
        """
        ...  # pragma: no cover
