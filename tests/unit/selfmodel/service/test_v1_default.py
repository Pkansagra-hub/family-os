"""M12.E1.I4 — fresh boot defaults to v1 conscience-first constitution."""

from __future__ import annotations

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.constitution_body import get_conscience_bucket
from k1.selfmodel.service.bootstrap_constitution import (
    BOOTSTRAP_CONSTITUTION_ID_V1,
    BOOTSTRAP_SIGNER_ID,
    BOOTSTRAP_WRITER_ID,
    ensure_bootstrap_constitution,
)
from k1.selfmodel.service.signature_chain import Ed25519SignatureChainValidator

T_MS = 1_700_000_000_000


def _store() -> InMemoryProjectionStore:
    return InMemoryProjectionStore(allowed_writers=(BOOTSTRAP_WRITER_ID,))


def test_default_schema_version_is_v1() -> None:
    """`ensure_bootstrap_constitution` defaults to v1 (M12.E1.I1)."""
    store = _store()
    validator = Ed25519SignatureChainValidator(min_signatures=1)
    res = ensure_bootstrap_constitution(store, now_ms=T_MS, validator=validator)
    assert res.created is True
    assert res.snapshot.constitution_id == BOOTSTRAP_CONSTITUTION_ID_V1
    assert BOOTSTRAP_SIGNER_ID in validator.known_signers


def test_v1_default_guardian_forbids_prescribe_medication() -> None:
    """M12.E1.I2 — guardian role MUST forbid `prescribe_medication`."""
    store = _store()
    res = ensure_bootstrap_constitution(store, now_ms=T_MS)
    bucket = get_conscience_bucket(res.snapshot.body, role="guardian")
    assert "prescribe_medication" in bucket.forbidden, (
        f"guardian.forbidden must include prescribe_medication, " f"got {bucket.forbidden!r}"
    )


def test_v1_default_member_forbids_prescribe_medication() -> None:
    store = _store()
    res = ensure_bootstrap_constitution(store, now_ms=T_MS)
    bucket = get_conscience_bucket(res.snapshot.body, role="member")
    assert "prescribe_medication" in bucket.forbidden


def test_v1_default_child_forbids_storyline_high_risk_acts() -> None:
    store = _store()
    res = ensure_bootstrap_constitution(store, now_ms=T_MS)
    bucket = get_conscience_bucket(res.snapshot.body, role="child")
    for act in (
        "prescribe_medication",
        "share_location",
        "set_routine",
        "grocery_order",
        "wellness_call",
    ):
        assert act in bucket.forbidden, f"child.forbidden missing {act}"


def test_v1_default_send_message_must_ask_everywhere() -> None:
    store = _store()
    res = ensure_bootstrap_constitution(store, now_ms=T_MS)
    for role in ("self", "guardian", "member", "child"):
        bucket = get_conscience_bucket(res.snapshot.body, role=role)
        if role == "child":
            # child has must_ask=[send_message] in v1 yaml
            assert "send_message" in bucket.must_ask
        else:
            assert (
                "send_message" in bucket.must_ask
            ), f"{role}.must_ask missing send_message: {bucket.must_ask!r}"
