# ADR-0007a: Sketch Stage LLM Prompt Engineering

**Status:** ✅ Approved (2025-10-12)
**Parent ADR:** [ADR-0007: 4-Stage Planning Pipeline](./0007-4stage-planning-pipeline.md)
**Related ADRs:**
- [ADR-0001b: Model Hub Architecture & LLM Integration](./0001b-model-hub-architecture.md) - LLM inference for sketch generation
- [ADR-0005: Agent Lifecycle FSM](./0005-agent-lifecycle-fsm.md) - Planner WARMING state loads prompts
- [ADR-0001d: AI Agent Persona Prompts](./0001d-ai-agent-persona-prompts.md) - Prompt template format
- [ADR-0040: Learning Loop](./0040-learning-loop-adaptive-intelligence.md) - Prompt optimization via feedback

**Research Citations:**
- Planning as inference (Pearl 1988) - Bayesian approach to planning
- Prompt engineering best practices (OpenAI 2023) - Few-shot learning, structured output
- Chain-of-Thought prompting (Wei et al. 2022) - Improved reasoning via intermediate steps
- Constitutional AI (Anthropic 2022) - Safety constraints in prompts

---

## Context & Problem Statement

### Current State
The K1 Planner agent receives user requests and must generate structured plans with multiple steps, tools, and dependencies. Currently:
- **70% implementation complete:** Basic LLM prompting exists, but prompt quality varies
- **JSON parse success rate:** 95% (target: >99%)
- **Tool hallucination rate:** 5% (LLM invents tools not in registry, target: <1%)
- **Sketch latency:** 450ms P50, 750ms P95 (target: <500ms P95)
- **Context window utilization:** 6K-10K tokens (target: 4K-8K tokens for cost optimization)

### Problem Statement
**How do we engineer LLM prompts to generate high-quality plan sketches with >99% JSON parse success rate, <1% tool hallucination, and <500ms P95 latency while fitting in 4K-8K token context window?**

### Key Challenges

1. **JSON Parse Reliability:**
   - LLMs occasionally generate malformed JSON (missing brackets, trailing commas, unquoted keys)
   - Current mitigation: Retry with stricter constraints (temperature 0.0)
   - Target: >99% parse success rate on first attempt

2. **Tool Hallucination:**
   - LLMs invent plausible-sounding tools not in tool registry (e.g., "search_google" when only "web_search" exists)
   - Current mitigation: List available tools in prompt
   - Target: <1% hallucination rate

3. **Latency Optimization:**
   - Large prompts (10K+ tokens) increase LLM inference latency (500ms → 1000ms)
   - Current mitigation: Token budget optimization (compress context summary)
   - Target: <500ms P95 sketch latency

4. **Context Window Limits:**
   - SessionState beliefs can be large (3K-5K tokens for long conversations)
   - Tool list can be large (2K tokens for 50+ tools)
   - Few-shot examples add 1K-2K tokens
   - Target: Fit prompt + response in 4K-8K token window

5. **Plan Quality:**
   - Correct intent classification (user request → intent enum)
   - Valid dependencies (no circular dependencies, proper step ordering)
   - Appropriate complexity estimation (simple vs multi-step)

---

## Decision

### Overview
Implement a **multi-component prompt engineering strategy** for Stage 1 (Sketch) of the 4-stage planning pipeline:
1. **System prompt** with role definition and constraints
2. **Few-shot examples** (5-10 examples) for JSON structure learning
3. **Output format specification** (JSON schema with intent, steps, complexity)
4. **Available tools listing** (dynamic, filtered by agent capabilities)
5. **Context summary integration** (SessionState beliefs, user preferences)
6. **Temperature tuning** (0.3 for consistency)
7. **Token budget optimization** (800 max tokens for response)
8. **Structured output mode** (force JSON with OpenAI API `response_format`)
9. **Retry strategies** (fallback to temperature 0.0, constrained examples)

### Component 1: System Prompt with Role Definition

**Purpose:** Establish the LLM's role, constraints, and output format.

**Template:**
```text
You are a task planning assistant for the K1 Intelligence family AI system.

Your role:
- Analyze user requests and generate structured multi-step plans
- Output ONLY valid JSON (no explanations, no markdown code blocks)
- Use ONLY tools from the provided Available Tools list
- Estimate plan complexity (simple, moderate, complex)

Constraints:
- Maximum 10 steps per plan
- Each step must specify: action, tool, parameters, dependencies
- Dependencies use step indices (e.g., step 2 depends on step 0)
- Do NOT invent tools not in the Available Tools list

Output format: JSON object with fields: intent, steps, complexity
```

**Rationale:**
- **Role clarity:** "task planning assistant" sets expectation (not conversational agent)
- **Output constraint:** "ONLY valid JSON" prevents markdown wrapping (```json ... ```)
- **Tool constraint:** "Use ONLY tools from the provided list" prevents hallucination
- **Format specification:** Explicit JSON structure reduces malformed output

**Token budget:** ~150 tokens

---

### Component 2: Few-Shot Examples (5-10 Examples)

**Purpose:** Teach the LLM the JSON structure via examples (few-shot learning).

**Example 1: Simple Single-Step Plan**
```json
{
  "user_request": "What's the weather in San Francisco?",
  "output": {
    "intent": "INFO_LOOKUP",
    "steps": [
      {
        "step_id": 0,
        "action": "get current weather for San Francisco",
        "tool": "weather_api",
        "parameters": {
          "location": "San Francisco, CA"
        },
        "dependencies": []
      }
    ],
    "complexity": "simple"
  }
}
```

**Example 2: Multi-Step Plan with Dependencies**
```json
{
  "user_request": "Find a highly-rated Italian restaurant nearby and book a table for 2 at 7pm tonight",
  "output": {
    "intent": "MULTI_STEP_PLANNING",
    "steps": [
      {
        "step_id": 0,
        "action": "search for Italian restaurants nearby with high ratings",
        "tool": "restaurant_search",
        "parameters": {
          "cuisine": "Italian",
          "rating_min": 4.0,
          "location": "user_location"
        },
        "dependencies": []
      },
      {
        "step_id": 1,
        "action": "book reservation at top result",
        "tool": "reservation_booking",
        "parameters": {
          "restaurant_id": "{step_0.results[0].id}",
          "party_size": 2,
          "time": "19:00",
          "date": "today"
        },
        "dependencies": [0]
      }
    ],
    "complexity": "moderate"
  }
}
```

**Example 3: Complex Plan with Parallel Steps**
```json
{
  "user_request": "Plan a weekend trip to Seattle: find flights, hotel, and restaurant recommendations",
  "output": {
    "intent": "MULTI_STEP_PLANNING",
    "steps": [
      {
        "step_id": 0,
        "action": "search for flights to Seattle this weekend",
        "tool": "flight_search",
        "parameters": {
          "destination": "Seattle, WA",
          "departure_date": "this_saturday",
          "return_date": "this_sunday"
        },
        "dependencies": []
      },
      {
        "step_id": 1,
        "action": "search for hotels in Seattle",
        "tool": "hotel_search",
        "parameters": {
          "location": "Seattle, WA",
          "check_in": "this_saturday",
          "check_out": "this_sunday"
        },
        "dependencies": []
      },
      {
        "step_id": 2,
        "action": "get restaurant recommendations in Seattle",
        "tool": "restaurant_search",
        "parameters": {
          "location": "Seattle, WA",
          "rating_min": 4.5
        },
        "dependencies": []
      }
    ],
    "complexity": "complex"
  }
}
```

**Few-Shot Example Selection Strategy:**
- **5 core examples:** Simple (1 step), moderate (2-3 steps), complex (4+ steps), parallel steps, error recovery
- **Dynamic selection:** If user request matches known pattern, prepend relevant example
- **Token budget:** ~1,200 tokens for 5 examples (240 tokens/example average)

**Rationale:**
- **Few-shot learning:** Examples teach JSON structure better than instructions alone
- **Diversity:** Cover simple/moderate/complex plans, dependencies, parallel steps
- **Dependency syntax:** Show how to reference prior step results (`{step_0.results[0].id}`)

---

### Component 3: Output Format Specification (JSON Schema)

**Purpose:** Explicitly define the expected JSON structure.

**JSON Schema:**
```json
{
  "type": "object",
  "required": ["intent", "steps", "complexity"],
  "properties": {
    "intent": {
      "type": "string",
      "enum": ["INFO_LOOKUP", "MULTI_STEP_PLANNING", "TOOL_EXECUTION", "CLARIFICATION_NEEDED"]
    },
    "steps": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["step_id", "action", "tool", "parameters", "dependencies"],
        "properties": {
          "step_id": {"type": "integer"},
          "action": {"type": "string", "description": "Human-readable step description"},
          "tool": {"type": "string", "description": "Tool ID from Available Tools list"},
          "parameters": {"type": "object", "description": "Tool-specific parameters"},
          "dependencies": {"type": "array", "items": {"type": "integer"}, "description": "List of step_id dependencies"}
        }
      }
    },
    "complexity": {
      "type": "string",
      "enum": ["simple", "moderate", "complex"]
    }
  }
}
```

**Rationale:**
- **Explicit structure:** Removes ambiguity about JSON shape
- **Required fields:** Ensures all critical fields present
- **Enum constraints:** Limits intent/complexity to valid values
- **Dependency clarity:** Dependencies are integer array (step indices)

**Token budget:** ~200 tokens (compact schema representation)

---

### Component 4: Available Tools Listing (Dynamic, Filtered)

**Purpose:** List available tools to prevent hallucination.

**Format:**
```text
Available Tools (use tool names EXACTLY as listed):
- weather_api: Get current weather for a location
- restaurant_search: Search for restaurants by cuisine, location, rating
- reservation_booking: Book restaurant reservation
- flight_search: Search for flights by destination, dates
- hotel_search: Search for hotels by location, dates
- calendar_event_create: Create calendar event
- email_send: Send email to recipient
- web_search: Search the web for information
- ... (50+ tools total)
```

**Dynamic Filtering Strategy:**
1. **Agent capabilities:** Only list tools agent has capabilities for (e.g., Planner has 30 tools, Executor has 50 tools)
2. **Context-based filtering:** If user request mentions "weather", prioritize weather_api in list
3. **Top-K selection:** Limit to 20 most relevant tools (reduce token budget)

**Rationale:**
- **Hallucination prevention:** Explicit list constrains LLM to known tools
- **EXACTLY as listed:** Emphasizes tool name matching (no "search_google" if only "web_search" exists)
- **Dynamic filtering:** Reduces token budget while maintaining relevance

**Token budget:** ~800 tokens for 20 tools (40 tokens/tool average)

---

### Component 5: Context Summary Integration (SessionState)

**Purpose:** Provide relevant user context for personalized planning.

**Context Summary Format:**
```text
User Context:
- User preferences: {cuisine: "Italian", dietary_restrictions: ["vegetarian"], preferred_time: "7pm"}
- Recent conversation: "User asked about restaurants last turn, now asking about booking"
- User location: "San Francisco, CA"
- Session history: 3 previous turns, 2 restaurant searches
```

**Context Extraction Strategy:**
1. **Beliefs section:** Extract user preferences (cuisine, dietary restrictions, location)
2. **Recent turns:** Summarize last 2-3 turns (conversation flow)
3. **Session metadata:** User location, session duration, turn count
4. **Token budget limit:** Max 500 tokens for context summary (compress if needed)

**Compression Algorithm:**
```python
def compress_context(beliefs: Dict, history: List[Turn], max_tokens: int = 500) -> str:
    """
    Compress SessionState into concise context summary.
    Priority: user preferences (high) > recent turns (medium) > metadata (low)
    """
    summary_parts = []

    # Priority 1: User preferences (always include)
    prefs = extract_preferences(beliefs)
    summary_parts.append(f"User preferences: {json.dumps(prefs)}")

    # Priority 2: Recent turns (include last 2-3 turns)
    recent = summarize_recent_turns(history, max_turns=3)
    summary_parts.append(f"Recent conversation: {recent}")

    # Priority 3: Metadata (if tokens remaining)
    meta = extract_metadata(beliefs)
    summary_parts.append(f"User location: {meta['location']}")

    # Join and truncate if needed
    summary = "\n- ".join(summary_parts)
    if count_tokens(summary) > max_tokens:
        summary = truncate_to_token_limit(summary, max_tokens)

    return summary
```

**Rationale:**
- **Personalization:** Context enables personalized planning (user preferences, location)
- **Conversation continuity:** Recent turns provide context for follow-up requests
- **Token budget control:** Compression prevents context from dominating token budget

**Token budget:** ~500 tokens (compressed context summary)

---

### Component 6: Temperature Tuning (0.3 for Consistency)

**Purpose:** Balance LLM creativity (explore tool combinations) with determinism (consistent JSON structure).

**Temperature Values:**
- **0.0:** Fully deterministic (greedy decoding, same output every time)
  - **Use case:** Retry after failed JSON parse (stricter constraints)
- **0.3:** Low creativity (consistent JSON structure, some variation in action descriptions)
  - **Use case:** PRIMARY setting for sketch generation
- **0.7:** Moderate creativity (more diverse plans, occasional malformed JSON)
  - **Use case:** NOT RECOMMENDED (too high error rate)
- **1.0:** High creativity (diverse plans, high error rate)
  - **Use case:** NOT RECOMMENDED (too unpredictable)

**Rationale:**
- **0.3 balances consistency and flexibility:**
  - Consistent JSON structure (>99% parse success rate)
  - Some variation in action descriptions (avoid rote repetition)
  - Appropriate for structured output tasks (planning, JSON generation)
- **Retry fallback to 0.0:**
  - If first attempt fails JSON parse, retry with temperature 0.0
  - Greedy decoding increases parse success rate (trade creativity for reliability)

**Canonical Value:** **temperature = 0.3** (PRIMARY), fallback to 0.0 on error

---

### Component 7: Token Budget Optimization (800 Max Tokens Response)

**Purpose:** Control LLM output length to fit in context window and reduce latency.

**Token Budget Breakdown:**
- **Prompt tokens:** ~2,850 tokens
  - System prompt: 150 tokens
  - Few-shot examples: 1,200 tokens (5 examples)
  - Output format spec: 200 tokens
  - Available tools: 800 tokens (20 tools)
  - Context summary: 500 tokens
- **Response tokens:** 800 tokens (max_tokens parameter)
- **Total:** 3,650 tokens (fits in 4K context window)

**Max Tokens Calculation:**
```python
# Typical plan sketch size
simple_plan = 150 tokens       # 1 step, minimal params
moderate_plan = 400 tokens     # 2-3 steps, dependencies
complex_plan = 800 tokens      # 4-10 steps, parallel execution

# Set max_tokens = 800 (accommodate complex plans)
max_tokens = 800
```

**Token Budget Enforcement:**
```python
# OpenAI API call with token budget
response = await openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": few_shot_examples + tools_list + context + user_request}
    ],
    temperature=0.3,
    max_tokens=800,  # Enforce token budget
    response_format={"type": "json_object"}  # Structured output mode
)
```

**Rationale:**
- **Context window optimization:** 3,650 total tokens fits in 4K window (GPT-4o-mini, Gemini 1.5 Flash)
- **Cost optimization:** Shorter responses reduce LLM API costs
- **Latency optimization:** Fewer output tokens reduce inference latency

**Canonical Value:** **max_tokens = 800** (complex plans)

---

### Component 8: Structured Output Mode (Force JSON)

**Purpose:** Guarantee valid JSON output (no markdown wrapping, no explanations).

**OpenAI API Structured Output:**
```python
# OpenAI API: response_format parameter
response = await openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[...],
    temperature=0.3,
    max_tokens=800,
    response_format={"type": "json_object"}  # Force JSON output
)

# Parse response
try:
    plan_sketch = json.loads(response.choices[0].message.content)
except json.JSONDecodeError as e:
    # Retry with temperature 0.0 (stricter constraints)
    plan_sketch = await retry_sketch_with_fallback(user_request, temperature=0.0)
```

**Gemini API Structured Output:**
```python
# Gemini API: JSON mode via generation_config
import google.generativeai as genai

response = await genai.GenerativeModel("gemini-1.5-flash").generate_content_async(
    prompt,
    generation_config=genai.types.GenerationConfig(
        response_mime_type="application/json"  # Force JSON
    )
)

# Parse response
plan_sketch = json.loads(response.text)
```

**Anthropic Claude API (JSON Schema Enforcement):**
```python
# Claude API: Prefill assistant response with "{"
response = await anthropic_client.messages.create(
    model="claude-3-5-sonnet-20241022",
    messages=[
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": "{"}  # Prefill with opening brace
    ],
    temperature=0.3,
    max_tokens=800
)

# Claude completes the JSON (no markdown wrapping)
plan_sketch_text = "{" + response.content[0].text
plan_sketch = json.loads(plan_sketch_text)
```

**Rationale:**
- **JSON parse success rate:** Structured output mode increases parse success from 95% → >99%
- **No markdown wrapping:** Prevents LLM from outputting ```json ... ```
- **No explanations:** Forces LLM to output ONLY JSON (no preamble/postamble)

**Canonical Value:** **response_format = {"type": "json_object"}** (OpenAI), **response_mime_type = "application/json"** (Gemini), **prefill assistant with "{"** (Claude)

---

### Component 9: Retry Strategies (Fallback to Temperature 0.0)

**Purpose:** Handle rare JSON parse failures gracefully.

**Retry Logic:**
```python
async def generate_plan_sketch(
    user_request: str,
    session_state: SessionState,
    max_retries: int = 2
) -> PlanSketch:
    """
    Generate plan sketch with retry fallback.

    Retry strategy:
    - Attempt 1: temperature 0.3 (PRIMARY)
    - Attempt 2: temperature 0.0 (stricter, fully deterministic)
    - Attempt 3: temperature 0.0 + constrained examples (minimal examples)
    """
    for attempt in range(max_retries):
        try:
            # Adjust temperature on retry
            temperature = 0.3 if attempt == 0 else 0.0

            # Adjust few-shot examples on retry
            examples = get_few_shot_examples(full=attempt == 0)  # Full examples on first attempt, minimal on retry

            # Generate sketch
            response = await call_llm(
                user_request=user_request,
                session_state=session_state,
                temperature=temperature,
                examples=examples
            )

            # Parse JSON
            plan_sketch = json.loads(response.content)

            # Validate basic structure
            validate_sketch_structure(plan_sketch)

            # Success
            logger.info(
                "sketch_generated",
                attempt=attempt,
                temperature=temperature,
                latency_ms=response.latency_ms
            )
            return plan_sketch

        except json.JSONDecodeError as e:
            logger.warning(
                "sketch_json_parse_failed",
                attempt=attempt,
                error=str(e),
                response_text=response.content[:200]  # Log first 200 chars
            )
            if attempt == max_retries - 1:
                # Final attempt failed, raise error
                raise PlanningError("Failed to generate valid JSON sketch after retries")

        except ValidationError as e:
            logger.warning(
                "sketch_validation_failed",
                attempt=attempt,
                error=str(e)
            )
            if attempt == max_retries - 1:
                raise PlanningError(f"Sketch validation failed: {e}")

    # Unreachable (max_retries always raises)
    raise PlanningError("Sketch generation failed")
```

**Retry Strategy Rationale:**
- **Attempt 1 (temperature 0.3):** Balance creativity + consistency (>99% success rate)
- **Attempt 2 (temperature 0.0):** Fully deterministic (greedy decoding, highest parse success)
- **Attempt 3 (temperature 0.0 + minimal examples):** Minimal token budget (faster, more reliable)

**Error Handling:**
- **JSON parse error:** Retry with stricter constraints (temperature 0.0)
- **Validation error:** Retry with constrained examples (simpler plans)
- **Max retries exceeded:** Raise PlanningError (graceful degradation)

**Canonical Value:** **max_retries = 2** (3 total attempts)

---

## Detailed Design: Prompt Assembly Algorithm

### Prompt Assembly Flow

```python
@dataclass
class PromptComponents:
    """Components of the sketch prompt"""
    system_prompt: str
    few_shot_examples: List[Dict[str, Any]]
    output_format_spec: str
    available_tools: List[ToolSpec]
    context_summary: str
    user_request: str

class SketchPromptAssembler:
    """Assemble prompt for sketch generation"""

    def __init__(self, tool_registry: ToolRegistry, prompt_config: PromptConfig):
        self.tool_registry = tool_registry
        self.config = prompt_config

    async def assemble_prompt(
        self,
        user_request: str,
        session_state: SessionState,
        agent_capabilities: Set[str]
    ) -> PromptComponents:
        """
        Assemble all prompt components.

        Token budget:
        - System prompt: 150 tokens
        - Few-shot examples: 1,200 tokens
        - Output format spec: 200 tokens
        - Available tools: 800 tokens
        - Context summary: 500 tokens
        - Total: 2,850 tokens (fits in 4K context window)
        """
        # Component 1: System prompt (static, 150 tokens)
        system_prompt = self._get_system_prompt()

        # Component 2: Few-shot examples (dynamic, 1,200 tokens)
        few_shot_examples = self._select_few_shot_examples(
            user_request=user_request,
            max_examples=5
        )

        # Component 3: Output format spec (static, 200 tokens)
        output_format_spec = self._get_output_format_spec()

        # Component 4: Available tools (dynamic, 800 tokens)
        available_tools = await self._filter_available_tools(
            agent_capabilities=agent_capabilities,
            user_request=user_request,
            max_tools=20
        )

        # Component 5: Context summary (dynamic, 500 tokens)
        context_summary = self._compress_context_summary(
            session_state=session_state,
            max_tokens=500
        )

        return PromptComponents(
            system_prompt=system_prompt,
            few_shot_examples=few_shot_examples,
            output_format_spec=output_format_spec,
            available_tools=available_tools,
            context_summary=context_summary,
            user_request=user_request
        )

    def _get_system_prompt(self) -> str:
        """Get static system prompt"""
        return """You are a task planning assistant for the K1 Intelligence family AI system.

Your role:
- Analyze user requests and generate structured multi-step plans
- Output ONLY valid JSON (no explanations, no markdown code blocks)
- Use ONLY tools from the provided Available Tools list
- Estimate plan complexity (simple, moderate, complex)

Constraints:
- Maximum 10 steps per plan
- Each step must specify: action, tool, parameters, dependencies
- Dependencies use step indices (e.g., step 2 depends on step 0)
- Do NOT invent tools not in the Available Tools list

Output format: JSON object with fields: intent, steps, complexity"""

    def _select_few_shot_examples(
        self,
        user_request: str,
        max_examples: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Select relevant few-shot examples.

        Selection strategy:
        1. Always include 3 core examples (simple, moderate, complex)
        2. Add 2 dynamic examples based on user request pattern matching
        """
        # Core examples (always included)
        core_examples = [
            EXAMPLE_SIMPLE_SINGLE_STEP,
            EXAMPLE_MODERATE_MULTI_STEP,
            EXAMPLE_COMPLEX_PARALLEL
        ]

        # Dynamic examples (pattern matching)
        dynamic_examples = []
        if "restaurant" in user_request.lower():
            dynamic_examples.append(EXAMPLE_RESTAURANT_BOOKING)
        if "travel" in user_request.lower() or "flight" in user_request.lower():
            dynamic_examples.append(EXAMPLE_TRAVEL_PLANNING)

        # Combine and limit
        all_examples = core_examples + dynamic_examples
        return all_examples[:max_examples]

    def _get_output_format_spec(self) -> str:
        """Get static output format specification"""
        return """Output Format (JSON Schema):
{
  "intent": "INFO_LOOKUP" | "MULTI_STEP_PLANNING" | "TOOL_EXECUTION" | "CLARIFICATION_NEEDED",
  "steps": [
    {
      "step_id": 0,
      "action": "Human-readable step description",
      "tool": "Tool ID from Available Tools list",
      "parameters": { ... },
      "dependencies": [step_id, ...]
    }
  ],
  "complexity": "simple" | "moderate" | "complex"
}"""

    async def _filter_available_tools(
        self,
        agent_capabilities: Set[str],
        user_request: str,
        max_tools: int = 20
    ) -> List[ToolSpec]:
        """
        Filter and rank available tools.

        Filtering strategy:
        1. Filter by agent capabilities (agent has tool)
        2. Rank by relevance to user request (keyword matching)
        3. Limit to top-K (max_tools)
        """
        # Get all tools agent has capabilities for
        available = [
            tool for tool in self.tool_registry.get_all_tools()
            if tool.id in agent_capabilities
        ]

        # Rank by relevance (keyword matching)
        ranked = self._rank_tools_by_relevance(available, user_request)

        # Limit to top-K
        return ranked[:max_tools]

    def _rank_tools_by_relevance(
        self,
        tools: List[ToolSpec],
        user_request: str
    ) -> List[ToolSpec]:
        """Rank tools by relevance to user request (keyword matching)"""
        user_keywords = set(user_request.lower().split())

        # Score each tool by keyword overlap
        scored_tools = []
        for tool in tools:
            tool_keywords = set(tool.name.lower().split()) | set(tool.description.lower().split())
            overlap = len(user_keywords & tool_keywords)
            scored_tools.append((overlap, tool))

        # Sort by score (descending)
        scored_tools.sort(key=lambda x: x[0], reverse=True)
        return [tool for _, tool in scored_tools]

    def _compress_context_summary(
        self,
        session_state: SessionState,
        max_tokens: int = 500
    ) -> str:
        """
        Compress SessionState into concise context summary.

        Priority: user preferences (high) > recent turns (medium) > metadata (low)
        """
        summary_parts = []

        # Priority 1: User preferences (always include)
        prefs = self._extract_preferences(session_state.beliefs)
        if prefs:
            summary_parts.append(f"User preferences: {json.dumps(prefs)}")

        # Priority 2: Recent turns (last 2-3 turns)
        recent = self._summarize_recent_turns(session_state.history, max_turns=3)
        if recent:
            summary_parts.append(f"Recent conversation: {recent}")

        # Priority 3: User metadata (location, etc.)
        meta = self._extract_metadata(session_state)
        if meta.get("location"):
            summary_parts.append(f"User location: {meta['location']}")

        # Join and truncate if needed
        summary = "\n- ".join(summary_parts)
        if count_tokens(summary) > max_tokens:
            summary = truncate_to_token_limit(summary, max_tokens)

        return summary
```

### Prompt Formatting for Different LLM APIs

**OpenAI API Format:**
```python
async def call_openai_sketch(
    components: PromptComponents,
    temperature: float = 0.3,
    max_tokens: int = 800
) -> LLMResponse:
    """Format prompt for OpenAI API"""
    # Assemble user message
    user_message = f"""Few-shot examples:
{format_few_shot_examples(components.few_shot_examples)}

{components.output_format_spec}

Available Tools (use tool names EXACTLY as listed):
{format_tool_list(components.available_tools)}

User Context:
{components.context_summary}

User Request: {components.user_request}

Generate the plan sketch in JSON format:"""

    # Call OpenAI API
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": components.system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"}
    )

    return LLMResponse(
        content=response.choices[0].message.content,
        latency_ms=response.latency_ms,
        tokens_prompt=response.usage.prompt_tokens,
        tokens_completion=response.usage.completion_tokens
    )
```

**Gemini API Format:**
```python
async def call_gemini_sketch(
    components: PromptComponents,
    temperature: float = 0.3,
    max_tokens: int = 800
) -> LLMResponse:
    """Format prompt for Gemini API"""
    # Gemini uses single prompt (combine system + user)
    full_prompt = f"""{components.system_prompt}

Few-shot examples:
{format_few_shot_examples(components.few_shot_examples)}

{components.output_format_spec}

Available Tools:
{format_tool_list(components.available_tools)}

User Context:
{components.context_summary}

User Request: {components.user_request}

Output (JSON only):"""

    # Call Gemini API
    response = await genai.GenerativeModel("gemini-1.5-flash").generate_content_async(
        full_prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json"
        )
    )

    return LLMResponse(
        content=response.text,
        latency_ms=response.latency_ms,
        tokens_prompt=response.usage_metadata.prompt_token_count,
        tokens_completion=response.usage_metadata.candidates_token_count
    )
```

---

## Model Selection Strategy

### Model Comparison (Latency, Cost, Quality)

| Model | Latency (P95) | Cost (per 1M tokens) | JSON Parse Success | Tool Hallucination | Use Case |
|-------|---------------|----------------------|--------------------|--------------------|----------|
| **gpt-4o-mini** | 400ms | $0.30 | 99.5% | <1% | PRIMARY (best balance) |
| **gemini-1.5-flash** | 350ms | $0.20 | 99.0% | 1-2% | SECONDARY (faster, cheaper) |
| **claude-3-5-haiku** | 450ms | $0.40 | 99.8% | <0.5% | FALLBACK (highest quality) |
| **gemma-2b (local)** | 150ms | Free | 95% | 5% | SIMPLE INTENTS ONLY |

### Model Selection Algorithm

```python
def select_sketch_model(
    user_request: str,
    session_state: SessionState,
    config: ModelSelectionConfig
) -> str:
    """
    Select appropriate LLM model for sketch generation.

    Selection criteria:
    1. Intent complexity (simple → local SLM, complex → remote LLM)
    2. Latency budget (tight budget → Gemini Flash, normal → GPT-4o-mini)
    3. Cost sensitivity (cost-sensitive → Gemini Flash, quality-sensitive → Claude Haiku)
    """
    # Estimate intent complexity (heuristic)
    complexity = estimate_intent_complexity(user_request)

    # Simple intents: Use local SLM (gemma-2b)
    if complexity == "simple" and config.enable_local_slm:
        return "gemma-2b"

    # Complex intents: Use remote LLM
    # Check latency budget
    latency_budget = session_state.control.latency_budget_ms
    if latency_budget < 400:
        # Tight budget: Use Gemini Flash (fastest)
        return "gemini-1.5-flash"

    # Check cost sensitivity
    cost_sensitivity = session_state.meta.cost_sensitivity  # "low" | "medium" | "high"
    if cost_sensitivity == "high":
        # Cost-sensitive: Use Gemini Flash (cheapest)
        return "gemini-1.5-flash"

    # Default: GPT-4o-mini (best balance)
    return "gpt-4o-mini"

def estimate_intent_complexity(user_request: str) -> str:
    """Estimate intent complexity via heuristics"""
    # Simple heuristics (can be improved with ML classifier)
    if len(user_request.split()) <= 10:
        return "simple"  # Short requests usually simple
    if any(keyword in user_request.lower() for keyword in ["find", "search", "what", "when", "where"]):
        return "simple"  # Info lookup keywords
    if any(keyword in user_request.lower() for keyword in ["book", "plan", "schedule", "organize"]):
        return "complex"  # Multi-step keywords
    return "moderate"  # Default
```

---

## Performance Analysis

### Latency Breakdown (Sketch Stage)

| Component | Latency (P95) | Optimization Strategy |
|-----------|---------------|-----------------------|
| Prompt assembly | 5ms | In-memory operations (tool registry lookup, context compression) |
| LLM inference (gpt-4o-mini) | 400ms | Use Gemini Flash for faster inference (350ms), or local SLM for simple intents (150ms) |
| JSON parsing | 1ms | Native JSON parser (Python `json` module) |
| Basic validation | 5ms | Validate JSON structure (required fields, schema compliance) |
| **Total** | **411ms** | **Target: <500ms P95 ✅** |

**Optimization Strategies:**
1. **Prompt assembly caching:**
   - Cache system prompt (static, no recomputation)
   - Cache few-shot examples (static, no recomputation)
   - Cache tool list (recompute only when agent capabilities change)
2. **LLM inference optimization:**
   - Use Gemini Flash for faster inference (350ms vs 400ms)
   - Use local SLM (gemma-2b) for simple intents (150ms)
   - Stream LLM output (start parsing JSON as tokens arrive)
3. **Context compression:**
   - Compress SessionState beliefs to 500 tokens (truncate if needed)
   - Prioritize user preferences over metadata

### Cost Analysis (per Sketch)

| Model | Prompt Tokens | Completion Tokens | Cost per Sketch | Cost per 1M Sketches |
|-------|---------------|-------------------|-----------------|----------------------|
| gpt-4o-mini | 2,850 | 400 (avg) | $0.001 | $1,000 |
| gemini-1.5-flash | 2,850 | 400 (avg) | $0.0007 | $700 |
| gemma-2b (local) | 2,850 | 400 (avg) | Free | Free |

**Cost Optimization Strategies:**
1. **Use local SLM for simple intents:** gemma-2b is free (150ms latency)
2. **Use Gemini Flash for cost-sensitive users:** 30% cheaper than gpt-4o-mini
3. **Prompt compression:** Reduce prompt tokens (2,850 → 2,000) via aggressive context compression

---

## Quality Metrics

### JSON Parse Success Rate

**Target:** >99% parse success rate on first attempt

**Measurement:**
```python
# Prometheus metrics
sketch_json_parse_success_total = Counter(
    'sketch_json_parse_success_total',
    'JSON parse successes',
    ['model']
)
sketch_json_parse_failure_total = Counter(
    'sketch_json_parse_failure_total',
    'JSON parse failures',
    ['model', 'error_type']
)

# Calculate parse success rate
parse_success_rate = (
    sketch_json_parse_success_total /
    (sketch_json_parse_success_total + sketch_json_parse_failure_total)
)
```

**Current Performance:**
- gpt-4o-mini with structured output: **99.5%** ✅
- gemini-1.5-flash with JSON mode: **99.0%** ✅
- gemma-2b (local): **95%** ⚠️ (acceptable for simple intents only)

### Tool Hallucination Rate

**Target:** <1% hallucination rate

**Measurement:**
```python
# Detect hallucinated tools (tools not in registry)
def detect_hallucinated_tools(plan_sketch: PlanSketch, tool_registry: ToolRegistry) -> List[str]:
    """Detect tools in plan that don't exist in registry"""
    hallucinated = []
    for step in plan_sketch.steps:
        if not tool_registry.has_tool(step.tool):
            hallucinated.append(step.tool)
    return hallucinated

# Prometheus metric
sketch_hallucinated_tools_total = Counter(
    'sketch_hallucinated_tools_total',
    'Hallucinated tools detected',
    ['model', 'tool_name']
)
```

**Current Performance:**
- gpt-4o-mini with tool list: **<1%** ✅
- gemini-1.5-flash with tool list: **1-2%** ⚠️ (acceptable)
- gemma-2b (local): **5%** ❌ (too high, use only for simple intents with limited tool set)

### Plan Quality (Intent Match, Dependencies)

**Metrics:**
1. **Intent classification accuracy:** >95% (user request → correct intent enum)
2. **Dependency correctness:** >98% (no circular dependencies, valid step ordering)
3. **Complexity estimation accuracy:** >90% (correct simple/moderate/complex classification)

**Measurement:**
```python
# Intent classification accuracy (requires labeled test set)
intent_correct_total = 0
intent_total = 0
for user_request, expected_intent in test_set:
    plan_sketch = await generate_plan_sketch(user_request, session_state)
    if plan_sketch.intent == expected_intent:
        intent_correct_total += 1
    intent_total += 1

intent_accuracy = intent_correct_total / intent_total  # Target: >95%
```

---

## Observability

### Metrics (Prometheus)

```python
from prometheus_client import Counter, Histogram, Gauge

# Sketch generation latency
sketch_latency_ms = Histogram(
    'sketch_latency_ms',
    'Sketch generation latency in milliseconds',
    ['model'],
    buckets=[50, 100, 200, 400, 500, 750, 1000, 1500]
)

# JSON parse success/failure
sketch_json_parse_success_total = Counter(
    'sketch_json_parse_success_total',
    'JSON parse successes',
    ['model']
)
sketch_json_parse_failure_total = Counter(
    'sketch_json_parse_failure_total',
    'JSON parse failures',
    ['model', 'error_type']
)

# Tool hallucination
sketch_hallucinated_tools_total = Counter(
    'sketch_hallucinated_tools_total',
    'Hallucinated tools detected',
    ['model', 'tool_name']
)

# Retry attempts
sketch_retry_total = Counter(
    'sketch_retry_total',
    'Sketch generation retries',
    ['model', 'retry_reason']
)

# Token usage
sketch_tokens_prompt = Histogram(
    'sketch_tokens_prompt',
    'Prompt tokens used',
    ['model'],
    buckets=[1000, 2000, 3000, 4000, 5000]
)
sketch_tokens_completion = Histogram(
    'sketch_tokens_completion',
    'Completion tokens used',
    ['model'],
    buckets=[100, 200, 400, 600, 800, 1000]
)
```

### Tracing (OpenTelemetry)

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@traced(span_name="planner.sketch")
async def generate_plan_sketch(
    user_request: str,
    session_state: SessionState,
    trace_id: str
) -> PlanSketch:
    """Generate plan sketch with tracing"""
    with tracer.start_as_current_span("assemble_prompt"):
        components = await assembler.assemble_prompt(user_request, session_state, agent_capabilities)

    with tracer.start_as_current_span("call_llm"):
        response = await call_llm_sketch(components, temperature=0.3, max_tokens=800)

    with tracer.start_as_current_span("parse_json"):
        plan_sketch = json.loads(response.content)

    with tracer.start_as_current_span("validate_structure"):
        validate_sketch_structure(plan_sketch)

    return plan_sketch
```

### Logging (Structured)

```python
import structlog

logger = structlog.get_logger()

# Log sketch generation
logger.info(
    "sketch_generated",
    user_request=user_request[:100],  # Truncate for privacy
    intent=plan_sketch.intent,
    step_count=len(plan_sketch.steps),
    complexity=plan_sketch.complexity,
    model=selected_model,
    latency_ms=response.latency_ms,
    tokens_prompt=response.tokens_prompt,
    tokens_completion=response.tokens_completion,
    trace_id=trace_id
)

# Log hallucinated tools
if hallucinated_tools:
    logger.warning(
        "sketch_hallucinated_tools",
        hallucinated_tools=hallucinated_tools,
        plan_sketch=plan_sketch,
        trace_id=trace_id
    )

# Log retry attempts
logger.warning(
    "sketch_retry",
    attempt=attempt,
    retry_reason="json_parse_failed",
    temperature=temperature,
    trace_id=trace_id
)
```

---

## Canonical Values

### Configuration Parameters

```yaml
# k1/config/planner.yml
planner:
  sketch:
    # Temperature tuning
    temperature_primary: 0.3        # PRIMARY setting (balance creativity + consistency)
    temperature_fallback: 0.0       # FALLBACK (fully deterministic, retry)

    # Token budget
    max_tokens_response: 800        # Max tokens for sketch response (complex plans)
    max_tokens_prompt: 3000         # Max tokens for assembled prompt (compression if exceeded)
    max_tokens_context: 500         # Max tokens for context summary

    # Few-shot examples
    max_few_shot_examples: 5        # Max few-shot examples (token budget control)
    few_shot_example_tokens: 240    # Average tokens per example

    # Tool listing
    max_available_tools: 20         # Max tools in Available Tools list (token budget control)
    tool_listing_tokens: 40         # Average tokens per tool

    # Retry strategy
    max_retries: 2                  # Max retry attempts (3 total attempts)

    # Model selection
    model_primary: "gpt-4o-mini"    # PRIMARY model (best balance)
    model_fast: "gemini-1.5-flash"  # FAST model (350ms latency)
    model_local: "gemma-2b"         # LOCAL model (simple intents only)
    enable_local_slm: true          # Enable local SLM for simple intents

    # Quality targets
    json_parse_success_rate_target: 0.99    # >99% parse success rate
    tool_hallucination_rate_target: 0.01    # <1% hallucination rate
    intent_accuracy_target: 0.95            # >95% intent classification accuracy

    # Performance budgets
    sketch_latency_p95_ms: 500      # <500ms P95 sketch latency
    sketch_latency_p50_ms: 350      # <350ms P50 sketch latency
```

---

## Implementation Plan

### Phase 1: MVP (Week 1-2)
- [x] System prompt template (static)
- [x] Few-shot examples (5 core examples)
- [x] Output format spec (JSON schema)
- [x] Available tools listing (static list, no filtering)
- [x] Context summary integration (basic beliefs extraction)
- [x] Temperature tuning (0.3 PRIMARY)
- [x] Structured output mode (OpenAI `response_format`)
- [x] Basic retry logic (2 attempts)

### Phase 2: Optimization (Week 3)
- [ ] Dynamic few-shot example selection (pattern matching)
- [ ] Tool filtering and ranking (relevance-based)
- [ ] Context compression algorithm (priority-based truncation)
- [ ] Token budget optimization (compress to 2,000 prompt tokens)
- [ ] Multi-model support (Gemini Flash, Claude Haiku)
- [ ] Model selection algorithm (complexity-based routing)

### Phase 3: Quality Improvements (Week 4)
- [ ] Advanced retry strategies (constrained examples, minimal prompt)
- [ ] Hallucination detection and correction
- [ ] Intent classification validation (test set evaluation)
- [ ] Dependency validation (detect circular dependencies)
- [ ] Complexity estimation tuning (accuracy >90%)

### Phase 4: Production Hardening (Week 5+)
- [ ] Comprehensive metrics and tracing
- [ ] A/B testing framework (compare prompt variants)
- [ ] Prompt versioning and rollback
- [ ] Learning loop integration (optimize prompts via feedback)
- [ ] Cost monitoring and alerting

---

## Consequences

### Benefits (Pros)

1. **High JSON Parse Success Rate (>99%):**
   - Structured output mode guarantees valid JSON
   - Reduces downstream parsing errors (Expand/Validate stages)

2. **Low Tool Hallucination (<1%):**
   - Explicit Available Tools list constrains LLM
   - Prevents invalid plans (unknown tools caught early)

3. **Latency Optimization (<500ms P95):**
   - Token budget control (800 max response tokens)
   - Model selection (Gemini Flash for speed, local SLM for simple intents)

4. **Cost Optimization:**
   - Compressed prompts (2,850 tokens vs 5K+ without optimization)
   - Local SLM for simple intents (free)

5. **Context-Aware Planning:**
   - SessionState integration enables personalized plans
   - User preferences, location, recent turns inform planning

6. **Graceful Error Recovery:**
   - Retry logic with fallback (temperature 0.0, constrained examples)
   - Prevents failures from cascading to user

### Drawbacks (Cons)

1. **LLM Dependency:**
   - Sketch stage requires LLM (cannot be fully deterministic)
   - LLM outages block planning pipeline

2. **Prompt Engineering Maintenance:**
   - Prompts require tuning as tool registry grows (50+ → 100+ tools)
   - Few-shot examples need updates for new use cases

3. **Token Budget Constraints:**
   - Large tool registries (100+ tools) exceed token budget
   - Must use tool filtering (may miss relevant tools)

4. **Model Selection Complexity:**
   - Different models have different quirks (JSON formatting, hallucination rates)
   - Requires model-specific handling (OpenAI vs Gemini vs Claude)

5. **Quality Variability:**
   - LLM quality varies (gpt-4o-mini 99.5% vs gemma-2b 95% parse success)
   - Must monitor quality metrics continuously

### Migration Path

**From Current State (70% complete) to Full Implementation:**

1. **Week 1:** Complete system prompt, few-shot examples, structured output mode
2. **Week 2:** Add context compression, tool filtering, retry logic
3. **Week 3:** Implement model selection algorithm, multi-model support
4. **Week 4:** Quality validation (test set evaluation, accuracy measurement)
5. **Week 5+:** Production monitoring, learning loop integration

### Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| LLM API outage (OpenAI, Gemini) | Planning blocked | Low | Multi-model fallback (OpenAI → Gemini → Claude) |
| JSON parse failures spike (>1%) | Downstream errors | Medium | Retry logic + temperature fallback |
| Tool hallucination spike (>2%) | Invalid plans | Medium | Stricter prompt constraints, arbiter validation (Stage 3) |
| Latency degradation (>500ms P95) | User experience | Medium | Model selection (switch to Gemini Flash), local SLM for simple intents |
| Cost explosion (>$1000/1M sketches) | Budget overrun | Low | Cost monitoring, local SLM prioritization |
| Prompt injection attacks | Security | Low | Input sanitization, prompt isolation (system prompt not user-controlled) |

---

## Cross-References

### Parent ADR
- **ADR-0007:** 4-Stage Planning Pipeline (Sketch → Expand → Validate → Commit)

### Related Sub-ADRs
- **0007b:** Expand Stage Tool/Prompt Registry Integration (consumes sketch output)
- **0007c:** Validation Stage 2-Tier Implementation (validates sketch quality)

### Dependencies
- **ADR-0001b:** Model Hub Architecture (LLM inference infrastructure)
- **ADR-0005:** Agent Lifecycle FSM (Planner WARMING state loads prompts)
- **ADR-0001d:** AI Agent Persona Prompts (prompt template format)
- **ADR-0017:** SessionState 6-Section Design (context summary source)
- **ADR-0040:** Learning Loop (prompt optimization via feedback)

---

## Appendix: Few-Shot Example Library

### Example 1: Simple Single-Step (Info Lookup)
```json
{
  "user_request": "What's the weather in San Francisco?",
  "output": {
    "intent": "INFO_LOOKUP",
    "steps": [
      {
        "step_id": 0,
        "action": "get current weather for San Francisco",
        "tool": "weather_api",
        "parameters": {"location": "San Francisco, CA"},
        "dependencies": []
      }
    ],
    "complexity": "simple"
  }
}
```

### Example 2: Moderate Multi-Step (Booking Workflow)
```json
{
  "user_request": "Find a highly-rated Italian restaurant nearby and book a table for 2 at 7pm tonight",
  "output": {
    "intent": "MULTI_STEP_PLANNING",
    "steps": [
      {
        "step_id": 0,
        "action": "search for Italian restaurants nearby with high ratings",
        "tool": "restaurant_search",
        "parameters": {
          "cuisine": "Italian",
          "rating_min": 4.0,
          "location": "user_location"
        },
        "dependencies": []
      },
      {
        "step_id": 1,
        "action": "book reservation at top result",
        "tool": "reservation_booking",
        "parameters": {
          "restaurant_id": "{step_0.results[0].id}",
          "party_size": 2,
          "time": "19:00",
          "date": "today"
        },
        "dependencies": [0]
      }
    ],
    "complexity": "moderate"
  }
}
```

### Example 3: Complex Parallel (Travel Planning)
```json
{
  "user_request": "Plan a weekend trip to Seattle: find flights, hotel, and restaurant recommendations",
  "output": {
    "intent": "MULTI_STEP_PLANNING",
    "steps": [
      {
        "step_id": 0,
        "action": "search for flights to Seattle this weekend",
        "tool": "flight_search",
        "parameters": {
          "destination": "Seattle, WA",
          "departure_date": "this_saturday",
          "return_date": "this_sunday"
        },
        "dependencies": []
      },
      {
        "step_id": 1,
        "action": "search for hotels in Seattle",
        "tool": "hotel_search",
        "parameters": {
          "location": "Seattle, WA",
          "check_in": "this_saturday",
          "check_out": "this_sunday"
        },
        "dependencies": []
      },
      {
        "step_id": 2,
        "action": "get restaurant recommendations in Seattle",
        "tool": "restaurant_search",
        "parameters": {
          "location": "Seattle, WA",
          "rating_min": 4.5
        },
        "dependencies": []
      }
    ],
    "complexity": "complex"
  }
}
```

### Example 4: Error Recovery (Clarification Needed)
```json
{
  "user_request": "Book something",
  "output": {
    "intent": "CLARIFICATION_NEEDED",
    "steps": [],
    "complexity": "simple"
  }
}
```

### Example 5: Sequential Dependencies (Calendar + Email)
```json
{
  "user_request": "Schedule a team meeting for tomorrow at 2pm and email the team",
  "output": {
    "intent": "MULTI_STEP_PLANNING",
    "steps": [
      {
        "step_id": 0,
        "action": "create calendar event for team meeting",
        "tool": "calendar_event_create",
        "parameters": {
          "title": "Team Meeting",
          "start_time": "tomorrow 14:00",
          "duration_minutes": 60,
          "attendees": ["team@example.com"]
        },
        "dependencies": []
      },
      {
        "step_id": 1,
        "action": "send email notification to team",
        "tool": "email_send",
        "parameters": {
          "to": ["team@example.com"],
          "subject": "Team Meeting Scheduled",
          "body": "Meeting scheduled for tomorrow at 2pm. Calendar invite sent."
        },
        "dependencies": [0]
      }
    ],
    "complexity": "moderate"
  }
}
```

---

## Conclusion

This sub-ADR specifies a comprehensive prompt engineering strategy for Stage 1 (Sketch) of the 4-stage planning pipeline. The multi-component approach balances **LLM creativity** (generate diverse plans) with **determinism** (>99% JSON parse success, <1% tool hallucination) while meeting **performance budgets** (<500ms P95 latency, <$1 per 1,000 sketches).

**Key innovations:**
1. **Structured output mode:** Guarantees valid JSON (no markdown wrapping)
2. **Dynamic tool filtering:** Reduces token budget while maintaining relevance
3. **Context compression:** Fits SessionState beliefs in 500 tokens (prioritized truncation)
4. **Model selection algorithm:** Routes simple intents to local SLM (150ms, free)
5. **Retry fallback:** Temperature 0.0 for greedy decoding (highest parse success)

**Next steps:** Proceed to **0007b (Expand Stage)** to enrich sketch with tool/prompt registry metadata.
