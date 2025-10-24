# ADR 0053: Knowledge Graph MCP Semantic Enhancement for AI Agent Enablement

**Status:** PROPOSED
**Date:** 2025-10-23
**Author:** K1 Intelligence Team
**Related ADRs:** ADR-0001 (Architecture), ADR-0010 (Contracts), ADR-0051 (Agent Scheduling)

---

## Problem

Current KG MCP server (`kg_mcp_server.py`) is **diagram-centric** — excellent for Mermaid visualization but **insufficient for AI agent development workflows**.

### Current Limitations

1. **No Repository Awareness**
   - Doesn't know where code lives
   - Can't link ADRs to implementations
   - No file system mapping

2. **No ADR Linking**
   - ADRs are isolated documents
   - No way to query "which code implements ADR-0051?"
   - No way to ask "which ADRs affect this module?"

3. **No Dependency Tracking**
   - No understanding of module dependencies
   - Can't answer "what breaks if I change this?"
   - No impact analysis capability

4. **No Semantic Understanding**
   - Nodes are generic (no type system)
   - Can't distinguish modules from files from ADRs
   - No semantic tagging

5. **AI Agent Inefficiency**
   - Agents can't ask "give me all context for feature X"
   - No cross-reference queries
   - Requires manual context gathering
   - Slow onboarding for AI-assisted development

### Impact on AI Agents

**Current:** AI agent must manually search repo → read ADRs → find contracts → locate code
**Desired:** AI agent calls single tool → gets complete, interconnected context

---

## Alternatives Considered

### 1. **No Change (Do Nothing)**
- ❌ KG remains visualization-only tool
- ❌ AI agents stay inefficient
- ❌ Misses opportunity to leverage existing graph infrastructure

### 2. **Build Separate AI Context Layer**
- ❌ Duplicates graph storage
- ❌ Maintains separate sync/indexes
- ❌ More complex than enhancing existing KG

### 3. **Replace with Graph Database (Neo4j)**
- ❌ Adds operational complexity
- ❌ Requires deployment/licensing
- ❌ Overkill for repository scale
- ❌ JSON storage sufficient for now

### 4. **Enhance Existing KG with Semantic Layers** ✅
- ✅ Reuses proven persistence model
- ✅ Backward compatible (Mermaid still works)
- ✅ Minimal operational overhead
- ✅ Directly enables AI agent workflows
- ✅ Can be staged (P0, P1, P2 priorities)

---

## Decision

**Implement phased semantic enhancement to KG MCP server**, progressively adding:

1. **Phase 1 (P0):** Semantic node types + ADR indexing
2. **Phase 2 (P0):** Module dependency mapping
3. **Phase 3 (P1):** AI-focused query tools
4. **Phase 4 (P1):** Context extraction for tasks
5. **Phase 5 (P2):** Impact analysis & diagnostics

### Architecture Approach

```
┌─────────────────────────────────────────────────────────┐
│ Current KG (Diagram-Centric)                            │
├─────────────────────────────────────────────────────────┤
│  - Mermaid parsing                                      │
│  - Node/edge management                                 │
│  - Path finding                                         │
│  - Search (basic)                                       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Enhanced KG (Repository-Aware + Semantic)               │
├─────────────────────────────────────────────────────────┤
│ [Diagram-Centric Layer (unchanged)]                    │
│ + [Repository Indexing Layer] (NEW)                    │
│   - ADR indexer                                         │
│   - Module indexer                                      │
│   - Contract indexer                                    │
│   - Dependency graph                                    │
│ + [Semantic Layer] (NEW)                               │
│   - Node types (adr, module, file, contract, etc.)     │
│   - Relation types (implements, depends_on, etc.)      │
│   - Metadata & annotations                             │
│ + [AI Query API] (NEW)                                 │
│   - Context extraction                                 │
│   - Impact analysis                                    │
│   - Implementation chains                              │
└─────────────────────────────────────────────────────────┘
```

### Benefits

| Capability | Current | Enhanced | Impact |
|-----------|---------|----------|--------|
| Mermaid visualization | ✅ | ✅ | Backward compatible |
| ADR discovery | ❌ | ✅ | AI agents find decisions |
| Code ↔ ADR linking | ❌ | ✅ | Understand "why" |
| Dependency tracking | ❌ | ✅ | Impact analysis |
| Context for tasks | ❌ | ✅ | 10x AI agent efficiency |
| Impact analysis | ❌ | ✅ | Safe refactoring |

---

## Consequences

### Positive

✅ **AI Agent Enablement**
- Single query returns complete development context
- Agents understand architecture rationale
- Faster feature development cycles

✅ **Developer Experience**
- Easier onboarding (new devs query KG for context)
- Better decision traceability
- Understanding of dependencies

✅ **Architecture Governance**
- ADR compliance visible
- Contract implementation tracking
- Dependency analysis

✅ **Backward Compatibility**
- Existing Mermaid workflows unchanged
- New features opt-in via new tools
- No breaking changes

### Negative

❌ **Maintenance Burden**
- More indexers to maintain
- Requires keeping indexes in sync with repo
- Additional test coverage needed

❌ **Complexity**
- Larger codebase (~1000 LOC → ~2000 LOC)
- More state to manage
- Potential for index inconsistency

❌ **Performance Considerations**
- Initial indexing may take time
- Memory usage increases with repo size
- Need to optimize queries for large graphs

### Mitigations

| Risk | Mitigation |
|------|-----------|
| Index drift | Implement validation tool, re-indexing on demand |
| Performance | Lazy loading, caching, BFS optimization |
| Complexity | Clear separation of layers, comprehensive tests |
| Maintenance | Automated tests for each indexer |

---

## Implementation Plan

### Epic: KG-MCP Semantic Enhancement

**Goal:** Enable AI agents to query repository architecture end-to-end

**Phases:**
- **Phase 1 (P0, Weeks 1-2):** Semantic foundation
- **Phase 2 (P0, Weeks 2-3):** Repository indexing
- **Phase 3 (P1, Week 4):** AI query tools
- **Phase 4 (P1, Week 5):** Context extraction
- **Phase 5 (P2, Week 6):** Advanced analytics

---

## Related Decisions

- **ADR-0001:** Architecture (uses K0/K1 layering)
- **ADR-0010:** Contracts (APIs, schemas, policies)
- **ADR-0051:** Agent Scheduling (example use case)
- **ADR-0040:** Testing Framework (WARD)

---

## References

- Current implementation: `d:/familyos/.github/mcp/kg_mcp_server.py`
- Repo structure: `docs/k1_module_analysis.md`
- ADR decisions: `docs/architecture/decisions/`
- Contracts: `k0/contracts/`, `k1/contracts/`

---

## Approval Checklist

- [ ] Architecture team review
- [ ] AI agent team alignment
- [ ] Performance impact assessed
- [ ] Testing strategy approved
- [ ] Documentation plan confirmed
