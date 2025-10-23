# Agent Prompts (ADR-0086e)

This directory contains Jinja2 prompt templates for dynamically spawned agents.

## Purpose

Prompt templates provide the LLM system prompts for dynamic agents. Each template:
- Defines agent role and expertise
- Includes example interactions
- Specifies response format
- Contains metadata (version, tokens, author)

## Template Format

Prompts use Jinja2 templating with metadata headers:
```
---
version: 1.0.0
max_tokens: 320
author: K1 Intelligence Module
created: 2025-10-23
---

You are {{agent_type}}, a specialized AI assistant...
```

## Performance

- Rendering: <5ms P95
- Token validation: 1 token ≈ 4 chars
- Template count: 58+ prompts

## Example Prompts

1. **health_specialist.prompt.j2** - Health metrics specialist (320 tokens)
2. **code_assistant.prompt.j2** - Code generation and review (280 tokens)
3. **finance_advisor.prompt.j2** - Financial planning (300 tokens)
4. **research_agent.prompt.j2** - Information gathering (250 tokens)
5. **creative_writer.prompt.j2** - Content generation (290 tokens)

## Template Variables

Available Jinja2 variables:
- `{{agent_type}}` - Agent type name
- `{{domain_expertise}}` - List of expertise areas
- `{{response_style}}` - Response style (concise/detailed/empathetic)
- `{{tools}}` - Available tools list
- `{{session_context}}` - Session-specific context

## Related ADRs

- ADR-0086: Dynamic Agent Creation Subsystem (parent)
- ADR-0086e: Prompt Directory (this component)
- ADR-0086d: Composition Pattern (prompt consumer)

## Implementation Status

STUB - M1 (1 day planned)
