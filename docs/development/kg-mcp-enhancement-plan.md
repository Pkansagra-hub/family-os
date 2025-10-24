# KG-MCP Semantic Enhancement - Epic & Issues

**Epic ID:** KG-MCP-E001
**Status:** PROPOSED
**Related ADR:** ADR-0087
**Created:** 2025-10-23

---

## Epic Overview

### Goal
Enable AI agents to query repository architecture comprehensively — understanding the full chain from ADRs → contracts → code → tests with single function calls.

### Success Criteria
- ✅ AI agent can ask "give me context for feature X" and get complete answer
- ✅ KG knows which code implements which ADRs
- ✅ Module dependency graph is queryable
- ✅ All queries complete in <100ms
- ✅ Backward compatible with existing Mermaid workflows
- ✅ 90%+ test coverage for new code

### Timeline
- **Phase 1 (P0):** Oct 23 - Nov 6 (Weeks 1-2)
- **Phase 2 (P0):** Nov 6 - Nov 20 (Weeks 2-3)
- **Phase 3 (P1):** Nov 20 - Dec 4 (Week 4)
- **Phase 4 (P1):** Dec 4 - Dec 18 (Week 5)
- **Phase 5 (P2):** Dec 18 - Jan 1 (Week 6)

### Budget: ~80-100 hours total

---

## Phase 1: Semantic Foundation (P0, 2 weeks)

### Goal
Establish semantic type system and extend node model for repository awareness.

### Issues

#### Issue KG-1.1: Add Semantic Node Type System
**Type:** Feature
**Effort:** 8 hours
**Owner:** TBD

**Description:**
Extend `KnowledgeGraphStore` to support typed nodes with semantic tagging.

**What it does:**
- Adds `node_type` field: "adr", "module", "file", "contract", "layer", "pattern", "decision"
- Adds `semantic_tags`: List of tags for classification
- Adds `metadata`: Rich dict for storing node-specific info
- Adds `created_by`: Tracks who/what created the node

**Acceptance Criteria:**
- [ ] Node schema updated to include all fields
- [ ] Migrations handle existing nodes (backward compatible)
- [ ] Tests verify all node types can be stored/retrieved
- [ ] Performance: <10ms per node operation

**Files to Modify:**
- `kg_mcp_server.py` — Add fields to node schema
- Tests — New test class `TestSemanticNodes`

**Code Sketch:**
```python
@dataclass
class SemanticNode:
    id: str
    node_type: str  # "adr", "module", etc.
    label: str
    semantic_tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_by: str = "system"
    file_path: Optional[str] = None
    source_code_snippet: Optional[str] = None
    created_at: float = field(default_factory=time.time)
```

---

#### Issue KG-1.2: Add Semantic Relation Types
**Type:** Feature
**Effort:** 6 hours
**Owner:** TBD

**Description:**
Extend edge model to support typed relations with meaning.

**What it does:**
- Adds `relation_type`: "implements", "depends_on", "tests", "documents", etc.
- Adds `strength`: confidence level (0.0-1.0)
- Adds `evidence`: why this relation exists (file reference, code line, etc.)

**Acceptance Criteria:**
- [ ] Edge schema updated
- [ ] RELATION_TYPES enum documented
- [ ] Tests verify all relation types
- [ ] Queries can filter by relation type

**Files to Modify:**
- `kg_mcp_server.py` — Update `_merge_edges`, edge schema
- Documentation — List of valid relation types

**Code Sketch:**
```python
SEMANTIC_RELATIONS = {
    "implements": "Code implements ADR",
    "depends_on": "Module depends on another",
    "tests": "Test covers functionality",
    "documents": "Documents component",
    "requires": "Requires contract",
    "violates": "Violates pattern",
    "contradicts": "Contradicts decision",
    "mitigates": "Mitigates risk",
}

# Edge now includes:
{
    "src": "agent_scheduler",
    "dst": "adr_0051",
    "relation_type": "implements",
    "strength": 0.95,
    "evidence": "k1/l2_orchestration/agent_scheduler.py:42"
}
```

---

#### Issue KG-1.3: Implement ADR Indexer
**Type:** Feature
**Effort:** 12 hours
**Owner:** TBD

**Description:**
Create indexer that scans `docs/architecture/decisions/` and creates semantic KG nodes.

**What it does:**
- Parses ADR files (extract status, relations, related ADRs)
- Creates semantic nodes for each ADR
- Links related ADRs
- Extracts front-matter metadata

**Acceptance Criteria:**
- [ ] ADRIndexer class created
- [ ] Scans all .md files in decisions/
- [ ] Extracts: title, status, problem, decision, consequences
- [ ] Links cross-referenced ADRs
- [ ] Creates nodes with type="adr"
- [ ] Tests verify parsing of sample ADRs
- [ ] Performance: <500ms for full directory

**Files to Create:**
- `kg_indexers.py` — New module with indexer classes
- `tests/test_kg_adr_indexer.py` — Unit + integration tests

**Example Flow:**
```
docs/architecture/decisions/0051-agent-scheduling.md
  ↓ ADRIndexer.ingest_directory()
  ↓ Parse YAML front-matter
  ↓ Extract links to ADR-0050, ADR-0052
  ↓ Create KG nodes:
    - Node: "adr_0051" (type: adr, semantic_tags: ["scheduling", "agents"])
    - Edge: adr_0051 --related_to--> adr_0050
    - Edge: adr_0051 --related_to--> adr_0052
```

**Tools/Scripts:**
```bash
python kg_indexers.py ingest_adrs docs/architecture/decisions/
# Output: Ingested 50 ADRs, created 50 nodes, 120 relations
```

---

#### Issue KG-1.4: Add MCP Tools for Semantic Queries
**Type:** Feature
**Effort:** 8 hours
**Owner:** TBD

**Description:**
Add MCP tools to query by node type and semantic tags.

**What it does:**
- `kg_find_by_type()` — Find all nodes of a type
- `kg_find_by_tags()` — Find nodes with semantic tags
- `kg_find_adr_by_status()` — Find ADRs by status
- `kg_get_related_adr()` — Find related ADRs

**Acceptance Criteria:**
- [ ] All 4 tools implemented
- [ ] Tools return paginated results
- [ ] Tests verify correctness
- [ ] Performance: <50ms per query

**Files to Modify:**
- `kg_mcp_server.py` — Add @mcp.tool() functions

---

#### Issue KG-1.5: Write Phase 1 Tests & Documentation
**Type:** QA + Docs
**Effort:** 8 hours
**Owner:** TBD

**Description:**
Comprehensive tests and usage guide for Phase 1.

**Acceptance Criteria:**
- [ ] 90%+ code coverage for semantic modules
- [ ] All edge cases tested
- [ ] README updated with new capabilities
- [ ] Example notebook showing usage
- [ ] Performance benchmarks documented

**Files to Create:**
- `tests/kg_semantic_test.py` — Integration tests
- `docs/kg_semantic_usage.md` — User guide

---

### Phase 1 Summary
- **Total Effort:** 42 hours
- **Risk Level:** LOW (extends existing, backward compatible)
- **Dependencies:** None
- **Deliverables:**
  - ✅ Semantic type system
  - ✅ ADR indexer + MCP tools
  - ✅ Full test coverage
  - ✅ Documentation

---

## Phase 2: Repository Indexing (P0, 2 weeks)

### Goal
Index K0/K1 modules, files, and contracts. Build complete dependency graph.

### Issues

#### Issue KG-2.1: Implement Module Indexer
**Type:** Feature
**Effort:** 14 hours
**Owner:** TBD

**Description:**
Scan `k0/` and `k1/` directories, create nodes for modules and extract dependencies.

**What it does:**
- Walks module hierarchy
- Creates semantic nodes for packages/modules
- Parses Python imports to build dependency graph
- Links to contracts
- Extracts docstrings for context

**Acceptance Criteria:**
- [ ] ModuleIndexer class created
- [ ] Scans k0/ and k1/ recursively
- [ ] Creates nodes for each module
- [ ] Extracts import dependencies
- [ ] Performance: <2 seconds for k0/ + k1/
- [ ] 90%+ accuracy on dependency detection

**Files to Create:**
- `kg_indexers.py` — Add ModuleIndexer class
- `tests/test_kg_module_indexer.py`

**Example Output:**
```
k0/kernel/core.py
  ↓ ModuleIndexer.ingest_module()
  ↓ Create nodes:
    - Node: "k0.kernel" (type: module)
    - Node: "k0.kernel.core" (type: file)
  ↓ Parse imports:
    - Edge: k0.kernel.core --depends_on--> k0.bus
    - Edge: k0.kernel.core --depends_on--> k0.storage
    - Edge: k0.kernel.core --implements--> adr_0001
```

---

#### Issue KG-2.2: Implement Contract Indexer
**Type:** Feature
**Effort:** 10 hours
**Owner:** TBD

**Description:**
Index OpenAPI specs and JSON schemas in contracts.

**What it does:**
- Scans `k0/contracts/` and `k1/contracts/`
- Creates nodes for each contract
- Extracts schema definitions
- Links to implementing modules

**Acceptance Criteria:**
- [ ] ContractIndexer created
- [ ] Parses OpenAPI 3.0 specs
- [ ] Parses JSON Schema files
- [ ] Creates contract nodes
- [ ] Performance: <1 second for all contracts

**Files to Create:**
- `kg_indexers.py` — Add ContractIndexer
- Tests

---

#### Issue KG-2.3: Build Dependency Graph Engine
**Type:** Feature
**Effort:** 12 hours
**Owner:** TBD

**Description:**
Create query engine for module dependencies.

**What it does:**
- Builds transitive dependency map
- Detects circular dependencies
- Computes dependency depth
- Answers "what would break if I change X?"

**Acceptance Criteria:**
- [ ] DependencyGraphEngine class
- [ ] Detects all dependency types
- [ ] Finds circular deps
- [ ] Performance: <100ms for deep queries

**Files to Create:**
- `kg_dependency_engine.py` — New module

---

#### Issue KG-2.4: Add MCP Tools for Repository Queries
**Type:** Feature
**Effort:** 10 hours
**Owner:** TBD

**Description:**
MCP tools for module/dependency queries.

**What it does:**
- `kg_get_module_deps()` — All dependencies
- `kg_get_dependents()` — What depends on this
- `kg_find_circular_deps()` — Detect cycles
- `kg_trace_import_chain()` — Show full import path

**Acceptance Criteria:**
- [ ] All 4 tools implemented
- [ ] <50ms performance
- [ ] Full test coverage

---

#### Issue KG-2.5: Phase 2 Tests & Documentation
**Type:** QA + Docs
**Effort:** 10 hours
**Owner:** TBD

**Files to Create:**
- Comprehensive test suite
- Usage guide
- Performance benchmarks

---

### Phase 2 Summary
- **Total Effort:** 56 hours
- **Risk Level:** MEDIUM (dependency parsing is complex)
- **Dependencies:** Phase 1 must be complete
- **Deliverables:**
  - ✅ Module indexer
  - ✅ Contract indexer
  - ✅ Dependency graph engine
  - ✅ MCP tools for queries

---

## Phase 3: AI Query Tools (P1, 1 week)

### Goal
Implement high-level queries that AI agents will actually use.

### Issues

#### Issue KG-3.1: Implement `kg_implementation_chain()` Tool
**Type:** Feature
**Effort:** 8 hours

**Description:**
Given an ADR, return everything needed to implement it.

**Returns:**
```python
{
    "adr": {"id": "adr_0051", "status": "ACCEPTED", ...},
    "contracts": [
        {"name": "agent_schedule.schema.json", "path": "..."}
    ],
    "modules": [
        {"name": "k1.l2_orchestration.agent_scheduler", "path": "..."}
    ],
    "files": ["agent_scheduler.py", "..."],
    "tests": ["test_agent_scheduler.py"],
    "related_adr": ["adr_0050", "adr_0052"],
    "patterns": ["state_machine", "actor_model"]
}
```

---

#### Issue KG-3.2: Implement `kg_dependency_impact()` Tool
**Type:** Feature
**Effort:** 8 hours

**Description:**
What breaks if I change this module?

**Returns:**
```python
{
    "module": "k0.kernel",
    "direct_dependents": ["k0.bus", "k1.orchestrator"],
    "transitive_dependents": [... all modules that depend transitively ...],
    "affected_tests": ["test_kernel.py", "test_integration.py"],
    "affected_contracts": ["kernel_api.yaml"],
    "breaking_changes": [...],
    "migration_effort": "HIGH"
}
```

---

#### Issue KG-3.3: Implement `kg_get_feature_context()` Tool
**Type:** Feature
**Effort:** 10 hours

**Description:**
Given a feature name, return everything an AI agent needs to implement it.

**Returns:**
```python
{
    "matching_adrs": [list of relevant ADRs],
    "similar_features": [existing implementations as reference],
    "required_contracts": [contracts to implement],
    "suggested_layer": "l2_orchestration",
    "test_template": "example test code",
    "performance_budget": {"p95_ms": 50},
    "related_modules": [modules to study],
    "quick_start": "Start by reading ADR-0051..."
}
```

---

#### Issue KG-3.4: Phase 3 Tests & Documentation
**Type:** QA + Docs
**Effort:** 6 hours

---

### Phase 3 Summary
- **Total Effort:** 32 hours
- **Dependencies:** Phase 2 complete
- **Deliverables:** 3 powerful AI-centric tools

---

## Phase 4: Context Extraction (P1, 1 week)

### Goal
AI agents ask one question, get complete answer with rationale.

### Issues

#### Issue KG-4.1: Implement AIContextBuilder
**Type:** Feature
**Effort:** 12 hours

**Description:**
Central class that builds optimal context for any development task.

**Methods:**
- `build_feature_context(feature_name)` → Full context for implementing feature
- `build_error_context(error_type)` → How to fix this error
- `build_module_context(module_name)` → Everything about a module
- `build_refactor_context(old_module, new_module)` → Safe refactoring guide

---

#### Issue KG-4.2: Implement `kg_ask()` Natural Language Tool
**Type:** Feature
**Effort:** 10 hours

**Description:**
"Natural language" queries that map to underlying tools.

**Examples:**
- `kg_ask("how do I add agent health monitoring?")` → `get_feature_context()`
- `kg_ask("what implements ADR-0051?")` → `implementation_chain()`
- `kg_ask("what breaks if I modify agent_scheduler?")` → `dependency_impact()`

---

#### Issue KG-4.3: Phase 4 Tests & Documentation
**Type:** QA + Docs
**Effort:** 8 hours

---

### Phase 4 Summary
- **Total Effort:** 30 hours
- **Deliverables:** Context builder + natural language queries

---

## Phase 5: Advanced Analytics (P2, 1 week)

### Goal
Governance, diagnostics, and advanced queries.

### Issues

#### Issue KG-5.1: Implement Impact Analysis
**Type:** Feature
**Effort:** 10 hours

**Description:**
ADR change → what code breaks?

---

#### Issue KG-5.2: Implement Architecture Diagnostics
**Type:** Feature
**Effort:** 8 hours

**Description:**
Find unmaintained modules, orphaned code, etc.

---

#### Issue KG-5.3: Phase 5 Tests & Documentation
**Type:** QA + Docs
**Effort:** 6 hours

---

### Phase 5 Summary
- **Total Effort:** 24 hours

---

## Total Epic Summary

| Phase | Focus | Hours | Risk | Status |
|-------|-------|-------|------|--------|
| **1** | Semantic foundation | 42 | LOW | PROPOSED |
| **2** | Repository indexing | 56 | MEDIUM | PROPOSED |
| **3** | AI query tools | 32 | LOW | PROPOSED |
| **4** | Context extraction | 30 | LOW | PROPOSED |
| **5** | Advanced analytics | 24 | LOW | PROPOSED |
| **TOTAL** | | **184 hours** | | |

---

## Success Metrics

- [ ] Phase 1: All semantic tests passing, 90%+ coverage
- [ ] Phase 2: 100% of k0/k1 modules indexed, dependency accuracy >95%
- [ ] Phase 3: AI tools working with <50ms latency
- [ ] Phase 4: Natural language queries understood
- [ ] Phase 5: Diagnostics identifying real architecture issues

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Dependency detection errors | Extensive testing, fallback to manual verification |
| Performance degradation | Caching, lazy loading, BFS optimization |
| Index drift | Validation tools, re-indexing on demand |
| Complexity explosion | Clear separation of concerns, modular design |

---

## Dependencies & Integration

- **Requires:** Python 3.8+, existing KG infrastructure
- **Integrates with:** Memory MCP, existing KG tools
- **Enables:** AI agent autonomous development
- **Backward compatible:** YES (existing Mermaid workflows untouched)

---

## Questions for Team

1. Should we stage deployment (P0 first, then P1/P2)?
2. Is 184 hours effort realistic for sprint planning?
3. Which team members should own which phases?
4. Should we add continuous indexing or on-demand indexing?
5. Performance SLA acceptable at <50ms per query?
