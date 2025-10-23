"""
Sketch Stage - LLM-Powered Plan Generation (Stage 1 of 4)

**ADR Reference:** ADR-0007a (Sketch Stage LLM Prompt Engineering)

**Purpose:**
Generate structured JSON plan sketch from user intent using LLM inference.

**Key Responsibilities:**
1. Assemble multi-component prompt (system, few-shot, tools, context)
2. Call Model Hub with temperature tuning (0.3 primary, 0.0 fallback)
3. Parse JSON response with retry logic
4. Return PlanSketch (intent, steps, complexity)

**Performance Target:** <500ms P95

**Input:** User request + SessionState context
**Output:** PlanSketch (JSON structure with intent, steps[], complexity)

**Model Selection:**
- gpt-4o-mini: PRIMARY (best balance, 99.5% parse success)
- gemini-1.5-flash: FAST (350ms latency, 99.0% parse success)
- gemma-2b (local): SIMPLE INTENTS (150ms, 95% parse success)

**Quality Metrics:**
- JSON parse success rate: >99%
- Tool hallucination rate: <1%
- Intent classification accuracy: >95%

**Token Budget:**
- Prompt: ~2,850 tokens (system 150 + examples 1200 + tools 800 + context 500 + format 200)
- Response: 800 max tokens
- Total: 3,650 tokens (fits in 4K context window)

**Error Handling:**
- Retry with temperature 0.0 on JSON parse failure
- Retry with constrained examples on validation failure
- Max 2 retries (3 total attempts)
"""

from .llm_client import LLMClient
from .prompt_assembler import PromptAssembler
from .sketch_generator import SketchGenerator

__all__ = ["PromptAssembler", "LLMClient", "SketchGenerator"]
