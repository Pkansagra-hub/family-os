"""Immutable per-session spatial binding metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpatialSessionBinding:
    """Identifiers used by a SpatialHandle for one session."""

    session_id: str
    principal_id: str | None = None
    actor_id: str | None = None
    device_id: str | None = None
    installation_id: str | None = None


__all__ = ["SpatialSessionBinding"]
