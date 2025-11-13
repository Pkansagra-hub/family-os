---
adr_number: '0086e'
title: Prompt Directory & Template Management
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l3_execution.agent_factory.prompt_manager
- k1.l3_execution.agents.prompt_loader
- k1.config.prompts
- k1.l4_runtime.prompt_cache
concerns:
- architecture
- cost
- maintainability
- observability
- performance
- privacy
- reliability
- scalability
- testing
implementation_status: COMPLETED
implementation_phase: Phase 1 (M1 - Dynamic Agent Creation)
implementation_date: '2025-11-03'
propagation:
  affected_adrs:
  - ADR-0001b
  - ADR-0007a
  - ADR-0086
  - ADR-0086b
  - ADR-0086d
  - ADR-0086e
  affected_contracts:
  - k1/contracts/schemas/prompt_template.yml
  - k1/contracts/schemas/prompt_directory.yml
  - k1/contracts/flatbuffers/layer4_runtime/prompt_cache_entry.fbs
  affected_tests:
  - tests/k1/l3_execution/test_prompt_manager.py
  - tests/k1/l3_execution/test_prompt_loader.py
  - tests/k1/config/test_prompt_validation.py
  triggers:
  - Modifying system architecture
  - Performance requirement changes
related_adrs:
- ADR-0001b
- ADR-0007a
- ADR-0086
- ADR-0086b
- ADR-0086d
- ADR-0086e
- ADR-0086h
related_contracts: []
related_diagrams: []
research_citations:
- "Prompt Engineering (Brown et al., 2020)"
- "Template Systems (Parr, 2004)"
- "Configuration Management (Humble & Farley, 2010)"
---

# ADR-0086e: Prompt Directory & Template Management

**Status:** Approved ✅ - Implementation Phase M1
**Decision Date:** 2025-10-23
**Implementation Date:** TBD (M1 - Issue 1.1.2)
**Review Date:** TBD (Post-implementation)
**Last Updated:** 2025-10-23
**Authors:** K1 Architecture Team
**Category:** Prompt Engineering & Template Management
**Parent ADR:** [ADR-0086 (Dynamic Agent Creation Subsystem)](0086-dynamic-agent-creation-subsystem.md)
**Related ADRs:**

- [ADR-0086d (Agent Composition)](0086d-agent-composition-pattern.md) - Composition uses prompts
- [ADR-0086b (Template System)](0086b-agent-template-system.md) - Templates reference prompts
- [ADR-0007a (Sketch Prompt Engineering)](0007a-sketch-stage-llm-prompt-engineering.md) - Prompt design patterns
- [ADR-0001b (Model Hub)](0001b-model-hub-architecture-llm-integration.md) - Prompt library integration

---

## Context

### Problem Statement

Dynamic agent creation requires **versioned, reusable prompt templates** for task-specific agents:

1. **Prompt Versioning:** Track prompt evolution (breaking changes, improvements)
2. **Template Rendering:** Jinja2 templates with variable substitution
3. **Token Budget:** Validate prompts don't exceed model context limits
4. **Injection Protection:** Prevent malicious prompt injection
5. **Fast Loading:** <5ms P95 rendering for agent creation

**Current State (Hardcoded Prompts):**

```python
# Hardcoded prompts (current)
HEALTH_SPECIALIST_PROMPT = """
You are a health specialist AI agent.
You help users analyze health metrics and provide fitness recommendations.
Available tools: {tools}
"""  # Hardcoded in Python
```

**Problems:**

- ❌ Prompt changes require code deployment
- ❌ No versioning (can't roll back)
- ❌ No token validation
- ❌ Difficult to A/B test prompts

**Desired State (Prompt Directory):**

```
k1/l3_execution/model_hub/prompt_library/agent_prompts/
├── health_specialist.prompt.j2     # v1.0.0
├── code_assistant.prompt.j2        # v1.0.0
├── concierge.prompt.j2             # v1.2.0 (updated)
└── ...
```

```jinja2
{# health_specialist.prompt.j2 #}
{# Version: 1.0.0 #}
{# Max Tokens: 2000 #}

You are a health specialist AI agent focused on {{ domain }}.

**Your Role:**
- Analyze health metrics (steps, heart rate, sleep patterns)
- Provide evidence-based fitness recommendations
- Track progress over time

**Personality:**
- Tone: {{ persona.tone }}
- Style: {{ persona.style }}

**Available Tools:**
{% for tool in tools %}
- {{ tool }}: {{ tool_descriptions[tool] }}
{% endfor %}

**Instructions:**
Answer user questions about health metrics using available tools.
Be {{ persona.tone }} and focus on actionable insights.
```

---

## Decision

We will implement a **PromptLibrary** with Jinja2 rendering, versioning, and validation:

### 1. Directory Structure

```
k1/l3_execution/model_hub/prompt_library/
├── __init__.py                              # PromptLibrary class
├── agent_prompts/
│   ├── __init__.py
│   ├── concierge.prompt.j2                  # v1.2.0 (Intent classification)
│   ├── planner.prompt.j2                    # v1.0.0 (Task planning)
│   ├── researcher.prompt.j2                 # v1.0.0 (Knowledge synthesis)
│   ├── safety_watch.prompt.j2               # v1.0.0 (Content filtering)
│   ├── health_specialist.prompt.j2          # v1.0.0 (Health domain)
│   ├── code_assistant.prompt.j2             # v1.0.0 (Code tasks)
│   ├── finance_advisor.prompt.j2            # v1.0.0 (Finance domain)
│   ├── travel_planner.prompt.j2             # v1.0.0 (Travel planning)
│   ├── recipe_assistant.prompt.j2           # v1.0.0 (Cooking/recipes)
│   └── fitness_coach.prompt.j2              # v1.0.0 (Fitness coaching)
│
├── system_prompts/
│   ├── base_system.prompt.j2                # Base system prompt
│   └── safety_guidelines.prompt.j2          # Safety/ethical guidelines
│
└── README.md                                # Prompt authoring guide
```

### 2. Prompt Template Format

**Template Header (Metadata):**

```jinja2
{# health_specialist.prompt.j2 #}
{# Version: 1.0.0 #}
{# Max Tokens: 2000 #}
{# Last Updated: 2025-10-23 #}
{# Author: K1 Team #}
{# Changelog: Initial version #}
```

**Template Body (Jinja2):**

```jinja2
You are a {{ agent_type }} AI agent specialized in {{ domain }}.

**Your Role:**
{{ role_description }}

**Personality:**
- Tone: {{ persona.tone }}
- Response Time Budget: {{ persona.response_time_budget_ms }}ms
- Reasoning Style: {{ persona.reasoning_style }}

**Available Tools:**
{% if tools|length > 0 %}
{% for tool in tools %}
- **{{ tool }}**: {{ tool_descriptions.get(tool, "Tool for " + tool) }}
{% endfor %}
{% else %}
No tools available (MODEL_CALL only).
{% endif %}

**Instructions:**
{{ instructions }}

**Examples:**
{{ examples }}

**Output Format:**
{{ output_format }}
```

### 3. PromptLibrary Implementation

```python
# k1/l3_execution/model_hub/prompt_library/__init__.py

from pathlib import Path
from typing import Dict, Optional
import jinja2
import re
import hashlib
from dataclasses import dataclass
from prometheus_client import Counter, Histogram

@dataclass
class PromptMetadata:
    """Prompt template metadata"""
    version: str
    max_tokens: int
    last_updated: str
    author: str
    changelog: str


@dataclass
class RenderedPrompt:
    """Rendered prompt with metadata"""
    content: str
    metadata: PromptMetadata
    token_count: int
    render_time_ms: float


class PromptLibrary:
    """
    Jinja2 prompt template library with versioning and validation.

    Responsibilities:
    1. Load Jinja2 prompt templates from disk
    2. Render templates with context variables
    3. Validate token budgets (<8000 tokens)
    4. Extract metadata (version, max_tokens)
    5. Cache rendered prompts (hash-based)

    Performance Target: <5ms P95 rendering
    """

    def __init__(
        self,
        prompts_dir: Path,
        cache_size: int = 128
    ):
        """
        Initialize prompt library.

        Args:
            prompts_dir: Path to agent_prompts/ directory
            cache_size: Cache size for rendered prompts
        """
        self.prompts_dir = prompts_dir
        self.cache_size = cache_size

        # Jinja2 environment
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(prompts_dir.parent),
            autoescape=jinja2.select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Render cache (hash → RenderedPrompt)
        self._cache: Dict[str, RenderedPrompt] = {}

        # Metrics
        self._init_metrics()

    async def load_template(
        self,
        template_path: str,
        trace_id: str = ""
    ) -> jinja2.Template:
        """
        Load Jinja2 template from disk.

        Args:
            template_path: Relative path (e.g., "agent_prompts/health_specialist.prompt.j2")
            trace_id: Trace ID for observability

        Returns:
            jinja2.Template: Loaded template (not yet rendered)

        Raises:
            TemplateNotFound: Template file doesn't exist
        """
        try:
            template = self.jinja_env.get_template(template_path)

            logger.debug(
                "prompt_template_loaded",
                template_path=template_path,
                trace_id=trace_id
            )

            return template

        except jinja2.TemplateNotFound as e:
            logger.error(
                "prompt_template_not_found",
                template_path=template_path,
                error=str(e),
                trace_id=trace_id
            )
            raise

    async def render(
        self,
        template_path: str,
        context: Dict,
        trace_id: str = ""
    ) -> RenderedPrompt:
        """
        Render prompt template with context.

        Flow:
        1. Compute cache key (template_path + context hash)
        2. Check cache (hit → return cached)
        3. Load template
        4. Extract metadata from comments
        5. Render with Jinja2
        6. Validate token budget
        7. Cache result

        Performance: <5ms P95

        Args:
            template_path: Template path
            context: Jinja2 context variables
            trace_id: Trace ID

        Returns:
            RenderedPrompt: Rendered content + metadata

        Raises:
            TokenBudgetExceeded: Rendered prompt exceeds max_tokens
        """
        import time
        start_time = time.perf_counter()

        # Step 1: Compute cache key
        cache_key = self._compute_cache_key(template_path, context)

        # Step 2: Check cache
        if cache_key in self._cache:
            self._metrics_cache_hits.inc()

            logger.debug(
                "prompt_cache_hit",
                template_path=template_path,
                cache_key=cache_key,
                trace_id=trace_id
            )

            return self._cache[cache_key]

        self._metrics_cache_misses.inc()

        # Step 3: Load template
        template = await self.load_template(template_path, trace_id)

        # Step 4: Extract metadata
        metadata = self._extract_metadata(template.source)

        # Step 5: Render with Jinja2
        rendered_content = template.render(**context)

        # Step 6: Validate token budget
        token_count = self._estimate_tokens(rendered_content)

        if token_count > metadata.max_tokens:
            self._metrics_token_budget_exceeded.inc()

            raise TokenBudgetExceeded(
                f"Rendered prompt {token_count} tokens exceeds budget {metadata.max_tokens}"
            )

        # Step 7: Create result
        render_time_ms = (time.perf_counter() - start_time) * 1000

        rendered = RenderedPrompt(
            content=rendered_content,
            metadata=metadata,
            token_count=token_count,
            render_time_ms=render_time_ms
        )

        # Cache result
        self._add_to_cache(cache_key, rendered)

        # Metrics
        self._metrics_render_latency.observe(render_time_ms)

        logger.info(
            "prompt_rendered",
            template_path=template_path,
            version=metadata.version,
            token_count=token_count,
            max_tokens=metadata.max_tokens,
            render_time_ms=render_time_ms,
            trace_id=trace_id
        )

        return rendered

    def _extract_metadata(self, template_source: str) -> PromptMetadata:
        """
        Extract metadata from Jinja2 template comments.

        Expected format:
        {# Version: 1.0.0 #}
        {# Max Tokens: 2000 #}
        {# Last Updated: 2025-10-23 #}
        {# Author: K1 Team #}
        {# Changelog: Initial version #}
        """
        version = self._extract_field(template_source, "Version", default="1.0.0")
        max_tokens = int(self._extract_field(template_source, "Max Tokens", default="8000"))
        last_updated = self._extract_field(template_source, "Last Updated", default="unknown")
        author = self._extract_field(template_source, "Author", default="K1 Team")
        changelog = self._extract_field(template_source, "Changelog", default="")

        return PromptMetadata(
            version=version,
            max_tokens=max_tokens,
            last_updated=last_updated,
            author=author,
            changelog=changelog
        )

    def _extract_field(self, source: str, field_name: str, default: str = "") -> str:
        """Extract field value from Jinja2 comment"""
        pattern = rf'{{\#\s*{field_name}:\s*(.+?)\s*\#}}'
        match = re.search(pattern, source)
        return match.group(1).strip() if match else default

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count (rough approximation).

        Rule of thumb: 1 token ≈ 4 characters
        More accurate: Use tiktoken library (future M2)
        """
        return len(text) // 4

    def _compute_cache_key(self, template_path: str, context: Dict) -> str:
        """Compute cache key from template + context"""
        # Sort context keys for consistency
        context_str = ":".join(f"{k}={v}" for k, v in sorted(context.items()))
        hash_input = f"{template_path}:{context_str}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    def _add_to_cache(self, cache_key: str, rendered: RenderedPrompt):
        """Add to cache with LRU eviction"""
        if len(self._cache) >= self.cache_size:
            # Evict oldest
            first_key = next(iter(self._cache))
            del self._cache[first_key]

        self._cache[cache_key] = rendered

    def invalidate_cache(self, cache_key: Optional[str] = None):
        """Invalidate cache (single or all)"""
        if cache_key:
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()

    def _init_metrics(self):
        """Initialize Prometheus metrics"""
        self._metrics_render_latency = Histogram(
            'k1_prompt_render_latency_ms',
            'Prompt rendering latency in milliseconds',
            buckets=[1, 2, 3, 5, 10, 20, 30]
        )

        self._metrics_cache_hits = Counter(
            'k1_prompt_cache_hits_total',
            'Prompt cache hits'
        )

        self._metrics_cache_misses = Counter(
            'k1_prompt_cache_misses_total',
            'Prompt cache misses'
        )

        self._metrics_token_budget_exceeded = Counter(
            'k1_prompt_token_budget_exceeded_total',
            'Prompts exceeding token budget'
        )


class TokenBudgetExceeded(Exception):
    """Raised when rendered prompt exceeds token budget"""
    pass
```

---

## Example Prompt Templates

### Health Specialist

```jinja2
{# health_specialist.prompt.j2 #}
{# Version: 1.0.0 #}
{# Max Tokens: 2000 #}
{# Last Updated: 2025-10-23 #}
{# Author: K1 Team #}
{# Changelog: Initial version for health metrics analysis #}

You are a health specialist AI agent focused on {{ domain|default("general wellness") }}.

**Your Role:**
- Analyze health metrics: steps, heart rate, sleep patterns, calories
- Provide evidence-based fitness recommendations
- Track progress over time and identify trends

**Personality:**
- Tone: {{ persona.tone|default("empathetic") }}
- Style: {{ persona.reasoning_style|default("data_driven") }}
- Response Budget: {{ persona.response_time_budget_ms|default(3000) }}ms

**Available Tools:**
{% if tools|length > 0 %}
{% for tool in tools %}
- **{{ tool }}**: Access {{ tool.replace("_", " ") }} data
{% endfor %}
{% else %}
*No tools available - rely on general knowledge only*
{% endif %}

**Instructions:**
1. Greet user warmly and acknowledge their health query
2. Use available tools to gather relevant health metrics
3. Analyze data and identify patterns/trends
4. Provide actionable recommendations based on evidence
5. Encourage progress and maintain {{ persona.tone }} tone

**Example:**
User: "What does my health metrics show?"
You: "I'd be happy to review your health metrics! Let me check your recent activity..."
[Use health_metrics tool]
"Great progress! You've averaged 8,500 steps per day this week, which is above the recommended 7,500 steps. Your sleep quality is solid at 7.2 hours per night. I recommend focusing on consistency rather than intensity..."

**Output Format:**
- Start with empathetic acknowledgment
- Present key metrics clearly
- Provide 2-3 actionable recommendations
- End with encouragement
```

### Code Assistant

```jinja2
{# code_assistant.prompt.j2 #}
{# Version: 1.0.0 #}
{# Max Tokens: 3000 #}
{# Last Updated: 2025-10-23 #}
{# Author: K1 Team #}
{# Changelog: Initial version for code tasks #}

You are a code assistant AI agent specialized in {{ domain|default("software engineering") }}.

**Your Role:**
- Code generation and review
- Debugging and error analysis
- Refactoring and optimization
- Test generation

**Personality:**
- Tone: {{ persona.tone|default("technical") }}
- Style: {{ persona.reasoning_style|default("deep_reasoning") }}
- Response Budget: {{ persona.response_time_budget_ms|default(5000) }}ms

**Available Tools:**
{% if tools|length > 0 %}
{% for tool in tools %}
- **{{ tool }}**: {{ tool_descriptions.get(tool, "Code analysis tool") }}
{% endfor %}
{% else %}
*No tools available*
{% endif %}

**Coding Standards:**
- Follow PEP 8 for Python
- Use type hints
- Write clear docstrings
- Handle errors explicitly
- Prefer readability over cleverness

**Instructions:**
1. Understand the user's code request
2. Use tools to analyze existing code (if applicable)
3. Generate/review code following best practices
4. Explain your reasoning
5. Provide tests if applicable

**Example:**
User: "Write a function to parse CSV files"
You: "I'll create a CSV parser with error handling and type hints..."
```python
def parse_csv(filepath: str) -> list[dict]:
    """Parse CSV file and return list of dictionaries."""
    import csv
    try:
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except FileNotFoundError:
        raise ValueError(f"CSV file not found: {filepath}")
```

**Output Format:**

- Provide code in markdown code blocks
- Include docstrings and comments
- Explain key decisions
- Add usage examples

```

---

## Performance Budgets

| Metric | Budget | Rationale |
|--------|--------|-----------|
| **Rendering (cached)** | <2ms P95 | Hash lookup + copy |
| **Rendering (uncached)** | <5ms P95 | Jinja2 rendering |
| **Template loading** | <3ms | Disk I/O (small files) |
| **Token estimation** | <1ms | Character counting |
| **Metadata extraction** | <1ms | Regex matching |
| **Cache hit rate** | >80% | Most agents reuse prompts |

---

## Validation & Testing

### WARD Integration Tests

```python
# tests/l3_execution/model_hub/test_prompt_library.py

from ward import test, fixture
from k1.l3_execution.model_hub.prompt_library import PromptLibrary

@fixture
def prompt_library():
    """Prompt library fixture"""
    prompts_dir = Path("k1/l3_execution/model_hub/prompt_library/agent_prompts")
    library = PromptLibrary(prompts_dir=prompts_dir)
    yield library
    library.invalidate_cache()


@test("render prompt successfully")
async def _(lib=prompt_library):
    context = {
        "agent_type": "health_specialist",
        "domain": "fitness",
        "persona": {"tone": "empathetic", "reasoning_style": "data_driven"},
        "tools": ["health_metrics", "activity_tracker"]
    }

    rendered = await lib.render(
        template_path="agent_prompts/health_specialist.prompt.j2",
        context=context,
        trace_id="test_1"
    )

    assert "health specialist" in rendered.content.lower()
    assert "empathetic" in rendered.content
    assert "health_metrics" in rendered.content


@test("validate token budget")
async def _(lib=prompt_library):
    # Create context that generates long prompt
    context = {
        "tools": ["tool_" + str(i) for i in range(1000)]  # Too many tools
    }

    with expecting(TokenBudgetExceeded):
        await lib.render(
            template_path="agent_prompts/health_specialist.prompt.j2",
            context=context,
            trace_id="test_2"
        )


@test("rendering latency <5ms P95")
async def _(lib=prompt_library):
    import time

    context = {
        "agent_type": "health_specialist",
        "persona": {"tone": "friendly"},
        "tools": ["health_metrics"]
    }

    latencies = []
    for i in range(100):
        lib.invalidate_cache()  # Force uncached

        start = time.perf_counter()
        await lib.render(
            template_path="agent_prompts/health_specialist.prompt.j2",
            context=context,
            trace_id=f"test_3_{i}"
        )
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    p95 = sorted(latencies)[94]
    assert p95 < 5, f"P95 render latency {p95:.2f}ms exceeds 5ms budget"
```

---

## Implementation Plan

**Day 1: Prompt Library (1 day)**

- [ ] Create `PromptLibrary` class
- [ ] Implement Jinja2 rendering
- [ ] Add metadata extraction
- [ ] Add token validation
- [ ] Create 10 example prompts
- [ ] Write WARD tests

**Total**: 1 day (within M1 budget)

---

## Dependencies

### Required

- ✅ **Jinja2:** Template rendering (already in requirements)
- ✅ **Python pathlib:** File system access

### Blocks

- 🔄 **ADR-0086d (Composition):** Composition needs prompt loading

---

## References

- [ADR-0086 (Dynamic Agent Creation)](0086-dynamic-agent-creation-subsystem.md)
- [ADR-0086d (Agent Composition)](0086d-agent-composition-pattern.md)
- [ADR-0007a (Sketch Prompt Engineering)](0007a-sketch-stage-llm-prompt-engineering.md)

---

**Status**: Approved ✅ → Implementation Phase M1 (Issue 1.1.2)

**Next Steps**:

1. Implement PromptLibrary (Day 1)
2. Create 10 example prompts
3. Write WARD tests
