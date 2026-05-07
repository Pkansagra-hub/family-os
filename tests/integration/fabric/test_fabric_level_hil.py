"""M12.E4.I2 -- Fabric-level conscience + HIL integration test.

These tests verify that ``CapabilityFabric._run_conscience_gate`` runs
BEFORE ``_run_hil_gate`` and short-circuits with
``conscience_forbidden`` when the actor's :class:`ConscienceDigest`
forbids the contract's ``social_act``. We exercise the helper directly
(no full Fabric pipeline) so the assertions are deterministic and do
not depend on capability registry contents or providers.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from k1.fabric.fabric import CapabilityFabric, FabricConfig
from k1.fabric.types import CapabilityRequest
from k1.selfmodel.contracts.conscience import ConscienceDigest

# ---------------------------------------------------------------------------
# Stub conscience port
# ---------------------------------------------------------------------------


class _StubConsciencePort:
    def __init__(
        self,
        forbidden: tuple[str, ...] = (),
        must_ask: tuple[str, ...] = (),
    ) -> None:
        self._digest = ConscienceDigest(
            forbidden_acts=forbidden,
            must_ask_acts=must_ask,
        )
        self.calls: list[tuple[str, int]] = []

    def get_digest(
        self,
        actor_id: str,
        *,
        T_ms: int,
        device_id: str | None = None,  # noqa: ARG002
    ) -> ConscienceDigest:
        self.calls.append((actor_id, T_ms))
        return self._digest


def _stub() -> Any:
    return object()


def _build(
    *,
    conscience_port: Any | None = None,
    hil_port: Any | None = None,
) -> CapabilityFabric:
    return CapabilityFabric(
        resolver=_stub(),
        context_builder=_stub(),
        validation_pipeline=_stub(),
        event_emitter=_stub(),
        registry=_stub(),
        provider_factory=_stub(),
        config=FabricConfig(),
        hil_port=hil_port,
        conscience_port=conscience_port,
    )


def _contract(
    *,
    name: str = "tool.execute.prescribe_medication",
    social_act: str | None = "prescribe_medication",
) -> Any:
    return SimpleNamespace(
        name=name,
        safety_band_min="RED",
        requires_human_confirmation=True,
        side_effects=[],
        description="prescribe a medication",
        social_act=social_act,
        risk_class="safety_sensitive",
    )


def _request(**overrides: Any) -> CapabilityRequest:
    base = dict(
        request_id="req-1",
        capability_name="tool.execute.prescribe_medication",
        params={"patient": "alice", "drug": "ibuprofen"},
        caller="test",
        caller_id="member.alice",
        trace_id="trace-1",
    )
    base.update(overrides)
    return CapabilityRequest(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Disabled paths (gate must not interfere)
# ---------------------------------------------------------------------------


def test_no_conscience_port_returns_none() -> None:
    fabric = _build(conscience_port=None)
    assert fabric._run_conscience_gate(_request(), _contract(), "trace-1") is None


def test_contract_without_social_act_returns_none() -> None:
    port = _StubConsciencePort(forbidden=("prescribe_medication",))
    fabric = _build(conscience_port=port)
    contract = _contract(social_act=None)
    assert fabric._run_conscience_gate(_request(), contract, "trace-1") is None
    # Should not even call the port when there's nothing to check.
    assert port.calls == []


def test_request_without_caller_id_returns_none() -> None:
    port = _StubConsciencePort(forbidden=("prescribe_medication",))
    fabric = _build(conscience_port=port)
    req = _request(caller_id="")
    assert fabric._run_conscience_gate(req, _contract(), "trace-1") is None
    assert port.calls == []


# ---------------------------------------------------------------------------
# Forbid path
# ---------------------------------------------------------------------------


def test_forbidden_act_short_circuits_with_conscience_forbidden() -> None:
    port = _StubConsciencePort(forbidden=("prescribe_medication",))
    fabric = _build(conscience_port=port)
    result = fabric._run_conscience_gate(_request(), _contract(), "trace-1")
    assert result is not None
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "conscience_forbidden"
    assert result.error.retriable is False
    assert port.calls and port.calls[0][0] == "member.alice"


def test_must_ask_only_does_not_block() -> None:
    """``must_ask`` is HIL territory; the conscience gate must not block."""
    port = _StubConsciencePort(must_ask=("prescribe_medication",))
    fabric = _build(conscience_port=port)
    assert fabric._run_conscience_gate(_request(), _contract(), "trace-1") is None


def test_unrelated_forbidden_act_does_not_block() -> None:
    port = _StubConsciencePort(forbidden=("share_location",))
    fabric = _build(conscience_port=port)
    assert fabric._run_conscience_gate(_request(), _contract(), "trace-1") is None


# ---------------------------------------------------------------------------
# Defensive path: digest lookup raises -> fail-open (allow through to HIL)
# ---------------------------------------------------------------------------


class _BrokenConsciencePort:
    def get_digest(self, *_a: Any, **_k: Any) -> ConscienceDigest:
        raise RuntimeError("oops")


def test_digest_exception_falls_through_to_hil() -> None:
    fabric = _build(conscience_port=_BrokenConsciencePort())
    # Must not raise; returns None so the HIL gate can still run.
    assert fabric._run_conscience_gate(_request(), _contract(), "trace-1") is None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
