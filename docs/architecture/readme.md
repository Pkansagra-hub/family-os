# K1 Intelligence Module - Architecture Documentation

## Overview

This directory contains architecture documentation for the K1 Intelligence Module (intelligence_module) - the agentic orchestrator kernel.

## Structure

```
architecture/
├── decisions/          # Architecture Decision Records (ADRs)
├── patterns/           # Architectural pattern guides
└── diagrams/           # Supporting architecture documentation
```

## Architecture Decision Records (ADRs)

ADRs document significant architectural decisions with context, alternatives, and consequences.

**Naming**: `NNNN-descriptive-title.md` (e.g., `0001-actor-model-agent-isolation.md`)

**Template**: Use `0000-template.md` as starting point

**Status Values**:
- **Proposed**: Under discussion
- **Accepted**: Approved and implemented
- **Deprecated**: No longer recommended
- **Superseded**: Replaced by another ADR

## Architectural Patterns

Guides for K1's core architectural patterns:

- **Actor Model** (Hewitt 1973): Agent isolation with message-passing
- **MPST** (Honda et al. 2008): Multiparty session types for protocol validation
- **Capabilities** (Dennis & Van Horn 1966): Fine-grained access control
- **SEDA** (Welsh et al. 2001): Staged event-driven architecture
- **Saga Pattern** (Garcia-Molina 1987): Distributed transaction management
- **Contract Net Protocol** (Smith 1980): Multi-agent negotiation

## Related Documentation

- **Complete Specifications**: `../whiteboard.md` (21,123 lines)
- **Module Structure**: `../k1_module_analysis.md` (52 modules, 758 files, 5 layers)
- **Architecture Diagrams**: `../../architecture_diagrams/` (11 diagrams)
- **Instruction Files**: `../../.github/instructions/`

## Contributing

When creating a new ADR:

1. Copy `decisions/0000-template.md` to `decisions/NNNN-title.md`
2. Fill in all sections (Context, Decision, Consequences, Alternatives, References)
3. Link to affected architecture diagrams
4. Reference module structure from `k1_module_analysis.md`
5. Cite research foundations (Hewitt, Honda, etc.)
6. Create PR with ADR + code changes together

## ADR Index

(ADRs will be listed here as they are created)

- `0000-template.md` - ADR template (reference only)
