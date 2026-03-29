"""
k1.fabric.adapters.test_bridge -- TestBridgeAdapter (5.2.4).

In-memory K0 stub for testing.  Returns canned responses for Bridge
operations (memory.recall, memory.store, tool execution via IFL).

Design:
  - ``is_available()`` configurable via constructor (default True).
  - Canned responses keyed by ``operation`` string.
  - IFL routes handled by a separate ``ifl_responses`` dict keyed by
    IFL address.
  - Thread-safe via RLock for concurrent test scenarios.
  - Capture mode: records all commands/queries/IFL calls for assertions.
  - No real K0 dependency.

Structural subtyping:
  Satisfies IBridgePort protocol without inheriting from it.

Exports:
  TestBridgeAdapter
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from k1.fabric.ports.bridge_port import BridgeCommandResult, BridgeHealth, IFLRoute

# ---------------------------------------------------------------------------
# Captured call record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapturedBridgeCall:
    """Record of a bridge operation for test assertions."""

    method: str  # "send_command", "query", "route_ifl"
    operation: str  # operation string or IFL address
    payload: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    timestamp_ms: int = 0


# ---------------------------------------------------------------------------
# TestBridgeAdapter
# ---------------------------------------------------------------------------


class TestBridgeAdapter:
    """
    In-memory K0 bridge stub for testing (5.2.4).

    Implements IBridgePort structurally:
      - async send_command(operation, payload, *, trace_id, timeout_ms) -> BridgeCommandResult
      - async query(operation, selectors, *, trace_id, timeout_ms) -> BridgeCommandResult
      - async route_ifl(route, payload, *, trace_id) -> BridgeCommandResult
      - is_available() -> bool
      - get_health() -> BridgeHealth

    Setup helpers for tests:
      - set_available(flag) -- toggle availability
      - set_health(health) -- override health snapshot
      - add_response(operation, result) -- canned response for operation
      - add_ifl_response(address, result) -- canned IFL response
      - add_handler(operation, handler) -- dynamic handler for operation
      - clear_responses() -- reset all canned responses
      - get_captured() -- list of all captured calls
      - drain() -- return + clear captured calls
      - assert_called(operation, count) -- assert call count
      - call_count / command_count / query_count / ifl_count -- introspection
    """

    def __init__(
        self,
        *,
        available: bool = True,
        health: Optional[BridgeHealth] = None,
        capture: bool = True,
    ) -> None:
        self._available = available
        self._health = health or BridgeHealth(
            available=available,
            mode="K0_FULL" if available else "K0_OFFLINE",
        )
        self._capture = capture

        # Canned responses: operation -> BridgeCommandResult
        self._responses: Dict[str, BridgeCommandResult] = {}
        # IFL responses: ifl_address -> BridgeCommandResult
        self._ifl_responses: Dict[str, BridgeCommandResult] = {}
        # Dynamic handlers: operation -> callable(payload) -> BridgeCommandResult
        self._handlers: Dict[str, Callable[..., BridgeCommandResult]] = {}

        # Captured calls
        self._captured: List[CapturedBridgeCall] = []

        self._lock = threading.RLock()

    # -- Setup helpers -----------------------------------------------------

    def set_available(self, flag: bool) -> None:
        """Toggle bridge availability."""
        with self._lock:
            self._available = flag
            if not flag and self._health.available:
                self._health = BridgeHealth(
                    available=False,
                    mode="K0_OFFLINE",
                    error_message="Manually set unavailable",
                )
            elif flag and not self._health.available:
                self._health = BridgeHealth(
                    available=True,
                    mode="K0_FULL",
                )

    def set_health(self, health: BridgeHealth) -> None:
        """Override the health snapshot."""
        with self._lock:
            self._health = health
            self._available = health.available

    def add_response(
        self,
        operation: str,
        result: BridgeCommandResult,
    ) -> None:
        """Register a canned response for an operation."""
        with self._lock:
            self._responses[operation] = result

    def add_ifl_response(
        self,
        address: str,
        result: BridgeCommandResult,
    ) -> None:
        """Register a canned IFL response by address."""
        with self._lock:
            self._ifl_responses[address] = result

    def add_handler(
        self,
        operation: str,
        handler: Callable[..., BridgeCommandResult],
    ) -> None:
        """
        Register a dynamic handler for an operation.

        handler(operation, payload, trace_id) -> BridgeCommandResult
        Dynamic handlers take priority over canned responses.
        """
        with self._lock:
            self._handlers[operation] = handler

    def clear_responses(self) -> None:
        """Remove all canned responses and handlers."""
        with self._lock:
            self._responses.clear()
            self._ifl_responses.clear()
            self._handlers.clear()

    # -- Capture helpers ---------------------------------------------------

    def get_captured(
        self,
        method: Optional[str] = None,
    ) -> List[CapturedBridgeCall]:
        """Return captured calls, optionally filtered by method."""
        with self._lock:
            if method is None:
                return list(self._captured)
            return [c for c in self._captured if c.method == method]

    def drain(self) -> List[CapturedBridgeCall]:
        """Return and clear all captured calls."""
        with self._lock:
            result = list(self._captured)
            self._captured.clear()
            return result

    def assert_called(self, operation: str, count: int = 1) -> None:
        """Assert that an operation was called exactly count times."""
        with self._lock:
            actual = sum(1 for c in self._captured if c.operation == operation)
        if actual != count:
            raise AssertionError(f"Expected {operation!r} called {count} time(s), " f"got {actual}")

    @property
    def call_count(self) -> int:
        """Total captured calls."""
        with self._lock:
            return len(self._captured)

    @property
    def command_count(self) -> int:
        """Captured send_command calls."""
        with self._lock:
            return sum(1 for c in self._captured if c.method == "send_command")

    @property
    def query_count(self) -> int:
        """Captured query calls."""
        with self._lock:
            return sum(1 for c in self._captured if c.method == "query")

    @property
    def ifl_count(self) -> int:
        """Captured route_ifl calls."""
        with self._lock:
            return sum(1 for c in self._captured if c.method == "route_ifl")

    # -- Protocol methods --------------------------------------------------

    async def send_command(
        self,
        operation: str,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        """Send a command (write op) -- returns canned or default response."""
        self._record("send_command", operation, payload, trace_id)

        if not self._available:
            return BridgeCommandResult.fail(
                "k0_offline",
                "Bridge unavailable",
                k0_mode="K0_OFFLINE",
                trace_id=trace_id,
            )

        return self._resolve(operation, payload, trace_id)

    async def query(
        self,
        operation: str,
        selectors: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        """Query K0 (read op) -- returns canned or default response."""
        self._record("query", operation, selectors, trace_id)

        if not self._available:
            return BridgeCommandResult.fail(
                "k0_offline",
                "Bridge unavailable",
                k0_mode="K0_OFFLINE",
                trace_id=trace_id,
            )

        return self._resolve(operation, selectors, trace_id)

    async def route_ifl(
        self,
        route: IFLRoute,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
    ) -> BridgeCommandResult:
        """Route an IFL tool call -- returns canned or default response."""
        self._record("route_ifl", route.address, payload, trace_id)

        if not self._available:
            return BridgeCommandResult.fail(
                "k0_offline",
                "Bridge unavailable",
                k0_mode="K0_OFFLINE",
                trace_id=trace_id,
            )

        with self._lock:
            if route.address in self._ifl_responses:
                return self._ifl_responses[route.address]

        # Fall back to generic operation-based resolve
        return self._resolve(route.address, payload, trace_id)

    def is_available(self) -> bool:
        """Check bridge availability."""
        with self._lock:
            return self._available

    def get_health(self) -> BridgeHealth:
        """Return current health snapshot."""
        with self._lock:
            return self._health

    # -- Internals ---------------------------------------------------------

    def _record(
        self,
        method: str,
        operation: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """Capture a call if capture is enabled."""
        if self._capture:
            with self._lock:
                self._captured.append(
                    CapturedBridgeCall(
                        method=method,
                        operation=operation,
                        payload=dict(payload),
                        trace_id=trace_id,
                        timestamp_ms=int(time.time() * 1000),
                    )
                )

    def _resolve(
        self,
        operation: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> BridgeCommandResult:
        """Resolve a response for an operation."""
        with self._lock:
            # Dynamic handler first
            handler = self._handlers.get(operation)
            if handler is not None:
                return handler(operation, payload, trace_id)

            # Canned response
            if operation in self._responses:
                return self._responses[operation]

        # Default: success with empty data
        return BridgeCommandResult.ok(trace_id=trace_id)

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"TestBridgeAdapter(available={self._available}, "
                f"responses={len(self._responses)}, "
                f"ifl_responses={len(self._ifl_responses)}, "
                f"captured={len(self._captured)})"
            )
