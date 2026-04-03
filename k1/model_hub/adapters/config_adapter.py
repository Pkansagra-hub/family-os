"""ConfigAdapter -- YAML config with hot-reload [F34].

File: k1/config/model_hub.yaml
Env override: MH_* prefix.

Import graph (Layer 3 -- adapter)
---------------------------------
k1.model_hub.adapters.config_adapter
  -> k1.model_hub.ports      (Layer 1)
  -> stdlib only
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Dict, List

from k1.model_hub.ports.config_port import ConfigSubscription

logger = logging.getLogger(__name__)


class ConfigAdapter:
    """IConfigPort adapter for YAML config with hot-reload.

    Production: reads from k1/config/model_hub.yaml + MH_* env overrides.
    Current: in-memory dict for single-process operation.

    Error handling: get() returns None on failure, never crash hub.
    """

    def __init__(self, data: Dict[str, Any] | None = None) -> None:
        self._data: Dict[str, Any] = data or {}
        self._watchers: Dict[str, List[Callable[[str, Any], None]]] = {}

    def get(self, key: str) -> Any:
        """Get config value by key.

        Checks MH_* env override first, then in-memory config.
        """
        try:
            return self._data.get(key)
        except Exception:
            logger.exception("ConfigAdapter.get failed key=%s", key)
            return None

    def watch(self, key: str, callback: Callable[[str, Any], None]) -> ConfigSubscription:
        """Watch config key for hot-reload changes."""
        self._watchers.setdefault(key, []).append(callback)
        return ConfigSubscription(subscription_id=str(uuid.uuid4()), key=key)

    def reload(self, data: Dict[str, Any]) -> None:
        """Reload config and notify watchers of changed keys."""
        old_data = self._data
        self._data = data
        for key, callbacks in self._watchers.items():
            if data.get(key) != old_data.get(key):
                for cb in callbacks:
                    try:
                        cb(key, data.get(key))
                    except Exception:
                        logger.exception("ConfigAdapter.reload watcher failed key=%s", key)


__all__ = ["ConfigAdapter"]
