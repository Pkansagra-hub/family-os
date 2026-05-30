"""Temporal service health model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalHealthStatus:
    """Lightweight health status for TemporalService."""

    ready: bool
    state_connected: bool
    device_context_connected: bool
    event_connected: bool


__all__ = ["TemporalHealthStatus"]
