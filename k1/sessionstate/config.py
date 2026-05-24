"""
SessionState Configuration — Constructor-Injected Config
=========================================================

Replaces runtime ``get_config().sessionstate.*`` calls with a single
``SessionStateConfig`` dataclass injected at construction time.

All defaults match the values previously in ``poc.k1_poc.config.loader``
(``defaults.yaml``).  Components receive the relevant sub-config via
their constructors instead of reaching into a global singleton.

Issue: P4.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# ---------------------------------------------------------------------------
# Sub-configs (mirror the POC ``sessionstate.*`` subtree)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TiersConfig:
    total_size_limit_bytes: int = 110_592
    hot_budget_bytes: int = 57_344
    warm_budget_bytes: int = 49_152
    normal_threshold_pct: float = 0.8
    elevated_threshold_pct: float = 0.9
    critical_threshold_pct: float = 0.95

    hot_section_budgets: Dict[str, int] = field(
        default_factory=lambda: {
            "control": 8192,
            "beliefs_active": 8192,
            "scoreboard": 6144,
            "history_active": 8192,
            "clarifications": 4096,
            "affective_now": 4096,
            "narrative_active": 4096,
            "meta": 2048,
            "task_state": 4096,
            "task_artifacts": 4096,
            "temporal": 4096,
        }
    )

    warm_section_budgets: Dict[str, int] = field(
        default_factory=lambda: {
            "telemetry": 8192,
            "beliefs_history": 12_288,
            "history_recent": 20_480,
            "persona": 8192,
            "artifacts_warm": 8192,
        }
    )


@dataclass(frozen=True)
class EvictionConfig:
    target_utilization: float = 0.70
    min_eviction_bytes: int = 1024
    max_eviction_iterations: int = 10


@dataclass(frozen=True)
class MigrationConfig:
    max_history_active_turns: int = 10
    compression_turn_threshold: int = 30
    target_hot_utilization: float = 0.70
    min_demote_bytes: int = 1024
    max_demote_iterations: int = 10


@dataclass(frozen=True)
class ThrashConfig:
    mild_migrations: int = 5
    mild_evictions: int = 2
    moderate_migrations: int = 10
    moderate_evictions: int = 5
    severe_migrations: int = 20
    severe_evictions: int = 10
    window_ms: int = 60_000


@dataclass(frozen=True)
class ReconstructionConfig:
    sla_local_cold_ms: float = 50.0
    sla_k0_fallback_ms: float = 100.0
    k0_timeout_ms: float = 80.0
    estimate_local_cold_base_ms: float = 5.0
    estimate_local_cold_per_kb_ms: float = 0.5
    estimate_k0_base_ms: float = 30.0
    estimate_k0_per_kb_ms: float = 1.0


@dataclass(frozen=True)
class ColdConfig:
    default_max_age_days: int = 30
    restore_sla_ms: float = 50.0


@dataclass(frozen=True)
class StorageConfig:
    default_db_path: str = "~/.familyos/k1/sessionstate.db"
    checkpoint_interval_s: float = 30.0
    sla_restore_ms: float = 50.0
    sla_storage_ms: float = 50.0


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionStateConfig:
    """All tuning knobs for the SessionState subsystem."""

    tiers: TiersConfig = field(default_factory=TiersConfig)
    eviction: EvictionConfig = field(default_factory=EvictionConfig)
    migration: MigrationConfig = field(default_factory=MigrationConfig)
    thrash: ThrashConfig = field(default_factory=ThrashConfig)
    reconstruction: ReconstructionConfig = field(default_factory=ReconstructionConfig)
    cold: ColdConfig = field(default_factory=ColdConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)

    flatbuffer_overhead_factor: float = 1.1
    llm_writable_sections: List[str] = field(
        default_factory=lambda: [
            "beliefs_active",
            "scoreboard",
            "clarifications",
            "narrative_active",
            "affective_now",
        ]
    )
