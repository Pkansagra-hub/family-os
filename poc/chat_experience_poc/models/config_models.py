"""
Pydantic Configuration Models

Defines config data structures for SessionConfig, PerformanceConfig, AgentConfig, K0BridgeConfig.
Referenced by config_loader.py

These models provide validation and type checking for all PoC configuration.
"""

from pydantic import BaseModel, Field, field_validator


class SessionConfig(BaseModel):
    """Session management configuration."""

    session_timeout_seconds: int = Field(
        default=600,
        description="Session idle timeout in seconds",
        ge=60,
        le=3600,
    )
    max_turns: int = Field(
        default=100,
        description="Maximum conversation turns per session",
        ge=10,
        le=1000,
    )
    max_session_memory_mb: float = Field(
        default=50.0,
        description="Maximum memory per session in MB",
        ge=1.0,
        le=500.0,
    )


class PerformanceConfig(BaseModel):
    """Performance budget configuration."""

    ttft_budget_ms: int = Field(
        default=150,
        description="Time to first token budget in milliseconds",
        ge=50,
        le=500,
    )
    e2e_latency_budget_ms: int = Field(
        default=2000,
        description="End-to-end latency budget in milliseconds",
        ge=500,
        le=5000,
    )
    memory_budget_mb: float = Field(
        default=500.0,
        description="Total memory budget in MB",
        ge=100.0,
        le=2000.0,
    )


class AgentConfig(BaseModel):
    """Agent management configuration."""

    max_concurrent_agents: int = Field(
        default=3,
        description="Maximum concurrent agents per session",
        ge=1,
        le=10,
    )
    agent_pool_size: int = Field(
        default=5,
        description="Maximum agents in idle pool per type",
        ge=1,
        le=20,
    )
    agent_idle_ttl_seconds: int = Field(
        default=600,
        description="Time to live for pooled agents",
        ge=60,
        le=3600,
    )
    warming_timeout_seconds: int = Field(
        default=35,
        description="WARMING state timeout in seconds",
        ge=10,
        le=120,
    )


class K0BridgeConfig(BaseModel):
    """K0 Bridge communication configuration."""

    batch_interval_ms: int = Field(
        default=250,
        description="Delta batch flush interval in milliseconds",
        ge=50,
        le=1000,
    )
    batch_size_max_deltas: int = Field(
        default=100,
        description="Maximum deltas per batch",
        ge=10,
        le=1000,
    )
    batch_size_max_bytes: int = Field(
        default=65536,
        description="Maximum batch size in bytes (64KB)",
        ge=1024,
        le=1048576,
    )
    k0_api_url: str = Field(
        default="http://localhost:8003",
        description="Mock K0 API base URL",
    )
    k0_timeout_seconds: float = Field(
        default=10.0,
        description="K0 API request timeout",
        ge=1.0,
        le=60.0,
    )
    k0_max_retries: int = Field(
        default=3,
        description="Maximum retries for K0 requests",
        ge=1,
        le=10,
    )


class TemporalConfig(BaseModel):
    """Temporal module configuration."""

    tick_interval_seconds: int = Field(
        default=60,
        description="Scheduler tick interval in seconds",
        ge=10,
        le=300,
    )
    max_triggers: int = Field(
        default=1000,
        description="Maximum active triggers",
        ge=100,
        le=10000,
    )


class OrchestratorBudgets(BaseModel):
    """Orchestrator performance budgets."""

    negotiation_deadline_ms: int = Field(default=50, ge=10, le=200)
    selection_deadline_ms: int = Field(default=30, ge=10, le=100)
    execution_deadline_ms: int = Field(default=1920, ge=1000, le=5000)


class AgentBudgets(BaseModel):
    """Agent lifecycle performance budgets."""

    warming_p95_ms: int = Field(default=35000, ge=10000, le=60000)
    idle_ttl_ms: int = Field(default=600000, ge=60000, le=3600000)
    draining_timeout_ms: int = Field(default=30000, ge=10000, le=60000)
    spawn_latency_p95_ms: int = Field(default=35000, ge=10000, le=60000)
    pool_reuse_latency_ms: int = Field(default=1, ge=0, le=10)


class LLMBudgets(BaseModel):
    """LLM performance budgets."""

    ttft_ms: int = Field(default=150, ge=50, le=500)
    tokens_per_second: int = Field(default=100, ge=50, le=500)
    max_completion_time_ms: int = Field(default=5000, ge=1000, le=30000)
    rate_limit_budget: int = Field(default=60, ge=10, le=1000)


class RuntimeBudgets(BaseModel):
    """Runtime component performance budgets."""

    state_access_p95_ms: float = Field(default=1.0, ge=0.1, le=10.0)
    state_write_p95_ms: float = Field(default=5.0, ge=1.0, le=50.0)
    mailbox_op_p95_ms: float = Field(default=0.5, ge=0.1, le=5.0)
    delta_computation_p95_ms: float = Field(default=5.0, ge=1.0, le=50.0)
    deltabus_delivery_p95_ms: float = Field(default=1.0, ge=0.1, le=10.0)


class E2EBudgets(BaseModel):
    """End-to-end performance budgets."""

    latency_p95_ms: int = Field(default=2000, ge=500, le=10000)
    latency_planning_p95_ms: int = Field(default=4000, ge=1000, le=20000)
    meta_intent_latency_ms: int = Field(default=200, ge=50, le=1000)
    proactive_tick_latency_ms: int = Field(default=1000, ge=100, le=5000)


class K0BridgeBudgets(BaseModel):
    """K0 Bridge performance budgets."""

    query_p95_ms: int = Field(default=50, ge=10, le=500)
    batch_send_p95_ms: int = Field(default=50, ge=10, le=500)
    sse_heartbeat_interval_ms: int = Field(default=30000, ge=10000, le=120000)
    sse_reconnect_jitter_ms: int = Field(default=500, ge=100, le=5000)


class MailboxConfig(BaseModel):
    """Mailbox configuration."""

    capacity: int = Field(default=64, ge=16, le=256)
    wfq_weights: list[int] = Field(default=[4, 2, 1, 1])
    backpressure_threshold: float = Field(default=0.8, ge=0.5, le=1.0)


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration."""

    failure_threshold: int = Field(default=5, ge=1, le=20)
    timeout_seconds: int = Field(default=60, ge=10, le=300)
    half_open_max_calls: int = Field(default=3, ge=1, le=10)


class MonitoringConfig(BaseModel):
    """Monitoring configuration."""

    metrics_export_interval_ms: int = Field(default=1000, ge=100, le=10000)
    log_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    trace_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)


class EnforcementConfig(BaseModel):
    """Budget enforcement configuration."""

    fail_fast: bool = Field(default=True)
    emit_metric: bool = Field(default=True)
    log_violations: bool = Field(default=True)


class PerfBudgets(BaseModel):
    """Complete performance budgets configuration."""

    orchestrator: OrchestratorBudgets = Field(default_factory=OrchestratorBudgets)
    agent: AgentBudgets = Field(default_factory=AgentBudgets)
    llm: LLMBudgets = Field(default_factory=LLMBudgets)
    runtime: RuntimeBudgets = Field(default_factory=RuntimeBudgets)
    e2e: E2EBudgets = Field(default_factory=E2EBudgets)
    k0_bridge: K0BridgeBudgets = Field(default_factory=K0BridgeBudgets)
    mailbox: MailboxConfig = Field(default_factory=MailboxConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    enforcement: EnforcementConfig = Field(default_factory=EnforcementConfig)


class POCConfig(BaseModel):
    """Complete PoC configuration."""

    session: SessionConfig = Field(default_factory=SessionConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    k0_bridge: K0BridgeConfig = Field(default_factory=K0BridgeConfig)
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)
    perf_budgets: PerfBudgets = Field(default_factory=PerfBudgets)

    environment: str = Field(
        default="development",
        description="Environment (development, staging, production)",
        pattern="^(development|staging|production)$",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug logging",
    )

    @field_validator("session")
    @classmethod
    def validate_session(cls, v: SessionConfig) -> SessionConfig:
        """Validate session configuration."""
        if v.session_timeout_seconds < 60:
            raise ValueError("session_timeout_seconds must be >= 60")
        if v.max_turns < 10:
            raise ValueError("max_turns must be >= 10")
        return v

    @field_validator("performance")
    @classmethod
    def validate_performance(cls, v: PerformanceConfig) -> PerformanceConfig:
        """Validate performance configuration."""
        if v.ttft_budget_ms >= v.e2e_latency_budget_ms:
            raise ValueError("ttft_budget_ms must be < e2e_latency_budget_ms")
        return v

    @field_validator("agent")
    @classmethod
    def validate_agent(cls, v: AgentConfig) -> AgentConfig:
        """Validate agent configuration."""
        if v.max_concurrent_agents > v.agent_pool_size * 2:
            raise ValueError("max_concurrent_agents shouldn't exceed pool_size * 2")
        return v


class Config(BaseModel):
    """Config model for env var overrides."""

    class Config:
        case_sensitive = True
        env_prefix = "K1_POC_"
