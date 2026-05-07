"""MS-3b Epic 3b.2 \u2014 auto-derived DEGRADED matrix tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bridge.core.degraded import (
    DegradedBehavior,
    DegradedMatrix,
    _derive_behavior,
    _infer_port_kind,
)
from bridge.core.events import EventBus, HealthTransition, utc_now
from bridge.core.health import K0HealthState

pytestmark = pytest.mark.asyncio


def _manifest(**overrides):
    """Tiny fixture builder \u2014 returns the dict shape ``DegradedMatrix`` accepts."""
    base = {
        "topic": overrides.pop("topic", "x.test.v1"),
        "direction": overrides.pop("direction", "k1_to_k0"),
        "delivery": overrides.pop("delivery", {}),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Derivation rules
# ---------------------------------------------------------------------------


def test_matrix_derived_from_online_required_true_raises_offline_error():
    raw = _manifest(delivery={"online_required": True, "transport": "http"})
    assert _derive_behavior(raw) is DegradedBehavior.RAISE_OFFLINE_ERROR


def test_matrix_derived_from_online_required_false_with_max_queue_age_queues():
    raw = _manifest(
        delivery={
            "online_required": False,
            "max_queue_age": "PT24H",
            "transport": "http",
        }
    )
    assert _derive_behavior(raw) is DegradedBehavior.QUEUE_TO_OUTBOX


def test_matrix_derived_from_obs_path_with_ttl_drops_after_ttl():
    raw = _manifest(
        delivery={
            "online_required": False,
            "max_queue_age": "PT5M",
            "kind": "obs",
            "transport": "http",
        }
    )
    assert _derive_behavior(raw) is DegradedBehavior.DROP_WITH_METRIC_AFTER_TTL


def test_matrix_for_sse_subscriber_marks_stream_closed():
    raw = _manifest(direction="k0_to_k1", delivery={"transport": "sse"})
    assert _derive_behavior(raw) is DegradedBehavior.MARK_STREAM_CLOSED


def test_matrix_for_generic_subscriber_is_n_a():
    raw = _manifest(direction="k0_to_k1", delivery={"transport": "http"})
    assert _derive_behavior(raw) is DegradedBehavior.N_A_SUBSCRIBER_SIDE


def test_port_kind_inferred_for_known_shapes():
    assert _infer_port_kind(_manifest(direction="k0_to_k1", delivery={"transport": "sse"})) == "sse"
    assert (
        _infer_port_kind(_manifest(direction="k1_to_k0", delivery={"transport": "http"}))
        == "command"
    )
    assert (
        _infer_port_kind(
            _manifest(direction="k1_to_k0", delivery={"transport": "http", "kind": "query"})
        )
        == "query"
    )
    assert (
        _infer_port_kind(_manifest(direction="k1_to_k0", delivery={"transport": "ifl"}))
        == "gateway"
    )


# ---------------------------------------------------------------------------
# DegradedMatrix lookup + lifecycle
# ---------------------------------------------------------------------------


def test_behavior_for_uses_full_key_then_topic_fallback():
    matrix = DegradedMatrix(
        [
            _manifest(
                topic="memory.write.v1",
                delivery={"online_required": False, "max_queue_age": "PT24H"},
            )
        ]
    )
    assert matrix.behavior_for("command", "memory.write.v1") is DegradedBehavior.QUEUE_TO_OUTBOX
    # Caller passing a different port kind \u2014 falls back to topic-only.
    assert matrix.behavior_for("query", "memory.write.v1") is DegradedBehavior.QUEUE_TO_OUTBOX


def test_behavior_for_state_returns_none_when_online():
    matrix = DegradedMatrix([_manifest(topic="x.v1", delivery={"online_required": True})])
    assert matrix.behavior_for_state("command", "x.v1", K0HealthState.ONLINE) is None
    assert (
        matrix.behavior_for_state("command", "x.v1", K0HealthState.OFFLINE)
        is DegradedBehavior.RAISE_OFFLINE_ERROR
    )


def test_degraded_topics_updates_on_health_transition():
    bus = EventBus()
    matrix = DegradedMatrix(
        [
            _manifest(
                topic="memory.write.v1",
                delivery={"online_required": False, "max_queue_age": "PT24H"},
            ),
            _manifest(
                topic="committed.plan.v1",
                delivery={"online_required": True, "transport": "http"},
            ),
        ],
        event_bus=bus,
        initial_state=K0HealthState.OFFLINE,
    )
    assert matrix.degraded_topics() == {"memory.write.v1", "committed.plan.v1"}

    bus.publish(
        HealthTransition(
            from_state="OFFLINE",
            to_state="ONLINE",
            at_utc=utc_now(),
        )
    )
    matrix.consume_pending_events()
    assert matrix.degraded_topics() == set()


def test_healthz_payload_renders_matrix():
    matrix = DegradedMatrix(
        [
            _manifest(
                topic="memory.write.v1",
                delivery={"online_required": False, "max_queue_age": "PT24H"},
            )
        ]
    )
    payload = matrix.healthz_payload()
    assert payload["health_state"] == "OFFLINE"
    assert payload["behaviors"]["memory.write.v1"] == "queue_to_outbox"
    assert "memory.write.v1" in payload["degraded_topics"]


# ---------------------------------------------------------------------------
# Real-manifest table check (D-resolved item 3, restricted to manifests
# that ship today; future contracts will be added as their manifests land).
# ---------------------------------------------------------------------------


def test_matrix_table_matches_real_manifest_memory_write_v1():
    from tooling.contracts.manifest_loader import load_manifests

    contracts_root = Path(__file__).resolve().parents[3] / "bridge" / "contracts"
    manifests = load_manifests(contracts_root)
    matrix = DegradedMatrix(manifests)
    assert matrix.behavior_for("command", "memory.write.v1") is DegradedBehavior.QUEUE_TO_OUTBOX
