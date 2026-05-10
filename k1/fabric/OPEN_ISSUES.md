# K1 Fabric — OPEN ISSUES

---

## Issue 1 — `asyncio.Semaphore` created outside the event loop

**File**: `k1/fabric/concurrency/dispatcher.py`
**Class**: `FabricDispatcher.__init__()`

`asyncio.Semaphore(max_concurrent)` is created in the synchronous `__init__` method. In Python
3.10+ the semaphore is correctly bound to the running event loop only when `.acquire()` is first
called (since PEP 652 removed the deprecated `loop` parameter), but constructing a Semaphore in a
non-async context that then runs in a different event loop (e.g. uvicorn creates a new loop per
worker) will silently attach to the wrong loop and produce `RuntimeError: Task attached to a
different loop` at runtime.

**Risk**: Silent runtime failure in multi-loop deployments. Fails loudly in pytest if the test
runner creates a new loop per test.

**Fix**: Construct the semaphore inside the first `async dispatch()` call (lazy), or move
`FabricDispatcher` construction into an `async` classmethod that runs inside the event loop.

---

## Issue 2 — `_schema_cache` is a module-level mutable global with no lock

**File**: `k1/fabric/core/contract_validator.py`
**Symbol**: `_schema_cache: Dict[str, dict]`

The JSON Schema cache is module-scoped and shared across all `ContractValidator` instances in the
process. It is populated lazily (on first validation of each contract type) but has no mutex. A
concurrent first-validation for the same contract type from two threads can result in a
double-write that is harmless for the same content but creates an inconsistent reference in rare
edge cases.

Larger problem: the cache is never cleared between test runs. Tests that mutate or patch schema
files on disk will silently use the stale cached schema for the lifetime of the process.

**Risk**: Flaky tests when schema fixtures are mutated. Race in heavily concurrent production
startup. Unpredictable behaviour when contract type schemas are hot-swapped.

**Fix**: Protect writes with a `threading.Lock`. Add a `clear_schema_cache()` module-level
function callable from test fixtures. Consider per-instance caching if isolation is required.

---

## Issue 3 — `RetrievalEngine` accesses `EmbeddingIndex._vectors` directly — data race confirmed

**File**: `k1/fabric/retrieval/retrieval_engine.py`
**Symbol**: `RetrievalEngine` → `getattr(index, "_vectors", {})`

> **CORRECTION (May 2026):** Original description had wrong file path — the file is
> `k1/fabric/retrieval/retrieval_engine.py`, **not** `k1/fabric/retrieval/engine.py`.
> `engine.py` does not exist.
>
> Additionally, the access pattern `getattr(self._index, "_vectors", {})` **bypasses
> `EmbeddingIndex._lock`** entirely. This is a **data race**: if `_vectors` is being
> mutated (e.g., during index update in another thread), the read races with the write.
> This is a concurrency correctness bug, not merely a coupling concern.

`RetrievalEngine` accesses the private `_vectors` dict on `EmbeddingIndex` via
`getattr(index, "_vectors", {})` to build candidate metadata after a FAISS search.
This couples retrieval logic to `EmbeddingIndex` internals and will break silently if
`EmbeddingIndex` renames, removes, or restructures `_vectors` (e.g., when
upgrading to `IndexIVFFlat` which does not support direct vector access by label without an
explicit id-map).

**Risk**: Silent regression on `EmbeddingIndex` refactor AND data race on concurrent
vector access. The FAISS IVF index path (`>10 000` vectors) already restructures
internal storage; once that branch is hit, `_vectors` may diverge.

**Fix**: Add a public `get_vectors_snapshot() -> Dict[str, np.ndarray]` method to
`EmbeddingIndex` that acquires `_lock` and returns a copy. `RetrievalEngine` should use
that method instead of `getattr(..., "_vectors", {})`.

---

## Issue 4 — MPSC mailbox is `None` (stub) — agents have no message channel

**File**: `k1/fabric/providers/agent_provider.py`
**Class**: `AgentFactory._spawn()`, step 2
**Epic**: 4.4 (pending)

All spawned `Agent` instances receive `mailbox=None`. The `IAgentMailbox` Protocol is declared but
no implementation exists. This means:
- No message can be sent to a running agent after spawn.
- Agent-to-agent communication is not possible.
- Agents cannot receive tool results via mailbox (they currently rely on direct return from `llm_handle.generate()`).

**Risk**: Any caller that attempts to send messages to an agent via a mailbox will silently
receive `None` on `agent._mailbox` and crash on dereference.

**Fix**: Implement Epic 4.4. Until then, guard every mailbox access with `if self._mailbox is not None`.

---

## Issue 5 — `BridgeConnectionAdapter` starts permanently disconnected

**File**: `k1/fabric/adapters/bridge_connection.py`
**Class**: `BridgeConnectionAdapter`

The adapter is "bridge-ready from day one" (per inline docs) but `_connected = False` at
construction and the bridge client protocol is undocumented and unbuilt. No reconnection logic,
no client-builder, no handshake sequence exists.

**Consequence in production**: every `BridgeProvider._execute()` call that reaches
`bridge.is_available()` returns `False`. The K0_OFFLINE fallback path is taken for all bridge
operations (memory.store, memory.recall, memory.delta, checkpoint, feedback.signal, IFL routing).
This silently degrades all K0 memory operations to no-ops.

**Risk**: Entire K0 memory layer is silently bypassed in production. No alarm is raised (the
fallback is designed to look like a soft degradation). Users see no error; data is lost.

**Fix**: Define and document the bridge client protocol. Implement `BridgeConnectionAdapter`
reconnect logic (with backoff). Add an explicit startup health check that fails loudly when
bridge is expected and unavailable.

---

## Issue 6 — ~~`LLMHandleBridge.generate()` not thread-safe; `AgentPool.get()` TOCTOU~~ ✅ OVERSTATED

**Files**: `k1/fabric/adapters/model_gateway_bridge.py`, `k1/fabric/providers/agent_provider.py`

> **UPDATE (May 2026):** OVERSTATED — the race window described cannot actually
> occur with the current implementation.
>
> `AgentPool.get(contract_name)` is fully synchronous and holds `threading.RLock` for
> the **entire** operation: pop from deque + reactivate (IDLE→ACTIVE). No async yield
> points exist within the lock. A second concurrent `get()` cannot interleave with the
> first. An agent cannot be returned to two callers simultaneously under these semantics.
>
> The "TOCTOU window" described was based on a misread of the code. The `in_use` flag
> is not needed because pool operations are already atomic under RLock.
>
> **Status: CLOSED — pool.get() is correctly atomic.**

~~`LLMHandleBridge.generate()` is documented as "NOT thread-safe by design". If pool eviction
logic races with reactivation the same `Agent` object could be handed to two callers.~~

~~**Fix**: Add an `in_use` flag to `Agent`.~~

---

## Issue 7 — `AvailabilityTracker.on_state_change()` auto-registers unknown providers

**File**: `k1/fabric/health/availability_tracker.py`
**Method**: `on_state_change(provider_id, old_state, new_state)`

When a `CircuitBreaker` fires a state-change notification for a `provider_id` that is not yet
tracked, `on_state_change()` silently calls `self.register(provider_id, initial_state=ONLINE)`
before applying the transition. This means any circuit breaker state change for an unknown
provider silently creates a new tracking entry, bypassing the normal explicit-registration flow
and skipping initial health probing.

**Risk**: Providers that are created on-the-fly (e.g., dynamic stub providers registered via hot-
reload) can enter tracking in ONLINE state without ever having passed a health check. If the CB
immediately transitions OPEN→HALF_OPEN, the tracker shows DEGRADED for a provider that has never
been healthy.

**Fix**: Log a WARNING and return without auto-registering when `provider_id` is not tracked. Let
the explicit `register()` call in `HealthChecker.register_provider_instance()` handle the initial
registration.

---

## Issue 8 — `WorkflowProvider._current_depth` depth guard is permanently dead

**File**: `k1/fabric/providers/workflow_provider.py`
**File**: `k1/fabric/factory.py`
**Class**: `WorkflowProvider`

> **CORRECTION (May 2026):** Original description identified the concurrency bug
> (shared instance variable) but **missed the primary bug**: `_current_depth` is
> **never incremented anywhere in `_execute()`**. The depth check fires against a
> value that never changes.

**Bug 1 (depth guard permanently dead):** `_execute()` has a guard:
```python
if self._current_depth >= self._max_depth:
    raise WorkflowDepthExceededError
```
but there is no `self._current_depth += 1` before the recursive call and no
`self._current_depth -= 1` after. The depth guard **can never trigger** regardless
of nesting depth.

**Bug 2 (factory always passes 0):** `factory.py:~250` always constructs
`WorkflowProvider(current_depth=0, ...)`. Even after fixing Bug 1, sub-workflows
spawned from within a workflow receive `current_depth=0` — the depth chain is
never threaded through the execution call chain.

**Bug 3 (concurrency — original issue):** `_current_depth` is an instance variable
shared across all concurrent executions on the same `WorkflowProvider` instance.
This is moot while Bug 1 exists, but must be fixed alongside it.

**Fix:**
1. Remove `_current_depth` from instance state entirely.
2. Pass `current_depth: int` as a parameter through `_execute()` and into recursive
   sub-workflow invocations (via `ExecutionContext.params` or a direct parameter).
3. Update `factory.py` to thread `current_depth` through the execution call chain.

---

## Issue 9 — `LocalEventAdapter` handlers called synchronously inside `emit()` — no timeout

**File**: `k1/fabric/adapters/local_event_adapter.py`
**Class**: `LocalEventAdapter`

In the `emit(topic, payload)` implementation, handlers registered for the topic are called
synchronously in the caller's thread, outside the adapter's `RLock` but still on the calling
stack. There is no timeout and no async offload.

**Consequence**: a slow or blocking event handler (e.g., a test assertion that does file I/O)
blocks the entire Fabric execution path for the duration of the handler. In production, this can
cause cascading latency spikes any time a slow subscriber is registered.

**Risk**: In production `LocalEventAdapter` is used for standalone mode and some test setups.
Any subscriber that does work proportional to payload size (logging, serialisation, assertion)
blocks execution.

**Fix**: Dispatch handlers via `asyncio.create_task()` when a running loop is available; fall back
to `threading.Thread(daemon=True)` for sync contexts. For the test capture path, the
synchronous dispatch is acceptable but should be explicitly gated behind `capture_mode=True`.

---

## Issue 10 — `PolicyEngine` metric observation is unlabeled — no per-capability breakout

**File**: `k1/fabric/policy/policy_engine.py`
**Method**: `_eval_policy()` `finally` block

The `get_default_metrics().observe_policy_evaluation()` call inside `PolicyEngine._eval_policy()`
records duration to a single histogram with no labels. Every capability type (tool, agent,
workflow) shares the same histogram bucket, making it impossible to distinguish which capability
class is causing policy evaluation latency.

**Risk**: When a class of capabilities starts producing slow policy evaluation (e.g., complex
affective routing for certain agents), the signal is invisible in production dashboards because
it is averaged across all capability types.

**Fix**: Pass `capability_name` and/or `provider_type` labels to
`observe_policy_evaluation(capability_name, provider_type)`. Update `FabricMetrics` to expose a
labeled histogram: `fabric_policy_evaluation_duration_seconds{capability_name, provider_type}`.

---

## Issue 11 — `DiscoverCapabilitiesHandler` uses synchronous `RetrievalEngine` but `FabricRetrieval` is async

**File**: `k1/fabric/core/discovery_tools.py`
**Symbol**: `RetrievalLike` Protocol

`DiscoverCapabilitiesHandler` and `FindPromptsHandler` declare a `RetrievalLike` Protocol that
requires **synchronous** `discover_capabilities()` and `find_relevant_prompts()` methods.
`FabricRetrieval` (the public retrieval facade on `Fabric`) has **async** versions of these
methods. Therefore `FabricRetrieval` does NOT satisfy `RetrievalLike`. The factory wires
`RetrievalEngine` (sync) directly to the handlers at construction — which works — but any caller
that tries to pass `FabricRetrieval` as a `RetrievalLike` will pass a Protocol runtime-check
but fail at the call site with a coroutine type error.

**Risk**: Confusing runtime failure if `FabricRetrieval` is accidentally passed to
`DiscoverCapabilitiesHandler`. No static-type warning because `@runtime_checkable` Protocol only
checks method existence, not async signature.

**Fix**: Unify the retrieval interface. Either make `DiscoverCapabilitiesHandler` accept async
and `await` the result, or add a sync passthrough to `FabricRetrieval`.

---

## Issue 12 — `AgentProvider` falls back to failure when factory is None (M3 stub behaviour still present)

**File**: `k1/fabric/providers/agent_provider.py`
**Class**: `AgentProvider._execute()`

When `AgentProvider._factory is None`, the provider returns
`CapabilityResult.failure_result(AgentNotImplementedError)`. This is documented as the M3 stub
path. In production, `FabricFactory` wires a real `AgentFactory`, so `_factory` should never be
None. However:
- There is no assertion or startup check that `_factory` is set for production mode.
- If `create_with_ports(production_mode=True)` is called with missing model_gateway or delta_bus,
  `AgentFactory` is still constructed but with `model_gateway=None`, causing silent
  capability degradation.

**Risk**: Capability calls to agent capabilities silently return "not implemented" if the factory
is misconfigured. The error is not surfaced at startup, only at invocation time.

**Fix**: Add a `validate_wiring()` method to `FabricFactory` that asserts all production-required
ports are non-None when `production_mode=True`. Run it at the end of `_construct_fabric()`.

---

## Issue 10 — `Issue 4 addendum`: `Agent.terminate()` nulls `_mailbox` without `close()`; `IAgentMailbox` is sync-only

**File**: `k1/fabric/providers/agent_provider.py`
**Method**: `Agent.terminate()`

Three related gaps discovered during Epic 4.4 analysis:

1. **Mailbox not closed before null:** `terminate()` at line ~622 does
   `self._mailbox = None` without calling `self._mailbox.close()` first. Any messages
   in-flight in the mailbox queue are silently discarded without drain.

2. **IAgentMailbox is sync-only:** `IAgentMailbox` protocol declares `send()` and
   `receive()` as synchronous methods. `receive()` will block the asyncio event loop
   thread. An `async def receive_async()` method is needed for non-blocking use.

3. **Existing LocalMailbox can be adapted:** `k1/bus/impl/local_mailbox.py`
   `LocalMailbox` already implements a queued FIFO with drain logic. Epic 4.4 should
   write a thin `AgentMailboxAdapter(LocalMailbox)` rather than building from scratch.

**Fix:**
1. Before `self._mailbox = None`, call `self._mailbox.close()` (or `drain()`) and await it.
2. Add `async def receive_async(self) -> Optional[Message]` to `IAgentMailbox`.
3. Reuse `LocalMailbox` as the backing store for the mailbox implementation.

---

## Issue 11 — `SchemaCompiler._cache` in `output_validation/schema_validator.py` has same check-then-set race as Issue 2

**File**: `k1/fabric/output_validation/schema_validator.py:52-100`
**Symbol**: `SchemaCompiler._cache`

`SchemaCompiler._cache` has the same pattern as Issue 2 (`contract_validator.py`):
check-if-key-exists then set, with no lock. Two concurrent first-validations for the same
schema type can both miss the cache and both attempt to compile+write, with the second
write overwriting the first.

**Fix**: Add `threading.Lock` around the cache check-then-set block. Same fix as Issue 2.

---

## Issue 12 — `registry_lookup_duration` histogram has no `labelnames`

**File**: `k1/fabric/metrics.py:~213`
**Symbol**: `registry_lookup_duration`

`registry_lookup_duration` histogram is defined without `labelnames`, unlike other histograms
in the same file (e.g., `execution_duration` has `labelnames=["capability", "provider"]`).
This means all registry lookups are aggregated into a single unlabelled bucket — it is
impossible to distinguish lookup latency by capability type or provider.

This is the same gap identified for Issue 10 (`execution_count`/`execution_duration` labels)
but for the registry subsystem.

**Fix**: Add `labelnames=["capability"]` to `registry_lookup_duration`. Update call sites to pass
the capability label when observing.
