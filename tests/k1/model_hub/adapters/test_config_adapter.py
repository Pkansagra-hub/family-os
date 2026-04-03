"""TestConfigAdapter -- test adapter for IConfigPort [6.1.5].

In-memory config with overridable keys and watch support.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List

from k1.model_hub.ports.config_port import ConfigSubscription


class TestConfigAdapter:
    """Deterministic IConfigPort for testing.

    Configurable:
      - Pre-load key/value pairs via constructor or set().

    Capture:
      - get_calls: All keys requested via get().
      - watch_calls: All keys watched via watch().

    isinstance(adapter, IConfigPort) == True.
    """

    def __init__(self, data: Dict[str, Any] | None = None) -> None:
        self._data: Dict[str, Any] = data or {}
        self._watchers: Dict[str, List[Callable[[str, Any], None]]] = {}
        self._get_calls: List[str] = []
        self._watch_calls: List[str] = []

    def get(self, key: str) -> Any:
        """Return in-memory config value, capture call."""
        self._get_calls.append(key)
        return self._data.get(key)

    def watch(self, key: str, callback: Callable[[str, Any], None]) -> ConfigSubscription:
        """Register watcher for config key changes."""
        self._watch_calls.append(key)
        self._watchers.setdefault(key, []).append(callback)
        return ConfigSubscription(subscription_id=str(uuid.uuid4()), key=key)

    # -- Test helpers ----------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        """Set config value and notify watchers."""
        self._data[key] = value
        for cb in self._watchers.get(key, []):
            cb(key, value)

    # -- Test inspection -------------------------------------------------------

    @property
    def get_calls(self) -> List[str]:
        return list(self._get_calls)

    @property
    def watch_calls(self) -> List[str]:
        return list(self._watch_calls)

    def reset(self) -> None:
        self._get_calls.clear()
        self._watch_calls.clear()
        self._watchers.clear()


__all__ = ["TestConfigAdapter"]
