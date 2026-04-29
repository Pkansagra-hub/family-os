"""
k1.memory_writer.pipeline.pipeline -- 5-stage linear pipeline for memory extraction.

Wires: Filter → Context → Extraction → Envelope → Batch.
One instance per session (session-bound). No shared state.

Each stage catches its own errors. Pipeline never crashes.
Returns PipelineResult with summary of what happened.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from k1.memory_writer.batch.batch_emitter import BatchEmitter
from k1.memory_writer.batch.delta_aggregator import DeltaAggregator
from k1.memory_writer.config import MWConfig
from k1.memory_writer.context.context_builder import ContextBuilder
from k1.memory_writer.context.session_reader import MWSessionReader
from k1.memory_writer.envelope.envelope_builder import EnvelopeBuilder
from k1.memory_writer.envelope.privacy_enforcer import PrivacyEnforcer
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.extraction.extraction_validator import ExtractionValidator
from k1.memory_writer.extraction.writer_agent import MemoryWriterAgent
from k1.memory_writer.filter.relevance_filter import RelevanceFilter
from k1.memory_writer.ports.event_subscription_port import IEventSubscriptionPort
from k1.memory_writer.types import FilterDecision

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    """Outcome of processing a single turn.

    Used by TurnDispatcher for logging and metrics.
    All fields have safe defaults — empty result is valid.
    """

    skipped: bool = False
    skip_reason: str = ""
    atoms_extracted: int = 0
    envelopes_submitted: int = 0
    llm_tokens_used: int = 0
    llm_latency_ms: float = 0.0
    trace_id: str = ""
    error: Optional[str] = None


class MemoryWriterPipeline:
    """5-stage linear pipeline for memory extraction.

    Wires: Filter → Context → Extraction → Envelope → Batch.
    One instance per session (session-bound). No shared state.

    Each stage catches its own errors. Pipeline never crashes.
    Returns PipelineResult with summary of what happened.
    """

    def __init__(
        self,
        # Stage 1
        relevance_filter: RelevanceFilter,
        # Stage 2
        session_reader: MWSessionReader,
        context_builder: ContextBuilder,
        # Stage 3
        writer_agent: MemoryWriterAgent,
        extraction_validator: ExtractionValidator,
        circuit_breaker: Any,
        # Stage 4
        envelope_builder: EnvelopeBuilder,
        privacy_enforcer: PrivacyEnforcer,
        # Stage 5
        delta_aggregator: DeltaAggregator,
        batch_emitter: BatchEmitter,
        # Observability
        event_port: IEventSubscriptionPort,
        config: MWConfig,
    ) -> None:
        self._filter = relevance_filter
        self._session_reader = session_reader
        self._context_builder = context_builder
        self._writer_agent = writer_agent
        self._validator = extraction_validator
        self._circuit_breaker = circuit_breaker
        self._envelope_builder = envelope_builder
        self._privacy_enforcer = privacy_enforcer
        self._aggregator = delta_aggregator
        self._emitter = batch_emitter
        self._event_port = event_port
        self._config = config

    async def process(self, payload: TurnCompletePayload) -> PipelineResult:
        """Process a single turn through the 5-stage pipeline.

        Args:
            payload: TurnCompletePayload from turn.complete.v1 event.

        Returns:
            PipelineResult with extraction summary. Never raises.
        """
        trace_id = payload.cognitive_trace_id or ""

        # ── Stage 1: Filter ──
        try:
            decision = self._filter.evaluate(
                user_message=payload.user_message,
                assistant_response=payload.assistant_response,
                entities=[],
                topics=[],
                turn_id=payload.turn_id,
                timestamp_ms=payload.timestamp_ms,
            )
        except Exception as exc:
            log.warning(
                "MW: filter error, allowing turn",
                extra={"trace_id": trace_id, "error": str(exc)},
            )
            decision = FilterDecision(passed=True, turn_id=payload.turn_id)

        if not decision.passed:
            skip_reason = decision.skip_reason.value if decision.skip_reason else ""
            await self._publish_safe(
                "k1.mw.filter.decision.v1",
                {
                    "trace_id": trace_id,
                    "action": "SKIP",
                    "rule_id": skip_reason,
                },
            )
            return PipelineResult(
                skipped=True,
                skip_reason=skip_reason,
                trace_id=trace_id,
            )

        await self._publish_safe(
            "k1.mw.filter.decision.v1",
            {
                "trace_id": trace_id,
                "action": "PASS",
            },
        )

        # ── Stage 2: Context Assembly ──
        try:
            snapshot = await self._session_reader.read_snapshot()
            context = self._context_builder.build(snapshot, payload)
        except Exception as exc:
            log.warning(
                "MW: context assembly failed",
                extra={"trace_id": trace_id, "error": str(exc)},
            )
            await self._publish_safe(
                "k1.mw.pipeline.error.v1",
                {
                    "trace_id": trace_id,
                    "stage": "context_assembly",
                    "error": str(exc),
                },
            )
            return PipelineResult(trace_id=trace_id, error="context_read_failed")

        # ── Stage 3: LLM Extraction ──
        if self._circuit_breaker.is_open:
            log.info(
                "MW: circuit breaker open, skipping extraction",
                extra={"trace_id": trace_id},
            )
            await self._publish_safe(
                "k1.mw.circuit.open.v1",
                {
                    "trace_id": trace_id,
                },
            )
            return PipelineResult(trace_id=trace_id, error="circuit_breaker_open")

        try:
            raw_extractions = await self._writer_agent.extract(context, trace_id)
        except Exception as exc:
            log.warning(
                "MW: extraction failed",
                extra={"trace_id": trace_id, "error": str(exc)},
            )
            self._circuit_breaker.record_failure()
            return PipelineResult(trace_id=trace_id, error="extraction_failed")

        if raw_extractions:
            self._circuit_breaker.record_success()

        atoms = self._validator.validate(raw_extractions, context)

        if not atoms:
            await self._publish_safe(
                "k1.mw.extraction.complete.v1",
                {
                    "trace_id": trace_id,
                    "atom_count": 0,
                },
            )
            return PipelineResult(atoms_extracted=0, trace_id=trace_id)

        await self._publish_safe(
            "k1.mw.extraction.complete.v1",
            {
                "trace_id": trace_id,
                "atom_count": len(atoms),
            },
        )

        # ── Stage 4: Envelope + Privacy ──
        envelopes = self._envelope_builder.build(atoms, context, trace_id)

        band = "GREEN"
        if context.control_context:
            band = context.control_context.get("safety_band", "GREEN")

        for env in envelopes:
            self._privacy_enforcer.enforce(env["body"], band)

        # ── Stage 5: Batch + Submit ──
        for env in envelopes:
            self._aggregator.add(env)

        batch = self._aggregator.flush()
        submitted = await self._emitter.emit(batch)

        await self._publish_safe(
            "k1.mw.batch.submitted.v1",
            {
                "trace_id": trace_id,
                "submitted_count": submitted,
                "batch_size": len(batch),
            },
        )

        return PipelineResult(
            atoms_extracted=len(atoms),
            envelopes_submitted=submitted,
            trace_id=trace_id,
        )

    async def flush_pending(self) -> int:
        """Flush any pending envelopes in the aggregator.

        Called during service shutdown to drain incomplete batches.
        """
        batch = self._aggregator.flush()
        if batch:
            return await self._emitter.emit(batch)
        return 0

    async def process_session(
        self, turns: list[TurnCompletePayload]
    ) -> PipelineResult:
        """Process a buffered batch of turns with ONE LLM call (Option B).

        Used by SessionBatchDispatcher. Skips per-turn relevance filtering
        because we extract from the full transcript at once.

        Args:
            turns: Buffered TurnCompletePayloads since last flush.

        Returns:
            PipelineResult with extraction summary. Never raises.
        """
        if not turns:
            return PipelineResult(skipped=True, skip_reason="empty_buffer")

        anchor = turns[-1]  # latest turn drives context (current snapshot)
        trace_id = anchor.cognitive_trace_id or ""

        # ── Stage 2: Context Assembly (enriched read with cold archive) ──
        # Session-batch path uses the enriched reader so the LLM sees the
        # full conversation arc, including turns demoted out of the live
        # 16KB history_active window into LOCAL COLD. Falls back to plain
        # snapshot if cold archive is not wired (test/standalone).
        try:
            snapshot = await self._session_reader.read_snapshot_enriched(
                anchor.session_id
            )
            context = self._context_builder.build(snapshot, anchor)
        except Exception as exc:
            log.warning(
                "MW: context assembly failed (session batch)",
                extra={"trace_id": trace_id, "error": str(exc)},
            )
            await self._publish_safe(
                "k1.mw.pipeline.error.v1",
                {
                    "trace_id": trace_id,
                    "stage": "context_assembly",
                    "error": str(exc),
                },
            )
            return PipelineResult(trace_id=trace_id, error="context_read_failed")

        # ── Stage 3: LLM Extraction (one call over full transcript) ──
        if self._circuit_breaker.is_open:
            log.info(
                "MW: circuit breaker open, skipping session batch",
                extra={"trace_id": trace_id},
            )
            await self._publish_safe(
                "k1.mw.circuit.open.v1", {"trace_id": trace_id}
            )
            return PipelineResult(trace_id=trace_id, error="circuit_breaker_open")

        try:
            raw_extractions = await self._writer_agent.extract_session(
                turns, context, trace_id
            )
        except Exception as exc:
            log.warning(
                "MW: session extraction failed",
                extra={"trace_id": trace_id, "error": str(exc)},
            )
            self._circuit_breaker.record_failure()
            return PipelineResult(trace_id=trace_id, error="extraction_failed")

        if raw_extractions:
            self._circuit_breaker.record_success()

        atoms = self._validator.validate(raw_extractions, context)

        if not atoms:
            await self._publish_safe(
                "k1.mw.extraction.complete.v1",
                {"trace_id": trace_id, "atom_count": 0, "turn_count": len(turns)},
            )
            return PipelineResult(atoms_extracted=0, trace_id=trace_id)

        await self._publish_safe(
            "k1.mw.extraction.complete.v1",
            {
                "trace_id": trace_id,
                "atom_count": len(atoms),
                "turn_count": len(turns),
            },
        )

        # ── Stage 4: Envelope + Privacy ──
        envelopes = self._envelope_builder.build(atoms, context, trace_id)

        band = "GREEN"
        if context.control_context:
            band = context.control_context.get("safety_band", "GREEN")

        for env in envelopes:
            self._privacy_enforcer.enforce(env["body"], band)

        # ── Stage 5: Batch + Submit ──
        for env in envelopes:
            self._aggregator.add(env)

        batch = self._aggregator.flush()
        submitted = await self._emitter.emit(batch)

        await self._publish_safe(
            "k1.mw.batch.submitted.v1",
            {
                "trace_id": trace_id,
                "submitted_count": submitted,
                "batch_size": len(batch),
                "turn_count": len(turns),
            },
        )

        return PipelineResult(
            atoms_extracted=len(atoms),
            envelopes_submitted=submitted,
            trace_id=trace_id,
        )

    async def _publish_safe(self, topic: str, payload: dict) -> None:
        """Publish observability event. Never raises (best-effort telemetry)."""
        try:
            await self._event_port.publish(topic, payload)
        except Exception:
            pass  # Telemetry failure is non-critical
