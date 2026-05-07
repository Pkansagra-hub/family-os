"""Tests for the MS-3a real-HTTP composite bridge client (HttpBridgeClient).

Covers the construction-guard contract (only ``BridgeRuntime.from_registry``
may instantiate it), the namespace-bag shape (per-contract publishers
reachable as attributes), and the runtime-driven wiring path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bridge.client import _RUNTIME_CONSTRUCTION_TOKEN, HttpBridgeClient
from bridge.runtime import BridgeRuntime, Role, Transport

CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "bridge" / "contracts"


class _StubTransport(Transport):
    """Transport stand-in that satisfies BridgeRuntime.from_registry's
    ``transport is not None`` branch without performing real I/O."""


# ---------------------------------------------------------------------------
# Construction guard
# ---------------------------------------------------------------------------


def test_direct_construction_without_token_raises() -> None:
    """Direct callers cannot instantiate ``HttpBridgeClient`` — RuntimeError."""
    with pytest.raises(RuntimeError, match="BridgeRuntime.from_registry"):
        HttpBridgeClient(_runtime_token=object())


def test_direct_construction_with_no_token_raises_typeerror() -> None:
    """The runtime-token argument is keyword-only and required."""
    with pytest.raises(TypeError):
        HttpBridgeClient()  # type: ignore[call-arg]


def test_construction_with_correct_token_succeeds() -> None:
    """The private sentinel token (only the runtime imports it) unlocks construction."""
    client = HttpBridgeClient(_runtime_token=_RUNTIME_CONSTRUCTION_TOKEN)
    assert client.memory_write_v1 is None
    assert client.query is None
    assert client.sse is None
    assert client.obs is None
    assert client.gateway is None


# ---------------------------------------------------------------------------
# Slots / shape
# ---------------------------------------------------------------------------


def test_http_bridge_client_uses_slots() -> None:
    """HttpBridgeClient declares __slots__ — no ad-hoc attribute injection."""
    client = HttpBridgeClient(_runtime_token=_RUNTIME_CONSTRUCTION_TOKEN)
    with pytest.raises(AttributeError):
        client.unknown_slot = "nope"  # type: ignore[attr-defined]


def test_http_bridge_client_slot_assignment_is_direct() -> None:
    """Slots are populated by name, not implicit re-binding via ``setattr``."""
    sentinel = object()
    client = HttpBridgeClient(
        _runtime_token=_RUNTIME_CONSTRUCTION_TOKEN,
        memory_write_v1=sentinel,
    )
    assert client.memory_write_v1 is sentinel


# ---------------------------------------------------------------------------
# Runtime wiring
# ---------------------------------------------------------------------------


def test_from_registry_k1_with_transport_populates_client() -> None:
    """When a K1 runtime is built with a transport, the ``client`` slot
    holds an HttpBridgeClient with the active-status contract clients."""
    runtime = BridgeRuntime.from_registry(
        contracts_path=CONTRACTS_PATH,
        role=Role.K1,
        transport=_StubTransport(),
    )
    assert runtime.client is not None
    assert isinstance(runtime.client, HttpBridgeClient)
    # memory.write.v1 manifest is status: active → client wired.
    assert runtime.client.memory_write_v1 is not None
    # MS-3a wires command-side only; query/sse/obs/gateway remain None.
    assert runtime.client.query is None


def test_from_registry_k1_without_transport_leaves_client_none() -> None:
    """No transport → no client wired (legacy default-construction path)."""
    runtime = BridgeRuntime.from_registry(
        contracts_path=CONTRACTS_PATH,
        role=Role.K1,
    )
    assert runtime.client is None
    assert runtime.command is None


def test_from_registry_k0_does_not_build_producer_client() -> None:
    """K0 runtimes are consumer-side; the producer ``client`` slot stays None."""
    runtime = BridgeRuntime.from_registry(
        contracts_path=CONTRACTS_PATH,
        role=Role.K0,
        transport=_StubTransport(),
    )
    assert runtime.client is None
