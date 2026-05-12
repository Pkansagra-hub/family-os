"""FabricRegistryAdapter -- production exact-name capability lookup [P03 fix].

Implements ``IFabricRegistryPort`` by wrapping a Fabric registry
object that exposes a synchronous ``lookup(name, version=...)`` method
(``CapabilityRegistryAPI`` or the public ``Fabric`` facade itself --
both expose the same surface, see ``k1/fabric/fabric.py:1483, 1632``).

The wrapped call is in-process and documented as <5ms, so we expose it
through an async signature without offloading -- consistent with the
rest of the planner port surface.

Import graph (Layer 2)
----------------------
k1.planner.adapters.fabric_registry_adapter
  -> k1.planner.ports.fabric_registry_port  (IFabricRegistryPort)
  -> typing, logging
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class _RegistryLookupLike(Protocol):
    """Structural protocol for the wrapped registry object.

    Both ``Fabric`` and ``CapabilityRegistryAPI`` satisfy this.
    """

    def lookup(self, name: str, *, version: Optional[str] = None) -> Any: ...


class FabricRegistryAdapter:
    """Production capability-registry adapter (exact-name O(1) lookup)."""

    __slots__ = ("_registry",)

    def __init__(self, registry: _RegistryLookupLike) -> None:
        if registry is None:
            raise TypeError("registry must not be None")
        if not hasattr(registry, "lookup"):
            raise TypeError(
                "registry must expose a synchronous lookup(name, *, version) method; "
                f"got {type(registry).__name__}"
            )
        self._registry = registry

    async def lookup(
        self,
        name: str,
        *,
        version: Optional[str] = None,
    ) -> Any:
        """Return the capability contract for ``(name, version)``, or None."""
        try:
            return self._registry.lookup(name, version=version)
        except Exception:
            logger.exception(
                "fabric_registry.lookup_failed",
                extra={"capability_name": name, "version": version},
            )
            return None


__all__ = ["FabricRegistryAdapter"]
