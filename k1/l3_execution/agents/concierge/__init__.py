"""
K1 Layer 3 Execution — agents/concierge/ (🤖 AI Agent)

PURPOSE:
========
AI Agent for NLU (Natural Language Understanding) & intent classification (<50ms P95).
Uses small language model (SLM) for fast inference on NPU/GPU.

RESPONSIBILITIES:
=================
1. Intent Classification: NLU, intent extraction (T2/T3 fallback from Layer 1)
2. Entity Extraction: Named entity recognition (NER)
3. Dialogue Act Classification: Question, command, statement, clarification

PRIMARY ADRs:
=============
- ADR-0005e: Agent Personalities (Concierge: 50ms budget)
  * Concierge is AI agent with 50ms response time budget
  * Fast NLU for intent classification
  * Model: Phi-3-mini (3.8B) on NPU/GPU for <50ms inference
  * Capabilities: TOOL_CALL, MEMORY_READ, MODEL_CALL

- ADR-0001b: Model Hub Integration (Concierge uses Model Hub)
  * Concierge calls Model Hub for LLM inference
  * Placement preference: NPU → GPU (low latency)
  * Fallback cascade: phi-3-mini (local) → gpt-4o-mini (remote)

RELATED ADRs:
=============
- ADR-0024: Performance Budgets (Concierge <50ms)
- ADR-0027: Model Placement (local-first SLM)
- ADR-0031: Cost Tracking (Concierge token usage)

CONCIERGE RESPONSIBILITIES:
============================
**1. Intent Classification (T2/T3 Fallback):**
- **Layer 1 T1:** Rule-based intent classification (80% coverage, <5ms)
- **Layer 1 T2:** Keyword/similarity matching (15% coverage, <20ms)
- **Layer 3 Concierge T3:** LLM-based NLU (5% coverage, <50ms)

**Example T3 Fallback:**
```
User: "Can you help me find a good recipe for something with chicken and mushrooms?"
T1: NO_MATCH (no keyword triggers)
T2: NO_MATCH (no similarity match)
T3 (Concierge): INTENT=search_recipe, ENTITIES=[chicken, mushrooms]
```

**2. Entity Extraction (NER):**
- Extract entities from user message: persons, places, dates, etc.
- Use SLM for entity recognition
- Return structured entities: `{type: "person", value: "John", confidence: 0.95}`

**3. Dialogue Act Classification:**
- Classify user message as: question, command, statement, clarification
- Used by Orchestrator for turn management
- Examples:
  - "What's the weather?" → QUESTION
  - "Turn on the lights" → COMMAND
  - "I like pizza" → STATEMENT
  - "Did you mean Seattle or Portland?" → CLARIFICATION

CONCIERGE ARCHITECTURE:
=======================
**Model Configuration:**
```yaml
agent_type: "concierge"
category: "ai_agent"
layer: 3

personality:
  response_time_budget_ms: 50
  reasoning_style: "fast_nlp"
  description: "Intent classification, greeting, routing"

model_hub:
  primary_model: "phi-3-mini"  # 3.8B SLM on NPU/GPU
  fallback_model: "gpt-4o-mini"  # Remote fallback
  placement_preference: ["NPU", "GPU"]  # Low latency

capabilities:
  - TOOL_CALL
  - MEMORY_READ
  - MODEL_CALL

performance_targets:
  inference_latency_ms: 50  # P95
  accuracy: 0.90  # Intent classification
  entity_extraction_accuracy: 0.85  # NER
```

**Inference Pipeline:**
```python
async def classify_intent(self, user_message: str) -> IntentResult:
    \"\"\"Classify intent using SLM (<50ms).\"\"\"
    # 1. Build prompt
    system_prompt = self.personality.format_personality_prompt()
    user_prompt = f\"\"\"Classify the intent of this message:

User: {user_message}

Respond with JSON:
{{
    "intent": "search_recipe" | "weather_query" | "control_device" | ...,
    "entities": [{{type": "food", "value": "chicken"}}, ...],
    "dialogue_act": "question" | "command" | "statement" | "clarification",
    "confidence": 0.95
}}
\"\"\"

    # 2. Call Model Hub
    model_request = ModelRequest(
        model="phi-3-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,  # Consistent intent classification
        max_tokens=200,  # Short response
        json_mode=True  # Enforce JSON output
    )

    response = await self.model_hub.inference(model_request)

    # 3. Parse response
    result = json.loads(response.content)
    return IntentResult(
        intent=result["intent"],
        entities=result["entities"],
        dialogue_act=result["dialogue_act"],
        confidence=result["confidence"]
    )
```

PERFORMANCE METRICS:
====================
- Intent classification: <50ms P95 (SLM inference)
- Accuracy: >90% (intent), >85% (entity extraction)
- Model: Phi-3-mini (3.8B) on NPU/GPU
- Fallback latency: <300ms (remote gpt-4o-mini)
- Token usage: ~150 tokens/request (system + user + response)

INTEGRATION POINTS:
===================
**Layer 1 → Layer 3 (T3 Fallback):**
```python
from k1.l3_execution.agents.concierge import ConciergeAgent

concierge = ConciergeAgent(config)
intent_result = await concierge.classify_intent(
    user_message="Can you help me find a good recipe with chicken?"
)
# Returns: IntentResult(intent="search_recipe", entities=[...], ...)
```

**Layer 3 → Layer 4 (Model Hub):**
```python
# Concierge calls Model Hub for inference
from k1.l3_execution.model_hub import ModelHub

model_hub = ModelHub()
response = await model_hub.inference(model_request)
```

**Layer 3 → Layer 2 (Intent to Orchestrator):**
```python
# Pass intent to Orchestrator for task planning
orchestrator.receive_intent(
    session_id=session_id,
    intent=intent_result.intent,
    entities=intent_result.entities
)
```

TESTING:
========
See tests/l3_execution/agents/test_concierge.py (ADR-0004d):
- Intent classification (<50ms P95)
- Accuracy (>90% intent, >85% entity extraction)
- Model placement (NPU → GPU fallback)
- Fallback cascade (phi-3-mini → gpt-4o-mini)
- Token usage tracking
- JSON mode enforcement

OBSERVABILITY:
==============
Prometheus Metrics (ADR-0029):
- layer3_concierge_inference_latency_ms{model}
- layer3_concierge_accuracy{metric_type="intent|entity"}
- layer3_concierge_token_usage{model}
- layer3_concierge_fallback_rate{}

Structured Logs:
```python
logger.info(
    "intent_classified",
    agent_id=agent_id,
    intent=intent_result.intent,
    confidence=intent_result.confidence,
    latency_ms=latency,
    model="phi-3-mini",
    accelerator="NPU",
    trace_id=trace_id
)
```

RESEARCH FOUNDATIONS:
=====================
- Intent classification (Hakkani-Tür et al. 2016) — Joint intent + entity models
- Small Language Models (Kaplan et al. 2020) — Scaling laws for efficient inference
- Dialogue acts (Bunt 2009) — Dialogue act taxonomy

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
