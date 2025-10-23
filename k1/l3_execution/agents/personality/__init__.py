"""
K1 Layer 3 Execution — agents/personality/

PURPOSE:
========
Persona adaptation for AI agents (<5ms trait formatting).
Formats SessionState persona section as LLM system prompt for personality consistency.

RESPONSIBILITIES:
=================
1. AI Agent Personalities:
   - Concierge (50ms): NLU, intent classification
   - Planner (5000ms): Task planning, LLM inference
   - Researcher (3000ms): Knowledge synthesis, retrieval
   - Safety Watch (100ms): Content filtering, PII detection

2. Trait Formatting: Format SessionState persona section as LLM system prompt (<5ms)
3. Capability Assignment: 5 capability types (TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL, NETWORK_ACCESS)

PRIMARY ADRs:
=============
- ADR-0005e: Agent Personalities (4 AI agents, capability system)
  * 4 AI agent personalities with response time budgets
  * Concierge: 50ms budget (fast NLU, intent classification)
  * Planner: 5000ms budget (deep reasoning, task decomposition)
  * Researcher: 3000ms budget (knowledge synthesis, RAG)
  * Safety Watch: 100ms budget (content filtering, PII detection)
  * 54 pure actors: procedural logic (no personalities)

- ADR-0017d: SessionState Persona Section
  * Persona stored in SessionState.persona section
  * Fields: name, response_style, expertise_areas, communication_preferences
  * Updated by user preferences, learning loop feedback

RELATED ADRs:
=============
- ADR-0001b: Model Hub (personality → LLM prompt injection)
- ADR-0010: Capability Security (personality-based capabilities)

PERSONALITY TRAITS:
===================
**Concierge (50ms budget):**
```yaml
name: "Concierge"
response_time_budget_ms: 50
reasoning_style: "fast_nlp"
description: "Intent classification, greeting, routing"
capabilities: [TOOL_CALL, MEMORY_READ, MODEL_CALL]
model_preferences:
  primary: "phi-3-mini"  # 3.8B SLM on NPU
  fallback: "gpt-4o-mini"  # Remote fallback
placement_preference: ["NPU", "GPU"]  # Low latency
```

**Planner (5000ms budget):**
```yaml
name: "Planner"
response_time_budget_ms: 5000
reasoning_style: "deep_reasoning"
description: "Task planning, 4-stage pipeline"
capabilities: [TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL]
model_preferences:
  primary: "gemma-2-9b"  # 9B model for planning
  fallback: "gpt-4o-mini"  # Remote fallback
placement_preference: ["GPU", "CPU", "Remote"]  # Allow longer latency
```

**Researcher (3000ms budget):**
```yaml
name: "Researcher"
response_time_budget_ms: 3000
reasoning_style: "knowledge_synthesis"
description: "Knowledge synthesis, RAG, multi-store retrieval"
capabilities: [TOOL_CALL, MEMORY_READ, MODEL_CALL, NETWORK_ACCESS]
model_preferences:
  primary: "gemma-2-9b"  # 9B model for synthesis
  fallback: "claude-3-haiku"  # Remote fallback (better synthesis)
placement_preference: ["GPU", "Remote"]  # Quality over latency
```

**Safety Watch (100ms budget):**
```yaml
name: "Safety Watch"
response_time_budget_ms: 100
reasoning_style: "rule_based_llm"
description: "Content filtering, PII detection, safety checks"
capabilities: [MEMORY_READ, MODEL_CALL]  # No tool execution
model_preferences:
  primary: "phi-3-mini"  # Fast safety checks
  fallback: "gpt-4o-mini"  # Remote fallback
placement_preference: ["NPU", "GPU"]  # Low latency
```

TRAIT FORMATTING:
=================
**System Prompt Generation (<5ms):**
```python
def format_personality_prompt(persona: PersonaSection, agent_type: str) -> str:
    \"\"\"Format persona as LLM system prompt.\"\"\"
    personality_traits = AGENT_PERSONALITIES[agent_type]

    prompt = f\"\"\"You are {personality_traits['name']}, a {personality_traits['description']}.

Your Response Style:
- Response Time Budget: {personality_traits['response_time_budget_ms']}ms
- Reasoning Style: {personality_traits['reasoning_style']}
- Capabilities: {', '.join(personality_traits['capabilities'])}

User Preferences (from SessionState.persona):
- Communication Style: {persona.communication_preferences.style}
- Expertise Areas: {', '.join(persona.expertise_areas)}
- Privacy Band: {persona.band}

Guidelines:
- Be concise and direct
- Respect privacy band restrictions
- Use tools when appropriate
- Stay within response time budget
\"\"\"
    return prompt
```

**Example Output:**
```
You are Concierge, a Intent classification, greeting, routing.

Your Response Style:
- Response Time Budget: 50ms
- Reasoning Style: fast_nlp
- Capabilities: TOOL_CALL, MEMORY_READ, MODEL_CALL

User Preferences (from SessionState.persona):
- Communication Style: casual
- Expertise Areas: technology, programming
- Privacy Band: GREEN

Guidelines:
- Be concise and direct
- Respect privacy band restrictions
- Use tools when appropriate
- Stay within response time budget
```

CAPABILITY ASSIGNMENT:
======================
**5 Capability Types (ADR-0010):**
1. **TOOL_CALL:** Execute tools (MCP, WASM, Process)
2. **MEMORY_READ:** Read SessionState (beliefs, scoreboard, history)
3. **MEMORY_WRITE:** Write SessionState (update beliefs, scoreboard)
4. **MODEL_CALL:** Call Model Hub (LLM inference)
5. **NETWORK_ACCESS:** Egress control (external API calls)

**Per-Agent Capabilities:**
- **Concierge:** TOOL_CALL, MEMORY_READ, MODEL_CALL
- **Planner:** TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL
- **Researcher:** TOOL_CALL, MEMORY_READ, MODEL_CALL, NETWORK_ACCESS
- **Safety Watch:** MEMORY_READ, MODEL_CALL (no tool execution)

PERFORMANCE METRICS:
====================
- Trait formatting: <5ms P95
- LLM prompt injection: <1ms overhead (string concatenation)
- Personality consistency: >95% (trait adherence across turns)

INTEGRATION POINTS:
===================
**Agent Hiring (Load Personality):**
```python
from k1.l3_execution.agents.personality import PersonalityManager

personality_mgr = PersonalityManager()
system_prompt = personality_mgr.format_personality_prompt(
    persona=session_state.persona,
    agent_type="concierge"
)

# Pass to Model Hub
model_request = ModelRequest(
    model="phi-3-mini",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
)
```

**SessionState Persona Section (ADR-0017d):**
```python
@dataclass
class PersonaSection:
    name: str  # User's preferred agent name
    communication_preferences: CommunicationPreferences
    expertise_areas: List[str]
    band: PrivacyBand  # GREEN | AMBER | RED | BLACK
```

TESTING:
========
See tests/l3_execution/agents/test_personality.py (ADR-0004d):
- Trait formatting (<5ms)
- System prompt generation (all 4 AI agents)
- Capability validation (5 types)
- Personality consistency (>95% trait adherence)
- LLM prompt injection overhead (<1ms)

OBSERVABILITY:
==============
Metrics: N/A (stateless personality formatting, no runtime metrics)
Logs: Structured logs for personality load, prompt generation errors

RESEARCH FOUNDATIONS:
=====================
- Persona-based LLM prompting (Wei et al. 2022) — Chain-of-thought with personas
- Capability-based security (Dennis & Van Horn 1966) — Unforgeable tokens

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
