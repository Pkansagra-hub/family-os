"""
Orchestrator Configuration -- Centralized config dataclass.

Single config object loaded by OrchestratorFactory at construction time.
Immutable after creation -- restart required for changes.

Source priority: env vars > config file > defaults.

Reference: Schema Whiteboard Section 2.

Import graph: k1.orchestrator.config imports from k1.orchestrator.types only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# Default guard ordering for V1 (5 active guards)
_DEFAULT_GUARD_ORDER: List[str] = [
    "ConcurrencyGuard",  # G0: wraps _process_one()
    "ConditionalEdgeEvaluator",  # G1: pre-wave, prune edges
    "OutputSchemaGuard",  # G2: post-step, validate result schema
    "ExecutionMonitor",  # G3: post-wave, emit progress delta
    "MicroReplanCheckpoint",  # G4: post-wave, check discovery heuristic
    "SafetyBandReRead",  # G5: post-wave, re-read safety_band
    # V1 REMOVED: TokenBudgetTracker, CostBudgetGuard, QualityGate
]

_KNOWN_GUARDS: frozenset = frozenset(
    {
        "ConcurrencyGuard",
        "ConditionalEdgeEvaluator",
        "OutputSchemaGuard",
        "ExecutionMonitor",
        "MicroReplanCheckpoint",
        "SafetyBandReRead",
        # V2 guards (known but not active in V1):
        "TokenBudgetTracker",
        "CostBudgetGuard",
        "QualityGate",
    }
)


@dataclass(frozen=True)
class OrchestratorConfig:
    """Centralized Orchestrator configuration.

    Loaded once at OrchestratorFactory construction time.
    Immutable after creation -- restart required for changes.

    Organized into logical groups per Schema Whiteboard Section 2:
      1. Concurrency
      2. Timeouts
      3. Retry
      4. Guards
      5. Workflow
      6. MCP (thin discovery layer)
      7. Circuit Breakers (CB_PLANNER only -- Orchestrator-owned)
      8. Telemetry
      9. Admin
      10. Pending context limits

    Ownership notes:
      CB_FABRIC, CB_MCP, CB_BRIDGE are owned by Concierge/Fabric.
      Orchestrator does NOT configure or manage them.
      ErrorRouter consumes AdapterError(CIRCUIT_OPEN) from adapters.
    """

    # --- 1. Concurrency ---
    max_concurrent_dags: int = 1  # V1: always 1 (ORCH-02)
    max_wave_parallelism: int = 5
    mailbox_capacity: int = 100

    # --- 2. Timeouts (ms) ---
    default_step_timeout_ms: int = 30_000
    plan_request_timeout_ms: int = 45_000
    hil_timeout_ms: int = 120_000
    drain_timeout_ms: int = 30_000
    shutdown_grace_period_ms: int = 30_000
    context_reap_interval_ms: int = 5_000

    # --- 3. Retry ---
    step_max_retries: int = 2
    step_retry_base_delay_ms: int = 100
    step_retry_max_delay_ms: int = 5_000

    # --- 4. Guards ---
    guard_order: List[str] = field(default_factory=lambda: list(_DEFAULT_GUARD_ORDER))
    max_micro_replans: int = 1  # ORCH-13
    substep_rate_limit_ms: int = 500

    # --- 5. Workflow ---
    max_workflow_depth: int = 3  # ORCH-12
    workflow_db_path: str = "data/orchestrator_workflows.db"
    scheduler_tick_interval_ms: int = 1_000

    # --- 6. MCP (thin discovery layer config) ---
    mcp_config_path: str = "k1/connectors/mcp_servers.yaml"
    mcp_discovery_interval_ms: int = 300_000
    mcp_max_servers: int = 10

    # --- 7. Circuit Breakers (CB_PLANNER only) ---
    cb_planner_failure_threshold: int = 3
    cb_planner_reset_timeout_ms: int = 60_000
    cb_planner_half_open_probes: int = 1

    # --- 8. Telemetry ---
    metrics_enabled: bool = True
    metrics_interval_ms: int = 10_000
    structured_log_level: str = "INFO"
    trace_sample_rate: float = 1.0
    trace_propagation: bool = True

    # --- 9. Admin ---
    admin_enabled: bool = True
    admin_port: int = 8081

    # --- 10. Pending context limits ---
    max_pending_plans: int = 50
    max_pending_hil: int = 20

    def __post_init__(self) -> None:
        errors: List[str] = []

        # Concurrency
        if self.max_concurrent_dags < 1:
            errors.append("max_concurrent_dags must be >= 1")
        if self.max_wave_parallelism < 1:
            errors.append("max_wave_parallelism must be >= 1")
        if not 1 <= self.mailbox_capacity <= 10_000:
            errors.append("mailbox_capacity must be 1-10000")

        # Timeouts
        if self.default_step_timeout_ms <= 0:
            errors.append("default_step_timeout_ms must be > 0")
        if self.plan_request_timeout_ms <= 0:
            errors.append("plan_request_timeout_ms must be > 0")
        if self.hil_timeout_ms <= 0:
            errors.append("hil_timeout_ms must be > 0")
        if self.drain_timeout_ms <= 0:
            errors.append("drain_timeout_ms must be > 0")
        if self.shutdown_grace_period_ms <= 0:
            errors.append("shutdown_grace_period_ms must be > 0")
        if self.context_reap_interval_ms <= 0:
            errors.append("context_reap_interval_ms must be > 0")

        # Retry
        if not 0 <= self.step_max_retries <= 10:
            errors.append("step_max_retries must be 0-10")
        if self.step_retry_base_delay_ms < 0:
            errors.append("step_retry_base_delay_ms must be >= 0")
        if self.step_retry_max_delay_ms < self.step_retry_base_delay_ms:
            errors.append("step_retry_max_delay_ms must be >= step_retry_base_delay_ms")

        # Guards
        guard_set = set(self.guard_order)
        if len(guard_set) != len(self.guard_order):
            errors.append("guard_order must contain unique entries")
        unknown = guard_set - _KNOWN_GUARDS
        if unknown:
            errors.append(f"unknown guards in guard_order: {unknown}")

        # Workflow
        if not 1 <= self.max_workflow_depth <= 10:
            errors.append("max_workflow_depth must be 1-10")
        if self.scheduler_tick_interval_ms <= 0:
            errors.append("scheduler_tick_interval_ms must be > 0")

        # MCP
        if self.mcp_max_servers < 1:
            errors.append("mcp_max_servers must be >= 1")
        if self.mcp_discovery_interval_ms <= 0:
            errors.append("mcp_discovery_interval_ms must be > 0")

        # Circuit Breakers
        if self.cb_planner_failure_threshold < 1:
            errors.append("cb_planner_failure_threshold must be >= 1")
        if self.cb_planner_reset_timeout_ms < 1_000:
            errors.append("cb_planner_reset_timeout_ms must be >= 1000")
        if self.cb_planner_half_open_probes < 1:
            errors.append("cb_planner_half_open_probes must be >= 1")

        # Telemetry
        if not 0.0 <= self.trace_sample_rate <= 1.0:
            errors.append("trace_sample_rate must be in [0.0, 1.0]")
        valid_log_levels = {"DEBUG", "INFO", "WARN", "ERROR"}
        if self.structured_log_level not in valid_log_levels:
            errors.append(
                f"structured_log_level '{self.structured_log_level}' " f"not in {valid_log_levels}"
            )

        # Pending context limits
        if self.max_pending_plans < 1:
            errors.append("max_pending_plans must be >= 1")
        if self.max_pending_hil < 1:
            errors.append("max_pending_hil must be >= 1")

        if errors:
            raise ValueError(f"OrchestratorConfig validation failed: " f"{'; '.join(errors)}")

    @classmethod
    def default(cls) -> "OrchestratorConfig":
        """Create config with all default values."""
        return cls()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OrchestratorConfig":
        """Create config from dictionary.

        Unknown keys are silently ignored (forward compatibility).
        """
        import inspect

        # Only pass keys that match constructor parameters
        valid_keys = {p.name for p in inspect.signature(cls).parameters.values()}
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        from dataclasses import asdict

        return asdict(self)
