# Knowledge Graph Instructions

## Purpose

Ensure consistent use of the Knowledge Graph MCP server so architectural context, dependencies, and annotations stay synchronized with Mermaid diagrams and implementation work.

## Store & Entry Points

- Server: `kg_mcp_server.py`
- Default store path: `%USERPROFILE%/.mcp_kg/kg_store.json` (override with `KG_STORE_PATH`).
- Diagram sources: `architecture_diagrams/` and archived snapshots under `_archive/`.
- Manual notes: persisted via `kg_add_memory` (`origin="manual"`).

## Core Workflow

1. **Ingest or refresh diagrams**
   - `kg_ingest(path, alias)` for Mermaid files; aliases should mirror diagram filenames (e.g., `d1_storage_backbone`).
   - Re-ingest after diagram updates; manual nodes/edges persist.
2. **Validate structure**
   - `kg_summary` for counts + hub overview.
   - `kg_graph` to inspect raw nodes/edges when debugging.
3. **Annotate architecture knowledge**
   - `kg_add_node` / `kg_add_edge` for missing components or manual relations.
   - `kg_add_memory` to capture design rationale, runbooks, or TODOs.
   - Record new aliases/notes in `docs/development/kg-mcp-usage.md` alongside timestamps.
4. **Trace dependencies**
   - `kg_neighbors(diagram, node_id, direction?)` for adjacency.
   - `kg_paths(diagram, src, dst, max_hops)` for pathfinding across bus/pipeline flows.
   - `kg_search(term)` to locate services, storage, or policies by name.
5. **Leverage during design**
   - Combine with `service-design.instructions.md` and `architecture-governance.instructions.md` to justify scope.
   - Export insights into ADRs or README updates as part of the same change.

## Governance & Hygiene

- Keep aliases unique and descriptive; reuse existing ones whenever possible.
- Remove deprecated nodes/edges when services retire (`kg_remove_*`).
- Sync diagram IDs and notable discoveries into `docs/development/mmd-diagram-usage.md` and ADRs.
- Back up the KG store before large batch edits; commit sanitized snapshots when necessary.

## Testing & Verification

- Run WARD suites touching the KG server after code changes: `python -m ward test --path Tests/kg/test_kg_mcp_store.py`.
- Confirm manual artifacts remain after ingestion cycles.
- Validate path queries for new topology adjustments as part of PR review.

## Checklist

- [ ] Diagram ingested/refreshed with alias recorded.
- [ ] Manual annotations/nodes added for new components.
- [ ] Dependencies traced via neighbors/paths during design.
- [ ] Findings logged in docs (usage log, ADR, or README).
- [ ] Ward KG tests executed when server/store changes occur.
