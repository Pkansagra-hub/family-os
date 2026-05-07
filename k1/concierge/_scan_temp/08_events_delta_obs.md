# 08 — Events, Delta, and Obs Subsystem Scan

> Scanned: 23 Python files (10 events, 9 delta, 4 obs)
> Scope: `k1.concierge.events`, `k1.concierge.delta`, `k1.concierge.obs`

---

## A. EVENTS SUBSYSTEM (10 files)

### A.1 `events/__init__.py` — Package Entrypoint

**Purpose:** Re-exports core event infrastructure for V3 canonical event schemas. Defines the "16 canonical event types" used across the K1 POC.

**Public API:**
- `CanonicalEventMeta` — base dataclass for all events
- `validate_canonical_metadata` — field presence validator
- `EVENT_SCHEMA_REGISTRY` — event_type → class mapping
- `validate_event` — full schema validation
- `validate_event_chain` — causation chain integrity

**Submodule Organization:**
| Submodule | Domain |
|---|---|
| `base` | CanonicalEventMeta + validation utilities |
| `conversation` | UserInputReceived, IntentArbitrated, DeadLettered, ResponseFinalDecided, Phase1Classified, TaskRouted |
| `task` | TaskCreated, TaskLeased, TaskProgressed, TaskCompleted, TaskFailed, TaskCancelled |
| `hitl` | HILRequested, HILResolved, TaskSuspended, TaskResumed + M6 lifecycle events |
| `weave` | WeaveCandidateArrived, WeaveDecisionMade, WeaveEmitted, WeaveMetricsEvent |
| `mutation` | TurnMutationSummary |
| `pool` | BackPool worker/lease/dependency events (7 classes) |
| `registry` | event_type → class mapping + deserialization |
| `validator` | Runtime schema + causation chain validation |

**Cross-component imports:** None from this file (all intra-package).

---

### A.2 `events/base.py` — CanonicalEventMeta Base Class

**Purpose:** Defines the V3 canonical event envelope metadata. Every V3 event payload extends `CanonicalEventMeta`. The 11 canonical metadata fields provide correlation, causation tracking, and schema versioning.

**Key Design Decision:** Event metadata is SEPARATE from bus Envelope transport metadata. The docstring explicitly maps:
- `Envelope.envelope_id` ≠ `event_id` (transport vs domain)
- `Envelope.cognitive_trace_id` → `correlation_id`
- `Envelope.parent_id` ≠ `causation_id` (bus ordering vs domain cause)
- `Envelope.created_ns` ≠ `ts_utc` (monotonic vs wall clock)
- `Envelope.sequence` ≠ ledger seq (bus gap detection vs session order)

**Constants:**
```python
CANONICAL_REQUIRED_FIELDS: frozenset[str]  # 8 required fields:
    # event_id, event_type, session_id, correlation_id,
    # causation_id, actor, ts_utc, payload_schema_version
```

**Classes:**

#### `CanonicalEventMeta` (dataclass)
Base class for all V3 canonical events.

| Field | Type | Default | Notes |
|---|---|---|---|
| `event_type` | `str` | `""` | Subclasses set as class-level default |
| `session_id` | `str` | `""` | Session scope |
| `correlation_id` | `str` | `""` | From Envelope.cognitive_trace_id |
| `causation_id` | `str` | `""` | Event that CAUSED this event |
| `parent_event_id` | `str` | `""` | Logical parent (domain hierarchy) |
| `task_id` | `str` | `""` | Task scope (empty for conversation-level) |
| `actor` | `str` | `""` | "front", "back", "fsm", "arbiter", "system" |
| `priority` | `int` | `1` | 0=URGENT .. 3=BACKGROUND |
| `payload_schema_version` | `str` | `"1.0.0"` | Semver |
| `event_id` | `str` | `uuid4()` | Auto-generated |
| `ts_utc` | `str` | `_utcnow_iso()` | Auto-generated ISO 8601 |

**Key Methods:**
- `to_payload() -> dict[str, Any]` — Serializes all canonical + subclass fields to dict
- `from_payload(cls, data) -> CanonicalEventMeta` — Deserializes from dict

**Functions:**
- `validate_canonical_metadata(payload: dict) -> (bool, list[str])` — Validates 8 required fields present/non-empty. `causation_id` and `correlation_id` allowed empty (root events / uncorrelated).
- `from_envelope(envelope, actor, causation_id=None) -> dict` — Extracts canonical metadata seed from a bus Envelope. Returns dict of kwargs for CanonicalEventMeta constructors.

**Cross-component imports:** None (stdlib only: uuid, dataclasses, datetime).

**Error handling:** Validation returns tuple `(is_valid, error_list)` — never raises.

---

### A.3 `events/conversation.py` — Conversation Events (4 + 2 M10 events)

**Purpose:** V3 canonical conversation-level event schemas.

**Classes:**

#### `UserInputReceived(CanonicalEventMeta)`
- `event_type = "conversation.user_input.received"` (init=False)
- Topic: `k1.session.user.input.v1`
- Fields: `text: str`, `input_type: str = "text"`, `device_id: str`, `raw_input: str`
- Root event of causal chains

#### `IntentArbitrated(CanonicalEventMeta)`
- `event_type = "conversation.intent.arbitrated"` (init=False)
- Topic: future `k1.session.intent.arbitrated.v1` (M4)
- Fields: `intent_class: str`, `confidence: float`, `target_task_id: str`, `routing_metadata: dict`
- Schema only; M4 implementation

#### `DeadLettered(CanonicalEventMeta)`
- `event_type = "conversation.dead_lettered"` (init=False)
- Topic: future `k1.internal.dead_letter.v1` (M2)
- Fields: `original_event: dict`, `reason: str`, `fsm_state_at_rejection: str`, `original_topic: str`
- Reasons: invalid_transition, orphan, expired

#### `ResponseFinalDecided(CanonicalEventMeta)`
- `event_type = "conversation.response_final.decided"` (init=False)
- M2 E2.5.4: Records decide_response_final() pure-function decision
- Fields: `decision_action: str`, `target_state: str`, `has_pending_results: bool`, `has_active_tasks: bool`, `emit_turn_completed: bool`, `schedule_weave: bool`, `entry_type: str`

#### `Phase1Classified(CanonicalEventMeta)` — M10 E10.3.4
- `event_type = "k1.phase1.classified.v1"` (init=False)
- Fields: `turn_number: int`, `complexity_tier: str`, `intent_primary: str`, `domain_primary: str`, `safety_band: str`, `emotion_primary: str`, `classification_latency_ms: float`, `is_degraded: bool`
- Observability event for tracing/dashboards

#### `TaskRouted(CanonicalEventMeta)` — M10 E10.3.4
- `event_type = "k1.task.routed.v1"` (init=False)
- Fields: `task_id: str`, `assigned_tier: str`, `routing_path: str`, `budget_limit: int`

**Cross-component imports:** `k1.concierge.events.base` only.

---

### A.4 `events/hitl.py` — HITL Events (4 M1 + 4 M6 events)

**Purpose:** V3 canonical HITL (human-in-the-loop) event schemas. Two layers:
1. **M1 events** (HILRequested/HILResolved/TaskSuspended/TaskResumed) — Back↔Front relay events on `k1.hil.*` topics
2. **M6 lifecycle events** (HITLRequestedEvent/HITLResolvedEvent/HITLTimedOutEvent/HITLBlockedRedEvent) — Observability/audit events on `k1.hitl.*` topics

**Causation chain:**
```
Back needs HITL -> hil.requested (causation) -> task.suspended
User answers    -> hil.resolved  (causation) -> task.resumed
```

**M1 Classes:**

#### `HILRequested(CanonicalEventMeta)`
- `event_type = "hil.requested"` | Topic: `k1.hil.request.v1`
- Fields: `hil_type: str` (clarification/approval/selection), `question: str`, `options: list[dict]`, `context: dict`, `side_effects: list[str]`, `safety_band: str = "GREEN"`, `timeout_s: float = 60.0`, `max_rounds: int = 2`

#### `HILResolved(CanonicalEventMeta)`
- `event_type = "hil.resolved"` | Topic: `k1.hil.response.v1`
- Fields: `resolution: dict`, `resolution_type: str = "selection"`, `elapsed_s: float`, `raw_user_text: str`

#### `TaskSuspended(CanonicalEventMeta)`
- `event_type = "task.suspended"` | Topic: `k1.orchestration.task.suspended.v1`
- Fields: `suspension_type: str`, `hil_request_event_id: str`, `suspension_count: int = 1`, `has_react_history: bool`, `react_history_len: int`

#### `TaskResumed(CanonicalEventMeta)`
- `event_type = "task.resumed"` | Topic: `k1.orchestration.task.resume.v1`
- Fields: `hil_resolved_event_id: str`, `resume_instruction: str`, `has_resume_context: bool`

**M6 Lifecycle Classes (observability/audit):**

#### `HITLRequestedEvent(CanonicalEventMeta)` — M6 E6.3.1
- `event_type = "hitl.lifecycle.requested"`
- Fields: `pending_hil_id: str`, `hil_type: str`, `parent_task_id: str`, `safety_band: str = "GREEN"`, `hil_deadline_ms: int`, `resume_token: str`, `device_id: str`

#### `HITLResolvedEvent(CanonicalEventMeta)` — M6 E6.3.2
- `event_type = "hitl.lifecycle.resolved"`
- Fields: `pending_hil_id: str`, `hil_type: str`, `parent_task_id: str`, `decision_branch: str = "clarified"`, `has_merged_params: bool`, `device_id: str`
- Decision branches: clarified / approved / approved_with_mods / cancelled / selected

#### `HITLTimedOutEvent(CanonicalEventMeta)` — M6 E6.3.3
- `event_type = "hitl.lifecycle.timed_out"`
- Fields: `pending_hil_id: str`, `hil_type: str`, `parent_task_id: str`, `timeout_ms: int`, `elapsed_ms: int`
- Triggers auto-cancel of parent task

#### `HITLBlockedRedEvent(CanonicalEventMeta)` — M6 E6.3.4
- `event_type = "hitl.lifecycle.blocked_red"`
- Fields: `capability_name: str`, `safety_band: str = "RED"`, `reason: str = "red_band_blocked"`
- RED-band capability blocked — no HILSubTask created

**Deprecates:** `poc/k1_poc/protocols/suspension_events.py`, `poc/k1_poc/protocols/hitl.py`

**Cross-component imports:** `k1.concierge.events.base` only.

---

### A.5 `events/task.py` — Task Lifecycle Events (6 classes)

**Purpose:** V3 canonical task lifecycle schemas.

#### `TaskCreated(CanonicalEventMeta)`
- `event_type = "task.created"` | Topic: `k1.orchestration.task.dispatch.v1`
- Fields: `action: str`, `depends_on: list[str]`, `dispatch_context: dict`

#### `TaskLeased(CanonicalEventMeta)`
- `event_type = "task.leased"` | Topic: future M7
- Fields: `worker_id: str`, `lease_expires_at: str`

#### `TaskProgressed(CanonicalEventMeta)`
- `event_type = "task.progressed"`
- Fields: `progress_pct: int`, `status_message: str`, `findings_so_far: dict`

#### `TaskCompleted(CanonicalEventMeta)`
- `event_type = "task.completed"` | Topic: `k1.orchestration.task.complete.v1`
- Fields: `result_data: dict`, `action: str`, `tool_calls_count: int`, `elapsed_ms: int`

#### `TaskFailed(CanonicalEventMeta)`
- `event_type = "task.failed"` | Topic: `k1.orchestration.task.failed.v1`
- Fields: `reason: str`, `error_code: str`, `completed_before_cancel: bool`, `tool_calls_completed: int`

#### `TaskCancelled(CanonicalEventMeta)`
- `event_type = "task.cancelled"` | Topic: `k1.orchestration.task.cancel.v1`
- Fields: `reason: str = "user_requested"`, `new_task_id: str`, `cancel_reason: str`, `had_token: bool`, `completed_before_cancel: bool`

**Deprecates:** `poc/k1_poc/protocols/cancel_events.py`

**Cross-component imports:** `k1.concierge.events.base` only.

---

### A.6 `events/mutation.py` — Turn Mutation Summary Event

**Purpose:** M4 E4.5.4 — Captures per-turn mutation statistics from DirectWriterAdapter. Appended to ledger at turn completion.

#### `TurnMutationSummary(CanonicalEventMeta)`
- `event_type = "mutation.turn_summary"`
- Emitted via ledger, NOT bus
- Fields: `turn_number: int`, `approved_count: int`, `rejected_count: int`, `failed_count: int`, `by_section: dict`, `by_rejection_reason: dict[str, int]`, `total_bytes_delta: int`, `total_duration_ms: float`, `device_id: str | None` (M5 E5.5.6)

**Cross-component imports:** `k1.concierge.events.base` only.

---

### A.7 `events/pool.py` — BackPool/Lease Lifecycle Events (7 classes)

**Purpose:** M7 E7.5.1 (5 events) + M7 E7.5.4 (2 dependency events). Pool worker lifecycle and task lease observability.

**Worker Lifecycle:**

#### `BackPoolWorkerAcquiredEvent(CanonicalEventMeta)`
- `event_type = "pool.worker.acquired"` | Topic: `k1.backpool.worker.acquired.v1`
- Fields: `worker_id: str`, `pool_size: int = 3`, `active_workers: int`, `session_id: str`

#### `BackPoolWorkerReleasedEvent(CanonicalEventMeta)`
- `event_type = "pool.worker.released"` | Topic: `k1.backpool.worker.released.v1`
- Fields: `worker_id: str`, `pool_size: int = 3`, `active_workers: int`, `release_reason: str = "completed"`

**Lease Lifecycle:**

#### `TaskLeasedEvent(CanonicalEventMeta)`
- `event_type = "pool.task.leased"` | Topic: `k1.backpool.task.leased.v1`
- Fields: `worker_id: str`, `lease_id: str`, `lease_ttl_s: int = 300`, `expires_at_ns: int`, `pool_size: int = 3`, `active_workers: int`

#### `TaskLeaseExpiredEvent(CanonicalEventMeta)`
- `event_type = "pool.task.lease_expired"` | Topic: `k1.backpool.task.leased.v1` (sub-type)
- Fields: `worker_id: str`, `lease_id: str`, `elapsed_s: float`, `renewals_used: int`, `hard_killed: bool`

#### `TaskLeaseRenewedEvent(CanonicalEventMeta)`
- `event_type = "pool.task.lease_renewed"` | Topic: `k1.backpool.task.leased.v1` (sub-type)
- Fields: `worker_id: str`, `lease_id: str`, `renewal_count: int`, `new_expires_at_ns: int`, `extension_s: int`

**Dependency Ordering (M7 E7.5.4):**

#### `TaskDeferredEvent(CanonicalEventMeta)`
- `event_type = "pool.task.deferred"` (internal, ledger only)
- Fields: `depends_on: str`, `queue_depth: int`

#### `DependencyFailedEvent(CanonicalEventMeta)`
- `event_type = "pool.task.dependency_failed"` (internal, ledger only)
- Fields: `depends_on: str`, `reason: str`

**Cross-component imports:** `k1.concierge.events.base` only.

---

### A.8 `events/weave.py` — Weave Events (3 + 1 metrics event)

**Purpose:** V3 canonical weave event schemas for result weaving into conversation.

#### `WeaveCandidateArrived(CanonicalEventMeta)`
- `event_type = "conversation.weave.candidate"` | Topic: `k1.orchestration.task.complete.v1` (shared with TaskCompleted)
- Fields: `task_description: str`, `result_data: dict`, `completed_at_ns: int`

#### `WeaveDecisionMade(CanonicalEventMeta)`
- `event_type = "conversation.weave.decided"` | Topic: `k1.internal.weave.batch.v1`
- Fields: `candidate_event_id: str`, `decision: str` (immediate/batch/defer/digest/suppress), `reason: str`, `fsm_state: str`, `batch_window_ms: int`, `signal_snapshot: dict` (M8 E8.2.4), `urgency_override: bool` (M8 E8.2.4), `emotional_gate_applied: bool` (M8 E8.2.4), `fallback_used: bool`

#### `WeaveEmitted(CanonicalEventMeta)`
- `event_type = "conversation.weave.emitted"` | Topic: `k1.response.final.v1`
- Fields: `candidate_event_ids: list[str]`, `response_text_preview: str`, `delivery_mode: str = "immediate"`

#### `WeaveMetricsEvent(CanonicalEventMeta)` — M8 E8.5.1
- `event_type = "metrics.weave.session"`
- Fields: `weave_count: int`, `digest_count: int`, `defer_count: int`, `suppress_count: int`, `avg_weave_latency_ms: float`, `user_acknowledged_rate: float`, `fallback_count: int`
- Emitted at session end with aggregate weave metrics

**Cross-component imports:** `k1.concierge.events.base` only.

---

### A.9 `events/registry.py` — Event Type Registry

**Purpose:** Maps `event_type` strings to canonical dataclass classes. Separate from BUILDERS because `event_type` (domain) ≠ topic (transport).

**Registry (EVENT_TYPE_REGISTRY):** 24 entries total

| Category | event_type | Class |
|---|---|---|
| Conversation (4) | `conversation.user_input.received` | `UserInputReceived` |
| | `conversation.intent.arbitrated` | `IntentArbitrated` |
| | `conversation.dead_lettered` | `DeadLettered` |
| | `conversation.response_final.decided` | `ResponseFinalDecided` |
| Task (6) | `task.created` | `TaskCreated` |
| | `task.leased` | `TaskLeased` |
| | `task.progressed` | `TaskProgressed` |
| | `task.completed` | `TaskCompleted` |
| | `task.failed` | `TaskFailed` |
| | `task.cancelled` | `TaskCancelled` |
| HITL (4) | `hil.requested` | `HILRequested` |
| | `hil.resolved` | `HILResolved` |
| | `task.suspended` | `TaskSuspended` |
| | `task.resumed` | `TaskResumed` |
| Weave (3) | `conversation.weave.candidate` | `WeaveCandidateArrived` |
| | `conversation.weave.decided` | `WeaveDecisionMade` |
| | `conversation.weave.emitted` | `WeaveEmitted` |
| Weave Metrics (1) | `metrics.weave.session` | `WeaveMetricsEvent` |
| Mutation (1) | `mutation.turn_summary` | `TurnMutationSummary` |
| BackPool (7) | `pool.worker.acquired` | `BackPoolWorkerAcquiredEvent` |
| | `pool.worker.released` | `BackPoolWorkerReleasedEvent` |
| | `pool.task.leased` | `TaskLeasedEvent` |
| | `pool.task.lease_expired` | `TaskLeaseExpiredEvent` |
| | `pool.task.lease_renewed` | `TaskLeaseRenewedEvent` |
| | `pool.task.deferred` | `TaskDeferredEvent` |
| | `pool.task.dependency_failed` | `DependencyFailedEvent` |

**NOTE:** The registry has 24 entries but does NOT include the M6 HITL lifecycle events (`hitl.lifecycle.requested`, `hitl.lifecycle.resolved`, `hitl.lifecycle.timed_out`, `hitl.lifecycle.blocked_red`) or the M10 observability events (`k1.phase1.classified.v1`, `k1.task.routed.v1`). These 6 event types are defined but NOT registered for deserialization.

**Functions:**
- `resolve_event_type(event_type: str) -> type[CanonicalEventMeta] | None` — Lookup by event_type string
- `deserialize_event(payload: dict) -> CanonicalEventMeta | None` — Dispatches to `from_payload()` via registry

**Cross-component imports:** All event submodules (conversation, hitl, mutation, pool, task, weave).

**Note:** `__all__` is duplicated at end of file (cosmetic issue).

---

### A.10 `events/validator.py` — Event Schema Validation

**Purpose:** Runtime validator for canonical event payloads. Two-layer validation: (1) canonical metadata fields, (2) type-specific domain fields.

**Public API:**
- `EVENT_SCHEMA_REGISTRY` — alias of `EVENT_TYPE_REGISTRY` (same object)
- `validate_event(payload: dict) -> (bool, list[str])` — Two layers: canonical metadata + type-specific field presence
- `validate_event_chain(events: list[dict]) -> (bool, list[str])` — Checks: event_id presence, no duplicates, causation_id references exist earlier in chain

**Internal:**
- `_get_type_specific_fields(cls)` — Uses `dataclasses.fields()` introspection to find subclass-added fields. Stays in sync automatically with class definitions.

**Validation Details:**
- Layer 1: Delegates to `validate_canonical_metadata()` (8 required fields)
- Layer 2: Checks all domain fields declared on the dataclass are present in payload
- Chain validation: Ordered list → each `causation_id` must reference an earlier `event_id`

**Cross-component imports:** `k1.concierge.events.base`, `k1.concierge.events.registry`.

---

## B. DELTA SUBSYSTEM (9 files)

### B.1 `delta/__init__.py` — Package Entrypoint

**Purpose:** Delta aggregation for SessionState coherence. Enforces the Single Writer Invariant for Back-originated state changes.

**Pipeline:**
```
Back emits deltas -> bus -> DeltaAggregator (500ms batch)
-> dedup + causal order -> DeltaApplicator.apply(batch)
-> MutationGuard preflight -> write to SS -> notify
```

**Public API (all re-exported):**
| Symbol | Source Module | Epic |
|---|---|---|
| `SessionDelta`, `VALID_DELTA_SECTIONS`, `VALID_DELTA_OPERATIONS` | session_delta | 11.1 |
| `ARTIFACT_CREATED`, `TASK_STATE_CHANGED`, `STATE_UPDATED`, `ALL_DELTA_TOPICS` | topics | 11.2 |
| `emit_artifact`, `emit_task_state_change`, `VALID_TASK_STATUSES` | emitters | 11.2 |
| `DeltaAggregator`, `DeltaBatch`, `DEFAULT_BATCH_WINDOW_MS` | aggregator | 11.3 |
| `DeltaApplicator`, `ApplyResult` | applicator | 11.4 |
| `WriterRole`, `SingleWriterViolation`, `SECTION_WRITERS`, `ALL_WRITER_SECTIONS`, `validate_writer`, `enforce_writer` | writer_registry | 11.5 |
| `SectionSnapshot`, `SnapshotReader` | snapshot_reader | — |
| `SectionOverflowHandler` | overflow | — |

**Cross-component imports:** All intra-package.

---

### B.2 `delta/session_delta.py` — SessionDelta Dataclass

**Purpose:** Single mutation dataclass destined for a SessionState section. Back emits these as bus events.

**Constants:**
```python
VALID_DELTA_SECTIONS: frozenset[str] = {
    "task_state", "task_artifacts", "history_active", "control", "meta"
}
VALID_DELTA_OPERATIONS: frozenset[str] = {"set", "append", "update", "delete"}
```

#### `SessionDelta` (dataclass)

| Field | Type | Default | Notes |
|---|---|---|---|
| `section` | `str` | required | Must be in VALID_DELTA_SECTIONS |
| `key` | `str` | required | Sub-key within section (e.g., task_id) |
| `operation` | `str` | required | Must be in VALID_DELTA_OPERATIONS |
| `data` | `dict[str, Any]` | required | Mutation payload |
| `delta_id` | `str` | `"delta-{uuid4_hex[:8]}"` | Auto-generated |
| `source_task_id` | `str \| None` | `None` | Originating task |
| `parent_delta_id` | `str \| None` | `None` | Causal parent for ordering |
| `timestamp_ns` | `int` | `0` | Monotonic timestamp |

**Key Methods:**
- `__post_init__()` — Validates section and operation against allowed sets. Raises `ValueError`.
- `dedup_key() -> str` — Returns `"{section}:{key}"` for batch deduplication
- `to_payload() -> bytes` — JSON bytes for bus envelope
- `to_dict() -> dict` — Serializes, omitting default optional fields
- `from_dict(cls, data) -> SessionDelta` — Deserializes
- `from_payload(cls, payload: bytes) -> SessionDelta` — Deserializes from bus payload bytes

**Section Ownership (V2 Section 5):**
- `task_state` — FSM via DeltaAggregator from Back bus events
- `task_artifacts` — FSM via DeltaAggregator from artifact topic
- `history_active` — FSM at turn boundary events (append-only)
- `control` — FSM state transitions + Phase 1 writes
- `meta` — FSM at turn end

**Cross-component imports:** None (stdlib only: json, uuid, dataclasses).

---

### B.3 `delta/topics.py` — Delta Bus Topic Constants

**Purpose:** Bus topic constants for SessionState mutations. All use `k1.session` prefix → `DeliveryMode.STRICT` in TimingConfig defaults.

**Constants:**
```python
ARTIFACT_CREATED    = "k1.session.artifact.created.v1"   # Back -> DeltaAggregator
TASK_STATE_CHANGED  = "k1.session.task.state.v1"         # Back -> DeltaAggregator
STATE_UPDATED       = "k1.session.state.updated.v1"      # DeltaAggregator -> Obs

ALL_DELTA_TOPICS: frozenset[str]  # All 3 topics
```

**Topic → Consumer:**
| Topic | Producer | Consumer | Mode |
|---|---|---|---|
| `k1.session.artifact.created.v1` | Back | DeltaAggregator | INTERACTIVE |
| `k1.session.task.state.v1` | Back | DeltaAggregator | INTERACTIVE |
| `k1.session.state.updated.v1` | DeltaAggregator | Observability | BACKGROUND |

**Cross-component imports:** None. References `k1/bus/timing/defaults.py` in docstring only.

---

### B.4 `delta/emitters.py` — Back-Side Delta Emitters

**Purpose:** Functions called by Back actor to emit deltas to the bus. Back NEVER writes SS directly (V2 Section 5, Rule 2).

**Constants:**
```python
VALID_TASK_STATUSES: frozenset[str] = {
    "DISPATCHED", "IN_PROGRESS", "SUSPENDED", "COMPLETED", "FAILED", "CANCELLED"
}
```

**Functions:**

#### `emit_artifact(task_id, artifact_type, artifact_data, publish_fn, parent_delta_id=None) -> SessionDelta`
- Creates `SessionDelta(section="task_artifacts", key="{task_id}:{artifact_type}", operation="append")`
- Publishes to `ARTIFACT_CREATED` topic via injected `publish_fn`
- Returns delta for observability/chaining

#### `emit_task_state_change(task_id, new_status, metadata=None, publish_fn=None, parent_delta_id=None) -> SessionDelta`
- Validates `new_status` against `VALID_TASK_STATUSES`. Raises `ValueError` if invalid.
- Creates `SessionDelta(section="task_state", key=task_id, operation="update")`
- Publishes to `TASK_STATE_CHANGED` topic via `publish_fn` (if not None)
- If `publish_fn=None`, delta is created but not published (testing mode)

**Cross-component imports:** `k1.concierge.delta.session_delta`, `k1.concierge.delta.topics`.

**Error handling:** `ValueError` on invalid task status.

---

### B.5 `delta/aggregator.py` — DeltaAggregator (500ms Batch Window)

**Purpose:** Collects SessionState deltas in fixed-window 500ms batches with dedup and causal ordering.

**Constants:**
- `DEFAULT_BATCH_WINDOW_MS = 500` — Module constant for backward compat; runtime reads from config

#### `DeltaBatch` (dataclass)

| Field | Type | Default |
|---|---|---|
| `deltas` | `list[SessionDelta]` | required |
| `batch_id` | `str` | required (format: "batch-N") |
| `collected_at_ns` | `int` | required (monotonic) |
| `dedup_count` | `int` | `0` |

#### `DeltaAggregator`

**Constructor:** `__init__(flush_fn: Callable[[DeltaBatch], Awaitable[None]], batch_window_ms: int | None = None)`
- If `batch_window_ms` is None, reads from `get_config().delta.batch_window_ms`
- `flush_fn` is the callback invoked with each batch (injected for testability)

**Slots:** `batch_window_ms`, `_flush_fn`, `_pending`, `_timer`, `_batch_count`, `_total_deltas`, `_total_deduped`

**Key Methods:**
- `async collect(delta: SessionDelta)` — Appends delta, starts batch timer on first delta. Fixed window (NOT sliding — timer doesn't reset on new deltas).
- `async flush() -> DeltaBatch | None` — Cancels timer, dedup, causal order, invokes flush_fn. Can be called manually at turn boundaries.
- `_dedup(deltas) -> list[SessionDelta]` — Static. Last-write-wins per `section:key`. Uses dict insertion for ordering.
- `_causal_order(deltas) -> list[SessionDelta]` — Static. Topological sort: parents before children via BFS. Falls back to input order if no causal links.

**Properties:** `pending_count`, `batch_count`, `stats` (dict with batch_count, total_deltas, total_deduped, pending)

**Batching Rules:**
1. First delta starts timer (500ms)
2. Subsequent deltas collected but DO NOT reset timer
3. On timer expiry: dedup → causal order → flush callback
4. New delta after flush starts new batch

**Cross-component imports:** `k1.concierge.config.get_config`, `k1.concierge.delta.session_delta`.

---

### B.6 `delta/applicator.py` — DeltaApplicator

**Purpose:** FSM's entry point for applying batched deltas to SessionState through MutationGuard preflight checks.

**Pipeline position:**
```
DeltaAggregator -> DeltaApplicator.apply(batch)
    -> MutationGuard.preflight() per delta (capacity check)
    -> Write to SS section
    -> Emit k1.session.state.updated.v1
```

#### `ApplyResult` (dataclass)

| Field | Type | Default |
|---|---|---|
| `batch_id` | `str` | required |
| `applied` | `int` | `0` |
| `rejected` | `int` | `0` |
| `evicted` | `int` | `0` |
| `rejections` | `list[dict[str, str]]` | `[]` |

**Properties:** `total` (applied + rejected), `success_rate` (applied / total, or 1.0 if empty)

#### `DeltaApplicator`

**Constructor:** All callbacks injectable for testability/decoupling:
- `preflight_fn: (section, operation, estimated_size) -> approval` — MutationGuard check. Result must have `.approved` bool + `.reason` str.
- `write_fn: async (section, key, operation, data) -> None` — SS section write
- `evict_fn: async (section, needed_bytes) -> evicted_count` — Section overflow eviction
- `notify_fn: async (batch_id, applied_count) -> None` — State.updated notification

**Key Methods:**
- `async apply(batch: DeltaBatch) -> ApplyResult` — Processes deltas sequentially. Calls notify_fn if any applied.
- `async _apply_single(delta, result) -> bool` — Per-delta: preflight → if rejected: evict → retry preflight once → write

**Eviction Retry Logic:**
1. Preflight rejects → attempt eviction
2. If eviction freed entries → retry preflight
3. If retry still fails → record rejection
4. If eviction freed 0 → record rejection immediately
5. If no evict_fn → reject directly

**Cross-component imports:** `k1.concierge.delta.aggregator.DeltaBatch`, `k1.concierge.delta.session_delta.SessionDelta`.

---

### B.7 `delta/overflow.py` — Section Overflow Handler

**Purpose:** Handles section capacity overflow by evicting oldest entries when MutationGuard rejects a write.

**Constants:**
```python
SECTION_BUDGETS: dict[str, int] = {
    "control": 8192, "beliefs_active": 8192, "scoreboard": 6144,
    "history_active": 8192, "clarifications": 4096, "affective_now": 4096,
    "narrative_active": 4096, "meta": 2048, "task_state": 4096, "task_artifacts": 4096
}
HOT_BUDGET_TOTAL: int = 53248  # ~52KB
TERMINAL_TASK_STATUSES: frozenset[str] = {"COMPLETED", "FAILED", "CANCELLED"}
HISTORY_WINDOW_SIZE: int = 20
```

#### `SectionOverflowHandler`

**Constructor:** `__init__(section_budgets=None, history_window=None)`
- Reads from `get_config().delta.overflow` for defaults

**Slots:** `_budgets`, `_eviction_log`, `_total_evicted`, `_history_window`

**Eviction Strategies per Section:**
| Section | Strategy | Budget |
|---|---|---|
| `task_artifacts` | Evict oldest by `timestamp_ns` | 4KB |
| `task_state` | Evict terminal tasks (COMPLETED/FAILED/CANCELLED) | 4KB |
| `history_active` | Sliding window, keep last N entries (default 20) | 8KB |
| Default (other) | No eviction | — |

**Key Methods:**
- `evict_oldest(section, current_data, needed_bytes) -> (remaining_data, evicted_keys)` — Dispatches to strategy
- `_evict_artifacts(data, needed_bytes)` — Sorts by `timestamp_ns`, evicts oldest until `needed_bytes` freed
- `_evict_terminal_tasks(data)` — Removes entries with terminal status
- `_evict_oldest_turns(data, keep)` — Sorts by key, keeps last `keep` entries
- `_record_eviction(section, evicted_keys, freed_bytes)` — Audit trail

**Properties:** `eviction_log` (list of dicts), `total_evicted`, `get_budget(section)`

**Cross-component imports:** `k1.concierge.config.get_config`.

---

### B.8 `delta/snapshot_reader.py` — Lock-Free SS Reads

**Purpose:** Provides point-in-time snapshots of SessionState sections. Reads return shallow copies, isolating from concurrent writes.

**Design:** V2 Section 5 Rule 3: "Reads are lock-free snapshots." Target: <1ms for snapshot creation.

#### `SectionSnapshot` (frozen dataclass)

| Field | Type |
|---|---|
| `section` | `str` |
| `data` | `dict[str, Any]` |
| `snapshot_ns` | `int` (monotonic) |
| `version` | `int` (monotonic counter) |

**Property:** `age_ms` — Staleness in milliseconds since creation.

#### `SnapshotReader`

**Constructor:** `__init__()` — Empty sections/versions dicts.

**Slots:** `_sections`, `_versions`

**Key Methods:**
- `register_section(name, initial_data=None)` — Initialize a section
- `read(section) -> SectionSnapshot` — Shallow copy of section data. Returns frozen snapshot.
- `write(section, key, value)` — Write + increment version counter
- `delete(section, key) -> bool` — Delete key + increment version
- `read_multiple(sections) -> dict[str, SectionSnapshot]` — Independent per-section reads (NOT atomically consistent across sections)

**Properties:** `section_names` (frozenset), `section_version(section) -> int`

**Cross-actor Read Scenarios:**
- Front reads task_artifacts while FSM writes → Front gets pre-write snapshot
- Back reads beliefs_active while Front writes → Back gets pre-write snapshot
- Both read history_active simultaneously → Both get same snapshot

**Cross-component imports:** None (stdlib only: time, dataclasses).

---

### B.9 `delta/writer_registry.py` — Single Writer Invariant Enforcement

**Purpose:** Encodes the Authoritative Read/Write Matrix from V2 Section 5. Validates that a WriterRole is authorized for a given section.

**Single Writer Invariant (ADR-0017g):**
1. **Sectional isolation** — Front and Back write DIFFERENT sections
2. **Back never writes SS directly** — Emits deltas to bus
3. **Reads are lock-free snapshots** — No write contention on reads

#### `WriterRole(str, Enum)`
```python
FRONT_LLM = "front_llm"
PHASE1 = "phase1"
FSM = "fsm"
EXPERIENCE_LAYER = "experience_layer"
SESSION_INIT = "session_init"
```
**Note:** Back LLM is intentionally ABSENT. It never writes SS directly.

#### `SingleWriterViolation(Exception)`
Raised when unauthorized writer attempts a section write.

**Section → Writer Matrix:**
```python
SECTION_WRITERS: dict[str, list[WriterRole]] = {
    "beliefs_active":    [FRONT_LLM],
    "scoreboard":        [PHASE1, FRONT_LLM],
    "affective_now":     [PHASE1, FRONT_LLM, EXPERIENCE_LAYER],
    "clarifications":    [FRONT_LLM],
    "narrative_active":  [FRONT_LLM],
    "control":           [FSM, PHASE1],
    "history_active":    [FSM],
    "meta":              [FSM],
    "persona":           [SESSION_INIT],
    "task_state":        [FSM],
    "task_artifacts":    [FSM],
}
ALL_WRITER_SECTIONS: frozenset[str]  # 11 sections
```

**Sequential Safety:** Phase1 finishes BEFORE Front LLM (TurnLock). ExperienceLayer fires at turn_end AFTER Front.

**Functions:**
- `validate_writer(section, role) -> bool` — Check authorization
- `enforce_writer(section, role) -> None` — Raises `SingleWriterViolation` if unauthorized

**Cross-component imports:** None (stdlib only: enum).

---

## C. OBS SUBSYSTEM (4 files)

### C.1 `obs/__init__.py` — Package Entrypoint

**Purpose:** Unified observability & telemetry package (M11). Re-exports core metrics infrastructure.

**Submodules mentioned in docstring (some not yet present as files):**
| Submodule | Status |
|---|---|
| `metrics` | Present — MetricEnvelope, MetricsCollector, MetricAggregator, SlidingWindow, TurnTimer |
| `actor_metrics` | Present — Front/Back per-mode/tier metrics |
| `react_metrics` | Present — ReAct loop telemetry |
| `alerts` | NOT present as file — AlertRule, AlertEngine, AlertEvent mentioned |
| `fsm_metrics` | NOT present as file — FSMMetricsSubscriber mentioned |
| `hitl_metrics` | NOT present as file — HITLMetricsSubscriber mentioned |
| `arbiter_metrics` | NOT present as file — ArbiterMetricsSubscriber mentioned |
| `weave_metrics` | NOT present as file — WeaveMetricsSubscriber mentioned |
| `phase1_metrics` | NOT present as file — Phase1MetricsSubscriber mentioned |

**Re-exports:**
- From `metrics`: MetricEnvelope, MetricsCollector, MetricAggregator, SlidingWindow, TurnTimer
- From `actor_metrics`: FrontOutcome, BackOutcome, record_front_metrics, record_back_metrics, classify_budget_utilization
- From `react_metrics`: ReactLoopOutcome, classify_exit_path, record_react_loop_metrics

---

### C.2 `obs/metrics.py` — Core Metrics Infrastructure

**Purpose:** M11 E11.1.1-E11.1.2, E11.2.4. Unified metrics emission/aggregation layer.

**Metric Naming Convention:** `{subsystem}.{component}.{metric_name}`
- Labels: `session_id`, `turn_number`, `actor`, `mode`, `tier`

#### `MetricEnvelope` (frozen dataclass) — M11 E11.1.1

| Field | Type | Default |
|---|---|---|
| `metric_name` | `str` | required |
| `metric_type` | `str` | required (counter/gauge/histogram/summary) |
| `value` | `float` | required |
| `labels` | `dict[str, str]` | `{}` |
| `session_id` | `str` | `""` |
| `turn_number` | `int` | `0` |
| `timestamp_ms` | `int` | auto-filled via `_now_ms()` |
| `source_event_id` | `int \| None` | `None` |

**Methods:** `to_dict()`, `to_json()`, `from_dict(cls, data)`
**Validation:** `__post_init__` raises `ValueError` for invalid `metric_type`.

#### `MetricsCollector` — M11 E11.1.1 (per-session)

**Constructor:** `__init__(session_id="", bus=None, enabled=True)`

**Internal state:** `_counters: dict[str, float]`, `_gauges: dict[str, float]`, `_histograms: dict[str, list[float]]`, `_pending: list[MetricEnvelope]`

**Methods:**
- `increment(name, labels=None, value=1.0, source_event_id=None)` — Counter: monotonically increasing
- `gauge(name, labels=None, value=0.0, source_event_id=None)` — Gauge: point-in-time value
- `observe(name, labels=None, value=0.0, source_event_id=None)` — Histogram: distribution observation
- `get_counter(name, labels)`, `get_gauge(name, labels)`, `get_histogram(name, labels)` — Query current state
- `get_counter_value(name, labels)` — Alias for get_counter
- `snapshot() -> dict` — Returns `{counters, gauges, histograms}`
- `pending_count() -> int` — Pending envelopes
- `drain_pending() -> list[MetricEnvelope]` — Drain and return pending
- `emit_all() -> int` — Publishes to bus via `build_metric_emitted()`. Returns count published.
- `reset()` — Clears all state (testing)

**Bus Integration in `emit_all()`:**
- Imports `k1.concierge.bus.builders.build_metric_emitted` (lazy import)
- Publishes each MetricEnvelope as a bus envelope
- Catches exceptions per metric (defensive)

#### `SlidingWindow` — M11 E11.1.2

**Constructor:** `__init__(window_size_ms=300_000)` — Default 5-minute window

**Methods:** `add(value, ts_ms=None)`, `count()`, `values()`, `sum()`, `mean()`, `rate(per_seconds=1.0)`, `percentile(p)`, `p50()`, `p95()`, `p99()`, `is_empty()`, `clear()`

Uses `deque[tuple[int, float]]`. Evicts stale entries on every operation.

#### `MetricAggregator` — M11 E11.1.2

**Constructor:** `__init__(window_size_s=300.0)` — Default 5-minute window

**Methods:**
- `record(envelope)` — Accepts MetricEnvelope or raw dict. Auto-creates SlidingWindow per (name, labels) key.
- `rate(metric_name, labels, per_seconds)` — Event rate
- `percentile(metric_name, labels, p)` — Distribution percentile
- `count(metric_name, labels)` — Observation count
- `latest_gauge(metric_name, labels)` — Last recorded gauge
- `get_window(metric_name, labels)` — Raw SlidingWindow (testing)
- `summary() -> dict` — All metrics with count, mean, sum, p50, p95, p99, rate_per_s
- `reset()` — Clear all

**Properties:** `window_size_ms`, `total_recorded`

#### `TurnTimer` (dataclass) — M11 E11.2.4

Per-turn latency breakdown across all processing phases.

| Field | Type | Notes |
|---|---|---|
| `turn_number` | `int` | |
| `phase1_start_ms` / `phase1_end_ms` | `int` | Phase 1 classification |
| `arbiter_start_ms` / `arbiter_end_ms` | `int` | Arbiter decision |
| `front_start_ms` / `front_end_ms` | `int` | Front LLM |
| `fsm_routing_start_ms` / `fsm_routing_end_ms` | `int` | FSM routing |
| `back_start_ms` / `back_end_ms` | `int` | Back LLM |
| `weave_decision_ms` | `int` | Weave decision |
| `weave_delivery_ms` | `int` | Weave delivery |
| `total_start_ms` / `total_end_ms` | `int` | Total turn |

**Computed Properties:** `total_ms`, `phase1_ms`, `arbiter_ms`, `front_ms`, `fsm_routing_ms`, `back_ms`

**Methods:**
- `to_breakdown() -> dict` — All fields + computed durations
- `emit(collector: MetricsCollector)` — Emits each phase as histogram observation: `turn.total_latency_ms`, `turn.phase1_latency_ms`, `turn.arbiter_latency_ms`, `turn.front_latency_ms`, `turn.fsm_routing_latency_ms`, `turn.back_latency_ms`, `turn.weave_decision_latency_ms`, `turn.weave_delivery_latency_ms`

#### `build_session_summary()` — M11 E11.5.3

Builds session-end observability summary from collector + aggregator. Returns dict for `k1.metrics.session_summary.v1`.

#### `emit_metric()` — M11 E11.1.3

Convenience router: dispatches to `increment`/`gauge`/`observe` based on `metric_type`.

**Helper:** `_label_key(name, labels) -> str` — Canonical key: `"name{k1=v1,k2=v2}"`. `_now_ms()` — Epoch milliseconds.

**Cross-component imports:** `k1.concierge.bus.builders.build_metric_emitted` (lazy import in `emit_all()`).

---

### C.3 `obs/actor_metrics.py` — Front/Back Actor Telemetry

**Purpose:** M11 E11.2.2 (Front per-mode) and E11.2.3 (Back per-tier) metrics instrumentation.

**Metric Naming:**
- `front.mode.{metric_name}` — labels: `mode`
- `back.tier.{metric_name}` — labels: `tier`

#### `FrontOutcome` (dataclass)
| Field | Type | Default |
|---|---|---|
| `mode` | `str` | `""` (PromptMode value) |
| `status` | `str` | `""` (ReactResult.status) |
| `iterations_used` | `int` | `0` |
| `iterations_budget` | `int` | `0` |
| `tool_call_count` | `int` | `0` |
| `degenerate_count` | `int` | `0` |
| `dispatched_tasks` | `int` | `0` |
| `has_text` | `bool` | `False` |
| `duration_ms` | `float` | `0.0` |

**Mode Expectations (alert thresholds):**
| Mode | Max Tools | Max Iters | Description |
|---|---|---|---|
| HITL_RELAY | 0 | 1 | Should have 0 tool calls |
| HITL_RESOLVE | 1 | 3 | Quick resolution |
| WEAVE | 2 | 3 | Quick weave |
| PRESENT | 2 | 3 | Quick present |
| STANDARD | 6 | 6 | Normal range |
| INTERRUPT | 0 | 1 | Immediate |
| ERROR | 0 | 1 | Immediate |
| CANCEL | 0 | 1 | Immediate |

#### `record_front_metrics(collector, outcome) -> list[dict]`
Emits 7 metrics:
- `front.mode.invocation_count` (counter)
- `front.mode.iterations_used` (histogram)
- `front.mode.iteration_utilization` (histogram)
- `front.mode.tool_calls` (histogram)
- `front.mode.degenerate_count` (counter, if > 0)
- `front.mode.dispatched_tasks` (histogram, if > 0)
- `front.mode.duration_ms` (histogram, if > 0)

Returns alert dicts for mode-specific violations (excess_tool_calls, excess_iterations).

#### `BackOutcome` (dataclass)
| Field | Type | Default |
|---|---|---|
| `tier` | `str` | `""` (ComplexityTier value) |
| `status` | `str` | `""` |
| `iterations_used` | `int` | `0` |
| `budget_limit` | `int` | `0` |
| `tool_call_count` | `int` | `0` |
| `degenerate_count` | `int` | `0` |
| `duration_ms` | `float` | `0.0` |
| `cancel_to_exit_ms` | `float` | `0.0` |
| `task_id` | `str` | `""` |

**Tier Budget Limits:**
```python
TIER_BUDGET_LIMITS = {"LOW": 4, "MEDIUM": 8, "HIGH": 12}
```

**Utilization Thresholds:**
```python
UTILIZATION_UNDER = 0.3
UTILIZATION_HEALTHY_LOW = 0.3
UTILIZATION_HEALTHY_HIGH = 0.8
UTILIZATION_NEAR_EXHAUSTION = 0.8
UTILIZATION_EXHAUSTED = 1.0
```

#### `record_back_metrics(collector, outcome) -> list[dict]`
Emits 7 metrics:
- `back.tier.invocation_count` (counter)
- `back.tier.iterations_used` (histogram)
- `back.tier.budget_utilization` (histogram)
- `back.tier.tool_calls` (histogram)
- `back.tier.suspension_count` (counter, if suspended)
- `back.tier.cancel_to_exit_latency_ms` (histogram, if cancelled)
- `back.tier.duration_ms` (histogram, if > 0)

Returns alert dicts for budget exhaustion.

#### `classify_budget_utilization(utilization: float) -> str`
Returns: "under" | "healthy" | "near_exhaustion" | "exhausted"

**Cross-component imports:** `k1.concierge.obs.metrics.MetricsCollector`.

---

### C.4 `obs/react_metrics.py` — ReAct Loop Telemetry

**Purpose:** M11 E11.2.1. Structured metrics from ReAct loop execution results. Called by front.py and back.py after loop returns.

**Metric Naming:** `react_loop.{actor}.{metric_name}` — Labels: actor, mode (front), tier (back), exit_path

#### `ReactLoopOutcome` (dataclass)
| Field | Type | Default |
|---|---|---|
| `actor` | `str` | `""` ("front" or "back") |
| `status` | `str` | `""` |
| `exit_path` | `str` | `""` |
| `iterations_used` | `int` | `0` |
| `iterations_budget` | `int` | `0` |
| `tool_calls_total` | `int` | `0` |
| `parallel_tool_calls` | `int` | `0` |
| `sequential_tool_calls` | `int` | `0` |
| `degenerate_count` | `int` | `0` |
| `forced_text` | `bool` | `False` |
| `duration_ms` | `float` | `0.0` |
| `mode` | `str` | `""` |
| `tier` | `str` | `""` |
| `dispatched_tasks` | `int` | `0` |
| `has_text` | `bool` | `False` |
| `validator_rejections` | `int` | `0` |

**Exit Path Classification (priority order):**
1. cancelled → `EXIT_CANCELLED`
2. suspended → `EXIT_SUSPENDED`
3. budget_exhausted → `EXIT_BUDGET_EXHAUSTED`
4. forced_text flag → `EXIT_FORCED_TEXT`
5. degenerate_count > 0 → `EXIT_DEGENERATE`
6. else → `EXIT_NORMAL`

#### `classify_exit_path(status, degenerate_count, forced_text, iterations_used, iterations_budget) -> str`
Implements priority classification above.

#### `record_react_loop_metrics(collector, outcome) -> None`
Emits ~15 metrics:
- `react_loop.{actor}.completion_count` (counter, by exit_path)
- `react_loop.{actor}.degenerate_count` (counter, if applicable)
- `react_loop.{actor}.budget_exhausted_count` (counter)
- `react_loop.{actor}.forced_text_count` (counter)
- `react_loop.{actor}.cancel_exit_count` (counter)
- `react_loop.{actor}.suspended_count` (counter, back only)
- `react_loop.{actor}.normal_completion_count` (counter)
- `react_loop.{actor}.validator_rejection_count` (counter)
- `react_loop.{actor}.iteration_count` (histogram)
- `react_loop.{actor}.iteration_utilization` (histogram)
- `react_loop.{actor}.tool_call_count` (histogram)
- `react_loop.{actor}.parallel_tool_calls` (histogram)
- `react_loop.{actor}.sequential_tool_calls` (histogram)
- `react_loop.{actor}.duration_ms` (histogram)
- `react_loop.{actor}.dispatched_task_count` (histogram, front only)

#### `build_react_loop_summary(outcome) -> dict`
Builds structured summary dict for bus emission. Suitable as payload for `build_metric_emitted()`.

**Cross-component imports:** `k1.concierge.obs.metrics.MetricsCollector`.

---

## D. CROSS-CUTTING ANALYSIS

### D.1 Complete Event Type Hierarchy

```
CanonicalEventMeta (base)
├── Conversation Events
│   ├── UserInputReceived          ("conversation.user_input.received")
│   ├── IntentArbitrated           ("conversation.intent.arbitrated")
│   ├── DeadLettered               ("conversation.dead_lettered")
│   ├── ResponseFinalDecided       ("conversation.response_final.decided")
│   ├── Phase1Classified           ("k1.phase1.classified.v1")         [NOT in registry]
│   └── TaskRouted                 ("k1.task.routed.v1")               [NOT in registry]
├── Task Lifecycle Events
│   ├── TaskCreated                ("task.created")
│   ├── TaskLeased                 ("task.leased")
│   ├── TaskProgressed             ("task.progressed")
│   ├── TaskCompleted              ("task.completed")
│   ├── TaskFailed                 ("task.failed")
│   └── TaskCancelled              ("task.cancelled")
├── HITL Events (M1)
│   ├── HILRequested               ("hil.requested")
│   ├── HILResolved                ("hil.resolved")
│   ├── TaskSuspended              ("task.suspended")
│   └── TaskResumed                ("task.resumed")
├── HITL Lifecycle Events (M6)     [NONE in registry]
│   ├── HITLRequestedEvent         ("hitl.lifecycle.requested")
│   ├── HITLResolvedEvent          ("hitl.lifecycle.resolved")
│   ├── HITLTimedOutEvent          ("hitl.lifecycle.timed_out")
│   └── HITLBlockedRedEvent        ("hitl.lifecycle.blocked_red")
├── Weave Events
│   ├── WeaveCandidateArrived      ("conversation.weave.candidate")
│   ├── WeaveDecisionMade          ("conversation.weave.decided")
│   ├── WeaveEmitted               ("conversation.weave.emitted")
│   └── WeaveMetricsEvent          ("metrics.weave.session")
├── Mutation Events
│   └── TurnMutationSummary        ("mutation.turn_summary")
└── BackPool Events
    ├── BackPoolWorkerAcquiredEvent ("pool.worker.acquired")
    ├── BackPoolWorkerReleasedEvent ("pool.worker.released")
    ├── TaskLeasedEvent             ("pool.task.leased")
    ├── TaskLeaseExpiredEvent       ("pool.task.lease_expired")
    ├── TaskLeaseRenewedEvent       ("pool.task.lease_renewed")
    ├── TaskDeferredEvent           ("pool.task.deferred")
    └── DependencyFailedEvent       ("pool.task.dependency_failed")
```

**Total event types defined:** 30
**Total in EVENT_TYPE_REGISTRY:** 24
**Unregistered:** 6 (Phase1Classified, TaskRouted, HITLRequestedEvent, HITLResolvedEvent, HITLTimedOutEvent, HITLBlockedRedEvent)

---

### D.2 Delta Pipeline Architecture

```
Back actor
    │
    ├── emit_artifact()          -> SessionDelta(section="task_artifacts")
    │                               -> publish to ARTIFACT_CREATED topic
    │
    └── emit_task_state_change() -> SessionDelta(section="task_state")
                                    -> publish to TASK_STATE_CHANGED topic
        │
        ▼
    DeltaAggregator (500ms fixed window)
        │
        ├── collect(delta) ─── start timer on first delta
        │
        ├── Timer expires OR manual flush()
        │   ├── _dedup()        ─── last-write-wins per section:key
        │   └── _causal_order() ─── topological sort (BFS)
        │
        └── flush_fn(DeltaBatch)
            │
            ▼
        DeltaApplicator.apply(batch)
            │
            ├── per delta:
            │   ├── preflight_fn(section, op, size) ── MutationGuard
            │   │   └── if rejected: evict_fn() → retry once
            │   └── write_fn(section, key, op, data) ── SS write
            │
            └── notify_fn() ── emit STATE_UPDATED topic
```

---

### D.3 Writer Authorization Matrix (delta/writer_registry.py)

| Section | FRONT_LLM | PHASE1 | FSM | EXPERIENCE_LAYER | SESSION_INIT |
|---|---|---|---|---|---|
| beliefs_active | ✅ | | | | |
| scoreboard | ✅ | ✅ | | | |
| affective_now | ✅ | ✅ | | ✅ | |
| clarifications | ✅ | | | | |
| narrative_active | ✅ | | | | |
| control | | ✅ | ✅ | | |
| history_active | | | ✅ | | |
| meta | | | ✅ | | |
| persona | | | | | ✅ |
| task_state | | | ✅ | | |
| task_artifacts | | | ✅ | | |

---

### D.4 Observability Metrics Inventory

**ReAct Loop Metrics (react_metrics.py):** ~15 metrics per actor
- Counters: completion_count (by exit_path), degenerate_count, budget_exhausted_count, forced_text_count, cancel_exit_count, suspended_count, normal_completion_count, validator_rejection_count
- Histograms: iteration_count, iteration_utilization, tool_call_count, parallel_tool_calls, sequential_tool_calls, duration_ms, dispatched_task_count

**Front Actor Metrics (actor_metrics.py):** 7 metrics per mode
- Counters: invocation_count, degenerate_count, alert_triggered
- Histograms: iterations_used, iteration_utilization, tool_calls, dispatched_tasks, duration_ms

**Back Actor Metrics (actor_metrics.py):** 7 metrics per tier
- Counters: invocation_count, suspension_count, alert_triggered
- Histograms: iterations_used, budget_utilization, tool_calls, cancel_to_exit_latency_ms, duration_ms

**Turn Timer Metrics (metrics.py):** 8 per-phase latency histograms
- turn.total_latency_ms, turn.phase1_latency_ms, turn.arbiter_latency_ms, turn.front_latency_ms, turn.fsm_routing_latency_ms, turn.back_latency_ms, turn.weave_decision_latency_ms, turn.weave_delivery_latency_ms

---

### D.5 Cross-Component Import Map

| Source Module | Imports From | Purpose |
|---|---|---|
| `events/__init__.py` | `events.base`, `events.validator` | Re-export |
| `events/conversation.py` | `events.base` | Base class |
| `events/hitl.py` | `events.base` | Base class |
| `events/task.py` | `events.base` | Base class |
| `events/mutation.py` | `events.base` | Base class |
| `events/pool.py` | `events.base` | Base class |
| `events/weave.py` | `events.base` | Base class |
| `events/registry.py` | `events.base`, `events.conversation`, `events.hitl`, `events.mutation`, `events.pool`, `events.task`, `events.weave` | Registry population |
| `events/validator.py` | `events.base`, `events.registry` | Validation |
| `delta/__init__.py` | All delta submodules | Re-export |
| `delta/aggregator.py` | `k1.concierge.config`, `delta.session_delta` | Config + delta type |
| `delta/applicator.py` | `delta.aggregator`, `delta.session_delta` | Pipeline types |
| `delta/emitters.py` | `delta.session_delta`, `delta.topics` | Delta creation + topics |
| `delta/overflow.py` | `k1.concierge.config` | Config for budgets |
| `delta/snapshot_reader.py` | (none) | Standalone |
| `delta/writer_registry.py` | (none) | Standalone |
| `obs/__init__.py` | `obs.actor_metrics`, `obs.metrics`, `obs.react_metrics` | Re-export |
| `obs/metrics.py` | `k1.concierge.bus.builders` (lazy) | Bus emission |
| `obs/actor_metrics.py` | `obs.metrics` | MetricsCollector |
| `obs/react_metrics.py` | `obs.metrics` | MetricsCollector |

**External dependencies outside k1.concierge:**
- `k1.concierge.config.get_config` — Used by aggregator.py and overflow.py
- `k1.concierge.bus.builders.build_metric_emitted` — Used by metrics.py (lazy import in emit_all)

**NO imports from:** k1.bus, k1.fabric, k1.sessionstate, k1.model_hub, k1.orchestrator, k1.planner, k0, bridge.

---

### D.6 Error Handling Patterns

| Module | Pattern | Details |
|---|---|---|
| `events/base.py` | Return tuple | `validate_canonical_metadata()` returns `(bool, list[str])`, never raises |
| `events/validator.py` | Return tuple | `validate_event()` and `validate_event_chain()` return `(bool, list[str])` |
| `delta/session_delta.py` | Raise ValueError | `__post_init__()` validates section/operation against allowed sets |
| `delta/emitters.py` | Raise ValueError | `emit_task_state_change()` validates new_status |
| `delta/writer_registry.py` | Raise SingleWriterViolation | `enforce_writer()` raises on unauthorized write |
| `delta/applicator.py` | Record + continue | Rejected deltas recorded in `ApplyResult.rejections`, processing continues |
| `obs/metrics.py` | Raise ValueError | `MetricEnvelope.__post_init__()` validates metric_type |
| `obs/metrics.py` | Catch + log | `emit_all()` catches exceptions per metric (defensive) |
| `obs/actor_metrics.py` | Early return | Returns `[]` if collector disabled/None |
| `obs/react_metrics.py` | Early return | Returns immediately if collector disabled/None |

---

### D.7 Noted Issues & Observations

1. **Duplicate `__all__`** in `events/registry.py` — Two identical `__all__` lists at end of file
2. **6 unregistered event types** — Phase1Classified, TaskRouted, and 4 M6 HITL lifecycle events are defined but not in EVENT_TYPE_REGISTRY. They cannot be deserialized via `deserialize_event()`.
3. **Missing obs submodules** — `__init__.py` docstring mentions alerts, fsm_metrics, hitl_metrics, arbiter_metrics, weave_metrics, phase1_metrics but these files don't exist yet.
4. **HOT_BUDGET_TOTAL mismatch** — Comment says "52KB" but actual sum of SECTION_BUDGETS = 53,248 bytes = 52KB. This is correct (52 × 1024 = 53,248). Constant name says 53248.
5. **`from_payload` not overridden** on Phase1Classified and TaskRouted — These events define `to_payload()` but not `from_payload()`. The base class `from_payload()` will lose domain-specific fields.
6. **Lazy import** in `metrics.py` `emit_all()` — `from k1.concierge.bus.builders import build_metric_emitted` inside the loop. This avoids circular imports but is imported on every call.
