"""Model Hub configuration [F02].

Frozen config dataclass with validation and factory methods.

Import graph (Layer 0 -- no internal deps)
------------------------------------------
k1.model_hub.config
  -> stdlib only

NEVER import from any service, port, adapter, or plugin module.

References
----------
- model_hub.mmd: Config section
- ADR-0001b: Model Hub Architecture
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ModelHubConfig:
    """Model Hub configuration (frozen, validated).

    Invariants:
      MH-09: cache_ttl_s default 300s (5min).
      MH-12: rate_limit_headroom_pct default 0.80 (80%).
      MH-14: health_check_interval_s default 30s.
      MH-15: timeout defaults per priority tier.
    """

    # Concurrency
    max_concurrent_requests: int = 50

    # Cache (MH-09)
    cache_max_entries: int = 1000
    cache_ttl_s: int = 300

    # Timeouts per priority tier (MH-15)
    realtime_timeout_ms: int = 10000
    interactive_timeout_ms: int = 30000
    background_timeout_ms: int = 60000

    # Rate limiting (MH-12)
    rate_limit_headroom_pct: float = 0.80

    # Health (MH-14)
    health_check_interval_s: int = 30

    # Manifest
    manifest_dir: str = "k1/config/providers"

    # Shutdown
    shutdown_grace_period_ms: int = 10000

    # Budget (MH-10)
    daily_budget_usd: float = 5.0
    monthly_budget_usd: float = 100.0

    def __post_init__(self) -> None:
        if self.max_concurrent_requests <= 0:
            raise ValueError(
                f"max_concurrent_requests must be > 0, got {self.max_concurrent_requests}"
            )
        if self.cache_max_entries <= 0:
            raise ValueError(f"cache_max_entries must be > 0, got {self.cache_max_entries}")
        if self.cache_ttl_s <= 0:
            raise ValueError(f"cache_ttl_s must be > 0, got {self.cache_ttl_s}")
        if self.realtime_timeout_ms <= 0:
            raise ValueError(f"realtime_timeout_ms must be > 0, got {self.realtime_timeout_ms}")
        if self.interactive_timeout_ms <= 0:
            raise ValueError(
                f"interactive_timeout_ms must be > 0, got {self.interactive_timeout_ms}"
            )
        if self.background_timeout_ms <= 0:
            raise ValueError(f"background_timeout_ms must be > 0, got {self.background_timeout_ms}")
        if not 0.0 < self.rate_limit_headroom_pct <= 1.0:
            raise ValueError(
                f"rate_limit_headroom_pct must be in (0.0, 1.0], got {self.rate_limit_headroom_pct}"
            )
        if self.health_check_interval_s <= 0:
            raise ValueError(
                f"health_check_interval_s must be > 0, got {self.health_check_interval_s}"
            )
        if self.shutdown_grace_period_ms <= 0:
            raise ValueError(
                f"shutdown_grace_period_ms must be > 0, got {self.shutdown_grace_period_ms}"
            )
        if self.daily_budget_usd <= 0:
            raise ValueError(f"daily_budget_usd must be > 0, got {self.daily_budget_usd}")
        if self.monthly_budget_usd <= 0:
            raise ValueError(f"monthly_budget_usd must be > 0, got {self.monthly_budget_usd}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelHubConfig:
        """Create config from dictionary.

        Raises ValueError on unknown keys.
        """
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        unknown = set(data.keys()) - valid_keys
        if unknown:
            raise ValueError(f"Unknown config keys: {unknown}")
        return cls(**data)


__all__ = [
    "ModelHubConfig",
]
