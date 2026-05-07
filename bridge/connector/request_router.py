"""Stage 3 of the IFL gateway pipeline: RequestRouter.

The router takes a (verified) caller + manifest + tool/args and dispatches
the call to the MCP Process Manager, normalising errors into
:class:`ConnectorResult`.

In v1 the router is intentionally simple: no retries, no rate-limit
enforcement, no circuit breaker. Those land in v1.1 (the schema already
reserves ``rate_limit`` and ``circuit_breaker`` for that work).
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from .contracts import (
    AdapterQuarantinedError,
    ConnectorCaller,
    ConnectorGatewayError,
    ConnectorResult,
    OfflineAdapterError,
    UnknownAdapterError,
)
from .mcp_process_manager import MCPProcessManager


@runtime_checkable
class RequestRouter(Protocol):
    """Protocol for stage-3 dispatch."""

    async def dispatch(
        self,
        *,
        adapter_id: str,
        tool: str,
        args: dict[str, Any],
        caller: ConnectorCaller,
        manifest: dict[str, Any],
    ) -> ConnectorResult:
        """Route the call and return the normalised :class:`ConnectorResult`."""
        ...  # pragma: no cover


class DefaultRequestRouter:
    """Default MS-5 router: single-shot dispatch via MCP Process Manager."""

    def __init__(self, *, process_manager: MCPProcessManager) -> None:
        self._pm = process_manager

    async def dispatch(
        self,
        *,
        adapter_id: str,
        tool: str,
        args: dict[str, Any],
        caller: ConnectorCaller,
        manifest: dict[str, Any],
    ) -> ConnectorResult:
        del manifest, caller  # reserved for v1.1 (rate limit, breaker)
        start = time.monotonic()
        try:
            data = await self._pm.invoke(adapter_id=adapter_id, tool=tool, args=args)
        except (
            UnknownAdapterError,
            OfflineAdapterError,
            AdapterQuarantinedError,
        ):
            # Re-raise gateway errors — the gateway layer translates them
            # into envelopes/HTTP responses; the router stays narrow.
            raise
        except ConnectorGatewayError as exc:
            return ConnectorResult(
                success=False,
                adapter_id=adapter_id,
                tool=tool,
                error_code=type(exc).__name__,
                error_message=str(exc),
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 — gateway boundary
            return ConnectorResult(
                success=False,
                adapter_id=adapter_id,
                tool=tool,
                error_code="adapter_error",
                error_message=str(exc),
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        return ConnectorResult(
            success=True,
            data=data if isinstance(data, dict) else {"result": data},
            adapter_id=adapter_id,
            tool=tool,
            latency_ms=int((time.monotonic() - start) * 1000),
        )


__all__ = ["DefaultRequestRouter", "RequestRouter"]
