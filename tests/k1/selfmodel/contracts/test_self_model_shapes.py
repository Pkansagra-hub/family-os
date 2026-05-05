"""M0.E1.I2 — self_model contract dataclasses are frozen and minimal-construct."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot, LayerObservation


def test_layer_observation_min_construct() -> None:
    obs = LayerObservation(actor_id="alice", layer="L3", kind="preference")
    assert obs.actor_id == "alice"
    assert obs.layer == "L3"
    assert obs.kind == "preference"
    assert obs.payload == {}
    assert obs.observed_at_ms == 0


def test_layer_observation_is_frozen() -> None:
    obs = LayerObservation(actor_id="alice", layer="L3", kind="preference")
    with pytest.raises(FrozenInstanceError):
        obs.actor_id = "bob"  # type: ignore[misc]


def test_k1_self_model_snapshot_min_construct() -> None:
    snap = K1SelfModelSnapshot(actor_id="alice")
    assert snap.actor_id == "alice"
    assert snap.revision == ""
    assert snap.L1_core == {}
    assert snap.L2_identity == {}
    assert snap.L3_pattern == {}
    assert snap.L4_context == {}
    assert snap.L5_state == {}


def test_k1_self_model_snapshot_is_frozen() -> None:
    snap = K1SelfModelSnapshot(actor_id="alice")
    with pytest.raises(FrozenInstanceError):
        snap.actor_id = "bob"  # type: ignore[misc]


def test_k1_self_model_snapshot_each_layer_has_independent_default() -> None:
    a = K1SelfModelSnapshot(actor_id="alice")
    b = K1SelfModelSnapshot(actor_id="bob")
    assert a.L3_pattern is not b.L3_pattern  # field(default_factory=dict)
