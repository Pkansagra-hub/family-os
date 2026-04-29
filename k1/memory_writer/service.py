"""
k1.memory_writer.service -- Top-level lifecycle wrapper for Memory Writer.

Held by Fabric per session. Manages start/stop lifecycle.
Session-bound: one instance per session, reused across turns.

Lifecycle:
  create → start() → [turn.complete.v1 events → pipeline] → stop()

Fabric lifecycle mapping:
  PENDING → create()
  WARMING → start()
  ACTIVE  → processing turns
  IDLE    → between turns (dispatcher stays subscribed)
  DRAINING → stop() called
  TERMINATED → garbage collected
"""

from __future__ import annotations

import logging

from k1.memory_writer.config import MWConfig
from k1.memory_writer.health.circuit_breaker import CircuitBreaker
from k1.memory_writer.pipeline.pipeline import MemoryWriterPipeline
from k1.memory_writer.pipeline.session_batch_dispatcher import SessionBatchDispatcher
from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher
from k1.memory_writer.ports.health_port import IHealthPort
from k1.memory_writer.types import HealthStatus

log = logging.getLogger(__name__)


class MemoryWriterService:
    """Top-level lifecycle wrapper for Memory Writer.

    Held by Fabric per session. Manages start/stop lifecycle.
    Session-bound: one instance per session, reused across turns.
    """

    def __init__(
        self,
        pipeline: MemoryWriterPipeline,
        dispatcher: TurnDispatcher | SessionBatchDispatcher,
        circuit_breaker: CircuitBreaker,
        health_port: IHealthPort,
        config: MWConfig,
    ) -> None:
        self._pipeline = pipeline
        self._dispatcher = dispatcher
        self._circuit_breaker = circuit_breaker
        self._health_port = health_port
        self._config = config
        self._started: bool = False

    async def start(self) -> None:
        """Start the MW service. Subscribe to events.

        Called by Fabric during WARMING phase.
        Idempotent — safe to call multiple times.
        """
        if self._started:
            return
        await self._dispatcher.start()
        self._started = True
        log.info("MW: MemoryWriterService started")

    async def stop(self) -> None:
        """Stop the MW service. Flush pending + unsubscribe.

        Called by Fabric during DRAINING phase.
        Idempotent — safe to call multiple times.
        """
        if not self._started:
            return
        await self._dispatcher.stop()
        self._started = False
        log.info("MW: MemoryWriterService stopped")

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Expose circuit breaker for health checks."""
        return self._circuit_breaker

    async def health_check(self) -> HealthStatus:
        """Health check for Fabric agent lifecycle probes.

        Returns:
            HealthStatus with circuit state and pipeline readiness.
        """
        return HealthStatus(
            is_healthy=self._started and not self._circuit_breaker.is_open,
            llm_circuit_open=self._circuit_breaker.is_open,
            pending_batch_count=self._pipeline._aggregator.pending_count,
            last_extraction_ms=0.0,  # tracked via metrics, not here
            detail="running" if self._started else "stopped",
        )
