# K1 Module README Template
# Epic 1.4 - Issue 1.4.1 - Architecture Component 5 of 5
# Version: 1.0.0
# Status: DRAFT
# Owner: Architecture Team
# ADR References: ADR-0004c (Module README Template & Auto-Generation)

---

## Overview

**Purpose:** This document defines the standardized README template for all 52 K1 modules.

**Key Features:**
1. 7-section template (Purpose, Architecture, API, Performance, Testing, Dependencies, Development)
2. K1-doc-gen tool (auto-generate READMEs from code metadata)
3. CI enforcement (README staleness checks)
4. Example populated README (agent_registry)

**ADR Reference:** ADR-0004c (Module README Template & Auto-Generation)

---

## Template Structure

Every module README must contain these 7 sections:

1. **Purpose** - What does this module do? Why does it exist?
2. **Architecture** - Layer, dependencies, Actor Model patterns
3. **API** - Public interfaces (classes, functions, messages)
4. **Performance** - Latency targets, benchmarks, optimizations
5. **Testing** - Test coverage, test files, test commands
6. **Dependencies** - Layer dependencies, third-party packages
7. **Development** - Setup, local development, debugging tips

---

## Section 1: Purpose

### Template

```markdown
# Module Name

## Purpose

Brief description of what this module does (1-2 sentences).

### Responsibilities

- Responsibility 1
- Responsibility 2
- Responsibility 3

### Non-Responsibilities

- What this module does NOT do (avoid scope creep)

### Research Foundation

- Citation 1 (e.g., Actor Model - Hewitt 1973)
- Citation 2 (e.g., Finite State Machines - Moore 1956)
```

### Example (Agent Registry)

```markdown
# Agent Registry

## Purpose

Agent Registry manages agent lifecycle (6-state FSM) and tracks active agents per session.

### Responsibilities

- Hire agents (PENDING → WARMING → ACTIVE)
- Terminate agents (ACTIVE → DRAINING → TERMINATED)
- Track agent blacklist (crash count, time window)
- Supervise agent health (restart policies)

### Non-Responsibilities

- Does NOT execute agent logic (delegates to Layer 3)
- Does NOT store agent state (delegates to SessionState)

### Research Foundation

- Actor Model (Hewitt 1973) - Message-passing, supervision
- Finite State Machines (Moore 1956) - 6-state lifecycle FSM
```

---

## Section 2: Architecture

### Template

```markdown
## Architecture

### Layer

- **Layer:** Layer N (Layer Name)
- **Module Path:** `k1/module/submodule.py`

### Dependencies

**Can import:**
- Layer X modules
- Layer Y modules

**Cannot import:**
- Layer Z modules (enforced by import-linter)

### Actor Model Patterns

**Mailbox:**
- Capacity: N messages
- Overflow policy: drop_oldest | reject_new

**Supervision:**
- Supervisor: module/supervisor
- Restart policy: one_for_one | one_for_all
- Max restarts: N (within time_window_ms)

**Message Types:**
- Incoming: MessageType1, MessageType2
- Outgoing: MessageType3, MessageType4
```

### Example (Agent Registry)

```markdown
## Architecture

### Layer

- **Layer:** Layer 2 (Orchestration)
- **Module Path:** `k1/orchestration/agent_registry.py`

### Dependencies

**Can import:**
- Layer 5 (Infrastructure): event_bus, metrics, logging

**Cannot import:**
- Layer 3 (Execution): Agent implementations (enforced by import-linter)

### Actor Model Patterns

**Mailbox:**
- Capacity: 100 messages
- Overflow policy: drop_oldest

**Supervision:**
- Supervisor: orchestration/agent_supervisor
- Restart policy: one_for_one
- Max restarts: 3 (within 600,000ms)

**Message Types:**
- Incoming: HireAgentMessage, TerminateAgentMessage
- Outgoing: AgentHiredEvent, AgentTerminatedEvent
```

---

## Section 3: API

### Template

```markdown
## API

### Classes

#### ClassName

**Purpose:** Brief description

**Constructor:**
```python
def __init__(self, param1: Type1, param2: Type2):
    """Docstring"""
```

**Public Methods:**

##### method_name

```python
async def method_name(self, arg1: Type1) -> ReturnType:
    """
    Brief description

    Args:
        arg1: Description

    Returns:
        Description

    Raises:
        ExceptionType: When condition occurs
    """
```

### Messages

#### MessageType

```python
@dataclass
class MessageType:
    field1: Type1
    field2: Type2
```

### Events

#### EventType

```python
@dataclass
class EventType:
    field1: Type1
    field2: Type2
```
```

### Example (Agent Registry)

```markdown
## API

### Classes

#### AgentRegistry

**Purpose:** Manages agent lifecycle and tracks active agents

**Constructor:**
```python
def __init__(self, config: AgentFabricConfig):
    """Initialize AgentRegistry with configuration"""
```

**Public Methods:**

##### hire_agent

```python
async def hire_agent(self, agent_id: str, trace_id: str) -> AgentState:
    """
    Hire agent (transition PENDING → WARMING → ACTIVE)

    Args:
        agent_id: Unique agent identifier
        trace_id: Cognitive trace ID for observability

    Returns:
        AgentState.ACTIVE if successful

    Raises:
        MaxAgentsExceededError: If max_agents_per_session exceeded
        AgentBlacklistedError: If agent is blacklisted
    """
```

##### terminate_agent

```python
async def terminate_agent(self, agent_id: str, trace_id: str) -> AgentState:
    """
    Terminate agent (transition ACTIVE → DRAINING → TERMINATED)

    Args:
        agent_id: Unique agent identifier
        trace_id: Cognitive trace ID for observability

    Returns:
        AgentState.TERMINATED if successful

    Raises:
        AgentNotFoundError: If agent_id not found
    """
```

### Messages

#### HireAgentMessage

```python
@dataclass
class HireAgentMessage:
    agent_id: str
    trace_id: str
```

#### TerminateAgentMessage

```python
@dataclass
class TerminateAgentMessage:
    agent_id: str
    trace_id: str
```

### Events

#### AgentHiredEvent

```python
@dataclass
class AgentHiredEvent:
    agent_id: str
    state: AgentState
    trace_id: str
```

#### AgentTerminatedEvent

```python
@dataclass
class AgentTerminatedEvent:
    agent_id: str
    state: AgentState
    trace_id: str
```
```

---

## Section 4: Performance

### Template

```markdown
## Performance

### Latency Targets (P95)

| Operation | Target (ms) | Current (ms) | Status |
|-----------|-------------|--------------|--------|
| operation1 | N | M | ✅ PASS / ❌ FAIL |
| operation2 | N | M | ✅ PASS / ❌ FAIL |

### Memory Targets

- **Per-session memory:** N KB (soft limit), M KB (hard limit)
- **Total module memory:** X MB

### Optimizations

- Optimization 1: Description
- Optimization 2: Description

### Benchmarks

**Environment:** Python 3.11, asyncio, single-threaded

**Results:**
```
Operation: operation1
  - Mean: N ms
  - P50: M ms
  - P95: X ms
  - P99: Y ms
```
```

### Example (Agent Registry)

```markdown
## Performance

### Latency Targets (P95)

| Operation | Target (ms) | Current (ms) | Status |
|-----------|-------------|--------------|--------|
| hire_agent | 5 | 3 | ✅ PASS |
| terminate_agent | 5 | 2 | ✅ PASS |
| get_agent_state | 2 | 1 | ✅ PASS |

### Memory Targets

- **Per-session memory:** 10 KB (soft limit), 20 KB (hard limit)
- **Total module memory:** 50 MB (max 3 agents/session * 1000 sessions)

### Optimizations

- O(1) agent lookup (dict-based registry, not list)
- Pre-allocated agent state objects (avoid allocations on hot path)
- FlatBuffers serialization for agent state (<1ms)

### Benchmarks

**Environment:** Python 3.11, asyncio, single-threaded

**Results:**
```
Operation: hire_agent
  - Mean: 2.8 ms
  - P50: 2.5 ms
  - P95: 3.2 ms
  - P99: 4.1 ms

Operation: terminate_agent
  - Mean: 1.9 ms
  - P50: 1.8 ms
  - P95: 2.1 ms
  - P99: 2.5 ms
```
```

---

## Section 5: Testing

### Template

```markdown
## Testing

### Test Coverage

- **Unit tests:** N% coverage
- **Integration tests:** M% coverage
- **Total coverage:** X% coverage

### Test Files

- `tests/module/test_unit.py` - Unit tests
- `tests/module/test_integration.py` - Integration tests

### Test Commands

```bash
# Run all tests for this module
python -m ward test --path tests/module/

# Run specific test
python -m ward test --search "test_name"

# Run with coverage
python -m ward test --path tests/module/ --coverage
```

### Key Test Cases

1. **Test Case 1:** Description
2. **Test Case 2:** Description
```

### Example (Agent Registry)

```markdown
## Testing

### Test Coverage

- **Unit tests:** 95% coverage
- **Integration tests:** 88% coverage
- **Total coverage:** 92% coverage

### Test Files

- `tests/orchestration/test_agent_registry_unit.py` - Unit tests (FSM transitions)
- `tests/orchestration/test_agent_registry_integration.py` - Integration tests (end-to-end)
- `tests/integration/test_layer2_orchestration.py` - Layer 2 integration tests

### Test Commands

```bash
# Run all tests for agent_registry
python -m ward test --path tests/orchestration/test_agent_registry_*

# Run FSM transition tests
python -m ward test --search "agent_registry FSM"

# Run with coverage
python -m ward test --path tests/orchestration/ --coverage
```

### Key Test Cases

1. **Hire agent (PENDING → ACTIVE):** Verifies FSM transitions
2. **Terminate agent (ACTIVE → TERMINATED):** Verifies cleanup
3. **Blacklist agent (3 crashes):** Verifies blacklist logic
4. **Max agents per session:** Verifies limit enforcement (3 agents/session)
5. **Supervisor restart:** Verifies restart policy (one_for_one)
```

---

## Section 6: Dependencies

### Template

```markdown
## Dependencies

### Layer Dependencies

**Can import:**
- `k1.layer_name.*` (Layer N)

**Cannot import:**
- `k1.layer_name.*` (Layer M) - enforced by import-linter

### Third-Party Packages

- `package1==version` - Purpose
- `package2==version` - Purpose

### FlatBuffers Schemas

- `schema_name.fbs` - Purpose (if applicable)

### Configuration Files

- `k1/config/module_config.yml` - Module configuration
```

### Example (Agent Registry)

```markdown
## Dependencies

### Layer Dependencies

**Can import:**
- `k1.infrastructure.*` (Layer 5) - event_bus, metrics, logging

**Cannot import:**
- `k1.execution.*` (Layer 3) - Agent implementations (enforced by import-linter)

### Third-Party Packages

- `prometheus_client==0.17.1` - Metrics collection
- `structlog==23.1.0` - Structured logging

### FlatBuffers Schemas

- `agent_state.fbs` - Agent state serialization

### Configuration Files

- `k1/config/agent_fabric.yml` - Agent fabric configuration
```

---

## Section 7: Development

### Template

```markdown
## Development

### Setup

```bash
# Clone repository
git clone https://github.com/org/k1_intelligence.git
cd k1_intelligence

# Install dependencies
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"
```

### Local Development

```bash
# Run module in development mode
python -m k1.module.submodule

# Run with debug logging
K1_LOG_LEVEL=DEBUG python -m k1.module.submodule
```

### Debugging Tips

- Tip 1: How to debug X
- Tip 2: How to debug Y

### Contributing

- Read `docs/development/contribution-guide.md`
- Follow ADR-0004 (52-Module 5-Layer Architecture)
- Write tests (WARD framework)
- Update this README if API changes
```

### Example (Agent Registry)

```markdown
## Development

### Setup

```bash
# Clone repository
git clone https://github.com/org/k1_intelligence.git
cd k1_intelligence

# Install dependencies
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"
```

### Local Development

```bash
# Run agent_registry in development mode
python -m k1.orchestration.agent_registry

# Run with debug logging
K1_LOG_LEVEL=DEBUG python -m k1.orchestration.agent_registry

# Run with metrics server (Prometheus)
K1_METRICS_PORT=9090 python -m k1.orchestration.agent_registry
```

### Debugging Tips

- **Agent lifecycle issues:** Enable DEBUG logging to see FSM transitions
- **Blacklist issues:** Check blacklist state in metrics: `agent_blacklist_total`
- **Performance issues:** Profile with `py-spy top --pid <pid>`

### Contributing

- Read `docs/development/contribution-guide.md`
- Follow ADR-0004 (52-Module 5-Layer Architecture)
- Write tests (WARD framework): `python -m ward test --path tests/orchestration/`
- Update this README if API changes (use k1-doc-gen tool)
```

---

## K1-doc-gen Tool

### Overview

**Purpose:** Auto-generate module READMEs from code metadata (docstrings, type hints, config files).

**Features:**
- Parses Python code (AST parsing)
- Extracts docstrings, type hints, decorators
- Generates README sections 1-7
- Validates against template (7-section structure)
- Updates existing READMEs (merges manual edits)

**ADR Reference:** ADR-0004c (Module README Template & Auto-Generation)

### Usage

```bash
# Generate README for single module
k1-doc-gen generate --module k1.orchestration.agent_registry

# Generate READMEs for all modules
k1-doc-gen generate --all

# Validate existing README
k1-doc-gen validate --module k1.orchestration.agent_registry

# Check staleness (code changed but README not updated)
k1-doc-gen check-stale
```

### Tool Architecture

```python
# File: tools/k1_doc_gen/generator.py

class READMEGenerator:
    """
    Auto-generate module READMEs from code metadata
    """

    def generate(self, module_path: str) -> str:
        """
        Generate README for module

        Steps:
        1. Parse Python code (AST parsing)
        2. Extract docstrings, type hints, decorators
        3. Extract config files (YAML)
        4. Generate 7 sections (Purpose, Architecture, API, Performance, Testing, Dependencies, Development)
        5. Validate against template
        6. Return README markdown
        """
        # 1. Parse code
        tree = ast.parse(self._read_file(module_path))

        # 2. Extract metadata
        classes = self._extract_classes(tree)
        functions = self._extract_functions(tree)
        messages = self._extract_messages(tree)

        # 3. Extract config
        config = self._extract_config(module_path)

        # 4. Generate sections
        purpose = self._generate_purpose_section(tree, config)
        architecture = self._generate_architecture_section(module_path, config)
        api = self._generate_api_section(classes, functions, messages)
        performance = self._generate_performance_section(config)
        testing = self._generate_testing_section(module_path)
        dependencies = self._generate_dependencies_section(tree, config)
        development = self._generate_development_section(module_path)

        # 5. Combine sections
        readme = self._format_readme(purpose, architecture, api, performance, testing, dependencies, development)

        # 6. Validate
        self._validate_readme(readme)

        return readme
```

### Code Metadata Extraction

**Docstrings:**
```python
# File: k1/orchestration/agent_registry.py

class AgentRegistry:
    """
    Manages agent lifecycle (6-state FSM) and tracks active agents

    Responsibilities:
    - Hire agents (PENDING → WARMING → ACTIVE)
    - Terminate agents (ACTIVE → DRAINING → TERMINATED)

    Research: Actor Model (Hewitt 1973), FSM (Moore 1956)
    """

    async def hire_agent(self, agent_id: str, trace_id: str) -> AgentState:
        """
        Hire agent (transition PENDING → WARMING → ACTIVE)

        Args:
            agent_id: Unique agent identifier
            trace_id: Cognitive trace ID

        Returns:
            AgentState.ACTIVE if successful

        Performance: <5ms P95 target
        """
        pass
```

**k1-doc-gen extracts:**
- Class purpose: "Manages agent lifecycle (6-state FSM)"
- Method description: "Hire agent (transition PENDING → WARMING → ACTIVE)"
- Performance target: "<5ms P95 target"
- Research citations: "Actor Model (Hewitt 1973)"

### Configuration Metadata

**Config file:**
```yaml
# File: k1/config/agent_fabric.yml

agent_fabric:
  module_name: "orchestration/agent_registry"
  layer: 2
  max_agents_per_session: 3

  performance:
    hire_agent_target_ms: 5
    terminate_agent_target_ms: 5

  dependencies:
    can_import:
      - "k1.infrastructure.*"
    cannot_import:
      - "k1.execution.*"
```

**k1-doc-gen extracts:**
- Module name: "orchestration/agent_registry"
- Layer: 2
- Performance targets: 5ms (hire_agent), 5ms (terminate_agent)
- Dependencies: can import Layer 5, cannot import Layer 3

### CI Enforcement

**GitHub Actions workflow:**

```yaml
# File: .github/workflows/readme-staleness.yml

name: README Staleness Check

on:
  pull_request:
    branches: [main, develop]

jobs:
  check-readme-staleness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install k1-doc-gen
        run: pip install -e ./tools/k1_doc_gen

      - name: Check README staleness
        run: k1-doc-gen check-stale
        # Fails if any module README is stale (code changed but README not updated)
```

**Staleness Detection:**
- Computes hash of module code (AST tree + docstrings)
- Compares with hash embedded in README (<!-- generated_from: hash -->)
- If hashes differ → README is stale → CI fails

### Manual vs Auto-Generated Content

**k1-doc-gen supports mixed content:**
- Auto-generated sections: Purpose, Architecture, API, Dependencies
- Manual sections: Performance, Testing, Development (require human input)

**Merge Strategy:**
```markdown
<!-- AUTO-GENERATED: DO NOT EDIT -->
# Agent Registry

## Purpose
[Auto-generated from docstrings]
<!-- END AUTO-GENERATED -->

<!-- MANUAL EDIT ALLOWED -->
## Performance

Custom benchmarks go here...
<!-- END MANUAL EDIT -->
```

### Generation Time

**Performance Target:** <10 seconds to generate README for one module

**Benchmark:**
- Parse code (AST): 2s
- Extract metadata: 1s
- Generate sections: 3s
- Validate: 1s
- Total: 7s ✅ PASS

---

## README Template Checklist

Before merging a module, ensure README has:

- [ ] Section 1: Purpose (what, why, responsibilities)
- [ ] Section 2: Architecture (layer, dependencies, Actor Model)
- [ ] Section 3: API (classes, methods, messages, events)
- [ ] Section 4: Performance (latency targets, benchmarks)
- [ ] Section 5: Testing (coverage, test files, key test cases)
- [ ] Section 6: Dependencies (layer deps, third-party packages)
- [ ] Section 7: Development (setup, debugging tips, contributing)
- [ ] Example code blocks (with syntax highlighting)
- [ ] ADR references (links to relevant ADRs)
- [ ] Research citations (if applicable)

---

## Compliance

### ADR References

- **ADR-0004:** 52-Module 5-Layer Architecture
- **ADR-0004c:** Module README Template & Auto-Generation

### Performance Requirements

- **k1-doc-gen generation time:** <10s per module
- **README staleness check:** <5s (CI enforcement)

### Quality Requirements

- **100% of modules have READMEs** (enforced by CI)
- **7-section structure** (enforced by k1-doc-gen validation)
- **Auto-generation preferred** (manual edits allowed for Performance/Testing/Development sections)

---

## Cross-References

### Related Contracts

- **module_manifest.yml:** Defines 52 modules (all require READMEs)
- **layer_dependencies.yml:** Layer dependency rules (documented in Architecture section)
- **ai_agent_classification.yml:** AI agent specifications (documented in Purpose section)

---

## Notes

- **Template is mandatory:** All 52 modules must use 7-section structure
- **Auto-generation preferred:** Use k1-doc-gen tool to generate initial README
- **Manual edits allowed:** Performance, Testing, Development sections may need human input
- **CI enforcement:** README staleness checks block PR merges if code changes but README doesn't
- **Generation time <10s:** Fast enough for CI pipeline (<5% overhead)
