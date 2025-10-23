"""
K1 Layer 3 Execution — model_hub/prompt_library/

PURPOSE:
========
Prompt templates (Jinja2) with <5ms template rendering.
Versioned templates for agent-specific prompts.

RESPONSIBILITIES:
=================
1. Prompt Templates: Jinja2 templates, semantic versioning
2. Agent Prompts: agent_prompts/ directory (4 AI agents: Concierge, Planner, Researcher, Safety Watch)
3. Template Rendering: Fill template with context (<5ms)

PRIMARY ADRs:
=============
- ADR-0001b: Model Hub Architecture (prompt library)
- ADR-0007a: Stage 1 Sketch (prompt engineering)

RELATED ADRs:
=============
- ADR-0005e: Agent Personalities (agent-specific prompts)

PERFORMANCE METRICS:
====================
- Template rendering: <5ms P95
- Template count: 20+ templates (agent-specific + system)

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
