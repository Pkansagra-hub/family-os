"""PlannerFactory -- pure static factory for planner object graph [F08].

Layer 7: the ONLY file in k1/planner/ that imports across ALL layers.
No other planner file may import from factory.py.

Four creation modes (aligned with OrchestratorFactory, FabricFactory)
---------------------------------------------------------------------
1. ``create_standalone``   -- zero-dep test shortcut (all test adapters)
2. ``create_for_testing``  -- integration tests (test adapters + overrides)
3. ``create_with_ports``   -- cross-subsystem tests (explicit typed ports)
4. ``create_production``   -- kernel Phase 5 (explicit typed ports)

Construction invariants
-----------------------
- 10-step wiring order (Section 9 of planner_implemented_spec.md)
- CommitService receives NO ILLMPort (PLAN-03: structural, not runtime)
- All port instances validated via @runtime_checkable isinstance checks
- No duplicate port identities (same id() in two slots)
- Config bounds validated before wiring

Import graph (Layer 7)
----------------------
k1.planner.factory
  -> k1.planner.config               (L0 -- PlannerConfig)
  -> k1.planner.types                (L0 -- errors, HealthStatus)
  -> k1.planner.ports                (L1 -- 7 port Protocols)
  -> k1.planner.services             (L3 -- ToolCallRouter, HILCoordinator)
  -> k1.planner.stages               (L4 -- 4 stage services)
  -> k1.planner.pipeline_controller  (L5 -- PipelineController)
  -> k1.planner.planner_agent        (L6 -- PlannerAgent)
  -> tests.k1.planner.adapters       (DEFERRED -- inside function body only)

NEVER imported by any planner module at layers 0-6.

References
----------
- planner_implemented_spec.md Section 9   (10-step wiring)
- planner_implemented_spec.md Section 15  (factory requirements)
- planner.md Section 30.5  (factory API)
- planner.md Section 30.6  (dependency layers)
"""

from __future__ import annotations

import logging
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple, Type

# -- Layer 0: types and config -------------------------------------------
from k1.planner.config import PlannerConfig

# -- Layer 5: pipeline orchestrator ----------------------------------------
from k1.planner.pipeline_controller import PipelineController

# -- Layer 6: top-level agent ----------------------------------------------
from k1.planner.planner_agent import PlannerAgent

# -- Layer 1: port protocols ----------------------------------------------
from k1.planner.ports import (
    IBridgePort,
    IDeltaEmitPort,
    IEventPort,
    IFabricRetrievalPort,
    ILLMPort,
    IMailboxPort,
    IStateReadPort,
)

# -- Layer 3: leaf services ------------------------------------------------
from k1.planner.services.hil_coordinator import HILCoordinator
from k1.planner.services.tool_call_router import ToolCallRouter

# -- Layer 4: stage services -----------------------------------------------
from k1.planner.stages.commit_service import CommitService
from k1.planner.stages.expand_service import ExpandService
from k1.planner.stages.sketch_service import SketchService
from k1.planner.stages.validate_service import ValidateService
from k1.planner.types import (
    DuplicatePortError,
    InvalidConfigError,
    InvalidPortError,
    MissingPortError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Port registry -- maps slot names to their Protocol types
# ---------------------------------------------------------------------------

_PORT_REGISTRY: List[Tuple[str, Type[Any]]] = [
    ("llm_port", ILLMPort),
    ("fabric_port", IFabricRetrievalPort),
    ("state_port", IStateReadPort),
    ("bridge_port", IBridgePort),
    ("delta_port", IDeltaEmitPort),
    ("event_port", IEventPort),
    ("mailbox_port", IMailboxPort),
]

# ---------------------------------------------------------------------------
# Config validation bounds
# ---------------------------------------------------------------------------

_CONFIG_BOUNDS: List[Tuple[str, str, Any]] = [
    ("mailbox_max_depth", ">= 1", lambda v: v >= 1),
    ("pipeline_timeout_ms", "> 0", lambda v: v > 0),
    ("max_tool_calls_per_plan", ">= 1", lambda v: v >= 1),
    ("max_hil_rounds", ">= 0", lambda v: v >= 0),
    ("total_token_budget", "> 0", lambda v: v > 0),
    ("sketch_timeout_ms", "> 0", lambda v: v > 0),
    ("expand_timeout_ms", "> 0", lambda v: v > 0),
    ("validate_timeout_ms", "> 0", lambda v: v > 0),
    ("commit_timeout_ms", "> 0", lambda v: v > 0),
    ("shutdown_grace_period_ms", "> 0", lambda v: v > 0),
]


class PlannerFactory:
    """Pure static factory -- no instance state.

    Constructs the full planner object graph using the 10-step wiring
    sequence documented in planner_implemented_spec.md Section 9.

    Four creation modes aligned with sibling factories
    (OrchestratorFactory, FabricFactory):

    - ``create_standalone()``  -- zero deps, all test adapters
    - ``create_for_testing()`` -- test defaults + selective overrides
    - ``create_with_ports()``  -- explicit typed ports (cross-subsystem tests)
    - ``create_production()``  -- explicit typed ports (kernel Phase 5)

    All methods validate ports and config before wiring.

    This class MUST NOT be instantiated.  All methods are ``@staticmethod``.
    """

    __slots__ = ()

    def __init__(self) -> None:
        raise TypeError(
            "PlannerFactory is a pure static factory and must not be instantiated. "
            "Use PlannerFactory.create_standalone(), .create_for_testing(), "
            ".create_with_ports(), or .create_production() instead."
        )

    # -----------------------------------------------------------------------
    # Public: create_standalone -- zero-dep test shortcut
    # -----------------------------------------------------------------------

    @staticmethod
    async def create_standalone(
        config: Optional[PlannerConfig] = None,
    ) -> PlannerAgent:
        """Create a planner with all test adapters, zero external deps.

        Matches sibling convention (OrchestratorFactory.create_standalone,
        FabricFactory.create_standalone): no required arguments, all ports
        wired to in-memory test adapters.

        Used for unit testing in isolation.  Completes in < 10ms (no I/O).

        Test adapter imports are deferred to prevent production code from
        depending on test infrastructure.

        Parameters
        ----------
        config : PlannerConfig, optional
            Planner configuration. Defaults to ``PlannerConfig()``.

        Returns
        -------
        PlannerAgent
            Fully-wired agent with test adapters.  Caller must invoke
            ``asyncio.create_task(agent.start())`` to begin the dequeue
            loop.
        """
        # Deferred import -- test adapters live outside production tree
        from tests.k1.planner.adapters import (
            TestBridgeAdapter,
            TestDeltaAdapter,
            TestEventAdapter,
            TestFabricRetrievalAdapter,
            TestLLMAdapter,
            TestMailboxAdapter,
            TestStateReadAdapter,
        )

        effective_config = config if config is not None else PlannerConfig()

        ports: Dict[str, Any] = {
            "llm_port": TestLLMAdapter(),
            "fabric_port": TestFabricRetrievalAdapter(),
            "state_port": TestStateReadAdapter(),
            "bridge_port": TestBridgeAdapter(),
            "delta_port": TestDeltaAdapter(),
            "event_port": TestEventAdapter(),
            "mailbox_port": TestMailboxAdapter(),
        }

        logger.info("planner_factory.create_standalone.start")
        PlannerFactory._validate_config(effective_config)
        agent = await PlannerFactory._wire(ports, effective_config)
        logger.info("planner_factory.create_standalone.complete")
        return agent

    # -----------------------------------------------------------------------
    # Public: create_for_testing -- test adapters + overrides
    # -----------------------------------------------------------------------

    @staticmethod
    async def create_for_testing(
        config: Optional[PlannerConfig] = None,
        **overrides: Any,
    ) -> Tuple[PlannerAgent, Dict[str, Any]]:
        """Create a planner wired to test adapters for integration tests.

        All 7 ports default to their test adapter counterparts.  Pass
        keyword arguments matching port slot names to override individual
        ports (e.g. ``llm_port=custom_llm``).

        Test adapter imports are deferred to prevent production code from
        depending on test infrastructure.

        Parameters
        ----------
        config : PlannerConfig, optional
            Planner configuration. Defaults to ``PlannerConfig()``.
        **overrides
            Port slot overrides keyed by name (``llm_port``, ``fabric_port``,
            ``state_port``, ``bridge_port``, ``delta_port``, ``event_port``,
            ``mailbox_port``).

        Returns
        -------
        Tuple[PlannerAgent, Dict[str, Any]]
            ``(agent, adapters_dict)`` where ``adapters_dict`` maps port
            slot names to the adapter instances used (for test assertions).
            Caller must spawn ``agent.start()`` as a background task.

        Raises
        ------
        InvalidPortError
            An override does not satisfy its Protocol.
        InvalidConfigError
            A config field violates validation bounds.
        """
        # Deferred import -- test adapters live outside production tree
        from tests.k1.planner.adapters import (
            TestBridgeAdapter,
            TestDeltaAdapter,
            TestEventAdapter,
            TestFabricRetrievalAdapter,
            TestLLMAdapter,
            TestMailboxAdapter,
            TestStateReadAdapter,
        )

        effective_config = config if config is not None else PlannerConfig()

        # Build default test adapters, then overlay overrides
        defaults: Dict[str, Any] = {
            "llm_port": TestLLMAdapter(),
            "fabric_port": TestFabricRetrievalAdapter(),
            "state_port": TestStateReadAdapter(),
            "bridge_port": TestBridgeAdapter(),
            "delta_port": TestDeltaAdapter(),
            "event_port": TestEventAdapter(),
            "mailbox_port": TestMailboxAdapter(),
        }

        # Validate override keys
        valid_keys = set(defaults.keys())
        invalid_keys = set(overrides.keys()) - valid_keys
        if invalid_keys:
            raise InvalidPortError(
                f"Unknown port slot(s) in overrides: {sorted(invalid_keys)}. "
                f"Valid slots: {sorted(valid_keys)}",
                port_name=", ".join(sorted(invalid_keys)),
            )

        ports = {**defaults, **overrides}

        logger.info("planner_factory.create_for_testing.start")
        PlannerFactory._validate_config(effective_config)
        PlannerFactory._validate_ports(ports)
        agent = await PlannerFactory._wire(ports, effective_config)
        logger.info("planner_factory.create_for_testing.complete")
        return agent, ports

    # -----------------------------------------------------------------------
    # Public: create_with_ports -- explicit typed ports
    # -----------------------------------------------------------------------

    @staticmethod
    async def create_with_ports(
        *,
        llm_port: ILLMPort,
        fabric_port: IFabricRetrievalPort,
        state_port: IStateReadPort,
        bridge_port: IBridgePort,
        delta_port: IDeltaEmitPort,
        event_port: IEventPort,
        mailbox_port: IMailboxPort,
        config: Optional[PlannerConfig] = None,
    ) -> PlannerAgent:
        """Create a planner with explicitly provided typed ports.

        Every port must be supplied -- no defaults, no test fallbacks.
        Matches OrchestratorFactory.create_with_ports convention:
        typed keyword-only args for IDE autocompletion and type checking.

        Use for cross-subsystem integration tests mixing real and test
        adapters with full control.

        Parameters
        ----------
        llm_port : ILLMPort
            Model Hub gateway.
        fabric_port : IFabricRetrievalPort
            Fabric retrieval (capability discovery, prompt search).
        state_port : IStateReadPort
            Session state reader (read-only, PLAN-01).
        bridge_port : IBridgePort
            K0 bridge (recall + persist_plan).
        delta_port : IDeltaEmitPort
            Delta stream emitter (fire-and-forget).
        event_port : IEventPort
            Event bus (pub/sub).
        mailbox_port : IMailboxPort
            Inbound request mailbox.
        config : PlannerConfig, optional
            Planner configuration. Defaults to ``PlannerConfig()``.

        Returns
        -------
        PlannerAgent
            Fully-wired agent.  Caller must spawn ``start()`` as a
            background task.

        Raises
        ------
        MissingPortError
            A required port is ``None``.
        InvalidPortError
            A port does not satisfy its Protocol.
        DuplicatePortError
            Two port slots share the same ``id()``.
        InvalidConfigError
            A config field violates validation bounds.
        """
        effective_config = config if config is not None else PlannerConfig()
        ports = {
            "llm_port": llm_port,
            "fabric_port": fabric_port,
            "state_port": state_port,
            "bridge_port": bridge_port,
            "delta_port": delta_port,
            "event_port": event_port,
            "mailbox_port": mailbox_port,
        }

        logger.info("planner_factory.create_with_ports.start")
        PlannerFactory._validate_config(effective_config)
        PlannerFactory._validate_ports(ports)
        agent = await PlannerFactory._wire(ports, effective_config)
        logger.info("planner_factory.create_with_ports.complete")
        return agent

    # -----------------------------------------------------------------------
    # Public: create_production -- kernel Phase 5
    # -----------------------------------------------------------------------

    @staticmethod
    async def create_production(
        *,
        llm_port: ILLMPort,
        fabric_port: IFabricRetrievalPort,
        state_port: IStateReadPort,
        bridge_port: IBridgePort,
        delta_port: IDeltaEmitPort,
        event_port: IEventPort,
        mailbox_port: IMailboxPort,
        config: Optional[PlannerConfig] = None,
    ) -> PlannerAgent:
        """Create a fully-wired planner for production (kernel Phase 5).

        All 7 ports MUST be real production adapters that satisfy their
        respective ``@runtime_checkable`` Protocol.

        Matches OrchestratorFactory.create_production convention.
        This is the ONLY entry point used by kernel bootstrap.

        Note: ``agent.start()`` is NOT called here because it enters an
        infinite dequeue loop.  The kernel bootstrap must spawn it:
        ``asyncio.create_task(agent.start())``.  When PlannerAgent
        lifecycle is refactored (init/run split), this method will call
        init() automatically -- matching OrchestratorFactory.create_production.

        Parameters
        ----------
        llm_port : ILLMPort
            Model Hub gateway (production: LLMGatewayAdapter).
        fabric_port : IFabricRetrievalPort
            Fabric retrieval (production: FabricRetrievalAdapter).
        state_port : IStateReadPort
            Session state reader (production: SessionStateReadAdapter).
        bridge_port : IBridgePort
            K0 bridge (production: BridgeAdapter).
        delta_port : IDeltaEmitPort
            Delta stream emitter (production: DeltaBusAdapter).
        event_port : IEventPort
            Event bus (production: EventBusAdapter).
        mailbox_port : IMailboxPort
            Inbound request mailbox (production: MailboxAdapter).
        config : PlannerConfig, optional
            Planner configuration. Defaults to ``PlannerConfig()``.

        Returns
        -------
        PlannerAgent
            Fully-wired agent.  Caller must invoke
            ``asyncio.create_task(agent.start())`` to begin the
            dequeue loop and accept plan requests.

        Raises
        ------
        MissingPortError
            A required port is ``None``.
        InvalidPortError
            A port does not satisfy its Protocol.
        DuplicatePortError
            Two port slots share the same ``id()``.
        InvalidConfigError
            A config field violates validation bounds.
        """
        effective_config = config if config is not None else PlannerConfig()
        ports = {
            "llm_port": llm_port,
            "fabric_port": fabric_port,
            "state_port": state_port,
            "bridge_port": bridge_port,
            "delta_port": delta_port,
            "event_port": event_port,
            "mailbox_port": mailbox_port,
        }

        logger.info("planner_factory.create_production.start")
        PlannerFactory._validate_config(effective_config)
        PlannerFactory._validate_ports(ports)
        agent = await PlannerFactory._wire(ports, effective_config)
        logger.info("planner_factory.create_production.complete")
        return agent

    # -----------------------------------------------------------------------
    # Internal: 10-step wiring (Section 9)
    # -----------------------------------------------------------------------

    @staticmethod
    async def _wire(
        ports: Dict[str, Any],
        config: PlannerConfig,
    ) -> PlannerAgent:
        """Construct the full planner object graph in dependency order.

        10-step wiring sequence from planner_implemented_spec.md Section 9.
        Each step only references objects created in prior steps.

        Note: ``agent.start()`` is NOT called here because it enters
        an infinite dequeue loop (``_run_loop``).  The caller (kernel
        or test harness) is responsible for spawning ``start()`` as a
        background task via ``asyncio.create_task(agent.start())``.

        Parameters
        ----------
        ports : Dict[str, Any]
            Validated port instances keyed by slot name.
        config : PlannerConfig
            Validated planner configuration.

        Returns
        -------
        PlannerAgent
            Fully-wired agent.  Caller must invoke ``start()`` to
            begin accepting plan requests.

        Raises
        ------
        PlannerInitError
            Agent startup failed or post-wiring health check failed.
        """
        llm_port = ports["llm_port"]
        fabric_port = ports["fabric_port"]
        state_port = ports["state_port"]
        bridge_port = ports["bridge_port"]
        delta_port = ports["delta_port"]
        event_port = ports["event_port"]
        mailbox_port = ports["mailbox_port"]

        # Step 1: Leaf service -- routes tool calls to 3 backend ports
        tool_router = ToolCallRouter(
            fabric_retrieval=fabric_port,
            state_read=state_port,
            bridge_port=bridge_port,
            config=config,
        )

        # Step 2: Leaf service -- manages HIL question/approval flow
        hil_coord = HILCoordinator(
            llm_port=llm_port,
            event_port=event_port,
            config=config,
        )

        # Step 3: Stage -- agentic sketch with tool-use
        sketch = SketchService(
            llm_port=llm_port,
            tool_router=tool_router,
            hil_coord=hil_coord,
        )

        # Step 4: Stage -- agentic expand with tool-use (no HIL)
        expand = ExpandService(
            llm_port=llm_port,
            tool_router=tool_router,
        )

        # Step 5: Stage -- deterministic + LLM arbiter validation
        validate = ValidateService(
            llm_port=llm_port,
            fabric_retrieval=fabric_port,
            hil_coord=hil_coord,
        )

        # Step 6: Stage -- zero LLM, deterministic assembly (PLAN-03)
        commit = CommitService(
            bridge_port=bridge_port,
            delta_port=delta_port,
            event_port=event_port,
        )

        # Step 7: Orchestrator -- 4-stage pipeline
        pipeline = PipelineController(
            sketch=sketch,
            expand=expand,
            validate=validate,
            commit=commit,
            delta_port=delta_port,
            event_port=event_port,
            config=config,
        )

        # Step 8: Top-level agent
        agent = PlannerAgent(
            mailbox=mailbox_port,
            pipeline=pipeline,
            event_port=event_port,
            config=config,
        )

        # Note: start() is NOT called here.  It enters an infinite
        # dequeue loop (_run_loop) and would block forever.  The caller
        # must spawn start() as a background task:
        #     task = asyncio.create_task(agent.start())

        logger.info(
            "planner_factory.wiring_complete",
            extra={
                "agent_type": type(agent).__qualname__,
                "config_timeout_ms": config.pipeline_timeout_ms,
            },
        )

        return agent

    # -----------------------------------------------------------------------
    # Internal: port validation
    # -----------------------------------------------------------------------

    @staticmethod
    def _validate_ports(ports: Dict[str, Any]) -> None:
        """Validate all 7 ports for completeness, protocol, and uniqueness.

        Checks are ordered: completeness first (fast fail), then protocol
        compliance, then duplicate identity.

        Parameters
        ----------
        ports : Dict[str, Any]
            Port instances keyed by slot name.

        Raises
        ------
        MissingPortError
            A port value is ``None``.
        InvalidPortError
            A port does not satisfy its ``@runtime_checkable`` Protocol.
        DuplicatePortError
            Two port slots share the same ``id()``.
        """
        # -- Pass 1: completeness (None check) --
        for slot_name, _ in _PORT_REGISTRY:
            value = ports.get(slot_name)
            if value is None:
                raise MissingPortError(
                    f"Port '{slot_name}' is None -- all 7 ports are required.",
                    port_name=slot_name,
                )

        # -- Pass 2: protocol compliance (isinstance against @runtime_checkable) --
        for slot_name, protocol_type in _PORT_REGISTRY:
            value = ports[slot_name]
            if not isinstance(value, protocol_type):
                raise InvalidPortError(
                    f"Port '{slot_name}' does not satisfy {protocol_type.__name__}. "
                    f"Got {type(value).__qualname__} which is missing required methods.",
                    port_name=slot_name,
                    expected_protocol=f"{protocol_type.__module__}.{protocol_type.__qualname__}",
                    actual_type=type(value).__qualname__,
                )

        # -- Pass 3: uniqueness (no two slots share the same id()) --
        slot_names = [name for name, _ in _PORT_REGISTRY]
        for name_a, name_b in combinations(slot_names, 2):
            if id(ports[name_a]) == id(ports[name_b]):
                raise DuplicatePortError(
                    f"Port slots '{name_a}' and '{name_b}' share the same "
                    f"object identity (id={id(ports[name_a])}). Each port "
                    f"slot must be a distinct instance.",
                    port_a=name_a,
                    port_b=name_b,
                )

    # -----------------------------------------------------------------------
    # Internal: config validation
    # -----------------------------------------------------------------------

    @staticmethod
    def _validate_config(config: PlannerConfig) -> None:
        """Validate PlannerConfig field values against known bounds.

        Parameters
        ----------
        config : PlannerConfig
            Configuration to validate.

        Raises
        ------
        InvalidConfigError
            A field violates its constraint.
        """
        for field_name, constraint_desc, check_fn in _CONFIG_BOUNDS:
            value = getattr(config, field_name, None)
            if value is None:
                raise InvalidConfigError(
                    f"Config field '{field_name}' is missing.",
                    field_name=field_name,
                    value=value,
                    constraint=constraint_desc,
                )
            if not check_fn(value):
                raise InvalidConfigError(
                    f"Config field '{field_name}' = {value!r} violates "
                    f"constraint: {constraint_desc}.",
                    field_name=field_name,
                    value=value,
                    constraint=constraint_desc,
                )


__all__ = ["PlannerFactory"]
