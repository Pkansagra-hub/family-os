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
    # P3.4c: tool_tier removed; tier is per-task derived in dispatch_task.
    session_mode: str = "standalone"  # standalone | testing
    session_id: str | None = None
    # These four flags gate ConciergeFactory component wiring only.
    # They do NOT suppress the corresponding KernelService Tier 1/2
    # startup stages (S5 Orchestrator, S6 Planner, etc.).  Setting
    # enable_orchestrator=False disables orchestrator dispatch inside
    # Concierge but the KernelService still instantiates and starts the
    # OrchestratorService in S5.
    enable_experience: bool = True
    enable_delta: bool = True
    enable_hitl: bool = True
    enable_orchestrator: bool = True
    # M16.E1.I3: when False (default), HIGH-tier dispatch with no
    # OrchestratorService wired raises ``OrchestratorNotWired`` instead
    # of silently falling back to the legacy ``PassthroughPlannerStub``
    # that wraps a single intent as a 1-step MEDIUM plan. Test/dev
    # contexts that intentionally run without an orchestrator (and want
    # the stub) should set this to True.
    allow_planner_passthrough: bool = False
    # M17.E1.I1: when False (default), Back-actor capability tools
    # (invoke_capability, batch_invoke_capabilities, spawn_via_fabric,
    # execute_workflow) refuse to run when ``ctx.dispatch is None`` and
    # return a ``dispatch_not_wired`` error instead of returning a
    # synthetic ``{"_poc": True}`` payload. Test/dev contexts that build
    # a ToolContext without an IDispatchPort and want the legacy POC
    # stub responses should set this to True.
    allow_dispatch_passthrough: bool = False
    auto_start_consumer: bool = True
    # M1 E1.4.1: Create and inject LedgerWriter into FSM at boot
    enable_ledger: bool = True
    # M2 E2.5.1: Create DeadLetterConsumer at boot
    enable_dead_letter_consumer: bool = True
    seed_memories: list[dict[str, Any]] = field(default_factory=list)
    delta_batch_window_ms: int = 500
    dead_letter_enabled: bool = True
    poll_interval_s: float = 0.05
    dedup_cache_size: int = 4096
    # Issue 2.0.5 (deferred from 2.0.3): Bus middleware config
    bus: BusConfig = field(default_factory=BusConfig)
    # Issue 2.1.3: Tier 1 boot/wiring config for multi-session KernelService
    max_sessions: int = 100  # SIM-D-02 session limit
    idle_timeout_minutes: int = 30  # session idle eviction
    bridge_enabled: bool = (
        True  # True = enable LocalOutbox queueing (SinkBridgeClient, OFFLINE mode); does NOT establish a live K0 connection — for live K0 use bridge_live when HttpBridgeClient is wired
    )
    bridge_offline_ok: bool = True  # allow startup without K0 (SIM-D-32)
    bridge_outbox_path: str = "./data/bridge_outbox.db"  # SinkBridgeClient SQLite queue
    # M14: live bridge endpoint. If non-empty, S4 wires a LiveBridgeAdapter pointed at
    # this URL (HttpBridgeClient via BridgeRuntime). Example: "http://localhost:8090".
    # When empty (default), S4 uses SinkBridgeAdapter (offline outbox mode).
    # Set via env var K0_ENDPOINT in ui/web/__main__.py.
    k0_endpoint: str = ""
    model_hub_plugins: list[str] = field(default_factory=lambda: ["openai"])
    system_bus_enabled: bool = True  # system_bus for admin events
    otel_enabled: bool = True  # OpenTelemetry tracing
    workflow_db_path: str = "./data/workflows.db"  # Orchestrator SQLite
    sessionstate_db_path: str = "./data/k1/sessionstate.db"  # Per-session SSM SQLite
    # W2: Bus durability (P6.13). When bus_outbox_path is set, the shared
    # bus persists envelopes on bus_durable_topics to a SQLite WAL outbox
    # before dispatch, enabling at-least-once delivery across restarts.
    # Defaults to None (disabled) to preserve current behavior.
    bus_outbox_path: str | None = None  # e.g. "./data/k1/bus_outbox.db"
    bus_durable_topics: tuple[str, ...] = ()  # e.g. ("k1.session.turn.complete.v1",)
    # W8: When True the Fabric ModuleLoader starts a background daemon
    # thread that polls contracts_dir for manifest changes and hot-reloads
    # contracts via EVENT_CONTRACT_HOT_RELOADED. Defaults to False — opt
    # in for prod profiles that need live contract updates without a
    # restart. Test profiles should leave it disabled to avoid daemon
    # threads leaking across test cases.
    module_loader_watch: bool = False
    # E7.M1.2: HIL (Human-in-the-Loop) service configuration.
    # When enable_hil_service=True (default), KernelService.startup() builds a
    # single HumanInTheLoopService (k1.hil.service) at S2.5 and threads the
    # resulting hil_port into Fabric, Concierge, Planner, and Orchestrator
    # factories. The per-method timeouts and round budget map onto HILConfig
    # fields one-for-one. Set enable_hil_service=False to skip wiring (each
    # subsystem then receives hil_port=None and falls back to its own
    # internal _NullHILAdapter, preserving pre-E7 behavior for tests that
    # cannot rely on HIL responses).
    enable_hil_service: bool = True
    hil_max_clarification_rounds: int = 2
    hil_clarification_timeout_ms: int = 60_000
    hil_approval_timeout_ms: int = 120_000
    hil_needs_human_timeout_ms: int = 60_000
    hil_override_timeout_ms: int = 60_000
    hil_capability_gate_timeout_ms: int = 120_000
    hil_enable_audit_topic: bool = True
    hil_enable_llm_synthesis: bool = True
    # M5.E3.I1: k1.selfmodel kernel wiring.
    # When True, KernelService._startup_tier1 builds a
    # SelfModelServiceBundle at S2.6 (after S2.5 HIL, before S4 Bridge)
    # and create_session installs a SelfModelHandle at P3.5 (after P3
    # per-session Fabric, before P4 Concierge). The handle wires:
    #   * step-0 ConciergePolicyGate into the per-session ToolDispatcher
    #   * GroundingCapsuleRenderer into the per-session prompt builder
    #   * RecallCitationWrapper around ToolContext.recall_fn
    # Defaults to False so existing kernel + session tests are unchanged.
    enable_self_model: bool = False
    # Path to the SQLite projection store used by k1.selfmodel. When
    # empty / None the kernel falls back to an in-memory store
    # (suitable for tests + dev). Honored only when
    # ``enable_self_model=True``.
    selfmodel_projection_db_path: str | None = None
    # Default space id seeded into the SituationFrameComposer.
    # Per-session composition resolves the actor's space relative to
    # this id when the session does not supply its own.
    selfmodel_space_id: str = "family:default"
    # M15.E1.I6: per-deployment override for the always-on
    # ``situation_kind`` used by the SituationFrameComposer/grounding
    # capsule renderer. Defaults to the broadest read-only V0
    # situation (``caregiver_context_briefing``); deployments that need
    # a tighter or differently-scoped capsule can override here without
    # patching kernel internals.
    selfmodel_situation_kind: str = "caregiver_context_briefing"
    # The resolved actor_id for the active family member (e.g. "actor:alex").
    # When set, _derive_session_actor uses this directly instead of falling
    # back to the opaque "actor:{session_id}" form.  Set by the web UI
    # coordinator after resolving the device → family member mapping.
    active_member_id: str = ""
    # M15: Family-tools (k1.tools.family) wiring. When True, S8 of
    # ``KernelService._startup_tier1`` bootstraps the FamilyToolsBundle
    # (K1FamilyStore + IdempotencyStore + ToolRegistry + NativeToolProvider)
    # and registers it with the shared Fabric. Defaults to False so legacy
    # deployments and the existing test suite are unchanged.
    enable_family_tools: bool = False
    family_tools_db_path: str = "./data/k1_family.db"
    # Dotted import paths to ``BaseToolService`` subclasses to register, e.g.
    # ``("k1.tools.family.adapters.calendar:CalendarToolService",)``. Empty
    # by default; ui/web populates this from environment when needed.
    family_tool_service_paths: tuple[str, ...] = ()
