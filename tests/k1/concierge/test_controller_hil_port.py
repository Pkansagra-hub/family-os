"""
tests.k1.concierge.test_controller_hil_port -- E4.M1.1 unified HIL port wiring
=============================================================================

Issue coverage:
  E4.M1.1 -- ``ConciergeController`` exposes ``_hil_port`` field plus
             ``set_hil_port`` setter.
  E4.M1.4 -- legacy ``_hil_coordinator`` field and ``set_hitl_coordinator``
             method deleted; only the unified path remains.

These tests assert the unified field defaults to ``None`` and that the
setter records and replaces values correctly.  Integration coverage
lands in E4.M1.6 once the factory wires a real ``IHILPort``.
"""

from __future__ import annotations

from typing import Any

from k1.concierge.bus.setup import create_poc_bus, create_poc_router
from k1.concierge.fsm.controller import ConciergeController


def _make_controller() -> ConciergeController:
    bus = create_poc_bus(capture=True)
    router = create_poc_router()
    return ConciergeController(bus=bus, router=router)


class _StubHILPort:
    """Bare stand-in for IHILPort -- the setter never invokes it in M1.1."""

    def __init__(self, label: str = "stub") -> None:
        self.label = label


def test_default_hil_port_none() -> None:
    """Newly constructed controllers have no unified HIL port attached."""
    fsm = _make_controller()
    assert fsm._hil_port is None
    # E4.M1.4: legacy `_hil_coordinator` slot was deleted from the controller.
    assert not hasattr(fsm, "_hil_coordinator")


def test_set_hil_port_attaches() -> None:
    """``set_hil_port`` records the provided port on the controller."""
    fsm = _make_controller()
    port: Any = _StubHILPort("first")

    fsm.set_hil_port(port)

    assert fsm._hil_port is port
    # E4.M1.4: legacy `set_hitl_coordinator` API is also gone.
    assert not hasattr(fsm, "set_hitl_coordinator")


def test_set_hil_port_replaces() -> None:
    """A second ``set_hil_port`` call replaces the previously attached port."""
    fsm = _make_controller()
    first: Any = _StubHILPort("first")
    second: Any = _StubHILPort("second")

    fsm.set_hil_port(first)
    fsm.set_hil_port(second)

    assert fsm._hil_port is second
    assert fsm._hil_port is not first
