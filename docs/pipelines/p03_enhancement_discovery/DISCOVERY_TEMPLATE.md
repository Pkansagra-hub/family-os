# P{XX} Phase Discovery & Enhancement Plan

> **Standard template for phase discovery.** Copy this file, replace `{XX}` with your pipeline ID,
> and fill every section. No section may be deleted -- mark `N/A` with justification if not applicable.
>
> **For LLM agents**: Every table below includes a COLUMN GUIDE explaining what goes in each column
> and an EXAMPLE row showing a correctly filled entry. Follow the example exactly. Do not invent
> categories, statuses, or formats not shown in the guide. When a column says "pick one of X / Y / Z",
> use ONLY those literal values.

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P{XX} |
| Module Scope | _{list every module in scope}_ |
| Discovery Date | YYYY-MM-DD |
| Milestone Target | M{N} |
| Governing ADRs | ADR-KXXX, ADR-KXXX |
| Related Dossier | `docs/pipelines/PXX_*_dossier.md` |
| Author | _{name or agent id}_ |
| Status | DRAFT / IN-REVIEW / ACCEPTED |

> **COLUMN GUIDE**:
>
> - **Pipeline ID**: The pipeline identifier, e.g. `P03`, `P08`. One pipeline per discovery doc.
> - **Module Scope**: Comma-separated list of every K0 module this discovery covers. Use dotted module paths.
> - **Discovery Date**: ISO-8601 date the discovery was started.
> - **Milestone Target**: The milestone this discovery feeds into, e.g. `M5`.
> - **Governing ADRs**: Every ADR that constrains this work. Use ADR IDs like `ADR-K003`.
> - **Related Dossier**: Relative path to the pipeline dossier file.
> - **Author**: GitHub username or agent identifier (e.g. `copilot-gpt4`).
> - **Status**: Pick exactly one of: `DRAFT`, `IN-REVIEW`, `ACCEPTED`.
>
> **EXAMPLE**:
>
> | Field | Value |
> | ----- | ----- |
> | Pipeline ID | P03 |
> | Module Scope | consolidation.scoring, consolidation.ranker, consolidation.merger |
> | Discovery Date | 2026-03-01 |
> | Milestone Target | M5 |
> | Governing ADRs | ADR-K001, ADR-K003 |
> | Related Dossier | `docs/pipelines/P03_consolidation_dossier_v2.md` |
> | Author | copilot-claude |
> | Status | DRAFT |

---

## 1. Current State Audit

### 1.1 Code Inventory

| # | File (relative path) | Lines | Status | Last Modified | Purpose |
| - | -------------------- | ----- | ------ | ------------- | ------- |
| 1 | | | NEW / MOD / LEGACY / DEPRECATED | | |

> **COLUMN GUIDE**:
>
> - **#**: Sequential row number, starting at 1.
> - **File**: Workspace-relative path, e.g. `k0/modules/consolidation/scoring.py`. No absolute paths.
> - **Lines**: Integer line count from `wc -l` or editor. Must be current, not guessed.
> - **Status**: Pick exactly one of: `NEW` (created this milestone), `MOD` (modified this milestone), `LEGACY` (untouched inherited code), `DEPRECATED` (marked for removal).
> - **Last Modified**: ISO-8601 date or milestone ID when last changed, e.g. `2026-02-15` or `M4`.
> - **Purpose**: One sentence. What this file does. Start with a verb: "Implements...", "Defines...", "Tests...".
>
> **EXAMPLE**:
>
> | # | File (relative path) | Lines | Status | Purpose | Last Modified |
> | - | -------------------- | ----- | ------ | ------- | ------------- |
> | 1 | k0/modules/embedding/backfill.py | 189 | MOD | Implements M25 v2.0 backfill: PENDING->READY vector conversion via pgvector | M4 |
> | 2 | k0/pipelines/p08/runner.py | 227 | NEW | 3-stage sequential P08 pipeline runner with fault isolation | M4 |
> | 3 | k0/modules/embedding/faiss_indexer.py | 0 | DEPRECATED | Deleted -- FAISS indexing replaced by pgvector native | M4 |

### 1.2 Contract Inventory

| # | Contract File | Version | Status | Lines | Governs (module / pipeline / schema) |
| - | ------------- | ------- | ------ | ----- | ------------------------------------ |
| 1 | | | active / deprecated | | |

> **COLUMN GUIDE**:
>
> - **Contract File**: Relative path to the YAML/dataclass/Pydantic contract file.
> - **Version**: Semantic version from the contract header, e.g. `v2`, `v1.3`.
> - **Status**: Pick one of: `active`, `deprecated`. If deprecated, the file must have a `deprecated: true` header.
> - **Lines**: Integer line count.
> - **Governs**: What this contract controls. Format: `module:<name>`, `pipeline:<name>`, or `schema:<name>`.
>
> **EXAMPLE**:
>
> | # | Contract File | Version | Status | Lines | Governs |
> | - | ------------- | ------- | ------ | ----- | ------- |
> | 1 | k0/contracts/modules/embedding.backfill.v2.yaml | v2 | active | 193 | module:embedding.backfill |
> | 2 | k0/contracts/modules/embedding.backfill.v1.yaml | v1 | deprecated | 150 | module:embedding.backfill |
> | 3 | k0/contracts/schemas/st_vec_v2.columns.yaml | v2 | active | 212 | schema:st_vec |

### 1.3 Config Inventory

#### 1.3.1 YAML Config Keys

| Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
| ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
| | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Config File**: Relative path to the YAML config, e.g. `k0/config/embeddings.yml`.
> - **Version**: Version from the YAML header, e.g. `v2.0`.
> - **Key (dot-path)**: Full dotted path to the key, e.g. `backends.ultrabert.dimension`. Walk the YAML tree.
> - **Value**: Current value in the config file. Quote strings, bare numbers/booleans.
> - **Type**: Python type: `str`, `int`, `float`, `bool`, `list[str]`, `dict`, etc.
> - **Default**: Value used if key is absent. Write `NONE` if no default (crash on missing).
> - **Required**: `yes` or `no`. `yes` means the system fails to start without it.
> - **Notes**: Why this value was chosen, or what changes it controls.
>
> **EXAMPLE**:
>
> | Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
> | ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
> | k0/config/embeddings.yml | v2.0 | backends.ultrabert.dimension | 768 | int | NONE | yes | Must match VECTOR(768) in st_vec |
> | k0/config/embeddings.yml | v2.0 | worker.enabled | false | bool | false | no | Disabled because P02 does inline embedding |

#### 1.3.2 Environment Variables

| Variable | Type | Default | Required | Used By | Purpose |
| -------- | ---- | ------- | -------- | ------- | ------- |
| | | | | | |

> **COLUMN GUIDE**:
>
> - **Variable**: Exact env var name in UPPER_SNAKE_CASE, e.g. `K0_DB_URL`.
> - **Type**: Expected type after parsing: `str`, `int`, `bool`, `url`, `path`.
> - **Default**: Value if unset. `NONE` = required, no fallback.
> - **Required**: `yes` or `no`.
> - **Used By**: Module or file that reads this variable.
> - **Purpose**: One sentence describing what it controls.
>
> **EXAMPLE**:
>
> | Variable | Type | Default | Required | Used By | Purpose |
> | -------- | ---- | ------- | -------- | ------- | ------- |
> | K0_DB_URL | url | NONE | yes | k0/db/engine.py | PostgreSQL connection string with pgvector extension |
> | K0_EMBEDDING_BATCH_SIZE | int | 500 | no | k0/modules/embedding/backfill.py | Max vectors per backfill batch |

#### 1.3.3 Feature Flags

| Flag Name | Source (env / config / DB) | Default | Scope (global / tenant / space) | Controls | Rollback Behavior |
| --------- | ------------------------- | ------- | ------------------------------- | -------- | ----------------- |
| | | | | | |

> **COLUMN GUIDE**:
>
> - **Flag Name**: Exact flag identifier, e.g. `ENABLE_P08_INTEGRITY_CHECK`.
> - **Source**: Where the flag is read from. Pick one of: `env`, `config`, `DB`.
> - **Default**: Value when flag is absent: `true`, `false`, or a specific value.
> - **Scope**: What level the flag operates at. Pick one of: `global`, `tenant`, `space`.
> - **Controls**: What behavior changes when the flag is toggled. One sentence.
> - **Rollback Behavior**: What happens if you flip the flag back. e.g. "Safe -- no data loss, next run skips stage".
>
> **EXAMPLE**:
>
> | Flag Name | Source | Default | Scope | Controls | Rollback Behavior |
> | --------- | ------ | ------- | ----- | -------- | ----------------- |
> | ENABLE_P08_INTEGRITY_CHECK | config | true | global | Enables/disables stage_30 integrity check in P08 runner | Safe -- next P08 run skips integrity, no data loss |

#### 1.3.4 Constants & Magic Numbers

| Constant | Location (file:line) | Value | Type | Rationale | Externalize? |
| -------- | -------------------- | ----- | ---- | --------- | ------------ |
| | | | | | |

> **COLUMN GUIDE**:
>
> - **Constant**: Name as it appears in code, e.g. `VECTOR_DIM`, `MAX_BATCH_SIZE`.
> - **Location**: File and line number, e.g. `k0/modules/embedding/backfill.py:14`.
> - **Value**: Current hardcoded value.
> - **Type**: Python type.
> - **Rationale**: Why this value was chosen. Not "because it works" -- give the real reason.
> - **Externalize?**: `yes` (should be moved to config), `no` (safe to keep hardcoded), `maybe` (needs discussion).
>
> **EXAMPLE**:
>
> | Constant | Location | Value | Type | Rationale | Externalize? |
> | -------- | -------- | ----- | ---- | --------- | ------------ |
> | VECTOR_DIM | k0/modules/embedding/backfill.py:14 | 768 | int | UltraBERT v2.1.0 output dimension, validated by vec_write | no -- tied to model, changing requires migration |
> | ORPHAN_BATCH_SIZE | k0/modules/embedding/cleanup.py:11 | 500 | int | Empirical sweet spot: avoids long locks, clears typical orphan backlogs in 1-3 passes | yes |

### 1.4 Migration Inventory

| # | Migration File | Table(s) | Operation (CREATE / ALTER / DROP / DATA) | Columns Affected | Reversible? |
| - | -------------- | -------- | ---------------------------------------- | ---------------- | ----------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Migration File**: Relative path, e.g. `k0/db/alembic/versions/0071_st_vec_pgvector_native.py`.
> - **Table(s)**: Comma-separated table names affected.
> - **Operation**: Pick one or more of: `CREATE`, `ALTER`, `DROP`, `DATA` (data migration / backfill).
> - **Columns Affected**: List columns added, removed, or modified. Format: `+column` (added), `-column` (removed), `~column` (modified).
> - **Reversible?**: `yes` (has working downgrade), `no` (destructive, one-way), `partial` (downgrade exists but loses data).
>
> **EXAMPLE**:
>
> | # | Migration File | Table(s) | Operation | Columns Affected | Reversible? |
> | - | -------------- | -------- | --------- | ---------------- | ----------- |
> | 1 | k0/db/alembic/versions/0071_st_vec_pgvector_native.py | st_vec | DROP, CREATE | +vector VECTOR(768), +vector_dim, +model_id, +status, +cognitive_trace_id, +created_at, +updated_at, -faiss_id, -indexed_at | no -- DROP destroys all rows |

---

## 2. API Surface Map

### 2.1 Public Functions & Methods

| # | Module | Function / Method | Signature | Return Type | Consumers (who calls it) | Idempotent? | Notes |
| - | ------ | ----------------- | --------- | ----------- | ------------------------ | ----------- | ----- |
| 1 | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Module**: Dotted Python module path, e.g. `k0.modules.embedding.backfill`.
> - **Function / Method**: Bare name, e.g. `run`, `get_metrics`, `P08Runner.handle`.
> - **Signature**: Full parameter list with types, e.g. `(message: dict, context: Context, envelope: Envelope)`. Include defaults.
> - **Return Type**: Python return type, e.g. `dict[str, Any]`, `None`, `list[float]`.
> - **Consumers**: Who calls this. Use module paths or pipeline IDs, e.g. `P08 stage_10`, `P02 inline`.
> - **Idempotent?**: `yes` (calling twice with same input = same result, no side effects), `no` (has side effects or non-deterministic), `conditional` (idempotent if precondition met -- explain in Notes).
> - **Notes**: Constraints, version info, or gotchas. Keep to one sentence.
>
> **EXAMPLE**:
>
> | # | Module | Function / Method | Signature | Return Type | Consumers | Idempotent? | Notes |
> | - | ------ | ----------------- | --------- | ----------- | --------- | ----------- | ----- |
> | 1 | k0.modules.embedding.backfill | run | (message: dict, context: Context, envelope: Envelope) | dict[str, Any] | P08 stage_10_backfill | conditional | Idempotent if vector already READY (upsert) |
> | 2 | k0.modules.embedding.backfill | get_metrics | () | dict[str, int] | P08Runner, tests | yes | Returns counter snapshot, no side effects |

### 2.2 Syscalls Used / Required

| # | Syscall | Signature | Status | Used By | SQL Pattern (if DB) | Notes |
| - | ------- | --------- | ------ | ------- | ------------------- | ----- |
| 1 | | | exists / needed / modify | | | |

> **COLUMN GUIDE**:
>
> - **Syscall**: Method name on the Syscalls class, e.g. `vec_write`, `hipp_events_missing_vectors`.
> - **Signature**: Full parameter list with types. Copy from `k0/kernel/syscalls.py`.
> - **Status**: Pick one of: `exists` (already implemented), `needed` (must be created), `modify` (exists but needs changes).
> - **Used By**: Module(s) that call this syscall.
> - **SQL Pattern**: The core SQL operation, e.g. `INSERT INTO st_vec ... ON CONFLICT DO UPDATE`, `SELECT COUNT(*) FROM st_vec WHERE ...`. Write `N/A` if not a DB syscall.
> - **Notes**: Version info, performance concerns, or constraints.
>
> **EXAMPLE**:
>
> | # | Syscall | Signature | Status | Used By | SQL Pattern | Notes |
> | - | ------- | --------- | ------ | ------- | ----------- | ----- |
> | 1 | vec_write | (embedding_id, event_id, tenant_id, space_id, vector, vector_dim, model_id, status, cognitive_trace_id) -> dict | exists | embedding.extract_from_cache, embedding.backfill | INSERT INTO st_vec (...) VALUES (...) ON CONFLICT (embedding_id) DO UPDATE | Modified in M4: vector is list[float] with ::vector cast |
> | 2 | vec_orphan_count | (tenant_id, space_id) -> dict | exists | embedding.cleanup | SELECT COUNT(*) FROM st_vec v WHERE NOT EXISTS (SELECT 1 FROM st_hipp_events h WHERE h.event_id = v.event_id) | New in M4 |

### 2.3 Internal Helpers (non-public but critical path)

| # | Module | Function | Signature | Called By | Purpose | Risk if Changed |
| - | ------ | -------- | --------- | --------- | ------- | --------------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Module**: Dotted path to the module containing the helper.
> - **Function**: Function name. These are NOT exported in `__init__.py` but are on the critical path.
> - **Signature**: Full parameter list with types.
> - **Called By**: Which public function(s) depend on this helper.
> - **Purpose**: What it does. One sentence starting with a verb.
> - **Risk if Changed**: What breaks if someone modifies this. e.g. "Breaks all P08 stages -- shared by backfill, cleanup, integrity".
>
> **EXAMPLE**:
>
> | # | Module | Function | Signature | Called By | Purpose | Risk if Changed |
> | - | ------ | -------- | --------- | --------- | ------- | --------------- |
> | 1 | k0.modules.embedding.backfill | _validate_dimension | (vector: list[float], expected: int) -> None | backfill.run | Asserts vector length matches expected_dim, raises ValueError | Breaks backfill silently if removed -- bad vectors would be written |

### 2.4 Classes & Dataclasses

| # | Module | Class | Base Class / Protocol | Key Attributes | Key Methods | Consumers |
| - | ------ | ----- | --------------------- | -------------- | ----------- | --------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Module**: Dotted module path.
> - **Class**: Class name exactly as defined.
> - **Base Class / Protocol**: What it inherits from or implements, e.g. `PipelineProtocol`, `dataclass`, `BaseModel`.
> - **Key Attributes**: Comma-separated list of important attributes with types, e.g. `pipeline_id: str, stages: list[Stage]`.
> - **Key Methods**: Comma-separated list of public methods, e.g. `handle(), on_startup(), on_shutdown()`.
> - **Consumers**: Who instantiates or uses this class.
>
> **EXAMPLE**:
>
> | # | Module | Class | Base Class / Protocol | Key Attributes | Key Methods | Consumers |
> | - | ------ | ----- | --------------------- | -------------- | ----------- | --------- |
> | 1 | k0.pipelines.p08.runner | P08Runner | PipelineProtocol | pipeline_id: str, spec: PipelineSpec, registry: ModuleRegistry | handle(message), on_startup(ctx), on_shutdown() | k0.scheduler, tests |
> | 2 | k0.modules.embedding.backfill | BackfillMetrics | dataclass | processed: int, skipped: int, errors: int | N/A (data only) | backfill.get_metrics() |

---

## 3. Algorithm Inventory

### 3.1 Current Algorithms

| # | Algorithm Name | Location (file:line) | Category | Input Type(s) | Input Constraints | Output Type(s) | Output Guarantees | Time Complexity | Space Complexity | Deterministic? | Stateful? | State Location | Parameters / Thresholds | Edge Cases Handled | Failure Mode | Fallback Behavior | Dependencies (libs / syscalls) | Description |
| - | -------------- | -------------------- | -------- | ------------- | ----------------- | -------------- | ----------------- | --------------- | ---------------- | -------------- | --------- | -------------- | ----------------------- | ------------------ | ------------ | ----------------- | ------------------------------ | ----------- |
| 1 | | | | | | | | O(?) | O(?) | yes / no | yes / no | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Algorithm Name**: Descriptive name, e.g. `orphan_detection`, `integrity_health_classification`. Not the function name -- the algorithm's name.
> - **Location**: `file_path:start_line`, e.g. `k0/modules/embedding/cleanup.py:45`.
> - **Category**: Pick one of: `scoring`, `ranking`, `filtering`, `aggregation`, `transformation`, `search`, `classification`, `validation`, `scheduling`, `routing`, `merging`, `splitting`, `other`.
> - **Input Type(s)**: Python types consumed, e.g. `list[dict], str, int`.
> - **Input Constraints**: What must be true about input, e.g. `vectors must be 768-dim`, `event_ids must be non-empty`, `batch_size > 0`.
> - **Output Type(s)**: Python types produced.
> - **Output Guarantees**: What is always true about output, e.g. `score in [0.0, 1.0]`, `result list is sorted descending`, `count >= 0`.
> - **Time Complexity**: Big-O notation, e.g. `O(n)`, `O(n log n)`, `O(n * m)`. State what n/m represent.
> - **Space Complexity**: Big-O notation for additional memory.
> - **Deterministic?**: `yes` (same input always same output) or `no` (uses randomness, time, external state).
> - **Stateful?**: `yes` (maintains state between calls) or `no` (pure function).
> - **State Location**: If stateful, where state lives: `module-level dict`, `DB table`, `in-memory counter`, etc. `N/A` if stateless.
> - **Parameters / Thresholds**: Every tunable value the algorithm uses, e.g. `batch_size=500, threshold=100, dry_run=False`.
> - **Edge Cases Handled**: Comma-separated list of edge cases the algorithm explicitly handles, e.g. `empty input, zero vectors, duplicate event_ids`.
> - **Failure Mode**: What happens when it fails: `raises ValueError`, `returns empty dict`, `logs and skips`, `aborts pipeline`.
> - **Fallback Behavior**: What happens when the algorithm cannot produce a result: `returns default score 0.0`, `skips record`, `N/A`.
> - **Dependencies**: Libraries or syscalls the algorithm depends on, e.g. `pgvector, vec_write syscall`.
> - **Description**: One sentence describing what the algorithm does. Start with a verb.
>
> **EXAMPLE**:
>
> | # | Algorithm Name | Location | Category | Input Type(s) | Input Constraints | Output Type(s) | Output Guarantees | Time | Space | Det? | Stateful? | State Location | Parameters | Edge Cases | Failure Mode | Fallback | Dependencies | Description |
> | - | -------------- | -------- | -------- | ------------- | ----------------- | -------------- | ----------------- | ---- | ----- | ---- | --------- | -------------- | ---------- | ----------- | ------------ | -------- | ------------ | ----------- |
> | 1 | orphan_detection | k0/modules/embedding/cleanup.py:45 | filtering | tenant_id: str, space_id: str | tenant_id and space_id must be non-empty | dict{orphan_count: int, deleted: int} | deleted <= orphan_count, deleted <= limit | O(n) where n = orphan count | O(1) | yes | no | N/A | batch_size=500, dry_run=False, limit=batch_size | zero orphans returns {0, 0}, missing table raises | raises RuntimeError on DB failure | returns {0, 0} if dry_run=True | vec_orphan_count, vec_delete_orphans syscalls | Finds st_vec rows with no matching st_hipp_events row and deletes them in batches |
> | 2 | health_classification | k0/modules/embedding/integrity_check.py:78 | classification | check_results: dict[str, int] | all 4 checks must be present | dict{health: str, checks: dict} | health is one of HEALTHY/DEGRADED/CRITICAL | O(1) | O(1) | yes | no | N/A | threshold=100 | all checks pass = HEALTHY, any > threshold = CRITICAL | raises ValueError if check missing | N/A -- always classifies | N/A | Classifies embedding health based on 4 integrity checks against threshold |

### 3.2 Algorithm Gaps

| # | Gap Description | Expected Behavior | Current Behavior | Severity (P0-P3) | Proposed Approach | Estimated Complexity |
| - | --------------- | ----------------- | ---------------- | ----------------- | ----------------- | -------------------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Gap Description**: What algorithm is missing or broken. One sentence.
> - **Expected Behavior**: What should happen. Be specific with inputs/outputs.
> - **Current Behavior**: What actually happens now: `not implemented`, `returns wrong result`, `crashes`.
> - **Severity**: `P0` = blocks pipeline, `P1` = degrades quality, `P2` = minor issue, `P3` = nice-to-have.
> - **Proposed Approach**: Brief description of how to fix it. One sentence.
> - **Estimated Complexity**: `trivial` (< 50 lines), `small` (50-200 lines), `medium` (200-500 lines), `large` (500+ lines).
>
> **EXAMPLE**:
>
> | # | Gap Description | Expected Behavior | Current Behavior | Severity | Proposed Approach | Estimated Complexity |
> | - | --------------- | ----------------- | ---------------- | -------- | ----------------- | -------------------- |
> | 1 | No vector similarity search API | Given a query vector, return top-k similar vectors from st_vec | HNSW index exists but no query function | P2 | Add vec_search syscall using pgvector <=> operator | small |

---

## 4. Data Flow & I/O Map

### 4.1 Pipeline Stage Map

| Stage Order | Stage ID | Module | Input Event / Topic | Output Event / Topic | Side Effects (DB writes, metrics, logs) | Error Topic | Retry Policy |
| ----------- | -------- | ------ | ------------------- | -------------------- | --------------------------------------- | ----------- | ------------ |
| 1 | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Stage Order**: Integer starting at 1. Determines execution sequence.
> - **Stage ID**: Code identifier, e.g. `stage_10_backfill`, `stage_20_cleanup`. Must match the code.
> - **Module**: Dotted module path that implements this stage.
> - **Input Event / Topic**: Bus topic or event this stage consumes, e.g. `k0.embedding.backfill.trigger`. Write `scheduler` if triggered by scheduler, not an event.
> - **Output Event / Topic**: Topic emitted on success. Write `N/A` if no event emitted.
> - **Side Effects**: Comma-separated: DB writes, metric increments, log entries. e.g. `writes st_vec rows, increments backfill_processed counter`.
> - **Error Topic**: Topic where errors are published, e.g. `k0.embedding.backfill.error`. Write `DLQ` if dead-letter queue.
> - **Retry Policy**: e.g. `3x exponential backoff`, `no retry`, `manual only`.
>
> **EXAMPLE**:
>
> | Stage Order | Stage ID | Module | Input Event / Topic | Output Event / Topic | Side Effects | Error Topic | Retry Policy |
> | ----------- | -------- | ------ | ------------------- | -------------------- | ------------ | ----------- | ------------ |
> | 1 | stage_10_backfill | k0.modules.embedding.backfill | scheduler (interval/threshold) | k0.embedding.backfill.complete | writes st_vec rows, increments backfill_processed counter | k0.embedding.backfill.error | 3x exponential backoff |
> | 2 | stage_20_cleanup | k0.modules.embedding.cleanup | stage_10 completion | k0.embedding.cleanup.complete | deletes orphan st_vec rows, increments cleanup_deleted counter | k0.embedding.cleanup.error | no retry (idempotent) |

### 4.2 Input Schemas (per stage / module)

**Stage: {stage_id}**

| # | Field | Type | Required | Nullable | Validation Rule | Source (upstream stage / external) | Example Value |
| - | ----- | ---- | -------- | -------- | --------------- | --------------------------------- | ------------- |
| 1 | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Field**: Exact key name in the input dict/message, e.g. `tenant_id`, `event_id`, `payload.vector`.
> - **Type**: Python type, e.g. `str`, `int`, `list[float]`, `dict[str, Any]`.
> - **Required**: `yes` or `no`. `yes` means processing fails without it.
> - **Nullable**: `yes` (can be None) or `no` (must have a value).
> - **Validation Rule**: Specific constraint, e.g. `len == 768`, `non-empty string`, `UUID format`, `> 0`. Write `none` if no validation.
> - **Source**: Where this field comes from: upstream stage name, external API, user input, DB lookup.
> - **Example Value**: A realistic value, e.g. `"evt_abc123"`, `[0.012, -0.034, ...]`, `768`.
>
> **EXAMPLE** (Stage: stage_10_backfill):
>
> | # | Field | Type | Required | Nullable | Validation Rule | Source | Example Value |
> | - | ----- | ---- | -------- | -------- | --------------- | ------ | ------------- |
> | 1 | tenant_id | str | yes | no | non-empty, max 64 chars | scheduler trigger | "tenant_001" |
> | 2 | space_id | str | yes | no | non-empty, max 64 chars | scheduler trigger | "space_default" |
> | 3 | batch_size | int | no | no | > 0, defaults to 500 | config | 500 |

### 4.3 Output Schemas (per stage / module)

**Stage: {stage_id}**

| # | Field | Type | Nullable | Produced By (logic) | Consumed By (downstream) | Example Value |
| - | ----- | ---- | -------- | ------------------- | ------------------------ | ------------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Field**: Exact key name in the output dict.
> - **Type**: Python type.
> - **Nullable**: `yes` or `no`.
> - **Produced By**: Which logic/function produces this field, e.g. `backfill.run() counter`, `SQL COUNT(*)`.
> - **Consumed By**: Downstream stage, metric, or log that reads this, e.g. `stage_20 input`, `P08Runner summary`, `metrics`.
> - **Example Value**: Realistic output value.
>
> **EXAMPLE** (Stage: stage_10_backfill):
>
> | # | Field | Type | Nullable | Produced By | Consumed By | Example Value |
> | - | ----- | ---- | -------- | ----------- | ----------- | ------------- |
> | 1 | processed | int | no | backfill.run() loop counter | P08Runner summary, metrics | 42 |
> | 2 | skipped | int | no | already-READY check | metrics | 3 |
> | 3 | errors | int | no | exception counter | P08Runner fault isolation | 0 |

### 4.4 Error Outputs

| # | Error Code / Type | Condition | HTTP Status (if API) | Handling (retry / skip / abort / DLQ) | Downstream Impact | Recoverable? |
| - | ----------------- | --------- | -------------------- | ------------------------------------- | ----------------- | ------------ |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Error Code / Type**: Exception class or error string, e.g. `ValueError`, `DimensionMismatchError`, `SYSCALL_FAILED`.
> - **Condition**: Exact condition that triggers this error, e.g. `vector length != 768`, `DB connection timeout`.
> - **HTTP Status**: If this surfaces as an API error, the HTTP code. Write `N/A` for internal-only errors.
> - **Handling**: Pick one of: `retry` (automatic), `skip` (log and continue), `abort` (stop pipeline), `DLQ` (send to dead-letter).
> - **Downstream Impact**: What happens to the pipeline/consumer when this error fires.
> - **Recoverable?**: `yes` (retry will succeed), `no` (data/config problem, needs human fix), `maybe` (depends on cause).
>
> **EXAMPLE**:
>
> | # | Error Code / Type | Condition | HTTP Status | Handling | Downstream Impact | Recoverable? |
> | - | ----------------- | --------- | ----------- | -------- | ----------------- | ------------ |
> | 1 | ValueError | vector length != 768 | N/A | skip | Single event skipped, backfill continues | no -- bad embedding data |
> | 2 | ConnectionError | DB unreachable | N/A | retry | Stage paused until DB recovers | yes -- transient |

### 4.5 Data Transformation Map

| # | Source Field(s) | Transformation | Target Field | Lossy? | Reversible? | Notes |
| - | --------------- | -------------- | ------------ | ------ | ----------- | ----- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Source Field(s)**: Input field(s) consumed. Comma-separated if multiple, e.g. `payload.text, payload.language`.
> - **Transformation**: What operation is applied, e.g. `UltraBERT encode`, `normalize to unit vector`, `cast to VECTOR(768)`.
> - **Target Field**: Output field name.
> - **Lossy?**: `yes` (information lost, cannot reconstruct source from target) or `no` (lossless, bijective).
> - **Reversible?**: `yes` (can get source back from target) or `no`.
> - **Notes**: Constraints, version dependencies, etc.
>
> **EXAMPLE**:
>
> | # | Source Field(s) | Transformation | Target Field | Lossy? | Reversible? | Notes |
> | - | --------------- | -------------- | ------------ | ------ | ----------- | ----- |
> | 1 | payload.text | UltraBERT v2.1.0 encode -> 768-dim float vector | st_vec.vector | yes | no | Text -> embedding is one-way |
> | 2 | payload.created_at (epoch int) | datetime.fromtimestamp() -> TIMESTAMPTZ | st_vec.created_at | no | yes | Precision: microseconds |

---

## 5. Storage & Persistence

### 5.1 Tables Touched

| # | Table | Operation (R / W / RW) | Key Columns Used | Access Pattern (point / range / scan / aggregate) | Index Used | Estimated Row Count |
| - | ----- | ---------------------- | ---------------- | ------------------------------------------------- | ---------- | ------------------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Table**: Exact DB table name, e.g. `st_vec`, `st_hipp_events`.
> - **Operation**: `R` (read only), `W` (write only), `RW` (both read and write).
> - **Key Columns Used**: Columns in WHERE/JOIN/INSERT clauses, e.g. `event_id, tenant_id, space_id`.
> - **Access Pattern**: Pick one of: `point` (single row by PK), `range` (bounded scan), `scan` (full table), `aggregate` (COUNT/SUM/etc).
> - **Index Used**: Index name that covers this access, e.g. `ix_st_vec_tenant`. Write `NONE (needs index)` if missing.
> - **Estimated Row Count**: Order of magnitude, e.g. `~10K`, `~1M`, `~100M`.
>
> **EXAMPLE**:
>
> | # | Table | Operation | Key Columns Used | Access Pattern | Index Used | Estimated Row Count |
> | - | ----- | --------- | ---------------- | -------------- | ---------- | ------------------- |
> | 1 | st_vec | RW | embedding_id, event_id, tenant_id, space_id | point (by embedding_id), range (by tenant+space) | ix_st_vec_tenant, PK | ~100K |
> | 2 | st_hipp_events | R | event_id | point (by event_id) | PK | ~500K |

### 5.2 Column-Level Detail

| Table | Column | Type | Nullable | Default | Read By (module) | Written By (module) | Indexed? | Notes |
| ----- | ------ | ---- | -------- | ------- | ---------------- | ------------------- | -------- | ----- |
| | | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Table**: DB table name.
> - **Column**: Exact column name.
> - **Type**: SQL type, e.g. `TEXT`, `VECTOR(768)`, `TIMESTAMPTZ`, `VARCHAR(64)`, `INTEGER`.
> - **Nullable**: `yes` or `no`.
> - **Default**: SQL default, e.g. `NOW()`, `'READY'`, `768`. Write `NONE` if no default.
> - **Read By**: Module(s) that SELECT this column.
> - **Written By**: Module(s) that INSERT/UPDATE this column.
> - **Indexed?**: `yes (index_name)` or `no`.
> - **Notes**: Constraints, CHECK clauses, FK relationships.
>
> **EXAMPLE**:
>
> | Table | Column | Type | Nullable | Default | Read By | Written By | Indexed? | Notes |
> | ----- | ------ | ---- | -------- | ------- | ------- | ---------- | -------- | ----- |
> | st_vec | vector | VECTOR(768) | no | NONE | integrity_check, search | extract_from_cache, backfill | yes (ix_st_vec_hnsw) | HNSW cosine ops, m=16, ef=64 |
> | st_vec | status | VARCHAR(16) | no | 'READY' | backfill, integrity_check | extract_from_cache, backfill | yes (ix_st_vec_status) | CHECK IN ('READY', 'FAILED') |

### 5.3 Query Patterns

| # | Query Purpose | SQL Pattern / Pseudocode | Frequency (per-event / batch / scheduled) | Expected Latency | Index Coverage | Notes |
| - | ------------- | ------------------------ | ----------------------------------------- | ---------------- | -------------- | ----- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Query Purpose**: What the query achieves, one phrase, e.g. `count orphan vectors`, `fetch events missing embeddings`.
> - **SQL Pattern**: Simplified SQL showing the structure. Use `...` for long column lists, e.g. `SELECT COUNT(*) FROM st_vec v WHERE NOT EXISTS (SELECT 1 FROM st_hipp_events h WHERE h.event_id = v.event_id)`.
> - **Frequency**: How often this runs: `per-event` (once per message), `batch` (periodic batch), `scheduled` (cron/interval).
> - **Expected Latency**: Target, e.g. `< 10ms`, `< 100ms`, `< 1s`.
> - **Index Coverage**: `full` (all WHERE columns indexed), `partial` (some indexed), `none` (seq scan).
> - **Notes**: Explain any performance concerns or planned optimizations.
>
> **EXAMPLE**:
>
> | # | Query Purpose | SQL Pattern | Frequency | Expected Latency | Index Coverage | Notes |
> | - | ------------- | ----------- | --------- | ---------------- | -------------- | ----- |
> | 1 | Count orphan vectors | SELECT COUNT(*) FROM st_vec v WHERE NOT EXISTS (SELECT 1 FROM st_hipp_events h WHERE h.event_id = v.event_id) | scheduled (P08 stage_20) | < 500ms at 100K rows | partial (ix_st_vec_event) | Anti-join pattern, consider index-only scan |

### 5.4 Storage Gaps

| # | Gap | Current State | Required State | Migration Needed? | Priority |
| - | --- | ------------- | -------------- | ----------------- | -------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Gap**: What is missing or wrong in storage. One sentence.
> - **Current State**: What exists now.
> - **Required State**: What should exist.
> - **Migration Needed?**: `yes` (need Alembic migration), `no` (code-only change), `maybe` (depends on approach).
> - **Priority**: `P0` to `P3`.
>
> **EXAMPLE**:
>
> | # | Gap | Current State | Required State | Migration Needed? | Priority |
> | - | --- | ------------- | -------------- | ----------------- | -------- |
> | 1 | No composite index on (tenant_id, space_id, status) | Separate indexes on tenant and status | Single composite index for common query pattern | yes | P2 |

---

## 6. Event Bus & Topics

### 6.1 Topics Consumed

| # | Topic | Schema (YAML ref) | Producer Module | Consumer Module | Ordering Guarantee | Idempotency Key |
| - | ----- | ------------------ | --------------- | --------------- | ------------------ | --------------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Topic**: Full topic string, e.g. `k0.hipp.event.written`, `k0.embedding.backfill.trigger`.
> - **Schema (YAML ref)**: Path to the YAML schema defining this topic's payload, e.g. `k0/contracts/events/hipp_event_written.v1.yaml`.
> - **Producer Module**: Module that publishes to this topic.
> - **Consumer Module**: Module that subscribes to this topic (your module).
> - **Ordering Guarantee**: `ordered` (messages arrive in order), `unordered` (no guarantee), `partitioned` (ordered within partition key).
> - **Idempotency Key**: Field used to deduplicate, e.g. `event_id`, `embedding_id`. Write `none` if no dedup.
>
> **EXAMPLE**:
>
> | # | Topic | Schema | Producer | Consumer | Ordering | Idempotency Key |
> | - | ----- | ------ | -------- | -------- | -------- | --------------- |
> | 1 | k0.hipp.event.written | k0/contracts/events/hipp_event_written.v1.yaml | core.hipp_events_writer | embedding.extract_from_cache | partitioned (by tenant_id) | event_id |

### 6.2 Topics Emitted

| # | Topic | Schema (YAML ref) | Emitter Module | Known Consumers | Payload Size Estimate | Frequency |
| - | ----- | ------------------ | -------------- | --------------- | --------------------- | --------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Topic**: Full topic string.
> - **Schema**: Path to YAML schema.
> - **Emitter Module**: Module that publishes.
> - **Known Consumers**: Comma-separated list of modules that consume this. Write `none yet` if no consumers.
> - **Payload Size Estimate**: Approximate bytes per message, e.g. `~200B`, `~3KB`, `~50KB`.
> - **Frequency**: Messages per time unit, e.g. `~100/min`, `1/hour`, `per-event`.
>
> **EXAMPLE**:
>
> | # | Topic | Schema | Emitter | Known Consumers | Payload Size | Frequency |
> | - | ----- | ------ | ------- | --------------- | ------------ | --------- |
> | 1 | k0.embedding.backfill.complete | k0/contracts/events/embedding_backfill_complete.v1.yaml | embedding.backfill | P08Runner (stage sequencing) | ~200B | ~10/hour (batch) |

### 6.3 Topic Gaps (needed but missing)

| # | Proposed Topic | Purpose | Producer | Consumer | Schema Draft | Priority |
| - | -------------- | ------- | -------- | -------- | ------------ | -------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Proposed Topic**: Topic string you want to create.
> - **Purpose**: Why this topic is needed. One sentence.
> - **Producer**: Module that would publish.
> - **Consumer**: Module that would subscribe.
> - **Schema Draft**: Inline field list or reference, e.g. `{tenant_id: str, space_id: str, count: int}`.
> - **Priority**: `P0` to `P3`.
>
> **EXAMPLE**:
>
> | # | Proposed Topic | Purpose | Producer | Consumer | Schema Draft | Priority |
> | - | -------------- | ------- | -------- | -------- | ------------ | -------- |
> | 1 | k0.consolidation.batch.ready | Signal that a batch of events is ready for consolidation scoring | batch_selector (R0) | consolidation.scoring | {tenant_id: str, space_id: str, event_ids: list[str], batch_size: int} | P1 |

---

## 7. Observability Audit

### 7.1 Existing Metrics

| # | Metric Name | Type (counter / gauge / histogram / summary) | Location (file:line) | Labels | Purpose | Alert Threshold |
| - | ----------- | --------------------------------------------- | -------------------- | ------ | ------- | --------------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Metric Name**: Exact metric name as it appears in code, e.g. `k0_embedding_backfill_processed_total`.
> - **Type**: Pick one of: `counter` (monotonically increasing), `gauge` (can go up/down), `histogram` (distribution), `summary`.
> - **Location**: `file:line` where the metric is defined/incremented.
> - **Labels**: Comma-separated label names, e.g. `tenant_id, status, pipeline_id`.
> - **Purpose**: What this metric tells you. One sentence.
> - **Alert Threshold**: When to alert, e.g. `> 100 errors/min`, `gauge == 0 for > 5min`. Write `none` if no alert defined.
>
> **EXAMPLE**:
>
> | # | Metric Name | Type | Location | Labels | Purpose | Alert Threshold |
> | - | ----------- | ---- | -------- | ------ | ------- | --------------- |
> | 1 | k0_embedding_backfill_processed_total | counter | k0/modules/embedding/backfill.py:23 | tenant_id, space_id | Counts vectors successfully backfilled | none |

### 7.2 Existing Traces / Spans

| # | Span Name | Location (file:line) | Attributes | Parent Span | Purpose |
| - | --------- | -------------------- | ---------- | ----------- | ------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Span Name**: OpenTelemetry span name, e.g. `p08.stage_10_backfill`, `embedding.vec_write`.
> - **Location**: `file:line` where span is created.
> - **Attributes**: Key-value pairs attached, e.g. `tenant_id, batch_size, duration_ms`.
> - **Parent Span**: Name of the parent span. Write `root` if it is a root span.
> - **Purpose**: What this trace captures. One sentence.
>
> **EXAMPLE**:
>
> | # | Span Name | Location | Attributes | Parent Span | Purpose |
> | - | --------- | -------- | ---------- | ----------- | ------- |
> | 1 | p08.handle | k0/pipelines/p08/runner.py:55 | pipeline_id, stage_count | root | Traces entire P08 pipeline execution |

### 7.3 Structured Log Points

| # | Log Level | Location (file:line) | Message Pattern | Fields | Purpose |
| - | --------- | -------------------- | --------------- | ------ | ------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Log Level**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
> - **Location**: `file:line`.
> - **Message Pattern**: The log message template with placeholders, e.g. `"Backfill complete: processed=%d skipped=%d"`.
> - **Fields**: Structured fields logged, e.g. `tenant_id, processed, skipped, duration_ms`.
> - **Purpose**: When would an operator look at this log.
>
> **EXAMPLE**:
>
> | # | Log Level | Location | Message Pattern | Fields | Purpose |
> | - | --------- | -------- | --------------- | ------ | ------- |
> | 1 | INFO | k0/modules/embedding/backfill.py:89 | "Backfill batch complete: processed=%d skipped=%d errors=%d" | tenant_id, space_id, processed, skipped, errors | Verify backfill progress per batch |

### 7.4 Observability Gaps

| # | Gap | What's Missing | Impact if Unresolved | Priority |
| - | --- | -------------- | -------------------- | -------- |
| 1 | | | | |

> **COLUMN GUIDE**:
>
> - **Gap**: What observability is missing. One sentence.
> - **What's Missing**: Specific metric, span, or log that should exist.
> - **Impact if Unresolved**: What goes wrong in production without this.
> - **Priority**: `P0` to `P3`.
>
> **EXAMPLE**:
>
> | # | Gap | What's Missing | Impact if Unresolved | Priority |
> | - | --- | -------------- | -------------------- | -------- |
> | 1 | No latency histogram for vec_write | histogram metric for vec_write syscall duration | Cannot detect slow writes, no SLO monitoring | P1 |

---

## 8. Test Coverage Audit

### 8.1 Existing Tests

| # | Test File | Lines | Test Count | Type (unit / integration / e2e / property) | Coverage Target (module / function) | Pass / Fail | Notes |
| - | --------- | ----- | ---------- | ------------------------------------------- | ----------------------------------- | ----------- | ----- |
| 1 | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Test File**: Relative path to test file.
> - **Lines**: Line count.
> - **Test Count**: Number of test functions/methods in the file. Count `def test_*` functions.
> - **Type**: Pick one of: `unit` (isolated, mocked deps), `integration` (real DB/bus), `e2e` (full pipeline), `property` (hypothesis/fuzzing).
> - **Coverage Target**: What module or function this file tests, e.g. `embedding.backfill.run`, `P08Runner`.
> - **Pass / Fail**: Current status: `PASS` (all green), `FAIL` (some failing), `SKIP` (skipped).
> - **Notes**: Known issues, flakiness, or limitations.
>
> **EXAMPLE**:
>
> | # | Test File | Lines | Test Count | Type | Coverage Target | Pass / Fail | Notes |
> | - | --------- | ----- | ---------- | ---- | --------------- | ----------- | ----- |
> | 1 | tests/k0/modules/embedding/test_m25_pgvector_backfill.py | 242 | 18 | integration | embedding.backfill.run | PASS | Uses real pgvector, 768-dim vectors |

### 8.2 Coverage Gaps

| # | Gap | What's Untested | Risk Level (P0-P3) | Proposed Test | Test Type |
| - | --- | --------------- | ------------------- | ------------- | --------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Gap**: What is not tested. One sentence.
> - **What's Untested**: Specific function, branch, or scenario.
> - **Risk Level**: `P0` = critical untested path, `P1` = important, `P2` = moderate, `P3` = low risk.
> - **Proposed Test**: Brief description of the test to write.
> - **Test Type**: `unit`, `integration`, `e2e`, `property`.
>
> **EXAMPLE**:
>
> | # | Gap | What's Untested | Risk Level | Proposed Test | Test Type |
> | - | --- | --------------- | ---------- | ------------- | --------- |
> | 1 | No test for concurrent backfill batches | Two backfill.run() calls with overlapping event sets | P1 | test_concurrent_backfill_idempotency: run 2 parallel batches, assert no duplicate vectors | integration |

### 8.3 Test Infrastructure Needs

| # | Need | Current State | Required State | Blocking Epic? |
| - | ---- | ------------- | -------------- | -------------- |
| 1 | | | | |

> **COLUMN GUIDE**:
>
> - **Need**: What test infrastructure is missing, e.g. `pgvector test fixture`, `bus mock`, `benchmark harness`.
> - **Current State**: What exists now.
> - **Required State**: What must exist for tests to work.
> - **Blocking Epic?**: Epic ID this blocks, or `no`.
>
> **EXAMPLE**:
>
> | # | Need | Current State | Required State | Blocking Epic? |
> | - | ---- | ------------- | -------------- | -------------- |
> | 1 | Shared pgvector test fixture | Each test file creates own DB setup | Shared conftest.py with pgvector session fixture | 5.03 |

---

## 9. Dependency Map

### 9.1 Upstream (what this pipeline / module needs)

| # | Dependency | Type (module / syscall / table / config / service / library) | Status (ready / partial / missing) | Owner Milestone | Gap if Missing |
| - | ---------- | ------------------------------------------------------------ | ---------------------------------- | --------------- | -------------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Dependency**: Name of the dependency, e.g. `vec_write syscall`, `st_vec table`, `pgvector extension`.
> - **Type**: Pick one of: `module`, `syscall`, `table`, `config`, `service`, `library`.
> - **Status**: `ready` (fully available), `partial` (exists but needs changes), `missing` (does not exist yet).
> - **Owner Milestone**: Which milestone owns this dependency, e.g. `M4`, `M5`.
> - **Gap if Missing**: What happens if this dependency is not available. One sentence.
>
> **EXAMPLE**:
>
> | # | Dependency | Type | Status | Owner Milestone | Gap if Missing |
> | - | ---------- | ---- | ------ | --------------- | -------------- |
> | 1 | vec_write syscall | syscall | ready | M4 | Cannot write embeddings to pgvector |
> | 2 | consolidation.scoring module | module | missing | M5 | No scoring algorithm for P03 stages |

### 9.2 Downstream (what depends on this)

| # | Dependent | Type | How Used | Impact if Changed | Owner Milestone |
| - | --------- | ---- | -------- | ----------------- | --------------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Dependent**: Module, pipeline, or component that depends on this work.
> - **Type**: `module`, `syscall`, `table`, `config`, `pipeline`.
> - **How Used**: One sentence explaining the dependency relationship.
> - **Impact if Changed**: What breaks downstream if this is modified.
> - **Owner Milestone**: Which milestone owns the dependent.
>
> **EXAMPLE**:
>
> | # | Dependent | Type | How Used | Impact if Changed | Owner Milestone |
> | - | --------- | ---- | -------- | ----------------- | --------------- |
> | 1 | P08 stage_10_backfill | pipeline | Calls embedding.backfill.run() | Stage fails if signature changes | M4 |

### 9.3 External Dependencies (libraries, services, extensions)

| # | Dependency | Version | Purpose | License | Pinned? | Upgrade Risk |
| - | ---------- | ------- | ------- | ------- | ------- | ------------ |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Dependency**: Package or service name, e.g. `pgvector`, `sqlalchemy`, `sentence-transformers`.
> - **Version**: Exact pinned version or range, e.g. `0.2.4`, `>=2.0,<3.0`.
> - **Purpose**: What it provides. One sentence.
> - **License**: SPDX identifier, e.g. `MIT`, `Apache-2.0`, `PostgreSQL`.
> - **Pinned?**: `yes` (exact version in requirements.txt) or `no` (range or unpinned).
> - **Upgrade Risk**: `low` (stable API), `medium` (minor breaking changes possible), `high` (major API changes expected).
>
> **EXAMPLE**:
>
> | # | Dependency | Version | Purpose | License | Pinned? | Upgrade Risk |
> | - | ---------- | ------- | ------- | ------- | ------- | ------------ |
> | 1 | pgvector | 0.2.4 | PostgreSQL vector similarity search extension | PostgreSQL | yes | low |

---

## 10. Performance Baseline

### 10.1 Current Benchmarks

| # | Operation | Dataset Size | p50 | p95 | p99 | Throughput (ops/s) | Memory Peak | Notes |
| - | --------- | ------------ | --- | --- | --- | ------------------ | ----------- | ----- |
| 1 | | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Operation**: What was measured, e.g. `vec_write single insert`, `backfill batch (500 vectors)`.
> - **Dataset Size**: Size of test data, e.g. `10K rows`, `100K vectors`, `1M events`.
> - **p50, p95, p99**: Latency percentiles in milliseconds.
> - **Throughput**: Operations per second.
> - **Memory Peak**: Peak RSS during operation, e.g. `128MB`, `2.1GB`.
> - **Notes**: Test environment, caveats, measurement tool used.
>
> **EXAMPLE**:
>
> | # | Operation | Dataset Size | p50 | p95 | p99 | Throughput | Memory Peak | Notes |
> | - | --------- | ------------ | --- | --- | --- | ---------- | ----------- | ----- |
> | 1 | vec_write single insert | 1 row | 2ms | 5ms | 12ms | 450/s | 45MB | Local PostgreSQL 16, pgvector 0.2.4 |

### 10.2 Known Bottlenecks

| # | Bottleneck | Location (file:line) | Cause | Measured Impact | Proposed Fix | Priority |
| - | ---------- | -------------------- | ----- | --------------- | ------------ | -------- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Bottleneck**: Short name, e.g. `sequential vec_write`, `full table scan on orphan count`.
> - **Location**: `file:line` where the bottleneck occurs.
> - **Cause**: Root cause explanation. One sentence.
> - **Measured Impact**: Quantified impact, e.g. `adds 200ms p95 per batch`, `3x memory vs optimal`.
> - **Proposed Fix**: How to fix it. One sentence.
> - **Priority**: `P0` to `P3`.
>
> **EXAMPLE**:
>
> | # | Bottleneck | Location | Cause | Measured Impact | Proposed Fix | Priority |
> | - | ---------- | -------- | ----- | --------------- | ------------ | -------- |
> | 1 | Sequential vec_write in backfill | k0/modules/embedding/backfill.py:67 | Inserts one row at a time instead of batch INSERT | 500 rows takes 1.1s vs estimated 200ms with batch | Use executemany or COPY for batch inserts | P2 |

### 10.3 Performance Targets

| # | Operation | Target p95 | Target Throughput | Target Memory | Acceptance Criteria |
| - | --------- | ---------- | ----------------- | ------------- | ------------------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Operation**: Same operation name as in 10.1.
> - **Target p95**: Maximum acceptable p95 latency, e.g. `< 50ms`.
> - **Target Throughput**: Minimum acceptable ops/s, e.g. `> 1000/s`.
> - **Target Memory**: Maximum acceptable memory, e.g. `< 512MB`.
> - **Acceptance Criteria**: How to verify the target is met, e.g. `benchmark test with 10K rows must pass`.
>
> **EXAMPLE**:
>
> | # | Operation | Target p95 | Target Throughput | Target Memory | Acceptance Criteria |
> | - | --------- | ---------- | ----------------- | ------------- | ------------------- |
> | 1 | backfill batch (500 vectors) | < 500ms | > 1000 vectors/s | < 256MB | test_backfill_performance with 10K vectors on CI |

---

## 11. Gap Analysis & Enhancement Register

### 11.1 Functional Gaps

| # | Gap ID | Gap Description | Current State | Desired State | Severity (P0-P3) | Proposed Fix | Related ADR |
| - | ------ | --------------- | ------------- | ------------- | ----------------- | ------------ | ----------- |
| 1 | FG-001 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Gap ID**: Format `FG-NNN`, sequential, e.g. `FG-001`, `FG-002`.
> - **Gap Description**: What is missing or wrong. One sentence.
> - **Current State**: What exists today.
> - **Desired State**: What should exist after the fix.
> - **Severity**: `P0` = blocker, `P1` = major, `P2` = minor, `P3` = cosmetic.
> - **Proposed Fix**: How to fix it. One sentence.
> - **Related ADR**: ADR that governs this area, or `none`.
>
> **EXAMPLE**:
>
> | # | Gap ID | Gap Description | Current State | Desired State | Severity | Proposed Fix | Related ADR |
> | - | ------ | --------------- | ------------- | ------------- | -------- | ------------ | ----------- |
> | 1 | FG-001 | No scoring algorithm for consolidation | P03 has no scoring module | Scoring module produces 0.0-1.0 relevance scores per event | P0 | Implement consolidation.scoring with configurable weights | ADR-K001 |

### 11.2 Contract Gaps

| # | Contract | Section / Field | Gap | Impact | Fix |
| - | -------- | --------------- | --- | ------ | --- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Contract**: Contract file path.
> - **Section / Field**: Which section or field in the contract is affected.
> - **Gap**: What is wrong or missing.
> - **Impact**: What breaks because of this gap.
> - **Fix**: How to fix the contract.
>
> **EXAMPLE**:
>
> | # | Contract | Section / Field | Gap | Impact | Fix |
> | - | -------- | --------------- | --- | ------ | --- |
> | 1 | k0/contracts/modules/consolidation.scoring.v1.yaml | output_schema | Missing score_confidence field | Downstream ranker cannot assess score reliability | Add score_confidence: float[0.0, 1.0] to output schema |

### 11.3 Architecture Gaps

| # | Area | Gap | ADR Needed? | Impact | Proposed Resolution |
| - | ---- | --- | ----------- | ------ | ------------------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Area**: Architecture area, e.g. `event bus`, `storage layer`, `module protocol`, `security`.
> - **Gap**: What architectural element is missing or misaligned.
> - **ADR Needed?**: `yes` (new ADR required), `no` (existing ADR covers it), `update` (existing ADR needs revision).
> - **Impact**: Consequence of not addressing this gap.
> - **Proposed Resolution**: How to close the gap.
>
> **EXAMPLE**:
>
> | # | Area | Gap | ADR Needed? | Impact | Proposed Resolution |
> | - | ---- | --- | ----------- | ------ | ------------------- |
> | 1 | module protocol | No standard way to report partial success | yes | Modules return success or failure, no nuance for "processed 490/500" | ADR for PartialResult protocol with processed/skipped/failed counts |

---

## 12. Security & Privacy Audit

### 12.1 Data Classification

| # | Field / Column / Payload Key | Classification (public / internal / confidential / PII / sensitive) | Handling (plain / masked / encrypted / hashed / redacted) | Retention Policy | Notes |
| - | ---------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------- | ---------------- | ----- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Field / Column / Payload Key**: Exact identifier: DB column, message field, or config key.
> - **Classification**: Pick one of: `public` (safe to expose), `internal` (not for external users), `confidential` (business sensitive), `PII` (personally identifiable), `sensitive` (security-critical like keys/tokens).
> - **Handling**: How this data is stored/transmitted. Pick one of: `plain`, `masked`, `encrypted`, `hashed`, `redacted`.
> - **Retention Policy**: How long data is kept, e.g. `indefinite`, `90 days`, `until tenant deletion`.
> - **Notes**: Compliance requirements, legal constraints.
>
> **EXAMPLE**:
>
> | # | Field / Column | Classification | Handling | Retention Policy | Notes |
> | - | -------------- | -------------- | -------- | ---------------- | ----- |
> | 1 | st_vec.vector | internal | plain | indefinite | Embedding of user text -- not PII itself but derived from PII |
> | 2 | st_hipp_events.payload | PII | encrypted at rest | until tenant deletion | Contains user-generated text content |

### 12.2 Capability Boundaries

| # | Operation | Required Capability | Enforced? (yes / no / partial) | Enforcement Location | Gap |
| - | --------- | ------------------- | ------------------------------ | -------------------- | --- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Operation**: What action requires authorization, e.g. `vec_write`, `delete orphans`, `read embeddings`.
> - **Required Capability**: Capability token/role needed, e.g. `cap:vec:write`, `cap:embedding:admin`.
> - **Enforced?**: `yes` (checked in code), `no` (not checked), `partial` (some paths checked).
> - **Enforcement Location**: `file:line` where the check happens.
> - **Gap**: What is missing if enforcement is `no` or `partial`.
>
> **EXAMPLE**:
>
> | # | Operation | Required Capability | Enforced? | Enforcement Location | Gap |
> | - | --------- | ------------------- | --------- | -------------------- | --- |
> | 1 | vec_delete_orphans | cap:vec:admin | no | N/A | No capability check -- any module can delete vectors |

### 12.3 Input Validation & Sanitization

| # | Input Source | Validation Applied | Sanitization Applied | Injection Risk | Notes |
| - | ----------- | ------------------ | -------------------- | -------------- | ----- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Input Source**: Where input comes from, e.g. `bus message`, `HTTP request`, `config file`, `DB query result`.
> - **Validation Applied**: What checks are done, e.g. `type check, length check, range check`. Write `none` if no validation.
> - **Sanitization Applied**: What cleaning is done, e.g. `strip whitespace, escape SQL, html_escape`. Write `none` if no sanitization.
> - **Injection Risk**: `none`, `low`, `medium`, `high`. Consider SQL injection, XSS, command injection.
> - **Notes**: Specific concerns or mitigations.
>
> **EXAMPLE**:
>
> | # | Input Source | Validation Applied | Sanitization Applied | Injection Risk | Notes |
> | - | ----------- | ------------------ | -------------------- | -------------- | ----- |
> | 1 | bus message (tenant_id) | type check (str), max length 64 | none | low | Parameterized queries prevent SQL injection |
> | 2 | bus message (vector) | type check (list), len == 768, all elements float | none | none | Numeric data, no injection surface |

---

## 13. Enhancement Proposals

### 13.1 Proposed Epics

| Epic ID | Title | Scope Summary | Estimated Files | Priority (P0-P3) | Dependencies | Issue Count |
| ------- | ----- | ------------- | --------------- | ----------------- | ------------ | ----------- |
| X.XX | | | | | | |

> **COLUMN GUIDE**:
>
> - **Epic ID**: Milestone.sequence format, e.g. `5.01`, `5.02`. Must be globally unique.
> - **Title**: Short descriptive title, 3-8 words, e.g. `Implement P03 Scoring Algorithm`.
> - **Scope Summary**: One sentence describing what the epic delivers.
> - **Estimated Files**: Count of files to create/modify, e.g. `5 NEW, 3 MOD`.
> - **Priority**: `P0` = must-have for milestone, `P1` = important, `P2` = nice-to-have, `P3` = future.
> - **Dependencies**: Other epic IDs this depends on, e.g. `5.01, 4.20`. Write `none` if independent.
> - **Issue Count**: Number of issues in the breakdown (Section 13.2).
>
> **EXAMPLE**:
>
> | Epic ID | Title | Scope Summary | Estimated Files | Priority | Dependencies | Issue Count |
> | ------- | ----- | ------------- | --------------- | -------- | ------------ | ----------- |
> | 5.01 | P03 Batch Selector Design | Design and implement R0 batch selector for consolidation pipeline | 3 NEW, 2 MOD | P0 | none | 4 |
> | 5.02 | P03 Scoring Algorithm | Implement configurable multi-signal scoring for memory consolidation | 4 NEW, 1 MOD | P0 | 5.01 | 5 |

### 13.2 Epic Detail

_(Repeat this subsection for each epic in 13.1)_

---

#### Epic {X.XX} -- {Title}

**Summary**: _{one-line description}_

**Problem**: _{what is wrong or missing today}_

**Solution**: _{how this epic fixes it}_

> **GUIDE**:
>
> - **Summary**: One sentence. Format: "Implements / Creates / Adds / Modifies [thing] for [purpose]".
> - **Problem**: One sentence. What is broken, missing, or suboptimal today. Be specific.
> - **Solution**: One sentence. What this epic delivers to fix the problem.

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | | | | |

> **COLUMN GUIDE**:
>
> - **Input**: Name of the input, e.g. `event_batch`, `tenant_id`, `scoring_config`.
> - **Type**: Python type.
> - **Source**: Where this input comes from: upstream epic, config, DB, user.
> - **Validation**: What checks are applied before use.
>
> **EXAMPLE**:
>
> | # | Input | Type | Source | Validation |
> | - | ----- | ---- | ------ | ---------- |
> | 1 | event_ids | list[str] | R0 batch selector output | non-empty, max 1000, all valid UUIDs |
> | 2 | scoring_weights | dict[str, float] | k0/config/consolidation.yml | all values in [0.0, 1.0], sum == 1.0 |

##### Outputs

| # | Output | Type | Consumer | Guarantees |
| - | ------ | ---- | -------- | ---------- |
| 1 | | | | |

> **COLUMN GUIDE**:
>
> - **Output**: Name of the output.
> - **Type**: Python type.
> - **Consumer**: Who consumes this output.
> - **Guarantees**: What is always true about the output, e.g. `sorted descending by score`, `all scores in [0, 1]`.
>
> **EXAMPLE**:
>
> | # | Output | Type | Consumer | Guarantees |
> | - | ------ | ---- | -------- | ---------- |
> | 1 | scored_events | list[ScoredEvent] | R7 truth writer | sorted descending by score, all scores in [0.0, 1.0] |

##### Algorithm Changes

| # | Algorithm | Change Type (new / modify / replace / remove) | Before | After | Rationale |
| - | --------- | ---------------------------------------------- | ------ | ----- | --------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Algorithm**: Name from Section 3.1, or new algorithm name.
> - **Change Type**: Pick one of: `new` (does not exist yet), `modify` (adjust existing), `replace` (swap out), `remove` (delete).
> - **Before**: What exists now. Write `N/A` if `new`.
> - **After**: What will exist after the change.
> - **Rationale**: Why this change is needed. One sentence.
>
> **EXAMPLE**:
>
> | # | Algorithm | Change Type | Before | After | Rationale |
> | - | --------- | ----------- | ------ | ----- | --------- |
> | 1 | relevance_scoring | new | N/A | Multi-signal weighted scorer: recency *w1 + frequency* w2 + semantic_similarity * w3 | P03 needs relevance ranking for consolidation |

##### Config Changes

| # | Key / Variable / Flag | Change (add / modify / remove) | Old Value | New Value | Type | Notes |
| - | --------------------- | ------------------------------ | --------- | --------- | ---- | ----- |
| 1 | | | | | | |

> **COLUMN GUIDE**:
>
> - **Key / Variable / Flag**: Config key, env var, or feature flag name.
> - **Change**: `add` (new key), `modify` (change value/type), `remove` (delete key).
> - **Old Value**: Current value. Write `N/A` if `add`.
> - **New Value**: Proposed value. Write `N/A` if `remove`.
> - **Type**: Python type.
> - **Notes**: Why this change is needed.
>
> **EXAMPLE**:
>
> | # | Key / Variable / Flag | Change | Old Value | New Value | Type | Notes |
> | - | --------------------- | ------ | --------- | --------- | ---- | ----- |
> | 1 | consolidation.scoring.weights.recency | add | N/A | 0.4 | float | Recency signal weight for relevance scoring |

##### Contract Changes

| # | Contract File | Change (new / modify / deprecate) | Section | Details |
| - | ------------- | --------------------------------- | ------- | ------- |
| 1 | | | | |

> **COLUMN GUIDE**:
>
> - **Contract File**: Relative path to the YAML contract.
> - **Change**: `new` (create file), `modify` (edit existing), `deprecate` (add deprecated header).
> - **Section**: Which section of the contract, e.g. `output_schema`, `triggers`, `stages`.
> - **Details**: What specifically changes.
>
> **EXAMPLE**:
>
> | # | Contract File | Change | Section | Details |
> | - | ------------- | ------ | ------- | ------- |
> | 1 | k0/contracts/modules/consolidation.scoring.v1.yaml | new | entire file | New v1 contract for scoring module: inputs, outputs, config, triggers |

##### Storage Changes

| # | Table | Operation | Column(s) | Migration File | Reversible? |
| - | ----- | --------- | --------- | -------------- | ----------- |
| 1 | | | | | |

> **COLUMN GUIDE**: Same as Section 1.4. Use `+column` / `-column` / `~column` notation.
>
> **EXAMPLE**:
>
> | # | Table | Operation | Column(s) | Migration File | Reversible? |
> | - | ----- | --------- | --------- | -------------- | ----------- |
> | 1 | st_consolidation_scores | CREATE | +event_id TEXT PK, +score FLOAT, +signals JSONB, +created_at TIMESTAMPTZ | 0072_consolidation_scores.py | no (new table) |

##### Syscall Changes

| # | Syscall | Change (new / modify / remove) | Before Signature | After Signature | Notes |
| - | ------- | ------------------------------ | ---------------- | --------------- | ----- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Syscall**: Syscall method name.
> - **Change**: `new`, `modify`, `remove`.
> - **Before Signature**: Current signature. Write `N/A` if `new`.
> - **After Signature**: Proposed signature. Write `N/A` if `remove`.
> - **Notes**: Why this change is needed.
>
> **EXAMPLE**:
>
> | # | Syscall | Change | Before Signature | After Signature | Notes |
> | - | ------- | ------ | ---------------- | --------------- | ----- |
> | 1 | score_write | new | N/A | (event_id, tenant_id, space_id, score, signals) -> dict | Persist consolidation scores for R7 truth writer |

##### Event / Topic Changes

| # | Topic | Change (new / modify / remove) | Schema Change | Impact |
| - | ----- | ------------------------------ | ------------- | ------ |
| 1 | | | | |

> **COLUMN GUIDE**:
>
> - **Topic**: Full topic string.
> - **Change**: `new`, `modify`, `remove`.
> - **Schema Change**: What changes in the topic payload schema.
> - **Impact**: Who is affected by this change.
>
> **EXAMPLE**:
>
> | # | Topic | Change | Schema Change | Impact |
> | - | ----- | ------ | ------------- | ------ |
> | 1 | k0.consolidation.scored | new | {event_id: str, score: float, signals: dict, tenant_id: str} | R7 truth writer subscribes to receive scored events |

##### Test Plan

| # | Test File | Test Name | Type | What It Proves | Priority |
| - | --------- | --------- | ---- | -------------- | -------- |
| 1 | | | | | |

> **COLUMN GUIDE**:
>
> - **Test File**: Proposed test file path.
> - **Test Name**: Proposed test function name. Must start with `test_`.
> - **Type**: `unit`, `integration`, `e2e`, `property`.
> - **What It Proves**: One sentence explaining what this test verifies.
> - **Priority**: `P0` (must have for acceptance), `P1` (important), `P2` (nice-to-have).
>
> **EXAMPLE**:
>
> | # | Test File | Test Name | Type | What It Proves | Priority |
> | - | --------- | --------- | ---- | -------------- | -------- |
> | 1 | tests/k0/modules/consolidation/test_scoring.py | test_scoring_weights_sum_to_one | unit | Validates that scoring config rejects weights that don't sum to 1.0 | P0 |
> | 2 | tests/k0/modules/consolidation/test_scoring.py | test_scoring_empty_batch | integration | Scoring returns empty list for empty event batch without error | P0 |

##### Risks

| # | Risk | Likelihood (low / med / high) | Impact (low / med / high) | Mitigation |
| - | ---- | ----------------------------- | ------------------------- | ---------- |
| 1 | | | | |

> **COLUMN GUIDE**:
>
> - **Risk**: What could go wrong. One sentence.
> - **Likelihood**: `low`, `med`, `high`.
> - **Impact**: `low`, `med`, `high`.
> - **Mitigation**: How to prevent or reduce the risk. One sentence.
>
> **EXAMPLE**:
>
> | # | Risk | Likelihood | Impact | Mitigation |
> | - | ---- | ---------- | ------ | ---------- |
> | 1 | Scoring weights need tuning after deployment | high | med | Make weights configurable via YAML, not hardcoded |

##### Acceptance Criteria

- [ ] _{criterion 1}_
- [ ] _{criterion 2}_

> **GUIDE**: Each criterion must be objectively verifiable. Format: "Given [context], when [action], then [result]".
> Do not write vague criteria like "works correctly" or "is fast".
>
> **EXAMPLE**:
>
> - [ ] Given 500 events with mixed recency/frequency signals, when scoring runs, then all scores are in [0.0, 1.0]
> - [ ] Given weights config summing to != 1.0, when module loads, then ValueError is raised
> - [ ] Given empty event batch, when scoring runs, then returns [] in < 10ms

##### Issues Breakdown

| Issue # | Title | Scope | Estimate (S / M / L) | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------------------- | ---------- | ------------------- |
| {X.XX}.1 | | | | | |
| {X.XX}.2 | | | | | |

> **COLUMN GUIDE**:
>
> - **Issue #**: Format `{EpicID}.N`, e.g. `5.02.1`, `5.02.2`. Sequential within the epic.
> - **Title**: Short title, 3-8 words. Describes a single deliverable.
> - **Scope**: One sentence describing what this issue delivers.
> - **Estimate**: `S` (< 2 hours, < 100 lines), `M` (2-8 hours, 100-500 lines), `L` (> 8 hours, > 500 lines).
> - **Depends On**: Other issue IDs this blocks on, e.g. `5.02.1`. Write `none` if independent.
> - **Acceptance Criteria**: One sentence. The single condition that proves this issue is done.
>
> **EXAMPLE**:
>
> | Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
> | ------- | ----- | ----- | -------- | ---------- | ------------------- |
> | 5.02.1 | Create scoring contract YAML | Write k0/contracts/modules/consolidation.scoring.v1.yaml with full I/O schema | S | none | Contract passes YAML lint and covers input, output, config, triggers |
> | 5.02.2 | Implement scoring algorithm | Build consolidation.scoring.run() with weighted multi-signal scorer | M | 5.02.1 | test_scoring_weights_sum_to_one and test_scoring_empty_batch pass |
> | 5.02.3 | Add scoring syscall | Add score_write to k0/kernel/syscalls.py | S | 5.02.1 | Syscall executes INSERT INTO st_consolidation_scores and returns row |
> | 5.02.4 | Integration tests | Write full integration test suite for scoring module | M | 5.02.2, 5.02.3 | All 8 tests pass, coverage > 90% on consolidation.scoring |

---

## 14. Risk Register

| # | Risk ID | Risk | Category (technical / schedule / dependency / security / performance) | Likelihood (low / med / high) | Impact (low / med / high) | Risk Score | Mitigation Strategy | Owner | Status (open / mitigated / accepted / closed) |
| - | ------- | ---- | -------------------------------------------------------------------- | ----------------------------- | ------------------------- | ---------- | ------------------- | ----- | ---------------------------------------------- |
| 1 | R-001 | | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Risk ID**: Format `R-NNN`, sequential, e.g. `R-001`, `R-002`.
> - **Risk**: What could go wrong. One sentence.
> - **Category**: Pick one of: `technical`, `schedule`, `dependency`, `security`, `performance`.
> - **Likelihood**: `low`, `med`, `high`.
> - **Impact**: `low`, `med`, `high`.
> - **Risk Score**: Likelihood x Impact: `low` (low-low, low-med), `medium` (med-med, low-high, high-low), `high` (med-high, high-med, high-high).
> - **Mitigation Strategy**: How to prevent or reduce the risk. One sentence.
> - **Owner**: Who is responsible for monitoring this risk. Name or role.
> - **Status**: Pick one of: `open` (active risk), `mitigated` (controls in place), `accepted` (known, no action), `closed` (no longer relevant).
>
> **EXAMPLE**:
>
> | # | Risk ID | Risk | Category | Likelihood | Impact | Risk Score | Mitigation | Owner | Status |
> | - | ------- | ---- | -------- | ---------- | ------ | ---------- | ---------- | ----- | ------ |
> | 1 | R-001 | Scoring algorithm performance degrades with large batches (>10K events) | performance | med | high | high | Implement batch chunking with configurable max_batch_size, add performance test | dev-lead | open |
> | 2 | R-002 | P03 depends on embedding syscalls from M4 that may change | dependency | low | med | low | M4 APIs are frozen and tested (155 tests pass) | dev-lead | mitigated |

---

## 15. Open Questions

| # | Question | Context | Blocking? | Answer | Status (open / answered / deferred) | Answered By | Date |
| - | -------- | ------- | --------- | ------ | ----------------------------------- | ----------- | ---- |
| 1 | | | | | | | |

> **COLUMN GUIDE**:
>
> - **Question**: The exact question. Be specific, not vague.
> - **Context**: Why this question matters. One sentence.
> - **Blocking?**: `yes` (cannot proceed without answer) or `no` (can proceed with assumption).
> - **Answer**: The answer when known. Leave blank if `open`.
> - **Status**: `open` (unanswered), `answered` (resolved), `deferred` (postponed to later milestone).
> - **Answered By**: Who answered. Leave blank if `open`.
> - **Date**: When answered. Leave blank if `open`.
>
> **EXAMPLE**:
>
> | # | Question | Context | Blocking? | Answer | Status | Answered By | Date |
> | - | -------- | ------- | --------- | ------ | ------ | ----------- | ---- |
> | 1 | Should consolidation scores be immutable or updatable? | Affects st_consolidation_scores schema (PK vs upsert) | yes | | open | | |
> | 2 | What is the target batch size for P03 stage 1? | Needed for performance targets and test data generation | no | 500 (same as P08 backfill) | answered | architect | 2026-03-01 |

---

## Appendix A: Glossary

| Term | Definition |
| ---- | ---------- |
| | |

> **GUIDE**: Add every domain-specific term, abbreviation, or K0 concept used in this document.
> Non-obvious terms only -- do not define "API" or "SQL".
>
> **EXAMPLE**:
>
> | Term | Definition |
> | ---- | ---------- |
> | HNSW | Hierarchical Navigable Small World -- approximate nearest neighbor graph index algorithm used by pgvector |
> | DLQ | Dead Letter Queue -- topic where unprocessable messages are sent for manual review |
> | P03 | Pipeline 03: Memory Consolidation -- scores, ranks, and merges hippocampal events into long-term memory |

## Appendix B: References

| # | Document | Path / URL | Relevance |
| - | -------- | ---------- | --------- |
| 1 | | | |

> **GUIDE**: Link every document referenced in this discovery. Use relative workspace paths.
>
> **EXAMPLE**:
>
> | # | Document | Path / URL | Relevance |
> | - | -------- | ---------- | --------- |
> | 1 | P03 Consolidation Dossier v2 | docs/pipelines/P03_consolidation_dossier_v2.md | Pipeline scope and stage definitions |
> | 2 | ADR-K003 pgvector Migration | docs/architecture/decisions-K0/adr-k003-v2-pgvector-migration.md | Storage decisions governing st_vec schema |
> | 3 | M4 Completion Record | docs/plans/MASTER_IMPLEMENTATION_SKELETON.md (M4 section) | Upstream milestone APIs and contracts |
