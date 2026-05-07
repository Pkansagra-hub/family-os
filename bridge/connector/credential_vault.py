"""Credential Vault Protocol (MS-5).

The vault stores per-adapter secrets (OAuth refresh tokens, API keys,
etc.) and is owned by the bridge runtime. MCP child processes do NOT
access the vault directly: per D17, secrets are passed to children at
``mcp/initialize`` time over stdio JSON-RPC, never via process env or
argv.

This module exposes the :class:`CredentialVault` Protocol plus an
:class:`InMemoryCredentialVault` reference implementation suitable for
tests and the in-tree echo MCP fixture.

Real backends (OS keychain via ``keyring``, sqlcipher fallback) land in
PR#3 of MS-5 under ``bridge/connector/vault/``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class VaultRecord:
    """A single credential record.

    Attributes:
        adapter_id: Owning adapter (e.g. ``google_calendar_father``).
        key: Credential type (e.g. ``oauth.refresh_token``).
        secret: The secret value. Never logged.
        backend: Which backend stored it (``memory``, ``keyring``,
            ``sqlcipher``). Used for the K0-side
            ``st_ifl_credentials_metadata`` row.
    """

    adapter_id: str
    key: str
    secret: str
    backend: str = "memory"


class CredentialNotFoundError(KeyError):
    """Raised when ``get`` is called for an unknown ``(adapter_id, key)``."""


@runtime_checkable
class CredentialVault(Protocol):
    """Storage Protocol for adapter credentials.

    Implementations must be safe to call from the bridge runtime's
    asyncio loop AND from synchronous MCP supervision threads — i.e.
    use a re-entrant lock or be intrinsically thread-safe.
    """

    backend_name: str
    """Name of the backing store; written into ``st_ifl_credentials_metadata``."""

    def put(self, *, adapter_id: str, key: str, secret: str) -> None:
        """Store or overwrite a credential."""
        ...  # pragma: no cover

    def get(self, *, adapter_id: str, key: str) -> str:
        """Read a credential; raises :class:`CredentialNotFoundError` if absent."""
        ...  # pragma: no cover

    def delete(self, *, adapter_id: str, key: str) -> None:
        """Remove a credential. Idempotent (no-op when absent)."""
        ...  # pragma: no cover

    def list_keys(self, *, adapter_id: str) -> list[str]:
        """List the credential keys held for an adapter."""
        ...  # pragma: no cover


class InMemoryCredentialVault:
    """Reference vault impl used in tests and the echo MCP fixture.

    Volatile by design: on process exit all secrets vanish. NOT for
    production. Real backends live in :mod:`bridge.connector.vault`
    (PR#3).
    """

    backend_name = "memory"

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()

    def put(self, *, adapter_id: str, key: str, secret: str) -> None:
        with self._lock:
            self._store[(adapter_id, key)] = secret

    def get(self, *, adapter_id: str, key: str) -> str:
        with self._lock:
            try:
                return self._store[(adapter_id, key)]
            except KeyError as exc:
                raise CredentialNotFoundError(
                    f"no credential for adapter_id={adapter_id!r} key={key!r}"
                ) from exc

    def delete(self, *, adapter_id: str, key: str) -> None:
        with self._lock:
            self._store.pop((adapter_id, key), None)

    def list_keys(self, *, adapter_id: str) -> list[str]:
        with self._lock:
            return sorted(k for (a, k) in self._store if a == adapter_id)


__all__ = [
    "CredentialNotFoundError",
    "CredentialVault",
    "InMemoryCredentialVault",
    "VaultRecord",
]
