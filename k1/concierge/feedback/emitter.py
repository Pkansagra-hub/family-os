"""K1 FeedbackEmitter — orchestrates detectors and publishes
:class:`FeedbackEnvelopeV1` via ``runtime.obs.feedback_envelope_v1``.

Boundary contract (per FEEDBACK.md K1 Step 4):

* The emitter owns the *shaping* concern — turning a typed detector
  signal (``CorrectionSignal`` / ``ValidationSignal`` / ``ReformulationSignal``)
  into a wire ``FeedbackEnvelopeV1`` whose ``payload`` matches the K0
  per-pipeline schema (P02 / P08 / P03 respectively).
* The emitter does **not** own detection (detector classes do) and does
  **not** own transport (the runtime-bound obs client does).
* Publish failures must not break the conversation flow — we log and
  continue (best-effort feedback per BRIDGE-MS-3e.0).

Pipeline mapping (anchors FEEDBACK.md "K1 Stage 5: Bridge Emission"):

    CorrectionSignal  -> P02 (write/correction)
    ValidationSignal  -> P08 (embeddings retrieval relevance)
    ReformulationSignal -> P03 (consolidation/salience)
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from k1.concierge.feedback.context import ConversationContext
from k1.concierge.feedback.detectors import (
    CorrectionSignal,
    ReformulationSignal,
    ValidationSignal,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from bridge.runtime import BridgeRuntime

logger = logging.getLogger(__name__)


# Constant headers per FEEDBACK.md K1 Step 4.
_SOURCE = "K1"
_SOURCE_COMPONENT_DEFAULT = "concierge.feedback"


class FeedbackEmitter:
    """Publish typed detector signals as ``feedback.envelope.v1`` messages.

    Construction takes a :class:`bridge.runtime.BridgeRuntime` whose
    ``obs.feedback_envelope_v1`` slot has been populated by the runtime
    builder (MS-3e wiring). Direct construction outside the runtime is
    rejected by the ``manifest_implementation_bound`` CI gate that
    polices generated client classes; this emitter is *infrastructure*
    around the generated client and is exempt.
    """

    def __init__(
        self,
        runtime: "BridgeRuntime",
        *,
        tenant_id: str,
        space_id: str,
        source_component: str = _SOURCE_COMPONENT_DEFAULT,
    ) -> None:
        if not tenant_id:
            raise ValueError("tenant_id required for feedback emission")
        if not space_id:
            raise ValueError("space_id required for feedback emission")
        self._runtime = runtime
        self._tenant_id = tenant_id
        self._space_id = space_id
        self._source_component = source_component

    # ------------------------------------------------------------------
    # Public dispatch — one entry point per signal class
    # ------------------------------------------------------------------

    async def emit_correction(
        self,
        signal: CorrectionSignal,
        *,
        context: ConversationContext,
    ) -> bool:
        """Build and publish a P02 feedback envelope. Returns success."""
        payload = self._shape_p02_payload(signal)
        envelope = self._build_envelope(
            signal=signal,
            context=context,
            payload=payload,
            signal_subtype="user_explicit_correction",
        )
        return await self._publish(envelope)

    async def emit_validation(
        self,
        signal: ValidationSignal,
        *,
        context: ConversationContext,
    ) -> bool:
        """Build and publish a P08 feedback envelope. Returns success."""
        payload = self._shape_p08_payload(signal)
        envelope = self._build_envelope(
            signal=signal,
            context=context,
            payload=payload,
            signal_subtype=f"user_{signal.polarity}_validation",
        )
        return await self._publish(envelope)

    async def emit_reformulation(
        self,
        signal: ReformulationSignal,
        *,
        context: ConversationContext,
    ) -> bool:
        """Build and publish a P03 feedback envelope. Returns success."""
        payload = self._shape_p03_payload(signal)
        envelope = self._build_envelope(
            signal=signal,
            context=context,
            payload=payload,
            signal_subtype="user_query_reformulation",
        )
        return await self._publish(envelope)

    # ------------------------------------------------------------------
    # Per-pipeline payload shapers (mirror k0/feedback/payloads.py)
    # ------------------------------------------------------------------

    @staticmethod
    def _shape_p02_payload(signal: CorrectionSignal) -> dict[str, Any]:
        """Shape P02 (Write) feedback. Required: extraction_quality OR user_correction.

        We always populate ``user_correction`` because every correction
        signal *is* the user-correction case. The ``field`` is bounded
        ("memory" or "response") because we don't yet have a structured
        diff, only the substring the user supplied.
        """
        actual = signal.original_content or ""
        expected = signal.corrected_content or signal.raw_text
        return {
            "extraction_quality": "poor",
            "user_correction": {
                "field": signal.correction_target or "memory",
                "expected": expected[:500] if expected else None,
                "actual": actual[:500] if actual else None,
            },
        }

    @staticmethod
    def _shape_p08_payload(signal: ValidationSignal) -> dict[str, Any]:
        """Shape P08 (Embeddings) feedback.

        Positive validation -> retrieval was relevant. Negative -> not.
        ``embedding_id`` is omitted at K1 (FeedbackWorker correlates by
        wal_positions/event_ids on the K0 side).
        """
        if signal.polarity == "positive":
            return {"retrieval_hit": True, "user_relevance": "relevant"}
        return {"retrieval_hit": False, "user_relevance": "irrelevant"}

    @staticmethod
    def _shape_p03_payload(signal: ReformulationSignal) -> dict[str, Any]:
        """Shape P03 (Consolidation) feedback.

        A reformulation tells P03 the prior recall was *insufficient*:
        emit a salience reduction (negative delta) signal targeting the
        grounded events. Magnitude scales with detector confidence.
        """
        delta = -0.10 * float(signal.confidence)
        # Clamp into the schema-allowed range [-1.0, 1.0].
        delta = max(-1.0, min(1.0, delta))
        return {
            "feedback_type": "SALIENCE_ADJUSTMENT",
            "salience_delta": round(delta, 4),
            "was_retrieved": True,
            "was_helpful": False,
            "confidence": round(float(signal.confidence), 4),
        }

    # ------------------------------------------------------------------
    # Envelope assembly + publish
    # ------------------------------------------------------------------

    def _build_envelope(
        self,
        *,
        signal: Any,
        context: ConversationContext,
        payload: dict[str, Any],
        signal_subtype: str,
    ) -> dict[str, Any]:
        correlation: dict[str, Any] = {
            "session_id": context.session_id,
            "message_id": context.message_id,
        }
        if context.recall_id:
            correlation["recall_id"] = context.recall_id
        if context.response_id:
            correlation["response_id"] = context.response_id
        if context.event_ids:
            correlation["event_ids"] = list(context.event_ids)
        if context.wal_positions:
            correlation["wal_positions"] = list(context.wal_positions)
        # Target the first grounded event by default (correction signals
        # also expose ``target_event_id``; copy it through if present).
        target_event_id = getattr(signal, "target_event_id", None)
        if target_event_id is None and context.grounded_event_ids:
            target_event_id = context.grounded_event_ids[0]
        if target_event_id is not None:
            correlation["target_entity_type"] = "event"
            correlation["target_entity_id"] = target_event_id

        provenance: dict[str, Any] = {
            "source_message_id": context.message_id,
        }

        priority_value = float(getattr(signal, "confidence", 0.5))
        priority_value = max(0.0, min(1.0, priority_value))

        return {
            "feedback_id": str(uuid.uuid4()),
            "pipeline_id": signal.pipeline_id,
            "signal_class": signal.signal_class,
            "signal_subtype": signal_subtype,
            "tenant_id": self._tenant_id,
            "space_id": self._space_id,
            "source": _SOURCE,
            "source_component": self._source_component,
            "session_id": context.session_id,
            "trace_id": context.message_id,
            "correlation": correlation,
            "provenance": provenance,
            "priority": priority_value,
            "payload": payload,
        }

    async def _publish(self, envelope: dict[str, Any]) -> bool:
        """Send via runtime.obs.feedback_envelope_v1.publish.

        Best-effort: failures are logged but do not raise. The K0 side
        is queueable (online_required=false); transient transport errors
        will be retried by the calling site if it cares.
        """
        client = self._resolve_client()
        if client is None:
            logger.warning(
                "feedback emitter: runtime.obs.feedback_envelope_v1 not bound; dropping signal"
            )
            return False

        # Build the Pydantic model the generated client expects.
        from bridge._generated.k1.models.feedback_envelope_v1 import (
            FeedbackEnvelopeV1,
        )

        try:
            payload_model = FeedbackEnvelopeV1.model_validate(envelope)
        except Exception:  # noqa: BLE001 - validation is the point
            logger.exception("feedback emitter: envelope failed wire-side validation; dropping")
            return False

        try:
            await client.publish(payload_model)
            return True
        except Exception:  # noqa: BLE001 - best-effort
            logger.exception("feedback emitter: publish failed; signal dropped")
            return False

    def _resolve_client(self) -> Any | None:
        obs_ns = getattr(self._runtime, "obs", None)
        if obs_ns is None:
            return None
        return getattr(obs_ns, "feedback_envelope_v1", None)


__all__ = ["FeedbackEmitter"]
