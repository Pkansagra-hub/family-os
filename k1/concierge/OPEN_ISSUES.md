# K1 Concierge — OPEN ISSUES

All known design gaps, stubs, deprecated paths, and failure modes in the current
concierge implementation.

---

## ISSUE-C01 — ExperienceLayer stubs: NarrativeWeaver, AnticipatoryResponder, ProactiveAgent

**Severity:** Medium
**Location:** `k1/concierge/experience/narrative_weaver.py`, `anticipatory_responder.py`, `proactive_agent.py`

> **CORRECTION (May 2026):** Original description had wrong method names.
> Actual methods: `NarrativeWeaver.weave()` (not `.compute()`),
> `AnticipatoryResponder.anticipate()` (not `.compute()`).

**Current behavior:**
All three sub-components return hard-coded empty defaults:
- `NarrativeWeaver.weave()` → `NarrativeContext(narrative_threads=[], story_arc=None)`
- `AnticipatoryResponder.anticipate()` → `Anticipation(predicted_needs=[], confidence=0.0)`
- `ProactiveAgent.generate_fill()` → `FillMessage(text="", trigger=None)`

**Failure mode:** Front LLM receives no narrative context, no anticipatory signal, and
COMPANIONING proactive fills never fire even though the FSM allows it. Users waiting
long periods in COMPANIONING state see nothing from the AI.

**Fix:** Implement NarrativeWeaver first (every 20th turn; identify recurring themes from
history). ProactiveAgent depends on NarrativeWeaver's arc to generate meaningful fills.
AnticipatoryResponder can be LLM-based using history + beliefs sections.

---

## ISSUE-C02 — EpisodicCompressor compression strategy is ignored; `ExperienceLayer` never calls it

**Severity:** Medium
**Location:** `k1/concierge/experience/episodic_compressor.py`, `k1/concierge/experience/experience_layer.py`

> **CORRECTION (May 2026):** Original description said `compress_segment()` was a stub
> (first-sentence extractive only). **This is wrong.** `compress_segment()` at
> `episodic_compressor.py:~210-252` is a full key-facts extractive implementation
> that extracts salient sentences by frequency scoring.
>
> The actual gaps are:
> 1. `compression_strategy` field on `EpisodicCompressor` is accepted but **ignored**
>    — the strategy enum has no effect on which algorithm runs.
> 2. `EpisodicCompressor` is **never called from `ExperienceLayer`** — the two classes
>    are completely decoupled. No call site connects them.

**Failure mode:** Even though compression is implemented, it is never invoked. Session
history grows indefinitely without compression. After 50+ turns, the LLM's effective
context becomes large and expensive.

**Fix:**
1. Wire `EpisodicCompressor` into `ExperienceLayer.process_turn()` (call on every Nth turn).
2. Implement strategy dispatch: `LLM_BASED` → `_compress_with_llm()`, `EXTRACTIVE` → current key-facts path.

---

## ISSUE-C03 — Back actor has no time-based task cancellation

**Severity:** Medium
**Location:** `k1/concierge/react/loop.py` (NOT `actors/back_actor.py`)

> **CORRECTION (May 2026):** Original description said the issue was in `back_actor.py`.
> **Actual location is `react/loop.py`.** The LLM invocation in the ReAct loop already
> has `asyncio.wait_for` protection. The gap is specifically in the `_run_tool()` closure
> inside `react/loop.py` — tool dispatch is not wrapped in `asyncio.wait_for`.

**Current behavior:**
Cancellation is iteration-based only — Back polls `cancel_token.is_cancelled()` at
each ReAct iteration boundary. A tool call that takes 30+ seconds (e.g., a slow
external API call) cannot be interrupted mid-execution.

**Failure mode:** Under user-requested cancellation (`USER_REQUESTED`), the FSM
transitions to CANCELLING and waits for `task.failed.v1`. If the current tool call
blocks for minutes, the user sees the system appear to hang in CANCELLING state.

**Fix:** Wrap `_run_tool()` in `asyncio.wait_for(tool_call(), timeout=config.tool_timeout_ms)`
in `react/loop.py`. Propagate `asyncio.TimeoutError` as `TIMEOUT` reason in the
CancellationToken. This requires tools registered in Fabric to be cancellable coroutines
(currently not enforced by `IDispatchPort`).

---

## ISSUE-C04 — Crash recovery re-delivers completed results to user

**Severity:** High
**Location:** `k1/concierge/core/crash_recovery.py:project_pending_results()`, `k1/concierge/ledger/recovery.py:221-256`

> **CORRECTION (May 2026):** Original description said projection checks `response.final.v1`.
> **Actual projection at `ledger/recovery.py:221-256` checks `conversation.weave.emitted`.**
> The event checked is `WeaveEmitted`, not `ResponseDelivered`.
> The `ResponseDelivered` event **does not exist** yet.
> The correct write point for the delivery-intent ledger entry is `controller.py:~3330`,
> NOT `front.py` — the ledger is unreachable from `front.py`.

**Current behavior:**
The ledger projection re-queues all `task.complete.v1` events that do not have a
corresponding `WeaveEmitted` in the log. However, `WeaveEmitted` is written *after* the
Front LLM's streaming response starts. If the process crashes after streaming starts but
before `WeaveEmitted` is written, the result is re-queued and re-delivered.

**Failure mode:** After a crash at the exact moment between streaming start and
`WeaveEmitted` write, the user receives the same message twice.

**Fix:** Add a `ResponseDelivered` ledger event written **before** streaming begins
(as delivery intent) at `controller.py:~3330`. Projection checks for `ResponseDelivered`
rather than `WeaveEmitted`. This makes delivery idempotent even if the stream fails.

---

## ISSUE-C05 — Config lives outside `k1/` in `poc.k1_poc.config` ✅ CLOSED

**Severity:** Low — RESOLVED
**Location:** `k1/concierge/config/__init__.py`, `k1/concierge/config/loader.py`

**Verified (M1 pre-implementation read):**
`k1/concierge/config/__init__.py` imports ONLY from `k1.concierge.config.loader`
(a standalone 1,400+ line module with no `from poc.` imports in production code).
The `from poc.k1_poc.config` lines that appeared in grep were in the module
docstring of `loader.py` as usage examples — not real import statements.
Stale docstring header removed in M1 implementation (loader.py lines 1–22 cleaned up).

**Status:** Closed. No re-export shim exists; all config classes are self-contained
in `k1/concierge/config/loader.py`. `py.typed` marker can be added as a future XS
cleanup if desired.

---

## ISSUE-C06 — WeavePolicy A/B flag has no runtime toggle API

**Severity:** Low
**Location:** `k1/concierge/core/weave_policy.py`, `WeavePolicyConfig.enabled`

**Current behavior:**
`WeavePolicyConfig` has an `enabled: bool` field for per-session A/B testing of the
weave policy (disabled sessions use `WeaveFallbackHandler` — static 500ms BATCH).
However, there is no HTTP or bus API to toggle this flag per-session at runtime. It is
set once at session creation and cannot change without restarting the session.

**Failure mode:** A/B experiments require session restart to switch arms. Cannot
dynamically enable/disable WeavePolicy for a live session during an experiment rollout
or rollback.

**Fix:** Expose a `weave_policy.set_enabled(bool)` call path. Trigger it via a bus
event (`system.config.v1` with `target=weave_policy`) or a kernel config update API.

---

## ISSUE-C07 — `subscribe_back_events` deprecated path (M3 → M8 migration)

**Severity:** Low
**Location:** `k1/concierge/actors/back.py:1127-1186` (NOT `fsm_controller.py`)

> **CORRECTION (May 2026):** Original description said the location was
> `k1/concierge/core/fsm_controller.py:subscribe_back_events()`. **Wrong location.**
> All three functions are in `back.py`:
> - `subscribe_back_events()` at `back.py:~1127`
> - `store_pending_context()` at `back.py:~1088`
> - `_clear_pending_context()` at `back.py:~1457`

**Current behavior:**
`subscribe_back_events()` in `back.py` is a legacy code path from pre-M3 architecture.
The method is annotated with `# deprecated as of M3, scheduled removal M8`. If called
by mistake, it registers duplicate subscriptions for `task.complete.v1` and
`task.failed.v1`, causing each completion event to trigger two state transitions.

**Failure mode:** Duplicate FSM transitions on `task.complete` — system cycles into
DELIVERING twice for the same result. Second transition dead-letters because FSM is
already in LISTENING after first transition.

**Fix:** Remove all three functions from `back.py`. Verify no external callers via
symbol search before removal.

---

## ISSUE-C08 — `back_resume_handler` has stale legacy `_get_pending_context` fallback

**Severity:** Low
**Location:** `k1/concierge/actors/back.py:back_resume_handler()` (NOT `back_actor.py`)

> **CORRECTION (May 2026):** Original description said the location was
> `actors/back_actor.py`. **Actual location is `back.py`**, which contains
> `back_resume_handler()` and `_get_pending_context()` at `back.py:~1457`.

**Current behavior:**
`back_resume_handler()` in `back.py` contains a fallback path:
```python
context = self._suspension_manager.get_resolution(task_id) \
    or self._get_pending_context(task_id)  # legacy, scheduled removal
```
`_get_pending_context()` reads from an old in-memory dict that is no longer populated
post-M3. It will always return `None`, making the fallback silently absent rather than
explicitly failing.

**Failure mode:** If a suspension resolution is not in `SuspensionManager` (ledger
replay edge case), Back resumes with `resolution=None`. Back will attempt to continue
the ReAct loop without the user's answer, likely producing a hallucinated response.

**Fix:** Remove `_get_pending_context()` and the fallback from `back.py`. Replace with
an explicit raise: `if resolution is None: raise SuspensionResolutionNotFound(task_id)`.
Handle the exception in the FSM controller by re-surfacing the HITL request to the user.

---

## ISSUE-C09 — Phase1 pipeline runs as a stub in non-poc deployments

**Severity:** High
**Location:** `k1/concierge/core/fsm_controller.py`, `k1/concierge/ports/classification_port.py`

**Current behavior:**
`StubPhase1Pipeline` is the default when UltraBERT is not available. It returns
`Phase1Result(domain="general", intent_class="SINGLE", confidence=0.5)` for every
input — a fixed classification.

**Failure mode:** Intent classification is the gate for: ArbiterDecision selection,
ComplexityTier determination, domain-specific prompt enrichment, privacy band routing.
With stub classification, all inputs are classified as `general/SINGLE` at 0.5 confidence.
This means: Arbiter always takes PARALLEL_NEW path, tasks always get LOW complexity tier,
domain-specific enrichments never fire. The system functions but performs significantly
below capability.

**Fix:** Either (a) include a minimal HuggingFace TorchScript UltraBERT build in the
standard Docker image (GPU or CPU), or (b) implement a keyword-based fallback that
correctly identifies at least domain (home/finance/health/calendar) and single vs.
bundled intent. The keyword fallback is O(n) on ~200 keywords — acceptable for
production when the full model is unavailable.

---

## ISSUE-C10 — Front history window does not include task chain context for WEAVING mode

**Severity:** Medium
**Location:** `k1/concierge/actors/front_actor.py:build_chat_history()`

**Current behavior:**
History window in WEAVING mode is the same as DELIVERING mode (5 turns). In WEAVING,
Front may be synthesizing results from 3–4 parallel tasks that were dispatched across
multiple turns. The 5-turn window may not include the original dispatch turns, so Front
reconstructs results without user-visible task context ("here are your results" without
knowing what was requested).

**Failure mode:** Front's weave response lacks grounding — it presents results without
referring back to what the user originally asked for, which feels disjointed. More
severely, if any parallel task chain has a dependency (task B was requested because task
A's result implied it), Front has no visibility into that chain in WEAVING mode.

**Fix:** In WEAVING mode, augment the history window with: (a) the `task_dispatch`
history entries for all tasks whose results are in the pending results queue, and (b)
the original user turn that triggered the dispatch. This is bounded (at most N pending
results × 2 entries) and solves grounding without widening the full window.
