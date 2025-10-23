"""
K1 Layer 3 Execution — model_hub/adapters/

PURPOSE:
========
Provider adapters (OpenAI, Anthropic, vLLM, Ollama) with <5ms overhead.
Unified interface across providers.

RESPONSIBILITIES:
=================
1. Unified Interface: Consistent API across providers
2. Provider Adapters:
   - OpenAI: GPT-4o, GPT-4o-mini (remote)
   - Anthropic: Claude-3-Haiku, Claude-3-Sonnet (remote)
   - vLLM: Gemma-2-9B (local GPU)
   - Ollama: Phi-3-mini (local NPU/CPU)
3. Request Translation: Convert ModelRequest to provider format
4. Response Normalization: Standardize ModelResponse format

PRIMARY ADRs:
=============
- ADR-0001b: Model Hub Architecture (adapter pattern)
- ADR-0027: Model Placement (provider selection)

RELATED ADRs:
=============
- ADR-0009: Circuit Breaker (adapter resilience)
- ADR-0024: Performance Budgets (adapter <5ms overhead)

PERFORMANCE METRICS:
====================
- Adapter overhead: <5ms P95
- Provider support: 4 providers (OpenAI, Anthropic, vLLM, Ollama)

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
