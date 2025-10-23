"""
K1 Layer 3 Execution — agents/registry/

PURPOSE:
========
Agent YAML specifications registry with O(1) hash table lookup.
Stores manifest for all 58 agent types (4 AI agents + 54 pure actors).

RESPONSIBILITIES:
=================
1. Agent Specifications: YAML manifest per agent type (registry/*.agent.yml)
2. Capability Declaration: Tool access, memory access, model access, network access
3. Personality Traits: Concierge (50ms), Planner (5000ms), Researcher (3000ms), Safety Watch (100ms)
4. O(1) Lookup: Hash table by agent_type, <1ms retrieval

PRIMARY ADRs:
=============
- ADR-0005: Agent Lifecycle (6-state FSM)
  * Agent registry provides specification for hire_fire to spawn agents
  * Contains FSM transition timeouts, warmup deadlines, IDLE TTL

- ADR-0005e: Agent Personalities (4 AI agents + 54 pure actors)
  * Personality traits: response_time_budget_ms, reasoning_style, tool_preferences
  * AI agents (4): Concierge, Planner, Researcher, Safety Watch
  * Pure actors (54): Orchestrator, Router, Supervisor, etc.

- ADR-0010: Capability Security
  * Capability declarations per agent type: TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL, NETWORK_ACCESS
  * Band requirements: GREEN/AMBER/RED/BLACK
  * Tool whitelist/blacklist per agent type

RELATED ADRs:
=============
- ADR-0002: Actor Model (all agents are actors)
- ADR-0010: Capability Security (agent capability declarations)

SCHEMA STRUCTURE (*.agent.yml):
================================
```yaml
agent_type: "concierge"  # Unique identifier
category: "ai_agent"  # ai_agent | pure_actor
layer: 3  # K1 layer (1-5)

# Personality (ADR-0005e)
personality:
  response_time_budget_ms: 50
  reasoning_style: "fast_nlp"  # fast_nlp | deep_reasoning | procedural
  description: "Intent classification, greeting, routing"

# Capabilities (ADR-0010)
capabilities:
  - TOOL_CALL  # Can execute tools
  - MEMORY_READ  # Can read SessionState
  - MODEL_CALL  # Can call Model Hub (AI agents only)
required_band: "GREEN"  # Minimum privacy band

# Lifecycle (ADR-0005)
lifecycle:
  warmup_timeout_ms: 250  # Max warmup time
  idle_ttl_ms: 300000  # 5 min idle → DRAINING
  drain_timeout_ms: 5000  # Max drain time

# Model Hub (AI agents only, ADR-0001b)
model_hub:
  primary_model: "phi-3-mini"  # SLM for fast inference
  fallback_model: "gpt-4o-mini"  # Remote fallback
  placement_preference: ["NPU", "GPU", "CPU"]  # Thermal-aware
```

PERFORMANCE METRICS:
====================
- Agent lookup: <1ms P95 (hash table)
- Registry size: 58 agent types (4 AI + 54 pure actors)
- Specification parsing: <10ms at startup (one-time cost)

INTEGRATION POINTS:
===================
Layer 3 hire_fire/ calls:
```python
from k1.l3_execution.agents.registry import AgentRegistry

registry = AgentRegistry()
spec = registry.get_agent_spec("concierge")  # O(1) lookup
# Returns: AgentSpec with personality, capabilities, lifecycle config
```

TESTING:
========
See tests/l3_execution/agents/test_registry.py:
- Agent spec loading (58 types)
- O(1) lookup performance (<1ms)
- Capability validation
- YAML schema validation

OBSERVABILITY:
==============
Metrics: N/A (static registry, no runtime metrics)
Logs: Structured logs for registry initialization, spec validation errors

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
