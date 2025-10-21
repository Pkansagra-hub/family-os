# 🧭 K1 Intelligence Module — Copilot Rules of Engagement

**K1 is the core agentic orchestrator kernel: production-ready, research-grounded, zero-tolerance for mediocrity.**

---

## 🚫 Zero-Tolerance Rules (Non-Negotiable)

- **NO MD FILES UNLESS REQUIRED** — Do NOT create any Markdown files that are not explicitly requested or mandatory (ADRs, API docs, etc.). No completion reports, guides, analysis docs, or summary files.
- **No auto-generated Markdown** — Create .md files ONLY when explicitly requested
- **No simulation code** — No `asyncio.sleep()`, `time.sleep()`, mock delays, or playground patterns
- **No mock theater** — Use real components with WARD; never fake functionality
- **ADR is mandatory** — All code changes require contract/ADR review FIRST or create ADRs before proceeding
- **Ask, don't assume** — When unclear, request clarification rather than guessing
- **Violation = PR rejection** — Immediate rejection for simulation code, excessive docs, or missing ADRs

---

## 1️⃣ ADR Governance Checklist

**BEFORE writing ANY code, documentation, or tests:**

- [ ] Read relevant contracts for change scope
- [ ] Read ADR Master Reference (`docs/ADR_MASTER_REFERENCE.md`)
- [ ] Identify all relevant ADRs in `docs/architecture/decisions/`
- [ ] Verify alignment with existing contracts + ADRs
- [ ] Flag any conflicts immediately
- [ ] Reference ADR numbers in code comments + commit messages
- [ ] If ADR missing/outdated → **CREATE/UPDATE before coding** (no exceptions)

**Memory + Knowledge Graph Integration:**
- `mem_find(query="master reference K1", project="k1_intelligence")` — discover context
- `mem_read_many(ids=[...])` — hydrate memories linked to relevant ADRs
- `kg_search(term, diagram?)` — navigate architecture relationships
- `mem_write(project="k1_intelligence", ...)` — log decisions + outcomes after work

---

## 2️⃣ Universal Task Workflow (3 Phases)

### **Before Work**
- Read ADRs + contracts (mandatory — see checklist above)
- Review `docs/whiteboard.md` (21K spec), `docs/k1_module_analysis.md` (52 modules)
- Check `architecture_diagrams/` for relevant Mermaid diagrams
- Load diagrams: `mmd_ingest(path)`, validate: `mmd_validate(diagram_id)`
- If missing: ADR? Diagram? → Create before coding

### **During Work**
- Follow architecture patterns: Actor Model, MPST, Capabilities, SEDA, Saga
- Respect module boundaries from `k1_module_analysis.md`
- Use FlatBuffers for serialization; validate MPST protocols
- No simulation code — use real components only
- Continuously verify ADR compliance as you implement
- Add `cognitive_trace_id` to all operations

### **After Work**
- Update architecture diagrams if structure changed
- Document decisions in ADRs with full rationale
- Run WARD tests: `python -m ward test --path tests/`
- Validate diagrams: `mmd_validate(diagram_id)`
- Update relevant docs in `docs/`
- Record diagram IDs in `docs/development/mmd-diagram-usage.md`
- Create memory entry: `mem_write(project="k1_intelligence", title, content, tags?)`

---

## 3️⃣ K1 Architecture Overview

**Core Vision:** Production-ready agentic orchestrator managing agent lifecycles, multi-agent coordination, adaptive learning, with strict performance/safety guarantees.

**5 Core Components:**
- 🤖 **Agent Fabric** — Lifecycle FSM (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
- 🔄 **Orchestrator Core** — 3-phase coordination (Negotiation → Selection → Execution)
- 📋 **Planner Agent** — 4-stage pipeline (Sketch → Expand → Validate → Commit)
- 🎯 **Protocol Monitor** — MPST/Scribble validation for 6 protocols
- 🧠 **Learning Loop** — Feedback signals + drift detection + hot-reload

**Architecture Built On:** Actor Model (Hewitt 1973), MPST (Honda 2008), Capabilities (Dennis 1966), SEDA (Welsh 2001), Saga Pattern (Garcia-Molina 1987), Contract Net (Smith 1980)

**Module Structure:** 52 modules, 758 files, 5 layers (see `docs/k1_module_analysis.md`)

**Performance Budgets (P95):**
| Metric | Budget | Current | Status |
|--------|--------|---------|--------|
| TTFT | 150ms | 140ms | ✅ |
| E2E Latency | 2000ms | 1850ms | ✅ |
| Memory | 500MB | 450MB | ✅ |

**Reference Docs:**
- `docs/whiteboard.md` — 21K-line spec (complete design)
- `docs/k1_module_analysis.md` — 52 modules breakdown
- `architecture_diagrams/` — 11 validated Mermaid diagrams

---

## 4️⃣ Development Standards

### Python Standards
- **PEP 8** — Style guide, type hints, Google-style docstrings
- **Code organization** — Clear naming, organized imports (stdlib → third-party → local)
- **Error handling** — Explicit exceptions, context in errors, recovery paths, structured logging
- See *Appendix A: Code Organization Example*

### Git Workflow
- **Branch naming:** `feature/<issue>-<desc>`, `fix/<issue>-<desc>`, `docs/<desc>`, `refactor/<desc>`, `test/<desc>`
- **PR requirements:** Description + architecture impact + diagram updates + ADR reference + WARD tests + performance notes + docs updates
- **PR Checklist:** See *Appendix B: PR Standards*

### Testing (WARD Framework)
- **Philosophy:** Integration > unit, real components only, comprehensive coverage, performance validation
- **No mock theater** — Use real implementations with WARD fixtures
- **Test organization:** See `tests/` structure in *Appendix C: Test Structure*
- **Run tests:** `python -m ward test --path tests/`
- See *Appendix D: WARD Test Example*

### Observability
- **Metrics** — Export Prometheus counters, histograms, gauges for all components
- **Tracing** — Add `cognitive_trace_id` to all operations; use OpenTelemetry spans
- **Logging** — Structured logs with context; use structlog
- See *Appendix E: Metrics + Tracing Snippets*

### Security & Privacy
- **Least privilege** — Agents get minimal capabilities
- **Capability-based access** — Use capabilities, not ambient authority
- **Privacy bands** — Respect GREEN/AMBER/RED classifications
- **Audit logging** — Log sensitive operations with trace_id
- **PII protection** — Redact PII in logs/metrics
- See *Appendix F: Security Patterns*

### Configuration & Environment
- **Config files** — `k1/config/*.yml` (YAML format)
- **Environment variables:** `K1_ENV`, `K1_LOG_LEVEL`, `K1_METRICS_PORT`, `K1_TRACE_ENABLED`
- See *Appendix G: Config Example*

---

## 5️⃣ Playbooks: MCP Toolchain

### Mermaid Diagrams (MMD)
- **Ingest:** `mmd_ingest(<absolute_path>)` before working
- **Validate:** `mmd_validate(<diagram_id>)` to check syntax
- **Summarize:** `mmd_summary(<diagram_id>)` for overview
- **Navigate:** `mmd_neighbors`, `mmd_paths` for deep dives
- **Standards:** Naming `k1_<component>_<type>.mmd`, include purpose + research citations, pass validation before commit
- **Log usage:** Record diagram IDs in `docs/development/mmd-diagram-usage.md`

### Knowledge Graph (KG)
- **Ingest:** `kg_ingest(path, alias?)` for diagrams
- **Query:** `kg_summary(<diagram_id>)`, `kg_neighbors(<diagram_id>, <node_id>)`
- **Search:** `kg_search(<term>, diagram?)`
- **Enrich:** `kg_add_node`, `kg_add_edge`, `kg_add_memory`
- **Maintenance:** Reuse aliases, record IDs in `docs/development/kg-mcp-usage.md`

### Memory MCP (Optional)
- **Write:** `mem_write(project="k1_intelligence", title, content, tags?)`
- **Search:** `mem_find(query, project="k1_intelligence")`
- **Read:** `mem_read_many(ids=[...])`
- **Link:** `mem_link(src_id, dest_id, relation)`
- **Best practices:** Use project key `k1_intelligence`, tag with module names, link to ADRs/diagrams

---

## 6️⃣ Quick Reference

### Repository Structure
- ✅ **ALLOWED at root:** README.md, LICENSE, .gitignore, pyproject.toml, setup.py
- ❌ **FORBIDDEN:** Loose .md files, .py files, scripts, test files

### Common Issues & Solutions
| Issue | Solution |
|-------|----------|
| Diagram won't validate | Check syntax with `mmd_validate`, fix special chars, avoid keywords |
| WARD tests failing | Initialize fixtures properly, check async/await, verify test isolation, run `--verbose` |
| Performance budget exceeded | Profile with `py-spy`, check for blocking I/O, verify KV cache hit rate (~75%) |
| ADR unclear | Use template in `docs/architecture/decisions/0000-template.md`, include problem/alternatives/decision/consequences |

### Useful Commands
```bash
# Testing
python -m ward test --path tests/
python -m ward test --search "orchestrator"

# Profiling
py-spy top --pid <pid>

# Metrics
curl localhost:9090/metrics
```

### Getting Help
- **Architecture:** `docs/whiteboard.md` (21K spec)
- **Modules:** `docs/k1_module_analysis.md` (52 modules)
- **Diagrams:** `architecture_diagrams/` (11 validated)
- **Patterns:** Research citations in diagram headers
- **Performance:** Section 3 budgets

---

<details>
<summary><strong>Appendix A: Code Organization Example</strong></summary>

```python
"""
Module: k1.agent_fabric.lifecycle
Purpose: Agent lifecycle FSM with 6 states

Research: Actor Model (Hewitt 1973), Capabilities (Dennis & Van Horn 1966)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict
import asyncio

# Constants
MAX_AGENTS_PER_SESSION = 3
SUPERVISOR_CHECK_INTERVAL_MS = 1000

class AgentState(Enum):
    """Agent lifecycle states"""
    PENDING = "PENDING"
    WARMING = "WARMING"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    DRAINING = "DRAINING"
    TERMINATED = "TERMINATED"

@dataclass
class Agent:
    """Agent instance with lifecycle management"""
    agent_id: str
    state: AgentState
    memory_mb: int
```

</details>

<details>
<summary><strong>Appendix B: PR Standards Checklist</strong></summary>

- [ ] Architecture diagrams updated (if applicable)
- [ ] ADR created/updated (if architectural change)
- [ ] WARD tests written and passing
- [ ] Documentation updated in `docs/`
- [ ] Performance budgets respected
- [ ] No simulation code (zero tolerance policy)
- [ ] Code follows K1 patterns and conventions
- [ ] Observability added (metrics, tracing, logging)

**PR description must include:**
1. What changed, why, and how
2. Affected modules from `k1_module_analysis.md`
3. Updated .mmd files (if structure changed)
4. ADR reference (if architectural change)
5. WARD test results (all passing)
6. Performance impact notes

</details>

<details>
<summary><strong>Appendix C: Test Structure</strong></summary>

```
tests/
├── agent_fabric/
│   ├── test_lifecycle_fsm.py
│   ├── test_supervisor.py
│   └── test_hiring_score.py
├── orchestrator/
│   ├── test_3phase.py
│   ├── test_negotiation.py
│   └── test_selection.py
├── planner/
│   ├── test_4stage_pipeline.py
│   ├── test_validation.py
│   └── test_fallbacks.py
├── protocol_monitor/
│   ├── test_mpst_validation.py
│   └── test_timeout_enforcement.py
└── integration/
    ├── test_end_to_end_turn.py
    ├── test_barge_in.py
    └── test_backpressure.py
```

**Philosophy:**
- Integration over unit tests
- Real components only (no mock theater)
- Comprehensive coverage for every feature
- Performance validation in tests

</details>

<details>
<summary><strong>Appendix D: WARD Test Example</strong></summary>

```python
from ward import test, fixture
import asyncio

@fixture
async def orchestrator():
    """Fixture for orchestrator with real agents"""
    orch = Orchestrator(config=test_config)
    await orch.initialize()
    yield orch
    await orch.shutdown()

@test("orchestrator completes 3-phase coordination")
async def _(orch=orchestrator):
    # Test real 3-phase flow
    task = TaskAnnouncement(...)
    result = await orch.coordinate(task)
    assert result.status == "COMPLETED"
    assert result.latency_ms < 250  # Performance validation
```

**Run tests:**
```bash
python -m ward test --path tests/
python -m ward test --path tests/agent_fabric/
python -m ward test --search "orchestrator"
python -m ward test --verbose
```

</details>

<details>
<summary><strong>Appendix E: Metrics + Tracing Snippets</strong></summary>

**Prometheus Metrics:**
```python
from prometheus_client import Counter, Histogram, Gauge

agent_transitions_total = Counter(
    'agent_transitions_total',
    'Total agent state transitions',
    ['from_state', 'to_state']
)

orchestration_latency_ms = Histogram(
    'orchestration_latency_ms',
    'Orchestration latency in milliseconds',
    buckets=[10, 50, 100, 250, 500, 1000, 2000]
)

active_agents = Gauge(
    'active_agents',
    'Number of agents in ACTIVE state'
)
```

**OpenTelemetry Tracing:**
```python
@traced(span_name="orchestrator.3phase")
async def coordinate(self, task: TaskAnnouncement, trace_id: str):
    """3-phase orchestration with tracing"""
    with self.tracer.start_as_current_span("phase1_negotiation"):
        proposals = await self.negotiate(task, trace_id)
```

**Structured Logging:**
```python
import structlog
logger = structlog.get_logger()

logger.info(
    "agent_transition",
    agent_id=agent.id,
    from_state=old_state.value,
    to_state=new_state.value,
    trace_id=trace_id,
    latency_ms=latency
)
```

</details>

<details>
<summary><strong>Appendix F: Security Patterns</strong></summary>

**Capability Checking:**
```python
if not agent.has_capability(Capability.TOOL_CALL):
    raise PermissionError(f"Agent {agent.id} lacks TOOL_CALL capability")
```

**Privacy Band Validation:**
```python
if task.band == PrivacyBand.RED and not arbiter.approve(task):
    raise SecurityError("RED band task requires arbiter approval")
```

**PII Redaction:**
```python
logger.info("user_message", message=redact_pii(text), trace_id=trace_id)
```

**Principles:**
- Least privilege — agents get minimal capabilities
- Capability-based access — use capabilities, not ambient authority
- Privacy bands — respect GREEN/AMBER/RED classifications
- Audit logging — log sensitive operations with trace_id

</details>

<details>
<summary><strong>Appendix G: Configuration Example</strong></summary>

**YAML Config (`k1/config/agent_fabric.yml`):**
```yaml
agent_fabric:
  max_agents_per_session: 3
  supervisor_check_interval_ms: 1000
  state_transitions:
    warming_timeout_ms: 200
    idle_timeout_ms: 60000
    draining_timeout_ms: 5000
  blacklist:
    crash_threshold: 3
    time_window_ms: 600000
    blacklist_duration_ms: 3600000
```

**Environment Variables:**
- `K1_ENV`: `development` | `staging` | `production`
- `K1_LOG_LEVEL`: `DEBUG` | `INFO` | `WARNING` | `ERROR`
- `K1_METRICS_PORT`: Prometheus metrics port (default: 9090)
- `K1_TRACE_ENABLED`: Enable OpenTelemetry tracing

</details>

---

## New Feature Checklist

Before implementing:
- [ ] ADR in `docs/architecture/decisions/`
- [ ] Architecture diagrams updated
- [ ] Module impact analyzed
- [ ] Performance budget defined
- [ ] WARD tests planned (integration > unit)
- [ ] Observability planned (metrics, traces, logs)
- [ ] Security/privacy implications assessed
- [ ] Configuration schema defined
- [ ] Documentation written
- [ ] Zero simulation policy respected

---
