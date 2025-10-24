# KG-MCP Enhancement - Project Roadmap & Board

**Project:** KG-MCP Semantic Enhancement for AI Agents
**Status:** PROPOSED
**Updated:** 2025-10-23

---

## Quick Overview

```
EPIC: KG-MCP-E001 (184 hours total)
├─ PHASE 1: Semantic Foundation (42h) ─ P0 ─ Oct 23 - Nov 6
│  ├─ KG-1.1: Semantic Node Types (8h) [NEW]
│  ├─ KG-1.2: Semantic Relations (6h) [NEW]
│  ├─ KG-1.3: ADR Indexer (12h) [NEW]
│  ├─ KG-1.4: Semantic Query Tools (8h) [NEW]
│  └─ KG-1.5: Tests & Docs (8h) [NEW]
│
├─ PHASE 2: Repository Indexing (56h) ─ P0 ─ Nov 6 - Nov 20
│  ├─ KG-2.1: Module Indexer (14h) [NEW]
│  ├─ KG-2.2: Contract Indexer (10h) [NEW]
│  ├─ KG-2.3: Dependency Engine (12h) [NEW]
│  ├─ KG-2.4: Dependency Query Tools (10h) [NEW]
│  └─ KG-2.5: Tests & Docs (10h) [NEW]
│
├─ PHASE 3: AI Query Tools (32h) ─ P1 ─ Nov 20 - Dec 4
│  ├─ KG-3.1: implementation_chain() (8h) [NEW]
│  ├─ KG-3.2: dependency_impact() (8h) [NEW]
│  ├─ KG-3.3: get_feature_context() (10h) [NEW]
│  └─ KG-3.4: Tests & Docs (6h) [NEW]
│
├─ PHASE 4: Context Extraction (30h) ─ P1 ─ Dec 4 - Dec 18
│  ├─ KG-4.1: AIContextBuilder (12h) [NEW]
│  ├─ KG-4.2: Natural Language Queries (10h) [NEW]
│  └─ KG-4.3: Tests & Docs (8h) [NEW]
│
└─ PHASE 5: Advanced Analytics (24h) ─ P2 ─ Dec 18 - Jan 1
   ├─ KG-5.1: Impact Analysis (10h) [NEW]
   ├─ KG-5.2: Architecture Diagnostics (8h) [NEW]
   └─ KG-5.3: Tests & Docs (6h) [NEW]
```

---

## Phase-by-Phase Breakdown

### 🟢 PHASE 1: Semantic Foundation (Oct 23 - Nov 6)

**Objective:** Add type system and ADR indexing to KG

| ID | Issue | Type | Hours | Status | Owner |
|----|-------|------|-------|--------|-------|
| KG-1.1 | Add Semantic Node Types | Feature | 8 | TODO | ? |
| KG-1.2 | Add Semantic Relation Types | Feature | 6 | TODO | ? |
| KG-1.3 | Implement ADR Indexer | Feature | 12 | TODO | ? |
| KG-1.4 | Add Semantic Query Tools | Feature | 8 | TODO | ? |
| KG-1.5 | Phase 1 Tests & Docs | QA/Docs | 8 | TODO | ? |

**Deliverables:**

- ✅ Typed node system working
- ✅ ADR indexer scans and creates nodes
- ✅ MCP tools for semantic queries
- ✅ 90%+ test coverage

**Definition of Done:**

- [ ] All issues closed
- [ ] Code review passed
- [ ] Test coverage >90%
- [ ] Docs complete
- [ ] Backward compatibility verified
- [ ] Performance <50ms for queries

**Dependencies:**

- None (foundational phase)

**Risks:**

- Low (extends existing, backward compatible)

---

### 🟡 PHASE 2: Repository Indexing (Nov 6 - Nov 20)

**Objective:** Index K0/K1 modules, contracts, and build dependency graph

| ID | Issue | Type | Hours | Status | Owner |
|----|-------|------|-------|--------|-------|
| KG-2.1 | Implement Module Indexer | Feature | 14 | TODO | ? |
| KG-2.2 | Implement Contract Indexer | Feature | 10 | TODO | ? |
| KG-2.3 | Build Dependency Graph Engine | Feature | 12 | TODO | ? |
| KG-2.4 | Add Repository Query Tools | Feature | 10 | TODO | ? |
| KG-2.5 | Phase 2 Tests & Docs | QA/Docs | 10 | TODO | ? |

**Deliverables:**

- ✅ Module indexer working on k0/ and k1/
- ✅ Contract indexer parsing OpenAPI & JSON schemas
- ✅ Full dependency graph queryable
- ✅ Circular dependency detection

**Definition of Done:**

- [ ] 100% of k0/k1 modules indexed
- [ ] Dependency accuracy >95%
- [ ] Circular deps detected
- [ ] Performance <100ms for deep queries

**Dependencies:**

- Phase 1 must be complete

**Risks:**

- Medium (dependency parsing complex, potential false positives)

---

### 🟣 PHASE 3: AI Query Tools (Nov 20 - Dec 4)

**Objective:** High-level queries AI agents will use

| ID | Issue | Type | Hours | Status | Owner |
|----|-------|------|-------|--------|-------|
| KG-3.1 | Implement `implementation_chain()` | Feature | 8 | TODO | ? |
| KG-3.2 | Implement `dependency_impact()` | Feature | 8 | TODO | ? |
| KG-3.3 | Implement `get_feature_context()` | Feature | 10 | TODO | ? |
| KG-3.4 | Phase 3 Tests & Docs | QA/Docs | 6 | TODO | ? |

**Deliverables:**

- ✅ 3 powerful AI-centric MCP tools
- ✅ Comprehensive documentation
- ✅ Example prompts for AI agents

**Definition of Done:**

- [ ] All tools working
- [ ] Latency <50ms
- [ ] Full test coverage
- [ ] AI agent can use independently

**Dependencies:**

- Phase 2 must be complete

**Risks:**

- Low (building on solid foundation)

---

### 🔵 PHASE 4: Context Extraction (Dec 4 - Dec 18)

**Objective:** Natural language context for AI agents

| ID | Issue | Type | Hours | Status | Owner |
|----|-------|------|-------|--------|-------|
| KG-4.1 | Implement AIContextBuilder | Feature | 12 | TODO | ? |
| KG-4.2 | Implement Natural Language Queries | Feature | 10 | TODO | ? |
| KG-4.3 | Phase 4 Tests & Docs | QA/Docs | 8 | TODO | ? |

**Deliverables:**

- ✅ Context builder for any development task
- ✅ Natural language query understanding
- ✅ Ready for AI agent integration

**Definition of Done:**

- [ ] All queries working
- [ ] Docs complete with examples
- [ ] AI agent can understand intent

**Dependencies:**

- Phase 3 complete

**Risks:**

- Low

---

### 🟠 PHASE 5: Advanced Analytics (Dec 18 - Jan 1)

**Objective:** Governance and diagnostics (P2, lower priority)

| ID | Issue | Type | Hours | Status | Owner |
|----|-------|------|-------|--------|-------|
| KG-5.1 | Implement Impact Analysis | Feature | 10 | TODO | ? |
| KG-5.2 | Implement Architecture Diagnostics | Feature | 8 | TODO | ? |
| KG-5.3 | Phase 5 Tests & Docs | QA/Docs | 6 | TODO | ? |

**Deliverables:**

- ✅ Impact analysis for ADR changes
- ✅ Architecture diagnostics (unmaintained code, etc.)

**Dependencies:**

- Phase 4 complete

**Risks:**

- Low

---

## Resource Requirements

### Team Composition

```
Project Lead (50h)
├─ Overall coordination
├─ Architecture reviews
└─ Critical path management

Backend Engineers (120h)
├─ Indexer implementations (Phase 1-2)
├─ Query engine (Phase 2-3)
└─ Context extraction (Phase 4-5)

QA/Test (30h)
├─ Test suite development
├─ Performance testing
└─ Integration testing

Documentation (20h)
├─ API documentation
├─ Usage guides
└─ Examples
```

### Estimated Team Allocation

- **1 Project Lead:** 30% (ongoing)
- **2 Backend Engineers:** 70% (full-time on project)
- **1 QA/Test Engineer:** 50% (testing)
- **1 Tech Writer:** 20% (documentation)

**Total:** ~2.5 FTE for 8-10 weeks

---

## Success Criteria by Phase

### Phase 1: Semantic Foundation

```
BEFORE:                          AFTER:
KG → Diagrams only              KG → Diagrams + Semantic types
     ↓                               ↓
     No ADR linking                 ADRs indexed
     No type system                 Typed nodes & relations
     Basic search                   Semantic queries
```

**Metrics:**

- ✅ 50 ADRs indexed successfully
- ✅ Semantic queries <10ms
- ✅ 90%+ test coverage

### Phase 2: Repository Indexing

```
BEFORE:                          AFTER:
Modules isolated                 Full dependency graph
     ↓                               ↓
     No dependency tracking         Can answer "what breaks?"
     No contract links              Contracts linked to code
     Unknown impact                 Impact analysis possible
```

**Metrics:**

- ✅ 100% of k0/k1 indexed
- ✅ Dependency accuracy >95%
- ✅ <100ms query latency

### Phase 3: AI Query Tools

```
BEFORE:                          AFTER:
AI agent manual search           AI queries KG for context
     ↓                               ↓
     Slow onboarding               Fast, autonomous development
     Missing context               Complete context available
     Error-prone                   Architecture-aware
```

**Metrics:**

- ✅ 3 AI tools working
- ✅ <50ms latency
- ✅ AI agent can use independently

### Phase 4: Context Extraction

```
BEFORE:                          AFTER:
AI: "Help me implement feature"  AI: "Help me implement feature"
     ↓                               ↓
     Manual context gathering      Automatic context extraction
     Incomplete answers            Complete, relevant answers
     Slow start                    Fast start, ready to code
```

**Metrics:**

- ✅ 95%+ context relevance
- ✅ <200ms context generation
- ✅ AI agent satisfaction

### Phase 5: Advanced Analytics

```
New capabilities:
- Impact analysis for ADR changes
- Architecture diagnostics
- Governance insights
```

---

## Critical Path

```
Start → Phase 1 (2 weeks) → Phase 2 (2 weeks) → Phase 3 (1 week)
                                                      ↓
                                                  Phase 4 (1 week)
                                                      ↓
                                                  Phase 5 (1 week)
                                                      ↓
                                                    Done! 🎉
```

**Longest single path:** 8 weeks

---

## Decision Points

### Decision 1: Deployment Strategy

**Question:** Deploy each phase separately or wait for Phase 3 completion?

**Option A:** Separate deployments (Phase 1 → Prod, Phase 2 → Prod, etc.)

- ✅ Earlier value delivery
- ✅ Feedback earlier
- ❌ More releases
- ❌ More testing per release

**Option B:** Wait for Phase 3 (all P0 phases together)

- ✅ Fewer releases
- ✅ More complete feature
- ❌ Longer time to value
- ❌ More risk in single release

**Recommendation:** Option A (phase-by-phase)

---

### Decision 2: Index Maintenance

**Question:** How to keep indexes in sync with repo?

**Option A:** Manual on-demand re-indexing

- ✅ Simple to implement
- ✅ Controlled updates
- ❌ Manual effort
- ❌ Stale data between runs

**Option B:** Automatic on commit hooks

- ✅ Always fresh
- ✅ Automatic
- ❌ Complex setup
- ❌ Potential performance impact

**Recommendation:** Option A initially, add Option B in Phase 5

---

### Decision 3: Performance SLA

**Question:** What latency targets?

**Proposal:**

- Single queries: <50ms (P95)
- Context extraction: <200ms (P95)
- Full graph traversal: <1000ms (P95)

**Acceptable?** YES / NO

---

## Open Questions

1. **Team:** Who should own each phase?
2. **Scheduling:** Can we allocate 2.5 FTE for 8-10 weeks?
3. **Prioritization:** Strictly follow Phase order or can parallelize?
4. **Testing:** Should we add property-based tests for dependency detection?
5. **Integration:** When should AI agent team start integration testing?
6. **Monitoring:** Should we add KG health metrics to observability?
7. **Fallback:** What if dependency detection has false positives?

---

## Approval Checklist

- [ ] Architecture team approves ADR-0053
- [ ] Roadmap approved by project leads
- [ ] Team allocation confirmed
- [ ] Success criteria agreed
- [ ] Deployment strategy decided
- [ ] Risk mitigations accepted
- [ ] Questions answered

---

## Next Steps

1. **Immediate (this week):**
   - [ ] Circulate ADR and roadmap for feedback
   - [ ] Assign team members to phases
   - [ ] Create Jira/GitHub issues from template

2. **Week 1 of Phase 1:**
   - [ ] Kick-off meeting
   - [ ] Set up development environment
   - [ ] Start KG-1.1 (Semantic Node Types)

3. **Ongoing:**
   - [ ] Weekly status updates
   - [ ] Bi-weekly demos
   - [ ] Risk monitoring

---

## References

- **ADR:** `docs/architecture/decisions/0053-kg-mcp-semantic-enhancement.md`
- **Current KG:** `d:/familyos/.github/mcp/kg_mcp_server.py`
- **Copilot Instructions:** `.github/copilot-instructions.md`
- **KG Usage Docs:** `.github/instructions/mmd-mcp-usage.instructions.md`

---

**Status:** READY FOR REVIEW 📋
