"""E3.M1.2 -- FabricFactory threads hil_port to CapabilityFabric.

Verifies all four public factory entry points (`create_standalone`,
`create_for_testing`, `create_with_ports`, `create_shared`) accept an
optional `hil_port` kwarg and store it on the returned
`CapabilityFabric` (`fabric.facade._hil_port`).
"""

from __future__ import annotations

from typing import Any

from k1.fabric.factory import FabricFactory


def _stub() -> Any:
    return object()


# ---------------------------------------------------------------------------
# Default behaviour: no hil_port -> None on facade
# ---------------------------------------------------------------------------


def test_create_standalone_default_hil_port_none() -> None:
    fabric = FabricFactory.create_standalone()
    assert fabric.facade._hil_port is None


def test_create_for_testing_default_hil_port_none() -> None:
    fabric = FabricFactory.create_for_testing()
    assert fabric.facade._hil_port is None


# ---------------------------------------------------------------------------
# Explicit hil_port threading
# ---------------------------------------------------------------------------


def test_create_standalone_threads_hil_port() -> None:
    sentinel = _stub()
    fabric = FabricFactory.create_standalone(hil_port=sentinel)
    assert fabric.facade._hil_port is sentinel


def test_create_for_testing_threads_hil_port() -> None:
    sentinel = _stub()
    fabric = FabricFactory.create_for_testing(hil_port=sentinel)
    assert fabric.facade._hil_port is sentinel


def test_create_with_ports_threads_hil_port() -> None:
    """create_with_ports requires real adapter wiring -- reuse the testing
    helper's adapters by going through create_for_testing's adapter
    construction, then call create_with_ports directly with them."""
    from k1.fabric.adapters.local_event import LocalEventAdapter
    from k1.fabric.adapters.test_bridge import TestBridgeAdapter
    from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
    from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
    from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
    from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter

    sentinel = _stub()
    fabric = FabricFactory.create_with_ports(
        state_reader=TestSessionStateReaderAdapter(),
        event_port=LocalEventAdapter(capture_mode=False),
        bridge=TestBridgeAdapter(),
        model_gateway=TestModelGatewayAdapter(),
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
        hil_port=sentinel,
    )
    assert fabric.facade._hil_port is sentinel


def test_create_shared_threads_hil_port() -> None:
    from k1.fabric.adapters.local_event import LocalEventAdapter
    from k1.fabric.adapters.test_bridge import TestBridgeAdapter
    from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
    from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
    from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter

    sentinel = _stub()
    fabric = FabricFactory.create_shared(
        event_port=LocalEventAdapter(capture_mode=False),
        bridge=TestBridgeAdapter(),
        model_gateway=TestModelGatewayAdapter(),
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
        production_mode=False,  # avoid dispatcher startup noise in tests
        hil_port=sentinel,
    )
    assert fabric.facade._hil_port is sentinel


# ---------------------------------------------------------------------------
# Backwards compatibility: legacy callers (no hil_port) still work
# ---------------------------------------------------------------------------


def test_legacy_create_standalone_call_still_works() -> None:
    fabric = FabricFactory.create_standalone()
    assert fabric.facade is not None
    assert fabric.facade._hil_port is None
