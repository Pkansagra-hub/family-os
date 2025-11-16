# K0 Pipeline Development Process

**Date:** November 15, 2025
**Purpose:** Repeatable workflow for designing, implementing, and integrating K0 pipelines (P01-P20)
**Status:** Authoritative Process Document

---

## Overview

This document defines the **mandatory workflow** for all K0 pipeline development. Think of this as a **pipeline factory loop** that you run for each pipeline (P01-P20), with shared components (modules, syscalls, tables) accumulating over time.

**Key Principle:**
> Design → Data → Modules → Contracts → Code → Integration

**Not Negotiable:**

- Data model BEFORE modules
- Contracts BEFORE implementations
- ADRs BEFORE code
- Tests BEFORE kernel integration

---

## Process Steps (Per Pipeline)

### Step 0: Create Pipeline Dossier

**Goal:** Create a working document for this pipeline
**Time:** 15-30 minutes
**Output:** `docs/pipelines/Pxx_<name>_dossier.md`

**Template:**

```markdown
# Pxx: <Pipeline Name> - Development Dossier

## Purpose
[1-2 sentence description of what this pipeline does]

## Inputs/Outputs
- **Entry Topic:** cognitive.memory.<action>.<stage>.v1
- **Exit Topic:** pxx.<pipeline>.<result>.v1
- **Storage Reads:** [tables]
- **Storage Writes:** [tables]

## Responsibilities
- [ ] Responsibility 1 (e.g., "Run affect analysis")
- [ ] Responsibility 2 (e.g., "Resolve space visibility")
- [ ] Responsibility 3 (e.g., "Compute novelty & write hippocampus")

## Draft Module Mapping
| Responsibility | Candidate Module | Notes |
|---------------|------------------|-------|
| Affect analysis | affect.analyze | Pure function, no storage |
| ... | ... | ... |

## Open Questions
- [ ] Question 1
- [ ] Question 2

## Status
- [ ] Step 1: Discovery (this doc) → 📘 Update Master Doc: Part 2.1 (Pipeline Registry)
- [ ] Step 2: Data design → 📘 Update Master Doc: Part 5.3 (Storage Contracts)
- [ ] Step 3: Module list frozen → 📘 Update Master Doc: Part 3.1 (Module Registry)
- [ ] Step 4: ADRs written → 📘 Update Master Doc: Part 7.1 (ADR Index), Part 2.1, Part 3.1
- [ ] Step 5: Contracts created → 📘 Update Master Doc: Part 5.1 (Contract Registry), Part 7.1
- [ ] Step 6: Pipeline spec YAML → 📘 Update Master Doc: Part 4.1 (Event Topics), Part 4.4 (DAG), Part 5.1
- [ ] Step 7: Modules implemented → ❌ No Master Doc update needed
- [ ] Step 8: Syscalls derived → 📘 Update Master Doc: Part 5.2 (Syscall Matrix), Part 5.4, Part 5.7
- [ ] Step 9: PipelineRunner wired → ❌ No Master Doc update needed
- [ ] Step 10: Kernel integrated → 📘 Update Master Doc: Part 2.1, Part 3.1 (Status → ⚠️ Implementation)
- [ ] Step 11: End-to-end tested → 📘 Update Master Doc: Part 2.1, Part 3.1, Part 6.4, Part 8.1 (Status → ✅ Production)
```

**This is NOT an ADR.** It's your **working sheet** that evolves as you progress through the steps.

---

### Step 1: Pipeline Discovery

**Goal:** Turn "P02 Write" into a clear, finite job
**Time:** 1-2 hours
**Inputs:** Kernel diagram, pipeline list, existing notes
**Output:** Completed "Pipeline Dossier" sections 1-3

**Tasks:**

1. **Define Scope (1-2 sentences)**
   - Example P02: "Take committed memory.delta envelopes and transform them into durable episodic/semantic memories, hippocampus entries, and completion events."
   - Write in Dossier "Purpose" section

2. **List Inputs & Outputs**
   - Input topics (what triggers this pipeline?)
   - Output topics (what events does it emit?)
   - Storage touched (which tables read/written?)
   - Fill "Inputs/Outputs" section in Dossier

3. **List Responsibilities as Bullets**
   - "Run affect analysis"
   - "Resolve space/visibility"
   - "Compute novelty & write hippocampus row"
   - "Write episodic/semantic, indexes, receipts"
   - Each bullet is **one testable unit of work**

4. **Group Responsibilities into Candidate Modules**
   - Each bullet or small cluster → potential module
   - Fill "Draft Module Mapping" table in Dossier
   - **Rule:** One module = one clearly bounded responsibility

**Completion Criteria:**

- [ ] Pipeline purpose fits in 2 sentences
- [ ] Input/output topics identified
- [ ] Storage tables identified
- [ ] Responsibilities listed (5-10 bullets max)
- [ ] Candidate modules identified (2-5 modules typical)

**📘 Update k0_architecture_master.md:**

**Location:** `k0/pipelines/k0_architecture_master.md` → Part 2.1: Pipeline Master Registry

**Action:** Add new row to Pipeline Master Registry table:

```markdown
| Pxx_NAME | 📝 Design | <1-2 sentence purpose> | <entry_topic> | <exit_topic> | v0.1.0 | docs/pipelines/Pxx_<name>_dossier.md | ADR-Pxx-* | YYYY-MM-DD | [Your Name] |
```

**Status Code:** Use `📝 Design` at this stage (pre-implementation planning)

**Fields to Fill:**

- Pipeline ID: `Pxx_NAME` (e.g., P02_WRITE)
- Status: `📝 Design`
- Purpose: Copy from Dossier "Purpose" section (1-2 sentences)
- Entry Topic: From "Inputs/Outputs" section
- Exit Topic: From "Inputs/Outputs" section
- Version: `v0.1.0` (initial)
- README Path: Link to Dossier (will update to README in Step 11)
- ADRs: `ADR-Pxx-*` (placeholder, will update in Step 4)
- Last Updated: Today's date
- Owner: Your name/team

**Why Now:** Establishes pipeline in master registry early, making it visible to other architects.

---

### Step 2: Data Design First

**Goal:** Ensure storage model exists BEFORE writing modules
**Time:** 2-4 hours
**Inputs:** Pipeline Dossier
**Output:** SQL migrations + updated storage docs

**Why First:** You CANNOT implement modules that rely on tables/columns that don't exist.

**Tasks:**

1. **List All Data Artifacts Needed**
   - From responsibilities, identify:
     - New tables?
     - New columns in existing tables?
     - New indexes?
   - Write in Dossier "Open Questions" section initially

2. **For Each New Table:**
   - Define **purpose** in one line
   - List columns:
     - Identity (primary key)
     - Linkage (space_id, envelope_id, tenant_id)
     - Key features (domain-specific columns)
     - Lifecycle (timestamps, crdt_*, privacy_band, retention)
   - Define indexes for query patterns

3. **Write Migration(s)**
   - Create `k0/contracts/sql/migrations/NNNN_pxx_<slug>.sql`
   - Follow migration template:

     ```sql
     -- Migration NNNN: Pxx <Pipeline Name> - <Purpose>
     -- Purpose: [One line]
     -- Date: YYYY-MM-DD
     -- Related: Pipeline Pxx, ADR-Pxx-*

     BEGIN;

     -- Table creation with comments
     CREATE TABLE IF NOT EXISTS st_xxx (...);

     -- Indexes
     CREATE INDEX IF NOT EXISTS idx_xxx ON st_xxx(...);

     COMMIT;
     ```

   - Update `k0/contracts/sql/storage.sql` if you maintain baseline

4. **Update Documentation**
   - `docs/versioning_documents/pipeline_implementation/Pxx_<name>.md`
   - Add section: "Data Structures Used by This Pipeline"
   - List tables, columns, purpose, lifecycle

**Completion Criteria:**

- [ ] All new tables have migrations
- [ ] All new columns have migrations
- [ ] Indexes defined for query patterns
- [ ] Storage docs updated
- [ ] Migrations tested (apply + rollback)

**📘 Update k0_architecture_master.md:**

**Location:** `k0/pipelines/k0_architecture_master.md` → Part 5.3: Storage Contract Definitions

**Action:** For each NEW table created, add entry to Storage Contracts table:

```markdown
| st_<name> | <Purpose in one line> | Pxx | NNNN_pxx_<slug>.sql | <partition_key> | <retention_policy> | v1 | YYYY-MM-DD |
```

**Fields to Fill:**

- Table Name: From migration file
- Purpose: From migration comment
- Owning Pipeline: `Pxx` (primary creator)
- Migration ID: `NNNN_pxx_<slug>.sql`
- Partition Key: Primary partitioning column (e.g., `family_id`, `space_id`)
- Retention: Retention policy (e.g., "10 years", "90 days", "indefinite")
- Schema Version: `v1` (initial)
- Created Date: Migration date

**Why Now:** Documents storage contracts as they're created, ensuring traceability.

**BLOCKER:** Do NOT proceed to Step 3 until migrations are written and tested.

---

### Step 3: Slice into Modules

**Goal:** Freeze the module list for this pipeline
**Time:** 1-2 hours
**Inputs:** Responsibilities (Step 1), Data model (Step 2)
**Output:** Module list table in Pipeline Dossier

**Tasks:**

1. **Create Module List Table**

For Pxx, create table in Dossier:

```markdown
| Module ID                      | Role in Pxx                       | Reads/Writes                                    | Latency (ms) | Band  | Idempotent |
|--------------------------------|-----------------------------------|-------------------------------------------------|--------------|-------|------------|
| affect.analyze                 | Label affect for salience/health  | Pure function (no storage)                      | 10           | GREEN | Yes        |
| space.resolve_visibility       | Resolve owner/visible_to/band     | read:st_space, st_social                        | 10           | GREEN | Yes        |
| hippocampus.pattern_separate   | Compute novelty + write hippo row | read:st_hipp_store, st_vec; write:st_hipp_store | 15           | AMBER | Yes        |
| core.writer                    | One UoW commit to epi/sem/indexes | write:st_epi, st_sem, st_vec, st_fts, st_outbox | 25           | GREEN | No*        |
```

2. **For Each Module:**
   - Assign a `module_id` following pattern: `<domain>.<action>` (e.g., `hippocampus.pattern_separate`)
   - Define role in 5-10 words
   - List storage operations: `read:table`, `write:table`, `emit:topic`
   - Estimate latency budget (P95 target)
   - Assign privacy band (GREEN/AMBER/RED based on data sensitivity)
   - Mark idempotent (can it be safely retried?)

3. **Check for Reuse**
   - Review existing modules from other pipelines
   - **Reuse existing modules** where possible
   - Only create new modules when responsibility/data justifies it

4. **Validate DAG Order**
   - Arrange modules in dependency order
   - Ensure no circular dependencies
   - Mark which modules can run in parallel

**Completion Criteria:**

- [ ] Module list table complete (2-5 modules typical)
- [ ] Each module has clear, bounded responsibility
- [ ] Latency budgets sum to < 100ms P95 (for fast pipelines)
- [ ] Storage operations match data model from Step 2
- [ ] Reuse opportunities identified
- [ ] No circular dependencies

**📘 Update k0_architecture_master.md:**

**Location:** `k0/pipelines/k0_architecture_master.md` → Part 3.1: Module Master Registry

**Action:** For each NEW module (not reused), add row to Module Master Registry table:

```markdown
| Mxx_<NAME> / <domain>.<action> | 📝 Design | <Responsibility in 5-10 words> | Pxx | <latency_ms> P95 | <read:tables; write:tables> | v0.1.0 | docs/modules/Mxx_<name>/README.md | ADR-Pxx-<module_slug> | YYYY-MM-DD | [Your Name] |
```

**Fields to Fill:**

- Module ID: Follow `<domain>.<action>` pattern (e.g., `hippocampus.pattern_separate`)
- Status: `📝 Design`
- Responsibility: From Module List table "Role in Pxx" column
- Primary Pipeline: `Pxx` (where first used)
- Latency Budget: From Module List table "Latency (ms)" column
- Storage Operations: From Module List table "Reads/Writes" column
- Version: `v0.1.0` (initial)
- README Path: Placeholder (will create in Step 11)
- Related ADRs: `ADR-Pxx-<module_slug>` (will create in Step 4)
- Last Updated: Today's date
- Owner: Your name/team

**For REUSED Modules:** Do NOT add new row. Instead, update existing module row:

- Add `Pxx` to "Used By" column (if that column exists in your registry)
- Update "Last Updated" date

**Why Now:** Freezes module boundaries in master registry, preventing duplication.

**BLOCKER:** Only proceed when this table feels right. Module boundaries are hard to change later.

---

### Step 4: Write ADRs

**Goal:** Capture **why** each module exists and how it behaves
**Time:** 1-2 hours per module
**Inputs:** Module list table (Step 3)
**Output:** ADR files for each module

**Location:** `docs/architecture/decisions-K0/ADR-Pxx-<module_slug>.md`

**Template Per Module:**

```markdown
# ADR-Pxx-<module_slug>: <Module Title>

**Status:** Accepted
**Date:** YYYY-MM-DD
**Deciders:** [Team/Individual]
**Related:** Pipeline Pxx, Migration NNNN

---

## Context

**Which pipeline(s):** Pxx [<Pipeline Name>]
**Problem:** [What problem does this module solve?]
**Scope:** [What is IN scope vs OUT of scope?]

## Decision

**Module ID:** `<domain>.<action>:v1`

**Responsibilities:**
- Responsibility 1
- Responsibility 2
- Responsibility 3

**Data Operations:**
- **Reads:** st_table1 (columns: col1, col2)
- **Writes:** st_table2 (columns: col3, col4)
- **Emits:** topic.name.v1

**Performance:**
- Latency Budget: XXms P95
- Idempotent: Yes/No
- Privacy Band: GREEN/AMBER/RED

## Data Impact

**Tables Used:**
- `st_table1` - Purpose, created in Migration NNNN
- `st_table2` - Purpose, created in Migration MMMM

**Columns:**
- `table.column` - Purpose, type, constraints

## Interactions

**Dependencies (must run before this module):**
- Module A (provides data X)

**Dependents (must run after this module):**
- Module B (consumes data Y)

**Parallel-Safe:** Can run in parallel with: [Module C, Module D]

## Consequences

**Positive:**
- Enables feature X
- Improves performance Y
- Maintains privacy invariant Z

**Negative:**
- Adds latency of XXms
- Requires storage migration
- Increases complexity

**Risks:**
- Risk 1 + mitigation
- Risk 2 + mitigation

## Alternatives Considered

**Alternative 1:** [Description]
**Why Rejected:** [Reason]

**Alternative 2:** [Description]
**Why Rejected:** [Reason]

## References

- Pipeline Dossier: docs/pipelines/Pxx_<name>_dossier.md
- Migration: k0/contracts/sql/migrations/NNNN_pxx_*.sql
- Related ADRs: [List]
```

**Best Practices:**

- One ADR per module (or tightly coupled pair)
- When module is reused across pipelines, extend existing ADR (don't duplicate)
- Cross-reference data model (migrations from Step 2)
- Be explicit about order dependencies

**Completion Criteria:**

- [ ] One ADR per new module
- [ ] Data operations match Step 2 migrations
- [ ] Performance budgets documented
- [ ] Dependencies clear
- [ ] Privacy implications documented
- [ ] Risks + mitigations identified

**📘 Update k0_architecture_master.md:**

**Location:** `k0/pipelines/k0_architecture_master.md` → Part 7.1: ADR Index & Cross-Links

**Action:** For each ADR created, add row to ADR Index table:

```markdown
| ADR-Pxx-<slug> | <Module Title> | Accepted | YYYY-MM-DD | Pxx, Mxx | Migration NNNN | k0/contracts/modules/<domain>.<action>.v1.yaml | docs/architecture/decisions-K0/ADR-Pxx-<slug>.md | [Decider Names] |
```

**Fields to Fill:**

- ADR ID: `ADR-Pxx-<module_slug>` (e.g., `ADR-P02-hippocampus`)
- Title: From ADR title
- Status: `Accepted` (after review approval)
- Date: ADR creation date
- Scope: `Pxx` (pipeline), `Mxx` (module if assigned M-number)
- Related Migrations: `Migration NNNN` (from Step 2)
- Implements Contract: Path to module YAML (will create in Step 5)
- ADR Path: Full path to ADR file
- Deciders: Names from ADR header

**Also Update:**

- Part 2.1 (Pipeline Registry): Update "Related ADRs" column with comma-separated ADR IDs
- Part 3.1 (Module Registry): Update "Related ADRs" column with specific ADR ID

**Why Now:** Links decisions to implementations, ensures architectural traceability.

---

### Step 5: Module Contracts (YAML)

**Goal:** Turn ADR decisions into machine-readable contracts
**Time:** 30-60 minutes per module
**Inputs:** Module ADRs (Step 4)
**Output:** `k0/contracts/modules/<domain>.<action>.v<version>.yaml`

**Template:**

```yaml
module_id: domain.action
version: v1

# Input/Output (optional but recommended)
input_event_types:
  - cognitive.memory.write.committed.v1
output_event_types:
  - p02.hippocampus.pattern_separated.v1

# Performance & Behavior
latency_budget_ms: 15
idempotent: true

# Storage Operations (from ADR)
side_effects:
  - read:st_hipp_store
  - write:st_hipp_store
  - emit:p02.hippocampus.pattern_separated.v1

# Error Handling
failure_modes:
  - code: NOVELTY_SCORE_MISSING
    policy: drop
  - code: STORAGE_TIMEOUT
    policy: retry

# Documentation
description: |
  Pattern separation module for episodic memory encoding.
  Computes novelty scores by comparing against existing memories
  in hippocampus storage. Writes enriched event with similarity
  metadata for downstream consolidation.
```

**Field Mapping from Module List Table:**

- `module_id` ← Module ID column
- `latency_budget_ms` ← Latency column
- `idempotent` ← Idempotent column
- `side_effects` ← Reads/Writes column (convert to format: `operation:resource`)

**Validation:**

```python
# Test contract loading
from k0.runtime import ModuleRegistry

registry = ModuleRegistry()
await registry.load_contracts("k0/contracts/modules")

# Should load without errors
assert "domain.action:v1" in registry
```

**Completion Criteria:**

- [ ] One YAML per module
- [ ] All required fields present
- [ ] Side effects match ADR data operations
- [ ] Latency budgets match performance targets
- [ ] ModuleRegistry.load_contracts() succeeds
- [ ] No validation errors

**📘 Update k0_architecture_master.md:**

**Location:** `k0/pipelines/k0_architecture_master.md` → Part 5.1: Global Contract Registry

**Action:** For each module contract created, add row to Global Contract Registry table:

```markdown
| <domain>.<action>:v1 | Module | <Purpose in one line> | Pxx, Mxx | <latency_ms> ms P95 | <idempotent: true/false> | k0/contracts/modules/<domain>.<action>.v1.yaml | ADR-Pxx-<slug> | YYYY-MM-DD | Active |
```

**Fields to Fill:**

- Contract ID: `<domain>.<action>:v1` (from YAML `module_id` + `version`)
- Type: `Module`
- Purpose: From YAML `description` field (first sentence)
- Scope: `Pxx` (pipeline), `Mxx` (module)
- Performance: From YAML `latency_budget_ms`
- Idempotent: From YAML `idempotent` field
- Contract Location: Path to YAML file
- Documented In: `ADR-Pxx-<slug>`
- Version Date: Today's date
- Status: `Active`

**Also Update:**

- Part 5.2 (Syscall Matrix): For each `side_effect` in YAML, note required capability (will complete in Step 8)
- Part 7.1 (ADR Index): Update "Implements Contract" column with YAML path

**Why Now:** Formalizes module contracts in registry, enabling validation and discovery.

---

### Step 6: Define Pipeline Spec (YAML)

**Goal:** Wire modules into a declarative DAG
**Time:** 30-60 minutes
**Inputs:** Module contracts (Step 5), ADRs (Step 4)
**Output:** `k0/contracts/pipelines/pxx_<name>.v1.yaml`

**Template:**

```yaml
pipeline_id: P02_WRITE
version: v1

# Topics
entry_topic: cognitive.memory.write.committed.v1
exit_topic: p02.write.complete.v1

# Concurrency
concurrency: 1      # Sequential or parallel (1-50)
max_queue: 512      # Backpressure threshold

# Human-readable description
description: |
  P02 Pipeline - Episodic Memory Write Path
  Processes committed memory.delta envelopes and writes to hippocampus storage
  with pattern separation, affect analysis, and consolidation routing.

# DAG Stages (execution order)
dag:
  # Stage 1: Affect Analysis
  - id: stage_10_affect
    module: affect.analyze:v1
    after: []
    config:
      confidence_threshold: 0.8

  # Stage 2: Space Resolution
  - id: stage_20_space
    module: space.resolve_visibility:v1
    after: [stage_10_affect]
    config:
      visibility_mode: household

  # Stage 3: Pattern Separation
  - id: stage_30_hippocampus
    module: hippocampus.pattern_separate:v1
    after: [stage_20_space]
    config:
      novelty_threshold: 0.7

  # Stage 4: Write to Storage
  - id: stage_40_writer
    module: core.writer:v1
    after: [stage_30_hippocampus]
```

**DAG Rules:**

- Stage `id` must be unique within pipeline
- Stage `after` must reference existing stage IDs (or be empty `[]`)
- No cycles allowed (DAG builder will detect)
- Stages with same `after` can run in parallel (future optimization)

**Validation:**

```python
# Test spec loading
from k0.runtime import PipelineSpec

spec = PipelineSpec.load("k0/contracts/pipelines/p02_write.v1.yaml")

# Check DAG
assert len(spec.dag) > 0
assert spec.pipeline_id == "P02_WRITE"
assert spec.declared_topics == ("cognitive.memory.write.committed.v1",)
```

**Completion Criteria:**

- [ ] Pipeline YAML created
- [ ] All modules referenced exist as contracts
- [ ] DAG order matches ADR dependencies
- [ ] No cycles detected
- [ ] Entry/exit topics correct
- [ ] PipelineSpec.load() succeeds
- [ ] Concurrency/max_queue set appropriately

**📘 Update k0_architecture_master.md:**

**Location:** `k0/pipelines/k0_architecture_master.md` → Multiple sections

**Action 1 - Part 4.1 (Event Topics Registry):**

For entry/exit topics, add rows to Event Topics Registry:

```markdown
| <entry_topic> | Input | Pxx | <Purpose> | <schema_path> | v1 | GREEN/AMBER/RED | YYYY-MM-DD | Active |
| <exit_topic> | Output | Pxx | <Purpose> | <schema_path> | v1 | GREEN/AMBER/RED | YYYY-MM-DD | Active |
```

**Fields to Fill:**

- Topic Name: From YAML `entry_topic` / `exit_topic`
- Direction: `Input` or `Output`
- Owner Pipeline: `Pxx`
- Purpose: From pipeline `description`
- Schema: Path to event schema JSON (if exists)
- Version: `v1`
- QoS Band: GREEN/AMBER/RED (based on criticality)
- Registered: Today's date
- Status: `Active`

**Action 2 - Part 4.4 (Pipeline Execution Graph):**

Update DAG hierarchy if Pxx introduces new execution level:

- Identify which level Pxx belongs to (based on entry topic)
- Update DAG diagram/table with Pxx position

**Action 3 - Part 5.1 (Global Contract Registry):**

Add pipeline contract:

```markdown
| Pxx:<name>:v1 | Pipeline | <Purpose> | Pxx | <sum of module latencies> ms P95 | N/A | k0/contracts/pipelines/pxx_<name>.v1.yaml | ADR-Pxx-* | YYYY-MM-DD | Active |
```

**Why Now:** Wires pipeline into event topology and contract ecosystem.

---

### Step 7: Implement Modules

**Goal:** Write actual `run()` functions matching contracts
**Time:** 2-4 hours per module
**Inputs:** Module contracts (Step 5), ADRs (Step 4), Data model (Step 2)
**Output:** Module implementations + unit tests

**Location:** `k0/modules/<domain>/<action>.py`

**Template:**

```python
"""
<Domain> <Action> Module

[Description from contract]
"""

from __future__ import annotations

import logging
from typing import Any

from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext

logger = logging.getLogger(__name__)


async def run(
    message: BusMessage,
    context: PipelineContext,
    **config: Any,
) -> dict[str, Any]:
    """
    Execute <action> on incoming event.

    Args:
        message: Incoming BusMessage with event data
        context: PipelineContext with syscalls, logger, config
        **config: Stage-specific configuration overrides

    Returns:
        Enriched envelope with <action> metadata

    Raises:
        <ErrorType>: When <condition>
    """
    # 1. Parse envelope
    import json
    envelope = json.loads(message.payload)

    # 2. Extract configuration
    param1 = config.get("param1", default_value)

    # 3. Perform core logic
    # Use ONLY context.syscalls for storage
    # Use ONLY context.logger for logging
    result = await _compute_result(envelope, context, param1)

    # 4. Enrich envelope
    enriched = {
        **envelope,
        "<domain>_<action>": {
            "result": result,
            "module_version": "v1",
            "computed_at": ...,
        }
    }

    # 5. Log completion
    context.logger.info(
        f"<Action> complete: result={result}",
        extra={
            "module": "<domain>.<action>",
            "result": result,
            "trace_id": message.trace_id,
        },
    )

    return enriched


def _compute_result(envelope: dict, context: PipelineContext, param1: Any) -> Any:
    """Helper function for core logic."""
    # Pure computation or syscalls usage
    pass
```

**Module Characteristics:**

- **Pure function** - No side state, no cross-module dependencies
- **Idempotent** - Can be called multiple times safely (if contract says so)
- **Fast** - Respects latency budget from contract
- **Isolated** - Uses `context.syscalls` for storage, `context.logger` for logging

**Unit Test Template:**

```python
# tests/k0/modules/test_<domain>_<action>.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext
from k0.modules.<domain>.<action> import run


@pytest.mark.asyncio
async def test_<action>_basic():
    """Test <action> with valid input."""
    # Arrange
    message = BusMessage(
        topic="test.topic",
        payload=b'{"field": "value"}',
        offset=1,
        trace_id="test-trace",
    )

    mock_syscalls = MagicMock()
    mock_syscalls.<method> = AsyncMock(return_value=[...])

    context = PipelineContext(
        syscalls=mock_syscalls,
        config={},
        logger=MagicMock(),
    )

    # Act
    result = await run(message, context, param1="value")

    # Assert
    assert "<domain>_<action>" in result
    assert result["<domain>_<action>"]["result"] is not None
    mock_syscalls.<method>.assert_called_once()


@pytest.mark.asyncio
async def test_<action>_error_handling():
    """Test <action> error handling."""
    # Test with invalid input, storage errors, etc.
    pass
```

**Testing Strategy:**

- Mock `context.syscalls` methods
- Assert syscalls called correctly (matches `side_effects` in contract)
- Assert output envelope has expected fields
- Test error cases (missing data, storage failures)
- **DO NOT** test syscall implementations here (test those separately)

**Completion Criteria:**

- [ ] Module implementation complete
- [ ] Signature matches: `async def run(message, context, **config)`
- [ ] Uses ONLY `context.syscalls` for storage
- [ ] Respects latency budget
- [ ] Unit tests written (3-5 tests per module)
- [ ] All tests pass
- [ ] Code follows K0 style guide

---

### Step 8: Derive Syscalls

**Goal:** Design minimal syscall surface for all modules in Pxx
**Time:** 2-4 hours
**Inputs:** Module code (Step 7), contracts (Step 5), data model (Step 2)
**Output:** Syscall interface + implementations in `k0/kernel/syscalls.py`

**Why After Modules:** You now know **exactly** what storage operations modules need.

**Tasks:**

1. **Walk Through Each Module's Code**
   - List every `context.syscalls.<method>()` call
   - Note parameters and return types
   - Group similar operations

2. **Build Syscall Requirements Table**

```markdown
| Module                       | Requirement (English)           | Proposed Syscall                     | Capability       |
|------------------------------|---------------------------------|--------------------------------------|------------------|
| hippocampus.pattern_separate | Get similar memories by vector  | hipp_store_query(space_id, vector)   | st_hipp_store.read |
| hippocampus.pattern_separate | Write hippocampus row           | hipp_store_upsert(event_id, payload) | st_hipp_store.write |
| space.resolve_visibility     | Resolve space visibility        | space_resolve_visibility(space_id)   | st_space.read    |
| core.writer                  | Commit memory (epi+sem+indexes) | write_memory(envelope)               | st_epi.write     |
```

3. **Check for Reuse**
   - Review existing syscalls in `k0/kernel/syscalls.py`
   - **Reuse existing syscalls** where possible
   - Only add new syscalls when operation is truly unique

4. **Design Syscall Interface**

For each new syscall:

```python
async def <syscall_name>(
    self,
    param1: Type1,
    param2: Type2,
    ...
) -> ReturnType:
    """
    [One-line description]

    Capability Required: "<table>.<operation>"

    Args:
        param1: [Description]
        param2: [Description]

    Returns:
        [Description]

    Raises:
        PermissionError: If capability not granted
        [OtherErrors]: When [conditions]

    Example:
        >>> await syscalls.<syscall_name>(arg1, arg2)
    """
    self._require_cap("<table>.<operation>")

    with self._uow_factory() as uow:
        conn = uow._connection
        # Implementation using migrations from Step 2
        ...
```

5. **Implement Against Data Model**
   - Use tables/columns from migrations (Step 2)
   - Follow existing syscall patterns
   - Add telemetry/logging
   - Handle errors gracefully

6. **Write Syscall Tests**

```python
# tests/k0/kernel/test_syscalls.py

@pytest.mark.asyncio
async def test_<syscall_name>_success():
    """Test <syscall> with valid inputs."""
    # Test against real UnitOfWork with in-memory DB
    pass

@pytest.mark.asyncio
async def test_<syscall_name>_permission_denied():
    """Test <syscall> without capability."""
    syscalls = Syscalls("TEST", set(), uow_factory)  # No caps

    with pytest.raises(PermissionError):
        await syscalls.<syscall_name>(...)
```

**Completion Criteria:**

- [ ] All module requirements covered
- [ ] Syscalls follow existing patterns
- [ ] Capability enforcement implemented
- [ ] Error handling robust
- [ ] Unit tests pass
- [ ] Integration tests with UnitOfWork pass
- [ ] Documentation complete (docstrings)

**📘 Update k0_architecture_master.md:**

**Location:** `k0/pipelines/k0_architecture_master.md` → Part 5.2: Syscall Matrix

**Action:** For each NEW syscall created, add row to Syscall Matrix table:

```markdown
| <syscall_name> | <table>.<operation> | <Purpose in one line> | <parameters> | <return_type> | Pxx (via Mxx) | k0/kernel/syscalls.py:<line> | ADR-Pxx-<slug> | YYYY-MM-DD |
```

**Fields to Fill:**

- Syscall Name: Function name (e.g., `hipp_store_query`)
- Required Capability: From docstring "Capability Required" (e.g., `st_hipp_store.read`)
- Purpose: From docstring first line
- Parameters: Signature summary (e.g., `space_id: UUID, vector: List[float]`)
- Return Type: From signature (e.g., `List[Dict[str, Any]]`)
- Used By: `Pxx (via Mxx)` - which pipeline/module calls it
- Location: File path and line number
- Documented In: Related ADR
- Created: Today's date

**Also Update:**

- Part 5.4 (Traceability Matrix): Add row linking syscall → capability → module → pipeline
- Part 5.7 (Cross-Reference): Update syscall-to-storage mapping

**For REUSED Syscalls:** Update "Used By" column to add `Pxx (via Mxx)`

**Why Now:** Documents capability model and syscall surface, ensuring security audit trail.

---

### Step 9: Wire PipelineRunner

**Goal:** Make Pxx executable end-to-end in code
**Time:** 1-2 hours
**Inputs:** Modules (Step 7), Syscalls (Step 8), Pipeline spec (Step 6)
**Output:** Working `PipelineRunner` instance for Pxx

**Tasks:**

1. **Create Test Harness**

```python
# tests/k0/pipelines/test_pxx_integration.py

import pytest
from k0.runtime import ModuleRegistry, PipelineRunner, PipelineSpec
from k0.pipelines.protocol import PipelineContext
from k0.bus import BusMessage


@pytest.mark.asyncio
async def test_pxx_end_to_end():
    """Test Pxx pipeline end-to-end with real modules."""
    # 1. Load module contracts
    registry = ModuleRegistry()
    await registry.load_contracts("k0/contracts/modules")

    # 2. Load pipeline spec
    spec = PipelineSpec.load("k0/contracts/pipelines/pxx_<name>.v1.yaml")

    # 3. Create runner
    runner = PipelineRunner(spec, registry)

    # 4. Create context with real syscalls
    syscalls = Syscalls(
        spec.pipeline_id,
        set(spec.required_caps),
        uow_factory
    )
    ctx = PipelineContext(
        syscalls=syscalls,
        config={},
        logger=logger,
    )

    # 5. Startup
    await runner.on_startup(ctx)

    # 6. Create test message
    msg = BusMessage(
        topic=spec.entry_topic,
        payload=b'{"test": "data"}',
        offset=1,
        trace_id="test-trace",
    )

    # 7. Execute pipeline
    await runner.handle(msg)

    # 8. Assert results
    # Check database state, receipts, etc.
    assert ...
```

2. **Test with Mocks First**
   - Mock syscalls to isolate DAG execution
   - Verify modules called in correct order
   - Verify stage configs passed correctly

3. **Test with Real Storage**
   - Use in-memory SQLite
   - Apply migrations
   - Test full data flow
   - Verify idempotency

**Completion Criteria:**

- [ ] PipelineRunner instantiates successfully
- [ ] on_startup() succeeds
- [ ] handle() executes all stages in order
- [ ] Module outputs flow correctly
- [ ] Storage operations work
- [ ] End-to-end test passes
- [ ] Idempotency verified (run twice, same result)

---

### Step 10: Integrate with K0 Kernel

**Goal:** Make Pxx part of the real K0 system
**Time:** 2-4 hours
**Inputs:** Working PipelineRunner (Step 9)
**Output:** Kernel discovers and executes Pxx on real events

**Tasks:**

1. **Extend Loader for YAML Discovery**

Add to `k0/pipelines/loader.py`:

```python
async def discover_and_boot_pipelines(
    bus_dispatcher,
    uow_factory,
    config,
    logger,
    syscalls_factory=None,
    pipeline_context_class=None,
) -> dict[str, Any]:
    """Discover both Python and YAML-based pipelines."""
    pipelines = {}

    # EXISTING: Python class pipelines
    for py_file in pipeline_dir.glob("p[0-9]*.py"):
        pipeline = _load_python_pipeline(py_file)
        pipelines[pipeline.pipeline_id] = pipeline

    # NEW: YAML spec pipelines
    from k0.runtime import ModuleRegistry, PipelineRunner, PipelineSpec

    # Initialize module registry (shared across all YAML pipelines)
    module_registry = ModuleRegistry()
    contracts_dir = Path(__file__).parent.parent / "contracts" / "modules"
    if contracts_dir.exists():
        await module_registry.load_contracts(contracts_dir)
        logger.info(f"Loaded {len(module_registry)} module contracts")

    # Discover YAML pipeline specs
    specs_dir = Path(__file__).parent.parent / "contracts" / "pipelines"
    if specs_dir.exists():
        for yaml_file in sorted(specs_dir.glob("*.yaml")):
            try:
                spec = PipelineSpec.load(yaml_file)

                # Create runner (implements PipelineProtocol)
                runner = PipelineRunner(spec, module_registry)

                # Create context
                ctx = pipeline_context_cls(
                    syscalls=syscalls_factory_fn(
                        spec.pipeline_id,
                        set(spec.required_caps),
                        uow_factory
                    ),
                    config=config.get(spec.pipeline_id, {}),
                    logger=logger.getChild(spec.pipeline_id),
                )

                # Startup
                await runner.on_startup(ctx)

                # Subscribe to topics
                for topic in spec.declared_topics:
                    bus_dispatcher.subscribe(topic, runner.handle)

                pipelines[spec.pipeline_id] = runner
                logger.info(f"Booted YAML pipeline: {spec.pipeline_id}")

            except Exception as e:
                logger.error(f"Failed to load YAML pipeline {yaml_file.name}: {e}")
                raise

    return pipelines
```

2. **Verify Kernel Integration**

```bash
# Rebuild kernel
cd k0/deploy
./k0.ps1 -Command restart

# Check logs for:
# "Loaded X module contracts"
# "Booted YAML pipeline: P02_WRITE"
# "Subscribed P02_WRITE to cognitive.memory.write.committed.v1"
```

3. **Test End-to-End with Real Events**

```python
# k0/provision_and_submit.py (or test harness)

# Submit envelope
receipt = await submit_envelope(...)

# Check:
# - Pipeline executed (check logs)
# - Data written (check st_hipp_store)
# - Receipt emitted (check st_pipeline_status)
# - Idempotent (submit again, same result)
```

**Completion Criteria:**

- [ ] Loader discovers YAML pipelines
- [ ] Kernel boots with Pxx in pipeline list
- [ ] Bus dispatcher routes messages to Pxx
- [ ] Real envelope submission triggers Pxx
- [ ] Data written to storage correctly
- [ ] Receipts emitted
- [ ] No errors in kernel logs
- [ ] Latency within budget

**📘 Update k0_architecture_master.md:**

**Location:** `k0/pipelines/k0_architecture_master.md` → Part 2.1: Pipeline Master Registry

**Action:** Update pipeline status from `📝 Design` to `⚠️ Implementation`:

```markdown
| Pxx_NAME | ⚠️ Implementation | ... | ... | ... | v0.1.0 | ... | ... | YYYY-MM-DD | [Your Name] |
```

**Fields to Update:**

- Status: Change from `📝 Design` → `⚠️ Implementation`
- Last Updated: Today's date

**Also Update:**

- Part 3.1 (Module Registry): Update module status to `⚠️ Implementation` for all new modules
- Part 6.2 (Phase Detail): If Pxx was planned in a phase, mark phase milestone progress
- Part 8.1 (Performance Budgets): Add actual P95 latency measurement (from load test)

**Why Now:** Marks pipeline as operational in kernel, transitioning from design to implementation.

---

### Step 11: Production Validation

**Goal:** Verify Pxx is production-ready
**Time:** 2-4 hours
**Inputs:** Integrated Pxx (Step 10)
**Output:** Validated, documented, production-ready pipeline

**Validation Checklist:**

**Functional:**

- [ ] Processes valid envelopes correctly
- [ ] Handles invalid envelopes gracefully
- [ ] Idempotent (duplicate messages safe)
- [ ] Error handling works (transient vs permanent errors)
- [ ] Backpressure works (max_queue enforced)

**Performance:**

- [ ] P95 latency < budget (measure with load test)
- [ ] No memory leaks (long-running test)
- [ ] Concurrency settings appropriate
- [ ] Query patterns indexed correctly

**Observability:**

- [ ] Logs include trace_id for correlation
- [ ] Metrics emitted (duration, success/error counts)
- [ ] Errors logged with context
- [ ] Pipeline status queryable

**Security:**

- [ ] Capability enforcement working
- [ ] Privacy bands respected
- [ ] No unauthorized storage access
- [ ] Audit trail complete

**Data Quality:**

- [ ] All promised fields written
- [ ] Data types correct
- [ ] Constraints satisfied
- [ ] Foreign keys valid

**Documentation:**

- [ ] Pipeline Dossier updated with final state
- [ ] ADRs published
- [ ] README updated with Pxx entry
- [ ] Migration plan updated

**Integration:**

- [ ] Works with other pipelines (no conflicts)
- [ ] Topics correct
- [ ] Storage migrations clean
- [ ] Rollback plan documented

**Completion Criteria:**

- [ ] All validation checks pass
- [ ] Load test successful (1000+ envelopes)
- [ ] Monitoring dashboard created
- [ ] Runbook created for operations
- [ ] Code reviewed and merged

**📘 Update k0_architecture_master.md:**

**Location:** `k0/pipelines/k0_architecture_master.md` → Multiple sections

**Action 1 - Part 2.1 (Pipeline Master Registry):**

Update pipeline status to `✅ Production`:

```markdown
| Pxx_NAME | ✅ Production | ... | ... | ... | v1.0.0 | k0/pipelines/pxx_<name>/README.md | ADR-Pxx-* | YYYY-MM-DD | [Your Name] |
```

**Fields to Update:**

- Status: Change from `⚠️ Implementation` → `✅ Production`
- Version: Bump from `v0.1.0` → `v1.0.0` (first production release)
- README Path: Update from Dossier to actual Pipeline README
- Last Updated: Today's date

**Action 2 - Part 3.1 (Module Registry):**

Update all new module statuses to `✅ Production`

**Action 3 - Part 6.4 (Milestone Tracking):**

Mark milestone complete if Pxx was part of a milestone

**Action 4 - Part 8.1 (Performance Budgets):**

Update with production performance data:

- Actual P95 latency (from load test)
- Throughput (events/sec)
- Resource usage (memory, CPU)

**Action 5 - Part 8.5 (Quality Gates):**

Document that Pxx passed all 4 quality gates

**Action 6 - Create Pipeline README:**

Create `k0/pipelines/pxx_<name>/README.md` using template from Part 2.2 (14-section template)

**Action 7 - Part 9.3 (Architecture Snapshots):**

If this is a major milestone, create architecture snapshot

**Why Now:** Marks pipeline as production-ready, establishes authoritative README, records performance baseline.

---

## Repeating for Next Pipeline

For pipeline P(xx+1):

1. **Create new Dossier** (`docs/pipelines/P<xx+1>_<name>_dossier.md`)
2. **Reuse modules** where possible (check existing module list)
3. **Reuse syscalls** where possible (check existing syscalls)
4. **Share data model** where appropriate (extend existing tables vs new tables)
5. **Follow same 11-step process**

**Key Principle:**
> Maximize reuse. Only create new components when existing ones don't fit.

**Typical Reuse Patterns:**

- Modules: 30-50% reused across pipelines
- Syscalls: 60-70% reused
- Tables: 70-80% reused (extend columns vs new tables)

---

## Process Governance

**Mandatory Reviews:**

1. **Step 2 (Data Design):** Database schema review required
2. **Step 4 (ADRs):** Architecture review required
3. **Step 10 (Kernel Integration):** Code review + QA sign-off required

**Documentation Requirements:**

- Pipeline Dossier kept up-to-date throughout process
- All ADRs published before Step 7 (implementation)
- Migration tested before Step 7
- README updated after Step 11

**Quality Gates:**

Cannot proceed to next step if:

- Tests failing
- Documentation incomplete
- Reviews not approved
- Performance budget exceeded
- Security concerns unresolved

---

## Tools & Automation

**Script Support:**

```bash
# Create pipeline scaffolding
./scripts/create_pipeline.sh P02 write

# Validate contracts
python -m k0.runtime.validate_contracts

# Run pipeline tests
pytest tests/k0/pipelines/test_p02*.py

# Load test pipeline
python k0/load_test.py --pipeline P02 --count 1000
```

**Templates:**

- Pipeline Dossier template (above)
- ADR template (above)
- Module contract template (above)
- Pipeline spec template (above)
- Module implementation template (above)

---

## Status Tracking

Track pipeline development status in `k0/PIPELINE_STATUS.md`:

```markdown
| Pipeline | Dossier | Data | Modules | ADRs | Contracts | Spec | Code | Syscalls | Runner | Kernel | Validated |
|----------|---------|------|---------|------|-----------|------|------|----------|--------|--------|-----------|
| P01      | ✅      | ✅   | ✅      | ✅   | ✅        | ✅   | ✅   | ✅       | ✅     | ✅     | ✅        |
| P02      | ✅      | ✅   | ✅      | ⏳   | ⏳        | ⏳   | ⏳   | ⏳       | ⏳     | ⏳     | ⏳        |
| P03      | ⏳      | ⏳   | ⏳      | ⏳   | ⏳        | ⏳   | ⏳   | ⏳       | ⏳     | ⏳     | ⏳        |
...
```

---

## Questions & Clarifications

**Q: Can I skip steps?**
A: No. Each step builds on previous. Skipping creates technical debt.

**Q: Can I work on multiple pipelines in parallel?**
A: Yes, but complete Step 2 (data design) for all before implementing any modules.

**Q: What if I need to change a module after Step 5?**
A: Update contract → update ADR → update implementation → retest. Don't skip documentation.

**Q: How do I know if a module should be reused vs created new?**
A: If responsibility + data operations are >80% similar, reuse. Otherwise create new.

**Q: What if syscalls are missing during Step 7?**
A: Mock them in tests. Design actual syscalls in Step 8. Don't block module implementation.

---

## Master Document Update Summary

**Purpose:** Keep `k0/pipelines/k0_architecture_master.md` synchronized with pipeline development

**Update Frequency by Step:**

| Step | Master Doc Section(s) Updated | Status Change | Critical? |
|------|-------------------------------|---------------|----------|
| Step 1 (Discovery) | Part 2.1 (Pipeline Registry) | Add row, status=📝 Design | ✅ Required |
| Step 2 (Data Design) | Part 5.3 (Storage Contracts) | Add new tables | ✅ Required |
| Step 3 (Modules) | Part 3.1 (Module Registry) | Add new modules | ✅ Required |
| Step 4 (ADRs) | Part 7.1 (ADR Index), Part 2.1, Part 3.1 | Link ADRs | ✅ Required |
| Step 5 (Contracts) | Part 5.1 (Contract Registry), Part 5.2, Part 7.1 | Add module contracts | ✅ Required |
| Step 6 (Pipeline Spec) | Part 4.1 (Event Topics), Part 4.4 (DAG), Part 5.1 | Add topics, pipeline contract | ✅ Required |
| Step 7 (Implementation) | None | N/A | ❌ Not needed |
| Step 8 (Syscalls) | Part 5.2 (Syscall Matrix), Part 5.4, Part 5.7 | Add syscalls, traceability | ✅ Required |
| Step 9 (Runner) | None | N/A | ❌ Not needed |
| Step 10 (Kernel) | Part 2.1, Part 3.1, Part 6.2, Part 8.1 | Status=⚠️ Implementation | ✅ Required |
| Step 11 (Production) | Part 2.1, Part 3.1, Part 6.4, Part 8.1, Part 8.5, Part 9.3 | Status=✅ Production, README, perf data | ✅ Required |

**Status Progression:**

- Step 1-9: `📝 Design` (planning phase)
- Step 10: `⚠️ Implementation` (integrated with kernel)
- Step 11: `✅ Production` (validated and operational)

**Governance Rule:**
> Master document updates are MANDATORY at steps marked "Required". PRs cannot be merged without corresponding master doc updates.

**Why This Matters:**

- Prevents architectural drift
- Maintains single source of truth
- Enables discovery and reuse
- Ensures traceability (requirements → design → implementation)
- Supports architecture reviews and audits

**Tooling Support:**

```bash
# Validate master doc consistency
python scripts/validate_master_doc.py

# Check for missing registry entries
python scripts/audit_registries.py --pipeline Pxx

# Generate diff report
python scripts/master_doc_diff.py --since last-release
```

---

## References

- **Pipeline Infrastructure:** `k0/pipelines/README.md`
- **Runtime Infrastructure:** `k0/runtime/README.md`
- **Migration Plan:** `k0/pipelines/MIGRATION_PLAN.md`
- **Architecture Decisions:** `docs/architecture/decisions-K0/`
- **Storage Schema:** `k0/contracts/sql/storage.sql`
- **Master Architecture Document:** `k0/pipelines/k0_architecture_master.md`

---

**This is the authoritative process. Follow it for all pipelines P01-P20.**
