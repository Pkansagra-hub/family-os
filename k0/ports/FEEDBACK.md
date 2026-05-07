# Feedback Wiring Guide

**Purpose**: Developer guide for wiring feedback between K1 (orchestration) and K0 (memory kernel).
**Last Updated**: 2025-12-24
**Related Plan**: [FEEDBACK-issues-tracker.md](../../docs/plans/defered/FEEDBACK-issues-tracker.md)

---

## Quick Navigation

| I am a... | I need to... | Go to... |
|-----------|--------------|----------|
| **K1 Developer** | Emit feedback to K0 | [Part 1: K1 Developer Guide](#part-1-k1-developer-guide) |
| **K0 Developer** | Receive feedback in my pipeline | [Part 2: K0 Developer Guide](#part-2-k0-developer-guide) |
| **Both** | Understand the architecture | [Architecture Overview](#architecture-overview) |

---

## Architecture Overview

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                        K1 (Orchestration Kernel)                         │
│                                                                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐   │
│  │   User Agent    │  │ Curiosity       │  │ Implicit Feedback       │   │
│  │                 │  │ Engine          │  │ Detectors               │   │
│  │ • Conversations │  │ • Gap detection │  │ • ReformulationDetector │   │
│  │ • Corrections   │  │ • Questions     │  │ • AbandonmentDetector   │   │
│  │ • Validations   │  │ • Learning loop │  │ • HedgingDetector       │   │
│  └────────┬────────┘  └────────┬────────┘  └────────────┬────────────┘   │
│           │                    │                        │                │
│           └────────────────────┼────────────────────────┘                │
│                                │                                         │
│                                ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    ConversationContext                              │ │
│  │  • Tracks event_ids, recall_ids, response_ids per session          │ │
│  │  • Caches correlation context for feedback emission                │ │
│  └────────────────────────────────┬────────────────────────────────────┘ │
│                                   │                                      │
│                                   ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    FeedbackEnvelope (Pydantic)                      │ │
│  │  • feedback_id, pipeline_id, signal_class                          │ │
│  │  • correlation: CorrelationIds (event_ids, session_id, etc.)       │ │
│  │  • provenance: FeedbackProvenance (hashes, timestamps)             │ │
│  │  • payload: dict (pipeline-specific, JSONB)                        │ │
│  └────────────────────────────────┬────────────────────────────────────┘ │
└───────────────────────────────────┼──────────────────────────────────────┘
                                    │
                                    ▼  HTTP POST /k0/obs.emit
┌───────────────────────────────────────────────────────────────────────────┐
│                          K0 (Memory Kernel)                               │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                      observe.py (kind: "feedback")                   │ │
│  │  • Receives FeedbackEnvelope                                         │ │
│  │  • Validates via FeedbackSchemaRegistry                              │ │
│  │  • Persists to st_feedback_signals                                   │ │
│  │  • Publishes to BusDispatcher topic (uses BUS_MESSAGE_ID_KEY)       │ │
│  └───────────────────────────────────┬──────────────────────────────────┘ │
│                                      │                                    │
│                   ┌──────────────────┼──────────────────┐                 │
│                   ▼                  ▼                  ▼                 │
│  ┌────────────────────┐ ┌────────────────┐ ┌────────────────────────────┐ │
│  │ feedback.signal.p02│ │feedback.signal │ │ feedback.signal.<pipeline>│ │
│  │ P02FeedbackHandler │ │.P08            │ │ (Your pipeline)           │ │
│  │ • Memory updates   │ │P08FeedbackHndlr│ │ • Subscribe to topic      │ │
│  │ • Salience adjust  │ │• Re-embed      │ │ • Handle signal classes   │ │
│  └────────────────────┘ └────────────────┘ └────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

### Entity ID Reference (K0 Schema)

| Column | Type | Table | Purpose |
|--------|------|-------|---------|
| `event_id` | TEXT (UUID) | `st_hipp_events` | **Primary Key** - unique per memory event |
| `cognitive_trace_id` | TEXT | `st_hipp_events` | End-to-end trace - spans multiple events |
| `wal_pos` | INTEGER | `st_wal` | WAL position (monotonic, FK from hipp_events) |
| `embedding_id` | TEXT (UUID) | `st_hipp_events` | Join key to st_vec (1:1 with event_id) |
| `episode_cluster_id` | TEXT | `st_hipp_events` | P03 cluster assignment (NULL until consolidated) |

**Critical Distinction**:

- `event_id` = **THE entity identifier** for feedback targeting (unique per memory)
- `cognitive_trace_id` = **observability correlation** (1 trace → N events in same request)

### Bus Message Metadata Constants

| Constant | Value | Purpose |
|----------|-------|----------|
| `BUS_MESSAGE_ID_KEY` | `"message_id"` | Metadata key for feedback stream message identification (replaces hardcoded strings) |

**Usage**: Import from `k0.bus` when constructing BusMessage objects for the feedback stream:

```python
from k0.bus import BusDispatcher, BusMessage, BUS_MESSAGE_ID_KEY
from k0.feedback.topics import feedback_signal_topic

# Good: Use constant
message = BusMessage(
    topic=feedback_signal_topic("P02", version="v1"),
    stream="feedback",
    payload={...},
    metadata={BUS_MESSAGE_ID_KEY: feedback_id}  # ✅
)

# Bad: Hardcoded string
metadata={"message_id": feedback_id}  # ❌
```

---

# Part 1: K1 Developer Guide

**Audience**: K1 orchestration kernel developers who need to emit feedback to K0.

---

## K1 Step 1: Track Correlation Context

Every conversation turn must track which K0 entities were involved:

```python
# k1/feedback/context.py

from dataclasses import dataclass, field
from typing import Optional
import uuid


@dataclass
class ConversationContext:
    """
    Tracks K0 entity IDs through a conversation turn.

    IMPORTANT: Cache this per session. When user provides feedback,
    you need these IDs to tell K0 WHICH entities the feedback is about.
    """

    session_id: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # K0 entity references (populated during conversation)
    wal_positions: list[int] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)  # st_hipp_events.event_id

    # K1 operation references
    recall_id: Optional[str] = None
    response_id: Optional[str] = None
    grounded_event_ids: list[str] = field(default_factory=list)  # Events actually used in response

    def record_ingestion(self, wal_pos: int, event_ids: list[str]) -> None:
        """Call after K0 command.submit returns."""
        self.wal_positions.append(wal_pos)
        self.event_ids.extend(event_ids)

    def record_recall(self, recall_id: str, event_ids: list[str]) -> None:
        """Call after K0 query.recall returns."""
        self.recall_id = recall_id
        self.event_ids.extend(event_ids)

    def record_response(self, response_id: str, grounded_event_ids: list[str]) -> None:
        """Call after LLM generates response with grounded memories."""
        self.response_id = response_id
        self.grounded_event_ids = grounded_event_ids


# Global cache - use Redis/session store in production
_conversation_contexts: dict[str, ConversationContext] = {}


def get_context(session_id: str) -> ConversationContext | None:
    """Get cached context for feedback correlation."""
    return _conversation_contexts.get(session_id)


def set_context(session_id: str, context: ConversationContext) -> None:
    """Cache context after response generation."""
    _conversation_contexts[session_id] = context
```

---

## K1 Step 2: Capture Context During Response Generation

```python
# k1/agents/conversation.py

from k1.feedback.context import ConversationContext, set_context
from k1.clients.k0 import K0Client
import uuid


async def generate_response(session_id: str, user_message: str) -> str:
    """
    Generate response and capture correlation context for feedback.
    """
    # Create context for this turn
    context = ConversationContext(
        session_id=session_id,
        message_id=str(uuid.uuid4()),
    )

    # 1. Recall memories from K0
    recall_result = await K0Client.recall(
        space_id=get_space_id(),
        query=user_message,
    )

    # Record what was recalled (CRITICAL for feedback correlation)
    context.record_recall(
        recall_id=recall_result.recall_id,
        event_ids=recall_result.event_ids,  # These are st_hipp_events.event_id values
    )

    # 2. Generate LLM response
    response = await llm.generate(
        prompt=user_message,
        context=recall_result.memories,
    )

    # Record which memories were grounded in the response
    context.record_response(
        response_id=str(uuid.uuid4()),
        grounded_event_ids=response.grounded_event_ids,
    )

    # 3. Cache context for feedback correlation (CRITICAL)
    set_context(session_id, context)

    return response.text
```

---

## K1 Step 3: Detect Feedback Signals

Implement detectors for different feedback types:

### 3a. Explicit Correction Detection

```python
# k1/feedback/detectors/correction.py

import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class CorrectionSignal:
    """Detected user correction."""
    target_event_id: str
    original_content: str
    corrected_content: str
    confidence: float


async def detect_correction(
    user_message: str,
    previous_response: str,
    grounded_event_ids: list[str],
    event_contents: dict[str, str],  # event_id -> content
) -> Optional[CorrectionSignal]:
    """
    Detect if user is correcting a memory.

    Patterns to detect:
    - "No, I actually..."
    - "That's wrong, it was..."
    - "I stopped doing X"
    - "It's not X, it's Y"
    """

    correction_patterns = [
        r"no,?\s+(i|it|that|we)\s+(actually|really|was|were|is)",
        r"that'?s?\s+(wrong|incorrect|not\s+right)",
        r"i\s+(stopped|don'?t|no\s+longer)",
        r"it'?s?\s+not\s+.+,?\s+(it'?s?|but)",
    ]

    for pattern in correction_patterns:
        if re.search(pattern, user_message.lower()):
            # User is correcting - determine which memory
            # In production, use LLM to identify target memory
            if grounded_event_ids:
                target_id = grounded_event_ids[0]  # Simplification
                return CorrectionSignal(
                    target_event_id=target_id,
                    original_content=event_contents.get(target_id, ""),
                    corrected_content=user_message,
                    confidence=0.85,
                )

    return None
```

### 3b. Validation Detection

```python
# k1/feedback/detectors/validation.py

@dataclass
class ValidationSignal:
    """User validated or invalidated a memory."""
    target_event_id: str
    is_valid: bool  # True = confirmed, False = denied
    confidence: float


async def detect_validation(
    user_message: str,
    grounded_event_ids: list[str],
) -> Optional[ValidationSignal]:
    """
    Detect if user is validating/confirming a memory.

    Positive patterns: "Yes", "That's right", "Correct", "Exactly"
    Negative patterns: "No", "That's wrong", "I don't think so"
    """

    positive_patterns = [
        r"^yes\b",
        r"that'?s?\s+(right|correct|true)",
        r"^exactly\b",
        r"^correct\b",
    ]

    negative_patterns = [
        r"^no\b",
        r"that'?s?\s+(wrong|incorrect|false)",
        r"i\s+don'?t\s+think\s+so",
    ]

    for pattern in positive_patterns:
        if re.search(pattern, user_message.lower()):
            if grounded_event_ids:
                return ValidationSignal(
                    target_event_id=grounded_event_ids[0],
                    is_valid=True,
                    confidence=0.90,
                )

    for pattern in negative_patterns:
        if re.search(pattern, user_message.lower()):
            if grounded_event_ids:
                return ValidationSignal(
                    target_event_id=grounded_event_ids[0],
                    is_valid=False,
                    confidence=0.85,
                )

    return None
```

### 3c. Implicit Feedback Detection

```python
# k1/feedback/detectors/implicit.py

from datetime import datetime, timezone
from dataclasses import dataclass


@dataclass
class ReformulationSignal:
    """User rephrased query after poor response."""
    affected_event_ids: list[str]
    confidence: float


@dataclass
class AbandonmentSignal:
    """User abandoned session without resolution."""
    affected_event_ids: list[str]
    session_duration_seconds: int


async def detect_reformulation(
    current_message: str,
    previous_message: str,
    previous_event_ids: list[str],
) -> Optional[ReformulationSignal]:
    """
    Detect if user is rephrasing because previous response was poor.

    Heuristic: High semantic similarity + different wording = reformulation
    """
    # Use embedding similarity
    from k1.nlp import compute_similarity

    similarity = await compute_similarity(current_message, previous_message)

    # High semantic overlap + different words = user is trying again
    if similarity > 0.7 and current_message != previous_message:
        return ReformulationSignal(
            affected_event_ids=previous_event_ids,
            confidence=0.6 + (similarity - 0.7) * 0.5,  # 0.6-0.75 range
        )

    return None


async def detect_abandonment(
    session_id: str,
    last_activity: datetime,
    unresolved_event_ids: list[str],
    timeout_seconds: int = 300,  # 5 minutes
) -> Optional[AbandonmentSignal]:
    """
    Detect if user abandoned session without resolution.

    Trigger: No activity for 5+ minutes after recall without positive signal.
    """
    now = datetime.now(timezone.utc)
    elapsed = (now - last_activity).total_seconds()

    if elapsed > timeout_seconds and unresolved_event_ids:
        return AbandonmentSignal(
            affected_event_ids=unresolved_event_ids,
            session_duration_seconds=int(elapsed),
        )

    return None
```

---

## K1 Step 4: Emit Feedback to K0

```python
# k1/feedback/emitter.py

import httpx
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from k1.feedback.context import get_context


async def emit_feedback_to_k0(
    session_id: str,
    pipeline_id: str,
    signal_class: str,  # "CORRECTION" | "VALIDATION" | "IMPLICIT" | "EXPLICIT" | "OUTCOME"
    signal_subtype: str,
    target_event_id: str,
    payload: dict[str, Any],
) -> None:
    """
    Emit feedback signal to K0 observe port.

    Args:
        session_id: Current conversation session
        pipeline_id: Target K0 pipeline (e.g., "P02", "P08")
        signal_class: Category of feedback signal
        signal_subtype: Specific signal type (e.g., "user_correction", "abandonment")
        target_event_id: The st_hipp_events.event_id this feedback is about
        payload: Pipeline-specific payload (will be stored as JSONB)
    """

    # Get cached correlation context
    context = get_context(session_id)
    if not context:
        raise ValueError(f"No correlation context for session: {session_id}")

    # Build correlation IDs
    correlation = {
        "session_id": context.session_id,
        "message_id": context.message_id,
        "wal_positions": context.wal_positions,
        "event_ids": list(set(context.event_ids)),
        "recall_id": context.recall_id,
        "response_id": context.response_id,
        "target_entity_type": "event",  # Targeting a st_hipp_events row
        "target_entity_id": target_event_id,
    }

    # Build provenance (for audit trail)
    recall_context = {
        "event_ids": context.event_ids,
        "grounded": context.grounded_event_ids,
    }
    provenance = {
        "source_message_id": context.message_id,
        "recall_context_hash": hashlib.sha256(
            json.dumps(recall_context, sort_keys=True).encode()
        ).hexdigest(),
        "feedback_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Build envelope
    envelope = {
        "feedback_id": str(uuid.uuid4()),
        "pipeline_id": pipeline_id,
        "tenant_id": get_tenant_id(),  # Your tenant resolution
        "space_id": get_space_id(),    # Your space resolution
        "signal_class": signal_class,
        "signal_subtype": signal_subtype,
        "correlation": correlation,
        "provenance": provenance,
        "payload": payload,
    }

    # Send to K0 observe port
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "http://k0-kernel:8000/k0/obs.emit",
            json={
                "kind": "feedback",
                "body": envelope,
            },
        )
        response.raise_for_status()
```

---

## K1 Step 5: Wire It All Together

```python
# k1/agents/feedback_handler.py

from k1.feedback.context import get_context
from k1.feedback.detectors.correction import detect_correction
from k1.feedback.detectors.validation import detect_validation
from k1.feedback.detectors.implicit import detect_reformulation
from k1.feedback.emitter import emit_feedback_to_k0


async def process_user_message_for_feedback(
    session_id: str,
    user_message: str,
    previous_message: str,
    previous_response: str,
) -> None:
    """
    Check user message for feedback signals and emit to K0.
    Call this BEFORE generating the next response.
    """

    context = get_context(session_id)
    if not context:
        return  # No prior context, skip feedback detection

    # Check for explicit correction
    correction = await detect_correction(
        user_message=user_message,
        previous_response=previous_response,
        grounded_event_ids=context.grounded_event_ids,
        event_contents={},  # Load from your cache
    )

    if correction:
        await emit_feedback_to_k0(
            session_id=session_id,
            pipeline_id="P02",
            signal_class="CORRECTION",
            signal_subtype="user_explicit_correction",
            target_event_id=correction.target_event_id,
            payload={
                "original_content": correction.original_content,
                "corrected_content": correction.corrected_content,
                "confidence": correction.confidence,
            },
        )
        return  # Don't double-count

    # Check for validation
    validation = await detect_validation(
        user_message=user_message,
        grounded_event_ids=context.grounded_event_ids,
    )

    if validation:
        await emit_feedback_to_k0(
            session_id=session_id,
            pipeline_id="P02",
            signal_class="VALIDATION",
            signal_subtype="user_memory_validation",
            target_event_id=validation.target_event_id,
            payload={
                "is_valid": validation.is_valid,
                "confidence": validation.confidence,
            },
        )
        return

    # Check for reformulation (implicit negative)
    reformulation = await detect_reformulation(
        current_message=user_message,
        previous_message=previous_message,
        previous_event_ids=context.event_ids,
    )

    if reformulation:
        # Emit negative signal for all affected events
        for event_id in reformulation.affected_event_ids:
            await emit_feedback_to_k0(
                session_id=session_id,
                pipeline_id="P02",
                signal_class="IMPLICIT",
                signal_subtype="reformulation_detected",
                target_event_id=event_id,
                payload={
                    "confidence": reformulation.confidence,
                    "signal_polarity": "negative",
                },
            )
```

---

## K1 Checklist

When implementing feedback in K1:

- [ ] Implement `ConversationContext` tracking per session
- [ ] Call `record_recall()` after every K0 query.recall
- [ ] Call `record_response()` after LLM generates response with grounded memories
- [ ] Cache context via `set_context()` for feedback correlation
- [ ] Implement correction detector (explicit user corrections)
- [ ] Implement validation detector (yes/no confirmations)
- [ ] Implement reformulation detector (implicit negative)
- [ ] Implement abandonment detector (session timeout)
- [ ] Call `emit_feedback_to_k0()` when signals are detected
- [ ] Handle HTTP errors gracefully (K0 might be unavailable)

---

# Part 2: K0 Developer Guide

**Audience**: K0 memory kernel developers who need to receive and handle feedback in their pipeline.

---

## K0 Step 1: Define Your Pipeline's Feedback Schema

Each pipeline has its **own feedback schema**. Do NOT create a universal schema.

```python
# k0/pipelines/pXX_your_pipeline/feedback.py

from pydantic import BaseModel, Field
from typing import Literal, Optional


class PXXFeedbackPayload(BaseModel):
    """
    Feedback payload specific to PXX pipeline.

    This schema defines what K1 can send to YOUR pipeline.
    Be specific about what fields you need.
    """

    # Required: What entity was feedback about?
    # This should match your pipeline's entity type
    target_entity_id: str = Field(..., description="ID of entity being rated")

    # Required: What happened?
    signal_type: Literal["positive", "negative", "correction", "validation"]

    # Optional: Pipeline-specific context
    your_pipeline_specific_field: Optional[str] = None

    # Optional: Confidence in this feedback (0.0 - 1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
```

### Example: P02 (Write/Hippocampus Pipeline)

```python
# k0/pipelines/p02_write/feedback.py

class P02FeedbackPayload(BaseModel):
    """Feedback for P02 - memory quality and corrections."""

    # Target is event_id from st_hipp_events
    event_id: str = Field(..., description="st_hipp_events.event_id")

    # What kind of feedback?
    feedback_type: Literal["correction", "validation", "quality"]

    # For corrections: what was wrong?
    original_content: Optional[str] = None
    corrected_content: Optional[str] = None

    # For validations: was the memory accurate?
    is_valid: Optional[bool] = None

    # For quality: how good was the extraction?
    extraction_quality: Optional[Literal["good", "partial", "poor"]] = None

    # Confidence in this feedback
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
```

### Example: P08 (Embeddings Pipeline)

```python
# k0/pipelines/p08_embeddings/feedback.py

class P08FeedbackPayload(BaseModel):
    """Feedback for P08 - embedding quality and retrieval relevance."""

    # Target is event_id (same as st_vec PK)
    event_id: str = Field(..., description="st_vec.event_id")

    # Retrieval outcome
    retrieval_hit: bool = Field(..., description="Was this embedding retrieved?")
    retrieval_rank: Optional[int] = Field(None, description="Position in results (1=best)")

    # User relevance judgment
    user_relevance: Literal["relevant", "irrelevant", "partial"]

    # Confidence
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
```

---

## K0 Step 2: Register Schema in FeedbackSchemaRegistry

```python
# k0/ports/feedback_registry.py

from pydantic import BaseModel
from typing import Type


class FeedbackSchemaRegistry:
    """
    Registry for pipeline-specific feedback schemas.

    Validates incoming feedback payloads before routing to handlers.
    """

    _schemas: dict[str, Type[BaseModel]] = {}
    _permissive_mode: bool = True  # Allow unknown pipelines in dev

    @classmethod
    def register(cls, pipeline_id: str, schema: Type[BaseModel]) -> None:
        """Register a feedback schema for a pipeline."""
        cls._schemas[pipeline_id] = schema

    @classmethod
    def validate(cls, pipeline_id: str, payload: dict) -> BaseModel | dict:
        """
        Validate payload against registered schema.

        Returns validated Pydantic model or raw dict if permissive.
        """
        schema = cls._schemas.get(pipeline_id)
        if schema:
            return schema.model_validate(payload)
        elif cls._permissive_mode:
            return payload  # Pass through unvalidated
        else:
            raise ValueError(f"No schema registered for pipeline: {pipeline_id}")

    @classmethod
    def list_registered(cls) -> list[str]:
        """List all registered pipeline IDs."""
        return list(cls._schemas.keys())


# === REGISTRATION ===
# Add your pipeline here when you create its feedback schema

from k0.pipelines.p02_write.feedback import P02FeedbackPayload
from k0.pipelines.p08_embeddings.feedback import P08FeedbackPayload

FeedbackSchemaRegistry.register("P02", P02FeedbackPayload)
FeedbackSchemaRegistry.register("P08", P08FeedbackPayload)

# Future pipelines:
# FeedbackSchemaRegistry.register("P03", P03FeedbackPayload)
# FeedbackSchemaRegistry.register("PXX", PXXFeedbackPayload)
```

---

## K0 Step 3: Create Feedback Handler for Your Pipeline

```python
# k0/pipelines/pXX_your_pipeline/feedback_handler.py

from k0.bus import BusDispatcher, BUS_MESSAGE_ID_KEY
from k0.db.session import get_session
from typing import Any
import logging

logger = logging.getLogger(__name__)


class PXXFeedbackHandler:
    """
    Handle feedback signals for PXX pipeline.

    Subscribe to feedback.signal.<pipeline>.v1 topic and process signals.
    """

    def __init__(self, bus: BusDispatcher):
        self.bus = bus
        # Subscribe to YOUR pipeline's feedback topic
        bus.subscribe("feedback.signal.pxx.v1", self.handle_feedback)

    async def handle_feedback(self, envelope: dict) -> None:
        """
        Main entry point for feedback processing.

        Routes to specific handlers based on signal_class.
        """
        signal_class = envelope.get("signal_class")
        correlation = envelope.get("correlation", {})
        payload = envelope.get("payload", {})

        target_id = correlation.get("target_entity_id")

        logger.info(
            f"PXX received feedback: signal_class={signal_class}, "
            f"target={target_id}"
        )

        match signal_class:
            case "CORRECTION":
                await self._handle_correction(target_id, payload)
            case "VALIDATION":
                await self._handle_validation(target_id, payload)
            case "IMPLICIT":
                await self._handle_implicit(target_id, payload)
            case "EXPLICIT":
                await self._handle_explicit(target_id, payload)
            case "OUTCOME":
                await self._handle_outcome(target_id, payload)
            case _:
                logger.warning(f"Unknown signal_class: {signal_class}")

    async def _handle_correction(self, target_id: str, payload: dict) -> None:
        """
        User explicitly corrected something.

        HIGHEST priority - user is telling us we're wrong.
        """
        # TODO: Implement your correction logic
        # Example: Update entity content, mark as corrected
        pass

    async def _handle_validation(self, target_id: str, payload: dict) -> None:
        """
        User confirmed or denied a recall.

        HIGH priority - direct user feedback on accuracy.
        """
        is_valid = payload.get("is_valid", True)

        if is_valid:
            # Boost confidence/salience
            await self._boost_entity(target_id, reason="user_validation")
        else:
            # Mark as potentially stale
            await self._mark_stale(target_id, reason="user_rejection")

    async def _handle_implicit(self, target_id: str, payload: dict) -> None:
        """
        Inferred from user behavior (reformulation, abandonment, hedging).

        MEDIUM priority - behavioral signal, lower confidence.
        """
        signal_polarity = payload.get("signal_polarity", "negative")
        confidence = payload.get("confidence", 0.5)

        if signal_polarity == "negative":
            # Reduce salience proportional to confidence
            await self._reduce_salience(target_id, factor=confidence)

    async def _handle_explicit(self, target_id: str, payload: dict) -> None:
        """
        Direct user feedback (thumbs up/down, ratings).

        HIGH priority - explicit user signal.
        """
        pass

    async def _handle_outcome(self, target_id: str, payload: dict) -> None:
        """
        Result of downstream processing.

        MEDIUM priority - system-generated signal.
        """
        pass

    # === Helper methods ===

    async def _boost_entity(self, entity_id: str, reason: str) -> None:
        """Boost salience/confidence of an entity."""
        # Implement based on your pipeline's schema
        pass

    async def _mark_stale(self, entity_id: str, reason: str) -> None:
        """Mark entity as potentially outdated."""
        pass

    async def _reduce_salience(self, entity_id: str, factor: float) -> None:
        """Reduce salience by a factor (0-1)."""
        pass
```

---

## K0 Step 4: Register Bus Topic

**Important**: When constructing BusMessage objects for feedback topics, always use `BUS_MESSAGE_ID_KEY` for the metadata key:

```python
from k0.bus import BUS_MESSAGE_ID_KEY

# In your handler:
metadata = {BUS_MESSAGE_ID_KEY: feedback_id}
```

```python
# k0/bus/topics.py

# Feedback topics - one per pipeline that accepts feedback
FEEDBACK_TOPICS = [
    "feedback.signal.p02.v1",
    "feedback.signal.p08.v1",
    # Add your pipeline here:
    # "feedback.signal.pxx.v1",
]
```

---

## K0 Step 5: Implement Adaptive Parameters (Optional)

If your pipeline has tunable parameters, use Thompson Sampling:

```python
# k0/pipelines/pXX_your_pipeline/adaptive.py

import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AdaptiveParameter:
    """
    Thompson Sampling for adaptive parameter learning.

    Use this for any parameter you want to tune based on feedback.
    """

    name: str
    min_value: float
    max_value: float
    alpha: float = 1.0  # Beta distribution prior (successes + 1)
    beta: float = 1.0   # Beta distribution prior (failures + 1)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def sample(self) -> float:
        """Sample from posterior distribution (Thompson Sampling)."""
        sampled = np.random.beta(self.alpha, self.beta)
        # Scale to parameter range
        return self.min_value + sampled * (self.max_value - self.min_value)

    def update(self, success: bool) -> None:
        """Update posterior based on feedback outcome."""
        if success:
            self.alpha += 1
        else:
            self.beta += 1
        self.last_updated = datetime.now(timezone.utc)

    @property
    def mean(self) -> float:
        """Current expected value."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        """Current uncertainty."""
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total ** 2 * (total + 1))


# Example: Per-parameter bandits for P03 consolidation
class P03AdaptiveParams:
    def __init__(self):
        self.similarity_threshold = AdaptiveParameter(
            name="similarity_threshold",
            min_value=0.5,
            max_value=0.95,
        )
        self.decay_lambda = AdaptiveParameter(
            name="decay_lambda",
            min_value=0.001,
            max_value=0.01,
        )
        self.salience_boost = AdaptiveParameter(
            name="salience_boost",
            min_value=0.05,
            max_value=0.3,
        )

    def receive_feedback(self, param_name: str, success: bool) -> None:
        """Update specific parameter based on feedback."""
        param = getattr(self, param_name, None)
        if param:
            param.update(success)
```

---

## K0 Step 6: Database Migration (st_feedback_signals)

```sql
-- migrations/0025_create_st_feedback_signals.sql

CREATE TABLE st_feedback_signals (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id TEXT UNIQUE NOT NULL,

    -- Routing
    pipeline_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    -- Classification
    signal_class TEXT NOT NULL,  -- OUTCOME, CORRECTION, IMPLICIT, EXPLICIT, VALIDATION
    signal_subtype TEXT NOT NULL,

    -- Correlation (links back to K0 entities)
    correlation JSONB NOT NULL,
    -- Example: {"session_id": "...", "event_ids": ["..."], "target_entity_id": "..."}

    -- Provenance (audit trail)
    provenance JSONB NOT NULL,
    -- Example: {"source_message_id": "...", "recall_context_hash": "...", "feedback_timestamp": "..."}

    -- Payload (pipeline-specific)
    payload JSONB NOT NULL,
    payload_hash TEXT NOT NULL,  -- SHA-256 for deduplication

    -- Processing state
    created_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ,
    processing_status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed

    -- Constraints
    CHECK (signal_class IN ('OUTCOME', 'CORRECTION', 'IMPLICIT', 'EXPLICIT', 'VALIDATION')),
    CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed'))
);

-- Indexes
CREATE INDEX idx_feedback_pipeline ON st_feedback_signals(pipeline_id, created_at DESC);
CREATE INDEX idx_feedback_tenant ON st_feedback_signals(tenant_id, space_id);
CREATE INDEX idx_feedback_status ON st_feedback_signals(processing_status)
    WHERE processing_status = 'pending';
CREATE INDEX idx_feedback_target ON st_feedback_signals(
    (correlation->>'target_entity_id')
);
```

---

## K0 Checklist

When adding feedback support to a new K0 pipeline (PXX):

- [ ] Create `k0/pipelines/pXX/feedback.py` with Pydantic payload schema
- [ ] Register schema in `FeedbackSchemaRegistry` (k0/ports/feedback_registry.py)
- [ ] Add `feedback.signal.PXX` to FEEDBACK_TOPICS (k0/bus/topics.py)
- [ ] Prefer using `k0.feedback.topics.feedback_signal_topic("PXX")` when constructing a pipeline-specific topic.
- [ ] Create `PXXFeedbackHandler` with topic subscription
- [ ] Import `BUS_MESSAGE_ID_KEY` from `k0.bus` for metadata construction
- [ ] Implement handlers for each signal_class you support:
  - [ ] `_handle_correction()` - user corrections
  - [ ] `_handle_validation()` - user confirmations/denials
  - [ ] `_handle_implicit()` - behavioral signals
  - [ ] `_handle_explicit()` - direct ratings
  - [ ] `_handle_outcome()` - system outcomes
- [ ] (Optional) Implement `AdaptiveParameter` for tunable thresholds
- [ ] Update [FEEDBACK-issues-tracker.md](../../docs/plans/defered/FEEDBACK-issues-tracker.md) with new issues
- [ ] Test with mock feedback via observe port

---

# Appendix

## Signal Classes Reference

| Class | Description | Confidence | Source | Priority |
|-------|-------------|------------|--------|----------|
| `CORRECTION` | User explicitly corrected something | High | User | P0 |
| `VALIDATION` | User confirmed/denied memory recall | Very High | User | P0 |
| `EXPLICIT` | User gave direct feedback (thumbs up/down) | High | User | P1 |
| `IMPLICIT` | Inferred from behavior (reformulation, abandonment) | Medium | Detector | P2 |
| `OUTCOME` | Result of downstream processing | Medium | System | P2 |

---

## Implicit Feedback Detectors (K1 implements these)

| Detector | Signal | Confidence | Description |
|----------|--------|------------|-------------|
| `CorrectionDetector` | CORRECTION | 0.85 | User rephrased to correct memory |
| `ValidationDetector` | VALIDATION | 0.90 | User confirmed/denied recall |
| `ReformulationDetector` | IMPLICIT (negative) | 0.60-0.75 | User rephrased query |
| `AbandonmentDetector` | IMPLICIT (negative) | 0.70 | User left without resolution |
| `HedgingDetector` | IMPLICIT (negative) | 0.50 | LLM response was uncertain |

---

## Safety Guardrails

All feedback is subject to:

1. **Rate limiting**: 100 signals/minute per tenant
2. **Duplicate suppression**: Same payload_hash within 5 seconds → ignored
3. **Anomaly detection**: Sudden spike in negative feedback → alert
4. **Schema validation**: BusMessage metadata must use `BUS_MESSAGE_ID_KEY` for feedback stream

---

## Related Documents

- [Issues Tracker](../../docs/plans/defered/FEEDBACK-issues-tracker.md)
- [Full Plan](../../docs/plans/defered/PLAN-feedback-pipeline-system.md)
- [Active Learning Loop Idea](../../docs/architecture/ideas/0001-active-learning-loop.md)
- [Observe Port](observe.py)
- [K0 Ports README](README.md)
