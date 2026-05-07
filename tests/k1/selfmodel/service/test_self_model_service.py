"""Unit tests for ``SelfModelService`` (M1.E1.I1)."""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.self_model import LayerObservation
from k1.selfmodel.service.errors import UnknownActorError
from k1.selfmodel.service.self_model import (
    SELF_MODEL_WRITER_ID,
    SelfModelService,
)
from k1.sessionstate.sections.meta import PrivacyBand, SessionIdentity
from tests.k1.selfmodel.service._helpers import (
    T0_MS,
    build_bundle,
    make_actor,
)


# ---------------------------------------------------------------------
# get
# ---------------------------------------------------------------------
def test_get_unknown_returns_none() -> None:
    bundle = build_bundle()
    assert bundle.self_model.get("ghost") is None


def test_get_returns_snapshot_with_freshness() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    res = bundle.self_model.get("a1")
    assert res is not None
    assert res.snapshot.actor_id == "a1"
    assert res.first_seen is False
    assert res.freshness.value == "fresh"


def test_empty_actor_id_rejected() -> None:
    bundle = build_bundle()
    with pytest.raises(ValueError):
        bundle.self_model.get("")


# ---------------------------------------------------------------------
# Seeding from MetaSection identity
# ---------------------------------------------------------------------
def _identity(user_id: str = "a1") -> SessionIdentity:
    return SessionIdentity(
        session_id="s1",
        user_id=user_id,
        device_id="d1",
        privacy_band=PrivacyBand.AMBER,
        is_anonymous=False,
        is_demo_mode=False,
    )


def test_seed_from_identity_creates_l1_block() -> None:
    bundle = build_bundle()
    res = bundle.self_model.get_or_seed_from_identity("a1", _identity("a1"))
    assert res.first_seen is True
    assert res.snapshot.L1_core["device_id"] == "d1"
    assert res.snapshot.L1_core["privacy_band"] == int(PrivacyBand.AMBER)
    # Onboarding fields are NOT inferred from identity.
    assert "name" not in res.snapshot.L1_core


def test_seed_idempotent_when_already_present() -> None:
    bundle = build_bundle(actors=(make_actor("a1", name="Aanya"),))
    first = bundle.self_model.get_or_seed_from_identity("a1", _identity("a1"))
    assert first.first_seen is False
    assert first.snapshot.L1_core["name"] == "Aanya"


def test_seed_requires_user_id() -> None:
    bundle = build_bundle()
    with pytest.raises(UnknownActorError):
        bundle.self_model.get_or_seed_from_identity("a1", SessionIdentity(user_id=""))


def test_seed_writer_id_must_be_allowed() -> None:
    # Build the bundle WITHOUT including SELF_MODEL_WRITER_ID in the
    # allowlist to demonstrate the error path is wired.
    from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore

    store = InMemoryProjectionStore(allowed_writers=("not:selfmodel",))
    sm = SelfModelService(store)
    with pytest.raises(RuntimeError, match="rejected"):
        sm.get_or_seed_from_identity("a1", _identity("a1"))


# ---------------------------------------------------------------------
# Layer observations
# ---------------------------------------------------------------------
def test_l4_l5_observations_stay_in_ram_only() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))

    bundle.self_model.update_layer(
        "L4",
        LayerObservation(
            actor_id="a1",
            layer="L4",
            kind="copresence",
            payload={"in_kitchen": True},
            observed_at_ms=T0_MS,
        ),
    )
    bundle.self_model.update_layer(
        "L5",
        LayerObservation(
            actor_id="a1",
            layer="L5",
            kind="mood",
            payload={"focused": True},
            observed_at_ms=T0_MS,
        ),
    )

    # Read back via the service: stitched in.
    res = bundle.self_model.get("a1")
    assert res is not None
    assert res.snapshot.L4_context == {"copresence": {"in_kitchen": True}}
    assert res.snapshot.L5_state == {"mood": {"focused": True}}

    # Direct read from the store: NEVER persisted.
    raw, _ = bundle.store.read_self("a1")
    assert raw is not None
    assert raw.L4_context == {}
    assert raw.L5_state == {}


def test_l3_observation_persists() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    bundle.self_model.update_layer(
        "L3",
        LayerObservation(
            actor_id="a1",
            layer="L3",
            kind="morning_routine",
            payload={"wake_at_ms": 25_200_000},
            observed_at_ms=T0_MS,
        ),
    )
    res = bundle.self_model.get("a1")
    assert res is not None
    assert res.snapshot.L3_pattern["morning_routine"] == {"wake_at_ms": 25_200_000}
    raw, _ = bundle.store.read_self("a1")
    assert raw is not None
    assert raw.L3_pattern["morning_routine"] == {"wake_at_ms": 25_200_000}


def test_l3_observation_for_unknown_actor_rejected() -> None:
    bundle = build_bundle()
    with pytest.raises(UnknownActorError):
        bundle.self_model.update_layer(
            "L3",
            LayerObservation(
                actor_id="ghost", layer="L3", kind="x", payload={}, observed_at_ms=T0_MS
            ),
        )


@pytest.mark.parametrize("layer", ["L1", "L2", "X", ""])
def test_unsupported_layer_rejected(layer: str) -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    with pytest.raises(ValueError):
        bundle.self_model.update_layer(
            layer,
            LayerObservation(
                actor_id="a1", layer=layer, kind="x", payload={}, observed_at_ms=T0_MS
            ),
        )


def test_observation_layer_must_match_layer_argument() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    with pytest.raises(ValueError):
        bundle.self_model.update_layer(
            "L4",
            LayerObservation(actor_id="a1", layer="L5", kind="x", payload={}, observed_at_ms=T0_MS),
        )


def test_observation_actor_id_required() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    with pytest.raises(ValueError):
        bundle.self_model.update_layer(
            "L4",
            LayerObservation(actor_id="", layer="L4", kind="x", payload={}, observed_at_ms=T0_MS),
        )


# ---------------------------------------------------------------------
# Freshness convenience
# ---------------------------------------------------------------------
def test_freshness_helper() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    assert bundle.self_model.freshness("a1").value == "fresh"
    bundle.store.mark_stale("self:a1")
    assert bundle.self_model.freshness("a1").value == "stale"


# ---------------------------------------------------------------------
# Cross-actor isolation
# ---------------------------------------------------------------------
def test_l4_l5_per_actor_isolation() -> None:
    bundle = build_bundle(actors=(make_actor("a1"), make_actor("a2", role="child")))
    bundle.self_model.update_layer(
        "L4",
        LayerObservation(
            actor_id="a1",
            layer="L4",
            kind="copresence",
            payload={"in_kitchen": True},
        ),
    )
    a1 = bundle.self_model.get("a1")
    a2 = bundle.self_model.get("a2")
    assert a1 is not None and a2 is not None
    assert a1.snapshot.L4_context == {"copresence": {"in_kitchen": True}}
    assert a2.snapshot.L4_context == {}  # no leak


def test_writer_id_constant_is_stable() -> None:
    assert SELF_MODEL_WRITER_ID == "selfmodel:self_model_service"
