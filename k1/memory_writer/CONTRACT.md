# K1 Memory Writer — CONTRACT

---

## 1. Purpose

`MemoryWriterService` observes conversation turns, extracts structured memory atoms from
them using an LLM, and submits those atoms to K0 via the Bridge. It is a stateless
side-effect component: it reads SessionState (read-only) and writes nothing back to it.

---

## 2. Core invariants

| ID | Statement | Enforcement |
|---|---|---|
| MW-01 | MW never writes to SessionState | `MemoryWriterFactory.create()` asserts no `IStateWritePort` in injected deps |
| MW-02 | SS snapshot latency < 1ms P99 | `MWSessionReader.read_snapshot()` raises `InvariantViolation` if exceeded |
| MW-03 | MW has no direct DB or HTTP ports | `MemoryWriterFactory.create()` rejects any raw DB/HTTP port |
| MW-04 | Every atom text is ≤ 50 words | `ExtractionValidator` truncates before atom creation |
| MW-05 | At most 6 atoms per turn | `ExtractionValidator.validate()` caps list |
| MW-06 | LLM token budget is always ≤ 2000 tokens (per-turn) | `MemoryWriterAgent.extract()` asserts before `chat()` |
| MW-07 | `RelevanceFilter` has no LLM dependency | `RelevanceFilter.__init__()` asserts |
| MW-08 | Batch window > 0 | `DeltaAggregator.__init__()` asserts |
| MW-09 | Bridge adapter is offline-capable | `MemoryWriterFactory.create()` soft-checks `supports_offline` |
| MW-10 | Every submitted envelope has a `cognitive_trace_id` | `EnvelopeBuilder.build()` asserts before returning |
| MW-11 | No UltraBERT (heavy embedding model) import in MW | CI/runtime `sys.modules` scan |
| MW-12 | `temporal_links` per atom: 0–5, valid `TemporalLinkType` values | `ExtractionValidator._validate_temporal_links()` |

---

## 3. Delivery guarantees

- **At-most-once extraction per turn** — `TurnDispatcher._processed_ids` (per-session set) deduplicates repeated `TOPIC_TURN_COMPLETE` deliveries for the same `turn_id`. Across restarts the set is lost — a turn replayed after crash may be re-extracted.
- **At-most-once extraction per session batch** — `SessionBatchDispatcher._processed_ids` (per-session set, under `asyncio.Lock`) deduplicates turns in buffer.
- **Offline-safe Bridge submission** — `IBridgeCommandPort.submit_batch()` is routed through Bridge's `LocalOutbox` (K0 WAL). If K0 is unreachable, the Bridge retains atoms until K0 recovers. MW itself has no WAL.
- **No ordering guarantee from MW to K0** — `DeltaAggregator.flush()` emits sorted by `(conversation_turn, extraction_sequence)` within a single batch. Across batches, Bridge submission order is best-effort.
- **Extraction is fire-and-forget** — MW never knows whether K0 accepted, reconciled, or discarded an atom. No ACK path.

---

## 4. Trigger and entry points

MW has **one external trigger**: the bus event `k1.session.turn.completed.v1`.

| Dispatcher | Topic subscribed | Behaviour |
|---|---|---|
| `TurnDispatcher` | `k1.session.turn.completed.v1` | One turn → one pipeline call (backpressure: newest wins when queue depth = 2) |
| `SessionBatchDispatcher` | `k1.session.turn.completed.v1` | Buffer up to 20 turns; flush on threshold, idle (300s), or `stop()` |

> **Live check:** M5-L1 verifies Concierge's publish topic and both MW dispatcher constants all use the same `completed` topic.

There is no direct API (no HTTP endpoint, no RPC). MW is bus-driven only.

---

## 5. Pipeline stages and contracts

Each turn payload flows through a 7-stage pipeline inside `MemoryWriterPipeline.process()`:

```
Stage 1: RelevanceFilter.evaluate()
  Input:  user_message, assistant_response, entities, topics, turn_id, timestamp_ms
  Output: FilterDecision(passed, skip_reason)
  Contract: No LLM call (MW-07). Must complete in O(words) time.
  Skip reasons: CLARIFICATION, SYSTEM_TURN, DUPLICATE, EMPTY, TRIVIAL

Stage 2: MWSessionReader.read_snapshot_enriched()
  Input:  session_id (for cold archive merging)
  Output: Dict[str, Any] — all SS sections except skip_sections
  Contract: Read-only (MW-01). Merges cold-archived history if LocalColdArchive is injected.

Stage 3a: ContextBuilder.build()
  Input:  SS snapshot + TurnCompletePayload
  Output: ExtractionContext (frozen, 25 fields)
  Contract: Temporal/spatial fields read payload-first (GAP-002 T7 fix).

Stage 3b: MemoryWriterAgent.extract() / extract_session()
  Input:  ExtractionContext, trace_id
  Output: List[RawExtraction]
  Contract: LLM call with budget_tokens ≤ 2000 (MW-06). Returns [] on LLM error (never raises).

Stage 4: ExtractionValidator.validate()
  Input:  List[RawExtraction], ExtractionContext
  Output: List[MemoryAtom] (frozen)
  Pipeline: truncate text → drop empties → resolve participants → drop < confidence_floor → cap temporal_links → cap at max_atoms_per_turn

Stage 5: EnvelopeBuilder.build() + PrivacyEnforcer.enforce()
  Input:  List[MemoryAtom], ExtractionContext, trace_id
  Output: List[dict] — K0-ready envelope bodies
  Contract: Every envelope has cognitive_trace_id (MW-10). Privacy enforcement applied per safety_band.

Stage 6: DeltaAggregator.add()
  Input:  envelope dict
  Output: bool (False = deduped by hash, discarded)
  Dedup key: SHA256(sorted_participants:sorted_topics)[:16]

Stage 7: BatchEmitter.emit(aggregator.flush())
  Input:  List[dict] sorted by (turn, sequence)
  Output: int (submitted count)
  Contract: Submits via IBridgeCommandPort.submit_batch(). Swallows bridge errors; returns 0 on failure.
```

**Pipeline errors** are fully swallowed at the `process()` level. Every stage exception is caught and returned as `PipelineResult(error=...)`. MW never raises to the bus dispatcher.

---

## 6. Port contracts

### `IBridgeCommandPort`

```python
async def submit(topic: str, schema_uri: str, body: Dict) -> None
async def submit_batch(envelopes: List[Dict]) -> None
```

- `submit_batch` is the hot path. `submit` is used for single-atom cases.
- Must be offline-capable (MW-09): stores locally when K0 unreachable.

### `IEventSubscriptionPort`

```python
async def subscribe(topic: str, handler: Callable[..., Coroutine]) -> Subscription
async def unsubscribe(subscription_id: str) -> None
async def publish(topic: str, payload: dict) -> None
```

- `subscribe` returns a `Subscription(subscription_id, topic)` handle.
- MW subscribes once at `start()` and unsubscribes at `stop()`.
- `publish` is used only for observability topics (MW-emitted events).

### `IModelHubPort`

```python
async def chat(messages: List[Dict[str, str]], budget_tokens: int, model_hint: str) -> ChatResponse
```

- `budget_tokens` must be ≤ 2000 (MW-06). Callers must assert before calling.
- `model_hint = "cheapest"` (default config). ModelHub selects the cheapest available provider.
- Returns `ChatResponse(content="", ...)` on provider error — never raises.

### `ISessionReadPort`

```python
async def snapshot(sections: List[str]) -> Dict[str, Any]
async def read_section(name: str) -> Optional[Dict[str, Any]]
async def list_sections() -> FrozenSet[str]
async def snapshot_all(exclude: FrozenSet[str] = frozenset()) -> Dict[str, Any]
async def read_archived_history(session_id: str, limit: int = 50) -> List[Dict[str, Any]]
```

- MW calls `snapshot_all(exclude={"telemetry", "artifacts_warm"})` on each turn.
- `read_archived_history` is called in `read_snapshot_enriched` when `LocalColdArchive` is injected.
- MW never calls any write variant of `ISessionReadPort`.

### `IHealthPort`

```python
async def is_ready() -> bool
async def health_check() -> HealthStatus
```

- `HealthStatus` fields: `is_healthy`, `llm_circuit_open`, `pending_batch_count`, `last_extraction_ms`, `detail`.
- `llm_circuit_open=True` means the LLM circuit breaker is open; extractions are being skipped.

---

## 7. Key types

### `MemoryAtom` (frozen, 37 fields)

The core unit of memory. Every atom has:

- `text` (≤ 50 words) — what was said/observed
- `topics`, `categories` — semantic classification
- `activity_type` — one of 30 `ActivityType` values
- `participants`, `participant_relationships` — who was involved (PersonResolution applied)
- `location_name`, `location_type`, `place_id`, `geohash_6` — where (privacy-enforced)
- `sentiment_label` (`SentimentLabel`), `emotion_tags`, `affect` (VAD triple)
- `temporal_links` (0–5 `TemporalLink`s, MW-12)
- `novelty` (`NoveltyLevel`), `elaboration_depth` (`ElaborationDepth`)
- `correction_signal`, `contradiction_signal`, `supersedes_concept` — K0 reconciliation signals
- `confidence` (0.0–1.0; floor = `config.confidence_floor = 0.30`)
- `session_id`, `conversation_turn`, `extraction_sequence` — provenance
- `operation` — always `"UPSERT"` from MW; `DELETE`/`EXPIRE` are K0 operations only

### `TurnCompletePayload` (17 fields)

The trigger event. Key fields:

- `turn_id`, `session_id`, `cognitive_trace_id`
- `user_message`, `assistant_response`
- `timestamp_ms`, `turn_number`
- Temporal snapshot (GAP-002): `mentioned_time_raw`, `mentioned_time_resolved_ms`, `mentioned_time_confidence`, `mentioned_time_is_relative`
- Spatial snapshot (GAP-002): `mentioned_location_raw`, `mentioned_location_type`, `mentioned_location_entity_id`, `mentioned_location_confidence`

### `ExtractionContext` (frozen, 25 fields)

Assembled from SS snapshot + `TurnCompletePayload` before LLM call. Provides:

- `current_turn`, `recent_turns` (CompressedTurn list)
- `active_persons` (from SS `beliefs_active`)
- `current_affect`, `baseline_affect` (Affect VAD)
- `active_topics`, `topic_salience`, `active_goals`
- `control_context` (safety_band, tenant_id, user_id, device_id)
- `session_id`, `conversation_turn`, `turn_timestamp_ms`
- Pre-resolved temporal/spatial fields from payload

### `FilterDecision` (frozen)

`passed: bool` + `skip_reason: Optional[SkipReason]`.
`SkipReason` values: `CLARIFICATION, SYSTEM_TURN, DUPLICATE, EMPTY, TRIVIAL, STALE (deprecated)`.

### `PipelineResult` (frozen)

Returned by every `process()` call regardless of success/failure:
`skipped, skip_reason, atoms_extracted, envelopes_submitted, llm_tokens_used, llm_latency_ms, trace_id, error`.

---

## 8. Bus topics produced (observability)

All topics are observability-only — no other K1 component subscribes to these.

| Topic | Payload | When emitted |
|---|---|---|
| `k1.mw.filter.decision.v1` | `FilterDecisionEvent` | After Stage 1, whether passed or skipped |
| `k1.mw.extraction.complete.v1` | `ExtractionCompleteEvent` | After Stage 3b LLM call |
| `k1.mw.batch.submitted.v1` | `BatchSubmittedEvent` | After Stage 7 Bridge submission |
| `k1.mw.pipeline.error.v1` | `PipelineErrorEvent` | On any stage exception |
| `k1.mw.circuit.open.v1` | `CircuitOpenEvent` | When `CircuitBreaker` transitions to OPEN |

All these are published via `_publish_safe()` which swallows all exceptions.

---

## 9. Privacy enforcement contract

Applied after `EnvelopeBuilder.build()`, before `DeltaAggregator.add()`. Source of band: `context.control_context["safety_band"]`.

| Band | Enforcement |
|---|---|
| `GREEN` | No-op |
| `AMBER` | `location_name` → category label only (e.g. `"Olive Garden"` → `"Restaurant"`) |
| `RED` | Strip all: `location_name`, `location_type`, `place_id`, `geohash_6`; replace participants with `["person_redacted_0", ...]` |
| Unknown | Treated as `RED` (fail-secure) |

**Defense-in-depth:** K0 Gate also enforces band policies on receipt. MW enforcement is a K1-side pre-submission filter.

---

## 10. Circuit breaker contract

`CircuitBreaker` protects the LLM extraction path only (Stage 3b).

```
CLOSED → (3 consecutive LLM failures) → OPEN (all extractions skipped)
OPEN   → (30s elapsed) → HALF_OPEN (one probe extraction)
HALF_OPEN → (probe succeeds) → CLOSED
HALF_OPEN → (probe fails) → OPEN
```

When OPEN: `MemoryWriterAgent.extract()` returns `[]` without calling `IModelHubPort.chat()`.
Circuit breaker state is instance-scoped (per `MemoryWriterService`). No cross-session bleed.

---

## 11. What MW does NOT do

- Does **not** write SessionState (MW-01)
- Does **not** issue DELETE or EXPIRE commands to K0 — reconciliation (EVOLVE/CONTRADICT) is signalled via `correction_signal`/`contradiction_signal` fields on atoms; K0 handles the operation
- Does **not** embed text (MW-11) — K0 P02 computes embeddings on receipt
- Does **not** access the internet directly (MW-03)
- Does **not** call Concierge, Orchestrator, Planner, or Fabric
- Does **not** have a health-check server or metrics exporter — observability is via bus events only
- Does **not** persist any state across restarts (all state is in-memory; processed_ids set is per-session)
