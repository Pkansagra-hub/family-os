"""KeyringVault — production credential vault backed by the system keyring.

On Windows this resolves to :class:`keyring.backends.Windows.WinVaultKeyring`,
which uses DPAPI to encrypt secrets per-user. macOS / Linux backends
work transparently via the same API; PR#2 ships the Windows path and
PR#2b extends test coverage to the other platforms.

Service-name layout: keyring stores credentials under a ``service``
string. We use ``family_os/<adapter_id>`` so secrets owned by different
adapters are namespaced inside the OS credential store. The "username"
column carries the credential ``key`` (e.g. ``oauth.refresh_token``).

Audit logging is always-on. Every store/retrieve/rotate/delete call
appends a row to the configured :class:`VaultAuditLog` regardless of
success — failures record ``ok=False`` with a sanitized error message.

A small in-memory index of ``(adapter_id, key)`` tuples is maintained
because the cross-platform :mod:`keyring` API does not expose a "list
all keys for a service" operation. The index is hydrated from the
audit log on startup so it survives process restarts.
"""

from __future__ import annotations

import threading
from typing import Any

from ..credential_vault import (
    CredentialNotFoundError,
    VaultHealth,
)
from .audit_log import VaultAuditLog

_SERVICE_PREFIX: str = "family_os"
_HEALTHCHECK_ADAPTER: str = "__healthcheck__"
_HEALTHCHECK_KEY: str = "ping"


def _service_for(adapter_id: str) -> str:
    """Compose the keyring service string for an adapter."""
    return f"{_SERVICE_PREFIX}/{adapter_id}"


class KeyringVault:
    """System-keyring-backed :class:`CredentialVault` implementation.

    Parameters:
        keyring_module: The keyring backend module to call. In
            production this is ``import keyring``; tests inject a
            stub. We accept the module rather than a backend instance
            so we benefit from keyring's runtime backend selection.
        audit_log: Required audit logger. Vault construction without
            an audit log is forbidden by gate
            ``vault_audit_log_required`` (lands in PR#2 alongside).
        backend_name: Override for testing. Production callers
            should leave this as the default ``"keyring"``.
    """

    def __init__(
        self,
        *,
        keyring_module: Any,
        audit_log: VaultAuditLog,
        backend_name: str = "keyring",
    ) -> None:
        self._kr = keyring_module
        self._audit = audit_log
        self.backend_name = backend_name
        self._lock = threading.RLock()
        # Index of known (adapter_id, key) tuples. Hydrated from audit
        # log so list_keys works across restarts; mutated on every
        # store/delete.
        self._index: set[tuple[str, str]] = set()
        self._hydrate_index()

    # -- Index recovery ----------------------------------------------------

    def _hydrate_index(self) -> None:
        """Re-derive the live key set from the audit log on startup."""
        for entry in self._audit.read_all():
            if not entry.ok:
                continue
            pair = (entry.adapter_id, entry.key)
            if entry.op in ("store", "rotate"):
                self._index.add(pair)
            elif entry.op == "delete":
                self._index.discard(pair)

    # -- CredentialVault Protocol -----------------------------------------

    def store(self, *, adapter_id: str, key: str, secret: str) -> None:
        with self._lock:
            try:
                self._kr.set_password(_service_for(adapter_id), key, secret)
            except Exception as exc:  # noqa: BLE001 — funnel into audit
                self._audit.append(
                    adapter_id=adapter_id,
                    key=key,
                    op="store",
                    backend=self.backend_name,
                    ok=False,
                    error=_sanitize(exc),
                )
                raise
            self._index.add((adapter_id, key))
            self._audit.append(
                adapter_id=adapter_id,
                key=key,
                op="store",
                backend=self.backend_name,
                ok=True,
            )

    def retrieve(self, *, adapter_id: str, key: str) -> str:
        with self._lock:
            try:
                secret = self._kr.get_password(_service_for(adapter_id), key)
            except Exception as exc:  # noqa: BLE001
                self._audit.append(
                    adapter_id=adapter_id,
                    key=key,
                    op="retrieve",
                    backend=self.backend_name,
                    ok=False,
                    error=_sanitize(exc),
                )
                raise
            if secret is None:
                self._audit.append(
                    adapter_id=adapter_id,
                    key=key,
                    op="retrieve",
                    backend=self.backend_name,
                    ok=False,
                    error="not found",
                )
                raise CredentialNotFoundError(
                    f"no credential for adapter_id={adapter_id!r} key={key!r}"
                )
            self._audit.append(
                adapter_id=adapter_id,
                key=key,
                op="retrieve",
                backend=self.backend_name,
                ok=True,
            )
            return secret

    def delete(self, *, adapter_id: str, key: str) -> None:
        with self._lock:
            try:
                self._kr.delete_password(_service_for(adapter_id), key)
            except Exception as exc:  # noqa: BLE001 — keyring raises
                # PasswordDeleteError when the entry doesn't exist;
                # treat that as an idempotent no-op (matches
                # InMemoryCredentialVault.delete contract).
                msg = _sanitize(exc)
                if (
                    "not found" in msg.lower()
                    or "no such" in msg.lower()
                    or type(exc).__name__ == "PasswordDeleteError"
                ):
                    self._index.discard((adapter_id, key))
                    self._audit.append(
                        adapter_id=adapter_id,
                        key=key,
                        op="delete",
                        backend=self.backend_name,
                        ok=True,
                        error="absent (idempotent no-op)",
                    )
                    return
                self._audit.append(
                    adapter_id=adapter_id,
                    key=key,
                    op="delete",
                    backend=self.backend_name,
                    ok=False,
                    error=msg,
                )
                raise
            self._index.discard((adapter_id, key))
            self._audit.append(
                adapter_id=adapter_id,
                key=key,
                op="delete",
                backend=self.backend_name,
                ok=True,
            )

    def rotate(self, *, adapter_id: str, key: str, new_secret: str) -> None:
        with self._lock:
            if (adapter_id, key) not in self._index:
                self._audit.append(
                    adapter_id=adapter_id,
                    key=key,
                    op="rotate",
                    backend=self.backend_name,
                    ok=False,
                    error="not found",
                )
                raise CredentialNotFoundError(
                    f"cannot rotate: no credential for " f"adapter_id={adapter_id!r} key={key!r}"
                )
            try:
                self._kr.set_password(_service_for(adapter_id), key, new_secret)
            except Exception as exc:  # noqa: BLE001
                self._audit.append(
                    adapter_id=adapter_id,
                    key=key,
                    op="rotate",
                    backend=self.backend_name,
                    ok=False,
                    error=_sanitize(exc),
                )
                raise
            self._audit.append(
                adapter_id=adapter_id,
                key=key,
                op="rotate",
                backend=self.backend_name,
                ok=True,
            )

    def list_keys(self, *, adapter_id: str) -> list[str]:
        with self._lock:
            return sorted(k for (a, k) in self._index if a == adapter_id)

    def health_check(self) -> VaultHealth:
        # Probe by writing+reading+deleting a known sentinel record.
        # We use a sentinel adapter_id / key to avoid colliding with
        # real credentials. Failures are surfaced as ok=False rather
        # than raised so callers can include vault status in /healthz.
        sentinel = "ok"
        try:
            self._kr.set_password(_service_for(_HEALTHCHECK_ADAPTER), _HEALTHCHECK_KEY, sentinel)
            got = self._kr.get_password(_service_for(_HEALTHCHECK_ADAPTER), _HEALTHCHECK_KEY)
            self._kr.delete_password(_service_for(_HEALTHCHECK_ADAPTER), _HEALTHCHECK_KEY)
        except Exception as exc:  # noqa: BLE001 — diagnostic
            return VaultHealth(
                backend=self.backend_name,
                ok=False,
                detail=_sanitize(exc),
            )
        if got != sentinel:
            return VaultHealth(
                backend=self.backend_name,
                ok=False,
                detail="round-trip mismatch",
            )
        return VaultHealth(
            backend=self.backend_name,
            ok=True,
            detail=f"{len(self._index)} record(s) tracked",
        )


def _sanitize(exc: BaseException) -> str:
    """One-line, secret-free error description for the audit log."""
    msg = f"{type(exc).__name__}: {exc}"
    # Trim to a single line of bounded length so log-tailing operators
    # don't need to deal with embedded newlines or pathological lengths.
    return msg.splitlines()[0][:240]


__all__ = ["KeyringVault"]
