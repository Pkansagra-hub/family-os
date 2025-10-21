# Service Design & Modification Instructions

## Purpose
Provide a reusable checklist and knowledge base for designing or updating services in FamilyOS. This guidance keeps new work aligned with the memory-centric architecture, event hub patterns, and production guardrails already codified in the repository.

## Baseline References
- Architecture diagrams: `architecture_diagrams/` (ingested as `d1_storage_backbone`, `d2_inputs_perception`, `d3_gateways_admission`).
- Knowledge graph store: `copilot-memories/kg_store.json` (query via MCP `kg_*` tools).
- Contract manifests: `contracts/` (service-specific schemas, manifests, examples).
- Pipeline modules: `pipelines/` (bus wiring, stage implementations P01–P20).
- Event system: `events/` (bus, dispatcher, handlers, middleware, persistence).
- Production policy: `.github/copilot-instructions.md` ("ABSOLUTE ZERO TOLERANCE" rules).

Always inspect the relevant diagram + contract entry before drafting a change. Use the KG to trace dependencies (e.g., `evt_bus → evt_dispatch → evt_handlers → pip_bus → P01…P20`).

## Core Design Workflow
1. **Capture Intent & Scope**
   - Write a short purpose statement. Confirm the service fits an existing pipeline stage or warrants a new one.
   - Identify consumers and required contracts (API, events, storage).
   - Review `docs/development/contracts-playbook.md` for the contract workflow, canonical payload examples, and partner tooling references before drafting changes.

2. **Inspect Existing Contracts**
   - Open the relevant `contracts/<domain>/` entries.
   - Validate schemas with provided examples; extend manifests when introducing new event types or storage schemas.

3. **Trace Architecture Edges**
   - Use the KG (`mcp_kg_kg_paths`) to confirm upstream/downstream services.
   - Reference diagrams `d1_storage_backbone`, `d2_inputs_perception`, `d3_gateways_admission` for flow alignment (event hub, cognitive loops, advisory surfaces).

4. **Author or Update Contracts First**
   - Modify manifests, OpenAPI specs, or event schemas as needed.
   - Update docstring examples and pipeline acceptance criteria.

5. **Implement Service Logic**
   - Follow production policy: **no simulated sleeps, no fake delays**.
   - Compose with existing buses (`evt_bus`, `pip_bus`) instead of bespoke queues.
   - Keep device-local, user-controlled assumptions intact; respect E2EE constraints.

6. **Validate Through Pipelines**
   - Ensure events flow `producer → evt_bus → evt_dispatch → evt_handlers → pip_bus → P01…P20`.
   - For cognitive integrations, verify hand-offs to working memory, hippocampus, or advisory loops per diagrams.

7. **Testing Requirements**
   - Apply WARD tests (see `.github/copilot-instructions.md`).
   - Cover contract adherence, pipeline integration, and failure modes (idempotency, redaction, QoS gates).

8. **Documentation Updates**
   - Update service README and relevant files in `docs/`.
   - Record diagram/KG references in `docs/development/mmd-diagram-usage.md` if new diagrams are ingested.
   - Refresh canonical payload samples in `k0/contracts/jsonschema/examples/` and regenerate partner assets (Postman collection under `docs/api/postman/`) when schemas or ports evolve.

## Architectural Guardrails
- **Memory Backbone First**: Every service exists to serve or consume the Memory Module. Enforce data ownership, family sync rules, and device-local storage assumptions.
- **Event Hub Attachment**: Publish via `events/bus.py`; configure `events/dispatcher.py` and `events/handlers.py` to route into `pipelines/memory_bus.py`. Never bypass the shared event infrastructure.
- **Pipeline Discipline**: Reuse P01–P20 stages when possible. For new stages, add `pipelines/memory_px.py`, update `pipelines/memory_registry.py`, and document in contracts plus diagrams.
- **Policy & Safety Hooks**: Thread requests through `policy/memory_decision.py`, QoS gates, and safety monitors. Confirm `intelligence` advisory signals still terminate at P04.
- **Observability**: Emit receipts, logs, and telemetry through existing stores (`storage/receipts_store.py`, `observability/*`). Adopt `cognitive_trace_id` across new events.

## Service Modification Checklist
- [ ] Intent documented (purpose, consumers, contract impact).
- [ ] Contracts edited and validated (events, API, storage).
- [ ] KG/diagram impact traced; relationships captured in docs if new.
- [ ] Implementation aligns with bus, pipeline, and policy layers.
- [ ] Tests written with WARD covering success, failure, edge cases.
- [ ] Docs and READMEs updated in same change.
- [ ] Diagram usage log updated when new diagrams are ingested.

## Common Pitfalls to Avoid
- Skipping contract updates or schema validation.
- Introducing ad hoc queues or background sleeps to mimic load.
- Forgetting advisory boundaries (P04 executes, intelligence modules advise).
- Leaving redaction, QoS, or safety gates unhooked.
- Omitting cognitive_trace_id propagation, which breaks observability.

## Tooling Shortcuts
- **Find adjacency**: `mcp_kg_kg_neighbors(diagram_id, node_id)`.
- **Trace flows**: `mcp_kg_kg_paths(diagram_id, src, dst, max_hops=6)`.
- **Diagram summary**: `mcp_mmd_mmd_summary(path_or_id)`.
- **Pipeline tests**: `python -m ward test --path tests/storage/test_progress_tracker.py` (replace with target test paths).

Keep this document close when planning service work. Update it whenever new architectural conventions emerge or when a postmortem uncovers a gap in the process.
