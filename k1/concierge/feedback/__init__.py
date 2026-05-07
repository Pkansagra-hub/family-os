"""K1 concierge feedback subsystem (MS-3e Epic 3e.2).

End-to-end pipeline that turns user-facing conversation signals into
typed :class:`bridge._generated.k1.models.feedback_envelope_v1.FeedbackEnvelopeV1`
emissions on the bridge ``feedback.envelope.v1`` contract.

Components:

* :class:`ConversationContext` — per-session correlation cache linking
  user message -> recall_id, response_id, grounded event_ids. Detectors
  read from it; the emitter stamps it onto the wire envelope.
* :class:`CorrectionDetector`, :class:`ValidationDetector`,
  :class:`ReformulationDetector` — three real-NLP detectors (regex +
  cosine similarity) returning per-class typed signals. No mocks.
* :class:`FeedbackEmitter` — orchestrates detectors and publishes
  ``FeedbackEnvelopeV1`` payloads through ``runtime.obs.feedback_envelope_v1``.

Wiring contract: callers obtain a runtime via ``BridgeRuntime.from_registry``
and pass ``runtime`` to :class:`FeedbackEmitter`. The runtime auto-wires
the ``runtime.obs.feedback_envelope_v1`` slot when the obs manifest is
loaded (see :mod:`bridge.runtime._build_k1_client`, MS-3e).
"""

from __future__ import annotations

from k1.concierge.feedback.context import ConversationContext, get_context, set_context
from k1.concierge.feedback.detectors import (
    CorrectionDetector,
    CorrectionSignal,
    ReformulationDetector,
    ReformulationSignal,
    ValidationDetector,
    ValidationSignal,
)
from k1.concierge.feedback.emitter import FeedbackEmitter

__all__ = [
    "ConversationContext",
    "get_context",
    "set_context",
    "CorrectionDetector",
    "CorrectionSignal",
    "ValidationDetector",
    "ValidationSignal",
    "ReformulationDetector",
    "ReformulationSignal",
    "FeedbackEmitter",
]
