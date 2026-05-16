# K1 Concierge — CONTRACT

`ConciergeRuntime` is the **session-scoped conversational engine** for K1. It owns
the two-actor LLM model (Front + Back), the 11-state cognitive FSM, response delivery
timing, and the full SessionState write path. It is not a shared service — it owns
one mailbox consumer task for one user session.

---

## 1. Public contract (what Concierge promises its callers)

### 1.1 Lifecycle

```python
async def start(self) -> None      # starts FSM, subscribes to bus, begins mailbox loop
async def stop(self) -> None       # drains in-flight work, unsubscribes, closes
```

`start()` creates the internal mailbox consumer task and returns after the task is
scheduled. Callers should `await runtime.start()` during session boot and later
`await runtime.stop()` during teardown; they should not create an additional task
around `start()`.

### 1.2 Self-model integration (set before `start()`)

```python
def set_self_model(self, handle: SelfModelHandle) -> None
    # Non-fatal — Concierge continues without a self-model if this raises
```

### 1.3 Dispatcher surfaces (used by Kernel to install SelfModel gate)

```python
front_dispatcher: FrontDispatcher    # message dispatch surface for Front actor
back_dispatcher:  BackDispatcher     # message dispatch surface for Back actor
front_ctx: FrontContext              # mutable context passed to Front each invocation
back_ctx:  BackContext               # mutable context passed to Back each invocation
```

These are exposed so `SelfModelHandle.install_into_session()` can wrap the dispatch
chain with policy gates before `start()` is called.

### 1.4 Construction

`ConciergeRuntime` is never instantiated directly. The canonical entry point is:

```python
ConciergeFactory.create_with_ports(
    bus: IBus,
    router: IMailboxRouter,
    front_mailbox: IMailbox,
    back_mailbox: IMailbox,
    ports: PortBundle,
    config: ConciergeConfig,
    hil_port: HumanInTheLoopService | None = None,
) -> ConciergeRuntime
```

---

## 2. Ports — what Concierge requires from each dependency

Concierge uses 8 ports. They are grouped in a `PortBundle` passed at construction.

### 2.1 `IInputPort`

```python
async def receive(self) -> Envelope        # blocks until next user-input envelope
def has_buffered(self) -> bool             # True if envelope already buffered
```

Used by: Front actor mailbox loop. One envelope = one user turn. The adapter
(`BusInputAdapter`) reads from the per-session bus `ACTOR_FRONT` mailbox.

### 2.2 `IOutputPort`

```python
async def send(self, envelope: Envelope) -> None
```

Required at construction as the injected output boundary and retained on the runtime
for live wiring diagnostics. The production adapter (`BusOutputAdapter`) publishes
envelopes to the same per-session bus that the FSM owns.

### 2.3 `IClassificationPort` (≡ `Phase1Pipeline`)

```python
def classify(self, text: str) -> Phase1Result
```

`Phase1Result` fields: `intent`, `domain`, `entities: list[str]`, `safety_band: str`,
`complexity_tier: str`, `confidence: float`.

Used by: FSM controller on every user input turn. In production: `UltraBERTPhase1Pipeline`
(local ML model, ~2ms). In test: `StubPhase1Pipeline` (fixed LOW/AMBER defaults).

The classification result drives:

- Which LLM prompt mode Front uses (STANDARD, INTERRUPT, CLARIFY_ASK, etc.)
- Which tool tier Back is given (LOW=3 tools, MEDIUM/HIGH=6 tools)
- Whether the Arbiter considers the input a cancel/modify/parallel intent

### 2.4 `ILLMPort` (≡ `IModelHubPort`)

```python
async def execute(self, request: HubRequest) -> HubResponse
async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]
```

Used by: Front actor (streaming) and Back actor (non-streaming). The same
`ModelHub` instance is shared across all sessions — Concierge does not own it.

Front calls `stream_execute` during normal conversation turns.
Back calls `execute` (non-streaming, structured JSON output).

**What Concierge requires from ILLMPort:**

- `execute()` must return a `HubResponse` with `.text: str` and `.tool_calls: list`
- `stream_execute()` must yield `HubChunk` objects with `.delta: str`
- Both must raise on terminal failure (not return empty); Concierge catches and emits
  `task.failed.v1` to the bus.

### 2.5 `IStatePort` (≡ `SSMStateAdapter`)

```python
def get_section(self, name: str) -> Any     # returns section object or None
def get_snapshot(self) -> dict[str, Any]    # full SS snapshot dict
```

This is the **read-only** face of SessionState seen by Concierge actors. The nine
SessionState sections relevant to Concierge:

| Section name | What it contains | Who reads it |
| --- | --- | --- |
| `persona` | family members, preferences, rules, user identity | Front (every turn) |
| `control` | FSM state, active_task_ids, complexity_tier, intent classification, privacy band | Front + Back + FSM |
| `history` | Typed conversation history entries | Front (chat context), Back (task context window) |
| `task_state` | Current task lifecycle: status, intents, progress, dependencies | Back (SS snapshot) |
| `task_artifacts` | Durable outputs: confirmations, bookings, created items | Back |
| `beliefs` | Inferred world model: family facts, schedules, preferences | Back (SS snapshot) |
| `affective_now` | Current emotional state: valence, arousal, dominance, band | Front (affect-aware prompting) |
| `clarification` | Open gaps, blocking gaps, clarification depth | Front (CLARIFY modes) |
| `scoreboard` | Short-term performance score (trust, quality) | Back |

**Write path is separate**: SS mutations from Back travel as bus events (deltas) to
`MemoryWriter`, never via direct SS write inside Concierge.

### 2.6 `IDispatchPort` (≡ `FabricDispatchAdapter`)

```python
async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult
async def dispatch_envelope(self, envelope: TaskEnvelope) -> AggregatedResult
```

`dispatch_direct` → Fabric LOW-tier capability execution (single capability, no
orchestration).
`dispatch_envelope` → Orchestrator MED/HIGH-tier task execution (multi-step workflow,
DAG, planner).

Used by: Back actor during its ReAct loop for `dispatch_direct()` capability
calls, and by the FSM dispatch path for MED/HIGH `dispatch_envelope()` task
handoff. The FSM routes LOW tasks to Back directly and MED/HIGH tasks through
the orchestrator envelope path.

### 2.7 `IDeltaPort` (≡ `IBus`)

The per-session bus. All internal events travel on this bus:

| Publisher | Topics emitted | Subscribers |
| --- | --- | --- |
| Front | `response.final.v1`, `response.stream.v1`, `task.dispatch.v1`, `task.cancel.v1`, `task.resume.v1` | FSM, Back |
| Back | `task.complete.v1`, `task.failed.v1`, `task.suspended.v1`, `tool.started.v1`, `tool.completed.v1` | FSM, Front |
| FSM | `state.updated.v1`, `turn.started.v1`, `turn.completed.v1`, `dead.letter.v1`, `intent.arbitrated.v1`, `hil.requested.v1`, `hil.resolved.v1` | observability, MemoryWriter |

`IDeltaPort` is the raw `IBus` — Concierge calls `publish()` and `subscribe()` directly.

### 2.8 `IMemoryPort`

```python
async def recall(
    self,
    query: str,
    memory_types: list[str] | None = None,
    max_results: int = 5,
) -> list[dict[str, Any]]
```

Used by: Front actor during prompt assembly. Returns recalled memories from bridge
(K0 long-term store). Returns `[]` when bridge is offline (`OfflineBridgeAdapter`).
The `RecallMemoryAdapter` wraps a `recall_fn` closure over the bridge client.

---

## 3. Error surface

| Error | Condition | Handling |
| --- | --- | --- |
| `IllegalTransitionError` | FSM guard rejects a bus event in current state | Dead-lettered — published to `dead.letter.v1`; FSM stays in current state |
| `FrontLockOverflowError` | Front mailbox queue exceeds `DEFAULT_MAX_QUEUE_DEPTH` | Event dropped; logged |
| LLM failure (any) | `execute()` or `stream_execute()` raises | Back emits `task.failed.v1`; FSM transitions accordingly |
| Back cancel race | `task.complete.v1` arrives after `task.cancel.v1` | `completed_before_cancel=True` in `TaskComplete` payload; Front handles gracefully |
| Phase 1 failure | `classify()` raises | `StubPhase1Pipeline` fallback applied (LOW/AMBER defaults) |
| WeavePolicy failure | `policy.decide()` raises | `WeaveFallbackHandler.fallback_decide()` — static 500ms BATCH window |
| SS section missing | `get_section(name)` returns `None` | `safe_get_section()` returns `None`; actors use defaults per section |
| Crash / restart | Process restart mid-session | `CrashRecoveryOrchestrator.recover()` replays ledger to rebuild FSM state |

---

## 4. Invariants that callers must respect

1. `set_self_model()` must be called **before** `start()` if self-model gates are
   required. Calling after start raises `RuntimeError` so a live mailbox turn
   cannot race the handle swap.
2. One `ConciergeRuntime` per session. Sessions must not share an instance.
3. The per-session `IBus` passed to Concierge must be isolated from other sessions.
   Concierge subscribes globally to the bus it receives.
4. `stop()` must be called before closing the session bus. Calling `bus.close()`
   first will cause unsubscribe calls on a closed bus.
5. The `IDispatchPort` must remain live for the entire session lifetime. Concierge
   does not cache the dispatch target — every Back ReAct iteration calls it.
6. Back NEVER writes SessionState directly. All SS mutations are emitted as bus events
   consumed by `MemoryWriter`. Bypassing this breaks the event-sourced ledger.
