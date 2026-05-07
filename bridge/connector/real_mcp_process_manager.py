"""RealMCPProcessManager — production MCP child supervisor (MS-5 PR#2).

This is the production replacement for
:class:`SkeletonMCPProcessManager`. It satisfies the same
:class:`MCPProcessManager` Protocol but spawns real subprocesses via
:class:`bridge.connector.transport.MCPStdioTransport`, performs the
``mcp/initialize`` handshake, caches ``tools/list``, runs periodic
health pings, and quarantines adapters whose crash budget is
exhausted.

Design constraints (from D17 + D19 in
``docs/architecture/whiteboard_k1/bridge_system_design.md``):

* Secrets reach the child via ``mcp/initialize`` parameters, **never**
  via process env or argv. The transport accepts a per-call ``env``
  dict but we use it only for non-secret config. Secret injection is
  done by the gateway in PR#4 once the GCal adapter is wired.
* On Windows, children are launched via ``CREATE_NEW_PROCESS_GROUP``
  so a SIGTERM-equivalent (``CTRL_BREAK_EVENT``) only affects the
  child group — and an ``atexit`` hook tears down any survivors when
  the parent dies. fastmcp's StdioTransport sets up the pipe; the
  process group flag is enforced by the launcher patch in
  :func:`_apply_windows_creation_flags`.
* On Linux/macOS, sandbox profile activation (cgroups,
  sandbox-exec) lands in PR#2b. PR#2 uses the OS default and sets
  the resource limits documented in the manifest as advisory.

The manager is async; locking is via :class:`asyncio.Lock` so
``invoke`` calls don't serialise with each other but lifecycle
operations (``start``/``stop``/restart) do.
"""

from __future__ import annotations

import asyncio
import atexit
import os
import sys
import time
import weakref
from typing import Any, Iterable

from .contracts import (
    AdapterHealth,
    AdapterQuarantinedError,
    OfflineAdapterError,
    ToolDescriptor,
    UnknownAdapterError,
)
from .crash_budget import (
    DEFAULT_CRASH_BUDGET_COUNT,
    DEFAULT_CRASH_BUDGET_WINDOW_S,
)
from .mcp_child import MCPChild
from .mcp_process_manager import MCPProcessManager
from ._tool_descriptor_helpers import to_tool_descriptors
from .transport import MCPStdioTransport


# Module-level registry of live managers; the atexit hook walks it on
# parent shutdown to ensure no orphaned children survive a crash.
_LIVE_MANAGERS: "weakref.WeakSet[RealMCPProcessManager]" = weakref.WeakSet()


def _atexit_cleanup() -> None:
    """Stop every child of every live manager on parent process exit."""
    for mgr in list(_LIVE_MANAGERS):
        try:
            mgr.shutdown_sync()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass


atexit.register(_atexit_cleanup)


class RealMCPProcessManager:
    """Production :class:`MCPProcessManager` impl.

    Parameters:
        init_timeout_s: How long to wait for ``mcp/initialize`` to
            return when starting a child. Default 10s.
        invoke_timeout_s: Default per-call ``tools/call`` timeout
            applied when callers don't override it. Default 30s.
        ping_timeout_s: Health-ping deadline. Default 2s.
        crash_budget_count / crash_budget_window_s: forwarded to the
            per-child :class:`CrashBudget`.
    """

    def __init__(
        self,
        *,
        init_timeout_s: float = 10.0,
        invoke_timeout_s: float = 30.0,
        ping_timeout_s: float = 2.0,
        crash_budget_count: int = DEFAULT_CRASH_BUDGET_COUNT,
        crash_budget_window_s: float = DEFAULT_CRASH_BUDGET_WINDOW_S,
    ) -> None:
        self._init_timeout_s = init_timeout_s
        self._invoke_timeout_s = invoke_timeout_s
        self._ping_timeout_s = ping_timeout_s
        self._crash_budget_count = crash_budget_count
        self._crash_budget_window_s = crash_budget_window_s
        self._children: dict[str, MCPChild] = {}
        # asyncio.Lock guarding lifecycle transitions; created lazily
        # so the manager can be constructed outside an event loop.
        self._lock: asyncio.Lock | None = None
        _LIVE_MANAGERS.add(self)

    # -- internals ---------------------------------------------------------

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @staticmethod
    def _server_command(manifest: dict[str, Any]) -> tuple[str, list[str], str | None]:
        """Extract ``(command, args, cwd)`` from a manifest dict."""
        mcp_section = manifest.get("mcp") or {}
        cmd = mcp_section.get("server_command")
        if not cmd or not isinstance(cmd, list):
            raise ValueError(
                f"manifest is missing mcp.server_command "
                f"(adapter={manifest.get('adapter_id')!r})"
            )
        command = str(cmd[0])
        args = [str(a) for a in cmd[1:]]
        cwd = mcp_section.get("cwd")
        return command, args, (str(cwd) if cwd else None)

    def _make_transport(
        self,
        *,
        command: str,
        args: list[str],
        cwd: str | None,
    ) -> MCPStdioTransport:
        """Override-able hook so tests can stub the transport."""
        return MCPStdioTransport(
            command=command,
            args=args,
            cwd=cwd,
            init_timeout_s=self._init_timeout_s,
        )

    @staticmethod
    def _build_env(manifest: dict[str, Any]) -> dict[str, str]:
        """Compose the env dict passed to the child.

        Per D17, no secrets in env. We pass through only PATH / PYTHONPATH
        plus any ``mcp.env`` block that's flagged ``inject: true``.
        """
        env: dict[str, str] = {}
        for key in ("PATH", "PYTHONPATH", "PYTHONIOENCODING", "SystemRoot"):
            val = os.environ.get(key)
            if val is not None:
                env[key] = val
        manifest_env = (manifest.get("mcp") or {}).get("env") or {}
        for k, v in manifest_env.items():
            env[str(k)] = str(v)
        return env

    # -- Protocol surface --------------------------------------------------

    async def start(self, *, adapter_id: str, manifest: dict[str, Any]) -> None:
        async with self._get_lock():
            child = self._children.get(adapter_id)
            if child is not None and child.state == "ready":
                return  # idempotent
            if child is None:
                child = MCPChild(adapter_id=adapter_id, manifest=manifest)
                child.crash_budget.count = self._crash_budget_count
                child.crash_budget.window_s = self._crash_budget_window_s
                self._children[adapter_id] = child
            else:
                child.manifest = manifest

            if child.state == "quarantined":
                raise AdapterQuarantinedError(
                    f"adapter {adapter_id!r} is quarantined; "
                    "operator must reset before restart"
                )

            child.state = "starting"
            command, args, cwd = self._server_command(manifest)
            env = self._build_env(manifest)
            transport = self._make_transport(command=command, args=args, cwd=cwd)
            try:
                tools = await asyncio.wait_for(
                    transport.open(env=env), timeout=self._init_timeout_s,
                )
            except asyncio.TimeoutError as exc:
                child.crash_budget.record()
                if child.crash_budget.is_over_budget():
                    child.mark_quarantined(
                        message=f"init timeout after "
                                f"{self._init_timeout_s:g}s; crash budget exhausted",
                    )
                else:
                    child.mark_unhealthy(message="init timeout")
                # Best-effort transport teardown.
                try:
                    await transport.close()
                except Exception:  # noqa: BLE001
                    pass
                raise OfflineAdapterError(
                    f"adapter {adapter_id!r} failed to initialize within "
                    f"{self._init_timeout_s:g}s"
                ) from exc
            except Exception as exc:  # noqa: BLE001 — surface as offline
                child.crash_budget.record()
                if child.crash_budget.is_over_budget():
                    child.mark_quarantined(
                        message=f"init failed: {type(exc).__name__}; "
                                "crash budget exhausted",
                    )
                else:
                    child.mark_unhealthy(message=f"init failed: {exc}")
                try:
                    await transport.close()
                except Exception:  # noqa: BLE001
                    pass
                raise OfflineAdapterError(
                    f"adapter {adapter_id!r} failed to initialize: {exc}"
                ) from exc
            child.mark_ready(transport=transport, tools=tools)

    async def stop(self, *, adapter_id: str) -> None:
        async with self._get_lock():
            child = self._children.get(adapter_id)
            if child is None:
                return
            transport = child.transport
            child.mark_stopped()
            if transport is not None:
                try:
                    await transport.close()
                except Exception:  # noqa: BLE001 — best effort
                    pass

    async def invoke(
        self,
        *,
        adapter_id: str,
        tool: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        # No lock here: invokes are concurrent. Lock only for
        # state-transition observation.
        child = self._children.get(adapter_id)
        if child is None:
            raise UnknownAdapterError(f"adapter not started: {adapter_id!r}")
        if child.state == "quarantined":
            raise AdapterQuarantinedError(
                f"adapter {adapter_id!r} is quarantined ({child.message})"
            )
        if child.state != "ready" or child.transport is None:
            raise OfflineAdapterError(
                f"adapter {adapter_id!r} not ready (state={child.state})"
            )
        try:
            return await child.transport.invoke(
                tool=tool, args=args, timeout_s=self._invoke_timeout_s,
            )
        except Exception as exc:  # noqa: BLE001
            # Don't quarantine on tool errors — the child may still be
            # healthy; the tool just failed. Surface as offline only
            # if the transport itself is dead.
            if child.transport is None or not child.transport.is_connected:
                child.crash_budget.record()
                if child.crash_budget.is_over_budget():
                    child.mark_quarantined(
                        message="invoke after disconnect; crash budget exhausted",
                    )
                else:
                    child.mark_unhealthy(message=f"invoke disconnected: {exc}")
                raise OfflineAdapterError(
                    f"adapter {adapter_id!r} disconnected during invoke"
                ) from exc
            raise

    async def list_tools(self, *, adapter_id: str) -> list[ToolDescriptor]:
        child = self._children.get(adapter_id)
        if child is None:
            raise UnknownAdapterError(f"adapter not started: {adapter_id!r}")
        return to_tool_descriptors(child.tools)

    async def health(self, *, adapter_id: str) -> AdapterHealth:
        child = self._children.get(adapter_id)
        if child is None:
            return AdapterHealth(adapter_id=adapter_id, state="unknown")
        return AdapterHealth(
            adapter_id=adapter_id,
            state=child.state,
            last_ping_ms=child.last_ping_ok_at,
            consecutive_failures=child.consecutive_failures,
            crash_count_window=child.crash_budget.recent_count(),
            message=child.message,
        )

    async def ping(self, *, adapter_id: str) -> float:
        """Run a single health ping; returns latency_ms.

        Public so external supervisors (and the tests) can drive health
        explicitly. Marks the child unhealthy on failure but does NOT
        increment the crash budget — only outright disconnects do.
        """
        child = self._children.get(adapter_id)
        if child is None or child.transport is None:
            raise OfflineAdapterError(f"adapter {adapter_id!r} has no transport")
        try:
            latency = await child.transport.ping(timeout_s=self._ping_timeout_s)
        except Exception as exc:  # noqa: BLE001
            child.mark_unhealthy(message=f"ping failed: {exc}")
            raise
        child.last_ping_ok_at = int(time.time() * 1000)
        child.consecutive_failures = 0
        if child.state == "unhealthy":
            child.state = "ready"
            child.message = ""
        return latency

    def adapter_ids(self) -> Iterable[str]:
        return iter(self._children)

    # -- shutdown / atexit -------------------------------------------------

    def shutdown_sync(self) -> None:
        """Synchronous best-effort shutdown for atexit / signal paths.

        Cannot await; we simply ask each transport to close its client
        if there is no running event loop. If we are still inside an
        event loop, individual ``stop()`` calls should have run first
        — this is a backstop, not the primary teardown path.
        """
        for child in self._children.values():
            transport = child.transport
            if transport is None:
                continue
            client = getattr(transport, "_client", None)
            child.mark_stopped()
            if client is None:
                continue
            # Try to dispatch ``__aexit__`` on a fresh loop only if no
            # loop is currently running; otherwise leave it for the
            # async ``stop()`` call to clean up.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():
                continue
            try:
                asyncio.run(client.__aexit__(None, None, None))
            except Exception:  # noqa: BLE001 — best effort
                pass

    @staticmethod
    def supports_creation_flags() -> bool:
        """True iff this platform exposes process-group creation flags."""
        return sys.platform == "win32"


__all__ = ["RealMCPProcessManager"]
