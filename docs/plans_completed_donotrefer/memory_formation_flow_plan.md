# Memory Formation Flow Plan

## Goal

Produce an end-to-end specification (and supporting ADR) for how memories are formed across the dual-kernel architecture, covering user ingress through K1, bridge envelopes, K0 pipeline execution, and resulting observability/feedback loops.

## Milestone 1 – Component Inventory (Discovery)

### Epic 1.1 – K1 Ingress & Agent Fabric Mapping

- Issue 1.1.1: Trace user chat path (clients → API gateway → ingress middleware → concierge agent) referencing ADR-0001, ADR-0004, ADR-0006.
- Issue 1.1.2: Catalogue dynamic agent creation lifecycle (Concierge, specialists, helpers) per ADR-0086 and supporting ADRs in `03-layer2-orchestration/`.
- Issue 1.1.3: Document SessionState touch-points (ADR-0017) and interaction with negotiation/selection phases (ADR-0006 series).

### Epic 1.2 – Tooling & Planning Interfaces

- Issue 1.2.1: Inventory MCP/WASM tool subsystems (ADR-0033 family) and their role in turn execution.
- Issue 1.2.2: Map Planner pipeline (ADR-0007 series) outputs that feed memory writers (FlowDef, tool results, execution traces).
- Issue 1.2.3: Identify observability hooks (cognitive_trace_id propagation per ADR-0029/0030) required for end-to-end tracing.

### Epic 1.3 – Writer Agents & Session Observers

- Issue 1.3.1: Extract responsibilities from `whiteboard_chatexp.md` and relevant ADR drafts for Tier-3 writer agents.
- Issue 1.3.2: Determine metadata expectations (affect tags, salience, decay hints) and how writers access SessionState snapshots.
- Issue 1.3.3: Confirm non-authoritative constraints (writers must not bypass bridge/P02) using ADR-0001c/0001d.

## Milestone 2 – Bridge & Contract Alignment

### Epic 2.1 – Envelope & Schema Review

- Issue 2.1.1: Review `k1.l5_infrastructure.bridge_k0` modules and ADR-0001a to understand batching, idempotency, QoS bands.
- Issue 2.1.2: Audit contract files (`k1/contracts/k0_bridge/**`, `k0/contracts/**`) for MemoryWrite/Recall envelopes, including fast vs smart lane indicators.
- Issue 2.1.3: Note serialization pathways (JSON primary, FlatBuffers optimization) and required headers/trace metadata.

### Epic 2.2 – Command & SSE Pathway Mapping

- Issue 2.2.1: Diagram command flow (writer → command_client → HTTP/2 → K0 Command port) with reference to architecture diagrams (`architecture_diagrams/k0/*.mmd`).
- Issue 2.2.2: Capture SSE/Observability return paths (receipts, topic subscriptions) and how K1 updates SessionState meta.
- Issue 2.2.3: Document backpressure/fast vs smart lane criteria per ADR-0049, ADR-0039b, ADR-0022.

## Milestone 3 – K0 Pipeline Detailing

### Epic 3.1 – P02 MemoryWrite Deep Dive

- Issue 3.1.1: Extract responsibilities from ADRs in `15-20-pipelines/` (especially P01-P04, P06, P08, P19) plus whiteboard specs.
- Issue 3.1.2: Determine decision logic for fast lane vs smart lane (intent clarity, obligations, privacy bands) and resulting pipeline fan-out.
- Issue 3.1.3: Identify storage drivers, receipts, and WAL interactions from architecture diagrams and ADR-0001d/0001c.

### Epic 3.2 – Downstream Pipeline Interactions

- Issue 3.2.1: Map how P03 (consolidation), P06 (learning), P08 (affect), P19 (personalization) subscribe to MemoryWrite outputs.
- Issue 3.2.2: Clarify multi-tenant (individual vs dyad vs family) storage strategy per ADR-0050 family, knowledge graph ADR-0081, and social relationship ADRs.
- Issue 3.2.3: Capture triggers for SSE events, proactive notifications (P05), and sync operations (P07) tied to new memories.

## Milestone 4 – Flow Synthesis & Validation

### Epic 4.1 – End-to-End Sequence Draft

- Issue 4.1.1: Produce sequence diagram (user message → concierge → planner/tools → writer → bridge → P02 → downstream pipelines → SSE) aligning with module names.
- Issue 4.1.2: Identify variants (GREEN fast path, AMBER smart path, RED band with extra policy evaluation) and note decision points.
- Issue 4.1.3: Validate against performance budgets (ADR-0024) and ensure non-blocking guarantees for chat UX.

### Epic 4.2 – Cross-Team Review Prep

- Issue 4.2.1: Prepare checklist of ADRs and diagrams for stakeholder sign-off (architecture, memory, policy teams).
- Issue 4.2.2: Outline test coverage requirements (writer agent tests, bridge contract tests, pipeline integration tests) referencing `testing-guide.md` and ADR testing standards.

## Milestone 5 – ADR Authoring & Publication

### Epic 5.1 – Draft ADR Content

- Issue 5.1.1: Assemble ADR structure (Context, Drivers, Decisions, Flow diagrams, Consequences) using findings from prior milestones.
- Issue 5.1.2: Ensure references to all supporting ADRs/diagrams/contracts with proper cross-links.
- Issue 5.1.3: Highlight governance rules (writer constraints, bridge-only boundary, pipeline ownership) as non-negotiable decisions.

### Epic 5.2 – Review & Rollout

- Issue 5.2.1: Coordinate review cycle (architecture team, K0 owners, K1 owners) and capture feedback.
- Issue 5.2.2: Finalize ADR numbering/status, update `adr_master_reference.md`, and link from relevant modules/docs.
- Issue 5.2.3: Plan follow-up work (diagram updates, implementation tickets) once ADR is accepted.
