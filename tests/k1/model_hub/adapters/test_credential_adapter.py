"""TestCredentialAdapter -- test adapter for ICredentialPort [6.1.6].

Fake API keys, no encryption. For test isolation only.
"""

from __future__ import annotations

from typing import Dict, List


class TestCredentialAdapter:
    """Deterministic ICredentialPort for testing.

    Configurable:
      - keys: Dict mapping provider_id -> API key string.

    Capture:
      - get_key_calls: All provider_ids requested via get_key().
      - refresh_key_calls: All provider_ids requested via refresh_key().

    isinstance(adapter, ICredentialPort) == True.
    """

    def __init__(self, keys: Dict[str, str] | None = None) -> None:
        self._keys: Dict[str, str] = keys or {
            "openai": "sk-test-openai",
            "anthropic": "sk-test-anthropic",
            "google": "sk-test-google",
        }
        self._get_key_calls: List[str] = []
        self._refresh_key_calls: List[str] = []

    async def get_key(self, provider_id: str) -> str:
        """Return fake API key, capture call."""
        self._get_key_calls.append(provider_id)
        return self._keys.get(provider_id, "")

    async def refresh_key(self, provider_id: str) -> str:
        """Return same fake key (no rotation in tests), capture call."""
        self._refresh_key_calls.append(provider_id)
        key: str = self._keys.get(provider_id, "")
        return key

    # -- Test helpers ----------------------------------------------------------

    def set_key(self, provider_id: str, key: str) -> None:
        """Set or update a fake API key."""
        self._keys[provider_id] = key

    # -- Test inspection -------------------------------------------------------

    @property
    def get_key_calls(self) -> List[str]:
        return list(self._get_key_calls)

    @property
    def refresh_key_calls(self) -> List[str]:
        return list(self._refresh_key_calls)

    def reset(self) -> None:
        self._get_key_calls.clear()
        self._refresh_key_calls.clear()


__all__ = ["TestCredentialAdapter"]
