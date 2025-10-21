# Mermaid Diagram MCP Usage

## Purpose

Provide a repeatable flow for ingesting FamilyOS architecture diagrams into the Mermaid MCP server and retrieving actionable summaries for development tasks.

## Prerequisites

- Python environment with the `mmd_mcp_server.py` registered as an MCP server.
- Access to archived diagrams under `architecture_diagrams/_archive/`.
- SQLite write permissions for the default MCP database (`%USERPROFILE%/.mcp_mmd/mmd.db`).

## Workflow

1. **Ingest a diagram**
   - Use the `mmd_ingest` tool with the absolute path to the `.mmd` file.
   - Example: `mmd_ingest("d:/FamilyOS_POC/architecture_diagrams/_archive/2025-09-24/project_architecture_part1.mmd")`.
   - The tool returns a persistent `diagram_id`, node/edge counts, and resolved include paths.
2. **Validate structure**
   - Run `mmd_validate(diagram_id)` to surface dangling edges or duplicates.
   - Pair with `mmd_summary(diagram_id)` for top hubs, role counts, and subgraph depth.
3. **Retrieve context**
   - Call the prompt `diagram.context(diagram_id)` for a compact overview (counts, hubs, and usage notes).
   - Use the new prompt `diagram.flows(diagram_id)` for highlighted flows; add `src`/`dst` parameters to trace a specific path.
4. **Dive deeper**
   - `mmd_neighbors(diagram_id, node)` exposes adjacency for contract analysis.
   - `mmd_paths(diagram_id, src, dst)` enumerates routes between two nodes (mirrored inside `diagram.flows`).
   - `code_hints(diagram_id, node)` suggests scaffolding folders and testing patterns based on node roles.

## Troubleshooting

- **`diagram_not_found`**: ensure the ingest path matches the stored diagram or reuse the exact `diagram_id`.
- **Permission errors**: clear locks on the MCP SQLite database and re-run ingestion.
- **Stale graphs**: re-run `mmd_ingest` after editing a diagram; the server replaces prior versions by path.

## References

- Server implementation: `mmd_mcp_server.py`
- Copilot guidance: `.github/copilot-instructions.md` (see "Mermaid MCP Playbook")
- Ingested diagram example: `1628ac12-2785-40d0-a992-bd3c986afdca` (Diagram D1)
