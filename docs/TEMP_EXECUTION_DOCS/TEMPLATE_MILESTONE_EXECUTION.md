# P03 Milestone Execution Document Template

> **Milestone**: M{N} — {Title}
> **Status**: NOT_STARTED | IN_PROGRESS | COMPLETED
> **Started**: YYYY-MM-DD
> **Completed**: YYYY-MM-DD
> **Prerequisites**: M0..M{N-1} must be COMPLETED

---

## Part A: Context Foundation (BEFORE YOU START)

### A.1 Dossier Sections Governing This Milestone

| Section | Title | Link | Why Needed |
|---------|-------|------|------------|
| §X.Y | Section Title | [Link](../pipelines/P03_consolidation_dossier_v2.md#xy-section-title) | Brief reason |
| Appendix Z | Appendix Title | [Link](../pipelines/P03_consolidation_dossier_v2.md#appendix-z) | Brief reason |

### A.2 Prior Milestone Outputs Consumed

| Artifact | From Milestone | Link to Part F Entry | How We Use It |
|----------|----------------|----------------------|---------------|
| P03 Pipeline Contract | M0 | [M0 Part F](./M0_EXECUTION.md#part-f-handoff-to-next-milestone) | Read pipeline_id, entry_topic |
| P03BatchEnvelope | M1 | [M1 Part F](./M1_EXECUTION.md#part-f-handoff-to-next-milestone) | Import for phase execution |

### A.3 Existing Repo Code Referenced

| Component | Path | Lines/Section | What Pattern We Copy |
|-----------|------|---------------|----------------------|
| UnitOfWork | [k0/uow/unit_of_work.py](../../k0/uow/unit_of_work.py) | L45-80 | stage_outbox() pattern |
| Feedback Envelope | [k0/feedback/envelope.py](../../k0/feedback/envelope.py) | L15-45 | Pydantic frozen model |
| Existing Migration | [k0/db/alembic/versions/0022_st_hipp_events.py](../../k0/db/alembic/versions/0022_st_hipp_events.py) | Full | Alembic migration structure |

### A.4 ADRs Governing This Work

| ADR | Path | Key Decisions Affecting This Milestone |
|-----|------|----------------------------------------|
| K004 | [decisions-K0/k004-capability-mesh.md](../../docs/architecture/decisions-K0/k004-capability-mesh.md) | Capability inheritance rules |
| P03-Architecture | [decisions-K0/pipelines/P03-consolidation-architecture.md](../../docs/architecture/decisions-K0/pipelines/P03-consolidation-architecture.md) | Phase order, entry/exit topics |

### A.5 Contracts/Schemas This Milestone Must Align With

| Contract | Path | Version | Fields We Must Match |
|----------|------|---------|----------------------|
| Kernel Envelope | [k0/contracts/jsonschema/envelope.schema.json](../../k0/contracts/jsonschema/envelope.schema.json) | v1 | trace_id, correlation_id |
| P03 Pipeline | [k0/contracts/pipelines/p03_consolidation.v1.yaml](../../k0/contracts/pipelines/p03_consolidation.v1.yaml) | v1 | pipeline_id, stages |

---

## Part B: Repository Patterns (HOW WE DO THINGS HERE)

### B.1 Pydantic Model Pattern (For Frozen/Immutable Data)

Source: [k0/feedback/envelope.py](../../k0/feedback/envelope.py)

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ExampleFrozenModel(BaseModel):
    """Immutable data container."""

    model_config = {"frozen": True}

    id: str = Field(..., description="Unique identifier")
    tenant_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict] = None
```

### B.2 Alembic Migration Pattern

Source: [k0/db/alembic/versions/0022_st_hipp_events.py](../../k0/db/alembic/versions/0022_st_hipp_events.py)

```python
"""Create st_example table

Revision ID: XXXX
Revises: YYYY
Create Date: YYYY-MM-DD
"""
from alembic import op
import sqlalchemy as sa

revision = 'XXXX'
down_revision = 'YYYY'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'st_example',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('space_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=True),
    )
    op.create_index('idx_example_tenant', 'st_example', ['tenant_id'])

def downgrade():
    op.drop_index('idx_example_tenant')
    op.drop_table('st_example')
```

### B.3 Module Contract YAML Pattern

Source: [k0/contracts/modules/](../../k0/contracts/modules/)

```yaml
module_id: "consolidation.example.v1"
version: "1.0.0"
description: "Brief description of module purpose"

input_types:
  - "p03.input.event.v1"

output_types:
  - "p03.output.result.v1"

required_capabilities:
  - "storage.read.st_hipp_events"
  - "storage.write.st_epi"

latency_budget_ms: 500
idempotent: true
side_effects:
  - "writes to st_epi"

failure_modes:
  - code: "TIMEOUT"
    retryable: true
    max_retries: 3
  - code: "VALIDATION_ERROR"
    retryable: false
```

### B.4 Test File Pattern

Source: [tests/k0/uow/test_unit_of_work.py](../../tests/k0/uow/test_unit_of_work.py)

```python
"""Tests for ExampleModule."""
import pytest
from ward import test, fixture

from k0.modules.example import ExampleClass


@fixture
def example_instance():
    """Create test instance."""
    return ExampleClass(config={})


@test("ExampleClass processes input correctly")
def test_example_processing(example_instance=example_instance):
    result = example_instance.process({"input": "value"})
    assert result.status == "SUCCESS"
    assert result.output is not None
```

### B.5 Import Conventions

```python
# Standard library first
from datetime import datetime
from typing import Optional, List, Dict

# Third party
from pydantic import BaseModel, Field

# K0 internal - absolute imports
from k0.kernel.syscalls import Syscalls
from k0.uow.unit_of_work import UnitOfWork
from k0.storage.offsets import OffsetStore

# Local module imports
from .envelope import P03BatchEnvelope
from .phases import P03Phase
```

---

## Part C: Scope Boundaries (WHAT TO DO / NOT DO)

### C.1 Files To CREATE (Exact Paths)

| File Path | Purpose | Created By Issue |
|-----------|---------|------------------|
| `k0/runtime/p03/envelope.py` | P03BatchEnvelope dataclass | 1.1.2 |
| `k0/runtime/p03/__init__.py` | Module init | 1.1.2 |
| `tests/k0/runtime/p03/test_envelope.py` | Envelope tests | 1.1.8 |

### C.2 Files To MODIFY (Exact Paths + What Changes)

| File Path | What To Change | Modified By Issue |
|-----------|----------------|-------------------|
| `governance/k0/k0_architecture_master.md` | Add P03 to Part 2.1 pipeline registry | 0.1.3 |
| `k0/pipelines/whiteboard.md` | Add P03 topics to event bus section | 0.1.4 |

### C.3 Files To NEVER TOUCH

| File Path | Reason |
|-----------|--------|
| `k0/db/alembic/versions/0001_*.py` through `0029_*.py` | Past migrations are immutable |
| `k0/kernel/syscalls.py` | Core kernel - separate ADR needed |
| `k0/contracts/jsonschema/envelope.schema.json` | Kernel envelope - not P03's to change |

### C.4 Out of Scope (Deferred to Later Milestone)

| Item | Deferred To | Reason |
|------|-------------|--------|
| st_learning_queue table | M2 Epic 2.3 | Learning tables are Epic 2.3 |
| P06 gap emission | M3 Epic 3.2 | Cross-pipeline in M3 |
| R5 Dream phase | M8 | Entire milestone dedicated |

---

## Part D: Execution Checklist (THE WORK)

### Epic N.1 — {Epic Title}

#### Issue N.1.1 — {Issue Title}

**Status**: NOT_STARTED | IN_PROGRESS | COMPLETED | BLOCKED

**Inputs Required**:

- [ ] Dossier section: [§X.Y](../pipelines/P03_consolidation_dossier_v2.md#xy)
- [ ] Prior artifact: [M{N-1} envelope](./M{N-1}_EXECUTION.md#part-f)
- [ ] Pattern from: [k0/feedback/envelope.py](../../k0/feedback/envelope.py)

**Work To Do**:

1. Create file `k0/runtime/p03/envelope.py`
2. Implement `P03CycleContext` class per dossier §15.2
3. Add docstrings referencing dossier sections

**Outputs Produced**:

- [ ] File: `k0/runtime/p03/envelope.py`
- [ ] Class: `P03CycleContext`
- [ ] Import works: `from k0.runtime.p03.envelope import P03CycleContext`

**Verification**:

```bash
# Syntax check
python -m py_compile k0/runtime/p03/envelope.py

# Import check
python -c "from k0.runtime.p03.envelope import P03CycleContext; print('OK')"
```

**Blocked By**: None

**Blocks**: Issue N.1.3, N.1.4

---

#### Issue N.1.2 — {Next Issue Title}

{Same structure as above}

---

## Part E: Outputs Manifest (WHAT WE PRODUCED)

> **Fill this section AS YOU COMPLETE each issue**

### E.1 Files Created

| File | Path | Created By | Verified |
|------|------|------------|----------|
| P03CycleContext | [k0/runtime/p03/envelope.py](../../k0/runtime/p03/envelope.py) | Issue 1.1.2 | ✅ imports work |

### E.2 Files Modified

| File | Path | What Changed | Modified By |
|------|------|--------------|-------------|
| Architecture Master | [governance/k0/k0_architecture_master.md](../../governance/k0/k0_architecture_master.md) | Added P03 to Part 2.1 | Issue 0.1.3 |

### E.3 Decisions Made (Not In Original Plan)

| Decision | Options Considered | Chosen | Rationale | Recorded In |
|----------|-------------------|--------|-----------|-------------|
| Use Pydantic over dataclass | Pydantic, dataclass, attrs | Pydantic | Matches existing k0/feedback/envelope.py pattern | Issue 1.1.1 comment |

### E.4 Governance Sync Status (End of Milestone)

```text
$ python -m governance.k0.scripts.sync --report
Date: YYYY-MM-DD
Status: SYNCED
Details: ...
```

### E.5 Test Results (End of Milestone)

```text
$ python -m ward test --path tests/k0/runtime/p03/
Date: YYYY-MM-DD
Result: X passed, 0 failed
```

---

## Part F: Handoff to Next Milestone (WHAT M{N+1} CAN USE)

### F.1 Contracts Now Available

| Contract | Path | Version | Status | Import/Usage |
|----------|------|---------|--------|--------------|
| P03 Pipeline | [k0/contracts/pipelines/p03_consolidation.v1.yaml](../../k0/contracts/pipelines/p03_consolidation.v1.yaml) | v1 | ACTIVE | Read for pipeline_id, stages |

### F.2 Code Entry Points Now Available

| Component | Path | Import Statement | Purpose |
|-----------|------|------------------|---------|
| P03CycleContext | [k0/runtime/p03/envelope.py](../../k0/runtime/p03/envelope.py) | `from k0.runtime.p03.envelope import P03CycleContext` | Immutable cycle header |
| P03BatchEnvelope | [k0/runtime/p03/envelope.py](../../k0/runtime/p03/envelope.py) | `from k0.runtime.p03.envelope import P03BatchEnvelope` | Full envelope state |

### F.3 Storage Surfaces Now Available

| Table | Migration | Path | Key Columns |
|-------|-----------|------|-------------|
| st_epi | 0030_st_epi.py | [k0/db/alembic/versions/0030_st_epi.py](../../k0/db/alembic/versions/0030_st_epi.py) | episode_id, cluster_id, tenant_id |

### F.4 Event Topics Now Registered

| Topic | Schema Path | Producer | Consumer |
|-------|-------------|----------|----------|
| p03.consolidation.triggered.v1 | [k0/contracts/schemas/p03_consolidation_triggered.json](../../k0/contracts/schemas/p03_consolidation_triggered.json) | Scheduler | P03 Runner |

### F.5 Known Gaps for Future Milestones

| Gap | Why Deferred | Needed By | Milestone |
|-----|--------------|-----------|-----------|
| st_learning_queue | Epic 2.3 scope | P06 integration | M3 |
| R5 Dream phase | Dedicated milestone | Full pipeline | M8 |

---

## Appendix: Quick Reference Commands

```bash
# Governance sync check
python -m governance.k0.scripts.sync --report

# Run specific test file
python -m ward test --path tests/k0/runtime/p03/test_envelope.py

# Run all P03 tests
python -m ward test --path tests/k0/runtime/p03/

# Type check
pyright k0/runtime/p03/

# Import verification
python -c "from k0.runtime.p03.envelope import P03BatchEnvelope; print('OK')"

# Apply migrations
alembic upgrade head

# Check migration status
alembic current
```
