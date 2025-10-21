# Architecture Governance Instructions

## Purpose

Define a repeatable governance loop for architecture changes so every modification to FamilyOS reinforces the memory-centric backbone, honors security policies, and stays traceable through diagrams, contracts, and decision logs.

## Core Principles

- **Memory-first**: All flows serve the Memory Module; never fragment state outside the approved storage tiers.
- **Contract-led**: Changes start with manifests and schemas in `contracts/` before code moves.
- **Event discipline**: Publish and consume exclusively through the shared event hub (`evt_bus → evt_dispatch → evt_handlers → pip_bus`).
- **Safety & compliance**: Enforce E2EE boundaries, redaction, QoS, and policy adjudication on every new edge.
- **Observability**: Maintain `cognitive_trace_id`, receipts, and telemetry for new services.
- **Traceability**: Every architectural decision ties back to diagrams, KG entries, and documentation in the same change set.

## Governance Workflow

1. **Context sweep**
   - Load the latest diagrams (`architecture_diagrams/`) via MCP (`mmd_ingest`, `mmd_summary`).
   - Query the knowledge graph (`kg_summary`, `kg_paths`) for upstream/downstream impact.
   - Review existing instructions: `service-design.instructions.md`, `pipeline-development.instructions.md`, `event-hub.instructions.md`.
2. **Hypothesis framing**
   - Capture the intent, affected domains, and expected user impact.
   - Identify contracts to extend (`contracts/<domain>/`) and target tiers (hot/cold storage, streaming, cache).
3. **Impact validation**
   - Map new edges onto the knowledge graph; ensure no orphaned nodes or bypassed guardrails.
   - Verify policy, QoS, and safety touchpoints in `storage/governance/` and `storage/security/`.
4. **Decision logging**
   - Create or update an ADR under `docs/project_planning/` or `docs/development/` with context → decision → consequences.
   - Record diagram IDs and KG aliases in `docs/development/mmd-diagram-usage.md` and `docs/development/kg-mcp-usage.md` when modified.
5. **Implementation gates**
   - Schedule peer review for contracts and diagrams before code merges.
   - Ensure testing plans align with `testing-requirements.instructions.md` and WARD suites.

## Decision Record Requirements

- State the triggering change, alternatives considered, and why rejected.
- Link to updated contracts, services, and tests.
- Capture compliance assessment (E2EE, data locality, retention, auditability).
- Note rollback strategy and blast radius controls.
- Reference KG diagram IDs and pipeline stages touched.

## Compliance & Risk Checks

- **Data residency**: Confirm tier placement (`storage/tiering/`, `storage/vector_indexes/`).
- **Security posture**: Verify key management, redaction, and DSM flows (`storage/security/`, `data/pii_*`).
- **Operational limits**: Respect QoS budgets (`data/cache/qos_*`, `storage/governance/qos`), idempotency ledgers, and DLQ capacity.
- **Audit & observability**: Update logging stores (`storage/events/events_wal.py`, `storage/events/events_outbox.py`, `storage/events/events_dlq.py`).
- **Backpressure**: Review `data/cache/backpressure_events.db` and policies before adding high-volume edges.

## Tooling Reference

- Mermaid MCP (`mmd_*`) for diagram ingestion, validation, and summaries.
- Knowledge Graph MCP (`kg_*`) for dependency tracing and impact analysis.
- Memory MCP (`mem_*`) for logging investigations or architectural notes.
- Ward test runner for integration suites (`python -m ward test --path Tests/storage`).

## Governance Checklist

- [ ] Diagram + KG context reviewed; impacts mapped.
- [ ] Contracts updated first with manifests/examples.
- [ ] Event hub and pipeline integrations confirmed.
- [ ] Compliance and safety assessments recorded.
- [ ] ADR or design note committed with references.
- [ ] Tests planned/executed per zero-simulation policy.
- [ ] Copilot instruction index updated if new patterns emerge.
