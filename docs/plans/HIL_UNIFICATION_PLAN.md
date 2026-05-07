# HIL Unification — Milestone / Epic / Issue Plan

> **Status:** Approved design (2026-04-29). Implementation pending.
> **Scope:** Replace 2 `HILCoordinator` classes + `IDeltaEmitPort.emit_hil_request` + missing fabric gate with ONE `HumanInTheLoopService` behind a real `IHILPort`. Hard cutover.
> **Owner:** Kernel remediation sweep.
> **Related findings:** F2, W10, Phase 2 `topic_clarification_emitted` FAIL, audit BLOAT-1.

---

## Approved Decisions (locked)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Capability contract supports **BOTH** `requires_human_confirmation: bool` + structured `side_effects: [...]` AND `safety_band_min` inference | Explicit fields win when present; `safety_band_min` (AMBER/RED → ASK) is the default fallback so existing contracts get HIL gating for free |
| 2 | Location: **`k1/hil/`** (top-level, not nested under kernel) | HIL+clarification is a tier-1 cross-cutting service; easier to discover and edit |
| 3 | Names: **`HumanInTheLoopService`** (impl) + **`IHILPort`** (protocol, lives in `k1/kernel/ports/hil_port.py`) | "Human in the loop + clarification when LLM is confused" — explicit name conveys both roles |
| 4 | Migration: **hard cutover** | Family-OS scale; old classes have ~5 callers total; shims would require a second cleanup |
| 5 | Bridge: **all HIL traffic funnels through Front LLM coordinator** which asks the user | Single user-surface; planner & fabric HIL no longer silently fail |
| 6 | Fabric gate defaults: GREEN=ALLOW, AMBER=ASK, RED=ASK | Safe default; explicit `requires_human_confirmation: false` overrides for AMBER/RED if a contract opts out |

---

## Architectural Invariants

1. **One outbound topic, one inbound topic.** All callers funnel through `k1.hil.request.v1` and `k1.hil.response.v1` with a `kind` discriminator (`clarification | approval | needs_human | override | capability_gate`).
2. **One correlation key:** `hil_request_id: UUID`. Caller's `task_id` / `trace_id` / `plan_id` ride along as metadata.
3. **One ledger.** All HIL events (requested / resolved / timed_out / blocked_red) go through shared `LedgerWriter`.
4. **One suspension store.** `SuspensionManager` is shared infra under `k1/hil/`, not concierge-internal.
5. **One safety-band model.** `safety_band_min` from contracts is authoritative for the fabric gate; explicit fields override.
6. **LLM is optional.** Only planner-clarification synthesizes question text via `ILLMPort`. All other callers pass pre-formed text.
7. **Caller-agnostic Front.** Front HITL_RELAY treats every `k1.hil.request.v1` envelope identically regardless of `kind`.

---

# Epic E1 — `HumanInTheLoopService` skeleton + `IHILPort` contract

**Goal:** Stand up the service module, the real protocol, and the Front bridge — with NO production callers wired yet. Existing HIL paths in concierge/planner/orchestrator continue to work unchanged. The new service must be independently constructable and unit-testable.

**Non-goals for E1:** Touching `concierge/factory.py`, `planner/factory.py`, `orchestrator_service.py`, `fabric/factory.py`, `kernel/service.py` wiring. Those are E4–E7.

**Branch hygiene:** Single feature branch `hil-unification-e1`. Each issue = one commit. Run only the tests listed in the issue's "Tests" section.

---

## E1.M1 — Module skeleton + protocol

### Issue E1.M1.1 — Create `k1/hil/` package skeleton

**Files to create (empty stubs first, no logic):**

| Path | Purpose | Approx size |
|------|---------|-------------|
| `k1/hil/__init__.py` | Public re-exports | ~30 lines |
| `k1/hil/types.py` | Dataclasses + enums | ~250 lines |
| `k1/hil/topics.py` | Topic constants | ~25 lines |
| `k1/hil/safety.py` | `SafetyBandPolicy` | ~80 lines |
| `k1/hil/suspension.py` | Re-export shim → `k1/concierge/protocols/suspension_manager` (moved in E4.M1) | ~10 lines for now |
| `k1/hil/ledger.py` | `HILLedgerAdapter` wrapping `LedgerWriter` | ~60 lines |
| `k1/hil/service.py` | `HumanInTheLoopService` | ~400 lines |
| `k1/hil/ports/__init__.py` | Port re-exports | ~10 lines |
| `k1/hil/ports/event_port.py` | `IEventPort` (HIL-local minimal protocol: `publish`, `subscribe`) | ~50 lines |
| `k1/hil/ports/llm_port.py` | `ILLMPort` (HIL-local minimal protocol: `synthesize_question`) | ~40 lines |
| `k1/hil/config.py` | `HILConfig` dataclass | ~50 lines |

**Why HIL-local ports (not reuse fabric/planner)?** Repo currently has 11 distinct `EventPort`/`IEventPort` Protocol declarations across fabric, planner, model_hub, sessionstate. HIL is cross-cutting; depending on any single subsystem's port creates a circular import risk when planner/fabric depend on HIL. Define the minimal surface HIL needs (publish + subscribe with `(topic, payload)` signature) and let production adapters (which already implement structural Protocols) satisfy it via duck typing.

**`k1/hil/__init__.py` exports:**

```python
from k1.hil.config import HILConfig
from k1.hil.safety import SafetyBandPolicy
from k1.hil.service import HumanInTheLoopService
from k1.hil.topics import (
    TOPIC_HIL_AUDIT,
    TOPIC_HIL_REQUEST,
    TOPIC_HIL_RESPONSE,
)
from k1.hil.types import (
    ApprovalRequest, ApprovalResponse,
    CapabilityGateRequest, GateDecision, GateOutcome,
    ClarificationRequest, ClarificationResponse,
    HILKind, HILEnvelope, HILResponseEnvelope,
    NeedsHumanRequest, NeedsHumanResponse,
    OverrideRequest, OverrideResponse,
)
__all__ = [...]  # explicit
```

**Tests:** None for this issue. Just `pytest --collect-only tests/k1/hil/` succeeds with zero collected tests after package exists.

**Verify:**

```powershell
python -c "from k1.hil import HumanInTheLoopService, IHILPort"  # both importable
```

---

### Issue E1.M1.2 — Promote `IHILPort` to a real protocol

**File:** `k1/kernel/ports/hil_port.py`

**Action:** Replace the current empty marker (lines 1-71, see [k1/kernel/ports/hil_port.py](k1/kernel/ports/hil_port.py)) with a real `Protocol` declaring 5 methods. Delete the "two coordinators is fine" rationale paragraph — it is now obsolete.

**New signature:**

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
from k1.hil.types import (
    ClarificationRequest, ClarificationResponse,
    ApprovalRequest, ApprovalResponse,
    NeedsHumanRequest, NeedsHumanResponse,
    OverrideRequest, OverrideResponse,
    CapabilityGateRequest, GateDecision,
)

@runtime_checkable
class IHILPort(Protocol):
    async def ask_clarification(self, req: ClarificationRequest) -> ClarificationResponse: ...
    async def request_approval(self, req: ApprovalRequest) -> ApprovalResponse: ...
    async def needs_human(self, req: NeedsHumanRequest) -> NeedsHumanResponse: ...
    async def request_override(self, req: OverrideRequest) -> OverrideResponse: ...
    async def gate_capability(self, req: CapabilityGateRequest) -> GateDecision: ...
    def reset_round_budget(self, caller_key: str) -> None: ...
    async def shutdown(self) -> None: ...
```

**Imports check:** `k1/kernel/ports/hil_port.py` MUST NOT import from `k1.hil.service`. Type-only imports of `k1.hil.types` are fine (types module has no service deps). This avoids `kernel.ports → hil.service → kernel.ports` cycles.

**File:** `k1/kernel/ports/__init__.py` — already re-exports `IHILPort` at line 49 ([k1/kernel/ports/**init**.py](k1/kernel/ports/__init__.py)). No change needed.

**Tests:** `tests/k1/kernel/test_hil_port_protocol.py` (NEW)

- `test_ihilport_has_required_methods` — `assert hasattr(IHILPort, 'ask_clarification')` × 7 methods.
- `test_ihilport_runtime_checkable` — `assert isinstance(stub_with_methods, IHILPort) is True`.
- `test_ihilport_rejects_incomplete` — class missing `gate_capability` should fail isinstance.
- `test_humanintheloopservice_satisfies_ihilport` — import `HumanInTheLoopService`, construct with stub deps, `isinstance(svc, IHILPort)`.

**Run:** `pytest tests/k1/kernel/test_hil_port_protocol.py -v`

---

### Issue E1.M1.3 — Define request/response types in `k1/hil/types.py`

**File:** `k1/hil/types.py`

**Discriminator enum:**

```python
class HILKind(str, Enum):
    CLARIFICATION = "clarification"
    APPROVAL      = "approval"
    NEEDS_HUMAN   = "needs_human"
    OVERRIDE      = "override"
    CAPABILITY_GATE = "capability_gate"
```

**Per-kind request dataclasses (frozen, slotted):**

| Class | Fields | Source caller |
|-------|--------|---------------|
| `ClarificationRequest` | `caller_key: str`, `trace_id: str`, `question_context: dict`, `synthesize_with_llm: bool=True`, `pre_formed_question: str\|None=None`, `timeout_ms: int=60_000` | Planner SKETCH |
| `ApprovalRequest` | `caller_key: str`, `trace_id: str`, `summary: str`, `options: list[dict]`, `side_effects: list[str]`, `safety_assessment: str`, `estimated_duration_ms: int`, `timeout_ms: int=120_000` | Planner VALIDATE |
| `NeedsHumanRequest` | `caller_key: str`, `task_id: str`, `trace_id: str`, `hil_type: Literal["clarification","approval","selection"]`, `question: str`, `options: list[dict]=[]`, `context: dict={}`, `side_effects: list[str]=[]`, `safety_band: SafetyBand=GREEN`, `react_history: list[dict]=[]`, `timeout_ms: int\|None=None` | Concierge Back→FSM |
| `OverrideRequest` | `caller_key: str`, `request_id: str`, `trace_id: str`, `plan_id: str`, `unresolved_capabilities: list[str]`, `proposed_alternatives: list[dict]`, `timeout_ms: int=60_000` | Orchestrator ConstraintResolver |
| `CapabilityGateRequest` | `caller_key: str`, `trace_id: str`, `capability_name: str`, `contract: CapabilityContractView`, `params: dict`, `params_summary: str`, `timeout_ms: int=120_000` | Fabric `CapabilityFabric.execute()` |

**Per-kind response dataclasses:**

| Class | Fields |
|-------|--------|
| `ClarificationResponse` | `hil_request_id: str`, `answer: str\|None`, `timed_out: bool`, `round_budget_exhausted: bool` |
| `ApprovalResponse` | `hil_request_id: str`, `decision: Literal["approve","modify","reject"]`, `modifications: dict\|None`, `timed_out: bool` |
| `NeedsHumanResponse` | `hil_request_id: str`, `decision: str`, `resolution: dict`, `raw_user_text: str\|None`, `timed_out: bool` |
| `OverrideResponse` | `hil_request_id: str`, `choice: Literal["override","fallback","abort"]`, `selected_alternative: dict\|None`, `fallback_action: str\|None`, `timed_out: bool` |
| `GateDecision` | `outcome: GateOutcome`, `hil_request_id: str\|None`, `reason: str`, `user_approved: bool\|None`, `audit_only: bool=False` |
| `GateOutcome` (enum) | `ALLOW`, `DENY`, `ASK_APPROVED`, `ASK_REJECTED`, `TIMEOUT` |

**Wire envelope (single shape on bus):**

```python
@dataclass(frozen=True, slots=True)
class HILEnvelope:
    hil_request_id: str          # UUID4
    kind: HILKind
    caller_key: str              # "planner:plan-abc", "concierge:task-xyz", "orchestrator:wave-3", "fabric:cap.unlock_door"
    trace_id: str
    created_at_ms: int           # int(time.time() * 1000)
    timeout_ms: int
    payload: dict[str, Any]      # kind-specific serialized request

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> HILEnvelope: ...

@dataclass(frozen=True, slots=True)
class HILResponseEnvelope:
    hil_request_id: str
    kind: HILKind
    responded_at_ms: int
    payload: dict[str, Any]      # kind-specific serialized response
    timed_out: bool = False
```

**`CapabilityContractView`** — minimal read-only view over the capability contract that HIL needs (avoids importing the full fabric `CapabilityContract` and creating circular deps):

```python
@dataclass(frozen=True, slots=True)
class CapabilityContractView:
    name: str
    safety_band_min: Literal["GREEN", "AMBER", "RED"]
    requires_human_confirmation: bool | None  # None = inferred from safety_band
    side_effects: list[dict]  # [{kind, target, reversible, ...}]
    description: str
```

**Tests:** `tests/k1/hil/test_types.py`

- Each request/response dataclass: construction with defaults, frozen enforcement, slots.
- `HILEnvelope.to_dict / from_dict` round-trip for all 5 kinds.
- `HILResponseEnvelope.to_dict / from_dict` round-trip.
- `HILKind` enum values match topic discriminator strings.

**Run:** `pytest tests/k1/hil/test_types.py -v`

---

### Issue E1.M1.4 — Define topics in `k1/hil/topics.py`

**File:** `k1/hil/topics.py`

```python
"""Single source of truth for HIL bus topics.

After E7, the following legacy constants are DELETED:
  - k1.planner.events.TOPIC_HIL_CLARIFICATION
  - k1.planner.events.TOPIC_HIL_APPROVAL_REQ
  - k1.planner.events.TOPIC_HIL_CLARIFICATION_RESP
  - k1.planner.events.TOPIC_HIL_APPROVAL_RESP
  - k1.orchestrator.events.HIL_OVERRIDE_RESPONSE
  - k1.orchestrator.events.HIL_FALLBACK_RESPONSE
  - All k1.hitl.* concierge audit topics (consolidated into k1.hil.audit.v1)
"""

TOPIC_HIL_REQUEST  = "k1.hil.request.v1"   # ALL outbound to user (Front bridge subscribes)
TOPIC_HIL_RESPONSE = "k1.hil.response.v1"  # ALL inbound from user (HIL service subscribes)
TOPIC_HIL_AUDIT    = "k1.hil.audit.v1"     # Optional observability (requested/resolved/timed_out/blocked)

# Caller-key namespaces (convention, not enforced):
#   planner:<plan_id>         — planner SKETCH/VALIDATE
#   concierge:<task_id>       — concierge Back→FSM
#   orchestrator:<plan_id>    — orchestrator constraint resolver
#   fabric:<capability_name>  — fabric pre-execution gate
```

**Tests:** `tests/k1/hil/test_topics.py`

- Topics are exact strings (regression guard).
- No collision with concierge `TOPIC_HIL_REQUEST = "k1.hil.request.v1"` (currently same value, intentional — concierge bus topic gets reused).

**Run:** `pytest tests/k1/hil/test_topics.py -v`

---

### Issue E1.M1.5 — Implement `SafetyBandPolicy` in `k1/hil/safety.py`

**File:** `k1/hil/safety.py`

**Class:**

```python
class SafetyBandPolicy:
    """Decides whether a capability invocation requires HIL.

    Decision matrix (Decision #6 of design):
      explicit requires_human_confirmation=True  → ASK
      explicit requires_human_confirmation=False → ALLOW (override)
      requires_human_confirmation=None (inferred):
        safety_band_min=GREEN + no side_effects → ALLOW
        safety_band_min=GREEN + side_effects    → ASK (escalate to AMBER)
        safety_band_min=AMBER                   → ASK
        safety_band_min=RED                     → ASK (always ask, never auto-deny)

    User can override RED via response — service writes audit_only=True
    and emits to TOPIC_HIL_AUDIT for governance review.
    """
    __slots__ = ()

    def decide(self, contract: CapabilityContractView, params: dict) -> SafetyDecision:
        """Returns one of:
          SafetyDecision.ALLOW  — execute without prompting user
          SafetyDecision.ASK    — must prompt user
          SafetyDecision.DENY   — never executable (reserved; not used today)
        """
```

**Why no `DENY` outcome today?** Even RED capabilities are askable per Decision #6. `DENY` is reserved for future hard-blocks (e.g. capabilities permanently disabled by org policy). Document that.

**Tests:** `tests/k1/hil/test_safety.py`

- GREEN no side_effects → ALLOW.
- GREEN with side_effects → ASK.
- AMBER → ASK.
- RED → ASK.
- Explicit `requires_human_confirmation=True` on GREEN → ASK.
- Explicit `requires_human_confirmation=False` on AMBER → ALLOW.
- Explicit `requires_human_confirmation=False` on RED → ASK (cannot override RED to ALLOW; document this).
- Edge: `requires_human_confirmation=None` + missing `side_effects` → infer from band only.

**Run:** `pytest tests/k1/hil/test_safety.py -v`

---

### Issue E1.M1.6 — Implement `HILLedgerAdapter` in `k1/hil/ledger.py`

**File:** `k1/hil/ledger.py`

**Why a wrapper?** Concierge `LedgerWriter` is currently coupled to concierge event types (`HILRequested`, `HILResolved` from `k1.concierge.events.hitl`). HIL service should not import concierge events. The adapter accepts an injected `LedgerWriter`, defines its own kernel-level event types in `k1/hil/types.py`, and writes them.

**Adapter shape:**

```python
class HILLedgerAdapter:
    __slots__ = ("_writer",)

    def __init__(self, writer: LedgerWriter | None) -> None:
        self._writer = writer  # None = no-op (for tests/dev without ledger)

    def write_requested(self, env: HILEnvelope) -> None: ...
    def write_resolved(self, env: HILEnvelope, resp: HILResponseEnvelope) -> None: ...
    def write_timed_out(self, env: HILEnvelope) -> None: ...
    def write_blocked(self, env: HILEnvelope, reason: str) -> None: ...
```

**Event types for ledger** (added to `k1/hil/types.py`):

```python
@dataclass(frozen=True, slots=True)
class HILRequestedEvent:
    hil_request_id: str
    kind: str
    caller_key: str
    trace_id: str
    timestamp_ms: int

@dataclass(frozen=True, slots=True)
class HILResolvedEvent:
    hil_request_id: str
    kind: str
    decision_summary: str
    timestamp_ms: int
    duration_ms: int

# … HILTimedOutEvent, HILBlockedEvent
```

**Tests:** `tests/k1/hil/test_ledger.py`

- `HILLedgerAdapter(None)` — all methods no-op without raising.
- `HILLedgerAdapter(real_writer)` — write_requested produces a `LedgerEntry` with correct event payload (use in-memory `LedgerWriter` from existing tests).
- Round-trip: write_requested + write_resolved, then `LedgerWriter.read_all()` yields both in order.

**Run:** `pytest tests/k1/hil/test_ledger.py -v`

---

### Issue E1.M1.7 — Define HIL-local ports in `k1/hil/ports/`

**File:** `k1/hil/ports/event_port.py`

```python
@runtime_checkable
class IEventPort(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...
    def subscribe(self, topic: str, handler: Callable[[str, dict], Awaitable[None]]) -> SubscriptionHandle: ...
```

**File:** `k1/hil/ports/llm_port.py`

```python
@runtime_checkable
class ILLMPort(Protocol):
    async def synthesize_question(
        self, *, context: dict, max_tokens: int = 300, trace_id: str | None = None,
    ) -> str | None:
        """Returns natural-language question, or None on failure (best-effort fallback)."""
```

**Adapter compatibility check (read-only verification, not a code change):**

- `k1.fabric.adapters.event_port_prod.EventPortProdAdapter` — has `async publish(topic, payload)` and `subscribe(topic, handler)`. Compatible.
- Concierge `bus.publish(envelope)` takes a full envelope, NOT `(topic, payload)`. We will write a small adapter inside the kernel bootstrap (E7) to bridge `bus.publish(env)` ↔ `event_port.publish(topic, payload)`. NOT in scope for E1.

**File:** `k1/hil/ports/__init__.py`

```python
from k1.hil.ports.event_port import IEventPort
from k1.hil.ports.llm_port import ILLMPort
__all__ = ["IEventPort", "ILLMPort"]
```

**Tests:** `tests/k1/hil/test_ports.py`

- Stub class with required methods → `isinstance(stub, IEventPort)` True.
- Stub missing `subscribe` → False.
- Same for `ILLMPort`.

**Run:** `pytest tests/k1/hil/test_ports.py -v`

---

### Issue E1.M1.8 — Implement `HumanInTheLoopService` core

**File:** `k1/hil/service.py`

**`__init__` signature:**

```python
class HumanInTheLoopService:
    __slots__ = (
        "_event_port", "_llm_port", "_safety_policy", "_ledger",
        "_suspension_mgr", "_config",
        "_pending",                # dict[str, asyncio.Future[HILResponseEnvelope]]
        "_round_budget",           # dict[str, int]  caller_key → round_count
        "_response_subscription",  # SubscriptionHandle
        "_lock",                   # asyncio.Lock for _pending mutations
    )

    def __init__(
        self,
        *,
        event_port: IEventPort,
        ledger: HILLedgerAdapter,
        suspension_mgr: SuspensionManager | None,
        safety_policy: SafetyBandPolicy,
        config: HILConfig,
        llm_port: ILLMPort | None = None,
    ) -> None:
        ...
        self._response_subscription = event_port.subscribe(
            TOPIC_HIL_RESPONSE, self._on_response
        )
```

**Method implementations (each follows the same 5-step pattern):**

```python
async def _request(self, kind: HILKind, caller_key: str, trace_id: str,
                   payload: dict, timeout_ms: int) -> HILResponseEnvelope:
    """Generic request lifecycle. All five public methods delegate here."""
    hil_id = str(uuid.uuid4())
    env = HILEnvelope(
        hil_request_id=hil_id, kind=kind, caller_key=caller_key,
        trace_id=trace_id, created_at_ms=int(time.time()*1000),
        timeout_ms=timeout_ms, payload=payload,
    )
    fut: asyncio.Future[HILResponseEnvelope] = asyncio.get_running_loop().create_future()
    async with self._lock:
        self._pending[hil_id] = fut

    self._ledger.write_requested(env)
    await self._event_port.publish(TOPIC_HIL_REQUEST, env.to_dict())

    try:
        resp = await asyncio.wait_for(fut, timeout=timeout_ms / 1000.0)
        self._ledger.write_resolved(env, resp)
        return resp
    except asyncio.TimeoutError:
        timeout_resp = HILResponseEnvelope(
            hil_request_id=hil_id, kind=kind,
            responded_at_ms=int(time.time()*1000),
            payload={}, timed_out=True,
        )
        self._ledger.write_timed_out(env)
        return timeout_resp
    finally:
        async with self._lock:
            self._pending.pop(hil_id, None)

async def _on_response(self, topic: str, data: dict) -> None:
    resp = HILResponseEnvelope.from_dict(data)
    async with self._lock:
        fut = self._pending.get(resp.hil_request_id)
    if fut is None:
        log.warning("hil_response_unknown_id  hil_request_id=%s", resp.hil_request_id)
        return  # late or unknown response — drop with warning
    if not fut.done():
        fut.set_result(resp)
```

**Per-method specializations:**

1. **`ask_clarification`** — caller_key like `planner:<plan_id>`. Round budget: `_round_budget[caller_key] += 1`; if `> config.max_clarification_rounds`, return `ClarificationResponse(answer=None, round_budget_exhausted=True)` WITHOUT publishing. If `req.synthesize_with_llm and self._llm_port is not None and req.pre_formed_question is None`, call `llm_port.synthesize_question(...)` to get the user-facing text; on `None`, log + skip (return answer=None). Publish via `_request(HILKind.CLARIFICATION, ...)`. Map `HILResponseEnvelope.payload["answer"]` to `ClarificationResponse.answer`.

2. **`request_approval`** — caller_key `planner:<plan_id>`. Does NOT consume clarification round budget. If LLM available, synthesize approval summary; otherwise use pre-formed `req.summary`. Map response `payload["decision"]` to `Literal["approve","modify","reject"]`.

3. **`needs_human`** — caller_key `concierge:<task_id>`. Pass `req.task_id` to `SuspensionManager.suspend(...)` if `_suspension_mgr is not None` BEFORE publishing (this gives concierge crash recovery). On response, call `suspension_mgr.resolve(...)`. Map `payload["resolution"]` dict directly into `NeedsHumanResponse.resolution`.

4. **`request_override`** — caller_key `orchestrator:<plan_id>`. Awaits `OverrideResponse` synchronously, blocking the caller's coroutine (this is the ConstraintResolver's design — it's allowed to block on user input).

5. **`gate_capability`** — caller_key `fabric:<capability_name>`. First call `safety_policy.decide(req.contract, req.params)`:
   - `ALLOW` → return `GateDecision(outcome=ALLOW, hil_request_id=None, reason="safety_band_green_no_side_effects")` immediately, NO publish.
   - `ASK` → publish, await response; on approve `outcome=ASK_APPROVED`, on reject `outcome=ASK_REJECTED`, on timeout `outcome=TIMEOUT`. Set `audit_only=True` if contract was RED + user approved (governance flag).
   - `DENY` → return `GateDecision(outcome=DENY, ...)` immediately; emit `TOPIC_HIL_AUDIT` event for governance.

**`reset_round_budget(caller_key)`** — clears `_round_budget[caller_key]`. Called by planner `LC_PLAN_START` lifecycle hook in E5.

**`shutdown()`** — unsubscribe from `TOPIC_HIL_RESPONSE`; cancel all pending futures with `asyncio.CancelledError`; flush ledger.

**Concurrency invariants:**

- `_pending` mutations always under `_lock` (asyncio.Lock).
- `_round_budget` mutations under same lock (single coordinator per caller_key, but multiple kinds may race within a caller).
- `_on_response` is the only task that resolves futures. Service methods only create + await + remove on cleanup.
- One `IHILPort` instance per kernel. Re-entrant via per-`hil_request_id` correlation; concurrent requests across kinds and callers are supported.

**Logging discipline (Family-OS pattern):** structured key=value logs at INFO for request/resolve/timeout, DEBUG for response correlation, WARNING for unknown response IDs.

**Tests:** see E1.M1.9 below (split out for size).

---

### Issue E1.M1.9 — Unit tests for `HumanInTheLoopService`

**File:** `tests/k1/hil/test_service.py`

**Fixtures:** in-memory `IEventPort` stub (records publishes; lets test inject responses by calling subscribed handler directly), `HILLedgerAdapter(None)`, no `SuspensionManager`, no `ILLMPort` (default).

**Test matrix (one method per row, plus cross-cutting):**

| Test | Asserts |
|------|---------|
| `test_ask_clarification_happy_path` | publishes envelope on `TOPIC_HIL_REQUEST` with `kind=clarification`; on response answer is returned |
| `test_ask_clarification_timeout` | no response → returns `ClarificationResponse(answer=None, timed_out=True)` |
| `test_ask_clarification_round_budget` | call N+1 times where N=`max_clarification_rounds`; (N+1)th returns `round_budget_exhausted=True` WITHOUT publishing |
| `test_reset_round_budget_per_caller` | budget keyed by `caller_key`; reset clears only that caller |
| `test_ask_clarification_llm_synthesis` | with `ILLMPort` stub returning "synth Q", envelope payload contains the synthesized question |
| `test_ask_clarification_llm_failure` | LLM returns None → still publishes with `pre_formed_question` fallback (or empty) |
| `test_request_approval_happy` | publishes `kind=approval`; decision mapped through |
| `test_request_approval_does_not_consume_clarification_budget` | exhaust clar budget, approval still works |
| `test_needs_human_with_suspension_mgr` | suspension_mgr.suspend called BEFORE publish; resolve called on response |
| `test_needs_human_without_suspension_mgr` | works in degraded mode (no suspension_mgr) |
| `test_request_override_happy` | publishes `kind=override`; choice mapped |
| `test_gate_capability_green_no_sideeffects_short_circuits` | `outcome=ALLOW`, NO publish on bus, NO ledger entry |
| `test_gate_capability_amber_asks` | `outcome=ASK_APPROVED` on user approve |
| `test_gate_capability_amber_user_denies` | `outcome=ASK_REJECTED` on user reject |
| `test_gate_capability_red_always_asks` | even with `requires_human_confirmation=False`, RED still asks |
| `test_gate_capability_explicit_requires_human_overrides_green` | GREEN + `requires_human_confirmation=True` → ASK |
| `test_gate_capability_timeout` | `outcome=TIMEOUT` after `timeout_ms` |
| `test_response_with_unknown_id_dropped` | resp arrives with no matching `_pending` entry → WARNING logged, no crash |
| `test_concurrent_requests_independent` | 3 concurrent `ask_clarification` calls with different `hil_request_id`; responses route correctly to each future |
| `test_shutdown_cancels_pending` | `await svc.shutdown()` while a request is pending → caller sees `CancelledError` |
| `test_ledger_writes_request_and_resolve` | with real in-memory `LedgerWriter`, two entries appear after one round trip |
| `test_ledger_writes_timeout` | timeout → `HILTimedOutEvent` written |
| `test_envelope_uuid_uniqueness` | 100 sequential calls → 100 unique `hil_request_id`s |

**Run:** `pytest tests/k1/hil/test_service.py -v` (target: < 2s, all in-memory)

---

### Issue E1.M1.10 — Define `HILConfig` in `k1/hil/config.py`

**File:** `k1/hil/config.py`

```python
@dataclass(frozen=True, slots=True)
class HILConfig:
    max_clarification_rounds: int = 2
    clarification_timeout_ms: int = 60_000
    approval_timeout_ms: int = 120_000
    needs_human_timeout_ms: int = 60_000
    override_timeout_ms: int = 60_000
    capability_gate_timeout_ms: int = 120_000
    enable_audit_topic: bool = True
    enable_llm_synthesis: bool = True

    @classmethod
    def from_kernel_config(cls, kc: "KernelConfig") -> HILConfig:
        """Build from KernelConfig fields. New fields added in E7.M2."""
        return cls(...)
```

**Tests:** `tests/k1/hil/test_config.py` — defaults match design (60/120/60/60/120 ms, 2 rounds).

**Run:** `pytest tests/k1/hil/test_config.py -v`

---

## E1.M2 — Front bridge subscriber

### Issue E1.M2.1 — Front subscribes to unified `k1.hil.request.v1`

**Audit first (read-only):** Confirm what Front currently subscribes to.

**Files to inspect:**

- `k1/concierge/bus/topics.py` — locate `FRONT_SUBSCRIPTIONS` (audit said line ~286).
- `k1/concierge/actors/front.py` — locate `PromptMode.HITL_RELAY` handler (line ~344) and `PromptMode.HITL_RESOLVE` (line ~352).
- `k1/concierge/bus/dispatch.py` (or equivalent) — how subscriptions are wired.

**Current state (per E1 audit):** Front subscribes to `TOPIC_HIL_REQUEST = "k1.hil.request.v1"` already. The legacy concierge HIL request constant happens to use the same topic string as our new unified topic. **This is convenient — we just need Front to handle the new envelope shape.**

**Action 1:** Update Front's HITL_RELAY handler to accept `HILEnvelope` (from `k1.hil.types`) shape:

- Old payload: `{task_id, hil_type, question, options, side_effects, ...}` (concierge `HILRequest.to_payload()`).
- New payload: `HILEnvelope.to_dict() = {hil_request_id, kind, caller_key, trace_id, created_at_ms, timeout_ms, payload: {...kind-specific...}}`.

**Action 2:** Front renders question based on `kind`:

- `clarification` — render the inner `payload["question"]` (from LLM-synthesized text or pre-formed).
- `approval` — render `payload["summary"]` + bullet list of `payload["side_effects"]` + options.
- `needs_human` — same as today's relay (question + options + side_effects).
- `override` — render `payload["unresolved_capabilities"]` + alternatives.
- `capability_gate` — render `"About to {capability_name}: {params_summary}. Approve?"`.

**Action 3:** Front emits user answer on `TOPIC_HIL_RESPONSE` with envelope:

```python
HILResponseEnvelope(
    hil_request_id=incoming.hil_request_id,
    kind=incoming.kind,
    responded_at_ms=int(time.time()*1000),
    payload={...kind-specific user answer...},
).to_dict()
```

**Note on legacy `task.suspended.v1` / `task.resume.v1`:** Concierge FSM still uses these for its own state tracking. The HIL service does NOT publish/subscribe to them. They are concierge-internal in E1. (E4 may delete them if the FSM no longer needs them after migration.)

**Tests:** `tests/k1/concierge/test_front_hil_unified_envelope.py` (NEW, isolated to Front module — no full-stack)

- Construct Front in HITL_RELAY mode with each of the 5 `kind` values; verify the prompt rendered to the LLM contains expected text.
- Construct Front in HITL_RESOLVE mode; verify the response envelope emitted matches `HILResponseEnvelope` shape with correct `hil_request_id`.
- Backward compat: feed Front the LEGACY concierge payload shape (`{task_id, hil_type, question, ...}` without `hil_request_id`); Front falls back to legacy rendering AND logs a deprecation warning. (This safety net exists only during E1; removed in E4 cleanup.)

**Run:** `pytest tests/k1/concierge/test_front_hil_unified_envelope.py -v`

---

### Issue E1.M2.2 — Round-trip integration test (Service ↔ Front, no kernel)

**File:** `tests/k1/hil/test_service_front_roundtrip.py`

**Setup:** in-memory bus (use `k1.bus.local_bus.LocalBus` directly OR a hand-rolled dict-based stub; no full kernel boot).

- Construct `HumanInTheLoopService` subscribed to bus.
- Construct minimal Front handler that subscribes to `TOPIC_HIL_REQUEST` and immediately echoes a canned answer on `TOPIC_HIL_RESPONSE`.

**Tests:**

- `test_clarification_roundtrip` — `await svc.ask_clarification(req)` returns canned answer.
- `test_approval_roundtrip` — same with approval.
- `test_gate_capability_roundtrip` — AMBER contract, Front approves, gate returns `ASK_APPROVED`.
- `test_concurrent_3_kinds_roundtrip` — fire clarification + approval + gate concurrently; all resolve correctly.
- `test_correlation_id_isolation` — fire 2 clarifications concurrently; second response (with right `hil_request_id`) goes to second future, not first.

**Run:** `pytest tests/k1/hil/test_service_front_roundtrip.py -v`

---

## E1 Exit Criteria (all must pass before starting E2/E3)

1. `pytest tests/k1/hil/ -v` — all green.
2. `pytest tests/k1/kernel/test_hil_port_protocol.py -v` — all green.
3. `pytest tests/k1/concierge/test_front_hil_unified_envelope.py -v` — all green.
4. `python -c "from k1.hil import HumanInTheLoopService; from k1.kernel.ports import IHILPort; svc = HumanInTheLoopService(...); assert isinstance(svc, IHILPort)"` — succeeds.
5. **No production caller wired** — `grep -r "HumanInTheLoopService" k1/` returns ONLY hits in `k1/hil/` and tests. `k1/concierge/factory.py`, `k1/planner/factory.py`, `k1/orchestrator/`, `k1/fabric/factory.py`, `k1/kernel/service.py` are unchanged.
6. **Old paths still work** — re-run any existing concierge HIL test (e.g. `tests/k1/concierge/test_m09_e93_hitl_recovery.py`) → still green.

**Commit message convention:**

```
hil(E1.M1.N): <issue title>

- <bullet of what changed>
- <bullet of tests added>
Refs: docs/plans/HIL_UNIFICATION_PLAN.md#issue-e1m1N
```

---

# Epic E2 — Capability contract schema extension

**Goal:** Add optional `requires_human_confirmation: bool` and structured `side_effects: [...]` to the capability-contract schema. Both honored by the `SafetyBandPolicy` (Decision #1: BOTH supported). Existing contracts validate unchanged. No behavior change yet — `gate_capability` consumes them in E3.

**Pre-flight inventory (already done):**

- Schema: [k1/contracts/schemas/tool_contract.schema.json](k1/contracts/schemas/tool_contract.schema.json) — declares `safety_band_min` enum (`GREEN | AMBER | RED | CRISIS`).
- Validator: [k1/fabric/core/contract_validator.py](k1/fabric/core/contract_validator.py) — uses jsonschema, schema map at line 44.
- Loader: [k1/fabric/contracts/tool_contract.py](k1/fabric/contracts/tool_contract.py) `_build_contract` at line 198 maps YAML → `CapabilityContract`.
- Dataclass: [k1/fabric/types.py](k1/fabric/types.py) line 661 `CapabilityContract` (frozen dataclass).
- Serialization: `to_dict` line ~733, `from_dict` line ~756.
- Existing AMBER contract example: [k1/contracts/tools/calendar_delete_event.yaml](k1/contracts/tools/calendar_delete_event.yaml).
- Three sister schemas exist: `tool_contract.schema.json`, `agent_contract.schema.json`, `workflow_contract.schema.json`, `prompt_contract.schema.json`. **All four** must get the same fields for consistency.

---

## Issue E2.1 — Extend the four contract JSON schemas

**Files (all four):**

- [k1/contracts/schemas/tool_contract.schema.json](k1/contracts/schemas/tool_contract.schema.json)
- `k1/contracts/schemas/agent_contract.schema.json`
- `k1/contracts/schemas/workflow_contract.schema.json`
- `k1/contracts/schemas/prompt_contract.schema.json`

**Add to each `properties` block (do NOT add to `required`):**

```json
"requires_human_confirmation": {
  "type": "boolean",
  "description": "Explicit override for HIL gating. true → always ask user; false → never ask (overrides safety_band inference, except RED still asks). Omit (null) → infer from safety_band_min and side_effects."
},
"side_effects": {
  "type": "array",
  "description": "Structured declaration of side effects this capability produces. Used by HIL service to render approval prompts and by audit log. Empty/omitted → no side effects.",
  "items": {
    "type": "object",
    "required": ["kind", "target"],
    "properties": {
      "kind": {
        "type": "string",
        "enum": [
          "data_write",       "data_delete",      "data_modify",
          "external_api_call","payment",          "physical_actuation",
          "notification_send","irreversible_op",  "third_party_share"
        ],
        "description": "Category of side effect"
      },
      "target": {
        "type": "string",
        "description": "What the side effect targets (e.g. 'calendar.event', 'payment.card.ending_4242', 'door.front')"
      },
      "reversible": {
        "type": "boolean",
        "default": false,
        "description": "Whether this side effect can be undone after execution"
      },
      "cost_estimate": {
        "type": "object",
        "properties": {
          "currency": {"type": "string"},
          "amount":   {"type": "number", "minimum": 0}
        }
      },
      "description": {"type": "string"}
    }
  }
}
```

**Schema validation rule to add (`oneOf` or `if/then`):** If `requires_human_confirmation` is present AND `safety_band_min == "GREEN"` AND `requires_human_confirmation == false` AND `side_effects` is non-empty → schema validation FAILS (you can't claim "no HIL needed" while declaring side effects). This catches contract authoring mistakes at validation time.

```json
"allOf": [
  {
    "if": {
      "properties": {
        "requires_human_confirmation": {"const": false},
        "side_effects": {"minItems": 1}
      },
      "required": ["requires_human_confirmation", "side_effects"]
    },
    "then": {
      "properties": {
        "safety_band_min": {"not": {"const": "GREEN"}}
      }
    }
  }
]
```

**Tests:** `tests/k1/contracts/test_tool_contract_schema_hil_fields.py` (NEW)

| Test | Asserts |
|------|---------|
| `test_existing_contract_still_validates` | All current `k1/contracts/tools/*.yaml` files validate unchanged (no `requires_human_confirmation`/`side_effects` present) |
| `test_requires_human_confirmation_optional` | Contract with `requires_human_confirmation: true` validates |
| `test_requires_human_confirmation_false_validates` | Same with `false` |
| `test_side_effects_array_validates` | Contract with one structured side_effect entry validates |
| `test_side_effects_kind_enum_enforced` | `kind: "bogus"` → validation error |
| `test_side_effects_requires_kind_and_target` | Missing `target` → validation error |
| `test_cost_estimate_optional` | side_effect without `cost_estimate` validates |
| `test_payment_side_effect_with_cost` | Full payment example validates |
| `test_inconsistent_green_no_hil_with_side_effects_rejected` | GREEN + `requires_human_confirmation=false` + non-empty side_effects → schema error |

**Run:** `pytest tests/k1/contracts/test_tool_contract_schema_hil_fields.py -v`

---

## Issue E2.2 — Extend `CapabilityContract` dataclass

**File:** [k1/fabric/types.py](k1/fabric/types.py) — modify `CapabilityContract` (line 661) AND `AgentContract` (line ~1175).

**Add fields after `availability` (line 711):**

```python
    # ---- HIL Policy Metadata (E2 — HIL Unification) ----
    # None = inferred from safety_band_min + side_effects via SafetyBandPolicy.
    # True/False = explicit override (RED contracts still always ask).
    requires_human_confirmation: bool | None = None
    side_effects: list[dict[str, Any]] = field(default_factory=list)
```

**Update `to_dict()` (after line 754):**

```python
    "requires_human_confirmation": self.requires_human_confirmation,
    "side_effects": [dict(se) for se in self.side_effects],
```

**Update `from_dict()` (after line 793):**

```python
    requires_human_confirmation=data.get("requires_human_confirmation"),  # None default preserves "infer"
    side_effects=list(data.get("side_effects", [])),
```

**Update `_build_contract()` in [k1/fabric/contracts/tool_contract.py](k1/fabric/contracts/tool_contract.py) line ~237 (after `availability=`):**

```python
    requires_human_confirmation=body.get("requires_human_confirmation"),  # None preserves "infer"
    side_effects=list(body.get("side_effects", [])),
```

**Update `AgentContract.from_dict` and `to_dict`** (line 867, 1233 area) — same two field additions. AgentContract inherits from CapabilityContract so the field declaration is automatic; only the explicit (de)serialization paths need lines added.

**Frozen dataclass note:** `field(default_factory=list)` for mutable default is required. List is mutated only by `from_dict`/`_build_contract`; consumers must NOT mutate `contract.side_effects` after construction (frozen guarantees the dataclass attr can't be reassigned, but the list inside is not deep-frozen — convention only).

**Tests:** `tests/k1/fabric/test_capability_contract_hil_fields.py` (NEW)

| Test | Asserts |
|------|---------|
| `test_default_requires_human_confirmation_is_none` | `CapabilityContract().requires_human_confirmation is None` |
| `test_default_side_effects_empty_list` | `CapabilityContract().side_effects == []` |
| `test_to_dict_round_trip_with_explicit_true` | construct → to_dict → from_dict preserves `requires_human_confirmation=True` |
| `test_to_dict_round_trip_with_side_effects` | preserves a 2-entry `side_effects` list |
| `test_to_dict_round_trip_with_none_explicit` | `None` round-trips as `None` (not omitted) |
| `test_from_yaml_loader_populates_fields` | Use `_build_contract` on a body dict containing both fields → `CapabilityContract` has them |
| `test_from_yaml_loader_legacy_contract` | Body dict WITHOUT either field → `requires_human_confirmation is None`, `side_effects == []` |
| `test_agent_contract_inherits_hil_fields` | `AgentContract` exposes both fields with defaults |

**Run:**

```powershell
pytest tests/k1/fabric/test_capability_contract_hil_fields.py -v
pytest tests/k1/fabric/test_tool_schema_validation.py -v   # regression
```

---

## Issue E2.3 — Add `CapabilityContractView` factory in `k1/hil/types.py`

**Why:** HIL service should not import `k1.fabric.types.CapabilityContract` directly — fabric imports HIL (E3), so the reverse would create a cycle. Provide a small adapter function `view_from_contract(c) -> CapabilityContractView` that callers in fabric use to construct the view at the call site.

**File:** `k1/hil/types.py` — add helper function:

```python
def view_from_capability_contract(contract: Any) -> CapabilityContractView:
    """Adapter from k1.fabric.types.CapabilityContract → CapabilityContractView.

    Accepts any object exposing the four attributes via duck typing (no import).
    Used by k1/fabric/fabric.py at the gate call site.
    """
    return CapabilityContractView(
        name=getattr(contract, "name", ""),
        safety_band_min=getattr(contract, "safety_band_min", "GREEN"),
        requires_human_confirmation=getattr(contract, "requires_human_confirmation", None),
        side_effects=list(getattr(contract, "side_effects", [])),
        description=getattr(contract, "description", ""),
    )
```

**Tests:** add to `tests/k1/hil/test_types.py`:

- `test_view_from_real_capability_contract` — pass a real `CapabilityContract` instance, verify all 5 view fields populated.
- `test_view_from_legacy_contract` — pass a `CapabilityContract` constructed with NO HIL fields → view has `requires_human_confirmation=None`, `side_effects=[]`.
- `test_view_from_duck_typed_object` — pass a `SimpleNamespace(name=..., safety_band_min=..., ...)` → view constructed.

**Run:** `pytest tests/k1/hil/test_types.py::test_view_from_real_capability_contract -v`

---

## Issue E2.4 — Annotate sensitive existing contracts (audit + targeted edits)

**Audit pass:** Review each `k1/contracts/tools/*.yaml`. Decide for each:

- Is it AMBER/RED with side effects that should ALWAYS ask the user? → add `requires_human_confirmation: true`.
- Is it GREEN with no side effects? → leave unchanged (default `None` → infer ALLOW).

**Concrete edits expected (verify with grep `safety_band_min` across `k1/contracts/tools/`):**

| File | Current band | Action |
|------|--------------|--------|
| `calendar_delete_event.yaml` | AMBER | Add `requires_human_confirmation: true`, add `side_effects: [{kind: data_delete, target: "calendar.event", reversible: false}]` |
| `calendar_create_event.yaml` | AMBER | Add `requires_human_confirmation: true`, `side_effects: [{kind: data_write, target: "calendar.event", reversible: true}]` |
| `notes_create.yaml` | AMBER | Add `requires_human_confirmation: false` (low-stakes write — let policy default ASK be overridden; or leave `None` and document the choice) |
| `recipe_meal_plan.yaml` | AMBER | Add `requires_human_confirmation: true` (multi-day plan, user should approve) |
| `build_agent.yaml` | AMBER | Add `requires_human_confirmation: true` (creates new agent — meta-level, must confirm) |
| All read-only weather/search contracts | GREEN | Leave unchanged |

**Documentation:** Append a section to `k1/contracts/tools/README.md` (CREATE if missing — this IS a structural doc so it's allowed):

- "HIL gating policy" subsection.
- Decision tree: when to set `requires_human_confirmation` explicitly vs. let safety band infer.
- Side-effect taxonomy reference.

**Tests:** `tests/k1/contracts/test_tool_contract_hil_annotations.py` (NEW)

| Test | Asserts |
|------|---------|
| `test_calendar_delete_requires_confirmation` | Load `calendar_delete_event.yaml`, assert `requires_human_confirmation is True` and side_effects has data_delete |
| `test_calendar_create_requires_confirmation` | Same for create |
| `test_recipe_meal_plan_requires_confirmation` | Same |
| `test_build_agent_requires_confirmation` | Same |
| `test_weather_contracts_no_explicit_hil` | All weather/search contracts have `requires_human_confirmation is None` |

**Run:** `pytest tests/k1/contracts/test_tool_contract_hil_annotations.py -v`

---

## E2 Exit Criteria

1. All four contract schemas accept the new fields with the inconsistency rule.
2. `CapabilityContract` + `AgentContract` dataclasses carry both fields with safe defaults.
3. `_build_contract` populates them from YAML.
4. `view_from_capability_contract` adapter works without importing fabric into HIL.
5. Sensitive contracts annotated; weather/search contracts untouched.
6. Existing fabric tests still pass: `pytest tests/k1/fabric/test_tool_schema_validation.py tests/k1/fabric/test_capability_contract*.py -v`.
7. **No fabric `execute()` change yet** — E3 consumes the new fields. Run `python -c "from k1.fabric.types import CapabilityContract; c = CapabilityContract(); print(c.requires_human_confirmation, c.side_effects)"` → prints `None []`.
8. **No HIL service change** — E2 only touches contracts + types.

---

---

# Epic E3 — Fabric capability gate (NEW HIL path)

**Goal:** Add the missing pre-execution HIL gate inside `CapabilityFabric._execute_impl()`. This is the only epic that creates a brand-new HIL path. After E3, every capability invocation (planner-driven, concierge-driven, orchestrator-driven, direct) automatically goes through HIL when the contract requires it.

**Pre-flight inventory (already done):**

- `CapabilityFabric.__init__` at [k1/fabric/fabric.py L268-289](k1/fabric/fabric.py#L268) — kwargs-only signature; safe to add `hil_port=` without breaking call sites.
- `CapabilityFabric._execute_impl` at [k1/fabric/fabric.py L380](k1/fabric/fabric.py#L380) — 9-step pipeline; insertion point is between Step 2 (resolve, line ~424) and Step 3 (build context, line ~474).
- `CapabilityResult.failure_result(...)` is the standard failure return shape — already used throughout `_execute_impl`.
- `EventEmitter` at `self._event_emitter` — has `emit_invoked` etc.
- Fabric construction: `FabricFactory._construct_fabric` in [k1/fabric/factory.py](k1/fabric/factory.py) — passes kwargs to `CapabilityFabric(...)`. We thread `hil_port` through `create_with_ports` / `create_shared` → `_construct_fabric` → `CapabilityFabric(hil_port=...)`.

---

## E3.M1 — Wire `IHILPort` through fabric

### Issue E3.M1.1 — Add `hil_port` parameter to `CapabilityFabric.__init__`

**File:** [k1/fabric/fabric.py](k1/fabric/fabric.py) line 268.

**Change:**

```python
def __init__(
    self,
    *,
    resolver: Any,
    context_builder: Any,
    validation_pipeline: Any,
    event_emitter: EventEmitter,
    registry: Any,
    provider_factory: Any,
    circuit_breakers: Optional[Dict[str, Any]] = None,
    dispatcher: Optional[FabricDispatcher] = None,
    config: Optional[FabricConfig] = None,
    hil_port: Optional["IHILPort"] = None,   # NEW — None disables gate (test harness path)
) -> None:
    ...
    self._hil_port = hil_port
```

**Type import (top of file, TYPE_CHECKING block to avoid runtime cycle):**

```python
if TYPE_CHECKING:
    from k1.kernel.ports.hil_port import IHILPort
```

**Tests:** `tests/k1/fabric/test_fabric_init_hil_port.py` (NEW)

- `test_default_hil_port_is_none` — construct with no `hil_port` kwarg → `_hil_port is None`.
- `test_explicit_hil_port_stored` — construct with stub `IHILPort` → stored on `_hil_port`.
- `test_existing_construction_unchanged` — re-run a couple of existing fabric construction tests to confirm no regressions.

**Run:** `pytest tests/k1/fabric/test_fabric_init_hil_port.py -v`

---

### Issue E3.M1.2 — Thread `hil_port` through `FabricFactory`

**File:** [k1/fabric/factory.py](k1/fabric/factory.py) — modify three entry points: `create_with_ports`, `create_shared`, `_construct_fabric`.

Each entry point gains `hil_port: Optional[IHILPort] = None` kwarg, passed through to `CapabilityFabric(hil_port=hil_port)`.

**Tests:** `tests/k1/fabric/test_fabric_factory_hil_port.py` (NEW)

- `test_create_with_ports_threads_hil_port` — pass stub, verify `fabric._hil_port is stub`.
- `test_create_shared_threads_hil_port` — same.
- `test_legacy_call_without_hil_port` — omit kwarg, fabric still constructed successfully with `_hil_port is None`.

**Run:** `pytest tests/k1/fabric/test_fabric_factory_hil_port.py -v`

---

## E3.M2 — Insert gate Step 2.5

### Issue E3.M2.1 — Add `_run_hil_gate` private method

**File:** [k1/fabric/fabric.py](k1/fabric/fabric.py) — add private method on `CapabilityFabric` (between `_resolve` and `_build_context`).

```python
async def _run_hil_gate(
    self,
    request: CapabilityRequest,
    contract: Any,           # CapabilityContract from k1.fabric.types
    trace_id: str,
) -> Optional[CapabilityResult]:
    """Pre-execution HIL gate. Returns None to ALLOW, or a failure CapabilityResult to short-circuit.

    Skips entirely when self._hil_port is None (no kernel wiring).
    """
    if self._hil_port is None:
        return None   # gate disabled — allow execution

    # Lazy imports to avoid module-import cycles
    from k1.hil.types import (
        CapabilityGateRequest, GateOutcome,
        view_from_capability_contract,
    )

    gate_req = CapabilityGateRequest(
        caller_key=f"fabric:{contract.name}",
        trace_id=trace_id,
        capability_name=contract.name,
        contract=view_from_capability_contract(contract),
        params=dict(request.params or {}),
        params_summary=self._summarize_params(request.params),
        timeout_ms=self._config.hil_gate_timeout_ms,
    )
    decision = await self._hil_port.gate_capability(gate_req)

    if decision.outcome in (GateOutcome.ALLOW, GateOutcome.ASK_APPROVED):
        return None  # proceed to execution

    error_code = {
        GateOutcome.DENY:         "hil_denied",
        GateOutcome.ASK_REJECTED: "hil_rejected_by_user",
        GateOutcome.TIMEOUT:      "hil_timeout",
    }.get(decision.outcome, "hil_unknown")

    return CapabilityResult.failure_result(
        request_id=request.request_id,
        error_code=error_code,
        error_message=decision.reason or "Capability blocked by Human-in-the-Loop gate",
        retriable=False,
        trace_id=trace_id,
        duration_ms=0,
    )

@staticmethod
def _summarize_params(params: Optional[dict]) -> str:
    """One-line summary of params for user-facing prompt. Redacts long values."""
    if not params:
        return "(no parameters)"
    pairs = []
    for k, v in params.items():
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        pairs.append(f"{k}={s}")
    return ", ".join(pairs[:5]) + ("..." if len(pairs) > 5 else "")
```

**Tests:** `tests/k1/fabric/test_fabric_hil_gate_internal.py` (NEW)

- `test_no_hil_port_returns_none` — `_run_hil_gate` with `_hil_port=None` returns `None`.
- `test_allow_returns_none` — stub returns `GateDecision(outcome=ALLOW, ...)` → `_run_hil_gate` returns None.
- `test_ask_approved_returns_none` — stub returns `ASK_APPROVED` → returns None.
- `test_ask_rejected_returns_failure_result` — stub returns `ASK_REJECTED` → returns `CapabilityResult` with `error_code="hil_rejected_by_user"`, `retriable=False`.
- `test_deny_returns_failure_result` — `error_code="hil_denied"`.
- `test_timeout_returns_failure_result` — `error_code="hil_timeout"`.
- `test_summarize_params_truncates_long_values` — value > 60 chars gets `...` suffix.
- `test_summarize_params_truncates_many_keys` — 7 keys → first 5 + `...`.

**Run:** `pytest tests/k1/fabric/test_fabric_hil_gate_internal.py -v`

---

### Issue E3.M2.2 — Insert gate call in `_execute_impl` between Step 2 and Step 3

**File:** [k1/fabric/fabric.py](k1/fabric/fabric.py) — modify `_execute_impl` around line 470.

**Insertion point:** Immediately after the lines:

```python
provider_id = resolved.provider_config.provider_id
provider_type = resolved.provider_config.provider_type
contract = resolved.contract
```

**Insert:**

```python
# --- Step 2.5: HIL gate (E3) ---
gate_start = time.perf_counter()
gate_failure = await self._run_hil_gate(request, contract, trace_id)
gate_ms = (time.perf_counter() - gate_start) * 1000.0

if gate_failure is not None:
    elapsed_ms = _elapsed_ms(start_time)
    gate_failure = CapabilityResult.failure_result(
        request_id=request.request_id,
        error_code=gate_failure.error.code,
        error_message=gate_failure.error.message,
        retriable=False,
        trace_id=trace_id,
        duration_ms=elapsed_ms,
        resolution_time_ms=resolve_ms,
    )
    self._emit_failure(request, gate_failure, start_time, provider_id)
    fabric_logger.result_return(
        trace_id=trace_id,
        request_id=request.request_id,
        capability_name=capability_name,
        provider_id=provider_id,
        duration_ms=elapsed_ms,
        success=False,
        error_code=gate_failure.error.code,
    )
    self._update_metrics(capability_name, elapsed_ms, success=False)
    self._emit_learning(
        request=request,
        provider_id=provider_id,
        success=False,
        duration_ms=elapsed_ms,
        error_code=gate_failure.error.code,
    )
    return self._finalize_execution_metrics(
        request=request,
        result=gate_failure,
        provider_type=provider_type,
        exec_start=exec_start,
    )

if self._hil_port is not None:
    logger.info(
        "hil_gate trace_id=%s capability=%s duration_ms=%.3f decision=allow",
        trace_id, capability_name, gate_ms,
    )
```

**Tests:** `tests/k1/fabric/test_fabric_execute_with_gate.py` (NEW)

| Test | Asserts |
| --- | --- |
| `test_green_capability_calls_gate_then_executes` | construct fabric with stub HIL recording calls; execute GREEN capability; HIL.gate_capability called once, returns ALLOW, provider invoked, success result. |
| `test_amber_user_approves_executes` | AMBER contract; stub returns `ASK_APPROVED`; provider invoked; success result. |
| `test_amber_user_rejects_returns_hil_rejected` | stub returns `ASK_REJECTED`; provider NOT invoked; result has `error_code="hil_rejected_by_user"`, `success=False`. |
| `test_red_capability_asks` | RED contract; verify `_run_hil_gate` is called; on approve, executes; on reject, fails. |
| `test_no_hil_port_skips_gate` | construct fabric with `hil_port=None`; execute AMBER capability; provider invoked directly (gate disabled). |
| `test_gate_failure_emits_failed_event` | reject path → `event_emitter.emit_failed(...)` called; learning signal emitted. |
| `test_gate_failure_increments_metrics` | metrics show 1 failure with `error_code="hil_rejected_by_user"`. |
| `test_gate_does_not_run_when_resolution_fails` | resolver returns None (Step 2 failure); `_run_hil_gate` NOT called. |

**Run:** `pytest tests/k1/fabric/test_fabric_execute_with_gate.py -v`

---

### Issue E3.M2.3 — Update existing fabric tests to inject stub HIL or rely on `None` default

**File scan:** Find all tests constructing `CapabilityFabric` directly:

```powershell
Get-ChildItem tests/k1/fabric -Recurse -Filter "*.py" | Select-String -Pattern "CapabilityFabric\(" -List
```

For each, choose ONE strategy:

- **Default**: Don't pass `hil_port` → `_hil_port is None` → gate is no-op. Existing test continues to pass unchanged. **Strongly preferred** for non-HIL tests.
- **Approve-all stub**: For tests that exercise AMBER capabilities and would now be gated, inject a stub:

  ```python
  class _AlwaysApproveHIL:
      async def gate_capability(self, req):
          from k1.hil.types import GateDecision, GateOutcome
          return GateDecision(outcome=GateOutcome.ALLOW, hil_request_id=None, reason="test_stub")
      # … other IHILPort methods raise NotImplementedError
  ```

**Concrete known callers:**

- `tests/k1/fabric/test_fabric_execute_pipeline.py` — likely uses GREEN; verify no change needed.
- `tests/k1/fabric/test_agent_431_432.py` — uses agent contracts; check `safety_band_min`.
- Any test loading `calendar_delete_event.yaml` etc. → must inject `_AlwaysApproveHIL` (since E2.4 marked it `requires_human_confirmation: true`).

**Run after changes:** `pytest tests/k1/fabric/ -v` — full fabric suite green.

---

### Issue E3.M2.4 — Add `hil_gate_timeout_ms` to `FabricConfig`

**File:** [k1/fabric/types.py](k1/fabric/types.py) `FabricConfig` dataclass.

```python
@dataclass(frozen=True)
class FabricConfig:
    ...
    hil_gate_timeout_ms: int = 120_000   # E3 — pass-through to gate_capability
```

**Use in `_run_hil_gate`:** `timeout_ms=self._config.hil_gate_timeout_ms`.

**Test:** `tests/k1/fabric/test_fabric_config_hil.py` — defaults match design.

**Run:** `pytest tests/k1/fabric/test_fabric_config_hil.py -v`

---

## E3 Exit Criteria

1. `pytest tests/k1/fabric/test_fabric_init_hil_port.py tests/k1/fabric/test_fabric_factory_hil_port.py tests/k1/fabric/test_fabric_hil_gate_internal.py tests/k1/fabric/test_fabric_execute_with_gate.py tests/k1/fabric/test_fabric_config_hil.py -v` — all green.
2. **Full fabric suite still green:** `pytest tests/k1/fabric/ -v` — no regressions.
3. **No HIL service consumed yet by other epics** — `grep -r "_run_hil_gate\|gate_capability" k1/` returns hits ONLY in `k1/fabric/` and `k1/hil/`.
4. **Backward compatibility preserved:** Existing callers of `FabricFactory.create_*` without `hil_port` kwarg construct fabric with gate disabled.
5. **Gate enforces both axes:**
   - Explicit `requires_human_confirmation: true` on a GREEN contract → gate asks.
   - GREEN + no side effects + `requires_human_confirmation: None` → gate short-circuits ALLOW (fast path verified by stub HIL recording the decision).
6. Capability execution latency overhead with `hil_port=None`: < 5 µs per call (single None check + early return).

---

---

# Epic E4 — Concierge migration

**Goal:** Delete concierge `HILCoordinator` and `SuspensionManager` (relocated). FSM, tools, and factory all call the unified `IHILPort` from kernel. The `task.suspended.v1` / `task.resume.v1` bus topics become Front-side rendering hooks, not HIL transport — Front subscribes to the unified `k1.hil.request.v1` (E1.M2) and emits `task.suspended.v1` for compatibility with the React UI.

**Pre-flight inventory (already done):**

- `k1/concierge/protocols/hitl_coordinator.py` (~600 LOC) — entire file deleted.
- `k1/concierge/protocols/suspension_manager.py` — relocated to `k1/hil/suspension.py` in E1; leave shim for one cycle, then delete.
- `k1/concierge/protocols/hitl.py` — keep `SafetyBand`, `escalate_safety_band`, `_get_hil_timeouts` (used elsewhere); HIL request/response dataclasses replaced by `k1/hil/types.py`.
- `k1/concierge/fsm/controller.py`:
  - L383: `self._hil_coordinator: Any | None = None` → replace with `self._hil_port`.
  - L528: `set_hitl_coordinator(coordinator)` → rename to `set_hil_port(hil_port)`.
  - L2752+: HITL handling site (`get_hil_count`, `_config.max_rounds`) — read from new service.
  - Other call sites grep returns ~10 hits.
- `k1/concierge/tools/implementations.py`:
  - L1138-1163 — `ctx.hil_coordinator.get_pending_request(...)` and `validate_before_invoke(...)` block in `execute_invoke_capability`. **Delete entirely** — fabric gate (E3) now enforces this.
  - L96 — `hil_coordinator: HILCoordinatorLike | None` parameter on `execute_invoke_capability`. Remove parameter.
- `k1/concierge/factory.py` (Step 11) — currently constructs `HILCoordinator(...)`. Replace with: accept `hil_port` from kernel, set on FSM via `fsm.set_hil_port(hil_port)`.
- `k1/concierge/sessions/types.py` (or wherever `front_ctx` is defined) — `hil_coordinator: Any` field → rename to `hil_port: IHILPort | None`.

**Tests touched (must update or rewrite):**

- `tests/k1/concierge/test_m09_e93_hitl_recovery.py` — rewrite around `HumanInTheLoopService` + `HILLedgerAdapter`.
- `tests/k1/concierge/test_m09_e95_recovery.py` — rewrite recovery scenarios.
- `tests/k1/concierge/test_m09_e92_suspension_recovery.py` — relocate to `tests/k1/hil/test_suspension_recovery.py`.
- `tests/k1/concierge/test_concierge_factory.py` L388 — assert `session.fsm._hil_port is not None`.
- `tests/k1/concierge/test_concierge_factory_stress.py` L98-145 — replace `inject(hil_coordinator=...)` with `inject(hil_port=...)`.
- `tests/k1/concierge/test_bootstrap_smoke.py` L163-164 — assert `runtime.fsm._hil_port is not None`.
- `tests/k1/concierge/test_tool_fabric_port_wiring.py` L460-495 — drop `hil_coordinator=hil` kwarg; rewrite `validate_before_invoke` tests as fabric-gate tests (move to E3 or delete as duplicate).

---

## E4.M1 — Replace coordinator with `IHILPort`

### Issue E4.M1.1 — Add `_hil_port` field + `set_hil_port` to `ConciergeController`

**File:** [k1/concierge/fsm/controller.py](k1/concierge/fsm/controller.py)

**Changes:**

```python
# L383 area — replace
self._hil_port: "IHILPort | None" = None  # Unified HIL service (E4)

# L528 area — replace set_hitl_coordinator
def set_hil_port(self, hil_port: "IHILPort") -> None:
    """Attach unified HIL service. Replaces legacy set_hitl_coordinator()."""
    self._hil_port = hil_port
    logger.info("ConciergeController.set_hil_port: attached %s", type(hil_port).__name__)
```

**Type import (TYPE_CHECKING):**

```python
if TYPE_CHECKING:
    from k1.kernel.ports.hil_port import IHILPort
```

**Tests:** `tests/k1/concierge/test_controller_hil_port.py` (NEW)

- `test_default_hil_port_none` — fresh controller has `_hil_port is None`.
- `test_set_hil_port_attaches` — `set_hil_port(stub)` → `_hil_port is stub`.
- `test_set_hil_port_replaces` — second call replaces first.

**Run:** `pytest tests/k1/concierge/test_controller_hil_port.py -v`

---

### Issue E4.M1.2 — Update FSM HITL handling site (L2752+)

**File:** [k1/concierge/fsm/controller.py](k1/concierge/fsm/controller.py) L2752+ block (currently calls `_hil_coordinator.get_hil_count` and reads `_config.max_rounds`).

**Replace** the inline logic with:

```python
# E4: delegate to unified HIL service. Round budget enforced by service.
if self._hil_port is not None:
    from k1.hil.types import NeedsHumanRequest

    needs_req = NeedsHumanRequest(
        caller_key=f"concierge:{task_id}",
        trace_id=trace_id,
        task_id=task_id,
        question=question,
        suggested_options=options,
        timeout_ms=self._config.hil_clarification_timeout_ms,
    )
    response = await self._hil_port.needs_human(needs_req)
    # response.outcome ∈ {ANSWERED, TIMEOUT, MAX_ROUNDS_EXCEEDED}
    return response
```

**Helper:** delete the `_should_escalate_safety_band` and round-counting logic from controller — moved into `SafetyBandPolicy` (E1.M1.5).

**Tests:** Existing FSM HITL tests (`test_m09_e93_hitl_recovery.py`) rewritten as integration tests that:

- Construct a real `HumanInTheLoopService` with stub event/llm ports.
- Attach to controller via `set_hil_port`.
- Trigger `needs_human` from FSM → verify event published + service awaits response.

**Run:** `pytest tests/k1/concierge/test_m09_e93_hitl_recovery.py -v`

---

### Issue E4.M1.3 — Strip `validate_before_invoke` and `get_pending_request` from tool

**File:** [k1/concierge/tools/implementations.py](k1/concierge/tools/implementations.py) L1130-1170 (the `execute_invoke_capability` HIL block).

**Delete the entire `if ctx.hil_coordinator is not None and ctx.active_task_id:` block** (L1138-1167). Fabric gate (E3) now provides L2 enforcement at every capability invocation regardless of caller.

**Also delete:**

- L96 `hil_coordinator: HILCoordinatorLike | None = None` parameter — unused after the block deletion.
- L50 `from k1.planner.types import HILCoordinatorLike` import.

**Tests:**

- Update `tests/k1/concierge/test_tool_fabric_port_wiring.py`:
  - DELETE `test_invoke_capability_blocks_red` (L491+) — now duplicated by E3 fabric tests.
  - DELETE `test_invoke_capability_allows_when_validate_returns_allow` (L460+) — same.
  - REPLACE with `test_invoke_capability_passes_through_to_fabric` proving the tool no longer references HIL.

**Run:** `pytest tests/k1/concierge/test_tool_fabric_port_wiring.py -v`

---

### Issue E4.M1.4 — Delete `k1/concierge/protocols/hitl_coordinator.py`

**Action:** Hard delete the file. No shim — Family-OS scale, ~5 callers all updated above.

**Cleanup imports:**

- `k1/concierge/protocols/__init__.py` — remove `HILCoordinator` export.
- Search-and-destroy: `grep -r "from k1.concierge.protocols.hitl_coordinator" .` → must return zero hits before commit.
- `k1/concierge/sessions/types.py` (or `front_ctx` definition) — rename `hil_coordinator: Any` field → `hil_port: "IHILPort | None"`.

**Tests:** N/A (deletion). Verify build:

```powershell
python -c "import k1.concierge"
pytest tests/k1/concierge/ --collect-only -q
```

---

### Issue E4.M1.5 — Migrate `suspension_manager` to `k1/hil/suspension.py`

**File ops:**

```powershell
Move-Item k1/concierge/protocols/suspension_manager.py k1/hil/suspension.py
```

**Update imports** in (grep first):

- `k1/concierge/fsm/controller.py` — `from k1.concierge.protocols.suspension_manager import SuspensionManager` → `from k1.hil.suspension import SuspensionManager`.
- `k1/concierge/protocols/hitl_coordinator.py` (already deleted in E4.M1.4 — N/A).
- `k1/hil/service.py` — import `SuspensionManager` for use inside `HumanInTheLoopService`.
- All `tests/k1/concierge/test_m09_e9*` files — update imports.

**Module path** inside the relocated file:

- `from k1.concierge.protocols.suspension import (...)` — keep the suspension dataclasses where they are; `suspension_manager.py` only moves. (Or also relocate `suspension.py` → `k1/hil/suspension_types.py` for full cleanliness — defer to E4.M2.)

**Tests:** Move `tests/k1/concierge/test_m09_e92_suspension_recovery.py` → `tests/k1/hil/test_suspension_recovery.py`. Update imports.

**Run:** `pytest tests/k1/hil/test_suspension_recovery.py -v`

---

### Issue E4.M1.6 — Update `ConciergeFactory` Step 11 to consume `hil_port`

**File:** [k1/concierge/factory.py](k1/concierge/factory.py) Step 11.

**Replace** the block that constructs `HILCoordinator(...)` with:

```python
# E4: Step 11 — attach unified HIL service from kernel.
# hil_port is provided by ConciergeFactory.create(... hil_port=...) caller.
if hil_port is not None:
    fsm.set_hil_port(hil_port)
else:
    logger.warning("ConciergeFactory.create: no hil_port provided; HITL gates will no-op")
```

**Add `hil_port` kwarg** to `ConciergeFactory.create()` signature (default None for test ergonomics).

**Tests:**

- `tests/k1/concierge/test_concierge_factory.py::test_factory_attaches_hil_port` — pass stub `IHILPort`, assert `session.fsm._hil_port is stub`.
- `tests/k1/concierge/test_bootstrap_smoke.py` L163-164 — update assertion to `_hil_port is not None`.
- `tests/k1/concierge/test_concierge_factory_stress.py::test_inject_hil_port_isolated` — replace `inject(hil_coordinator=)` → `inject(hil_port=)`.

**Run:** `pytest tests/k1/concierge/test_concierge_factory.py tests/k1/concierge/test_concierge_factory_stress.py tests/k1/concierge/test_bootstrap_smoke.py -v`

---

## E4.M2 — Cleanup legacy topics & dataclasses

### Issue E4.M2.1 — Audit + delete legacy concierge HIL topics

**Files to scan:**

```powershell
Select-String -Path k1/concierge/**/*.py,k1/k1_bus_core/**/*.py -Pattern 'k1\.hitl\.|hitl\.requested|hitl\.resolved|task\.suspended|task\.resume' -List
```

**Decision per topic:**

- `task.suspended.v1` / `task.resume.v1` — KEEP. Front and React UI subscribe. Concierge controller publishes them as a side effect of receiving HIL responses (rendering hook).
- `k1.hitl.requested.v1` / `k1.hitl.resolved.v1` (if present) — DELETE. Replaced by `k1.hil.request.v1` / `k1.hil.response.v1` (E1.M1.4).

**Tests:** verify no test references deleted topic names.

**Run:** `Select-String -Path tests -Pattern 'hitl\.requested|hitl\.resolved' -List` → zero hits.

---

### Issue E4.M2.2 — Optionally relocate `suspension.py` dataclasses

**File:** [k1/concierge/protocols/suspension.py](k1/concierge/protocols/suspension.py).

**Decision:** Defer. Dataclasses (`SuspensionType`, `SuspensionRequest`, `SuspensionResolution`, `SuspensionLimitExceeded`, `TaskSuspendedEvent`, `TaskResumeEvent`) are still consumed by Front for `task.suspended.v1` payload construction. Leave in concierge for now; revisit in post-E8 cleanup.

---

## E4 Exit Criteria

1. `k1/concierge/protocols/hitl_coordinator.py` does not exist.
2. `k1/concierge/protocols/suspension_manager.py` does not exist (moved to `k1/hil/suspension.py`).
3. `grep -r "HILCoordinator\|set_hitl_coordinator\|validate_before_invoke" k1/concierge/` returns zero hits.
4. `grep -r "_hil_coordinator\|hil_coordinator" k1/concierge/` returns zero hits (only `_hil_port` / `hil_port` remain).
5. `pytest tests/k1/concierge/ -v` — green (after rewrite).
6. `pytest tests/k1/hil/test_suspension_recovery.py -v` — green.
7. Concierge `execute_invoke_capability` no longer references HIL — fabric gate enforces.
8. `python -c "from k1.concierge.factory import ConciergeFactory; help(ConciergeFactory.create)"` shows `hil_port` parameter.

---

---

# Epic E5 — Planner migration

**Goal:** Delete `k1/planner/services/hil_coordinator.py` and the `HILCoordinatorLike` Protocol. SketchService and ValidateService consume the unified `IHILPort` directly. The PLAN-10 round budget (max 2 HIL rounds per plan) moves into `HumanInTheLoopService` keyed by caller.

**Pre-flight inventory (already done):**

- `k1/planner/services/hil_coordinator.py` (574 LOC) — `class HILCoordinator` with `request_clarification`, `request_approval`, `round_count`, `reset`. Uses `ILLMPort` + `IEventPort` + topics `TOPIC_HIL_CLARIFICATION` / `_RESP` / `TOPIC_HIL_APPROVAL_REQ` / `_RESP`.
- `k1/planner/services/__init__.py` L20 — exports `HILCoordinator`.
- `k1/planner/types.py` L379 — `HILCoordinatorLike` Protocol with `round_count`, `reset()`, `request_clarification()`, `request_approval()`.
- `k1/planner/stages/sketch_service.py` — `SketchService.__init__` accepts `hil_coord: HILCoordinatorLike` parameter; calls `hil_coord.request_clarification(...)` on `needs_clarification == true`.
- `k1/planner/stages/validate_service.py` L252-256 — `ValidateService.__init__(llm_port, fab, hil_coord: HILCoordinatorLike)`; property at L293 exposes `hil_coord`. Calls `request_approval(...)` for high-impact plans.
- `k1/planner/pipeline/pipeline_controller.py` `LC_PLAN_START` — calls `hil_coord.reset()` to zero round budget.
- `k1/planner/factory.py` — constructs `HILCoordinator(llm_port, event_port, config)` and threads into both stages.

**Tests touched:**

- `tests/k1/planner/test_planner_validate_3_3.py` — 25+ tests use `FakeHILCoordinator()`. Replace with `FakeHILPort()` adapter.
- `tests/k1/planner/test_planner_micro_validate_5_1_4.py` L217-222 — `_make_validate_service` helper takes hil; replace.
- `tests/k1/planner/test_planner_micro_replan_5_1.py` — `FakeSketchService` / `FakeValidateService` — drop hil_coord field.
- `tests/k1/planner/test_planner_events_1_5_5_9.py` L164 — `test_publisher_is_hil_coordinator_during_sketch` rename → `test_publisher_is_hil_service_during_sketch`.
- `tests/k1/planner/test_planner_commit_3_4.py` L636 `test_no_hil_coordinator_import` — keep but update reference.
- `tests/k1/planner/test_planner_hil_coordinator_4_2.py` — DELETE entirely; replace with `test_planner_hil_integration.py`.

---

## E5.M1 — Delete `HILCoordinator` and refit services

### Issue E5.M1.1 — Replace `hil_coord: HILCoordinatorLike` with `hil_port: IHILPort` in both services

**File:** [k1/planner/stages/sketch_service.py](k1/planner/stages/sketch_service.py)

**Constructor change:**

```python
def __init__(
    self,
    ...,
    hil_port: "IHILPort",   # was: hil_coord: HILCoordinatorLike
    ...,
) -> None:
    ...
    self._hil_port = hil_port
```

**Call site change** (where `hil_coord.request_clarification(...)` is called):

```python
from k1.hil.types import ClarificationRequest

req = ClarificationRequest(
    caller_key=f"planner:sketch:{plan_id}",
    trace_id=trace_id,
    question=question,
    context=ambiguity_context,
    options=suggested_options,           # may be []
    timeout_ms=self._config.hil_clarification_timeout_ms,
)
response = await self._hil_port.ask_clarification(req)
# response.outcome ∈ {ANSWERED, TIMEOUT, MAX_ROUNDS_EXCEEDED}
if response.outcome != HILOutcome.ANSWERED:
    return self._abort_sketch(reason=response.outcome.value)
clarification_text = response.answer_text
```

**File:** [k1/planner/stages/validate_service.py](k1/planner/stages/validate_service.py) L252+

**Constructor change:** same swap, `hil_coord` → `hil_port`. Property at L293 renamed.

**Call site change:**

```python
from k1.hil.types import ApprovalRequest

req = ApprovalRequest(
    caller_key=f"planner:validate:{plan_id}",
    trace_id=trace_id,
    summary=plan_summary,
    side_effects=side_effects_list,
    safety_band=safety_band,
    estimated_duration_ms=duration_ms,
    timeout_ms=self._config.hil_approval_timeout_ms,
)
decision = await self._hil_port.request_approval(req)
# decision.outcome ∈ {APPROVED, MODIFIED, REJECTED, TIMEOUT}
```

**Tests:**

- `tests/k1/planner/test_sketch_service_hil_port.py` (NEW) — 5 tests covering ANSWERED/TIMEOUT/MAX_ROUNDS_EXCEEDED, abort behavior, caller_key format.
- `tests/k1/planner/test_validate_service_hil_port.py` (NEW) — 6 tests covering APPROVED/MODIFIED/REJECTED/TIMEOUT, side-effects passthrough.

**Run:**

```powershell
pytest tests/k1/planner/test_sketch_service_hil_port.py tests/k1/planner/test_validate_service_hil_port.py -v
```

---

### Issue E5.M1.2 — Move PLAN-10 round budget into `HumanInTheLoopService`

**File:** `k1/hil/service.py` (created in E1.M1.8) — extend the `_request` lifecycle to track per-caller round count.

**Add to `HILConfig` (E1.M1.10):**

```python
max_rounds_per_caller: int = 2   # PLAN-10 budget (planner uses "planner:sketch:<plan_id>" prefix)
```

**Behavior:**

- When a request arrives with `caller_key` matching prefix `planner:`, the service increments a counter keyed by `caller_key.rsplit(':', 1)[0]` (i.e. `planner:sketch:plan_42` → bucket `planner:sketch`).
- Wait: simpler — use the caller_key as-is. Round budget is per `(caller_key)`. `PipelineController.LC_PLAN_START` calls `service.reset_round_budget(caller_key="planner:sketch:<plan_id>")` AND `caller_key="planner:validate:<plan_id>"`.
- When budget exceeded → return outcome `MAX_ROUNDS_EXCEEDED` immediately, no event published.

**New service method:**

```python
async def reset_round_budget(self, caller_key: str) -> None:
    """Zero the round counter for a caller (planner LC_PLAN_START hook)."""
    self._rounds.pop(caller_key, None)
```

**Tests:** `tests/k1/hil/test_round_budget.py` (NEW)

- `test_first_two_rounds_succeed` — call ask_clarification twice with same caller_key → both reach service.
- `test_third_round_returns_max_rounds_exceeded` — third call returns `MAX_ROUNDS_EXCEEDED` without publishing event.
- `test_reset_clears_budget` — after `reset_round_budget`, three more calls succeed.
- `test_different_caller_keys_have_independent_budgets` — `planner:validate:p1` and `planner:sketch:p1` are separate.
- `test_concierge_caller_no_round_limit` — `caller_key="concierge:..."` is not subject to PLAN-10 (config-driven).

**Run:** `pytest tests/k1/hil/test_round_budget.py -v`

---

### Issue E5.M1.3 — Update `PipelineController.LC_PLAN_START` to call `reset_round_budget`

**File:** [k1/planner/pipeline/pipeline_controller.py](k1/planner/pipeline/pipeline_controller.py)

**Replace:**

```python
self._sketch_service._hil_coord.reset()  # OLD
```

**With:**

```python
await self._hil_port.reset_round_budget(f"planner:sketch:{plan_id}")
await self._hil_port.reset_round_budget(f"planner:validate:{plan_id}")
```

**Tests:** Existing `test_pipeline_controller_*.py` covers LC_PLAN_START — update fakes.

**Run:** `pytest tests/k1/planner/test_pipeline_controller_*.py -v`

---

### Issue E5.M1.4 — Thread `hil_port` through `PlannerFactory`

**File:** `k1/planner/factory.py`

**Replace** the `HILCoordinator(llm_port, event_port, config)` construction with `hil_port` accepted as a kwarg from kernel:

```python
def create(
    self,
    *,
    llm_port: ILLMPort,
    fabric_retrieval: Any,
    hil_port: "IHILPort",      # NEW
    config: PlannerConfig,
    ...
):
    sketch = SketchService(..., hil_port=hil_port, ...)
    validate = ValidateService(llm_port, fabric_retrieval, hil_port=hil_port)
    pipeline = PipelineController(sketch=sketch, validate=validate, hil_port=hil_port, ...)
    ...
```

**Tests:** `tests/k1/planner/test_planner_factory_hil_port.py` (NEW) — 3 tests verifying `hil_port` threading.

**Run:** `pytest tests/k1/planner/test_planner_factory_hil_port.py -v`

---

### Issue E5.M1.5 — Delete `HILCoordinator` class + `HILCoordinatorLike` Protocol

**File ops:**

```powershell
Remove-Item k1/planner/services/hil_coordinator.py
```

**Edits:**

- `k1/planner/services/__init__.py` — remove `HILCoordinator` import + `__all__` entry; remove the comment block referencing F26.
- `k1/planner/types.py` L374-433 — delete the entire `HILCoordinatorLike` Protocol + Section 12 header.
- `k1/planner/stages/sketch_service.py` L388-401 — delete the `_HILCoordinatorLike_DEPRECATED` shim.
- `k1/planner/stages/validate_service.py` L92 — delete `HILCoordinatorLike` import.
- Delete topic constants: `TOPIC_HIL_CLARIFICATION`, `TOPIC_HIL_CLARIFICATION_RESP`, `TOPIC_HIL_APPROVAL_REQ`, `TOPIC_HIL_APPROVAL_RESP` from wherever they live (likely `k1/planner/services/hil_coordinator.py` itself, plus `k1/k1_bus_core/topics.py`).

**Verify:**

```powershell
Select-String -Path k1 -Pattern 'HILCoordinator(?!Like)|HILCoordinatorLike|TOPIC_HIL_CLARIFICATION|TOPIC_HIL_APPROVAL' -List
```

→ zero hits in `k1/planner/`.

**Tests:** `pytest tests/k1/planner/ --collect-only -q` — no import errors.

---

### Issue E5.M1.6 — Rewrite planner HIL tests

**Delete:** `tests/k1/planner/test_planner_hil_coordinator_4_2.py` (~35 tests).

**Create:** `tests/k1/planner/test_planner_hil_integration.py` covering:

- Sketch clarification flow with stub HIL service end-to-end (no LLM).
- Validate approval flow with stub HIL service.
- Round budget reset on LC_PLAN_START.
- MAX_ROUNDS_EXCEEDED short-circuits sketch.
- TIMEOUT propagated as plan abort.

**Update existing tests:**

- `tests/k1/planner/test_planner_validate_3_3.py` — replace `FakeHILCoordinator` with `FakeHILPort` (small adapter exposing `request_approval`/`ask_clarification`).
- `tests/k1/planner/test_planner_micro_validate_5_1_4.py` L217-222 — same swap.
- `tests/k1/planner/test_planner_micro_replan_5_1.py` — drop `hil_coord` from FakeSketchService/FakeValidateService.
- `tests/k1/planner/test_planner_events_1_5_5_9.py:164` — rename test, assert publisher is HIL service.
- `tests/k1/planner/test_planner_commit_3_4.py:636` `test_no_hil_coordinator_import` — keep, update assertion.

**Run:**

```powershell
pytest tests/k1/planner/ -v
```

---

## E5 Exit Criteria

1. `k1/planner/services/hil_coordinator.py` does not exist.
2. `HILCoordinatorLike` Protocol does not exist anywhere in `k1/planner/`.
3. `grep -r "HILCoordinator\|hil_coord" k1/planner/` returns zero hits (only `_hil_port`/`hil_port`).
4. `pytest tests/k1/planner/ -v` — green.
5. PLAN-10 budget enforced inside `HumanInTheLoopService`, reset by `PipelineController` on LC_PLAN_START.
6. Topic constants `TOPIC_HIL_CLARIFICATION*`, `TOPIC_HIL_APPROVAL*` removed from codebase.

---

# Epic E6 — Orchestrator migration

**Goal:** Delete `IDeltaEmitPort.emit_hil_request`, `_pending_hil` registry, `PendingHILContext`, and the `HIL_OVERRIDE_RESPONSE` / `HIL_FALLBACK_RESPONSE` event subscriptions. `ConstraintResolver.trigger_hil_fallback` and `ExecutionMonitor` HIL-override path call `await hil_port.request_override(...)` directly. The DAG wave correctly resumes after the user response (current code path has a known gap where `_pending_hil` is parked but no resume hook fires — fixed in this epic).

**Pre-flight inventory (already done):**

- `k1/orchestrator/__init__.py` L18-19, L88, L186, L231-232 — exports `HIL_OVERRIDE_RESPONSE`, `HIL_FALLBACK_RESPONSE`, `PendingHILContext`. ALL deleted.
- `IDeltaEmitPort.emit_hil_request` — defined in `k1/orchestrator/ports/delta_emit_port.py` (verify line); 4 fakes implement it (`tests/k1/orchestrator/test_workflow_supervisor.py:108`, `test_gap_detector.py:110`, `test_workflow_compiler.py:101`, `test_sqlite_workflow_adapter.py:327`).
- `OrchestratorService._pending_hil: Dict[str, PendingHILContext]` — registry of parked HIL contexts.
- `OrchestratorService._on_hil_override` / `_on_hil_fallback` — bus subscribers for response topics. Need to re-route to fire a coroutine `set_result` instead of dictionary lookup.
- `ConstraintResolver.trigger_hil_fallback` — currently emits delta + parks; should `await hil_port.request_override(...)`.
- `ExecutionMonitor` — large-wave HIL override path at L1041, parks `PendingHILContext`.
- `tests/k1/orchestrator/test_event_catalog.py` L271-276 — uses `service._pending_hil` directly; full rewrite.
- `tests/k1/orchestrator/test_execution_monitor.py` L48 imports `PendingHILContext`; L83 fake; L93 `pending_hil: Dict`; L481, L562, L1081, L1094 assertions.
- `tests/k1/orchestrator/test_wiring_contract.py:43` `IDeltaEmitPort: ["emit", "emit_progress", "emit_hil_request"]` — drop last entry.

---

## E6.M1 — Delete delta-port HIL emission

### Issue E6.M1.1 — Add `hil_port` to `OrchestratorService.__init__`

**File:** `k1/orchestrator/service.py` (or wherever `OrchestratorService` lives)

```python
def __init__(self, ..., hil_port: "IHILPort | None" = None) -> None:
    ...
    self._hil_port = hil_port
```

**Pass into** `ConstraintResolver` and `ExecutionMonitor` constructors.

**Tests:** `tests/k1/orchestrator/test_service_hil_port.py` (NEW) — 3 tests.

**Run:** `pytest tests/k1/orchestrator/test_service_hil_port.py -v`

---

### Issue E6.M1.2 — Replace `emit_hil_request` in `ConstraintResolver.trigger_hil_fallback`

**File:** [k1/orchestrator/orchestration/constraint_resolver.py](k1/orchestrator/orchestration/constraint_resolver.py) `trigger_hil_fallback`

**Replace:**

```python
await self._delta_port.emit_hil_request(hil_request, trace_id=trace_id)
# ... park PendingHILContext ...
```

**With:**

```python
from k1.hil.types import OverrideRequest

req = OverrideRequest(
    caller_key=f"orchestrator:resolver:{plan_id}",
    trace_id=trace_id,
    constraint_violation=violation_summary,
    options=fallback_options,
    safety_band=current_band,
    timeout_ms=self._config.hil_override_timeout_ms,
)
decision = await self._hil_port.request_override(req)
# decision.outcome ∈ {OVERRIDE_APPROVED, OVERRIDE_REJECTED, TIMEOUT}
if decision.outcome != OverrideOutcome.OVERRIDE_APPROVED:
    raise ConstraintUnresolvableError(reason=decision.outcome.value)
return decision.chosen_option
```

The `await` blocks the resolver coroutine until response arrives. No `_pending_hil` dict needed.

**Tests:** `tests/k1/orchestrator/test_constraint_resolver_hil.py` (NEW) — 4 tests covering APPROVED/REJECTED/TIMEOUT, no delta emission, exception propagation.

**Run:** `pytest tests/k1/orchestrator/test_constraint_resolver_hil.py -v`

---

### Issue E6.M1.3 — Replace HIL override path in `ExecutionMonitor`

**File:** Find via `grep "_pending_hil" k1/orchestrator/`. The large-wave HIL override at `test_execution_monitor.py:1041` invokes `ExecutionMonitor._trigger_hil_override(...)` (or similar).

**Replace** with `await self._hil_port.request_override(...)`. Same pattern as E6.M1.2.

**Tests:** Rewrite `tests/k1/orchestrator/test_execution_monitor.py::TestAfterWaveHILParking` (L481+) and `test_large_wave_triggers_hil_override` (L1041+) to assert `hil_port.request_override` is called and the wave resumes after response.

**Run:** `pytest tests/k1/orchestrator/test_execution_monitor.py -v`

---

### Issue E6.M1.4 — Delete `_pending_hil`, `PendingHILContext`, response subscribers

**File:** `k1/orchestrator/service.py`

**Delete:**

- `self._pending_hil: Dict[str, PendingHILContext] = {}` field.
- `_on_hil_override(self, payload)` method.
- `_on_hil_fallback(self, payload)` method.
- Subscriptions to `HIL_OVERRIDE_RESPONSE` and `HIL_FALLBACK_RESPONSE` (in `start()` / setup).
- Metric `set_pending_hil` (if defined).

**File:** `k1/orchestrator/types.py`

- Delete `PendingHILContext` dataclass.

**File:** `k1/orchestrator/__init__.py`

- Remove L18-19, L88, L186, L231-232 exports.

**Tests:**

- `tests/k1/orchestrator/test_init_lifecycle.py` L425, L496-497, L842 — drop `assert not service._pending_hil` lines.
- `tests/k1/orchestrator/test_event_catalog.py` L271-276 — DELETE the section using `service._pending_hil[...]`.
- `tests/k1/orchestrator/test_execution_monitor.py:48` — drop `PendingHILContext` import; L83/L93 fake fields.

**Run:** `pytest tests/k1/orchestrator/ -v`

---

### Issue E6.M1.5 — Delete `IDeltaEmitPort.emit_hil_request`

**File:** `k1/orchestrator/ports/delta_emit_port.py`

- Delete `async def emit_hil_request(self, hil_request, trace_id) -> None` method.

**File:** `k1/orchestrator/adapters/` (find via `grep "emit_hil_request" k1/orchestrator/adapters/`)

- Delete implementation (likely in `delta_bridge_adapter.py` or similar).

**Tests update:**

- `tests/k1/orchestrator/test_wiring_contract.py:43` — change list to `["emit", "emit_progress"]`.
- `tests/k1/orchestrator/test_workflow_supervisor.py:108` — drop fake method.
- `tests/k1/orchestrator/test_gap_detector.py:110` — drop fake method.
- `tests/k1/orchestrator/test_workflow_compiler.py:101` — drop fake method.
- `tests/k1/orchestrator/test_sqlite_workflow_adapter.py:327` — drop fake method.
- `tests/k1/orchestrator/test_adapter_delta_bridge.py` — drop `test_emit_hil_request_*` cases.

**Verify:**

```powershell
Select-String -Path k1,tests -Pattern 'emit_hil_request' -List
```

→ zero hits.

**Run:** `pytest tests/k1/orchestrator/ -v`

---

### Issue E6.M1.6 — DAG resume verification (closes the historical gap)

**Why:** Even before E6, the DAG resume after HIL response was suspect — `_pending_hil` parked the context but no test verified the wave actually resumed. With `await hil_port.request_override(...)` the resume is automatic (coroutine wakeup). Add explicit test.

**Test:** `tests/k1/orchestrator/test_dag_resume_after_hil.py` (NEW)

- `test_wave_with_hil_resumes_on_user_approval` — start a 3-task wave; mid-wave HIL override fires; stub HIL service responds APPROVED after 50ms; assert remaining tasks complete and DAG reaches DONE state.
- `test_wave_with_hil_aborts_on_user_rejection` — same but REJECTED → wave aborts, partial-result emitted, DAG state ABORTED.
- `test_wave_with_hil_timeout_aborts` — TIMEOUT → DAG state ABORTED with `error_code="hil_timeout"`.

**Run:** `pytest tests/k1/orchestrator/test_dag_resume_after_hil.py -v`

---

## E6 Exit Criteria

1. `IDeltaEmitPort.emit_hil_request` does not exist.
2. `OrchestratorService._pending_hil`, `PendingHILContext` do not exist.
3. `HIL_OVERRIDE_RESPONSE`, `HIL_FALLBACK_RESPONSE` constants removed from `k1/orchestrator/__init__.py`.
4. `grep -r "emit_hil_request\|_pending_hil\|PendingHILContext\|HIL_OVERRIDE_RESPONSE\|HIL_FALLBACK_RESPONSE" k1 tests` returns zero hits.
5. `pytest tests/k1/orchestrator/ -v` — green.
6. DAG resume verified: large-wave HIL override → user approves → remaining wave completes (proven by `test_dag_resume_after_hil.py`).
7. `OrchestratorService.__init__` accepts `hil_port` from kernel bootstrap.

---

---

# Epic E7 — End-to-end kernel integration

**Goal:** Wire `HumanInTheLoopService` into kernel bootstrap as the SINGLE source of truth, thread `hil_port` into all four downstream factories (fabric, concierge, planner, orchestrator), purge dead constants/topics, refresh probes, and update the findings doc.

**Pre-flight inventory (already done in earlier kernel-port-adapter audit; see `/memories/session/kernel_port_adapter_extraction.md`):**

- `k1/kernel/service.py` — `KernelService.start()` has staged init S1-S4. S2 = bus, S3 = fabric/concierge/planner/orchestrator construction.
- `k1/kernel/config.py` — `KernelConfig` dataclass; current HIL config absent.
- `scripts/kernel_probe_phase1.py` through `scripts/kernel_probe_phase8.py` — 8 numbered probes; `phase2_hil` covers HIL surface.
- `docs/test_results/kernel_findings.md` — W10 currently OPEN; Phase 2 probe currently has `topic_clarification_emitted=FAIL`.

---

## E7.M1 — Kernel bootstrap wiring

### Issue E7.M1.1 — Construct `HumanInTheLoopService` in `KernelService.start()` S2

**File:** [k1/kernel/service.py](k1/kernel/service.py) — between bus init (S2) and fabric/concierge construction (S3).

**Insert:**

```python
# --- S2.5: Human-in-the-Loop service (E7) ---
from k1.hil.service import HumanInTheLoopService
from k1.hil.policy import SafetyBandPolicy
from k1.hil.adapters import HILLedgerAdapter, HILEventAdapter, HILLLMAdapter
from k1.hil.config import HILConfig

hil_config = HILConfig(
    default_timeout_ms=self._config.hil_default_timeout_ms,
    clarification_timeout_ms=self._config.hil_clarification_timeout_ms,
    approval_timeout_ms=self._config.hil_approval_timeout_ms,
    override_timeout_ms=self._config.hil_override_timeout_ms,
    capability_gate_timeout_ms=self._config.hil_capability_gate_timeout_ms,
    needs_human_timeout_ms=self._config.hil_needs_human_timeout_ms,
    max_rounds_per_caller=self._config.hil_max_rounds,
    block_red=self._config.hil_block_red,
)

hil_event_adapter = HILEventAdapter(bus=self._bus)
hil_llm_adapter = HILLLMAdapter(llm_port=llm_port)  # llm_port already constructed in S2
hil_ledger_adapter = HILLedgerAdapter(ledger_writer=self._ledger_writer)
safety_policy = SafetyBandPolicy(block_red=hil_config.block_red)

self._hil_service = HumanInTheLoopService(
    config=hil_config,
    event_port=hil_event_adapter,
    llm_port=hil_llm_adapter,
    ledger=hil_ledger_adapter,
    policy=safety_policy,
)
await self._hil_service.start()  # subscribes to k1.hil.response.v1
```

**Pass `hil_port=self._hil_service` into:**

- `FabricFactory.create_shared(..., hil_port=self._hil_service)` (E3.M1.2).
- `ConciergeFactory.create(..., hil_port=self._hil_service)` (E4.M1.6).
- `PlannerFactory.create(..., hil_port=self._hil_service)` (E5.M1.4).
- `OrchestratorService(..., hil_port=self._hil_service)` (E6.M1.1).

**Shutdown** in `KernelService.shutdown()`:

```python
await self._hil_service.shutdown()  # cancels pending suspensions, drains ledger
```

**Tests:** `tests/k1/kernel/test_kernel_service_hil_wiring.py` (NEW)

- `test_hil_service_constructed_in_start` — start kernel, assert `kernel._hil_service is not None`.
- `test_hil_port_threaded_to_fabric` — fabric instance has `_hil_port is kernel._hil_service`.
- `test_hil_port_threaded_to_concierge` — concierge controller has `_hil_port is kernel._hil_service`.
- `test_hil_port_threaded_to_planner` — planner sketch/validate services share the same `_hil_port`.
- `test_hil_port_threaded_to_orchestrator` — orchestrator service `_hil_port is kernel._hil_service`.
- `test_single_coordinator_invariant` — count instances of `HumanInTheLoopService` in the running kernel via reflection → exactly 1.
- `test_shutdown_drains_pending` — start, fire pending HIL request, shutdown → request resolved with `outcome=CANCELLED`.

**Run:** `pytest tests/k1/kernel/test_kernel_service_hil_wiring.py -v`

---

### Issue E7.M1.2 — Add HIL fields to `KernelConfig`

**File:** [k1/kernel/config.py](k1/kernel/config.py) `KernelConfig` dataclass.

**Add:**

```python
# ---- HIL (E7) ----
hil_default_timeout_ms:        int  = 60_000
hil_clarification_timeout_ms:  int  = 60_000   # planner sketch
hil_approval_timeout_ms:       int  = 120_000  # planner validate
hil_override_timeout_ms:       int  = 60_000   # orchestrator constraint resolver
hil_capability_gate_timeout_ms:int  = 120_000  # fabric gate
hil_needs_human_timeout_ms:    int  = 120_000  # concierge needs_human
hil_max_rounds:                int  = 2        # PLAN-10
hil_block_red:                 bool = False    # Decision #6 — even RED is askable
```

**Tests:** `tests/k1/kernel/test_kernel_config_hil.py` (NEW)

- `test_default_values` — verify all 8 defaults match design.
- `test_explicit_override` — construct `KernelConfig(hil_max_rounds=5)` → field == 5.

**Run:** `pytest tests/k1/kernel/test_kernel_config_hil.py -v`

---

### Issue E7.M1.3 — Topic cleanup pass

**Delete dead constants** (find via grep):

```powershell
Select-String -Path k1 -Pattern 'TOPIC_HIL_CLARIFICATION|TOPIC_HIL_APPROVAL|HIL_OVERRIDE_RESPONSE|HIL_FALLBACK_RESPONSE|TOPIC_HITL_REQUESTED|TOPIC_HITL_RESOLVED|TOPIC_HITL_TIMED_OUT|TOPIC_HITL_BLOCKED_RED' -List
```

**Decision per topic:**

- `TOPIC_HIL_CLARIFICATION` / `_RESP` (planner) — DELETE; replaced by unified `k1.hil.request.v1` / `k1.hil.response.v1`.
- `TOPIC_HIL_APPROVAL_REQ` / `_RESP` (planner) — DELETE; same.
- `HIL_OVERRIDE_RESPONSE` / `HIL_FALLBACK_RESPONSE` (orchestrator) — DELETE; resolver awaits `IHILPort` directly.
- `TOPIC_HITL_REQUESTED` / `_RESOLVED` / `_TIMED_OUT` / `_BLOCKED_RED` (concierge audit) — collapse to single `k1.hil.audit.v1`.

**Verify zero callers** before commit.

**File:** `k1/k1_bus_core/topics.py` (or wherever defined) — remove constants.

**Tests:** `tests/k1/integration/test_no_legacy_hil_topics.py` (NEW) — single test that imports `k1` and asserts none of the deleted names are present in `k1.k1_bus_core.topics` namespace.

**Run:** `pytest tests/k1/integration/test_no_legacy_hil_topics.py -v`

---

### Issue E7.M1.4 — Probe updates

**File:** `scripts/kernel_probe_phase2_hil.py`

**Update assertions:**

- Subscriber signature `(topic, data)` (already done previously per session memory).
- `coordinator_count = 1` — count `isinstance(_, HumanInTheLoopService)` across kernel internals; assert exactly one.
- `IHILPort` conformance: `isinstance(kernel._hil_service, IHILPort)` (Protocol with `runtime_checkable`).
- All 5 request types round-trip on `k1.hil.request.v1`:
  - Issue test request of each `HILKind` (CLARIFICATION/APPROVAL/NEEDS_HUMAN/OVERRIDE/CAPABILITY_GATE).
  - Subscribe to `k1.hil.request.v1` → verify each emits one envelope with correct `kind` field.

**File:** `scripts/kernel_probe_phase3_fabric.py`

- Add: invoke an AMBER capability with no HIL responder → assert `gate_capability` blocks (TIMEOUT after small budget).
- Invoke same with auto-approve responder → assert capability executes.

**File:** `scripts/kernel_probe_phase1.py`

- After kernel start, assert: `fabric._hil_port is not None`, `concierge.fsm._hil_port is not None`, `planner._hil_port is not None`, `orchestrator._hil_port is not None`, AND `all four refer to the same instance`.

**Run:**

```powershell
python scripts/kernel_probe_phase1.py
python scripts/kernel_probe_phase2_hil.py
python scripts/kernel_probe_phase3_fabric.py
```

→ all green.

---

### Issue E7.M1.5 — Refresh findings doc

**File:** `docs/test_results/kernel_findings.md`

**Edits:**

- W10 status: OPEN → ✅ RESOLVED (link to `HIL_UNIFICATION_PLAN.md`).
- F2 status: OPEN → ✅ RESOLVED.
- Phase 2 row `topic_clarification_emitted=FAIL` → PASS.
- Add new section "## HIL Unification (E1-E8 completed)" summarizing:
  - Single `HumanInTheLoopService` SOT.
  - 5 unified request types via 1 topic.
  - Fabric gate as Defense-in-Depth L3.
  - Round budget centralized.
  - DAG resume via coroutine await (no parked dict).

**Run:** N/A (docs).

---

## E7 Exit Criteria

1. `kernel._hil_service` exists, is a `HumanInTheLoopService`, conforms to `IHILPort`.
2. Fabric, concierge, planner, orchestrator all reference the SAME instance.
3. `pytest tests/k1/kernel/test_kernel_service_hil_wiring.py tests/k1/kernel/test_kernel_config_hil.py tests/k1/integration/test_no_legacy_hil_topics.py -v` — green.
4. All 8 kernel probes green: `for /L %i in (1,1,8) do python scripts/kernel_probe_phase%i.py`.
5. `kernel_findings.md` shows W10 + F2 resolved.
6. `Select-String -Path k1 -Pattern 'TOPIC_HIL_CLARIFICATION|TOPIC_HIL_APPROVAL|HIL_OVERRIDE_RESPONSE|HIL_FALLBACK_RESPONSE'` — zero hits.
7. Kernel cold-boot time impact: < 50ms (HIL service startup is constant-time — subscribe + create policy).

---

# Epic E8 — End-to-end integration testing (no mocks)

**Goal:** Prove the unified HIL works end-to-end against a REAL kernel + REAL bus + REAL `HumanInTheLoopService` + REAL fabric/concierge/planner/orchestrator. The ONLY test fixture is `HILUserSimulator` — it stands in for the human user (subscribing to `k1.hil.request.v1` and emitting scripted responses on `k1.hil.response.v1`). NOT a mock of any service collaborator. NO `unittest.mock` import allowed in `tests/k1/integration/hil/`.

**Test discipline (per user directive):** Run ONLY the integration tests in `tests/k1/integration/hil/`. Do NOT run full kernel suite.

---

## E8.M1 — Test harness

### Issue E8.M1.1 — `HILUserSimulator` fixture

**File:** `tests/k1/integration/hil/conftest.py` (NEW)

```python
@pytest.fixture
async def hil_user_simulator(kernel_service):
    """Stand-in for the human user. Subscribes to k1.hil.request.v1, emits scripted responses."""
    sim = HILUserSimulator(bus=kernel_service._bus)
    await sim.start()
    yield sim
    await sim.stop()


class HILUserSimulator:
    def __init__(self, bus):
        self._bus = bus
        self._scripts: dict[str, Callable] = {}   # kind → response_factory
        self._received: list[dict] = []

    def script(self, kind: str, response_fn: Callable[[dict], dict]) -> None:
        """Register a response factory for a HIL request kind."""
        self._scripts[kind] = response_fn

    async def start(self):
        await self._bus.subscribe("k1.hil.request.v1", self._on_request)

    async def _on_request(self, topic: str, payload: dict) -> None:
        self._received.append(payload)
        kind = payload.get("kind")
        responder = self._scripts.get(kind)
        if responder is None:
            return  # no scripted response → request will TIMEOUT
        response = responder(payload)
        await self._bus.publish("k1.hil.response.v1", response)
```

**Kernel fixture:** `kernel_service` boots a real `KernelService(config=KernelConfig(model_mode="test", enable_hitl=True))` via `await KernelService.start()`. Tear-down via `await kernel_service.shutdown()`.

**Tests:** `tests/k1/integration/hil/test_simulator_smoke.py` (NEW)

- `test_simulator_receives_request` — emit request manually → simulator captures it.
- `test_simulator_emits_scripted_response` — script approval → request resolves with that response.
- `test_unscripted_request_times_out` — no script → TIMEOUT after configured budget.

**Run:** `pytest tests/k1/integration/hil/test_simulator_smoke.py -v`

---

## E8.M2 — End-to-end coverage by surface

### Issue E8.M2.1 — Concierge `needs_human` E2E

**File:** `tests/k1/integration/hil/test_e2e_concierge_needs_human.py` (NEW)

**Scenario:** User prompt to concierge → Back tool returns `needs_human=True` → real `HumanInTheLoopService` issues request → real Front rendering pipeline emits user-visible event → simulator answers → Back resumes → final concierge response.

**Assertions:**

- Ledger has exactly one `HILRequested` and one `HILResolved` for the request.
- The single global `_hil_service` instance handled the request (no other coordinator invoked).
- Round-trip latency < 500ms with simulator responding immediately.
- Caller_key is `concierge:<task_id>`.

---

### Issue E8.M2.2 — Planner clarification E2E

**File:** `tests/k1/integration/hil/test_e2e_planner_clarification.py` (NEW)

**Scenario:** Submit ambiguous goal → planner SKETCH triggers `ask_clarification` → simulator answers → SKETCH retries → VALIDATE passes → `plan.committed.v1` event.

**Assertions:**

- After 2 successful clarifications, a 3rd ambiguous turn returns `MAX_ROUNDS_EXCEEDED` and the plan aborts.
- After `LC_PLAN_START` reset, the budget restarts.

---

### Issue E8.M2.3 — Orchestrator override E2E

**File:** `tests/k1/integration/hil/test_e2e_orchestrator_override.py` (NEW)

**Scenario:** Plan with one unresolvable constraint → ConstraintResolver awaits `request_override` → simulator picks an override option → DAG wave resumes → all tasks complete.

**Assertions:**

- No `_pending_hil` registry exists (verified via `getattr(orchestrator, "_pending_hil", None) is None`).
- Wave completion event `wave.completed.v1` emitted AFTER the user response.
- Rejection by simulator → DAG state ABORTED with `error_code="hil_rejected"`.

---

### Issue E8.M2.4 — Fabric capability gate E2E

**File:** `tests/k1/integration/hil/test_e2e_fabric_gate.py` (NEW)

**Scenarios:**

- AMBER capability `calendar_delete_event` invoked through real fabric → gate fires → simulator approves → execution proceeds → success.
- Same, simulator rejects → result has `error_code="hil_rejected_by_user"`, provider NOT invoked.
- GREEN capability `weather_current` invoked → gate short-circuits ALLOW → simulator receives ZERO requests with `kind=capability_gate`.
- RED capability (synthesize one in-test) → gate fires regardless of safety band override (Decision #6 — RED is askable).

---

### Issue E8.M2.5 — Crash recovery E2E

**File:** `tests/k1/integration/hil/test_e2e_crash_recovery.py` (NEW)

**Scenario:**

1. Start kernel with persistent ledger path.
2. Trigger HIL request via concierge `needs_human`.
3. Kill kernel mid-suspension via `await kernel.shutdown(force=True)`.
4. Restart kernel with same ledger path.
5. Pending HIL recovered via `HILLedgerAdapter.replay()` → request re-emitted on bus.
6. Simulator answers → flow completes.

**Assertions:**

- After step 4, `kernel._hil_service.pending_count > 0` (recovered).
- After step 6, ledger has exactly one `HILResolved` for the original request id.

---

### Issue E8.M2.6 — Multi-source convergence E2E

**File:** `tests/k1/integration/hil/test_e2e_multi_source.py` (NEW)

**Scenario:** Single user session triggers concurrently:

- Planner clarification (`ask_clarification`).
- Concierge needs_human (`needs_human`).
- Fabric gate (`gate_capability`) on AMBER capability.

Simulator scripts a unique response for each `kind`. All three should resolve independently.

**Assertions:**

- Three distinct `hil_request_id` values seen by simulator.
- Each response routes to the correct caller (verified via correlation in ledger).
- Total wall time < 1s (no serialization across requests).
- Front renders all three (count of `task.suspended.v1` or equivalent rendering events == 3).

---

### Issue E8.M2.7 — All probes + smoke

**Action:** Run all 8 kernel probes against the HIL-enabled kernel; assert zero FAILs.

**Test:** `tests/k1/integration/hil/test_probes_smoke.py` (NEW)

```python
@pytest.mark.parametrize("phase", range(1, 9))
def test_probe_phase_passes(phase, hil_enabled_kernel):
    result = subprocess.run(
        ["python", f"scripts/kernel_probe_phase{phase}.py"],
        capture_output=True, env={"PYTHONPATH": "."},
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

---

## E8 Exit Criteria

1. `pytest tests/k1/integration/hil/ -v` — all green.
2. `Select-String -Path tests/k1/integration/hil -Pattern 'unittest\.mock|MagicMock|AsyncMock' -List` — zero hits.
3. All 8 kernel probes pass with HIL-enabled kernel.
4. Multi-source test proves three concurrent surfaces share the SAME service instance and produce three distinct request ids.
5. Crash recovery test proves persistence via ledger replay.
6. End-to-end latency budget: simulator-immediate response → full round-trip < 500ms for any single surface.

---

---

# Cross-cutting cleanup (post-E8)

- Delete `k1.hitl.*.v1` audit topics if obs has migrated to `k1.hil.audit.v1`.
- Delete `IDeltaEmitPort.emit_hil_request` references from any remaining docs (`docs/whiteboard/`, `docs/architecture/`).
- Update `docs/architecture/decisions-K1/09-communication/0016-sse-event-schemas/` to point SSE filter `tool.approval_required` at `k1.hil.request.v1` with `kind=capability_gate`.
- Update `docs/v3_milestones.md:8773` (issue 6.1.5 — duplicate round-budget enforcement; now resolved).

---

# Execution order

```
E1 (skeleton + bridge)
  ├─► E2 (contract schema)        ─┐
  └─► E3 (fabric gate)            ─┤
        ├─► E4 (concierge migration)
        ├─► E5 (planner migration)
        └─► E6 (orchestrator migration)
              └─► E7 (kernel wiring + cleanup)
                    └─► E8 (E2E no-mock testing)
```

E2/E3 can run in parallel after E1. E4/E5/E6 can run in parallel after E2+E3. E7 gates on all three. E8 gates on E7.

---

# Out of scope

- K0 bridge HIL (deferred to MS-3 with W9).
- Multi-tenant HIL request fan-out (single-user assumption holds for Family-OS).
- HIL via external channels (SMS, push notification) — Front LLM is the only surface for now.
- Persistence of HIL response history beyond the ledger.

---

# Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Hard cutover breaks an obscure caller | Pre-flight grep for all `HILCoordinator`, `emit_hil_request`, `TOPIC_HIL_CLARIFICATION` etc. before E4 starts; capture in E1 audit issue |
| Front bridge timing race (response arrives before subscriber registered) | Service registers inbound subscriber in `__init__`, before any caller can invoke a method |
| Round-budget moved from planner to service may double-count if planner retries | E5.2 keys budget by `caller="planner:<plan_id>"`, reset on `LC_PLAN_START` |
| AMBER contracts that should NOT ask | Annotate explicitly with `requires_human_confirmation: false` in E2.3 audit |
| E2E tests flaky due to real bus timing | Use `HILUserSimulator` with deterministic ordering; assert via ledger not bus stats |
