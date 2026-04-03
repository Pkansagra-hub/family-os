"""IConfigPort -- configuration access [F14].

Read hub config with optional watch for hot-reload.

Import graph (Layer 1)
----------------------
k1.model_hub.ports.config_port
  -> stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConfigSubscription:
    """Config watch subscription handle."""

    subscription_id: str
    key: str


@runtime_checkable
class IConfigPort(Protocol):
    """Configuration access port.

    Keys: budgets, timeouts, placement rules.
    Provider config: from manifests (not here).
    """

    def get(self, key: str) -> Any:
        """Get a config value by key."""
        ...

    def watch(self, key: str, callback: Callable[[str, Any], None]) -> ConfigSubscription:
        """Watch a config key for changes, calling callback on update."""
        ...


__all__ = ["IConfigPort", "ConfigSubscription"]
