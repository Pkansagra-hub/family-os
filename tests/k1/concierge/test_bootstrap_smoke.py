"""
tests.k1.concierge.test_bootstrap_smoke
E-0.5.24 I-0.5.24.1 + I-0.5.24.2: Bootstrap smoke test + port wiring verification.

Validates:
    1. start_kernel(KernelConfig(test_mode=True)) produces a valid KernelRuntime.
    2. All required KernelRuntime fields are populated (bus, router, fsm, etc.).
    3. runtime.started == True after boot.
    4. stop_kernel() completes cleanly and sets started = False.
    5. FSM late-wired setters were invoked (ledger, history_sink, session_state,
       hitl_coordinator, weave_batcher, weave_policy, activity_tracker, orchestrator).
    6. Front/back dispatchers created with correct tool tier.
    7. Optional subsystem gating via KernelConfig flags.
"""

from __future__ import annotations

from dataclasses import fields as dc_fields

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.concierge.kernel.bootstrap import KernelRuntime, start_kernel, stop_kernel

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def test_config() -> KernelConfig:
    """Minimal config for bootstrap smoke tests — test_mode=True avoids LLM."""
    return KernelConfig(
        test_mode=True,
        ordered_bus=True,
        capture_bus=False,
        session_mode="standalone",
        auto_start_consumer=False,  # Don't launch background task in tests
        enable_experience=True,
        enable_delta=True,
        enable_hitl=True,
        enable_orchestrator=True,
        enable_ledger=True,
        enable_dead_letter_consumer=True,
    )


@pytest.fixture
async def runtime(test_config: KernelConfig) -> KernelRuntime:
    """Boot a full kernel, yield runtime, then stop."""
    rt = await start_kernel(test_config)
    yield rt
    await stop_kernel(rt)


# =========================================================================
# 1. Smoke: start_kernel returns a valid KernelRuntime
# =========================================================================


class TestBootstrapSmoke:
    """start_kernel(test_mode=True) produces a valid KernelRuntime."""

    async def test_returns_kernel_runtime(self, runtime: KernelRuntime) -> None:
        assert isinstance(runtime, KernelRuntime)

    async def test_started_is_true(self, runtime: KernelRuntime) -> None:
        assert runtime.started is True

    async def test_config_preserved(self, runtime: KernelRuntime) -> None:
        assert runtime.config.test_mode is True

    async def test_bus_not_none(self, runtime: KernelRuntime) -> None:
        assert runtime.bus is not None

    async def test_router_not_none(self, runtime: KernelRuntime) -> None:
        assert runtime.router is not None

    async def test_adapter_is_none(self, runtime: KernelRuntime) -> None:
        # P4B.1: adapter (SessionBusAdapter) no longer created; KernelService path
        assert runtime.adapter is None

    async def test_front_mailbox_not_none(self, runtime: KernelRuntime) -> None:
        assert runtime.front_mailbox is not None

    async def test_back_mailbox_not_none(self, runtime: KernelRuntime) -> None:
        assert runtime.back_mailbox is not None

    async def test_session_state_not_none(self, runtime: KernelRuntime) -> None:
        assert runtime.session_state is not None

    async def test_capability_registry_is_none(self, runtime: KernelRuntime) -> None:
        # P4B.1: capability_registry is now internal to Fabric
        assert runtime.capability_registry is None

    async def test_model_not_none(self, runtime: KernelRuntime) -> None:
        assert runtime.model is not None

    async def test_fsm_is_concierge_controller(self, runtime: KernelRuntime) -> None:
        from k1.concierge.fsm.controller import ConciergeController

        assert isinstance(runtime.fsm, ConciergeController)

    async def test_front_dispatcher_not_none(self, runtime: KernelRuntime) -> None:
        assert runtime.front_dispatcher is not None

    async def test_back_dispatcher_not_none(self, runtime: KernelRuntime) -> None:
        assert runtime.back_dispatcher is not None


# =========================================================================
# 2. Stop: stop_kernel sets started = False and doesn't raise
# =========================================================================


class TestStopKernel:
    """stop_kernel() tears down gracefully."""

    async def test_stop_sets_started_false(self, test_config: KernelConfig) -> None:
        rt = await start_kernel(test_config)
        assert rt.started is True
        await stop_kernel(rt)
        assert rt.started is False

    async def test_stop_idempotent(self, test_config: KernelConfig) -> None:
        """Calling stop_kernel twice doesn't raise."""
        rt = await start_kernel(test_config)
        await stop_kernel(rt)
        await stop_kernel(rt)  # second call should be safe
        assert rt.started is False

    async def test_stop_with_consumer_task(self) -> None:
        """stop_kernel cancels consumer_task if running."""
        cfg = KernelConfig(test_mode=True, auto_start_consumer=True)
        rt = await start_kernel(cfg)
        assert rt.consumer_task is not None
        assert not rt.consumer_task.done()
        await stop_kernel(rt)
        assert rt.started is False
        assert rt.consumer_task.done()


# =========================================================================
# 3. FSM Wiring: late-wired setter methods were called
# =========================================================================


class TestFSMWiring:
    """Verify FSM late-wired setters are invoked by start_kernel."""

    async def test_ledger_wired(self, runtime: KernelRuntime) -> None:
        assert runtime.ledger is not None
        assert runtime.ledger_store is not None
        # FSM should have ledger reference
        assert runtime.fsm._ledger is not None

    async def test_session_state_wired(self, runtime: KernelRuntime) -> None:
        # set_session_state binds _task_bridge and _control_ext
        assert runtime.fsm._task_bridge is not None

    async def test_hitl_coordinator_wired(self, runtime: KernelRuntime) -> None:
        # E4.M1.4: legacy `HILCoordinator` deleted.  `runtime.hitl_coordinator`
        # is no longer constructed by the concierge factory; the FSM's
        # `_hil_port` slot remains None until E4.M1.6 threads the unified
        # HIL service through the kernel.
        assert runtime.hitl_coordinator is None
        assert runtime.fsm._hil_port is None

    async def test_weave_batcher_wired(self, runtime: KernelRuntime) -> None:
        assert hasattr(runtime, "weave_batcher")
        # FSM should have _weave_batcher
        assert runtime.fsm._weave_batcher is not None

    async def test_weave_policy_wired(self, runtime: KernelRuntime) -> None:
        assert hasattr(runtime, "weave_policy")
        assert runtime.fsm._weave_policy is not None

    async def test_activity_tracker_wired(self, runtime: KernelRuntime) -> None:
        assert hasattr(runtime, "activity_tracker")
        assert runtime.fsm._activity_tracker is not None

    async def test_orchestrator_wired(self, runtime: KernelRuntime) -> None:
        assert runtime.orchestrator is not None
        assert runtime.fsm._orchestrator is not None


# =========================================================================
# 4. Optional Subsystems: gated by config flags
# =========================================================================


class TestSubsystemGating:
    """Config flags gate optional subsystem creation."""

    async def test_experience_layer_created(self, runtime: KernelRuntime) -> None:
        assert runtime.experience_layer is not None

    async def test_delta_aggregator_created(self, runtime: KernelRuntime) -> None:
        assert runtime.delta_aggregator is not None

    async def test_delta_applicator_wired(self, runtime: KernelRuntime) -> None:
        # F1 fix: delta_applicator now exposed via SessionInstance.
        assert runtime.delta_applicator is not None

    async def test_disable_experience(self) -> None:
        cfg = KernelConfig(test_mode=True, auto_start_consumer=False, enable_experience=False)
        rt = await start_kernel(cfg)
        try:
            assert rt.experience_layer is None
        finally:
            await stop_kernel(rt)

    async def test_disable_delta(self) -> None:
        cfg = KernelConfig(test_mode=True, auto_start_consumer=False, enable_delta=False)
        rt = await start_kernel(cfg)
        try:
            assert rt.delta_aggregator is None
            assert rt.delta_applicator is None
        finally:
            await stop_kernel(rt)

    async def test_disable_hitl(self) -> None:
        cfg = KernelConfig(test_mode=True, auto_start_consumer=False, enable_hitl=False)
        rt = await start_kernel(cfg)
        try:
            assert rt.hitl_coordinator is None
        finally:
            await stop_kernel(rt)

    async def test_orchestrator_always_created(self) -> None:
        # P4B.1: KernelService always creates Orchestrator (Tier 1 shared)
        cfg = KernelConfig(test_mode=True, auto_start_consumer=False, enable_orchestrator=False)
        rt = await start_kernel(cfg)
        try:
            assert rt.orchestrator is not None
        finally:
            await stop_kernel(rt)

    async def test_disable_ledger(self) -> None:
        cfg = KernelConfig(test_mode=True, auto_start_consumer=False, enable_ledger=False)
        rt = await start_kernel(cfg)
        try:
            assert rt.ledger is None
            assert rt.ledger_store is None
        finally:
            await stop_kernel(rt)


# =========================================================================
# 5. Front subscriptions: bus subscriptions were created
# =========================================================================


class TestBusSubscriptions:
    """Front event subscriptions are created, back are empty."""

    async def test_front_subscriptions_populated(self, runtime: KernelRuntime) -> None:
        assert isinstance(runtime.front_subscriptions, list)
        assert len(runtime.front_subscriptions) > 0

    async def test_back_subscriptions_empty(self, runtime: KernelRuntime) -> None:
        assert runtime.back_subscriptions == []


# =========================================================================
# 6. Consumer task: auto_start_consumer gating
# =========================================================================


class TestConsumerTask:
    """Consumer task creation gated by auto_start_consumer."""

    async def test_consumer_always_started(self, runtime: KernelRuntime) -> None:
        # P4B.1: KernelService always starts ConciergeRuntime consumer
        assert runtime.consumer_task is not None

    async def test_consumer_created_when_enabled(self) -> None:
        cfg = KernelConfig(test_mode=True, auto_start_consumer=True)
        rt = await start_kernel(cfg)
        try:
            assert rt.consumer_task is not None
            assert not rt.consumer_task.done()
        finally:
            await stop_kernel(rt)


# =========================================================================
# 7. Session ID: auto-generation and custom override
# =========================================================================


class TestSessionID:
    """Session ID generation and propagation."""

    async def test_session_id_auto_generated(self, runtime: KernelRuntime) -> None:
        # Ledger gets a session_id matching k-{8 hex} pattern
        if runtime.ledger is not None:
            sid = runtime.ledger._session_id
            assert sid.startswith("k-")
            assert len(sid) == 10  # "k-" + 8 hex chars

    async def test_session_id_custom_override(self) -> None:
        cfg = KernelConfig(
            test_mode=True,
            auto_start_consumer=False,
            session_id="custom-sess-42",
        )
        rt = await start_kernel(cfg)
        try:
            assert rt.ledger._session_id == "custom-sess-42"
        finally:
            await stop_kernel(rt)


# =========================================================================
# 8. Model: test_mode uses TestModelHubBridge
# =========================================================================


class TestModelCreation:
    """test_mode=True produces TestModelHubBridge."""

    async def test_test_mode_model_not_none(self, runtime: KernelRuntime) -> None:
        # P4B.1: model is now ModelHub (via KernelService), not TestModelHubBridge
        assert runtime.model is not None


# =========================================================================
# 9. KernelRuntime dataclass: field inventory
# =========================================================================


class TestKernelRuntimeFields:
    """KernelRuntime has the expected set of fields."""

    def test_required_field_names(self) -> None:
        field_names = {f.name for f in dc_fields(KernelRuntime)}
        expected_required = {
            "config",
            "bus",
            "router",
            "adapter",
            "front_mailbox",
            "back_mailbox",
            "session_state",
            "capability_registry",
            "model",
            "fsm",
            "front_dispatcher",
            "back_dispatcher",
        }
        assert expected_required.issubset(field_names)

    def test_optional_field_names(self) -> None:
        field_names = {f.name for f in dc_fields(KernelRuntime)}
        expected_optional = {
            "experience_layer",
            "delta_aggregator",
            "delta_applicator",
            "hitl_coordinator",
            "orchestrator",
            "front_subscriptions",
            "back_subscriptions",
            "consumer_task",
            "ledger",
            "ledger_store",
            "dead_letter_consumer",
            "started",
            # 2.0.9: converged fields (previously undeclared / from ConciergeRuntime)
            "weave_batcher",
            "weave_policy",
            "activity_tracker",
            "front_ctx",
            "back_ctx",
        }
        assert expected_optional.issubset(field_names)


# =========================================================================
# 10. KernelConfig: defaults and field inventory
# =========================================================================


class TestKernelConfigDefaults:
    """KernelConfig defaults match expected values."""

    def test_default_ordered_bus(self) -> None:
        assert KernelConfig().ordered_bus is True

    def test_default_test_mode(self) -> None:
        assert KernelConfig().test_mode is False

    def test_default_session_mode(self) -> None:
        assert KernelConfig().session_mode == "standalone"

    def test_default_enable_flags_all_true(self) -> None:
        cfg = KernelConfig()
        assert cfg.enable_experience is True
        assert cfg.enable_delta is True
        assert cfg.enable_hitl is True
        assert cfg.enable_orchestrator is True
        assert cfg.auto_start_consumer is True
        assert cfg.enable_ledger is True
        assert cfg.enable_dead_letter_consumer is True

    def test_default_session_id_none(self) -> None:
        assert KernelConfig().session_id is None

    def test_default_seed_memories_empty(self) -> None:
        assert KernelConfig().seed_memories == []
