"""Vault factory — selects a backend by env / explicit name (MS-5 PR#2).

Default selection logic:

* ``BRIDGE_VAULT_BACKEND=memory`` (or unset in tests) → in-memory vault.
* ``BRIDGE_VAULT_BACKEND=keyring`` → :class:`KeyringVault` over the
  system keyring (Windows DPAPI in production).
* ``BRIDGE_VAULT_BACKEND=sqlcipher`` → reserved for PR#2b; raises
  :class:`NotImplementedError` until then.

The factory always provisions a :class:`VaultAuditLog` for non-memory
backends, defaulting to ``BRIDGE_VAULT_AUDIT_LOG`` env var or
``./var/bridge/vault_audit.jsonl`` if unset.

Production deployments wire the factory inside the bridge runtime; the
gateway and tests still accept any :class:`CredentialVault` instance
directly so this module is intentionally side-effect-free.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..credential_vault import CredentialVault, InMemoryCredentialVault
from .audit_log import VaultAuditLog
from .keyring_vault import KeyringVault

_ENV_BACKEND: str = "BRIDGE_VAULT_BACKEND"
_ENV_AUDIT_PATH: str = "BRIDGE_VAULT_AUDIT_LOG"
_DEFAULT_AUDIT_PATH: str = "var/bridge/vault_audit.jsonl"


def create_vault(
    *,
    backend: str | None = None,
    audit_log_path: str | os.PathLike[str] | None = None,
) -> CredentialVault:
    """Construct a :class:`CredentialVault` for the requested backend.

    Args:
        backend: ``memory`` | ``keyring`` | ``sqlcipher``. Defaults to
            ``$BRIDGE_VAULT_BACKEND`` then ``"memory"``.
        audit_log_path: Audit-log file path for non-memory backends.
            Defaults to ``$BRIDGE_VAULT_AUDIT_LOG`` then
            ``./var/bridge/vault_audit.jsonl``.

    Raises:
        ValueError: unknown backend name.
        NotImplementedError: backend reserved for a later PR.
    """
    selected = backend or os.getenv(_ENV_BACKEND, "memory")
    selected = selected.strip().lower()

    if selected == "memory":
        return InMemoryCredentialVault()

    if selected == "keyring":
        import keyring  # local import: avoid keyring import cost in tests

        path = audit_log_path or os.getenv(_ENV_AUDIT_PATH) or _DEFAULT_AUDIT_PATH
        audit = VaultAuditLog(path=Path(path))
        return KeyringVault(keyring_module=keyring, audit_log=audit)

    if selected == "sqlcipher":
        raise NotImplementedError("sqlcipher vault backend is reserved for MS-5 PR#2b")

    raise ValueError(
        f"unknown vault backend {selected!r}; " "expected one of: memory, keyring, sqlcipher"
    )


__all__ = ["create_vault"]
