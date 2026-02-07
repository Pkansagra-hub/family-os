---
adr_id: XXX-000
title: "[Decision Title]"
status: Proposed
date: YYYY-MM-DD
module: fabric | sessionstate | orchestrator | planner | concierge | model_hub | bus | bridge | agent | cross-cutting
layer: "L0 | L1 | L2 | L2.5 | L3 | L4 | L5 | L6"
authors:
  - "[Author Name]"
related_adrs: []
related_events: []
related_contracts: []
related_ports: []
implements_issue: ""
superseded_by: ""
tags: []
---

# XXX-000: [Decision Title]

## Context

### Problem Statement

[What is the issue we're trying to solve? What is driving this decision?]

### Current Situation

[Describe the current state before this decision]

### Constraints

- [Constraint 1]
- [Constraint 2]

### Requirements

- [Requirement 1]
- [Requirement 2]

---

## Decision

### Chosen Approach

[What architectural decision did we make? Be specific and clear.]

### Key Design

[What are the main components or elements of this decision?]

### Rationale

[Why did we choose this approach? What makes it the best option?]

---

## Alternatives Considered

### Alternative 1: [Name]

**Description:** [Brief description]

**Pros:**


- [Pro 1]


**Cons:**

- [Con 1]

**Rejected because:** [Reason]

### Alternative 2: [Name]

**Description:** [Brief description]


**Pros:**


- [Pro 1]

**Cons:**

- [Con 1]

**Rejected because:** [Reason]

---

## Consequences

### Positive

- [Benefit 1]
- [Benefit 2]

### Negative

- [Trade-off 1]
- [Trade-off 2]

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| [Risk 1] | Low/Med/High | Low/Med/High | [Mitigation] |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| [Component] | `k1/module/file.py` | New / Modified |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.module.event.v1` | Emitted / Consumed | [What it does] |

### Contracts Affected

| Contract | Type | Change |
|----------|------|--------|
| `module.contract.yaml` | Module | [Change description] |

### Port/Adapter Impact

| Port | Adapter | Change |
|------|---------|--------|
| `IPortName` | `AdapterName` | [Change description] |

### Success Metrics

- Metric 1: [Description and target]
- Metric 2: [Description and target]

### Testing Strategy

- [ ] Unit tests in `tests/k1/module/`
- [ ] Integration tests
- [ ] Contract tests
- [ ] Performance benchmarks

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| YYYY-MM-DD | [Name] | Initial decision |
