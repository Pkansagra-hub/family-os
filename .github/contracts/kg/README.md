# Knowledge Graph v2 Contracts

**Version:** 2.0.0
**Status:** ACTIVE
**Last Updated:** 2025-10-23

---

## Overview

Contract definitions for the Knowledge Graph v2 MCP server. These contracts define:

1. **Node Schema** - Semantic nodes (ADRs, modules, contracts, files)
2. **Edge Schema** - Relations between nodes (implements, depends_on, references, tests)
3. **OpenAPI Spec** - 15 MCP tool interfaces

---

## Files

| File | Purpose | Status |
|------|---------|--------|
| `node.schema.json` | Node data model | ✅ Validated |
| `edge.schema.json` | Edge data model | ✅ Validated |
| `kg_tools.openapi.yaml` | MCP tool API specs | ✅ Validated |

---

## Node Types

| Type | Description | Example ID |
|------|-------------|------------|
| `adr` | Architecture Decision Record | `adr_0051` |
| `module` | Python module/file | `k0.kernel.core` |
| `contract` | OpenAPI/AsyncAPI/JSON Schema | `agent_schedule.schema.json` |
| `file` | Generic file | `readme.md` |

---

## Relation Types

| Relation | Description | Example |
|----------|-------------|---------|
| `implements` | Code implements ADR | `agent_scheduler.py` → `adr_0051` |
| `depends_on` | Module dependency | `agent_scheduler` → `k0.kernel` |
| `references` | Cross-reference | `adr_0051` → `adr_0050` |
| `tests` | Test coverage | `test_scheduler.py` → `agent_scheduler` |

---

## MCP Tools (15 Total)

### Core Operations (4 tools)
- `kg_search` - Full-text search
- `kg_neighbors` - Get adjacent nodes
- `kg_add_node` - Create/update node
- `kg_add_edge` - Create edge

### Queries (3 tools)
- `kg_find_by_type` - Find nodes by type
- `kg_graph_summary` - Statistics
- `kg_paths` - Find paths between nodes

### Dependency Analysis (3 tools)
- `kg_get_module_deps` - Module dependencies
- `kg_dependency_impact` - Impact analysis
- `kg_find_circular_deps` - Circular deps

### AI Context (3 tools)
- `kg_implementation_chain` - ADR → code chain
- `kg_get_feature_context` - Feature context
- `kg_ask` - Natural language queries

### Diagnostics (2 tools)
- `kg_diagnostics` - Architecture health checks

---

## Validation

All schemas pass validation:

```bash
python k0/automation/lint_schemas.py \
  --schema-dir .github/contracts/kg/ \
  --openapi .github/contracts/kg/kg_tools.openapi.yaml
```

Output: `[SchemaLint] All schemas and contract documents validated successfully.`

---

## Usage Examples

### Node Example
```json
{
  "node_id": "adr_0051",
  "node_type": "adr",
  "label": "Agent Scheduling",
  "file_path": "docs/architecture/decisions/0051-agent-scheduling.md",
  "tags": ["scheduling", "agents"],
  "content_preview": "ADR-0051: Agent Scheduling. This ADR describes...",
  "created_at": 1729700000,
  "indexed_at": 1729700000
}
```

### Edge Example
```json
{
  "src": "k1.l2_orchestration.agent_scheduler",
  "dst": "adr_0051",
  "relation": "implements",
  "evidence": "agent_scheduler.py:line 1 (docstring: 'Implements ADR-0051')"
}
```

---

## Contract Guarantees

1. **Schema Validation** - All nodes/edges validated against JSON schemas
2. **Type Safety** - Only 4 node types, 4 relation types allowed
3. **Referential Integrity** - Edges reference existing nodes (enforced by SQLite FK)
4. **Performance** - All queries < 100ms (enforced by tests)
5. **Backward Compatibility** - Additive changes only

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0.0 | 2025-10-23 | Initial v2 contracts (clean-slate from v1) |

---

## Related Documents

- **Implementation Plan:** `.github/epics/kg-v2-implementation-plan.md`
- **ADR:** `.github/architecture/0088-knowledge-graph-v2-architecture.md`
- **Store Implementation:** `.github/mcp/kg_store.py` (to be created)
- **MCP Server:** `.github/mcp/kg_v2_server.py` (to be created)
