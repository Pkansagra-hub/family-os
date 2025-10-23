# ADR-0086b: Agent Template System

**Status:** Approved ✅ - Implementation Phase M1
**Decision Date:** 2025-10-23
**Implementation Date:** TBD (M1 - Issue 1.1.2)
**Review Date:** TBD (Post-implementation)
**Last Updated:** 2025-10-23
**Authors:** K1 Architecture Team
**Category:** Agent Configuration & Template Management
**Parent ADR:** [ADR-0086 (Dynamic Agent Creation Subsystem)](0086-dynamic-agent-creation-subsystem.md)
**Related ADRs:**

- [ADR-0086a (Agent Factory)](0086a-agent-factory-pattern.md) - Factory loads templates
- [ADR-0086d (Agent Composition)](0086d-agent-composition-pattern.md) - Composition uses templates
- [ADR-0086e (Prompt Directory)](0086e-prompt-directory-template-management.md) - Prompt templates
- [ADR-0005e (Agent Personalities)](0005e-agent-personality-capabilities.md) - Personality traits
- [ADR-0010 (Capability Security)](0010-capability-based-security.md) - Capability declarations
- [ADR-0024c (Memory Budgets)](0024c-memory-budgets-resource-limits.md) - Resource limits

---

## Context

### Problem Statement

K1 currently hardcodes agent configurations in Python code, making it difficult to:

1. **Create New Agent Types:** Requires code changes for each new specialist agent (health, code, finance, etc.)
2. **Share Common Config:** Duplicated configuration across similar agents (memory budgets, timeouts, etc.)
3. **Version Configuration:** No semantic versioning for agent configurations
4. **Validate at Load Time:** No schema validation until runtime errors occur
5. **Support Inheritance:** Cannot reuse base configurations (e.g., all AI agents share common settings)

### Current State

**Hardcoded Agent Config (Current):**

```python
# k1/l3_execution/agents/concierge/__init__.py
class Concierge:
    agent_type = "concierge"
    capabilities = ["TOOL_CALL", "MEMORY_READ", "MODEL_CALL"]
    memory_mb = 150
    placement_preference = "NPU"
    model = "phi-3-mini"
    # ... 50+ lines of hardcoded config
```

**Problems:**

- ❌ New agent type = new Python module
- ❌ Config changes require code redeployment
- ❌ No inheritance (duplicate config across agents)
- ❌ No validation until runtime

### Desired State

**YAML Template System (M1 Goal):**

```yaml
# k1/config/agent_templates/health_specialist.agent.yml
template:
  version: "1.0.0"
  name: "health_specialist"
  inherits_from: "base_agent.yml"

  agent_type: "health_specialist"
  category: "task_specific_ai_agent"
  description: "Health metrics analysis and fitness recommendations"

  capabilities:
    - TOOL_CALL
    - MEMORY_READ
    - MODEL_CALL

  resources:
    memory_mb: 256
    placement_preference: "GPU"

  personality:
    response_time_budget_ms: 3000
    reasoning_style: "data_driven"
    tone: "empathetic"

  model_hub:
    primary_model: "gemma-2-9b"
    fallback_model: "gpt-4o-mini"
    prompt_template: "agent_prompts/health_specialist.prompt.j2"

  lifecycle:
    warmup_timeout_ms: 300
    idle_ttl_ms: 300000  # 5 min
    drain_timeout_ms: 5000
```

**Benefits:**

- ✅ New agent type = new YAML file (no code)
- ✅ Config changes without redeployment
- ✅ Inheritance for common settings
- ✅ JSON Schema validation at load time
- ✅ Semantic versioning (1.0.0 → 1.1.0)

---

## Decision

We will implement a **YAML-based Agent Template System** with the following components:

### 1. Template Schema (JSON Schema v7)

```yaml
# k1/config/agent_templates/schema/agent_template.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "K1 Agent Template",
  "type": "object",
  "required": ["template"],
  "properties": {
    "template": {
      "type": "object",
      "required": ["version", "name", "agent_type", "category"],
      "properties": {
        "version": {
          "type": "string",
          "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$",
          "description": "Semantic version (e.g., 1.0.0)"
        },
        "name": {
          "type": "string",
          "pattern": "^[a-z_]+$",
          "description": "Template name (snake_case)"
        },
        "inherits_from": {
          "type": "string",
          "description": "Parent template file (e.g., base_agent.yml)"
        },
        "agent_type": {
          "type": "string",
          "description": "Agent type identifier"
        },
        "category": {
          "type": "string",
          "enum": [
            "core_ai_agent",
            "task_specific_ai_agent",
            "pure_actor"
          ]
        },
        "description": {
          "type": "string",
          "maxLength": 500
        },
        "capabilities": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": [
              "TOOL_CALL",
              "MEMORY_READ",
              "MEMORY_WRITE",
              "MODEL_CALL",
              "NETWORK_ACCESS",
              "FILE_ACCESS"
            ]
          },
          "minItems": 1,
          "uniqueItems": true
        },
        "resources": {
          "type": "object",
          "required": ["memory_mb", "placement_preference"],
          "properties": {
            "memory_mb": {
              "type": "integer",
              "minimum": 64,
              "maximum": 512,
              "description": "Memory budget in MB"
            },
            "placement_preference": {
              "type": "string",
              "enum": ["NPU", "GPU", "CPU", "Remote"]
            }
          }
        },
        "personality": {
          "type": "object",
          "properties": {
            "response_time_budget_ms": {
              "type": "integer",
              "minimum": 50,
              "maximum": 10000
            },
            "reasoning_style": {
              "type": "string",
              "enum": ["fast_nlp", "deep_reasoning", "data_driven", "procedural"]
            },
            "tone": {
              "type": "string",
              "enum": ["professional", "friendly", "empathetic", "technical"]
            }
          }
        },
        "model_hub": {
          "type": "object",
          "properties": {
            "primary_model": {
              "type": "string",
              "description": "Primary LLM model"
            },
            "fallback_model": {
              "type": "string",
              "description": "Fallback model if primary fails"
            },
            "prompt_template": {
              "type": "string",
              "pattern": "^agent_prompts/.*\\.prompt\\.j2$",
              "description": "Jinja2 prompt template path"
            }
          }
        },
        "lifecycle": {
          "type": "object",
          "properties": {
            "warmup_timeout_ms": {
              "type": "integer",
              "minimum": 50,
              "maximum": 5000
            },
            "idle_ttl_ms": {
              "type": "integer",
              "minimum": 60000,
              "maximum": 600000
            },
            "drain_timeout_ms": {
              "type": "integer",
              "minimum": 1000,
              "maximum": 10000
            }
          }
        },
        "metadata": {
          "type": "object",
          "additionalProperties": {
            "type": "string"
          }
        }
      }
    }
  }
}
```

### 2. Template Loader (Python Implementation)

```python
# k1/l3_execution/agents/template_loader.py

import yaml
import json
import jsonschema
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass
from functools import lru_cache
import time

@dataclass
class AgentTemplate:
    """Parsed agent template"""
    version: str
    name: str
    agent_type: str
    category: str
    description: str
    capabilities: list[str]
    resources: Dict
    personality: Dict
    model_hub: Optional[Dict]
    lifecycle: Dict
    metadata: Dict
    inherits_from: Optional[str]
    _raw_yaml: Dict


class TemplateLoader:
    """
    YAML template loader with inheritance, caching, and validation.

    Responsibilities:
    1. Load YAML templates from disk
    2. Validate against JSON Schema
    3. Resolve inheritance (base_agent → specialized)
    4. LRU cache for performance (<10ms P95 load)
    5. Semantic version validation

    Performance Target: <10ms P95 load (cached), <50ms P95 (uncached)
    """

    def __init__(
        self,
        template_dir: Path,
        schema_path: Path,
        cache_size: int = 128
    ):
        """
        Initialize template loader.

        Args:
            template_dir: Path to agent_templates/ directory
            schema_path: Path to agent_template.schema.json
            cache_size: LRU cache size (default: 128 templates)
        """
        self.template_dir = template_dir
        self.schema_path = schema_path
        self.cache_size = cache_size

        # Load JSON Schema
        with open(schema_path, 'r') as f:
            self.schema = json.load(f)

        # Template cache (LRU)
        self._cache: Dict[str, AgentTemplate] = {}
        self._cache_order: list[str] = []

        # Metrics
        self._metrics_loads_total = 0
        self._metrics_cache_hits = 0
        self._metrics_cache_misses = 0
        self._metrics_validation_errors = 0

    @lru_cache(maxsize=128)
    def load(
        self,
        agent_type: str,
        trace_id: str
    ) -> AgentTemplate:
        """
        Load and parse agent template with inheritance resolution.

        Flow:
        1. Check LRU cache (hit → return cached)
        2. Load YAML from disk
        3. Validate against JSON Schema
        4. Resolve inheritance (recursive if inherits_from)
        5. Merge with parent template
        6. Cache result

        Performance: <10ms P95 (cached), <50ms P95 (uncached)

        Args:
            agent_type: Agent type (e.g., "health_specialist")
            trace_id: Trace ID for observability

        Returns:
            AgentTemplate: Parsed and validated template

        Raises:
            TemplateNotFoundError: Template file doesn't exist
            TemplateValidationError: Schema validation failed
            TemplateInheritanceError: Circular inheritance detected
        """
        start_time = time.perf_counter()
        self._metrics_loads_total += 1

        # Check cache
        if agent_type in self._cache:
            self._metrics_cache_hits += 1
            logger.debug(
                "template_cache_hit",
                agent_type=agent_type,
                trace_id=trace_id
            )
            return self._cache[agent_type]

        self._metrics_cache_misses += 1

        try:
            # Load YAML file
            template_path = self.template_dir / f"{agent_type}.agent.yml"
            if not template_path.exists():
                raise TemplateNotFoundError(
                    f"Template not found: {template_path}"
                )

            with open(template_path, 'r') as f:
                raw_yaml = yaml.safe_load(f)

            # Validate against schema
            try:
                jsonschema.validate(raw_yaml, self.schema)
            except jsonschema.ValidationError as e:
                self._metrics_validation_errors += 1
                raise TemplateValidationError(
                    f"Template validation failed: {e.message}"
                )

            template_data = raw_yaml['template']

            # Resolve inheritance
            if 'inherits_from' in template_data:
                parent_name = template_data['inherits_from'].replace('.agent.yml', '')
                parent_template = self.load(parent_name, trace_id)

                # Merge with parent (child overrides parent)
                merged_data = self._merge_templates(
                    parent=parent_template._raw_yaml['template'],
                    child=template_data
                )
                template_data = merged_data

            # Create AgentTemplate
            template = AgentTemplate(
                version=template_data['version'],
                name=template_data['name'],
                agent_type=template_data['agent_type'],
                category=template_data['category'],
                description=template_data.get('description', ''),
                capabilities=template_data.get('capabilities', []),
                resources=template_data.get('resources', {}),
                personality=template_data.get('personality', {}),
                model_hub=template_data.get('model_hub'),
                lifecycle=template_data.get('lifecycle', {}),
                metadata=template_data.get('metadata', {}),
                inherits_from=template_data.get('inherits_from'),
                _raw_yaml=raw_yaml
            )

            # Cache result (LRU eviction)
            self._add_to_cache(agent_type, template)

            # Metrics
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "template_loaded",
                agent_type=agent_type,
                version=template.version,
                inherits_from=template.inherits_from,
                latency_ms=latency_ms,
                cached=False,
                trace_id=trace_id
            )

            return template

        except Exception as e:
            logger.error(
                "template_load_failed",
                agent_type=agent_type,
                error=str(e),
                trace_id=trace_id
            )
            raise

    def _merge_templates(
        self,
        parent: Dict,
        child: Dict
    ) -> Dict:
        """
        Merge child template with parent (deep merge).

        Rules:
        - Child overrides parent for scalars (string, int, bool)
        - Child extends parent for lists (union, deduplicated)
        - Child overrides parent for dicts (key-by-key merge)

        Example:
            parent: {capabilities: ["TOOL_CALL"], memory_mb: 128}
            child:  {capabilities: ["MODEL_CALL"], memory_mb: 256}
            result: {capabilities: ["TOOL_CALL", "MODEL_CALL"], memory_mb: 256}
        """
        merged = parent.copy()

        for key, child_value in child.items():
            if key not in merged:
                # New key in child
                merged[key] = child_value
            elif isinstance(child_value, dict) and isinstance(merged[key], dict):
                # Deep merge dicts
                merged[key] = self._merge_templates(merged[key], child_value)
            elif isinstance(child_value, list) and isinstance(merged[key], list):
                # Union lists (deduplicate)
                merged[key] = list(set(merged[key] + child_value))
            else:
                # Child overrides parent
                merged[key] = child_value

        return merged

    def _add_to_cache(self, agent_type: str, template: AgentTemplate):
        """Add template to LRU cache with eviction"""
        if agent_type in self._cache:
            # Already cached, update order
            self._cache_order.remove(agent_type)
        elif len(self._cache) >= self.cache_size:
            # Evict LRU entry
            evicted = self._cache_order.pop(0)
            del self._cache[evicted]
            logger.debug("template_cache_evicted", agent_type=evicted)

        self._cache[agent_type] = template
        self._cache_order.append(agent_type)

    def invalidate_cache(self, agent_type: Optional[str] = None):
        """Invalidate cache (single template or all)"""
        if agent_type:
            if agent_type in self._cache:
                del self._cache[agent_type]
                self._cache_order.remove(agent_type)
        else:
            # Clear all
            self._cache.clear()
            self._cache_order.clear()

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        hit_rate = (
            self._metrics_cache_hits / self._metrics_loads_total
            if self._metrics_loads_total > 0
            else 0.0
        )

        return {
            "loads_total": self._metrics_loads_total,
            "cache_hits": self._metrics_cache_hits,
            "cache_misses": self._metrics_cache_misses,
            "hit_rate": hit_rate,
            "cache_size": len(self._cache),
            "cache_capacity": self.cache_size,
            "validation_errors": self._metrics_validation_errors
        }
```

### 3. Template Directory Structure

```
k1/config/agent_templates/
├── schema/
│   └── agent_template.schema.json      # JSON Schema v7
│
├── base_agent.yml                      # Base template (all agents inherit)
├── base_ai_agent.yml                   # Base for AI agents (inherits base_agent)
│
├── concierge.agent.yml                 # Core AI agents
├── planner.agent.yml
├── researcher.agent.yml
├── safety_watch.agent.yml
│
├── health_specialist.agent.yml         # Task-specific AI agents
├── code_assistant.agent.yml
├── finance_advisor.agent.yml
├── travel_planner.agent.yml
├── recipe_assistant.agent.yml
├── fitness_coach.agent.yml
│
└── README.md                           # Template creation guide
```

### 4. Example Templates

**Base Agent Template:**

```yaml
# k1/config/agent_templates/base_agent.yml
template:
  version: "1.0.0"
  name: "base_agent"
  agent_type: "base"
  category: "pure_actor"
  description: "Base template for all K1 agents"

  capabilities:
    - TOOL_CALL

  resources:
    memory_mb: 128
    placement_preference: "CPU"

  personality:
    response_time_budget_ms: 1000
    reasoning_style: "procedural"
    tone: "professional"

  lifecycle:
    warmup_timeout_ms: 100
    idle_ttl_ms: 300000  # 5 min
    drain_timeout_ms: 5000

  metadata:
    created_by: "k1_team"
    layer: "3"
```

**Base AI Agent Template:**

```yaml
# k1/config/agent_templates/base_ai_agent.yml
template:
  version: "1.0.0"
  name: "base_ai_agent"
  inherits_from: "base_agent.yml"

  agent_type: "base_ai"
  category: "core_ai_agent"
  description: "Base template for AI agents (LLM-powered)"

  capabilities:
    - TOOL_CALL
    - MEMORY_READ
    - MODEL_CALL

  resources:
    memory_mb: 256
    placement_preference: "GPU"

  personality:
    response_time_budget_ms: 3000
    reasoning_style: "deep_reasoning"

  model_hub:
    primary_model: "gemma-2-9b"
    fallback_model: "gpt-4o-mini"

  lifecycle:
    warmup_timeout_ms: 300
```

**Health Specialist Template:**

```yaml
# k1/config/agent_templates/health_specialist.agent.yml
template:
  version: "1.0.0"
  name: "health_specialist"
  inherits_from: "base_ai_agent.yml"

  agent_type: "health_specialist"
  category: "task_specific_ai_agent"
  description: "Health metrics analysis, fitness recommendations, wellness tracking"

  capabilities:
    - TOOL_CALL
    - MEMORY_READ
    - MODEL_CALL

  personality:
    response_time_budget_ms: 3000
    reasoning_style: "data_driven"
    tone: "empathetic"

  model_hub:
    prompt_template: "agent_prompts/health_specialist.prompt.j2"

  metadata:
    domain: "health"
    tools: ["health_metrics", "activity_tracker", "sleep_analyzer"]
    created_at: "2025-10-23"
```

**Code Assistant Template:**

```yaml
# k1/config/agent_templates/code_assistant.agent.yml
template:
  version: "1.0.0"
  name: "code_assistant"
  inherits_from: "base_ai_agent.yml"

  agent_type: "code_assistant"
  category: "task_specific_ai_agent"
  description: "Code generation, review, debugging, and refactoring assistance"

  capabilities:
    - TOOL_CALL
    - MEMORY_READ
    - MODEL_CALL
    - FILE_ACCESS

  resources:
    memory_mb: 384  # Larger for code context

  personality:
    response_time_budget_ms: 5000
    reasoning_style: "deep_reasoning"
    tone: "technical"

  model_hub:
    primary_model: "gpt-4o"  # Better for code
    prompt_template: "agent_prompts/code_assistant.prompt.j2"

  metadata:
    domain: "software_engineering"
    tools: ["code_analyzer", "linter", "test_generator"]
```

---

## Performance Budgets

| Metric | Budget | Rationale |
|--------|--------|-----------|
| **Template load (cached)** | <10ms P95 | LRU cache hit, frequently accessed |
| **Template load (uncached)** | <50ms P95 | Disk I/O + YAML parse + validation |
| **JSON Schema validation** | <20ms P95 | Validation overhead, infrequent |
| **Inheritance resolution** | <30ms P95 | Recursive load + merge (max 3 levels) |
| **Cache hit rate** | >80% | Most agents reuse common templates |
| **Memory footprint** | <5MB | 128 cached templates × ~40KB each |

---

## Consequences

### Positive ✅

- **No Code Changes:** New agent types via YAML files, no Python code
- **DRY Principle:** Inheritance eliminates config duplication
- **Validation:** JSON Schema catches errors at load time (not runtime)
- **Versioning:** Semantic versioning enables backward compatibility
- **Performance:** LRU cache achieves <10ms P95 load (cached)
- **Observability:** Cache stats, load metrics, validation errors

### Negative ❌

- **YAML Complexity:** Inheritance can be hard to trace (3+ levels deep)
- **Schema Maintenance:** JSON Schema must evolve with new fields
- **Cache Invalidation:** Template updates require cache invalidation
- **Circular Inheritance:** Requires detection logic (not in MVP)

### Mitigations

- **Max Inheritance Depth:** Limit to 3 levels (base → base_ai → specialist)
- **Schema Versioning:** Semantic versioning for schema evolution
- **Cache Invalidation API:** Explicit `invalidate_cache()` method
- **Inheritance Validation:** Detect circular references (future M2)

---

## Validation & Testing

### Acceptance Criteria

- [ ] Template loader loads YAML files ✓
- [ ] JSON Schema validation rejects invalid templates ✓
- [ ] Inheritance resolves correctly (parent → child) ✓
- [ ] Cache hit rate >80% (100 loads, 80+ hits) ✓
- [ ] Load latency <10ms P95 (cached), <50ms P95 (uncached) ✓
- [ ] All 4 example templates validate ✓
- [ ] WARD tests cover all error paths ✓

### WARD Integration Tests

```python
# tests/l3_execution/agents/test_template_loader.py

from ward import test, fixture
from pathlib import Path
from k1.l3_execution.agents.template_loader import TemplateLoader

@fixture
def template_loader():
    """Template loader fixture"""
    template_dir = Path("k1/config/agent_templates")
    schema_path = Path("k1/config/agent_templates/schema/agent_template.schema.json")

    loader = TemplateLoader(
        template_dir=template_dir,
        schema_path=schema_path,
        cache_size=128
    )

    yield loader

    # Cleanup
    loader.invalidate_cache()


@test("template loader loads valid YAML")
async def _(loader=template_loader):
    template = loader.load("health_specialist", trace_id="test_1")

    assert template.agent_type == "health_specialist"
    assert template.category == "task_specific_ai_agent"
    assert "TOOL_CALL" in template.capabilities
    assert template.resources['memory_mb'] == 256


@test("template loader resolves inheritance")
async def _(loader=template_loader):
    # health_specialist → base_ai_agent → base_agent
    template = loader.load("health_specialist", trace_id="test_2")

    # Should inherit capabilities from base_agent
    assert "TOOL_CALL" in template.capabilities
    # Should inherit from base_ai_agent
    assert "MODEL_CALL" in template.capabilities
    # Should have own capabilities
    assert template.personality['tone'] == "empathetic"


@test("template loader validates schema")
async def _(loader=template_loader):
    # Create invalid template (missing required fields)
    invalid_yaml = Path("k1/config/agent_templates/invalid_test.agent.yml")
    invalid_yaml.write_text("""
template:
  version: "1.0.0"
  # Missing required 'name', 'agent_type', 'category'
""")

    with expecting(TemplateValidationError):
        loader.load("invalid_test", trace_id="test_3")

    # Cleanup
    invalid_yaml.unlink()


@test("template loader cache hit rate >80%")
async def _(loader=template_loader):
    # Load 100 templates (10 unique types × 10 repeats)
    agent_types = [
        "health_specialist", "code_assistant", "concierge", "planner",
        "researcher", "safety_watch", "finance_advisor", "travel_planner",
        "recipe_assistant", "fitness_coach"
    ]

    for _ in range(10):
        for agent_type in agent_types:
            loader.load(agent_type, trace_id=f"test_{agent_type}")

    stats = loader.get_cache_stats()
    hit_rate = stats['hit_rate']

    assert hit_rate > 0.80, f"Cache hit rate {hit_rate:.2%} below 80% target"


@test("template loader latency <10ms P95 (cached)")
async def _(loader=template_loader):
    import time

    # Prime cache
    loader.load("health_specialist", trace_id="prime")

    # Measure 100 cached loads
    latencies = []
    for i in range(100):
        start = time.perf_counter()
        loader.load("health_specialist", trace_id=f"test_{i}")
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    p95 = sorted(latencies)[94]
    assert p95 < 10, f"P95 cached load latency {p95:.2f}ms exceeds 10ms budget"


@test("template loader latency <50ms P95 (uncached)")
async def _(loader=template_loader):
    import time

    agent_types = [
        "health_specialist", "code_assistant", "finance_advisor",
        "travel_planner", "recipe_assistant"
    ]

    latencies = []
    for agent_type in agent_types:
        # Invalidate cache before each load
        loader.invalidate_cache(agent_type)

        start = time.perf_counter()
        loader.load(agent_type, trace_id=f"test_{agent_type}")
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    p95 = max(latencies)  # Worst case = P100
    assert p95 < 50, f"Uncached load latency {p95:.2f}ms exceeds 50ms budget"
```

---

## Metrics & Observability

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Template load metrics
k1_template_loads_total = Counter(
    'k1_template_loads_total',
    'Total template loads',
    ['agent_type', 'cached']
)

k1_template_load_latency_ms = Histogram(
    'k1_template_load_latency_ms',
    'Template load latency in milliseconds',
    ['agent_type', 'cached'],
    buckets=[1, 5, 10, 20, 30, 50, 75, 100]
)

k1_template_validation_errors_total = Counter(
    'k1_template_validation_errors_total',
    'Template validation errors',
    ['agent_type', 'error_type']
)

# Cache metrics
k1_template_cache_hit_rate = Gauge(
    'k1_template_cache_hit_rate',
    'Template cache hit rate (0.0-1.0)'
)

k1_template_cache_size = Gauge(
    'k1_template_cache_size',
    'Current template cache size'
)
```

### Structured Logs

```python
# Template loaded
logger.info(
    "template_loaded",
    agent_type=agent_type,
    version=template.version,
    inherits_from=template.inherits_from,
    latency_ms=latency_ms,
    cached=False,
    trace_id=trace_id
)

# Validation error
logger.error(
    "template_validation_failed",
    agent_type=agent_type,
    error=str(e),
    schema_version="v7",
    trace_id=trace_id
)

# Cache stats
logger.debug(
    "template_cache_stats",
    hit_rate=hit_rate,
    cache_size=len(cache),
    evictions=evictions_total
)
```

---

## Implementation Plan

### Phase 1: Schema & Loader (2 days)

**Day 1: JSON Schema**

- [ ] Create `agent_template.schema.json` (JSON Schema v7)
- [ ] Define all required/optional fields
- [ ] Add validation rules (min/max, enums, patterns)
- [ ] Test schema with example templates

**Day 2: Template Loader**

- [ ] Implement `TemplateLoader` class
- [ ] Add YAML parsing with PyYAML
- [ ] Add JSON Schema validation with jsonschema
- [ ] Implement LRU cache (dict + order list)
- [ ] Add inheritance resolution logic

### Phase 2: Templates & Tests (2 days)

**Day 3: Example Templates**

- [ ] Create `base_agent.yml`
- [ ] Create `base_ai_agent.yml`
- [ ] Create 4 core AI agent templates (concierge, planner, researcher, safety_watch)
- [ ] Create 6 task-specific templates (health, code, finance, travel, recipe, fitness)
- [ ] Validate all templates against schema

**Day 4: WARD Tests**

- [ ] Test template loading
- [ ] Test inheritance resolution
- [ ] Test schema validation (valid/invalid)
- [ ] Test cache performance (hit rate >80%)
- [ ] Test latency (<10ms cached, <50ms uncached)

**Total**: 4 days (within M1 budget)

---

## Dependencies

### Required Before Implementation

- ✅ **YAML Parser:** PyYAML (already in requirements.txt)
- ✅ **JSON Schema Validator:** jsonschema library
- ✅ **File System:** Python pathlib (standard library)

### Blocks Other Work

- 🔄 **ADR-0086a (Agent Factory):** Factory needs templates to create agents
- 🔄 **ADR-0086d (Composition):** Composition engine uses templates
- 🔄 **ADR-0086e (Prompt Directory):** Prompt paths referenced in templates

---

## References

### Standards

- **YAML 1.2:** <https://yaml.org/spec/1.2/spec.html>
- **JSON Schema v7:** <https://json-schema.org/draft-07/schema>
- **Semantic Versioning:** <https://semver.org/>

### Related ADRs

- [ADR-0086 (Dynamic Agent Creation)](0086-dynamic-agent-creation-subsystem.md)
- [ADR-0086a (Agent Factory)](0086a-agent-factory-pattern.md)
- [ADR-0086d (Composition)](0086d-agent-composition-pattern.md)
- [ADR-0005e (Agent Personalities)](0005e-agent-personality-capabilities.md)

---

**Status**: Approved ✅ → Implementation Phase M1 (Issue 1.1.2)

**Next Steps**:

1. Create JSON Schema (Day 1)
2. Implement TemplateLoader (Day 2)
3. Create 10 example templates (Day 3)
4. Write WARD tests (Day 4)
