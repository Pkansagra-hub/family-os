"""Kernel configuration dataclass -- zero-dependency extraction.

Extracted from ``k1.concierge.kernel.bootstrap`` so that consumers
(e.g. ConciergeFactory) can import ``KernelConfig`` without triggering
the heavy bootstrap import chain (actors → react → model_hub).

Lives in ``k1.concierge.config`` — the canonical config package for
the Concierge subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BusConfig:
    """Bus infrastructure configuration (middleware, mailbox, timing)."""

    topic_validation_enabled: bool = True
    tracing_enabled: bool = False
    metrics_enabled: bool = False
    gap_timeout_ms: int = 5000
    mailbox_capacity: int = 64
    priority_wfq: bool = True


@dataclass
class KernelConfig:
    """Configuration for independent kernel startup."""

    ordered_bus: bool = True
    capture_bus: bool = False
    test_mode: bool = False
    model_mode: str = "test"  # "test" | "hub" — controls _create_model()
    tool_tier: str = "LOW"
    session_mode: str = "standalone"  # standalone | testing
    session_id: str | None = None
    enable_experience: bool = True
    enable_delta: bool = True
    enable_hitl: bool = True
    enable_orchestrator: bool = True
    auto_start_consumer: bool = True
    # M1 E1.4.1: Create and inject LedgerWriter into FSM at boot
    enable_ledger: bool = True
    # M2 E2.5.1: Create DeadLetterConsumer at boot
    enable_dead_letter_consumer: bool = True
    seed_memories: list[dict[str, Any]] = field(default_factory=list)
    # Issue 2.0.5: Config values previously fetched via get_config()
    phase1_pipeline: str = "ultrabert"
    # P4B.8: default False so lazy_load (~10ms boot) is honored.
    # Set True to pay the ~20s model load cost up-front during boot.
    phase1_warmup_on_startup: bool = False
    delta_batch_window_ms: int = 500
    dead_letter_enabled: bool = True
    poll_interval_s: float = 0.05
    dedup_cache_size: int = 4096
    # Issue 2.0.5 (deferred from 2.0.3): Bus middleware config
    bus: BusConfig = field(default_factory=BusConfig)
    # Issue 2.1.3: Tier 1 boot/wiring config for multi-session KernelService
    max_sessions: int = 100  # SIM-D-02 session limit
    idle_timeout_minutes: int = 30  # session idle eviction
    bridge_enabled: bool = True  # enable/disable K0 connection
    bridge_offline_ok: bool = True  # allow startup without K0 (SIM-D-32)
    bridge_outbox_path: str = "./data/bridge_outbox.db"  # SinkBridgeClient SQLite queue
    model_hub_plugins: list[str] = field(default_factory=lambda: ["openai"])
    system_bus_enabled: bool = True  # system_bus for admin events
    otel_enabled: bool = True  # OpenTelemetry tracing
    workflow_db_path: str = "./data/workflows.db"  # Orchestrator SQLite
    sessionstate_db_path: str = "./data/k1/sessionstate.db"  # Per-session SSM SQLite
