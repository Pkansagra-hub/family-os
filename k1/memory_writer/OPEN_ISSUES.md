# K1 Memory Writer — OPEN ISSUES

---

## ISSUE-MW01 — `SessionBatchDispatcher` uses stale topic `k1.session.turn.completed.v1`

**Severity:** High
**Location:** `k1/memory_writer/pipeline/session_batch_dispatcher.py`, class constant `TOPIC`

**Current behavior:**
`SessionBatchDispatcher.TOPIC = "k1.session.turn.completed.v1"` (with `d`).
`TurnDispatcher.TOPIC = "k1.session.turn.complete.v1"` (without `d`).
The docstring inside `SessionBatchDispatcher` explicitly notes the old topic was
"a dead pipeline." The default `extraction_mode` is `"session_batch"`, which selects
`SessionBatchDispatcher`. This means the default production path subscribes to a topic
that may never receive events — depending on which variant Concierge actually emits.

**Failure mode:** If Concierge emits only `k1.session.turn.complete.v1`, `SessionBatchDispatcher`
receives zero events. The buffer never fills; no extraction occurs; all turns are silently
dropped. There is no counter, no error, no bus event emitted. Memory for the session is empty.

**Fix:** Audit which exact topic Concierge emits (check `k1/concierge/events.py`). Align
`SessionBatchDispatcher.TOPIC` to match. Consider emitting both topics during a transition
period. Add a startup assertion or integration test that verifies the dispatcher's subscribed
topic matches the emitter's published topic.

---

## ISSUE-MW02 — `_processed_ids` is unbounded and lost on restart; duplicate extraction on crash

**Severity:** Medium
**Location:** `k1/memory_writer/pipeline/turn_dispatcher.py`, `session_batch_dispatcher.py`

**Current behavior:**
`_processed_ids: set[str]` is an in-memory set per `MemoryWriterService` instance. On crash or
restart, the set is empty. A `turn_id` that was already extracted in the previous session can
be re-delivered (via at-least-once bus delivery) and re-extracted, producing duplicate atoms
in K0. For long sessions, `_processed_ids` also grows without bound (one entry per turn, no
pruning).

**Failure mode (dedup):** Crash during extraction of turn 7. On restart, bus replays turns 5–10.
Turns 5–6 were submitted to Bridge (K0 accepted); turns 5–6 are re-extracted and re-submitted.
K0 may UPSERT them again — depending on K0's own dedup, the atoms appear twice or a new version
overrides the previous one.

**Failure mode (memory):** A 1000-turn session accumulates 1000 strings in `_processed_ids`.
Each `turn_id` is ~36 bytes (UUID). 1000 entries ≈ 36KB. Not severe in practice, but the set
is never pruned even after flush.

**Fix (short term):** Cap `_processed_ids` to a sliding window of the last N turn IDs
(use `deque(maxlen=200)`). Older entries drop off naturally.

**Fix (long term):** Persist `_processed_ids` to a lightweight sidecar (e.g. a K0-backed KV key
`mw:processed:{session_id}`) and restore on startup. Alternatively, stamp each atom with its
source `turn_id`; let K0 enforce idempotency on `(session_id, turn_id, extraction_sequence)`.

---

## ISSUE-MW03 — `SBD._flush_buffer()` may run concurrently; second flush sees empty buffer silently

**Severity:** Medium
**Location:** `k1/memory_writer/pipeline/session_batch_dispatcher.py:_flush_buffer()`

**Current behavior:**
Three triggers can call `_flush_buffer()` concurrently: the threshold check inside
`_on_turn_completed()` (spawns a task), the idle loop (spawns a task), and `stop()` (direct
await). Each flush acquires the `asyncio.Lock`, drains the buffer, releases lock, then calls
`pipeline.process_session()` on the drained copy. If two flush tasks race, the first grabs
the buffer and the second sees `[]`. The second task calls `pipeline.process_session([])` —
which is a no-op but still acquires the pipeline, reads SS, and calls the LLM with an empty
turn list.

**Failure mode:** Not a data loss issue (second flush produces no atoms). However, in a
high-turn session with both threshold and idle flush firing simultaneously, two empty LLM calls
are made. Each costs ≈ one `IModelHubPort.chat()` invocation (background priority, but still
counted against model budget).

**Fix:** Guard `_flush_buffer()` with a `_flush_in_progress: bool` flag. If `True`, skip the
second flush entirely (do not even acquire the lock). Or check `if not self._buffer: return`
after acquiring the lock before draining.

---

## ISSUE-MW04 — `PlaceResolver` is constructed with empty entities; geohash always falls back to `"000000"`

**Severity:** Medium
**Location:** `k1/memory_writer/factory.py` (line: `PlaceResolver([])`), `place_resolver.py`

**Current behavior:**
`MemoryWriterFactory.create()` constructs `PlaceResolver([])` — with an empty entity list.
A factory comment says "populated per-turn from SS." But `PlaceResolver` receives no update
mechanism; it has no `update_entities()` method. The entity list provided at construction is
all it has. On every `resolve_with_geohash()` call: no entity matches → place_id resolved but
no geohash → sentinel `"000000"` returned.

**Failure mode:** Every atom with a location gets `geohash_6 = "000000"`. K0 proximity queries
and location-based retrieval fail silently — all family memories appear to be co-located at
lat/lon (0°, 0°) (the ocean near Ghana). No error is raised; no warning is emitted.

**Fix:** On each pipeline `process()` call, extract the `beliefs_active.known_locations` list
from the SS snapshot and pass it to `PlaceResolver` (either re-construct or add a
`set_entities()` method). Alternatively, move entity resolution into `ContextBuilder.build()`
and pass resolved place data directly into the `ExtractionContext` used by `FieldMapper`.

---

## ISSUE-MW05 — Confidence floor (`0.30`) silently drops atoms; no observability on drop rate

**Severity:** Low
**Location:** `k1/memory_writer/extraction/extraction_validator.py`, `k1/memory_writer/config.py`

**Current behavior:**
`ExtractionValidator.validate()` drops all `RawExtraction` items where `confidence < 0.30`.
This is the correct behaviour (low-confidence atoms should not be written), but the number
dropped is not tracked. `PipelineResult.atoms_extracted` reflects atoms AFTER the confidence
filter — callers cannot distinguish "3 atoms extracted" from "8 extracted, 5 dropped for
low confidence."

**Failure mode:** If the LLM degrades in quality and starts returning 0.0–0.25 confidence
across many turns, MW appears healthy (circuit breaker stays closed, `atoms_extracted > 0`
from the occasional high-confidence item), but effective memory write rate drops dramatically
without any alert.

**Fix:** Add `atoms_below_confidence_floor: int` to `PipelineResult`. Emit this as part of
`ExtractionCompleteEvent` on `k1.mw.extraction.complete.v1`. Add a Prometheus counter
`mw_atoms_confidence_dropped_total` in `HealthAdapter` or a metrics shim.

---

## ISSUE-MW06 — `TurnDispatcher._queued_payload` newest-wins may drop important correction turns

**Severity:** Low
**Location:** `k1/memory_writer/pipeline/turn_dispatcher.py`

**Current behavior:**
When a turn arrives while `_processing=True` and `_queued_payload` is already set, the newer
turn replaces the older one. The older queued turn is silently discarded. This is intentional
for trivial conversational turns (e.g. "thanks", "OK") but dangerous for correction turns —
turns with `correction_signal=True` or `contradiction_signal=True` carry semantic updates
that should never be dropped.

**Failure mode:** User says "I meant yesterday, not today" (correction turn) arrives queued
while a prior extraction is in flight. A new trivial turn arrives 2 seconds later. The
correction turn is dropped. K0 retains the incorrect atom; the user's correction is lost.

**Fix:** When replacing `_queued_payload`, check if the outgoing queued payload has
`correction_signal` or `contradiction_signal` fields in the raw dict. If so, do not replace —
either buffer both (expand queue depth to 2) or prioritize correction turns over trivial ones.
Alternatively, move to `SessionBatchDispatcher` by default and keep `per_turn` mode only for
latency-sensitive scenarios.

---

## ISSUE-MW07 — `phantom_sections` (`affective_baseline`, `ifl`) silently omitted from ExtractionContext

**Severity:** Low
**Location:** `k1/memory_writer/context/context_builder.py`, `k1/memory_writer/config.py` (comment)

**Current behavior:**
`ContextBuilder.build()` attempts to read `affective_baseline` (for `baseline_affect`) and
`ifl` (for `device_context`) from the SS snapshot. These sections are documented as "phantom
sections" — they are not in `SessionState.ALL_SECTIONS`. `snapshot_all(exclude=...)` excludes
sections not in ALL_SECTIONS. The dict keys for these sections are never present. The context
fields default to `None` / `{}`.

**Failure mode:** `baseline_affect = None` means affect delta calculations (current vs. baseline)
in `MemoryWriterAgent` always treat the baseline as unknown. Atoms that should be flagged as
`NOVEL` or `SURPRISING` (because they deviate from baseline) are classified as `EXPECTED`.
Device context (`ifl`) absent means MW cannot distinguish "shared device" from "personal device"
for privacy enforcement nuance.

**Fix:** If `affective_baseline` and `ifl` are legitimate SS sections that are populated by
Concierge or another component, add them to `SessionState.ALL_SECTIONS`. If they are deprecated
or future sections, add `TODO` comments and remove the silent omission pattern — log a warning
instead.

---

## ISSUE-MW08 — `read_snapshot_enriched` cold archive merge has no pagination; limit is hard-coded to 50

**Severity:** Low
**Location:** `k1/memory_writer/context/session_reader.py:read_snapshot_enriched()`

**Current behavior:**
`read_archived_history(session_id, limit=50)` fetches the last 50 archived turns from
`LocalColdArchive` and merges them into `history_active`. For sessions longer than 50
archived turns, the full context is not available to the LLM. In `session_batch` mode,
the batch itself may contain 20 turns; the cold archive adds 50 more — total context window
of 70 turns passed to the LLM. This may exceed `llm_token_budget_session=4000` tokens for
long turns.

**Failure mode (context truncation):** A session with 200 archived turns only sees the most
recent 50. MW extracts atoms based on incomplete conversation history. Cross-turn references
("like we discussed last week") cannot be resolved.

**Failure mode (token overflow):** 70 long turns × average 100 tokens each = 7000 tokens >
4000 budget. The LLM call is rejected or truncated. `MemoryWriterAgent.extract_session()`
returns `[]`. Extraction silently fails for that batch.

**Fix:** Add adaptive history limit: estimate tokens for the current batch, then compute
remaining budget before allocating archive slots. Expose `history_limit` as a config field
(`config.archive_history_limit`, default 50) rather than a hard-coded literal. Add a
`PipelineResult.context_truncated: bool` flag when estimated tokens exceed budget.

---

## ISSUE-MW09 — Circuit breaker is instance-scoped but `HealthAdapter` probes are lambdas

**Severity:** Low
**Location:** `k1/memory_writer/adapters/health_adapter.py`, `k1/memory_writer/fabric_registration.py`

**Current behavior:**
`HealthAdapter.__init__(cb, is_ready_fn: Callable[[], bool], last_ms_fn: Callable[[], float])`.
`HealthAdapter.last_extraction_ms` is always `0.0` — the comment says "tracked via metrics,
not here." The `last_ms_fn` lambda is documented but not actually recorded anywhere in the
pipeline. `health_check()` returns `HealthStatus(last_extraction_ms=0.0)` always.

**Failure mode:** Operator tooling that relies on `HealthStatus.last_extraction_ms` to detect
a stuck pipeline (e.g. "no extraction for 5 minutes → alert") always sees `0.0` regardless of
actual pipeline state. A permanently stuck MW (no turns processed, circuit open) looks identical
to a healthy MW in health check output.

**Fix:** Have `MemoryWriterPipeline` record the last successful extraction timestamp in a
field (e.g. `_last_extraction_ms: float` updated after Stage 7). Pass a lambda
`lambda: pipeline._last_extraction_ms` as `last_ms_fn` to `HealthAdapter`. This requires
either exposing the field or adding a `last_extraction_ms` property to `MemoryWriterPipeline`.

---

## ISSUE-MW10 — `ExtractionValidator` does not validate `operation` field; UPSERT hardcoded but not checked

**Severity:** Low
**Location:** `k1/memory_writer/extraction/extraction_validator.py`, `k1/memory_writer/types.py`

**Current behavior:**
`MemoryAtom.operation = "UPSERT"` is a hard-coded default. `RawExtraction` does not have an
`operation` field — the LLM cannot set it. However, `ExtractionValidator.validate()` constructs
`MemoryAtom` from `RawExtraction` fields without ever verifying the operation is valid. If a
future version of `MemoryWriterAgent.extract()` returns a `RawExtraction` with an `operation`
override (e.g. from a prompt change), the validator would silently pass it through, and K0
could receive a `DELETE` or `EXPIRE` operation from MW — violating the design invariant that MW
only UPSERTs.

**Fix:** Add `operation: str = "UPSERT"` to `RawExtraction`. In `ExtractionValidator.validate()`,
assert `raw.operation == "UPSERT"` before constructing the `MemoryAtom`, raising
`InvariantViolation("MW-UPSERT_ONLY", ...)` otherwise. Register this as invariant MW-13.
