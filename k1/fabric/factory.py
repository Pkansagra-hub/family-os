"""
k1.fabric.factory -- FabricFactory (5.3.1).

Composition root for the Capability Fabric.  Constructs ALL subsystems
and wires ALL dependencies in a dependency-safe order.

Three factory methods:
  create_standalone()    -- All test adapters, no external deps.
  create_for_testing()   -- Test adapters + event capture mode.
  create_with_ports()    -- Custom adapter injection (production).
  create_shared()        -- Shared Fabric, no session state (kernel-level).

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

import json
import logging
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_bridge import TestBridgeAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_mcp_transport import TestMCPTransport
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.adapters.test_wasm_runtime import TestWASMRuntime
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
from k1.fabric.ports import (
    IDeltaBusPort,
    IEventPort,
    IFabricK0Port,
    IModelGatewayPort,
    IPromptSystemPort,
    ISessionStateReader,
)
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
    from k1.fabric.providers.local import LocalStubProvider
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
    #
    # M19.E1 (audit H-3 fix): the previous handler passed those four deps
    # directly to AgentProvider as kwargs, but AgentProvider.__init__
    # only accepts ``agent_factory`` and ``capability_names`` and silently
    # discards everything else through ``**_kwargs``. The result was that
    # production AgentProvider instances ran in stub mode (no factory ⇒
    # health_check returns UNKNOWN, execute() fails) and ``agent.*``
    # capability dispatch silently broke.
    #
    # The fix wires a real ``AgentFactory`` here, with:
    #   * ``contract_loader`` closing over the CapabilityRegistry's
    #     ``lookup`` method so ``AgentContract`` records authored under
    #     ``k1/contracts/agents/`` are loaded on demand.
    #   * ``capability_names`` populated from every AgentContract in the
    #     registry that targets this ``provider_id`` (informational; used
    #     by AgentProvider.capabilities() and health_check()).
    #
    # When ``model_gateway_port`` is missing the factory still constructs
    # but its ``has_model_gateway`` flips to False; AgentProvider's
    # health_check then surfaces a DEGRADED status instead of silently
    # claiming healthy.
    def _create_agent(config: Any, **deps: Any) -> Any:
        from k1.fabric.providers.agent_provider import AgentFactory
        from k1.fabric.types import AgentContract

        registry = deps.get("registry")
        contract_loader: Any = None
        capability_names: list[str] = []
        if registry is not None:

            def contract_loader(name: str) -> Any:  # noqa: E306 -- nested closure
                ct = registry.lookup(name)
                return ct if isinstance(ct, AgentContract) else None

            try:
                capability_names = [
                    ct.name
                    for ct in registry.list_all()
                    if isinstance(ct, AgentContract)
                    and getattr(ct, "provider_id", "") == config.provider_id
                ]
            except Exception:  # pragma: no cover -- defensive
                capability_names = []

        agent_factory = AgentFactory(
            context_builder=deps.get("context_builder"),
            model_gateway=deps.get("model_gateway_port"),
            state_reader=deps.get("state_reader"),
            delta_bus=deps.get("delta_bus"),
            contract_loader=contract_loader,
        )
        grounding_port = deps.get("grounding_port")
        if grounding_port is None:
            context_builder = deps.get("context_builder")
            grounding_port = getattr(context_builder, "grounding_port", None)
        return AgentProvider(
            config,
            agent_factory=agent_factory,
            capability_names=capability_names,
            grounding_port=grounding_port,
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

    # LocalStub (M12.E3): in-process deterministic stub for storyline
    # capabilities. Takes only the config; no external port deps.
    def _create_local_stub(config: Any, **deps: Any) -> Any:  # noqa: ARG001
        return LocalStubProvider(config)

    provider_factory.register_handler(ProviderType.MCP.value, _create_mcp)
    provider_factory.register_handler(ProviderType.WASM.value, _create_wasm)
    provider_factory.register_handler(ProviderType.BRIDGE.value, _create_bridge)
    provider_factory.register_handler(ProviderType.AGENT.value, _create_agent)
    provider_factory.register_handler(ProviderType.WORKFLOW.value, _create_workflow)
    provider_factory.register_handler(ProviderType.CONCIERGE.value, _create_concierge)
    provider_factory.register_handler(ProviderType.LOCAL_STUB.value, _create_local_stub)


# ---------------------------------------------------------------------------
# Auto-populate ProviderRegistry from loaded capability contracts
# ---------------------------------------------------------------------------


def _auto_register_providers(
    capability_registry: Any,
    provider_registry: ProviderRegistry,
) -> None:
    """
    Scan all contracts in the CapabilityRegistry and auto-register
    their referenced providers into the ProviderRegistry.

    Each unique provider_id gets a ProviderConfig entry derived from
    the contract's provider_type, provider_id, and endpoint fields.

    This bridges the gap between:
      - ModuleLoader loading contracts into CapabilityRegistry (2.2.1)
      - ProviderMatcher looking up provider_id in ProviderRegistry (3.1.1)

    Without this step, resolution fails at Step 2 (provider matching)
    because ProviderRegistry is empty even though contracts are loaded.

    Called after ModuleLoader.start() in Step 20 of _construct_fabric().
    """
    from k1.fabric.types import ProviderConfig, ProviderType

    seen: set[str] = set()

    for contract in capability_registry.list_all():
        provider_id = getattr(contract, "provider_id", "")
        if not provider_id or provider_id in seen:
            continue
        seen.add(provider_id)

        # Skip if already registered (e.g., by explicit setup)
        if provider_registry.contains(provider_id):
            continue

        provider_type = getattr(contract, "provider_type", ProviderType.MCP.value)
        endpoint = getattr(contract, "provider_endpoint", None)

        # Derive transport from provider_id naming convention
        transport = None
        if provider_type == ProviderType.MCP.value:
            if "stdio" in provider_id:
                transport = "stdio"
            elif "sse" in provider_id:
                transport = "sse"
            elif "handler" in provider_id:
                transport = "stdio"  # Local handlers use stdio-like transport

        # Derive module_path for WASM providers
        module_path = None
        if provider_type == ProviderType.WASM.value:
            module_path = getattr(contract, "module_path", None) or f"modules/{provider_id}.wasm"

        config = ProviderConfig(
            provider_id=provider_id,
            provider_type=provider_type,
            endpoint=endpoint or f"local://{provider_id}",
            transport=transport,
            module_path=module_path,
            max_execution_ms=30000 if provider_type != ProviderType.WASM.value else 5000,
        )

        try:
            provider_registry.register_provider(provider_id, config)
            logger.debug("Auto-registered provider: %s (%s)", provider_id, provider_type)
        except Exception:
            logger.debug(
                "Skipped provider registration for %s (already exists or error)",
                provider_id,
            )


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
      create_shared()       -- No session state, production ports.
                               For kernel-level shared components.

    Thread Safety:
        Factory methods are stateless (static). The returned Fabric
        instance is thread-safe via internal component locking.
    """

    @staticmethod
    def create_standalone(
        *,
        contracts_dir: Optional[str] = None,
        config: Optional[FabricConfig] = None,
        hil_port: Optional[Any] = None,
        conscience_port: Optional[Any] = None,
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
            hil_port=hil_port,
            conscience_port=conscience_port,
        )

    @staticmethod
    def create_for_testing(
        *,
        capture_events: bool = True,
        contracts_dir: Optional[str] = None,
        config: Optional[FabricConfig] = None,
        mcp_transport: Optional[Any] = None,
        wasm_runtime: Optional[Any] = None,
        hil_port: Optional[Any] = None,
        conscience_port: Optional[Any] = None,
        grounding_port: Optional[Any] = None,
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
            mcp_transport: Optional custom MCP transport. If provided,
                used instead of TestMCPTransport.  Pass an
                AutoDiscoveryMCPTransport for real tool execution.
            wasm_runtime: Optional custom WASM runtime. If provided,
                used instead of TestWASMRuntime.  Pass an
                AutoDiscoveryWASMRuntime for real WASM execution.

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
            mcp_transport=mcp_transport,
            wasm_runtime=wasm_runtime,
            hil_port=hil_port,
            conscience_port=conscience_port,
            grounding_port=grounding_port,
        )

    @staticmethod
    def create_with_ports(
        state_reader: ISessionStateReader,
        event_port: IEventPort,
        bridge: IFabricK0Port,
        model_gateway: IModelGatewayPort,
        prompt_system: IPromptSystemPort,
        delta_bus: IDeltaBusPort,
        *,
        production_mode: bool = False,
        contracts_dir: Optional[str] = None,
        config: Optional[FabricConfig] = None,
        embedding_port: Optional[
            Any
        ] = None,  # No IEmbeddingPort Protocol defined yet (M-10/TD-3.1)
        capability_registry: Optional[CapabilityRegistry] = None,
        mcp_transport: Optional[Any] = None,
        wasm_runtime: Optional[Any] = None,
        hil_port: Optional[Any] = None,
        conscience_port: Optional[Any] = None,
        grounding_port: Optional[Any] = None,
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
            capability_registry: Optional pre-built CapabilityRegistry.
                If provided, this registry is used instead of creating
                a new one.  Enables sharing a single registry across
                multiple per-session Fabric instances (SIM-D-36).
                If None, a fresh registry is constructed (backward-compatible).

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
            capability_registry=capability_registry,
            mcp_transport=mcp_transport,
            wasm_runtime=wasm_runtime,
            hil_port=hil_port,
            conscience_port=conscience_port,
            grounding_port=grounding_port,
        )

    @staticmethod
    def create_shared(
        event_port: Any,
        bridge: Any,
        model_gateway: Any,
        prompt_system: Any,
        delta_bus: Any,
        *,
        state_reader: Optional[Any] = None,
        production_mode: bool = True,
        contracts_dir: Optional[str] = None,
        config: Optional[FabricConfig] = None,
        embedding_port: Optional[Any] = None,
        capability_registry: Optional[Any] = None,
        mcp_transport: Optional[Any] = None,
        wasm_runtime: Optional[Any] = None,
        hil_port: Optional[Any] = None,
        conscience_port: Optional[Any] = None,
        grounding_port: Optional[Any] = None,
    ) -> Fabric:
        """
        Create a shared Fabric instance.

        For kernel-level components (Orchestrator, Planner) that operate
        outside a user session.  Uses ``NullSessionStateReaderAdapter``
        internally when no ``state_reader`` is provided, so no
        ``session_id`` is required.

        When a ``state_reader`` *is* supplied (e.g. a
        ``SessionRoutingStateReader``), the shared Fabric can access
        per-session context for capabilities that carry a ``session_id``.

        WORKFLOW and CONCIERGE providers are still registered but will
        raise ``ValueError`` at instantiation time if invoked — this is
        expected because shared Fabric serves AGENT, BRIDGE, and MCP
        provider types only.

        Args:
            event_port: IEventPort implementation.
            bridge: IBridgePort implementation.
            model_gateway: IModelGatewayPort implementation.
            prompt_system: IPromptSystemPort implementation.
            delta_bus: IDeltaBusPort implementation.
            state_reader: Optional ISessionStateReader implementation.
                When provided, replaces the default null reader so the
                shared Fabric can read per-session state.
            production_mode: Enable FabricDispatcher for bounded
                parallelism (default True for shared Fabric).
            contracts_dir: Directory to scan for capability contracts.
            config: Optional FabricConfig override.
            embedding_port: Optional IEmbeddingPort for real vector search.
            capability_registry: Optional pre-built CapabilityRegistry
                for sharing across Fabric instances (SIM-D-36).

        Returns:
            Fully wired Fabric instance.
        """
        if state_reader is None:
            from k1.fabric.adapters.null_state_reader import (
                NullSessionStateReaderAdapter,
            )

            state_reader = NullSessionStateReaderAdapter()

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
            capability_registry=capability_registry,
            mcp_transport=mcp_transport,
            wasm_runtime=wasm_runtime,
            hil_port=hil_port,
            conscience_port=conscience_port,
            grounding_port=grounding_port,
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
    mcp_transport: Optional[Any] = None,
    wasm_runtime: Optional[Any] = None,
    capability_registry: Optional[Any] = None,
    hil_port: Optional[Any] = None,
    conscience_port: Optional[Any] = None,
    grounding_port: Optional[Any] = None,
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
    # If a pre-built registry was injected, use it (SIM-D-36: shared
    # registry across per-session Fabric instances).  Otherwise create new.
    if capability_registry is not None:
        registry = capability_registry
    else:
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
    # W4 note: SecurityContext and QoSIntegration are intentionally stateless
    # — Security reads from CapabilityRequest+CapabilityContract; QoS reads
    # from request.params (budget_remaining_pct, latency_remaining_pct).
    # Only AffectiveRouting and CognitiveLoadRouting consult SessionState
    # via state_reader. Do not "fix" by injecting state_reader into the
    # stateless adapters.
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
        grounding_port=grounding_port,
    )

    # ===== STEP 9: ProviderFactory (port_deps) =====
    # Build test transport/runtime adapters if not in production mode
    # If mcp_transport was injected (e.g. AutoDiscoveryMCPTransport), use it;
    # otherwise fall back to TestMCPTransport for unit tests, or
    # AutoDiscoveryMCPTransport for production.
    # If wasm_runtime was injected (e.g. AutoDiscoveryWASMRuntime), use it;
    # otherwise fall back to TestWASMRuntime for unit tests.
    effective_mcp_transport: Any = mcp_transport
    effective_wasm_runtime: Any = wasm_runtime
    if not production_mode:
        if effective_mcp_transport is None:
            effective_mcp_transport = TestMCPTransport(connected=True)
        if effective_wasm_runtime is None:
            effective_wasm_runtime = TestWASMRuntime(available=True)
    else:
        # F3 fix (audit F101-F103): in production_mode, fall back to
        # AutoDiscoveryMCPTransport when no explicit transport was
        # injected. Previously this left mcp_transport=None which
        # caused MCPProvider construction to raise at first invocation.
        if effective_mcp_transport is None:
            try:
                from k1.fabric.adapters.auto_mcp_transport import (
                    AutoDiscoveryMCPTransport,
                )

                effective_mcp_transport = AutoDiscoveryMCPTransport()
            except Exception as exc:  # pragma: no cover -- defensive
                logger.warning(
                    "F3 fallback: AutoDiscoveryMCPTransport unavailable (%s); "
                    "MCP capabilities will fail at invoke time.",
                    exc,
                )

    provider_factory = ProviderFactory(
        bridge_port=bridge,
        model_gateway_port=model_gateway,
        state_reader=state_reader,
        delta_bus=delta_bus,
        context_builder=context_builder,
        grounding_port=grounding_port,
        registry=registry,
        mcp_transport=effective_mcp_transport,
        wasm_runtime=effective_wasm_runtime,
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
        dispatcher=_dispatcher,
        config=fabric_config,
        hil_port=hil_port,
        conscience_port=conscience_port,
    )

    # ===== STEP 18: FabricRetrieval =====
    fabric_retrieval = FabricRetrieval(
        retrieval_engine=retrieval_engine,
    )

    # ===== STEP 19: CapabilityRegistryAPI =====
    registry_api = CapabilityRegistryAPI(registry=registry)

    # ===== STEP 19b: Wire meta-tools (F4) =====
    # Register BuildAgentHandler as an explicit handler on the MCP transport
    # so that resolution of ``tool.write.build_agent`` actually executes the
    # in-process Python handler instead of returning "Unknown tool".
    # Per fabric-implementation-plan.md Step 20.
    if effective_mcp_transport is not None and hasattr(effective_mcp_transport, "register_handler"):
        try:
            from k1.fabric.core.agent_builder import (
                BUILD_AGENT_CAPABILITY_NAME,
                BUILD_AGENT_PROVIDER_ID,
                AgentComposer,
                AgentSpecValidator,
                BuildAgentHandler,
            )
            from k1.fabric.providers.mcp_provider import MCPResponse as _MCPResponse
            from k1.fabric.types import CapabilityRequest as _CapabilityRequest
            from k1.fabric.types import SafetyBand as _SafetyBand

            spec_validator = AgentSpecValidator(registry=registry, prompt_system=prompt_system)
            agent_composer = AgentComposer(registry=registry, prompt_system=prompt_system)
            build_agent_handler = BuildAgentHandler(
                validator=spec_validator,
                composer=agent_composer,
                registry=registry,
                security=security_context,
                emitter=event_emitter,
            )

            async def _build_agent_mcp_adapter(mcp_request: Any) -> Any:
                """Adapt MCPRequest -> CapabilityRequest -> handler -> MCPResponse."""
                args = dict(getattr(mcp_request, "arguments", {}) or {})
                cap_request = _CapabilityRequest(
                    capability_name=BUILD_AGENT_CAPABILITY_NAME,
                    params=args,
                    caller=str(args.get("_caller", "fabric")),
                    session_id=str(args.get("_session_id", "")),
                    safety_band=str(args.get("_safety_band", _SafetyBand.AMBER.value)),
                    trace_id=getattr(mcp_request, "trace_id", "") or "",
                )
                result = build_agent_handler.execute(cap_request)
                payload: Dict[str, Any] = {
                    "agent_name": "",
                    "status": "failed",
                    "errors": [],
                }
                if result.success and result.data:
                    payload.update(result.data)
                else:
                    err = result.error
                    payload["status"] = "failed"
                    payload["errors"] = [getattr(err, "message", "") or "build_agent failed"]
                    payload.setdefault("agent_name", str(args.get("agent_name", "")))
                return _MCPResponse(
                    success=bool(result.success),
                    content=[{"type": "text", "text": json.dumps(payload)}],
                    error_message="" if result.success else getattr(result.error, "message", ""),
                    latency_ms=int(getattr(result, "duration_ms", 0) or 0),
                )

            effective_mcp_transport.register_handler(
                BUILD_AGENT_CAPABILITY_NAME, _build_agent_mcp_adapter
            )
            logger.info(
                "F4: Registered %s handler with MCP transport (provider=%s)",
                BUILD_AGENT_CAPABILITY_NAME,
                BUILD_AGENT_PROVIDER_ID,
            )
        except Exception as exc:  # pragma: no cover -- defensive
            logger.warning(
                "F4: Failed to wire BuildAgentHandler to MCP transport: %s",
                exc,
                exc_info=True,
            )

    # ===== STEP 20: Bootstrap + assemble Fabric =====
    # Scan contracts directory if it exists.
    # SIM-D-36 follow-up: when a pre-built capability_registry was
    # injected (per-session Fabric on shared registry), all contracts
    # are already loaded — re-scanning yields 24 noisy "duplicate
    # contract" warnings and loaded=0. Skip the scan in that case.
    if capability_registry is not None:
        logger.debug(
            "Skipping contract scan: capability_registry was injected "
            "(per-session Fabric reuses shared registry)."
        )
    elif effective_contracts_dir.exists():
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

    # ===== STEP 20b: Auto-populate ProviderRegistry from loaded contracts =====
    _auto_register_providers(registry, provider_registry)

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
        gap_detector=gap_detector,
        context_builder=context_builder,
    )

    logger.info("Fabric construction complete (production_mode=%s)", production_mode)
    return fabric
