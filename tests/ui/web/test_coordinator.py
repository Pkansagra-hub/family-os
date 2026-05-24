"""tests.ui.web.test_coordinator — UiCoordinator boot + slot wiring.

Validates that:
    1. UiCoordinator.initialize_system() runs all 4 phases successfully.
    2. Required runtime slots are populated from KernelRuntime.
    3. Output channel + web bus subscriptions are wired in phase 3.
    4. Health check passes for test-mode boot.
    5. shutdown_system() tears everything down cleanly.
"""

from __future__ import annotations

import pytest

from ui.web.coordinator import UiCoordinator, get_web_coordinator, reset_coordinator


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_coordinator()
    yield
    reset_coordinator()


@pytest.fixture
async def coordinator() -> UiCoordinator:
    coord = UiCoordinator(test_mode=True)
    ok = await coord.initialize_system()
    assert ok, "UiCoordinator.initialize_system() returned False"
    yield coord
    await coord.shutdown_system()


# -------------------------------------------------------------------------
# 1. Lifecycle
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_runs_all_four_phases(coordinator: UiCoordinator) -> None:
    assert coordinator.system_ready is True
    assert coordinator.phases_completed == ["phase1", "phase2", "phase3", "phase4"]
    for phase in ("phase1", "phase2", "phase3", "phase4"):
        assert phase in coordinator.startup_times
        assert coordinator.startup_times[phase] >= 0.0


@pytest.mark.asyncio
async def test_shutdown_clears_ready_flag() -> None:
    coord = UiCoordinator(test_mode=True)
    assert await coord.initialize_system() is True
    assert coord.system_ready is True
    await coord.shutdown_system()
    assert coord.system_ready is False


# -------------------------------------------------------------------------
# 2. Slot wiring
# -------------------------------------------------------------------------


# Universally-populated slots in test mode. weave_batcher / weave_policy /
# activity_tracker / dead_letter_consumer are gated by config flags and may
# be None even when their enable_* flag is True — they are tested separately.
_REQUIRED_RUNTIME_SLOTS = (
    "bus",
    "router",
    "model",
    "fsm",
    "session_state",
    "front_mailbox",
    "back_mailbox",
    "front_dispatcher",
    "back_dispatcher",
    "hil_port",
    "front_ctx",
    "back_ctx",
    "experience_layer",
    "delta_aggregator",
    "delta_applicator",
    "orchestrator",
    "ledger",
    "ledger_store",
)


@pytest.mark.asyncio
async def test_runtime_slots_populated(coordinator: UiCoordinator) -> None:
    for slot in _REQUIRED_RUNTIME_SLOTS:
        assert getattr(coordinator, slot) is not None, f"slot {slot!r} is None"


@pytest.mark.asyncio
async def test_family_profile_loaded(coordinator: UiCoordinator) -> None:
    assert coordinator.family_profile
    assert "family_name" in coordinator.family_profile
    assert isinstance(coordinator.family_profile.get("members"), list)


# -------------------------------------------------------------------------
# 3. Phase 3 — Web wiring
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_output_channel_wired(coordinator: UiCoordinator) -> None:
    assert coordinator.output_channel is not None
    # OutputChannel exposes the WebSocketRenderer we injected
    assert coordinator.output_channel._renderer is coordinator.renderer


@pytest.mark.asyncio
async def test_web_bus_subscriptions_created(coordinator: UiCoordinator) -> None:
    # 7 subscriptions: TOPIC_STATE_UPDATED, TOPIC_AFFECT_UPDATE,
    # TOPIC_TOOL_STARTED, TOPIC_TOOL_COMPLETED, TOPIC_TOOL_STATE_CHANGED,
    # TOPIC_HIL_REQUEST, TOPIC_TASK_FAILED
    assert len(coordinator._web_subscriptions) == 7


# -------------------------------------------------------------------------
# 4. Singleton helper
# -------------------------------------------------------------------------


def test_singleton_returns_same_instance() -> None:
    a = get_web_coordinator(test_mode=True)
    b = get_web_coordinator(test_mode=True)
    assert a is b


def test_reset_drops_singleton() -> None:
    a = get_web_coordinator(test_mode=True)
    reset_coordinator()
    b = get_web_coordinator(test_mode=True)
    assert a is not b


# -------------------------------------------------------------------------
# 5. Status report
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_report_shape(coordinator: UiCoordinator) -> None:
    report = coordinator.get_status_report()
    assert report["system_ready"] is True
    assert report["test_mode"] is True
    assert report["phases_completed"] == ["phase1", "phase2", "phase3", "phase4"]
    assert "components" in report
    assert "fsm_state" in report["components"]
    assert report["total_startup_s"] >= 0.0
