"""
Memory Writer v2 Event Definitions -- All events MW produces and consumes.

Defines topic constants and frozen payload dataclasses for every event
the Memory Writer emits or subscribes to on the K1 Bus.

Source of truth:
  - k1/contracts/modules/memory_writer/module.contract.yaml (events section)
  - k1/contracts/modules/memory_writer/wiring.contract.yaml (events section)
  - docs/plans/MASTER_IMPLEMENTATION_SKELETON.md Epic 1.9

Consumed (input triggers):
  turn.complete.v1 -- Concierge emits after DELIVERING; triggers MW pipeline.

Produced (observability):
  k1.mw.filter.decision.v1    -- After relevance filter evaluates a turn.
  k1.mw.extraction.complete.v1 -- After successful LLM extraction + validation.
  k1.mw.batch.submitted.v1    -- After batch submitted to Bridge.
  k1.mw.pipeline.error.v1     -- On any pipeline stage error.
  k1.mw.circuit.open.v1       -- When LLM circuit breaker trips to OPEN.

Import graph:
  - k1.memory_writer.events -> stdlib only (dataclasses, typing)
  - NEVER import from service, port, or adapter modules
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ===========================================================================
# Topic Constants
# ===========================================================================

# --- Consumed ---
TOPIC_TURN_COMPLETE = "turn.complete.v1"

# --- Produced (observability) ---
TOPIC_FILTER_DECISION = "k1.mw.filter.decision.v1"
TOPIC_EXTRACTION_COMPLETE = "k1.mw.extraction.complete.v1"
TOPIC_BATCH_SUBMITTED = "k1.mw.batch.submitted.v1"
TOPIC_PIPELINE_ERROR = "k1.mw.pipeline.error.v1"
TOPIC_CIRCUIT_OPEN = "k1.mw.circuit.open.v1"

# Convenience tuple of all topics MW produces (for subscription validation)
ALL_PRODUCED_TOPICS = (
    TOPIC_FILTER_DECISION,
    TOPIC_EXTRACTION_COMPLETE,
    TOPIC_BATCH_SUBMITTED,
    TOPIC_PIPELINE_ERROR,
    TOPIC_CIRCUIT_OPEN,
)

# Convenience tuple of all topics MW consumes
ALL_CONSUMED_TOPICS = (TOPIC_TURN_COMPLETE,)


# ===========================================================================
# Consumed Event Payloads
# ===========================================================================


@dataclass(frozen=True)
class TurnCompletePayload:
    """Payload for turn.complete.v1 -- the sole input trigger for MW.

    Emitted by Concierge after DELIVERING state.
    """

    turn_id: str
    session_id: str
    cognitive_trace_id: str
    user_message: str
    assistant_response: str
    timestamp_ms: int
    turn_number: int
    # Temporal/spatial context from beliefs_active (GAP-002 Epic 1.1, eliminates race condition T7)
    mentioned_time_raw: str = ""
    mentioned_time_resolved_ms: int = 0
    mentioned_time_confidence: float = 0.0
    mentioned_time_is_relative: bool = True
    mentioned_location_raw: str = ""
    mentioned_location_type: str = ""
    mentioned_location_entity_id: str = ""
    mentioned_location_confidence: float = 0.0


# ===========================================================================
# Produced Event Payloads
# ===========================================================================


@dataclass(frozen=True)
class FilterDecisionEvent:
    """Payload for k1.mw.filter.decision.v1.

    Emitted after every RelevanceFilter evaluation (PASS or SKIP).
    Zero LLM cost -- pure rule evaluation.
    """

    turn_id: str
    decision: str  # "PASS" or "SKIP"
    skip_reason: Optional[str]  # SkipReason value or None when PASS
    latency_ms: float


@dataclass(frozen=True)
class ExtractionCompleteEvent:
    """Payload for k1.mw.extraction.complete.v1.

    Emitted after successful LLM extraction + validation.
    """

    turn_id: str
    atom_count: int
    total_tokens: int
    latency_ms: float


@dataclass(frozen=True)
class BatchSubmittedEvent:
    """Payload for k1.mw.batch.submitted.v1.

    Emitted after a batch is submitted to Bridge via IBridgeCommandPort.
    """

    batch_id: str
    envelope_count: int
    bridge_latency_ms: float


@dataclass(frozen=True)
class PipelineErrorEvent:
    """Payload for k1.mw.pipeline.error.v1.

    Emitted when any pipeline stage encounters an error.
    The pipeline skips to the next turn (no retry).
    """

    turn_id: str
    stage: str  # "filter", "context", "extraction", "envelope", "batch"
    error_type: str  # Exception class name or error category
    message: str


@dataclass(frozen=True)
class CircuitOpenEvent:
    """Payload for k1.mw.circuit.open.v1.

    Emitted when the LLM circuit breaker trips from CLOSED to OPEN.
    While OPEN, WriterAgent.extract() returns empty list (no LLM calls).
    """

    failure_count: int
    recovery_probe_at: str  # ISO 8601 UTC timestamp of next probe attempt
