"""M5.E2.I1 — selfmodel <-> k1.sessionstate seam.

Per IMPLEMENTATION_PLAN_SELF_MODEL.md M5.E2.I1:

    Validate: MetaSection seed -> SelfModelService.get; PrivacyBand
    mapping; writer authorization rejected for unregistered ids.
    Acceptance: integration test green using real SessionStateFactory
    + DirectWriterAdapter.

This is a wiring test only. No business logic added — just plumbs
the real ``SessionStateFactory.create_for_testing()`` manager + a
real ``InMemoryProjectionStore`` (with the canonical
``selfmodel:*`` allowlist) through ``SelfModelService``.
"""

from __future__ import annotations

import pytest

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.service.self_model import (
    SELF_MODEL_WRITER_ID,
    SelfModelService,
)
from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.sections.meta import (
    MetaSection,
    PrivacyBand,
    SessionIdentity,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _store() -> InMemoryProjectionStore:
    """Store with canonical writer allowlist (mirrors kernel S2.6)."""
    return InMemoryProjectionStore(allowed_writers=(SELF_MODEL_WRITER_ID, "test:fixture"))


def _identity(*, user_id="actor:liam", privacy=PrivacyBand.AMBER) -> SessionIdentity:
    return SessionIdentity(
        session_id="sess-1",
        user_id=user_id,
        device_id="dev-1",
        privacy_band=privacy,
        is_anonymous=False,
        is_demo_mode=False,
    )


# ---------------------------------------------------------------------
# Seed pathway: MetaSection.identity -> SelfModelService.get_or_seed
# ---------------------------------------------------------------------
def test_meta_section_seeds_self_model_first_read() -> None:
    """First read seeds L1 from the live MetaSection identity."""
    manager = SessionStateFactory.create_for_testing(session_id="sess-1")
    try:
        manager.start()
        meta: MetaSection = manager.get_section("meta")
        meta.identity = _identity(user_id="actor:liam", privacy=PrivacyBand.RED)

        sm = SelfModelService(_store())
        # First read: must seed (no row exists yet) and return first_seen=True.
        result = sm.get_or_seed_from_identity("actor:liam", meta.identity)
        assert result.first_seen is True
        assert result.snapshot.actor_id == "actor:liam"
        # PrivacyBand mapping: SessionIdentity.privacy_band (IntEnum) is
        # propagated into L1_core["privacy_band"] as an int.
        assert result.snapshot.L1_core["privacy_band"] == int(PrivacyBand.RED)
        assert result.snapshot.L1_core["device_id"] == "dev-1"
        assert result.snapshot.L1_core["is_anonymous"] is False
        assert result.snapshot.L1_core["is_demo_mode"] is False
    finally:
        manager.stop()


def test_second_read_does_not_reseed() -> None:
    """A subsequent read returns the persisted row (first_seen=False)."""
    manager = SessionStateFactory.create_for_testing(session_id="sess-1")
    try:
        manager.start()
        meta: MetaSection = manager.get_section("meta")
        meta.identity = _identity(privacy=PrivacyBand.GREEN)

        sm = SelfModelService(_store())
        first = sm.get_or_seed_from_identity("actor:liam", meta.identity)
        second = sm.get_or_seed_from_identity("actor:liam", meta.identity)
        assert first.first_seen is True
        assert second.first_seen is False
        assert second.snapshot.actor_id == first.snapshot.actor_id
    finally:
        manager.stop()


# ---------------------------------------------------------------------
# All four PrivacyBand values map cleanly through the seed.
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "band",
    [PrivacyBand.GREEN, PrivacyBand.AMBER, PrivacyBand.RED, PrivacyBand.BLACK],
)
def test_privacy_band_round_trips_into_l1(band: PrivacyBand) -> None:
    sm = SelfModelService(_store())
    out = sm.get_or_seed_from_identity("actor:x", _identity(user_id="actor:x", privacy=band))
    assert out.snapshot.L1_core["privacy_band"] == int(band)


# ---------------------------------------------------------------------
# Writer authorization: stores reject unregistered writer ids.
# ---------------------------------------------------------------------
def test_unregistered_writer_id_is_rejected_by_projection_store() -> None:
    """The store's allowlist is the K1 enforcement boundary for writer ids.

    Per the M5 wiring contract, ``KernelService.startup`` registers
    only the canonical ``selfmodel:*`` writer ids on the projection
    store. Any other writer id (e.g. a stray adapter or test harness
    writing through the wrong door) MUST be rejected.
    """
    store = _store()  # allowlist = (selfmodel:self_model_service, test:fixture)
    snap = K1SelfModelSnapshot(actor_id="actor:rogue", L1_core={"actor_id": "actor:rogue"})

    # Canonical writer accepted.
    ok = store.write_self(snap, writer_id=SELF_MODEL_WRITER_ID)
    assert ok.accepted is True

    # Unregistered writer rejected.
    bad = store.write_self(snap, writer_id="rogue:not_in_allowlist")
    assert bad.accepted is False
    assert "writer" in (bad.reason or "").lower() or "allow" in (bad.reason or "").lower()


def test_self_model_service_surfaces_store_rejection() -> None:
    """If the store rejects the SelfModelService writer id, the service
    must raise — never silently drop the seed."""
    # Allowlist deliberately omits SELF_MODEL_WRITER_ID.
    misconfigured = InMemoryProjectionStore(allowed_writers=("test:fixture",))
    sm = SelfModelService(misconfigured)
    with pytest.raises(RuntimeError, match="rejected"):
        sm.get_or_seed_from_identity("actor:x", _identity(user_id="actor:x"))


# ---------------------------------------------------------------------
# UnknownActorError when the identity carries no user_id at all.
# ---------------------------------------------------------------------
def test_seed_requires_user_id_in_identity() -> None:
    from k1.selfmodel.service.self_model import UnknownActorError

    sm = SelfModelService(_store())
    blank = SessionIdentity(session_id="s", user_id="", device_id="d")
    with pytest.raises(UnknownActorError):
        sm.get_or_seed_from_identity("actor:x", blank)
