# Whiteboard: K1 Proactive Service

**Purpose:** Design a new sibling K1 service that owns proactive delivery end-to-end —
ingress fan-in, gating, surface nomination, durable outbox, and **loop closure** for
all proactive flows (workflow completions, curiosity gaps, prospective reminders,
drift advisories, suggestions, ambient insights).
**Status:** Design — pre-implementation whiteboard
**Last Updated:** 2026-05-04
**Audience:** K1 architecture team
**Recipe followed:** `k1/orchestrator/ARCHITECTURE.md` (sibling service template)

---

## §0 Why a new service (not a milestone bolt-on)

Three independent proactive sources already exist or are blueprinted:

| Source | Origin | Today |
|---|---|---|
| **WorkflowEngine completions** (Flow 4) | `k1/orchestrator/workflows/workflow_supervisor.py` already emits `k1.orchestration.workflow.run_completed` | Half-wired — no delivery envelope |
| **K0 Active Learning** — `curiosity.intent.v1` SSE | Bridge SSE listener planned; `PROACTIVE_DECISION → BUDGET_GATE → CURIOSITY_AGENT → CONCIERGE_FSM` in K1 skeleton diagram | Diagram only |
| **K0 Proactive signals** — `k0.proactive.signal.v1` (prospective reminders, drift) | Bridge SSE → `WORKFLOW_SCHEDULER → REMINDER_AGENT` | Diagram only |

If we ship M18 narrowly (workflow only), the next milestone either rewrites or duplicates the channel. **Three sources × one delivery problem ⇒ one service.** Sibling to `k1/orchestrator/`, `k1/concierge/`, `k1/planner/`.

### What already exists in tree (and what we reuse)

| Surface | Status | Reuse plan |
|---|---|---|
| `TOPIC_PROACTIVE_FILL = "k1.proactive.fill.v1"` | exists | KEEP — service publishes into it |
| `build_proactive_fill()` builder | exists | KEEP |
| `ProactiveScheduler` (`k1/concierge/scheduler/proactive_scheduler.py`) | exists, narrow | DEPRECATE after migration; logic absorbed by service |
| `ProactiveWakeHandler` + FSM state `PROACTIVE_WAKE` | exists | KEEP — service triggers it |
| `WeavePolicy` (M8) | exists | KEEP — service nominates surface, WeavePolicy resolves |
| `HILLedgerAdapter` (M13.E2.I1) | exists | MIRROR for outbox shape |

---

## §1 Service Surface (NEW — `k1/proactive/`)

Mirror of `k1/orchestrator/` exactly. 8 ports, all `@runtime_checkable Protocol`.

### IIngressPort — `ports/ingress_port.py`

| Method | Signature |
|---|---|
| `subscribe` | `(topic: str, handler: Callable[[str, Dict[str, Any]], None]) -> SubscriptionHandle` |
| `unsubscribe` | `(handle: SubscriptionHandle) -> bool` |

Wraps `IEventPort` for inbound topic subscription. Subscribes to:

- `k1.proactive.ingress.v1` (in-kernel producers — WorkflowSupervisor publishes here)
- `k0.curiosity.intent.v1` (Bridge SSE)
- `k0.proactive.signal.v1` (Bridge SSE)
- `k0.learning.advisory.v1` (Bridge SSE)
- `k1.concierge.session.opened.v1` (drain trigger)
- `k1.concierge.session.idle.v1` (deferred-delivery window)
- `k1.concierge.turn.completed.v1` (closure correlation)
- `k1.memory.delta.v1` (gap-resolution correlation, filtered)

### IOutboxPort — `ports/outbox_port.py`

| Method | Signature |
|---|---|
| `persist` | `(envelope: ProactiveDeliveryEnvelope, decision: DeliveryDecision) -> OutboxEntryId` |
| `mark_emitted` | `(entry_id: OutboxEntryId, surface: SurfaceTier) -> None` |
| `mark_closed` | `(entry_id: OutboxEntryId, outcome: ClosureOutcome) -> None` |
| `get_pending` | `() -> List[OutboxEntry]` |
| `get_expired` | `(now: float) -> List[OutboxEntry]` |
| `get_by_correlation` | `(correlation_key: str) -> Optional[OutboxEntry]` |
| `get_for_digest` | `(recipient: str, kind: str) -> List[OutboxEntry]` |

SQLite-backed. Crash-safe. Mirrors `HILLedgerAdapter`.

### IAttentionBudgetPort — `ports/attention_budget_port.py`

| Method | Signature |
|---|---|
| `try_spend` | `(recipient: str, cost: int = 1) -> BudgetDecision` |
| `peek` | `(recipient: str) -> BudgetState` |
| `refund` | `(recipient: str, cost: int = 1) -> None` |

Token bucket per recipient (default 3/day, configurable). REASK consumes a fresh token (decision §5). Returns `BudgetDecision { granted, remaining, refill_at_ms }`.

### IReadinessPort — `ports/readiness_port.py`

| Method | Signature |
|---|---|
| `assess` | `(recipient: str) -> ReadinessScore` |

Wraps `ContextMonitor` from SessionState. Returns `ReadinessScore { idle_ms, cognitive_load, current_activity, stress_score, driving, in_meeting, topic }`. **READ-ONLY — mirrors ORCH-01.**

### IConsciencePort — `ports/conscience_port.py`

| Method | Signature |
|---|---|
| `evaluate` | `(envelope: ProactiveDeliveryEnvelope) -> ConsciencePolicy` |

Returns `ConsciencePolicy { allow: bool, band: GREEN|AMBER|RED|BLACK, reason: str }`. RED → escalate to L1+INLINE. BLACK → drop with audit. Mirrors M12.E4 `_run_conscience_gate`.

### IQuietHoursPort — `ports/quiet_hours_port.py`

| Method | Signature |
|---|---|
| `is_quiet` | `(recipient: str, now: float) -> QuietWindow` |
| `next_open_window` | `(recipient: str, now: float) -> float` |

Reads L3 routines. Returns `QuietWindow { active, ends_at_ms, allow_breakthrough_priorities: List[Priority] }`.

### IDeliveryPort — `ports/delivery_port.py`

| Method | Signature |
|---|---|
| `emit_fill` | `(envelope: ProactiveDeliveryEnvelope, decision: DeliveryDecision) -> None` |
| `emit_ambient` | `(envelope: ProactiveDeliveryEnvelope) -> None` |
| `emit_closure` | `(envelope_id: str, outcome: ClosureOutcome, correlation: Dict) -> None` |
| `emit_suppressed` | `(envelope_id: str, reason: SuppressionReason) -> None` |
| `emit_surface_chosen` | `(envelope_id: str, surface: SurfaceTier, latency_ms: int) -> None` |

Publishes to bus topics. `emit_fill` → `TOPIC_PROACTIVE_FILL` (existing). `emit_ambient` → `k1.proactive.ambient.v1` (new). All other topics: see §3.

### IDeltaEmitPort — `ports/delta_emit_port.py`

Same shape as orchestrator's. Service emits trace deltas only.

### `__init__.py` re-exports

8 ports + `OutboxEntryId`, `ClosureOutcome`, `SuppressionReason`, `SurfaceTier` enums.

---

## §2 Internal Architecture

### Core Services (1 service + 5 guards + 4 closure components)

```
ProactiveService (~600 lines target)
├── IngressLoop (~250 lines)
│   ├── normalizes incoming events to ProactiveDeliveryEnvelope
│   └── enriches with closure_policy + surface_hint defaults per source
├── DecisionPipeline (~400 lines)
│   └── Guards (5 ordered):
│       ├── ConscienceGuard          (PROAC-01) before_decide
│       ├── TTLGuard                 (PROAC-05) before_decide
│       ├── ReadinessGuard           (PROAC-03) decide
│       ├── AttentionBudgetGuard     (PROAC-02) decide
│       └── WeavePolicyNominator     (PROAC-04) after_decide
├── OutboxReplayer (~200 lines, asyncio task)
│   └── ticks every 30s — drain expired, drain session-opened DEFERs
├── ClosurePipeline (~500 lines)
│   ├── CorrelationWatcher  — envelope_id → ClosureContext map, outbox-backed
│   ├── ReplyClassifier      — turn → {ACCEPT, REJECT, DEFER, ANSWER, ACK, SILENT} (rule-based, NO LLM — PROAC-09)
│   ├── TimeoutReaper        — cron tick — applies on_timeout policy
│   └── ClosureEmitter       — publishes k1.proactive.loop.closed.v1
└── DigestAggregator (~150 lines)
    └── DIGEST surface — bundles outbox items into next-session-start digest
```

### Processing flow (mirror of OrchestratorService.mailbox_loop)

```
init()
  ├─ validate_ports → outbox crash recovery (replay PENDING/SCHEDULED)
  ├─ subscribe_events:
  │     k1.proactive.ingress.v1
  │     k0.curiosity.intent.v1
  │     k0.proactive.signal.v1
  │     k0.learning.advisory.v1
  │     k1.concierge.session.opened.v1
  │     k1.concierge.session.idle.v1
  │     k1.concierge.turn.completed.v1
  │     k1.memory.delta.v1                     (filtered by correlation.envelope_id)
  └─ asyncio.create_task(replay_loop + reaper_loop + correlation_loop)

ingress_loop → normalize → ProactiveDeliveryEnvelope → DecisionPipeline:
  ├─ ConscienceGuard:          BLACK → emit_suppressed(CONSCIENCE) → drop
  │                            RED   → upgrade to L1+INLINE_INTERRUPT, force allowed=[INLINE]
  ├─ TTLGuard:                 expired → emit_suppressed(TTL) → drop
  ├─ ReadinessGuard:           quiet hours + low priority → defer to next_open_window
  │                            high cognitive_load → strip INLINE_INTERRUPT from allowed
  │                            driving → strip WEAVE/INLINE, allow only AMBIENT/DEFER/DIGEST
  ├─ AttentionBudgetGuard:     try_spend(recipient)
  │                            denied → DEFER (schedule at refill_at_ms)
  │                            granted → continue
  └─ WeavePolicyNominator:     produce DeliveryDecision { allowed_surfaces, urgency, preferred }

→ outbox.persist(envelope, decision) → OutboxEntryId
→ if AMBIENT-only: delivery_port.emit_ambient(); auto-close as DELIVERED_AMBIENT
→ else:            delivery_port.emit_fill(envelope, decision)
                   correlation_watcher.register(envelope, on_timeout=closure_policy.on_timeout)
                   outbox.mark_emitted(...)

closure_loop:
  ├─ on k1.concierge.turn.completed.v1 with in_reply_to_envelope_ids:
  │     for each id → ReplyClassifier.classify(turn) → ClosureEmitter.emit(outcome)
  │                   outbox.mark_closed(...)
  ├─ on k1.memory.delta.v1 with correlation.envelope_id (L1 gap closure):
  │     ClosureEmitter.emit(ANSWERED) → outbox.mark_closed(...)
  └─ on TimeoutReaper tick:
        for entry in outbox.get_expired(now):
          dispatch closure_policy.on_timeout: REASK | DIGEST | DROP | ESCALATE
```

### Guard Pipeline (all extend `ProactiveGuard` ABC)

| Guard | Invariant | Hook | Decision Logic |
|---|---|---|---|
| ConscienceGuard | PROAC-01 | before_decide | RED→escalate, BLACK→drop+audit |
| TTLGuard | PROAC-05 | before_decide | now > created_at + ttl_ms → drop |
| ReadinessGuard | PROAC-03 | decide | quiet hours, cognitive_load, driving, in_meeting filter `allowed_surfaces` |
| AttentionBudgetGuard | PROAC-02 | decide | try_spend; denied → DEFER not DROP |
| WeavePolicyNominator | PROAC-04 | after_decide | Computes `preferred_surface` from intersection of `surface_hint.allowed`, ReadinessGuard's filtered `allowed_surfaces`, and source priority |

---

## §3 Loop Shapes (the closure-classification model)

Every envelope declares its **loop shape** at ingress time. The loop shape determines what counts as closure and what happens on silence.

| ID | Shape | Closure means | On silence | Examples |
|---|---|---|---|---|
| **L1** | Question→Answer (must close) | User reply produces a typed answer that updates a K0 record | REASK ×N (with backoff) → DIGEST → DROP | curiosity gap, HIL fallback, value-conflict |
| **L2** | Notification→Ack (should close) | Implicit ack (any next turn) OR explicit ("thanks/ok/snooze") | DIGEST on next session | workflow completion, prospective reminder, drift (low) |
| **L3** | Suggestion→Decision (may close) | ACCEPT/REJECT/DEFER reply | SILENT_TIMEOUT = soft reject (learning signal) — never re-ask | "want me to book?", "add Tuesday yoga to routine?" |
| **L4** | Ambient→No-reply (cannot close) | None — auto-closed on emit as DELIVERED_AMBIENT | nothing | digest, "you walked 12k steps" |

### Per-loop closure windows (locked)

| Loop | Window | Persists across session? |
|---|---|---|
| L1 | 24h | YES |
| L2 | session + 24h grace | YES |
| L3 | current session, 60s after present | NO — closes as SILENT_TIMEOUT on session end |
| L4 | N/A | N/A |

### REASK semantics (L1 only)

- Carries the same `correlation.gap_id` so K0 P03 doesn't double-count.
- Each REASK consumes a fresh attention-budget token (decision §5).
- Default `retry_max=2`, `retry_backoff_ms=86_400_000` (24h).
- After exhaustion → DIGEST roll-up, then DROP.

---

## §4 Surface Tiers (the presentation question)

Six surfaces. Source declares **allowed/preferred/forbidden**, ProactiveService computes **nominated**, Concierge's WeavePolicy resolves to **chosen**.

| Surface | Where it appears | When | Loop shapes |
|---|---|---|---|
| **INLINE_INTERRUPT** | Front actor pre-empts current turn, breaks into reply mid-stream | RED conscience, HIL blocking, safety advisory | L1 (RED only) |
| **WEAVE** | Front actor at next natural pause between turns (existing M8) | High-priority Q, time-sensitive notify | L1, L2 (time-sensitive) |
| **BATCH** | Bundled in WeaveBatcher's 500ms window as small-talk turn | Multiple low-priority items arriving together | L2, L3 |
| **DEFER** | Held; presented at next session boot or session-idle gap | Medium-priority, dense current convo | L1 (with backoff), L2, L3 |
| **DIGEST** | Rolled into periodic summary (daily/weekly check-in) | Low-priority, repeat REASKs, completed-while-away | L2, L4 |
| **AMBIENT** | Peripheral channel — UI badge/tray/status bar, never enters convo | Background insights, FYI, low-band drift | L4, L2-low |

### `surface_hint` defaults per source

| Source | Allowed | Preferred | Forbidden |
|---|---|---|---|
| Curiosity gap | WEAVE, DEFER, DIGEST | WEAVE | INLINE, AMBIENT |
| HIL fallback (blocking) | INLINE, WEAVE | INLINE | BATCH, DIGEST, AMBIENT |
| Workflow completion (high-value) | WEAVE, BATCH, DEFER, AMBIENT | WEAVE | INLINE, DIGEST |
| Workflow completion (low-value) | BATCH, DEFER, AMBIENT, DIGEST | AMBIENT | INLINE, WEAVE |
| Prospective reminder | WEAVE, BATCH | WEAVE | DIGEST, AMBIENT |
| Drift advisory (low) | DIGEST, AMBIENT | DIGEST | INLINE, WEAVE |
| Drift advisory (high, RED) | INLINE, WEAVE | WEAVE | AMBIENT, DIGEST |
| Suggestion (book/add routine) | WEAVE, DEFER | WEAVE | INLINE, DIGEST, AMBIENT |
| Ambient insight | AMBIENT only | AMBIENT | all others |
| Daily digest itself | DIGEST only | DIGEST | all others |

### Two-step decision (the contract with Concierge)

```
1. ProactiveService runs DecisionPipeline → DeliveryDecision {
       allowed_surfaces, preferred_surface, urgency_score,
       correlation, closure_policy
   }
2. publish TOPIC_PROACTIVE_FILL { envelope, decision }
3. Concierge WeavePolicy receives FILL, applies its own context:
       - Current FSM state (LISTENING / PRESENTING / THINKING)
       - Front actor occupancy
       - Live cognitive load score
       - Topic similarity to current convo
       - Politeness FTA assessment
   → resolves surface ∈ allowed_surfaces → executes presentation
4. Concierge emits k1.proactive.surface.chosen.v1
       → ProactiveService records latency_ms metric
```

**Service nominates; Concierge resolves.** Neither owns presentation alone. Service knows source/closure/budget; Concierge knows current cognitive moment.

### AMBIENT — new surface, new contract

- New topic `k1.proactive.ambient.v1 { envelope_id, summary, badge_kind, ttl_ms }`.
- Consumed by client UI tray/badge code (Layer 1/2), NOT by Front/Back actors.
- Concierge does not handle AMBIENT — service publishes directly. Front actor budget untouched.
- No correlation watcher registered. Auto-closed on emit as `DELIVERED_AMBIENT`.

### Loop × Surface matrix

| Loop | Surface | Closure handling |
|---|---|---|
| L1 | INLINE/WEAVE | Watcher; full closure expected |
| L1 | DEFER | Watcher persists across session boundary |
| L1 | DIGEST | Bundle with `gap_id` array; user replies to specific item |
| L2 | INLINE/WEAVE/BATCH/DEFER | Implicit/explicit ack |
| L2 | AMBIENT | Auto-closed as DELIVERED_AMBIENT |
| L3 | WEAVE/DEFER | Watcher; SILENT_TIMEOUT in window = soft reject |
| L3 | BATCH | Per-item watcher in bundle ("yes to A, no to B") |
| L4 | AMBIENT only | Auto-closed |

---

## §5 Types (`types.py`)

### Enums

```
SurfaceTier        = INLINE_INTERRUPT | WEAVE | BATCH | DEFER | DIGEST | AMBIENT
LoopShape          = L1_QUESTION | L2_NOTIFY | L3_SUGGEST | L4_AMBIENT
ClosureOutcome     = ANSWERED | ACK_IMPLICIT | ACK_EXPLICIT | ACCEPT | REJECT | DEFER
                   | SILENT_TIMEOUT | DELIVERED_AMBIENT | EXPIRED | DROPPED | REASKED
SuppressionReason  = CONSCIENCE | BUDGET | QUIET_HOURS | TTL | DUPLICATE | DEVICE_LOST
TimeoutAction      = REASK | DIGEST | DROP | ESCALATE
SourceKind         = WORKFLOW_COMPLETION | CURIOSITY_GAP | PROSPECTIVE_REMINDER
                   | DRIFT_ADVISORY | SUGGESTION | AMBIENT_INSIGHT | HIL_FALLBACK
                   | VALUE_CONFLICT | DIGEST_ROLLUP
Priority           = REALTIME | PROGRESS | BACKGROUND
ConscienceBand     = GREEN | AMBER | RED | BLACK
```

### Core dataclasses

```
ProactiveDeliveryEnvelope:
  envelope_id           str       # ULID
  source                SourceKind
  recipient_actor       str       # user-id or actor-id
  loop_shape            LoopShape
  priority              Priority
  sensitivity           ConscienceBand   # source-declared, ConscienceGuard may upgrade
  summary               str       # short presentation hint (NOT the rendered message)
  payload               Dict[str, Any]
  created_at_ms         int
  ttl_ms                int
  surface_hint          SurfaceHint
  closure_policy        ClosurePolicy
  correlation           Correlation       # gap_id?, run_id?, suggestion_id?, parent_envelope_id?
  trace_id              str

SurfaceHint:
  allowed               List[SurfaceTier]
  preferred             SurfaceTier
  forbidden             List[SurfaceTier]

ClosurePolicy:
  ack_required          bool
  closure_window_ms     int       # per-loop default
  retry_max             int
  retry_backoff_ms      int
  on_timeout            TimeoutAction
  digest_kind           Optional[str]    # which digest channel to roll into

Correlation:
  envelope_id           str
  gap_id                Optional[str]
  run_id                Optional[str]
  suggestion_id         Optional[str]
  parent_envelope_id    Optional[str]    # for REASK chain
  reask_count           int = 0

DeliveryDecision:
  allowed_surfaces      List[SurfaceTier]
  preferred_surface     SurfaceTier
  urgency_score         float            # 0..1
  budget_spent          int
  scheduled_for_ms      Optional[int]    # set when DEFERRED
  reason                str

OutboxEntry:
  entry_id              OutboxEntryId
  envelope              ProactiveDeliveryEnvelope
  decision              DeliveryDecision
  status                PENDING | SCHEDULED | EMITTED | CLOSED | EXPIRED | SUPPRESSED
  emitted_surface       Optional[SurfaceTier]
  closed_outcome        Optional[ClosureOutcome]
  emitted_at_ms         Optional[int]
  closed_at_ms          Optional[int]
  next_check_at_ms      int

ClosureContext:           # in-memory + outbox-backed
  envelope_id           str
  loop_shape            LoopShape
  expires_at_ms         int
  on_timeout            TimeoutAction
  recipient             str

ReadinessScore:
  idle_ms               int
  cognitive_load        float            # 0..1
  current_activity      str
  stress_score          float            # 0..1
  driving               bool
  in_meeting            bool
  topic                 str

BudgetState:
  remaining             int
  capacity              int
  refill_at_ms          int

QuietWindow:
  active                bool
  ends_at_ms            int
  allow_breakthrough_priorities  List[Priority]
```

---

## §6 Events (`events.py`)

### Emitted by ProactiveService

| Topic | Purpose |
|---|---|
| `k1.proactive.delivery.scheduled.v1` | Outbox persisted, awaiting emit window |
| `k1.proactive.delivery.emitted.v1` | FILL/AMBIENT pushed |
| `k1.proactive.surface.chosen.v1` | (mirrored from concierge for metrics) |
| `k1.proactive.loop.closed.v1` | `{ envelope_id, source, loop_shape, outcome, correlation, latency_ms }` — **single closure topic for K0 to subscribe once** |
| `k1.proactive.loop.timeout.v1` | `{ envelope_id, action: REASK\|DIGEST\|DROP }` |
| `k1.proactive.delivery.suppressed.v1` | `{ envelope_id, reason: CONSCIENCE\|BUDGET\|QUIET_HOURS\|TTL }` |
| `k1.proactive.fill.v1` | (existing — passthrough to FSM) |
| `k1.proactive.ambient.v1` | (NEW — UI tray/badge) |
| `k1.proactive.digest.ready.v1` | DigestAggregator emits when bundle is ready |

### Consumed

| Topic | Source |
|---|---|
| `k1.proactive.ingress.v1` | in-kernel producers (WorkflowSupervisor) |
| `k0.curiosity.intent.v1` | Bridge SSE |
| `k0.proactive.signal.v1` | Bridge SSE |
| `k0.learning.advisory.v1` | Bridge SSE |
| `k1.concierge.session.opened.v1` | Concierge — drain DEFER outbox + emit digests |
| `k1.concierge.session.idle.v1` | Concierge — present DEFERs |
| `k1.concierge.turn.completed.v1` | Concierge — closure correlation via `in_reply_to_envelope_ids` |
| `k1.memory.delta.v1` | Memory writer — L1 gap-resolution closure (filtered by `correlation.envelope_id`) |
| `k1.proactive.surface.chosen.v1` | Concierge — metrics |

---

## §7 Touchpoint changes (the only non-additive surfaces)

The service is **additive everywhere except two small contract changes**:

### Touchpoint A — Concierge stamps reply correlation

**Where:** `k1/concierge/session.py` (or wherever turn events are emitted).

**Change:**

1. Add session-state slot `last_proactive_envelope_ids: List[str]` (a list — BATCH delivers multiple).
2. On FSM transition `PROACTIVE_WAKE → DELIVERING → LISTENING`, append the envelope_ids being presented.
3. On next user turn, if slot non-empty AND turn is within `closure_window_ms`:
   - Stamp `in_reply_to_envelope_ids: List[str]` on `k1.concierge.turn.completed.v1`.
   - Clear slot after stamp.
4. On window expiry or unrelated turn, clear without stamping (becomes SILENT_TIMEOUT signal for L3).

This is the **only** contract change Concierge needs. Proactive service does NOT reach into Concierge state.

### Touchpoint B — WorkflowSupervisor publishes ingress

**Where:** `k1/orchestrator/workflows/workflow_supervisor.py` `complete_run()`, line ~232 (right after the existing `k1.orchestration.workflow.run_completed` emit).

**Change:** one additional `await self._delta.emit("k1.proactive.ingress.v1", { source: "workflow_completion", run_id, recipient_actor, summary, payload, ... }, trace)`.

The supervisor does **not** know ProactiveService exists. Pure bus contract.

### Touchpoint C — K0 listens for closure (Bridge round-trip)

**Where:** Bridge K1→K0 channel (already existing per `bridge_architecture.mmd`).

**Change:** K0 subscribes to `k1.proactive.loop.closed.v1`. On L1 ANSWERED → mark `st_learning_queue` row RESOLVED, update Bayesian anchor. On L3 SILENT_TIMEOUT → record as soft-reject signal for learning. No new Bridge plumbing — same existing K1→K0 pipe used by `memory.formed.v1`.

---

## §8 Cross-Component Connections

| # | Connection | Direction | Type crossing | Compatibility |
|---|---|---|---|---|
| 1 | Orchestrator → Proactive | bus only | `Dict` over `k1.proactive.ingress.v1` | ✅ no imports |
| 2 | Bridge SSE → Proactive | bus only | `Dict` over `k0.*.v1` topics | ✅ no imports |
| 3 | Proactive → Concierge | bus only | `Dict` over `k1.proactive.fill.v1` (existing) | ✅ no imports |
| 4 | Proactive → Client UI | bus only | `Dict` over `k1.proactive.ambient.v1` (NEW) | ✅ no imports |
| 5 | SessionState → Proactive | port (read-only) | `IReadinessPort` wraps `ISessionStateReader` | ✅ via `k1.fabric.ports` |
| 6 | Conscience → Proactive | port (read-only) | `IConsciencePort` | ✅ |
| 7 | Routines (L3) → Proactive | port (read-only) | `IQuietHoursPort` | ✅ |
| 8 | Memory writer → Proactive | bus only | `k1.memory.delta.v1` filtered | ✅ no imports |
| 9 | Concierge → Proactive | bus only | `k1.concierge.turn.completed.v1` | ✅ no imports |
| 10 | Proactive → K0 (closure) | bus only | `k1.proactive.loop.closed.v1` via Bridge | ✅ no imports |

**Hexagonal cleanliness target: zero peer-component imports** (matches Orchestrator's clean rating). All cross-component types come through `k1.fabric` or are bus `Dict`.

---

## §9 Factory + Config

### ProactiveFactory (`factory.py`)

Mirrors `OrchestratorFactory` exactly:

- `create_production(config, adapters_dict) -> ProactiveService`
- `create_standalone(config) -> ProactiveService`
- `create_for_testing(config) -> Tuple[ProactiveService, Dict]`

### ProactiveConfig (`config.py`)

| Group | Fields |
|---|---|
| Budget | `budget_capacity_per_day=3`, `budget_refill_window_hours=24`, `reask_costs_token=true` |
| Closure windows (ms) | `l1_window_ms=86_400_000`, `l2_window_ms=session_plus_24h`, `l3_window_ms=60_000` |
| Retry | `l1_retry_max=2`, `l1_retry_backoff_ms=86_400_000` |
| Timing | `replayer_tick_ms=30_000`, `reaper_tick_ms=60_000`, `correlation_buffer_size=500` |
| Surface | `ambient_default_ttl_ms=3_600_000`, `digest_kinds=["daily","weekly","session_open"]` |
| Quiet hours | `quiet_breakthrough_priorities=["REALTIME"]` |
| Outbox | `outbox_path`, `outbox_max_pending=10_000`, `outbox_purge_after_days=30` |
| Multi-device | `device_dedup_enabled=true`, `device_lease_ms=5_000` |
| Telemetry | `metrics_enabled=true`, `trace_sample_rate=1.0` |

---

## §10 Invariants (PROAC-01 .. PROAC-12)

| ID | Invariant | Enforcement |
|---|---|---|
| **PROAC-01** | Service never speaks directly to user — only publishes FILL/AMBIENT topics; FSM owns presentation | No string templating in service code |
| **PROAC-02** | Conscience gate runs before budget gate (RED message must not even cost a token) | DecisionPipeline guard order |
| **PROAC-03** | Attention budget is per-recipient global (one bucket for all sources) | `IAttentionBudgetPort` keyed by `recipient` only |
| **PROAC-04** | Outbox writes are durable before any "accepted" ack returns to producer | `outbox.persist()` is sync-fsync before publish |
| **PROAC-05** | TTL is checked at decide-time AND deliver-time | TTLGuard runs in pipeline + at outbox replay |
| **PROAC-06** | Multi-device dedup: only one device emits FILL per envelope_id | `loop.closed.v1` is dedup signal, all devices subscribe |
| **PROAC-07** | gap_id correlation: L1 closure publishes `loop.closed.v1` with full correlation so K0 marks gap RESOLVED | Mandatory `correlation.gap_id` for SourceKind=CURIOSITY_GAP |
| **PROAC-08** | Service never writes SessionState (read-only via IReadinessPort) | Mirror of ORCH-01 |
| **PROAC-09** | Service never makes LLM calls (rule-based ReplyClassifier only) | Mirror of ORCH-02; phrasing happens in Concierge Front actor |
| **PROAC-10** | All ingress sources funnel through one envelope contract — no source-specific shortcuts | IngressLoop is sole envelope constructor |
| **PROAC-11** | Every emitted envelope produces exactly one terminal `loop.closed.v1` event (no leaks, no duplicates) | OutboxReplayer + TimeoutReaper guarantee |
| **PROAC-12** | AMBIENT surface auto-closes on emit (no watcher); all other surfaces register a watcher | DecisionPipeline sets `register_watcher = surface != AMBIENT` |

---

## §11 Tree shape

```
k1/proactive/
├── ARCHITECTURE.md                       # generated from this whiteboard
├── __init__.py
├── config.py
├── events.py                             # topic constants + Emitted/Consumed lists
├── metrics.py
├── tracing.py
├── types.py
├── factory.py
├── ports/
│   ├── __init__.py
│   ├── ingress_port.py
│   ├── outbox_port.py
│   ├── attention_budget_port.py
│   ├── readiness_port.py
│   ├── conscience_port.py
│   ├── quiet_hours_port.py
│   ├── delivery_port.py
│   └── delta_emit_port.py
├── adapters/
│   ├── __init__.py
│   ├── ingress_bus_adapter.py
│   ├── outbox_sqlite_adapter.py          # mirrors HILLedgerAdapter
│   ├── attention_budget_memory_adapter.py
│   ├── readiness_sessionstate_adapter.py
│   ├── conscience_adapter.py
│   ├── quiet_hours_routines_adapter.py
│   ├── delivery_bus_adapter.py
│   └── delta_emit_adapter.py
├── service/
│   ├── __init__.py
│   ├── proactive_service.py              # the brain
│   ├── ingress_loop.py
│   ├── decision_pipeline.py
│   ├── outbox_replayer.py
│   └── digest_aggregator.py
├── guards/
│   ├── __init__.py                       # ProactiveGuard ABC
│   ├── conscience_guard.py
│   ├── ttl_guard.py
│   ├── readiness_guard.py
│   ├── attention_budget_guard.py
│   └── weave_policy_nominator.py
└── closure/
    ├── __init__.py
    ├── correlation_watcher.py
    ├── reply_classifier.py
    ├── timeout_reaper.py
    └── closure_emitter.py
```

---

## §12 Migration of existing code

| Existing | Action |
|---|---|
| `k1/concierge/scheduler/proactive_scheduler.py` | DEPRECATE after service ships; logic absorbed by `OutboxReplayer` + `DigestAggregator` |
| `k1/concierge/bus/builders.py::build_proactive_fill` | KEEP — service uses it via `IDeliveryPort` adapter |
| `k1/concierge/bus/topics.py::TOPIC_PROACTIVE_FILL` | KEEP — promoted to "shared" topic |
| `k1/concierge/fsm/interrupt_handler.py::ProactiveWakeHandler` | KEEP — receives FILL from service |
| `k1/concierge/session.py::397` (current `build_proactive_fill` call site) | MIGRATE — emit `k1.proactive.ingress.v1` instead; service handles fill emission |
| `k1/orchestrator/workflows/workflow_supervisor.py::232` | ADD `k1.proactive.ingress.v1` emit alongside existing `k1.orchestration.workflow.run_completed` |

---

## §13 Test Plan (initial slice — not full ~1,800 parity)

| Test file | Target |
|---|---|
| `tests/k1/proactive/test_ingress_loop.py` | All 4 source kinds normalize correctly |
| `tests/k1/proactive/test_decision_pipeline.py` | 5 guards in order; conscience-then-budget; readiness-strips-INLINE-when-driving |
| `tests/k1/proactive/test_outbox_sqlite.py` | Persist/replay/expire/correlate roundtrips, crash recovery |
| `tests/k1/proactive/test_correlation_watcher.py` | Per-loop closure windows, REASK chain, SILENT_TIMEOUT for L3 |
| `tests/k1/proactive/test_timeout_reaper.py` | REASK→DIGEST→DROP escalation, ESCALATE for RED |
| `tests/k1/proactive/test_surface_nomination.py` | All 9 source defaults produce correct allowed/preferred/forbidden |
| `tests/k1/proactive/test_loop_shapes.py` | L1/L2/L3/L4 closure semantics each |
| `tests/k1/proactive/test_factory.py` | `create_for_testing()` returns service + adapters dict |
| `tests/k1/proactive/test_workflow_producer_integration.py` | WorkflowSupervisor.complete_run → ingress envelope |
| `tests/k1/proactive/test_concierge_correlation_integration.py` | `in_reply_to_envelope_ids` stamping → closure |
| `tests/k1/proactive/test_invariants.py` | PROAC-01..12 each |

Test infra mirrors orchestrator: real in-memory adapters, no mocks, `script_*` helpers, `FrozenClock`, factory-first.

---

## §14 Phasing (suggested epic breakdown)

| Epic | Slice | Producers wired |
|---|---|---|
| **PROAC.E1** | Spine: types, ports, factory, config, ARCHITECTURE.md generated from this whiteboard | none |
| **PROAC.E2** | Adapters: outbox SQLite, attention budget, readiness, conscience, quiet hours, delivery bus | none |
| **PROAC.E3** | Service core: IngressLoop + DecisionPipeline + 5 guards | WorkflowSupervisor (touchpoint B) |
| **PROAC.E4** | Closure pipeline: CorrelationWatcher + ReplyClassifier + TimeoutReaper + ClosureEmitter | + Concierge touchpoint A |
| **PROAC.E5** | Surface nomination + AMBIENT topic + WeavePolicy contract | + Concierge `surface.chosen.v1` emission |
| **PROAC.E6** | DigestAggregator + session-open drain + REASK escalation | + K0 listens for `loop.closed.v1` (touchpoint C) |
| **PROAC.E7** | K0 SSE producer adapters: curiosity gap, prospective reminder, drift advisory | Bridge SSE consumer wiring |
| **PROAC.E8** | Multi-device dedup + invariant test sweep + chaos tests | none |

---

## §15 Open questions resolved (for the record)

| # | Question | Decision |
|---|---|---|
| 1 | Where does reply correlation live? | Concierge owns it; stamps `in_reply_to_envelope_ids` on turn events |
| 2 | Per-loop closure windows | L1=24h, L2=session+24h, L3=60s, L4=N/A |
| 3 | Closure event topology | Single topic `k1.proactive.loop.closed.v1` with `loop_shape` + `outcome` discriminators |
| 4 | L3 silence semantics | SILENT_TIMEOUT = soft reject; never re-ask suggestions (politeness theory) |
| 5 | REASK budget cost | Fresh token per REASK |
| 6 | Multi-device dedup signal | `loop.closed.v1` — all devices subscribe, dequeue local outbox copy |
| 7 | Sibling vs sub-package | `k1/proactive/` sibling to `k1/orchestrator/`, `k1/concierge/`, `k1/planner/` |
| 8 | ProactiveScheduler fate | DEPRECATE after migration |
| 9 | AMBIENT closure | Auto-close on emit as DELIVERED_AMBIENT (no watcher) |
| 10 | Service vs Concierge presentation responsibility | Service nominates surface; Concierge WeavePolicy resolves with live cognitive context |

---

## §16 K0 Active-Learning-Loop alignment (gap-fill from `0001-active-learning-loop.md`)

The K0 doc is detection-only per ADR-0001/0001c: K0 emits typed `CuriosityIntent` SSE envelopes; **all phrasing, action, and policy execution lives in K1.** Concierge's Front LLM is the **only** user-facing rendering intelligence in K1 (Planner is the only other LLM user; every other K1 service is a non-LLM actor — see `k1/concierge/concierge_unified.mmd`). Therefore:

- **Proactive Service is a non-LLM actor.** It owns ingress, gating, surface nomination, durable outbox, closure, REASK, federated feedback emission. It builds a structured `RenderRequest` and hands it to Concierge via FILL.
- **Concierge Front LLM is the renderer.** It consumes `RenderRequest`, applies persona, FTA framing, Constitutional critique-revise, ZPD scaffolding, and Socratic multi-step progression. It speaks to the user.

This collapses the earlier "Curiosity Agents Service" idea — that would have duplicated Concierge's Front LLM. Instead, the work splits into (a) extensions to this Proactive Service, (b) extensions to Concierge.

### §16.1 Six K0 SSE intent topics → one normalized envelope

K0 emits a **family** of typed topics, each with different `prompt_hints` shape. Proactive Service subscribes to all and normalizes to one envelope, preserving `intent_topic` + `prompt_hints` for downstream rendering.

| K0 SSE topic | K0 producer | `SourceKind` | Concierge render mode (Front LLM) |
|---|---|---|---|
| `curiosity.intent.detected.v1` | P03 entropy scanner | `CURIOSITY_GAP` | `RENDER_PROACTIVE_TEXT` |
| `curiosity.intent.visual.v1` | Visual novelty (DINOv2/BLIP-2) | `CURIOSITY_VISUAL` | `RENDER_PROACTIVE_MULTIMODAL_VISION` |
| `curiosity.intent.audio.v1` | Acoustic novelty (PANNs/AudioCLIP) | `CURIOSITY_AUDIO` | `RENDER_PROACTIVE_MULTIMODAL_AUDIO` |
| `curiosity.intent.counterfactual.v1` | SCM/causal engine | `COUNTERFACTUAL` | `RENDER_PROACTIVE_COUNTERFACTUAL` |
| `curiosity.intent.values.v1` | CRDT family value conflict | `VALUE_CONFLICT` | `RENDER_PROACTIVE_FAMILY_MEDIATION` (multi-recipient) |
| `curiosity.intent.simulation.v1` | Scenario Lab | `RELEASE_SIMULATION` | `RENDER_PROACTIVE_RELEASE_GATE` |

`SourceKind` enum (§5) extends with: `CURIOSITY_VISUAL`, `CURIOSITY_AUDIO`, `COUNTERFACTUAL`, `VALUE_CONFLICT`, `RELEASE_SIMULATION`, `STALE_ANCHOR_REVALIDATION`.

### §16.2 New responsibilities ADDED to Proactive Service

| # | Capability | Where it lands |
|---|---|---|
| **A1** | **Multi-recipient routing** — `recipients: List[str]` for CRDT family-conflict envelopes. Per-recipient outbox rows + per-recipient correlation watchers; closure aggregated under one `parent_envelope_id`. | §5 type extension |
| **A2** | **Child-safety GATE** (block-only, not language adjustment) | New `ChildSafetyGuard` between Conscience and TTL; reads recipient age/role from policy; hard-block forbidden topics for <13 (financial, medical, relationship-conflict, trauma); language adjustment is Concierge's job |
| **A3** | **Per-band consent gate** (distinct from global conscience) — RED/AMBER proactive questions require explicit per-band opt-in; user can deny RED proactive while still allowing RED user-initiated capabilities | New `IConsentPort.allows_proactive(recipient, band) -> bool`; consulted inside `ConscienceGuard` |
| **A4** | **Question history outbox extension** (analog of K0 `st_question_history`) — render text (post-Concierge), asked_at/answered_at, answer_text, user_satisfaction, led_to_kg_update, response_time_seconds, privacy_band; GDPR-deletable | New `IQuestionHistoryPort` (separate from outbox); Concierge emits `k1.proactive.rendered.v1 { envelope_id, rendered_text }` after Front LLM speaks → service appends |
| **A5** | **Federated feedback signal emission** — feature vector for K0 P21 federated curiosity learner | New topic `k1.proactive.feedback.signal.v1 { helpfulness_score, answer_latency_ms, follow_up_events, privacy_band_alignment, topic_similarity, time_of_day_norm, days_since_last_question }`; emitted on every `loop.closed.v1` |
| **A6** | **Topic-similarity input to ReadinessGuard** — wakes question when recent convo topic ≈ gap topic | New `ITopicSimilarityPort.score(recent_convo_text, intent.prompt_hints) -> float`; ReadinessGuard upgrades urgency when score>0.7 |
| **A7** | **`STALE_ANCHOR_REVALIDATION` source** — new `SourceKind` from K0 `p06.anchor.decay.v1`; carries `old_confidence` + `new_confidence`; closure outcomes extend with `ANSWERED_NO_CHANGE` (resets decay) and `ANSWERED_DRIFT_CONFIRMED` (resets anchor) | §5 enum extension; §6 outcome extension |
| **A8** | **Idempotency on K0 `intent_id`** — K0 may resend same intent if SSE delivery fails (offline replay). Dedup on `(intent_id, gap_id)` in addition to envelope_id ULID. | Outbox unique index `(intent_id, gap_id)` |
| **A9** | **Experiment port** — A/B per K0 §7.5 control (passive) vs treatment (proactive) groups | New `IExperimentPort.assignment(recipient) -> ExperimentArm`; consulted in IngressLoop; CONTROL arm → drop envelope + emit `k1.proactive.experiment.dropped.v1` for telemetry parity |
| **A10** | **Privacy-band tag carried end-to-end** | Envelope `privacy_band: GREEN/AMBER/RED` (separate from `sensitivity` ConscienceBand); routed into `IQuestionHistoryPort` for retention/GDPR class |

### §16.3 RenderRequest contract (the missing handoff to Concierge)

The service NEVER builds user-facing prose. It builds `RenderRequest` and embeds it in FILL. Concierge Front LLM consumes it.

```
RenderRequest:
  intent_topic           str             # e.g. curiosity.intent.visual.v1
  source_kind            SourceKind
  loop_shape             LoopShape
  render_mode            str             # RENDER_PROACTIVE_TEXT | _MULTIMODAL_VISION | _MULTIMODAL_AUDIO
                                         # | _COUNTERFACTUAL | _FAMILY_MEDIATION | _RELEASE_GATE
                                         # | _STALE_ANCHOR_REVALIDATE
  prompt_hints           Dict            # pass-through from K0 (caption, lever, candidates,
                                         # suggested_frame, bbox, scene_context, old_value, new_value)
  evidence_uri           Optional[str]   # for multimodal (image/audio asset)
  recipients             List[str]       # multi-recipient for VALUE_CONFLICT
  sensitivity            ConscienceBand  # ConscienceGuard outcome
  privacy_band           PrivacyBand     # GREEN | AMBER | RED
  pedagogical_hint       Dict            # bloom_level, scaffolding_needed, prior_engagement,
                                         # socratic_responsiveness   (read by service from per-recipient state cache)
  constitution_ref       str             # which family constitution profile to apply
  dialogue_plan          Optional[DialoguePlan]   # multi-step Socratic
  closure_window_ms      int             # so Concierge knows reply window
  surface_tier           SurfaceTier     # already nominated by service
  correlation            Correlation     # gap_id, intent_id, parent_envelope_id, reask_count
```

`summary` field on the envelope is downgraded to "≤120 char debug/log hint, never user-facing copy."

### §16.4 Multi-step Socratic dialogue (state, not prose, owned by service)

The K0 doc §3.5 / §9.3 require multi-turn Socratic flows: `OBSERVATION → ATTRIBUTION → COUNTEREXAMPLE → PLAN`.

- **State machine owned by Proactive Service** (closure pipeline extension) — `dialogue_plan_id` groups N envelopes; each user reply triggers next step's envelope; closure only when plan terminal step reached OR user disengages OR TTL expires.
- **Step rendering owned by Concierge Front LLM** — receives `RenderRequest.dialogue_plan` containing current step + plan history; LLM generates each step's question with full Socratic context.
- **DialoguePlan type:**

```
DialoguePlan:
  plan_id               str
  steps                 List[DialogueStep]      # OBSERVATION, ATTRIBUTION, COUNTEREXAMPLE, PLAN
  current_step_idx      int
  history               List[DialogueTurn]      # {step_idx, rendered_question, user_reply, classified_outcome}
  branch_strategy       LINEAR | CONDITIONAL    # CONDITIONAL: ZPD-driven step skip
  max_steps             int = 4
  plan_ttl_ms           int = 86_400_000

DialogueStep:
  move                  OBSERVATION | ATTRIBUTION | COUNTEREXAMPLE | PLAN
  template_ref          str                     # which Concierge prompt template
  required_outcome      ClosureOutcome | None   # if reached, plan completes early
```

- **Closure semantics:** `loop.closed.v1` fires at plan termination with aggregated `outcomes: List[ClosureOutcome]`. Per-step replies emit `k1.proactive.dialogue.step.completed.v1` for analytics but do NOT close the loop.
- **REASK semantics inside a plan:** if user disengages mid-plan, REASK starts plan over OR resumes at last step (per `branch_strategy.resume_policy`).

### §16.5 Concierge extensions REQUIRED (upstream dependencies on this service)

These are NOT in `k1/proactive/`; they are amendments to Concierge that the service depends on. Tracked here so the team builds both halves coherently. Detailed design lives in `k1/concierge/concierge_unified.mmd` updates (out of scope for this whiteboard, but enumerated).

| # | Concierge change | Why |
|---|---|---|
| **C1** | New Front LLM **prompt modes** — `RENDER_PROACTIVE_TEXT`, `RENDER_PROACTIVE_MULTIMODAL_VISION`, `RENDER_PROACTIVE_MULTIMODAL_AUDIO`, `RENDER_PROACTIVE_COUNTERFACTUAL`, `RENDER_PROACTIVE_FAMILY_MEDIATION`, `RENDER_PROACTIVE_RELEASE_GATE`, `RENDER_PROACTIVE_STALE_ANCHOR_REVALIDATE` (additions to existing 10) | One per `render_mode`; consume `RenderRequest`; ILLMPort VISION capability already declared, so multimodal modes are wiring not new infra |
| **C2** | New cognitive tool `critique_against_constitution(rendered_text, constitution_ref) -> CritiqueResult` — Front LLM self-critique-revise loop per K0 §3.6 | Constitutional AI critique-revise lives where the LLM lives; service supplies `constitution_ref`, Front loops until aligned or suppresses |
| **C3** | New SessionState section `pedagogical_model` (per-recipient: bloom_level 1–6, scaffolding_needed bool, socratic_responsiveness 0–1, last_updated_at) | Front reads to choose phrasing complexity; updated by Concierge on each user turn outcome (rule-based, no LLM) |
| **C4** | New SessionState section `question_render_log` (durable trail of rendered text, used for post-render emission to service's `IQuestionHistoryPort`) | Privacy/GDPR; analytics; concierge already single-writer to SS per ADR-0017 |
| **C5** | New emission `k1.proactive.rendered.v1 { envelope_id, rendered_text, render_mode, latency_ms }` after Front speaks | Service consumes → appends to question history; closes the analytics loop |
| **C6** | FSM extension: optional sub-state under `DELIVERING` for **multi-step Socratic dialogue** (`SOCRATIC_STEP`) — re-enters with `dialogue_plan_id` slot in session state; on user reply, FSM consults plan state, transitions back to DELIVERING for next step OR LISTENING on plan termination | Concierge already manages turn context — only it can natively progress multi-step dialogues |
| **C7** | FSM extension: `last_proactive_envelope_ids: List[str]` slot (already in §7.A) — list (not single) because BATCH delivery presents multiple; carries multi-recipient ids when applicable | Reply correlation back-channel |
| **C8** | Front LLM **politeness/FTA framing** parameterized by `RenderRequest.sensitivity` + `privacy_band` (Brown-Levinson levels: bald-on-record / positive / negative / off-record) | Brown-Levinson FTA mitigation per K0 §3.7; pure prompt-template work |
| **C9** | **Child-safety language adjustment** when `recipients[i].age < 13` — age-appropriate vocabulary, parental-consent acknowledgement; topic blocking is service's job (A2), tone is Concierge's | Both halves needed — service blocks forbidden topics, Concierge softens allowed ones |

### §16.6 Updated event topology

**Emitted by Proactive Service** (additions to §6):

| Topic | Purpose |
|---|---|
| `k1.proactive.feedback.signal.v1` | Federated feedback feature vector → K0 P21 |
| `k1.proactive.dialogue.step.completed.v1` | Per-step Socratic step closure (analytics; not loop closure) |
| `k1.proactive.experiment.dropped.v1` | A/B control-arm telemetry parity |
| `k1.proactive.consent.denied.v1` | Per-band consent gate triggered (audit) |
| `k1.proactive.child_safety.blocked.v1` | Child-safety guard triggered (audit) |

**Consumed by Proactive Service** (additions to §6):

| Topic | Source |
|---|---|
| `curiosity.intent.detected.v1` | Bridge SSE — text gap |
| `curiosity.intent.visual.v1` | Bridge SSE — visual novelty |
| `curiosity.intent.audio.v1` | Bridge SSE — acoustic novelty |
| `curiosity.intent.counterfactual.v1` | Bridge SSE — SCM/causal |
| `curiosity.intent.values.v1` | Bridge SSE — CRDT conflict |
| `curiosity.intent.simulation.v1` | Bridge SSE — Scenario Lab |
| `p06.anchor.decay.v1` | Bridge SSE — stale anchor revalidation |
| `k1.proactive.rendered.v1` | Concierge — appends rendered text to question history |

### §16.7 Updated invariants (additions to §10)

| ID | Invariant | Enforcement |
|---|---|---|
| **PROAC-13** | Service NEVER renders user-facing prose. All user copy comes from Concierge Front LLM via `RenderRequest`. | Code review + lint rule banning string templating in `k1/proactive/` |
| **PROAC-14** | Constitutional critique-revise loop runs in Concierge Front LLM, not service. Service supplies `constitution_ref`. | Mirror of PROAC-09 |
| **PROAC-15** | Child-safety **block** is service's job; child-safety **language adjustment** is Concierge's job. Both required. | A2 + C9 paired |
| **PROAC-16** | Per-band consent gate is distinct from global conscience gate — user may deny RED proactive while allowing RED user-initiated. | A3 — separate `IConsentPort` |
| **PROAC-17** | Idempotency on `(intent_id, gap_id)` in addition to envelope_id ULID. | A8 — outbox unique index |
| **PROAC-18** | Multi-step Socratic dialogue state lives in service outbox; per-step rendering is Concierge's. Closure fires only at plan termination. | A1 of §16.4; §16.5 C6 |
| **PROAC-19** | Federated feedback signal emitted on EVERY `loop.closed.v1`, including SILENT_TIMEOUT and DELIVERED_AMBIENT (silence is data per K0 §3.6). | A5 |
| **PROAC-20** | Question history outbox is GDPR-deletable; rendered text retained per `privacy_band` retention class. | A4 + A10 |

### §16.8 Updated tree shape (additions to §11)

```
k1/proactive/
├── ports/
│   ├── consent_port.py                   # A3 — IConsentPort.allows_proactive(recipient, band)
│   ├── topic_similarity_port.py          # A6 — ITopicSimilarityPort
│   ├── question_history_port.py          # A4 — IQuestionHistoryPort
│   └── experiment_port.py                # A9 — IExperimentPort
├── adapters/
│   ├── consent_adapter.py
│   ├── topic_similarity_embedding_adapter.py
│   ├── question_history_sqlite_adapter.py
│   └── experiment_assignment_adapter.py
├── guards/
│   └── child_safety_guard.py             # A2 — between Conscience and TTL
├── service/
│   └── dialogue_plan_progressor.py       # §16.4 — multi-step Socratic state
└── closure/
    └── federated_signal_emitter.py       # A5 — k1.proactive.feedback.signal.v1
```

### §16.9 Updated phasing (additions to §14)

| Epic | Slice | Note |
|---|---|---|
| **PROAC.E9** | RenderRequest contract + 7 Concierge prompt modes (C1) + post-render emission (C5) | Paired Concierge work |
| **PROAC.E10** | Per-band consent gate (A3) + child-safety guard (A2) + child-safety language (C9) | Paired |
| **PROAC.E11** | Question history outbox (A4) + privacy_band (A10) + GDPR delete | Standalone |
| **PROAC.E12** | Multi-step Socratic DialoguePlan progressor (§16.4) + Concierge SOCRATIC_STEP sub-state (C6) + Constitutional critique tool (C2) | Paired — biggest slice |
| **PROAC.E13** | Federated feedback signal emitter (A5) + ITopicSimilarityPort (A6) + IExperimentPort (A9) + STALE_ANCHOR_REVALIDATION (A7) | K0 P21 + federated learner enabled |
| **PROAC.E14** | Multimodal RenderRequest passthrough (C1 vision/audio modes) + multi-recipient routing (A1) for VALUE_CONFLICT | Pairs with K0 §9.2 + §9.4 producers |
| **PROAC.E15** | Idempotency on intent_id (A8) + per-recipient pedagogical_model SS section (C3) + question_render_log SS section (C4) | Cleanup + analytics polish |

### §16.10 Open question resolutions (additions to §15)

| # | Question | Decision |
|---|---|---|
| 11 | Where does Constitutional critique-revise loop live? | Concierge Front LLM (PROAC-14). Service supplies `constitution_ref` only. |
| 12 | Where do specialized "agents" (visual, counterfactual, family mediator) live? | Collapsed to Concierge prompt-mode table (C1). No separate K1 agent service — would duplicate Front LLM. |
| 13 | Where does multi-step Socratic dialogue state live? | Service outbox + closure pipeline (state). Concierge Front LLM (rendering). FSM SOCRATIC_STEP sub-state (progression). |
| 14 | Multi-recipient envelopes — one outbox row or N? | N rows (per-recipient watcher) sharing `parent_envelope_id`; closure aggregates. |
| 15 | A/B control arm — drop entirely or just suppress delivery? | Drop entirely + emit `experiment.dropped.v1` for telemetry parity. |
| 16 | Federated signal — every closure or only ANSWERED? | Every closure including SILENT_TIMEOUT and DELIVERED_AMBIENT (PROAC-19). Silence is data. |
| 17 | Question history retention | Per `privacy_band`: GREEN=2y, AMBER=180d, RED=30d default; configurable per family; GDPR-deletable. |
| 18 | Child <13 RED-band proactive | Hard-block at service A2; never reaches Concierge. |
| 19 | `summary` field's role on envelope | Downgraded to ≤120-char debug/log hint, never user-facing copy. |

---

## §17 Next step

This whiteboard is the source of truth. Next deliverable: generate `k1/proactive/ARCHITECTURE.md` from §1–§10 + §16 (matching the §-structure of `k1/orchestrator/ARCHITECTURE.md`), then start PROAC.E1.

The Concierge extensions (§16.5 C1–C9) will be tracked as amendments to `k1/concierge/concierge_unified.mmd` and paired into the matching epics in §16.9. They are **not** a separate service — they are extensions to the existing user-facing Concierge.
