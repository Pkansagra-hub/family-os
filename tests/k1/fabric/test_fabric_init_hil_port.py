"""E3.M1.1 -- CapabilityFabric.__init__ accepts an optional hil_port.

Verifies:
  - Default construction (no hil_port kwarg) leaves _hil_port == None.
  - Explicit hil_port kwarg is stored on the instance.
  - The slot exists in __slots__ (frozen-ish container guarantee).
  - Existing construction call sites (no hil_port) keep working.
"""

from __future__ import annotations

from typing import Any

from k1.fabric.fabric import CapabilityFabric, FabricConfig


def _stub() -> Any:
    """Returns a bare object usable as a duck-typed dependency."""
    return object()


def _build(**overrides: Any) -> CapabilityFabric:
    """Construct CapabilityFabric with all-stub dependencies + optional overrides."""
    kwargs = dict(
        resolver=_stub(),
        context_builder=_stub(),
        validation_pipeline=_stub(),
        event_emitter=_stub(),
        registry=_stub(),
        provider_factory=_stub(),
        config=FabricConfig(),
    )
    kwargs.update(overrides)
    return CapabilityFabric(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Slot exists
# ---------------------------------------------------------------------------


def test_capability_fabric_slots_include_hil_port() -> None:
    assert "_hil_port" in CapabilityFabric.__slots__


# ---------------------------------------------------------------------------
# Default behaviour
# ---------------------------------------------------------------------------


def test_default_hil_port_is_none() -> None:
    fabric = _build()
    assert fabric._hil_port is None


# ---------------------------------------------------------------------------
# Explicit injection
# ---------------------------------------------------------------------------


def test_explicit_hil_port_stored() -> None:
    sentinel = _stub()
    fabric = _build(hil_port=sentinel)
    assert fabric._hil_port is sentinel


# ---------------------------------------------------------------------------
# Backwards compatibility: existing legacy construction shapes keep working
# ---------------------------------------------------------------------------


def test_construction_without_hil_port_kwarg_succeeds() -> None:
    """Legacy construction (no hil_port arg) must not raise."""
    fabric = _build()
    # Sanity: other slots still wired
    assert fabric._resolver is not None
    assert fabric._context_builder is not None
    assert fabric._validation_pipeline is not None


def test_construction_with_circuit_breakers_and_hil_port() -> None:
    """Mixing newer HIL kwarg with existing optional kwargs works."""
    cb_map = {"mcp-test": _stub()}
    fabric = _build(circuit_breakers=cb_map, hil_port=_stub())
    assert fabric._hil_port is not None
    assert fabric._circuit_breakers is cb_map
