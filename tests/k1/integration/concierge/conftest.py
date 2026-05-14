"""Shared fixtures for end-to-end concierge flow tests.

Boots a real ``KernelService`` (no mocks) with isolated SQLite paths
under ``tmp_path``. Each test creates a session and drives a real user
message through the per-session bus.

Test mode wiring:
    - ``model_mode='test'``     -> StubProviderPlugin registered for every
                                   capability (returns canned ``"OK"``).
    - ``bridge_enabled=False``  -> no K0 connection required.
    - ``auto_start_consumer=True`` (default) -> FSM consumer task runs.

The LLM is a real plugin (just deterministic) -- there are
no ``unittest.mock`` objects in the wire path.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from k1.bus.envelope.envelope import Envelope
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService


@pytest.fixture
def kernel_config(tmp_path) -> KernelConfig:
    """Minimal isolated KernelConfig for concierge end-to-end tests."""
    return KernelConfig(
        test_mode=True,
        model_mode="test",
        ordered_bus=True,
        capture_bus=False,
        session_mode="standalone",
        enable_experience=True,
        enable_delta=True,
        enable_hitl=True,
        enable_orchestrator=True,
        enable_ledger=True,
        enable_dead_letter_consumer=True,
        bridge_enabled=False,
        bridge_offline_ok=True,
        otel_enabled=False,
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        workflow_db_path=str(tmp_path / "wf.db"),
        bridge_outbox_path=str(tmp_path / "bridge.db"),
    )


@pytest.fixture
async def kernel_service(kernel_config: KernelConfig):
    """Boot a real KernelService with isolated state and shut it down cleanly."""
    svc = KernelService(config=kernel_config)
    await svc.startup()
    try:
        yield svc
    finally:
        await svc.shutdown()


class BusCapture:
    """Sync subscriber that records every envelope on a topic.

    The LocalBus dispatch is synchronous; ``handler`` runs on the publisher's
    thread. We capture envelopes into a thread-safe list and signal arrival
    via a ``threading.Event`` so async tests can ``await wait_one(timeout)``.
    """

    __slots__ = ("_bus", "_handle", "_lock", "_topic", "envelopes", "received")

    def __init__(self, bus: Any, topic: str) -> None:
        self._bus = bus
        self._topic = topic
        self._handle: Any = None
        self._lock = threading.RLock()
        self.envelopes: list[Envelope] = []
        self.received = threading.Event()

    def start(self) -> None:
        if self._handle is None:
            self._handle = self._bus.subscribe(self._topic, self._on_envelope)

    def stop(self) -> None:
        if self._handle is None:
            return
        try:
            self._bus.unsubscribe(self._handle)
        except Exception:
            pass
        self._handle = None

    def _on_envelope(self, env: Envelope) -> None:
        with self._lock:
            self.envelopes.append(env)
        self.received.set()

    async def wait_one(self, timeout_s: float = 10.0) -> Envelope:
        """Await arrival of at least one envelope; return the first."""
        deadline = asyncio.get_event_loop().time() + timeout_s
        while not self.received.is_set():
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"BusCapture[{self._topic}]: no envelope after {timeout_s}s")
            await asyncio.sleep(0.05)
        with self._lock:
            return self.envelopes[0]


def inject_test_mcp_transport(session_fabric: Any) -> Any:
    """Replace the per-session fabric's MCP transport with a TestMCPTransport.

    Walks ``session_fabric.facade._provider_factory._port_deps`` and
    overwrites ``mcp_transport``.  Must be called BEFORE any MCP-routed
    capability is invoked, because ``MCPProvider`` caches the transport
    reference at construction time.

    Returns the installed ``TestMCPTransport`` so tests can register
    canned responses and inspect captured calls.
    """
    from k1.fabric.adapters.test_mcp_transport import TestMCPTransport

    facade = getattr(session_fabric, "facade", None) or session_fabric
    pf = getattr(facade, "_provider_factory", None)
    if pf is None:
        raise RuntimeError("inject_test_mcp_transport: facade._provider_factory missing")
    port_deps = getattr(pf, "_port_deps", None)
    if port_deps is None:
        raise RuntimeError("inject_test_mcp_transport: provider_factory._port_deps missing")
    transport = TestMCPTransport(connected=True)
    port_deps["mcp_transport"] = transport
    pf._port_deps = port_deps
    return transport
