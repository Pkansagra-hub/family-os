# Agent Templates (ADR-0086b)

This directory contains agent template YAML files for dynamic agent creation.

## Purpose

Agent templates define the structure and configuration for dynamically spawned agents. Each template specifies:
- Agent type and category
- Required capabilities
- Resource requirements
- Default persona traits
- Tool whitelist

## Template Structure

Templates use JSON Schema v7 validation with 3-level inheritance:
- `base_agent.agent.yml` - Root template (all agents inherit)
- `base_ai_agent.agent.yml` - AI agent base (LLM-powered agents)
- Specialist templates - Domain-specific agents (e.g., health_specialist, code_assistant)

## Performance

- Template loading (cached): <10ms P95
- Template loading (uncached): <50ms P95
- Cache hit rate: >80%
- LRU cache: 128 templates

## Example Templates

1. **health_specialist.agent.yml** - Health metrics specialist
2. **code_assistant.agent.yml** - Code generation and review
3. **finance_advisor.agent.yml** - Financial planning
4. **research_agent.agent.yml** - Information gathering
5. **creative_writer.agent.yml** - Content generation

## Schema Validation

All templates are validated against JSON Schema v7:
```yaml
$schema: http://json-schema.org/draft-07/schema#
type: object
required: [agent_type, category, capabilities, resources]
```

## Related ADRs

- ADR-0086: Dynamic Agent Creation Subsystem (parent)
- ADR-0086b: Template System (this component)
- ADR-0086a: Agent Factory (template consumer)

## Implementation Status

STUB - M1 (4 days planned)
