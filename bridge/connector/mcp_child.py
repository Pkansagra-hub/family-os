"""MCPChild — per-adapter MCP subprocess record (MS-5 PR#2).

The :class:`SkeletonMCPProcessManager` (PR#1) tracked adapter state in
a private ``_AdapterRecord``. PR#2's :class:`RealMCPProcessManager`
upgrades that to a public dataclass so we can:

1. Hold the live :class:`MCPStdioTransport` reference.
2. Track ``last_ping_ok_at`` for the health subsystem.
3. Carry the per-adapter :class:`CrashBudget`.
4. Surface lifecycle state for the
   :class:`bridge.connector.contracts.AdapterHealth` snapshot.

The class is intentionally a passive record — all transitions are
driven by the process manager so we keep the lock discipline in one
place.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from .crash_budget import CrashBudget
from .transport import MCPStdioTransport

ChildState = Literal[
    "stopped",
    "starting",
    "ready",
    "unhealthy",
    "quarantined",
]


@dataclass(slots=True)
class MCPChild:
    """One running (or recently-running) MCP child process.

    Attributes:
        adapter_id: Owning adapter id (manifest ``adapter_id``).
        manifest: Full manifest dict — kept for restart fidelity.
        transport: Live :class:`MCPStdioTransport` once ``state`` is
            ``ready``; ``None`` otherwise.
        state: Lifecycle state. See :data:`ChildState`.
        last_ping_ok_at: Epoch-ms of the last successful health ping.
            Used by ``health()``; 0 means never pinged.
        consecutive_failures: How many consecutive pings have failed
            since the last successful one.
        crash_budget: Per-adapter crash counter + sliding-window
            quarantine logic (see :mod:`crash_budget`).
        tools: Cached ``tools/list`` from the most recent open() call.
        message: One-line operator-visible status string. Set on
            errors to give ``health()`` something to display.
    """

    adapter_id: str
    manifest: dict[str, Any]
    transport: MCPStdioTransport | None = None
    state: ChildState = "stopped"
    last_ping_ok_at: int = 0
    consecutive_failures: int = 0
    crash_budget: CrashBudget = field(default_factory=CrashBudget)
    tools: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""

    def mark_ready(self, *, transport: MCPStdioTransport, tools: list[dict[str, Any]]) -> None:
        self.transport = transport
        self.tools = list(tools)
        self.state = "ready"
        self.last_ping_ok_at = int(time.time() * 1000)
        self.consecutive_failures = 0
        self.message = ""

    def mark_unhealthy(self, *, message: str) -> None:
        self.state = "unhealthy"
        self.consecutive_failures += 1
        self.message = message

    def mark_stopped(self) -> None:
        self.transport = None
        self.state = "stopped"
        self.message = ""

    def mark_quarantined(self, *, message: str) -> None:
        self.transport = None
        self.state = "quarantined"
        self.message = message


__all__ = ["ChildState", "MCPChild"]
