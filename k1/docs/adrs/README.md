# K1 Architecture Decision Records

Canonical ADR repository for K1 Cognitive Kernel.

All ADRs follow a **sync-ready format** with YAML frontmatter that governance tooling can parse,
enabling bidirectional sync between decisions and implementation.

## Quick Start

```bash
# Check K1 ADR sync status
python -m governance.k1.scripts.sync --report

# Scan ADRs only
python -m governance.k1.scripts.adr_scanner

# Create a new ADR from template
cp k1/docs/adrs/_template.md k1/docs/adrs/FAB-XXX-your-decision-title.md
```

## ADR ID Scheme

| Prefix | Module | Example |
|--------|--------|---------|
| `FAB-` | Capability Fabric | FAB-001, FAB-002 |
| `SS-`  | SessionState | SS-001 |
| `ORCH-`| Orchestrator | ORCH-001 |
| `PLAN-`| Planner | PLAN-001 |
| `CONC-`| Concierge | CONC-001 |
| `MH-`  | Model Hub | MH-001 |
| `BUS-` | Event Bus | BUS-001 |
| `BRG-` | Bridge | BRG-001 |
| `AGT-` | Agent System | AGT-001 |
| `K1-`  | Cross-cutting K1 | K1-001 |

## File Naming

```
<PREFIX>-<NNN>-<kebab-case-title>.md
```

Examples:
- `FAB-001-envelope-schema-format.md`
- `SS-001-hot-warm-cold-tier-design.md`
- `K1-001-hexagonal-port-pattern.md`

## Directory Structure

```
k1/docs/adrs/
  _template.md          # ADR template (YAML frontmatter + markdown body)
  README.md             # This file
  FAB-001-*.md          # Fabric ADRs
  SS-001-*.md           # SessionState ADRs
  ORCH-001-*.md         # Orchestrator ADRs
  ...
```

## Sync-Ready Format

Every ADR **must** have YAML frontmatter with these required fields:

```yaml
---
adr_id: FAB-001
title: Envelope Schema Format
status: Proposed | Accepted | Deprecated | Superseded
date: 2026-02-06
module: fabric
layer: L2.5
authors:
  - name
related_adrs: []
related_events: []
related_contracts: []
related_ports: []
implements_issue: ""        # Issue ID from implementation plan (e.g., "1.1.7")
superseded_by: ""
tags: []
---
```

The governance sync tool (`governance/k1/scripts/adr_scanner.py`) parses this frontmatter
to build the ADR registry and detect drift between decisions and implementation.

## Status Lifecycle

```
Proposed --> Accepted --> [Deprecated | Superseded]
```

- **Proposed**: Under discussion. Not binding.
- **Accepted**: Binding. Implementation must comply.
- **Deprecated**: No longer relevant. Kept for history.
- **Superseded**: Replaced by a newer ADR (set `superseded_by`).

## Relationship to Legacy ADRs

Legacy ADRs in `docs/architecture/decisions-K1/` remain as historical reference.
New ADRs go in `k1/docs/adrs/` using the sync-ready format.
The governance tool scans both locations but only `k1/docs/adrs/` is authoritative.
