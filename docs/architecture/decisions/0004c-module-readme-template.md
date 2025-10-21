# ADR-0004c: Module README Template & Auto-Generation

**Status:** ✅ **COMPLETED** (2025-10-12)
**Date:** 2025-10-12
**Last Updated:** 2025-10-17 (M2 Context: See ADR-0074 for module metadata schema and extension points)
**Deciders:** K1 Architecture Team
**Technical Story:** Standardize module documentation with auto-generated README templates for all 52+ K1 modules
**Parent ADR:** [ADR-0004: 52-Module 5-Layer Microkernel Architecture](0004-52-module-5-layer-architecture.md)
**Related ADRs:**
- [ADR-0004a: Layer 1-2 Event Bus Communication](0004a-layer1-2-event-bus-communication.md)
- [ADR-0004b: Module Dependency Management](0004b-module-dependency-management.md)
- [ADR-0074 (Pluggable Module System - **NEW M2**)](0074-pluggable-module-system.md)

---

## Executive Summary

K1 has **52+ modules across 5 layers**. Each module needs consistent documentation for maintainability.

**Solution:** **Standardized README.md template + auto-generation tool (`k1-doc-gen`)**.

**Key Features:**
- **Template sections:** Purpose, Architecture, API, Performance, Testing, Dependencies
- **Auto-generation:** Extracts metadata from code (docstrings, imports, metrics)
- **CI enforcement:** PRs blocked if module README missing or outdated
- **Performance:** <10s to generate all 52 module READMEs

**Template Structure:**
```
# Module: k1.execution.agent_registry

## Purpose
What this module does (1-2 sentences)

## Architecture
Layer, dependencies, design patterns

## API
Public classes, functions, usage examples

## Performance Budgets
Latency targets, memory constraints

## Testing
Test coverage, how to run tests

## Dependencies
Required modules (Layer 4, Layer 5)
```

**Auto-Generation Flow:**
```
k1-doc-gen --module k1.execution.agent_registry
  ↓
1. Parse module docstrings (Purpose, Architecture)
2. Extract imports (Dependencies → show Layer 4, Layer 5 imports)
3. Extract public API (classes, functions with docstrings)
4. Extract metrics (Prometheus metrics → Performance)
5. Generate README.md (fill template)
  ↓
Output: k1/execution/agent_registry/README.md
```

---

## Context

### The Challenge

**K1 has 52+ modules (from ADR-0004):**
- **Layer 1:** 4 modules (Input Processing)
- **Layer 2:** 3 modules (Orchestration)
- **Layer 3:** 22 modules (Execution)
- **Layer 4:** 8 modules (Runtime Core)
- **Layer 5:** 19 modules (Infrastructure)

**Problem:**
- **Inconsistent documentation:** Some modules have READMEs, some don't
- **Outdated docs:** READMEs not updated when code changes
- **Hard to onboard:** New developers don't know where to start
- **Manual effort:** Writing READMEs manually is tedious (52 modules × 30min = 26 hours)

**Example: Missing Context**
```
# Developer question: "What does k1.execution.agent_registry do?"
# Without README:
#   1. Read code (500+ lines, time-consuming)
#   2. Guess from module name (ambiguous)
#   3. Ask team (interrupt others)

# With README:
#   1. Read Purpose section (30 seconds)
#   2. Check API examples (2 minutes)
#   3. Start coding (fast onboarding)
```

**Requirement:**
- Standardized README template (consistent structure)
- Auto-generation tool (fast, accurate)
- CI enforcement (prevent outdated docs)
- Low maintenance overhead (<10s to regenerate)

---

## Decision

We adopt a **standardized README.md template** with an **auto-generation tool (`k1-doc-gen`)** that extracts metadata from code.

**Architecture:**

```
┌────────────────────────────────────────────────────────────────────────┐
│                     Module Source Code                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  # File: k1/execution/agent_registry/__init__.py                       │
│  """                                                                    │
│  Module: k1.execution.agent_registry                                   │
│  Purpose: Agent lifecycle registry (hire, fire, lookup)                │
│  Layer: 3 (Execution)                                                  │
│  """                                                                    │
│                                                                          │
│  from k1.runtime.session_state import SessionState  # Layer 4          │
│  from k1.infrastructure.metrics import agent_registry_total  # Layer 5 │
│                                                                          │
│  class AgentRegistry:                                                   │
│      """Agent registry for session-scoped agent tracking"""            │
│      def register(self, agent_id: str):                                │
│          """Register agent in session"""                               │
│          pass                                                           │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ k1-doc-gen --module k1.execution.agent_registry
                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      k1-doc-gen (Auto-Generation Tool)                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Parse module docstring → Extract Purpose, Layer                    │
│  2. Parse imports → Extract Dependencies (Layer 4, Layer 5)            │
│  3. Parse classes/functions → Extract Public API + docstrings          │
│  4. Parse metrics → Extract Prometheus metrics (performance)           │
│  5. Find tests → Extract test coverage (pytest --cov)                  │
│  6. Fill template → Generate README.md                                 │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ Output
                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Generated README.md                                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  # Module: k1.execution.agent_registry                                 │
│                                                                          │
│  ## Purpose                                                             │
│  Agent lifecycle registry (hire, fire, lookup)                         │
│                                                                          │
│  ## Architecture                                                        │
│  - **Layer:** 3 (Execution)                                            │
│  - **Dependencies:** Layer 4 (session_state), Layer 5 (metrics)        │
│                                                                          │
│  ## API                                                                 │
│  ### AgentRegistry                                                      │
│  Agent registry for session-scoped agent tracking                      │
│                                                                          │
│  **Methods:**                                                           │
│  - `register(agent_id: str)` - Register agent in session               │
│                                                                          │
│  ## Performance Budgets                                                 │
│  - `agent_registry_total` - Total registered agents                    │
│                                                                          │
│  ## Testing                                                             │
│  - Coverage: 95%                                                        │
│  - Run: `pytest tests/execution/test_agent_registry.py`                │
│                                                                          │
│  ## Dependencies                                                        │
│  - Layer 4: `k1.runtime.session_state`                                 │
│  - Layer 5: `k1.infrastructure.metrics`                                │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Design

### Component 1: README Template

**File:** `.github/templates/MODULE_README_TEMPLATE.md`

**Purpose:** Standardized template for all module READMEs.

```markdown
# Module: {module_name}

**Layer:** {layer_number} ({layer_name})
**Purpose:** {one_sentence_purpose}
**Status:** {status}  <!-- ✅ STABLE | 🚧 IN PROGRESS | 🔬 EXPERIMENTAL -->

---

## Purpose

{detailed_purpose_2_3_sentences}

**Responsibilities:**
- {responsibility_1}
- {responsibility_2}
- {responsibility_3}

**Out of Scope:**
- {not_responsibility_1}
- {not_responsibility_2}

---

## Architecture

### Design Patterns
- {pattern_1} (e.g., Actor Model, Saga Pattern, Circuit Breaker)
- {pattern_2}

### Dependencies
**Imports (Allowed by Layer {layer_number}):**
{dependency_list_with_layers}

**Example:**
```python
# Layer {layer_number} can import:
from k1.{dependency_module_1} import {class_1}  # Layer X
from k1.{dependency_module_2} import {class_2}  # Layer Y
```

### Related ADRs
- [ADR-XXXX: {adr_title}]({adr_link})

---

## API

### Public Classes

#### `{ClassName}`
{class_docstring}

**Constructor:**
```python
{class_name}({constructor_signature})
```

**Methods:**

##### `{method_name}({method_signature}) -> {return_type}`
{method_docstring}

**Example:**
```python
{usage_example}
```

**Raises:**
- `{ExceptionType}`: {exception_description}

---

### Public Functions

#### `{function_name}({function_signature}) -> {return_type}`
{function_docstring}

**Example:**
```python
{usage_example}
```

---

## Performance Budgets

| Metric | Budget (P95) | Current | Status |
|--------|--------------|---------|--------|
| {metric_1} | {budget_1} | {current_1} | {status_1} |
| {metric_2} | {budget_2} | {current_2} | {status_2} |

**Prometheus Metrics:**
- `{metric_name_1}` - {metric_description_1}
- `{metric_name_2}` - {metric_description_2}

---

## Testing

**Coverage:** {coverage_percentage}% (target: ≥90%)

**Test Files:**
- `tests/{module_path}/test_{module_name}.py`

**Run Tests:**
```bash
pytest tests/{module_path}/ -v
```

**Integration Tests:**
- {integration_test_description_1}
- {integration_test_description_2}

---

## Dependencies

### Required Modules
**Layer {layer_number} imports:**
{dependency_list_with_import_statements}

### Required External Packages
{external_packages_list}

---

## Development

### Adding New Features
1. {step_1}
2. {step_2}
3. Update this README (run `k1-doc-gen`)

### Common Patterns
{common_pattern_1_with_code_example}

---

## References
- [ADR-XXXX: {related_adr}]({adr_link})
- {research_paper_citation_if_applicable}

---

**Last Updated:** {auto_generated_timestamp}
**Auto-Generated:** ✅ (via `k1-doc-gen`)
```

---

### Component 2: Auto-Generation Tool (`k1-doc-gen`)

**File:** `tools/k1_doc_gen.py`

**Purpose:** Extract metadata from module code, fill README template.

```python
"""
k1-doc-gen: Auto-generate module READMEs from code metadata

Usage:
    k1-doc-gen --module k1.execution.agent_registry
    k1-doc-gen --all  # Generate all module READMEs
"""

import ast
import importlib
import inspect
from pathlib import Path
from typing import List, Dict
import subprocess

class ModuleDocGenerator:
    """Auto-generate module README from code metadata"""

    def __init__(self, module_name: str):
        self.module_name = module_name
        self.module_path = Path("k1") / module_name.replace("k1.", "").replace(".", "/")
        self.readme_path = self.module_path / "README.md"

    def generate(self):
        """Generate README.md for module"""

        # 1. Extract metadata from code
        metadata = self._extract_metadata()

        # 2. Load template
        template = self._load_template()

        # 3. Fill template with metadata
        readme_content = self._fill_template(template, metadata)

        # 4. Write README.md
        self.readme_path.write_text(readme_content)

        print(f"✅ Generated: {self.readme_path}")

    def _extract_metadata(self) -> Dict:
        """Extract metadata from module code"""

        # Parse __init__.py for module docstring
        init_file = self.module_path / "__init__.py"
        if not init_file.exists():
            raise FileNotFoundError(f"Module not found: {init_file}")

        with open(init_file) as f:
            tree = ast.parse(f.read())

        # Extract module docstring
        module_docstring = ast.get_docstring(tree) or ""

        # Parse docstring for Purpose, Layer
        purpose = self._parse_docstring_field(module_docstring, "Purpose:")
        layer = self._parse_docstring_field(module_docstring, "Layer:")

        # Extract imports (dependencies)
        imports = self._extract_imports(tree)

        # Extract public API (classes, functions)
        public_api = self._extract_public_api(tree)

        # Extract metrics (Prometheus)
        metrics = self._extract_metrics(tree)

        # Extract test coverage
        coverage = self._extract_test_coverage()

        return {
            "module_name": self.module_name,
            "purpose": purpose,
            "layer": layer,
            "imports": imports,
            "public_api": public_api,
            "metrics": metrics,
            "coverage": coverage,
        }

    def _extract_imports(self, tree: ast.AST) -> List[Dict]:
        """Extract imports with layer annotations"""
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("k1."):
                    # Determine layer from module name
                    layer = self._get_layer_from_module(node.module)

                    for alias in node.names:
                        imports.append({
                            "module": node.module,
                            "name": alias.name,
                            "layer": layer,
                        })

        return imports

    def _extract_public_api(self, tree: ast.AST) -> List[Dict]:
        """Extract public classes and functions"""
        api = []

        for node in ast.walk(tree):
            # Extract classes
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                class_doc = ast.get_docstring(node) or ""

                # Extract methods
                methods = []
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                        method_doc = ast.get_docstring(item) or ""
                        methods.append({
                            "name": item.name,
                            "docstring": method_doc,
                            "signature": self._get_function_signature(item),
                        })

                api.append({
                    "type": "class",
                    "name": node.name,
                    "docstring": class_doc,
                    "methods": methods,
                })

            # Extract functions
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                func_doc = ast.get_docstring(node) or ""
                api.append({
                    "type": "function",
                    "name": node.name,
                    "docstring": func_doc,
                    "signature": self._get_function_signature(node),
                })

        return api

    def _extract_metrics(self, tree: ast.AST) -> List[Dict]:
        """Extract Prometheus metrics from code"""
        metrics = []

        for node in ast.walk(tree):
            # Find Counter, Histogram, Gauge definitions
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        # Check if value is Prometheus metric
                        if isinstance(node.value, ast.Call):
                            if hasattr(node.value.func, 'attr'):
                                metric_type = node.value.func.attr  # Counter, Histogram, etc.
                                if metric_type in ['Counter', 'Histogram', 'Gauge']:
                                    # Extract metric name from first arg
                                    if node.value.args:
                                        metric_name = node.value.args[0].s if hasattr(node.value.args[0], 's') else ""
                                        metrics.append({
                                            "name": metric_name,
                                            "type": metric_type,
                                        })

        return metrics

    def _extract_test_coverage(self) -> int:
        """Extract test coverage from pytest --cov"""
        try:
            result = subprocess.run(
                ["pytest", f"tests/{self.module_path}", "--cov", "--cov-report=term-missing"],
                capture_output=True,
                text=True,
            )
            # Parse coverage from output (e.g., "95%")
            for line in result.stdout.split("\n"):
                if self.module_name in line:
                    coverage_str = line.split()[-1]  # Last column (percentage)
                    return int(coverage_str.replace("%", ""))
        except Exception:
            return 0  # Coverage unknown

        return 0

    def _get_layer_from_module(self, module_name: str) -> str:
        """Determine layer number from module name"""
        layer_map = {
            "k1.input": "Layer 1 (Input)",
            "k1.orchestration": "Layer 2 (Orchestration)",
            "k1.execution": "Layer 3 (Execution)",
            "k1.runtime": "Layer 4 (Runtime Core)",
            "k1.infrastructure": "Layer 5 (Infrastructure)",
        }

        for prefix, layer in layer_map.items():
            if module_name.startswith(prefix):
                return layer

        return "Unknown Layer"

    def _fill_template(self, template: str, metadata: Dict) -> str:
        """Fill template with extracted metadata"""
        # Replace placeholders
        content = template
        content = content.replace("{module_name}", metadata["module_name"])
        content = content.replace("{purpose}", metadata["purpose"])
        content = content.replace("{layer}", metadata["layer"])

        # Fill imports section
        imports_section = "\n".join([
            f"- `{imp['module']}` ({imp['layer']})"
            for imp in metadata["imports"]
        ])
        content = content.replace("{imports_section}", imports_section)

        # Fill API section
        api_section = self._format_api_section(metadata["public_api"])
        content = content.replace("{api_section}", api_section)

        # Fill metrics section
        metrics_section = "\n".join([
            f"- `{metric['name']}` ({metric['type']})"
            for metric in metadata["metrics"]
        ])
        content = content.replace("{metrics_section}", metrics_section)

        # Fill coverage
        content = content.replace("{coverage}", str(metadata["coverage"]))

        return content

    def _load_template(self) -> str:
        """Load README template"""
        template_path = Path(".github/templates/MODULE_README_TEMPLATE.md")
        return template_path.read_text()

    def _parse_docstring_field(self, docstring: str, field: str) -> str:
        """Extract field from docstring (e.g., 'Purpose: ...')"""
        for line in docstring.split("\n"):
            if line.strip().startswith(field):
                return line.split(field)[1].strip()
        return ""

    def _get_function_signature(self, node: ast.FunctionDef) -> str:
        """Extract function signature as string"""
        args = [arg.arg for arg in node.args.args]
        return f"({', '.join(args)})"

    def _format_api_section(self, api: List[Dict]) -> str:
        """Format public API as Markdown"""
        sections = []

        for item in api:
            if item["type"] == "class":
                section = f"### {item['name']}\n{item['docstring']}\n"
                for method in item["methods"]:
                    section += f"\n#### `{method['name']}{method['signature']}`\n{method['docstring']}\n"
                sections.append(section)
            elif item["type"] == "function":
                section = f"### `{item['name']}{item['signature']}`\n{item['docstring']}\n"
                sections.append(section)

        return "\n".join(sections)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate module READMEs")
    parser.add_argument("--module", help="Module name (e.g., k1.execution.agent_registry)")
    parser.add_argument("--all", action="store_true", help="Generate all module READMEs")
    args = parser.parse_args()

    if args.all:
        # Find all modules (k1/*/__init__.py)
        modules = []
        for init_file in Path("k1").rglob("__init__.py"):
            module_name = "k1." + str(init_file.parent).replace("/", ".").replace("\\", ".").replace("k1.", "")
            modules.append(module_name)

        for module in modules:
            generator = ModuleDocGenerator(module)
            generator.generate()

    elif args.module:
        generator = ModuleDocGenerator(args.module)
        generator.generate()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

---

### Component 3: CI Enforcement (GitHub Actions)

**File:** `.github/workflows/docs.yml`

**Purpose:** Enforce README presence and freshness in CI.

```yaml
name: Documentation Checks

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  readme-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .

      - name: Check module READMEs exist
        run: |
          python tools/check_module_readmes.py
          # CRITICAL: Fails if any module missing README

      - name: Check READMEs are up-to-date
        run: |
          # Regenerate all READMEs
          python tools/k1_doc_gen.py --all

          # Check if any READMEs changed
          if ! git diff --quiet; then
            echo "❌ Module READMEs are outdated!"
            echo "Run: python tools/k1_doc_gen.py --all"
            git diff --stat
            exit 1
          fi

          echo "✅ All module READMEs up-to-date"
```

---

## Example Generated README

**Input:** `k1-doc-gen --module k1.execution.agent_registry`

**Output:** `k1/execution/agent_registry/README.md`

```markdown
# Module: k1.execution.agent_registry

**Layer:** 3 (Execution)
**Purpose:** Agent lifecycle registry (hire, fire, lookup)
**Status:** ✅ STABLE

---

## Purpose

Manages agent lifecycle within a session scope. Tracks agent states (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED).

**Responsibilities:**
- Register agents in session
- Track agent state transitions
- Provide agent lookup by ID
- Enforce max agents per session limit (3 agents)

**Out of Scope:**
- Agent execution (handled by agent_supervisor)
- Agent scheduling (handled by infrastructure/scheduler)

---

## Architecture

### Design Patterns
- Actor Model (each agent is isolated actor)
- Registry Pattern (centralized agent lookup)

### Dependencies
**Imports (Allowed by Layer 3):**
- `k1.runtime.session_state` (Layer 4) - Session state management
- `k1.infrastructure.metrics` (Layer 5) - Prometheus metrics

**Example:**
```python
# Layer 3 can import:
from k1.runtime.session_state import SessionState  # Layer 4
from k1.infrastructure.metrics import agent_registry_total  # Layer 5
```

### Related ADRs
- [ADR-0002: Actor Model for Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR-0005: Agent Lifecycle FSM](0005-agent-lifecycle-fsm.md)

---

## API

### Public Classes

#### `AgentRegistry`
Agent registry for session-scoped agent tracking

**Constructor:**
```python
AgentRegistry(session_id: str, max_agents: int = 3)
```

**Methods:**

##### `register(agent_id: str, capabilities: List[str]) -> None`
Register agent in session

**Example:**
```python
registry = AgentRegistry(session_id="session_123")
registry.register(agent_id="agent_001", capabilities=["TOOL_CALL", "MEMORY_READ"])
```

**Raises:**
- `MaxAgentsExceeded`: If session already has 3 agents

##### `lookup(agent_id: str) -> Agent | None`
Lookup agent by ID

**Example:**
```python
agent = registry.lookup(agent_id="agent_001")
if agent:
    print(f"Agent state: {agent.state}")
```

---

## Performance Budgets

| Metric | Budget (P95) | Current | Status |
|--------|--------------|---------|--------|
| Register latency | 50ms | 35ms | ✅ |
| Lookup latency | 1ms | 0.5ms | ✅ |

**Prometheus Metrics:**
- `agent_registry_total` (Gauge) - Total registered agents in session
- `agent_registry_register_latency_ms` (Histogram) - Registration latency

---

## Testing

**Coverage:** 95% (target: ≥90%)

**Test Files:**
- `tests/execution/test_agent_registry.py`

**Run Tests:**
```bash
pytest tests/execution/test_agent_registry.py -v
```

**Integration Tests:**
- Test max agents limit enforcement
- Test agent state transition tracking

---

## Dependencies

### Required Modules
**Layer 3 imports:**
- `k1.runtime.session_state` (Layer 4)
- `k1.infrastructure.metrics` (Layer 5)

### Required External Packages
- `prometheus_client` (metrics)

---

## Development

### Adding New Features
1. Update `AgentRegistry` class in `__init__.py`
2. Add tests in `tests/execution/test_agent_registry.py`
3. Update this README (run `k1-doc-gen --module k1.execution.agent_registry`)

### Common Patterns
**Agent registration:**
```python
registry = AgentRegistry(session_id="session_123")
registry.register(agent_id="agent_001", capabilities=["TOOL_CALL"])
```

---

## References
- [ADR-0005: Agent Lifecycle FSM](0005-agent-lifecycle-fsm.md)
- Actor Model (Hewitt 1973)

---

**Last Updated:** 2025-10-12T10:30:00Z
**Auto-Generated:** ✅ (via `k1-doc-gen`)
```

---

## Consequences

### Positive ✅

**✅ Consistent Documentation:**
- All 52 modules have identical README structure
- Developers know where to find information (Purpose, API, Performance)
- **Result:** Faster onboarding, less confusion

**✅ Auto-Generated (Low Maintenance):**
- `k1-doc-gen --all` regenerates all READMEs in <10s
- No manual README updates needed (extracts from code)
- **Result:** Always up-to-date documentation

**✅ CI Enforcement:**
- PRs blocked if module README missing
- PRs blocked if README outdated (git diff check)
- **Result:** Documentation never falls behind code

**✅ Discoverable APIs:**
- All public classes/functions documented with examples
- Developers can find APIs without reading code
- **Result:** Faster development, less interruptions

---

### Negative ⚠️

**⚠️ Auto-Generated Content Quality:**
- Docstrings must be high-quality (tool extracts them)
- Missing docstrings → incomplete READMEs
- **Mitigation:** Enforce docstring coverage in CI (pydocstyle)
- **Risk Level:** MEDIUM (requires developer discipline)

**⚠️ Template Maintenance:**
- Template changes require regenerating all 52 READMEs
- **Mitigation:** Version template, document breaking changes
- **Risk Level:** LOW (template rarely changes)

---

## Implementation Notes

### **Implementation Timeline**

**Phase 1 (Week 1): Template & Tool**
- Create `MODULE_README_TEMPLATE.md`
- Implement `k1_doc_gen.py` (metadata extraction, template filling)
- Test on 3 sample modules (agent_registry, orchestrator, event_bus)

**Phase 2 (Week 2): Generate All READMEs**
- Run `k1-doc-gen --all` for all 52 modules
- Manual review (check quality, fix missing docstrings)
- Commit all generated READMEs

**Phase 3 (Week 3): CI Integration**
- Add `.github/workflows/docs.yml` (README checks)
- Test on sample PRs (expect CI to catch missing READMEs)
- Update CONTRIBUTING.md with `k1-doc-gen` instructions

**Phase 4 (Week 4): Refinement**
- Collect developer feedback (missing sections, unclear examples)
- Refine template based on feedback
- Regenerate all READMEs with updated template

---

### **Success Metrics**

**Quality:**
- ✅ All 52 modules have README.md
- ✅ All READMEs follow template structure
- ✅ 100% docstring coverage for public APIs

**Performance:**
- ✅ Generate all READMEs: <10s
- ✅ CI overhead: <5s (README checks)

**Developer Experience:**
- ✅ Onboarding time reduced by 50% (with READMEs vs without)
- ✅ Zero outdated READMEs (CI enforcement)

---

## References

### **Related ADRs**

- [ADR-0004: 52-Module 5-Layer Architecture](0004-52-module-5-layer-architecture.md) — Parent ADR
- [ADR-0004a: Layer 1-2 Event Bus Communication](0004a-layer1-2-event-bus-communication.md)
- [ADR-0004b: Module Dependency Management](0004b-module-dependency-management.md)

---

**Document Status:** ✅ **COMPLETE** - Module README template and auto-generation fully specified with template structure, k1-doc-gen tool design, CI enforcement, and example generated README.

**Cross-References:**
- ADR-0004 (Parent): 52-Module 5-Layer Architecture
- All 52 K1 modules (target for README generation)

**Canonical Values:**
- **Generation time:** <10s for all 52 modules
- **Template sections:** 7 sections (Purpose, Architecture, API, Performance, Testing, Dependencies, Development)

**Document End**
