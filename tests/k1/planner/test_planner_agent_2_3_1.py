"""Tests for PlannerAgent skeleton & constructor (Issue 2.3.1).

Tests cover:
  - Constructor with valid dependencies (4 params)
  - Constructor None-rejection for each dependency
  - Internal state initialisation (plan_lock, cancel_set, running, subscriptions)
  - Properties (read-only access to internal state)
  - __slots__ presence and completeness
  - Public interface method signatures exist (start, stop, on_cancel, micro_replan)
  - Stub methods raise NotImplementedError (placeholder for later issues)
  - Layer 3 import validation
  - __all__ export verification
  - Package facade re-export (k1.planner.PlannerAgent)

References
----------
- planner.md Section 3.1   (Planner Core -- PlannerAgent)
- planner.md Section 23    (Lifecycle -- 6 Phases)
- planner.md Section 24    (Concurrency Model)
- planner.md Section 30.5.1 F02 (planner_agent.py spec)
- planner.md Section 30.6  (Dependency Layers)
- docs/plans/planner-implementation-plan.md Issue 2.3.1
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Dict, List, Tuple

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.planner.config import PlannerConfig
from k1.planner.pipeline_controller import PipelineController
from k1.planner.planner_agent import PlannerAgent
from k1.planner.ports.event_port import IEventPort
from k1.planner.ports.mailbox_port import IMailboxPort

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class FakeDeltaPort:
    """Minimal IDeltaEmitPort implementation that records emitted deltas."""

    def __init__(self) -> None:
        self.emitted: List[Any] = []

    def emit(self, delta: Any) -> None:
        self.emitted.append(delta)


class FakeEventPort:
    """Minimal IEventPort implementation that records emitted events."""

    def __init__(self) -> None:
        self.emitted: List[Tuple[str, Dict[str, Any]]] = []
        self.subscriptions: List[Tuple[str, Any]] = []

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        self.emitted.append((topic, payload))

    def subscribe(self, topic: str, handler: Any) -> SubscriptionHandle:
        self.subscriptions.append((topic, handler))
        return SubscriptionHandle(subscription_id=f"sub-{topic}", topic=topic)

    def unsubscribe(self, handle: Any) -> bool:
        return True


class FakeMailboxPort:
    """Minimal IMailboxPort implementation for constructor injection."""

    def __init__(self) -> None:
        self.enqueued: List[Any] = []
        self.cancelled: List[str] = []

    async def dequeue(self) -> Any:
        """Dequeue stub -- blocks forever (never called in 2.3.1 tests)."""
        import asyncio

        await asyncio.Future()  # type: ignore[arg-type]

    async def enqueue(self, request: Any) -> None:
        self.enqueued.append(request)

    async def send_cancel(self, request_id: str) -> None:
        self.cancelled.append(request_id)

    def drain(self) -> List[Any]:
        return []

    async def micro_replan(self, request: Any) -> Any:
        return None


class FakeService:
    """Minimal stub for stage services (SketchService, etc.)."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name


def _make_pipeline(
    *,
    delta_port: Any = None,
    event_port: Any = None,
) -> PipelineController:
    """Helper to construct a minimal PipelineController for injection."""
    return PipelineController(
        sketch=FakeService("sketch"),
        expand=FakeService("expand"),
        validate=FakeService("validate"),
        commit=FakeService("commit"),
        delta_port=delta_port if delta_port is not None else FakeDeltaPort(),
        event_port=event_port if event_port is not None else FakeEventPort(),
        config=PlannerConfig(),
    )


def _make_agent(
    *,
    mailbox: Any = None,
    pipeline: Any = None,
    event_port: Any = None,
    config: Any = None,
) -> PlannerAgent:
    """Helper to construct PlannerAgent with defaults for unspecified params."""
    return PlannerAgent(
        mailbox=mailbox if mailbox is not None else FakeMailboxPort(),
        pipeline=pipeline if pipeline is not None else _make_pipeline(),
        event_port=event_port if event_port is not None else FakeEventPort(),
        config=config if config is not None else PlannerConfig(),
    )


# ===========================================================================
# 1. __slots__ verification
# ===========================================================================


class TestSlots:
    """PlannerAgent uses __slots__ for memory efficiency and attribute safety."""

    def test_has_slots(self) -> None:
        assert hasattr(PlannerAgent, "__slots__")

    def test_all_slots_present(self) -> None:
        expected = {
            "_mailbox",
            "_pipeline",
            "_event_port",
            "_config",
            "_plan_lock",
            "_cancel_set",
            "_running",
            "_subscriptions",
            "_in_flight_request_id",
        }
        assert set(PlannerAgent.__slots__) == expected

    def test_no_instance_dict(self) -> None:
        agent = _make_agent()
        assert not hasattr(agent, "__dict__")

    def test_cannot_set_arbitrary_attribute(self) -> None:
        agent = _make_agent()
        with pytest.raises(AttributeError):
            agent.not_a_real_slot = "boom"  # type: ignore[attr-defined]


# ===========================================================================
# 2. Constructor -- valid dependencies
# ===========================================================================


class TestConstructorValid:
    """Constructor accepts 4 injected dependencies and initialises state."""

    def test_constructor_stores_mailbox(self) -> None:
        mb = FakeMailboxPort()
        agent = _make_agent(mailbox=mb)
        assert agent._mailbox is mb
        assert agent.mailbox is mb

    def test_constructor_stores_pipeline(self) -> None:
        pipe = _make_pipeline()
        agent = _make_agent(pipeline=pipe)
        assert agent._pipeline is pipe
        assert agent.pipeline is pipe

    def test_constructor_stores_event_port(self) -> None:
        ep = FakeEventPort()
        agent = _make_agent(event_port=ep)
        assert agent._event_port is ep
        assert agent.event_port is ep

    def test_constructor_stores_config(self) -> None:
        cfg = PlannerConfig()
        agent = _make_agent(config=cfg)
        assert agent._config is cfg
        assert agent.config is cfg

    def test_constructor_creates_plan_lock(self) -> None:
        agent = _make_agent()
        assert isinstance(agent._plan_lock, asyncio.Lock)
        assert isinstance(agent.plan_lock, asyncio.Lock)

    def test_constructor_plan_lock_is_unlocked(self) -> None:
        agent = _make_agent()
        assert not agent._plan_lock.locked()

    def test_constructor_cancel_set_empty(self) -> None:
        agent = _make_agent()
        # 4.2.5 / P06: _cancel_set is now Dict[request_id, monotonic_ts]
        # (was Set[str]). Public ``cancel_set`` property still exposes
        # a Set view for backward compatibility.
        assert agent._cancel_set == {}
        assert agent.cancel_set == set()

    def test_constructor_running_is_false(self) -> None:
        agent = _make_agent()
        assert agent._running is False
        assert agent.running is False

    def test_constructor_subscriptions_empty(self) -> None:
        agent = _make_agent()
        assert agent._subscriptions == []
        assert agent.subscriptions == []


# ===========================================================================
# 3. Constructor -- None rejection
# ===========================================================================


class TestConstructorNoneRejection:
    """Constructor rejects None for each dependency with ValueError."""

    def test_none_mailbox_raises(self) -> None:
        with pytest.raises(ValueError, match="mailbox must not be None"):
            PlannerAgent(
                mailbox=None,  # type: ignore[arg-type]
                pipeline=_make_pipeline(),
                event_port=FakeEventPort(),
                config=PlannerConfig(),
            )

    def test_none_pipeline_raises(self) -> None:
        with pytest.raises(ValueError, match="pipeline must not be None"):
            PlannerAgent(
                mailbox=FakeMailboxPort(),
                pipeline=None,  # type: ignore[arg-type]
                event_port=FakeEventPort(),
                config=PlannerConfig(),
            )

    def test_none_event_port_raises(self) -> None:
        with pytest.raises(ValueError, match="event_port must not be None"):
            PlannerAgent(
                mailbox=FakeMailboxPort(),
                pipeline=_make_pipeline(),
                event_port=None,  # type: ignore[arg-type]
                config=PlannerConfig(),
            )

    def test_none_config_raises(self) -> None:
        with pytest.raises(ValueError, match="config must not be None"):
            PlannerAgent(
                mailbox=FakeMailboxPort(),
                pipeline=_make_pipeline(),
                event_port=FakeEventPort(),
                config=None,  # type: ignore[arg-type]
            )


# ===========================================================================
# 4. Properties -- read-only access
# ===========================================================================


class TestProperties:
    """Properties provide read-only access to internal state."""

    def test_cancel_set_returns_copy(self) -> None:
        """cancel_set property returns a copy, not the internal set."""
        agent = _make_agent()
        copy1 = agent.cancel_set
        copy1.add("injected")
        assert "injected" not in agent.cancel_set
        assert "injected" not in agent._cancel_set

    def test_subscriptions_returns_copy(self) -> None:
        """subscriptions property returns a copy, not the internal list."""
        agent = _make_agent()
        copy1 = agent.subscriptions
        copy1.append(SubscriptionHandle(subscription_id="injected", topic="x"))
        assert len(agent.subscriptions) == 0
        assert len(agent._subscriptions) == 0

    def test_plan_lock_returns_same_instance(self) -> None:
        """plan_lock property returns the same Lock object (not a copy)."""
        agent = _make_agent()
        assert agent.plan_lock is agent._plan_lock


# ===========================================================================
# 5. Public interface -- method signatures
# ===========================================================================


class TestPublicInterface:
    """Public methods exist with correct signatures."""

    def test_start_is_coroutine(self) -> None:
        agent = _make_agent()
        assert inspect.iscoroutinefunction(agent.start)

    def test_stop_is_coroutine(self) -> None:
        agent = _make_agent()
        assert inspect.iscoroutinefunction(agent.stop)

    def test_on_cancel_is_coroutine(self) -> None:
        agent = _make_agent()
        assert inspect.iscoroutinefunction(agent.on_cancel)

    def test_micro_replan_is_coroutine(self) -> None:
        agent = _make_agent()
        assert inspect.iscoroutinefunction(agent.micro_replan)

    def test_start_signature(self) -> None:
        sig = inspect.signature(PlannerAgent.start)
        params = list(sig.parameters.keys())
        assert params == ["self"]

    def test_stop_signature(self) -> None:
        sig = inspect.signature(PlannerAgent.stop)
        params = list(sig.parameters.keys())
        assert params == ["self"]

    def test_on_cancel_signature(self) -> None:
        sig = inspect.signature(PlannerAgent.on_cancel)
        params = list(sig.parameters.keys())
        assert params == ["self", "request_id"]

    def test_micro_replan_signature(self) -> None:
        sig = inspect.signature(PlannerAgent.micro_replan)
        params = list(sig.parameters.keys())
        assert params == ["self", "request"]


# ===========================================================================
# 6. Stub methods raise NotImplementedError
# ===========================================================================


class TestStubBehavior:
    """Remaining stub methods raise NotImplementedError.

    start(), stop(), on_cancel(), micro_replan() were implemented in
    Issues 2.3.2-2.3.6 and are tested in test_planner_agent_2_3_2_3_4.py
    and test_planner_agent_2_3_5_6_7.py.
    """

    @pytest.mark.asyncio
    async def test_no_stubs_remain(self) -> None:
        """All public methods are now implemented (no NotImplementedError)."""
        # This test documents that all stubs have been replaced.
        # Individual behavior is tested in dedicated test files.
        pass


# ===========================================================================
# 7. Multiple instances do not share state
# ===========================================================================


class TestInstanceIsolation:
    """Multiple PlannerAgent instances have independent state."""

    def test_cancel_sets_are_independent(self) -> None:
        agent1 = _make_agent()
        agent2 = _make_agent()
        # 4.2.5 / P06: _cancel_set is Dict[str, float]; insert via item-set.
        agent1._cancel_set["req-001"] = 0.0
        assert "req-001" not in agent2._cancel_set

    def test_plan_locks_are_independent(self) -> None:
        agent1 = _make_agent()
        agent2 = _make_agent()
        assert agent1._plan_lock is not agent2._plan_lock

    def test_subscriptions_are_independent(self) -> None:
        agent1 = _make_agent()
        agent2 = _make_agent()
        agent1._subscriptions.append(SubscriptionHandle(subscription_id="sub-1", topic="test"))
        assert len(agent2._subscriptions) == 0


# ===========================================================================
# 8. Layer 3 import validation
# ===========================================================================


class TestLayerCompliance:
    """PlannerAgent is Layer 3 -- imports Layer 2, Layer 1, Layer 0 only."""

    def test_imports_pipeline_controller_layer2(self) -> None:
        """PlannerAgent can import PipelineController (Layer 2)."""
        from k1.planner.planner_agent import PipelineController as PC

        assert PC is PipelineController

    def test_imports_mailbox_port_layer1(self) -> None:
        """PlannerAgent can import IMailboxPort (Layer 1)."""
        from k1.planner.planner_agent import IMailboxPort as MP

        assert MP is IMailboxPort

    def test_imports_event_port_layer1(self) -> None:
        """PlannerAgent can import IEventPort (Layer 1)."""
        from k1.planner.planner_agent import IEventPort as EP

        assert EP is IEventPort

    def test_imports_config_layer0(self) -> None:
        """PlannerAgent can import PlannerConfig (Layer 0)."""
        from k1.planner.planner_agent import PlannerConfig as PC

        assert PC is PlannerConfig

    def test_does_not_import_factory(self) -> None:
        """PlannerAgent must NOT import from factory.py (higher layer)."""
        import k1.planner.planner_agent as mod

        source = inspect.getsource(mod)
        assert "from k1.planner.factory" not in source
        assert "import k1.planner.factory" not in source


# ===========================================================================
# 9. __all__ export
# ===========================================================================


class TestModuleExports:
    """Module exports are correct."""

    def test_all_contains_planner_agent(self) -> None:
        import k1.planner.planner_agent as mod

        assert "PlannerAgent" in mod.__all__

    def test_package_facade_exports_planner_agent(self) -> None:
        """k1.planner.__init__.py re-exports PlannerAgent."""
        from k1.planner import PlannerAgent as PA

        assert PA is PlannerAgent

    def test_package_all_contains_planner_agent(self) -> None:
        import k1.planner as pkg

        assert "PlannerAgent" in pkg.__all__


# ===========================================================================
# 10. Constructor dependency types
# ===========================================================================


class TestDependencyTypes:
    """Constructor accepts correct types for dependencies."""

    def test_accepts_structural_mailbox_port(self) -> None:
        """IMailboxPort is a structural Protocol -- FakeMailboxPort satisfies it."""
        mb = FakeMailboxPort()
        agent = _make_agent(mailbox=mb)
        assert isinstance(agent.mailbox, FakeMailboxPort)

    def test_accepts_structural_event_port(self) -> None:
        """IEventPort is a structural Protocol -- FakeEventPort satisfies it."""
        ep = FakeEventPort()
        agent = _make_agent(event_port=ep)
        assert isinstance(agent.event_port, FakeEventPort)

    def test_accepts_real_pipeline_controller(self) -> None:
        """Pipeline is a concrete PipelineController instance."""
        pipe = _make_pipeline()
        agent = _make_agent(pipeline=pipe)
        assert isinstance(agent.pipeline, PipelineController)

    def test_accepts_real_planner_config(self) -> None:
        """Config is a real PlannerConfig (frozen dataclass)."""
        cfg = PlannerConfig()
        agent = _make_agent(config=cfg)
        assert isinstance(agent.config, PlannerConfig)
