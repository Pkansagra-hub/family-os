"""
k1.memory_writer.factory -- Factory for creating MemoryWriterService instances.

Single entry point for MW subsystem construction.
Validates all required ports and runs init-time invariants.

Called by Fabric when spawning a session-bound MW agent.
"""

from __future__ import annotations

import logging
from pathlib import Path

from k1.memory_writer.batch.batch_emitter import BatchEmitter
from k1.memory_writer.batch.delta_aggregator import DeltaAggregator
from k1.memory_writer.config import MWConfig
from k1.memory_writer.context.context_builder import ContextBuilder
from k1.memory_writer.context.person_resolver import PersonResolver
from k1.memory_writer.context.session_reader import MWSessionReader
from k1.memory_writer.envelope.envelope_builder import EnvelopeBuilder
from k1.memory_writer.envelope.field_mapper import FieldMapper
from k1.memory_writer.envelope.privacy_enforcer import PrivacyEnforcer
from k1.memory_writer.extraction.extraction_validator import ExtractionValidator
from k1.memory_writer.extraction.raw_extraction import PromptLoader
from k1.memory_writer.extraction.writer_agent import MemoryWriterAgent
from k1.memory_writer.filter.relevance_filter import RelevanceFilter
from k1.memory_writer.health.circuit_breaker import CircuitBreaker
from k1.memory_writer.invariants import validate_init_invariants
from k1.memory_writer.pipeline.pipeline import MemoryWriterPipeline
from k1.memory_writer.pipeline.session_batch_dispatcher import SessionBatchDispatcher
from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher
from k1.memory_writer.place_resolver import PlaceResolver
from k1.memory_writer.ports.bridge_command_port import IBridgeCommandPort
from k1.memory_writer.ports.event_subscription_port import IEventSubscriptionPort
from k1.memory_writer.ports.health_port import IHealthPort
from k1.memory_writer.ports.model_hub_port import IModelHubPort
from k1.memory_writer.ports.session_read_port import ISessionReadPort
from k1.memory_writer.service import MemoryWriterService

log = logging.getLogger(__name__)


class MemoryWriterFactory:
    """Factory for creating MemoryWriterService instances.

    Single entry point for MW subsystem construction.
    Validates all required ports and runs init-time invariants.

    Called by Fabric when spawning a session-bound MW agent.
    """

    @staticmethod
    def create(
        session_read_port: ISessionReadPort,
        model_hub_port: IModelHubPort,
        bridge_command_port: IBridgeCommandPort,
        event_subscription_port: IEventSubscriptionPort,
        health_port: IHealthPort,
        config: MWConfig | None = None,
    ) -> MemoryWriterService:
        """Create a fully wired MemoryWriterService.

        Args:
            session_read_port: SS snapshot reader.
            model_hub_port: LLM extraction calls.
            bridge_command_port: K0 envelope submission.
            event_subscription_port: K1 Bus subscription.
            health_port: Readiness/liveness probes.
            config: MWConfig. Defaults to MWConfig() if None.

        Returns:
            MemoryWriterService ready to start().

        Raises:
            InvariantViolation: If init-time invariant checks fail.
            TypeError: If required ports are missing or wrong type.
        """
        config = config or MWConfig()

        # ── Validate required ports ──
        required_ports = {
            "session_read_port": (session_read_port, ISessionReadPort),
            "model_hub_port": (model_hub_port, IModelHubPort),
            "bridge_command_port": (bridge_command_port, IBridgeCommandPort),
            "event_subscription_port": (event_subscription_port, IEventSubscriptionPort),
            "health_port": (health_port, IHealthPort),
        }
        for name, (port, protocol) in required_ports.items():
            if port is None:
                raise TypeError(f"Required port {name} is None")
            if not isinstance(port, protocol):
                raise TypeError(f"{name} does not implement {protocol.__name__}")

        # ── Run init-time invariant checks ──
        dependencies = {
            "session_read_port": session_read_port,
            "model_hub_port": model_hub_port,
            "bridge_command_port": bridge_command_port,
            "event_subscription_port": event_subscription_port,
            "health_port": health_port,
        }
        filter_deps = {"session_read_port": session_read_port}
        validate_init_invariants(dependencies, filter_deps, bridge_command_port, config)

        # ── Construct pipeline components ──
        # Stage 1
        relevance_filter = RelevanceFilter(config)

        # Stage 2
        session_reader = MWSessionReader(session_read_port, config)
        place_resolver = PlaceResolver([])  # populated per-turn from SS
        context_builder = ContextBuilder(config)

        # Stage 3
        prompt_loader = PromptLoader(Path(__file__).parent / "extraction" / "prompts")
        writer_agent = MemoryWriterAgent(model_hub_port, config, prompt_loader)
        person_resolver = PersonResolver()
        extraction_validator = ExtractionValidator(person_resolver, config)
        circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_probe_seconds=config.circuit_breaker_recovery_probe_seconds,
        )

        # Stage 4
        field_mapper = FieldMapper(place_resolver, config)
        envelope_builder = EnvelopeBuilder(field_mapper)
        privacy_enforcer = PrivacyEnforcer()

        # Stage 5
        delta_aggregator = DeltaAggregator(config)
        batch_emitter = BatchEmitter(bridge_command_port)

        # ── Wire pipeline ──
        pipeline = MemoryWriterPipeline(
            relevance_filter=relevance_filter,
            session_reader=session_reader,
            context_builder=context_builder,
            writer_agent=writer_agent,
            extraction_validator=extraction_validator,
            circuit_breaker=circuit_breaker,
            envelope_builder=envelope_builder,
            privacy_enforcer=privacy_enforcer,
            delta_aggregator=delta_aggregator,
            batch_emitter=batch_emitter,
            event_port=event_subscription_port,
            config=config,
        )

        # ── Create dispatcher + service ──
        if config.extraction_mode == "per_turn":
            dispatcher = TurnDispatcher(pipeline, event_subscription_port)
        else:
            dispatcher = SessionBatchDispatcher(
                pipeline,
                event_subscription_port,
                flush_turn_threshold=config.flush_turn_threshold,
                flush_idle_seconds=config.flush_idle_seconds,
            )

        return MemoryWriterService(
            pipeline=pipeline,
            dispatcher=dispatcher,
            circuit_breaker=circuit_breaker,
            health_port=health_port,
            config=config,
        )
