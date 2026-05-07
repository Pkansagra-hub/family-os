"""k1.memory_writer.fabric_registration -- Fabric session lifecycle integration.

Registers Memory Writer with Fabric's agent lifecycle.
Called by Fabric during session initialization to create and wire
a MemoryWriterService for the session.

Lifecycle:
  create_for_session() -> started MemoryWriterService
  teardown_session()   -> stop + flush + cleanup
"""

from __future__ import annotations

from typing import Any

from k1.memory_writer.adapters.health_adapter import HealthAdapter
from k1.memory_writer.config import MWConfig
from k1.memory_writer.factory import MemoryWriterFactory
from k1.memory_writer.health.circuit_breaker import CircuitBreaker
from k1.memory_writer.service import MemoryWriterService


class MemoryWriterFabricRegistration:
    """Registers Memory Writer with Fabric's agent lifecycle.

    Called by Fabric during session initialization to create and
    wire a MemoryWriterService for the session.
    """

    @staticmethod
    async def create_for_session(
        session_read_adapter: Any,
        model_hub_adapter: Any,
        bridge_command_adapter: Any,
        event_subscription_adapter: Any,
        config: MWConfig | None = None,
    ) -> MemoryWriterService:
        """Create and start a MemoryWriterService for a session.

        Args:
            session_read_adapter: SessionReadAdapter instance.
            model_hub_adapter: ModelHubAdapter instance.
            bridge_command_adapter: BridgeCommandAdapter instance.
            event_subscription_adapter: EventSubscriptionAdapter instance.
            config: MWConfig (optional, defaults to MWConfig()).

        Returns:
            Started MemoryWriterService.

        Raises:
            InvariantViolation: If init-time invariant checks fail.
        """
        config = config or MWConfig()

        # Circuit breaker created here (Phase 5 E-MW-5.3)
        circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_probe_seconds=config.circuit_breaker_recovery_probe_seconds,
        )

        # Forward-reference for get_started lambda
        service: MemoryWriterService | None = None

        # Health adapter composes CB + service state
        health_adapter = HealthAdapter(
            circuit_breaker=circuit_breaker,
            get_pending_count=lambda: 0,  # Updated after pipeline creation
            get_started=lambda: service.is_started if service is not None else False,
        )

        service = MemoryWriterFactory.create(
            session_read_port=session_read_adapter,
            model_hub_port=model_hub_adapter,
            bridge_command_port=bridge_command_adapter,
            event_subscription_port=event_subscription_adapter,
            health_port=health_adapter,
            config=config,
        )

        await service.start()
        return service

    @staticmethod
    async def teardown_session(service: MemoryWriterService) -> None:
        """Stop and clean up a MemoryWriterService.

        Called by Fabric during session termination / DRAINING phase.
        Flushes pending batches and unsubscribes from events.
        """
        await service.stop()
