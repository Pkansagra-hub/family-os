"""ConciergeConfig -- frozen, Concierge-only configuration.

Extracted from ``k1.concierge.factory`` into a dedicated config module
so that consumers can import without pulling the factory import chain.

Lives in ``k1.concierge.config.concierge`` -- the canonical location.
``k1.concierge.factory`` re-exports for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

# P3.4c: tool_tier removed; canonical tiers live in dispatcher.


@dataclass(frozen=True)
class ConciergeConfig:
    """Configuration for Concierge subsystem wiring.

    Contains ONLY fields that the Concierge factory and session need.
    Infrastructure fields (ordered_bus, capture_bus, test_mode, session_mode)
    are excluded -- those belong to KernelService.
    """

    enable_experience: bool = True
    enable_delta: bool = True
    enable_hitl: bool = True
    enable_orchestrator: bool = True
    # M16.E1.I3: see ``KernelConfig.allow_planner_passthrough``.
    allow_planner_passthrough: bool = False
    # M17.E1.I1: see ``KernelConfig.allow_dispatch_passthrough``.
    allow_dispatch_passthrough: bool = False
    auto_start_consumer: bool = True
    enable_ledger: bool = True
    # M5 G5: opt-in ledger-driven crash recovery at session create.
    # Default False to preserve cold-start semantics; flip True via
    # KernelConfig.enable_ledger_recovery for production warm-start.
    enable_ledger_recovery: bool = True
    enable_dead_letter_consumer: bool = True
    session_id: str | None = None
    seed_memories: list[dict[str, Any]] = field(default_factory=list)
    delta_batch_window_ms: int = 100
    dead_letter_enabled: bool = False
    backpool_size: int = 3
    backpool_max_concurrent_per_session: int = 2
    backpool_lease_ttl_s: float = 300.0
    backpool_reclaim_check_interval_s: float = 30.0
    backpool_enable_dependency_ordering: bool = True
    backpool_max_renewals: int = 3
    backpool_lease_grace_period_s: float = 5.0

    def __post_init__(self) -> None:
        if self.delta_batch_window_ms <= 0:
            raise ValueError(f"delta_batch_window_ms must be > 0, got {self.delta_batch_window_ms}")

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_kernel_config(cls, kc: Any) -> ConciergeConfig:
        """Create from a KernelConfig instance (backward compatibility)."""
        return cls(
            enable_experience=getattr(kc, "enable_experience", True),
            enable_delta=getattr(kc, "enable_delta", True),
            enable_hitl=getattr(kc, "enable_hitl", True),
            enable_orchestrator=getattr(kc, "enable_orchestrator", True),
            allow_planner_passthrough=getattr(kc, "allow_planner_passthrough", False),
            allow_dispatch_passthrough=getattr(kc, "allow_dispatch_passthrough", False),
            auto_start_consumer=getattr(kc, "auto_start_consumer", True),
            enable_ledger=getattr(kc, "enable_ledger", True),
            enable_ledger_recovery=getattr(kc, "enable_ledger_recovery", False),
            enable_dead_letter_consumer=getattr(kc, "enable_dead_letter_consumer", True),
            session_id=getattr(kc, "session_id", None),
            seed_memories=getattr(kc, "seed_memories", []),
            backpool_size=getattr(kc, "backpool_size", 3),
            backpool_max_concurrent_per_session=getattr(
                kc,
                "backpool_max_concurrent_per_session",
                2,
            ),
            backpool_lease_ttl_s=getattr(kc, "backpool_lease_ttl_s", 300.0),
            backpool_reclaim_check_interval_s=getattr(
                kc,
                "backpool_reclaim_check_interval_s",
                30.0,
            ),
            backpool_enable_dependency_ordering=getattr(
                kc,
                "backpool_enable_dependency_ordering",
                True,
            ),
            backpool_max_renewals=getattr(kc, "backpool_max_renewals", 3),
            backpool_lease_grace_period_s=getattr(kc, "backpool_lease_grace_period_s", 5.0),
        )

    # Alias for plan naming convention
    from_legacy = from_kernel_config

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConciergeConfig:
        """Create from a plain dict (e.g. deserialized JSON/YAML)."""
        # Only pass keys that are valid fields to avoid TypeError
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid}
        return cls(**filtered)

    @classmethod
    def for_testing(cls, **overrides: Any) -> ConciergeConfig:
        """Minimal config for tests -- all optional subsystems disabled."""
        defaults: dict[str, Any] = {
            "enable_experience": False,
            "enable_delta": False,
            "enable_hitl": False,
            "enable_orchestrator": False,
            # M16.E1.I3: tests boot without an orchestrator, so allow
            # the legacy PassthroughPlannerStub fallback by default.
            "allow_planner_passthrough": True,
            "enable_ledger": False,
            "enable_dead_letter_consumer": False,
            "auto_start_consumer": False,
        }
        defaults.update(overrides)
        return cls(**defaults)

    # ------------------------------------------------------------------
    # Immutable override
    # ------------------------------------------------------------------

    def with_overrides(self, **kwargs: Any) -> ConciergeConfig:
        """Return a new frozen instance with selected fields replaced."""
        return replace(self, **kwargs)
