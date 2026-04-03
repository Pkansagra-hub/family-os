"""ICredentialPort -- credential store access [F15].

MH-02: ALL API keys in CredentialStore (never in config/env/manifest).

Import graph (Layer 1)
----------------------
k1.model_hub.ports.credential_port
  -> stdlib only
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ICredentialPort(Protocol):
    """Credential store access (MH-02).

    Source: OS keychain / Vault / env.
    Keys NEVER stored in manifest YAML.
    """

    async def get_key(self, provider_id: str) -> str:
        """Retrieve API key for a provider."""
        ...

    async def refresh_key(self, provider_id: str) -> str:
        """Refresh and return a new API key for a provider."""
        ...


__all__ = ["ICredentialPort"]
