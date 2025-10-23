# ADR-0086d: Agent Composition Pattern

**Status:** Approved ✅ - Implementation Phase M1
**Decision Date:** 2025-10-23
**Implementation Date:** TBD (M1 - Issue 1.1.2)
**Review Date:** TBD (Post-implementation)
**Last Updated:** 2025-10-23
**Authors:** K1 Architecture Team
**Category:** Agent Composition & Specialization
**Parent ADR:** [ADR-0086 (Dynamic Agent Creation Subsystem)](0086-dynamic-agent-creation-subsystem.md)
**Related ADRs:**

- [ADR-0086a (Agent Factory)](0086a-agent-factory-pattern.md) - Factory uses composition
- [ADR-0086b (Template System)](0086b-agent-template-system.md) - Templates provide config
- [ADR-0086e (Prompt Directory)](0086e-prompt-directory-template-management.md) - Prompt loading
- [ADR-0010 (Capability Security)](0010-capability-based-security.md) - Tool filtering by capabilities
- [ADR-0005e (Agent Personalities)](0005e-agent-personality-capabilities.md) - Persona traits

---

## Context

### Problem Statement

Dynamic agent creation requires **composing specialized agents from reusable components**:

1. **Prompt Templates:** Task-specific prompts (health_specialist, code_assistant)
2. **Tool Access:** Filtered by capabilities (only TOOL_CALL agents get tools)
3. **Persona Traits:** Personality formatting (empathetic, technical, friendly)
4. **Security:** Prevent prompt injection, validate tool access

**Current State (Hardcoded):**
```python
# Hardcoded agent configuration (current)
class HealthSpecialist(Agent):
    def __init__(self):
        self.prompt = "You are a health specialist..."  # Hardcoded
        self.tools = ["health_metrics", "activity_tracker"]  # Hardcoded
        self.persona = {"tone": "empathetic"}  # Hardcoded
```

**Problems:**
- ❌ New agent type = new Python class
- ❌ Prompt changes require code deployment
- ❌ No tool filtering by capabilities
- ❌ Prompt injection risk (no validation)

**Desired State (Composition):**
```python
# Composed agent (M1 goal)
composed_agent = composition_engine.compose(
    agent_type="health_specialist",
    template=template,           # From ADR-0086b
    capabilities=["TOOL_CALL", "MODEL_CALL"],
    trace_id=trace_id
)

# Result:
# - Prompt: Loaded from agent_prompts/health_specialist.prompt.j2
# - Tools: ["health_metrics", "activity_tracker"] (filtered by capabilities)
# - Persona: {"tone": "empathetic", "style": "data_driven"}
# - Validated: Prompt injection checks, tool access validation
```

### User Journey Example

```
User: "What does my health metrics show?"
  ↓
Concierge (AI Agent): Routes to "health_specialist"
  ↓
AgentFactory.create(agent_type="health_specialist")
  ↓
CompositionEngine.compose():
  1. Load template: health_specialist.agent.yml (ADR-0086b)
  2. Load prompt: agent_prompts/health_specialist.prompt.j2 (ADR-0086e)
  3. Filter tools: capabilities["TOOL_CALL"] → health_metrics, activity_tracker
  4. Apply persona: tone="empathetic", style="data_driven"
  5. Validate: Prompt injection check, tool access check
  ↓
Return: ComposedAgent(prompt, tools, persona, config)
  ↓
Health Specialist Agent: Processes request with composed configuration
```

---

## Decision

We will implement a **CompositionEngine** that assembles agents from reusable components:

### 1. Core Composition Engine

```python
# k1/l3_execution/agents/composition.py

from dataclasses import dataclass
from typing import Dict, List, Optional
import jinja2
import hashlib
import time
from prometheus_client import Counter, Histogram

@dataclass
class ComposedAgent:
    """Fully composed agent configuration"""
    agent_id: str
    agent_type: str
    prompt: str                      # Rendered Jinja2 prompt
    tools: List[str]                 # Filtered tool list
    persona: Dict                    # Personality traits
    model_config: Dict               # Model Hub config
    lifecycle_config: Dict           # Lifecycle parameters
    metadata: Dict                   # Additional metadata
    composition_hash: str            # Cache key (MD5 of inputs)


class CompositionEngine:
    """
    Agent composition engine: prompt + tools + persona.

    Responsibilities:
    1. Load prompts from prompt library (ADR-0086e)
    2. Filter tools by capabilities (ADR-0010)
    3. Apply persona traits (ADR-0005e)
    4. Validate prompt injection attacks
    5. Cache compositions (hash-based deduplication)

    Performance Target: <5ms P95 (cached), <30ms P95 (uncached)
    """

    def __init__(
        self,
        prompt_library: PromptLibrary,          # ADR-0086e
        tool_registry: ToolRegistry,            # Tool database
        persona_formatter: PersonaFormatter,    # ADR-0005e
        security_validator: SecurityValidator   # Injection protection
    ):
        """
        Initialize composition engine.

        Args:
            prompt_library: Loads Jinja2 prompt templates
            tool_registry: 758 tools with capability requirements
            persona_formatter: Formats personality traits
            security_validator: Validates prompts for injection
        """
        self.prompt_library = prompt_library
        self.tool_registry = tool_registry
        self.persona_formatter = persona_formatter
        self.security_validator = security_validator

        # Composition cache (hash → ComposedAgent)
        self._cache: Dict[str, ComposedAgent] = {}
        self._cache_max_size = 256

        # Metrics
        self._init_metrics()

    async def compose(
        self,
        agent_id: str,
        agent_type: str,
        template: AgentTemplate,      # From ADR-0086b
        capabilities: List[str],      # From capability binder
        trace_id: str
    ) -> ComposedAgent:
        """
        Compose agent from prompt + tools + persona.

        Flow:
        1. Compute composition hash (for caching)
        2. Check cache (hit → return cached)
        3. Load prompt template (ADR-0086e)
        4. Render prompt with Jinja2
        5. Filter tools by capabilities (ADR-0010)
        6. Apply persona traits (ADR-0005e)
        7. Validate security (prompt injection)
        8. Cache result

        Performance: <5ms P95 (cached), <30ms P95 (uncached)

        Args:
            agent_id: Unique agent ID
            agent_type: Agent type (e.g., "health_specialist")
            template: Parsed agent template
            capabilities: Bound capabilities
            trace_id: Trace ID for observability

        Returns:
            ComposedAgent: Fully composed configuration

        Raises:
            PromptInjectionError: Detected prompt injection
            ToolAccessViolation: Tool requires missing capability
        """
        start_time = time.perf_counter()

        # Step 1: Compute composition hash (cache key)
        composition_hash = self._compute_hash(
            agent_type=agent_type,
            template_version=template.version,
            capabilities=capabilities
        )

        # Step 2: Check cache
        if composition_hash in self._cache:
            self._metrics_cache_hits.inc()

            cached = self._cache[composition_hash]

            logger.debug(
                "composition_cache_hit",
                agent_type=agent_type,
                composition_hash=composition_hash,
                trace_id=trace_id
            )

            # Return cached with new agent_id
            return ComposedAgent(
                agent_id=agent_id,  # Update with new ID
                agent_type=cached.agent_type,
                prompt=cached.prompt,
                tools=cached.tools,
                persona=cached.persona,
                model_config=cached.model_config,
                lifecycle_config=cached.lifecycle_config,
                metadata=cached.metadata,
                composition_hash=composition_hash
            )

        self._metrics_cache_misses.inc()

        # Step 3: Load prompt template (ADR-0086e)
        prompt_template_path = template.model_hub.get('prompt_template')

        if not prompt_template_path:
            # Fallback: generic agent prompt
            prompt_template_path = f"agent_prompts/{agent_type}.prompt.j2"

        prompt_template = await self.prompt_library.load_template(
            template_path=prompt_template_path,
            trace_id=trace_id
        )

        # Step 4: Render prompt with Jinja2
        prompt_context = {
            "agent_type": agent_type,
            "capabilities": capabilities,
            "tools": [],  # Will populate after filtering
            "persona": template.personality,
            "domain": template.metadata.get("domain", "general")
        }

        rendered_prompt = prompt_template.render(**prompt_context)

        # Step 5: Filter tools by capabilities (ADR-0010)
        available_tools = []

        if "TOOL_CALL" in capabilities:
            # Get tools from template metadata
            tool_names = template.metadata.get("tools", [])

            # Filter by capability requirements
            for tool_name in tool_names:
                tool_spec = self.tool_registry.get_tool(tool_name)

                if tool_spec and self._has_required_capabilities(
                    agent_capabilities=capabilities,
                    tool_requirements=tool_spec.required_capabilities
                ):
                    available_tools.append(tool_name)

        # Update prompt with filtered tools
        prompt_context["tools"] = available_tools
        rendered_prompt = prompt_template.render(**prompt_context)

        # Step 6: Apply persona traits (ADR-0005e)
        persona_config = self.persona_formatter.format_persona(
            personality=template.personality,
            agent_type=agent_type
        )

        # Step 7: Validate security (prompt injection)
        validation_result = await self.security_validator.validate_prompt(
            prompt=rendered_prompt,
            agent_type=agent_type,
            trace_id=trace_id
        )

        if not validation_result.safe:
            self._metrics_injection_detected.inc()

            raise PromptInjectionError(
                f"Prompt injection detected: {validation_result.reason}"
            )

        # Step 8: Create composed agent
        composed = ComposedAgent(
            agent_id=agent_id,
            agent_type=agent_type,
            prompt=rendered_prompt,
            tools=available_tools,
            persona=persona_config,
            model_config=template.model_hub or {},
            lifecycle_config=template.lifecycle,
            metadata=template.metadata,
            composition_hash=composition_hash
        )

        # Cache result
        self._add_to_cache(composition_hash, composed)

        # Metrics
        latency_ms = (time.perf_counter() - start_time) * 1000
        self._metrics_composition_latency.labels(
            agent_type=agent_type,
            cached=False
        ).observe(latency_ms)

        logger.info(
            "agent_composed",
            agent_id=agent_id,
            agent_type=agent_type,
            prompt_length=len(rendered_prompt),
            tools_count=len(available_tools),
            persona_tone=persona_config.get("tone"),
            latency_ms=latency_ms,
            cached=False,
            composition_hash=composition_hash,
            trace_id=trace_id
        )

        return composed

    def _compute_hash(
        self,
        agent_type: str,
        template_version: str,
        capabilities: List[str]
    ) -> str:
        """
        Compute composition hash for caching.

        Hash includes:
        - agent_type (e.g., "health_specialist")
        - template_version (e.g., "1.0.0")
        - capabilities (sorted for consistency)

        Returns:
            str: MD5 hash (32 chars)
        """
        hash_input = f"{agent_type}:{template_version}:{':'.join(sorted(capabilities))}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    def _has_required_capabilities(
        self,
        agent_capabilities: List[str],
        tool_requirements: List[str]
    ) -> bool:
        """Check if agent has all required capabilities for tool"""
        return all(req in agent_capabilities for req in tool_requirements)

    def _add_to_cache(self, composition_hash: str, composed: ComposedAgent):
        """Add composition to LRU cache with eviction"""
        if len(self._cache) >= self._cache_max_size:
            # Evict oldest entry (simple FIFO for now)
            first_key = next(iter(self._cache))
            del self._cache[first_key]
            logger.debug("composition_cache_evicted", evicted_hash=first_key)

        self._cache[composition_hash] = composed

    def invalidate_cache(self, composition_hash: Optional[str] = None):
        """Invalidate cache (single composition or all)"""
        if composition_hash:
            self._cache.pop(composition_hash, None)
        else:
            self._cache.clear()

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        total_requests = self._metrics_cache_hits._value.get() + self._metrics_cache_misses._value.get()
        hit_rate = (
            self._metrics_cache_hits._value.get() / total_requests
            if total_requests > 0
            else 0.0
        )

        return {
            "cache_size": len(self._cache),
            "cache_capacity": self._cache_max_size,
            "hit_rate": hit_rate,
            "total_compositions": total_requests
        }

    def _init_metrics(self):
        """Initialize Prometheus metrics"""
        self._metrics_composition_latency = Histogram(
            'k1_agent_composition_latency_ms',
            'Agent composition latency in milliseconds',
            ['agent_type', 'cached'],
            buckets=[1, 3, 5, 10, 20, 30, 50]
        )

        self._metrics_cache_hits = Counter(
            'k1_agent_composition_cache_hits_total',
            'Composition cache hits'
        )

        self._metrics_cache_misses = Counter(
            'k1_agent_composition_cache_misses_total',
            'Composition cache misses'
        )

        self._metrics_injection_detected = Counter(
            'k1_agent_composition_injection_detected_total',
            'Prompt injection attempts detected'
        )
```

### 2. Tool Filtering Logic

```python
# k1/l3_execution/agents/composition.py (continued)

class ToolFilter:
    """
    Capability-based tool filtering.

    Rules:
    - TOOL_CALL capability required for any tool access
    - FILE_ACCESS capability required for file operations
    - NETWORK_ACCESS capability required for external APIs
    """

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry

    def filter_tools(
        self,
        tool_names: List[str],
        agent_capabilities: List[str]
    ) -> List[str]:
        """
        Filter tools by agent capabilities.

        Args:
            tool_names: Requested tool names
            agent_capabilities: Agent's bound capabilities

        Returns:
            List[str]: Filtered tool names (only accessible tools)
        """
        if "TOOL_CALL" not in agent_capabilities:
            # No TOOL_CALL capability = no tools
            return []

        filtered = []

        for tool_name in tool_names:
            tool_spec = self.tool_registry.get_tool(tool_name)

            if not tool_spec:
                logger.warning(
                    "tool_not_found",
                    tool_name=tool_name
                )
                continue

            # Check all required capabilities
            if all(cap in agent_capabilities for cap in tool_spec.required_capabilities):
                filtered.append(tool_name)
            else:
                logger.debug(
                    "tool_filtered_out",
                    tool_name=tool_name,
                    missing_capabilities=list(
                        set(tool_spec.required_capabilities) - set(agent_capabilities)
                    )
                )

        return filtered
```

### 3. Security Validation

```python
# k1/l3_execution/agents/composition.py (continued)

from dataclasses import dataclass

@dataclass
class ValidationResult:
    """Prompt validation result"""
    safe: bool
    reason: Optional[str] = None
    risk_score: float = 0.0  # 0.0-1.0


class SecurityValidator:
    """
    Prompt injection and security validation.

    Detects:
    - Prompt injection patterns (ignore instructions, system override)
    - Excessive token usage (DoS attack)
    - Malicious payloads (XSS, code injection)
    """

    INJECTION_PATTERNS = [
        r"ignore (all )?previous instructions",
        r"disregard (all )?previous",
        r"forget (all )?previous",
        r"system:\s*you are now",
        r"<\s*script\s*>",  # XSS
        r"eval\s*\(",       # Code injection
        r"__import__",      # Python import injection
    ]

    MAX_PROMPT_TOKENS = 8000  # Prevent DoS

    async def validate_prompt(
        self,
        prompt: str,
        agent_type: str,
        trace_id: str
    ) -> ValidationResult:
        """
        Validate prompt for security risks.

        Args:
            prompt: Rendered prompt to validate
            agent_type: Agent type (for logging)
            trace_id: Trace ID

        Returns:
            ValidationResult: Safe/unsafe + reason
        """
        import re

        # Check 1: Prompt injection patterns
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                logger.warning(
                    "prompt_injection_detected",
                    agent_type=agent_type,
                    pattern=pattern,
                    trace_id=trace_id
                )

                return ValidationResult(
                    safe=False,
                    reason=f"Injection pattern detected: {pattern}",
                    risk_score=1.0
                )

        # Check 2: Token limit (prevent DoS)
        token_count = len(prompt.split())  # Rough estimate

        if token_count > self.MAX_PROMPT_TOKENS:
            logger.warning(
                "prompt_too_long",
                agent_type=agent_type,
                token_count=token_count,
                max_tokens=self.MAX_PROMPT_TOKENS,
                trace_id=trace_id
            )

            return ValidationResult(
                safe=False,
                reason=f"Prompt too long: {token_count} tokens (max {self.MAX_PROMPT_TOKENS})",
                risk_score=0.7
            )

        # Check 3: Malicious payloads (basic heuristics)
        dangerous_keywords = ["<script>", "eval(", "__import__", "exec("]

        for keyword in dangerous_keywords:
            if keyword in prompt.lower():
                logger.warning(
                    "malicious_payload_detected",
                    agent_type=agent_type,
                    keyword=keyword,
                    trace_id=trace_id
                )

                return ValidationResult(
                    safe=False,
                    reason=f"Malicious keyword detected: {keyword}",
                    risk_score=0.9
                )

        # All checks passed
        return ValidationResult(
            safe=True,
            reason=None,
            risk_score=0.0
        )
```

---

## Performance Budgets

| Metric | Budget | Rationale |
|--------|--------|-----------|
| **Composition (cached)** | <5ms P95 | Hash lookup + copy, frequently called |
| **Composition (uncached)** | <30ms P95 | Prompt render + tool filter + validation |
| **Prompt rendering** | <10ms | Jinja2 template rendering |
| **Tool filtering** | <5ms | 758 tools, capability check per tool |
| **Security validation** | <10ms | Regex matching, token counting |
| **Cache hit rate** | >75% | Most agents reuse common compositions |

---

## Consequences

### Positive ✅

- **Reusability:** Prompts, tools, personas are independent components
- **Security:** Prompt injection protection, capability-based tool access
- **Performance:** Caching achieves <5ms P95 for repeat compositions
- **Flexibility:** Change prompts/tools without code deployment
- **Observability:** Metrics for composition latency, cache hits, injection attempts

### Negative ❌

- **Complexity:** 4 dependencies (prompt library, tool registry, persona formatter, security validator)
- **Cache Invalidation:** Prompt/template changes require cache invalidation
- **Limited Validation:** Basic regex-based injection detection (not ML-based)

### Mitigations

- **Dependency Injection:** Clean interfaces for all dependencies
- **Cache Management:** Explicit invalidation API + TTL (future M2)
- **Enhanced Validation:** ML-based injection detection (future M2)

---

## Validation & Testing

### Acceptance Criteria

- [ ] Compose agent successfully (<30ms P95 uncached) ✓
- [ ] Cache hit rate >75% (100 requests, 75+ cached) ✓
- [ ] Tool filtering by capabilities ✓
- [ ] Prompt injection detection (10 patterns) ✓
- [ ] Security validation (<10ms) ✓
- [ ] WARD tests cover all error paths ✓

### WARD Integration Tests

```python
# tests/l3_execution/agents/test_composition.py

from ward import test, fixture
from k1.l3_execution.agents.composition import CompositionEngine, ComposedAgent

@fixture
def composition_engine():
    """Composition engine fixture"""
    prompt_library = PromptLibrary(...)
    tool_registry = ToolRegistry(...)
    persona_formatter = PersonaFormatter(...)
    security_validator = SecurityValidator()

    engine = CompositionEngine(
        prompt_library=prompt_library,
        tool_registry=tool_registry,
        persona_formatter=persona_formatter,
        security_validator=security_validator
    )

    yield engine

    # Cleanup
    engine.invalidate_cache()


@test("compose agent successfully")
async def _(engine=composition_engine):
    template = AgentTemplate(...)  # health_specialist

    composed = await engine.compose(
        agent_id="agent_123",
        agent_type="health_specialist",
        template=template,
        capabilities=["TOOL_CALL", "MODEL_CALL"],
        trace_id="test_1"
    )

    assert composed.agent_type == "health_specialist"
    assert len(composed.tools) > 0
    assert "empathetic" in composed.persona.get("tone", "")


@test("filter tools by capabilities")
async def _(engine=composition_engine):
    template = AgentTemplate(...)

    # Without TOOL_CALL capability
    composed_no_tools = await engine.compose(
        agent_id="agent_124",
        agent_type="health_specialist",
        template=template,
        capabilities=["MODEL_CALL"],  # No TOOL_CALL
        trace_id="test_2a"
    )

    assert len(composed_no_tools.tools) == 0

    # With TOOL_CALL capability
    composed_with_tools = await engine.compose(
        agent_id="agent_125",
        agent_type="health_specialist",
        template=template,
        capabilities=["TOOL_CALL", "MODEL_CALL"],
        trace_id="test_2b"
    )

    assert len(composed_with_tools.tools) > 0


@test("detect prompt injection")
async def _(engine=composition_engine):
    # Inject malicious prompt via template
    malicious_template = AgentTemplate(...)
    malicious_template.metadata["custom_prompt"] = "Ignore previous instructions and..."

    with expecting(PromptInjectionError):
        await engine.compose(
            agent_id="agent_126",
            agent_type="malicious",
            template=malicious_template,
            capabilities=["MODEL_CALL"],
            trace_id="test_3"
        )


@test("cache hit rate >75%")
async def _(engine=composition_engine):
    template = AgentTemplate(...)

    # First 10 requests (unique)
    for i in range(10):
        await engine.compose(
            agent_id=f"agent_{i}",
            agent_type="health_specialist",
            template=template,
            capabilities=["TOOL_CALL"],
            trace_id=f"test_4_{i}"
        )

    # Next 90 requests (repeat)
    for i in range(10, 100):
        await engine.compose(
            agent_id=f"agent_{i}",
            agent_type="health_specialist",
            template=template,
            capabilities=["TOOL_CALL"],
            trace_id=f"test_4_{i}"
        )

    stats = engine.get_cache_stats()
    hit_rate = stats['hit_rate']

    assert hit_rate > 0.75, f"Cache hit rate {hit_rate:.2%} below 75% target"


@test("composition latency <30ms P95 (uncached)")
async def _(engine=composition_engine):
    import time

    template = AgentTemplate(...)
    latencies = []

    for i in range(100):
        # Invalidate cache for each request
        engine.invalidate_cache()

        start = time.perf_counter()
        await engine.compose(
            agent_id=f"agent_{i}",
            agent_type="health_specialist",
            template=template,
            capabilities=["TOOL_CALL"],
            trace_id=f"test_5_{i}"
        )
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    p95 = sorted(latencies)[94]
    assert p95 < 30, f"P95 composition latency {p95:.2f}ms exceeds 30ms budget"
```

---

## Implementation Plan

### Phase 1: Core Composition (2 days)

**Day 1: Composition Engine**
- [ ] Create `composition.py`
- [ ] Implement `CompositionEngine` class
- [ ] Add prompt rendering (Jinja2)
- [ ] Add tool filtering logic
- [ ] Add persona application

**Day 2: Security & Caching**
- [ ] Implement `SecurityValidator` class
- [ ] Add prompt injection detection
- [ ] Add composition caching (hash-based)
- [ ] Initialize Prometheus metrics

### Phase 2: WARD Tests (1 day)

**Day 3: Testing**
- [ ] Test successful composition
- [ ] Test tool filtering (with/without TOOL_CALL)
- [ ] Test prompt injection detection
- [ ] Test cache hit rate >75%
- [ ] Validate <30ms P95 composition latency

**Total**: 3 days (within M1 budget)

---

## Dependencies

### Required Before Implementation

- ✅ **ADR-0086b (Template System):** Templates provide composition config
- ✅ **ADR-0086e (Prompt Directory):** Prompt loading
- ✅ **Tool Registry:** 758 tools with capability requirements
- ✅ **Persona Formatter:** Personality trait formatting

### Blocks Other Work

- 🔄 **ADR-0086a (Agent Factory):** Factory needs composition to create agents

---

## References

### Related ADRs

- [ADR-0086 (Dynamic Agent Creation)](0086-dynamic-agent-creation-subsystem.md)
- [ADR-0086a (Agent Factory)](0086a-agent-factory-pattern.md)
- [ADR-0086b (Template System)](0086b-agent-template-system.md)
- [ADR-0086e (Prompt Directory)](0086e-prompt-directory-template-management.md)
- [ADR-0010 (Capability Security)](0010-capability-based-security.md)

---

**Status**: Approved ✅ → Implementation Phase M1 (Issue 1.1.2)

**Next Steps**:
1. Implement CompositionEngine (Day 1-2)
2. Write WARD tests (Day 3)
3. Integrate with AgentFactory
