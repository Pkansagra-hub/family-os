"""Unit tests for ``ConstitutionService`` read path (M1.E1.I3)."""

from __future__ import annotations

import pytest

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.constitution import ConstitutionSnapshot
from k1.selfmodel.service.constitution import (
    ConstitutionService,
    stub_signature_validator,
)
from k1.selfmodel.service.errors import (
    ConstitutionSafeModeError,
    ConstitutionUnavailableError,
)
from tests.k1.selfmodel.service._helpers import (
    DEFAULT_CONSTITUTION_ID,
    build_bundle,
    make_constitution,
    v0_body,
)


def test_get_active_returns_signed_snapshot() -> None:
    bundle = build_bundle(constitution=make_constitution(body=v0_body()))
    res = bundle.constitution.get_active()
    assert res.snapshot.constitution_id == DEFAULT_CONSTITUTION_ID
    assert res.snapshot.version == "v0"
    assert res.safe_mode is False
    assert res.freshness.value == "fresh"


def test_missing_row_raises_unavailable() -> None:
    bundle = build_bundle()
    with pytest.raises(ConstitutionUnavailableError):
        bundle.constitution.get_active()


def test_unsigned_snapshot_triggers_safe_mode() -> None:
    bundle = build_bundle(
        constitution=make_constitution(body=v0_body(), signed=False)
    )
    with pytest.raises(ConstitutionUnavailableError):
        bundle.constitution.get_active()
    assert bundle.constitution.is_safe_mode is True
    with pytest.raises(ConstitutionSafeModeError):
        bundle.constitution.ensure_writable()


def test_safe_mode_clears_after_recovery() -> None:
    store = InMemoryProjectionStore(allowed_writers=("test:fixture",))
    # First write: unsigned → triggers safe-mode.
    store.write_constitution(
        make_constitution(body=v0_body(), signed=False),
        writer_id="test:fixture",
    )
    svc = ConstitutionService(store, constitution_id=DEFAULT_CONSTITUTION_ID)
    with pytest.raises(ConstitutionUnavailableError):
        svc.get_active()
    assert svc.is_safe_mode

    # Replace with a signed snapshot.
    store.write_constitution(
        make_constitution(body=v0_body(), signed=True),
        writer_id="test:fixture",
    )
    res = svc.get_active()
    assert res.safe_mode is False
    assert svc.is_safe_mode is False
    svc.ensure_writable()  # no raise


def test_custom_validator_invoked() -> None:
    calls: list[ConstitutionSnapshot] = []

    def my_validator(s: ConstitutionSnapshot) -> bool:
        calls.append(s)
        return s.version == "v0"

    bundle = build_bundle(
        constitution=make_constitution(body=v0_body(), version="v0", signed=True)
    )
    bundle.constitution.__init__(  # re-init with the validator (test convenience)
        bundle.store,
        constitution_id=DEFAULT_CONSTITUTION_ID,
        validator=my_validator,
    )
    res = bundle.constitution.get_active()
    assert res.snapshot.version == "v0"
    assert len(calls) == 1


def test_constructor_rejects_empty_id() -> None:
    bundle = build_bundle()
    with pytest.raises(ValueError):
        ConstitutionService(bundle.store, constitution_id="")


def test_stub_validator_treats_empty_signatures_as_invalid() -> None:
    snap = make_constitution(body=v0_body(), signed=False)
    assert stub_signature_validator(snap) is False
    snap2 = make_constitution(body=v0_body(), signed=True)
    assert stub_signature_validator(snap2) is True


def test_freshness_helper() -> None:
    bundle = build_bundle(constitution=make_constitution(body=v0_body()))
    assert bundle.constitution.freshness().value == "fresh"
    bundle.store.mark_stale(f"constitution:{DEFAULT_CONSTITUTION_ID}")
    assert bundle.constitution.freshness().value == "stale"
