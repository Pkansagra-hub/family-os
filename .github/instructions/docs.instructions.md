---
description: Documentation, READMEs, and ADRs.
applyTo: "docs/**/*.md,**/README.md,docs/architecture/decisions/**/*.md,.github/**/*.md"
---
# 📝 Documentation & ADRs — Keep it Close to Code & Contracts

## Overview
This file ensures documentation stays synchronized with code and contracts. All documentation follows the structure defined in `documentation-standards.instructions.md` and integrates with the 5-step code development workflow in `service-design.instructions.md`.

---

## 1) Documentation Locations

### Module Documentation
- **Location**: `README.md` in module root (beside code)
- **Purpose**: Module overview, quick start, main use cases
- **Content**: Purpose, architecture, API overview, examples

### Longform Documentation
- **Location**: `docs/<topic>/` directories
- **Structure**:
  ```
  docs/
  ├── architecture/       # Architecture documentation
  │   ├── decisions/      # ADRs (Architecture Decision Records)
  │   ├── patterns/       # Design patterns
  │   ├── diagrams/       # Diagram references
  │   └── tables/         # Architecture tables
  ├── api/               # API documentation
  ├── deployment/        # Deployment guides
  ├── development/       # Developer guides
  └── user/              # End-user documentation
  ```

### Architecture Decision Records (ADRs)
- **Location**: `docs/architecture/decisions/XXXX-<title>.md`
- **Template**: Use `docs/architecture/decisions/0000-template.md`
- **Naming**: `XXXX` is sequential number (0001, 0002, etc.)
- **Status**: DRAFT, PROPOSED, ACCEPTED, IMPLEMENTED, SUPERSEDED, REJECTED

### Contract Examples
- **Location**: `k1/contracts/jsonschema/examples/`
- **Format**: JSON files matching contract schemas
- **Requirement**: Examples must be kept in sync with contract schemas

---

## 2) ADR Template & Structure

### Required Sections:
```
# ADR-XXXX: <Title>

## Status
DRAFT | PROPOSED | ACCEPTED | IMPLEMENTED | SUPERSEDED | REJECTED

## Context
- What problem are we solving?
- What are the constraints?
- What existing ADRs relate to this?

## Decision
- What did we decide?
- Why this approach?

## Alternatives Considered
- Alternative 1: <description> (why rejected)
- Alternative 2: <description> (why rejected)

## Consequences
- Positive outcomes
- Risks or downsides
- Performance impact
- Security implications

## Related ADRs
- Builds on: ADR-XXXX
- Supersedes: ADR-YYYY
- Relates to: ADR-ZZZZ

## Related Contracts & Code
- Contracts: `k1/contracts/api/...yaml`
- Implementation: `k1/l3_execution/agents/...py`
- Tests: `tests/l3_execution/agents/test_...py`
```

---

## 3) Documentation Style & Content

### Writing Standards:
- **Clear headings**: Use H2/H3 hierarchy, avoid H1 in docs
- **Short paragraphs**: 2-3 sentences max per paragraph
- **Code examples**: Real examples from `k1/contracts/jsonschema/examples/`
- **Links**: Use relative paths for internal references
- **No orphaned files**: Every Markdown file must fit into the structure above

### Examples in Documentation:
- Reference contract examples: `See example in k1/contracts/jsonschema/examples/agent_creation.json`
- Use code blocks with language: ` ```python`, ` ```yaml`, ` ```json`
- Include actual working code from the repository

### Linking Strategy:
- **To ADRs**: `See [ADR-0086](../decisions/0086-dynamic-agents.md)`
- **To Code**: `Implementation: [factory.py](../../k1/l3_execution/agents/dynamic_creation/factory.py)`
- **To Contracts**: `Schema: [agent_schema.json](../../../k1/contracts/jsonschema/agent_schema.json)`

---

## 4) Integration with 5-Step Code Development Workflow

When implementing new code (per `service-design.instructions.md`):

### GATE 1: ADR Discovery
- [ ] Search existing ADRs in `docs/architecture/decisions/`
- [ ] If missing: Create new ADR with full context, decision, alternatives

### GATE 2: Contracts
- [ ] Contract examples added to `k1/contracts/jsonschema/examples/`
- [ ] Examples documented and validated

### GATE 3: Implementation
- [ ] Code comments reference ADR numbers
- [ ] README.md updated with new features
- [ ] Module documentation reflects changes

### GATE 4: Tests
- [ ] Test files documented in README or `docs/development/testing-guide.md`
- [ ] Performance targets from ADR documented

### GATE 5: Memory Documentation
- [ ] Decision record created with files touched
- [ ] Architecture diagrams updated if needed
- [ ] References added to relevant ADRs

---

## 5) Keeping Documentation Up-to-Date

### Synchronization Rules:
- **Update docs in same PR as code changes** — Never lag
- **Update docs in same PR as contract changes** — Keep examples synced
- **Update ADR when decision status changes** — Track evolution
- **Update diagrams when architecture changes** — Maintain visual representation

### Change Checklist:
- [ ] Code changes: Update related README.md
- [ ] Contract changes: Update `k1/contracts/jsonschema/examples/`
- [ ] ADR status change: Update `docs/architecture/decisions/XXXX.md`
- [ ] Architecture change: Update `architecture_diagrams/` and reference in docs
- [ ] API changes: Update `docs/api/` documentation
- [ ] Deployment changes: Update `docs/deployment/` guides

### Documentation Audit:
- Review docs quarterly for accuracy
- Check all links are valid (no 404s)
- Verify examples match current code
- Remove obsolete documentation with timestamp notes

---

## 6) Common Documentation Patterns

### New Module Documentation
Create `<module>/README.md`:
```markdown
# Module: <Name>

## Purpose
<What does this module do?>

## Architecture
<How does it work? Reference ADR-XXXX if applicable>

## Quick Start
<Example usage>

## API
<Main classes/functions>

## Related ADRs
- ADR-XXXX: <reason>

## Tests
Run: `python -m ward test --path tests/<module>/`
```

### New API Documentation
Create `docs/api/<component>.md`:
```markdown
# API: <Component>

## Overview
<What endpoints/events are provided?>

## Endpoints
[OpenAPI spec reference or examples]

## Examples
[Contract examples from k1/contracts/]

## Related Contracts
- `k1/contracts/api/<component>.yaml`

## Related ADRs
- ADR-XXXX
```

### New Deployment Guide
Create `docs/deployment/<component>.md`:
```markdown
# Deployment: <Component>

## Prerequisites
<Requirements>

## Installation
<Step by step>

## Configuration
<Config options>

## Verification
<How to verify it works>

## Troubleshooting
<Common issues>
```

---

## 7) No Stray Markdown Files

**Forbidden locations** for documentation:
- ❌ Root level loose `.md` files (except README.md)
- ❌ Random directories outside `docs/`
- ❌ Service-specific docs outside `docs/<layer>/<component>/`
- ❌ Undocumented diagrams outside `architecture_diagrams/`

**Correct approach**:
- ✅ All docs in `docs/` with proper subdirectory structure
- ✅ Module docs as `<module>/README.md`
- ✅ All diagrams in `architecture_diagrams/` with references in `docs/architecture/diagrams/README.md`
- ✅ ADRs only in `docs/architecture/decisions/`

---

## Quick Links

- **Documentation Standards**: `documentation-standards.instructions.md`
- **Code Development Workflow**: `service-design.instructions.md`
- **ADR Master Reference**: `docs/ADR_MASTER_REFERENCE.md`
- **ADR Template**: `docs/architecture/decisions/0000-template.md`
- **Architecture Diagrams**: `architecture_diagrams/`
- **Contract Examples**: `k1/contracts/jsonschema/examples/`
