"""Spatial SessionState boundary."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class ISpatialStatePort(Protocol):
    """Read/write spatial and place-registry SessionState projections."""

    async def write_spatial_section(self, session_id: str, payload: Mapping[str, Any]) -> None:
        """Write the canonical HOT spatial section."""
        ...  # pragma: no cover

    async def read_spatial_section(self, session_id: str) -> Mapping[str, Any] | None:
        """Read the HOT spatial section if present."""
        ...  # pragma: no cover

    async def write_place_registry_section(
        self, session_id: str, payload: Mapping[str, Any]
    ) -> None:
        """Write the WARM place registry projection."""
        ...  # pragma: no cover

    async def read_place_registry_section(self, session_id: str) -> Mapping[str, Any] | None:
        """Read the WARM place registry projection if present."""
        ...  # pragma: no cover


__all__ = ["ISpatialStatePort"]
