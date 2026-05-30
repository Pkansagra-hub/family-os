"""Health payloads for the grounding service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingHealthStatus:
    """Readiness snapshot for grounding runtime wiring."""

    ready: bool
    temporal_connected: bool
    spatial_connected: bool
    state_connected: bool
    identity_connected: bool
    policy_connected: bool
    event_connected: bool


__all__ = ["GroundingHealthStatus"]
