# 📚 Step-by-Step Feature Development Guide

**For:** New developers adding features to FamilyOS K1
**Duration:** ~2-3 hours per feature (with ADR approval)
**Last Updated:** October 23, 2025

---

## Overview: The 5-Step Process

```
STEP 1: ADR Discovery & Creation
    ↓
STEP 2: Contract Definition
    ↓
STEP 3: Write Implementation Code
    ↓
STEP 4: Write Tests
    ↓
STEP 5: Document & Update Diagrams
    ↓
Ready for PR! 🎉
```

**⚠️ CRITICAL:** Each step must be complete before moving to the next. Do NOT skip steps.

---

## STEP 1: ADR Discovery & Creation (30 min)

### What is an ADR?

**ADR = Architecture Decision Record**
A document that explains:

- What problem you're solving
- Why you chose this approach
- What trade-offs exist

### 1.1: Search for Existing ADRs

Go to: `docs/architecture/decisions/`

```powershell
# Open this folder in VS Code
code docs/architecture/decisions/
```

Look for files that match your feature. Examples:

- Adding agent scheduling? → Search for `agent`, `scheduling`, `lifecycle`
- Adding a new protocol? → Search for `protocol`, `validation`
- Adding observability? → Search for `metrics`, `tracing`, `logging`

**If you find a matching ADR:**

- Open it and read the `Decision` section
- Check if it says `ACCEPTED` or `IMPLEMENTED` (status at top)
- If yes → You can skip GATE 1 and move to Step 2
- If no (says REJECTED/DEPRECATED) → Talk to team lead

**If you DON'T find a matching ADR:**

- Continue to Step 1.2

### 1.2: Create a New ADR

1. **Open the template:**

   ```powershell
   code docs/architecture/decisions/0000-template.md
   ```

2. **Copy the template and create your ADR:**
   - Find the highest numbered ADR: e.g., `0050-something.md`
   - Create next number: `0051-your-feature-name.md`
   - Example: `0051-k1-agent-scheduling.md`

3. **Fill in each section:**

```markdown
# ADR 0051: K1 Agent Scheduling System

## Status: PROPOSED
(Change to ACCEPTED after team approves)

## Problem
What is the issue? Why do we need this?

Example:
"K1 agents currently run continuously without lifecycle management.
This wastes resources. We need a scheduling system to manage
agent lifecycle (startup, idle, shutdown)."

## Alternatives Considered
What other approaches did you think about?

Example:
1. **Always-on agents** - Simple but wasteful
2. **Manual scheduling** - Requires human intervention
3. **Automatic scheduling with state machine** - Complex but efficient ✅

## Decision
What approach did you choose? Why?

Example:
"We will implement an automatic scheduling system using a state
machine (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED).
This is efficient and follows established patterns (Actor Model)."

## Consequences
What are the trade-offs?

Example:
- ✅ Resource efficient
- ✅ Scalable to 1000+ agents
- ❌ More complex code
- ❌ Requires monitoring
```

4. **Save the file** (don't commit yet)

### 1.3: Get Team Approval

Post in team chat or discussion:

```
"I created ADR 0051 for [feature].
Please review: docs/architecture/decisions/0051-your-feature.md"
```

Wait for at least 1 approval comment. Look for: ✅ LGTM (Looks Good To Me)

**Once approved:**

- Update status to `ACCEPTED` in ADR file
- Note down your ADR number (e.g., `0051`)
- Move to STEP 2 ✅

---

## STEP 2: Contract Definition (45 min)

### What is a Contract?

A contract defines:

- **What data** your feature accepts (input schemas)
- **What data** your feature returns (output schemas)
- **What endpoints/APIs** exist
- **What rules** must be enforced

### 2.1: Check Existing Contracts

Go to: `k1/contracts/`

```powershell
code k1/contracts/
```

You'll see folders:

- `api/` → API specifications
- `jsonschema/` → Data structure definitions
- `policy/` → Business rules
- `observability/` → Metrics/logging schemas

**Look for:**

- Does a schema already exist for your feature's data?
- Does an API spec exist?

### 2.2: Create Data Schema (if needed)

If your feature needs data structures, create a JSON Schema file.

**File location:** `k1/contracts/jsonschema/[your-feature].schema.json`

**Example:** `k1/contracts/jsonschema/agent-schedule.schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Agent Schedule Request",
  "description": "Request to schedule an agent for execution",
  "type": "object",
  "properties": {
    "agent_id": {
      "type": "string",
      "description": "Unique agent identifier"
    },
    "schedule_time": {
      "type": "string",
      "format": "date-time",
      "description": "When to start the agent (ISO 8601)"
    },
    "max_duration_seconds": {
      "type": "integer",
      "minimum": 1,
      "description": "Maximum execution time"
    }
  },
  "required": ["agent_id", "schedule_time"]
}
```

### 2.3: Create API Specification (if needed)

If your feature has endpoints, define them in OpenAPI format.

**File location:** `k1/contracts/api/[your-feature].yaml`

**Example:** `k1/contracts/api/agent-scheduler.yaml`

```yaml
openapi: 3.0.0
info:
  title: Agent Scheduler API
  version: 1.0.0
  description: Schedule K1 agents for execution

paths:
  /agents/{agent_id}/schedule:
    post:
      summary: Schedule an agent
      parameters:
        - name: agent_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "../jsonschema/agent-schedule.schema.json"
      responses:
        "200":
          description: Agent scheduled successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  schedule_id:
                    type: string
                  status:
                    type: string
                    enum: [scheduled, running, completed]
```

### 2.4: Validate Contracts

Run the contract validator:

```powershell
cd d:\familyos
python k0/automation/lint_schemas.py --validate
```

Expected output:

```
✅ All schemas valid
✅ All API specs valid
```

If errors appear, fix them and run again.

### 2.5: Update VERSION

Edit: `k1/contracts/VERSION`

Increment the version number:

```
# Before
version = "1.2.3"

# After (bump minor or patch)
version = "1.2.4"
```

**Move to STEP 3 ✅**

---

## STEP 3: Write Implementation Code (60 min)

### 3.1: Choose Your Layer

K1 has 5 layers. Place your code in the appropriate layer:

| Layer | Folder | Purpose |
|-------|--------|---------|
| L1 Input | `k1/l1_input/` | API requests, webhooks |
| L2 Orchestration | `k1/l2_orchestration/` | Coordination logic |
| L3 Execution | `k1/l3_execution/` | Core business logic |
| L4 Ingress/Runtime | `k1/l4_ingress/`, `k1/l4_runtime/` | Runtime services |
| L5 Infrastructure | `k1/l5_infrastructure/` | Low-level infrastructure |

**Example:** Agent scheduling logic → `k1/l2_orchestration/`

### 3.2: Create Your Module

Create a new Python file:

```powershell
# Example
New-Item -Path k1/l2_orchestration/agent_scheduler.py -ItemType File
```

### 3.3: Write Code with Requirements

**MUST HAVE:**

1. ✅ ADR reference in comment
2. ✅ `cognitive_trace_id` for tracing
3. ✅ Type hints
4. ✅ Docstrings
5. ✅ Structured logging
6. ❌ NO `time.sleep()` or `asyncio.sleep()`
7. ❌ NO mock implementations

**Example Code:**

```python
"""
Agent scheduler module.

References: ADR-0051-k1-agent-scheduling
"""

import logging
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ScheduleRequest:
    """Request to schedule an agent."""
    agent_id: str
    schedule_time: datetime
    max_duration_seconds: int


class AgentScheduler:
    """
    Manages agent lifecycle scheduling.

    Implements the state machine from ADR-0051:
    PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
    """

    def __init__(self):
        self.scheduled_agents = {}

    def schedule_agent(
        self,
        request: ScheduleRequest,
        cognitive_trace_id: str
    ) -> dict:
        """
        Schedule an agent for execution.

        Args:
            request: Schedule request with agent details
            cognitive_trace_id: Trace ID for observability

        Returns:
            Schedule response with schedule_id and status

        References:
            ADR-0051: Agent Scheduling System
        """
        logger.info(
            "Scheduling agent",
            extra={
                "trace_id": cognitive_trace_id,
                "agent_id": request.agent_id,
                "schedule_time": request.schedule_time.isoformat()
            }
        )

        # Your implementation here
        schedule_id = f"sched_{request.agent_id}_{int(datetime.now().timestamp())}"

        self.scheduled_agents[schedule_id] = {
            "agent_id": request.agent_id,
            "status": "PENDING",
            "scheduled_at": datetime.now().isoformat()
        }

        logger.info(
            "Agent scheduled successfully",
            extra={
                "trace_id": cognitive_trace_id,
                "schedule_id": schedule_id
            }
        )

        return {
            "schedule_id": schedule_id,
            "status": "PENDING"
        }
```

### 3.4: Check Contract Compliance

Review your code:

- Does it accept data matching your schema? ✅
- Does it return data matching your schema? ✅
- Does it implement all API endpoints? ✅

If NO → Update contracts in STEP 2 and validate again.

**Move to STEP 4 ✅**

---

## STEP 4: Write Tests (60 min)

### 4.1: Understand WARD Framework

WARD is FamilyOS's testing framework. Key principles:

- ✅ **Real components** - Not mocks
- ✅ **Integration tests** - Test whole workflows
- ✅ **Performance budgets** - Track latencies

### 4.2: Create Test File

Create: `tests/k1/l2_orchestration/test_agent_scheduler.py`

```powershell
New-Item -Path tests/k1/l2_orchestration/test_agent_scheduler.py -ItemType File
```

### 4.3: Write Tests

```python
"""
Tests for agent scheduler module.

References: ADR-0051-k1-agent-scheduling
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from k1.l2_orchestration.agent_scheduler import AgentScheduler, ScheduleRequest


@pytest.fixture
def scheduler():
    """Fixture: Create a fresh scheduler for each test."""
    return AgentScheduler()


class TestAgentScheduler:
    """Test suite for AgentScheduler."""

    def test_schedule_agent_success(self, scheduler):
        """Test: Successfully schedule an agent."""
        # Setup
        future_time = datetime.now() + timedelta(hours=1)
        request = ScheduleRequest(
            agent_id="agent_001",
            schedule_time=future_time,
            max_duration_seconds=3600
        )

        # Execute
        response = scheduler.schedule_agent(
            request,
            cognitive_trace_id="trace_123"
        )

        # Assert
        assert response["status"] == "PENDING"
        assert "schedule_id" in response
        assert response["schedule_id"].startswith("sched_")

    def test_schedule_agent_with_valid_trace_id(self, scheduler):
        """Test: Trace ID is included in logging."""
        future_time = datetime.now() + timedelta(hours=1)
        request = ScheduleRequest(
            agent_id="agent_002",
            schedule_time=future_time,
            max_duration_seconds=1800
        )

        # Execute with specific trace ID
        response = scheduler.schedule_agent(
            request,
            cognitive_trace_id="trace_xyz_789"
        )

        # Assert - response should be valid
        assert response is not None
        assert len(scheduler.scheduled_agents) > 0

    def test_multiple_agents_scheduled(self, scheduler):
        """Test: Multiple agents can be scheduled."""
        future_time = datetime.now() + timedelta(hours=1)

        # Schedule 3 agents
        for i in range(3):
            request = ScheduleRequest(
                agent_id=f"agent_{i:03d}",
                schedule_time=future_time,
                max_duration_seconds=3600
            )
            scheduler.schedule_agent(request, f"trace_{i}")

        # Assert all scheduled
        assert len(scheduler.scheduled_agents) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 4.4: Run Tests

```powershell
# Run all tests for your module
python -m ward test --path tests/k1/l2_orchestration/ --search "agent_scheduler"

# Or with pytest
python -m pytest tests/k1/l2_orchestration/test_agent_scheduler.py -v
```

Expected output:

```
test_schedule_agent_success ✅ PASSED
test_schedule_agent_with_valid_trace_id ✅ PASSED
test_multiple_agents_scheduled ✅ PASSED

===== 3 passed in 0.15s =====
```

**If tests fail:**

1. Read the error message
2. Fix the bug in your implementation code
3. Run tests again until all pass ✅

**Move to STEP 5 ✅**

---

## STEP 5: Document & Update Diagrams (30 min)

### 5.1: Create Memory Entry

Memory is a knowledge base that tracks decisions.

```python
# Open Python terminal or script
from mcp_memory import mem_write, mem_link

# Create memory entry
memory_id = mem_write(
    project="k1_intelligence",
    title="Agent Scheduler Implementation - ADR-0051",
    content="""
    **Feature**: K1 Agent Lifecycle Scheduling
    **ADR**: ADR-0051-k1-agent-scheduling (ACCEPTED)

    **Problem Solved**:
    - K1 agents ran continuously without lifecycle management
    - Wasted resources and didn't scale

    **Solution Implemented**:
    - State machine: PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
    - Automatic scheduling based on demand
    - Resource-aware resource allocation

    **Files Created/Modified**:
    - k1/l2_orchestration/agent_scheduler.py (NEW)
    - k1/contracts/jsonschema/agent-schedule.schema.json (NEW)
    - k1/contracts/api/agent-scheduler.yaml (NEW)
    - tests/k1/l2_orchestration/test_agent_scheduler.py (NEW)

    **Tests**: 3 tests created, all passing ✅
    - test_schedule_agent_success
    - test_schedule_agent_with_valid_trace_id
    - test_multiple_agents_scheduled

    **Performance**:
    - Schedule latency: ~10ms (P95)
    - Budget: 50ms ✅

    **Validated With**:
    - Contract validation: ✅
    - Test coverage: ✅
    - Code review: Pending
    """,
    tags=["k1_agent_fabric", "scheduling", "lifecycle", "implementation"]
)

print(f"Memory ID: {memory_id}")
```

### 5.2: Update Architecture Diagrams (Optional)

If your feature changes the architecture, update the relevant diagram:

```powershell
# Find relevant diagram
Get-ChildItem architecture_diagrams/k1/ -Filter "*.mmd"

# Example: agent lifecycle diagram
code architecture_diagrams/k1/agent_lifecycle.mmd
```

If you updated the diagram, validate it:

```python
from mcp_mmd import mmd_ingest, mmd_validate

# Ingest the diagram
diagram_id = mmd_ingest("d:/familyos/architecture_diagrams/k1/agent_lifecycle.mmd")

# Validate it
mmd_validate(diagram_id)
# Should show: ✅ Diagram valid
```

---

## STEP 6: Open a Pull Request (15 min)

### 6.1: Commit Your Changes

```powershell
cd d:\familyos

# Check what you changed
git status

# Stage files
git add docs/architecture/decisions/0051-*.md
git add k1/l2_orchestration/agent_scheduler.py
git add k1/contracts/jsonschema/agent-schedule.schema.json
git add k1/contracts/api/agent-scheduler.yaml
git add tests/k1/l2_orchestration/test_agent_scheduler.py
git add k1/contracts/VERSION

# Commit
git commit -m "feat: Implement K1 agent scheduling system (ADR-0051)

- Add agent lifecycle state machine
- Create scheduler module in L2 orchestration
- Define contracts for schedule requests/responses
- Add comprehensive test coverage (3 tests)
- Update contracts VERSION

References: ADR-0051-k1-agent-scheduling
Fixes: #<issue-number>"
```

### 6.2: Push to Branch

```powershell
# Create feature branch
git checkout -b feature/0051-agent-scheduling

# Push
git push origin feature/0051-agent-scheduling
```

### 6.3: Open PR on GitHub

1. Go to: `https://github.com/Pkansagra-hub/family-os`
2. Click "New Pull Request"
3. Base: `develop`, Compare: `feature/0051-agent-scheduling`
4. Fill PR description:

```markdown
# Feature: K1 Agent Scheduling System

## Overview
Implements automatic agent lifecycle scheduling to manage resource efficiency.

## Related
- Closes #123 (if applicable)
- ADR: ADR-0051-k1-agent-scheduling (ACCEPTED)

## Changes
- ✅ Agent scheduler module (L2 orchestration)
- ✅ JSON schema for schedule requests
- ✅ OpenAPI specification for scheduler API
- ✅ 3 integration tests, all passing
- ✅ Contracts validated
- ✅ Memory documented

## Tests
```bash
python -m ward test --path tests/k1/l2_orchestration/
# 3 tests PASSED ✅
```

## Performance

- Schedule latency: ~10ms (P95)
- Performance budget: 50ms ✅

## Architecture Impact

- Adds L2 orchestration layer for agent scheduling
- No breaking changes to existing APIs
- See ADR-0051 for detailed decision rationale

```

5. Click "Create Pull Request"

### 6.4: Review Process

Wait for:
- ✅ Code review approval
- ✅ Tests passing
- ✅ No conflicts

Once approved: Merge and delete branch 🎉

---

## Checklist: Before Each Step

### Before STEP 1 ✅
- [ ] Know what feature you're building
- [ ] Talk to team about the idea
- [ ] Have a GitHub issue or epic reference

### Before STEP 2 ✅
- [ ] ADR created and approved
- [ ] ADR status set to `ACCEPTED`
- [ ] ADR number noted

### Before STEP 3 ✅
- [ ] Contracts created and validated
- [ ] Contracts VERSION updated
- [ ] Understand which K1 layer to use

### Before STEP 4 ✅
- [ ] Implementation code complete
- [ ] Code follows patterns (trace_id, docstrings, logging)
- [ ] No `time.sleep()` or `asyncio.sleep()` used
- [ ] Contract compliance verified

### Before STEP 5 ✅
- [ ] All tests passing
- [ ] Test coverage reasonable
- [ ] Performance within budget

### Before PR ✅
- [ ] Memory entry created
- [ ] Diagrams updated (if needed)
- [ ] All files committed
- [ ] Branch pushed

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Contract validation fails** | Run `python k0/automation/lint_schemas.py --validate --fix` |
| **Tests fail** | Run `python -m pytest -vv` for detailed output |
| **Can't find which layer** | Ask in team chat or check `docs/k1_module_analysis.md` |
| **ADR template not clear** | Read existing ADRs in `docs/architecture/decisions/` |
| **Git conflicts** | Run `git pull origin develop` then resolve conflicts |
| **Performance slow** | Profile with `py-spy`, check for blocking I/O |

---

## Example: Complete Feature (15 min walkthrough)

**Feature:** Add K1 agent health monitoring

### STEP 1: ADR
```markdown
# ADR-0052: K1 Agent Health Monitoring

## Problem
Agents fail silently. No way to know if an agent is healthy.

## Decision
Add health check endpoints and heartbeat monitoring.

## Consequences
- Can detect agent failures early
- Requires additional logging
```

### STEP 2: Contracts

```json
// health-check.schema.json
{
  "type": "object",
  "properties": {
    "agent_id": {"type": "string"},
    "status": {"enum": ["HEALTHY", "DEGRADED", "FAILED"]},
    "last_heartbeat": {"type": "string", "format": "date-time"}
  }
}
```

### STEP 3: Code

```python
# k1/l2_orchestration/health_monitor.py
class HealthMonitor:
    def check_agent_health(self, agent_id, cognitive_trace_id):
        """Check if agent is healthy."""
        # Implementation
        pass
```

### STEP 4: Tests

```python
def test_check_agent_health():
    monitor = HealthMonitor()
    response = monitor.check_agent_health("agent_001", "trace_123")
    assert response["status"] in ["HEALTHY", "DEGRADED", "FAILED"]
```

### STEP 5: Memory + PR

- Create memory entry
- Open PR with all changes
- Team reviews and approves

**Done! 🎉**

---

## Getting Help

- **Questions about ADR?** → Read `docs/architecture/decisions/0000-template.md`
- **Questions about contracts?** → Read `k1/contracts/README.md`
- **Questions about testing?** → Read `.github/instructions/testing-requirements.instructions.md`
- **Questions about architecture?** → Read `docs/whiteboard.md`
- **Still stuck?** → Ask in team chat with your ADR link

---

**Good luck! You've got this! 🚀**
