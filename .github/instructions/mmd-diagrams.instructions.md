---
description: Guidance for editing and ingesting Mermaid architecture diagrams.
applyTo: "architecture_diagrams/**/*.mmd"
---

# 🧠 Mermaid Diagram Expectations

## 1) Contracts First

- Every node/edge must map to an existing contract or tracked TODO in `contracts/`.
- Keep labels specific (include ports, topics, pipeline IDs) to ease event tracing.

## 2) Editing Workflow

1. Update the `.mmd` source alongside any related contract or code change.
2. Regenerate rendered assets in `architecture_diagrams/renders/` if the diagram feeds documentation.
3. Re-ingest the file with `mmd_ingest(<abs_path>)` so the MCP graph stays current.
4. Record the new `diagram_id` and counts in `docs/development/mmd-diagram-usage.md`.

## 3) Validation

- Run `mmd_validate` after edits; resolve dangling edges and duplicate links immediately.
- Use `diagram.context` + `diagram.flows` to confirm the narrative and major routes are intact.

## 4) Review Checklist

- ✅ Node/edge names align with code modules or contracts.
- ✅ Pipeline references (P01–P20) are annotated where data crosses tiers.
- ✅ Family permissions, safety, and QoS gates are represented in new flows.
- ✅ SSE and events topics include `cognitive_trace_id` when applicable.
