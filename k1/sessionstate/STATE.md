# K1 SessionState — STATE

All mutable state owned by `k1/sessionstate/`. Organised by class.
"Thread-safe via" indicates which lock guards concurrent access.

---

## 1. `SessionStateManager`

| Field | Type | Init value | Mutated by | Thread-safe via |
|---|---|---|---|---|
| `_state` | `ManagerState` enum | `CREATED` | `start()`, `stop()` | `_write_lock` |
| `_session_id` | `str` | constructor | immutable | n/a |
| `_write_lock` | `threading.RLock` | new | n/a (synchronizer itself) | n/a |
| `_hot` | `HotTier` | constructor | mutations, reconstruction | `_write_lock` |
| `_warm` | `WarmTier` | constructor | mutations, migration, eviction, reconstruction | `_write_lock` |
| `_size_tracker` | `SizeTracker` | constructor (all zeros) | every mutation, eviction, reconstruction | `_write_lock` |
| `_mutation_guard` | `MutationGuard` | constructor | emergency mode, section locks | see MutationGuard |
| `_eviction_engine` | `EvictionEngine` | constructor | eviction iteration count | `_write_lock` |
| `_migration_engine` | `MigrationEngine` | constructor | migration iteration count | `_write_lock` |
| `_reconstruction` | `ReconstructionSLA` | constructor | SLA counters | `_write_lock` |
| `_local_cold` | `LocalColdArchive` | constructor | archive/restore calls | SQLite WAL |

`ManagerState` transitions:
```
CREATED → STARTING → RUNNING → STOPPING → STOPPED
                                         └→ ERROR
```

---

## 2. `HotTier`

| Field | Type | Init value | Mutated by |
|---|---|---|---|
| `_sections` | `Dict[str, ISection]` | 10 section objects | migration, eviction |
| `_total_bytes` | `int` | 0 | every mutation |
| `_budget_bytes` | `int` | 53,248 | immutable |

Section objects held in `_sections` are themselves mutable (see §5–9 below).

---

## 3. `WarmTier`

| Field | Type | Init value | Mutated by |
|---|---|---|---|
| `_sections` | `Dict[str, ISection]` | 5 section objects | migration, eviction |
| `_total_bytes` | `int` | 0 | every mutation |
| `_budget_bytes` | `int` | 49,152 | immutable |

---

## 4. `SizeTracker`

| Field | Type | Init value | Mutated by |
|---|---|---|---|
| `_section_sizes` | `Dict[str, int]` | all zeros (15 entries) | `update()`, `reset()`, `set()` |
| `_hot_total` | `int` | 0 | `update()` for HOT sections |
| `_warm_total` | `int` | 0 | `update()` for WARM sections |

Pressure calculation (read-only, computed on call):
- `get_pressure()` → `PressureLevel` based on `total / TOTAL_LIMIT`
- `get_hot_pressure()` → based on `_hot_total / hot_budget`
- `get_warm_pressure()` → based on `_warm_total / warm_budget`

Thresholds:
- NORMAL: < 80%
- ELEVATED: 80–89%
- CRITICAL: 90–94%
- EMERGENCY: ≥ 95%

---

## 5. `MutationGuard`

| Field | Type | Init value | Mutated by | Thread-safe via |
|---|---|---|---|---|
| `_emergency_mode` | `bool` | `False` | `set_emergency_mode(active)` | `_emergency_lock` |
| `_locked_sections` | `Set[str]` | empty set | `lock_section()`, `unlock_section()` | `_section_lock` |
| `_emergency_lock` | `threading.Lock` | new | n/a | n/a |
| `_section_lock` | `threading.Lock` | new | n/a | n/a |

`FLATBUFFER_OVERHEAD_FACTOR = 1.10` — applied to `estimated_bytes` in preflight.
`VALID_OPERATIONS` — `frozenset` (~35 strings). Immutable after class construction.

---

## 6. HOT section state: `ControlSection`

| Field | Type | Description |
|---|---|---|
| `flow_state` | `FlowState` | `phase: FlowPhase`, `locked_by: str?`, `lock_reason: str?` |
| `turn_lock` | `TurnLock` | `is_locked: bool`, `locked_by: str?`, `lock_reason: str?` |
| `agent_leases` | `List[AgentLease]` | Active agent leases |
| `domain_context` | `DomainContext` | current_domain, active_capabilities, constraints |
| `safety_context` | `SafetyContext` | privacy_band, content_flags, blocked_topics |
| `intent_classification` | `IntentClassification` | intent, confidence, alternatives |
| `privacy_band` | `PrivacyBand` | GREEN/AMBER/RED/BLACK |

`AgentLease` fields: `agent_id, agent_type, state: AgentState, lease_started_ms, lease_expires_ms, capabilities[], priority`

`AgentState` (IntEnum): `PENDING=0 WARMING=1 ACTIVE=2 IDLE=3 DRAINING=4 TERMINATED=5`

`FlowPhase` (IntEnum): `IDLE=0 NEGOTIATION=1 SELECTION=2 EXECUTION=3`

---

## 7. HOT section state: `BeliefsActiveSection`

| Field | Type | Capacity | Eviction |
|---|---|---|---|
| `facts` | `List[Fact]` | max ~50 | Demotes → `beliefs_history` when HOT pressure > threshold |
| `entities` | `List[EntityRef]` | unbounded (within 8KB) | same |
| `mentioned_time` | `MentionedTime?` | 1 | same |
| `mentioned_location` | `MentionedLocation?` | 1 | same |
| `pinned_fact_ids` | `List[str]` | small | not evicted (filter from demote list) |

`Fact` fields: `id: str, subject: str, predicate: str, object: str` (SVO triple),
`confidence: float, source: str, timestamp_ms: int, privacy_band: PrivacyBand`

---

## 8. HOT section state: `HistoryActiveSection`

| Field | Type | Capacity |
|---|---|---|
| `turns` | `List[Turn]` | max 10 full-fidelity turns |
| `typed_entries` | `List[TypedHistoryEntry]` | per-turn, 9 entry types |
| `current_turn_number` | `int` | monotonically increasing |
| `user_tokens_total` | `int` | cumulative |
| `response_tokens_total` | `int` | cumulative |

`TypedHistoryEntry` types: `user / ack / final / weave / clarification / hitl_request / hitl_response / error / proactive`

On overflow (> 10 turns): oldest turn compressed via `MigrationEngine.demote()` to `history_recent`.

Turn compression pipeline:

| Turn number range | Storage | Format |
|---|---|---|
| 1–10 | `history_active` (HOT) | Full `Turn` + `TypedHistoryEntry[]` |
| 11–30 | `history_recent` (WARM) | `CompressedTurn` (entities + intents + key phrases) |
| 31–40 | `history_recent` (WARM) | `SummarizedTurn` (single sentence ~100 chars) |
| 41+ | LOCAL COLD (SQLite) | FlatBuffer/JSON bytes in `st_history_archive` |

---

## 9. HOT section state: `TaskStateSection`

| Field | Type | Capacity | Lifetime |
|---|---|---|---|
| `entries` | `List[TaskStateEntry]` | max 20 | Until pruned |
| `last_updated_ms` | `int` | 1 | per mutation |

`TaskStateEntry` fields: `task_id, action, status: TaskStatus, dispatched_at_ms, completed_at_ms, depends_on[], progress_pct, pending_hil, hil_suspensions_count, presented_at_turn, pending_hil_data?`

Pruning rule: entries where `presented_at_turn > 0` AND `current_turn - presented_at_turn > _PRUNE_AFTER_TURNS=10` are **deleted** (not demoted). Non-presented tasks are never pruned.

`TaskStatus` states: `PENDING → DISPATCHED → RUNNING → COMPLETED / FAILED / CANCELLED`

**POC note:** `to_flatbuffer()` returns JSON bytes, not FlatBuffer.

---

## 10. HOT section state: `TaskArtifactsSection`

| Field | Type | Capacity | Eviction |
|---|---|---|---|
| `artifacts` | `List[TaskArtifactEntry]` | max 30 | Demotes → `artifacts_warm` 10 turns after `presented_at_turn > 0` |

`TaskArtifactEntry` fields: `artifact_id, task_id, artifact_type: ArtifactType, content, content_hash, created_at_ms, presented_at_turn`

**POC note:** `to_flatbuffer()` returns JSON bytes, not FlatBuffer.

---

## 11. HOT section state: `MetaSection`

| Field | Type | Mutated by |
|---|---|---|
| `session_identity` | `SessionIdentity` | start, restore |
| `session_lifecycle` | `SessionLifecycle` | lifecycle transitions |
| `memory_usage` | `MemoryUsage` | every SizeTracker update (synced on checkpoint) |
| `version_info` | `VersionInfo` | immutable after construction |
| `session_id` | `str` | start |
| `user_id` | `str?` | start |
| `privacy_band` | `PrivacyBand` | control section mutation |
| `turn_count` | `int` | every `push_turn` in history_active |

---

## 12. HOT section state: `ScoreboardSection`

| Field | Type | Capacity |
|---|---|---|
| `referents` | `List[Referent]` | bounded by 6KB |
| `questions` | `List[Question]` | QUD stack |
| `topics` | `List[Topic]` | topic stack |
| `salience` | `List[SalienceEntry]` | per-entity/topic |
| `commitments` | `List[Commitment]` | |
| `current_turn` | `int` | |
| `last_user_intent` | `str?` | |

---

## 13. HOT section state: `AffectiveNowSection`

| Field | Type | Notes |
|---|---|---|
| `current_emotion` | `str` | emotion label |
| `intensity` | `float` | 0.0–1.0 |
| `dimensions` | `EmotionDimensions` | valence[-1..+1], arousal[0..1], dominance[0..1] |
| `trajectory` | `EmotionTrajectory` | trend direction |
| `snapshots` | `List[EmotionSnapshot]` | last 5 |
| `empathy_needed` | `bool` | |
| `celebration_appropriate` | `bool` | |

`EmotionDimensions.quadrant` property: derived from valence + arousal.

---

## 14. HOT section state: `NarrativeActiveSection`

| Field | Type | Capacity |
|---|---|---|
| `primary_thread` | `ConversationThread` | 1 |
| `paused_threads` | `List[ConversationThread]` | max 5 |
| `narrative_arc` | `NarrativeArc` | 1 |
| `current_thread_id` | `str` | |
| `resumption_hint` | `str?` | |

---

## 15. HOT section state: `ClarificationsSection`

| Field | Type | Capacity |
|---|---|---|
| `pending` | `List[Clarification]` | max ~20 |
| `recently_resolved` | `List[Clarification]` | last 5 |
| `is_blocked` | `bool` | |
| `blocking_clarification_id` | `str?` | |

`can_evict=False` (alongside `control`, `meta`, `task_state`).

---

## 16. WARM section state: `BeliefsHistorySection`

| Field | Type | Capacity | Eviction |
|---|---|---|---|
| `archived_facts` | `List[ArchivedFact]` | max 100 | LRU score < 0.2 evicted to LOCAL COLD |
| `entity_fact_index` | `List[EntityFactIndex]` | | |
| `eviction_threshold` | `float` | 0.2 | configurable |

`ArchivedFact` wraps `Fact` + `original_turn, last_accessed_turn, access_count, demoted_at_ms, lru_score, is_stale`

LRU score formula:
```
score = max(0.0, (1 - min(1, turns_since_access * 0.1)) + min(0.5, access_count * 0.05))
```

---

## 17. WARM section state: `HistoryRecentSection`

| Field | Type | Capacity |
|---|---|---|
| `compressed_turns` | `List[CompressedTurn]` | max 20 (turns 11–30) |
| `summarized_turns` | `List[SummarizedTurn]` | max 10 (turns 31–40) |
| `session_summary` | `str?` | ~200 chars |

`CompressedTurn` fields: `turn_id, turn_number, entities[], intents[], key_phrases[], timestamp_ms, emotion, user_tokens, response_tokens, archived_to_local_cold, archive_id?`

`SummarizedTurn` fields: `turn_id, turn_number, summary` (~100 chars), `timestamp_ms, primary_intent, primary_entity`

---

## 18. WARM section state: `TelemetrySection`

| Field | Type | Notes |
|---|---|---|
| `token_data` | `TokenData` | total_input/output/cost tokens |
| `cost_data` | `CostData` | USD estimates by model |
| `latency_data` | `LatencyData` | per-operation P50/P95 |
| `error_data` | `ErrorData` | error counts by type |
| `turn_timings` | `List[TurnTiming]` | per-turn latency breakdown |
| `performance_summary` | `PerformanceSummary` | rolling window aggregate |

Eviction priority: 1 (first to evict — cheapest to lose).

---

## 19. WARM section state: `PersonaSection`

| Field | Type | Notes |
|---|---|---|
| `personality_profile` | `PersonalityProfile` | trait scores |
| `voice_preferences` | `VoicePreferences` | style, formality, length |
| `vocabulary_entries` | `List[VocabularyEntry]` | preferred terms, avoid list |
| `interaction_style` | `InteractionStyle` | response patterns |
| `calibration_confidence` | `float` | 0.0–1.0, how much persona has been calibrated |

Eviction priority: 5/10 (last to evict — most costly to lose).

---

## 20. WARM section state: `ArtifactsWarmSection`

| Field | Type | Capacity | Eviction |
|---|---|---|---|
| `artifacts` | `List[TaskArtifactEntry]` | max 50, LRU | Evicted to `st_artifacts_archive` when > 50 or over budget |

---

## 21. `EvictionEngine` tracking state

| Field | Type | Notes |
|---|---|---|
| `_eviction_count` | `int` | total evictions in current window |
| `_last_eviction_ms` | `int` | timestamp of last eviction |
| `_thrash_tracker` | `ThrashTracker` | counts migrations + evictions in 60s window |

---

## 22. `MigrationEngine` tracking state

| Field | Type | Notes |
|---|---|---|
| `_migration_count` | `int` | total demotions in current window |
| `_last_migration_ms` | `int` | timestamp of last migration |
| `_thrash_tracker` | `ThrashTracker` (shared) | same instance as EvictionEngine |

---

## 23. `ReconstructionSLA` tracking state

| Field | Type | Notes |
|---|---|---|
| `_local_cold_attempts` | `int` | total reconstruct attempts from LOCAL COLD |
| `_local_cold_breaches` | `int` | attempts that exceeded 50ms SLA |
| `_k0_attempts` | `int` | total K0 fallback attempts |
| `_k0_breaches` | `int` | attempts that exceeded 100ms SLA |
| `_last_reconstruction_ms` | `int` | latency of most recent reconstruction |

---

## 24. `DirectWriterAdapter` state

| Field | Type | Init | Mutated by | Thread-safe via |
|---|---|---|---|---|
| `_manager` | `SessionStateManager?` | `None` | `bind_manager()` (once) | set once before use |
| `_guard` | `MutationGuard?` | `None` | `bind_manager()` (once) | set once before use |
| `_writer_id` | `str` | constructor | immutable | n/a |
| `_lock` | `threading.RLock` | new | n/a | n/a |
| `_is_connected` | `bool` | `False` | `bind_manager()` | `_lock` |
| `_mutation_count` | `int` | 0 | each `request_mutation()` | `_lock` |
| `_rejection_count` | `int` | 0 | each rejected preflight | `_lock` |

---

## 25. `StandaloneLifecycle` state

| Field | Type | Init | Mutated by | Thread-safe via |
|---|---|---|---|---|
| `_state` | `LifecycleState` | `CREATED` | `start()`, `stop()` | `_lock` |
| `_manager` | `SessionStateManager?` | `None` | `bind_manager()` (once) | set once |
| `_lock` | `threading.RLock` | new | n/a | n/a |
| `_timer` | `threading.Timer?` | `None` | `_start_periodic_checkpoint()`, `stop()` | `_lock` |
| `_checkpoint_count` | `int` | 0 | each `checkpoint()` | `_lock` |
| `_last_checkpoint_ms` | `int` | 0 | each `checkpoint()` | `_lock` |
| `_started_at_ms` | `int` | 0 | `start()` | `_lock` |

`LifecycleState` transitions:
```
CREATED → STARTING → RUNNING → STOPPING → STOPPED
                                         └→ ERROR
```

---

## 26. `LocalEventAdapter` state

| Field | Type | Init | Thread-safe via |
|---|---|---|---|
| `_handlers` | `Dict[str, Dict[str, Callable]]` | empty | `_lock` |
| `_queue` | `queue.Queue` | new | `queue.Queue` internal lock |
| `_dispatch_thread` | `threading.Thread` | new (daemon) | n/a |
| `_running` | `bool` | `False` | `_lock` |
| `_lock` | `threading.RLock` | new | n/a |
| `_captured` | `List[Tuple]` | `[]` (if `capture_mode=True`) | `_lock` |
| `_event_count` | `int` | 0 | `_lock` |
| `_drop_count` | `int` | 0 | `_lock` (incremented if queue full) |

Thread name: `"LocalEventAdapter-Dispatch"`.

---

## 27. `LocalColdArchive` state

| Field | Type | Notes |
|---|---|---|
| `_db_path` | `str` | expanded from `~/.familyos/k1/sessionstate.db` |
| `_conn` | `sqlite3.Connection` | WAL, `check_same_thread=False` |
| `_archive_count` | `int` | total archives written |
| `_restore_count` | `int` | total restores read |
| `_last_restore_ms` | `int` | latency of most recent restore |

Tables are created on first use via `_init_db()` if not present.

---

## 28. `SectionDataAdapter` state

| Field | Type | Notes |
|---|---|---|
| `_hot` | `HotTier` | reference, not owned |
| `_warm` | `WarmTier` | reference, not owned |
| `_overflow` | `Dict[str, List[MigrationItem]]` | buffered items awaiting `accept_demoted()` call |

`_overflow` accumulates items when `add_items(section, items)` is called before the target
section is ready to accept them. If `accept_demoted()` never succeeds, items remain here
indefinitely (see OPEN_ISSUES.md — SS-08).
