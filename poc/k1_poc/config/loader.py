"""
poc.k1_poc.config.loader -- YAML-based central configuration loader.

Loads POC knobs from ``defaults.yaml`` with optional per-environment
override files.  All values are exposed through typed dataclass trees
so call-sites get IDE completion and static-analysis safety.

Usage::

    from poc.k1_poc.config import get_config
    cfg = get_config()                          # singleton, loads once
    cfg.actors.back.history_window              # -> 5
    cfg.bus.mailbox_capacity                    # -> 64
    cfg.delta.batch_window_ms                   # -> 500

Override at startup::

    from poc.k1_poc.config import load_config
    cfg = load_config("path/to/override.yaml")  # replaces singleton
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULTS_PATH = Path(__file__).parent / "defaults.yaml"


# =========================================================================
# Typed dataclass tree
# =========================================================================


@dataclass
class BackActorConfig:
    """Knobs from actors/back.py."""

    max_iterations: dict[str, int] = field(
        default_factory=lambda: {"LOW": 4, "MEDIUM": 8, "HIGH": 12}
    )
    budget_floor: int = 2
    history_window: int = 5
    default_safety_band: str = "AMBER"
    hitl_timeout_s: int = 60
    summarize_args_max_len: int = 200
    summarize_result_max_len: int = 500
    sensitive_keys: list[str] = field(
        default_factory=lambda: [
            "session_id",
            "payment",
            "credential",
            "password",
            "token",
        ]
    )


@dataclass
class FrontActorConfig:
    """Knobs from actors/front.py."""

    history_window_fallback: int = 20
    default_tier: str = "LOW"
    default_affect_confidence: float = 1.0
    default_fsm_state: str = "DISPATCHING"


@dataclass
class ActorsConfig:
    back: BackActorConfig = field(default_factory=BackActorConfig)
    front: FrontActorConfig = field(default_factory=FrontActorConfig)
    back_pool: "BackPoolConfig" = field(default_factory=lambda: BackPoolConfig())


@dataclass
class BusConfig:
    """Knobs from bus/setup.py."""

    mailbox_capacity: int = 64
    gap_timeout_ms: int = 5000
    actor_front_id: str = "front_half"
    actor_back_id: str = "back_half"
    priority_wfq: bool = True
    # M1 E1.3: Validate canonical event payloads in builders (off in prod, on in tests)
    validate_canonical_events: bool = False


@dataclass
class OverflowConfig:
    """Knobs from delta/overflow.py."""

    hot_budget_total: int = 53248
    history_window_size: int = 20
    section_budgets: dict[str, int] = field(
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
        }
    )


@dataclass
class DeltaConfig:
    """Knobs from delta/aggregator.py + delta/overflow.py."""

    batch_window_ms: int = 500
    overflow: OverflowConfig = field(default_factory=OverflowConfig)


@dataclass
class ExperienceConfig:
    """Knobs from experience/layer.py."""

    emotional_processor_cadence: int = 25
    narrative_weaver_cadence: int = 20
    anticipatory_responder_cadence: int = 30
    ep_skip_confidence_threshold: float = 0.8
    proactive_wait_threshold_ms: int = 5000


@dataclass
class FsmConfig:
    """Knobs from fsm/front_lock.py, history_writer.py, task_bridge.py, interrupt_handler.py."""

    front_lock_max_queue_depth: int = 8
    front_history_window: int = 20
    back_history_window: int = 5
    prune_completed_after_turns: int = 10
    evict_artifacts_after_turns: int = 10
    cancel_keywords: list[str] = field(
        default_factory=lambda: [
            "cancel",
            "stop",
            "abort",
            "nevermind",
            "never mind",
            "don't bother",
            "forget it",
            "skip it",
            "call it off",
        ]
    )
    # M2: FSM hardening additions
    pending_results_max_depth: int = 16
    pending_results_ttl_seconds: int = 300
    dead_letter_enabled: bool = True
    idempotency_ledger_max_entries: int = 500


@dataclass
class KernelConfig:
    """Knobs from kernel/bootstrap.py."""

    poll_interval_s: float = 0.05
    dedup_cache_size: int = 4096


@dataclass
class LlmConfig:
    """Knobs from llm/model_selection.py, llm/gemini_adapter.py, llm/types.py."""

    default_model: str = "gemini-2.5-flash"
    batch_max_concurrency: int = 5
    default_max_tokens: int = 4096
    default_timeout_ms: int = 30_000
    default_temperature: float = 1.0
    model_hint_overrides: dict[str, str] = field(
        default_factory=lambda: {
            "fast": "gemini-2.5-flash",
            "smart": "gemini-2.5-pro",
            "cheap": "gemini-2.5-flash",
            "thinking": "gemini-2.5-flash",
            "pro": "gemini-2.5-pro",
            "flash": "gemini-2.5-flash",
        }
    )
    model_selection_table: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "CHAT": {"front": "gemini-2.5-flash", "back": "gemini-2.5-flash"},
            "TOOL_CALL": {
                "front": "gemini-2.5-pro",
                "back": "gemini-2.5-pro",
                "planner": "gemini-2.5-pro",
            },
            "STRUCTURED": {"front": "gemini-2.5-flash", "back": "gemini-2.5-flash"},
            "REASON": {"front": "gemini-2.5-pro", "back": "gemini-2.5-pro"},
            "STREAM": {"front": "gemini-2.5-flash"},
        }
    )


@dataclass
class OrchestratorConfig:
    """Knobs from orchestrator/routing.py, orchestrator/degradation.py, orchestrator/types.py."""

    tier_fabric_budget: dict[str, int] = field(
        default_factory=lambda: {"LOW": 1, "MEDIUM": 2, "HIGH": 10}
    )
    tier_planner_token_budget: dict[str, int] = field(
        default_factory=lambda: {"LOW": 0, "MEDIUM": 0, "HIGH": 3500}
    )
    default_budget_timeout_ms: int = 60_000
    canned_response_text: str = "I'm having trouble right now. Could you try again in a moment?"


@dataclass
class PromptConfig:
    """Knobs from prompt/builder.py, prompt/mode.py, prompt/clarify_depth.py."""

    context_window: int = 128_000
    safety_margin: float = 0.80
    chars_per_token: int = 4
    max_iterations: dict[str, int] = field(
        default_factory=lambda: {
            "STANDARD": 6,
            "CLARIFY_ASK": 3,
            "CLARIFY_RESOLVE": 5,
            "HITL_RELAY": 1,
            "HITL_RESOLVE": 3,
            "PRESENT": 3,
            "WEAVE": 3,
            "CANCEL": 3,
            "INTERRUPT": 6,
            "ERROR": 2,
        }
    )
    crisis_iterations: dict[str, int] = field(
        default_factory=lambda: {
            "STANDARD": 4,
            "CLARIFY_ASK": 2,
            "CLARIFY_RESOLVE": 4,
            "HITL_RELAY": 1,
            "HITL_RESOLVE": 2,
            "PRESENT": 2,
            "WEAVE": 2,
            "CANCEL": 2,
            "INTERRUPT": 4,
            "ERROR": 2,
        }
    )
    affect_confidence_threshold: float = 0.6
    max_clarify_depth: int = 2
    back_max_tool_calls: int = 5


@dataclass
class ProtocolsConfig:
    """Knobs from protocols/suspension.py, protocols/hitl.py, protocols/weave_batcher.py."""

    max_suspensions_per_task: int = 2
    max_concurrent_suspensions: int = 1
    suspension_timeouts: dict[str, float] = field(
        default_factory=lambda: {
            "clarification": 60.0,
            "approval": 120.0,
            "selection": 90.0,
        }
    )
    hil_timeouts: dict[str, int] = field(
        default_factory=lambda: {
            "clarification": 60_000,
            "approval": 120_000,
            "selection": 90_000,
        }
    )
    weave_batch_window_ms: int = 500
    # M2: Max queued depth for weave batcher
    weave_max_queued_depth: int = 16


@dataclass
class ReactConfig:
    """Knobs from react/loop.py."""

    default_front_max_iterations: int = 6
    default_back_max_iterations: int = 10
    front_degenerate_fallback: str = "Let me think about that for a moment."
    front_budget_fallback: str = "Let me get back to you on that."
    parallel_tools_enabled: bool = True


@dataclass
class TaskConfig:
    """Knobs from task/complexity.py."""

    tier_budget: dict[str, int] = field(default_factory=lambda: {"LOW": 4, "MEDIUM": 8, "HIGH": 12})


@dataclass
class ToolsConfig:
    """Knobs from tools/dispatcher.py."""

    budget_limits: dict[str, int] = field(
        default_factory=lambda: {"LOW": 5, "MEDIUM": 10, "HIGH": 20, "CRISIS": 3}
    )


# =========================================================================
# M7: BackPool config
# =========================================================================


@dataclass
class BackPoolConfig:
    """Knobs from actors/back_pool.py (M7: BackPool + Task Lease Model)."""

    pool_size: int = 3
    max_concurrent_per_session: int = 2
    lease_ttl_s: float = 300.0
    reclaim_check_interval_s: float = 30.0
    enable_dependency_ordering: bool = True
    lease_renewal_extension_s: float = 60.0
    max_lease_renewals: int = 3
    grace_period_s: float = 5.0


# =========================================================================
# M5: Arbiter config
# =========================================================================


@dataclass
class ArbiterConfig:
    """Knobs from fsm/arbiter.py (M5: Conversation Arbiter)."""

    domain_overlap_threshold: float = 0.7
    entity_overlap_threshold: float = 0.5
    high_impact_confirmation_required: bool = True
    high_impact_actions: list[str] = field(
        default_factory=lambda: ["booking", "payment", "deletion", "send_message"]
    )
    cancel_keywords: list[str] = field(
        default_factory=lambda: [
            "cancel",
            "stop",
            "abort",
            "nevermind",
            "never mind",
            "don't bother",
            "forget it",
            "skip it",
            "call it off",
        ]
    )
    defer_keywords: list[str] = field(
        default_factory=lambda: [
            "ok",
            "okay",
            "sure",
            "keep going",
            "i'll wait",
            "no rush",
            "take your time",
            "sounds good",
            "got it",
            "alright",
            "fine",
            "go ahead",
            "continue",
            "carry on",
        ]
    )


# =========================================================================
# M8: Weave Policy config
# =========================================================================


@dataclass
class WeavePolicyConfig:
    """Knobs from protocols/weave_policy.py (M8: Adaptive Weave Policy)."""

    enabled: bool = True
    idle_eager_ms: int = 10_000
    idle_batch_ms: int = 3_000
    typing_suppress_ms: int = 500
    digest_threshold_count: int = 3
    digest_window_ms: int = 15_000
    pool_pressure_threshold: float = 0.8
    pool_pressure_batch_ms: int = 2_000
    default_batch_ms: int = 500
    max_batch_ms: int = 5_000
    emotional_suppress_valence: float = -0.5
    max_consecutive_defers: int = 5


# =========================================================================
# M9: Ledger config
# =========================================================================


@dataclass
class LedgerConfig:
    """Knobs for ledger/ (M9: Protocol Lifecycle Migration)."""

    max_events_per_session: int = 10_000
    compaction_threshold: int = 1_000
    crash_recovery_timeout_s: float = 30.0


# =========================================================================
# M10: Phase 1 / UltraBERT config
# =========================================================================


@dataclass
class Phase1Config:
    """Knobs from fsm/ultrabert_phase1.py (M10: UltraBERT Integration)."""

    pipeline: str = "stub"  # "ultrabert" | "stub" -- default stub for tests
    intent_confidence_threshold: float = 0.3
    complexity_thresholds: dict[str, int] = field(
        default_factory=lambda: {"low_max": 0, "medium_max": 2}
    )
    degradation_fallback_enabled: bool = True
    warmup_on_startup: bool = True
    cache_size: int = 64
    cache_ttl_s: float = 30.0
    target_latency_ms: int = 25


# =========================================================================
# M11: Observability config
# =========================================================================


@dataclass
class ObsMetricsConfig:
    """Metrics emission knobs (M11 11.1)."""

    enabled: bool = True
    window_size_s: float = 300.0
    emit_interval_s: float = 10.0


@dataclass
class ObsAlertRuleConfig:
    """A single alert threshold rule (M11 11.5.2)."""

    name: str = ""
    metric: str = ""
    condition: str = ""  # rate_gt, p95_gt, count_gt, gauge_gt
    threshold: float = 0.0
    window_s: float = 300.0
    severity: str = "warning"  # info, warning, critical
    cooldown_s: float = 600.0
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class ObsAlertsConfig:
    """Alert engine knobs (M11 11.5)."""

    enabled: bool = True
    evaluation_interval_s: float = 10.0
    default_cooldown_s: float = 600.0
    rules: list[ObsAlertRuleConfig] = field(default_factory=list)


@dataclass
class ObsFsmConfig:
    """FSM observability knobs (M11 11.3.1)."""

    stuck_state_thresholds: dict[str, int] = field(
        default_factory=lambda: {"COMPANIONING": 120, "CLARIFYING_WORKER": 300}
    )


@dataclass
class ObsConfig:
    """Root observability config (M11: Observability & Telemetry)."""

    metrics: ObsMetricsConfig = field(default_factory=ObsMetricsConfig)
    alerts: ObsAlertsConfig = field(default_factory=ObsAlertsConfig)
    fsm: ObsFsmConfig = field(default_factory=ObsFsmConfig)


# =========================================================================
# SessionState config tree
# =========================================================================


@dataclass
class SessionStateTiersConfig:
    """Tier budgets and pressure thresholds from sizetracker, tiers/hot, tiers/warm."""

    total_size_limit_bytes: int = 106496
    hot_budget_bytes: int = 53248
    warm_budget_bytes: int = 49152
    normal_threshold_pct: float = 0.80
    elevated_threshold_pct: float = 0.90
    critical_threshold_pct: float = 0.95
    hot_section_budgets: dict[str, int] = field(
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
        }
    )
    warm_section_budgets: dict[str, int] = field(
        default_factory=lambda: {
            "telemetry": 8192,
            "beliefs_history": 12288,
            "history_recent": 20480,
            "persona": 8192,
            "artifacts_warm": 8192,
        }
    )


@dataclass
class EvictionConfig:
    """Knobs from sessionstate/eviction.py."""

    target_utilization: float = 0.70
    min_eviction_bytes: int = 1024
    max_eviction_iterations: int = 10


@dataclass
class MigrationConfig:
    """Knobs from sessionstate/migration.py."""

    max_history_active_turns: int = 10
    compression_turn_threshold: int = 30
    target_hot_utilization: float = 0.70
    min_demote_bytes: int = 1024
    max_demote_iterations: int = 10


@dataclass
class ThrashConfig:
    """Knobs from sessionstate/snapshot.py thrash detection."""

    mild_migrations: int = 5
    mild_evictions: int = 2
    moderate_migrations: int = 10
    moderate_evictions: int = 5
    severe_migrations: int = 20
    severe_evictions: int = 10
    window_ms: int = 60_000


@dataclass
class ReconstructionConfig:
    """Knobs from sessionstate/reconstruction.py."""

    sla_local_cold_ms: float = 50.0
    sla_k0_fallback_ms: float = 100.0
    k0_timeout_ms: float = 80.0
    estimate_local_cold_base_ms: float = 5.0
    estimate_local_cold_per_kb_ms: float = 0.5
    estimate_k0_base_ms: float = 30.0
    estimate_k0_per_kb_ms: float = 1.0


@dataclass
class StorageConfig:
    """Knobs from factory.py, local_cold.py, adapters/sqlite_storage.py."""

    default_db_path: str = "~/.familyos/k1/sessionstate.db"
    checkpoint_interval_s: float = 30.0
    sla_restore_ms: float = 50.0
    sla_storage_ms: float = 50.0


@dataclass
class ColdTierConfig:
    """Knobs from tiers/local_cold.py."""

    default_max_age_days: int = 30
    restore_sla_ms: float = 50.0


@dataclass
class SectionConfig:
    """Generic per-section config (budget + optional extra knobs)."""

    budget_bytes: int = 0
    # Optional per-section fields stored as a flat dict for flexibility
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionStateSectionsConfig:
    """Per-section knobs for all 15 session state sections."""

    history_active_budget_bytes: int = 16384
    history_active_max_turns: int = 25

    history_recent_budget_bytes: int = 20480
    history_recent_eviction_priority: int = 3
    history_recent_max_compressed_turns: int = 20
    history_recent_max_summarized_turns: int = 10
    history_recent_max_session_summary_chars: int = 200
    history_recent_compressed_start: int = 11
    history_recent_compressed_end: int = 30
    history_recent_summarized_start: int = 31
    history_recent_summarized_end: int = 40

    scoreboard_budget_bytes: int = 6144
    scoreboard_default_decay_rate: float = 0.1
    scoreboard_min_salience: float = 0.01

    narrative_active_budget_bytes: int = 4096
    narrative_active_max_paused_threads: int = 5
    narrative_active_default_resumption_template: str = "Earlier, you were discussing {title}."

    telemetry_budget_bytes: int = 8192
    telemetry_eviction_priority: int = 1
    telemetry_max_turn_timings: int = 20
    telemetry_max_latency_samples: int = 100
    telemetry_latency_sla_p95_ms: int = 500

    task_state_budget_bytes: int = 4096
    task_state_max_tasks: int = 20

    task_artifacts_budget_bytes: int = 4096
    task_artifacts_max_artifacts: int = 30

    beliefs_active_budget_bytes: int = 8192
    beliefs_active_max_facts: int = 50

    beliefs_history_budget_bytes: int = 12288
    beliefs_history_eviction_priority: int = 2
    beliefs_history_max_facts: int = 100

    clarifications_budget_bytes: int = 4096
    clarifications_max_pending: int = 20
    clarifications_max_recently_resolved: int = 5

    affective_now_budget_bytes: int = 4096
    affective_now_max_recent_emotions: int = 5
    affective_now_significant_change_threshold: float = 0.3

    control_budget_bytes: int = 8192
    control_default_lease_ttl_ms: int = 30_000
    control_flow_timeout_ms: int = 60_000
    control_lock_timeout_ms: int = 30_000

    meta_budget_bytes: int = 2048
    meta_idle_timeout_ms: int = 3_600_000
    meta_max_lifetime_ms: int = 86_400_000

    persona_budget_bytes: int = 8192
    persona_eviction_priority: int = 4
    persona_max_vocabulary_entries: int = 30
    persona_max_custom_traits: int = 20

    artifacts_warm_budget_bytes: int = 8192
    artifacts_warm_max_artifacts: int = 50


@dataclass
class SessionStateConfig:
    """Root sessionstate config."""

    tiers: SessionStateTiersConfig = field(default_factory=SessionStateTiersConfig)
    eviction: EvictionConfig = field(default_factory=EvictionConfig)
    migration: MigrationConfig = field(default_factory=MigrationConfig)
    thrash: ThrashConfig = field(default_factory=ThrashConfig)
    reconstruction: ReconstructionConfig = field(default_factory=ReconstructionConfig)
    flatbuffer_overhead_factor: float = 1.10
    storage: StorageConfig = field(default_factory=StorageConfig)
    cold: ColdTierConfig = field(default_factory=ColdTierConfig)
    sections: SessionStateSectionsConfig = field(default_factory=SessionStateSectionsConfig)
    # M4 E4.2.2: LLM-writable vs system-owned section classification
    llm_writable_sections: list[str] = field(
        default_factory=lambda: [
            "beliefs_active",
            "scoreboard",
            "clarifications",
            "narrative_active",
            "affective_now",
        ]
    )
    system_owned_sections: list[str] = field(
        default_factory=lambda: [
            "control",
            "task_state",
            "task_artifacts",
            "meta",
            "history_active",
            "beliefs_history",
            "history_recent",
            "persona",
            "telemetry",
            "artifacts_warm",
        ]
    )


@dataclass
class PocConfig:
    """Root configuration for the entire POC."""

    actors: ActorsConfig = field(default_factory=ActorsConfig)
    bus: BusConfig = field(default_factory=BusConfig)
    delta: DeltaConfig = field(default_factory=DeltaConfig)
    experience: ExperienceConfig = field(default_factory=ExperienceConfig)
    fsm: FsmConfig = field(default_factory=FsmConfig)
    kernel: KernelConfig = field(default_factory=KernelConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    protocols: ProtocolsConfig = field(default_factory=ProtocolsConfig)
    react: ReactConfig = field(default_factory=ReactConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    sessionstate: SessionStateConfig = field(default_factory=SessionStateConfig)
    # M5: Conversation Arbiter
    arbiter: ArbiterConfig = field(default_factory=ArbiterConfig)
    # M8: Adaptive Weave Policy
    weave_policy: WeavePolicyConfig = field(default_factory=WeavePolicyConfig)
    # M9: Protocol Lifecycle Migration
    ledger: LedgerConfig = field(default_factory=LedgerConfig)
    # M10: UltraBERT Integration
    phase1: Phase1Config = field(default_factory=Phase1Config)
    # M11: Observability & Telemetry
    obs: ObsConfig = field(default_factory=ObsConfig)


# =========================================================================
# YAML loading helpers
# =========================================================================


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base* (override wins)."""
    merged = dict(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return a dict (empty dict on missing file)."""
    try:
        import yaml  # lazy import -- yaml is a runtime dep
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required for config loading.  Install with: pip install pyyaml"
        ) from exc

    if not path.exists():
        logger.warning("Config file not found: %s — using built-in defaults", path)
        return {}

    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _build_back(raw: dict[str, Any]) -> BackActorConfig:
    cfg = BackActorConfig()
    if not raw:
        return cfg
    for attr in (
        "budget_floor",
        "history_window",
        "default_safety_band",
        "hitl_timeout_s",
        "summarize_args_max_len",
        "summarize_result_max_len",
    ):
        if attr in raw:
            setattr(cfg, attr, raw[attr])
    if "max_iterations" in raw and isinstance(raw["max_iterations"], dict):
        cfg.max_iterations = {str(k): int(v) for k, v in raw["max_iterations"].items()}
    if "sensitive_keys" in raw and isinstance(raw["sensitive_keys"], list):
        cfg.sensitive_keys = [str(k) for k in raw["sensitive_keys"]]
    return cfg


def _build_front(raw: dict[str, Any]) -> FrontActorConfig:
    cfg = FrontActorConfig()
    if not raw:
        return cfg
    for attr in (
        "history_window_fallback",
        "default_tier",
        "default_affect_confidence",
        "default_fsm_state",
    ):
        if attr in raw:
            setattr(cfg, attr, raw[attr])
    return cfg


def _build_bus(raw: dict[str, Any]) -> BusConfig:
    cfg = BusConfig()
    if not raw:
        return cfg
    for attr in (
        "mailbox_capacity",
        "gap_timeout_ms",
        "actor_front_id",
        "actor_back_id",
        "priority_wfq",
    ):
        if attr in raw:
            setattr(cfg, attr, raw[attr])
    return cfg


def _build_overflow(raw: dict[str, Any]) -> OverflowConfig:
    cfg = OverflowConfig()
    if not raw:
        return cfg
    for attr in ("hot_budget_total", "history_window_size"):
        if attr in raw:
            setattr(cfg, attr, raw[attr])
    if "section_budgets" in raw and isinstance(raw["section_budgets"], dict):
        cfg.section_budgets = {str(k): int(v) for k, v in raw["section_budgets"].items()}
    return cfg


def _build_delta(raw: dict[str, Any]) -> DeltaConfig:
    cfg = DeltaConfig()
    if not raw:
        return cfg
    if "batch_window_ms" in raw:
        cfg.batch_window_ms = int(raw["batch_window_ms"])
    cfg.overflow = _build_overflow(raw.get("overflow", {}))
    return cfg


def _build_experience(raw: dict[str, Any]) -> ExperienceConfig:
    cfg = ExperienceConfig()
    if not raw:
        return cfg
    for attr in (
        "emotional_processor_cadence",
        "narrative_weaver_cadence",
        "anticipatory_responder_cadence",
        "proactive_wait_threshold_ms",
    ):
        if attr in raw:
            setattr(cfg, attr, int(raw[attr]))
    if "ep_skip_confidence_threshold" in raw:
        cfg.ep_skip_confidence_threshold = float(raw["ep_skip_confidence_threshold"])
    return cfg


def _build_fsm(raw: dict[str, Any]) -> FsmConfig:
    cfg = FsmConfig()
    if not raw:
        return cfg
    for attr in (
        "front_lock_max_queue_depth",
        "front_history_window",
        "back_history_window",
        "prune_completed_after_turns",
        "evict_artifacts_after_turns",
        "pending_results_max_depth",
        "pending_results_ttl_seconds",
        "idempotency_ledger_max_entries",
    ):
        if attr in raw:
            setattr(cfg, attr, int(raw[attr]))
    if "dead_letter_enabled" in raw:
        cfg.dead_letter_enabled = bool(raw["dead_letter_enabled"])
    if "cancel_keywords" in raw and isinstance(raw["cancel_keywords"], list):
        cfg.cancel_keywords = [str(k) for k in raw["cancel_keywords"]]
    return cfg


def _build_kernel(raw: dict[str, Any]) -> KernelConfig:
    cfg = KernelConfig()
    if not raw:
        return cfg
    if "poll_interval_s" in raw:
        cfg.poll_interval_s = float(raw["poll_interval_s"])
    if "dedup_cache_size" in raw:
        cfg.dedup_cache_size = int(raw["dedup_cache_size"])
    return cfg


def _build_llm(raw: dict[str, Any]) -> LlmConfig:
    cfg = LlmConfig()
    if not raw:
        return cfg
    if "default_model" in raw:
        cfg.default_model = str(raw["default_model"])
    if "batch_max_concurrency" in raw:
        cfg.batch_max_concurrency = int(raw["batch_max_concurrency"])
    if "default_max_tokens" in raw:
        cfg.default_max_tokens = int(raw["default_max_tokens"])
    if "default_timeout_ms" in raw:
        cfg.default_timeout_ms = int(raw["default_timeout_ms"])
    if "default_temperature" in raw:
        cfg.default_temperature = float(raw["default_temperature"])
    if "model_hint_overrides" in raw and isinstance(raw["model_hint_overrides"], dict):
        cfg.model_hint_overrides = {str(k): str(v) for k, v in raw["model_hint_overrides"].items()}
    if "model_selection_table" in raw and isinstance(raw["model_selection_table"], dict):
        cfg.model_selection_table = {
            str(cap): {str(actor): str(model) for actor, model in actors.items()}
            for cap, actors in raw["model_selection_table"].items()
            if isinstance(actors, dict)
        }
    return cfg


def _build_orchestrator(raw: dict[str, Any]) -> OrchestratorConfig:
    cfg = OrchestratorConfig()
    if not raw:
        return cfg
    if "tier_fabric_budget" in raw and isinstance(raw["tier_fabric_budget"], dict):
        cfg.tier_fabric_budget = {str(k): int(v) for k, v in raw["tier_fabric_budget"].items()}
    if "tier_planner_token_budget" in raw and isinstance(raw["tier_planner_token_budget"], dict):
        cfg.tier_planner_token_budget = {
            str(k): int(v) for k, v in raw["tier_planner_token_budget"].items()
        }
    if "default_budget_timeout_ms" in raw:
        cfg.default_budget_timeout_ms = int(raw["default_budget_timeout_ms"])
    if "canned_response_text" in raw:
        cfg.canned_response_text = str(raw["canned_response_text"])
    return cfg


def _build_prompt(raw: dict[str, Any]) -> PromptConfig:
    cfg = PromptConfig()
    if not raw:
        return cfg
    if "context_window" in raw:
        cfg.context_window = int(raw["context_window"])
    if "safety_margin" in raw:
        cfg.safety_margin = float(raw["safety_margin"])
    if "chars_per_token" in raw:
        cfg.chars_per_token = int(raw["chars_per_token"])
    if "max_iterations" in raw and isinstance(raw["max_iterations"], dict):
        cfg.max_iterations = {str(k): int(v) for k, v in raw["max_iterations"].items()}
    if "crisis_iterations" in raw and isinstance(raw["crisis_iterations"], dict):
        cfg.crisis_iterations = {str(k): int(v) for k, v in raw["crisis_iterations"].items()}
    if "affect_confidence_threshold" in raw:
        cfg.affect_confidence_threshold = float(raw["affect_confidence_threshold"])
    if "max_clarify_depth" in raw:
        cfg.max_clarify_depth = int(raw["max_clarify_depth"])
    if "back_max_tool_calls" in raw:
        cfg.back_max_tool_calls = int(raw["back_max_tool_calls"])
    return cfg


def _build_protocols(raw: dict[str, Any]) -> ProtocolsConfig:
    cfg = ProtocolsConfig()
    if not raw:
        return cfg
    if "max_suspensions_per_task" in raw:
        cfg.max_suspensions_per_task = int(raw["max_suspensions_per_task"])
    if "max_concurrent_suspensions" in raw:
        cfg.max_concurrent_suspensions = int(raw["max_concurrent_suspensions"])
    if "suspension_timeouts" in raw and isinstance(raw["suspension_timeouts"], dict):
        cfg.suspension_timeouts = {str(k): float(v) for k, v in raw["suspension_timeouts"].items()}
    if "hil_timeouts" in raw and isinstance(raw["hil_timeouts"], dict):
        cfg.hil_timeouts = {str(k): int(v) for k, v in raw["hil_timeouts"].items()}
    if "weave_batch_window_ms" in raw:
        cfg.weave_batch_window_ms = int(raw["weave_batch_window_ms"])
    if "weave_max_queued_depth" in raw:
        cfg.weave_max_queued_depth = int(raw["weave_max_queued_depth"])
    return cfg


def _build_react(raw: dict[str, Any]) -> ReactConfig:
    cfg = ReactConfig()
    if not raw:
        return cfg
    if "default_front_max_iterations" in raw:
        cfg.default_front_max_iterations = int(raw["default_front_max_iterations"])
    if "default_back_max_iterations" in raw:
        cfg.default_back_max_iterations = int(raw["default_back_max_iterations"])
    if "front_degenerate_fallback" in raw:
        cfg.front_degenerate_fallback = str(raw["front_degenerate_fallback"])
    if "front_budget_fallback" in raw:
        cfg.front_budget_fallback = str(raw["front_budget_fallback"])
    return cfg


def _build_task(raw: dict[str, Any]) -> TaskConfig:
    cfg = TaskConfig()
    if not raw:
        return cfg
    if "tier_budget" in raw and isinstance(raw["tier_budget"], dict):
        cfg.tier_budget = {str(k): int(v) for k, v in raw["tier_budget"].items()}
    return cfg


def _build_tools(raw: dict[str, Any]) -> ToolsConfig:
    cfg = ToolsConfig()
    if not raw:
        return cfg
    if "budget_limits" in raw and isinstance(raw["budget_limits"], dict):
        cfg.budget_limits = {str(k): int(v) for k, v in raw["budget_limits"].items()}
    return cfg


# -- M7: BackPool builder ------------------------------------------------


def _build_back_pool(raw: dict[str, Any]) -> BackPoolConfig:
    cfg = BackPoolConfig()
    if not raw:
        return cfg
    for attr in ("pool_size", "max_concurrent_per_session", "max_lease_renewals"):
        if attr in raw:
            setattr(cfg, attr, int(raw[attr]))
    for attr in (
        "lease_ttl_s",
        "reclaim_check_interval_s",
        "lease_renewal_extension_s",
        "grace_period_s",
    ):
        if attr in raw:
            setattr(cfg, attr, float(raw[attr]))
    if "enable_dependency_ordering" in raw:
        cfg.enable_dependency_ordering = bool(raw["enable_dependency_ordering"])
    return cfg


# -- M5: Arbiter builder -------------------------------------------------


def _build_arbiter(raw: dict[str, Any]) -> ArbiterConfig:
    cfg = ArbiterConfig()
    if not raw:
        return cfg
    for attr in ("domain_overlap_threshold", "entity_overlap_threshold"):
        if attr in raw:
            setattr(cfg, attr, float(raw[attr]))
    if "high_impact_confirmation_required" in raw:
        cfg.high_impact_confirmation_required = bool(raw["high_impact_confirmation_required"])
    if "high_impact_actions" in raw and isinstance(raw["high_impact_actions"], list):
        cfg.high_impact_actions = [str(a) for a in raw["high_impact_actions"]]
    if "cancel_keywords" in raw and isinstance(raw["cancel_keywords"], list):
        cfg.cancel_keywords = [str(k) for k in raw["cancel_keywords"]]
    if "defer_keywords" in raw and isinstance(raw["defer_keywords"], list):
        cfg.defer_keywords = [str(k) for k in raw["defer_keywords"]]
    return cfg


# -- M8: Weave Policy builder --------------------------------------------


def _build_weave_policy(raw: dict[str, Any]) -> WeavePolicyConfig:
    cfg = WeavePolicyConfig()
    if not raw:
        return cfg
    if "enabled" in raw:
        cfg.enabled = bool(raw["enabled"])
    for attr in (
        "idle_eager_ms",
        "idle_batch_ms",
        "typing_suppress_ms",
        "digest_threshold_count",
        "digest_window_ms",
        "pool_pressure_batch_ms",
        "default_batch_ms",
        "max_batch_ms",
        "max_consecutive_defers",
    ):
        if attr in raw:
            setattr(cfg, attr, int(raw[attr]))
    for attr in ("pool_pressure_threshold", "emotional_suppress_valence"):
        if attr in raw:
            setattr(cfg, attr, float(raw[attr]))
    return cfg


# -- M9: Ledger builder --------------------------------------------------


def _build_ledger(raw: dict[str, Any]) -> LedgerConfig:
    cfg = LedgerConfig()
    if not raw:
        return cfg
    for attr in ("max_events_per_session", "compaction_threshold"):
        if attr in raw:
            setattr(cfg, attr, int(raw[attr]))
    if "crash_recovery_timeout_s" in raw:
        cfg.crash_recovery_timeout_s = float(raw["crash_recovery_timeout_s"])
    return cfg


# -- M10: Phase 1 builder ------------------------------------------------


def _build_phase1(raw: dict[str, Any]) -> Phase1Config:
    cfg = Phase1Config()
    if not raw:
        return cfg
    if "pipeline" in raw:
        cfg.pipeline = str(raw["pipeline"]).lower()
    if "intent_confidence_threshold" in raw:
        cfg.intent_confidence_threshold = float(raw["intent_confidence_threshold"])
    if "complexity_thresholds" in raw and isinstance(raw["complexity_thresholds"], dict):
        cfg.complexity_thresholds = {
            str(k): int(v) for k, v in raw["complexity_thresholds"].items()
        }
    for attr in ("degradation_fallback_enabled", "warmup_on_startup"):
        if attr in raw:
            setattr(cfg, attr, bool(raw[attr]))
    if "cache_size" in raw:
        cfg.cache_size = int(raw["cache_size"])
    if "cache_ttl_s" in raw:
        cfg.cache_ttl_s = float(raw["cache_ttl_s"])
    if "target_latency_ms" in raw:
        cfg.target_latency_ms = int(raw["target_latency_ms"])
    return cfg


# -- M11: Observability builders ------------------------------------------


def _build_obs_metrics(raw: dict[str, Any]) -> ObsMetricsConfig:
    cfg = ObsMetricsConfig()
    if not raw:
        return cfg
    if "enabled" in raw:
        cfg.enabled = bool(raw["enabled"])
    if "window_size_s" in raw:
        cfg.window_size_s = float(raw["window_size_s"])
    if "emit_interval_s" in raw:
        cfg.emit_interval_s = float(raw["emit_interval_s"])
    return cfg


def _build_obs_alert_rules(raw_list: list[dict[str, Any]]) -> list[ObsAlertRuleConfig]:
    rules: list[ObsAlertRuleConfig] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        rule = ObsAlertRuleConfig(
            name=str(item.get("name", "")),
            metric=str(item.get("metric", "")),
            condition=str(item.get("condition", "")),
            threshold=float(item.get("threshold", 0.0)),
            window_s=float(item.get("window_s", 300.0)),
            severity=str(item.get("severity", "warning")),
            cooldown_s=float(item.get("cooldown_s", 600.0)),
            labels=(
                {str(k): str(v) for k, v in item.get("labels", {}).items()}
                if isinstance(item.get("labels"), dict)
                else {}
            ),
        )
        rules.append(rule)
    return rules


def _build_obs_alerts(raw: dict[str, Any]) -> ObsAlertsConfig:
    cfg = ObsAlertsConfig()
    if not raw:
        return cfg
    if "enabled" in raw:
        cfg.enabled = bool(raw["enabled"])
    if "evaluation_interval_s" in raw:
        cfg.evaluation_interval_s = float(raw["evaluation_interval_s"])
    if "default_cooldown_s" in raw:
        cfg.default_cooldown_s = float(raw["default_cooldown_s"])
    if "rules" in raw and isinstance(raw["rules"], list):
        cfg.rules = _build_obs_alert_rules(raw["rules"])
    return cfg


def _build_obs_fsm(raw: dict[str, Any]) -> ObsFsmConfig:
    cfg = ObsFsmConfig()
    if not raw:
        return cfg
    if "stuck_state_thresholds" in raw and isinstance(raw["stuck_state_thresholds"], dict):
        cfg.stuck_state_thresholds = {
            str(k): int(v) for k, v in raw["stuck_state_thresholds"].items()
        }
    return cfg


def _build_obs(raw: dict[str, Any]) -> ObsConfig:
    if not raw:
        return ObsConfig()
    return ObsConfig(
        metrics=_build_obs_metrics(raw.get("metrics", {})),
        alerts=_build_obs_alerts(raw.get("alerts", {})),
        fsm=_build_obs_fsm(raw.get("fsm", {})),
    )


# -- sessionstate builders ------------------------------------------------


def _build_ss_tiers(raw: dict[str, Any]) -> SessionStateTiersConfig:
    cfg = SessionStateTiersConfig()
    if not raw:
        return cfg
    for key in (
        "total_size_limit_bytes",
        "hot_budget_bytes",
        "warm_budget_bytes",
    ):
        if key in raw:
            setattr(cfg, key, int(raw[key]))
    for key in (
        "normal_threshold_pct",
        "elevated_threshold_pct",
        "critical_threshold_pct",
    ):
        if key in raw:
            setattr(cfg, key, float(raw[key]))
    if "hot_section_budgets" in raw and isinstance(raw["hot_section_budgets"], dict):
        cfg.hot_section_budgets = {str(k): int(v) for k, v in raw["hot_section_budgets"].items()}
    if "warm_section_budgets" in raw and isinstance(raw["warm_section_budgets"], dict):
        cfg.warm_section_budgets = {str(k): int(v) for k, v in raw["warm_section_budgets"].items()}
    return cfg


def _build_ss_eviction(raw: dict[str, Any]) -> EvictionConfig:
    cfg = EvictionConfig()
    if not raw:
        return cfg
    if "target_utilization" in raw:
        cfg.target_utilization = float(raw["target_utilization"])
    if "min_eviction_bytes" in raw:
        cfg.min_eviction_bytes = int(raw["min_eviction_bytes"])
    if "max_eviction_iterations" in raw:
        cfg.max_eviction_iterations = int(raw["max_eviction_iterations"])
    return cfg


def _build_ss_migration(raw: dict[str, Any]) -> MigrationConfig:
    cfg = MigrationConfig()
    if not raw:
        return cfg
    for key in (
        "max_history_active_turns",
        "compression_turn_threshold",
        "min_demote_bytes",
        "max_demote_iterations",
    ):
        if key in raw:
            setattr(cfg, key, int(raw[key]))
    if "target_hot_utilization" in raw:
        cfg.target_hot_utilization = float(raw["target_hot_utilization"])
    return cfg


def _build_ss_thrash(raw: dict[str, Any]) -> ThrashConfig:
    cfg = ThrashConfig()
    if not raw:
        return cfg
    for key in (
        "mild_migrations",
        "mild_evictions",
        "moderate_migrations",
        "moderate_evictions",
        "severe_migrations",
        "severe_evictions",
        "window_ms",
    ):
        if key in raw:
            setattr(cfg, key, int(raw[key]))
    return cfg


def _build_ss_reconstruction(raw: dict[str, Any]) -> ReconstructionConfig:
    cfg = ReconstructionConfig()
    if not raw:
        return cfg
    for key in (
        "sla_local_cold_ms",
        "sla_k0_fallback_ms",
        "k0_timeout_ms",
        "estimate_local_cold_base_ms",
        "estimate_local_cold_per_kb_ms",
        "estimate_k0_base_ms",
        "estimate_k0_per_kb_ms",
    ):
        if key in raw:
            setattr(cfg, key, float(raw[key]))
    return cfg


def _build_ss_storage(raw: dict[str, Any]) -> StorageConfig:
    cfg = StorageConfig()
    if not raw:
        return cfg
    if "default_db_path" in raw:
        cfg.default_db_path = str(raw["default_db_path"])
    if "checkpoint_interval_s" in raw:
        cfg.checkpoint_interval_s = float(raw["checkpoint_interval_s"])
    if "sla_restore_ms" in raw:
        cfg.sla_restore_ms = float(raw["sla_restore_ms"])
    if "sla_storage_ms" in raw:
        cfg.sla_storage_ms = float(raw["sla_storage_ms"])
    return cfg


def _build_ss_cold(raw: dict[str, Any]) -> ColdTierConfig:
    cfg = ColdTierConfig()
    if not raw:
        return cfg
    if "default_max_age_days" in raw:
        cfg.default_max_age_days = int(raw["default_max_age_days"])
    if "restore_sla_ms" in raw:
        cfg.restore_sla_ms = float(raw["restore_sla_ms"])
    return cfg


def _build_ss_sections(raw: dict[str, Any]) -> SessionStateSectionsConfig:
    cfg = SessionStateSectionsConfig()
    if not raw:
        return cfg
    # Flatten all section sub-dicts into prefix_key format
    for section_name, section_raw in raw.items():
        if not isinstance(section_raw, dict):
            continue
        for key, val in section_raw.items():
            attr = f"{section_name}_{key}"
            if hasattr(cfg, attr):
                # Coerce type based on existing default
                cur = getattr(cfg, attr)
                if isinstance(cur, int):
                    setattr(cfg, attr, int(val))
                elif isinstance(cur, float):
                    setattr(cfg, attr, float(val))
                elif isinstance(cur, str):
                    setattr(cfg, attr, str(val))
    return cfg


def _build_sessionstate(raw: dict[str, Any]) -> SessionStateConfig:
    if not raw:
        return SessionStateConfig()
    fbo = raw.get("flatbuffer_overhead_factor", 1.10)
    cfg = SessionStateConfig(
        tiers=_build_ss_tiers(raw.get("tiers", {})),
        eviction=_build_ss_eviction(raw.get("eviction", {})),
        migration=_build_ss_migration(raw.get("migration", {})),
        thrash=_build_ss_thrash(raw.get("thrash", {})),
        reconstruction=_build_ss_reconstruction(raw.get("reconstruction", {})),
        flatbuffer_overhead_factor=float(fbo),
        storage=_build_ss_storage(raw.get("storage", {})),
        cold=_build_ss_cold(raw.get("cold", {})),
        sections=_build_ss_sections(raw.get("sections", {})),
    )
    # M4 E4.2.2: LLM-writable / system-owned section classification
    if "llm_writable_sections" in raw and isinstance(raw["llm_writable_sections"], list):
        cfg.llm_writable_sections = [str(s) for s in raw["llm_writable_sections"]]
    if "system_owned_sections" in raw and isinstance(raw["system_owned_sections"], list):
        cfg.system_owned_sections = [str(s) for s in raw["system_owned_sections"]]
    return cfg


def _build_config(raw: dict[str, Any]) -> PocConfig:
    """Construct a PocConfig from a raw YAML dict."""
    actors_raw = raw.get("actors", {})
    return PocConfig(
        actors=ActorsConfig(
            back=_build_back(actors_raw.get("back", {})),
            front=_build_front(actors_raw.get("front", {})),
            back_pool=_build_back_pool(actors_raw.get("back_pool", {})),
        ),
        bus=_build_bus(raw.get("bus", {})),
        delta=_build_delta(raw.get("delta", {})),
        experience=_build_experience(raw.get("experience", {})),
        fsm=_build_fsm(raw.get("fsm", {})),
        kernel=_build_kernel(raw.get("kernel", {})),
        llm=_build_llm(raw.get("llm", {})),
        orchestrator=_build_orchestrator(raw.get("orchestrator", {})),
        prompt=_build_prompt(raw.get("prompt", {})),
        protocols=_build_protocols(raw.get("protocols", {})),
        react=_build_react(raw.get("react", {})),
        task=_build_task(raw.get("task", {})),
        tools=_build_tools(raw.get("tools", {})),
        sessionstate=_build_sessionstate(raw.get("sessionstate", {})),
        arbiter=_build_arbiter(raw.get("arbiter", {})),
        weave_policy=_build_weave_policy(raw.get("weave_policy", {})),
        ledger=_build_ledger(raw.get("ledger", {})),
        phase1=_build_phase1(raw.get("phase1", {})),
        obs=_build_obs(raw.get("obs", {})),
    )


# =========================================================================
# Singleton management
# =========================================================================

_singleton: PocConfig | None = None


def load_config(override_path: str | Path | None = None) -> PocConfig:
    """Load (or reload) the POC config.

    1. Reads ``defaults.yaml`` from this package.
    2. If *override_path* is given, deep-merges it on top.
    3. If env var ``K1_POC_CONFIG`` points to a file, deep-merges that too.
    4. Stores the result as the module singleton.

    Returns:
        The newly loaded PocConfig.
    """
    global _singleton

    raw = _load_yaml(_DEFAULTS_PATH)

    if override_path is not None:
        raw = _deep_merge(raw, _load_yaml(Path(override_path)))

    env_path = os.environ.get("K1_POC_CONFIG")
    if env_path:
        raw = _deep_merge(raw, _load_yaml(Path(env_path)))

    _singleton = _build_config(raw)
    logger.info("PocConfig loaded (override=%s, env=%s)", override_path, env_path)
    return _singleton


def get_config() -> PocConfig:
    """Return the current PocConfig singleton (loads defaults on first call)."""
    global _singleton
    if _singleton is None:
        _singleton = _build_config(_load_yaml(_DEFAULTS_PATH))
    return _singleton


def reset_config() -> None:
    """Clear the singleton (for testing)."""
    global _singleton
    _singleton = None
