"""Layer 3: Execution

Agent lifecycle, AI integration (Model Hub), tool execution, dialogue management.

Performance Budget: Model Hub <50ms P95, Tools <3000ms P95

Module Categories:
- agents/: Agent lifecycle (6 modules) + AI agents (2 modules: Concierge, Researcher)
- model_hub/: AI integration infrastructure (7 modules) - ONLY for 4 AI agents
- tools/: Tool execution engine (5 modules) - MCP/WASM/Process sandboxes
- dialogue/: Dialogue management (4 modules) - Common ground, turn-taking

Key Architectural Point:
- Model Hub is ONLY for AI agents (Concierge, Planner, Researcher, Safety Watch)
- Pure actors (54 modules) use deterministic logic (no LLM calls)
"""
