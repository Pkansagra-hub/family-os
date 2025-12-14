# Module Documentation Template

**Purpose**: Reusable skeleton for documenting K0/K1 modules (hippocampus, workspace, affect, etc.)
**Usage**: Copy sections to `k0/modules/<module_name>/README.md` and fill in details
**Maintenance**: Update this template when module documentation patterns change

---

## Template Structure

This skeleton provides 13 sections covering:

- Purpose & architecture position
- External interfaces (APIs, events, storage)
- Internal components & responsibilities
- Data model & storage schema
- Pipeline integration (owned vs participates)
- Invariants, guarantees & assumptions
- Performance & scaling characteristics
- Security, PII & safety controls
- Observability (metrics, traces, logs)
- ADRs, contracts & diagrams
- Testing strategy
- Migration & evolution plans
- Open questions & TODOs

---

# <module_name> Module

**Status**: DRAFT | REVIEWED | IMPLEMENTED
**Owner**: <team/role>
**Layer**: <e.g. cognition / infra / governance>
**Primary Pipelines**: PXX, PYY, ...

---

## 1. Purpose & Scope

### 1.1 Mission

> Short paragraph: what this module is *for* and what it should never do.

- Primary responsibilities:
  - …
- Non-goals (out of scope):
  - …

### 1.2 Position in the Architecture

- Upstream dependencies:
  - …
- Downstream consumers:
  - …
- Relationship to:
  - K0 (memory kernel):
  - K1 (intelligence kernel):

---

## 2. External Interfaces

### 2.1 Public APIs (in-process)

List functions/classes other modules/pipelines can call directly.

- API surface:
  - `<ModuleService>.method_name(params) -> Result`
  - …

For each, define:

#### `method_name`

- **Description**: …
- **Input**:
  - …
- **Output**:
  - …
- **Error modes**:
  - …
- **Idempotency**:
  - …

### 2.2 Event Interfaces (Bus Topics)

- Subscribes to topics:
  - `<domain.sub.action.vN>` – reason: …
- Emits topics:
  - `<domain.sub.action.vN>` – reason: …

> All topics must exist in the global **Event Bus Topic Registry** (see `k0/pipelines/whiteboard.md` Section 3).

### 2.3 Storage Interfaces

- Tables read:
  - `st_<table>` – purpose: …
- Tables written:
  - `st_<table>` – semantics: insert / update / delete / soft-delete
- External services:
  - `<service>` – <read-only / read-write / cache-only>

---

## 3. Internal Components & Responsibilities

> Describe the internal structure of the module. This is *inside* the module boundary.

### 3.1 High-Level Structure

- Core classes:
  - `<ComponentName>` – role: …
- Submodules / files:
  - `./service.py` – …
  - `./repository.py` – …
  - `./tasks.py` – …

### 3.2 Responsibilities by Component

For each internal component:

#### <ComponentName>

- **Role**: …
- **Inputs**: …
- **Outputs**: …
- **Called by**: …
- **Calls into**: …
- **Stateful?**: yes/no (describe state if yes)

---

## 4. Data Model

### 4.1 Core Data Structures

- Domain structs / value objects:
  - `<DomainType>` – fields & meaning
- Serialization formats:
  - JSON schema IDs:
  - FlatBuffers / other:

### 4.2 Storage Schema References

- Tables:
  - `st_<table>` – link: `../storage/README.md` or migrations
- Indices:
  - …
- Retention:
  - How long data is kept, by band / space / user.

---

## 5. Pipeline Integration

> How this module plugs into the 20 pipelines.

### 5.1 Owned Pipelines

- Primary pipelines this module **owns**:
  - PXX – role:
  - PYY – role:

For each owned pipeline, reference its mini-spec:

- `PXX` spec: `../pipelines/whiteboard.md#6.2-pxx-<name>`

### 5.2 Participates In (Non-Owned)

- Pipelines where this module is used but not owned:
  - PAA – used as inline helper / service
  - PBB – used as separate event-driven component

### 5.3 Trigger–Effect Chains

- When module receives `<topic_a>`:
  - It does:
  - It may emit:
- When module API `<method_name>` is called:
  - It reads:
  - It writes:
  - It emits:

---

## 6. Invariants, Guarantees & Assumptions

### 6.1 Invariants

- Always true:
  - …
- Never allowed:
  - …

### 6.2 Guarantees

- On success:
  - …
- Across retries / idempotent replays:
  - …
- Ordering assumptions:
  - …

### 6.3 Assumptions

- About upstream:
  - …
- About downstream:
  - …
- About storage / infra:
  - …

---

## 7. Performance & Scaling

- Latency targets:
  - API calls:
  - Event handling:
- Throughput expectations:
  - Events/sec nominal:
  - Max burst:
- Batch behavior:
  - Batch size:
  - Impact on memory / CPU:
- Parallelism strategy:
  - Async tasks:
  - Worker pools:
  - Process / thread usage:

---

## 8. Security, PII & Safety

- Bands handled:
  - GREEN:
  - AMBER:
  - RED:
  - BLACK:
- PII rules:
  - Fields never stored:
  - Fields only in band `<X>`:
- Access control:
  - Which roles / caps can call this module:
- Safety hooks:
  - Which policies / classifiers must pass:
- Audit:
  - What is logged:
  - Where:
  - Retention:

---

## 9. Observability

- Metrics:
  - `module_<name>_requests_total{status=...}`
  - …
- Traces:
  - Span names:
  - Attributes:
- Logs:
  - Log keys:
  - Error patterns:
- Dashboards:
  - Links / descriptions:

---

## 10. ADRs, Contracts & Diagrams

- ADRs:
  - ADR-`XXXX` – <decision title>
  - ADR-`YYYY` – …
- Contracts:
  - `contracts/modules/<module_name>/*.json`
  - `contracts/events/<topic>.json`
- Diagrams:
  - `architecture_diagrams/k0/<module_name>_*.mmd`

---

## 11. Testing Strategy

- Unit tests:
  - Key scenarios:
- Integration tests:
  - Pipelines touched:
- Property-based / fuzz:
  - …
- Performance tests:
  - Targets & benchmarks:

---

## 12. Migration / Evolution

- Known future phases:
  - Phase 1:
  - Phase 2:
- Backward compatibility:
  - How schema / topics will evolve:
- Deprecation plan:
  - What can be removed later and how:

---

## 13. Open Questions / TODOs

- [ ] …
- [ ] …
- [ ] …

---

## Module Registry

Track all K0/K1 modules with standardized status and ownership.

| Module | Status | Owner | Layer | Primary Pipelines | README |
|--------|--------|-------|-------|-------------------|--------|


**Status definitions:**

- **DESIGN** — Architecture complete, not yet implemented
- **DRAFT** — Partial implementation, not production-ready (current affect status)
- **REVIEWED** — Implementation complete, under review
- **IMPLEMENTED** — Production-ready, tests passing

---

## Usage Instructions

1. **Copy this template** to `k0/modules/<module_name>/README.md`
2. **Replace all `<placeholders>`** with actual module details
3. **Delete sections** that don't apply (rare - most modules need all 13)
4. **Update Event Bus Topic Registry** (`k0/pipelines/whiteboard.md` Section 3) when adding new topics
5. **Link from pipeline specs** when module is used in P01-P20
6. **Add to Module Registry** above with status, owner, layer, and pipelines
7. **Keep synchronized** with ADRs, contracts, and diagrams

---

## Template Maintenance

Update this template when:

- [ ] New module patterns emerge (e.g., streaming modules, stateful agents)
- [ ] Section structure changes (add/remove/reorganize)
- [ ] Cross-references change (ADR locations, diagram paths, contract schemas)
- [ ] Observability standards evolve (new metric patterns, trace conventions)
