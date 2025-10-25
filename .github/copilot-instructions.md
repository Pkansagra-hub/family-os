# 🧭 K1 Intelligence Module — Copilot Rules of Engagement

**K1 is the core agentic orchestrator kernel: production-ready, research-grounded, zero-tolerance for mediocrity.**

---

## 🚫 Zero-Tolerance Rules (Non-Negotiable)

- **NO MD FILES UNLESS REQUIRED** — Do NOT create any Markdown files that are not explicitly requested or mandatory (ADRs, API docs, etc.). No completion reports, guides, analysis docs, or summary files.
- **No auto-generated Markdown** — Create .md files ONLY when explicitly requested
- **No simulation code** — No `asyncio.sleep()`, `time.sleep()`, mock delays, or playground patterns
- **No mock theater** — Use real components with WARD; never fake functionality
- **ADR is mandatory** — All code changes require contract/ADR review FIRST or create ADRs before proceeding
- **Ask, don't assume** — When unclear, request clarification rather than guessing
- **Violation = PR rejection** — Immediate rejection for simulation code, excessive docs, or missing ADRs

---

## 1️⃣ Universal Code Development Workflow (5-Step Gated Process)

**SCOPE: This applies to EVERY code change - 10 lines or 10,000 lines.**

Whether you're:
- Creating a new service/module
- Adding a new function
- Fixing a bug
- Modifying existing code
- Adding configuration
- ANY production code change

→ **Follow the 5-Step Gated Process below**

**CRITICAL: This is a GATED workflow. Each step is a blocker. Do NOT proceed to next step until current step is complete.**

**📋 For detailed implementation guidance with code examples, see: `.github/instructions/service-design.instructions.md`**

### Quick Reference: The 5 Gates

**🚦 GATE 1: ADR Discovery & Validation (KG-Enhanced)**
- **KG Search:** `kg_v2_hybrid_search("component architecture")` for semantic discovery
- **Find ADRs:** `kg_v2_find_by_type("adr")` for fast type filtering
- **Navigate:** `kg_v2_neighbors("adr_id")` to find related ADRs
- **Dependencies:** `kg_v2_paths("adr_src", "adr_dst")` to understand decision chains
- **Fallback:** Search `docs/architecture/decisions/` manually if KG unavailable
- If missing: HALT → Prompt user → Brainstorm blockers → Create ADR
- Validate: ADR exists, status is ACCEPTED/IMPLEMENTED, aligns with task

**🚦 GATE 2: Contract Discovery & Validation (KG-Enhanced)**
- **KG Search:** `kg_v2_find_by_type("contract")` to find existing contracts
- **Patterns:** `kg_v2_neighbors("module_id", relation="uses_contract")` for similar usage
- **Dependencies:** `kg_v2_get_module_deps("module_id")` to understand contract needs
- **Fallback:** Check `k1/contracts/` manually for API specs, schemas, policies
- If missing: HALT → Create contracts (schemas → API → examples → policies)
- Validate contracts: `python k0/automation/lint_schemas.py`
- Update VERSION file

**🚦 GATE 3: Implementation with Contract Compliance (KG-Enhanced)**
- **Context:** `kg_v2_implementation_chain("adr_id")` for complete implementation needs
- **Feature Context:** `kg_v2_get_feature_context("feature_name")` for related work
- **Dependencies:** `kg_v2_get_module_deps("module_id")` before importing
- **Impact Check:** `kg_v2_dependency_impact("module_id")` to avoid breaking changes
- **Circular Deps:** `kg_v2_find_circular_deps()` to avoid import cycles
- Write production code following architecture patterns
- **NO simulation code** (no `asyncio.sleep()`, `time.sleep()`)
- Add `cognitive_trace_id`, reference ADR numbers in comments
- Check for contract deviations → Update contracts if needed

**🚦 GATE 4: Test Implementation (WARD Framework, KG-Enhanced)**
- **Test Patterns:** `kg_v2_search("test integration component")` for similar tests
- **Existing Tests:** `kg_v2_neighbors("module_id", relation="tested_by")` to find patterns
- Integration tests > unit tests, real components only
- Test contract compliance and performance budgets
- Run: `python -m ward test --path tests/`
- All tests must pass before proceeding

**🚦 GATE 5: Memory Documentation (KG-Enhanced)**
- **Health Check:** `kg_v2_graph_summary()` to understand architecture impact
- **Doc Gaps:** `kg_v2_diagnostics("orphaned_nodes")` to find missing links
- **Circular Deps:** `kg_v2_find_circular_deps()` to verify no cycles introduced
- Create memory: `mem_write(project="k1_intelligence", title, content, tags)`
- Include: Epic/Issue, ADRs, decisions, files touched, tests, performance
- Link related memories: `mem_link(src_id, dest_id, relation)`
- Update architecture diagrams if changed

### Workflow Enforcement

Each gate is a **BLOCKER**:
- ❌ **ADR missing** → Cannot proceed to contracts
- ❌ **Contracts missing** → Cannot proceed to implementation
- ❌ **Contract deviations** → Must update contracts first
- ❌ **Tests failing** → Cannot proceed to documentation
- ❌ **Memory not documented** → Work incomplete

**Remember**: Read `.github/instructions/service-design.instructions.md` for detailed step-by-step guidance with code examples and best practices.

---

## 2️⃣ K1 Architecture Overview

**Core Vision:** Production-ready agentic orchestrator managing agent lifecycles, multi-agent coordination, adaptive learning, with strict performance/safety guarantees.

**5 Core Components:**
- 🤖 **Agent Fabric** — Lifecycle FSM (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
- 🔄 **Orchestrator Core** — 3-phase coordination (Negotiation → Selection → Execution)
- 📋 **Planner Agent** — 4-stage pipeline (Sketch → Expand → Validate → Commit)
- 🎯 **Protocol Monitor** — MPST/Scribble validation for 6 protocols
- 🧠 **Learning Loop** — Feedback signals + drift detection + hot-reload

**Architecture Built On:** Actor Model (Hewitt 1973), MPST (Honda 2008), Capabilities (Dennis 1966), SEDA (Welsh 2001), Saga Pattern (Garcia-Molina 1987), Contract Net (Smith 1980)

**Module Structure:** 52 modules, 758 files, 5 layers (see `docs/k1_module_analysis.md`)

**Performance Budgets (P95):**
| Metric | Budget | Current | Status |
|--------|--------|---------|--------|
| TTFT | 150ms | 140ms | ✅ |
| E2E Latency | 2000ms | 1850ms | ✅ |
| Memory | 500MB | 450MB | ✅ |

**Reference Docs:**
- `docs/whiteboard.md` — 21K-line spec (complete design)
- `docs/k1_module_analysis.md` — 52 modules breakdown
- `architecture_diagrams/` — 11 validated Mermaid diagrams

---

## 3️⃣ Development Standards

### Python Standards
- **PEP 8** — Style guide, type hints, Google-style docstrings
- **Code organization** — Clear naming, organized imports (stdlib → third-party → local)
- **Error handling** — Explicit exceptions, context in errors, recovery paths, structured logging
- See *Appendix A: Code Organization Example*

### Git Workflow
- **Branch naming:** `feature/<issue>-<desc>`, `fix/<issue>-<desc>`, `docs/<desc>`, `refactor/<desc>`, `test/<desc>`
- **PR requirements:** Description + architecture impact + diagram updates + ADR reference + WARD tests + performance notes + docs updates
- **PR Checklist:** See *Appendix B: PR Standards*

### Testing (WARD Framework)
- **Philosophy:** Integration > unit, real components only, comprehensive coverage, performance validation
- **No mock theater** — Use real implementations with WARD fixtures
- **Test organization:** See `tests/` structure in *Appendix C: Test Structure*
- **Run tests:** `python -m ward test --path tests/`
- See *Appendix D: WARD Test Example*

### Observability
- **Metrics** — Export Prometheus counters, histograms, gauges for all components
- **Tracing** — Add `cognitive_trace_id` to all operations; use OpenTelemetry spans
- **Logging** — Structured logs with context; use structlog
- See *Appendix E: Metrics + Tracing Snippets*

### Security & Privacy
- **Least privilege** — Agents get minimal capabilities
- **Capability-based access** — Use capabilities, not ambient authority
- **Privacy bands** — Respect GREEN/AMBER/RED classifications
- **Audit logging** — Log sensitive operations with trace_id
- **PII protection** — Redact PII in logs/metrics
- See *Appendix F: Security Patterns*

### Configuration & Environment
- **Config files** — `k1/config/*.yml` (YAML format)
- **Environment variables:** `K1_ENV`, `K1_LOG_LEVEL`, `K1_METRICS_PORT`, `K1_TRACE_ENABLED`
- See *Appendix G: Config Example*

---

## 4️⃣ Playbooks: MCP Toolchain

### Mermaid Diagrams (MMD)
- **Ingest:** `mmd_ingest(<absolute_path>)` before working
- **Validate:** `mmd_validate(<diagram_id>)` to check syntax
- **Summarize:** `mmd_summary(<diagram_id>)` for overview
- **Navigate:** `mmd_neighbors`, `mmd_paths` for deep dives
- **Standards:** Naming `k1_<component>_<type>.mmd`, include purpose + research citations, pass validation before commit
- **Log usage:** Record diagram IDs in `docs/development/mmd-diagram-usage.md`

### Knowledge Graph (KG) - Semantic Repository Intelligence

**PRIORITY: Use KG tools FIRST for all discovery tasks. They provide semantic understanding and are faster than manual file searches.**

**Core Discovery (Use These Most):**
```python
# Hybrid search - BEST for initial discovery (semantic + keyword)
kg_v2_hybrid_search(query="agent lifecycle architecture", alpha=0.5, limit=20)
# alpha: 0.0=pure vector, 0.5=balanced, 1.0=pure keyword

# Find nodes by type - FAST type filtering
kg_v2_find_by_type(node_type="adr", limit=50)  # Types: adr, module, contract

# Full-text search - Good for keyword searches
kg_v2_search(query="orchestrator coordination", limit=20)
```

**Graph Navigation:**
```python
# Find adjacent nodes (relationships)
kg_v2_neighbors(node_id="adr_0005", direction="both")
# direction: "outgoing", "incoming", "both"
# relation: optional filter ("references", "depends_on", "uses_contract")

# Find paths between nodes (understand connections)
kg_v2_paths(src="adr_0005", dst="module_name", max_hops=6, max_paths=5)

# Get transitive dependencies (what module needs)
kg_v2_get_module_deps(module_id="module_k1.l2_orchestration.orchestrator", depth=3)
```

**AI Context Tools (Smart Queries):**
```python
# Get complete implementation context for ADR
# Returns: modules, dependencies, related decisions
kg_v2_implementation_chain(adr_id="adr_0086")

# Get feature context (ADRs + modules + contracts)
# Answers: "What exists related to this feature?"
kg_v2_get_feature_context(feature_name="agent lifecycle")

# Analyze impact of changing module
# Returns: direct/transitive dependents with risk assessment
kg_v2_dependency_impact(module_id="module_k1.l4_runtime.session_state")
```

**Diagnostics & Health:**
```python
# Graph statistics (node/edge counts, type distribution)
kg_v2_graph_summary()

# Find circular dependencies (avoid import cycles)
kg_v2_find_circular_deps()

# Find orphaned nodes (documentation gaps)
kg_v2_diagnostics(diagnostic_type="orphaned_nodes")
```

**When to Use KG Tools:**
- ✅ **GATE 1:** Find ADRs with `kg_v2_hybrid_search()` or `kg_v2_find_by_type("adr")`
- ✅ **GATE 2:** Find contracts with `kg_v2_find_by_type("contract")` or `kg_v2_neighbors()`
- ✅ **GATE 3:** Get implementation context with `kg_v2_implementation_chain()`
- ✅ **GATE 3:** Check dependencies with `kg_v2_get_module_deps()` and `kg_v2_dependency_impact()`
- ✅ **GATE 4:** Find test patterns with `kg_v2_search("test integration")`
- ✅ **GATE 5:** Check health with `kg_v2_graph_summary()` and `kg_v2_diagnostics()`

**Best Practices:**
- Use `kg_v2_hybrid_search()` for initial exploration (best semantic + keyword blend)
- Use `kg_v2_find_by_type()` when you know exact type needed
- Use `kg_v2_implementation_chain()` before implementing ADRs
- Use `kg_v2_dependency_impact()` before modifying existing modules
- Use `kg_v2_find_circular_deps()` to avoid circular import bugs

### Memory MCP (Optional)
- **Write:** `mem_write(project="k1_intelligence", title, content, tags?)`
- **Search:** `mem_find(query, project="k1_intelligence")`
- **Read:** `mem_read_many(ids=[...])`
- **Link:** `mem_link(src_id, dest_id, relation)`
- **Best practices:** Use project key `k1_intelligence`, tag with module names, link to ADRs/diagrams

---

## 5️⃣ Quick Reference

### Repository Structure
- ✅ **ALLOWED at root:** README.md, LICENSE, .gitignore, pyproject.toml, setup.py
- ❌ **FORBIDDEN:** Loose .md files, .py files, scripts, test files

### Common Issues & Solutions
| Issue | Solution |
|-------|----------|
| Diagram won't validate | Check syntax with `mmd_validate`, fix special chars, avoid keywords |
| WARD tests failing | Initialize fixtures properly, check async/await, verify test isolation, run `--verbose` |
| Performance budget exceeded | Profile with `py-spy`, check for blocking I/O, verify KV cache hit rate (~75%) |
| ADR unclear | Use template in `docs/architecture/decisions/0000-template.md`, include problem/alternatives/decision/consequences |

### Useful Commands
```bash
# Testing
python -m ward test --path tests/
python -m ward test --search "orchestrator"

# Profiling
py-spy top --pid <pid>

# Metrics
curl localhost:9090/metrics
```

### Getting Help
- **Architecture:** `docs/whiteboard.md` (21K spec)
- **Modules:** `docs/k1_module_analysis.md` (52 modules)
- **Diagrams:** `architecture_diagrams/` (11 validated)
- **Patterns:** Research citations in diagram headers
- **Performance:** Section 3 budgets

---

## 6️⃣ Using Instruction Files in `.github/instructions/`

Each instruction file provides domain-specific guidance for different tasks. **Read the relevant instruction file FIRST** before proceeding with work.

### When to Use Each File

| File | When to Use | Purpose | Quick Start |
|------|----------|---------|------------|
| **copilot-instructions.md** | Every session | Overall rules, 5-step workflow, architecture overview | Start here for all work |
| **service-design.instructions.md** | Before GATE 1 through GATE 5 | Complete 5-step gated workflow implementation | Implementing new features/components |
| **documentation-standards.instructions.md** | Writing documentation | Doc standards, templates, structure requirements | Creating ADRs, READMEs, design docs |
| **docs.instructions.md** | Writing docs/READMEs | Specific guidance for doc files and ADRs | Creating `docs/**/*.md` files |
| **mmd-diagrams.instructions.md** | Before working with diagrams | Diagram structure, locations, naming, validation | Creating/editing `.mmd` files |
| **mmd-mcp-usage.instructions.md** | Ingesting diagrams into MCP | How to use MCP tools for diagram analysis | Using `mmd_ingest`, `mmd_validate`, etc. |
| **testing-requirements.instructions.md** | Before GATE 4 (Testing) | Comprehensive testing standards, coverage, performance | Understanding testing philosophy & requirements |
| **tests.instructions.md** | Writing tests | Test structure, WARD framework, patterns, assertions | Actually writing test code |

### Instruction File Decision Tree

```
START: About to work on something
│
├─ Writing CODE?
│  ├─ New service/module/function?
│  │  └─> Read: service-design.instructions.md (all 5 gates)
│  │
│  ├─ Fixing a bug/modifying code?
│  │  ├─> Check: service-design.instructions.md (GATE 3)
│  │  └─> Check: testing-requirements.instructions.md (GATE 4)
│  │
│  └─ Writing TESTS?
│     ├─> Understand philosophy: testing-requirements.instructions.md
│     └─> Write code: tests.instructions.md
│
├─ Writing DOCUMENTATION?
│  ├─ ADR (Architecture Decision)?
│  │  └─> Read: documentation-standards.instructions.md + docs.instructions.md
│  │
│  ├─ README or design docs?
│  │  └─> Read: docs.instructions.md + documentation-standards.instructions.md
│  │
│  └─ Other markdown?
│     └─> Read: documentation-standards.instructions.md
│
├─ Working with ARCHITECTURE DIAGRAMS?
│  ├─ Creating/editing .mmd files?
│  │  └─> Read: mmd-diagrams.instructions.md
│  │
│  └─ Ingesting into MCP for analysis?
│     └─> Read: mmd-mcp-usage.instructions.md
│
└─ UNCERTAIN?
   └─> Start with: copilot-instructions.md (this file)
      Then check decision tree
```

### Integration Example

**Scenario:** You're implementing K1 orchestrator 3-phase coordination

1. **Start with:** `copilot-instructions.md` (overview of 5-step workflow)
2. **GATE 1 (ADRs):** Read `service-design.instructions.md` (ADR discovery section)
   - Check `docs/architecture/decisions/` for existing ADRs
   - Reference `documentation-standards.instructions.md` for ADR template
3. **GATE 2 (Contracts):** Read `service-design.instructions.md` (contract discovery section)
   - Update schemas in `k1/contracts/`
   - Validate: `python k0/automation/lint_schemas.py --validate`
4. **GATE 3 (Implementation):** Read `service-design.instructions.md` (implementation section)
   - Add `cognitive_trace_id` to orchestrator
   - Reference ADR numbers in code comments
5. **GATE 4 (Testing):** Read both:
   - `testing-requirements.instructions.md` (understand requirements)
   - `tests.instructions.md` (write actual tests)
   - Create `tests/k1/component/test_orchestrator_3phase.py`
6. **GATE 5 (Memory):** Document decisions
   - Record in `mem_write(project="k1_intelligence", ...)`
   - Link to ADRs with `mem_link(...)`
   - Update `architecture_diagrams/` if needed
   - Reference in `docs/architecture/diagrams/k1/README.md`

---

## New Feature Checklist

Before implementing:
- [ ] ADR in `docs/architecture/decisions/`
- [ ] Architecture diagrams updated
- [ ] Module impact analyzed
- [ ] Performance budget defined
- [ ] WARD tests planned (integration > unit)
- [ ] Observability planned (metrics, traces, logs)
- [ ] Security/privacy implications assessed
- [ ] Configuration schema defined
- [ ] Documentation written
- [ ] Zero simulation policy respected

---
