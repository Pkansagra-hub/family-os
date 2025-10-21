# ADR-0007b: Expand Stage Tool/Prompt Registry Integration

**Status:** ✅ Approved (2025-10-12)
**Parent ADR:** [ADR-0007: 4-Stage Planning Pipeline](./0007-4stage-planning-pipeline.md)
**Related ADRs:**
- [ADR-0007a: Sketch Stage LLM Prompt Engineering](./0007a-sketch-stage-llm-prompt-engineering.md) - Provides sketch input
- [ADR-0007c: Validation Stage 2-Tier Implementation](./0007c-validation-stage-2-tier-implementation.md) - Validates expanded plan
- [ADR-0010: Capability-Based Security](./0010-capability-based-security.md) - Capability validation

**Research Citations:**
- Registry pattern (Gamma et al. 1994) - Design pattern for service lookup
- Schema validation (JSON Schema 2020) - Structured data validation

---

## Context & Problem Statement

### Current State
After Stage 1 (Sketch), the Planner has a PlanSketch with basic structure (intent, steps, dependencies) but **missing critical metadata**:
- ❌ **No tool schemas** (schema_in, schema_out for each tool)
- ❌ **No cost/latency hints** (estimated_latency_ms, estimated_cost_usd)
- ❌ **No capability requirements** (caps_required, band_required)
- ❌ **No prompt templates** (for LLM-based tools)

### Problem Statement
**How do we enrich PlanSketch with tool/prompt metadata in a deterministic, <1ms operation to enable downstream validation (Stage 3) and execution (Stage 4)?**

### Key Challenges

1. **Registry Lookup Performance:**
   - Tool registry has 50+ tools, must lookup tool metadata in <1ms
   - Prompt registry has 100+ templates, must match description → prompt in <1ms
   - Target: <1ms P95 expand latency

2. **Unknown Tools:**
   - LLM may hallucinate tools not in registry (despite prompt constraints)
   - Current: 1-2% hallucination rate (0007a target: <1%)
   - Must handle gracefully: log warning, continue expansion (Tier 1 validation will catch)

3. **Metadata Completeness:**
   - Some tools have partial metadata (no cost hint, no latency hint)
   - Must provide defaults (cost_hint = 0.0, latency_hint = 1000ms)

4. **Prompt Matching Accuracy:**
   - Step description may not exactly match prompt template name
   - Need fuzzy matching (keyword overlap, semantic similarity)
   - Target: >90% prompt match success rate

---

## Decision

### Overview
Implement a **deterministic registry-based expansion** for Stage 2 (Expand) of the 4-stage planning pipeline:
1. **Tool registry lookup** (tool_id → ToolSpec with schema_in, schema_out, latency_hint, cost_hint, band_required, caps_required)
2. **Prompt registry matching** (step description → PromptTemplate with prompt_id, model_class, latency_hint, cost_hint)
3. **Metadata enrichment** (add missing fields to sketch steps)
4. **Unknown tool handling** (log warnings, continue expansion)
5. **Expansion metrics** (expansion_latency_ms, unknown_tools_total, prompt_match_success_rate)

### Component 1: Tool Registry Lookup

**Purpose:** Enrich steps with tool metadata from centralized tool registry.

**Tool Registry Structure:**
```python
@dataclass
class ToolSpec:
    """Tool specification with all metadata"""
    id: str                             # Unique tool ID (e.g., "weather_api")
    name: str                           # Human-readable name
    description: str                    # Tool description
    schema_in: Dict[str, Any]          # Input schema (JSON Schema)
    schema_out: Dict[str, Any]         # Output schema (JSON Schema)
    latency_hint_ms: int               # Expected latency (P95)
    cost_hint_usd: float               # Expected cost per call
    band_required: str                 # Privacy band required (GREEN|AMBER|RED)
    caps_required: Set[str]            # Capabilities required
    category: str                      # Tool category (search, booking, etc.)
    version: str                       # Tool version (for breaking changes)

class ToolRegistry:
    """Centralized tool registry with O(1) lookup"""

    def __init__(self):
        self.tools: Dict[str, ToolSpec] = {}  # tool_id → ToolSpec
        self._load_tools()

    def _load_tools(self):
        """Load tools from configuration (YAML/JSON)"""
        # Load from k1/config/tools.yml
        tools_config = load_yaml("k1/config/tools.yml")
        for tool_data in tools_config["tools"]:
            tool = ToolSpec(**tool_data)
            self.tools[tool.id] = tool

    def get_tool(self, tool_id: str) -> Optional[ToolSpec]:
        """Get tool by ID (O(1) hash table lookup)"""
        return self.tools.get(tool_id)

    def has_tool(self, tool_id: str) -> bool:
        """Check if tool exists"""
        return tool_id in self.tools

    def get_all_tools(self) -> List[ToolSpec]:
        """Get all tools (for listing, filtering)"""
        return list(self.tools.values())
```

**Tool Registry Example (YAML):**
```yaml
# k1/config/tools.yml
tools:
  - id: weather_api
    name: Weather API
    description: Get current weather for a location
    schema_in:
      type: object
      required: [location]
      properties:
        location: {type: string, description: "City and state (e.g., 'San Francisco, CA')"}
    schema_out:
      type: object
      properties:
        temperature: {type: number, description: "Temperature in Fahrenheit"}
        conditions: {type: string, description: "Weather conditions (e.g., 'Sunny')"}
        humidity: {type: number, description: "Humidity percentage"}
    latency_hint_ms: 150
    cost_hint_usd: 0.001
    band_required: GREEN
    caps_required: [TOOL_CALL]
    category: search
    version: "1.0"

  - id: restaurant_search
    name: Restaurant Search
    description: Search for restaurants by cuisine, location, rating
    schema_in:
      type: object
      required: [location]
      properties:
        cuisine: {type: string}
        location: {type: string}
        rating_min: {type: number}
    schema_out:
      type: object
      properties:
        results:
          type: array
          items:
            type: object
            properties:
              id: {type: string}
              name: {type: string}
              rating: {type: number}
              address: {type: string}
    latency_hint_ms: 300
    cost_hint_usd: 0.005
    band_required: GREEN
    caps_required: [TOOL_CALL]
    category: search
    version: "1.0"

  - id: reservation_booking
    name: Reservation Booking
    description: Book restaurant reservation
    schema_in:
      type: object
      required: [restaurant_id, party_size, time, date]
      properties:
        restaurant_id: {type: string}
        party_size: {type: integer}
        time: {type: string, format: "HH:MM"}
        date: {type: string, format: "YYYY-MM-DD"}
    schema_out:
      type: object
      properties:
        booking_id: {type: string}
        confirmation_code: {type: string}
        status: {type: string, enum: [CONFIRMED, PENDING, FAILED]}
    latency_hint_ms: 500
    cost_hint_usd: 0.01
    band_required: AMBER  # Booking requires user consent
    caps_required: [TOOL_CALL, WRITE_EXTERNAL]
    category: booking
    version: "1.0"
```

**Lookup Algorithm:**
```python
async def enrich_step_with_tool_metadata(
    step: PlanStep,
    tool_registry: ToolRegistry
) -> ExpandedPlanStep:
    """
    Enrich step with tool metadata from registry.

    Returns ExpandedPlanStep with:
    - schema_in, schema_out (for validation)
    - latency_hint_ms, cost_hint_usd (for budget validation)
    - band_required, caps_required (for security validation)
    """
    # Lookup tool (O(1) hash table lookup)
    tool_spec = tool_registry.get_tool(step.tool)

    if tool_spec is None:
        # Unknown tool: log warning, use defaults
        logger.warning(
            "expand_unknown_tool",
            tool_id=step.tool,
            step_id=step.step_id
        )
        # Use defaults (will fail validation in Stage 3)
        tool_spec = ToolSpec(
            id=step.tool,
            name=step.tool,
            description="Unknown tool",
            schema_in={},
            schema_out={},
            latency_hint_ms=1000,  # Conservative default
            cost_hint_usd=0.0,
            band_required="RED",   # Safest default
            caps_required=set(),
            category="unknown",
            version="0.0"
        )

    # Create expanded step
    return ExpandedPlanStep(
        # Original fields from sketch
        step_id=step.step_id,
        action=step.action,
        tool=step.tool,
        parameters=step.parameters,
        dependencies=step.dependencies,

        # Enriched metadata from tool registry
        schema_in=tool_spec.schema_in,
        schema_out=tool_spec.schema_out,
        latency_hint_ms=tool_spec.latency_hint_ms,
        cost_hint_usd=tool_spec.cost_hint_usd,
        band_required=tool_spec.band_required,
        caps_required=tool_spec.caps_required,
        category=tool_spec.category,
        tool_version=tool_spec.version
    )
```

**Performance Analysis:**
- **Lookup complexity:** O(1) (hash table)
- **Latency:** <0.1ms per step (hash table lookup + struct copy)
- **Total expand latency:** <1ms for 10 steps (10 × 0.1ms)

---

### Component 2: Prompt Registry Matching

**Purpose:** Match step descriptions to prompt templates for LLM-based tools.

**Prompt Registry Structure:**
```python
@dataclass
class PromptTemplate:
    """Prompt template specification"""
    id: str                            # Unique prompt ID
    name: str                          # Human-readable name
    description: str                   # Prompt description
    model_class: str                   # Model class (GPT4, GEMINI, CLAUDE)
    prompt_text: str                   # Prompt template with {{variables}}
    latency_hint_ms: int               # Expected LLM latency
    cost_hint_usd: float               # Expected LLM cost
    temperature: float                 # Temperature setting
    max_tokens: int                    # Max tokens
    keywords: Set[str]                 # Keywords for matching

class PromptRegistry:
    """Centralized prompt template registry"""

    def __init__(self):
        self.prompts: Dict[str, PromptTemplate] = {}  # prompt_id → PromptTemplate
        self.keyword_index: Dict[str, List[str]] = {}  # keyword → [prompt_ids]
        self._load_prompts()

    def _load_prompts(self):
        """Load prompts from configuration"""
        prompts_config = load_yaml("k1/config/prompts.yml")
        for prompt_data in prompts_config["prompts"]:
            prompt = PromptTemplate(**prompt_data)
            self.prompts[prompt.id] = prompt

            # Build keyword index
            for keyword in prompt.keywords:
                if keyword not in self.keyword_index:
                    self.keyword_index[keyword] = []
                self.keyword_index[keyword].append(prompt.id)

    def match_prompt(
        self,
        step_description: str,
        tool_category: str
    ) -> Optional[PromptTemplate]:
        """
        Match step description to prompt template.

        Matching algorithm:
        1. Keyword matching (step description keywords → prompt keywords)
        2. Category matching (tool category → prompt category)
        3. Return highest scoring prompt
        """
        # Extract keywords from step description
        step_keywords = set(step_description.lower().split())

        # Score each prompt by keyword overlap
        scored_prompts = []
        for prompt_id, prompt in self.prompts.items():
            # Keyword overlap score
            keyword_overlap = len(step_keywords & prompt.keywords)

            # Category match bonus
            category_bonus = 10 if tool_category in prompt.description.lower() else 0

            total_score = keyword_overlap + category_bonus
            if total_score > 0:
                scored_prompts.append((total_score, prompt))

        # Return highest scoring prompt
        if scored_prompts:
            scored_prompts.sort(key=lambda x: x[0], reverse=True)
            return scored_prompts[0][1]

        return None  # No match found
```

**Prompt Registry Example (YAML):**
```yaml
# k1/config/prompts.yml
prompts:
  - id: restaurant_recommendation
    name: Restaurant Recommendation Prompt
    description: Generate restaurant recommendations based on preferences
    model_class: GPT4
    prompt_text: |
      Based on the following preferences, recommend restaurants:
      - Cuisine: {{cuisine}}
      - Location: {{location}}
      - Rating minimum: {{rating_min}}

      Provide top 3 recommendations with reasons.
    latency_hint_ms: 400
    cost_hint_usd: 0.002
    temperature: 0.7
    max_tokens: 300
    keywords: [restaurant, recommend, food, dining, cuisine]

  - id: travel_itinerary
    name: Travel Itinerary Prompt
    description: Generate travel itinerary for destination
    model_class: GPT4
    prompt_text: |
      Create a travel itinerary for:
      - Destination: {{destination}}
      - Duration: {{duration_days}} days
      - Interests: {{interests}}

      Include hotels, restaurants, activities.
    latency_hint_ms: 600
    cost_hint_usd: 0.004
    temperature: 0.5
    max_tokens: 800
    keywords: [travel, trip, itinerary, vacation, plan, destination]
```

**Matching Algorithm:**
```python
async def enrich_step_with_prompt_template(
    step: ExpandedPlanStep,
    prompt_registry: PromptRegistry
) -> ExpandedPlanStep:
    """
    Enrich step with prompt template (if LLM-based tool).

    Only applies to tools that use LLM internally (e.g., recommendation tools).
    """
    # Check if tool uses LLM (category = "llm_tool")
    if step.category != "llm_tool":
        return step  # Not LLM-based, skip prompt matching

    # Match prompt template
    prompt_template = prompt_registry.match_prompt(
        step_description=step.action,
        tool_category=step.category
    )

    if prompt_template:
        # Update latency/cost hints (add LLM overhead)
        step.latency_hint_ms += prompt_template.latency_hint_ms
        step.cost_hint_usd += prompt_template.cost_hint_usd
        step.prompt_template_id = prompt_template.id

        logger.info(
            "expand_prompt_matched",
            step_id=step.step_id,
            prompt_id=prompt_template.id,
            latency_added_ms=prompt_template.latency_hint_ms
        )
    else:
        logger.warning(
            "expand_prompt_not_matched",
            step_id=step.step_id,
            step_action=step.action
        )

    return step
```

**Performance Analysis:**
- **Matching complexity:** O(P × K) where P = prompts, K = keywords (typically P=100, K=5)
- **Latency:** <0.5ms (keyword overlap computation)
- **Match success rate:** >90% (keyword + category matching)

---

### Component 3: Metadata Enrichment (Complete Expanded Plan)

**Purpose:** Combine tool metadata + prompt metadata into fully expanded plan.

**Data Structures:**

```python
@dataclass
class PlanStep:
    """Original plan step from sketch (Stage 1 output)"""
    step_id: int
    action: str
    tool: str
    parameters: Dict[str, Any]
    dependencies: List[int]

@dataclass
class ExpandedPlanStep(PlanStep):
    """Expanded plan step with registry metadata (Stage 2 output)"""
    # Inherited from PlanStep: step_id, action, tool, parameters, dependencies

    # Tool metadata (from tool registry)
    schema_in: Dict[str, Any]
    schema_out: Dict[str, Any]
    latency_hint_ms: int
    cost_hint_usd: float
    band_required: str
    caps_required: Set[str]
    category: str
    tool_version: str

    # Prompt metadata (from prompt registry, if applicable)
    prompt_template_id: Optional[str] = None

@dataclass
class PlanSketch:
    """Plan sketch from Stage 1"""
    intent: str
    steps: List[PlanStep]
    complexity: str

@dataclass
class ExpandedPlan(PlanSketch):
    """Expanded plan from Stage 2"""
    # Inherited from PlanSketch: intent, complexity
    steps: List[ExpandedPlanStep]  # Override with expanded steps

    # Aggregate metadata (computed during expansion)
    total_latency_hint_ms: int
    total_cost_hint_usd: float
    highest_band_required: str  # Max(step.band_required for all steps)
    all_caps_required: Set[str]  # Union(step.caps_required for all steps)
```

**Expansion Algorithm:**
```python
class PlanExpander:
    """Expand plan sketches with registry metadata"""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        prompt_registry: PromptRegistry
    ):
        self.tool_registry = tool_registry
        self.prompt_registry = prompt_registry

    async def expand_plan(
        self,
        sketch: PlanSketch,
        trace_id: str
    ) -> ExpandedPlan:
        """
        Expand plan sketch with tool/prompt metadata.

        Steps:
        1. For each step, lookup tool metadata (tool registry)
        2. For LLM-based tools, match prompt template (prompt registry)
        3. Compute aggregate metadata (total latency, total cost, highest band)
        4. Return ExpandedPlan
        """
        expanded_steps = []

        # Expand each step
        for step in sketch.steps:
            # Step 1: Enrich with tool metadata
            expanded_step = await self.enrich_step_with_tool_metadata(
                step,
                self.tool_registry
            )

            # Step 2: Enrich with prompt template (if LLM-based)
            expanded_step = await self.enrich_step_with_prompt_template(
                expanded_step,
                self.prompt_registry
            )

            expanded_steps.append(expanded_step)

        # Step 3: Compute aggregate metadata
        total_latency_hint_ms = sum(s.latency_hint_ms for s in expanded_steps)
        total_cost_hint_usd = sum(s.cost_hint_usd for s in expanded_steps)

        # Highest band (GREEN < AMBER < RED)
        band_priority = {"GREEN": 1, "AMBER": 2, "RED": 3}
        highest_band = max(
            (s.band_required for s in expanded_steps),
            key=lambda b: band_priority[b]
        )

        # Union of all required capabilities
        all_caps_required = set()
        for step in expanded_steps:
            all_caps_required.update(step.caps_required)

        # Create expanded plan
        expanded_plan = ExpandedPlan(
            intent=sketch.intent,
            steps=expanded_steps,
            complexity=sketch.complexity,
            total_latency_hint_ms=total_latency_hint_ms,
            total_cost_hint_usd=total_cost_hint_usd,
            highest_band_required=highest_band,
            all_caps_required=all_caps_required
        )

        logger.info(
            "plan_expanded",
            intent=sketch.intent,
            step_count=len(expanded_steps),
            total_latency_ms=total_latency_hint_ms,
            total_cost_usd=total_cost_hint_usd,
            highest_band=highest_band,
            trace_id=trace_id
        )

        return expanded_plan

    async def enrich_step_with_tool_metadata(
        self,
        step: PlanStep,
        tool_registry: ToolRegistry
    ) -> ExpandedPlanStep:
        """(Implementation shown in Component 1)"""
        # ... (see Component 1 code)

    async def enrich_step_with_prompt_template(
        self,
        step: ExpandedPlanStep,
        prompt_registry: PromptRegistry
    ) -> ExpandedPlanStep:
        """(Implementation shown in Component 2)"""
        # ... (see Component 2 code)
```

---

### Component 4: Unknown Tool Handling (Graceful Degradation)

**Purpose:** Handle LLM hallucinated tools gracefully without blocking expansion.

**Strategy:**
1. **Log warning** (unknown tool detected)
2. **Use conservative defaults** (high latency, RED band, no capabilities)
3. **Continue expansion** (don't fail entire plan)
4. **Let validation catch** (Stage 3 Tier 1 will reject unknown tool)

**Implementation:**
```python
# In enrich_step_with_tool_metadata (Component 1)
if tool_spec is None:
    # Unknown tool: log warning, use defaults
    logger.warning(
        "expand_unknown_tool",
        tool_id=step.tool,
        step_id=step.step_id,
        step_action=step.action,
        trace_id=trace_id
    )

    # Emit metric
    unknown_tools_total.labels(tool_id=step.tool).inc()

    # Use conservative defaults
    tool_spec = ToolSpec(
        id=step.tool,
        name=step.tool,
        description="Unknown tool (not in registry)",
        schema_in={},
        schema_out={},
        latency_hint_ms=1000,  # Conservative default (1s)
        cost_hint_usd=0.0,     # Unknown cost
        band_required="RED",   # Safest default (requires arbiter)
        caps_required=set(),   # No capabilities (will fail validation)
        category="unknown",
        version="0.0"
    )

    # Continue expansion with defaults
    # Stage 3 validation will catch unknown tool and reject plan
```

**Rationale:**
- **Don't block expansion:** Allow pipeline to continue (fail-fast at validation, not expansion)
- **Conservative defaults:** Ensure unknown tools don't bypass security checks (RED band, no capabilities)
- **Observability:** Log + emit metrics for monitoring hallucination rate

---

### Component 5: Expansion Metrics (Observability)

**Purpose:** Monitor expansion performance, unknown tools, prompt matching.

**Metrics (Prometheus):**
```python
from prometheus_client import Counter, Histogram

# Expansion latency
expand_latency_ms = Histogram(
    'expand_latency_ms',
    'Plan expansion latency in milliseconds',
    buckets=[0.5, 1, 2, 5, 10]
)

# Unknown tools
unknown_tools_total = Counter(
    'unknown_tools_total',
    'Unknown tools detected during expansion',
    ['tool_id']
)

# Prompt matching
prompt_match_success_total = Counter(
    'prompt_match_success_total',
    'Prompt template matches'
)
prompt_match_failure_total = Counter(
    'prompt_match_failure_total',
    'Prompt template match failures'
)

# Step enrichment
steps_enriched_total = Counter(
    'steps_enriched_total',
    'Steps enriched with metadata',
    ['category']
)
```

**Tracing (OpenTelemetry):**
```python
@traced(span_name="planner.expand")
async def expand_plan(
    sketch: PlanSketch,
    trace_id: str
) -> ExpandedPlan:
    """Expand plan with tracing"""
    with tracer.start_as_current_span("expand_steps"):
        expanded_steps = []
        for step in sketch.steps:
            with tracer.start_as_current_span(f"expand_step_{step.step_id}"):
                expanded_step = await expand_step(step)
                expanded_steps.append(expanded_step)

    with tracer.start_as_current_span("compute_aggregates"):
        expanded_plan = compute_aggregates(sketch, expanded_steps)

    return expanded_plan
```

---

## Performance Analysis

### Latency Breakdown (Expand Stage)

| Component | Latency (P95) | Optimization |
|-----------|---------------|--------------|
| Tool registry lookup (10 steps) | 0.5ms | O(1) hash table |
| Prompt registry matching (2 LLM tools) | 0.3ms | Keyword index |
| Aggregate metadata computation | 0.1ms | Simple arithmetic |
| **Total** | **0.9ms** | **Target: <1ms P95 ✅** |

**Scalability:**
- **Plan size:** 10 steps → ~1ms, 20 steps → ~2ms (linear scaling)
- **Registry size:** 50 tools → <1ms, 100 tools → <1ms (O(1) lookup)

---

## Quality Metrics

### Unknown Tool Rate

**Target:** <1% (Stage 1 sketch hallucination rate)

**Measurement:**
```python
unknown_tool_rate = unknown_tools_total / steps_enriched_total
# Target: <0.01 (1%)
```

### Prompt Match Success Rate

**Target:** >90%

**Measurement:**
```python
prompt_match_rate = prompt_match_success_total / (prompt_match_success_total + prompt_match_failure_total)
# Target: >0.90 (90%)
```

---

## Observability

### Logging (Structured)
```python
logger.info(
    "plan_expanded",
    intent=sketch.intent,
    step_count=len(expanded_steps),
    total_latency_ms=total_latency_hint_ms,
    total_cost_usd=total_cost_hint_usd,
    highest_band=highest_band,
    unknown_tools=unknown_tool_count,
    trace_id=trace_id
)
```

---

## Canonical Values

```yaml
# k1/config/planner.yml
planner:
  expand:
    # Performance targets
    expand_latency_p95_ms: 1          # <1ms P95 expand latency

    # Quality targets
    unknown_tool_rate_target: 0.01    # <1% unknown tool rate
    prompt_match_rate_target: 0.90    # >90% prompt match rate

    # Defaults for unknown tools
    unknown_tool_latency_default_ms: 1000
    unknown_tool_cost_default_usd: 0.0
    unknown_tool_band_default: RED

    # Registry paths
    tool_registry_path: "k1/config/tools.yml"
    prompt_registry_path: "k1/config/prompts.yml"
```

---

## Implementation Plan

### Phase 1: MVP (Week 1)
- [x] Tool registry structure (ToolSpec, ToolRegistry)
- [x] Tool registry loading (YAML config)
- [x] Tool lookup algorithm (O(1) hash table)
- [x] Metadata enrichment (ExpandedPlanStep)
- [x] Unknown tool handling (conservative defaults)

### Phase 2: Prompt Matching (Week 2)
- [ ] Prompt registry structure (PromptTemplate, PromptRegistry)
- [ ] Prompt matching algorithm (keyword overlap)
- [ ] Prompt enrichment (latency/cost hints)

### Phase 3: Observability (Week 3)
- [ ] Expansion metrics (latency, unknown tools, prompt matching)
- [ ] Tracing (OpenTelemetry spans)
- [ ] Structured logging

---

## Consequences

### Benefits
1. **<1ms P95 latency** (deterministic registry lookup)
2. **100% coverage** for known tools (registry has all 50+ tools)
3. **Graceful unknown tool handling** (log + continue, validation catches)
4. **Schema validation enablement** (Stage 3 uses schema_in/schema_out)

### Drawbacks
1. **Registry maintenance** (must update tools.yml for new tools)
2. **Prompt matching accuracy** (90% success rate, 10% miss)

---

## Cross-References

### Parent ADR
- **ADR-0007:** 4-Stage Planning Pipeline

### Related Sub-ADRs
- **0007a:** Sketch Stage (provides sketch input)
- **0007c:** Validation Stage (validates expanded plan)

### Dependencies
- **ADR-0010:** Capability-Based Security (caps_required validation)

---

## Conclusion

Stage 2 (Expand) enriches PlanSketch with tool/prompt metadata in <1ms via deterministic registry lookup. This enables downstream validation (Stage 3) and execution (Stage 4) to operate on complete, validated plans.

**Key innovations:**
1. O(1) tool registry lookup (hash table)
2. Keyword-based prompt matching (>90% success rate)
3. Conservative unknown tool defaults (graceful degradation)
4. Aggregate metadata computation (total latency, cost, band)

**Next step:** Proceed to **0007c (Validation Stage)** for 2-tier validation (rule-based + LLM arbiter).
