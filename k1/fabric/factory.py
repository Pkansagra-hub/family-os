"""
k1.fabric.factory -- FabricFactory (5.3.1).

Composition root for the Capability Fabric.  Constructs ALL subsystems
and wires ALL dependencies in a dependency-safe order.

Three factory methods:
  create_standalone()    -- All test adapters, no external deps.
  create_for_testing()   -- Test adapters + event capture mode.
  create_with_ports()    -- Custom adapter injection (production).

Construction order (20 steps, dependency-safe):
  1. Adapters (ports first, no dependencies)
  2. ContractValidator (no dependencies)
  3. CapabilityRegistry (validator + event_port)
  4. ModuleLoader (registry + contracts_dir + event_port)
  5. PolicyEngine subsystem (security + affective + cognitive + qos)
  6. ProviderRegistry (event_port)
  7. CircuitBreaker config (per provider type)
  8. ContextBuilder (state_reader + prompt_system)
  9. ProviderFactory (port_deps)
  10. Provider resolution chain (matcher + selector + resolver)
  11. Retrieval subsystem (embedding + filter + ranker + top_k + engine)
  12. OutputValidationPipeline (state_reader + event_port)
  13. HealthChecker + AvailabilityTracker
  14. Wire HealthChecker <-> CircuitBreaker bidirectional
  15. FabricDispatcher (optional, production mode)
  16. EventEmitter (event_port)
  17. CapabilityFabric facade
  18. FabricRetrieval
  19. CapabilityRegistryAPI
  20. Return Fabric container

References:
  - fabric-wiring-guide.md (complete wiring documentation)
  - fabric_discussion.md Section 15 (Factory Methods)
  - Epic 5.3.1 in fabric-implementation-plan.md

Exports:
  FabricFactory -- Static factory methods for Fabric construction
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_bridge import TestBridgeAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.circuit_breaker.breaker import CircuitBreaker
from k1.fabric.core.context_builder import ContextBuilder
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.module_loader import ModuleLoader
from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.events.event_emitter import EventEmitter, ProactiveGapDetector
from k1.fabric.fabric import (
    CapabilityFabric,
    CapabilityRegistryAPI,
    Fabric,
    FabricConfig,
    FabricRetrieval,
)
from k1.fabric.health.availability_tracker import AvailabilityTracker
from k1.fabric.health.health_checker import HealthChecker
from k1.fabric.output_validation.pipeline import OutputValidationPipeline
from k1.fabric.policy.affective_routing import AffectiveRouting
from k1.fabric.policy.cognitive_load_routing import CognitiveLoadRouting
from k1.fabric.policy.policy_engine import PolicyEngine
from k1.fabric.policy.qos_integration import QoSIntegration
from k1.fabric.policy.security_context import SecurityContext
from k1.fabric.provider_resolution.provider_factory import ProviderFactory
from k1.fabric.provider_resolution.provider_matcher import ProviderMatcher
from k1.fabric.provider_resolution.provider_registry import ProviderRegistry
from k1.fabric.provider_resolution.provider_selector import ProviderSelector
from k1.fabric.provider_resolution.resolver import Resolver
from k1.fabric.retrieval.embedding_index import EmbeddingIndex
from k1.fabric.retrieval.hard_filter import HardFilter
from k1.fabric.retrieval.retrieval_engine import RetrievalEngine
from k1.fabric.retrieval.soft_ranker import SoftRanker
from k1.fabric.retrieval.top_k_selector import TopKSelector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default contracts directory
# ---------------------------------------------------------------------------

_DEFAULT_CONTRACTS_DIR = Path("k1/contracts")


# ---------------------------------------------------------------------------
# Embedding port stub (for standalone mode without real embeddings)
# ---------------------------------------------------------------------------


class _StubEmbeddingPort:
    """
    Stub embedding port for standalone/testing mode.

    Returns zero vectors.  Production deployments inject a real
    IEmbeddingPort implementation via create_with_ports().
    """

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    def embed(self, text: str) -> Any:
        """Return a zero vector of the configured dimension."""
        import numpy as np

        return np.zeros(self._dim, dtype=np.float32)


# ---------------------------------------------------------------------------
# Provider handler constructors (registered with ProviderFactory)
# ---------------------------------------------------------------------------


def _register_provider_handlers(
    provider_factory: ProviderFactory,
) -> None:
    """
    Register all provider type handler constructors with the ProviderFactory.

    Each handler constructor takes (ProviderConfig, **port_deps) and
    returns a CapabilityProvider.  The port_deps are whatever keyword
    arguments were passed to ProviderFactory.__init__().

    Imports are deferred to avoid circular import issues.
    """
    from k1.fabric.providers.agent_provider import AgentProvider
    from k1.fabric.providers.bridge_provider import BridgeProvider
    from k1.fabric.providers.concierge_provider import ConciergeProvider
    from k1.fabric.providers.mcp_provider import MCPProvider
    from k1.fabric.providers.wasm_provider import WASMProvider
    from k1.fabric.providers.workflow_provider import WorkflowProvider
    from k1.fabric.types import ProviderType

    # MCP: takes config + transport
    def _create_mcp(config: Any, **deps: Any) -> Any:
        transport = deps.get("mcp_transport")
        if transport is None:
            raise ValueError("MCPProvider requires mcp_transport in port_deps")
        return MCPProvider(config, transport=transport)

    # WASM: takes config + runtime
    def _create_wasm(config: Any, **deps: Any) -> Any:
        runtime = deps.get("wasm_runtime")
        if runtime is None:
            raise ValueError("WASMProvider requires wasm_runtime in port_deps")
        return WASMProvider(config, runtime=runtime)

    # Bridge: takes config + bridge_port
    def _create_bridge(config: Any, **deps: Any) -> Any:
        bridge = deps.get("bridge_port")
        if bridge is None:
            raise ValueError("BridgeProvider requires bridge_port in port_deps")
        return BridgeProvider(config, bridge=bridge)

    # Agent: takes config + model_gateway + state_reader + delta_bus + context_builder
    def _create_agent(config: Any, **deps: Any) -> Any:
        return AgentProvider(
            config,
            model_gateway=deps.get("model_gateway_port"),
            state_reader=deps.get("state_reader"),
            delta_bus=deps.get("delta_bus"),
            context_builder=deps.get("context_builder"),
        )

    # Workflow: takes config + workflow_registry + capability_lookup + orchestrator
    def _create_workflow(config: Any, **deps: Any) -> Any:
        workflow_registry = deps.get("workflow_registry")
        capability_lookup = deps.get("capability_lookup")
        orchestrator = deps.get("orchestrator")
        if workflow_registry is None or capability_lookup is None or orchestrator is None:
            raise ValueError(
                "WorkflowProvider requires workflow_registry, "
                "capability_lookup, and orchestrator in port_deps"
            )
        return WorkflowProvider(
            config,
            workflow_registry=workflow_registry,
            capability_lookup=capability_lookup,
            orchestrator=orchestrator,
        )

    # Concierge: takes config + router
    def _create_concierge(config: Any, **deps: Any) -> Any:
        router = deps.get("concierge_router")
        if router is None:
            raise ValueError("ConciergeProvider requires concierge_router in port_deps")
        return ConciergeProvider(config, router=router)

    provider_factory.register_handler(ProviderType.MCP.value, _create_mcp)
    provider_factory.register_handler(ProviderType.WASM.value, _create_wasm)
    provider_factory.register_handler(ProviderType.BRIDGE.value, _create_bridge)
    provider_factory.register_handler(ProviderType.AGENT.value, _create_agent)
    provider_factory.register_handler(ProviderType.WORKFLOW.value, _create_workflow)
    provider_factory.register_handler(ProviderType.CONCIERGE.value, _create_concierge)


# ---------------------------------------------------------------------------
# 5.3.1 -- FabricFactory
# ---------------------------------------------------------------------------


class FabricFactory:
    """
    Composition root for the Capability Fabric.

    Static factory methods for constructing a fully-wired Fabric instance
    with appropriate adapters.

    Three factory methods:
      create_standalone()   -- All test adapters, no external deps.
                               For development, examples, unit tests.
      create_for_testing()  -- Test adapters + event capture mode.
                               For integration tests with event assertions.
      create_with_ports()   -- Custom adapter injection.
                               For production deployment.

    Thread Safety:
        Factory methods are stateless (static). The returned Fabric
        instance is thread-safe via internal component locking.
    """

    @staticmethod
    def create_standalone(
        *,
        contracts_dir: Optional[str] = None,
        config: Optional[FabricConfig] = None,
    ) -> Fabric:
        """
        Create Fabric with all test adapters, no external deps.

        Suitable for development, examples, and unit tests.
        All ports use in-memory test adapters.  No external services
        required (SessionState, Bridge, LLM, etc.).

        Args:
            contracts_dir: Directory to scan for capability contracts.
                Defaults to 'k1/contracts'.
            config: Optional FabricConfig override.

        Returns:
            Fully wired Fabric instance.
        """
        state_reader = TestSessionStateReaderAdapter()
        event_port = LocalEventAdapter(capture_mode=False)
        bridge = TestBridgeAdapter()
        model_gateway = TestModelGatewayAdapter()
        prompt_system = TestPromptSystemAdapter()
        delta_bus = TestDeltaBusAdapter()

        return _construct_fabric(
            state_reader=state_reader,
            event_port=event_port,
            bridge=bridge,
            model_gateway=model_gateway,
            prompt_system=prompt_system,
            delta_bus=delta_bus,
            production_mode=False,
            contracts_dir=contracts_dir,
            config=config,
        )

    @staticmethod
    def create_for_testing(
        *,
        capture_events: bool = True,
        contracts_dir: Optional[str] = None,
        config: Optional[FabricConfig] = None,
    ) -> Fabric:
        """
        Create Fabric with test adapters + event capture mode.

        Suitable for integration tests where you need to assert on
        emitted events.  Similar to standalone but with capture_mode
        enabled on the event adapter.

        Args:
            capture_events: Enable event capture mode (default True).
            contracts_dir: Directory to scan for capability contracts.
            config: Optional FabricConfig override.

        Returns:
            Fully wired Fabric instance with event capture.
        """
        state_reader = TestSessionStateReaderAdapter()
        event_port = LocalEventAdapter(capture_mode=capture_events)
        bridge = TestBridgeAdapter()
        model_gateway = TestModelGatewayAdapter()
        prompt_system = TestPromptSystemAdapter()
        delta_bus = TestDeltaBusAdapter()

        return _construct_fabric(
            state_reader=state_reader,
            event_port=event_port,
            bridge=bridge,
            model_gateway=model_gateway,
            prompt_system=prompt_system,
            delta_bus=delta_bus,
            production_mode=False,
            contracts_dir=contracts_dir,
            config=config,
        )

    @staticmethod
    def create_with_ports(
        state_reader: Any,
        event_port: Any,
        bridge: Any,
        model_gateway: Any,
        prompt_system: Any,
        delta_bus: Any,
        *,
        production_mode: bool = False,
        contracts_dir: Optional[str] = None,
        config: Optional[FabricConfig] = None,
        embedding_port: Optional[Any] = None,
    ) -> Fabric:
        """
        Create Fabric with custom adapter injection.

        For production deployment with real infrastructure.

        Args:
            state_reader: ISessionStateReader implementation.
            event_port: IEventPort implementation.
            bridge: IBridgePort implementation.
            model_gateway: IModelGatewayPort implementation.
            prompt_system: IPromptSystemPort implementation.
            delta_bus: IDeltaBusPort implementation.
            production_mode: If True, enables FabricDispatcher for
                bounded parallelism.
            contracts_dir: Directory to scan for capability contracts.
            config: Optional FabricConfig override.
            embedding_port: Optional IEmbeddingPort for real vector search.

        Returns:
            Fully wired Fabric instance.
        """
        return _construct_fabric(
            state_reader=state_reader,
            event_port=event_port,
            bridge=bridge,
            model_gateway=model_gateway,
            prompt_system=prompt_system,
            delta_bus=delta_bus,
            production_mode=production_mode,
            contracts_dir=contracts_dir,
            config=config,
            embedding_port=embedding_port,
        )


# ---------------------------------------------------------------------------
# Internal: Dependency-safe construction
# ---------------------------------------------------------------------------


def _construct_fabric(
    state_reader: Any,
    event_port: Any,
    bridge: Any,
    model_gateway: Any,
    prompt_system: Any,
    delta_bus: Any,
    production_mode: bool,
    contracts_dir: Optional[str] = None,
    config: Optional[FabricConfig] = None,
    embedding_port: Optional[Any] = None,
) -> Fabric:
    """
    Internal: Build a Fabric instance in dependency-safe order.

    20-step construction:
      1. Adapters are already provided as parameters.
      2. ContractValidator (no deps).
      3. CapabilityRegistry (validator + event_port).
      4. ModuleLoader (registry + contracts_dir + event_port).
      5. PolicyEngine subsystem (state_reader).
      6. ProviderRegistry (event_port).
      7. CircuitBreakers dict (shared reference).
      8. ContextBuilder (state_reader + prompt_system).
      9. ProviderFactory (port_deps).
      10. Resolution chain (matcher + selector + resolver).
      11. Retrieval subsystem.
      12. OutputValidationPipeline (state_reader + event_port).
      13. HealthChecker + AvailabilityTracker.
      14. Wire bidirectional callbacks.
      15. FabricDispatcher (production mode only).
      16. EventEmitter.
      17. CapabilityFabric.
      18. FabricRetrieval.
      19. CapabilityRegistryAPI.
      20. Assemble + return Fabric.
    """
    fabric_config = config or FabricConfig()
    effective_contracts_dir = Path(contracts_dir) if contracts_dir else _DEFAULT_CONTRACTS_DIR

    logger.info(
        "Constructing Fabric (production_mode=%s, contracts_dir=%s)",
        production_mode,
        effective_contracts_dir,
    )

    # ===== STEP 2: ContractValidator (no dependencies) =====
    validator = ContractValidator()

    # ===== STEP 3: CapabilityRegistry (validator + event_port) =====
    registry = CapabilityRegistry(
        validator=validator,
        event_port=event_port,
    )

    # ===== STEP 4: ModuleLoader (registry + contracts_dir + event_port) =====
    module_loader = ModuleLoader(
        registry=registry,
        contracts_dir=effective_contracts_dir,
        event_port=event_port,
        validator=validator,
    )

    # ===== STEP 5: PolicyEngine subsystem (state_reader) =====
    security_context = SecurityContext()
    affective_routing = AffectiveRouting(state_reader=state_reader)
    cognitive_routing = CognitiveLoadRouting(state_reader=state_reader)
    qos_integration = QoSIntegration()

    policy_engine = PolicyEngine(
        security=security_context,
        affective=affective_routing,
        cognitive=cognitive_routing,
        qos=qos_integration,
    )

    # ===== STEP 6: ProviderRegistry (event_port) =====
    provider_registry = ProviderRegistry(event_port=event_port)

    # ===== STEP 7: CircuitBreakers (shared mutable dict) =====
    circuit_breakers: Dict[str, CircuitBreaker] = {}

    # ===== STEP 8: ContextBuilder (state_reader + prompt_system) =====
    context_builder = ContextBuilder(
        state_reader=state_reader,
        prompt_system=prompt_system,
    )

    # ===== STEP 9: ProviderFactory (port_deps) =====
    provider_factory = ProviderFactory(
        bridge_port=bridge,
        model_gateway_port=model_gateway,
        state_reader=state_reader,
        delta_bus=delta_bus,
        context_builder=context_builder,
        registry=registry,
    )
    _register_provider_handlers(provider_factory)

    # ===== STEP 10: Resolution chain =====
    provider_matcher = ProviderMatcher(provider_registry=provider_registry)
    provider_selector = ProviderSelector()

    resolver = Resolver(
        capability_registry=registry,
        provider_matcher=provider_matcher,
        provider_selector=provider_selector,
        provider_factory=provider_factory,
        policy_engine=policy_engine,
    )

    # ===== STEP 11: Retrieval subsystem =====
    embedding_index = EmbeddingIndex()
    hard_filter = HardFilter()
    soft_ranker = SoftRanker()
    top_k_selector = TopKSelector()

    effective_embedding_port = embedding_port or _StubEmbeddingPort()

    retrieval_engine = RetrievalEngine(
        embedding_index=embedding_index,
        hard_filter=hard_filter,
        soft_ranker=soft_ranker,
        top_k_selector=top_k_selector,
        embedding_port=effective_embedding_port,
        registry_port=registry,
    )

    # ===== STEP 12: OutputValidationPipeline =====
    validation_pipeline = OutputValidationPipeline(
        state_reader=state_reader,
        event_port=event_port,
    )

    # ===== STEP 13: HealthChecker + AvailabilityTracker =====
    availability_tracker = AvailabilityTracker(
        event_port=event_port,
        registry_updater=registry.update_availability,
    )

    # Cast to Mapping for covariant type compatibility with ICircuitBreaker
    cb_mapping: Mapping[str, Any] = circuit_breakers
    health_checker = HealthChecker(
        provider_registry=provider_registry,
        availability_tracker=availability_tracker,
        circuit_breakers=cb_mapping,  # type: ignore[arg-type]
        event_port=event_port,
    )

    # ===== STEP 14: Wire bidirectional callbacks =====
    # HealthChecker already holds circuit_breakers dict reference.
    # As CBs are added to the dict, HealthChecker sees them.
    # CB -> HealthChecker callback is wired when CBs are created
    # (via on_state_change listener).

    # ===== STEP 15: FabricDispatcher (production mode only) =====
    _dispatcher = None
    if production_mode:
        from k1.fabric.concurrency.dispatcher import FabricDispatcher

        _dispatcher = FabricDispatcher(
            event_callback=lambda topic, payload: event_port.emit(topic, payload),
        )

    # ===== STEP 16: EventEmitter =====
    event_emitter = EventEmitter(event_port=event_port)

    # ===== STEP 17: CapabilityFabric (FabricFacade) =====
    fabric_facade = CapabilityFabric(
        resolver=resolver,
        context_builder=context_builder,
        validation_pipeline=validation_pipeline,
        event_emitter=event_emitter,
        registry=registry,
        provider_factory=provider_factory,
        circuit_breakers=circuit_breakers,
        config=fabric_config,
    )

    # ===== STEP 18: FabricRetrieval =====
    fabric_retrieval = FabricRetrieval(
        retrieval_engine=retrieval_engine,
    )

    # ===== STEP 19: CapabilityRegistryAPI =====
    registry_api = CapabilityRegistryAPI(registry=registry)

    # ===== STEP 20: Bootstrap + assemble Fabric =====
    # Scan contracts directory if it exists
    if effective_contracts_dir.exists():
        try:
            module_loader.start(watch=False)
            logger.info("Module loader scanned %s", effective_contracts_dir)
        except Exception:
            logger.warning(
                "Module loader scan failed for %s",
                effective_contracts_dir,
                exc_info=True,
            )
    else:
        logger.debug(
            "Contracts directory %s does not exist, skipping scan",
            effective_contracts_dir,
        )

    # 5.4.4: Wire ProactiveGapDetector event subscriptions
    gap_detector = ProactiveGapDetector(
        event_port=event_port,
        event_emitter=event_emitter,
        module_loader=module_loader,
    )
    gap_detector.wire_subscriptions()

    # Start HealthChecker periodic loop in production mode
    # Note: health_checker.start() is async, so callers should invoke
    # fabric.start_health_checker() after construction if in async context.
    # The Fabric container exposes a convenience method for this.

    fabric = Fabric(
        facade=fabric_facade,
        retrieval=fabric_retrieval,
        registry_api=registry_api,
        registry=registry,
        module_loader=module_loader,
        health_checker=health_checker,
        event_port=event_port,
        event_emitter=event_emitter,
    )

    logger.info("Fabric construction complete (production_mode=%s)", production_mode)
    return fabric
