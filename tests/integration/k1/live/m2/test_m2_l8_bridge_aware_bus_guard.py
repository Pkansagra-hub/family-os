"""M2-L8 live-kernel BridgeAwareLocalBus subscription-topology probe.

Covers kernel sweep row M2-L8 (SUBSCRIPTION / I2.7.5, I2.7.11 / R10):

    The per-session bus must be a ``BridgeAwareLocalBus`` wrapper that
    refuses ``bus.publish(<bridge_reserved_topic>, ...)`` and raises
    ``UnknownContractError`` instead of silently forwarding the envelope
    through K1 local-bus subscribers (bypassing the bridge registry).

Background — R10 mitigation (I2.7.5 / I2.7.11)
------------------------------------------------
``BridgeAwareLocalBus`` (``bridge/bus_guard.py``) is a proxy around
``LocalBus`` that intercepts ``publish()`` calls.  On construction it
loads every YAML manifest under ``bridge/contracts/manifests/`` and
builds a ``frozenset[str]`` of "bridge-bound" topics — those whose
``direction`` is in ``{k0_to_k1, k1_to_k0, device_to_k0, k0_to_device}``.
Any publish to a bridge-bound topic raises
``bridge.bus_guard.UnknownContractError``.

GAP status
----------
I2.7.11 was open — ``BridgeAwareLocalBus`` existed but was NOT wired into
the kernel session bus (line 2040 of ``service.py`` was a plain
``BusFactory.create_local_ordered()``).  Fixed in this sweep: the raw bus
is now wrapped before being stored in ``SessionInstance.bus``.

Test coverage
-------------
| # | Assertion | Tracing ref | Expected |
|---|-----------|-------------|---------|
| 1 | ``session.bus`` is ``BridgeAwareLocalBus`` (proxy wired) | I2.7.11 / R10 | GREEN |
| 2 | ``session.bus.bridge_topics`` is a non-empty frozenset | I2.7.5 | GREEN |
| 3 | Publishing a bridge-reserved topic raises ``UnknownContractError`` | I2.7.5 R10 | GREEN |
| 4 | Publishing a non-reserved topic succeeds (no exception) | I2.7.5 R10 | GREEN |
| 5 | Two independent sessions each have their own guard instance | M2 general | GREEN |
| 6 | Known cross-kernel topics present in ``bridge_topics`` | I2.7.5 | GREEN |
| 7 | ``UnknownContractError`` message contains "R10" | I2.7.5 UX | GREEN |
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bridge.bus_guard import BridgeAwareLocalBus, UnknownContractError
from k1.bus.envelope.envelope import Envelope
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService

pytestmark = pytest.mark.integration


# ── helpers ──────────────────────────────────────────────────────────────────


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _recipe_a(tmp_path: Path) -> KernelConfig:
    return KernelConfig(
        test_mode=True,
        model_mode="test",
        ordered_bus=True,
        session_mode="standalone",
        bridge_enabled=False,
        bridge_offline_ok=True,
        otel_enabled=False,
        enable_hitl=False,
        enable_hil_service=False,
        enable_self_model=False,
        enable_family_tools=False,
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        workflow_db_path=str(tmp_path / "workflows.db"),
        bridge_outbox_path=str(tmp_path / "bridge.db"),
    )


def _make_envelope(topic: str) -> Envelope:
    return Envelope(topic=topic, payload=b"{}")


# ── guard identity probe ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l8_session_bus_is_bridge_aware(tmp_path: Path) -> None:
    """session.bus is a BridgeAwareLocalBus — R10 guard is wired (I2.7.11 fixed).

    The per-session bus must be a BridgeAwareLocalBus proxy, NOT a plain
    LocalBus. This is the PORT-IDENTITY sub-check for M2-L8.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    await svc.startup()

    session_id = "m2l8-bus-identity"
    await svc.create_session(session_id)
    session = svc._sessions[session_id]

    # ── 1. Bus type is BridgeAwareLocalBus ────────────────────────────────────
    assert isinstance(session.bus, BridgeAwareLocalBus), (
        f"session.bus is {type(session.bus).__name__!r}, expected BridgeAwareLocalBus. "
        "R10 guard (I2.7.11) is not wired — fix: wrap raw bus in _create_session_tier2."
    )

    # ── 2. bridge_topics is a non-empty frozenset ─────────────────────────────
    bridge_topics = session.bus.bridge_topics
    assert isinstance(
        bridge_topics, frozenset
    ), f"bridge_topics is {type(bridge_topics).__name__!r}, expected frozenset"
    assert len(bridge_topics) > 0, (
        "bridge_topics is empty — no YAML manifests loaded from bridge/contracts/manifests/. "
        "Check that load_bridge_topics() can read the contracts directory."
    )

    await svc.shutdown()


# ── reserved-topic guard probe ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l8_publish_reserved_topic_raises(tmp_path: Path) -> None:
    """Publishing a bridge-reserved topic raises UnknownContractError (I2.7.5 R10).

    Any topic in BridgeAwareLocalBus.bridge_topics must be refused on the
    local bus. The error message must contain 'R10'.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    await svc.startup()

    session_id = "m2l8-reserved-topic"
    await svc.create_session(session_id)
    session = svc._sessions[session_id]

    bridge_topics = session.bus.bridge_topics
    # Pick the first reserved topic as the test subject
    reserved_topic = next(iter(sorted(bridge_topics)))

    # ── 3. Publish bridge-reserved topic → UnknownContractError ──────────────
    with pytest.raises(UnknownContractError) as exc_info:
        session.bus.publish(_make_envelope(reserved_topic))

    # ── 7. Error message contains "R10" ──────────────────────────────────────
    assert "R10" in str(
        exc_info.value
    ), f"UnknownContractError message missing 'R10': {exc_info.value!r}"

    await svc.shutdown()


# ── non-reserved topic probe ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l8_publish_non_reserved_topic_succeeds(tmp_path: Path) -> None:
    """Publishing a non-bridge topic succeeds — guard only blocks cross-kernel topics.

    A custom K1-internal topic must pass through without raising.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    await svc.startup()

    session_id = "m2l8-non-reserved"
    await svc.create_session(session_id)
    session = svc._sessions[session_id]

    # ── 4. Publish a non-reserved topic → no exception ────────────────────────
    # Use a clearly local topic that will never appear in bridge manifests
    local_topic = "k1.session.internal.test.v1"
    assert (
        local_topic not in session.bus.bridge_topics
    ), f"Test topic {local_topic!r} unexpectedly appeared in bridge_topics"
    # Should not raise — LocalBus will dispatch to any subscribers
    session.bus.publish(_make_envelope(local_topic))

    await svc.shutdown()


# ── known topics probe ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l8_known_cross_kernel_topics_in_bridge_topics(tmp_path: Path) -> None:
    """Well-known cross-kernel topics from bridge/contracts/manifests/ are guarded.

    These topics are known to be cross-kernel (k1_to_k0 direction) and
    must be present in bridge_topics to ensure the guard is loaded correctly.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    await svc.startup()

    session_id = "m2l8-known-topics"
    await svc.create_session(session_id)
    bridge_topics = svc._sessions[session_id].bus.bridge_topics

    # ── 6. Known cross-kernel topics must be guarded ──────────────────────────
    # These are the primary K1→K0 command/event topics from the manifests.
    # If any are missing it means a manifest was removed or direction changed.
    well_known_bridge_topics = [
        "memory.write.v1",  # k1_to_k0 memory command
        "recall.request.v1",  # k1_to_k0 query
    ]
    missing = [t for t in well_known_bridge_topics if t not in bridge_topics]
    assert not missing, (
        f"Well-known cross-kernel topics not found in bridge_topics: {missing}. "
        f"Loaded topics: {sorted(bridge_topics)}"
    )

    await svc.shutdown()


# ── two-session independence probe ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l8_two_sessions_have_independent_guard_instances(tmp_path: Path) -> None:
    """Two sessions each have their own BridgeAwareLocalBus proxy instance.

    The guard is not shared — each session's bus wraps its own inner LocalBus.
    Both must be BridgeAwareLocalBus and must hold identical bridge_topics sets.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    await svc.startup()

    await svc.create_session("m2l8-ind-a")
    await svc.create_session("m2l8-ind-b")

    bus_a = svc._sessions["m2l8-ind-a"].bus
    bus_b = svc._sessions["m2l8-ind-b"].bus

    # ── 5. Independent instances, same guard sets ─────────────────────────────
    assert bus_a is not bus_b, "Sessions share the same bus object — isolation broken"
    assert isinstance(bus_a, BridgeAwareLocalBus)
    assert isinstance(bus_b, BridgeAwareLocalBus)
    # Both load the same manifest set — topic guards must be equal
    assert (
        bus_a.bridge_topics == bus_b.bridge_topics
    ), "Sessions have divergent bridge_topics sets — manifest loading is non-deterministic"
    # Inner buses must be different objects (per-session isolation)
    assert (
        bus_a.inner is not bus_b.inner
    ), "Sessions share the inner LocalBus — per-session isolation broken"

    await svc.shutdown()
