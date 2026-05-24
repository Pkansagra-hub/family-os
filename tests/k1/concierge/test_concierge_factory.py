"""
I-0.5.21.5 -- ConciergeFactory integration tests.

Covers:
  (a) create_standalone() returns valid session with all test adapters
  (b) create_for_testing(overrides=...) merges correctly
  (c) create_with_ports() with all 8 explicit ports
  (d) start()/stop() lifecycle
  (e) PortBundle validation and optional-port defaults
  (f) ConciergeConfig flag gating
  (g) 16-step wiring verification
  (h) ToolContext actor fields
  (i) TypeError on instantiation
  (j) Backward-compat re-exports from bootstrap
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from k1.concierge.factory import (
    _ALL_PORT_KEYS,
    ConciergeConfig,
    ConciergeFactory,
    PortBundle,
)
from k1.concierge.session import ConciergeRuntime

# ---------------------------------------------------------------------------
# (a) create_standalone
# ---------------------------------------------------------------------------


class TestCreateStandalone:
    """create_standalone() returns a valid session with all test adapters."""

    def test_returns_concierge_session(self):
        session = ConciergeFactory.create_standalone()
        assert isinstance(session, ConciergeRuntime)

    def test_session_not_started(self):
        session = ConciergeFactory.create_standalone()
        assert session.started is False

    def test_fsm_is_concierge_controller(self):
        from k1.concierge.fsm.controller import ConciergeController

        session = ConciergeFactory.create_standalone()
        assert isinstance(session.fsm, ConciergeController)

    def test_bus_is_wired(self):
        session = ConciergeFactory.create_standalone()
        assert session.bus is not None

    def test_model_is_test_adapter(self):
        from k1.concierge.adapters.test_llm import TestModelHubBridge

        session = ConciergeFactory.create_standalone()
        assert isinstance(session.model, TestModelHubBridge)

    def test_session_state_is_test_adapter(self):
        from k1.concierge.adapters import InMemoryStateAdapter

        session = ConciergeFactory.create_standalone()
        assert isinstance(session.session_state, InMemoryStateAdapter)

    def test_subsystems_disabled_by_for_testing_config(self):
        """for_testing() config disables optional subsystems."""
        session = ConciergeFactory.create_standalone()
        assert session.experience_layer is None
        assert session.delta_aggregator is None
        assert session.hil_port is None
        assert session.orchestrator is None
        assert session.ledger is None
        assert session.dead_letter_consumer is None


# ---------------------------------------------------------------------------
# (b) create_for_testing with overrides
# ---------------------------------------------------------------------------


class TestCreateForTesting:
    """create_for_testing() merges overrides into test adapters."""

    def test_default_returns_session(self):
        session = ConciergeFactory.create_for_testing()
        assert isinstance(session, ConciergeRuntime)

    def test_override_state_port(self):
        from k1.concierge.adapters import InMemoryStateAdapter
        from k1.sessionstate.public_types import TaskArtifactsSection, TaskStateSection
        from k1.sessionstate.sections.control import ControlSection

        custom_state = InMemoryStateAdapter()
        custom_state.seed("task_state", TaskStateSection())
        custom_state.seed("task_artifacts", TaskArtifactsSection())
        custom_state.seed("control", ControlSection(session_id="custom"))
        custom_state.seed("test_marker", {"hello": "world"})

        session = ConciergeFactory.create_for_testing(
            overrides={"state": custom_state},
        )
        assert session.session_state is custom_state
        assert session.session_state.get_section("test_marker") == {"hello": "world"}

    def test_unknown_override_raises(self):
        with pytest.raises(ValueError, match="Unknown override key 'nonexistent'"):
            ConciergeFactory.create_for_testing(overrides={"nonexistent": object()})

    def test_config_override(self):
        """Custom config enables specific subsystems."""
        cfg = ConciergeConfig.for_testing(enable_ledger=True)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.ledger is not None


# ---------------------------------------------------------------------------
# (c) create_with_ports
# ---------------------------------------------------------------------------


class TestCreateWithPorts:
    """create_with_ports() wires all 8 explicit ports."""

    @pytest.fixture
    def adapters(self):
        return ConciergeFactory._build_test_adapters()

    @pytest.fixture
    def port_bundle(self, adapters):
        return PortBundle(
            delta=adapters["delta"],
            input_=adapters["input_"],
            output=adapters["output"],
            state=adapters["state"],
            llm=adapters["llm"],
            dispatch=adapters["dispatch"],
            memory=adapters["memory"],
        )

    def test_returns_session(self, adapters, port_bundle):
        session = ConciergeFactory.create_with_ports(
            bus=adapters["delta"],
            router=adapters["_router"],
            front_mailbox=adapters["_front_mailbox"],
            back_mailbox=adapters["_back_mailbox"],
            ports=port_bundle,
            config=ConciergeConfig.for_testing(),
        )
        assert isinstance(session, ConciergeRuntime)

    def test_ports_wired_to_session(self, adapters, port_bundle):
        session = ConciergeFactory.create_with_ports(
            bus=adapters["delta"],
            router=adapters["_router"],
            front_mailbox=adapters["_front_mailbox"],
            back_mailbox=adapters["_back_mailbox"],
            ports=port_bundle,
            config=ConciergeConfig.for_testing(),
        )
        assert session.bus is adapters["delta"]
        assert session.model is adapters["llm"]
        assert session.session_state is adapters["state"]

    def test_default_config_when_none(self, adapters, port_bundle):
        """Config defaults to all-enabled when not provided."""
        session = ConciergeFactory.create_with_ports(
            bus=adapters["delta"],
            router=adapters["_router"],
            front_mailbox=adapters["_front_mailbox"],
            back_mailbox=adapters["_back_mailbox"],
            ports=port_bundle,
        )
        # Default config has enable_experience=True
        assert session.experience_layer is not None


# ---------------------------------------------------------------------------
# (d) start/stop lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Session start()/stop() manages consumer task correctly."""

    async def test_start_creates_consumer_task(self):
        session = ConciergeFactory.create_standalone()
        assert session.started is False
        await session.start()
        assert session.started is True
        await session.stop()

    async def test_stop_cancels_consumer(self):
        session = ConciergeFactory.create_standalone()
        await session.start()
        assert session._consumer_task is not None
        assert not session._consumer_task.done()
        await session.stop()
        assert session.started is False

    async def test_double_start_is_idempotent(self):
        session = ConciergeFactory.create_standalone()
        await session.start()
        task1 = session._consumer_task
        await session.start()  # second start should be no-op
        assert session._consumer_task is task1
        await session.stop()

    async def test_stop_without_start_is_safe(self):
        session = ConciergeFactory.create_standalone()
        await session.stop()  # should not raise
        assert session.started is False

    async def test_start_stop_start_cycle(self):
        """Session can be started after being stopped."""
        session = ConciergeFactory.create_standalone()
        await session.start()
        await session.stop()
        assert session.started is False
        await session.start()
        assert session.started is True
        await session.stop()


# ---------------------------------------------------------------------------
# (e) PortBundle validation and optional defaults
# ---------------------------------------------------------------------------


class TestPortBundle:
    """PortBundle validation and optional port defaults."""

    def test_all_port_keys_frozenset(self):
        assert _ALL_PORT_KEYS == frozenset(
            {"input_", "output", "llm", "state", "dispatch", "delta", "memory", "temporal"}
        )

    def test_optional_ports_default_to_none(self):
        adapters = ConciergeFactory._build_test_adapters()
        bundle = PortBundle(
            delta=adapters["delta"],
            input_=adapters["input_"],
            output=adapters["output"],
            state=adapters["state"],
            llm=adapters["llm"],
        )
        assert bundle.dispatch is None
        assert bundle.memory is None

    def test_validate_required_passes_with_all(self):
        adapters = ConciergeFactory._build_test_adapters()
        bundle = PortBundle(
            delta=adapters["delta"],
            input_=adapters["input_"],
            output=adapters["output"],
            state=adapters["state"],
            llm=adapters["llm"],
        )
        bundle.validate_required()  # should not raise

    def test_validate_required_fails_when_missing(self):
        """PortBundle.validate_required() names missing ports in error."""
        adapters = ConciergeFactory._build_test_adapters()
        # Force None into a required field via object.__setattr__ on frozen dataclass
        bundle = PortBundle(
            delta=adapters["delta"],
            input_=adapters["input_"],
            output=adapters["output"],
            state=adapters["state"],
            llm=adapters["llm"],
        )
        object.__setattr__(bundle, "delta", None)
        with pytest.raises(ValueError, match="delta"):
            bundle.validate_required()

    def test_frozen_immutability(self):
        adapters = ConciergeFactory._build_test_adapters()
        bundle = PortBundle(
            delta=adapters["delta"],
            input_=adapters["input_"],
            output=adapters["output"],
            state=adapters["state"],
            llm=adapters["llm"],
        )
        with pytest.raises(AttributeError):
            bundle.delta = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# (f) ConciergeConfig flag gating
# ---------------------------------------------------------------------------


class TestConfigFlagGating:
    """Each config flag controls whether corresponding subsystem is wired."""

    def test_enable_ledger_true(self):
        cfg = ConciergeConfig.for_testing(enable_ledger=True)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.ledger is not None
        assert session._ledger_store is not None

    def test_enable_ledger_false(self):
        cfg = ConciergeConfig.for_testing(enable_ledger=False)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.ledger is None

    def test_enable_experience_true(self):
        cfg = ConciergeConfig.for_testing(enable_experience=True)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.experience_layer is not None

    def test_enable_experience_false(self):
        cfg = ConciergeConfig.for_testing(enable_experience=False)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.experience_layer is None

    def test_m6_opp_pipeline_wired_when_experience_enabled(self):
        """M6.E1.I1: factory must attach OppPipeline to the FSM with
        EpisodicCompressor + DynamicIdentityContext, and the same
        compressor instance must back ExperienceLayer."""
        cfg = ConciergeConfig.for_testing(enable_experience=True)
        session = ConciergeFactory.create_for_testing(config=cfg)
        opp = getattr(session.fsm, "_opp_pipeline", None)
        assert opp is not None, "FSM must have _opp_pipeline attached"
        status = opp.status()
        assert status["opp6_episodic_compression"] is True
        assert status["opp7_dynamic_identity"] is True
        # Single-instance-per-session invariant: same compressor on both.
        assert session.experience_layer is not None
        assert (
            session.experience_layer.episodic_compressor is opp._episodic_compressor
        ), "ExperienceLayer must share the OppPipeline's compressor"

    def test_m6_opp_pipeline_absent_when_experience_disabled(self):
        """When ``enable_experience=False`` the OPP wiring must also be off."""
        cfg = ConciergeConfig.for_testing(enable_experience=False)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert getattr(session.fsm, "_opp_pipeline", None) is None
        assert session.experience_layer is None

    def test_enable_delta_true(self):
        cfg = ConciergeConfig.for_testing(enable_delta=True)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.delta_aggregator is not None

    def test_enable_delta_false(self):
        cfg = ConciergeConfig.for_testing(enable_delta=False)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.delta_aggregator is None

    def test_enable_hitl_true(self):
        # E4.M1.4: legacy `HILCoordinator` deleted; the factory no longer
        # constructs a `runtime.hil_port` even when enable_hitl=True.
        # The `hil_port` wiring lands in E4.M1.6, after which this test will
        # assert against `runtime.hil_port` (or the renamed field).
        cfg = ConciergeConfig.for_testing(enable_hitl=True)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.hil_port is None

    def test_enable_hitl_false(self):
        cfg = ConciergeConfig.for_testing(enable_hitl=False)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.hil_port is None

    def test_dead_letter_requires_both_flags(self):
        """Dead letter needs both enable_dead_letter_consumer AND dead_letter_enabled."""
        cfg = ConciergeConfig.for_testing(
            enable_dead_letter_consumer=True, dead_letter_enabled=False
        )
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.dead_letter_consumer is None

    def test_for_testing_defaults_disable_all(self):
        """ConciergeConfig.for_testing() disables all optional subsystems."""
        cfg = ConciergeConfig.for_testing()
        assert cfg.enable_experience is False
        assert cfg.enable_delta is False
        assert cfg.enable_hitl is False
        assert cfg.enable_orchestrator is False
        assert cfg.enable_ledger is False
        assert cfg.enable_dead_letter_consumer is False
        assert cfg.auto_start_consumer is False


# ---------------------------------------------------------------------------
# (g) 16-step wiring verification
# ---------------------------------------------------------------------------


class TestWiringVerification:
    """Verify key subsystems are wired into the FSM."""

    def test_fsm_has_session_state(self):
        session = ConciergeFactory.create_standalone()
        assert session.fsm._ss is not None

    def test_dispatchers_wired(self):
        session = ConciergeFactory.create_standalone()
        assert session._front_dispatcher is not None
        assert session._back_dispatcher is not None

    def test_ledger_wired_when_enabled(self):
        cfg = ConciergeConfig.for_testing(enable_ledger=True)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.fsm._ledger is not None

    def test_hitl_wired_into_fsm_when_enabled(self):
        # E4.M1.6: with no `hil_port` passed through the factory, the FSM's
        # `_hil_port` attribute remains None even when `enable_hitl=True`.
        # Real wiring is exercised by `test_factory_attaches_hil_port`.
        cfg = ConciergeConfig.for_testing(enable_hitl=True)
        session = ConciergeFactory.create_for_testing(config=cfg)
        assert session.fsm._hil_port is None

    def test_factory_attaches_hil_port(self):
        # E4.M1.6: passing a stub IHILPort through the factory threads it
        # into the FSM via `set_hil_port` at Step 11.
        class _StubHILPort:
            async def gate_capability(self, req):  # pragma: no cover - stub
                raise NotImplementedError

            async def needs_human(self, req):  # pragma: no cover - stub
                raise NotImplementedError

            async def submit_response(self, resp):  # pragma: no cover - stub
                raise NotImplementedError

        stub = _StubHILPort()
        session = ConciergeFactory.create_for_testing(hil_port=stub)
        assert session.fsm._hil_port is stub

    def test_front_subscriptions_populated(self):
        session = ConciergeFactory.create_standalone()
        # Standalone has a router, so front subscriptions should be created
        assert isinstance(session._front_subscriptions, list)


# ---------------------------------------------------------------------------
# (h) ToolContext actor fields
# ---------------------------------------------------------------------------


class TestToolContextWiring:
    """Verify front/back ToolContext actor fields are correct."""

    def test_front_dispatcher_actor(self):
        session = ConciergeFactory.create_standalone()
        # The front dispatcher's context should have actor="front"
        ctx = getattr(session._front_dispatcher, "_ctx", None)
        if ctx is not None:
            assert ctx.actor == "front"

    def test_back_dispatcher_actor(self):
        session = ConciergeFactory.create_standalone()
        ctx = getattr(session._back_dispatcher, "_ctx", None)
        if ctx is not None:
            assert ctx.actor == "back"


# ---------------------------------------------------------------------------
# (i) TypeError on instantiation
# ---------------------------------------------------------------------------


class TestNoInstantiation:
    """ConciergeFactory cannot be instantiated."""

    def test_instantiation_raises_type_error(self):
        with pytest.raises(TypeError, match="@classmethod pattern"):
            ConciergeFactory()


# ---------------------------------------------------------------------------
# (j) ConciergeConfig
# ---------------------------------------------------------------------------


class TestConciergeConfig:
    """ConciergeConfig frozen dataclass behavior."""

    def test_frozen(self):
        cfg = ConciergeConfig()
        with pytest.raises(AttributeError):
            cfg.enable_experience = False  # type: ignore[misc]

    def test_from_kernel_config(self):
        from k1.concierge.config.kernel import KernelConfig

        kc = KernelConfig(enable_experience=False, session_id="s1")
        cc = ConciergeConfig.from_kernel_config(kc)
        assert cc.enable_experience is False
        assert cc.session_id == "s1"

    def test_from_kernel_config_defaults(self):
        """Missing attributes on kernel config fall back to defaults."""
        kc = SimpleNamespace()  # empty object — no attrs
        cc = ConciergeConfig.from_kernel_config(kc)
        assert cc.enable_experience is True

    def test_for_testing_overrides(self):
        cfg = ConciergeConfig.for_testing(enable_ledger=True)
        assert cfg.enable_ledger is True
        assert cfg.enable_experience is False  # still disabled by for_testing default


# ---------------------------------------------------------------------------
# (k) Backward-compat re-exports from bootstrap
# ---------------------------------------------------------------------------


class TestBackwardCompatExports:
    """bootstrap.py re-exports canonical definitions from config/factory.

    P4B.4 + P4B.5: The OrchestratorStub adapter trinity
    (`_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter`) and
    `_build_delta_applicator` re-exports were removed from
    ``k1.concierge.kernel.bootstrap`` once the stub itself was deleted. Only
    ``KernelConfig`` / ``KernelRuntime`` / ``start_kernel`` / ``stop_kernel``
    remain re-exported.
    """

    def test_kernel_config_re_export(self):
        """bootstrap.py KernelConfig is the same as config.kernel KernelConfig."""
        from k1.concierge.config.kernel import KernelConfig as FromConfig
        from k1.concierge.kernel.bootstrap import KernelConfig as FromBootstrap

        assert FromConfig is FromBootstrap
