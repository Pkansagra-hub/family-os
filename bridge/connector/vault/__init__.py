"""Real vault backends (MS-5 PR#2).

This package ships the production-grade :class:`CredentialVault`
implementations:

* :class:`KeyringVault` — wraps the system keyring (Windows DPAPI via
  ``WinVaultKeyring``; macOS Keychain and Linux Secret Service work
  out-of-box for PR#2b once those platforms are tested).
* :class:`VaultAuditLog` — append-only JSONL recorder for every
  store / retrieve / rotate / delete call. Records ``adapter_id``,
  ``key``, ``op``, ``backend``, and ``ts`` — never the secret itself.
* :func:`create_vault` — factory selector keyed off
  ``BRIDGE_VAULT_BACKEND`` env var (``memory`` for tests/echo,
  ``keyring`` for production).

The reference :class:`bridge.connector.credential_vault.InMemoryCredentialVault`
remains the test-time fallback and ships in the parent module.
"""

from __future__ import annotations

from .audit_log import VaultAuditEntry, VaultAuditLog
from .factory import create_vault
from .keyring_vault import KeyringVault

__all__ = [
    "KeyringVault",
    "VaultAuditEntry",
    "VaultAuditLog",
    "create_vault",
]
