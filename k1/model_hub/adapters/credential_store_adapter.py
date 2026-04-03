"""CredentialStoreAdapter -- encrypted credential store access [F35].

MH-02: ALL API keys in CredentialStore (never in config/env/manifest).
Encrypted (AES256-GCM at rest).
Source: OS keychain / Vault / env.

Import graph (Layer 3 -- adapter)
---------------------------------
k1.model_hub.adapters.credential_store_adapter
  -> k1.model_hub.ports      (Layer 1)
  -> stdlib only (no external crypto yet)
"""

from __future__ import annotations

import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)


class CredentialStoreAdapter:
    """ICredentialPort adapter for encrypted credential store.

    Production: retrieves from OS keychain / Vault / encrypted store.
    Current: reads from environment variables (MH_KEY_<PROVIDER_ID>).

    MH-02: Keys NEVER stored in manifest YAML or config files.
    Error handling: return empty string on failure, never crash hub.
    """

    def __init__(self, key_overrides: Dict[str, str] | None = None) -> None:
        self._overrides: Dict[str, str] = key_overrides or {}

    async def get_key(self, provider_id: str) -> str:
        """Retrieve API key for a provider.

        Lookup order: overrides dict -> env MH_KEY_<PROVIDER_ID> -> empty.
        """
        try:
            if provider_id in self._overrides:
                return self._overrides[provider_id]
            env_key = f"MH_KEY_{provider_id.upper()}"
            return os.environ.get(env_key, "")
        except Exception:
            logger.exception(
                "CredentialStoreAdapter.get_key failed provider=%s",
                provider_id,
            )
            return ""

    async def refresh_key(self, provider_id: str) -> str:
        """Refresh API key (re-read from source).

        Current implementation: same as get_key (no rotation yet).
        """
        return await self.get_key(provider_id)


__all__ = ["CredentialStoreAdapter"]
