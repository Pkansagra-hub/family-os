"""Configuration for the k1.grounding kernel module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingConfig:
    """Static policy for envelope freshness, leases, and projection defaults."""

    envelope_ttl_ms: int = 60_000
    agent_lease_ttl_seconds: int = 900
    raw_spatial_allowed_by_default: bool = False
    default_consumer: str = "front"
