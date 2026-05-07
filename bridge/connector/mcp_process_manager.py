"""MCPProcessManager — supervises one MCP child process per active adapter.

MS-5 PR#1 ships this as a Protocol + skeleton. Real subprocess spawning,
per-OS sandbox profile activation, stdio JSON-RPC framing, and crash
budget enforcement land in PR#2.

The skeleton is exercised by the gateway pipeline tests via a stub
implementation that records ``invoke`` calls and reports a fixed health
state — sufficient to lock the contract surface without yet running real
MCP children.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Iterable, Protocol, runtime_checkable

from .contracts import (
    AdapterHealth,
    AdapterQuarantinedError,
    OfflineAdapterError,
    ToolDescriptor,
    UnknownAdapterError,
)


@runtime_checkable
class MCPProcessManager(Protocol):
    """Protocol for MCP child-process supervision.

    Real impl (PR#2) wraps :mod:`subprocess` with stdio JSON-RPC framing,
    per-OS sandbox activation (cgroup/sandbox-exec/Job Object), and
    health-ping driven crash budgeting.
    """

    async def start(self, *, adapter_id: str, manifest: dict[str, Any]) -> None:
        """Spawn the MCP child for ``adapter_id`` per ``manifest.mcp.server_command``."""
        ...  # pragma: no cover

    async def stop(self, *, adapter_id: str) -> None:
        """Send SIGTERM, then SIGKILL after grace period. Idempotent."""
        ...  # pragma: no cover

    async def invoke(
        self,
        *,
        adapter_id: str,
        tool: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a ``tools/call`` JSON-RPC request to the child; return its
        ``content`` payload.

        Raises:
            UnknownAdapterError: never started or already stopped.
            OfflineAdapterError: child crashed and is restarting.
            AdapterQuarantinedError: child exceeded crash budget.
        """
        ...  # pragma: no cover

    async def list_tools(self, *, adapter_id: str) -> list[ToolDescriptor]:
        """Cached MCP ``tools/list`` for the adapter."""
        ...  # pragma: no cover

    async def health(self, *, adapter_id: str) -> AdapterHealth:
        """Current health snapshot."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Skeleton (PR#1) — no real subprocess yet
# ---------------------------------------------------------------------------


class _AdapterRecord:
    """Per-adapter state held by the skeleton manager."""

    __slots__ = (
        "adapter_id",
        "manifest",
        "state",
        "tools",
        "last_ping_ms",
        "consecutive_failures",
        "crashes",
    )

    def __init__(self, *, adapter_id: str, manifest: dict[str, Any]) -> None:
        self.adapter_id = adapter_id
        self.manifest = manifest
        self.state = "stopped"  # stopped | starting | ready | unhealthy | quarantined
        self.tools: list[ToolDescriptor] = []
        self.last_ping_ms = 0
        self.consecutive_failures = 0
        self.crashes: deque[float] = deque(maxlen=32)


class SkeletonMCPProcessManager:
    """In-process skeleton manager.

    PR#1 contract: tracks adapter records, returns canned ``ready`` health,
    and delegates ``invoke`` to a per-adapter Python callable registered
    via :meth:`bind_tool`. Tests inject their own callables to exercise
    the gateway pipeline end-to-end without spawning subprocesses.

    Real subprocess + stdio + sandbox lands in PR#2 (subclass or replace
    this class while keeping the Protocol surface identical).
    """

    #: Configurable so tests can shrink the budget.
    crash_budget_count: int = 3
    crash_budget_window_s: float = 60.0

    def __init__(self) -> None:
        self._records: dict[str, _AdapterRecord] = {}
        # Bound tool callables: (adapter_id, tool) -> async callable
        self._tool_impls: dict[tuple[str, str], Any] = {}

    # -- Skeleton wiring ---------------------------------------------------

    def bind_tool(
        self,
        *,
        adapter_id: str,
        tool: str,
        impl: Any,
    ) -> None:
        """Register an in-process callable as the tool implementation.

        ``impl`` must be ``async def impl(args: dict) -> dict``. PR#1
        only — once PR#2 spawns real MCP children, the manager calls
        them over stdio and ``bind_tool`` becomes test-only.
        """

        self._tool_impls[(adapter_id, tool)] = impl

    def record_crash(self, *, adapter_id: str) -> None:
        """Test/PR#2 hook: record a crash and quarantine if over budget."""

        record = self._records.get(adapter_id)
        if record is None:
            return
        now = time.monotonic()
        record.crashes.append(now)
        cutoff = now - self.crash_budget_window_s
        recent = [t for t in record.crashes if t >= cutoff]
        record.crashes = deque(recent, maxlen=record.crashes.maxlen)
        if len(recent) >= self.crash_budget_count:
            record.state = "quarantined"

    # -- Protocol surface --------------------------------------------------

    async def start(self, *, adapter_id: str, manifest: dict[str, Any]) -> None:
        record = self._records.get(adapter_id)
        if record is None:
            record = _AdapterRecord(adapter_id=adapter_id, manifest=manifest)
            self._records[adapter_id] = record
        record.state = "ready"
        record.last_ping_ms = int(time.time() * 1000)

    async def stop(self, *, adapter_id: str) -> None:
        record = self._records.get(adapter_id)
        if record is not None:
            record.state = "stopped"

    async def invoke(
        self,
        *,
        adapter_id: str,
        tool: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        record = self._records.get(adapter_id)
        if record is None:
            raise UnknownAdapterError(f"adapter not started: {adapter_id!r}")
        if record.state == "quarantined":
            raise AdapterQuarantinedError(
                f"adapter {adapter_id!r} quarantined "
                f"({self.crash_budget_count} crashes within "
                f"{self.crash_budget_window_s:g}s)"
            )
        if record.state != "ready":
            raise OfflineAdapterError(f"adapter {adapter_id!r} not ready (state={record.state})")
        impl = self._tool_impls.get((adapter_id, tool))
        if impl is None:
            raise UnknownAdapterError(f"no tool {tool!r} bound on adapter {adapter_id!r}")
        return await impl(args)

    async def list_tools(self, *, adapter_id: str) -> list[ToolDescriptor]:
        record = self._records.get(adapter_id)
        if record is None:
            raise UnknownAdapterError(f"adapter not started: {adapter_id!r}")
        return list(record.tools)

    async def health(self, *, adapter_id: str) -> AdapterHealth:
        record = self._records.get(adapter_id)
        if record is None:
            return AdapterHealth(adapter_id=adapter_id, state="unknown")
        return AdapterHealth(
            adapter_id=adapter_id,
            state=record.state,
            last_ping_ms=record.last_ping_ms,
            consecutive_failures=record.consecutive_failures,
            crash_count_window=len(record.crashes),
        )

    def adapter_ids(self) -> Iterable[str]:
        """Iterate over registered adapter ids (skeleton helper)."""

        return iter(self._records)


__all__ = [
    "MCPProcessManager",
    "SkeletonMCPProcessManager",
]
