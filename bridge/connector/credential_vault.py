"""Credential Vault Protocol (MS-5).

The vault stores per-adapter secrets (OAuth refresh tokens, API keys,
etc.) and is owned by the bridge runtime. MCP child processes do NOT
access the vault directly: per D17, secrets are passed to children at
``mcp/initialize`` time over stdio JSON-RPC, never via process env or
argv.

This module exposes the :class:`CredentialVault` Protocol plus an
:class:`InMemoryCredentialVault` reference implementation suitable for
tests and the in-tree echo MCP fixture.

Real backends (OS keychain via ``keyring``, AES-GCM SQLite fallback)
land under ``bridge/connector/vault/`` (PR#2 ships the Windows DPAPI
``KeyringVault``; PR#2b adds the cross-platform sqlcipher fallback).

Method names are deliberately ``store/retrieve`` (not ``put/get``) to
match the operational contract documented in
``bridge/ARCHITECTURE.md`` §10 and the implementation plan's MS-5
"Locked decisions" table.
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


@dataclass(frozen=True, slots=True)
class VaultHealth:
    """Health-check result for a vault backend.

    Attributes:
        backend: ``backend_name`` of the reporting vault.
        ok: True iff the backend is reachable and accepting reads/writes.
        detail: Optional one-line status message (used in
            ``/healthz`` output and operator runbooks).
    """

    backend: str
    ok: bool
    detail: str = ""


class CredentialNotFoundError(KeyError):
    """Raised when ``retrieve`` is called for an unknown ``(adapter_id, key)``."""


@runtime_checkable
class CredentialVault(Protocol):
    """Storage Protocol for adapter credentials.

    Implementations must be safe to call from the bridge runtime's
    asyncio loop AND from synchronous MCP supervision threads — i.e.
    use a re-entrant lock or be intrinsically thread-safe.

    Methods are synchronous; async callers (e.g. the gateway's
    pre-invoke step) wrap with ``asyncio.to_thread`` when required.
    """

    backend_name: str
    """Name of the backing store; written into ``st_ifl_credentials_metadata``."""

    def store(self, *, adapter_id: str, key: str, secret: str) -> None:
        """Store or overwrite a credential."""
        ...  # pragma: no cover

    def retrieve(self, *, adapter_id: str, key: str) -> str:
        """Read a credential; raises :class:`CredentialNotFoundError` if absent."""
        ...  # pragma: no cover

    def delete(self, *, adapter_id: str, key: str) -> None:
        """Remove a credential. Idempotent (no-op when absent)."""
        ...  # pragma: no cover

    def rotate(self, *, adapter_id: str, key: str, new_secret: str) -> None:
        """Atomically replace an existing credential with a new value.

        Implementations should perform the replacement under the same
        lock used by :meth:`store` so concurrent readers either see
        the old secret or the new secret, never an empty/missing
        record. Raises :class:`CredentialNotFoundError` if no record
        exists for ``(adapter_id, key)`` — callers must
        :meth:`store` first.
        """
        ...  # pragma: no cover

    def list_keys(self, *, adapter_id: str) -> list[str]:
        """List the credential keys held for an adapter."""
        ...  # pragma: no cover

    def health_check(self) -> VaultHealth:
        """Probe the backing store; reports operational status."""
        ...  # pragma: no cover


class InMemoryCredentialVault:
    """Reference vault impl used in tests and the echo MCP fixture.

    Volatile by design: on process exit all secrets vanish. NOT for
    production. Real backends live in :mod:`bridge.connector.vault`
    (PR#2 ships ``KeyringVault``; PR#2b adds the AES-GCM SQLite
    fallback).
    """

    backend_name = "memory"

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()

    def store(self, *, adapter_id: str, key: str, secret: str) -> None:
        with self._lock:
            self._store[(adapter_id, key)] = secret

    def retrieve(self, *, adapter_id: str, key: str) -> str:
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

    def rotate(self, *, adapter_id: str, key: str, new_secret: str) -> None:
        with self._lock:
            if (adapter_id, key) not in self._store:
                raise CredentialNotFoundError(
                    f"cannot rotate: no credential for "
                    f"adapter_id={adapter_id!r} key={key!r}"
                )
            self._store[(adapter_id, key)] = new_secret

    def list_keys(self, *, adapter_id: str) -> list[str]:
        with self._lock:
            return sorted(k for (a, k) in self._store if a == adapter_id)

    def health_check(self) -> VaultHealth:
        # In-memory store is always healthy if the lock is acquirable.
        with self._lock:
            return VaultHealth(
                backend=self.backend_name,
                ok=True,
                detail=f"{len(self._store)} record(s) in volatile store",
            )


__all__ = [
    "CredentialNotFoundError",
    "CredentialVault",
    "InMemoryCredentialVault",
    "VaultHealth",
    "VaultRecord",
]
