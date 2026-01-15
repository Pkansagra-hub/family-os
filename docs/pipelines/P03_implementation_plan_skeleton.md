# P03 Implementation Plan — Skeleton (Milestones → Epics → Issues)

> **Source inputs**: `P03_consolidation_dossier_v2.md`, `P03_envelope_fields_discovery.md`, `P03_consolidation_dossier_v2_notes.md`
> **Purpose**: Planning scaffold only (no detailed ticket text).

## Totals (planning-level)

- **Milestones**: 9 (M0-M8 + Research Appendix)
- **Epics**: 28
- **Issues**: ~175 (order-of-magnitude; will change when converted into real tickets)

---

## Milestone 0 — Governance + Decisions + Contract baseline

> **Scope note (avoid drift)**:
>
> - Milestone 0 is the **authority-setting milestone**: it establishes canonical names (pipeline IDs, topic names, table names, capability names) and registers them in governance before any production code lands.
> - **If a name is not in the dossier**, it must be resolved explicitly in **Issue 0.1.2** (decision recorded) *before* creating contract files that depend on it.
> - Source-of-truth inputs for this milestone:
>   - Dossier canonical naming + topics + stage mapping: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D/E/F/G)
>   - Governance master registry (must be kept in sync): `governance/k0/k0_architecture_master.md`
>   - Topic registry used by scanners/humans: `k0/pipelines/whiteboard.md`
>   - Contract artifact locations (must match master registry rows):
>     - Pipelines: `k0/contracts/pipelines/`
>     - Modules: `k0/contracts/modules/`
>     - Schemas: `k0/contracts/schemas/`
>     - JSON schema: `k0/contracts/jsonschema/`
>     - Capabilities: `k0/contracts/capabilities/`
>   - ADR locations: `docs/architecture/decisions-K0/`
>

### Epic 0.1 — Governance sync + drift resolution

#### Issue 0.1.1 — Run governance sync and capture baseline

- **Goal**: Establish current governance sync baseline (pre-P03 contracts/modules) and lock in the “starting point” for drift.
- **Deliverables**:

  - Attach `python -m governance.k0.scripts.sync --report` output to ticket.
  - Record repo branch + commit SHA for baseline.
- **Acceptance**:

  - Sync report shows `OVERALL SYNCED` (or drift is explicitly explained + linked to planned P03 work).
- **References**:

  - Tool: `governance/k0/scripts/sync.py`
  - Master registry: `governance/k0/k0_architecture_master.md`

#### Issue 0.1.2 — Reconcile P03 dossier vs K0 master registry (before writing new contracts)

- **Goal**: Identify and resolve naming/registry mismatches so P03 contracts/ADRs don’t land into a moving target.
- **Scope**:

  - Pipeline ID alignment: dossier uses `P03_CONSOLIDATE` / `P03_INCREMENTAL` (Appendix E) while K0 code/tests already assume `P03_CONSOLIDATION` in multiple runtime schema + fabric registry examples (and the governance pipeline registry currently uses `P03` as the short ID in Part 2.1).
  - Topic name alignment: use `p03.consolidation.triggered.v1` as the canonical scheduler entry topic (matches existing K0 topic naming patterns like `system.backpressure.triggered.v1` and the current registry/whiteboard), and update dossier references accordingly.
  - Storage naming: P03 should consume/update `st_hipp_events` (and write truth-layer tables like `st_epi`, `st_sem`, `st_kg_dom`, `st_kg_edges`, …); the master’s current P03 dependency row (Part 2.2) still references `st_hipp_store` and must be corrected.
  - Contract paths: the master event registry currently references `contracts/schemas/...` in some rows, but this repo’s canonical event schema location is `k0/contracts/schemas/` (root `contracts/schemas/` is empty).
- **Deliverables**:

  - A short “diff list” (table) in the ticket with:
    - *Current registry value* → *dossier canonical value* → *decision (keep/change)*
  - Approved canonical list for: pipeline IDs, event topics, table names, capability names.
- **Acceptance**:

  - No unresolved naming conflicts remain for: P03 pipeline contract(s), P03 event topics, and new storage tables.
- **References**:

  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D/E/F/G)
  - Master registry: `governance/k0/k0_architecture_master.md` (Part 2/4/5/6/11/13)
  - Topic registry source: `k0/pipelines/whiteboard.md`

#### Issue 0.1.3 — Register P03 (Planning) artifacts across master registries

- **Goal**: Bring K0 governance registries to a P03-ready *Planning* state so implementation can proceed without governance drift.
- **Deliverables (update master registry tables)**:

  - **Part 2 (Pipelines)**: Confirm P03 row, update “Modules Used” placeholder plan, scheduler usage, dossier link, and dependency list.
  - **Part 4 (Events)**: Add all canonical P03 topics (Appendix E) + P06 integration topics (`p06.gap.resolved.v1`, `p06.anchor.updated.v1`) as Planning.
  - **Part 5 (Contracts)**: Add rows for P03 pipeline contract(s), module contract set, capability contract file, event schema files, config schema.
  - **Part 6 (Storage)**: Add Planning rows for P03 truth-layer tables that do not yet exist in DB (if missing), plus P03 audit/learning tables (e.g., `st_consolidation_audit`, `st_learning_queue`, `st_anchors`, `st_anchor_observations`).
  - **Part 7 (Syscalls/Capabilities)**: Ensure required storage capabilities are enumerated for P03 modules/pipeline.
  - **Part 9 (Scheduler)**: Register P03 triggers (INTERVAL/THRESHOLD/MANUAL; Appendix D.5).
  - **Part 10 (Observability)**: Register P03 metrics names/labels (Appendix D.9 + Appendix G.5).
  - **Part 11 (ADRs)**: Add new P03 ADR entries (see Epic 0.2) and cross-links.
  - **Part 13 (Configuration)**: Register all `p03.*` config keys (Appendix E.7 + Appendix F).
- **Acceptance**:

  - `governance/k0/k0_architecture_master.md` contains Planning-complete entries for P03 across parts listed above.
  - Running `python -m governance.k0.scripts.sync --report` after adding P03 contract files (Epic 0.2) remains `SYNCED`.

#### Issue 0.1.4 — Update K0 pipeline whiteboard topic registry for P03

- **Goal**: Ensure the event topic registry used by scanners and humans includes P03 topics.
- **Deliverables**:

  - Update `k0/pipelines/whiteboard.md` to include canonical P03 topics and their producers/consumers.
- **Acceptance**:

  - P03 topics appear in `k0/pipelines/whiteboard.md` event bus namespace tables.
  - Event scanner (`governance/k0/scripts/event_scanner.py`) picks up P03 topics once contract YAMLs exist.

### Epic 0.2 — ADR + contract set for P03

#### Issue 0.2.1 — ADR: P03 Consolidation pipeline architecture (entry/exit topics, DAG shape)

- **Goal**: Establish the authoritative P03 pipeline architecture decision aligned with K0 governance + dossier.
- **Deliverables**:

  - New pipeline ADR file under `docs/architecture/decisions-K0/pipelines/`:
    - `P03-consolidation-architecture.md` (naming aligned to `P02-write-pipeline-architecture.md` style)
  - ADR must explicitly define:
    - pipeline variants (batch vs incremental)
    - entry/exit topics (Appendix E.2)
    - stage mapping (Appendix D.3)
    - concurrency model + single-writer-per-space strategy
    - dependency contracts with P02/P05/P06/P08
- **Acceptance**:

  - ADR indexed in `governance/k0/k0_architecture_master.md` Part 11.1
  - ADR references: dossier Appendix D + Appendix E canonical names

#### Issue 0.2.2 — ADR: R0–R8 state machine + idempotency + retry matrix

- **Goal**: Lock the operational semantics: phase states, retries, timeouts, idempotency keys.
- **Deliverables**:

  - ADR (pipeline or core) that adopts Appendix G as normative:
    - INIT/PROC/SKIP/FAIL/DONE states
    - idempotency keys per phase
    - retry matrix + DLQ conditions
- **Acceptance**:

  - ADR references Appendix G and is cross-linked from P03 pipeline ADR.

#### Issue 0.2.3 — ADR: Capability/security model for P03 (storage + fabric)

- **Goal**: Define capability boundaries for P03 modules and fabric invocation policies.
- **Deliverables**:

  - ADR that specifies:
    - required capabilities per stage/module (Appendix D.2.2)
    - fabric invocation policy (`INTERSECT_CALLER` etc; Appendix D.8.3)
    - RLS posture for learning tables (Appendix I + Milestone 2.3)
- **Acceptance**:

  - ADR references existing K0 decisions (e.g., K004 capability mesh) and is indexed.

#### Issue 0.2.4 — ADR: Closed-loop feedback ingestion + safety guardrails

- **Goal**: Define how P03 consumes feedback signals safely (shadow mode, rollback, budgets).
- **Deliverables**:

  - ADR aligned with existing feedback subsystem ADR:
    - `docs/architecture/decisions-K0/k020-feedback-signals-subsystem.md`
  - Explicit constraints:
    - learning compute budget (<5% of cycle time)
    - quarantine/velocity anomaly rules
    - rollback triggers and canary schedule
- **Acceptance**:

  - ADR indexed; includes linkages to P06 topics and P03 parameter store tables.

#### Issue 0.2.5 — Contracts: P03 pipeline contract(s) (YAML)

- **Goal**: Add the canonical pipeline contract(s) under `k0/contracts/pipelines/`.
- **Deliverables**:

  - `k0/contracts/pipelines/p03_consolidation.v1.yaml` (batch mode)
  - (Optional / Planning) `k0/contracts/pipelines/p03_incremental.v1.yaml`
  - Each contract must include:
    - `pipeline_id`, `entry_topic`, `exit_topic`, `concurrency`, `max_queue_depth`
    - `required_capabilities` list (Appendix D.2.2)
    - stage DAG consistent with Appendix D.3
- **Acceptance**:

  - Pipeline contract(s) registered in master Part 5.2.
  - Governance sync remains `SYNCED` after adding contract(s) and updating master.

#### Issue 0.2.6 — Contracts: P03 module contracts (YAML) for every stage module

- **Goal**: Create module contract YAMLs for the full P03 stage set.
- **Deliverables**:

  - New module contract files under `k0/contracts/modules/` for each P03 stage module, e.g.:
    - `consolidation.batch_selector.v1.yaml`
    - `consolidation.importance_scorer.v1.yaml`
    - `consolidation.hebbian_learner.v1.yaml`
    - `consolidation.episodic_clusterer.v1.yaml`
    - `consolidation.episode_builder.v1.yaml`
    - `consolidation.simhash_deduplicator.v1.yaml`
    - `consolidation.decay_scorer.v1.yaml`
    - `consolidation.prune_decider.v1.yaml`
    - `consolidation.entity_extractor.v1.yaml`
    - `consolidation.relationship_builder.v1.yaml`
    - `consolidation.causal_inference.v1.yaml`
    - `consolidation.counterfactual.v1.yaml`
    - `consolidation.forward_simulator.v1.yaml`
    - `consolidation.insight_generator.v1.yaml`
    - `consolidation.motor_rehearsal.v1.yaml` (TDL-HCO)
    - `consolidation.status_updater.v1.yaml`
    - `consolidation.memory_writer.v1.yaml`
    - (If separate) `consolidation.gap_detector.v1.yaml`
  - Each module contract must declare:
    - `module_id`, `version`, `latency_budget_ms`, `idempotent`, `side_effects`
    - `input_event_types` / `output_event_types` (where applicable)
    - required capabilities
    - failure modes and retry policy hooks (Appendix D.10)
- **Acceptance**:

  - All module contracts registered in master Part 5.1.
  - No orphan modules: every planned module has a contract file and a registry row.

#### Issue 0.2.7 — Contracts: P03 capabilities (fabric) registry

- **Goal**: Define canonical fabric capabilities for P03 (Appendix E.5) in `k0/contracts/capabilities/`.
- **Deliverables**:

  - Add a new capability contract file OR extend `k0/contracts/capabilities/core.v1.yaml` (decision recorded in ADR):
    - `k0/contracts/capabilities/consolidation.v1.yaml` (preferred for separation)
  - Include: `score_importance`, `cluster_episodes`, `detect_duplicates`, `extract_entities`, etc.
- **Acceptance**:

  - Capability set referenced by pipeline and module contracts.
  - Capability names match the canonical registry (Appendix E.5).

#### Issue 0.2.8 — Contracts: P03 event topic schemas (JSON)

- **Goal**: Provide machine-readable schemas for all P03 topics (not just two).
- **Deliverables**:

  - Add schema files under `k0/contracts/schemas/` for (at minimum):
    - `p03_consolidation_triggered.json`
    - `p03_consolidation_complete.json`
    - `p03_phase_complete.json`
    - `p03_episode_formed.json`
    - `p03_pattern_discovered.json`
    - `p03_gap_detected.json`
    - `p03_kg_updated.json`
    - `p03_insight_generated.json`
    - (If emitted) truth/audit events: `p03_truth_reinforced.json`, `p03_truth_created.json`, `p03_truth_evolved.json`, `p03_memory_pruned.json`
  - Update master Part 5.3 to register each schema.
  - Ensure correlation and tracing fields are consistent with envelope conventions.
- **Acceptance**:

  - All P03 topics in master Part 4.1 have a schema path (or an explicit “schema TBD” with a tracked follow-up).

#### Issue 0.2.9 — Contracts: P03 config schema + threshold validation contract

- **Goal**: Make threshold/config governance enforceable (Appendix F validation rules).
- **Deliverables**:

  - JSON schema under `k0/contracts/jsonschema/` for P03 config surface (naming to be finalized):
    - `p03.config.schema.json` (includes keys from Appendix E.7 and Appendix F)
  - Add example config(s) under `k0/contracts/jsonschema/examples/`.
- **Acceptance**:

  - Threshold ordering rules are expressible and validated in tests (even if enforcement is initially “validate at startup”).

#### Issue 0.2.10 — Contract checksum + registry hygiene

- **Goal**: Ensure contract changes follow the repo’s contract hygiene workflow.
- **Deliverables**:

  - Update contract registries in `governance/k0/k0_architecture_master.md` (Part 5) for every new contract artifact.
  - Update `k0/contracts/VERSION` checksums if required by the automation.
  - Add/extend contract validation tests (existing Ward suites) to cover new schemas.
- **Acceptance**:

  - Contract lint/validation passes and VERSION is updated consistently.

---

## Milestone 1 — Core pipeline skeleton + envelope + sequential runner

> **Scope note (avoid drift)**:
>
> - Milestone 1 implements the **core execution semantics and envelope state**. The sequential runner must remain aligned to the dossier’s normative state machine.
> - Canonical sources for Milestone 1:
>   - Envelope fields and per-phase state: `docs/pipelines/P03_envelope_fields_discovery.md` (Part II, Sections 14–21)
>   - Phase order/skip/retry/idempotency: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.0 + Appendix G)
>   - Envelope execution notes (immutability/lazy embedding): `docs/pipelines/P03_consolidation_dossier_v2_notes.md`
> - When repository code disagrees with dossier semantics, **dossier wins** unless an explicit ADR/Issue decision is recorded (Milestone 0).
>

### Epic 1.1 — Envelope model (from envelope discovery)

#### Issue 1.1.1 — Confirm envelope design + choose implementation pattern (dataclass vs Pydantic)

- **Goal**: Translate the envelope design spec into an implementation-ready blueprint *without drifting* from dossier/discovery.
- **Scope / Decisions**:
  - Confirm that **P03BatchEnvelope is internal pipeline state**, distinct from the kernel event envelope (`k0/contracts/jsonschema/envelope.schema.json`).
  - Decide whether the implementation is:
    - **dataclasses** (closest to `P03_envelope_fields_discovery.md`), or
    - **Pydantic BaseModel** (closer to existing style like `k0/feedback/envelope.py`) while preserving immutability requirements.
  - Decide module location (expected to be new):
    - Preferred: `k0/runtime/p03/` or `k0/pipelines/p03/` for pipeline-owned state, OR
    - `k0/modules/core/` if treated as shared kernel data types.
- **Deliverables**:
  - A short decision note in the ticket:
    - chosen representation (dataclass vs Pydantic)
    - chosen file layout (paths + module names)
    - rationale: immutability, JSON serialization, performance (lazy embeddings), testability
- **Acceptance**:
  - Implementation plan explicitly maps to the discovery spec sections and lists which classes will exist and where.
- **References**:
  - Design spec: `docs/pipelines/P03_envelope_fields_discovery.md` (Part II, Sections 14–21)
  - Dossier notes: `docs/pipelines/P03_consolidation_dossier_v2_notes.md` (Section “Envelope architecture / execution model”)
  - Kernel envelope schema (not P03BatchEnvelope): `k0/contracts/jsonschema/envelope.schema.json`
  - Existing Pydantic envelope pattern: `k0/feedback/envelope.py`

#### Issue 1.1.2 — Implement immutable cycle context (P03CycleContext)

- **Goal**: Create the immutable “batch header” required by the dossier: set once in R0 and never mutated.
- **Deliverables**:
  - Implement `P03CycleContext` with:
    - `cycle_id` (ULID)
    - `batch_id` derived as `SHA256(sorted(event_ids))[:16]`
    - `tenant_id`, `space_id`, `trace_id`
    - trigger context (`trigger_type`, `trigger_reason`, `triggered_at`)
    - scheduler context (`scheduler_token`, `qos_band`, `priority`, `deadline_ms`)
    - batch metadata (`batch_size`, immutable `event_ids`, `pending_before`)
  - Provide a factory `create(...)` matching the design spec.
- **Acceptance**:
  - `P03CycleContext` is enforced immutable after construction (frozen dataclass or Pydantic frozen model).
  - `batch_id` is stable/deterministic for the same set of event IDs.
- **References**:
  - Spec: `docs/pipelines/P03_envelope_fields_discovery.md` (Sections 1.1–1.4, 15.2)
  - Dossier notes: `docs/pipelines/P03_consolidation_dossier_v2_notes.md` (immutability after R0)

#### Issue 1.1.3 — Implement per-event state (P03EventState) + decision enums

- **Goal**: Provide a single per-event state object that accumulates enrichment from R1–R6 and supports idempotent retries.
- **Deliverables**:
  - Implement:
    - `ReconciliationAction` enum (PENDING/REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT/PRUNE/SKIP)
    - `P03EventState` with:
      - identification (`event_id`, `hipp_event_id`)
      - content + P02-precomputed metadata (including `embedding_id`)
      - **lazy embedding materialization**: store vector only when needed
      - R1 importance fields + factor breakdown
      - R2 cluster assignment fields
      - R3 reconciliation decision fields + dedup/decay
      - R6 optimistic locking fields (`expected_version`, `version_conflict`)
  - Provide helper methods (or equivalent) to:
    - `materialize_embedding(...)`
    - `set_importance(...)`
    - `assign_cluster(...)`
    - `set_reconciliation(...)`
- **Acceptance**:
  - Default construction does **not** require loading embeddings (IDs only).
  - Event state updates are by `event_id` (safe for merges).
- **References**:
  - Spec: `docs/pipelines/P03_envelope_fields_discovery.md` (Sections 2.x, 16.1)
  - Dossier notes: `docs/pipelines/P03_consolidation_dossier_v2_notes.md` (lazy embedding loading)

#### Issue 1.1.4 — Implement phase output container (P03PhaseOutputs) and core aggregate types

- **Goal**: Provide a structured place for batch-level aggregates per phase (clusters, KG outputs, dream outputs, reconciliation summary).
- **Deliverables**:
  - Implement `P03PhaseOutputs` and the minimal nested types required for downstream phases:
    - `EpisodeCluster`, `DedupMerge`
    - `KGEntity`, `KGEntityUpdate`, `KGEdge`, `KGEdgeUpdate`, `CausalEdge`, `GapCandidate`
    - `CounterfactualScenario`, `Insight`, `RoutineOptimization`, `ProspectiveMemory`
  - Ensure the container can be populated once per phase and supports “skip R5”.
- **Acceptance**:
  - All fields referenced by the propagation table exist and have safe defaults.
- **References**:
  - Spec: `docs/pipelines/P03_envelope_fields_discovery.md` (Sections 3.x, 17.x, 20.2)

#### Issue 1.1.5 — Implement staged writes container (P03StagedWrites) + deterministic commit ordering

- **Goal**: Model the R6→R7 boundary: R1–R6 accumulate deferred writes; R7 commits them atomically in dependency order.
- **Deliverables**:
  - Implement:
    - `WriteOperation` enum
    - `StagedWrite` with idempotency key rules
    - `StagedOutboxEvent`
    - `P03StagedWrites` with:
      - per-layer write lists (st_epi/st_sem/st_procedural/st_social/st_prospective/st_kg_dom/st_kg_edges/st_vec)
      - source updates list (`st_hipp_events_updates`)
      - learning queue list (`st_learning_queue_writes`)
      - outbox events list
      - helpers: `add_write(...)`, `add_outbox_event(...)`, `total_writes()`
      - deterministic `get_all_writes_ordered()` consistent with spec
- **Acceptance**:
  - Ordering is deterministic and matches the dependency order described in the spec.
  - Idempotency keys are phase-scoped and stable (sufficient for retry dedup).
- **References**:
  - Spec: `docs/pipelines/P03_envelope_fields_discovery.md` (Section 18.1)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (R6 staging + R7 commit semantics; see “R6 — Staging Table Updates” and tracing span tree)

#### Issue 1.1.6 — Implement observability payload carried in the envelope

- **Goal**: Provide structured tracing/log context and error collection as first-class envelope state.
- **Deliverables**:
  - Implement:
    - `P03ObservabilityContext` with phase timing maps + metric aggregation helpers
    - `P03Error` record (phase/stage/error_type/message/event_id/recoverable/timestamp)
  - Ensure the envelope provides `mark_phase_start(...)` / `mark_phase_complete(...)` (or equivalent) and captures phase durations.
- **Acceptance**:
  - Every phase transition can be traced and timed using envelope state alone.
- **References**:
  - Spec: `docs/pipelines/P03_envelope_fields_discovery.md` (Section 19.x)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Distributed tracing span hierarchy)

#### Issue 1.1.7 — Implement serialization for checkpointing/retries (summary + full)

- **Goal**: Make envelope state safe to persist (DLQ/checkpoints/debug snapshots) without forcing huge payloads.
- **Deliverables**:
  - Implement `P03EnvelopeSerializer` (or equivalent) that provides:
    - `to_dict(...)` (summary: counts, ids, phase, timings)
    - `to_full_dict(...)` (full per-event state for recovery/debug)
    - (If needed) `from_dict(...)` / `from_full_dict(...)` for restore
  - Explicitly define size policy:
    - embeddings are IDs by default
    - full vectors never included unless explicitly requested
- **Acceptance**:
  - Roundtrip works for summary and full versions.
  - Summary serialization does not include per-event raw bodies by default.
- **References**:
  - Spec: `docs/pipelines/P03_envelope_fields_discovery.md` (Section 21.2)

#### Issue 1.1.8 — Add envelope model tests + fixtures

- **Goal**: Ensure envelope invariants are enforced and regressions are caught early.
- **Deliverables**:
  - Add tests under `tests/k0/pipelines/` (new file) covering:
    - `P03CycleContext.create()` determinism (`batch_id` stable across permutations)
    - immutability of `P03CycleContext`
    - `P03StagedWrites.get_all_writes_ordered()` ordering
    - serializer roundtrip (`to_full_dict` → restore)
    - lazy embedding: default event state keeps `embedding_id` without materializing vectors
- **Acceptance**:
  - Tests pass in CI and are deterministic.
- **References**:
  - Existing envelope tests/patterns (do not copy semantics, copy style):
    - `tests/k0/gate/test_full_envelope_signature.py`
    - `k0/scripts/test_envelope_samples.py`

### Epic 1.2 — Sequential phase runner + checkpoints

#### Issue 1.2.1 — Confirm sequential-runner contract (vs generic DAG) + map to Appendix G

- **Goal**: Lock the semantics of “sequential R0→R8” execution and retries so the runner implementation does not drift from the dossier’s state machine.
- **Scope / Decisions**:
  - Runner must follow **Appendix G** phase definitions (states, idempotency keys, retryability, skip conditions) and the **Phase Transition Rules** shown in Part II.
  - Decide how P03 will be hosted in K0:
    - (A) a dedicated `P03` pipeline class implementing `PipelineProtocol`, which internally calls a sequential runner, OR
    - (B) a declarative pipeline spec executed by the generic `k0/runtime/pipeline_runner.py` (note: current runner is parallel-by-level; P03 requires strict sequential semantics).
  - Explicitly define what constitutes:
    - “cycle” (cycle_id / cycle_ulid)
    - “checkpoint” (phase boundary snapshot + offset/watermark data)
    - “resume from phase” (allowed phases per abort matrix)
- **Deliverables**:
  - A short “runner contract note” in the ticket that lists:
    - phase order + allowed transitions (including skip transitions)
    - phase states: INIT/PROC/SKIP/FAIL/DONE
    - resume matrix (which phase can resume from where)
    - which persistence surfaces are used for offsets/status (Phase bookkeeping vs offset/watermark)
- **Acceptance**:
  - Ticket includes a table mapping each phase R0–R8 to:
    - inputs/outputs, idempotency key, retry policy, skip condition, checkpoint boundary.
- **References**:
  - Dossier phase transitions + abort/recovery: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.0 “Phase Transition Rules”, “Abort & Recovery Semantics”)
  - Normative state machine spec: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G: G.1–G.5)
  - Existing K0 runner (parallel-by-level, not sequential): `k0/runtime/pipeline_runner.py`
  - Pipeline host interface: `k0/pipelines/protocol.py`

#### Issue 1.2.2 — Define the R0–R8 phase interface (typed inputs/outputs + hooks)

- **Goal**: Provide a single, testable interface for phases so the sequential runner can execute them uniformly and capture bookkeeping/observability consistently.
- **Deliverables**:
  - Define:
    - `P03PhaseId` enum (R0…R8)
    - `P03PhaseStatus` enum (INIT/PROC/SKIP/FAIL/DONE)
    - `P03PhaseResult` record (status, outputs summary, error info, durations, skip_reason)
    - A `P03Phase` protocol/interface with something equivalent to:
      - `phase_id: P03PhaseId`
      - `async run(envelope, ctx) -> P03PhaseResult`
      - `should_skip(envelope, ctx) -> (bool, reason)`
      - `idempotency_key(envelope) -> str`
  - Define what the runner passes as “ctx” (at minimum: syscalls, fabric, logger, QoS context, config).
- **Acceptance**:
  - Interface supports:
    - deterministic idempotency keys per phase (Appendix G)
    - skip decision with explicit reason
    - emitting consistent observability events per phase.
- **References**:
  - Appendix G per-phase tables: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.2)
  - Envelope model that the phases operate on: `docs/pipelines/P03_envelope_fields_discovery.md` (Per-phase outputs, observability fields)
  - Host pipeline interface + context: `k0/pipelines/protocol.py`

#### Issue 1.2.3 — Implement the sequential runner core (R0–R8 orchestration)

- **Goal**: Implement the engine that runs phases strictly in order, applies transitions/skip rules, and records per-phase results.
- **Deliverables**:
  - Implement `P03SequentialRunner` (name/location decided in Issue 1.1.1) that:
    - takes a `P03BatchEnvelope` (from Epic 1.1)
    - executes phases in order with a loop:
      - mark phase start
      - evaluate skip policy
      - run phase
      - validate outputs and update envelope
      - checkpoint boundary (hook)
      - decide next phase via transition rules
    - supports “resume from phase” entrypoint: `run_from(phase_id=...)`.
  - Explicitly *do not* reuse the generic DAG runner’s parallel grouping semantics for P03.
- **Acceptance**:
  - Runner enforces legal transitions (reject illegal jumps).
  - Runner records a phase timeline sufficient for later metrics emission.
- **References**:
  - Transition rules example: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.0 “Phase Transition Rules”)
  - Normative phase contracts: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G)
  - Generic DAG runner baseline (contrast): `k0/runtime/pipeline_runner.py`

#### Issue 1.2.4 — Phase transition bookkeeping + observability events (make state machine visible)

- **Goal**: Ensure every phase transition (including skips and aborts) is observable from logs/metrics and from envelope state.
- **Deliverables**:
  - In the runner, emit structured log events per phase:
    - `phase_start`, `phase_skip`, `phase_complete`, `phase_fail`
    - include: cycle_id, batch_id, space_id, phase_id, status, duration_ms, skip_reason, retry_count (if applicable)
  - Update the envelope’s observability context to store:
    - phase statuses, start/end timestamps, durations, error summaries.
  - Define a minimal “phase completion” summary suitable for:
    - outbox emission (R8)
    - audit persistence (Milestone 2/3)
- **Acceptance**:
  - Given an envelope snapshot (summary serialization), an operator can answer:
    - which phase last ran, whether it was skipped, and why.
- **References**:
  - Dossier metrics per phase: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.5)
  - Dossier tracing guidance: `docs/pipelines/P03_consolidation_dossier_v2.md` (Part III “Distributed Tracing”)
  - Envelope observability fields: `docs/pipelines/P03_envelope_fields_discovery.md` (Observability fields section)

#### Issue 1.2.5 — Define checkpoint + resume contract (envelope snapshot + persistence hooks)

- **Goal**: Create a runner-level checkpointing surface that can be wired to DB offsets/watermarks and used for recovery.
- **Deliverables**:
  - Define a `P03Checkpoint` record containing at minimum:
    - cycle_id, batch_id, phase_id, phase_status, created_at
    - envelope summary (small) and/or full snapshot (optional)
    - offset/watermark fields needed to resume (e.g., last processed wal_pos / event_id)
  - Define a `CheckpointStore` interface with `save(checkpoint)` / `load_latest(space_id, ...)`.
  - Add runner hooks:
    - `on_checkpoint(checkpoint)` (called at phase boundaries)
    - `on_resume(checkpoint)` (called when resuming)
  - Define how offsets are represented for P03:
    - subscriber_id = pipeline id
    - topic = entry topic
    - offset = wal_pos / last processed position
- **Acceptance**:
  - Checkpoint contract is compatible with K0’s existing offset storage patterns (even if the concrete P03 checkpoint persistence is implemented in later milestones).
- **References**:
  - Dossier offset + resume intent: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.9.2 “Pipeline Offset Updates”)
  - Dossier offset/watermark tables: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.14)
  - Existing offset storage implementation: `k0/storage/offsets.py`
  - UnitOfWork offset upsert surface: `k0/uow/unit_of_work.py` (`upsert_offset`)

#### Issue 1.2.6 — Implement offset/watermark integration path (no-op safe until Milestone 2)

- **Goal**: Wire the sequential runner to the offset persistence surface in a way that is safe even before full P03 ingestion is implemented.
- **Deliverables**:
  - Implement (or define) the runner’s “ack” behavior:
    - when a cycle completes successfully (R8 DONE), persist offset for the P03 subscriber.
    - when a cycle aborts with a resumable phase, persist checkpoint but do not advance offset.
  - Ensure the integration works both:
    - inside a `UnitOfWork` (preferred for atomicity when R7 writes are introduced), and
    - outside UoW (read-only phases).
- **Acceptance**:
  - Offset writes are never performed for partial/incomplete cycles.
  - Offset updates are idempotent for the same cycle (safe for retries).
- **References**:
  - OffsetStore: `k0/storage/offsets.py`
  - UnitOfWork: `k0/uow/unit_of_work.py`
  - Pipeline protocol idempotency patterns: `k0/pipelines/protocol.py`

#### Issue 1.2.7 — Deterministic cycle seeding + skip rule encoding (R5 optional; R2→R6 fast-path)

- **Goal**: Make all “randomized” or heuristic behavior deterministic per cycle, and ensure skip rules are implemented exactly and are observable.
- **Deliverables**:
  - Define a deterministic seed derivation function using `cycle_id` (ULID) (and optionally `batch_id`) and document it in code comments.
  - Ensure phases that use randomness (e.g., sampling, exploratory search) receive the seeded RNG from the runner.
  - Implement skip rules as first-class policy checks:
    - R5 skip-on-backlog (with config thresholds)
    - optional “minimal work” fast-path transition: R2 → R6 (skipping R3–R5) per transition rules
  - Record skip decisions in envelope observability.
- **Acceptance**:
  - Two runs with the same `cycle_id` and same inputs must produce identical skip decisions and identical seeded-random choices.
  - Skip reasons are always populated when a phase is skipped.
- **References**:
  - Transition and skip rules: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.0 “Phase Transition Rules” and Appendix G.1)
  - R5 skip condition and fields: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.2, R5 table)
  - Envelope discovery (skip_reason field included in R5Output): `docs/pipelines/P03_envelope_fields_discovery.md` (Per-phase outputs)

#### Issue 1.2.8 — Add sequential runner tests (transitions, resume, deterministic seeding, skip visibility)

- **Goal**: Prove the runner semantics match Appendix G and remain stable under refactors.
- **Deliverables**:
  - Add tests under `tests/k0/pipelines/` (new file) covering:
    - legal transition enforcement (including R2→R6 and optional R5)
    - skip behavior: R5 skipped emits status=SKIP and stores skip_reason
    - deterministic seeding: same cycle_id yields same RNG output sequence
    - checkpoint hooks called at phase boundaries
    - resume: given a checkpoint at phase X, runner starts at X and does not re-run earlier phases
- **Acceptance**:
  - Tests are deterministic and do not require real DB/network services (use small stub phases; avoid mocking storage except at the boundary).
- **References**:
  - Appendix G: `docs/pipelines/P03_consolidation_dossier_v2.md`
  - K0 pipeline protocol: `k0/pipelines/protocol.py`

### Epic 1.3 — Scheduler + concurrency guard

#### Issue 1.3.1 — Implement P03 trigger specs (INTERVAL/THRESHOLD/MANUAL) without schema drift

- **Goal**: Configure P03’s declarative triggers exactly as specified in the dossier (Appendix D.5), while using the *actual* K0 trigger schema so registration succeeds.
- **Deliverables**:
  - Define P03 triggers in the P03 pipeline contract YAML (see Epic 0.2.5):
    - INTERVAL trigger for periodic consolidation
    - THRESHOLD trigger on `st_hipp_events` pending condition
    - MANUAL trigger for admin/debug on-demand runs
  - Ensure the YAML fields match K0’s `TriggerSpec`:
    - `type: interval|threshold|manual` (lowercase)
    - For threshold: `table`, `condition`, `threshold_count`, `check_interval_seconds`
    - (Optional) `batch_size` and `catch_up_enabled` if used by P03
- **Acceptance**:
  - P03 pipeline YAML validates under `k0/runtime/schemas.py::TriggerSpec`.
  - `PipelineScheduler.register_pipeline(...)` creates all trigger engines for P03 without error.
- **References**:
  - Dossier trigger blueprint: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.5.1)
  - K0 Trigger schema: `k0/runtime/schemas.py` (`TriggerType`, `TriggerSpec`)
  - K0 trigger engine factory: `k0/scheduler/triggers.py` (`create_trigger_engine`)
  - K0 scheduler registration: `k0/scheduler/scheduler.py` (`PipelineScheduler.register_pipeline`)

#### Issue 1.3.2 — Extend manual triggering to carry P03 options (reason/skip_r5/max_events) via TriggerEvent.context

- **Goal**: Support the dossier’s manual trigger API semantics by propagating a manual trigger payload into the pipeline execution entrypoint.
- **Deliverables**:
  - Extend manual trigger invocation so it can pass context:
    - `reason` string
    - `options.skip_r5` (bool)
    - `options.max_events` (int)
    - (Optional) `options.space_id` / `options.tenant_id` to target a specific partition in debug mode
  - Represent these fields in `TriggerEvent.context` (already supported by `TriggerEvent`).
  - Update `PipelineScheduler.fire_manual_trigger(...)` (or a new method) to accept this payload and pass it down to the `ManualTriggerEngine`.
- **Acceptance**:
  - Manual trigger produces a `TriggerEvent` that includes the payload in `context`.
  - P03 can read `TriggerEvent.context` in R0 to apply `skip_r5` and `max_events` deterministically.
- **References**:
  - Dossier manual trigger API: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.5.3)
  - Trigger event type: `k0/scheduler/triggers.py` (`TriggerEvent.context`, `ManualTriggerEngine.fire`)
  - Scheduler manual trigger entrypoint: `k0/scheduler/scheduler.py` (`PipelineScheduler.fire_manual_trigger`)

#### Issue 1.3.3 — Validate overlap policy (single-flight) matches trigger semantics (SKIP vs QUEUE)

- **Goal**: Ensure scheduler-level overlap behavior is deterministic and matches the documented operational intent:
  - Interval triggers should **SKIP** overlapping runs.
  - Threshold/manual triggers should **QUEUE** at most one pending run (coalesced).
- **Deliverables**:
  - Confirm P03 uses the existing `SingleFlightGate` behavior as-is (no semantic drift), including:
    - `OverlapPolicy.SKIP` for interval triggers
    - `OverlapPolicy.QUEUE` (depth 1 / coalesce) for threshold/manual triggers
  - Add targeted tests for:
    - overlap policy mapping by trigger type
    - queue depth behavior (coalescing) for repeated threshold fires
- **Acceptance**:
  - Tests demonstrate that repeated THRESHOLD/MANUAL fires during an in-flight run result in at most one queued run.
  - Interval fires during an in-flight run are skipped (not queued).
- **References**:
  - Concurrency gate: `k0/scheduler/concurrency.py` (`SingleFlightGate`, `_get_overlap_policy`, `reset_single_flight_gate`)
  - Scheduler dispatch path: `k0/scheduler/scheduler.py` (`_make_trigger_callback` → executor)
  - Trigger types: `k0/runtime/schemas.py` (`TriggerType`)

#### Issue 1.3.4 — Implement single-writer-per-space guard using PostgreSQL advisory locks (per dossier lock key pattern)

- **Goal**: Enforce the dossier requirement that consolidation cycles must not overlap **within the same (tenant_id, space_id)** even across multiple K0 instances.
- **Deliverables**:
  - Define the lock scope and key mapping consistent with the dossier:
    - logical lock key: `{pipeline_id}:{tenant_id}:{space_id}`
    - acquisition strategy: non-blocking `pg_try_advisory_lock(...)` (or a bounded-wait variant) with explicit behavior when lock cannot be acquired.
  - Implement a small Postgres-backed lock helper (location to be chosen to fit K0 layering; e.g., as a syscall or DB helper) that:
    - acquires/releases the advisory lock
    - supports best-effort cleanup on exceptions
  - Integrate lock acquisition at the start of a P03 cycle (R0) and release on completion/abort.
- **Acceptance**:
  - When two workers attempt to run P03 for the same space concurrently, one proceeds and the other deterministically defers/skips according to policy.
  - Lock acquisition/failure is observable (structured log + metric counter).
- **References**:
  - Dossier concurrency requirement + lock key pattern: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.10.2, 4.10.6)
  - Dossier retry/error matrix includes lock timeout handling: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.4 rows referencing LOCK_TIMEOUT)
  - Existing scheduler-level gating (in-memory only): `k0/scheduler/concurrency.py`

#### Issue 1.3.5 — Define batch selection/backpressure inputs (deadline/budgets) and plumb trigger context into R0

- **Goal**: Make batch selection (R0) explicitly parameterized by trigger and resource context, enabling backpressure and deterministic behavior.
- **Deliverables**:
  - Define the minimal trigger-derived inputs that R0 consumes:
    - `trigger_type` + `trigger_reason`
    - `max_events` override (manual trigger option)
    - `threshold_count`/`count` context (threshold trigger)
    - (Optional) `batch_size` from `TriggerSpec` if used
    - `deadline_ms` and QoS budgets from cycle context (Epic 1.1)
  - Ensure these arrive at the P03 runner as part of the cycle context / envelope.
  - Define the backpressure policy for R0 in ticket text:
    - how the selected batch size is derived (bounded by `max_events` and by QoS budgets)
    - what happens when backlog is large but QoS/token acquisition fails (defer, smaller batch, or skip)
- **Acceptance**:
  - R0 selection is deterministic for the same inputs (including trigger context and budgets).
  - R0 never exceeds configured `max_events` / effective batch size.
- **References**:
  - Dossier scheduler + trigger intent: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.5.1)
  - Trigger event context carrier: `k0/scheduler/triggers.py` (`TriggerEvent.context`)
  - Trigger schema fields (batch_size, threshold_count): `k0/runtime/schemas.py` (`TriggerSpec`)

#### Issue 1.3.6 — Integrate QoS token acquisition + budget enforcement into cycle start/end (acquire/release)

- **Goal**: Apply the dossier’s QoS-aware consolidation requirement by acquiring scheduler capacity before heavy work and enforcing per-cycle budgets during execution.
- **Deliverables**:
  - At cycle start (R0), acquire a scheduler token via `QoSContext.acquire(band, port, cost)` and store it in the cycle context.
  - Ensure token release happens exactly once in all exit paths (success, skip, fail, abort) using `try/finally` semantics.
  - Define and document the initial cost model (even if simple):
    - $cost = f(batch\_size)$ for `port="command"` acquisitions
  - Enforce `fanout_budget` and `top_k_budget` through `QoSContext.consume_*` at phase boundaries where applicable.
  - Define behavior when capacity/budgets are exhausted:
    - `SchedulerCapacityError` (defer / reschedule / smaller batch per policy)
    - `QoSBudgetError` (stop or reduce work per policy)
- **Acceptance**:
  - QoS token is always released (no leaked capacity) even when phases fail.
  - Capacity/budget exhaustion paths are test-covered and observable.
- **References**:
  - Dossier QoS integration overview + scheduler integration: `docs/pipelines/P03_consolidation_dossier_v2.md` (Sections 15.1–15.2)
  - K0 QoS scheduler: `k0/qos/scheduler.py` (`Scheduler.acquire`, `SchedulerToken.release`, `SchedulerCapacityError`)
  - K0 QoS context: `k0/qos/context.py` (`QoSContext`, `QoSBudgetError`)

---

## Milestone 2 — Storage + migrations + transactional backbone

### Epic 2.1 — Core truth + operational tables

> **Scope note (avoid confusion)**:

> - Epic 2.1 covers **truth-layer tables** (Sections 6.3–6.10) and **operational backbone tables** needed for resume/outbox/retention (Sections 6.14–6.16), plus the **P03 consolidation columns** added to `st_hipp_events` (Section 6.2).
> - Epic 2.1 does **not** implement learning/audit tables like `st_learning_queue`, `st_anchors`, `st_anchor_observations`, `st_learned_weights` (Sections 6.11–6.13, 6.17). Those are handled in **Epic 2.2 / Epic 2.3**.
> - For tables that already exist in `k0/db/alembic/versions/`, the expectation is **verify dossier alignment and add corrective migrations** (do not edit past migrations).

#### Issue 2.1.1 — Storage gap analysis: dossier schema vs existing Alembic migrations (truth + ops tables)

- **Goal**: Produce a precise “already exists vs missing vs mismatched” map for P03’s required tables, before writing new migrations.
- **Deliverables**:
  - A checklist/table in the ticket covering each storage surface below:
    - Truth layer (8): `st_epi`, `st_sem`, `st_procedural`, `st_social`, `st_prospective`, `st_kg_dom`, `st_kg_edges`, `st_vec`
    - Operational: `st_offsets`, `st_pipeline_status`, `st_pipeline_watermarks`, `st_outbox`, `st_retention_policy`
    - Source staging: `st_hipp_events` (including the P03 consolidation columns)
  - For each surface, cite:
    - dossier section(s)
    - existing migration file (if present), or “NEW MIGRATION REQUIRED”
    - required delta (columns/indexes/types/constraints)
- **Acceptance**:
  - All tables and indexes required by dossier sections 6.2–6.16 are either:
    - mapped to an existing Alembic migration file, or
    - explicitly marked as missing with a planned issue below.
  - The gap analysis explicitly calls out (as “known likely deltas” to confirm):
    - `st_outbox.next_attempt_ts` type (dossier uses BIGINT; current migration uses TEXT)
    - missing P03 consolidation columns on `st_hipp_events` (and the P03 pending-scan index)
- **References**:
  - Dossier storage canonical DDL: `docs/pipelines/P03_consolidation_dossier_v2.md` (Sections 6.2–6.16)
  - Existing K0 Alembic migrations directory: `k0/db/alembic/versions/`
    - Offsets: `k0/db/alembic/versions/0005_st_offsets.py`
    - Outbox: `k0/db/alembic/versions/0008_st_outbox.py`
    - Retention policy: `k0/db/alembic/versions/0014_st_retention_policy.py`
    - Pipeline status: `k0/db/alembic/versions/0020_st_pipeline_status.py`
    - Pipeline watermarks: `k0/db/alembic/versions/0021_st_pipeline_watermarks.py`
    - Hipp events: `k0/db/alembic/versions/0022_st_hipp_events.py`
    - Vectors: `k0/db/alembic/versions/0025_st_vec.py`

#### Issue 2.1.2 — Create `st_epi` (episodic memory) table + indexes (Section 6.3)

- **Goal**: Implement the dossier’s canonical `st_epi` schema and indexes.
- **Deliverables**:
  - New Alembic migration under `k0/db/alembic/versions/` that:
    - creates table `st_epi` with all columns and constraints shown in Section 6.3
    - creates indexes:
      - `idx_epi_tenant_time` on `(tenant_id, start_time_utc DESC)`
      - `idx_epi_space_time` on `(space_id, start_time_utc DESC)`
      - `idx_epi_cluster` on `(cluster_id)` with `WHERE cluster_id IS NOT NULL`
      - `idx_epi_canonical` on `(is_canonical, archival_status)`
- **Acceptance**:
  - Migration applies cleanly on PostgreSQL.
  - `st_epi` columns and index names match Section 6.3 exactly.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.3)
  - Alembic style reference: any existing migration under `k0/db/alembic/versions/`

#### Issue 2.1.3 — Create `st_sem` (semantic patterns) table + indexes (Section 6.4)

- **Goal**: Implement the dossier’s canonical `st_sem` schema and indexes.
- **Deliverables**:
  - New Alembic migration that:
    - creates table `st_sem` with column-level CHECK constraints as specified in Section 6.4 (notably `pattern_type`)
    - creates indexes:
      - `idx_sem_tenant_type` on `(tenant_id, pattern_type)`
      - `idx_sem_actor_type` on `(actor_id, pattern_type)` with `WHERE actor_id IS NOT NULL`
      - `idx_sem_canonical` on `(is_canonical, archival_status)`
      - `idx_sem_confidence` on `(confidence_score DESC)` with `WHERE is_canonical = TRUE`
- **Acceptance**:
  - Migration applies cleanly and index partial predicates are PostgreSQL-correct.
  - Index names/columns match dossier Section 6.4.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.4)

#### Issue 2.1.4 — Create `st_procedural` (habits & routines) table (Section 6.5)

- **Goal**: Implement the dossier’s canonical `st_procedural` schema.
- **Deliverables**:
  - New Alembic migration that creates `st_procedural` with the exact columns and defaults in Section 6.5.
  - (If indexes are needed for performance, add only those explicitly specified by the dossier; otherwise do not invent new ones.)
- **Acceptance**:
  - `st_procedural` matches Section 6.5 schema (column names, nullability, defaults).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.5)

#### Issue 2.1.5 — Create `st_social` (relationships) table + uniqueness constraint (Section 6.6)

- **Goal**: Implement the dossier’s canonical `st_social` schema, including its uniqueness constraint.
- **Deliverables**:
  - New Alembic migration that creates `st_social` per Section 6.6, including:
    - `UNIQUE(tenant_id, actor_a_id, actor_b_id, is_canonical)`
- **Acceptance**:
  - Uniqueness constraint prevents duplicate canonical relationship rows for a tenant.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.6)

#### Issue 2.1.6 — Create `st_prospective` (intentions & goals) table + CHECK constraints (Section 6.7)

- **Goal**: Implement the dossier’s canonical `st_prospective` schema with the enum-like CHECK constraints.
- **Deliverables**:
  - New Alembic migration that creates `st_prospective` per Section 6.7, including CHECK constraints for:
    - `intention_type IN ('GOAL','PLAN','REMINDER','COMMITMENT','WISH')`
    - `status IN ('ACTIVE','COMPLETED','ABANDONED','DEFERRED')`
- **Acceptance**:
  - Postgres rejects invalid `intention_type` and invalid `status` values.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.7)

#### Issue 2.1.7 — Create `st_kg_dom` (KG entities) table + indexes (Section 6.8)

- **Goal**: Implement the dossier’s canonical `st_kg_dom` schema and indexes.
- **Deliverables**:
  - New Alembic migration that creates `st_kg_dom` per Section 6.8.
  - Create indexes:
    - `idx_kg_dom_tenant_type` on `(tenant_id, entity_type)`
    - `idx_kg_dom_name` on `(canonical_name)`
    - `idx_kg_dom_canonical` on `(is_canonical, archival_status)`
- **Acceptance**:
  - Index names/columns match Section 6.8.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.8)

#### Issue 2.1.8 — Create `st_kg_edges` (KG relationships) table + FKs + indexes (Section 6.9)

- **Goal**: Implement the dossier’s canonical `st_kg_edges` schema, including referential integrity to `st_kg_dom`.
- **Deliverables**:
  - New Alembic migration that creates `st_kg_edges` per Section 6.9, including:
    - foreign keys: `source_entity_id` → `st_kg_dom(entity_id)` and `target_entity_id` → `st_kg_dom(entity_id)`
  - Create indexes:
    - `idx_kg_edges_source` on `(source_entity_id, relation_type)`
    - `idx_kg_edges_target` on `(target_entity_id, relation_type)`
    - `idx_kg_edges_canonical` on `(is_canonical, archival_status)`
- **Acceptance**:
  - FK constraints prevent edges referencing non-existent KG entities.
  - Index names/columns match Section 6.9.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.9)

#### Issue 2.1.9 — Verify `st_vec` (embeddings) matches dossier + migrate deltas if needed (Section 6.10)

- **Goal**: Ensure the existing `st_vec` table is aligned with dossier Section 6.10 and is usable by P03 (reads) and P08 (indexing).
- **Deliverables**:
  - Verify `st_vec` has the columns and indexes specified in Section 6.10.
  - If any mismatch is found, add a corrective migration (do not edit past migrations).
- **Acceptance**:
  - `st_vec` contains, at minimum: `embedding_id` PK, `event_id` FK to `st_hipp_events`, tenant/space columns, vector bytes, model_id, status, created/updated timestamps, and FAISS fields.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.10)
  - Existing migration: `k0/db/alembic/versions/0025_st_vec.py`

#### Issue 2.1.10 — Add P03 consolidation columns + pending index to `st_hipp_events` (Section 6.2 + 6.2.2)

- **Goal**: Make the staging table support the P03 consolidation lifecycle, and provide the pending-scan index called out by the dossier.
- **Deliverables**:
  - New Alembic migration that alters `st_hipp_events` to add the P03 consolidation columns described in Section 6.2:
    - `consolidation_status` with CHECK constraint allowing:
      - `PENDING`, `IN_PROGRESS`, `CONSOLIDATED`, `DUPLICATE`, `PRUNED`, `PENDING_REVIEW` (and NULL allowed for “new from P02”)
    - `consolidation_cycle_id`
    - `consolidated_at`
    - `reconciliation_decision`
    - `truth_match_id`
    - `truth_match_similarity`
  - Add the dossier’s P03-specific partial index:
    - `idx_hipp_events_consolidation` on `(consolidation_status, event_time_utc)`
      - predicate: `consolidation_status IS NULL OR consolidation_status = 'PENDING'`
- **Acceptance**:
  - New events with `consolidation_status = NULL` are selectable efficiently for the next consolidation cycle.
  - Invalid consolidation statuses are rejected by Postgres.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.2.2 lifecycle + Section 6.2 indexes)
  - Existing base table migration: `k0/db/alembic/versions/0022_st_hipp_events.py`

#### Issue 2.1.11 — Reconcile `st_outbox.next_attempt_ts` type with dossier (Section 6.15)

- **Goal**: Align the outbox schema with the dossier’s canonical types, to avoid timestamp sorting/compare bugs in retry scheduling.
- **Deliverables**:
  - Verify `st_outbox` matches Section 6.15, with special attention to `next_attempt_ts`.
  - If needed, add a corrective migration that changes `next_attempt_ts` from TEXT → BIGINT (Unix time) and updates any dependent indexes.
  - Ensure uniqueness index `uq_outbox_idem` matches dossier fields.
- **Acceptance**:
  - `next_attempt_ts` supports numeric range comparisons and ordering without casts.
  - Idempotency uniqueness remains enforced exactly as dossier specifies.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.15)
  - Existing migration: `k0/db/alembic/versions/0008_st_outbox.py`

#### Issue 2.1.12 — Verify offsets/status/watermarks + retention policy tables match dossier (Sections 6.14–6.16)

- **Goal**: Confirm that resume-capability tables and retention policy surfaces match dossier DDL and can be used immediately by the P03 runner/checkpointing work.
- **Deliverables**:
  - Verify and document alignment for:
    - `st_offsets` (dossier Section 6.14) ↔ existing `k0/db/alembic/versions/0005_st_offsets.py`
    - `st_pipeline_status` (dossier Section 6.14) ↔ existing `k0/db/alembic/versions/0020_st_pipeline_status.py`
    - `st_pipeline_watermarks` (dossier Section 6.14) ↔ existing `k0/db/alembic/versions/0021_st_pipeline_watermarks.py`
    - `st_retention_policy` (dossier Section 6.16) ↔ existing `k0/db/alembic/versions/0014_st_retention_policy.py`
  - If any mismatch is found, add corrective migrations (do not edit past migrations).
- **Acceptance**:
  - P03 can:
    - read/write subscriber offsets (`st_offsets`) for its entry topic,
    - write per-wal processing outcomes (`st_pipeline_status`),
    - read/write per-space watermarks (`st_pipeline_watermarks`),
    - consult `st_retention_policy` for lifecycle decisions.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Sections 6.14–6.16)
  - Existing migrations: see files listed above in Issue 2.1.1

### Epic 2.2 — Audit + explainability + compliance

> **Scope note (avoid confusion)**:

> - Epic 2.2 defines the **audit/explainability/compliance storage surfaces and hooks** needed for P03 to be transparent and policy-aligned.
> - Epic 2.2 intentionally limits “learning” to what is required for auditability (schema + write path + read path). Parameter-learning tables and feedback persistence live in **Epic 2.3**.
> - Repository reality check: there is currently **no** Alembic migration creating `st_consolidation_audit` (search `k0/db/alembic/versions/`), so this epic must introduce it via a **new migration**.

#### Issue 2.2.1 — Create `st_consolidation_audit` table + indexes (+ outcome-tracking columns) (Sections 6.20 + 1.4.7)

- **Goal**: Add the dossier’s canonical audit table to storage so P03 can record every consolidation decision for explainability, debugging, and (later) learning analysis.
- **Deliverables**:
  - New Alembic migration under `k0/db/alembic/versions/` that creates `st_consolidation_audit`.
  - The created schema must support **both**:
    - decision audit / explainability (Section 6.20), and
    - threshold outcome tracking fields used by the Thompson Sampling loop (Section 1.4.7).
  - Minimum required columns (superset of dossier requirements; do not invent unrelated fields):
    - Identity: `audit_id` (TEXT primary key)
    - What was affected: `memory_id` (TEXT), `source_table` (TEXT)
    - Decision details:
      - `action` (TEXT) — per Section 6.20
      - `formula_used` (TEXT), `formula_version` (TEXT)
      - `inputs_json` (TEXT), `outputs_json` (TEXT) — store JSON text (repo pattern: JSON-in-TEXT)
      - `explanation` (TEXT), `confidence` (REAL)
      - `decision_id` (UUID or TEXT), `decision_type` (TEXT) — per Section 1.4.7
      - `threshold_used` (REAL), `threshold_name` (TEXT)
      - `outcome_evaluated` (BOOLEAN default FALSE), `outcome_success` (BOOLEAN), `evaluated_at` (BIGINT)
    - Context: `space_id` (TEXT), `cycle_id` (TEXT nullable)
    - Timestamps: `created_at` (BIGINT, epoch ms)
  - Indexes (match dossier names/keys):
    - `idx_audit_memory_time` on `(memory_id, created_at)`
    - `idx_audit_action` on `(action, created_at)`
    - `idx_audit_formula` on `(formula_used, created_at)`
    - `idx_audit_decision` on `(decision_id)`
    - `idx_consolidation_audit_outcome_eval` on `(outcome_evaluated, created_at)` with predicate `outcome_evaluated = FALSE` (Postgres partial index)
  - Multi-tenant isolation:
    - Add space isolation enforcement consistent with K0’s established approach (RLS if applicable in your Postgres deployment; otherwise enforce `space_id` filtering in all query builders and add tests).
- **Acceptance**:
  - Migration applies cleanly on PostgreSQL.
  - `st_consolidation_audit` supports inserts for both:
    - “audit per write” records (action/formula/inputs/outputs/explanation), and
    - “decision outcome tracking” records (decision_id/threshold_used/outcome columns).
  - Cross-space reads are prevented by policy (RLS) and/or are proven impossible by integration tests.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md`
    - Section 6.20 (audit table schema + indexes + isolation intent)
    - Section 1.4.7 (decision outcome tracking + schema extensions + outcome evaluation index)

#### Issue 2.2.2 — Implement the P03 decision audit logger (write path) (Sections 6.20 + 14.10)

- **Goal**: Ensure every consolidation decision that changes state or truth is recorded to `st_consolidation_audit` in a deterministic, queryable format.
- **Deliverables**:
  - A P03-local “decision logger” component (module/file location per P03 code layout) that:
    - writes `audit_id`, `memory_id`, `source_table`, `action`, `formula_used`, `formula_version`, `inputs_json`, `outputs_json`, `explanation`, `confidence`, `space_id`, `cycle_id`, `created_at`.
    - accepts structured inputs/outputs and serializes them to JSON text.
    - never logs raw PII in `inputs_json`/`outputs_json`/`explanation` (IDs only); apply K0 redaction obligations where appropriate.
  - Define a stable “explanation template” convention (Section 14.10) so the user-facing string can be rendered consistently.
  - Add trace context linkage (at minimum: `cycle_id`, `space_id`, `tenant_id` if available in calling context) so audit records can be correlated to logs/traces.
- **Acceptance**:
  - For a given consolidation run, at least one audit record is written per decision type that occurs (REINFORCE/EXTEND/CREATE/PRUNE/etc.).
  - The logger rejects/strips forbidden fields for RED-band data (or logs only safe placeholders).
  - Writes are idempotent per `audit_id` (no duplicate PK violations under retry).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.20.3 “Record Decision”)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.10 “Explanation Templates”)
  - K0 policy redaction: `k0/policy/redaction.py` (`apply_redactions`)

#### Issue 2.2.3 — Implement explainability query API for a memory decision (read path) (Sections 6.20.3 + 14.10)

- **Goal**: Provide a stable query surface that returns “why was this memory handled this way?” from `st_consolidation_audit`.
- **Deliverables**:
  - A function/service entry point (and optionally a HTTP endpoint) that:
    - looks up the latest audit record for `(memory_id, space_id)` ordered by `created_at DESC`
    - returns a response containing: `memory_id`, `action`, `explanation`, `confidence`, `created_at`
    - does not leak `inputs_json` / `outputs_json` to end users by default (only for ops/debug contexts).
  - Unit/integration tests for:
    - no record → default explanation
    - record exists → template renders correctly
    - cross-space lookup returns no data
- **Acceptance**:
  - For an audited memory id, explainability returns deterministic output and the same action/confidence as stored.
  - Cross-space lookups cannot retrieve other space’s audit records.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.20.3 “Generate Explanations”)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.10 “Memory Decision Explanations”)

#### Issue 2.2.4 — Retention wiring for audit records (90-day raw + aggregation plan) (Section 6.20)

- **Goal**: Make audit retention explicit and enforceable: keep detailed audit for 90 days, then aggregate, preserving compliance and storage constraints.
- **Deliverables**:
  - Update/configure retention policies so `st_consolidation_audit` is governed by `st_retention_policy`.
  - Implement a maintenance job (scheduler wiring per K0 ops patterns) that:
    - deletes raw audit rows older than 90 days, and
    - writes daily aggregated summaries per space before deletion (table name + schema must be decided and documented as part of this issue; keep it minimal: day, space_id, action counts, avg confidence).
  - Ensure the job logs what it did (counts, time range) without emitting sensitive payloads.
- **Acceptance**:
  - Running the job twice is safe (idempotent aggregation and deletion).
  - Raw audit data does not grow unbounded past retention windows.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.20 “Retention Policy”)
  - Existing retention system surfaces:
    - `k0/db/alembic/versions/0014_st_retention_policy.py`
    - `k0/policy/retention_enforcer.py`
    - `k0/db/alembic/versions/0015_st_archive_manifest.py` (if aggregation/archival uses manifest tracking)

#### Issue 2.2.5 — GDPR erasure hooks: tombstone + GC semantics across P03 memory layers (Section 14.7)

- **Goal**: Implement an explicit, testable erasure path that propagates GDPR Article 17 requests through P03-owned data (and coordinates with shared stores like embeddings and KG).
- **Deliverables**:
  - An erasure handler entry point that supports at least these scopes (per dossier):
    - `ACTOR_DATA`, `ALL_MENTIONS`, `FULL_PURGE`
  - Implement the dossier’s cascade at a minimum:
    - mark affected `st_hipp_events` rows as TOMBSTONE (or equivalent deletion marker)
    - cascade to truth tables (`st_epi`, `st_sem`, `st_kg_dom`, `st_kg_edges`, …)
    - delete associated embeddings from `st_vec` and coordinate index rebuild with P08
    - write an auditable compliance entry to the WAL (append-only)
  - Decide and implement what happens to `st_consolidation_audit` rows for purged data:
    - either delete them for `FULL_PURGE`, or
    - retain only non-identifying aggregated summaries (no actor identifiers), consistent with data minimization.
- **Acceptance**:
  - An erasure request produces deterministic counts of affected rows per table.
  - After erasure completes, subsequent reads in the same space cannot retrieve erased records.
  - Compliance actions are recorded in WAL/audit without leaking sensitive payload fields.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.7 “Data Minimization & GDPR”)
  - K0 WAL: `k0/storage/wal.py`
  - K0 retention deletion hook: `k0/policy/retention_enforcer.py`

### Epic 2.3 — Learning + feedback persistence

> **Scope note (avoid confusion)**:

> - Epic 2.3 covers **learning + feedback persistence storage surfaces** for P03 and closely-related shared stores: gaps (`st_learning_queue`), Bayesian anchors (`st_anchors`, `st_anchor_observations`), learned parameters (`st_learned_weights`, `st_learned_weights_history`), feedback quarantine (`st_feedback_quarantine`), and golden dataset validation (`st_golden_dataset_pairs`, `st_validation_results`).
> - Epic 2.3 also includes **schema reconciliation work** where the dossier’s canonical schema conflicts with existing code/migrations (notably `st_feedback_signals` and `st_dlq`). These must be handled as **explicit “decision + corrective migration(s)”** work items to avoid drift.
> - As with Epic 2.1: **do not edit past Alembic migrations**. Add new migrations to reconcile deltas.

#### Issue 2.3.1 — Storage gap analysis: learning + feedback tables vs existing Alembic migrations (Sections 6.11–6.13, 6.17, 6.21–6.23 + DLQ 13.4)

- **Goal**: Produce a precise “already exists vs missing vs mismatched” map for Epic 2.3 storage surfaces before writing new migrations (and surface any dossier↔repo conflicts that require an ADR/decision).
- **Deliverables**:
  - A checklist/table (in the ticket) covering each storage surface below, with:
    - dossier section reference,
    - current repo artifact(s) (migration + runtime code),
    - status: **EXISTS**, **MISSING**, **MISMATCH**,
    - action: **create new migration**, **create corrective migration**, or **decision required**.
  - The checklist must cover at minimum:
    - `st_learning_queue` (6.11)
    - `st_anchors` (6.12)
    - `st_anchor_observations` (6.13)
    - `st_learned_weights` (6.17)
    - `st_feedback_quarantine` (6.21)
    - `st_learned_weights_history` (6.23)
    - `st_golden_dataset_pairs` + `st_validation_results` (golden dataset schema block in dossier)
    - `st_feedback_signals` consumption fields (dossier “Consumption Fields” table)
    - `st_dlq` (dossier Section 13.4) vs existing `k0/storage/dlq.py` + `k0/db/alembic/versions/0009_st_dlq.py`.
- **Acceptance**:
  - Every table/index/policy listed above is accounted for with an explicit next action.
  - Any dossier↔repo mismatch is captured as **Decision required** (with pointers to the exact dossier section + the exact repo file(s) that disagree).
- **References**:
  - Dossier canonical schemas:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Sections 6.11–6.13, 6.17, 6.21–6.23)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.4 “Dead Letter Queue Schema (st_dlq)”)
  - Existing migrations:
    - `k0/db/alembic/versions/0009_st_dlq.py`
    - `k0/db/alembic/versions/0026_st_feedback_signals.py`
  - Existing runtime code:
    - `k0/storage/dlq.py`
    - `k0/ports/observe.py`
    - `k0/feedback/worker.py`

#### Issue 2.3.2 — Create `st_learning_queue` (gap queue) table + indexes (Section 6.11)

- **Goal**: Implement the dossier’s canonical gap queue schema for P03→P06 learning gaps.
- **Deliverables**:
  - New Alembic migration under `k0/db/alembic/versions/` that creates `st_learning_queue` per Section 6.11, including:
    - gap_type CHECK constraint values
    - generated `importance_score` column
    - lifecycle `status` CHECK constraint values
    - FK to `st_hipp_events(event_id)` for `related_event_id`
  - Create the dossier indexes with the same names/keys/predicates:
    - `idx_learning_queue_importance` (partial index on `status = 'PENDING'`)
    - `idx_learning_queue_status`
    - `idx_learning_queue_tenant`
- **Acceptance**:
  - Migration applies cleanly on PostgreSQL.
  - Gap records with `status='PENDING'` can be efficiently queried in descending importance.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.11)

#### Issue 2.3.3 — Create `st_anchors` (Bayesian beliefs) table + indexes (Section 6.12)

- **Goal**: Implement the dossier’s canonical Bayesian anchor storage (Beta distributions) used by P03 and P06.
- **Deliverables**:
  - New Alembic migration that creates `st_anchors` per Section 6.12, including:
    - composite primary key
    - generated `confidence` and `uncertainty` columns
    - lifecycle `status` CHECK constraint values
  - Create the dossier indexes:
    - `idx_anchors_entity`
    - `idx_anchors_confidence` (partial: `status = 'ACTIVE'`)
    - `idx_anchors_drift` (partial: `drift_detected = TRUE`)
- **Acceptance**:
  - Inserts/updates compute generated columns correctly.
  - Index predicates are PostgreSQL-correct and match dossier.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.12)

#### Issue 2.3.4 — Create `st_anchor_observations` (evidence log) table + indexes (Section 6.13)

- **Goal**: Persist an append-only evidence log that explains how anchors were updated.
- **Deliverables**:
  - New Alembic migration that creates `st_anchor_observations` per Section 6.13, including:
    - FK to `st_anchors` composite key
    - FK to `st_hipp_events(event_id)`
  - Create index `idx_anchor_obs_anchor` per dossier.
- **Acceptance**:
  - Referential integrity holds (cannot insert an observation for a missing anchor).
  - Latest-observation queries for an anchor are efficient.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.13)

#### Issue 2.3.5 — Create `st_learned_weights` (adaptive parameters) table + indexes + RLS enforcement strategy (Section 6.17)

- **Goal**: Implement the canonical learned-parameter store and its isolation model so later P03 phases can safely load/update adaptive params.
- **Deliverables**:
  - New Alembic migration that creates `st_learned_weights` per Section 6.17, including:
    - UNIQUE(space_id, param_key, param_scope, scope_id)
    - CHECK constraints for `param_scope`, `confidence`, `sample_count`
    - indexes:
      - `idx_learned_weights_space_key`
      - `idx_learned_weights_scope`
      - `idx_learned_weights_confidence`
  - Isolation decision + implementation:
    - Implement the dossier’s RLS approach (enable RLS + policy based on `current_setting('app.current_space_id', true)`), **or** if the repo’s Postgres connection management cannot support this yet, document the blocker and implement an interim guardrail:
      - require explicit `space_id` predicates in all query builders, and
      - add an integration test that proves cross-space reads are impossible through the P03 access layer.
  - If RLS is enabled, implement a minimal, reusable “set space context” hook for DB sessions (as required by the dossier’s “SET LOCAL app.current_space_id = …” example).
- **Acceptance**:
  - Schema matches dossier Section 6.17 (columns, constraints, indexes).
  - Cross-space access is prevented by RLS (preferred) or proven impossible by tests + query builder enforcement (interim).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.17)

#### Issue 2.3.6 — Create `st_learned_weights_history` (parameter versioning) + retention (last 10 versions) + RLS (Section 6.23)

- **Goal**: Add durable parameter history to support rollback and longitudinal analysis.
- **Deliverables**:
  - New Alembic migration that creates `st_learned_weights_history` per Section 6.23, including:
    - FK to `st_learned_weights(param_id)`
    - UNIQUE(param_id, version)
    - indexes:
      - `idx_weights_history_param_version`
      - `idx_weights_history_param_time`
      - `idx_weights_history_space`
  - Implement/define how “last 10 versions per parameter” is enforced:
    - either via a DB trigger/function, or
    - via a small maintenance routine invoked after each parameter update (delete versions older than last 10).
  - Apply the dossier’s isolation model to the history table (RLS policy or equivalent enforcement).
- **Acceptance**:
  - After repeatedly updating a parameter, `st_learned_weights_history` retains only the most recent 10 versions for that `param_id`.
  - Rollback queries can efficiently fetch the most recent versions.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.23)

#### Issue 2.3.7 — Create `st_feedback_quarantine` (suspicious signal quarantine) + indexes + isolation (Section 6.21)

- **Goal**: Provide the persistence surface for quarantining anomalous/adversarial feedback signals before they affect learning.
- **Deliverables**:
  - New Alembic migration that creates `st_feedback_quarantine` per Section 6.21, including indexes:
    - `idx_quarantine_space_status` (partial: `decision IS NULL`)
    - `idx_quarantine_auto_release` (partial: `decision IS NULL`)
    - `idx_quarantine_signal`
  - If the quarantine flow expects fields on `st_feedback_signals` (e.g., `quarantine_status`), add a **separate corrective migration** to add those fields (do not edit existing migrations).
  - Isolation enforcement per dossier (RLS policy or equivalent application-level enforcement).
- **Acceptance**:
  - Quarantine insert/query/update flows are supported by indexes (unreviewed-by-space and auto-release scans are efficient).
  - Cross-space access is blocked by policy and/or proven impossible by tests.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.21)

#### Issue 2.3.8 — Reconcile `st_feedback_signals` for P03 consumption semantics (consumed_at/consumed_by) + resolve repo drift (Consumption Fields)

- **Goal**: Make P03 feedback consumption durable and deterministic, while resolving the current schema↔code mismatch around `st_feedback_signals`.
- **Deliverables**:
  - **Decision required**: choose the canonical `st_feedback_signals` shape for K0 going forward:
    - dossier-driven (“consumed_at/consumed_by” semantics), and/or
    - current repo migration (`k0/db/alembic/versions/0026_st_feedback_signals.py`) shape, and/or
    - current runtime usage in `k0/ports/observe.py` and `k0/feedback/worker.py`.
  - After the decision, implement alignment via:
    - corrective migration(s) adding required columns (at minimum `consumed_at` BIGINT and `consumed_by` TEXT if dossier semantics are adopted), and
    - code updates in the relevant writers/readers so column names and types match the chosen contract.
  - Add a P03-side consumption update query that matches the dossier pattern:
    - only consume signals where `consumed_at IS NULL` (or equivalent pending predicate)
    - idempotent updates under retries.
- **Acceptance**:
  - No runtime component references columns that do not exist.
  - P03 can mark signals as consumed exactly once (idempotent), and reprocessing does not occur.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Consumption Fields section for `st_feedback_signals`)
  - Existing migration: `k0/db/alembic/versions/0026_st_feedback_signals.py`
  - Current writers/readers:
    - `k0/ports/observe.py`
    - `k0/feedback/worker.py`

#### Issue 2.3.9 — Create `st_golden_dataset_pairs` + `st_validation_results` tables + indexes (Golden dataset validation schema)

- **Goal**: Add durable golden dataset and validation result storage surfaces for drift detection and weekly validation loops.
- **Deliverables**:
  - New Alembic migration that creates:
    - `st_golden_dataset_pairs` with indexes:
      - `idx_golden_pairs_entity_type`
      - `idx_golden_pairs_ground_truth`
      - `idx_golden_pairs_active`
    - `st_validation_results` with index:
      - `idx_validation_results_created`
  - Ensure types match the dossier expectations (e.g., JSONB columns for pair payloads, BIGINT timestamps).
- **Acceptance**:
  - Migrations apply cleanly on PostgreSQL.
  - Basic read/write queries in the dossier examples work without casts.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (golden dataset schema block for `st_golden_dataset_pairs` and `st_validation_results`)

#### Issue 2.3.10 — Reconcile `st_dlq` schema and DLQ driver against dossier (Section 13.4)

- **Goal**: Ensure P03 can reliably record failures to the DLQ using the schema and retry semantics described in the dossier.
- **Deliverables**:
  - **Decision required**: dossier Section 13.4 defines a `st_dlq` shape that conflicts with current repo reality:
    - existing migration: `k0/db/alembic/versions/0009_st_dlq.py` (BigInteger `id`, SQLite-export schema)
    - existing driver: `k0/storage/dlq.py` (writes the SQLite-export column set)
  - After the decision, implement one of:
    - (A) **Bring repo into dossier compliance**: add new migration(s) + a driver update that support the dossier schema and retry indexes (`idx_dlq_status_next`, `idx_dlq_pipeline_phase`). If schema-breaking changes are required, include a safe migration plan (new table + backfill + cutover).
    - (B) **Declare dossier outdated via ADR and align dossier to repo** (only if governance explicitly permits; otherwise prefer A).
- **Acceptance**:
  - P03 error handling can record a DLQ entry that includes pipeline_id, phase, payload_json, error_type/code/message, attempts, and status.
  - Retry scans can efficiently query pending work via the dossier’s indexes (or the explicitly decided alternative).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.4)
  - Existing migration: `k0/db/alembic/versions/0009_st_dlq.py`
  - Existing driver: `k0/storage/dlq.py`

---

## Milestone 3 — End-to-end wiring: DB ↔ outbox ↔ bus

### Epic 3.1 — Outbox writer + publisher

> **Scope note (avoid confusion)**:

> - Epic 3.1 covers the **transactional outbox write path** (R7 writes staged via `UnitOfWork.stage_outbox`) and the **publisher / drain loop** that delivers staged entries to the bus.
> - Epic 3.1 also covers emission of the **`p03.consolidation.complete.v1`** cycle-summary event at the end of R8.
> - Epic 3.1 does **not** cover consumption of external events or pipelines (that is Epic 3.2).
> - K0 repo reality: `k0/uow/unit_of_work.py` already provides `stage_outbox()` + auto-flush on commit, and `k0/storage/outbox.py` provides `OutboxStore`. Verify dossier alignment, then extend/integrate rather than duplicate.

#### Issue 3.1.1 — Verify K0 UnitOfWork + OutboxStore alignment with dossier transactional-outbox pattern (Sections 4.8.1, D.7.1, 6.15)

- **Goal**: Confirm that the existing K0 outbox wiring (UnitOfWork + OutboxStore) supports the dossier's R7 atomic-write semantics, and document any gaps that need corrective work.
- **Deliverables**:
  - A comparison table (in this ticket) with:
    - dossier expectation (Section 4.8.1, D.7.1, 6.15),
    - K0 reality (`k0/uow/unit_of_work.py`, `k0/storage/outbox.py`, `k0/db/alembic/versions/0008_st_outbox.py`),
    - status: **ALIGNED** or **GAP**.
  - If any GAP is found:
    - small gaps → file a follow-on corrective issue in this epic,
    - design-level gaps → escalate to ADR.
- **Acceptance**:
  - Table explicitly confirms or denies:
    - outbox entries are written inside the same Postgres transaction as truth writes,
    - commit failure rolls back outbox entries,
    - `stage_outbox()` accepts the fields required by `st_outbox` (Section 6.15).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.1 "Outbox Pattern Implementation")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.7.1 "UnitOfWork Pattern")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.15 "`st_outbox`")
  - K0:
    - `k0/uow/unit_of_work.py` (`stage_outbox`, `_flush_outbox`, `_commit`)
    - `k0/storage/outbox.py` (`OutboxStore.enqueue`, `OutboxEntry`)
    - `k0/db/alembic/versions/0008_st_outbox.py`

#### Issue 3.1.2 — Implement P03 TruthWriter orchestration (R7) integrating UnitOfWork.stage_outbox for durable event staging (Section 4.8, D.7.1)

- **Goal**: Ensure R7's truth-layer writes (st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges, st_vec, st_hipp_events) and corresponding bus-event staging are atomic within a single UnitOfWork scope.
- **Deliverables**:
  - P03 `TruthWriter` module (or equivalent orchestrator) that:
    - opens a UnitOfWork via `context.syscalls.unit_of_work()` (or explicit K0 factory),
    - inserts/updates all staged truth-layer rows,
    - stages outbox entries for each emittable event type (e.g., `p03.truth.created.v1`, `p03.pattern.detected.v1`, etc.) using `uow.stage_outbox(OutboxEntry(...))`,
    - commits (success) or rolls back (failure) atomically.
  - Idempotency key pattern: `p03:r7:{cycle_ulid}:{table}:{record_id}` (per dossier Appendix G R7).
- **Acceptance**:
  - A commit includes both truth rows **and** staged outbox entries in the same Postgres transaction.
  - A transaction failure leaves no orphan outbox entries.
  - Integration test proves atomicity (fail mid-write → nothing persisted).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.7.1)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G "R7 Truth Writer")
  - K0:
    - `k0/uow/unit_of_work.py`
    - `k0/storage/outbox.py`

#### Issue 3.1.3 — Implement / integrate OutboxPublisher (drain loop) for P03 with retry + backoff semantics (Sections 4.8.1, 13.5, D.6.2)

- **Goal**: Deliver staged outbox entries to the K0 bus with at-least-once semantics and bounded retries, using K0's established retry infrastructure.
- **Deliverables**:
  - Either:
    - (A) Reuse an existing K0 outbox publisher / driver worker pool if it already provides compatible semantics, **or**
    - (B) Implement a P03-specific drain loop that:
      - calls `OutboxStore.dequeue_ready_batch(driver="p03", ...)` (respects `next_attempt_ts` backoff),
      - publishes each entry to the bus via `BusDispatcher.dispatch(...)`,
      - marks entries as delivered via `OutboxStore.mark_applied(...)`,
      - on failure: updates `retries`, computes `next_attempt_ts` using exponential backoff (per Section 13.5 / K0 RetryScheduler), and requeues.
  - DLQ escalation: after max retries exceeded (per-driver config, default 3), move entry to DLQ (`st_dlq`) with status `ABANDONED`.
  - Idempotency at the publisher level: outbox entries carry `fingerprint`; duplicate deliveries are safe if consumer is idempotent (document expectation).
- **Acceptance**:
  - Under normal operation, staged events reach the bus.
  - Under transient bus failure, events are retried according to exponential backoff (verify via test).
  - After exhausting retries, event is visible in `st_dlq` with appropriate error context.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.1, 13.5 "Retry Strategy (K0 RetryScheduler)")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.6.2 "Event Emission Pattern")
  - K0:
    - `k0/storage/outbox.py` (`dequeue_ready_batch`, `mark_applied`, `schedule_retry`)
    - `k0/outbox/scheduler.py` (if it exists; otherwise design as part of this issue)
    - `k0/bus/core.py` (`BusDispatcher`)
    - `k0/storage/dlq.py`

#### Issue 3.1.4 — Define and register `p03.consolidation.complete.v1` event schema + payload builder (Sections 9.6.1, D.6.3)

- **Goal**: Codify the canonical schema for the cycle-completion event so producers and consumers share a validated contract.
- **Deliverables**:
  - Pydantic / dataclass model (per dossier's D.6.3 patterns) for `P03ConsolidationCompletePayload` with fields:
    - `cycle_id`, `tenant_id`, `space_id`, `status` (SUCCESS | PARTIAL | FAILED), `summary` object (events_processed, clusters_created, duplicates_found, entities_created, edges_created, gaps_detected, decisions breakdown), `duration_ms`, `completed_at`.
  - Define the machine-readable JSON schema in `k0/contracts/schemas/p03_consolidation_complete.json` and reference it from the governance event registry (Part 4.1 + Part 5.3).
  - A builder helper used by R8 to construct the payload from `ConsolidationCycleResult`.
- **Acceptance**:
  - Payload builder produces valid JSON that passes schema validation.
  - Schema is discoverable by downstream consumers (P04, monitoring).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.6.1 "Consolidation Complete: p03.consolidation.complete.v1")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.6.3 "Topic Schema Contracts")

#### Issue 3.1.5 — Implement R8 event emission logic (stage completion event + gaps via outbox, drain to bus) (Sections 4.9, D.6.2, Appendix G R8)

- **Goal**: At the end of each consolidation cycle, emit `p03.consolidation.complete.v1` (and any per-gap `p03.gap.detected.v1` events) durably via the outbox pattern.
- **Deliverables**:
  - R8 phase implementation (in P03 runner) that:
    - builds `P03ConsolidationCompletePayload` from cycle results,
    - stages it via `uow.stage_outbox(...)` (or direct `OutboxStore` call if outside transaction),
    - for each gap candidate (from R4/R5), stages a `p03.gap.detected.v1` entry.
  - The stage → drain → bus path established in Issue 3.1.3 handles actual delivery.
  - Idempotency key pattern: `p03:r8:{cycle_ulid}:{topic}:{offset}` (per dossier Appendix G R8).
- **Acceptance**:
  - After a successful cycle, `p03.consolidation.complete.v1` is observable on the bus.
  - Gaps detected during the cycle appear as `p03.gap.detected.v1` events.
  - Metric counters (`p03_r8_events_emitted`, `p03_r8_gaps_detected`) are incremented.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.9 "R8 — Event Emission & Completion")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.6.2)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G "R8: Event Emission (EMIT)")

#### Issue 3.1.6 — Integration tests for atomic outbox + truth write (R7) and bus delivery (R8)

- **Goal**: Prove end-to-end correctness of the outbox path with deterministic assertions.
- **Deliverables**:
  - Test: mid-transaction failure rolls back both truth rows and outbox entries (no leakage).
  - Test: successful commit results in outbox entries; publisher drains them and events appear on a mock/in-memory bus.
  - Test: publisher retries on transient failure; after exhaustion, entry lands in DLQ.
  - Test: `p03.consolidation.complete.v1` payload matches registered schema.
- **Acceptance**:
  - All tests pass; coverage includes happy path + failure path.
  - No flaky timing issues (use deterministic test fixtures).
- **References**:
  - Existing K0 test patterns:
    - `tests/k0/uow/test_unit_of_work.py`
    - `tests/k0/storage/test_outbox_async.py`

### Epic 3.2 — Cross-pipeline integration (P02/P05/P06/P08/P21)

> **Scope note (avoid confusion)**:

> - Epic 3.2 covers the **cross-pipeline integration surfaces** where P03 consumes from, coordinates with, or publishes to other pipelines.
> - Integration patterns:
>   - **P02→P03**: P03 polls `st_hipp_events` by offset; marks consolidation status post-processing.
>   - **P03→P06**: P03 emits `p03.gap.detected.v1` bus events and persists to `st_learning_queue`.
>   - **P03↔P05**: P03 queries token budget and actor availability; may degrade or pause on exhaustion.
>   - **P03→P08**: P03 notifies P08 of new embeddings; sync/async modes with circuit breaker fallback.
>   - **P21→P03**: P03 subscribes to `feedback.signal.p03.v1`; marks `st_feedback_signals` as consumed.
> - Epic 3.2 does **not** cover the internal outbox/event-emission logic (that is Epic 3.1).
> - K0 repo reality: `k0/storage/offsets.py` provides `OffsetStore` for cursor tracking; `k0/bus/core.py` provides subscription. Circuit breaker patterns are dossier-specified but not yet implemented in K0; identify as gap if needed.

#### Issue 3.2.1 — Implement P02→P03 ingestion: offset-based polling of `st_hipp_events` (Sections 9.2, 4.1)

- **Goal**: P03 reliably reads events staged by P02, respecting prior offset and updating offset after successful processing.
- **Deliverables**:
  - `P03EventIngestion` module (or integration in R0 phase) that:
    - fetches current P03 subscriber offset from `OffsetStore` (subscriber_id="p03_consolidation", topic="st_hipp_events"),
    - queries `st_hipp_events` WHERE `event_id > :last_offset` AND `consolidation_status IS NULL OR = 'PENDING'` AND `embedding_status = 'READY'` (per Section 9.2.1),
    - passes batch to R1+.
  - After R8 completes (per-cycle), update offset via `OffsetStore.upsert(...)` with the highest processed `event_id`.
  - Idempotency: if cycle fails mid-way, offset is NOT advanced; next run re-processes the same batch.
- **Acceptance**:
  - P03 only processes events newer than last committed offset.
  - Offset advances only after R8 commits (all-or-nothing semantics).
  - Integration test: inject events, run cycle, verify offset advanced; inject failure mid-cycle, verify offset unchanged.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.2 "P02 → P03 Contract")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.1 "R0 — Batch Selection & Context Hydration")
  - K0:
    - `k0/storage/offsets.py` (`OffsetStore.fetch`, `OffsetStore.upsert`)
    - `k0/db/alembic/versions/0003_st_hipp_events.py` (or latest migration)

#### Issue 3.2.2 — Implement P02→P03 status writeback: mark `st_hipp_events.consolidation_status` after processing (Section 4.9, 6.10)

- **Goal**: After R7/R8 completes, update `st_hipp_events` rows with their final consolidation outcome (CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW).
- **Deliverables**:
  - A status writeback helper (in TruthWriter or R6 phase) that:
    - for each processed event, sets `consolidation_status` to the appropriate enum value,
    - sets `consolidated_at` timestamp,
    - optionally sets `consolidated_by = 'P03:{cycle_id}'`.
  - Writeback is inside the same UnitOfWork scope as R7 truth writes (atomic with truth layer inserts).
- **Acceptance**:
  - Querying `st_hipp_events WHERE consolidation_status IS NULL` excludes all processed events.
  - Status values match dossier enum (CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW).
  - Failure rolls back both truth writes AND status updates (no orphan states).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.9 "R8 — Event Emission & Completion")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.10 "`st_hipp_events` consolidation fields")
  - K0:
    - `k0/db/alembic/versions/0003_st_hipp_events.py` (consolidation_status column)

#### Issue 3.2.3 — Implement P03→P06 integration: emit `p03.gap.detected.v1` + persist to `st_learning_queue` (Sections 9.3, 6.11)

- **Goal**: When P03 detects a knowledge gap (ambiguous entity, low-confidence edge, contradiction, etc.), emit to the bus and persist a durable queue record for P06 active learning.
- **Deliverables**:
  - `GapEmitter` module that:
    - constructs `GapDetectedPayload` per Section 9.3.1 schema (gap_id, tenant_id, space_id, gap_type, importance_score, context, ttl_hours, detected_at),
    - stages outbox entry via `uow.stage_outbox(...)` (Topic: `familyos.p03.gaps` / `p03.gap.detected.v1`),
    - inserts a corresponding row into `st_learning_queue` with status=PENDING (per Section 6.11).
  - Gap types supported: AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE, MISSING_ATTRIBUTE, CONTRADICTION, CONCEPT_DRIFT, STRUCTURAL_HOLE, STALE_ANCHOR.
  - Idempotency: gap_id is deterministic (e.g., `p03:gap:{cycle_id}:{source_event_id}:{gap_type}`); duplicate inserts are rejected by unique index.
- **Acceptance**:
  - Gaps appear on the bus topic `familyos.p03.gaps` (or configured topic name).
  - `st_learning_queue` contains a matching row with `gap_id`, `gap_type`, `importance_score`, `status='PENDING'`.
  - Metric counters (`p03_gaps_emitted_total`, `p03_gaps_by_type`) are incremented.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.3 "P03 → P06 Contract (Active Learning)")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.11 "`st_learning_queue`")

#### Issue 3.2.4 — Implement P03↔P05 budget client: query token budget + availability before gap emission (Sections 9.5, 15.2)

- **Goal**: Before emitting user-facing gaps (clarification questions), P03 checks P05 attention budget and actor availability to avoid over-prompting.
- **Deliverables**:
  - `P05BudgetClient` integration module that:
    - implements `query_token_budget(actor_id, tenant_id)` per Section 9.5.2 contract,
    - implements `query_availability(actor_id, tenant_id, space_id, question_type)` per Section 9.5.1 contract,
    - returns structured response (tokens_remaining, is_available, rejection_reason).
  - Degradation behavior when budget exhausted:
    - if `tokens_remaining == 0` or `is_available == False`: suppress gap emission, increment `p03_gaps_suppressed_budget` metric, optionally queue gap for later retry.
  - Failure behavior when P05 unavailable:
    - configurable: DEGRADE (emit anyway with warning) or STOP (fail cycle with retriable error).
- **Acceptance**:
  - Gap emission respects token budget (no emission if budget=0).
  - Availability check respects DND_MODE, BUDGET_EXHAUSTED, RATE_LIMITED, OFFLINE.
  - Integration test: mock P05 returning budget=0 → verify gap NOT emitted.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.5 "P03 ↔ P05 Attention Contract")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.2 "K0 Scheduler Integration")

#### Issue 3.2.5 — Implement P03→P08 embedding coordination: sync/async notification + circuit breaker (Sections 9.4, 13.6)

- **Goal**: When P03 creates or updates embeddings (in st_vec), notify P08 so it can update FAISS indexes; support sync and async modes with circuit-breaker protection.
- **Deliverables**:
  - `P08Coordinator` integration module implementing the Section 9.4.2 protocol:
    - `notify_embedding_created(embedding, config: P08CoordinationConfig)` with SYNC / ASYNC mode.
    - SYNC mode: publish to `familyos.p03.embeddings`, wait for ack from `familyos.p08.embedding.indexed.v1` with timeout.
    - ASYNC mode: batch embeddings, flush periodically (batch_size + flush_interval per config).
  - Circuit breaker wrapping P08 calls (per Section 13.6):
    - failure_threshold: 5 consecutive failures → OPEN state
    - reset_timeout_seconds: 60 → HALF_OPEN → probe
    - when OPEN: skip P08 notification, log warning, increment `p03_p08_circuit_open` counter.
  - Failure policy (configurable):
    - DEGRADE: proceed with cycle even if P08 unreachable (embeddings indexed later),
    - STOP: fail cycle with retriable error.
- **Acceptance**:
  - In SYNC mode, cycle blocks until P08 ack or timeout.
  - In ASYNC mode, embeddings are batched and flushed; eventual consistency is acceptable.
  - Circuit breaker opens after 5 failures; reopens after 60s half-open probe.
  - Metrics: `p03_p08_notifications_total`, `p03_p08_ack_latency_ms`, `p03_p08_circuit_state`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.4 "P03 → P08 Contract (Embedding Index)")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.6 "Circuit Breakers")

#### Issue 3.2.6 — Implement P21→P03 feedback consumption: subscribe to `feedback.signal.p03.v1` + mark consumed (Sections 9.8, 6.9)

- **Goal**: P03 consumes feedback signals dispatched by P21, routes them to the appropriate learning module, and marks them consumed in `st_feedback_signals`.
- **Deliverables**:
  - `P03FeedbackConsumer` module that:
    - subscribes to bus topic `feedback.signal.p03.v1` (or `feedback.signal.p03`) during pipeline init,
    - receives `FeedbackEnvelope` payloads validated by P21,
    - routes payload to appropriate handler based on `feedback_type`:
      - SALIENCE_ADJUSTMENT → ImportanceLearner (M2)
      - DECAY_REVERSAL → DecayLearner (M3)
      - CLUSTER_CORRECTION → SimilarityLearner (M4)
      - REINFORCEMENT_OUTCOME → HebbianLearner (M4)
      - NOVELTY_SIGNAL → AuditLogger (M1)
      - REGRET_SIGNAL → RegretLearner (M6)
    - marks signal consumed via: `UPDATE st_feedback_signals SET consumed_at=..., consumed_by='P03' WHERE signal_id=...`.
  - Idempotency: if signal already consumed (consumed_at IS NOT NULL), skip processing.
- **Acceptance**:
  - Feedback signals with `target_pipeline='P03'` are processed and marked consumed.
  - Routing coverage: all 6 feedback types have handlers (even if stub).
  - Integration test: emit mock feedback → verify consumed_at populated, handler invoked.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.8 "P21 Feedback Integration")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.9 "`st_feedback_signals` consumption fields")
  - K0:
    - `k0/bus/core.py` (subscription API)
    - Existing migration: `k0/db/alembic/versions/0026_st_feedback_signals.py`

#### Issue 3.2.7 — Integration tests for cross-pipeline contracts (P02, P05, P06, P08, P21)

- **Goal**: Prove end-to-end correctness of all cross-pipeline integration points with deterministic assertions.
- **Deliverables**:
  - Test: P02→P03 offset-based ingestion (new events processed, offset advanced).
  - Test: P03→P06 gap emission (bus event + `st_learning_queue` row).
  - Test: P03↔P05 budget check (budget exhausted → gap suppressed).
  - Test: P03→P08 circuit breaker (5 failures → OPEN state, skip notification).
  - Test: P21→P03 feedback consumption (signal received → routed → marked consumed).
- **Acceptance**:
  - All tests pass; coverage includes happy path + failure / degradation paths.
  - No flaky timing issues (use deterministic test fixtures or controlled mocks).
- **References**:
  - Existing K0 test patterns:
    - `tests/k0/storage/test_offsets.py`
    - `tests/k0/bus/test_subscription.py`

---

## Milestone 4 — Implement R1–R4 core cognition

### Epic 4.1 — R1 ReplayCoordinator (importance + hebbian)

> **Scope note (avoid confusion)**:

> - Epic 4.1 covers the **R1 Hippocampal Replay phase** (NREM1 analog): importance scoring, batch selection, and association strengthening (Hebbian learning).
> - Module: M23 ReplayCoordinator
> - Key tables: reads `st_hipp_events`, updates `st_kg_edges` (Hebbian), persists to `st_learned_weights` (importance weights).
> - Epic 4.1 does **not** cover episodic clustering (R2, Epic 4.2), duplicate detection (R3, Epic 4.3), or KG consolidation (R4, Epic 4.4).
> - Dossier references: Sections 4.2, 2.4 (formulas), Appendix C.2 (algorithms), Section 7.4.6 (M23 module).

#### Issue 4.1.1 — Implement ImportanceScorer with weighted-sum formula (Section 4.2.2, Appendix C.2.1)

- **Goal**: Compute importance scores for hippocampal events to prioritize which memories get consolidated.
- **Deliverables**:
  - `ImportanceScorer` class implementing the dossier formula (Section 2.4):

    ```
    importance = (
        0.35 × |sentiment| × |affect_valence| × (1 + affect_arousal)
      + 0.25 × exp(-λ_recency × days_since)
      + 0.20 × log(1 + access_count) / log(10)
      + 0.20 × participant_count × avg_relationship_strength
    )
    ```

  - Configurable weights (default: 0.35/0.25/0.20/0.20) loaded from `st_learned_weights` with fallback to static priors.
  - Event-type multipliers: photo=1.2, milestone=2.0, routine=0.5 (per Appendix C.2.1).
  - Batch selection: `select_batch(events, batch_size)` returns top-N by importance.
- **Acceptance**:
  - High-emotion, high-novelty events rank higher than mundane events.
  - Score normalized to [0.0, 1.0].
  - Component breakdown logged to `st_consolidation_audit` for factor audit.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.2.2)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 2.4 "Scientific Formulas")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.2.1 "Importance Scoring Algorithm")

#### Issue 4.1.2 — Implement factor audit logging for importance scoring (st_consolidation_audit)

- **Goal**: Persist per-event importance component breakdown for debugging, learning, and observability.
- **Deliverables**:
  - On each `compute_importance_score()` call, capture:
    - `emotional_component`, `recency_component`, `frequency_component`, `social_component`
    - `event_type_multiplier`, `final_score`
  - Insert row into `st_consolidation_audit` with `audit_type='IMPORTANCE_SCORE'`.
  - Sampling config: log 100% in debug mode, 10% in production (configurable).
- **Acceptance**:
  - Audit rows are queryable for post-hoc analysis of scoring behavior.
  - Production logging does not impact P03 cycle latency (<1ms overhead).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.2.1 "OUTPUTS" section)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.19 "`st_consolidation_audit`")

#### Issue 4.1.3 — Implement HebbianLearner: co-occurrence extraction + edge weight updates (Appendix C.2.2)

- **Goal**: Strengthen knowledge graph edges between entities that frequently co-occur ("cells that fire together, wire together").
- **Deliverables**:
  - `HebbianLearner` class implementing:
    - `extract_cooccurrences(event)` → List[(source_id, target_id, relation_type)] for actor-actor, actor-location, actor-topic pairs.
    - `update_edge_weight(current_weight, current_count, event_importance)` → new_weight with soft saturation formula:

      ```
      delta = learning_rate × (max_weight - current_weight) × event_importance
      new_weight = current_weight + delta
      ```

    - `process_batch(events)` → Dict of edge updates to apply.
  - Batch SQL updates to `st_kg_edges` (weight, co_occurrence_count, last_updated_at).
  - New edges created with initial weight = `learning_rate × avg_importance`.
- **Acceptance**:
  - Entities appearing together in events have their edge weight increased.
  - Soft saturation prevents weight exceeding 1.0.
  - Edges below `min_weight=0.01` are pruned (archived).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.2.3 "Association Strengthening")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.2.2 "Hebbian Learning Algorithm")

#### Issue 4.1.4 — Implement Hebbian anti-decay and edge normalization (Appendix C.2.2.1, C.2.2.5)

- **Goal**: Weaken wrong associations (anti-Hebbian) and ensure consistent weight interpretation [0.0, 1.0].
- **Deliverables**:
  - Anti-Hebbian decay: apply negative delta on conflict signals:
    - ENTITY_MERGE_REJECTED: -0.2
    - ASSOCIATION_WRONG: -0.3
    - MUTUAL_EXCLUSION: -0.4
    - CONTRADICTION: -0.15
  - Formula: `Δw = -anti_lr × current_weight × confidence × penalty` (anti_lr=0.15).
  - Weight normalization: hard clamp to [0.0, 1.0] after every update.
  - Prune edges where weight < 0.01 → set `archival_status='ARCHIVED'`.
- **Acceptance**:
  - Conflict signals reduce edge weights.
  - All edge weights remain in [0.0, 1.0].
  - Metrics: `p03_hebbian_weight_distribution` histogram.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.2.2.1 "Anti-Hebbian Decay")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.2.2.5 "Weight Normalization")

#### Issue 4.1.5 — Implement closed-loop importance weight learning (gradient descent + softmax) (Section 4.2.2.1)

- **Goal**: Transform static importance weights into learnable parameters based on actual memory grounding outcomes.
- **Deliverables**:
  - `ImportanceWeightLearner` class that:
    - collects ground truth from `st_feedback_signals` (MEMORY_GROUNDED = positive, MEMORY_RECALLED_NOT_USED = negative),
    - computes gradient descent updates on weight vector (learning_rate configurable),
    - applies softmax normalization to ensure weights sum to 1.0,
    - persists updated weights to `st_learned_weights` with versioning.
  - Nightly batch training job (or end-of-cycle incremental update).
  - Momentum smoothing: `w_new = β × w_old + (1-β) × w_adjusted` (β=0.9).
  - Bounds enforcement: clamp each weight to [0.05, 0.60].
- **Acceptance**:
  - Learned weights adapt to user's actual memory usage patterns.
  - Weights remain interpretable and bounded.
  - Rollback trigger: 3 consecutive nights with increasing loss → revert to prior version.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.2.2.1 "Closed-Loop Importance Learning")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.2.1.1 "ImportanceWeightLearner")

#### Issue 4.1.6 — Implement cold start strategy for importance weights (500-sample threshold + fallback hierarchy) (Section 4.2.2.2)

- **Goal**: Ensure graceful behavior for new spaces that lack learned weights.
- **Deliverables**:
  - Cold start fallback hierarchy:
    1. Per-space learned weights (if `sample_count >= 500`)
    2. Global learned weights (if per-space insufficient)
    3. Static priors (hardcoded: 0.35/0.25/0.20/0.20)
  - Progressive blending for 100 ≤ samples < 500:

    ```
    α = sample_count / 500
    weight = α × w_learned + (1-α) × w_static
    ```

  - Config: `P03_IMPORTANCE_MIN_SAMPLES = 500` (adjustable).
- **Acceptance**:
  - New spaces use static priors without error.
  - Spaces with partial data smoothly blend toward learned weights.
  - Gauge: `p03_importance_cold_start_spaces` tracks spaces using fallback.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.2.2.2 "Cold Start Strategy")

#### Issue 4.1.7 — R1 metrics: importance distribution, hebbian update counts, learning budget hooks (Section 8.2)

- **Goal**: Instrument R1 phase with observability metrics.
- **Deliverables**:
  - Metrics:
    - `p03_importance_score_distribution` (histogram): distribution of importance scores per batch.
    - `p03_importance_weight_drift` (gauge): max absolute change in any weight.
    - `p03_importance_sample_count` (gauge): number of feedback samples used for training.
    - `p03_hebbian_edges_updated` (counter): edges strengthened per cycle.
    - `p03_hebbian_edges_created` (counter): new edges created per cycle.
    - `p03_hebbian_edges_pruned` (counter): edges archived due to decay.
    - `p03_hebbian_weight_distribution` (histogram): distribution of edge weights.
  - Learning budget tracking hook: emit `p03_r1_learning_time_ms` to ensure <5% of cycle time.
- **Acceptance**:
  - Metrics are emitted via K0 observability layer.
  - Dashboards can visualize importance and hebbian trends.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2 "Metrics Reference")

#### Issue 4.1.8 — Unit + integration tests for R1 ReplayCoordinator

- **Goal**: Prove correctness of importance scoring and Hebbian learning.
- **Deliverables**:
  - Test: high-emotion event scores higher than low-emotion event.
  - Test: recency decay formula produces expected curve.
  - Test: co-occurrence of entities increases edge weight.
  - Test: anti-Hebbian signal decreases edge weight.
  - Test: cold start fallback returns static priors for new space.
  - Test: softmax normalization ensures weights sum to 1.0.
  - Integration test: full R1 phase processes batch and produces expected outputs.
- **Acceptance**:
  - All tests pass; coverage includes formula edge cases.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

### Epic 4.2 — R2 Episodic clustering (DBSCAN + adaptive params)

> **Scope note (avoid confusion)**:

> - Epic 4.2 covers the **R2 Neocortical Integration phase** (NREM2 analog): episodic clustering using DBSCAN on UltraBERT embeddings.
> - Module: M18 EpisodicIntegrator
> - Key tables: reads `st_hipp_events` + `st_vec`, outputs staged episode candidates (R6 writes to `st_epi`).
> - Epic 4.2 does **not** cover duplicate detection (R3, Epic 4.3), KG consolidation (R4, Epic 4.4), or truth writes (R7, Epic 5.2).
> - Dossier references: Sections 4.3, Appendix C.3 (algorithms), Section 7.4.2 (M18 module).

#### Issue 4.2.1 — Implement composite distance function (semantic + temporal) for DBSCAN (Section 4.3.1, Appendix C.3)

- **Goal**: Define the distance metric for clustering events into episodes.
- **Deliverables**:
  - `CompositeDistance` class implementing:

    ```
    distance = (1 - temporal_weight) × cosine_distance(emb_a, emb_b)
             + temporal_weight × normalized_time_distance(ts_a, ts_b)
    ```

  - `cosine_distance` computed from `st_vec` embeddings (768-dim UltraBERT).
  - `normalized_time_distance` = `abs(ts_a - ts_b) / max_time_gap` (capped at 1.0).
  - Configurable `temporal_weight` (default: 0.3) loaded from `st_learned_weights`.
- **Acceptance**:
  - Events close in semantic space AND time cluster together.
  - Distance values in [0.0, 2.0] (sum of two [0,1] components).
  - Config: `P03_DBSCAN_TEMPORAL_WEIGHT = 0.3`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.3.1)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.3.1 "DBSCAN")

#### Issue 4.2.2 — Implement pre-clustering episode split (time gaps, location, activity) (Appendix C.3.1.1)

- **Goal**: Split long event sequences BEFORE DBSCAN to prevent cross-activity clusters.
- **Deliverables**:
  - `EpisodeSplitter.split_long_sequences(events)` that detects breaks via:
    1. Location change (geohash prefix differs by >4 chars)
    2. Activity type change
    3. Time gap > 30 minutes
    4. Hard limit: episode > 4 hours
  - Returns List[List[HippEvent]] — each sub-sequence becomes DBSCAN input.
- **Acceptance**:
  - Morning gym + afternoon meeting are split into separate sequences.
  - Silhouette score improves from ~0.3 to >0.5 for multi-activity days.
  - Metrics: `p03_episode_splits_total`, `p03_episode_split_by_type`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.3.1.1 "Pre-Clustering Episode Split")

#### Issue 4.2.3 — Implement DBSCAN clustering with configurable eps/min_samples (Section 4.3.1)

- **Goal**: Cluster hippocampal events into coherent episodes using density-based clustering.
- **Deliverables**:
  - `EpisodicDBSCAN` class wrapping scikit-learn DBSCAN with:
    - `eps` parameter (default: 0.25) loaded from `st_learned_weights`
    - `min_samples` parameter (default: 2) loaded from `st_learned_weights`
    - custom distance metric (Issue 4.2.1)
  - Output: List of clusters, each containing event_ids + centroid embedding.
  - Noise handling: singleton events (cluster=-1) marked as `is_noise=True`.
- **Acceptance**:
  - Semantically similar, temporally proximate events cluster together.
  - Silhouette score > 0.5 (per ADR k003.3).
  - Config: `P03_DBSCAN_EPS_DEFAULT = 0.25`, `P03_DBSCAN_MIN_SAMPLES_DEFAULT = 2`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.3.1)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.3.1)

#### Issue 4.2.4 — Write episode candidates to staged writes container (not DB yet)

- **Goal**: Collect R2 clustering outputs into a staging container for later R7 commit.
- **Deliverables**:
  - `StagedWrites` container (or `ConsolidationManifest`) that accumulates:
    - `EpisodeCandidate` objects with: cluster_id, event_ids, centroid_embedding, temporal_bounds, confidence_score.
  - No DB write in R2 — staged writes are passed to R6/R7.
  - Manifest includes metadata: cluster_count, noise_count, avg_cluster_size.
- **Acceptance**:
  - R2 produces in-memory candidates; R7 commits them atomically.
  - Staged writes can be inspected/validated before commit.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.7 "R6 — Status Marking")

#### Issue 4.2.5 — Implement adaptive eps learning (silhouette-driven adjustment) (Section 4.3.1.1)

- **Goal**: Tune `eps` per-space based on cluster quality feedback.
- **Deliverables**:
  - After each cycle, compute silhouette score for generated clusters.
  - Adjustment rules:
    - silhouette < 0.5 AND avg_cluster_size > 10 → decrease eps by 0.02 (too loose)
    - silhouette < 0.5 AND singleton_rate > 0.20 → increase eps by 0.02 (too tight)
  - Momentum smoothing: `eps_new = 0.9 × eps_old + 0.1 × eps_adjusted`.
  - Bounds enforcement: `eps ∈ [0.15, 0.40]`.
  - Persist updated eps to `st_learned_weights` (param_key: `dbscan_eps`, scope: space).
- **Acceptance**:
  - Per-space eps converges to value achieving silhouette > 0.5.
  - Gauge: `p03_dbscan_eps_current`, `p03_dbscan_silhouette`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.3.1.1 "Adaptive Eps Learning")

#### Issue 4.2.6 — Implement adaptive min_samples learning (singleton-rate driven) (Appendix C.3.1.2)

- **Goal**: Tune `min_samples` per-space based on noise level.
- **Deliverables**:
  - After each cycle, compute singleton_rate (% of events in cluster=-1).
  - Adjustment rules:
    - singleton_rate > 0.20 → increase min_samples by 1 (max 5)
    - singleton_rate < 0.05 → decrease min_samples by 1 (min 2)
  - Persist updated min_samples to `st_learned_weights` (param_key: `dbscan_min_samples`).
- **Acceptance**:
  - Noisy spaces get higher min_samples to reduce micro-episodes.
  - Sparse spaces get lower min_samples to allow clustering.
  - Gauge: `p03_dbscan_min_samples_current`, `p03_dbscan_singleton_rate`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.3.1.2 "Adaptive Min_samples")

#### Issue 4.2.7 — Implement closed-loop cluster quality metrics (silhouette, grounding, correction, singleton rates)

- **Goal**: Track cluster quality for adaptive learning and observability.
- **Deliverables**:
  - Compute after each R2 phase:
    - `silhouette_score`: sklearn silhouette on embeddings (target > 0.5)
    - `grounding_rate`: % of clusters used in P04 queries within 7 days
    - `correction_rate`: % of clusters receiving CLUSTER_CORRECTION feedback
    - `singleton_rate`: % of events not assigned to any cluster
  - Persist quality snapshot to `st_consolidation_audit` with `audit_type='CLUSTER_QUALITY'`.
  - Emit metrics for dashboards.
- **Acceptance**:
  - Quality metrics are tracked per-space over time.
  - Degradation triggers alerts (silhouette < 0.3 for 3 consecutive cycles).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.3.1.1)
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2 "Clustering metrics")

#### Issue 4.2.8 — Unit + integration tests for R2 Episodic clustering

- **Goal**: Prove correctness of DBSCAN clustering and adaptive parameter learning.
- **Deliverables**:
  - Test: semantically similar events cluster together.
  - Test: events with large time gap are split before clustering.
  - Test: location change triggers pre-split.
  - Test: silhouette < 0.5 triggers eps adjustment.
  - Test: singleton_rate > 0.20 triggers min_samples adjustment.
  - Test: staged writes contain expected cluster structure.
  - Integration test: full R2 phase produces valid episode candidates.
- **Acceptance**:
  - All tests pass; coverage includes edge cases (empty batch, all noise, single event).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

### Epic 4.3 — R3 Duplicate detection + retention/decay

> **Scope note (avoid confusion)**:
>
> - Epic 4.3 covers the **R3 Synaptic Homeostasis phase** (SWS analog): duplicate detection, decay computation, and pruning decisions.
> - Modules: M19 DuplicateDetector, M20 RetentionEnforcer
> - Key tables: reads `st_hipp_events`, updates `archival_status` / `decay_factor` across all memory tables, writes to `st_pruned_entities`.
> - Epic 4.3 does **not** cover KG consolidation (R4, Epic 4.4), or truth writes (R7, Epic 5.2).
> - Dossier references: Sections 4.4, 2.4 (formulas), Appendix C.4 (algorithms), Section 7.4.2-7.4.3 (M19/M20 modules).

#### Issue 4.3.1 — Implement SimHash fingerprinting with per-content-type thresholds (Appendix C.4.1, C.4.1.1)

- **Goal**: Fast syntactic duplicate detection using 64-bit locality-sensitive hashing.
- **Deliverables**:
  - `SimHasher` class implementing:
    - `tokenize(text)`: Extract 3-gram shingles from event body.
    - `compute_simhash(text)`: Compute 64-bit SimHash signature.
    - `hamming_distance(hash1, hash2)`: Count differing bits.
    - `is_near_duplicate(hash1, hash2, content_type)`: Check distance ≤ threshold.
  - Per-content-type threshold matrix (from Appendix C.4.1.1):
    - TRANSACTION=1, CALENDAR_EVENT=2, CONTACT_UPDATE=2, CHAT_MESSAGE=3, PHOTO_CAPTION=4, JOURNAL_ENTRY=4, VOICE_MEMO=5
  - Store `simhash_hex` (16-char hex) in `st_hipp_events`.
- **Acceptance**:
  - "I ate pizza" vs "I ate pizza" → distance=0 (exact duplicate).
  - Thresholds loaded from `st_learned_weights` or fallback to static matrix.
  - Metrics: `p03_simhash_threshold_current`, `p03_simhash_hamming_distance` histogram.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.4.1 "SimHash")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.4.1.1 "Content-Type Thresholds")

#### Issue 4.3.2 — Implement two-stage deduplication pipeline (SimHash → embedding verification) (Appendix C.4.1.2)

- **Goal**: Combine fast SimHash filtering with accurate embedding verification to catch both syntactic and semantic duplicates.
- **Deliverables**:
  - `Stage1SimHashFilter.find_candidates(new_event, recent_events, threshold)`:
    - Returns List[(event_id, hamming_distance)] for events within threshold.
  - `Stage2EmbeddingVerifier.verify_duplicate(event1, event2)`:
    - Computes cosine similarity from 768-dim UltraBERT embeddings.
    - Returns (is_duplicate, similarity, decision_type): DUPLICATE (≥0.85), LIKELY_DUPLICATE (0.70-0.85), NOT_DUPLICATE (<0.70).
  - `TwoStageDeduplicator.find_duplicates(new_event, window_events)`:
    - Runs Stage 1 → Stage 2 → Fallback (embedding-only for ≥0.90 similarity).
  - Schema addition: `st_hipp_events.duplicate_check_method` (SIMHASH_ONLY, TWO_STAGE, EMBEDDING_FALLBACK).
- **Acceptance**:
  - "Had pizza for dinner" vs "Ate pizza tonight" → semantic duplicate caught by Stage 2.
  - "I ate pizza" vs "I hate pizza" → NOT_DUPLICATE (Stage 2 rejects false positive).
  - Metrics: `p03_dedup_stage1_candidates`, `p03_dedup_stage2_confirmed`, `p03_dedup_stage2_rejected`, `p03_dedup_fallback_caught`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.4.1.2 "Two-Stage Deduplication Pipeline")

#### Issue 4.3.3 — Implement UnifiedDecayEngine with per-layer lambda configuration (Section 4.4.1.1, Appendix C.4.2)

- **Goal**: Single decay engine serving all 8 memory tables with consistent exponential decay semantics.
- **Deliverables**:
  - `UnifiedDecayEngine` class wrapping `ExponentialDecayEngine` with:
    - Per-layer default λ values (from dossier table):
      - st_epi=0.005, st_sem=0.003, st_procedural=0.010, st_social=0.002, st_kg_dom=0.001, st_kg_edges=0.008, st_prospective=0.020, st_hipp_events=0.100
    - Effective lambda formula: `λ_effective = λ_base × space_modifier × entity_type_modifier × importance_modifier`.
    - `compute_decay_factor(record, table, current_time)`: Returns decay in [0.0, 1.0].
    - `classify_record(decay_factor)`: Returns ACTIVE (≥0.10), ARCHIVE_CANDIDATE (0.01-0.10), PRUNE_CANDIDATE (<0.01).
  - Schema additions (all memory tables): `access_count`, `last_accessed_at`, `resurrection_count`, `decay_immune`.
- **Acceptance**:
  - Episodic memory (λ=0.005) decays to 0.50 after ~139 days (half-life).
  - High-importance memories decay slower (importance_modifier applied).
  - Metrics: `p03_decay_factor_distribution` histogram, `p03_decay_total_active`/`archived`/`tombstoned` gauges.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.4.1.1 "Unified Decay Architecture")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.4.2 "Exponential Decay")

#### Issue 4.3.4 — Implement M20 RetentionEnforcer: archive/tombstone decisioning + resurrection (Section 7.4.3, Appendix C.4.2.1)

- **Goal**: Evaluate retention decisions and support resurrection of wrongly archived memories.
- **Deliverables**:
  - `RetentionEnforcer.evaluate(record, table)`:
    - Returns RetentionDecision: record_id, current_decay, new_decay, action (KEEP, DECAY, ARCHIVE, TOMBSTONE), reason.
    - Thresholds: ARCHIVE @ decay<0.10, TOMBSTONE @ decay<0.01.
  - `RetentionEnforcer.resurrect(entity_id, trigger_type)`:
    - Resurrection formula: `new_decay = max(0.70, 0.50 + old_decay × 0.50)`.
    - Increment `resurrection_count`; alert if ≥3 (suggests λ too aggressive).
    - Trigger types: QUERY, CO_OCCURRENCE, USER_MENTION.
  - Audit trail: log resurrection to `st_consolidation_audit` with trigger, old/new decay, resurrection_count.
- **Acceptance**:
  - Record with decay=0.05 → action=ARCHIVE.
  - Archived entity queried → resurrected to decay=0.70.
  - Metrics: `p03_resurrections_total`, `p03_resurrection_rate`, `p03_resurrection_loops`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 7.4.3 "M20 RetentionEnforcer")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.4.2.1 "Memory Resurrection")

#### Issue 4.3.5 — Implement per-entity access tracking (access_count, intervals, λ estimation) (Section 4.4.1)

- **Goal**: Track access patterns to enable adaptive per-entity decay rates.
- **Deliverables**:
  - Schema additions: `access_count`, `first_access_at`, `last_access_at`, `access_intervals_ms` (JSONB array, max 10).
  - Index: partial index on `access_count >= 5` for learning-eligible entities.
  - `AccessTracker.record_access(entity_id, timestamp)`:
    - Increment access_count, update last_access_at, append to intervals array.
  - `BayesianLambdaEstimator.estimate_lambda(entity_id)`:
    - Requires: access_count ≥ 5, spread ≥ 7 days.
    - Bayesian model: Prior λ ~ Gamma(α=2, β=2/λ_base), Posterior from inter-access intervals.
- **Acceptance**:
  - Entity accessed 5+ times → λ estimated from intervals.
  - "Mom" queried daily → λ estimate ~0.0005 (slow decay).
  - Metrics: `p03_entities_with_5plus_accesses`, `p03_access_spread_histogram`, `p03_lambda_estimation_triggered`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.4.1 "Per-Entity Access Tracking")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.4.2.2 "Adaptive Lambda Learning")

#### Issue 4.3.6 — Implement pruning regret detection + 14-day tracking window (Section 4.4.2)

- **Goal**: Detect when pruned entities are later queried ("regret") to improve decay calibration.
- **Deliverables**:
  - `st_pruned_entities` table: entity_id, canonical_name, embedding, entity_type, pruned_at, space_id.
  - `PruneRegretDetector.check_query(query_embedding)`:
    - Compare query against st_pruned_entities (cosine similarity ≥0.85 = regret).
    - Emit REGRET_SIGNAL to P21 feedback if match found.
  - `PrunedEntitiesCleanup` nightly job (2am):
    - Delete rows where `pruned_at < now - 14 days`.
  - Storage estimates: ~6MB per 1400 entities (medium space).
- **Acceptance**:
  - Pruned entity matched by query → regret signal emitted, λ adjustment triggered.
  - Entities older than 14 days auto-cleaned.
  - Metrics: `p03_pruned_entities_tracked`, `p03_prune_regrets`, `p03_regret_rate`, `p03_pruned_entities_cleaned`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.4.2 "Pruning Regret Detection")

#### Issue 4.3.7 — Implement M19 DuplicateDetector with novelty scoring (Section 7.4.2, Section 2.4)

- **Goal**: Calculate novelty scores for events to inform importance and consolidation priority.
- **Deliverables**:
  - `DuplicateDetector.detect(event, existing_hashes)`:
    - Returns DuplicationResult: is_duplicate, near_duplicates[], novelty_score, duplicate_of.
  - `DuplicateDetector._calculate_novelty_score(event, near_duplicates)`:
    - Base novelty: `1.0 - max_similarity_to_near_duplicates`.
    - Bonuses (from Section 2.4): first_occurrence=+0.15, milestone=+0.20, rare_pattern=+0.10, temporal_anomaly=+0.10.
    - Penalty: routine_activity=-0.30.
    - Clamp to [0.0, 1.0].
  - Store `novelty_score` in `st_hipp_events`.
- **Acceptance**:
  - First birthday party → novelty ~0.85 (first + milestone bonuses).
  - "Wake up 7am" on Monday → novelty ~0.20 (routine penalty).
  - Metrics: `p03_novelty_score_distribution`, `p03_novelty_bonus_applied` by type.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 7.4.2 "M19 DuplicateDetector")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 2.4 "Novelty Score formula")

#### Issue 4.3.8 — Implement adaptive novelty bonus learning (Section 4.4.2.1)

- **Goal**: Learn per-space novelty bonus values from grounding feedback.
- **Deliverables**:
  - `AdaptiveNoveltyBonusLearner.adjust_bonus(bonus_type, feedback_signal, current_bonus)`:
    - NOVEL_EVENT_GROUNDED → +0.01, NOVEL_EVENT_NEVER_QUERIED → -0.02, USER_SAYS_NOT_NEW → -0.03.
    - Clamp to [0.05, 0.30].
  - Persist learned bonuses to `st_learned_weights` (param_key: `novelty_bonus_{type}`, scope: space).
  - Consume feedback signals from P21 (NOVEL_EVENT_*, MILESTONE_GROUNDED, RARE_PATTERN_USEFUL).
- **Acceptance**:
  - Space with many "not new" corrections → first_occurrence bonus decreases.
  - Space with high milestone grounding → milestone bonus increases.
  - Metrics: `p03_novelty_bonus_current`, `p03_novelty_false_positive_rate`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.4.2.1 "Adaptive Novelty Bonuses")

#### Issue 4.3.9 — Implement decay immunity ontology (FAMILY_MEMBER, core identity) (Section 4.4.3.1)

- **Goal**: Prevent decay of core identity facts that should persist forever.
- **Deliverables**:
  - `ImmunityChecker.should_mark_immune(entity_type, entity_attributes)`:
    - Entity-level immunity: FAMILY_MEMBER → all attributes immune.
    - Attribute-level immunity matrix:
      - PERSON: birthday, name, relationship_to_user
      - PLACE: home_address, work_address
      - EVENT: wedding_date, birth_date, death_date
      - ORGANIZATION: employer, school
      - CONCEPT: core_value, religion, political_affiliation
  - Auto-mark `decay_immune=TRUE` during entity creation/update.
  - `RetentionEnforcer.evaluate()` skips records where `decay_immune=TRUE`.
- **Acceptance**:
  - Entity type=FAMILY_MEMBER → decay_immune=TRUE.
  - PERSON with birthday attribute → birthday never decays.
  - Immune entities excluded from decay calculations.
  - Metrics: `p03_decay_immune_entities` gauge.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.4.3.1 "Decay Immunity")

#### Issue 4.3.10 — Implement prune decision audit logging (st_consolidation_audit)

- **Goal**: Record all prune/archive/tombstone decisions for debugging, learning, and compliance.
- **Deliverables**:
  - On each ARCHIVE or TOMBSTONE decision, log to `st_consolidation_audit`:
    - audit_id, memory_id, source_table, action (ARCHIVE, TOMBSTONE, PRUNE_REGRET).
    - formula_used: 'exponential_decay_v1'.
    - inputs_json: decay_factor, days_since_observed, effective_lambda, importance_score.
    - outputs_json: new_archival_status, threshold_used.
    - explanation: human-readable reason.
  - Sampling config: 100% in debug mode, 10% in production (configurable).
- **Acceptance**:
  - All prune decisions are auditable.
  - Audit log queryable for post-hoc analysis.
  - Production overhead <1ms per decision.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2 "Metrics Reference")

#### Issue 4.3.11 — Implement MinHash LSH for scale (>50K events) (Appendix C.4.1.3)

- **Goal**: Sub-linear duplicate detection for high-volume spaces.
- **Deliverables**:
  - `MinHashLSH` class implementing:
    - `compute_minhash(text)`: 128-hash signature using MurmurHash3.
    - `hash_bands(signature)`: Split into 32 bands of 4 rows each.
    - `index_event(event_id, signature)`: Add to LSH index (band_hash → event_ids).
    - `find_candidates(signature)`: Return candidate set from matching bands.
  - Auto-switch logic: SimHash pairwise (<10K), SimHash+bucketing (10K-50K), MinHash LSH (>50K).
  - Schema: `st_hipp_events.minhash_signature` (BYTEA, 1KB).
  - Nightly index rebuild during R0 (store in Redis).
  - Feature flag: `P03_FF_MINHASH_LSH = FALSE` (disabled by default).
- **Acceptance**:
  - 100K events → dedup latency <20ms per event.
  - LSH recall >90% for Jaccard similarity ≥0.85.
  - Metrics: `p03_dedup_method_used`, `p03_lsh_index_size`, `p03_lsh_rebuild_duration_seconds`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.4.1.3 "MinHash LSH")

#### Issue 4.3.12 — Unit + integration tests for R3 Duplicate detection + Decay

- **Goal**: Prove correctness of deduplication and decay logic.
- **Deliverables**:
  - Test: SimHash distance=0 for identical text.
  - Test: Two-stage pipeline catches semantic duplicate missed by SimHash.
  - Test: Stage 2 rejects SimHash false positive (opposite meaning).
  - Test: Decay factor decreases over time with correct λ.
  - Test: ARCHIVE triggered at decay<0.10, TOMBSTONE at decay<0.01.
  - Test: Resurrection restores decay to ≥0.70.
  - Test: Decay immunity skips immune entities.
  - Test: Prune regret detection matches query to pruned entity.
  - Test: Novelty bonuses applied correctly (first, milestone, rare).
  - Integration test: full R3 phase processes batch and produces expected outputs.
- **Acceptance**:
  - All tests pass; coverage includes edge cases (empty batch, all duplicates, no decay).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

### Epic 4.4 — R4 KG consolidation (entities/edges/causal + ambiguity gaps)

> **Scope note (avoid confusion)**:
>
> - Epic 4.4 covers the **R4 Knowledge Graph Consolidation phase** (NREM2-3 analog): entity extraction, disambiguation, merge cascades, and edge updates.
> - Module: M21 KGConsolidator
> - Key tables: reads `st_hipp_events`, outputs to `st_kg_dom` (entities), `st_kg_edges` (relationships), `st_entity_merges` (merge history), `st_entity_resolutions` (disambiguation audit).
> - Epic 4.4 does **not** cover duplicate detection (R3, Epic 4.3), Dream phase (R5, Epic 8.1), or truth writes (R7, Epic 5.2).
> - Dossier references: Sections 4.5, Appendix C.5 (algorithms), Section 7.4.4 (M21 module).

#### Issue 4.4.1 — Integrate UltraBERT NER entity extraction from P02 (Appendix C.5.1)

- **Goal**: Process named entity recognition outputs from P02 for knowledge graph population.
- **Deliverables**:
  - `UltraBERTEntityExtractor` integration that consumes P02 NER output:
    - Entity types: PERSON, LOCATION, ORGANIZATION, EVENT, FOOD, ACTIVITY, OBJECT, CONCEPT.
    - Per-type confidence thresholds: PERSON=0.85, LOCATION=0.80, EVENT=0.75, FOOD=0.70.
  - `extract_entities(event)`: Returns List[ExtractedEntity] with text_span, entity_type, confidence, positions.
  - Entity normalization: lowercase, strip whitespace, canonical form.
  - Store extracted entities in `st_hipp_events.entities_json`.
- **Acceptance**:
  - "Uncle Bob visited Grandma's house" → extracts PERSON("Uncle Bob"), LOCATION("Grandma's house").
  - Low-confidence entities (<threshold) are discarded.
  - Metrics: `p03_entities_extracted_total` by type, `p03_entity_confidence_distribution`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.5.1 "UltraBERT NER")

#### Issue 4.4.2 — Implement per-entity-type disambiguation weights (embedding vs string) (Section 4.5.1.1)

- **Goal**: Apply different embedding/string weight ratios based on entity type.
- **Deliverables**:
  - `EntityDisambiguator.compute_similarity(entity1, entity2)`:
    - Per-type weight matrix (from dossier):
      - PERSON: embedding=0.50, string=0.50
      - FAMILY_MEMBER: embedding=0.30, string=0.70
      - PLACE: embedding=0.60, string=0.40
      - ORGANIZATION: embedding=0.55, string=0.45
      - THING: embedding=0.80, string=0.20
      - CONCEPT: embedding=0.85, string=0.15
      - EVENT: embedding=0.70, string=0.30
    - Weighted formula: `similarity = (w_embedding × embedding_sim) + (w_string × string_sim)`.
  - `fuzzy_string_match(name1, name2)`: Best of Levenshtein, Jaro-Winkler, Token Sort.
  - Persist/load weights from `st_learned_weights` (param_key: `disambiguation_{type}_embedding`).
- **Acceptance**:
  - FAMILY_MEMBER with name mismatch → low similarity (string-weighted).
  - CONCEPT with synonym → high similarity (embedding-weighted).
  - Metrics: `p03_disambiguation_weight_embedding`, `p03_disambiguation_weight_string` by type.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.5.1.1 "Per-Entity-Type Disambiguation")

#### Issue 4.4.3 — Implement disambiguation weight learning from user feedback (Section 4.5.1.1)

- **Goal**: Adjust embedding/string weights based on merge corrections.
- **Deliverables**:
  - `DisambiguationWeightLearner.adjust_weights(entity_type, entity1, entity2, feedback_signal)`:
    - ENTITY_MERGE_REJECTED → increase weight on differing component (+0.05/-0.05).
    - ENTITY_MANUAL_MERGE → decrease weight on matching component (-0.03/+0.03).
    - ENTITY_SPLIT → increase both weights (+0.04/+0.04).
  - Normalization: weights sum to 1.0, clamp to [0.15, 0.85].
  - Consume feedback signals from P21 (ENTITY_MERGE_*, ENTITY_SPLIT).
- **Acceptance**:
  - Many ENTITY_MERGE_REJECTED for PERSON → string weight increases.
  - Weights evolve toward actual disambiguation needs.
  - Metrics: `p03_disambiguation_false_positives`, `p03_disambiguation_false_negatives`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.5.1.1 "Learning from User Corrections")

#### Issue 4.4.4 — Implement ambiguous entity resolution with context hierarchy (Section 4.5.1.2)

- **Goal**: Resolve ambiguous mentions ("John") to specific entities using contextual clues.
- **Deliverables**:
  - `AmbiguousEntityResolver.resolve(mention, candidates, event_context)`:
    - Priority hierarchy (from dossier):
      1. Recent context (same session/conversation): +0.35
      2. Co-occurring entities (who else mentioned): +0.30
      3. Location context (where event happened): +0.20
      4. Temporal pattern (time of day/week): +0.10
      5. Frequency (most mentioned): +0.05
    - Returns (entity_id, confidence, resolution_method).
  - Schema: `st_entity_resolutions` table for audit (resolution_id, mention_text, resolved_entity_id, candidates_json, confidence, resolution_method).
- **Acceptance**:
  - "Meeting with John" in office context → coworker John.
  - "Dinner with John and Mary" → Mary's husband John.
  - Metrics: `p03_ambiguous_entities_detected`, `p03_ambiguous_auto_resolved`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.5.1.2 "Ambiguous Entity Resolution")

#### Issue 4.4.5 — Implement entity resolution confidence bands + P06 gap emission (Section 4.5.1.2)

- **Goal**: Route low-confidence resolutions to P06 for user clarification.
- **Deliverables**:
  - Confidence thresholds (from dossier):
    - ≥0.85: Auto-resolve, proceed.
    - 0.60-0.85: Resolve + flag for review in `st_entity_resolutions.review_outcome`.
    - <0.60: Emit `AMBIGUOUS_ENTITY` gap to P06.
  - `emit_ambiguous_gap(mention, candidates, event_context)`:
    - Payload: gap_type, gap_id, space_id, mention_text, candidates[], context_event_id, suggested_resolution, confidence.
    - Topic: `p03.gap.detected.v1`.
  - Track review outcomes: `reviewed_by`, `review_outcome` (CONFIRMED, CORRECTED), `corrected_entity_id`.
- **Acceptance**:
  - Confidence 0.42 → gap emitted to P06, not auto-resolved.
  - Confidence 0.75 → resolved but flagged for review.
  - Metrics: `p03_ambiguous_flagged`, `p03_ambiguous_emitted_p06`, `p03_ambiguous_resolution_accuracy`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.5.1.2 "Confidence Thresholds & Actions")

#### Issue 4.4.6 — Implement adaptive merge thresholds per entity type (Section 4.5.1.4)

- **Goal**: Learn per-entity-type similarity thresholds for merge decisions.
- **Deliverables**:
  - Per-type initial thresholds (from dossier):
    - FAMILY_MEMBER=0.90 [0.85, 0.98], PERSON=0.85 [0.80, 0.95], PLACE=0.75 [0.65, 0.85], ORGANIZATION=0.80 [0.70, 0.90], THING=0.70 [0.60, 0.80], CONCEPT=0.65 [0.55, 0.75], EVENT=0.75 [0.65, 0.85].
  - `DisambiguationThresholdLearner.adjust_threshold(entity_type, feedback_signal, current_threshold)`:
    - ENTITY_MERGE_REJECTED → +0.03, ENTITY_SPLIT → +0.05, ENTITY_MANUAL_MERGE → -0.02.
    - Clamp to type-specific bounds.
  - Persist to `st_learned_weights` (param_key: `disambiguation_threshold_{type}`).
  - Drift monitoring: alert if threshold drifts >0.15 in 30 days.
- **Acceptance**:
  - FAMILY_MEMBER threshold starts at 0.90, can increase toward 0.98 on rejections.
  - CONCEPT threshold starts at 0.65, can decrease toward 0.55 on manual merges.
  - Metrics: `p03_disambiguation_threshold_current`, `p03_disambiguation_precision`, `p03_disambiguation_recall`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.5.1.4 "Adaptive Thresholds")

#### Issue 4.4.7 — Implement entity merge cascade + st_entity_merges undo support (Section 4.5.1.3)

- **Goal**: Complete entity merges with full cascade across all referencing tables and reversibility.
- **Deliverables**:
  - `EntityMerger.merge_entities(primary_id, secondary_id, reason, initiated_by)`:
    - 6-step process: Validate → Select Primary → Merge Attributes → Cascade References → Archive Secondary → Log for Undo.
    - Returns merge_id for tracking.
  - `cascade_update_references(merge_id, primary_id, secondary_id)`:
    - Tables: st_kg_edges (source/target), st_hipp_events (entities_json), st_epi (entity_ids), st_sem (entity_ids), st_social (actor_id), st_procedural (participants), st_vec (metadata_json).
    - Track via `merge_cascade_id` column.
  - Schema: `st_entity_merges` table (merge_id, primary/secondary_entity_id, snapshots, cascade_counts, merged_at, reversed_at).
  - `EntityMerger.reverse_merge(merge_id, reversed_by)`: Undo merge using cascade_id tracking.
- **Acceptance**:
  - Merge updates all referencing tables atomically.
  - Undo restores secondary entity and reverts all cascade updates.
  - Metrics: `p03_entities_merged`, `p03_merge_cascade_updates`, `p03_merges_reversed`, `p03_merge_duration_seconds`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.5.1.3 "Entity Merge Process")

#### Issue 4.4.8 — Implement M21 KGConsolidator: entity resolution + edge discovery (Section 7.4.4)

- **Goal**: Orchestrate entity extraction, resolution, and relationship discovery from episode clusters.
- **Deliverables**:
  - `KGConsolidator.consolidate(clusters, existing_kg)`:
    - Extract entities from cluster events.
    - Resolve against existing `st_kg_dom` (new vs update).
    - Discover relationships via co-occurrence (Hebbian, min co-occurrence=2).
    - Generate KGUpdate objects: CREATE_ENTITY, UPDATE_ENTITY, CREATE_EDGE, UPDATE_EDGE.
  - `_discover_relationships(cluster, entities)`:
    - Confidence formula: `min(0.9, 0.3 + 0.1 × co_occurrences)`.
    - Infer relationship type from entity types.
  - Edge confidence threshold: 0.5 (from config).
- **Acceptance**:
  - Entities appearing together in 3+ events → edge confidence 0.60.
  - New entities create st_kg_dom records; existing entities update observation_count.
  - Metrics: `p03_entities_created`, `p03_entities_updated`, `p03_edges_created`, `p03_edges_updated`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 7.4.4 "M21 KGConsolidator")

#### Issue 4.4.9 — Implement Granger causality inference for edge directionality (Appendix C.5.2, Section 4.5.4)

- **Goal**: Infer causal direction for temporal relationships (A causes B vs correlation).
- **Deliverables**:
  - `GrangerCausalityInference.compute_temporal_precedence(entity_a, entity_b, observations)`:
    - Returns: a_before_b, b_before_a, simultaneous, precedence_ratio.
    - Simultaneous threshold: ≤1 minute.
  - `infer_causal_direction(entity_a, entity_b, observations, config)`:
    - Requires min_observations (default 5).
    - Precedence ratio ≥ threshold → A CAUSES B edge.
    - Returns CausalEdge with source_id, target_id, relation_type='CAUSES', confidence.
  - Store directed edges in `st_kg_edges` with `relation_type='CAUSES'`.
- **Acceptance**:
  - "Alarm" always before "Wake up" (ratio 0.95) → Alarm CAUSES Wake_up.
  - "Rain" mixed with "Stay home" (ratio 0.55) → no causal edge.
  - Metrics: `p03_causal_edges_inferred`, `p03_causal_precedence_ratio` histogram.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.5.2 "Granger Causality")
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.5.4 "Causal Inference")

#### Issue 4.4.10 — Implement adaptive causality thresholds by category (Section 4.5.4.1)

- **Goal**: Apply different precedence ratio thresholds based on relationship stakes.
- **Deliverables**:
  - Per-category threshold matrix (from dossier):
    - Health/Medical: 0.85 (high stakes, strong evidence).
    - Financial: 0.80 (important, moderate risk).
    - Social/Routine: 0.70 (lower stakes).
    - Preference/Habit: 0.65 (personal, flexible).
  - `CausalCategoryClassifier.classify(source_entity, target_entity, relationship_type)`:
    - Classify based on entity types and relationship context.
  - Consume feedback for threshold learning:
    - CAUSAL_EDGE_CONFIRMED → reinforce.
    - CAUSAL_EDGE_REJECTED → increase threshold +0.03.
    - CAUSAL_EDGE_REVERSED → increase threshold +0.05.
- **Acceptance**:
  - "Medication A → symptom relief" requires ratio ≥0.85.
  - "Coffee → productive" requires only ≥0.65.
  - Metrics: `p03_causal_threshold_current` by category.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.5.4.1 "Adaptive Causality Thresholds")

#### Issue 4.4.11 — Implement edge demotion hook for contradicted relationships (Section 4.5.4)

- **Goal**: Demote or archive edges when evidence contradicts existing causal claims.
- **Deliverables**:
  - `EdgeDemoter.evaluate_contradiction(edge_id, contradiction_evidence)`:
    - If precedence ratio drops below threshold → demote confidence.
    - If confidence drops below 0.30 → archive edge.
  - Demotion triggers:
    - Reversed temporal pattern (B now precedes A).
    - User feedback: CAUSAL_EDGE_REJECTED.
    - Conflicting observations (new data contradicts old pattern).
  - Emit demotion event: `p03.edge.demoted.v1` for downstream notification.
- **Acceptance**:
  - Edge with confidence 0.80 contradicted → demoted to 0.50.
  - Edge with confidence <0.30 → archived.
  - Metrics: `p03_edges_demoted`, `p03_edges_archived_contradiction`.
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.5.4 "Causal Inference")

#### Issue 4.4.12 — Unit + integration tests for R4 KG consolidation

- **Goal**: Prove correctness of entity resolution, merge cascade, and causal inference.
- **Deliverables**:
  - Test: Entity extraction produces correct types and confidence.
  - Test: Per-entity-type weights produce expected similarity.
  - Test: Disambiguation weight learning adjusts on feedback.
  - Test: Ambiguous resolution uses context hierarchy correctly.
  - Test: Low confidence (<0.60) emits P06 gap.
  - Test: Merge cascade updates all 7 referencing tables.
  - Test: Merge undo restores secondary entity and reverts cascades.
  - Test: Granger causality infers correct direction.
  - Test: Causality threshold varies by category.
  - Test: Edge demotion triggers on contradiction.
  - Integration test: full R4 phase processes clusters and produces expected KG updates.
- **Acceptance**:
  - All tests pass; coverage includes edge cases (no candidates, single entity, conflicting patterns).
- **References**:
  - Dossier:
    - `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

---

## Milestone 5 — R6–R8 finalize: stage → commit → emit

### Epic 5.1 — R6 staging and manifests

#### Issue 5.1.1 — R6Output dataclass and StagedWritesContainer

- **Goal**: Implement the core R6Output dataclass that accumulates all staged writes from R1-R5 phases for atomic commit in R7.
- **Scope**:
  - Create `R6Output` dataclass in `k0/modules/consolidation/staging/r6_output.py`
  - Implement fields: `staged_event_updates: list[StagedEventUpdate]`, `staged_truth_writes: list[StagedTruthWrite]`, `staged_kg_writes: list[StagedKGWrite]`, `staged_outbox_events: list[StagedOutboxEvent]`, `reconciliation_summary: ReconciliationSummary`
  - Create `StagedEventUpdate` dataclass: event_id, consolidation_status, near_duplicates_json, novelty_score, episode_cluster_id
  - Create `StagedTruthWrite` dataclass: table_name, operation (INSERT/UPDATE/ARCHIVE), record_data, idempotency_key
  - Create `StagedKGWrite` dataclass: table (st_kg_dom/st_kg_edges), operation, entity_or_edge_data, idempotency_key
  - Create `StagedOutboxEvent` dataclass: topic, event_type, payload, idempotency_key
  - Implement `StagedWritesContainer` class with append/extend methods and serialization support
- **Deliverables**:
  - `k0/modules/consolidation/staging/r6_output.py` (R6Output, all staged write dataclasses)
  - `k0/modules/consolidation/staging/container.py` (StagedWritesContainer)
  - `k0/contracts/modules/staging/r6_output.yaml` (schema validation)
- **Acceptance Criteria**:
  - All dataclasses frozen, hashable, JSON-serializable
  - StagedWritesContainer supports atomic batch assembly
  - Schema validates against dossier Appendix G R6 specification
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G "R6Output dataclass")

---

#### Issue 5.1.2 — Consolidation status marking logic

- **Goal**: Implement logic to determine and assign consolidation_status to each processed event based on R1-R5 outcomes.
- **Scope**:
  - Create `ConsolidationStatusMarker` in `k0/modules/consolidation/staging/status_marker.py`
  - Implement status determination rules from dossier Section 4.7.1:
    - `CONSOLIDATED`: Event successfully processed, truth records created/updated
    - `DUPLICATE`: Event identified as duplicate by M19 SimHash or embedding verification
    - `PRUNED`: Event matched existing truth with PRUNE decision (decay < threshold)
    - `PENDING_REVIEW`: Event flagged for P06 active learning (ambiguous entity, contradiction)
  - Accept inputs: DuplicateDetectionResult, ReconciliationDecision, GapDetectionResult
  - Emit status with reasoning trace for audit
  - Handle edge cases: partial processing failures, timeout events
- **Deliverables**:
  - `k0/modules/consolidation/staging/status_marker.py` (ConsolidationStatusMarker)
  - `k0/contracts/modules/staging/consolidation_status.yaml` (status enum + validation)
- **Acceptance Criteria**:
  - All four status values correctly assigned based on phase outcomes
  - Status assignment is deterministic and idempotent
  - Reasoning trace captures decision path for debugging
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.7.1 "Consolidation Status Marking")

---

#### Issue 5.1.3 — Deduplication metadata population

- **Goal**: Populate deduplication-related metadata fields on staged event updates from M19 DuplicateDetector results.
- **Scope**:
  - Create `DedupMetadataPopulator` in `k0/modules/consolidation/staging/dedup_metadata.py`
  - Populate `near_duplicates_json` field per dossier Section 4.7.2:
    - Array of `{event_id, simhash_distance, embedding_similarity, detection_stage}`
    - Include all candidates from Stage 1 SimHash filter (Hamming ≤ threshold)
    - Annotate which passed Stage 2 embedding verification
  - Populate `novelty_score` from M20 novelty calculation (0.0-1.0 range)
  - Populate `episode_cluster_id` from M18 clustering assignment (nullable for singleton events)
  - Handle empty near_duplicates (novelty_score = 1.0 baseline + bonuses)
- **Deliverables**:
  - `k0/modules/consolidation/staging/dedup_metadata.py` (DedupMetadataPopulator)
  - `k0/contracts/modules/staging/dedup_metadata.yaml` (near_duplicates_json schema)
- **Acceptance Criteria**:
  - near_duplicates_json correctly captures all SimHash candidates with verification results
  - novelty_score reflects dossier formula (base + first/milestone/rare bonuses - routine penalty)
  - episode_cluster_id links to M18 cluster or null for singletons
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.7.2 "Deduplication Metadata")

---

#### Issue 5.1.4 — Reconciliation decision recording

- **Goal**: Record reconciliation decisions with full audit trail including decision type, target truth reference, and similarity scores.
- **Scope**:
  - Create `ReconciliationRecorder` in `k0/modules/consolidation/staging/reconciliation_recorder.py`
  - Record decision types per dossier Section 1.3:
    - `REINFORCE` (similarity > 0.85): target_truth_id, observation_count_delta, confidence_boost
    - `EXTEND` (similarity 0.6-0.85): target_truth_id, extended_attributes, source_episodes_json_append
    - `CREATE` (similarity < 0.6): new_truth_record, is_canonical=1, initial_confidence
    - `EVOLVE`: old_truth_id (is_canonical=0), new_truth_id (is_canonical=1), evolution_reason
    - `CONTRADICT`: truth_id, contradiction_type, flagged_for_p06=true
    - `PRUNE`: truth_id, decay_value, archive_or_tombstone
  - Store similarity scores that drove decision: embedding_similarity, attribute_match_score, temporal_proximity
  - Generate decision trace for st_reconciliation_log table
- **Deliverables**:
  - `k0/modules/consolidation/staging/reconciliation_recorder.py` (ReconciliationRecorder)
  - `k0/contracts/modules/staging/reconciliation_decision.yaml` (decision schema)
- **Acceptance Criteria**:
  - All six decision types recorded with complete metadata
  - Similarity scores captured at decision granularity
  - Decision trace enables post-hoc analysis and P06 learning
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.3 "Reconciliation Decision Types", Section 4.7.3 "Reconciliation Decision Recording")

---

#### Issue 5.1.5 — Idempotency key generation for R6

- **Goal**: Generate and validate idempotency keys for all R6 staged writes to ensure exactly-once semantics across retries.
- **Scope**:
  - Create `IdempotencyKeyGenerator` in `k0/modules/consolidation/staging/idempotency.py`
  - Implement key format per dossier Section 12.2.3:
    - R6 staging: `p03:staging:{cycle_ulid}:{event_id}`
    - R7 writes: `p03:write:{cycle_ulid}:{table}:{record_id}`
    - R8 emission: `p03:emit:{cycle_ulid}:{topic}:{offset}`
  - Validate key uniqueness within cycle scope
  - Support key extraction for deduplication on retry
  - Store keys in st_idempotency_log with TTL (default 7 days)
- **Deliverables**:
  - `k0/modules/consolidation/staging/idempotency.py` (IdempotencyKeyGenerator)
  - `k0/contracts/modules/staging/idempotency_key.yaml` (key format validation)
- **Acceptance Criteria**:
  - Keys follow exact dossier format with cycle_ulid scope
  - Duplicate key detection prevents re-processing on retry
  - TTL cleanup prevents unbounded key accumulation
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 12.2.3 "Idempotency Key Design")

---

#### Issue 5.1.6 — Staged truth writes assembly

- **Goal**: Assemble staged writes for all 8 memory layer tables based on reconciliation decisions and layer-specific logic.
- **Scope**:
  - Create `StagedTruthAssembler` in `k0/modules/consolidation/staging/truth_assembler.py`
  - Generate StagedTruthWrite records for each layer:
    - `st_epi`: episode records with cluster_id, source linking, temporal anchoring
    - `st_sem`: pattern records with confidence, source_episodes_json
    - `st_procedural`: routine patterns, temporal regularity, action sequences
    - `st_social`: relationship updates, interaction frequency, sentiment
    - `st_prospective`: future patterns, goal inference, reminder hints
    - `st_kg_dom`: entity canonical records
    - `st_kg_edges`: edges with confidence, temporal bounds
    - `st_vec`: aggregated embeddings (coordinates with P08)
  - Apply operation type based on decision: INSERT (CREATE), UPDATE (REINFORCE/EXTEND), ARCHIVE (PRUNE)
  - Generate idempotency key per write
- **Deliverables**:
  - `k0/modules/consolidation/staging/truth_assembler.py` (StagedTruthAssembler)
  - Per-layer write builders in `k0/modules/consolidation/staging/layers/`
- **Acceptance Criteria**:
  - All 8 memory layers correctly populated from reconciliation decisions
  - Operation types match decision semantics
  - Each write has unique idempotency key
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Sections 4.8 "R7 – TruthWriter", Appendix G "R6Output")

---

#### Issue 5.1.7 — Staged KG writes assembly

- **Goal**: Assemble staged writes for knowledge graph tables (st_kg_dom, st_kg_edges) from M21 KGConsolidator outputs.
- **Scope**:
  - Create `StagedKGAssembler` in `k0/modules/consolidation/staging/kg_assembler.py`
  - Generate StagedKGWrite for entities:
    - New entity creation (entity_type, canonical_name, embedding, confidence)
    - Entity merge updates (winner absorbs loser, update st_entity_merges)
    - Entity attribute updates (append to attributes_json)
  - Generate StagedKGWrite for edges:
    - New edge creation (source_id, target_id, relation, confidence, temporal_bounds)
    - Edge confidence updates (co-occurrence reinforcement)
    - Edge demotion/archive (contradiction handling, confidence < 0.30)
    - Granger causality CAUSES edges (direction, precedence_ratio)
  - Track entity merge cascades for rollback support
- **Deliverables**:
  - `k0/modules/consolidation/staging/kg_assembler.py` (StagedKGAssembler)
  - `k0/contracts/modules/staging/kg_writes.yaml` (entity/edge write schemas)
- **Acceptance Criteria**:
  - Entity operations reflect disambiguation and merge decisions
  - Edge operations include Granger causality edges with proper direction
  - Merge cascade tracked in st_entity_merges for undo support
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 7.4.4 "M21 KGConsolidator", Section 4.5 "R4 – KG Consolidation")

---

#### Issue 5.1.8 — Staged outbox events assembly

- **Goal**: Assemble staged outbox events for R8 emission based on consolidation outcomes.
- **Scope**:
  - Create `StagedOutboxAssembler` in `k0/modules/consolidation/staging/outbox_assembler.py`
  - Generate StagedOutboxEvent for each emission type:
    - `p03.consolidation.complete.v1`: cycle summary, events processed, decisions by type
    - `p03.pattern.detected.v1`: new semantic patterns for downstream consumers
    - `p03.entity.resolved.v1`: entity disambiguation results for KG sync
    - `p03.gap.detected.v1`: knowledge gaps for P06 active learning
    - `p03.memory.updated.v1`: layer-specific update notifications
  - Include idempotency key per event
  - Support topic routing based on event type
- **Deliverables**:
  - `k0/modules/consolidation/staging/outbox_assembler.py` (StagedOutboxAssembler)
  - `k0/contracts/modules/staging/outbox_events.yaml` (event schemas per topic)
- **Acceptance Criteria**:
  - All dossier-specified event types assembled with correct payloads
  - Idempotency keys prevent duplicate emission on retry
  - Events routable to correct topics
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.9 "R8 – Emission", Appendix G "R8Output")

---

#### Issue 5.1.9 — Manifest validation before commit

- **Goal**: Validate R6Output manifest for completeness and consistency before passing to R7 TruthWriter.
- **Scope**:
  - Create `ManifestValidator` in `k0/modules/consolidation/staging/manifest_validator.py`
  - Implement validation checks:
    - Completeness: All input events have corresponding status assignment
    - Idempotency: All staged writes have unique, valid idempotency keys
    - Referential integrity: truth writes reference valid entity IDs
    - Schema compliance: All staged writes validate against contracts
    - Consistency: Decision counts match write counts (CREATE → INSERT, etc.)
  - Generate validation report with pass/fail per check
  - Block R7 execution on validation failure
  - Support partial validation for debugging
- **Deliverables**:
  - `k0/modules/consolidation/staging/manifest_validator.py` (ManifestValidator)
  - `k0/contracts/modules/staging/validation_report.yaml` (report schema)
- **Acceptance Criteria**:
  - All dossier-mandated validations implemented
  - Validation failure prevents R7 execution with clear error
  - Partial validation aids debugging without blocking
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.7 "R6 – Staging Table Updates")

---

#### Issue 5.1.10 — ReconciliationSummary generation

- **Goal**: Generate consolidated summary of all reconciliation decisions for cycle metrics and downstream reporting.
- **Scope**:
  - Create `ReconciliationSummary` dataclass in `k0/modules/consolidation/staging/summary.py`
  - Aggregate counts by decision type: reinforce_count, extend_count, create_count, evolve_count, contradict_count, prune_count
  - Aggregate by layer: writes per st_epi, st_sem, st_procedural, etc.
  - Track entity operations: entities_created, entities_merged, entities_flagged_ambiguous
  - Track edge operations: edges_created, edges_updated, edges_demoted
  - Calculate cycle statistics: events_processed, processing_duration_ms, avg_confidence
  - Support JSON serialization for p03.consolidation.complete.v1 event
- **Deliverables**:
  - `k0/modules/consolidation/staging/summary.py` (ReconciliationSummary)
  - `k0/contracts/modules/staging/reconciliation_summary.yaml` (summary schema)
- **Acceptance Criteria**:
  - All decision and operation counts accurately aggregated
  - Summary JSON embeddable in cycle completion event
  - Statistics useful for monitoring and alerting
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G "R6Output.reconciliation_summary")

---

#### Issue 5.1.11 — R6 phase coordinator

- **Goal**: Implement R6 phase coordinator that orchestrates status marking, metadata population, and manifest assembly.
- **Scope**:
  - Create `R6Coordinator` in `k0/modules/consolidation/staging/r6_coordinator.py`
  - Accept inputs from R1-R5 phases: clustering results, duplicate detection, reconciliation decisions, KG consolidation, gap detection
  - Orchestrate sub-components in order:
    1. ConsolidationStatusMarker → status per event
    2. DedupMetadataPopulator → near_duplicates, novelty_score
    3. ReconciliationRecorder → decision audit trail
    4. StagedTruthAssembler → memory layer writes
    5. StagedKGAssembler → KG writes
    6. StagedOutboxAssembler → emission events
    7. ReconciliationSummary → cycle statistics
    8. ManifestValidator → pre-commit validation
  - Emit R6Output with all staged writes and summary
  - Support partial execution for testing/debugging
- **Deliverables**:
  - `k0/modules/consolidation/staging/r6_coordinator.py` (R6Coordinator)
  - `k0/contracts/pipelines/p03_r6.yaml` (R6 phase contract)
- **Acceptance Criteria**:
  - All sub-components orchestrated in correct order
  - R6Output fully populated and validated
  - Partial execution mode for isolated testing
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.7 "R6 – Staging Table Updates", Appendix G)

---

#### Issue 5.1.12 — R6 staging unit and integration tests

- **Goal**: Comprehensive test coverage for all R6 staging components ensuring manifest correctness and validation.
- **Scope**:
  - Unit tests per component:
    - R6Output serialization/deserialization round-trip
    - ConsolidationStatusMarker for all status assignment paths
    - DedupMetadataPopulator with various near_duplicate scenarios
    - ReconciliationRecorder for all six decision types
    - IdempotencyKeyGenerator format and uniqueness
    - StagedTruthAssembler per-layer write generation
    - StagedKGAssembler entity/edge scenarios
    - StagedOutboxAssembler event assembly
    - ManifestValidator pass/fail scenarios
    - ReconciliationSummary aggregation accuracy
  - Integration tests:
    - R6Coordinator end-to-end with mock R1-R5 outputs
    - Manifest validation blocking on invalid input
    - Idempotency key collision detection
    - Full cycle staging with representative event mix
  - Contract validation tests:
    - All staged writes validate against YAML schemas
    - R6Output schema compliance
- **Deliverables**:
  - `tests/k0/modules/consolidation/staging/test_r6_output.py`
  - `tests/k0/modules/consolidation/staging/test_status_marker.py`
  - `tests/k0/modules/consolidation/staging/test_dedup_metadata.py`
  - `tests/k0/modules/consolidation/staging/test_reconciliation_recorder.py`
  - `tests/k0/modules/consolidation/staging/test_idempotency.py`
  - `tests/k0/modules/consolidation/staging/test_assemblers.py`
  - `tests/k0/modules/consolidation/staging/test_manifest_validator.py`
  - `tests/k0/modules/consolidation/staging/test_r6_coordinator.py`
- **Acceptance Criteria**:
  - ≥90% line coverage for staging module
  - All decision types and status values exercised
  - Integration tests cover full R6 phase flow
  - Contract validation tests pass for all schemas
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

### Epic 5.2 — R7 TruthWriter + R8 emission

#### Issue 5.2.1 — M24 TruthWriter module scaffolding and decision router

- **Goal**: Implement the core M24 TruthWriter module that orchestrates durable writes to all memory layers based on reconciliation decisions.
- **Scope**:
  - Create `TruthWriter` class in `k0/modules/consolidation/truth_writer/writer.py`
  - Implement configuration: `batch_size` (default: 100), `transaction_mode` ('ATOMIC' or 'PARTIAL')
  - Implement `write_decisions(decisions: List[ReconciliationDecision]) -> WriteResult` per dossier Section 7.4.7
  - Implement decision routing via `_apply_decision()`:
    - `REINFORCE` → `_reinforce()`: increment observation_count, boost confidence, refresh last_observed_at
    - `EXTEND` → `_extend()`: append to source_episodes_json, update attributes
    - `CREATE` → `_create()`: INSERT new record with is_canonical=1, initial confidence
    - `EVOLVE` → `_evolve()`: mark old is_canonical=0, create new with is_canonical=1
    - `PRUNE` → `_prune()`: apply decay, archive/tombstone based on threshold
    - `CONTRADICT` → `_emit_gap()`: emit gap for P06, no write
  - Return `WriteResult(successes=[], failures=[])` with per-decision outcomes
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/writer.py` (TruthWriter)
  - `k0/modules/consolidation/truth_writer/result.py` (WriteResult dataclass)
  - `k0/contracts/modules/consolidation/truth_writer.yaml` (module contract)
- **Acceptance Criteria**:
  - All six decision types correctly routed to appropriate handlers
  - ATOMIC mode rolls back entire batch on failure
  - PARTIAL mode continues on failure, records failed decision IDs
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 7.4.7 "M24 — TruthWriter", Section 4.8 "R7 — Memory Layer Writes")

---

#### Issue 5.2.2 — Outbox pattern implementation for durable writes

- **Goal**: Implement transactional outbox pattern for all memory layer writes ensuring durability and exactly-once semantics.
- **Scope**:
  - Create `OutboxWriter` in `k0/modules/consolidation/truth_writer/outbox.py`
  - Implement writes via st_outbox per dossier Section 4.8.1:
    - INSERT operations to st_outbox with: driver, op_kind, payload, fingerprint (idempotency key)
    - Support status lifecycle: PENDING → PROCESSING → (FAILED/DEAD)
    - Implement backoff_exp for retry scheduling
  - Integrate with st_outbox schema from dossier Section 6.15:
    - `driver`: target table (e.g., 'st_epi', 'st_sem', 'st_kg_dom')
    - `fingerprint`: `p03:write:{cycle_ulid}:{table}:{record_id}`
    - `requeue_seq` for ordered retry
  - Support batch outbox insertion for efficiency
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/outbox.py` (OutboxWriter)
  - `k0/contracts/modules/consolidation/outbox.yaml` (outbox operation schema)
- **Acceptance Criteria**:
  - All writes go through st_outbox for durability
  - Idempotency keys prevent duplicate writes on retry
  - Failed writes accumulate in outbox with retry scheduling
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.1 "Outbox Pattern Implementation", Section 6.15 "st_outbox")

---

#### Issue 5.2.3 — st_epi (episodic) layer writer

- **Goal**: Implement episodic memory layer writer for episode clustering results and source event linking.
- **Scope**:
  - Create `EpisodicLayerWriter` in `k0/modules/consolidation/truth_writer/layers/episodic.py`
  - Implement writes per dossier Section 4.8.2:
    - Episode records with cluster_id from M18 EpisodicClusterer
    - Source event linking via source_events_json
    - Temporal anchoring: started_at, ended_at, temporal_spread
  - Handle decision types:
    - CREATE: INSERT new episode with initial confidence
    - EXTEND: UPDATE existing episode, append to source_events_json
    - REINFORCE: Increment observation_count, update last_observed_at
  - Generate idempotency key: `p03:write:{cycle_ulid}:st_epi:{episode_id}`
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/layers/episodic.py` (EpisodicLayerWriter)
- **Acceptance Criteria**:
  - Episode records correctly linked to source events
  - Temporal anchoring reflects cluster temporal bounds
  - Idempotent writes on retry
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.2 "st_epi (Episodic) Writes")

---

#### Issue 5.2.4 — st_sem (semantic) layer writer

- **Goal**: Implement semantic memory layer writer for pattern records with confidence and source episode linking.
- **Scope**:
  - Create `SemanticLayerWriter` in `k0/modules/consolidation/truth_writer/layers/semantic.py`
  - Implement writes per dossier Section 4.8.3:
    - Pattern records with initial_confidence, current_confidence
    - source_episodes_json population with contributing episode IDs
    - observation_count and last_observed_at tracking
  - Handle decision types:
    - CREATE: INSERT new pattern with is_canonical=1
    - EXTEND: Append episodes to source_episodes_json, update attributes
    - REINFORCE: Increment observation_count, apply confidence boost
    - EVOLVE: Mark old pattern is_canonical=0, create new version
  - Support pattern hierarchy (parent_pattern_id for generalizations)
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/layers/semantic.py` (SemanticLayerWriter)
- **Acceptance Criteria**:
  - Pattern records link to source episodes
  - Confidence correctly updated based on decision type
  - Pattern evolution maintains version history
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.3 "st_sem (Semantic) Writes")

---

#### Issue 5.2.5 — st_procedural (habits) layer writer

- **Goal**: Implement procedural memory layer writer for routine patterns and temporal regularity.
- **Scope**:
  - Create `ProceduralLayerWriter` in `k0/modules/consolidation/truth_writer/layers/procedural.py`
  - Implement writes per dossier Section 4.8.4:
    - Routine patterns with action_sequence_json
    - Temporal regularity scores (daily/weekly/monthly patterns)
    - Trigger conditions and expected outcomes
  - Handle decision types:
    - CREATE: INSERT new routine pattern
    - EXTEND: Append new action sequences, update regularity
    - REINFORCE: Strengthen pattern confidence
    - PRUNE: Archive decayed routines
  - Support V(s) value function storage for TDL-HCO integration
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/layers/procedural.py` (ProceduralLayerWriter)
- **Acceptance Criteria**:
  - Routine patterns correctly encode action sequences
  - Temporal regularity reflects observed patterns
  - Value function storage ready for R5 Dream phase
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.4 "st_procedural (Habits) Writes")

---

#### Issue 5.2.6 — st_social (relationships) layer writer

- **Goal**: Implement social memory layer writer for relationship strength and interaction tracking.
- **Scope**:
  - Create `SocialLayerWriter` in `k0/modules/consolidation/truth_writer/layers/social.py`
  - Implement writes per dossier Section 4.8.5:
    - Relationship strength updates (actor pairs)
    - Interaction frequency tracking (count per time window)
    - Sentiment aggregation (rolling average)
  - Handle decision types:
    - CREATE: INSERT new relationship with initial strength
    - EXTEND: Update interaction metrics, add new interaction types
    - REINFORCE: Boost relationship strength
  - Support decay for inactive relationships
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/layers/social.py` (SocialLayerWriter)
- **Acceptance Criteria**:
  - Relationship strength reflects interaction patterns
  - Sentiment aggregation smooths individual data points
  - Inactive relationships decay appropriately
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.5 "st_social (Relationships) Writes")

---

#### Issue 5.2.7 — st_prospective (intentions) layer writer

- **Goal**: Implement prospective memory layer writer for future-oriented patterns and goal inference.
- **Scope**:
  - Create `ProspectiveLayerWriter` in `k0/modules/consolidation/truth_writer/layers/prospective.py`
  - Implement writes per dossier Section 4.8.6:
    - Future-oriented patterns (intentions, plans)
    - Goal inference results from R5 Dream phase
    - Reminder generation hints (trigger_time, trigger_context)
  - Handle decision types:
    - CREATE: INSERT new prospective pattern
    - EXTEND: Update goal inference, add trigger contexts
    - PRUNE: Archive completed or expired intentions
  - Support counterfactual storage from CPN (R5)
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/layers/prospective.py` (ProspectiveLayerWriter)
- **Acceptance Criteria**:
  - Future patterns correctly linked to source episodes
  - Goal inference results stored with confidence
  - Counterfactuals from R5 persisted for retrieval
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.6 "st_prospective (Intentions) Writes")

---

#### Issue 5.2.8 — st_kg_dom / st_kg_edges (KG) layer writer

- **Goal**: Implement knowledge graph layer writer for entity and edge persistence from M21 KGConsolidator.
- **Scope**:
  - Create `KGLayerWriter` in `k0/modules/consolidation/truth_writer/layers/kg.py`
  - Implement st_kg_dom writes per dossier Section 4.8.7:
    - Entity canonical records (entity_type, canonical_name, embedding)
    - Entity attributes_json
    - Confidence and temporal validity
  - Implement st_kg_edges writes:
    - Relationship edges (source_id, target_id, relation_type)
    - Edge confidence and temporal bounds
    - Granger causality CAUSES edges with precedence_ratio
  - Handle merge cascade updates (st_entity_merges tracking)
  - Handle decision types:
    - CREATE: INSERT new entity/edge
    - EXTEND: UPDATE attributes/confidence
    - PRUNE: Archive low-confidence edges
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/layers/kg.py` (KGLayerWriter)
- **Acceptance Criteria**:
  - Entities correctly persisted with embeddings
  - Edges include temporal validity and direction
  - Merge cascade tracked for undo support
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.7 "st_kg_dom / st_kg_edges (KG) Writes")

---

#### Issue 5.2.9 — st_vec coordination with P08 embedding index

- **Goal**: Implement vector embedding layer writer with P08 index notification for search updates.
- **Scope**:
  - Create `VectorLayerWriter` in `k0/modules/consolidation/truth_writer/layers/vector.py`
  - Implement writes per dossier Section 4.8.8:
    - Aggregated embeddings for patterns (mean/weighted average)
    - Index update coordination with P08 via outbox event
    - Embedding metadata (model_version, source_count)
  - Emit P08 coordination events:
    - `p03.embedding.created.v1`: New embedding for indexing
    - `p03.embedding.updated.v1`: Updated embedding requiring re-index
  - Handle circuit breaker for P08 unavailability (use cached embeddings)
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/layers/vector.py` (VectorLayerWriter)
  - `k0/contracts/events/p03.embedding.created.v1.yaml`
- **Acceptance Criteria**:
  - Embeddings correctly aggregated and persisted
  - P08 notified for index updates via outbox
  - Circuit breaker prevents cascade failure on P08 outage
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8.8 "st_vec (Embeddings) Writes")

---

#### Issue 5.2.10 — UnitOfWork integration for atomic multi-table writes

- **Goal**: Integrate K0 UnitOfWork for atomic transactions across all memory layer writes.
- **Scope**:
  - Integrate with `k0/uow/unit_of_work.py` per dossier Appendix D.7.1
  - Implement atomic write pattern:
    - Begin transaction via `context.syscalls.unit_of_work()`
    - Execute all layer writes within transaction scope
    - Commit atomically or rollback on any failure
  - Support optimistic locking per dossier Appendix D.7.3:
    - Use version columns for concurrent update detection
    - Re-read and retry on VERSION_CONFLICT
  - Support capability-gated access per dossier Appendix D.7.2:
    - Validate required_caps before each storage operation
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/transaction.py` (TransactionCoordinator)
- **Acceptance Criteria**:
  - All 8 layer writes atomic within single transaction
  - VERSION_CONFLICT triggers re-read and retry (max 3)
  - Capability violations raise PermissionError
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.7 "Storage Integration", Section 6.15 "st_outbox")

---

#### Issue 5.2.11 — R8 bus event emission implementation

- **Goal**: Implement R8 phase event emission for all consolidation outcome events.
- **Scope**:
  - Create `EventEmitter` in `k0/modules/consolidation/emission/emitter.py`
  - Implement emission for all topics per dossier Section 4.9.1:
    - `p03.consolidation.complete.v1`: cycle summary, events processed, decisions by type
    - `p03.pattern.detected.v1`: new semantic patterns discovered
    - `p03.truth.reinforced.v1`: existing truth reinforced
    - `p03.truth.created.v1`: new truth record created
    - `p03.truth.evolved.v1`: truth evolved (new version)
    - `p03.memory.pruned.v1`: memory pruned (archived/tombstoned)
  - Include idempotency key per event: `p03:emit:{cycle_ulid}:{topic}:{offset}`
  - Support circuit breaker for bus unavailability (queue locally, retry)
- **Deliverables**:
  - `k0/modules/consolidation/emission/emitter.py` (EventEmitter)
  - `k0/contracts/events/p03.consolidation.complete.v1.yaml`
  - `k0/contracts/events/p03.pattern.detected.v1.yaml`
  - `k0/contracts/events/p03.truth.*.v1.yaml` (4 event schemas)
- **Acceptance Criteria**:
  - All event types emitted with correct payloads
  - Idempotency prevents duplicate emission
  - Circuit breaker queues events on bus outage
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.9.1 "Bus Event Emission", Appendix G.5 "R8 Metrics")

---

#### Issue 5.2.12 — R8 gap emission for P06 Active Learning

- **Goal**: Implement gap detection event emission for P06 Active Learning integration.
- **Scope**:
  - Create `GapEmitter` in `k0/modules/consolidation/emission/gap_emitter.py`
  - Implement `p03.gap.detected.v1` emission per dossier Section 9.3.1:
    - Payload: gap_id, tenant_id, space_id, gap_type, importance_score, context
    - Gap types: AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE, MISSING_ATTRIBUTE, CONTRADICTION, CONCEPT_DRIFT, STRUCTURAL_HOLE, STALE_ANCHOR
    - Context: source_event_ids, conflicting_truths, question_template
    - TTL: ttl_hours (default: 168 = 7 days)
  - Integrate with M25 GapDetector output
  - Deduplicate gaps before emission (same gap_type + entity)
  - Cap at max_gaps_per_cycle (default: 50)
- **Deliverables**:
  - `k0/modules/consolidation/emission/gap_emitter.py` (GapEmitter)
  - `k0/contracts/events/p03.gap.detected.v1.yaml`
- **Acceptance Criteria**:
  - All gap types correctly emitted with full context
  - Gaps deduplicated within cycle
  - Cap enforced to prevent P06 overload
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.3.1 "Gap Emission: p03.gap.detected.v1", Section 7.4.8 "M25 — GapDetector")

---

#### Issue 5.2.13 — Pipeline offset updates and checkpoint

- **Goal**: Implement pipeline offset updates for resume capability and checkpoint tracking.
- **Scope**:
  - Create `OffsetManager` in `k0/modules/consolidation/emission/offset_manager.py`
  - Implement writes to st_pipeline_offsets per dossier Section 4.9.2:
    - subscriber_id: 'p03_consolidation'
    - topic: source topic name
    - offset: last processed wal_pos
    - updated_ts: checkpoint timestamp
  - Implement writes to st_pipeline_status per dossier Section 6.14:
    - status: OK, ERROR, DEFERRED
    - duration_ms: cycle processing time
    - error_kind, error_msg: on failure
  - Support high-water mark updates (st_pipeline_watermarks) for compaction
- **Deliverables**:
  - `k0/modules/consolidation/emission/offset_manager.py` (OffsetManager)
- **Acceptance Criteria**:
  - Offsets correctly persisted for resume on restart
  - Status reflects cycle outcome
  - High-water marks enable log compaction
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.9.2 "Pipeline Offset Updates", Section 6.14 "st_pipeline_offsets")

---

#### Issue 5.2.14 — Cycle metrics aggregation and emission

- **Goal**: Aggregate and emit comprehensive cycle metrics for monitoring and alerting.
- **Scope**:
  - Create `MetricsAggregator` in `k0/modules/consolidation/emission/metrics.py`
  - Implement aggregation per dossier Section 4.9.3 and Appendix G.5:
    - Cycle duration (p03_r7_duration_ms, p03_r8_duration_ms)
    - Events processed count (p03_events_processed_total)
    - Decisions by type (reinforce/extend/create/evolve/prune counts)
    - Writes by layer (st_epi, st_sem, etc.)
    - Error counts and categories
    - Gaps detected count (p03_r8_gaps_detected)
  - Emit via MetricsExporter per dossier Appendix D.9.1
  - Support histogram for batch sizes and durations
- **Deliverables**:
  - `k0/modules/consolidation/emission/metrics.py` (MetricsAggregator)
- **Acceptance Criteria**:
  - All dossier-specified metrics emitted
  - Histograms capture distribution data
  - Metrics available for Prometheus scraping
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.9.3 "Metrics Aggregation", Appendix D.9.1 "Metrics Export Pattern", Appendix G.5 "Metrics Per Phase")

---

#### Issue 5.2.15 — R7/R8 phase coordinator

- **Goal**: Implement R7/R8 phase coordinator that orchestrates TruthWriter and emission.
- **Scope**:
  - Create `R7R8Coordinator` in `k0/modules/consolidation/truth_writer/r7r8_coordinator.py`
  - Accept R6Output from staging phase
  - Orchestrate R7 phase:
    1. TruthWriter.write_decisions() for all staged truth writes
    2. KGLayerWriter for staged KG writes
    3. VectorLayerWriter for embeddings with P08 coordination
    4. Commit via UnitOfWork
  - Orchestrate R8 phase:
    1. EventEmitter.emit() for all outbox events
    2. GapEmitter.emit_gaps() for P06
    3. OffsetManager.update_offsets()
    4. MetricsAggregator.aggregate_and_emit()
  - Handle error recovery per dossier Appendix G.4:
    - R7 TRANSACTION_FAIL → full cycle retry (max 3)
    - R8 BUS_UNAVAILABLE → queue locally (max 10 retries)
- **Deliverables**:
  - `k0/modules/consolidation/truth_writer/r7r8_coordinator.py` (R7R8Coordinator)
  - `k0/contracts/pipelines/p03_r7r8.yaml` (R7/R8 phase contract)
- **Acceptance Criteria**:
  - R7 writes atomic across all layers
  - R8 emissions follow successful R7 commit
  - Error recovery follows dossier matrix
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.8, Section 4.9, Appendix G.3 "State Transition Rules", Appendix G.4 "Error Recovery Matrix")

---

#### Issue 5.2.16 — R7/R8 unit and integration tests

- **Goal**: Comprehensive test coverage for TruthWriter and emission components.
- **Scope**:
  - Unit tests per component:
    - TruthWriter decision routing for all 6 types
    - OutboxWriter idempotency and retry logic
    - Each layer writer (EpisodicLayerWriter, SemanticLayerWriter, etc.)
    - UnitOfWork atomic commit/rollback scenarios
    - EventEmitter for all event types
    - GapEmitter gap type coverage and deduplication
    - OffsetManager checkpoint persistence
    - MetricsAggregator accuracy
  - Integration tests:
    - R7R8Coordinator end-to-end with mock R6Output
    - Atomic write verification (rollback on failure)
    - P08 coordination circuit breaker behavior
    - Bus unavailability local queueing
    - Full cycle write and emission flow
  - Contract validation tests:
    - All event schemas validate
    - Layer write schemas validate
- **Deliverables**:
  - `tests/k0/modules/consolidation/truth_writer/test_writer.py`
  - `tests/k0/modules/consolidation/truth_writer/test_outbox.py`
  - `tests/k0/modules/consolidation/truth_writer/test_layers.py`
  - `tests/k0/modules/consolidation/truth_writer/test_transaction.py`
  - `tests/k0/modules/consolidation/emission/test_emitter.py`
  - `tests/k0/modules/consolidation/emission/test_gap_emitter.py`
  - `tests/k0/modules/consolidation/emission/test_offset_manager.py`
  - `tests/k0/modules/consolidation/emission/test_r7r8_coordinator.py`
- **Acceptance Criteria**:
  - ≥90% line coverage for truth_writer and emission modules
  - All decision types and event types exercised
  - Integration tests cover full R7/R8 phase flow
  - Error recovery paths tested
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

---

## Milestone 6 — Ops readiness: observability, DLQ, security/privacy, performance

### Epic 6.1 — Metrics/tracing/logging implementation

#### Issue 6.1.1 — P03 metrics registry and exporter integration

- **Goal**: Establish centralized metrics registry integrating with K0 MetricsExporter for Prometheus-compatible emission.
- **Scope**:
  - Create `P03MetricsRegistry` in `k0/modules/consolidation/observability/metrics_registry.py`
  - Integrate with `k0/obs/metrics.py` MetricsExporter
  - Define all P03 metric types per dossier Section 8.2:
    - Counters: p03_cycle_total, p03_events_processed_total, p03_decisions_total, p03_gaps_detected_total
    - Histograms: p03_cycle_duration_seconds, p03_phase_duration_seconds, p03_decision_confidence, p03_similarity_scores
    - Gauges: p03_pending_events, p03_layer_size, p03_layer_avg_confidence
  - Support label dimensions: tenant_id, space_id, phase, decision_type, layer, status
  - Implement metric naming convention validation (p03_ prefix)
- **Deliverables**:
  - `k0/modules/consolidation/observability/metrics_registry.py`
  - `k0/contracts/modules/observability/metrics_schema.yaml`
- **Acceptance Criteria**:
  - All metrics registered with K0 MetricsExporter
  - Metrics scrapable via Prometheus endpoint
  - Label cardinality bounded (no unbounded dimensions)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2 "Metric Definitions", Appendix D.9.1 "Metrics Export Pattern")

---

#### Issue 6.1.2 — Consolidation cycle metrics implementation

- **Goal**: Implement core cycle-level metrics for monitoring consolidation health and throughput.
- **Scope**:
  - Implement cycle metrics per dossier Section 8.2.1:
    - `p03_cycle_total` (Counter): labels [tenant_id, status] where status ∈ {success, failure, partial, aborted}
    - `p03_cycle_duration_seconds` (Histogram): buckets [1, 5, 10, 30, 60, 120, 300, 600]
    - `p03_events_processed_total` (Counter): labels [tenant_id, space_id, outcome] where outcome ∈ {consolidated, duplicate, pruned}
    - `p03_pending_events` (Gauge): labels [tenant_id, space_id]
  - Create `CycleMetricsCollector` in `k0/modules/consolidation/observability/cycle_metrics.py`
  - Instrument R0 (cycle start) and R8 (cycle end) phases
  - Support batch size tracking and queue depth monitoring
- **Deliverables**:
  - `k0/modules/consolidation/observability/cycle_metrics.py`
- **Acceptance Criteria**:
  - Cycle count increments on each consolidation run
  - Duration histogram captures full R0-R8 time
  - Pending queue accurately reflects unconsolidated events
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.1 "Consolidation Cycle Metrics")

---

#### Issue 6.1.3 — Phase timing histograms per R0-R8

- **Goal**: Implement per-phase duration histograms for identifying performance bottlenecks.
- **Scope**:
  - Implement `p03_phase_duration_seconds` (Histogram) per dossier Section 8.2.1:
    - Labels: [tenant_id, phase] where phase ∈ {R0, R1, R2, R3, R4, R5, R6, R7, R8}
    - Buckets: [0.1, 0.5, 1, 5, 10, 30, 60, 120] seconds
  - Create `PhaseTimingCollector` in `k0/modules/consolidation/observability/phase_timing.py`
  - Instrument each phase coordinator with timing start/end
  - Support phase skip tracking (e.g., R5 skip, R2 single-event skip)
  - Emit phase-specific metrics from Appendix G.5:
    - R0: p03_r0_batch_size, p03_r0_duration_ms
    - R1: p03_r1_avg_importance
    - R2: p03_r2_clusters, p03_r2_noise_count
    - R3: p03_r3_dedup_count, p03_r3_prune_count
    - R4: p03_r4_entities, p03_r4_edges, p03_r4_gaps
    - R5: p03_r5_insights, p03_r5_skipped
    - R6: p03_r6_staged_count
    - R7: p03_r7_writes, p03_r7_failures
    - R8: p03_r8_events_emitted, p03_r8_gaps_detected
- **Deliverables**:
  - `k0/modules/consolidation/observability/phase_timing.py`
- **Acceptance Criteria**:
  - Each phase emits duration histogram observation
  - Phase-specific metrics captured per dossier Appendix G.5
  - Skipped phases emit p03_r{N}_skipped counter
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.5 "Metrics Per Phase")

---

#### Issue 6.1.4 — Decision metrics implementation (by type/layer)

- **Goal**: Implement reconciliation decision metrics for monitoring decision distribution and confidence.
- **Scope**:
  - Implement metrics per dossier Section 8.2.2:
    - `p03_decisions_total` (Counter): labels [tenant_id, decision_type, target_layer]
      - decision_type ∈ {REINFORCE, EXTEND, CREATE, EVOLVE, PRUNE, CONTRADICT}
      - target_layer ∈ {st_epi, st_sem, st_procedural, st_social, st_kg_dom, st_kg_edges, st_prospective}
    - `p03_decision_confidence` (Histogram): labels [tenant_id, decision_type], buckets [0.1-0.99]
    - `p03_similarity_scores` (Histogram): labels [tenant_id, match_result] where match_result ∈ {match, partial, no_match}
  - Create `DecisionMetricsCollector` in `k0/modules/consolidation/observability/decision_metrics.py`
  - Instrument R3 (reconciliation) and R7 (write) phases
- **Deliverables**:
  - `k0/modules/consolidation/observability/decision_metrics.py`
- **Acceptance Criteria**:
  - Decision distribution visible per type and layer
  - Confidence histogram enables threshold tuning analysis
  - Similarity scores correlate with decision outcomes
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.2 "Decision Metrics")

---

#### Issue 6.1.5 — Gap detection metrics for P06 integration

- **Goal**: Implement knowledge gap detection metrics for monitoring Active Learning demand.
- **Scope**:
  - Implement metrics per dossier Section 8.2.3:
    - `p03_gaps_detected_total` (Counter): labels [tenant_id, gap_type]
      - gap_type ∈ {AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE, MISSING_ATTRIBUTE, CONTRADICTION, CONCEPT_DRIFT, STRUCTURAL_HOLE, STALE_ANCHOR}
    - `p03_gap_importance_score` (Histogram): labels [tenant_id, gap_type], buckets [0.1-1.0]
    - `p03_gaps_pending` (Gauge): labels [tenant_id, gap_type, status] where status ∈ {PENDING, RESOLVED, EXPIRED}
  - Create `GapMetricsCollector` in `k0/modules/consolidation/observability/gap_metrics.py`
  - Instrument M25 GapDetector and R8 gap emission
- **Deliverables**:
  - `k0/modules/consolidation/observability/gap_metrics.py`
- **Acceptance Criteria**:
  - Gap distribution visible by type
  - Importance histogram enables priority tuning
  - Pending queue depth alerts on P06 backlog
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.3 "Gap Detection Metrics")

---

#### Issue 6.1.6 — Memory layer metrics implementation

- **Goal**: Implement memory layer health metrics for monitoring growth and quality.
- **Scope**:
  - Implement metrics per dossier Section 8.2.4:
    - `p03_layer_records_total` (Counter): labels [tenant_id, layer, operation]
      - operation ∈ {create, update, archive, tombstone}
    - `p03_layer_size` (Gauge): labels [tenant_id, layer, archival_status]
    - `p03_layer_avg_confidence` (Gauge): labels [tenant_id, layer]
    - `p03_layer_avg_decay` (Gauge): labels [tenant_id, layer]
  - Create `LayerMetricsCollector` in `k0/modules/consolidation/observability/layer_metrics.py`
  - Instrument R7 layer writers
  - Support periodic snapshot updates (not per-write)
- **Deliverables**:
  - `k0/modules/consolidation/observability/layer_metrics.py`
- **Acceptance Criteria**:
  - Layer sizes trackable over time
  - Confidence/decay trends visible per layer
  - Archive vs active ratio monitorable
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.4 "Memory Layer Metrics")

---

#### Issue 6.1.7 — Module performance metrics (M18-M25)

- **Goal**: Implement per-module performance metrics for identifying slow modules.
- **Scope**:
  - Implement metrics per dossier Section 8.2.5:
    - `p03_module_duration_seconds` (Histogram): labels [tenant_id, module]
      - module ∈ {M18, M19, M20, M21, M22, M23, M24, M25}
      - buckets [0.01, 0.05, 0.1, 0.5, 1, 5, 10, 30]
    - `p03_module_items_processed` (Counter): labels [tenant_id, module, outcome]
    - `p03_clustering_clusters_created` (Counter): labels [tenant_id]
    - `p03_clustering_cluster_size` (Histogram): buckets [1, 2, 5, 10, 20, 50, 100]
  - Create `ModuleMetricsCollector` in `k0/modules/consolidation/observability/module_metrics.py`
  - Instrument each module's run() entry/exit
- **Deliverables**:
  - `k0/modules/consolidation/observability/module_metrics.py`
- **Acceptance Criteria**:
  - Module duration p99 identifiable
  - Throughput per module trackable
  - Clustering metrics correlate with R2 phase
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.5 "Module Performance Metrics")

---

#### Issue 6.1.8 — Shadow mode and learning metrics

- **Goal**: Implement shadow mode comparison and learning performance metrics.
- **Scope**:
  - Implement shadow metrics per dossier Section 8.2.6:
    - `p03_shadow_executions_total` (Counter): labels [tenant_id, learning_type, outcome]
      - learning_type ∈ {importance, hebbian, decay, similarity, threshold}
      - outcome ∈ {agreement, improvement, regression, divergence}
    - `p03_shadow_agreement_rate` (Gauge): labels [tenant_id, learning_type]
    - `p03_shadow_improvement_rate` (Gauge): labels [tenant_id, learning_type]
    - `p03_shadow_regression_rate` (Gauge): labels [tenant_id, learning_type]
    - `p03_shadow_promotion_eligibility` (Gauge): 0/1 per learning_type
  - Implement learning budget metrics per Section 8.2.2:
    - `p03_learning_time_pct` (Gauge): percentage of cycle time
    - `p03_learning_latency_ms` (Histogram): buckets [1-1000ms]
    - `p03_learning_budget_exceeded` (Counter): when >5%
  - Create `ShadowModeMetricsCollector` in `k0/modules/consolidation/observability/shadow_metrics.py`
- **Deliverables**:
  - `k0/modules/consolidation/observability/shadow_metrics.py`
  - `k0/modules/consolidation/observability/learning_metrics.py`
- **Acceptance Criteria**:
  - Shadow mode outcome distribution visible
  - Promotion eligibility calculable from metrics
  - Learning budget alerts at >4% (warning) and >5% (critical)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.6 "Shadow Mode Learning Metrics", Section 8.2.2 "Learning Performance Metrics")

---

#### Issue 6.1.9 — Decay engine metrics (resurrections, immunity)

- **Goal**: Implement decay engine metrics for monitoring memory lifecycle health.
- **Scope**:
  - Implement metrics per dossier Section 8.2.7:
    - `p03_decay_total_active` (Gauge): labels [tenant_id, space_id]
    - `p03_decay_total_archived` (Gauge): labels [tenant_id, space_id]
    - `p03_decay_total_tombstoned` (Gauge): labels [tenant_id, space_id]
    - `p03_decay_resurrections_total` (Counter): labels [tenant_id, space_id, layer, trigger]
      - trigger ∈ {QUERY, CO_OCCURRENCE, USER_MENTION}
    - `p03_resurrection_rate` (Gauge): resurrections per 1000 accesses
    - `p03_resurrection_loops` (Counter): entities with resurrection_count ≥ 3
    - `p03_decay_immune_entities` (Gauge): labels [tenant_id, space_id, layer, reason]
    - `p03_decay_immune_skipped` (Counter): decay updates skipped
    - `p03_premature_archival_rate` (Gauge): accessed within 7 days of archival
  - Create `DecayMetricsCollector` in `k0/modules/consolidation/observability/decay_metrics.py`
  - Instrument M20 RetentionEnforcer and UnifiedDecayEngine
- **Deliverables**:
  - `k0/modules/consolidation/observability/decay_metrics.py`
- **Acceptance Criteria**:
  - Resurrection rate alerts on instability (loops ≥ 3)
  - Immunity coverage visible per layer
  - Premature archival rate enables λ tuning
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.7 "Decay Engine Metrics")

---

#### Issue 6.1.10 — Distributed tracing span hierarchy implementation

- **Goal**: Implement OpenTelemetry-compatible distributed tracing with proper span hierarchy.
- **Scope**:
  - Integrate with `k0/obs/tracing.py` TracerFactory per dossier Section 8.3
  - Implement span hierarchy per dossier Section 8.3.1:

    ```
    p03.consolidation_cycle (root)
    ├── p03.r0.batch_selection
    ├── p03.r1.importance_scoring
    ├── p03.r2.episodic_integration
    │   └── p03.r2.clustering (child)
    ├── p03.r3.duplicate_detection
    │   └── p03.r3.decay_calculation
    ├── p03.r4.kg_consolidation
    │   ├── p03.r4.entity_resolution
    │   └── p03.r4.edge_discovery
    ├── p03.r5.dream_phase
    ├── p03.r6.staging
    ├── p03.r7.memory_writes
    │   └── p03.r7.layer_write (per layer)
    └── p03.r8.event_emission
    ```

  - Create `P03Tracer` in `k0/modules/consolidation/observability/tracer.py`
  - Support span attributes: cycle_id, batch_size, event_count, decision_count
  - Support span events for significant milestones
- **Deliverables**:
  - `k0/modules/consolidation/observability/tracer.py`
- **Acceptance Criteria**:
  - Full trace visible in Jaeger/Zipkin
  - Span hierarchy matches dossier specification
  - Cross-phase correlation via trace_id
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.3 "Distributed Tracing", Appendix D.9.2 "Distributed Tracing Pattern")

---

#### Issue 6.1.11 — Trace context propagation (cycle_id, tenant_id, space_id baggage)

- **Goal**: Implement trace context propagation across phases and into bus events.
- **Scope**:
  - Implement TraceContext per dossier Section 8.3.2:
    - Required baggage: cycle_id, tenant_id, space_id, correlation_id
    - Optional baggage: source_event_ids, triggered_by, parent_cycle_id
  - Create `TraceContextPropagator` in `k0/modules/consolidation/observability/trace_context.py`
  - Implement `inject_into_event()` for bus event trace injection
  - Support trace_id and span_id extraction from incoming messages
  - Enable cross-service correlation with P06, P08
- **Deliverables**:
  - `k0/modules/consolidation/observability/trace_context.py`
- **Acceptance Criteria**:
  - Baggage propagates across all phases
  - Bus events contain trace context
  - Cross-pipeline traces linkable (P03 → P06)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.3.2 "Trace Context Propagation")

---

#### Issue 6.1.12 — Structured logging schema and context fields

- **Goal**: Implement structured JSON logging with consistent context fields.
- **Scope**:
  - Integrate with `k0/obs/log.py` and structlog per dossier Section 8.4
  - Implement P03_LOG_SCHEMA per dossier Section 8.4.1:
    - Required: timestamp, level, message, correlation_id
    - P03-specific: cycle_id, phase, tenant_id, space_id
    - Contextual: event_id, decision_type, target_layer, duration_ms, error_code
  - Create `P03Logger` in `k0/modules/consolidation/observability/logger.py`
  - Support log context inheritance across phases
  - Implement log enrichment with trace_id
- **Deliverables**:
  - `k0/modules/consolidation/observability/logger.py`
  - `k0/contracts/modules/observability/log_schema.yaml`
- **Acceptance Criteria**:
  - All logs emit as valid JSON
  - Context fields consistent across phases
  - Logs correlatable with traces
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.4.1 "Log Schema", Appendix D.9.3 "Structured Logging Pattern")

---

#### Issue 6.1.13 — Log levels by phase matrix implementation

- **Goal**: Implement phase-appropriate log levels following dossier matrix.
- **Scope**:
  - Implement log level matrix per dossier Section 8.4.2:

    | Phase | INFO | DEBUG | WARN | ERROR |
    |-------|------|-------|------|-------|
    | R0 | Cycle start, trigger | Lock acquisition | Lock contention | Lock timeout |
    | R1 | Batch size, importance range | Per-event scoring | Low-importance batch | Batch failed |
    | R2 | Cluster count, avg size | Per-cluster details | Oversized clusters | Clustering failed |
    | R3 | Duplicates, pruned | Per-event decisions | High novelty conflicts | Dedup error |
    | R4 | Entities/edges created | Resolution details | Ambiguous entities | KG update failed |
    | R5 | Insights generated | Counterfactual details | No insights | Exploration error |
    | R6 | Events updated | Per-event status | Update conflicts | Staging failed |
    | R7 | Records written | Per-layer counts | Retry scenarios | Write failed |
    | R8 | Events emitted, gaps | Per-event emission | Bus unavailable | Emission failed |

  - Create `PhaseLogLevelConfig` in `k0/modules/consolidation/observability/log_levels.py`
  - Support runtime log level adjustment per phase
- **Deliverables**:
  - `k0/modules/consolidation/observability/log_levels.py`
- **Acceptance Criteria**:
  - Log verbosity appropriate per phase
  - DEBUG logs suppressible in production
  - WARN/ERROR logs always captured
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.4.2 "Log Levels by Phase")

---

#### Issue 6.1.14 — Cross-space leakage detection metrics

- **Goal**: Implement security metrics for detecting cross-space data access attempts.
- **Scope**:
  - Implement metrics per dossier Section 8.1:
    - `p03_cross_space_query_attempts` (Counter): labels [table, query_type]
    - `p03_rls_policy_blocks` (Counter): labels [table, policy_name]
    - `p03_isolation_health` (Gauge): 1 if no violations, 0 otherwise
  - Create `CrossSpaceLeakageDetector` in `k0/modules/consolidation/observability/security_metrics.py`
  - Integrate with RLS policy monitoring
  - Support weekly automated scan job
  - Implement alert: P03CrossSpaceLeakageDetected (critical if > 0)
- **Deliverables**:
  - `k0/modules/consolidation/observability/security_metrics.py`
- **Acceptance Criteria**:
  - Any cross-space attempt triggers immediate alert
  - RLS block spikes detected (> 10/5min)
  - Isolation health gauge reflects weekly scan
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.1 "Cross-Space Leakage Detection")

---

#### Issue 6.1.15 — Formula debug tracing (3-level: User/Ops/Debug)

- **Goal**: Implement formula-level debug tracing with configurable sampling.
- **Scope**:
  - Implement 3-level tracing per dossier Section 8.5.1:

    | Level | Audience | Content | Retention |
    |-------|----------|---------|-----------|
    | User | End users | Natural language explanation | 90 days |
    | Ops | Support | Structured audit + decision path | 90 days |
    | Debug | Developers | Full computation trace + intermediates | 7 days |

  - Create `FormulaTracer` in `k0/modules/consolidation/observability/formula_tracer.py`
  - Implement trace content per dossier:
    - Input capture (values, types, feature flags, context)
    - Step-by-step computation (intermediates, branch decisions)
    - Performance timing (per-step, total)
    - Output details (decision, confidence, side effects)
  - Support sampling rate config: `P03_FF_DEBUG_TRACE_RATE` (default 1%)
  - Always trace: errors, rollbacks, anomalies
  - Implement metrics: p03_debug_traces_captured, p03_debug_trace_storage_bytes, p03_debug_trace_sampling_rate
- **Deliverables**:
  - `k0/modules/consolidation/observability/formula_tracer.py`
  - `k0/contracts/modules/observability/formula_trace_schema.yaml`
- **Acceptance Criteria**:
  - Debug traces capture full computation path
  - Sampling rate configurable via feature flag
  - Trace storage bounded by retention policy
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.5.1 "Formula Debug Tracing")

---

#### Issue 6.1.16 — Formula comparison metrics (new vs old version)

- **Goal**: Implement metrics for comparing formula versions during shadow mode and canary rollout.
- **Scope**:
  - Implement comparison metrics per dossier Section 8.7:
    - Memory retrieval accuracy: P04 grounding rate by formula version
    - Decay calibration error: Regret signal rate by version
    - Processing time: p99 latency comparison
    - Edge case handling: Error rate delta
  - Create `FormulaComparisonMetrics` in `k0/modules/consolidation/observability/formula_comparison.py`
  - Support Prometheus queries for side-by-side comparison
  - Implement statistical significance check (p < 0.05)
  - Support anomaly highlighting for regressions > 5%
- **Deliverables**:
  - `k0/modules/consolidation/observability/formula_comparison.py`
- **Acceptance Criteria**:
  - Version comparison visible in dashboards
  - Regression > 5% triggers alert
  - Statistical significance calculated before winner declared
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.7 "Formula Comparison Metrics")

---

#### Issue 6.1.17 — Grafana dashboard definitions

- **Goal**: Create Grafana dashboard JSON definitions for P03 monitoring.
- **Scope**:
  - Implement dashboards per dossier Section 8.5:
    - **P03 Health Dashboard** (Section 8.5.1):
      - Cycle overview: cycles/24h, success rate, duration p95
      - Event processing: events/hour, pending queue
      - Decision distribution: pie chart by type
    - **Memory Growth Dashboard** (Section 8.5.2):
      - Layer sizes over time
      - Creation vs archival rate
      - Avg confidence/decay per layer
    - **P03 Learning Performance Dashboard**:
      - Learning time % (target <5%)
      - Queue depth and overflow
      - Latency p99 by operation
    - **Gap Queue Dashboard**:
      - Pending gaps by type
      - Resolution rate
      - Queue age distribution
  - Create JSON dashboard definitions in `k0/modules/consolidation/observability/dashboards/`
  - Support variables: tenant_id, space_id, time_range
- **Deliverables**:
  - `k0/modules/consolidation/observability/dashboards/p03_health.json`
  - `k0/modules/consolidation/observability/dashboards/p03_memory_growth.json`
  - `k0/modules/consolidation/observability/dashboards/p03_learning.json`
  - `k0/modules/consolidation/observability/dashboards/p03_gaps.json`
- **Acceptance Criteria**:
  - Dashboards importable into Grafana
  - All dossier-specified panels implemented
  - Variables support multi-tenant filtering
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.5 "Dashboards")

---

#### Issue 6.1.18 — Alerting rules configuration

- **Goal**: Implement Prometheus alerting rules for P03 operational health.
- **Scope**:
  - Implement alerts per dossier Section 8.6:
    - `P03CycleFailureRate`: failure rate > 10% for 15m (warning)
    - `P03PendingQueueHigh`: pending > 10K for 30m (warning)
    - `P03CycleDurationHigh`: p95 > 300s for 30m (warning)
    - `P03GapQueueOverflow`: pending gaps > 500 for 1h (info)
    - `P03CrossSpaceLeakageDetected`: any attempt (critical)
    - `P03LearningBudgetExceeded`: >5% for 5m (warning)
    - `P03LearningQueueOverflow`: >50/min for 5m (critical)
  - Create alert rule YAML in `k0/modules/consolidation/observability/alerts/`
  - Support severity levels: critical, warning, info
  - Include runbook links in annotations
- **Deliverables**:
  - `k0/modules/consolidation/observability/alerts/p03_alerts.yaml`
- **Acceptance Criteria**:
  - All dossier-specified alerts implemented
  - Alerts fire correctly in test scenarios
  - Runbook links resolve to valid documentation
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.6 "Alerting Rules")

---

#### Issue 6.1.19 — Observability unit and integration tests

- **Goal**: Comprehensive test coverage for all observability components.
- **Scope**:
  - Unit tests per component:
    - MetricsRegistry registration and emission
    - CycleMetricsCollector counter/histogram behavior
    - PhaseTimingCollector per-phase tracking
    - DecisionMetricsCollector label dimensions
    - P03Tracer span hierarchy creation
    - TraceContextPropagator baggage handling
    - P03Logger context inheritance
    - FormulaTracer sampling and capture
    - CrossSpaceLeakageDetector violation detection
  - Integration tests:
    - Full cycle metrics emission end-to-end
    - Trace propagation across phases
    - Log correlation with traces
    - Dashboard query validation
    - Alert rule firing scenarios
  - Contract validation:
    - Metrics schema compliance
    - Log schema compliance
    - Trace schema compliance
- **Deliverables**:
  - `tests/k0/modules/consolidation/observability/test_metrics_registry.py`
  - `tests/k0/modules/consolidation/observability/test_cycle_metrics.py`
  - `tests/k0/modules/consolidation/observability/test_tracer.py`
  - `tests/k0/modules/consolidation/observability/test_logger.py`
  - `tests/k0/modules/consolidation/observability/test_formula_tracer.py`
  - `tests/k0/modules/consolidation/observability/test_integration.py`
- **Acceptance Criteria**:
  - ≥90% line coverage for observability module
  - All metric types exercised
  - Trace hierarchy validated
  - Alert conditions tested
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

### Epic 6.2 — DLQ + retries + circuit breakers

> **References**:
>
> - Dossier Section 13: Error Handling & Dead Letter Queue
> - Dossier Section 13.2: Error Classification (TRANSIENT/VALIDATION/LOGIC/FATAL)
> - Dossier Section 13.3: K0 DLQ Integration (P03ErrorHandler)
> - Dossier Section 13.4: Dead Letter Queue Schema (st_dlq)
> - Dossier Section 13.5: Retry Strategy (K0 RetryScheduler)
> - Dossier Section 13.6: Circuit Breaker (External Dependencies)
> - Dossier Section 13.7: Partial Failure Handling (COMMIT_PARTIAL/ROLLBACK_ALL/QUARANTINE_BATCH)
> - Dossier Section 13.8: K0 CLI Integration (k0ctl dlq)
> - Dossier Section 13.9: Edge Case Handling Matrix
> - Dossier Section 13.10: Recovery Procedures
> - Dossier Section 12.2.2: P08 Coordination Circuit Breaker config
> - Dossier Section 6.21: st_feedback_quarantine (Suspicious Signals)

---

#### Issue 6.2.1 — ErrorClassifier implementation

- **Goal**: Implement error classification logic that routes errors to appropriate handling strategies (retry vs DLQ vs alert).
- **Deliverables**:
  - `k0/pipelines/p03/error_handler.py`:
    - `ErrorClassifier` class with `classify_error(error: Exception) -> str` returning one of `TRANSIENT`, `VALIDATION`, `LOGIC`, `FATAL`
    - Classification rules:
      - `TRANSIENT`: ConnectionError, TimeoutError, LockError, RetryableDBError
      - `VALIDATION`: ValidationError, SchemaError, ConstraintError
      - `LOGIC`: ReconciliationError, FormulaError, DataIntegrityError
      - `FATAL`: MemoryError, DiskFullError, OutOfSpaceError
    - Classification metrics: increment `p03_errors_classified_total{error_type=...}`
- **Acceptance Criteria**:
  - All 4 error types correctly routed
  - Unknown exceptions default to `LOGIC` type
  - Classification is deterministic and fast (<1ms)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.2 "Error Classification" table)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.3 "K0 DLQ Integration" `_classify_error()`)

---

#### Issue 6.2.2 — P03ErrorHandler core implementation

- **Goal**: Implement the central error handler that routes errors to retry scheduler, DLQ, and alerting based on classification.
- **Deliverables**:
  - `k0/pipelines/p03/error_handler.py`:
    - `P03ErrorHandler` class with injected dependencies:
      - `dlq_store: DLQStore` (from `k0/storage/dlq.py`)
      - `retry_scheduler: RetryScheduler` (from `k0/outbox/scheduler.py`)
      - `metrics: MetricsExporter` (from `k0/obs/metrics.py`)
      - `emitter: ObservabilityEmitter` (from `k0/obs/events.py`)
    - `handle_error(cycle_id, phase, event_id, error, payload)` method:
      - Classify error
      - Record metric `p03_errors_total{phase=..., error_type=...}`
      - If TRANSIENT: query RetryScheduler.decide() → schedule retry or DLQ
      - If VALIDATION/LOGIC/FATAL: immediate DLQ
      - If LOGIC or FATAL: emit `p03.error.critical.v1` event via ObservabilityEmitter
    - `_get_attempt_count(event_id)` helper to track retry attempts
    - `_schedule_retry(event_id, delay_ms)` helper for retry scheduling
- **Acceptance Criteria**:
  - TRANSIENT errors retry up to max_attempts before DLQ
  - VALIDATION/LOGIC/FATAL go directly to DLQ
  - Critical errors (LOGIC, FATAL) emit alerting events
  - All paths record metrics
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.3 "K0 DLQ Integration" full code block)

---

#### Issue 6.2.3 — DLQRecord and DLQStore P03 integration

- **Goal**: Integrate P03 with K0's DLQStore for recording failed operations.
- **Deliverables**:
  - `k0/pipelines/p03/error_handler.py`:
    - `_send_to_dlq()` method creating `DLQRecord` with:
      - `id`: `{cycle_id}:{phase}:{event_id}`
      - `pipeline_id`: `'p03_consolidation'`
      - `phase`: R0-R8 phase identifier
      - `event_id`, `entity_id`: source identifiers
      - `payload_json`: serialized failed item
      - `error_type`, `error_code`, `error_message`, `stack_trace`
      - `attempt_count`, `max_attempts` (default 3)
      - `last_attempt_at`, `next_attempt_at`
      - `status`: initial `'PENDING'`
  - Ensure P03's DLQ usage is compatible with existing `k0/storage/dlq.py` API
  - Add migration if st_dlq needs P03-specific columns (phase, pipeline_id)
- **Acceptance Criteria**:
  - DLQ records persist with all required fields
  - DLQ records queryable by pipeline_id and phase
  - Idempotent: same error recorded only once (use id as PK)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.4 "Dead Letter Queue Schema (st_dlq)")
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.3 `_send_to_dlq()` code)

---

#### Issue 6.2.4 — P03RetryConfig and RetryScheduler integration

- **Goal**: Implement P03-specific retry configuration with phase overrides.
- **Deliverables**:
  - `k0/pipelines/p03/retry_config.py`:
    - `P03RetryConfig` dataclass:
      - `base_delay_ms: int = 1000`
      - `max_delay_ms: int = 60000`
      - `exponential_base: float = 2.0`
      - `jitter_factor: float = 0.1`
      - `phase_overrides: dict` with:
        - `'R0': {'max_attempts': 5}` (trigger detection can retry more)
        - `'R7': {'max_attempts': 10}` (truth writes critical)
        - `'R8': {'max_attempts': 3}` (bus emission standard)
    - `create_p03_retry_scheduler() -> RetryScheduler` factory function
    - `get_max_attempts(phase: str) -> int` helper
  - Integration: P03ErrorHandler uses P03RetryConfig for phase-aware retry decisions
- **Acceptance Criteria**:
  - Retry delays use exponential backoff with jitter
  - Phase-specific max_attempts respected
  - Scheduler returns `RetryDecision` with `should_retry`, `delay_ms`
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.5 "Retry Strategy (K0 RetryScheduler)")

---

#### Issue 6.2.5 — P03CircuitBreaker base implementation

- **Goal**: Implement circuit breaker state machine for external dependency protection.
- **Deliverables**:
  - `k0/pipelines/p03/circuit_breaker.py`:
    - `CircuitBreakerConfig` dataclass:
      - `name: str`
      - `failure_threshold: int = 5`
      - `success_threshold: int = 3`
      - `timeout_seconds: int = 30`
      - `half_open_attempts: int = 1`
      - `fallback: P08FallbackStrategy`
    - `P03CircuitBreaker` class:
      - States: `CLOSED`, `OPEN`, `HALF_OPEN`
      - `should_allow_request() -> bool`
      - `record_success()` / `record_failure()`
      - `_time_since_opened() -> float`
      - State transitions per dossier spec
    - Integration with K0 chaos toggles: `k0/chaos/toggles.py` for testing
- **Acceptance Criteria**:
  - CLOSED → OPEN after failure_threshold consecutive failures
  - OPEN → HALF_OPEN after timeout_seconds
  - HALF_OPEN → CLOSED after success_threshold consecutive successes
  - HALF_OPEN → OPEN on any failure
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.6 "Circuit Breaker (External Dependencies)")

---

#### Issue 6.2.6 — P08 embedding circuit breaker

- **Goal**: Configure circuit breaker for P08 embedding coordination dependency.
- **Deliverables**:
  - `k0/pipelines/p03/circuit_breaker.py`:
    - `P08_CIRCUIT_BREAKER` instance:
      - `name="p03_p08_coordination"`
      - `failure_threshold=5`
      - `success_threshold=3`
      - `timeout_seconds=30`
      - `half_open_attempts=1`
      - `fallback=P08FallbackStrategy.QUEUE_LOCAL`
    - `P08FallbackStrategy` enum: `QUEUE_LOCAL`, `SKIP_EMBEDDING`, `FAIL_FAST`
  - `k0/pipelines/p03/r2_handler.py`:
    - Wrap P08 embedding calls with circuit breaker check
    - If circuit OPEN: queue locally for retry when circuit closes
  - Metrics:
    - `p03_p08_circuit_state{state=CLOSED|OPEN|HALF_OPEN}` gauge
    - `p03_p08_circuit_open_seconds` histogram (duration of open state)
- **Acceptance Criteria**:
  - P08 failures trigger circuit opening after threshold
  - Local queue drains when circuit closes
  - Metrics track circuit state and duration
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 12.2.2 "P08 Coordination Circuit Breaker")
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.9 "P08 circuit open > 5min" edge case)

---

#### Issue 6.2.7 — Bus dispatcher circuit breaker

- **Goal**: Configure circuit breaker for event bus publishing dependency.
- **Deliverables**:
  - `k0/pipelines/p03/circuit_breaker.py`:
    - `BUS_CIRCUIT_BREAKER` instance:
      - `name="p03_bus_dispatcher"`
      - Same thresholds as P08 circuit breaker
      - `fallback=BusFallbackStrategy.QUEUE_OUTBOX`
    - `BusFallbackStrategy` enum: `QUEUE_OUTBOX`, `FAIL_CYCLE`, `DROP_NON_CRITICAL`
  - `k0/pipelines/p03/r8_handler.py`:
    - Wrap bus publish calls with circuit breaker check
    - If circuit OPEN: queue events to st_outbox for later emission
  - Metrics:
    - `p03_bus_circuit_state{state=...}` gauge
    - `p03_bus_circuit_open_seconds` histogram
- **Acceptance Criteria**:
  - Bus unavailability triggers circuit opening
  - Outbox queue used as fallback
  - Circuit recovery triggers outbox drain
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.6 `P03_CIRCUITS['bus_dispatcher']`)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.9 "R8 | Bus unavailable | Queue events locally")

---

#### Issue 6.2.8 — FAISS index circuit breaker

- **Goal**: Configure circuit breaker for FAISS vector index dependency.
- **Deliverables**:
  - `k0/pipelines/p03/circuit_breaker.py`:
    - `FAISS_CIRCUIT_BREAKER` instance:
      - `name="p03_faiss_index"`
      - Same thresholds as other circuit breakers
      - `fallback=FAISSFallbackStrategy.BRUTE_FORCE`
    - `FAISSFallbackStrategy` enum: `BRUTE_FORCE`, `SKIP_SIMILARITY`, `FAIL_PHASE`
  - `k0/pipelines/p03/r2_handler.py`:
    - Wrap FAISS similarity calls with circuit breaker check
    - If circuit OPEN: fall back to brute-force similarity (slower)
  - Metrics:
    - `p03_faiss_circuit_state{state=...}` gauge
    - `p03_faiss_fallback_total` counter
- **Acceptance Criteria**:
  - FAISS unavailability triggers circuit opening
  - Brute-force fallback maintains functionality (slower)
  - FAISS recovery triggers index rebuild notification
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.6 `P03_CIRCUITS['faiss_index']`)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.9 "FAISS index unavailable" edge case)

---

#### Issue 6.2.9 — Partial failure handling strategies

- **Goal**: Implement configurable partial failure recovery strategies for batch processing.
- **Deliverables**:
  - `k0/pipelines/p03/failure_strategy.py`:
    - `PartialFailureStrategy` enum: `COMMIT_PARTIAL`, `ROLLBACK_ALL`, `QUARANTINE_BATCH`
    - `PartialFailureHandler` class:
      - `handle_partial_failure(successful: List, failed: List, strategy: PartialFailureStrategy)`
      - COMMIT_PARTIAL: commit successful via UnitOfWork, move failed to DLQ, advance offset to last successful
      - ROLLBACK_ALL: rollback entire batch, do not advance offset
      - QUARANTINE_BATCH: move entire batch to DLQ with special status, advance offset
    - Strategy selection based on failure rate threshold (e.g., >20% → QUARANTINE_BATCH)
  - Integration with K0:
    - `k0/uow/unit_of_work.py`: UnitOfWork._commit() /_rollback()
    - `k0/storage/offsets.py`: OffsetStore.upsert()
- **Acceptance Criteria**:
  - All 3 strategies implemented and tested
  - Strategy selection based on configurable thresholds
  - Offset management correct for each strategy
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.7 "Partial Failure Handling" diagram)

---

#### Issue 6.2.10 — st_feedback_quarantine schema

- **Goal**: Implement quarantine table for suspicious feedback signals.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_feedback_quarantine.py`:
    - Create `st_feedback_quarantine` table per dossier Section 6.21:
      - `quarantine_id TEXT PRIMARY KEY`
      - `signal_id TEXT NOT NULL` (FK to st_feedback_signals)
      - `space_id TEXT NOT NULL`
      - `reason TEXT NOT NULL` CHECK IN ('RATE_LIMIT', 'VELOCITY_SPIKE', 'ANOMALY', 'ENTROPY')
      - `severity TEXT NOT NULL` CHECK IN ('LOW', 'MEDIUM', 'HIGH')
      - `detected_at BIGINT NOT NULL`
      - `reviewed_at BIGINT` (nullable)
      - `reviewed_by TEXT` (nullable)
      - `decision TEXT` CHECK IN ('RELEASE', 'DISCARD', NULL)
      - `auto_release_at BIGINT NOT NULL` (48h after detected_at)
    - Indexes: `idx_quarantine_space_status`, `idx_quarantine_auto_release`, `idx_quarantine_signal`
    - RLS policy: `quarantine_isolation` for multi-tenant isolation
- **Acceptance Criteria**:
  - Migration applies cleanly
  - RLS enforces space isolation
  - Indexes optimize pending/auto-release queries
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.21 "st_feedback_quarantine")

---

#### Issue 6.2.11 — QuarantineDetector implementation

- **Goal**: Implement detection logic for suspicious feedback signals.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/quarantine_detector.py`:
    - `QuarantineDetector` class:
      - `detect_suspicious(signal: FeedbackSignal) -> Optional[QuarantineReason]`
      - Detection rules:
        - `RATE_LIMIT`: FeedbackRateLimiter reports exceeded
        - `VELOCITY_SPIKE`: VelocityAnomalyDetector reports spike
        - `ANOMALY`: P21 anomaly flag present
        - `ENTROPY`: signal entropy exceeds threshold
    - `quarantine_suspicious_signal(signal_id, space_id, reason, severity)` method:
      - Insert into st_feedback_quarantine
      - Set `auto_release_at` = detected_at + 48 hours
      - Emit security alert if severity == 'HIGH'
    - `QuarantineReason` enum: `RATE_LIMIT`, `VELOCITY_SPIKE`, `ANOMALY`, `ENTROPY`
    - `QuarantineSeverity` enum: `LOW`, `MEDIUM`, `HIGH`
- **Acceptance Criteria**:
  - All 4 detection reasons implemented
  - High-severity quarantines emit security alerts
  - Quarantine records created with correct auto_release_at
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.21.3 "Quarantine Process")

---

#### Issue 6.2.12 — FeedbackRateLimiter implementation

- **Goal**: Implement rate limiting for feedback signals per user/device.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/rate_limiter.py`:
    - `FeedbackRateLimiter` class:
      - `__init__(max_signals_per_minute: int = 100)`
      - `window_size: int = 60` seconds
      - `check_rate_limit(db, space_id, user_id) -> bool` returning True if limit exceeded
      - Query: count signals in st_feedback_signals where space_id, user_id, created_at > window_start
  - Integration with QuarantineDetector:
    - If rate limit exceeded, return `QuarantineReason.RATE_LIMIT`
  - Metrics:
    - `p03_rate_limit_exceeded_total{space_id=...}` counter
- **Acceptance Criteria**:
  - Rate limit enforced per user per space
  - Configurable max_signals_per_minute
  - Query efficient with proper indexes on st_feedback_signals
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.21.4 "Rate Limiting")

---

#### Issue 6.2.13 — VelocityAnomalyDetector implementation

- **Goal**: Detect sudden spikes in feedback signal volume.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/anomaly_detector.py`:
    - `VelocityAnomalyDetector` class:
      - `detect_velocity_spike(db, space_id) -> bool`
      - Compare last 5 minutes rate to last hour average rate
      - Spike threshold: recent_rate > baseline_rate * 10 (10x baseline)
      - recent_window: 5 minutes
      - baseline_window: 60 minutes
  - Integration with QuarantineDetector:
    - If velocity spike detected, return `QuarantineReason.VELOCITY_SPIKE`
  - Metrics:
    - `p03_velocity_spike_detected_total{space_id=...}` counter
    - `p03_feedback_rate_per_minute{space_id=...}` gauge
- **Acceptance Criteria**:
  - Spike detection uses 10x baseline threshold
  - Detection fast (<100ms)
  - False positive rate acceptable (tune via config)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.21.4 "Velocity Anomaly Detection")

---

#### Issue 6.2.14 — Quarantine auto-release job

- **Goal**: Implement background job to auto-release quarantined signals after 48 hours.
- **Deliverables**:
  - `k0/pipelines/p03/maintenance/quarantine_cleanup.py`:
    - `auto_release_quarantined_signals(db) -> int` returning count released
    - Query: find signals where decision IS NULL AND auto_release_at <= now
    - For each:
      - UPDATE st_feedback_quarantine SET reviewed_at=now, reviewed_by='AUTO', decision='RELEASE'
      - UPDATE st_feedback_signals SET quarantine_status='RELEASED' WHERE signal_id=...
    - Return count of released signals
  - Register with K0 PipelineScheduler:
    - Add to `k0/contracts/pipelines/p03_maintenance.yaml`:
      - `trigger: INTERVAL` with `interval_seconds: 3600` (hourly)
    - Handler calls `auto_release_quarantined_signals()`
    - Records `p03_quarantine_auto_released` counter
- **Acceptance Criteria**:
  - Signals auto-released after 48 hours if not reviewed
  - Auto-release updates both quarantine table and signal table
  - Job runs hourly with idempotent behavior
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.21.3 "Auto-Release")

---

#### Issue 6.2.15 — Manual quarantine review API

- **Goal**: Implement API for manual review of quarantined signals.
- **Deliverables**:
  - `k0/pipelines/p03/api/quarantine_review.py`:
    - `review_quarantined_signal(db, quarantine_id, reviewer_id, decision: 'RELEASE'|'DISCARD') -> None`
    - UPDATE st_feedback_quarantine SET reviewed_at, reviewed_by, decision
    - If RELEASE: UPDATE st_feedback_signals SET quarantine_status='RELEASED'
    - If DISCARD: UPDATE st_feedback_signals SET quarantine_status='DISCARDED'
  - Register with K0 CapabilityFabric:
    - Capability: `consolidation.quarantine.review`
    - Handler: `handle_quarantine_review_request`
    - Add to `k0/contracts/capabilities/p03_capabilities.yaml`
  - CLI commands in `k0/cli/commands/quarantine.py`:
    - `k0ctl quarantine list --space <space_id>` - list pending items
    - `k0ctl quarantine show <quarantine_id>` - get details
    - `k0ctl quarantine review <quarantine_id> --decision RELEASE|DISCARD` - submit review
  - Metrics:
    - `p03_quarantine_decisions{decision=RELEASE|DISCARD}` counter
- **Acceptance Criteria**:
  - Review updates both quarantine and signal tables
  - API enforces space isolation via RLS
  - Metrics track review decisions
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.21.3 "Manual Review")

---

#### Issue 6.2.16 — k0ctl dlq commands for P03

- **Goal**: Implement CLI commands for P03 DLQ management.
- **Deliverables**:
  - `k0/cli/commands/dlq.py`:
    - `k0ctl dlq list --pipeline p03_consolidation --status PENDING` - list pending DLQ items
    - `k0ctl dlq get <dlq_id> --verbose` - inspect specific failed event
    - `k0ctl dlq requeue <dlq_id>` - requeue single item for retry
    - `k0ctl dlq requeue-all --pipeline p03_consolidation --max-items 100` - bulk requeue
    - `k0ctl dlq purge --pipeline p03_consolidation --older-than 7d` - purge old items
    - `k0ctl dlq stats --pipeline p03_consolidation` - DLQ statistics
  - Commands use `k0/storage/dlq.py` API: list_pending(), get(), mark_requeued(), purge()
- **Acceptance Criteria**:
  - All 6 CLI commands functional
  - Commands respect pipeline and status filters
  - Purge respects older-than filter
  - Stats shows counts by phase, error_type, status
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.8 "K0 CLI Integration (k0ctl dlq)")
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.10.1 "Manual DLQ Recovery")

---

#### Issue 6.2.17 — P03LearningAnomalyDetector

- **Goal**: Implement pipeline-specific anomaly detection for learning parameters.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/learning_anomaly.py`:
    - `P03LearningAnomalyDetector` class:
      - `check_parameter_drift(param_key, current_value, previous_value) -> bool`
        - Threshold: >20% change in 24h triggers pause + alert
      - `check_contradictory_signals(entity_id, signals: List[FeedbackSignal]) -> bool`
        - Detect opposing signals for same entity (opposite salience_delta signs)
        - Flag for review if detected
      - `check_formula_regression(quality_before, quality_after) -> bool`
        - Threshold: >10% drop triggers auto-rollback
      - `pause_learning(param_key)` / `resume_learning(param_key)` helpers
      - `emit_alert(alert_type, param_key, details)` helper
- **Acceptance Criteria**:
  - Parameter drift >20% triggers pause + alert
  - Contradictory signals flagged for review
  - Formula regression >10% triggers rollback
  - Learning paused until reviewed
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.9 "P03 Learning Anomaly Detection")

---

#### Issue 6.2.18 — Edge case handling implementation

- **Goal**: Implement handlers for dossier-defined edge cases.
- **Deliverables**:
  - `k0/pipelines/p03/edge_cases.py`:
    - Edge case handlers per Section 13.9 matrix:
      - `handle_empty_hipp_events()`: emit `p03.health.idle.v1` event
      - `handle_corrupted_embeddings()`: skip event, flag for P08 re-embedding
      - `handle_partial_r7_failure()`: use COMMIT_PARTIAL strategy
      - `handle_backlog_overflow()`: trigger adaptive batching, increase batch_size to 2000
      - `handle_p08_circuit_open()`: queue locally, process on HALF_OPEN
      - `handle_faiss_unavailable()`: fall back to brute-force
      - `handle_duplicate_trigger()`: idempotent skip
      - `handle_memory_pressure()`: skip R5 via `can_skip_dream_phase()`
      - `handle_kg_explosion()`: partition KG by space_id
  - Metrics per edge case (from Section 13.9):
    - `p03_idle_cycles_total`, `p03_corrupted_embeddings_total`, `p03_partial_write_failures_total`, etc.
- **Acceptance Criteria**:
  - All 9 edge cases have handlers
  - Each handler logs appropriate level and emits metric
  - Edge cases tested in integration tests
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 13.9 "Edge Case Handling Matrix")

---

#### Issue 6.2.19 — Quarantine metrics implementation

- **Goal**: Implement metrics for quarantine monitoring.
- **Deliverables**:
  - `k0/pipelines/p03/obs/quarantine_metrics.py`:
    - `p03_quarantine_signals_total` Counter with labels `reason`, `severity`
    - `p03_quarantine_decisions` Counter with label `decision` (RELEASE, DISCARD, AUTO_RELEASE)
    - `p03_quarantine_auto_released` Counter
    - `p03_quarantine_pending_reviews` Gauge with label `severity`
  - Integration:
    - QuarantineDetector increments `p03_quarantine_signals_total`
    - Manual review increments `p03_quarantine_decisions`
    - Auto-release job increments `p03_quarantine_auto_released`
    - Background gauge updater for `p03_quarantine_pending_reviews`
- **Acceptance Criteria**:
  - All quarantine operations recorded in metrics
  - Pending reviews gauge reflects current state
  - Labels allow filtering by reason/severity/decision
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.21.5 "Metrics & Monitoring")

---

#### Issue 6.2.20 — DLQ + retry integration tests

- **Goal**: Comprehensive testing of error handling, DLQ, retries, and circuit breakers.
- **Deliverables**:
  - `tests/k0/modules/consolidation/resilience/test_error_handler.py`:
    - Test error classification for all 4 types
    - Test retry scheduling with exponential backoff
    - Test DLQ record creation
    - Test critical error alerting
  - `tests/k0/modules/consolidation/resilience/test_circuit_breaker.py`:
    - Test state transitions: CLOSED→OPEN→HALF_OPEN→CLOSED
    - Test P08, Bus, FAISS circuit breakers
    - Test fallback strategies
  - `tests/k0/modules/consolidation/resilience/test_quarantine.py`:
    - Test rate limiting detection
    - Test velocity spike detection
    - Test quarantine insertion
    - Test auto-release after 48h
    - Test manual review
  - `tests/k0/modules/consolidation/resilience/test_partial_failure.py`:
    - Test COMMIT_PARTIAL, ROLLBACK_ALL, QUARANTINE_BATCH strategies
- **Acceptance Criteria**:
  - ≥90% line coverage for resilience module
  - All circuit breaker states tested
  - All quarantine paths tested
  - All partial failure strategies tested
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

### Epic 6.3 — Security & privacy enforcement

> **References**:
>
> - Dossier Section 14: Security & Privacy
> - Dossier Section 14.1: K0 Policy Engine Integration
> - Dossier Section 14.2: Privacy Band Enforcement (GREEN/AMBER/RED)
> - Dossier Section 14.3: K0 ACL Enforcer Integration
> - Dossier Section 14.4: K0 Location Privacy Integration
> - Dossier Section 14.5: Audit Trail (K0 Observability)
> - Dossier Section 14.6: K0 Retention Enforcer Integration
> - Dossier Section 14.7: Data Minimization & GDPR
> - Dossier Section 14.8: Encryption (K0 Crypto Layer)
> - Dossier Section 14.11: Learning Data Isolation
> - Dossier Section 8.1: Cross-Space Leakage Detection
> - Dossier Section 6.17: st_learned_weights RLS
> - Dossier Section 6.19.2: st_pruned_entities RLS
> - Dossier Section 6.20.2: st_consolidation_audit RLS

---

#### Issue 6.3.1 — RLS policy for st_learned_weights

- **Goal**: Implement Row-Level Security for learned weights table to enforce space isolation.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_learned_weights_rls.py`:
    - `ALTER TABLE st_learned_weights ENABLE ROW LEVEL SECURITY;`
    - Create isolation policy:

      ```sql
      CREATE POLICY learned_weights_isolation ON st_learned_weights
        FOR ALL
        USING (space_id = current_setting('app.current_space_id', true));
      ```

    - Create superuser bypass policy:

      ```sql
      CREATE POLICY learned_weights_superuser ON st_learned_weights
        TO superuser
        USING (true);
      ```

  - Verify RLS enabled via `SELECT relrowsecurity FROM pg_class WHERE relname = 'st_learned_weights'`
- **Acceptance Criteria**:
  - RLS enabled on st_learned_weights
  - Queries without context return empty (not other space's data)
  - Superuser can access all data for migrations
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.17 "Row-Level Security")

---

#### Issue 6.3.2 — RLS policy for st_consolidation_audit

- **Goal**: Implement Row-Level Security for audit table to enforce space isolation.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_consolidation_audit_rls.py`:
    - `ALTER TABLE st_consolidation_audit ENABLE ROW LEVEL SECURITY;`
    - Create isolation policy:

      ```sql
      CREATE POLICY audit_isolation ON st_consolidation_audit
        FOR ALL USING (space_id = current_space_id());
      ```

    - Grant access: `GRANT SELECT ON st_consolidation_audit TO p03_role, audit_role;`
    - Grant insert: `GRANT INSERT ON st_consolidation_audit TO p03_role;`
- **Acceptance Criteria**:
  - RLS enabled on st_consolidation_audit
  - Audit queries isolated by space
  - Audit readers can only see their space's decisions
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.20.2 "Row Level Security")
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.5.1 "Decision Audit Schema")

---

#### Issue 6.3.3 — RLS policy for st_pruned_entities

- **Goal**: Implement Row-Level Security for pruned entities table.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_pruned_entities_rls.py`:
    - `ALTER TABLE st_pruned_entities ENABLE ROW LEVEL SECURITY;`
    - Create isolation policy via space memberships:

      ```sql
      CREATE POLICY st_pruned_entities_isolation ON st_pruned_entities
        FOR ALL
        USING (
          space_id IN (
            SELECT space_id FROM st_space_memberships
            WHERE user_id = current_setting('app.current_user_id')::TEXT
          )
        );
      ```

- **Acceptance Criteria**:
  - RLS enabled on st_pruned_entities
  - Only users with space membership can see pruned entities
  - Cross-space pruned entity access blocked
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.19.2 "Row-Level Security")

---

#### Issue 6.3.4 — RLS policy for st_decay_feedback

- **Goal**: Implement Row-Level Security for decay feedback table.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_decay_feedback_rls.py`:
    - `ALTER TABLE st_decay_feedback ENABLE ROW LEVEL SECURITY;`
    - Create isolation policy:

      ```sql
      CREATE POLICY decay_feedback_isolation ON st_decay_feedback
        USING (space_id = current_setting('app.current_space_id')::TEXT);
      ```

    - Grant access: `GRANT SELECT, INSERT ON st_decay_feedback TO p03_role;`
- **Acceptance Criteria**:
  - RLS enabled on st_decay_feedback
  - Decay observations isolated by space
  - No cross-space decay data leakage
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.22 "st_decay_feedback")

---

#### Issue 6.3.5 — Application context setup helper

- **Goal**: Implement helper to set space_id in session for RLS enforcement.
- **Deliverables**:
  - `k0/pipelines/p03/security/context.py`:
    - `set_space_context(conn: Connection, space_id: str) -> None`:
      - Execute `SET LOCAL app.current_space_id = $1`
      - Must be called at connection start within transaction
    - `set_tenant_context(conn: Connection, tenant_id: str) -> None`:
      - Execute `SET LOCAL app.current_tenant_id = $1`
    - `set_user_context(conn: Connection, user_id: str) -> None`:
      - Execute `SET LOCAL app.current_user_id = $1`
    - `get_current_space_id(conn: Connection) -> str`:
      - Execute `SELECT current_setting('app.current_space_id', true)`
  - `k0/pipelines/p03/context_manager.py`:
    - Context manager for automatic context setup:

      ```python
      async with space_context(db, space_id) as conn:
          # All queries filtered by RLS
      ```

- **Acceptance Criteria**:
  - Context set at connection acquisition
  - Context cleared after transaction commit
  - All P03 database operations use context manager
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.17 "Application Context Setup")

---

#### Issue 6.3.6 — Cross-space isolation integration tests

- **Goal**: Comprehensive testing of RLS-based space isolation.
- **Deliverables**:
  - `tests/k0/modules/consolidation/security/test_cross_space_isolation.py`:
    - `test_cross_space_isolation()`:
      - Create data in space_a
      - Set context to space_b
      - Query data → assert empty result (not space_a's data)
    - `test_rls_enforcement()`:
      - Verify RLS enabled on all learning tables:
        - st_learned_weights
        - st_consolidation_audit
        - st_pruned_entities
        - st_decay_feedback
        - st_feedback_signals
        - st_feedback_quarantine
      - Check `SELECT relrowsecurity FROM pg_class WHERE relname = ?`
    - `test_no_cross_space_joins()`:
      - Verify code doesn't contain JOINs without space_id filters
      - Static analysis or query log scanning
- **Acceptance Criteria**:
  - All 6 learning tables have RLS enabled
  - Cross-space access returns empty, not other space's data
  - No exceptions or privilege escalation paths
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.1 "Cross-Space Leakage Detection" testing section)

---

#### Issue 6.3.7 — RLS enforcement verification job

- **Goal**: Implement automated verification that RLS is active on all learning tables.
- **Deliverables**:
  - `k0/pipelines/p03/security/rls_verifier.py`:
    - `verify_rls_enabled(db) -> List[str]`:
      - Check each table: `SELECT relrowsecurity FROM pg_class WHERE relname = $1`
      - Return list of tables missing RLS
    - `verify_rls_policies(db, table: str) -> List[PolicyInfo]`:
      - Query: `SELECT polname, polcmd, qual FROM pg_policies WHERE tablename = $1`
      - Return policy details
    - `emit_rls_health_metric()`:
      - Set `p03_isolation_health` gauge to 1 if all tables protected, 0 otherwise
  - Tables to verify:
    - st_learned_weights, st_consolidation_audit, st_pruned_entities
    - st_decay_feedback, st_feedback_signals, st_feedback_quarantine
- **Acceptance Criteria**:
  - Verification runs on startup
  - Missing RLS triggers critical alert
  - Health metric reflects current state
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.1 `check_rls_policies()`)

---

#### Issue 6.3.8 — Query audit scanner for missing space_id

- **Goal**: Implement automated scan for queries missing space_id filters.
- **Deliverables**:
  - `k0/pipelines/p03/security/query_auditor.py`:
    - `CrossSpaceAuditor` class:
      - `audit_queries(time_window_hours: int = 168) -> List[Violation]`:
        - Query pg_stat_statements for queries to learning tables
        - Flag queries without `space_id` in WHERE clause
        - Return list of violations
      - `weekly_scan()`:
        - Call `audit_queries(168)` for last week
        - Call `check_rls_policies()`
        - Call `verify_no_cross_space_joins()`
      - `emit_alert(alert_type, details)`:
        - If violations found, emit security alert
        - Set `p03_isolation_health` gauge to 0
  - Metrics:
    - `p03_cross_space_query_attempts` Counter (should always be 0)
    - `p03_rls_policy_blocks` Counter (tracks RLS enforcement)
    - `p03_isolation_health` Gauge (1 = healthy, 0 = violations)
- **Acceptance Criteria**:
  - Scans pg_stat_statements for violations
  - Alerts on any query without space_id filter
  - Weekly scan runs automatically
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.1 `CrossSpaceAuditor` class)

---

#### Issue 6.3.9 — Weekly automated security scan job

- **Goal**: Schedule weekly security scan for cross-space violations.
- **Deliverables**:
  - `k0/pipelines/p03/security/weekly_scan.py`:
    - `run_weekly_security_scan() -> SecurityReport`
    - Calls `CrossSpaceAuditor.weekly_scan()`
    - Generates security report
    - Emits alert if violations found
  - Register with K0 PipelineScheduler:
    - Add to `k0/contracts/pipelines/p03_security_scan.yaml`:
      - `trigger: INTERVAL` with `interval_seconds: 604800` (weekly)
      - Or use cron-style via K0 scheduler extension
    - Checklist automated:
      - Review all RLS policies for correctness
      - Audit query logs for missing space_id filters
      - Verify no cross-space JOINs exist in code
      - Test isolation with synthetic cross-space attempts
      - Review `p03_cross_space_query_attempts` metric (should be 0)
  - Register with K0 CapabilityFabric:
    - Capability: `consolidation.security.scan`
    - Handler: `handle_security_scan_request`
    - Add to `k0/contracts/capabilities/p03_capabilities.yaml`
  - CLI commands in `k0/cli/commands/security.py`:
    - `k0ctl security scan --pipeline p03_consolidation` - manual trigger
    - `k0ctl security status --pipeline p03_consolidation` - isolation health
- **Acceptance Criteria**:
  - Job runs weekly
  - Report generated with all checklist items
  - Violations trigger critical alerts
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.1 "Quarterly Manual Review Checklist")

---

#### Issue 6.3.10 — PrivacyBandEnforcer implementation

- **Goal**: Implement privacy band enforcement for cross-event linking.
- **Deliverables**:
  - `k0/pipelines/p03/security/privacy_band.py`:
    - `PrivacyBandEnforcer` class:
      - `BAND_CONSTRAINTS` dict per dossier:
        - GREEN: cross_event_linking=True, cross_actor_linking=True, kg_ingestion=True, location_precision='full'
        - AMBER: cross_event_linking=True, cross_actor_linking=False (same actor only), kg_ingestion=True, location_precision='city'
        - RED: cross_event_linking=False (self only), cross_actor_linking=False, kg_ingestion=False, location_precision='country'
      - `can_link_events(event_a, event_b, stamp_a, stamp_b) -> bool`:
        - RED events can only self-reference
        - AMBER events link only within same actor
        - GREEN events can link freely within space
      - `get_band_constraints(band: str) -> dict`
  - Integration with K0:
    - `k0/policy/pep_syscall.py`: `evaluate_envelope()`, `_lookup_band_policy()`
    - `k0/policy/policy_stamp.py`: `PolicyStamp.band`
- **Acceptance Criteria**:
  - All 3 bands enforced correctly
  - RED events never linked to other events
  - AMBER events only linked within same actor
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.2 "Privacy Band Enforcement")

---

#### Issue 6.3.11 — Location privacy masking

- **Goal**: Implement location masking based on privacy band.
- **Deliverables**:
  - `k0/pipelines/p03/security/location_privacy.py`:
    - `P03LocationPrivacy` class:
      - `process_location_for_kg(event, policy_stamp) -> Optional[dict]`:
        - Get precision for band from K0 location_privacy.py
        - Mask location to allowed precision
        - Return geohash with precision_meters
      - `_precision_to_meters(precision: int) -> int`:
        - Map geohash precision to meters per dossier table
        - 1=5000000 (country), 4=39000 (city), 8=40 (building)
  - Integration with K0:
    - `k0/policy/location_privacy.py`: `mask_location_for_band()`, `get_geohash_precision_for_band()`, `lat_lon_to_geohash()`
- **Acceptance Criteria**:
  - GREEN band: full precision
  - AMBER band: city precision (~10km)
  - RED band: country precision
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.4 "K0 Location Privacy Integration")

---

#### Issue 6.3.12 — Tenant isolation query builder

- **Goal**: Ensure all P03 queries include mandatory tenant/space isolation.
- **Deliverables**:
  - `k0/pipelines/p03/security/query_builder.py`:
    - `P03TenantIsolation` class:
      - `verify_consolidation_access(tenant_id, space_id, actor_id) -> bool`:
        - Use K0 ACL Enforcer to check permission
      - `build_isolated_query(base_query, tenant_id, space_id) -> str`:
        - Append `WHERE tenant_id = :tenant_id AND space_id = :space_id`
        - Raise error if isolation not applied
    - `ConsolidationQueryBuilder` class:
      - All methods MUST include tenant_id filter
      - `build_truth_query(tenant_id, space_id, pattern_type) -> str`
      - `build_event_query(tenant_id, space_id, event_ids) -> str`
      - Static analysis hook to verify all queries have isolation
- **Acceptance Criteria**:
  - All queries include tenant_id and space_id filters
  - Query builder enforces isolation at construction time
  - Missing isolation raises exception
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.3 "K0 ACL Enforcer Integration")

---

#### Issue 6.3.13 — P03AuditTrail implementation

- **Goal**: Implement audit trail for reconciliation decisions via K0 Observability.
- **Deliverables**:
  - `k0/pipelines/p03/security/audit_trail.py`:
    - `P03AuditTrail` class:
      - Injected: `emitter: ObservabilityEmitter`, `obligations: ObligationStore`
      - `log_reconciliation_decision(cycle_id, phase, tenant_id, space_id, decision_type, source_event_id, target_truth_id, similarity_score, confidence_before, confidence_after) -> None`:
        - Emit via K0 ObservabilityEmitter
        - Event type: `p03.reconciliation.decision`
        - Include all parameters and timestamp
      - `log_erasure_completed(erasure_id, tenant_id, actor_id, scope, affected_counts) -> None`:
        - Emit `p03.erasure.completed` event
      - `log_security_event(event_type, details) -> None`:
        - Generic security event logging
- **Acceptance Criteria**:
  - All reconciliation decisions audited
  - Audit events queryable by trace_id, cycle_id
  - Audit stored in st_cognitive_traces via K0
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.5 "Audit Trail (K0 Observability)")

---

#### Issue 6.3.14 — GDPR erasure handler

- **Goal**: Implement GDPR Article 17 erasure request handling.
- **Deliverables**:
  - `k0/pipelines/p03/security/erasure_handler.py`:
    - `P03ErasureHandler` class:
      - `handle_erasure_request(tenant_id, actor_id, erasure_scope) -> ErasureResult`:
        - Scope options: 'ACTOR_DATA', 'ALL_MENTIONS', 'FULL_PURGE'
        - Steps:
          1. Mark st_hipp_events as TOMBSTONE where actor_id matches
          2. Cascade to all truth tables (st_epi, st_sem, etc.)
          3. Remove from st_vec (embedding deletion)
          4. Request FAISS index rebuild from P08 via K0 BusDispatcher
          5. Update st_kg_dom and st_kg_edges (anonymize or delete)
          6. Log erasure in K0 audit trail (ObservabilityEmitter)
          7. Record in K0 WAL for compliance (WriteAheadLog.append())
      - `_cascade_erasure(tenant_id, actor_id, scope) -> dict`:
        - Return affected_counts per table
    - `ErasureResult` dataclass:
      - `erasure_id: str`
      - `status: str` ('COMPLETED', 'PARTIAL', 'FAILED')
      - `affected_counts: dict`
- **Acceptance Criteria**:
  - All memory layers erased/anonymized
  - FAISS index rebuild requested
  - Full audit trail in WAL
  - Erasure completes within SLA
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.7 "Data Minimization & GDPR")

---

#### Issue 6.3.15 — Tombstone lifecycle management

- **Goal**: Implement tombstone semantics for soft deletes.
- **Deliverables**:
  - `k0/pipelines/p03/security/tombstone.py`:
    - `TombstoneManager` class:
      - `mark_tombstone(entity_id, table, reason) -> None`:
        - Set `archival_status = 'TOMBSTONE'`
        - Record tombstone_at timestamp
        - Emit `p03.entity.tombstoned.v1` event
      - `get_tombstoned_entities(older_than_days: int) -> List`:
        - Query for TOMBSTONE entities older than threshold
      - `hard_delete_tombstones(older_than_days: int = 90) -> int`:
        - Delete TOMBSTONE entities older than 90 days
        - Return count deleted
    - Lifecycle: ACTIVE → ARCHIVED → TOMBSTONE → (hard delete after 90 days)
  - Thresholds from dossier:
    - `P03_DECAY_ARCHIVE_THRESHOLD = 0.10` (ACTIVE → ARCHIVED)
    - `P03_DECAY_TOMBSTONE_THRESHOLD = 0.01` (ARCHIVED → TOMBSTONE)
- **Acceptance Criteria**:
  - Tombstone marks entity for deletion without immediate removal
  - Hard delete only after 90-day retention period
  - Full audit trail for all state transitions
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.4.5 "Tombstone Creation & Garbage Collection")
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 3.6.3 decay thresholds)

---

#### Issue 6.3.16 — Retention policy enforcement

- **Goal**: Implement retention policy enforcement for memory layers.
- **Deliverables**:
  - `k0/pipelines/p03/security/retention.py`:
    - `P03RetentionPolicy` class:
      - `apply_band_retention(tenant_id, band) -> int`:
        - Use K0 RetentionEnforcer.apply_policies()
        - RED band: shortest retention
        - GREEN band: longest retention
        - Return records_archived count
      - `get_purgeable_records(tenant_id) -> List`:
        - Use K0 RetentionEnforcer.get_expired_resources()
        - Return list of expired resources
    - Retention periods per band:
      - GREEN: 365 days
      - AMBER: 180 days
      - RED: 30 days
- **Acceptance Criteria**:
  - Retention enforced by privacy band
  - Expired records archived/deleted
  - Metrics track retention operations
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.6 "K0 Retention Enforcer Integration")

---

#### Issue 6.3.17 — Content fingerprinting for dedup

- **Goal**: Implement secure content fingerprinting using K0 crypto layer.
- **Deliverables**:
  - `k0/pipelines/p03/security/crypto.py`:
    - `P03Encryption` class:
      - `SENSITIVE_COLUMNS` dict per dossier:
        - st_hipp_events: body_text, attachments_json, location_name
        - st_epi: episode_summary
        - st_sem: pattern_description, pattern_attributes_json
      - `hash_sensitive_content(content: str) -> str`:
        - Use K0 crypto.hash_payload()
      - `compute_content_fingerprint(event: dict) -> str`:
        - Use K0 crypto.compute_envelope_sha256()
      - `is_sensitive_column(table: str, column: str) -> bool`
  - Integration with K0:
    - `k0/security/crypto.py`: `hash_payload()`, `compute_envelope_sha256()`, `encode_base64url()`
- **Acceptance Criteria**:
  - Fingerprints are deterministic
  - Sensitive columns identified correctly
  - Hash function is cryptographically secure
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 14.8 "Encryption (K0 Crypto Layer)")

---

#### Issue 6.3.18 — Cross-space leakage metrics

- **Goal**: Implement metrics for cross-space leakage detection.
- **Deliverables**:
  - `k0/pipelines/p03/obs/security_metrics.py`:
    - `p03_cross_space_query_attempts` Counter:
      - Labels: `table`, `query_type`
      - Should always be 0
    - `p03_rls_policy_blocks` Counter:
      - Labels: `table`, `policy_name`
      - Tracks queries blocked by RLS
    - `p03_isolation_health` Gauge:
      - 1 if no violations detected, 0 otherwise
    - `p03_erasure_requests_total` Counter:
      - Labels: `scope`, `status`
    - `p03_tombstone_count` Gauge:
      - Labels: `table`, `space_id`
- **Acceptance Criteria**:
  - All security operations recorded in metrics
  - Isolation health reflects current state
  - Cross-space attempts immediately visible
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.1 "Metrics")

---

#### Issue 6.3.19 — Security alerting rules

- **Goal**: Implement alerting rules for security violations.
- **Deliverables**:
  - `k0/telemetry/mixins/p03_security_alerts.py`:
    - Alert rule builder following K0 telemetry patterns
  - Generated output: `k0/telemetry/generated/rules/p03_security_alerts.yaml`:
    - `P03CrossSpaceLeakageDetected`:
      - Expression: `p03_cross_space_query_attempts > 0`
      - Duration: 1m
      - Severity: critical
    - `P03RLSBlockSpike`:
      - Expression: `rate(p03_rls_policy_blocks[5m]) > 10`
      - Duration: 5m
      - Severity: warning
    - `P03IsolationHealthDegraded`:
      - Expression: `p03_isolation_health == 0`
      - Duration: 1m
      - Severity: critical
    - `P03MissingRLSPolicy`:
      - Expression: custom metric from RLS verifier
      - Severity: critical
- **Acceptance Criteria**:
  - All security violations trigger alerts
  - Critical alerts page on-call
  - Alert descriptions include remediation steps
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.1 "Alert Configuration")

---

#### Issue 6.3.20 — Security integration tests

- **Goal**: Comprehensive testing of all security features.
- **Deliverables**:
  - `tests/k0/modules/consolidation/security/test_rls.py`:
    - Test RLS enabled on all tables
    - Test cross-space access returns empty
    - Test superuser bypass works
  - `tests/k0/modules/consolidation/security/test_privacy_bands.py`:
    - Test GREEN band linking rules
    - Test AMBER band same-actor-only
    - Test RED band self-only
  - `tests/k0/modules/consolidation/security/test_erasure.py`:
    - Test erasure cascades to all tables
    - Test FAISS rebuild requested
    - Test audit trail created
  - `tests/k0/modules/consolidation/security/test_tombstone.py`:
    - Test lifecycle transitions
    - Test 90-day hard delete
  - `tests/k0/modules/consolidation/security/test_location_masking.py`:
    - Test precision per band
- **Acceptance Criteria**:
  - ≥90% line coverage for security module
  - All privacy bands tested
  - All erasure paths tested
  - All RLS tables verified
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

### Epic 6.4 — Performance + QoS

> **References**:
>
> - Dossier Section 15: Performance Tuning
> - Dossier Section 15.1: K0 QoS Integration Overview
> - Dossier Section 15.2: K0 Scheduler Integration
> - Dossier Section 15.3: Performance Baselines (Phase Latency, Throughput, Resource Utilization)
> - Dossier Section 15.4: Batch Size Optimization (K0-Aware)
> - Dossier Section 15.5: Embedding Query Optimization
> - Dossier Section 15.6: Memory Management (K0-Aware)
> - Dossier Section 15.7: Database Optimization (PostgreSQL)
> - Dossier Section 15.8: K0 Metrics Export
> - Dossier Section 15.9: Learning Compute Budget
> - Dossier Section 15.10: Learning Batch Processing
> - Dossier Section 10.5: Performance Tests
> - Dossier Section 10.7: Test Fixtures

---

#### Issue 6.4.1 — P03SchedulerIntegration implementation

- **Goal**: Implement integration with K0 QoS Scheduler for token-based resource management.
- **Deliverables**:
  - `k0/pipelines/p03/qos/scheduler_integration.py`:
    - `P03SchedulerIntegration` class:
      - `acquire_batch_token(batch_size: int, band: str = "GREEN") -> Optional[SchedulerToken]`
      - `release_token(token: SchedulerToken) -> None`
    - `P03_SCHEDULER_PROFILES` dict:
      - `BATCH_CONSOLIDATION`: estimated_cost=100.0, port='command'
      - `SIMILARITY_SEARCH`: estimated_cost=50.0, port='query'
      - `DREAM_EXPLORATION`: estimated_cost=200.0, port='command'
  - Integration with K0:
    - `k0/qos/scheduler.py`: `Scheduler.acquire()`, `Scheduler._release()`
    - `k0/qos/metrics.py`: `QoSMetrics.record_acquisition()`
- **Acceptance Criteria**:
  - Token acquired before batch processing starts
  - Token released on batch completion
  - Metrics recorded via K0 QoSMetrics
  - WDRR algorithm respects priority bands (GREEN > AMBER > RED)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.2 "K0 Scheduler Integration")

---

#### Issue 6.4.2 — P03QoSContext budget management

- **Goal**: Implement K0 QoSContext integration for fanout and top_k budget management.
- **Deliverables**:
  - `k0/pipelines/p03/qos/context_integration.py`:
    - `P03QoSContext` class:
      - `check_fanout_budget(required: int) -> bool`
      - `consume_fanout(amount: int) -> bool`
      - `check_top_k_budget(required: int) -> bool`
      - `consume_top_k(amount: int) -> bool`
      - `apply_tightening(obligations: list[dict]) -> None`
    - `P03_QOS_DEFAULTS` dict:
      - `fanout_budget`: 1000 (max cross-event queries per batch)
      - `top_k_budget`: 500 (max similarity results per batch)
  - Integration with K0:
    - `k0/qos/context.py`: `QoSContext.consume_fanout()`, `QoSContext.consume_top_k()`
    - `k0/qos/policy.py`: `apply_qos_obligations()`
- **Acceptance Criteria**:
  - Budget checked before cross-event queries
  - Operations fail gracefully when budget exhausted
  - Tightening applied when policy obligations require it
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.3 "K0 QoSContext Integration")

---

#### Issue 6.4.3 — P03AdaptiveBatchSizer implementation

- **Goal**: Implement K0-aware adaptive batch sizing based on scheduler state and resource constraints.
- **Deliverables**:
  - `k0/pipelines/p03/qos/batch_sizer.py`:
    - `P03AdaptiveBatchSizer` class:
      - `compute_optimal_batch_size(available_memory_mb: int, time_budget_seconds: int) -> int`
    - Factors:
      - Contention factor: >10 active tokens → 0.5x, >5 → 0.75x, else 1.0x
      - Memory factor: available_memory_mb / 512
      - Time factor: time_budget_seconds / 300
    - Output clamped to [100, 10000]
  - Batch size table from dossier:
    - Small (100): 5s latency, 50MB memory, cost=10
    - Medium (1000): 30s latency, 200MB memory, cost=100
    - Large (10000): 5min latency, 1GB memory, cost=1000
- **Acceptance Criteria**:
  - Batch size adapts to K0 scheduler contention
  - Memory and time constraints respected
  - Port utilization reported to K0 QoSMetrics
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.4 "Batch Size Optimization (K0-Aware)")

---

#### Issue 6.4.4 — Phase latency targets implementation

- **Goal**: Implement and track phase latency targets per dossier baselines.
- **Deliverables**:
  - `k0/pipelines/p03/obs/phase_metrics.py`:
    - Phase latency targets (P50/P95/P99):
      - R0: 10ms/50ms/100ms
      - R1: 20ms/100ms/200ms
      - R2: 50ms/200ms/500ms
      - R3: 30ms/150ms/300ms
      - R4: 100ms/300ms/600ms
      - R5: 200ms/500ms/1000ms
      - R6: 10ms/30ms/50ms
      - R7: 50ms/150ms/300ms
      - R8: 5ms/20ms/50ms
      - Full Cycle: 500ms/1500ms/3000ms
    - `record_phase_duration(phase: str, duration_ms: float) -> None`
  - Histogram with buckets: [0.1, 0.5, 1, 5, 10, 30, 60, 120]
- **Acceptance Criteria**:
  - All 9 phases tracked with histograms
  - Full cycle duration tracked
  - Metrics exposed via K0 MetricsExporter
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.3.1 "Phase Latency Targets")

---

#### Issue 6.4.5 — Throughput targets implementation

- **Goal**: Implement throughput tracking and SLO validation.
- **Deliverables**:
  - `k0/pipelines/p03/obs/throughput_metrics.py`:
    - Throughput targets:
      - Events per cycle: 1000
      - Cycles per hour: 40 (90s interval)
      - Events per hour: 40,000
      - Peak events per hour: 100,000 (adaptive batching)
    - `record_batch_size(phase: str, size: int) -> None`
    - `set_backlog_size(tenant_id: str, size: int) -> None`
  - `P03_SLO_TARGETS` dict:
    - `cycle_duration_p99_ms`: 300000 (5 min)
    - `batch_throughput_min`: 100 events/sec
    - `memory_max_mb`: 512
    - `error_rate_max`: 0.01 (1%)
- **Acceptance Criteria**:
  - Throughput metrics tracked in real-time
  - SLO targets configurable
  - Alerts fire when below targets
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.3.2 "Throughput Targets")

---

#### Issue 6.4.6 — Resource utilization tracking

- **Goal**: Implement resource utilization tracking per dossier baselines.
- **Deliverables**:
  - `k0/pipelines/p03/obs/resource_metrics.py`:
    - Resource targets:
      - Memory per cycle: <512MB, alert at 80%
      - CPU per cycle: <2 cores, alert at 90% for >30s
      - DB connections: <10 pooled, alert at 80% exhaustion
      - FAISS queries/cycle: <100
    - Metrics:
      - `p03_memory_mb` Gauge (stage labels)
      - `p03_cpu_utilization` Gauge
      - `p03_db_pool_active` Gauge
      - `p03_faiss_queries_total` Counter
- **Acceptance Criteria**:
  - All resource metrics tracked
  - Alert thresholds match dossier
  - Metrics integrated with K0 ObservabilityEmitter
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.3.3 "Resource Utilization Targets")

---

#### Issue 6.4.7 — P03StreamingProcessor implementation

- **Goal**: Implement streaming event processor to prevent OOM on large datasets.
- **Deliverables**:
  - `k0/pipelines/p03/streaming/processor.py`:
    - `P03StreamingProcessor` class:
      - `process_events_streaming(events: AsyncIterator[HippEvent], batch_size: int = 100) -> None`
    - Per-batch processing with memory release after each batch
    - K0 trace spans for each batch
    - Memory pressure reporting to K0 metrics
  - Memory thresholds from dossier:
    - `warning_mb`: 256 (log warning)
    - `throttle_mb`: 384 (reduce batch size)
    - `critical_mb`: 480 (pause and GC)
- **Acceptance Criteria**:
  - Streaming processes 100K+ events without OOM
  - Memory released between batches
  - Batch count and sizes tracked in metrics
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.6.1 "Streaming with K0 Observability")

---

#### Issue 6.4.8 — P03EmbeddingCache implementation

- **Goal**: Implement LRU cache for embeddings to reduce FAISS query load.
- **Deliverables**:
  - `k0/pipelines/p03/cache/embedding_cache.py`:
    - `P03EmbeddingCache` class:
      - `get(key: str) -> Optional[np.ndarray]`
      - `set(key: str, value: np.ndarray) -> None`
    - Config:
      - `max_size`: 10000 entries
      - `ttl_seconds`: 3600 (1 hour)
    - Metrics:
      - `p03_embedding_cache_hit` Counter
      - `p03_embedding_cache_miss` Counter
      - `p03_embedding_cache_eviction` Counter
      - `p03_embedding_cache_expired` Counter
  - Cache priority levels:
    - `cluster_centroids`: HIGH (always cache)
    - `recent_patterns`: MEDIUM (cache 1 hour)
    - `archived_patterns`: LOW (don't cache)
- **Acceptance Criteria**:
  - LRU eviction when cache full
  - TTL expiration enforced
  - All cache operations tracked in K0 metrics
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.6.2 "Embedding Caching with K0 Metrics")

---

#### Issue 6.4.9 — P03EmbeddingQueryOptimizer implementation

- **Goal**: Implement two-stage retrieval with K0 QoS budget tracking.
- **Deliverables**:
  - `k0/pipelines/p03/qos/query_optimizer.py`:
    - `P03EmbeddingQueryOptimizer` class:
      - `query_similar_patterns(query_embedding: np.ndarray, top_k: int = 10) -> List[PatternMatch]`
    - Two-stage retrieval:
      - Stage 1: FAISS ANN via K0 CapabilityFabric (fast, 3x over-retrieve)
      - Stage 2: Exact cosine similarity for re-ranking (accurate)
    - Raises `QoSBudgetExceededError` if insufficient top_k budget
  - Integration with K0:
    - `k0/fabric/fabric.py`: `CapabilityFabric.invoke()` for P08 embedding
    - `k0/qos/context.py`: `QoSContext.consume_top_k()`
- **Acceptance Criteria**:
  - Budget checked before query
  - Over-retrieve 3x for quality
  - Re-ranking improves precision
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.5 "Embedding Query Optimization (K0-Aware)")

---

#### Issue 6.4.10 — PostgreSQL session optimization

- **Goal**: Implement PostgreSQL session settings for P03 performance.
- **Deliverables**:
  - `k0/pipelines/p03/db/session_config.py`:
    - `P03DatabaseConfig` class:
      - `from_k0_settings(pg_settings: PostgresSettings) -> dict`
    - Session settings from dossier:
      - `statement_timeout`: 300s (5 min max)
      - `lock_timeout`: 30s
      - `idle_in_transaction_session_timeout`: 60s
      - `work_mem`: 256MB
      - `maintenance_work_mem`: 512MB
  - Integration with K0:
    - `k0/config/postgres.py`: `PostgresSettings`
    - `k0/db/pool.py`: `AsyncPgPool`
- **Acceptance Criteria**:
  - Session settings applied at connection time
  - Timeouts prevent stuck transactions
  - Memory settings optimize sorts/hashes
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.7.2 "PostgreSQL Configuration (K0 Kernel Config)")

---

#### Issue 6.4.11 — LearningBudgetManager implementation

- **Goal**: Implement learning budget enforcement (<5% of cycle time).
- **Deliverables**:
  - `k0/pipelines/p03/qos/learning_budget.py`:
    - `LearningBudgetManager` class:
      - `execute_with_budget(component: str, operation: Callable, priority: int) -> Optional[Any]`
      - `get_budget_usage() -> dict`
      - `reset() -> None`
    - Component budget breakdown:
      - `feedback_ingestion`: 20% of 5% = 1% cycle
      - `parameter_update`: 30% of 5% = 1.5% cycle
      - `quality_monitoring`: 30% of 5% = 1.5% cycle
      - `audit_logging`: 20% of 5% = 1% cycle
    - Priority levels: 1=Critical, 2=High, 3=Medium, 4=Low
    - Low priority skipped when budget exhausted
- **Acceptance Criteria**:
  - Learning stays within 5% budget
  - Budget tracked per component
  - Low priority operations skipped if over budget
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.9 "Learning Compute Budget")

---

#### Issue 6.4.12 — Learning budget metrics

- **Goal**: Implement metrics for learning budget tracking.
- **Deliverables**:
  - `k0/pipelines/p03/obs/learning_metrics.py`:
    - Metrics from dossier:
      - `p03_learning_time_pct` Gauge (space_id, component)
      - `p03_learning_latency_ms` Histogram (component, operation)
      - `p03_learning_queue_depth` Gauge (space_id)
      - `p03_learning_queue_overflow` Counter (space_id)
      - `p03_learning_batch_size` Histogram (operation)
      - `p03_learning_batch_duration_ms` Histogram (operation)
      - `p03_learning_skip_count` Counter (component, reason)
      - `p03_learning_budget_exceeded` Counter (space_id)
      - `p03_learning_parameter_updates` Counter (param_key, space_id)
      - `p03_audit_writes` Counter (batch_size)
      - `p03_audit_drops` Counter
- **Acceptance Criteria**:
  - All learning operations tracked
  - Budget percentage calculated per cycle
  - Skip reasons categorized
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.2 "Learning Performance Metrics")

---

#### Issue 6.4.13 — Learning budget alerting

- **Goal**: Implement alerting for learning budget violations.
- **Deliverables**:
  - `k0/telemetry/mixins/p03_learning_alerts.py`:
    - Alert rule builder following K0 telemetry patterns
  - Generated output: `k0/telemetry/generated/rules/p03_learning_alerts.yaml`:
    - `P03LearningBudgetExceeded`:
      - expr: `p03_learning_time_pct > 5`
      - for: 5m
      - severity: warning
    - `P03LearningSkipRateHigh`:
      - expr: `rate(p03_learning_skip_count[1h]) > 10`
      - for: 15m
      - severity: warning
    - `P03LearningQueueOverflow`:
      - expr: `rate(p03_learning_queue_overflow[5m]) > 50`
      - for: 5m
      - severity: critical
    - `P03LearningQueueHigh`:
      - expr: `p03_learning_queue_depth > 500`
      - for: 5m
      - severity: warning
    - `P03LearningQueueCritical`:
      - expr: `p03_learning_queue_depth > 1000`
      - for: 1m
      - severity: critical
- **Acceptance Criteria**:
  - Alerts defined per dossier thresholds
  - Critical alerts page on-call
  - Alert descriptions include context
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.2 "Alert Configuration")

---

#### Issue 6.4.14 — FeedbackQueue with overflow handling

- **Goal**: Implement feedback signal queue with sampling overflow protection.
- **Deliverables**:
  - `k0/pipelines/p03/learning/feedback_queue.py`:
    - `FeedbackQueue` class:
      - `enqueue(signal: FeedbackSignal) -> bool`
      - `dequeue_batch(batch_size: int) -> List[FeedbackSignal]`
      - `depth() -> int`
    - Config:
      - `max_depth`: 1000 signals
    - Overflow strategy: sample 10%, discard 90%
  - Metrics:
    - `p03_learning_queue_overflow` incremented on discard
- **Acceptance Criteria**:
  - Queue never blocks on full
  - Sampling preserves signal diversity
  - Overflow count tracked
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.10 "Queue Management")

---

#### Issue 6.4.15 — AsyncAuditLogger implementation

- **Goal**: Implement non-blocking audit logging with batched writes.
- **Deliverables**:
  - `k0/pipelines/p03/learning/async_audit.py`:
    - `AsyncAuditLogger` class:
      - `start() -> None` (start background writer)
      - `log_audit(record: AuditRecord) -> None` (non-blocking enqueue)
      - `_writer_loop() -> None` (batch writes every 30s)
      - `_write_batch(batch: List[AuditRecord]) -> None`
    - Batch config:
      - Write interval: 30 seconds
      - Max batch size: 50 records
    - Uses `db.executemany()` for batched inserts
- **Acceptance Criteria**:
  - Audit writes non-blocking
  - Batches amortize transaction overhead
  - Drops tracked when queue full
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 15.10 "Async Writes")

---

#### Issue 6.4.16 — P03TestFixtures implementation

- **Goal**: Implement test fixtures for performance testing.
- **Deliverables**:
  - `tests/fixtures/p03.py`:
    - `P03TestFixtures` class:
      - `create_random_events(n: int, tenant_id: str, space_id: str) -> List[dict]`:
        - 768-dim embedding vectors
        - Random salience scores [0.1, 1.0]
        - ULID event IDs
        - MD5 content hashes
      - `create_events_with_patterns(n_events: int, n_patterns: int, events_per_pattern: int) -> List[dict]`
      - `create_semantic_truth(content: str, confidence: float, observation_count: int) -> dict`
      - `create_events_matching_truth(truth: dict, n_events: int, similarity: float) -> List[dict]`
- **Acceptance Criteria**:
  - Fixtures generate valid st_hipp_events schema
  - Pattern-based fixtures enable clustering tests
  - Similarity control enables reinforcement tests
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.7 "Test Fixtures")

---

#### Issue 6.4.17 — Throughput benchmark tests

- **Goal**: Implement throughput benchmark tests per dossier targets.
- **Deliverables**:
  - `tests/k0/pipelines/p03/performance/test_throughput.py`:
    - `TestThroughputBenchmarks` class:
      - `test_consolidation_throughput()`:
        - Setup: 1000 events via `create_random_events(n=1000)`
        - Target: ≥1000 events/minute
        - Assert events_per_minute >= 1000
      - `test_large_batch_cycle_time()`:
        - Setup: 10000 events
        - Target: <5 minutes (300s)
        - Assert elapsed < 300
- **Acceptance Criteria**:
  - Tests marked with `@pytest.mark.performance`
  - Throughput calculated correctly
  - Clear failure messages with actual vs target
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.5 "Performance Tests" - TestThroughputBenchmarks)

---

#### Issue 6.4.18 — Memory footprint benchmark tests

- **Goal**: Implement memory usage benchmark tests per dossier targets.
- **Deliverables**:
  - `tests/k0/pipelines/p03/performance/test_memory.py`:
    - `TestMemoryFootprint` class:
      - `test_peak_memory_under_limit()`:
        - Setup: 10000 events
        - Target: <500MB peak
        - Use `tracemalloc` for measurement
        - Assert peak_mb < 500
      - `test_streaming_prevents_oom()`:
        - Setup: 100000 events
        - Stream with batch_size=1000
        - Assert no MemoryError raised
- **Acceptance Criteria**:
  - Tests marked with `@pytest.mark.performance`
  - Memory measured via tracemalloc
  - Streaming test validates OOM prevention
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.5 "Performance Tests" - TestMemoryFootprint)

---

#### Issue 6.4.19 — Performance dashboard implementation

- **Goal**: Implement Grafana dashboard for learning performance monitoring.
- **Deliverables**:
  - `k0/telemetry/mixins/p03_dashboards.py`:
    - Dashboard builder following K0 telemetry patterns (see `k0/telemetry/mixins/slo_dashboards.py`)
  - Generated output: `k0/telemetry/generated/dashboards/p03_learning_performance.json`:
    - Row 1: Budget Overview
      - Learning Time % gauge (target <5%)
      - Budget by Component bar chart
      - Skip Rate time series
    - Row 2: Queue Health
      - Queue Depth gauge (warning >500)
      - Overflow Rate time series
      - Batch Size Distribution histogram
    - Row 3: Operation Performance
      - Latency p99 by Operation time series
      - Batch Duration histogram
      - Parameter Update Rate time series
    - Row 4: Quality Indicators
      - Signal Confidence Distribution histogram
      - Audit Write Success Rate time series
      - Learning vs Consolidation Time stacked area
  - PromQL queries from dossier Section 8.2.2
- **Acceptance Criteria**:
  - Dashboard imports cleanly into Grafana
  - All panels use correct metrics
  - Layout matches dossier specification
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.2 "Dashboard Layout")

---

#### Issue 6.4.20 — Performance integration tests

- **Goal**: Comprehensive integration testing of all performance components.
- **Deliverables**:
  - `tests/k0/pipelines/p03/performance/test_qos_integration.py`:
    - Test scheduler token acquisition/release
    - Test QoS budget enforcement (fanout, top_k)
    - Test adaptive batch sizing under contention
  - `tests/k0/pipelines/p03/performance/test_learning_budget.py`:
    - Test 5% budget enforcement
    - Test component budget allocation
    - Test skip behavior when over budget
  - `tests/k0/pipelines/p03/performance/test_streaming.py`:
    - Test streaming processor memory release
    - Test memory threshold triggers
    - Test batch metrics emission
  - `tests/k0/pipelines/p03/performance/test_caching.py`:
    - Test embedding cache LRU eviction
    - Test TTL expiration
    - Test cache hit/miss metrics
- **Acceptance Criteria**:
  - ≥90% line coverage for qos module
  - All K0 integrations tested
  - Budget enforcement validated
  - Memory management validated
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

---

## Milestone 7 — Closed-loop learning (safe, incremental rollout)

> **Architectural Note: Two-System Feedback Architecture**
>
> P03 participates in **two distinct feedback systems** with different purposes and ports:
>
> | System | Port | Purpose | Creates |
> |--------|------|---------|--------|
> | **Memory Formation** | Command Port (`memory.delta`) | Add NEW FACTS (user answers) | st_hipp_events row |
> | **Model Refinement** | Obs Port (`kind: feedback`) | TUNE WEIGHTS/THRESHOLDS | st_learned_weights update |
>
> **Invariants** (see Dossier Section 9.9 for complete list):
> - **INV-MEM-1**: gap_id round-trip (out with question, back with answer in `body.correlation.gap_id`)
> - **INV-MEM-4**: User answer creates st_hipp_events row (answer IS memory)
> - **INV-MODEL-1**: FeedbackEnvelope (Obs Port) does NOT create st_hipp_events (feedback tunes, not creates)
>
> **Implicit vs Explicit Gap Resolution**:
> - Milestone 7 implements **explicit feedback** paths (P21 → P03, P06 → P03)
> - Milestone 8 (Epic 8.2) implements **implicit resolution** via GapAutoResolver
> - Priority: Try implicit first (GapAutoResolver in R0), then explicit (P06) after grace period (24-72 hours)
>
> See: Dossier Section 9.9 "Feedback System Invariants", Section 5.3A "Implicit Gap Resolution"

### Epic 7.1 — Feedback ingestion (P21 → P03)

> **System**: Model Refinement Feedback (Obs Port)
>
> This epic implements **System 2: Model Refinement Feedback** which tunes algorithm weights.
> FeedbackEnvelopes arrive via Obs Port and update st_learned_weights — they do NOT create memories.
>
> **Key Invariants** (Dossier Section 9.9.4):
> - INV-MODEL-1: Feedback is not memory (no st_hipp_events rows)
> - INV-MODEL-2: Signals target existing events (correlation.event_ids)
> - INV-MODEL-3: Weight bounds enforced (clamped values)
> - INV-MODEL-4: Idempotent updates (consumed_at prevents double-processing)

> **References**:
>
> - **Dossier Section 9.9: Feedback System Invariants (Two-System Architecture)** ← CRITICAL
> - Dossier Section 5.7: P03 Feedback Handler Implementation
> - Dossier Section 5.7.1: Handler Architecture
> - Dossier Section 5.7.2: Bus Subscription Registration
> - Dossier Section 5.7.3: Feedback Consumption Tracking
> - Dossier Section 9.8.5: P03FeedbackPayload Schema Definition
> - Dossier Section 9.8.6: P03 Schema Registration
> - Dossier Section 9.8.7: P03 Signal Coverage Validation
> - K0 Feedback Architecture: `k0/ports/FEEDBACK.md`
> - K0 Feedback Subsystem: `k0/feedback/`

---

#### Issue 7.1.1 — P03FeedbackPayload schema definition

- **Goal**: Define structured Pydantic payload schema for all 6 feedback signal types P03 consumes.
- **Deliverables**:
  - `k0/feedback/schemas/p03_consolidation.py`:
    - `P03FeedbackPayload` class (Pydantic BaseModel):
      - `feedback_type`: Literal enum (6 types)
      - `wal_positions`: list[int] (target events)
      - `entity_id`: str | None (target entity)
      - `cluster_id`: str | None (target cluster)
      - `salience_delta`: float | None (-1.0 to +1.0)
      - `importance_override`: float | None (0.0 to 1.0)
      - `decay_lambda_delta`: float | None (λ adjustment)
      - `was_retrieved`: bool | None (Hebbian signal)
      - `was_helpful`: bool | None (success/failure)
      - `user_confirmed`: bool | None (cluster correction)
      - `retrieval_query`: str | None (K1 context)
      - `session_context`: dict | None (K1 context)
      - `confidence`: float (0.0-1.0, default 0.5)
    - Literal types for `feedback_type`:
      - `SALIENCE_ADJUSTMENT` → Importance learning (M2)
      - `DECAY_REVERSAL` → Decay learning (M3)
      - `CLUSTER_CORRECTION` → Similarity learning (M4)
      - `REINFORCEMENT_OUTCOME` → Hebbian learning (M4)
      - `NOVELTY_SIGNAL` → Audit logging (M1)
      - `REGRET_SIGNAL` → Regret learning (M6)
- **Acceptance Criteria**:
  - Schema validates all 6 feedback types from whiteboard research
  - Field mapping to R1-R4 formulas documented
  - Extra fields forbidden (`extra="forbid"`)
  - Schema version: 1.0
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.8.5 "P03FeedbackPayload Schema Definition")
  - Pattern: `k0/feedback/payloads.py` (P02FeedbackPayload, P08FeedbackPayload)

---

#### Issue 7.1.2 — P03FeedbackPayload schema registration with P21

- **Goal**: Register P03 payload schema with P21 FeedbackSchemaRegistry for validation and dispatch.
- **Deliverables**:
  - `k0/feedback/schema_registry.py`:
    - Add P03 registration: `FeedbackSchemaRegistry.register_pydantic("P03", P03FeedbackPayload)`
  - `k0/feedback/topics.py`:
    - Add `FEEDBACK_SIGNAL_P03_V1 = "feedback.signal.p03.v1"`
    - Add `"P03"` to `FEEDBACK_PIPELINES_V1` tuple
    - Add `FEEDBACK_SIGNAL_P03_V1` to `FEEDBACK_SIGNAL_TOPICS_V1`
  - Health metric: `p03_schema_registered` gauge (0=not registered, 1=registered)
- **Acceptance Criteria**:
  - P21 can look up P03 in registry → gets `P03FeedbackPayload`
  - Validation flow: envelope.payload validated against schema before dispatch
  - Invalid payloads quarantined with validation error details
  - Registration confirmed at pipeline startup
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.8.6 "P03 Schema Registration")
  - Pattern: `k0/feedback/schema_registry.py` (existing P02/P08 registrations)

---

#### Issue 7.1.3 — P03FeedbackHandler implementation (central routing hub)

- **Goal**: Implement central handler class that receives feedback signals and routes to appropriate learning modules.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/handler.py`:
    - `P03FeedbackHandler` class:
      - `topics = ["feedback.signal.p03.v1"]` (subscription declaration)
      - `__init__(db_pool, metrics_registry)` → initialize all learners
      - `async def handle(msg: BusMessage, ctx: PipelineContext)` → main entry
      - Deserialize `FeedbackEnvelope` from `msg.payload`
      - Validate `P03FeedbackPayload` from envelope.payload
      - Match `payload.feedback_type` to route
      - Call `_mark_consumed()` on success/skip/failure
    - Internal routing methods:
      - `_route_to_importance_learner()` → SALIENCE_ADJUSTMENT
      - `_route_to_decay_learner()` → DECAY_REVERSAL
      - `_route_to_similarity_learner()` → CLUSTER_CORRECTION
      - `_route_to_hebbian_learner()` → REINFORCEMENT_OUTCOME
      - `_log_memory_gap()` → NOVELTY_SIGNAL
      - `_route_to_regret_learner()` → REGRET_SIGNAL
    - Learner initialization:
      - `ImportanceLearner(db_pool)` (M2)
      - `DecayLearner(db_pool)` (M3)
      - `SimilarityLearner(db_pool)` (M4)
      - `HebbianLearner(db_pool)` (M4)
      - `RegretLearner(db_pool)` (M6)
      - `AuditLogger(db_pool)` (M1)
- **Acceptance Criteria**:
  - Handler receives and deserializes feedback envelopes
  - All 6 feedback types routed to correct learners
  - Unknown feedback types marked as SKIPPED
  - Errors caught and marked as FAILED for P21 retry
  - Single point of control for feedback routing
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.1 "Handler Architecture")
  - K0 Pattern: `k0/ports/FEEDBACK.md` (Part 2: K0 Developer Guide)

---

#### Issue 7.1.4 — Bus subscription registration for feedback.signal.p03.v1

- **Goal**: Register P03FeedbackHandler with K0 BusDispatcher during pipeline initialization.
- **Deliverables**:
  - `k0/pipelines/p03/__init__.py`:
    - `register_handlers(bus: BusDispatcher, db_pool, metrics_registry)` function:
      - Instantiate `P03FeedbackHandler`
      - Call `bus.subscribe(topic="feedback.signal.p03.v1", handler=handler, priority=Priority.NORMAL)`
      - Set `metrics_registry.p03_feedback_subscribed.set(1)` on success
      - Log: `"P03FeedbackHandler subscribed to feedback.signal.p03.v1"`
  - Integration with pipeline boot sequence:
    - Called after feedback subsystem is running
    - Called during `discover_and_boot_pipelines()` phase
- **Acceptance Criteria**:
  - P03 actively subscribes during initialization
  - Subscription failure causes P03 unhealthy state
  - `p03_feedback_subscribed` gauge reflects subscription status
  - Startup order: feedback subsystem → P03 init → subscription
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.2 "Bus Subscription Registration")
  - K0 Pattern: `k0/feedback/topics.py` (topic naming conventions)

---

#### Issue 7.1.5 — SALIENCE_ADJUSTMENT routing to ImportanceLearner (M2)

- **Goal**: Implement routing of salience adjustment signals to importance learning module.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/handler.py`:
    - `_route_to_importance_learner(payload, ctx)` method:
      - Call `importance_learner.adjust_salience(entity_id, salience_delta, confidence, space_id)`
      - Handle null entity_id (use wal_positions fallback)
  - `k0/pipelines/p03/learning/importance.py`:
    - `ImportanceLearner.adjust_salience()` method:
      - Apply α_imp adjustment based on salience_delta
      - Weight by confidence factor
      - Update st_learned_weights for entity/type
      - Record history in st_learned_weights_history
- **Acceptance Criteria**:
  - SALIENCE_ADJUSTMENT signals update importance weights
  - Confidence weighting applied correctly
  - Weight changes recorded in history for rollback
  - Bounds enforced (clamp to safe range)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.1 signal routing table)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.8.5 field mapping)

---

#### Issue 7.1.6 — DECAY_REVERSAL routing to DecayLearner (M3)

- **Goal**: Implement routing of decay reversal signals when pruned memories were needed.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/handler.py`:
    - `_route_to_decay_learner(payload, ctx)` method:
      - Call `decay_learner.adjust_lambda(entity_id, lambda_delta, confidence, space_id)`
  - `k0/pipelines/p03/learning/decay.py`:
    - `DecayLearner.adjust_lambda()` method:
      - Apply λ adjustment based on decay_lambda_delta
      - Weight by confidence factor
      - Update st_learned_weights for decay parameters
      - Record history for rollback
- **Acceptance Criteria**:
  - DECAY_REVERSAL signals reduce decay rate (λ)
  - Entity-specific λ values preserved
  - Confidence weighting applied
  - Rollback capability maintained
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.1 signal routing table)

---

#### Issue 7.1.7 — CLUSTER_CORRECTION routing to SimilarityLearner (M4)

- **Goal**: Implement routing of cluster correction signals for user-confirmed groupings.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/handler.py`:
    - `_route_to_similarity_learner(payload, ctx)` method:
      - Call `similarity_learner.adjust_clustering(cluster_id, wal_positions, user_confirmed, confidence, space_id)`
  - `k0/pipelines/p03/learning/similarity.py`:
    - `SimilarityLearner.adjust_clustering()` method:
      - If user_confirmed=True: reinforce cluster (boost similarity threshold)
      - If user_confirmed=False: split cluster (raise threshold)
      - Update DBSCAN adaptive params (eps, min_samples)
      - Record adjustment in st_causal_feedback
- **Acceptance Criteria**:
  - User confirmations reinforce clusters
  - User rejections trigger cluster splits
  - DBSCAN parameters adjusted per feedback
  - All adjustments auditable
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.1 signal routing table)

---

#### Issue 7.1.8 — REINFORCEMENT_OUTCOME routing to HebbianLearner (M4)

- **Goal**: Implement routing of reinforcement outcome signals for Hebbian learning.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/handler.py`:
    - `_route_to_hebbian_learner(payload, ctx)` method:
      - Call `hebbian_learner.update_outcome(entity_id, was_retrieved, was_helpful, confidence, space_id)`
  - `k0/pipelines/p03/learning/hebbian.py`:
    - `HebbianLearner.update_outcome()` method:
      - Fire-together-wire-together: update co-activation strength
      - If was_retrieved + was_helpful: boost connection weight
      - If was_retrieved + not was_helpful: decay connection weight
      - Update st_kg_edges weights for related entities
- **Acceptance Criteria**:
  - Retrieved + helpful memories get reinforced
  - Retrieved + unhelpful memories get decayed
  - Co-activation patterns tracked
  - Edge weights updated via Hebbian formula
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.1 signal routing table)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.2.2 HebbianLearner class)

---

#### Issue 7.1.9 — NOVELTY_SIGNAL routing to AuditLogger (M1)

- **Goal**: Implement routing of novelty signals for memory gap detection logging.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/handler.py`:
    - `_log_memory_gap(payload, ctx)` method:
      - Call `audit_logger.log_memory_gap(retrieval_query, session_context, confidence, space_id)`
  - `k0/pipelines/p03/obs/audit_logger.py`:
    - `AuditLogger.log_memory_gap()` method:
      - Insert into st_consolidation_audit with action_type='MEMORY_GAP'
      - Record retrieval_query that triggered gap detection
      - Record session_context for debugging
      - Emit `p03.gap.detected.v1` event for P06 Active Learning
- **Acceptance Criteria**:
  - Novelty signals logged in audit trail
  - Memory gaps emitted to P06 for question generation
  - Retrieval context preserved for analysis
  - Gap deduplication applied before emission
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.1 signal routing table)

---

#### Issue 7.1.10 — REGRET_SIGNAL routing to RegretLearner (M6)

- **Goal**: Implement routing of regret signals when pruned entities were later queried.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/handler.py`:
    - `_route_to_regret_learner(payload, ctx)` method:
      - Call `regret_learner.process_regret(entity_id, lambda_delta, confidence, space_id)`
  - `k0/pipelines/p03/learning/regret.py`:
    - `RegretLearner.process_regret()` method:
      - Record regret in st_decay_feedback
      - Adjust λ for entity type (lower decay rate)
      - Optionally trigger decay reversal for similar entities
      - Increment `p03_regret_signals_processed` counter
- **Acceptance Criteria**:
  - Regret signals recorded for analysis
  - Decay rates adjusted to prevent future regret
  - Similar entities identified for preemptive adjustment
  - High-confidence regrets (≥0.90) trigger immediate action
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.1 signal routing table)

---

#### Issue 7.1.11 — Feedback consumption tracking in st_feedback_signals

- **Goal**: Implement marking of consumed feedback signals to prevent reprocessing.
- **Deliverables**:
  - `k0/pipelines/p03/feedback/handler.py`:
    - `_mark_consumed(envelope_id, ctx, status, reason)` method:
      - UPDATE st_feedback_signals SET:
        - `consumed_at` = current timestamp (ms)
        - `consumed_by` = 'P03'
        - `consumption_status` = PROCESSED | SKIPPED | FAILED
        - `consumption_reason` = optional reason string
      - Increment `p03_feedback_consumption_status` counter by status
  - Consumption status semantics:
    - PROCESSED: Applied to learning (no retry)
    - SKIPPED: Filtered (low confidence, duplicate, unknown type)
    - FAILED: Error during processing (P21 retries up to 3x)
- **Acceptance Criteria**:
  - All processed signals marked with consumed_at and consumed_by
  - Status correctly reflects processing outcome
  - Failed signals retried by P21 (up to 3 times before DLQ)
  - No duplicate processing of same envelope_id
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.3 "Feedback Consumption Tracking")

---

#### Issue 7.1.12 — Feedback consumption audit linkage

- **Goal**: Link consumed feedback signals to consolidation audit entries for full traceability.
- **Deliverables**:
  - `k0/pipelines/p03/learning/*.py` (all learners):
    - Include `feedback_envelope_id` in st_consolidation_audit inserts
    - Record decision_id from learning update
    - Link formula_version to audit entry
  - Audit trail flow:
    - Feedback envelope → learning update → audit entry (with envelope reference)
- **Acceptance Criteria**:
  - All learning updates reference originating feedback envelope
  - Audit entries queryable by feedback_envelope_id
  - Full provenance chain from signal to decision
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.3 "Audit Trail")

---

#### Issue 7.1.13 — Feedback consumption metrics implementation

- **Goal**: Implement metrics for feedback consumption monitoring.
- **Deliverables**:
  - `k0/pipelines/p03/obs/feedback_metrics.py`:
    - `p03_feedback_subscribed` (gauge): 0=not subscribed, 1=subscribed
    - `p03_feedback_messages_received` (counter): Total messages by signal_type
    - `p03_feedback_consumption_status` (counter): Outcomes by status (PROCESSED/SKIPPED/FAILED)
    - `p03_feedback_processing_latency_ms` (histogram): Time to process each signal
    - `p03_feedback_routing_errors` (counter): Routing failures by type
  - Metric registration in MetricsRegistry during handler init
- **Acceptance Criteria**:
  - All metrics exposed via K0 MetricsExporter
  - Labels include signal_type and status dimensions
  - Latency histogram uses standard buckets
  - Metrics documented in telemetry mixins
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.2 "Metrics")

---

#### Issue 7.1.14 — Feedback consumption alerting rules

- **Goal**: Implement alerting for feedback consumption failures and backlog.
- **Deliverables**:
  - `k0/telemetry/mixins/p03_feedback_alerts.py`:
    - Alert rule builder following K0 telemetry patterns
  - Generated output: `k0/telemetry/generated/rules/p03_feedback_alerts.yaml`:
    - `P03FeedbackFailedRate`: Alert if FAILED rate > 5% for 15 minutes
    - `P03FeedbackBacklog`: Alert if consumed_by IS NULL count > 100
    - `P03FeedbackSubscriptionDown`: Alert if p03_feedback_subscribed = 0 for 5 minutes
- **Acceptance Criteria**:
  - Critical alerts page on-call for subscription down
  - Warning alerts for high failure rate
  - Alert descriptions include remediation steps
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.3 "Consumption Monitoring")

---

#### Issue 7.1.15 — Signal coverage validation tests

- **Goal**: Validate that P03FeedbackPayload schema covers all whiteboard learning signals.
- **Deliverables**:
  - `tests/k0/feedback/test_p03_schema_coverage.py`:
    - `test_salience_adjustment_signal()`: Grounding signal representation
    - `test_decay_reversal_signal()`: Decay reversal representation
    - `test_cluster_correction_signal()`: User clustering correction
    - `test_reinforcement_outcome_signal()`: Hebbian outcome
    - `test_novelty_signal()`: Memory gap detection
    - `test_regret_signal()`: Pruned entity regret
    - `test_all_whiteboard_signals_covered()`: Matrix validation
  - Coverage matrix verification:
    - Grounding → salience_delta + was_helpful ✅
    - Correction → salience_delta ✅
    - Entity co-access → wal_positions (multiple) ✅
    - Regret → feedback_type: REGRET_SIGNAL ✅
    - Novelty → feedback_type: NOVELTY_SIGNAL ✅
    - Decay reversal → feedback_type: DECAY_REVERSAL ✅
    - Cluster correction → feedback_type: CLUSTER_CORRECTION ✅
- **Acceptance Criteria**:
  - Every whiteboard signal can be represented as P03FeedbackPayload
  - Coverage report generated in CI
  - Schema completeness validated
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.8.7 "P03 Signal Coverage Validation")

---

#### Issue 7.1.16 — P03FeedbackHandler unit tests

- **Goal**: Comprehensive unit testing of handler routing logic.
- **Deliverables**:
  - `tests/k0/pipelines/p03/feedback/test_handler.py`:
    - `TestP03FeedbackHandler` class:
      - `test_salience_adjustment_routing()`: Route to ImportanceLearner
      - `test_decay_reversal_routing()`: Route to DecayLearner
      - `test_cluster_correction_routing()`: Route to SimilarityLearner
      - `test_reinforcement_outcome_routing()`: Route to HebbianLearner
      - `test_novelty_signal_routing()`: Route to AuditLogger
      - `test_regret_signal_routing()`: Route to RegretLearner
      - `test_unknown_signal_type_skipped()`: Unknown types marked SKIPPED
      - `test_validation_error_marked_failed()`: Invalid payloads marked FAILED
      - `test_processing_error_marked_failed()`: Learner errors marked FAILED
      - `test_consumed_status_updated()`: Status written to st_feedback_signals
- **Acceptance Criteria**:
  - ≥90% line coverage for handler module
  - All routing paths tested
  - Error handling validated
  - Consumption tracking verified
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

---

#### Issue 7.1.17 — Feedback handler integration tests

- **Goal**: End-to-end integration testing of feedback consumption flow.
- **Deliverables**:
  - `tests/k0/pipelines/p03/feedback/test_integration.py`:
    - `TestFeedbackIntegration` class:
      - `test_full_feedback_cycle()`: P21 dispatch → P03 consume → learning update
      - `test_subscription_registration()`: Handler subscribes during boot
      - `test_consumption_tracking_persisted()`: st_feedback_signals updated
      - `test_audit_trail_linkage()`: feedback_envelope_id in st_consolidation_audit
      - `test_retry_on_failure()`: Failed signals retried by P21
      - `test_duplicate_prevention()`: Same envelope_id not processed twice
  - Test fixtures:
    - Mock BusDispatcher with controllable message delivery
    - Test database with st_feedback_signals seeded
    - Learner stubs for isolation
- **Acceptance Criteria**:
  - Full consumption cycle tested with real DB
  - Subscription verified during boot sequence
  - Audit linkage validated
  - Retry semantics confirmed
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

---

#### Issue 7.1.18 — P03 health check for feedback subscription

- **Goal**: Implement health check that reports unhealthy if feedback subscription fails.
- **Deliverables**:
  - `k0/pipelines/p03/health.py`:
    - `FeedbackSubscriptionCheck` class:
      - Check `p03_feedback_subscribed` gauge value
      - Return unhealthy if gauge = 0
      - Include subscription topic in health details
  - Integration with K0 health endpoint:
    - Add P03FeedbackSubscription to pipeline health checks
    - Health status propagates to `/k0/observe.health`
- **Acceptance Criteria**:
  - P03 reports unhealthy if not subscribed to feedback topic
  - Health check runs on startup and periodically
  - Health endpoint includes subscription details
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.7.2 "Health Check")

### Epic 7.2 — Parameter store + rollback loop

> **References**:
>
> - Dossier Section 6.17: st_learned_weights (Adaptive Parameters)
> - Dossier Section 6.22: st_learned_weights_history
> - Dossier Section 6.22.4: Usage Patterns (Record Version, Rollback)
> - Dossier Section 6.22.5: Quality-Based Rollback
> - Dossier Section 6.22.6: Metrics & Monitoring
> - Dossier Section 1.4.6: Per-Space Threshold Isolation (Hierarchical Fallback)
> - Dossier Section 1.4.9: Threshold Stability and Bounds

---

#### Issue 7.2.1 — st_learned_weights table schema and migration

- **Goal**: Create central storage table for all learned hyperparameters with hierarchical scoping.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_learned_weights.py`:
    - CREATE TABLE st_learned_weights with columns:
      - `param_id` TEXT PRIMARY KEY (UUID)
      - `param_key` TEXT NOT NULL (e.g., "importance_emotional", "decay_lambda_PERSON")
      - `param_scope` TEXT NOT NULL CHECK IN ('global', 'space', 'entity_type', 'entity')
      - `scope_id` TEXT (space_id, entity_type, or entity_id; NULL for global)
      - `space_id` TEXT NOT NULL (isolation)
      - `current_value` REAL NOT NULL
      - `prior_value` REAL NOT NULL (initial/default)
      - `confidence` REAL NOT NULL DEFAULT 0.0 CHECK (0-1)
      - `sample_count` INTEGER NOT NULL DEFAULT 0
      - `last_updated_at` BIGINT NOT NULL
      - `version` INTEGER NOT NULL DEFAULT 1
      - `previous_value` REAL (for immediate rollback)
      - `quality_at_update` REAL (quality metric when last updated)
      - `rollback_eligible` BOOLEAN NOT NULL DEFAULT TRUE
      - `created_at` BIGINT NOT NULL
      - `updated_at` BIGINT NOT NULL
    - UNIQUE constraint on (space_id, param_key, param_scope, scope_id)
    - Indexes: space_key, scope, confidence DESC
- **Acceptance Criteria**:
  - Table created with all columns per dossier schema
  - RLS policy for multi-tenant isolation
  - UNIQUE constraint prevents duplicate parameters
  - All indexes created for query patterns
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.17 "st_learned_weights")

---

#### Issue 7.2.2 — st_learned_weights_history table schema and migration

- **Goal**: Create history table for parameter versioning and rollback capability.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_learned_weights_history.py`:
    - CREATE TABLE st_learned_weights_history with columns:
      - `history_id` TEXT PRIMARY KEY
      - `param_id` TEXT NOT NULL (FK to st_learned_weights.param_id)
      - `version` INTEGER NOT NULL
      - `value` REAL NOT NULL (parameter value at this version)
      - `quality_at_time` REAL (quality metric when applied)
      - `space_id` TEXT NOT NULL (isolation)
      - `applied_at` BIGINT NOT NULL
    - FOREIGN KEY to st_learned_weights ON DELETE CASCADE
    - UNIQUE constraint on (param_id, version)
    - Indexes: param_version DESC, param_time DESC, space_time DESC
- **Acceptance Criteria**:
  - Table created with all columns per dossier schema
  - CASCADE delete when parent parameter deleted
  - RLS policy for space isolation
  - Indexes support rollback queries
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.22 "st_learned_weights_history")

---

#### Issue 7.2.3 — Hierarchical parameter lookup implementation

- **Goal**: Implement 3-level fallback hierarchy for parameter retrieval (space → entity_type → global).
- **Deliverables**:
  - `k0/pipelines/p03/learning/parameter_store.py`:
    - `ParameterStore` class:
      - `async def get_parameter(param_key, space_id, entity_type=None)` → float
      - `async def get_with_fallback(param_key, scope_chain)` → float | None
      - `_build_scope_chain(space_id, entity_type)` → list of (scope, scope_id)
    - Fallback order:
      1. Space-specific (param_scope='space', scope_id=space_id)
      2. Entity-type-specific (param_scope='entity_type', scope_id=entity_type)
      3. Global (param_scope='global', scope_id=NULL)
    - Return prior_value if no learned value exists
- **Acceptance Criteria**:
  - Lookup respects 3-level hierarchy
  - Falls back to prior_value if nothing learned
  - Confidence-weighted lookup option (use higher confidence)
  - Query uses indexes efficiently
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.6 "Per-Space Threshold Isolation")

---

#### Issue 7.2.4 — Parameter update with history recording

- **Goal**: Implement parameter updates that automatically record version history.
- **Deliverables**:
  - `k0/pipelines/p03/learning/parameter_updater.py`:
    - `async def update_parameter_with_history(db, param_id, new_value, quality_metric, space_id)`:
      1. Get current state (current_value, version)
      2. INSERT into st_learned_weights_history (history_id, param_id, version+1, current_value, quality, space_id, applied_at)
      3. UPDATE st_learned_weights SET current_value=new, previous_value=current, version=version+1, quality_at_update=quality
    - `async def initialize_parameter(db, param_key, prior_value, space_id, scope, scope_id)`:
      - Create new parameter with prior_value as both current and prior
- **Acceptance Criteria**:
  - Every update creates history entry
  - Previous value preserved for immediate rollback
  - Version incremented atomically
  - Quality metric recorded for rollback decisions
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.22.4 "Record Version on Update")

---

#### Issue 7.2.5 — Manual rollback API implementation

- **Goal**: Implement capability to rollback parameters to any previous version.
- **Deliverables**:
  - `k0/pipelines/p03/learning/rollback_manager.py`:
    - `async def rollback_parameter(db, param_id, target_version, space_id)` → bool:
      1. Get target version from st_learned_weights_history
      2. UPDATE st_learned_weights SET current_value=target.value, previous_value=current, quality_at_update=target.quality, rollback_eligible=FALSE
      3. INSERT rollback event into history
      4. Return True if successful
    - `async def get_rollback_history(db, param_id, space_id)` → list of versions
    - `async def get_version_details(db, param_id, version, space_id)` → version info
  - CLI integration via k0ctl:
    - `k0ctl p03 weights rollback --param-id <id> --version <ver>`
    - `k0ctl p03 weights history --param-id <id>`
- **Acceptance Criteria**:
  - Rollback restores exact historical value
  - Rollback event recorded in history
  - rollback_eligible=FALSE prevents auto-rollback loops
  - CLI commands work for operators
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.22.4 "Rollback to Previous Version")

---

#### Issue 7.2.6 — Automatic quality-based rollback triggers

- **Goal**: Implement automatic rollback when quality degrades by 15% threshold.
- **Deliverables**:
  - `k0/pipelines/p03/learning/quality_monitor.py`:
    - `QualityMonitor` class:
      - `async def check_quality_regression(db, param_id, current_quality, space_id)` → bool:
        1. Get quality history for last 7 days (up to 10 versions)
        2. Calculate average of last 3 versions
        3. If current_quality < (avg * 0.85): trigger rollback
      - `async def trigger_rollback(db, param_id, space_id)`:
        1. Find version with best quality_at_time in history
        2. Call rollback_parameter to that version
        3. Emit alert and increment counter
    - Integration hook: call after each learning update
- **Acceptance Criteria**:
  - 15% degradation threshold triggers rollback
  - Best historical version selected (not just previous)
  - Alert emitted on automatic rollback
  - Metric incremented: p03_weights_rollbacks_total{reason="quality_regression"}
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.22.5 "Quality-Based Rollback")

---

#### Issue 7.2.7 — History version cleanup job

- **Goal**: Implement automatic cleanup keeping only last 10 versions per parameter.
- **Deliverables**:
  - `k0/pipelines/p03/maintenance/history_cleanup.py`:
    - `async def cleanup_parameter_history(db)` → int (deleted count):
      1. Find parameters with >10 versions: SELECT param_id, COUNT(*) GROUP BY param_id HAVING COUNT(*) > 10
      2. For each: DELETE WHERE version NOT IN (SELECT version ORDER BY version DESC LIMIT 10)
      3. Return total deleted
    - `async def get_history_stats(db)` → dict with version counts per param
  - PipelineScheduler trigger:
    - INTERVAL trigger: daily at 3am UTC
    - Register in p03_consolidation.v1.yaml
- **Acceptance Criteria**:
  - Only last 10 versions retained per parameter
  - Cleanup runs daily
  - Deleted count tracked in metrics
  - No orphaned history records
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.22.4 "Automatic Cleanup")

---

#### Issue 7.2.8 — Momentum-based stability implementation

- **Goal**: Implement EMA smoothing to prevent wild swings from single feedback signals.
- **Deliverables**:
  - `k0/pipelines/p03/learning/momentum_updater.py`:
    - `MomentumThresholdUpdater` class:
      - `def update_with_momentum(old_value, new_value, momentum=0.9)` → float:
        - Returns: momentum *old_value + (1 - momentum)* new_value
      - `def update_beta_with_momentum(old_alpha, old_beta, success, failure, momentum=0.9)` → (alpha, beta)
    - Configuration:
      - `P03_THRESHOLD_MOMENTUM = 0.9` (90% old, 10% new)
      - `P03_UPDATE_SPEED_CONFIG` dict per param_type
  - Apply in all learners before parameter update
- **Acceptance Criteria**:
  - Momentum applied to all parameter updates
  - Configurable momentum per parameter type
  - Single noisy signal doesn't cause major swing
  - update_speed config allows tuning per use case
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.9 "Momentum Update")

---

#### Issue 7.2.9 — Bounds enforcement implementation

- **Goal**: Implement parameter bounds clamping to prevent extreme values.
- **Deliverables**:
  - `k0/pipelines/p03/learning/bounds_enforcer.py`:
    - `BoundsEnforcer` class:
      - `def clamp(value, param_key)` → float (clamped value)
      - `async def check_bounds(param_key, space_id, value)` → emit alert if hit
    - Configuration (from dossier):
      - `P03_THRESHOLD_BOUNDS`:
        - 'reinforce': (0.75, 0.95)
        - 'extend_lower': (0.45, 0.75)
        - 'importance_*': (0.0, 1.0)
        - 'decay_lambda_*': (0.001, 0.1)
    - `ThresholdBoundMonitor` class:
      - `emit_bound_alert(space_id, threshold_name, bound_type, value, bound)`
      - Log warning and emit alert when within 0.01 of bound
- **Acceptance Criteria**:
  - All parameters clamped to configured bounds
  - Alert emitted when hitting bounds
  - Bound violations logged with context
  - p03_threshold_bound_hits counter incremented
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.9 "Stability Bounds")

---

#### Issue 7.2.10 — Rollback eligibility flag management

- **Goal**: Implement rollback_eligible flag to prevent auto-rollback loops.
- **Deliverables**:
  - `k0/pipelines/p03/learning/rollback_manager.py`:
    - Add rollback_eligible check:
      - `async def is_rollback_eligible(db, param_id)` → bool
      - Auto-rollback skipped if rollback_eligible=FALSE
    - Set rollback_eligible=FALSE after manual rollback
    - Reset rollback_eligible=TRUE after N successful updates:
      - `async def reset_eligibility_after_success(db, param_id, threshold=5)`
  - Quality monitor integration:
    - Check eligibility before triggering rollback
    - Skip and log if not eligible
- **Acceptance Criteria**:
  - Manual rollbacks mark parameter ineligible for auto-rollback
  - Auto-rollback respects eligibility flag
  - Eligibility resets after 5 successful updates
  - Prevents infinite rollback loops
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.17 schema, Section 6.22.4)

---

#### Issue 7.2.11 — Quality metrics correlation implementation

- **Goal**: Implement metrics tracking quality regressions and rollback events.
- **Deliverables**:
  - `k0/pipelines/p03/obs/weights_metrics.py`:
    - `p03_weights_history_versions` (gauge): Versions per parameter by param_key
    - `p03_weights_rollbacks_total` (counter): Rollbacks by reason (manual, automatic, quality_regression)
    - `p03_weights_history_cleanup_deleted` (counter): History records deleted
    - `p03_weights_quality_regressions` (counter): Quality regression events
    - `p03_weights_bound_hits` (counter): Bound violation count by threshold
    - `p03_weights_current_quality` (gauge): Current quality score by param_key
  - Metric registration in MetricsRegistry
- **Acceptance Criteria**:
  - All metrics exposed via K0 MetricsExporter
  - Labels include param_key and reason dimensions
  - Metrics updated on every relevant event
  - Dashboard can track quality trends
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.22.6 "Metrics & Monitoring")

---

#### Issue 7.2.12 — Parameter store alerting rules

- **Goal**: Implement alerts for quality regressions and rollback events.
- **Deliverables**:
  - `k0/telemetry/mixins/p03_weights_alerts.py`:
    - Alert rule builder following K0 telemetry patterns
  - Generated output: `k0/telemetry/generated/rules/p03_weights_alerts.yaml`:
    - `P03QualityRegression`: Alert if quality drops >15% for any parameter
    - `P03ThresholdBoundHit`: Warning when threshold hits bound
    - `P03AutoRollbackTriggered`: Info when automatic rollback occurs
    - `P03HighRollbackRate`: Warning if >3 rollbacks in 24h for same param
- **Acceptance Criteria**:
  - Alerts defined per dossier thresholds
  - Critical alerts for sustained quality regression
  - Warning for bound violations
  - Alert descriptions include remediation steps
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.9 "Alerts")

---

#### Issue 7.2.13 — Parameter initialization with priors

- **Goal**: Implement parameter initialization from prior values for cold start.
- **Deliverables**:
  - `k0/pipelines/p03/learning/parameter_initializer.py`:
    - `ParameterInitializer` class:
      - `PRIOR_VALUES` dict with defaults:
        - 'importance_recency': 0.3
        - 'importance_salience': 0.5
        - 'importance_novelty': 0.2
        - 'decay_lambda_PERSON': 0.01
        - 'decay_lambda_PLACE': 0.02
        - 'threshold_reinforce': 0.85
        - 'threshold_extend_lower': 0.60
      - `async def ensure_parameter_exists(db, param_key, space_id, scope, scope_id)`:
        1. Check if parameter exists
        2. If not, create with prior_value from PRIOR_VALUES
        3. Return current parameter
      - `async def initialize_space(db, space_id)`:
        - Create all required parameters for a new space
- **Acceptance Criteria**:
  - All parameters have documented prior values
  - New spaces auto-initialized on first access
  - Prior values match dossier specifications
  - No missing parameters during learning
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.5 "Cold Start Strategy")

---

#### Issue 7.2.14 — RLS policies for parameter tables

- **Goal**: Implement Row-Level Security for multi-tenant isolation of parameters.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_learned_weights_rls.py`:
    - Enable RLS on st_learned_weights
    - Policy: space_id = current_setting('app.current_space_id')
    - Superuser bypass policy
  - `k0/db/alembic/versions/XXXX_st_learned_weights_history_rls.py`:
    - Enable RLS on st_learned_weights_history
    - Same policy pattern
  - Context setter in parameter_store.py:
    - `async def set_space_context(conn, space_id)` before all queries
- **Acceptance Criteria**:
  - RLS enabled on both tables
  - Cross-space parameter access blocked
  - Superuser can access all for ops
  - Context set at connection acquisition
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.17 "Row-Level Security")

---

#### Issue 7.2.15 — Parameter store unit tests

- **Goal**: Comprehensive unit testing of parameter store operations.
- **Deliverables**:
  - `tests/k0/pipelines/p03/learning/test_parameter_store.py`:
    - `TestParameterStore` class:
      - `test_hierarchical_lookup_space_level()`: Space-specific found
      - `test_hierarchical_lookup_entity_type_fallback()`: Falls back to entity_type
      - `test_hierarchical_lookup_global_fallback()`: Falls back to global
      - `test_hierarchical_lookup_prior_fallback()`: Falls back to prior_value
      - `test_update_creates_history()`: History entry created
      - `test_version_incremented()`: Version increases on update
      - `test_previous_value_preserved()`: Previous value stored
  - `tests/k0/pipelines/p03/learning/test_rollback.py`:
    - `test_rollback_restores_value()`: Correct value restored
    - `test_rollback_records_event()`: History entry for rollback
    - `test_rollback_sets_ineligible()`: rollback_eligible=FALSE
    - `test_auto_rollback_respects_eligibility()`: Skip if ineligible
- **Acceptance Criteria**:
  - ≥90% line coverage for parameter_store module
  - All fallback paths tested
  - Rollback mechanics validated
  - Edge cases covered (empty history, etc.)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

---

#### Issue 7.2.16 — Quality monitor integration tests

- **Goal**: End-to-end testing of quality-based rollback flow.
- **Deliverables**:
  - `tests/k0/pipelines/p03/learning/test_quality_monitor.py`:
    - `TestQualityMonitor` class:
      - `test_no_rollback_when_quality_stable()`: No action if <15% drop
      - `test_rollback_triggered_at_15_percent_drop()`: Rollback fires at threshold
      - `test_best_version_selected()`: Highest quality version chosen
      - `test_alert_emitted_on_rollback()`: Alert sent
      - `test_metric_incremented()`: p03_weights_quality_regressions++
      - `test_eligibility_checked()`: Skip if not eligible
  - Integration with real database:
    - Setup: Create param with history, varying quality
    - Execute: Call check_quality_regression
    - Assert: Correct rollback behavior
- **Acceptance Criteria**:
  - Full rollback flow tested with real DB
  - 15% threshold validated
  - Best version selection validated
  - Alert and metrics validated
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.22.5)

---

#### Issue 7.2.17 — Bounds enforcer integration tests

- **Goal**: Test bounds enforcement and alerting behavior.
- **Deliverables**:
  - `tests/k0/pipelines/p03/learning/test_bounds_enforcer.py`:
    - `TestBoundsEnforcer` class:
      - `test_value_clamped_to_lower_bound()`: Below min → min
      - `test_value_clamped_to_upper_bound()`: Above max → max
      - `test_value_in_bounds_unchanged()`: Within bounds → unchanged
      - `test_alert_at_lower_bound()`: Alert when hitting lower
      - `test_alert_at_upper_bound()`: Alert when hitting upper
      - `test_metric_incremented()`: p03_threshold_bound_hits++
- **Acceptance Criteria**:
  - All configured bounds enforced
  - Alerts fire at boundary
  - Metrics track violations
  - No silent failures
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.9 "Bound Violation Alerts")

---

#### Issue 7.2.18 — History cleanup job tests

- **Goal**: Test automatic cleanup of old history versions.
- **Deliverables**:
  - `tests/k0/pipelines/p03/maintenance/test_history_cleanup.py`:
    - `TestHistoryCleanup` class:
      - `test_cleanup_keeps_last_10()`: Only 10 versions retained
      - `test_cleanup_deletes_oldest()`: Oldest versions removed
      - `test_cleanup_returns_count()`: Correct deleted count
      - `test_cleanup_with_no_excess()`: No deletion if ≤10 versions
      - `test_cleanup_multiple_params()`: Works across many parameters
  - Performance test:
    - `test_cleanup_performance()`: Handles 1000 parameters efficiently
- **Acceptance Criteria**:
  - Exactly 10 versions retained
  - Cleanup completes in reasonable time
  - Metric tracks deleted count
  - No data corruption
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.22.4 "Automatic Cleanup")

### Epic 7.3 — Learning algorithms rollout

> **References**:
>
> - Dossier Section 11.6: Feature Flags
> - Dossier Section 11.7: Formula Canary Rollout
> - Dossier Section 12.4: Feature Flag Master List
> - Dossier Section 12.4.3: Shadow Mode Specification
> - Dossier Section 8.2.6: Shadow Mode Learning Metrics
> - Dossier Section 1.4.5: Thompson Sampling for Thresholds
> - Dossier Section 1.4.8: Threshold Cold Start Strategy
> - Dossier Section 1.4.6: Per-Space Threshold Isolation
> - Dossier Section 4.6.5: Shadow Mode Validation (MCTS)
> - Dossier Section 1.4.4: Golden Dataset Validation

---

#### Issue 7.3.1 — Extend K0 FeatureFlags with P03 learning modules

- **Goal**: Register P03 learning modules in existing K0 feature flags infrastructure (`k0/config/feature_flags.py`).
- **Deliverables**:
  - Update `k0/config/feature_flags.yaml`:
    - Add P03 learning modules under `modules:` section:

      ```yaml
      # P03 - Consolidation Learning Modules
      p03.learning.importance:
        enabled_tier: rule_based     # baseline formula
        fallback_tier: rule_based
        rollout_percentage: 0.0      # 0% = disabled, >0% = gradual rollout
        shadow_mode: true            # NEW: dual execution for comparison
        max_failures_before_fallback: 3
        description: "P03 importance scoring learning"
      p03.learning.hebbian:
        enabled_tier: rule_based
        fallback_tier: rule_based
        rollout_percentage: 0.0
        shadow_mode: true
        description: "P03 Hebbian co-activation learning"
      p03.learning.decay:
        enabled_tier: rule_based
        rollout_percentage: 0.0
        shadow_mode: true
        description: "P03 decay rate learning"
      p03.learning.similarity:
        enabled_tier: rule_based
        rollout_percentage: 0.0
        shadow_mode: true
        description: "P03 similarity threshold learning"
      p03.learning.threshold:
        enabled_tier: rule_based
        rollout_percentage: 0.0
        shadow_mode: true
        description: "P03 Thompson Sampling threshold learning"
      ```

  - Extend `k0/config/feature_flags.py`:
    - Add `shadow_mode: bool = False` field to `ModuleFlag` dataclass
    - Add method: `is_shadow_mode(module_id: str) -> bool`
    - Add method: `get_shadow_flags() -> list[str]` (all modules with shadow_mode=True)
  - CLI via existing `k0ctl`:
    - `k0ctl feature set p03.learning.importance --rollout 5.0`
    - `k0ctl feature set p03.learning.importance --shadow false`
- **Acceptance Criteria**:
  - All 5 P03 learning modules registered in feature_flags.yaml
  - `shadow_mode` field added to ModuleFlag without breaking existing flags
  - `get_feature_flags().is_shadow_mode("p03.learning.importance")` works
  - Existing M02/M04/M06/M07/M10 flags unaffected
- **References**:
  - K0 Pattern: `k0/config/feature_flags.py` (FeatureFlags, ModuleFlag, MLTier)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 12.4 "Feature Flag Master List")

---

#### Issue 7.3.2 — Shadow mode dual execution in K0 FeatureFlags

- **Goal**: Extend K0 FeatureFlags to support dual execution when `shadow_mode=True`.
- **Deliverables**:
  - Update `k0/config/feature_flags.py`:
    - Add `@with_shadow_comparison(module_id: str)` decorator:

      ```python
      def with_shadow_comparison(module_id: str):
          """Decorator that runs both baseline and learned when shadow_mode=True."""
          def decorator(func: Callable):
              async def wrapper(*args, **kwargs):
                  flags = get_feature_flags()
                  flag = flags.get_flag(module_id)

                  if flag and flag.shadow_mode:
                      # Execute baseline (always applies)
                      baseline_result = await baseline_fn(*args, **kwargs)
                      # Execute learned (log only, don't apply)
                      try:
                          learned_result = await func(*args, **kwargs)
                          await log_shadow_comparison(module_id, baseline_result, learned_result)
                      except Exception as e:
                          logger.warning(f"Shadow execution failed: {e}")
                      return baseline_result
                  else:
                      return await func(*args, **kwargs)
              return wrapper
          return decorator
      ```

    - Shadow comparison logging to `st_consolidation_audit`
    - Exception isolation: learned_fn errors logged but don't block production
  - Metrics via existing K0 telemetry pattern:
    - `k0_feature_shadow_executions_total{module_id}` (counter)
    - `k0_feature_shadow_errors_total{module_id}` (counter)
- **Acceptance Criteria**:
  - Baseline always applies when shadow_mode=True (safe path)
  - Learned executes but results discarded
  - Errors in learned path logged, don't affect production
  - Decorator integrates with existing `@with_ml_tier()` pattern
- **References**:
  - K0 Pattern: `k0/config/feature_flags.py` (`@with_ml_tier()` decorator)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 12.4.3 "Shadow Mode Specification")

---

#### Issue 7.3.3 — Shadow mode validation criteria

- **Goal**: Implement criteria for determining when shadow mode shows improvement vs regression.
- **Deliverables**:
  - `k0/pipelines/p03/learning/shadow_comparator.py`:
    - `ShadowModeComparator` class:
      - `compare_importance_scores(baseline, learned, ground_truth)` → "agreement" | "improvement" | "regression" | "divergence"
      - `compare_decay_rates(baseline, learned, access_pattern)` → outcome
      - `compare_similarity_thresholds(baseline, learned, user_corrections)` → outcome
      - `compute_outcome_score(signals)` → float (0-1)
    - Comparison logic:
      - Agreement: within 5% tolerance
      - Improvement: learned error < baseline error × 0.9
      - Regression: learned error > baseline error × 1.1
      - Divergence: different but neither clearly better
    - Criteria from dossier:
      - >20% difference triggers investigation
      - User corrections favoring new → improvement signal
- **Acceptance Criteria**:
  - All comparison outcomes categorized correctly
  - Outcome score aggregates multiple signals
  - Thresholds configurable via config
  - Edge cases handled (division by zero, missing data)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.6 "Shadow Comparison Logic")

---

#### Issue 7.3.4 — Shadow comparison metrics implementation

- **Goal**: Implement metrics for tracking shadow mode performance.
- **Deliverables**:
  - `k0/pipelines/p03/obs/shadow_metrics.py`:
    - `p03_shadow_executions_total` (counter): Total executions by learning_type, outcome
    - `p03_shadow_agreement_rate` (gauge): % agreement by learning_type
    - `p03_shadow_improvement_rate` (gauge): % improvement by learning_type
    - `p03_shadow_regression_rate` (gauge): % regression by learning_type
    - `p03_shadow_divergence_magnitude` (histogram): Magnitude of differences
    - `p03_shadow_promotion_eligibility` (gauge): 0=no, 1=yes by learning_type
    - `p03_shadow_sample_size` (gauge): Samples collected (last 7 days)
  - Rate calculation job (runs hourly):
    - Query st_consolidation_audit for shadow comparisons
    - Compute rates and update gauges
- **Acceptance Criteria**:
  - All metrics exposed via K0 MetricsExporter
  - Labels include learning_type dimension
  - Rates calculated correctly from audit data
  - Promotion eligibility computed per criteria
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.6 "Shadow Mode Learning Metrics")

---

#### Issue 7.3.5 — Promotion eligibility computation

- **Goal**: Implement automated computation of whether shadow mode meets promotion criteria.
- **Deliverables**:
  - `k0/pipelines/p03/learning/promotion_checker.py`:
    - `PromotionEligibilityChecker` class:
      - `async def check_eligibility(learning_type)` → (eligible: bool, reasons: list)
      - Criteria from dossier:
        - Agreement rate > 80%
        - Improvement rate > regression rate
        - Shadow duration ≥ 7 days
        - Sample size ≥ 1000 decisions
        - No critical errors (0 exceptions)
      - `async def get_promotion_report(learning_type)` → detailed report
    - Update `p03_shadow_promotion_eligibility` gauge on check
    - Emit event when newly eligible: `p03.learning.promotion_eligible.v1`
- **Acceptance Criteria**:
  - All 5 criteria evaluated correctly
  - Eligibility gauge reflects current state
  - Event emitted on state change (not eligible → eligible)
  - Report includes all metrics and thresholds
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 12.4.3 "Promotion Criteria")

---

#### Issue 7.3.6 — Canary rollout via K0 rollout_percentage

- **Goal**: Implement gradual rollout using K0's existing `rollout_percentage` mechanism.
- **Deliverables**:
  - `k0/pipelines/p03/learning/rollout_manager.py`:
    - `P03RolloutManager` class (wraps K0 FeatureFlags):
      - Rollout phases mapped to `rollout_percentage`:
        - Phase 0: Shadow mode (shadow_mode=True, rollout_percentage=0.0)
        - Phase 1: Canary (shadow_mode=False, rollout_percentage=5.0)
        - Phase 2: Gradual (rollout_percentage: 25.0 → 50.0 → 75.0)
        - Phase 3: Full (rollout_percentage=100.0)
      - `async def get_current_phase(module_id: str)` → RolloutPhase
      - `async def advance_phase(module_id: str)` → RolloutPhase:

        ```python
        flags = get_feature_flags()
        current = flags.get_flag(module_id).rollout_percentage
        next_pct = PHASE_PROGRESSION.get(current, 100.0)
        flags.set_tier(module_id, flag.enabled_tier, next_pct)
        ```

      - `async def rollback_phase(module_id: str)` → previous phase
    - Uses K0's consistent hashing (`request_id`) for deterministic routing
    - CLI via existing k0ctl:
      - `k0ctl feature set p03.learning.importance --rollout 25.0`
- **Acceptance Criteria**:
  - Phase progression: 0% → 5% → 25% → 50% → 75% → 100%
  - K0's consistent hashing ensures same entity always in same cohort
  - Rollback via `--rollout` flag immediately takes effect
  - No separate canary infrastructure (uses K0 FeatureFlags)
- **References**:
  - K0 Pattern: `k0/config/feature_flags.py` (`rollout_percentage`, `should_use_advanced_tier()`)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 11.7 "Formula Canary Rollout")

---

#### Issue 7.3.7 — Halt criteria using K0 auto-fallback mechanism

- **Goal**: Extend K0's `max_failures_before_fallback` pattern for P03 learning halt criteria.
- **Deliverables**:
  - Update `k0/config/feature_flags.py`:
    - Add `halt_criteria` to `ModuleFlag` dataclass:

      ```python
      @dataclass
      class ModuleFlag:
          # ... existing fields ...
          halt_on_regression_pct: float = 10.0  # halt if regression > 10%
          halt_on_error_rate_pct: float = 5.0   # halt if error rate > 5%
      ```

  - `k0/pipelines/p03/learning/halt_monitor.py`:
    - `P03HaltMonitor` class:
      - Uses K0's `record_failure()` + `max_failures_before_fallback`
      - Additional criteria from dossier:
        - User corrections spike > 3× baseline → `record_failure()` ×3
        - Regret signal rate doubles → `record_failure()` ×2
      - `async def check_and_update_halt_status(module_id)`:

        ```python
        flags = get_feature_flags()
        flag = flags.get_flag(module_id)
        if regression_rate > flag.halt_on_regression_pct:
            flags.record_failure(module_id)  # triggers auto-fallback
        ```

    - Integrates with K0's existing fallback (uses `fallback_tier`)
  - Alert emission via K0 telemetry pattern (not separate system)
- **Acceptance Criteria**:
  - Uses K0's `record_failure()` → auto-fallback mechanism
  - P03-specific halt criteria map to failure recording
  - Alert via existing K0 alerting infrastructure
  - No duplicate rollback system
- **References**:
  - K0 Pattern: `k0/config/feature_flags.py` (`record_failure()`, `max_failures_before_fallback`)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 11.7 "Halt Criteria")

---

#### Issue 7.3.8 — Golden dataset validation implementation

- **Goal**: Implement weekly validation of similarity formulas against curated test cases.
- **Deliverables**:
  - `k0/pipelines/p03/validation/golden_dataset.py`:
    - `GoldenDatasetCurator` class:
      - `async def add_to_golden_dataset(pair_id, entity1, entity2, is_same, confidence, source)`
      - `async def augment_from_corrections()`: Auto-add high-confidence corrections
    - `GoldenDatasetValidator` class:
      - `async def validate()` → (precision, recall, f1, details)
      - Targets from dossier:
        - Precision > 0.90 (alert if < 0.85)
        - Recall > 0.85 (alert if < 0.80)
        - F1 > 0.87 (alert if < 0.82)
      - `async def detect_drift()`: Alert if F1 drops > 5% week-over-week
  - st_golden_dataset_pairs table (from dossier schema)
  - PipelineScheduler trigger: weekly (Sunday 3am UTC)
- **Acceptance Criteria**:
  - Validation runs weekly automatically
  - Precision/Recall/F1 computed correctly
  - Alerts fire when below thresholds
  - Drift detection catches week-over-week degradation
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.4 "Golden Dataset Validation")

---

#### Issue 7.3.9 — Thompson Sampling threshold learner

- **Goal**: Implement Thompson Sampling for learning optimal reconciliation thresholds.
- **Deliverables**:
  - `k0/pipelines/p03/learning/thompson_sampling.py`:
    - `ThompsonSamplingThresholds` class:
      - `async def sample_threshold(threshold_name, space_id)` → float
      - `async def update_beta_params(threshold_name, space_id, success, failure)`
      - `async def get_expected_value(threshold_name, space_id)` → float
      - `async def load_beta_params(threshold_name, space_id)` → (alpha, beta)
    - Beta-Bernoulli model:
      - Prior: α=2, β=2 (weak uniform prior)
      - Update: α += successes, β += failures
      - Sample: np.random.beta(α, β)
    - Thresholds from dossier:
      - REINFORCE: bounds (0.75, 0.95), default 0.85
      - EXTEND_LOWER: bounds (0.45, 0.75), default 0.60
- **Acceptance Criteria**:
  - Thompson Sampling correctly samples from Beta distribution
  - Beta parameters persist in st_learned_weights
  - Bounds enforced on sampled values
  - Natural exploration/exploitation balance
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.5 "Thompson Sampling for Thresholds")

---

#### Issue 7.3.10 — Cold start strategy implementation

- **Goal**: Implement phased cold start for threshold learning based on signal count.
- **Deliverables**:
  - `k0/pipelines/p03/learning/cold_start.py`:
    - `ColdStartThresholdManager` class:
      - `async def get_threshold_with_cold_start(threshold_name, space_id)` → float
      - `async def get_cold_start_phase(space_id)` → "cold" | "warm" | "hot"
      - Phase definitions from dossier:
        - Cold (<100 signals): Use static defaults, no learning
        - Warm (100-500 signals): Thompson Sampling with wide bounds
        - Hot (>500 signals): Thompson Sampling with tight bounds
      - Bound widths:
        - Warm: (0.70, 0.98) — wider exploration
        - Hot: (0.75, 0.95) — tighter exploitation
    - Auto-transition as signal count grows
- **Acceptance Criteria**:
  - Phase detection based on signal count
  - Static defaults in cold phase
  - Wider bounds in warm phase
  - Tighter bounds in hot phase
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.8 "Threshold Cold Start Strategy")

---

#### Issue 7.3.11 — Per-space threshold isolation with fallback

- **Goal**: Implement hierarchical threshold learning with 3-level fallback.
- **Deliverables**:
  - `k0/pipelines/p03/learning/per_space_threshold.py`:
    - `PerSpaceThresholdManager` class:
      - `async def get_threshold(threshold_name, space_id, use_thompson=True)` → float
      - Fallback hierarchy:
        1. Space-specific (if signal_count ≥ 100)
        2. Global (aggregated across spaces)
        3. Static default (REINFORCE=0.85, EXTEND_LOWER=0.60)
      - `async def get_signal_count(space_id)` → int
    - `GlobalThresholdAggregator` class:
      - `async def aggregate_global_thresholds()`: Nightly job
      - Pool α and β from all spaces (privacy-safe: counts only)
      - Store in st_learned_weights with scope='global'
- **Acceptance Criteria**:
  - 3-level fallback works correctly
  - Space isolation maintained (no data leakage)
  - Global aggregation runs nightly
  - Privacy-safe (only counts pooled)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.6 "Per-Space Threshold Isolation")

---

#### Issue 7.3.12 — Causal threshold learning implementation

- **Goal**: Implement per-category bounds and feedback adjustment for causal inference thresholds.
- **Deliverables**:
  - `k0/pipelines/p03/learning/causal_threshold.py`:
    - `CausalThresholdLearner` class:
      - Per-category thresholds (from dossier):
        - TEMPORAL: (0.70, 0.95), default 0.85
        - SEMANTIC: (0.75, 0.98), default 0.90
        - BEHAVIORAL: (0.60, 0.90), default 0.75
      - `async def get_causal_threshold(category, space_id)` → float
      - `async def update_from_feedback(category, space_id, signal)`:
        - EDGE_CONFIRMED: α += 1
        - EDGE_REJECTED: β += 1
        - EDGE_DEMOTED: adjust based on outcome
    - Feedback adjustment deltas from dossier:
      - Wrong prediction: +0.03 to threshold
      - Missed causation: -0.02 to threshold
- **Acceptance Criteria**:
  - Category-specific bounds enforced
  - Feedback signals update thresholds
  - Adjustment deltas match dossier
  - All updates bounded to safe range
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.9 + causal sections)

---

#### Issue 7.3.13 — DBSCAN adaptive parameters learning

- **Goal**: Implement learning of DBSCAN clustering parameters from feedback.
- **Deliverables**:
  - `k0/pipelines/p03/learning/dbscan_params.py`:
    - `DBSCANParamsLearner` class:
      - Learnable parameters:
        - `eps`: Neighborhood radius (default 0.5, bounds [0.3, 0.8])
        - `min_samples`: Minimum cluster size (default 2, bounds [2, 10])
        - `temporal_weight`: Temporal vs semantic weighting (default 0.3)
      - `async def get_params(space_id)` → DBSCANParams
      - `async def update_from_feedback(space_id, signal)`:
        - CLUSTER_CONFIRMED: current params working
        - CLUSTER_SPLIT_REQUESTED: eps too high or min_samples too low
        - CLUSTER_MERGE_REQUESTED: eps too low or min_samples too high
    - Gradient-free optimization via feedback accumulation
- **Acceptance Criteria**:
  - All 3 parameters learnable
  - Bounds prevent extreme values
  - Feedback signals adjust parameters
  - Per-space isolation maintained
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (R2 clustering sections)

---

#### Issue 7.3.14 — R5 MCTS adaptive rollouts implementation

- **Goal**: Implement adaptive rollout allocation based on decision importance.
- **Deliverables**:
  - `k0/pipelines/p03/learning/mcts_adaptive.py`:
    - `MCTSAdaptiveRollouts` class:
      - `async def compute_rollout_count(decision_importance)` → int
      - Allocation strategy:
        - Low importance (< 0.3): 5 rollouts
        - Medium importance (0.3-0.7): 20 rollouts
        - High importance (> 0.7): 50 rollouts
      - `async def update_allocation_params(space_id, feedback)`:
        - Learn optimal rollout counts from outcomes
    - Integration with R5 DreamExplorer:
      - Query rollout count before MCTS execution
      - Track rollout count vs outcome quality
- **Acceptance Criteria**:
  - Rollout count varies by decision importance
  - Compute budget respected
  - Outcome quality correlates with rollout count
  - Learning improves allocation over time
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.5 + R5 sections)

---

#### Issue 7.3.15 — R5 shadow validation (MCTS vs heuristic)

- **Goal**: Implement shadow mode comparing MCTS decisions to heuristic baseline.
- **Deliverables**:
  - `k0/pipelines/p03/learning/mcts_shadow.py`:
    - `ShadowOutcomeTracker` class:
      - `async def record_decision(decision_id, heuristic_choice, mcts_choice, context)`
      - `async def evaluate_outcome(decision_id, outcome_signals)` (after 7 days)
      - `compute_outcome_score(signals)` → float (0-1)
    - st_mcts_shadow_log table (from dossier schema)
    - Comparison metrics:
      - Decision agreement rate
      - MCTS better rate (when they differ)
      - Average outcome difference
    - Promotion decision query (30-day analysis)
  - PipelineScheduler trigger: outcome evaluation job (daily)
- **Acceptance Criteria**:
  - All shadow decisions logged
  - Outcomes evaluated after 7-day delay
  - Metrics computed correctly
  - Promotion recommendation generated
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.5 "Shadow Mode Validation")

---

#### Issue 7.3.16 — st_mcts_shadow_log table migration

- **Goal**: Create storage table for MCTS shadow mode decision logging.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_mcts_shadow_log.py`:
    - CREATE TABLE st_mcts_shadow_log with columns:
      - `decision_id` UUID PRIMARY KEY
      - `decision_type` TEXT NOT NULL (merge, causal, cluster, etc.)
      - `heuristic_choice` TEXT NOT NULL
      - `mcts_choice` TEXT NOT NULL
      - `choices_differ` BOOLEAN NOT NULL
      - `context_json` JSONB
      - `applied_choice` TEXT NOT NULL
      - `outcome_heuristic` REAL
      - `outcome_mcts` REAL
      - `mcts_better` BOOLEAN
      - `evaluated_at` BIGINT
      - `created_at` BIGINT NOT NULL
    - Indexes: decision_type, created_at, choices_differ, evaluated_at
- **Acceptance Criteria**:
  - Table created with all columns per dossier schema
  - Indexes support analysis queries
  - No RLS needed (internal audit table)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.5 "Schema")

---

#### Issue 7.3.17 — st_golden_dataset_pairs table migration

- **Goal**: Create storage table for golden dataset validation pairs.
- **Deliverables**:
  - `k0/db/alembic/versions/XXXX_st_golden_dataset_pairs.py`:
    - CREATE TABLE st_golden_dataset_pairs with columns:
      - `pair_id` TEXT PRIMARY KEY
      - `entity1_id` TEXT NOT NULL
      - `entity2_id` TEXT NOT NULL
      - `is_same` BOOLEAN NOT NULL (true=duplicate, false=distinct)
      - `confidence` REAL NOT NULL
      - `source` TEXT NOT NULL (manual, user_correction, auto_generated)
      - `active` BOOLEAN NOT NULL DEFAULT TRUE
      - `created_at` BIGINT NOT NULL
      - `updated_at` BIGINT NOT NULL
    - Indexes: active, source, confidence
- **Acceptance Criteria**:
  - Table created with all columns per dossier schema
  - Active flag supports soft removal
  - Source tracks provenance
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.4 "Golden Dataset Structure")

---

#### Issue 7.3.18 — Learning rollout alerting rules

- **Goal**: Implement alerts for learning rollout issues.
- **Deliverables**:
  - `k0/telemetry/mixins/p03_rollout_alerts.py`:
    - Alert rule builder following K0 telemetry patterns
  - Generated output: `k0/telemetry/generated/rules/p03_rollout_alerts.yaml`:
    - `P03ShadowRegressionRate`: Warning if regression_rate > 10%
    - `P03CanaryHaltTriggered`: Critical when canary halts
    - `P03GoldenDatasetPrecisionLow`: Warning if precision < 0.85
    - `P03GoldenDatasetRecallLow`: Warning if recall < 0.80
    - `P03GoldenDatasetF1Drift`: Warning if F1 drops > 5% week-over-week
    - `P03PromotionEligible`: Info when formula becomes eligible
- **Acceptance Criteria**:
  - All rollout-related alerts defined
  - Thresholds match dossier specifications
  - Alert descriptions include remediation steps
  - Critical alerts page on-call
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 1.4.4 alerts + Section 11.7)

---

#### Issue 7.3.19 — Learning rollout dashboard

- **Goal**: Implement Grafana dashboard for monitoring learning rollout status.
- **Deliverables**:
  - `k0/telemetry/mixins/p03_rollout_dashboards.py`:
    - Dashboard builder following K0 telemetry patterns
  - Generated output: `k0/telemetry/generated/dashboards/p03_learning_rollout.json`:
    - Row 1: Feature Flag States (all learning flags)
    - Row 2: Shadow Mode Metrics (agreement, improvement, regression rates)
    - Row 3: Canary Progress (current phase, % rollout, halt history)
    - Row 4: Promotion Eligibility (per formula)
    - Row 5: Golden Dataset Validation (Precision, Recall, F1 trends)
    - Row 6: MCTS Shadow Comparison (heuristic vs MCTS outcomes)
- **Acceptance Criteria**:
  - Dashboard imports cleanly into Grafana
  - All metrics visualized
  - Rollout progress clearly visible
  - Historical trends available
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 8.2.6)

---

#### Issue 7.3.20 — Learning algorithms integration tests

- **Goal**: Comprehensive integration testing of learning rollout system.
- **Deliverables**:
  - `tests/k0/pipelines/p03/learning/test_feature_flags.py`:
    - Test flag state transitions
    - Test master switch override
  - `tests/k0/pipelines/p03/learning/test_shadow_mode.py`:
    - Test dual execution
    - Test baseline-only application
    - Test error isolation
  - `tests/k0/pipelines/p03/learning/test_canary_rollout.py`:
    - Test phase progression
    - Test space selection stratification
    - Test automatic halt
  - `tests/k0/pipelines/p03/learning/test_thompson_sampling.py`:
    - Test Beta distribution sampling
    - Test parameter updates
    - Test cold start phases
  - `tests/k0/pipelines/p03/learning/test_golden_dataset.py`:
    - Test validation calculation
    - Test drift detection
- **Acceptance Criteria**:
  - ≥90% line coverage for learning module
  - All rollout paths tested
  - Halt conditions validated
  - Thompson Sampling statistically verified
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 10.4 "Test Categories")

---

## Milestone 8 — R5 Dream Phase + P06 Active Learning Integration

### Epic 8.1 — R5 Dream algorithms implementation

> **References**:
>
> - Dossier Section 4.6: R5 — Dream-Like Exploration (REM)
> - Dossier Section 4.6.0: MVP Strategy (R5 modes, metrics, rollout)
> - Dossier Section 4.6.1: Counterfactual Thinking (CPN)
> - Dossier Section 4.6.2: Forward Simulation (TPN-MCTS) + Adaptive Rollouts
> - Dossier Section 4.6.3: Episodic Simulation (SPC-UQ)
> - Dossier Section 4.6.4: Insight Generation (BGT-SM)
> - Dossier Section 4.6.5: Shadow Mode Validation (heuristic vs MCTS)
> - Dossier Section 4.6.6: Motor Rehearsal Analog (TDL-HCO)
> - Dossier Section 4.6.7: R5 Complexity Assessment (MVP vs Phase 2)
> - Dossier: PhaseTransition.can_skip_dream_phase (backlog/time-window skip)
> - Dossier Appendix D.2.3: Exit topic `p03.insight.generated.v1`
> - Dossier Appendix D.3.1: stage_50/stage_51/stage_52 mapping
> - Dossier Section 7.4.5: M22 — DreamExplorer (Insight model, explore() flow)
> - Dossier Appendix C.6.3/C.6.4: BGT-SM thresholds + TDL-HCO value learning

---

#### Issue 8.1.1 — R5 execution mode control (disabled/shadow/enabled_low/enabled)

- **Goal**: Implement R5 execution mode control consistent with the dossier MVP strategy and rollout phases.
- **Deliverables**:
  - Config flag `P03_FF_R5_MODE` with values: `disabled`, `shadow`, `enabled_low`, `enabled` (default `disabled` for MVP).
  - R5 mode metrics:
    - `p03_r5_mode` (gauge: 0=disabled, 1=shadow, 2=enabled_low, 3=enabled)
    - `p03_r5_compute_seconds_saved` (counter)
- **Acceptance Criteria**:
  - Default behavior is MVP-safe: R5 skipped when mode is `disabled`
  - `enabled_low` enforces reduced rollouts (per dossier)
  - R5 mode is observable via metrics
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.0)

---

#### Issue 8.1.2 — R5 skip conditions (backlog/time window) + accounting

- **Goal**: Enforce R5 skip logic for backlog pressure and time window constraints.
- **Deliverables**:
  - R5 skip predicate aligned to dossier:
    - Skip if `cycle_context.backlog_size > 1000` OR `cycle_context.remaining_window_seconds < 60`
  - `p03_r5_skipped_decisions` (counter) incremented when R5 is skipped.
- **Acceptance Criteria**:
  - When skip condition is met, pipeline transitions from R4 to R6 without R5
  - Skip path does not break downstream R6/R7/R8 expectations
  - Metric increments match actual skip events
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (PhaseTransition.can_skip_dream_phase; R5 timing table)

---

#### Issue 8.1.3 — M22 DreamExplorer scaffold + deterministic execution

- **Goal**: Implement the DreamExplorer module skeleton for R5, including config and deterministic behavior.
- **Deliverables**:
  - `M22 DreamExplorer` implementation aligned to dossier:
    - `Insight` model fields: type, description, confidence, supporting_evidence, novelty_score
    - `DreamConfig`: `depth`, `creativity`, `max_insights` (defaults per dossier)
    - `explore(recent_patterns, kg_subgraph)` orchestrates CPN, TPN-MCTS, BGT-SM then ranks by novelty
  - Determinism requirements:
    - Seed random walks / rollout sampling with `cycle_ulid` for repeatable tests
    - Perturbation ordering deterministic (sorted by entity_id)
- **Acceptance Criteria**:
  - DreamExplorer returns at most `max_insights` insights sorted by novelty
  - Deterministic outputs in CI given fixed seed inputs
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 7.4.5; Section 4.6.7)

---

#### Issue 8.1.4 — CPN counterfactual generation (UPWARD/DOWNWARD/SEMIFACTUAL)

- **Goal**: Generate counterfactual scenarios from recent patterns using the CPN algorithm.
- **Deliverables**:
  - Implement CPN scenario generation modes:
    - UPWARD (better outcome), DOWNWARD (worse outcome), SEMIFACTUAL (different path, same outcome)
  - Persist top scenarios to `st_prospective` (counterfactual/prospective records) via R5 outputs.
- **Acceptance Criteria**:
  - Counterfactuals include plausibility and success probability (per dossier scenario metrics)
  - Only scenarios meeting minimum quality thresholds are retained
  - Writes occur through the staged write path (R6/R7), not ad-hoc DB writes
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.1; Appendix C.6.1)

---

#### Issue 8.1.5 — TPN-MCTS forward simulation with UCT selection

- **Goal**: Implement forward simulation using MCTS (UCT selection) to explore future outcomes.
- **Deliverables**:
  - UCT selection with static exploration constant $c=\sqrt{2}\approx1.414$.
  - Forward simulation outputs: action sequences + predicted outcomes + probabilities.
- **Acceptance Criteria**:
  - MCTS uses UCT selection with correct unvisited-node handling
  - Forward simulation returns bounded number of scenarios within compute budget
  - Behavior consistent with dossier compute constraints (1000 rollouts per cycle cap)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.2; Section 4.6.2.2)

---

#### Issue 8.1.6 — Adaptive rollout allocation + early termination

- **Goal**: Allocate rollout counts based on decision importance and terminate early when decision is clear.
- **Deliverables**:
  - Decision type → rollout allocation table (merge/split=100, causal=50, cluster=30, reinforce=20, decay/novelty=10).
  - Decision classification adjustments:
    - Boost rollouts for `FAMILY_MEMBER` entities
    - Reduce rollouts for low-confidence contexts (<0.60)
  - Early termination conditions:
    - Clear winner (>90% visits)
    - Low uncertainty (CI width <5%)
    - Budget exhausted (per-cycle cap)
- **Acceptance Criteria**:
  - Rollout counts follow dossier table and are capped at 100
  - Early termination triggers correctly
  - Compute budget is enforced globally per cycle
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.2.1)

---

#### Issue 8.1.7 — Persist MCTS decisions + metrics

- **Goal**: Store MCTS decision traces for analysis and expose key MCTS metrics.
- **Deliverables**:
  - `st_mcts_decisions` table for decision traces (decision_id, type, rollouts_allocated/executed, early termination, chosen_action, CI width, compute_ms).
  - Metrics:
    - `p03_mcts_rollouts` (histogram)
    - `p03_mcts_early_termination_rate` (gauge)
    - `p03_mcts_compute_budget_used` (counter)
    - `p03_mcts_budget_exhausted` (counter)
- **Acceptance Criteria**:
  - Records written for all executed MCTS decisions
  - Metrics align with stored traces and per-cycle budgets
  - Indexes support decision_type + created_at queries
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.2.1)

---

#### Issue 8.1.8 — SPC-UQ episodic simulation with uncertainty quantification

- **Goal**: Recombine episode fragments to reconstruct plausible narratives with uncertainty signals.
- **Deliverables**:
  - SPC-UQ implementation producing reconstructed timelines (fragments) plus uncertainty estimates.
  - Gating to respect R5 compute constraints (skip or limit in MVP, per dossier complexity assessment).
- **Acceptance Criteria**:
  - Episodic simulation produces bounded outputs (max candidates per cycle)
  - Uncertainty quantification is captured for downstream ranking/filtering
  - MVP mode can disable SPC-UQ entirely
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.3; Section 4.6.7)

---

#### Issue 8.1.9 — BGT-SM bisociative insight generation (semantic distance + PMI)

- **Goal**: Discover remote associations via random walks and information-theoretic surprise scoring.
- **Deliverables**:
  - Random walk with restart (restart probability 0.15, steps 1000) seeded deterministically.
  - Remote-associate filtering: semantic distance > 0.7.
  - Surprise threshold: PMI > 3.0.
  - Novelty scoring consistent with dossier (distance × pmi / (count+1)).
- **Acceptance Criteria**:
  - Only insights meeting semantic distance + PMI thresholds are produced
  - Writes to `st_sem` use `pattern_type='insight'`
  - Deterministic execution in CI with fixed seed
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.4; Appendix C.6.3)

---

#### Issue 8.1.10 — Insight quality thresholds + ranking

- **Goal**: Implement quality filters for surfacing user-visible R5 insights.
- **Deliverables**:
  - Enforce insight quality thresholds:
    - Semantic distance > 0.7
    - PMI score > 3.0
    - Novelty score > 0.5
    - Serendipity > 0.6 (novelty × relevance × actionability)
  - Rank insights by novelty_score and retain top N (max_insights).
- **Acceptance Criteria**:
  - Insights failing thresholds are not emitted nor written as surfaced insights
  - Top-N selection is stable and deterministic for identical inputs
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.6.3 “Insight Quality Thresholds”; Section 7.4.5)

---

#### Issue 8.1.11 — TDL-HCO motor rehearsal for habits (value function + bottlenecks)

- **Goal**: Optimize procedural routines via TD learning and identify bottlenecks via negative value gradients.
- **Deliverables**:
  - TD(0) learning for value function $V(s)$ per step with $\gamma=0.9$ and $\alpha=0.1$.
  - Bottleneck detection rule: $\Delta V(s_t)=V(s_{t+1})-V(s_t) < -2.0$.
  - Persist optimized routines to `st_procedural` and write proposed improvements to `st_prospective`.
- **Acceptance Criteria**:
  - Value function learned from execution history
  - Bottlenecks detected per dossier threshold
  - Outputs staged for atomic write (R6/R7)
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.6; Appendix C.6.4)

---

#### Issue 8.1.12 — R5 outputs routed through staged writes container (R6Output)

- **Goal**: Ensure all R5 outputs flow through the R6 staging container for atomic application in R7.
- **Deliverables**:
  - R5 produces staged records compatible with `R6Output`:
    - staged_truth_writes (st_sem/st_procedural/st_prospective targets)
    - staged_outbox_events (including insight event)
    - reconciliation summary includes R5 work performed/skipped
- **Acceptance Criteria**:
  - No direct writes to truth tables in R5 (only staged output)
  - R7 consumes R6Output and writes atomically via UnitOfWork
  - Idempotency keys remain stable across retries
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (R6Output snippet; Appendix D.3 mapping)

---

#### Issue 8.1.13 — Emit R5 insight event `p03.insight.generated.v1`

- **Goal**: Emit insight events when R5 produces user-facing insights.
- **Deliverables**:
  - Outbox-backed emission of `p03.insight.generated.v1` with payload including:
    - insight_type, description, confidence, novelty_score, supporting evidence
  - Ensure emission happens in R8 via outbox drain (idempotent).
- **Acceptance Criteria**:
  - Insight events only emitted when an insight passes quality thresholds
  - Events are deduplicated on retry (idempotency)
  - Topic name exactly matches dossier registry
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.2.3 “Exit Topics”)

---

#### Issue 8.1.14 — R5 shadow validation (heuristic vs MCTS) integration

- **Goal**: Implement the dossier’s shadow validation loop to justify MCTS compute cost before enabling.
- **Deliverables**:
  - Shadow mode behavior for R5 decisions:
    - Compute heuristic choice
    - Run MCTS read-only
    - Apply heuristic
    - Log to `st_mcts_shadow_log`
  - Outcome scoring and evaluation window (30 days) per dossier.
  - Promotion logic from `shadow` → `enabled_low` based on “diff >20% and MCTS better >55%”.
- **Acceptance Criteria**:
  - Shadow decisions logged for later evaluation
  - Outcome evaluation runs after 7-day delay
  - Recommendation thresholds match dossier tables
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 4.6.0; Section 4.6.5)
  - Plan Dependencies: Issue 7.3.15–7.3.16 (shadow log + schema)

### Epic 8.2 — P06 Active Learning integration

> **System**: Memory Formation Feedback (Command Port)
>
> This epic implements **System 1: Memory Formation Feedback** (the gap resolution loop).
> User answers to gap questions arrive via Command Port (`memory.delta`) and become st_hipp_events rows.
>
> **Two-System Architecture** (Dossier Section 9.9):
>
> | Aspect | This Epic (8.2) | Epic 7.1 |
> |--------|-----------------|----------|
> | **System** | Memory Formation | Model Refinement |
> | **Port** | Command Port | Obs Port |
> | **Topic** | `memory.delta` | `feedback.signal.p03` |
> | **Creates** | st_hipp_events (new facts) | st_learned_weights (tuning) |
> | **Invariants** | INV-MEM-1 through INV-MEM-8 | INV-MODEL-1 through INV-MODEL-5 |
>
> **Key Invariants** (Dossier Section 9.9.4):
> - **INV-MEM-1**: gap_id round-trip — gap_id sent with question MUST come back with answer
> - **INV-MEM-3**: gap_id location — `envelope.body.correlation.gap_id` (not header)
> - **INV-MEM-4**: Answer creates memory — user response becomes st_hipp_events row
> - **INV-MEM-6**: Resolution type mutex — gap is IMPLICIT or USER_ANSWER, never both
> - **INV-MEM-7**: Grace period — P06 waits 24-72 hours before asking (allows implicit resolution)

> **References**:
>
> - **Dossier Section 9.9: Feedback System Invariants (Two-System Architecture)** ← CRITICAL
> - Dossier Section 5: P06 Active Learning Integration (5.1–5.7)
> - Dossier Section 5.2: Gap detection during reconciliation (gap types + algorithm)
> - Dossier Section 5.3: Entropy scanning (proactive gap detection)
> - Dossier Section 5.3A: Implicit Gap Resolution (GapAutoResolver)
> - Dossier Section 5.6: Attention budget integration (token bucket)
> - Dossier Section 6.11: `st_learning_queue` schema (gap queue)
> - Dossier Section 9.3: P03 → P06 contract + `p06.gap.resolved.v1` (9.3.1–9.3.3)
> - Dossier Appendix E.2.3: P06 integration topics (`p06.gap.resolved.v1`, `p06.anchor.updated.v1`)
> - Dossier Section 12.1.2 + 12.3.1: Gap queue max depth + gap priority weights/flags
> - Idea-0001: `docs/architecture/ideas/0001-active-learning-loop.md`

---

#### Issue 8.2.1 — Shannon entropy scoring (gap uncertainty normalization)

- **Goal**: Implement the dossier’s Shannon-entropy-based uncertainty scoring used to prioritize gaps.
- **Deliverables**:
  - A normalized entropy function for candidate distributions (e.g., ambiguous entity candidates):
    - compute Shannon entropy, normalize by $\log_2(n)$, clamp to $[0, 1]$
  - Default entropy fallback for non-distribution cases: `entropy = 1.0 - confidence`.
- **Acceptance Criteria**:
  - For candidate distributions, entropy is $0$ when a single candidate dominates and approaches $1$ when candidates are uniform.
  - Entropy output is always in $[0, 1]$.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.2.2 `_calculate_entropy`)

---

#### Issue 8.2.2 — Beta-distribution belief modeling for anchors (confirmations/contradictions)

- **Goal**: Ensure user beliefs (“anchors”) are modeled as Beta distributions and updated consistently across evidence types.
- **Deliverables**:
  - Anchor update logic aligned to the dossier’s Beta primer and update patterns:
    - $\alpha$ increments for evidence FOR
    - $\beta$ increments for evidence AGAINST
    - optional temporal decay before updates (if enabled by policy)
  - Explicit handling for contradictory evidence pathways:
    - mark unresolved contradictions for P06 where required (gap emission)
    - apply confidence penalties for unresolved contradictions (do not block completion by default)
- **Acceptance Criteria**:
  - Anchor posterior mean (confidence) matches $\alpha/(\alpha+\beta)$.
  - Contradictions do not stall P03 by default; they are routed to P06 when configured.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.4; Section 12.1.1)
  - Storage: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.12 `st_anchors`)

---

#### Issue 8.2.3 — Gap priority scoring + tunable weights (entropy/recency/impact)

- **Goal**: Implement the resolved gap priority formula with tunable weights and expose weight overrides.
- **Deliverables**:
  - Implement the `compute_gap_priority(...)` scoring function from the dossier’s resolved TODOs.
  - Support feature-flag overrides for weights:
    - `P03_GAP_WEIGHT_ENTROPY` (default 0.5)
    - `P03_GAP_WEIGHT_RECENCY` (default 0.3)
    - `P03_GAP_WEIGHT_IMPACT` (default 0.2)
- **Acceptance Criteria**:
  - Priority is clamped to $[0, 1]$.
  - Weight overrides take effect without requiring code changes.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 12.3.1)

---

#### Issue 8.2.4 — Implement GapDetector (R4/R7) for all canonical gap types

- **Goal**: Detect gaps during reconciliation using the dossier’s canonical gap type set and triggers.
- **Deliverables**:
  - Implement gap detection for:
    - `AMBIGUOUS_ENTITY`, `LOW_CONFIDENCE_EDGE`, `MISSING_ATTRIBUTE`, `CONTRADICTION`, `CONCEPT_DRIFT`, `STRUCTURAL_HOLE`, `STALE_ANCHOR`
  - Encode ambiguity and confidence thresholds consistent with dossier guidance (auto-resolve, flag, emit-to-P06 thresholds).
- **Acceptance Criteria**:
  - For ambiguous entity resolution, the correct action is taken at each threshold bucket (auto-resolve vs flagged vs emitted-to-P06).
  - All emitted gaps include the fields required for downstream question framing.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.2.1–5.2.2)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Entity disambiguation emit thresholds + metrics near Section 4.5.1.2)

---

#### Issue 8.2.5 — Durable gap emission (persist `st_learning_queue` then publish `p03.gap.detected.v1`)

- **Goal**: Emit gaps to P06 in a durable, idempotent way.
- **Deliverables**:
  - Implement gap persistence into `st_learning_queue` prior to publication.
  - Emit `p03.gap.detected.v1` with payload matching the contract (required fields, naming, and partition key).
  - Ensure emission path supports idempotency (same gap_id should not double-enqueue).
- **Acceptance Criteria**:
  - `st_learning_queue` contains a durable row for every emitted gap.
  - Outgoing event validates against the dossier contract for `p03.gap.detected.v1`.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.2.3; Section 9.3.1)
  - Storage: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.11)

---

#### Issue 8.2.6 — Gap deduplication + queue depth backpressure

- **Goal**: Prevent unbounded growth and redundant gaps in `st_learning_queue`.
- **Deliverables**:
  - Deduplicate candidate gaps against existing queue entries (same gap_type/entity_id/truth_id context) before persisting.
  - Enforce queue depth controls:
    - stop gap detection above `gap_queue_max_depth`
    - emit warnings above `gap_queue_high_watermark`
    - enforce `gap_priority_floor`, with the exception that high-entropy gaps (entropy > 0.7) always queue
- **Acceptance Criteria**:
  - Duplicate gaps are suppressed deterministically.
  - Queue depth limits are enforced and observable.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.3.1 dedup + rate limiting)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 12.1.2)

---

#### Issue 8.2.7 — Entropy Scanner background process (proactive gap detection)

- **Goal**: Implement the background scan loop that produces gaps without waiting for new events.
- **Deliverables**:
  - Scheduler triggers:
    - daily cron (4 AM)
    - post-consolidation trigger
    - manual trigger surface
  - Implement the three scan families:
    - ontology violations (missing required attributes)
    - anchor decay (stale anchors)
    - structural hole detection (missing expected KG edges)
  - Rate limit per scan (max N gaps per scan) and priority sort by importance_score.
- **Acceptance Criteria**:
  - Scan results are deduplicated and persisted to `st_learning_queue`.
  - Scanner does not exceed configured per-scan limits.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.3.1–5.3.3)

---

#### Issue 8.2.8 — Attention budget gating (token bucket + per-context configuration)

- **Goal**: Prevent user question fatigue via the dossier’s attention budget rules.
- **Deliverables**:
  - Implement token-bucket style attention budget checks (or the dossier’s configured integration surface) with:
    - max_tokens per day
    - refill rate
    - bounded overdraw for high-priority gaps
  - Provide per-context budget profiles (onboarding / normal / low_engagement) with explicit config keys.
- **Acceptance Criteria**:
  - Low-priority gaps are suppressed when budget is exhausted.
  - High-priority gaps can overdraw within configured limit.
  - Reasons for suppression are recorded (budget exhausted vs rate limited vs DND).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.6.1)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 12.3.4)
  - Idea-0001: `docs/architecture/ideas/0001-active-learning-loop.md` (attention/budgeting narrative)

---

#### Issue 8.2.9 — Consume P06 resolution events (`p06.gap.resolved.v1` → update gap lifecycle)

- **Goal**: Close the loop by consuming P06 resolution acknowledgments and updating the gap queue.
- **Deliverables**:
  - Subscribe to `p06.gap.resolved.v1` and update `st_learning_queue` status:
    - ANSWERED / DISMISSED / EXPIRED / SUPERSEDED mapped onto queue lifecycle (`ANSWERED`, `REJECTED`, `EXPIRED`, `SUPPRESSED` or equivalent, per decision)
  - If `resolution_type=ANSWERED`, store `answer_event_id` and mark the gap record as ready for reconsolidation linking.
- **Acceptance Criteria**:
  - Gap lifecycle transitions are consistent and idempotent.
  - Resolution events validate against the dossier contract.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.3.2)
  - Storage: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.11 status fields)
  - Canonical topic registry: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix E.2.3)

---

#### Issue 8.2.10 — Gap answer correlation convention (`body.correlation.gap_id`) + correctness checks

- **Goal**: Ensure user answers can be deterministically correlated back to the originating gap.
- **Deliverables**:
  - Enforce the canonical convention:
    - answer events include `body.correlation.gap_id` (ULID)
  - Where needed, implement a correctness check path that can resolve `gap_id` from persisted event/WAL JSON when given `answer_event_id`.
- **Acceptance Criteria**:
  - For any resolved gap with an `answer_event_id`, P03 can prove the answer event references the same `gap_id` (or emits a structured error).
  - No PII is stored in the correlation payload.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.3.3)
  - Idea-0001: `docs/architecture/ideas/0001-active-learning-loop.md` (closure flow)

---

#### Issue 8.2.11 — Consume `p06.anchor.updated.v1` (belief anchor refinements)

- **Goal**: Apply P06’s anchor refinements back into K0 belief storage.
- **Deliverables**:
  - Subscribe to `p06.anchor.updated.v1`.
  - Define and implement the mapping from `P06AnchorUpdated` payload into `st_anchors` updates.
  - Ensure updates are tenant/space isolated and auditable.
- **Acceptance Criteria**:
  - Incoming events are validated against an explicit schema (or, if schema is missing, the missing contract is resolved via Milestone 0 governance before implementation).
  - Anchor updates are applied deterministically and are safe under retries.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix E.2.3 topic registry)
  - Storage: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 6.12)

---

#### Issue 8.2.12 — Observability for gap detection + emission + resolution

- **Goal**: Make the gap loop observable end-to-end so operators can diagnose backlog, spam, and closure effectiveness.
- **Deliverables**:
  - Metrics for ambiguous entity detection outcomes:
    - detected / auto_resolved / flagged / emitted_to_p06
    - accuracy gauge for flagged resolutions
  - Metrics for gap queue health:
    - queue depth, suppressed due to depth/budget, expired, resolved
  - Structured logs for:
    - “gap_created”, “gap_suppressed”, “gap_emitted”, “gap_resolved”
- **Acceptance Criteria**:
  - Metrics increment in the correct code paths and have stable label sets.
  - Operators can distinguish suppression reasons (depth vs budget vs dedup).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (ambiguous entity metrics + config thresholds near Section 4.5.1.2)
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 12.1.2 depth policy)

---

#### Issue 8.2.13 — Active learning integration tests (contracts + lifecycle)

- **Goal**: Validate the P03↔P06 active learning loop with deterministic tests.
- **Deliverables**:
  - Tests that cover:
    - `p03.gap.detected.v1` payload validation against the contract
    - dedup + max depth enforcement
    - status transitions in `st_learning_queue` upon `p06.gap.resolved.v1`
    - entropy scoring normalization for candidate distributions
  - A minimal “loop test” fixture: detected gap → emitted → resolved → queue updated.
- **Acceptance Criteria**:
  - Tests are deterministic and do not depend on external services.
  - Contract-breaking changes fail tests.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 9.3; Section 6.11)

---

#### Issue 8.2.14 — GapAutoResolver implicit resolution (R0 preemptive path)

- **Goal**: Implement implicit gap resolution that auto-resolves gaps when users naturally provide clarifying context.
- **Deliverables**:
  - `GapAutoResolver` class that:
    - Loads pending `AMBIGUOUS_ENTITY` gaps from `st_learning_queue`
    - Matches extracted NER entities against gap candidates using Jaccard similarity
    - Applies label matching bonus (+0.10) and specificity bonus (+0.15)
    - Auto-resolves gaps when confidence ≥ 0.75
    - Updates `st_learning_queue.status = 'RESOLVED'` with `resolution_type = 'IMPLICIT'`
  - Two-pass matching strategy:
    1. NER-based: Match extracted entities against gap candidates
    2. Text-based: Fallback keyword matching in raw event text
  - Integration with R0 Batch Selector phase
- **Acceptance Criteria**:
  - Gaps matching incoming entities with confidence ≥ 0.75 are auto-resolved
  - Resolution includes `match_reason`, `source_event_id`, and `resolved_at` timestamp
  - Implicit resolutions marked with `resolution_type = 'IMPLICIT'` (distinguishable from explicit P06 answers)
  - P06 question generation excludes gaps with `resolution_type = 'IMPLICIT'`
- **Design Philosophy**:
  - "Don't ask users questions they've already answered"
  - System should be smart enough to recognize clarifying context in normal conversation
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.3A "Implicit Gap Resolution")
  - Implementation: `k0/modules/consolidation/gap_auto_resolver.py`

---

#### Issue 8.2.15 — P06 grace period configuration (implicit resolution window)

- **Goal**: Ensure P06 waits for implicit resolution before generating explicit questions.
- **Deliverables**:
  - Grace period configuration:
    - `P03_IMPLICIT_GRACE_PERIOD_HOURS` (default: 24 hours)
    - Configurable range: 24-72 hours
  - P06 question generator filter:
    - Exclude gaps where `created_at + grace_period > now()`
    - Exclude gaps where `resolution_type = 'IMPLICIT'`
  - Metrics for grace period effectiveness:
    - `p03_gaps_resolved_during_grace_period` counter
    - `p03_gaps_escalated_to_p06` counter (gaps that passed grace period without implicit resolution)
- **Acceptance Criteria**:
  - New gaps are not immediately eligible for P06 questions
  - Grace period is configurable via environment variable
  - Metrics track implicit vs explicit resolution rates
- **Rationale**:
  - Give the GapAutoResolver time to find implicit resolutions before bothering users
  - Reduces question fatigue while maintaining gap closure rate
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.3A.5 "P06 Grace Period Integration")

---

#### Issue 8.2.16 — Implicit resolution observability + metrics

- **Goal**: Make implicit resolution path observable for tuning and debugging.
- **Deliverables**:
  - Metrics:
    - `p03_gaps_auto_resolved_total` (counter by gap_type)
    - `p03_gaps_checked_for_implicit` (counter)
    - `p03_implicit_match_confidence` (histogram)
    - `p03_implicit_resolution_latency_ms` (histogram)
  - Structured logs:
    - `gap_auto_resolved`: gap_id, gap_type, resolved_value, confidence, match_reason
    - `gap_implicit_match_failed`: gap_id, best_confidence, threshold
  - GapAutoResolverStats dataclass for aggregated stats
- **Acceptance Criteria**:
  - Operators can see implicit resolution rate vs explicit P06 rate
  - Match confidence distribution visible for threshold tuning
  - Latency tracked for performance optimization
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Section 5.3A.6 "Metrics")

### Epic 8.3 — K0 Kernel integration (Appendix D)

> **References**:
>
> - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D: “P03 Kernel Integration Blueprint”)
> - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.2: Pipeline contract design + topic design)
> - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.3: Stage mapping + parallel execution groups)
> - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.5–D.6: Scheduler triggers + bus subscription/emission)
> - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.7–D.8: UnitOfWork + capability-gated syscalls + fabric)
> - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.10: Failure modes)
> - K0 code: `k0/kernel/app.py` (YAML pipeline boot + scheduler trigger executor)
> - K0 code: `k0/runtime/pipeline_runner.py` + `k0/runtime/schemas.py` (PipelineRunner, PipelineSpec, TriggerSpec, FailureMode)
> - K0 code: `k0/bus/core.py` (BusDispatcher subscribe/dispatch + BusMessage contract)
> - K0 code: `k0/uow/unit_of_work.py` (UnitOfWork transaction + outbox staging)
> - K0 code: `k0/fabric/loader.py` + `k0/contracts/capabilities/*.yaml` (capability definition loading/registration)

---

#### Issue 8.3.1 — P03 pipeline contract YAML (`p03_consolidation.v1.yaml`) aligned to Appendix D

- **Goal**: Define the authoritative P03 batch-mode pipeline contract that the kernel can boot and run without bespoke wiring.
- **Deliverables**:
  - `k0/contracts/pipelines/p03_consolidation.v1.yaml` with:
    - `pipeline_id: P03_CONSOLIDATION` and `version: v1`
    - `declared_topics` including `p03.consolidation.triggered.v1` (as the batch-mode entry topic)
    - `exit_topic: p03.consolidation.complete.v1`
    - `required_capabilities` consistent with Appendix D.2.2 (non-empty; least privilege)
    - `dag` containing the full stage set from Appendix D.3.1
- **Acceptance Criteria**:
  - `PipelineSpec.load(...)` validates the file without errors.
  - `required_capabilities` is non-empty and matches the intended storage/fabric access surface.
  - `k0/kernel/app.py` boot sequence can load the spec and subscribe the runner to `declared_topics`.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.2.1–D.2.3)
  - K0: `k0/kernel/app.py` (pipeline spec loading + subscription)

---

#### Issue 8.3.2 — DAG stage registration (18 stages) + dependency/parallelism correctness

- **Goal**: Ensure P03’s DAG stage IDs, ordering, and safe parallelism match the kernel’s declarative DAG execution model.
- **Deliverables**:
  - `k0/contracts/pipelines/p03_consolidation.v1.yaml` `dag:` section encodes all stages with exact IDs from Appendix D.3.1:
    - `stage_00_select_batch` through `stage_80_event_emitter`
  - Stage dependency graph matches Appendix D.3.1 (e.g., stage_20 after stage_10+stage_11; stage_70 after stage_60; stage_80 after stage_70).
  - A DAG validation test that asserts:
    - stage count = 18
    - expected parallel groups are possible (Appendix D.3.2)
- **Acceptance Criteria**:
  - `PipelineRunner(spec, registry)` builds a DAG successfully.
  - Parallel execution groups match Appendix D.3.2 (max parallel group size = 3).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.3.1–D.3.2)
  - K0: `k0/runtime/pipeline_runner.py`, `k0/runtime/dag_builder.py`

---

#### Issue 8.3.3 — Module contract YAMLs per stage (`consolidation.*.v1.yaml`) incl. failure modes

- **Goal**: Ensure each P03 stage module is contract-defined for registry lookup, latency budgets, idempotency, side effects, and known failure handling.
- **Deliverables**:
  - Module contract YAMLs under `k0/contracts/modules/` for every stage module in Appendix D.3.1 (and any P03-specific helpers like `gap_emitter`), including:
    - `module_id`, `version`, `latency_budget_ms`, `idempotent`, `side_effects`
    - `fabric_capabilities` (where applicable)
    - `failure_modes` entries aligned to Appendix D.10.1
- **Acceptance Criteria**:
  - `ModuleRegistry.load_contracts("k0/contracts/modules")` loads all P03 module contracts without validation errors.
  - For each stage’s `module: <module_id>:v1` in the pipeline DAG, `ModuleRegistry.get(...)` can resolve an implementation (or the missing implementation is tracked as a concrete follow-up).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.3.3; Appendix D.10.1)
  - K0: `k0/runtime/module_registry.py`, `k0/runtime/schemas.py`

---

#### Issue 8.3.4 — Fabric capability registration for P03 (score_importance, cluster_episodes, ...)

- **Goal**: Make P03 modules invokable by capability name via K0 Fabric (ADR-K004), without hardcoding provider wiring.
- **Deliverables**:
  - `k0/contracts/capabilities/consolidation.v1.yaml` defining P03 capability names and their providers (module-based), including at minimum:
    - `score_importance` → `consolidation.importance_scorer`
    - `cluster_episodes` → `consolidation.episodic_clusterer`
    - `detect_duplicates` → `consolidation.simhash_deduplicator`
    - `extract_entities` → `consolidation.entity_extractor`
  - Capability timeouts/latency budgets consistent with Appendix D.4.2.
- **Acceptance Criteria**:
  - `discover_and_register_capabilities(...)` registers the P03 capability set from YAML.
  - Capability names match the canonical registry (Appendix E) and the dossier examples (Appendix D.4.3).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.4.2–D.4.3; Appendix D.8)
  - K0: `k0/fabric/loader.py`, `k0/contracts/capabilities/core.v1.yaml` (pattern)

---

#### Issue 8.3.5 — PipelineScheduler trigger configuration (INTERVAL / THRESHOLD / MANUAL)

- **Goal**: Configure declarative triggers so P03_CONSOLIDATION can run on interval, backlog threshold, and manual request.
- **Deliverables**:
  - `k0/contracts/pipelines/p03_consolidation.v1.yaml` `triggers:` list (using K0 schema field names), including:
    - `interval` trigger: `interval_seconds: 5400` (90 minutes)
    - `threshold` trigger: `table: st_hipp_events`, condition for P03 backlog, `threshold_count: 500`
    - `manual` trigger for admin/debug execution
- **Acceptance Criteria**:
  - Scheduler can register the P03 spec and start its triggers without error.
  - Manual trigger invocation fires and executes the pipeline via the kernel’s scheduler executor.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.5.1–D.5.2)
  - K0: `k0/scheduler/scheduler.py`, `k0/runtime/schemas.py`

---

#### Issue 8.3.6 — BusDispatcher subscription pattern for P03 entry topics (kernel boot wiring)

- **Goal**: Ensure P03 receives trigger events through the standard bus subscription path.
- **Deliverables**:
  - `k0/contracts/pipelines/p03_consolidation.v1.yaml` `declared_topics` ordering ensures the scheduler’s synthetic trigger message uses the correct topic:
    - first topic = `p03.consolidation.triggered.v1`
  - Validate the topic list includes (optional) incremental hook:
    - `p02.write.complete.v1` (if/when P03_INCREMENTAL is enabled)
- **Acceptance Criteria**:
  - On kernel startup, `k0/kernel/app.py` subscribes the P03 runner to all declared topics.
  - When the scheduler fires, it constructs a synthetic `BusMessage` whose `topic` matches the runner’s first declared topic and successfully executes `runner.handle(...)`.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.6.1)
  - K0: `k0/kernel/app.py` (trigger executor), `k0/bus/core.py` (BusMessage)

---

#### Issue 8.3.7 — UnitOfWork pattern for atomic multi-table writes (stage_70)

- **Goal**: Ensure P03 commits truth updates atomically across all touched tables and outbox events.
- **Deliverables**:
  - `consolidation.memory_writer:v1` stage implementation uses UnitOfWork to:
    - write/update truth tables (episodes, semantic patterns, KG)
    - update `st_hipp_events.consolidation_status`
    - stage outbox events for R8 emission
- **Acceptance Criteria**:
  - All writes for a cycle are committed or rolled back as a single transaction.
  - Outbox entries are staged inside the same UnitOfWork so emission is durable and idempotent.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.7.1)
  - K0: `k0/uow/unit_of_work.py`

---

#### Issue 8.3.8 — Capability-gated storage access validation (least privilege enforcement)

- **Goal**: Ensure P03 can only read/write storage surfaces explicitly declared in its contracts.
- **Deliverables**:
  - `k0/contracts/pipelines/p03_consolidation.v1.yaml` declares the required storage capabilities (Appendix D.2.2).
  - P03 stage implementations rely on `context.syscalls` (not direct DB access) so capability checks are enforced.
- **Acceptance Criteria**:
  - Attempting a storage operation without the matching capability fails fast with a permissions error.
  - The granted capability set logged at pipeline boot matches the spec’s `required_capabilities` (no implicit grants).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.2.2; Appendix D.7.2)
  - K0: `k0/kernel/app.py` (granted_caps derived from spec), `k0/kernel/syscalls.py`

---

#### Issue 8.3.9 — Optimistic locking for concurrent updates (version-based)

- **Goal**: Prevent lost updates when multiple consolidation cycles or adjacent pipelines touch the same rows.
- **Deliverables**:
  - Implement (or reuse) version-based update patterns for key writes (at minimum `st_hipp_events` status updates), using PostgreSQL `RETURNING` semantics.
  - Configuration flag to enable/disable optimistic locking per dossier policy default.
- **Acceptance Criteria**:
  - On version mismatch, the update detects contention deterministically and routes to the pipeline’s retry/error path (no silent overwrite).
  - When enabled, optimistic locking is applied consistently to all “hot” update surfaces identified in the dossier.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.7.3; Appendix C.1.3)

---

#### Issue 8.3.10 — Module failure modes declaration in contracts (retry/DLQ readiness)

- **Goal**: Make failure handling explicit and machine-checkable via module contracts.
- **Deliverables**:
  - Each P03 module contract includes `failure_modes` entries for known errors, with policies aligned to Appendix D.10.1.
  - Failure mode shapes validate against the runtime schema.
- **Acceptance Criteria**:
  - Contracts validate; failure modes are present for critical modules (clustering, KG writes, memory_writer).
  - Failure mode codes are stable and referenced by tests/telemetry where appropriate.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix D.10.1)
  - K0: `k0/runtime/schemas.py` (`FailureMode`)

### Epic 8.4 — State machine + error recovery (Appendix G)

> **References**:
>
> - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G: “R0-R8 State Machine Specification”)
> - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.2–G.5: phase specs, transition rules, error recovery matrix, metrics)
> - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.8.2: ExponentialBackoffScheduler; Appendix C.8.3: WFQ)
> - K0: `k0/pipelines/protocol.py` (idempotency + status/processed tables expectations)
> - K0: `k0/outbox/scheduler.py` (retry scheduling primitives)
> - K0: `k0/storage/dlq.py` (DLQ persistence)
> - K0: `k0/qos/scheduler.py` (kernel QoS capacity tokens)

---

#### Issue 8.4.1 — Implement canonical R0–R8 phase state machine (INIT/PROC/SKIP/FAIL/DONE)

- **Goal**: Encode the dossier’s P03 consolidation execution semantics as an explicit, machine-checkable state machine for phases R0–R8.
- **Deliverables**:
  - Canonical phase identifiers (`R0`…`R8`) and state enum values exactly matching the dossier diagram/legend: `INIT`, `PROC`, `SKIP`, `FAIL`, `DONE`.
  - A transition table implementation aligned to Appendix G.3 (current_state + event → next_state with conditions).
  - Validation guardrails:
    - illegal transitions rejected deterministically (structured error)
    - transitions are traceable (log/trace includes from_state/to_state, cycle_id, phase)
- **Acceptance Criteria**:
  - The transition rules implemented are a direct encoding of Appendix G.3 (no extra states, no renamed states).
  - R0 supports `no_events → IDLE` without advancing the cycle.
  - `*.FAIL → dlq_recorded → IDLE` is supported as the terminal failure path.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.1, G.3)

---

#### Issue 8.4.2 — Per-phase idempotency key generation (cycle/batch/event/table-scoped)

- **Goal**: Ensure each phase is idempotent and independently retriable, using the dossier’s canonical idempotency key shapes.
- **Deliverables**:
  - Implement the idempotency key formats from Appendix G.2:
    - R0: `p03:cycle:{cycle_ulid}`
    - R1–R5: `p03:rN:{cycle_ulid}:{batch_hash}`
    - R6: `p03:r6:{cycle_ulid}:{event_id}`
    - R7: `p03:r7:{cycle_ulid}:{table}:{record_id}`
    - R8: `p03:r8:{cycle_ulid}:{topic}:{offset}`
  - Define and standardize `batch_hash` computation to match the dossier’s R0 batch model (batch_id derived from sorted event_ids, stable across retries).
  - Ensure idempotency keys are used consistently for:
    - phase re-entry (skip redoing work)
    - staged writes and outbox emission (no duplicates under retries)
- **Acceptance Criteria**:
  - For the same cycle inputs, idempotency keys remain stable across retries and restarts.
  - Idempotency keys are persisted and used to short-circuit duplicate processing as per K0 pipeline protocol expectations.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.2)
  - K0: `k0/pipelines/protocol.py` (idempotency pattern references)

---

#### Issue 8.4.3 — Per-phase timeout enforcement aligned to Appendix G

- **Goal**: Enforce hard per-phase time budgets so a consolidation cycle cannot stall indefinitely.
- **Deliverables**:
  - Timeout enforcement for each phase matching Appendix G.2:
    - R0: 30s
    - R1: 60s
    - R2: 120s
    - R3: 60s
    - R4: 90s
    - R5: 120s (configurable)
    - R6: 30s
    - R7: 60s
    - R8: 30s
  - A consistent timeout failure classification path that feeds the error recovery matrix (Issue 8.4.5).
- **Acceptance Criteria**:
  - A phase exceeding its time budget is transitioned through the correct error path (retry/skip/fail) based on Appendix G.4.
  - Observability includes per-phase duration metric emission even on timeout.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.2, G.4, G.5)

---

#### Issue 8.4.4 — Encode phase skip conditions (R2 single-event micro-episode; R5 backlog skip)

- **Goal**: Implement the dossier’s explicit conditional skip rules without altering the overall R0→R8 semantics.
- **Deliverables**:
  - R2 skip rule: `batch_size < 2` results in `R2.SKIP` and produces a deterministic micro-episode path (still feeding downstream phases).
  - R5 skip rule:
    - skip when `p03.phases.r5_dream.skip_on_backlog=true` AND pending backlog exceeds `p03.phases.r5_dream.backlog_threshold`.
    - R5 output records `skipped=true` and a structured `skip_reason`.
  - Transition rule enforcement consistent with Appendix G.3 (R4 → R6 when R5 is disabled or backlogged).
- **Acceptance Criteria**:
  - For `batch_size=1`, R2 is skipped and the cycle still completes (R8 emits completion) without errors.
  - When backlog threshold is exceeded, R5 is skipped and the cycle proceeds R6→R7→R8 without attempting counterfactual compute.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.2 R2/R5; Appendix G.3)

---

#### Issue 8.4.5 — Implement the Appendix G error recovery matrix (phase-specific retry/skip/fail)

- **Goal**: Make failure handling deterministic and phase-appropriate by implementing the dossier’s explicit error taxonomy and recovery actions.
- **Deliverables**:
  - Error type classification and mapping for the matrix in Appendix G.4, including:
    - PostgreSQL-specific notes (e.g., `LOCK_TIMEOUT` replacing SQLite `DB_LOCKED`)
    - external dependency failures (e.g., `P08_UNAVAILABLE`)
    - write-path failures (`TRANSACTION_FAIL`, `SERIALIZATION_FAIL`)
  - Recovery strategy execution (retry/skip/reduce-batch/quarantine/DLQ) per row in Appendix G.4.
  - DLQ recording path for terminal failure states (integrate with K0 DLQ persistence).
- **Acceptance Criteria**:
  - For each phase/error pair in Appendix G.4, the correct recovery action, retry budget, and backoff policy is applied.
  - Terminal failures are recorded to `st_dlq` with stable fingerprinting and sufficient metadata for replay.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.4)
  - K0: `k0/storage/dlq.py` (DLQ persistence)

---

#### Issue 8.4.6 — Exponential backoff scheduler for retries (base 100ms, cap 64s, jitter, 6 retries)

- **Goal**: Standardize retry timing so transient failures recover without thundering-herd behavior.
- **Deliverables**:
  - Implement the dossier’s `ExponentialBackoffScheduler` semantics:
    - delay formula: $\min(\text{cap}, \text{base} \cdot 2^{\text{attempt}})$ plus jitter
    - `BASE_DELAY_MS=100`, `MAX_DELAY_MS=64000`, `MAX_RETRIES=6`, `JITTER_FACTOR=0.2`
  - Ensure backoff scheduling updates `st_outbox.next_attempt_ts` when the failing unit is an outbox-backed operation.
  - Align implementation with K0’s existing retry scheduling primitives where applicable.
- **Acceptance Criteria**:
  - Delay schedule matches the dossier’s attempt table (100ms → 200ms → 400ms … capped).
  - Retries do not exceed the dossier maximum retry budget.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.8.2)
  - K0: `k0/outbox/scheduler.py` (RetryScheduler patterns)

---

#### Issue 8.4.7 — Weighted fair queuing (WFQ) for multi-tenant consolidation scheduling

- **Goal**: Prevent noisy tenants/spaces from monopolizing consolidation cycles, while preserving predictable progress for all tenants.
- **Deliverables**:
  - WFQ selection algorithm aligned to Appendix C.8.3:
    - per-queue virtual time tracking
    - select next item by minimum virtual finish time
    - weights default to 1.0 when not configured
  - Define queue identity and cost model consistent with P03 reality:
    - queue_id at minimum includes `tenant_id` and `space_id`
    - item_cost uses a measurable proxy (e.g., batch_size or estimated compute units)
  - Integrate WFQ selection with K0 QoS capacity tokens (acquire token after selection to respect kernel port budgets).
- **Acceptance Criteria**:
  - With configured weights, observed service share approximates the dossier’s example allocations under sustained load.
  - When a queue is empty, it does not block other queues.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix C.8.3)
  - K0: `k0/qos/scheduler.py` (capacity token acquisition)

---

#### Issue 8.4.8 — Phase metrics emission (duration + outcome counters) aligned to Appendix G.5

- **Goal**: Make the entire R0–R8 lifecycle observable and debuggable in production.
- **Deliverables**:
  - Emit the canonical metrics from Appendix G.5 with stable names:
    - e.g., `p03_r2_duration_ms`, `p03_r2_clusters`, `p03_r5_skipped`, `p03_r8_events_emitted`, etc.
  - Emit success/fail/skip counters per phase with a stable label set (phase + outcome at minimum).
  - Ensure metrics are emitted on both success and failure paths (including timeouts).
- **Acceptance Criteria**:
  - For each phase R0–R8, at least the metrics listed in Appendix G.5 are emitted in the correct phase boundary.
  - Metric names match the dossier exactly (no alternate naming).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.5)

---

#### Issue 8.4.9 — State persistence for checkpoint/resume (cycle-level + phase-level)

- **Goal**: Allow safe checkpointing and resumption after crash/restart without double-writing truth or double-emitting events.
- **Deliverables**:
  - Persist cycle/phase execution state sufficient to resume:
    - cycle_id and phase state
    - timing (started/updated)
    - last successfully completed phase
    - error_kind/error_msg for failures
  - Ensure persistence integrates with K0’s pipeline status patterns (st_pipeline_status) and idempotency records.
  - Resume behavior:
    - if a phase is `DONE`, do not re-run it
    - if a phase is `PROC` with exceeded timeout, route through error recovery
- **Acceptance Criteria**:
  - After a simulated crash mid-cycle, the next run resumes at the correct phase boundary without violating idempotency.
  - Resume does not cause duplicate outbox emissions (R8 idempotency enforced).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G.1–G.3)
  - K0: `k0/pipelines/protocol.py` (status/idempotency expectations)

---

#### Issue 8.4.10 — State machine integration tests (transition rules, skip rules, retry/backoff, resume)

- **Goal**: Provide deterministic tests that prevent regressions in phase semantics and recovery behavior.
- **Deliverables**:
  - Tests covering:
    - Appendix G.3 transitions (happy path + illegal transition rejection)
    - R2 single-event skip behavior
    - R5 backlog skip behavior
    - Exponential backoff schedule boundaries (base/cap/retries)
    - checkpoint/resume correctness (no duplicate writes/events)
- **Acceptance Criteria**:
  - Tests are deterministic and do not depend on external services.
  - Contract-breaking changes to Appendix G semantics fail tests.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix G; Appendix C.8.2–C.8.3)

### Epic 8.5 — UltraBERT integration validation

#### Issue 8.5.1 — Validate UltraBERT version + canonical model_id alignment (dossier vs repo)

- **Goal**: Ensure the UltraBERT version/capability set assumed by P03 (Appendix H) matches what K0 actually runs today in P02, and define a single canonical `model_id` strategy for stored vectors and downstream consumers.
- **Deliverables**:
  - Produce a version/reference inventory with an explicit “source of truth” decision:
    - Dossier target: UltraBERT v2.2.1 (Appendix H)
    - K0 config: `k0/config/models.yaml`
    - Packaged wheels: `wheels/familyos_ultrabert-*.whl`
    - P02 inline embedding config: `k0/contracts/pipelines/p02_write.v1.yaml` (stage_22 `model_id`)
    - Extract output model_id: `k0/modules/embedding/extract_from_cache.py`
    - Storage default model_id: `k0/db/alembic/versions/0025_st_vec.py` (st_vec default)
  - Create an Appendix-H capability verification matrix and validate it against the real K0 integration surface:
    - map each Appendix-H capability to the K0 callable used (`k0/runtime/ultrabert_adapter.py`) and the phase(s) that depend on it (R0/R1/R2/R4/R7)
    - explicitly mark any capability that is not implemented in K0 as a decision/drift item (do not silently assume it exists).
  - Define the compatibility policy P03 will enforce when consuming vectors:
    - required `vector_dim == 768`
    - allowed `model_id` set (explicit allowlist)
    - behavior on mismatch (skip, degrade, or schedule recompute via embedding maintenance).
- **Acceptance Criteria**:
  - A single canonical `model_id` convention is selected and documented in the ticket (e.g., `ultrabert_v2.2.1`), with an explicit upgrade/migration path if the repo is behind Appendix H.
  - P03 consumption rules are unambiguous: it either accepts legacy `model_id`s or forces recompute, but does not silently mix incompatible embedding spaces.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix H)
  - P02: `k0/contracts/pipelines/p02_write.v1.yaml` (stage_22)
  - K0: `k0/config/models.yaml`, `wheels/`, `k0/db/alembic/versions/0025_st_vec.py`

---

#### Issue 8.5.2 — Define and test “P03 consumes P02 precomputed UltraBERT signals” (no duplicate inference)

- **Goal**: Make “do not duplicate P02 UltraBERT work” an enforceable contract: P03 must consume embeddings and affect/safety outputs already produced during ingestion, only calling UltraBERT when the required signal is missing.
- **Deliverables**:
  - Define an explicit “P02 → P03 precomputed outputs map” covering at minimum:
    - embeddings: `st_vec.vector` + `st_vec.vector_dim` + `st_vec.model_id` (joined via `st_hipp_events.embedding_id`)
    - affect/safety: outputs produced by `affect.analyze:v1` and written into `st_hipp_events` by P02
    - ingress/activity provenance: outputs produced by `context.ingress_classify:v1` and written into `st_hipp_events` by P02
  - Add a P03 runtime guard + metric:
    - if `st_vec.status in {READY, INDEXED}` and dims match, P03 MUST NOT call `ultrabert_embed`
    - emit a counter for “skipped inference because precomputed signal exists”.
  - Integration test that runs a P03 cycle on P02-produced rows and asserts:
    - embeddings are read from storage, not recomputed
    - any UltraBERT invocation is attributable to missing/PENDING data (and is observable).
- **Acceptance Criteria**:
  - For a batch where P02 has written `st_vec` rows (READY/INDEXED), P03 completes its embedding-dependent phases without calling the UltraBERT embedding path.
- **References**:
  - P02 contract: `k0/contracts/pipelines/p02_write.v1.yaml` (stage_22, stage_70)
  - K0 modules: `k0/modules/embedding/extract_from_cache.py`, `k0/modules/core/hipp_events_writer.py`
  - K0 syscalls: `k0/kernel/syscalls.py` (`ultrabert_embed`, `vec_query`, `vec_write`)

---

#### Issue 8.5.3 — R0 pre-filter validation: safety + affect + ingress signals are sourced from P02

- **Goal**: Validate that P03 R0 pre-filter behavior uses the existing P02-enriched safety and ingress signals (and does not re-run UltraBERT).
- **Deliverables**:
  - Enumerate the exact fields P03 will consume for prefiltering (e.g., `privacy_band`, `affect_band`, safety signals, ingress/activity fields), and map each field to its P02 producer module.
  - Confirm P03’s prefilter conditions align with dossier semantics for R0 and are expressible using P02 outputs.
  - Tests for representative cases:
    - RED-band/safety-flagged event is gated/handled per R0 rules
    - low-risk events pass R0 without any UltraBERT calls.
- **Acceptance Criteria**:
  - R0 classification is fully satisfied by P02-written fields for the common path.
  - Any UltraBERT calls from R0 are treated as a bug unless explicitly justified as “missing signal repair”.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix H; R0 usage)
  - P02: `k0/contracts/pipelines/p02_write.v1.yaml` (stage_30_affect_analyze, stage_41_ingress_classify)
  - K0 modules: `k0/modules/affect/analyze.py`, `k0/modules/context/ingress_classify.py`

---

#### Issue 8.5.4 — R1 integration validation: embeddings + sentiment/emotions consumption correctness

- **Goal**: Ensure P03 R1 consumes the same UltraBERT-derived signals P02 computed (embedding, sentiment/emotions outputs) with correct schema, types, and defaulting behavior.
- **Deliverables**:
  - Define the required R1 input set and validate it exists in P02 outputs for typical events.
  - Confirm any model-derived values (e.g., valence/arousal/emotion tags) are used without recomputation.
  - Add tests that verify:
    - embeddings are decoded correctly (dim and numeric stability)
    - emotion/sentiment fields are present and in expected ranges.
- **Acceptance Criteria**:
  - P03 R1 produces deterministic scores when given the same P02-produced inputs.
  - R1 never triggers UltraBERT inference in the normal path.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix H; R1 usage)
  - P02: `k0/contracts/pipelines/p02_write.v1.yaml` (stage_22_embedding_extract, stage_30_affect_analyze)
  - K0: `k0/modules/embedding/extract_from_cache.py`, `k0/modules/affect/analyze.py`

---

#### Issue 8.5.5 — R2 clustering validation: DBSCAN consumes stored 768-dim vectors (byte packing + metric)

- **Goal**: Confirm P03 R2 clustering uses the vectors written by P02 into `st_vec` (packed float32 blob) correctly, including dimensionality, endianness, and the chosen distance metric.
- **Deliverables**:
  - Confirm the storage format and decode path are consistent with existing K0 embedding utilities:
    - `st_vec.vector` length is exactly 3072 bytes for 768×float32
    - decoding uses the same packing contract as P02/P08 (`struct.unpack("768f", ...)`).
  - Decide and document the distance metric used by DBSCAN (cosine vs L2) and whether vectors must be normalized prior to clustering.
  - Tests:
    - pack/unpack roundtrip preserves vector values within float32 tolerance
    - clustering uses decoded embeddings without re-embedding.
- **Acceptance Criteria**:
  - P03 can cluster a batch of P02-produced events using stored vectors with no UltraBERT calls.
  - Dimensional mismatches or malformed vectors are handled explicitly (skip/degrade) and are observable.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix H; R2 usage)
  - Storage: `k0/db/alembic/versions/0025_st_vec.py`
  - P08: `k0/modules/embedding/faiss_indexer.py` (vector decode contract)

---

#### Issue 8.5.6 — R4 entity/relation integration strategy: reuse P02 outputs; only enrich when missing

- **Goal**: Validate what entity/relation signals P02 already produces (semantic projection), and ensure P03 only invokes UltraBERT NER/relation capabilities when required by dossier semantics and not already available.
- **Deliverables**:
  - Inventory P02 semantic projection outputs relevant to R4 and where they are stored (st_hipp_events fields and/or KG tables).
  - Define R4 enrichment policy:
    - preferred: consume existing P02 entities/relations
    - fallback: run UltraBERT NER/relation only for missing/low-confidence cases.
  - Add tests to validate “reuse-first” behavior.
- **Acceptance Criteria**:
  - P03 does not duplicate P02 entity extraction on the normal path.
  - Any enrichment calls are measurable and gated by explicit conditions.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix H; R4 usage)
  - P02: `k0/contracts/pipelines/p02_write.v1.yaml` (stage_20_ca1_semantic_project)

---

#### Issue 8.5.7 — R7 NLI contradiction detection integration: backend selection + warmup + budgets

- **Goal**: Validate and integrate UltraBERT NLI usage for R7 contradiction detection per Appendix H, with explicit backend selection and warmup behavior that fits K0 runtime constraints.
- **Deliverables**:
  - Confirm which NLI capability API is used in K0 and how it is configured (backend, INT8 ONNX defaults, warmup).
  - Define how R7 invokes NLI (pairwise comparisons, batch strategy, caching opportunities) to meet throughput constraints.
  - Add a test/benchmark case that measures the steady-state vs first-call behavior.
- **Acceptance Criteria**:
  - R7 NLI integration produces stable contradiction outputs and remains within the dossier’s performance envelope when warm.
  - The first-call penalty is bounded and/or amortized by warmup.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix H; R7 usage)
  - K0: `k0/runtime/ultrabert_adapter.py`, `k0/config/models.yaml`

---

#### Issue 8.5.8 — UltraBERT warmup + backend configuration validation (ONNX INT8 production default)

- **Goal**: Validate that K0’s runtime configuration surfaces the dossier-required backend selection and supports warmup so P03 does not take a catastrophic first-call latency hit.
- **Deliverables**:
  - Verify and document (in-ticket) the effective warmup/backends knobs:
    - config in `k0/config/models.yaml`
    - env var flags consumed by `k0/runtime/ultrabert_adapter.py`
  - Add a startup validation check (or smoke test) that asserts UltraBERT backend matches expectations in production configuration.
- **Acceptance Criteria**:
  - Running the kernel with “prod config” results in the intended backend (ONNX INT8) and warmup mode.
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix H)
  - K0: `k0/config/models.yaml`, `k0/runtime/ultrabert_adapter.py`

---

#### Issue 8.5.9 — Performance validation: first-call latency + throughput targets for UltraBERT-dependent phases

- **Goal**: Validate UltraBERT performance targets required by Appendix H in the K0 runtime context (especially for any P03 phases that must invoke UltraBERT directly, e.g., NLI).
- **Deliverables**:
  - Add a benchmark harness (or reusable test runner) to measure:
    - first-call latency (cold start) vs warmed latency
    - throughput under batch inputs (samples/sec)
  - Record and attach benchmark results to the ticket, with environment notes (CPU vs GPU, backend, model version).
- **Acceptance Criteria**:
  - Observed first-call and steady-state performance are within the dossier’s stated targets (or deviations are explained with an explicit mitigation plan).
- **References**:
  - Dossier: `docs/pipelines/P03_consolidation_dossier_v2.md` (Appendix H)
  - P02: `k0/contracts/pipelines/p02_write.v1.yaml` (stage ordering/caching assumptions)

---

#### Issue 8.5.10 — Vector storage approach validation: st_vec blob + FAISS vs pgvector diagram claims

- **Goal**: Eliminate ambiguity about how vectors are stored and queried so P03 uses the real K0 execution path (and does not build against a diagram-only architecture).
- **Deliverables**:
  - Confirm the “as-implemented” storage/query approach for embeddings:
    - storage table schema and storage type (`st_vec.vector` packed float32 blob): `k0/db/alembic/versions/0025_st_vec.py`
    - FAISS indexing contract and decode format: `k0/modules/embedding/faiss_indexer.py`
    - diagram claims around `st_vec (pgvector)`: `architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd`
    - any pgvector search client code paths and whether they are in use: `k0/drivers/pgvector.py`
  - Produce a clear compatibility statement for P03:
    - “P03 reads packed vectors from st_vec; similarity comes from FAISS index maintained by P08” (or the decided alternative).
- **Acceptance Criteria**:
  - P03 implementation assumptions match the active storage/query path in K0.
  - Any drift between diagram and runtime is captured as an explicit governance/drift item (not left implicit).
- **References**:
  - Diagram: `architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd`
  - Storage: `k0/db/alembic/versions/0025_st_vec.py`
  - Embedding modules: `k0/modules/embedding/`
  - Vector search drivers: `k0/drivers/pgvector.py`

---

## Appendix — Future Research Tracking (from Dossier Appendix I)

> These are **not** implementation issues. They track research/design proposals for future phases.

### Research Area: Closed-Loop Feedback System

- [RESEARCH] Adaptive thresholds via Thompson Sampling (per-entity/space)
- [RESEARCH] Per-entity decay calibration (λ learned from re-query patterns)
- [RESEARCH] Query regret tracking (prune-then-query detection)
- [RESEARCH] Learnable importance weights (gradient descent on access correlation)
- [RESEARCH] Implicit feedback collection (st_implicit_feedback schema design)
- [RESEARCH] Bayesian prior tuning (α+β effective samples analysis)
