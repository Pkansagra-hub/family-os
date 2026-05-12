"""IFabricRegistryPort -- Planner capability *registry* protocol [P03 fix].

Distinct from ``IFabricRetrievalPort`` (semantic discovery / 4-stage
ranking). This port exposes the deterministic O(1) registry lookup
exposed by ``Fabric.registry_api.lookup(name, version=...)``.

Why a separate port?
--------------------
``ToolCallRouter.get_schema(capability_name)`` is meant to be a fast,
deterministic exact-name lookup used by EXPAND (SS11.2). Using
``IFabricRetrievalPort.discover_capabilities(intent=name, top_k=1)``
as a stand-in works only as long as the capability name happens to
embed in a unique embedding -- otherwise EXPAND silently picks a
similar-but-wrong capability. This port closes that hole.

PLAN-06 enforcement
-------------------
This port exposes ``lookup()`` ONLY. There is no execution path on
this interface.

Adapter: ``FabricRegistryAdapter`` (k1.planner.adapters.fabric_registry_adapter).

Import graph (Layer 1)
----------------------
k1.planner.ports.fabric_registry_port
  -> typing
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class IFabricRegistryPort(Protocol):
    """Read-only Fabric capability registry port (exact-name lookup).

    Structural protocol (``typing.Protocol``). Any object with a
    matching async ``lookup`` signature satisfies it.
    """

    async def lookup(
        self,
        name: str,
        *,
        version: Optional[str] = None,
    ) -> Any:
        """Return the capability contract registered under ``name``.

        Args:
            name: Canonical capability name (exact match, no fuzzy).
            version: Optional exact version string (e.g. ``"2.1.0"``).
                When ``None``, the latest registered version is returned.

        Returns:
            The capability contract object, or ``None`` if no contract
            is registered under that ``(name, version)`` pair.
        """
        ...  # pragma: no cover


__all__ = ["IFabricRegistryPort"]
