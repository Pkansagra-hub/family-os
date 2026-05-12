"""ConnectorHost — pluggable MCP/connector dispatch for pseudo-K0.

K1 invokes K0-side connectors through the bridge contract
``connector.execute.*`` (the gateway port). On a real K0, those calls
land in the connector gateway which routes to a registered MCP handler.

The pseudo-K0 mirrors that shape: handlers register against
``(adapter_id, action)`` pairs and are looked up at dispatch time.
Unknown pairs raise :class:`ConnectorNotFound` so the FastAPI layer can
translate to a 404-style envelope reply.

This module has no FastAPI / HTTP dependency — the server layer owns
routing; this owns the registry + dispatch only.
"""

from __future__ import annotations

import threading
from typing import Any, Awaitable, Callable, Dict, Protocol, Tuple, runtime_checkable

__all__ = [
    "ConnectorNotFound",
    "DuplicateHandler",
    "IMCPHandler",
    "ConnectorHost",
    "HandlerFn",
]

HandlerFn = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class ConnectorNotFound(KeyError):
    """Raised when ``dispatch`` is called with no matching handler."""


class DuplicateHandler(ValueError):
    """Raised when ``register`` collides with an existing key."""


@runtime_checkable
class IMCPHandler(Protocol):
    """Async connector handler protocol.

    Implementations expose an ``adapter_id`` + ``action`` pair and an
    ``async execute(params)`` method that returns a JSON-serialisable
    dict. The pseudo-K0 server passes the connector params dict from the
    envelope body straight through.
    """

    adapter_id: str
    action: str

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]: ...


class ConnectorHost:
    """Thread-safe registry + dispatcher for MCP-style handlers.

    Parameters
    ----------
    None — construct with no args and call :meth:`register` to add
    handlers (or :meth:`register_fn` to register a bare callable).
    """

    def __init__(self) -> None:
        self._handlers: Dict[Tuple[str, str], HandlerFn] = {}
        self._lock = threading.Lock()

    # -- registration --------------------------------------------------------

    def register(self, handler: IMCPHandler) -> None:
        """Register an :class:`IMCPHandler` instance.

        Raises
        ------
        DuplicateHandler
            If ``(adapter_id, action)`` is already registered.
        """
        key = (handler.adapter_id, handler.action)
        with self._lock:
            if key in self._handlers:
                raise DuplicateHandler(
                    f"handler already registered for adapter_id={key[0]!r} action={key[1]!r}"
                )
            self._handlers[key] = handler.execute

    def register_fn(self, adapter_id: str, action: str, fn: HandlerFn) -> None:
        """Register a bare async callable under ``(adapter_id, action)``."""
        key = (adapter_id, action)
        with self._lock:
            if key in self._handlers:
                raise DuplicateHandler(
                    f"handler already registered for adapter_id={adapter_id!r} action={action!r}"
                )
            self._handlers[key] = fn

    def unregister(self, adapter_id: str, action: str) -> bool:
        """Remove a handler. Returns True if present, False if not."""
        with self._lock:
            return self._handlers.pop((adapter_id, action), None) is not None

    # -- introspection -------------------------------------------------------

    def has(self, adapter_id: str, action: str) -> bool:
        with self._lock:
            return (adapter_id, action) in self._handlers

    def list_handlers(self) -> list[Tuple[str, str]]:
        with self._lock:
            return sorted(self._handlers.keys())

    # -- dispatch ------------------------------------------------------------

    async def dispatch(
        self,
        adapter_id: str,
        action: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Look up and invoke the handler for ``(adapter_id, action)``.

        Raises
        ------
        ConnectorNotFound
            If no handler is registered.
        """
        with self._lock:
            fn = self._handlers.get((adapter_id, action))
        if fn is None:
            raise ConnectorNotFound(
                f"no connector handler for adapter_id={adapter_id!r} action={action!r}"
            )
        result = await fn(params)
        if not isinstance(result, dict):
            raise TypeError(
                f"connector handler {adapter_id}/{action} returned {type(result).__name__}, "
                "expected dict"
            )
        return result
