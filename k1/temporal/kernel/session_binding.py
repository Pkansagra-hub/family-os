"""Immutable per-session temporal binding metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalSessionBinding:
    """Identifiers used by a TemporalHandle for one session."""

    session_id: str
    principal_id: str | None = None
    device_id: str | None = None
    installation_id: str | None = None


__all__ = ["TemporalSessionBinding"]
