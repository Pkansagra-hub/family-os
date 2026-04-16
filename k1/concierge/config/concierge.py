"""ConciergeConfig -- frozen, Concierge-only configuration.

Extracted from ``k1.concierge.factory`` into a dedicated config module
so that consumers can import without pulling the factory import chain.

Lives in ``k1.concierge.config.concierge`` -- the canonical location.
``k1.concierge.factory`` re-exports for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

_VALID_TOOL_TIERS = frozenset({"LOW", "MED", "HIGH"})
_VALID_PHASE1_PIPELINES = frozenset({"stub", "ultrabert"})


@dataclass(frozen=True)
class ConciergeConfig:
    """Configuration for Concierge subsystem wiring.

    Contains ONLY fields that the Concierge factory and session need.
    Infrastructure fields (ordered_bus, capture_bus, test_mode, session_mode)
    are excluded -- those belong to KernelService.
    """

    tool_tier: str = "LOW"
    enable_experience: bool = True
    enable_delta: bool = True
    enable_hitl: bool = True
    enable_orchestrator: bool = True
    auto_start_consumer: bool = True
    enable_ledger: bool = True
    enable_dead_letter_consumer: bool = True
    session_id: str | None = None
    seed_memories: list[dict[str, Any]] = field(default_factory=list)
    phase1_pipeline: str = "stub"
    phase1_warmup: bool = False
    delta_batch_window_ms: int = 100
    dead_letter_enabled: bool = False

    def __post_init__(self) -> None:
        if self.tool_tier not in _VALID_TOOL_TIERS:
            raise ValueError(
                f"tool_tier must be one of {sorted(_VALID_TOOL_TIERS)}, got {self.tool_tier!r}"
            )
        if self.delta_batch_window_ms <= 0:
            raise ValueError(f"delta_batch_window_ms must be > 0, got {self.delta_batch_window_ms}")
        if self.phase1_pipeline not in _VALID_PHASE1_PIPELINES:
            raise ValueError(
                f"phase1_pipeline must be one of {sorted(_VALID_PHASE1_PIPELINES)}, "
                f"got {self.phase1_pipeline!r}"
            )

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_kernel_config(cls, kc: Any) -> ConciergeConfig:
        """Create from a KernelConfig instance (backward compatibility)."""
        return cls(
            tool_tier=getattr(kc, "tool_tier", "LOW"),
            enable_experience=getattr(kc, "enable_experience", True),
            enable_delta=getattr(kc, "enable_delta", True),
            enable_hitl=getattr(kc, "enable_hitl", True),
            enable_orchestrator=getattr(kc, "enable_orchestrator", True),
            auto_start_consumer=getattr(kc, "auto_start_consumer", True),
            enable_ledger=getattr(kc, "enable_ledger", True),
            enable_dead_letter_consumer=getattr(kc, "enable_dead_letter_consumer", True),
            session_id=getattr(kc, "session_id", None),
            seed_memories=getattr(kc, "seed_memories", []),
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
