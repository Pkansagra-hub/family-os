---
description: MCP workflow for ingesting and analyzing Mermaid architecture diagrams.
applyTo: "**/*"
---

# 🧠 Mermaid MCP Usage & Workflow

## Purpose

Enable rapid architecture analysis by ingesting system-level and component-level diagrams into the MCP graph store, with repeatable commands for validation, exploration, and code scaffolding.

## Prerequisites

- Python environment with `mmd_mcp_server.py` registered as MCP server
- Diagrams stored in:
  - System-level: `architecture_diagrams/k0/` or `architecture_diagrams/k1/`
  - Component-level: `docs/architecture/diagrams/k0/`, `docs/architecture/diagrams/k1/`, or `docs/architecture/diagrams/services/`
- SQLite write permissions for MCP database (`%USERPROFILE%/.mcp_mmd/mmd.db`)

## Workflow

### Step 1: Ingest Diagram
```bash
# System-level diagram (e.g., K1 agent fabric)
mmd_ingest("d:/familyos/architecture_diagrams/k1/k1_complete_with_flows.mmd")

# Component-level diagram (e.g., agent lifecycle)
mmd_ingest("d:/familyos/docs/architecture/diagrams/k1/agent_lifecycle.mmd")

# With optional alias for easier reference
mmd_ingest("d:/familyos/docs/architecture/diagrams/k1/agent_lifecycle.mmd", alias="k1_agent_lifecycle")
```

**Returns:**
- `diagram_id`: Persistent identifier (e.g., `1628ac12-2785-40d0-a992-bd3c986afdca`)
- Node count, edge count
- Resolved include paths (if using Mermaid `!include`)

### Step 2: Validate Structure
```bash
# Check for syntax errors, dangling edges, duplicate links
mmd_validate("diagram_id_or_alias")

# Get high-level stats and structure
mmd_summary("diagram_id_or_alias")

# Expected output: node types, role distribution, top hubs, subgraph depth
```

### Step 3: Explore & Analyze
```bash
# Full graph structure
mmd_graph("diagram_id_or_alias")

# Adjacent nodes (outgoing/incoming/both)
mmd_neighbors("diagram_id_or_alias", "node_id", direction="both")

# Find paths between nodes
mmd_paths("diagram_id_or_alias", "src_node", "dst_node", max_hops=6, max_paths=5)

# Get code scaffolding hints
mmd_code_hints("diagram_id_or_alias", "node_id")
```

### Step 4: Record & Link
```bash
# Add to usage documentation
# File: docs/development/mmd-diagram-usage.md

- **Diagram**: k1_agent_lifecycle
- **Path**: docs/architecture/diagrams/k1/agent_lifecycle.mmd
- **Diagram ID**: 1628ac12-2785-40d0-a992-bd3c986afdca
- **Node Count**: 8
- **Edge Count**: 12
- **Purpose**: Agent lifecycle state machine (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
- **Related ADRs**: ADR-0005, ADR-0086
```

### Step 5: Integrate into 5-Step Workflow
- **GATE 1 (ADR Discovery)**: Reference diagram ID in ADR decision
- **GATE 3 (Implementation)**: Update diagram labels as implementation progresses
- **GATE 5 (Memory)**: Record diagram changes in memory entry with `mem_link` to ADRs

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `diagram_not_found` | Check diagram ID/alias is correct; re-ingest if diagram was moved |
| `mmd_validate` fails | Check for special characters, duplicate node IDs, unclosed quotes; validate with `mmd_validate()` again |
| Dangling edges | Verify all target node IDs exist; check spelling in edges |
| Permission errors | Clear locks on SQLite database (`%USERPROFILE%/.mcp_mmd/mmd.db`); re-run ingestion |
| Stale graph data | Re-ingest: `mmd_ingest("<absolute_path>")` overwrites prior version by path |
| Path-relative includes fail | Use absolute paths in ingest calls; check include file exists at relative location |

## Quick Reference

### Common Commands
```python
# List all ingested diagrams
mmd_list()

# Ingest with validation
mmd_ingest("<absolute_path>")
mmd_validate("<diagram_id>")
mmd_summary("<diagram_id>")

# Navigation
mmd_neighbors("<diagram_id>", "<node_id>", direction="both")
mmd_paths("<diagram_id>", "<src>", "<dst>", max_hops=6, max_paths=5)
mmd_graph("<diagram_id>")

# Scaffolding
mmd_code_hints("<diagram_id>", "<node_id>")

# Cleanup (if needed)
mmd_delete("<diagram_id>")  # Remove from MCP store
```

### Best Practices
- ✅ Use absolute paths: `d:/familyos/docs/architecture/diagrams/k1/...`
- ✅ Validate after ingest: `mmd_validate(diagram_id)`
- ✅ Record diagram IDs in `docs/development/mmd-diagram-usage.md`
- ✅ Link diagrams to ADRs in memory entries
- ✅ Keep system and component diagrams separate
- ❌ Don't use relative paths in ingest calls
- ❌ Don't skip validation before committing changes
- ❌ Don't forget to update usage documentation

## Integration with 5-Step Workflow

### GATE 1: ADR Discovery
- Reference diagram in ADR if architecture change affects component relationships
- Example comment in ADR: `See architecture_diagrams/k1/k1_agent_lifecycle.mmd`

### GATE 3: Implementation
- Update diagram labels to match actual implementation (ports, topics, pipeline IDs)
- Add nodes/edges for new components
- Validate with `mmd_validate()`

### GATE 5: Memory Documentation
```python
# Record diagram usage in memory
mem_write(
    project="k1_intelligence",
    title="K1 Agent Lifecycle Diagram Ingested",
    content="""
    Ingested diagram: k1_agent_lifecycle
    Diagram ID: 1628ac12-2785-40d0-a992-bd3c986afdca
    Path: docs/architecture/diagrams/k1/agent_lifecycle.mmd
    Nodes: 8, Edges: 12
    Related ADRs: ADR-0005, ADR-0086
    Purpose: Document agent state machine transitions
    """,
    tags=["k1_agent_fabric", "architecture", "diagram"]
)

# Link to related memories
mem_link(memory_id, adr_memory_id, relation="references")
mem_link(memory_id, implementation_memory_id, relation="documents")
```

## References

- MCP Server: `mmd_mcp_server.py`
- Copilot Guidance: `.github/copilot-instructions.md` (Section 5: "Playbooks - Mermaid Diagrams")
- Diagram Standards: `.github/instructions/mmd-diagrams.instructions.md`
- 5-Step Workflow: `.github/instructions/service-design.instructions.md`
- Usage Log: `docs/development/mmd-diagram-usage.md`
