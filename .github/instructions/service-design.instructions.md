```instructions
# Code Development Workflow (Universal)

## Scope: ALL Code Changes

**This workflow applies to EVERY code change, regardless of size:**
- ✅ New feature (10,000 lines)
- ✅ Small bug fix (10 lines)
- ✅ New service/module
- ✅ Existing service modification
- ✅ New function/class
- ✅ Configuration changes
- ✅ Any production code

**If you're writing code → Follow the 5-Step Gated Process**

### Examples of What This Covers:

| Scenario | Lines Changed | Follow 5-Step Process? |
|----------|---------------|------------------------|
| New microservice with API | 10,000 lines | ✅ YES |
| Add new endpoint to existing service | 200 lines | ✅ YES |
| Fix bug in existing function | 10 lines | ✅ YES |
| Add new helper function | 50 lines | ✅ YES |
| Refactor existing module | 500 lines | ✅ YES |
| Add new configuration file | 20 lines | ✅ YES |
| Update data schema | 5 lines | ✅ YES |
| Add new class/component | 300 lines | ✅ YES |

**Exception:** Only documentation changes (README updates, comments) without code logic changes can skip this process.

---

## Purpose
Provide a **mandatory 5-step gated workflow** for ALL code development in FamilyOS. This ensures:
- Architectural decisions are documented (ADRs)
- API contracts exist before implementation
- Code matches contracts
- Comprehensive test coverage
- Knowledge is preserved for future work

## Baseline References
- **ADRs**: `docs/architecture/decisions/` (architectural decisions)
- **Contracts**: `k1/contracts/` (API specs, schemas, policies)
- **Architecture diagrams**: `architecture_diagrams/` (Mermaid diagrams)
- **Knowledge graph**: Query via MCP `kg_*` tools
- **Testing standards**: `.github/instructions/testing-requirements.instructions.md`
- **Production policy**: `.github/copilot-instructions.md` (zero-tolerance rules)

---

## 🚦 5-Step Gated Workflow (MANDATORY)

**CRITICAL**: Each step is a **GATE**. Do NOT proceed until current gate passes.

---

### **STEP 1: ADR Discovery & Validation** 🚦 GATE 1

**Objective:** Ensure architectural foundation exists before any work.

#### Actions:
1. **Search for Relevant ADRs:**
   ```bash
   # Search by component name
   grep_search(query="<component_name>", includePattern="docs/architecture/decisions/**/*.md")

   # Check master reference
   read_file("docs/ADR_MASTER_REFERENCE.md")

   # Check family map for relationships
   read_file("docs/adr_family_map.md")
   ```

2. **Validate ADR Coverage:**
   - Does ADR exist for this component/feature?
   - Is ADR status ACCEPTED or IMPLEMENTED?
   - Are all related/parent ADRs reviewed?

#### Decision Point:
- ✅ **ADR EXISTS** → Proceed to Step 2
- ❌ **ADR MISSING** → **HALT IMMEDIATELY**

#### If ADR Missing:
1. **PROMPT USER:**
   ```
   ⚠️ BLOCKER: No ADR found for [component/feature]

   I need to create an ADR before proceeding. Let me brainstorm:

   Questions to resolve:
   - What architectural decisions need documentation?
   - What alternatives should we evaluate?
   - What are performance/security/scalability implications?
   - Which existing ADRs does this relate to?
   - What are the trade-offs?

   Shall I create ADR-XXXX: [Proposed Title]?
   ```

2. **CREATE ADR:**
   - Use template: `docs/architecture/decisions/0000-template.md`
   - Document: Context, Decision, Alternatives, Consequences
   - Include: Performance targets, security considerations, dependencies

3. **UPDATE REFERENCES:**
   - Add to `docs/ADR_MASTER_REFERENCE.md`
   - Add to `docs/adr_family_map.md`
   - Link related ADRs

4. **RETURN TO STEP 1** to validate ADR exists

#### Gate 1 Checklist:
- [ ] Relevant ADR(s) identified
- [ ] ADR status verified (ACCEPTED/IMPLEMENTED)
- [ ] Related ADRs reviewed
- [ ] ADR decision aligns with task

---

### **STEP 2: Contract Discovery & Validation** 🚦 GATE 2

**Objective:** Ensure API contracts exist before implementation.

#### Actions:
1. **Check Contract Locations:**
   ```
   k1/contracts/
   ├── api/              # OpenAPI/AsyncAPI specs
   ├── jsonschema/       # Data schemas
   │   └── examples/     # Example payloads
   ├── policy/           # Policy contracts
   ├── observability/    # Metrics/tracing contracts
   └── VERSION           # Contract version tracking
   ```

2. **Validate Contracts:**
   ```bash
   # Run contract validation
   python k0/automation/lint_schemas.py

   # Check for examples
   ls k1/contracts/jsonschema/examples/
   ```

3. **Review Contract Playbook:**
   ```bash
   read_file("docs/development/contracts-playbook.md")
   ```

#### Decision Point:
- ✅ **CONTRACTS EXIST** → Proceed to Step 3
- ❌ **CONTRACTS MISSING** → **HALT IMMEDIATELY**

#### If Contracts Missing:
1. **CREATE CONTRACTS (in order):**

   **A. Define Data Schemas (JSON Schema):**
   ```json
   // k1/contracts/jsonschema/<component>_schema.json
   {
     "$schema": "http://json-schema.org/draft-07/schema#",
     "title": "ComponentRequest",
     "description": "Request schema for component X (ADR-XXXX)",
     "type": "object",
     "properties": { ... },
     "required": [ ... ]
   }
   ```

   **B. Define API Contracts (OpenAPI):**
   ```yaml
   # k1/contracts/api/<component>_api.yaml
   openapi: 3.0.0
   info:
     title: Component API
     version: 1.0.0
     description: API for component X (ADR-XXXX)
   paths: ...
   ```

   **C. Add Examples:**
   ```bash
   # k1/contracts/jsonschema/examples/<component>_example.json
   { "example": "payload" }
   ```

   **D. Define Policy Contracts (if security-relevant):**
   ```yaml
   # k1/contracts/policy/<component>_policy.yaml
   capabilities: [...]
   privacy_bands: [...]
   audit_requirements: [...]
   ```

2. **Validate Contracts:**
   ```bash
   python k0/automation/lint_schemas.py
   ```

3. **Update VERSION:**
   ```bash
   # Increment version in k1/contracts/VERSION
   echo "1.1.0" > k1/contracts/VERSION
   ```

4. **Reference ADRs:**
   - Add ADR references in contract descriptions
   - Link contracts to ADRs in documentation

5. **RETURN TO STEP 2** to validate contracts exist

#### Gate 2 Checklist:
- [ ] All required contracts identified
- [ ] Contracts reference ADR numbers
- [ ] Schemas validated successfully
- [ ] Examples provided
- [ ] VERSION file updated
- [ ] Contract playbook reviewed

---

### **STEP 3: Implementation with Contract Compliance** 🚦 GATE 3

**Objective:** Write production-ready code adhering to contracts.

#### Actions:

**A. Pre-Implementation Review:**
1. Read `docs/whiteboard.md` (21K spec)
2. Read `docs/k1_module_analysis.md` (52 modules)
3. Load architecture diagrams:
   ```python
   mmd_ingest("<absolute_path_to_diagram>")
   mmd_validate("<diagram_id>")
   mmd_summary("<diagram_id>")
   ```

**B. During Implementation:**
1. **Follow Architecture Patterns:**
   - Actor Model (Hewitt 1973)
   - MPST (Honda 2008)
   - Capabilities (Dennis 1966)
   - SEDA (Welsh 2001)
   - Saga Pattern (Garcia-Molina 1987)

2. **Respect Module Boundaries:**
   - Check `docs/k1_module_analysis.md` for layer isolation
   - Use proper import paths

3. **Implementation Standards:**
   - Use FlatBuffers for serialization
   - Validate MPST protocols
   - **NO simulation code** (no `asyncio.sleep()`, `time.sleep()`)
   - Add `cognitive_trace_id` to all operations
   - Reference ADR numbers in code comments

4. **Code Organization:**
   ```python
   """
   Module: k1.<layer>.<component>
   Purpose: <brief description>

   ADR: ADR-XXXX - <ADR title>
   Related ADRs: ADR-YYYY, ADR-ZZZZ

   Research: <citations>
   """
   ```

**C. Contract Deviation Check:**
1. Compare implementation against contracts
2. Check for deviations:
   - New fields added?
   - Changed types?
   - Different behavior?
   - Additional endpoints?

#### Decision Point:
- ✅ **NO DEVIATION** → Proceed to Step 4
- ⚠️ **DEVIATION DETECTED** → **UPDATE CONTRACTS**

#### If Deviation Found:
1. **Document Deviation Reason**
2. **Update Contracts:**
   - Update schemas/specs
   - Update examples
   - Increment VERSION
3. **Re-validate:**
   ```bash
   python k0/automation/lint_schemas.py
   ```
4. **Continue to Step 4**

#### Gate 3 Checklist:
- [ ] Code implements all contract requirements
- [ ] No undocumented deviations
- [ ] Observability added (metrics, traces, logs)
- [ ] ADR references in code comments
- [ ] Module boundaries respected
- [ ] No simulation code
- [ ] `cognitive_trace_id` propagated

---

### **STEP 4: Test Implementation** 🚦 GATE 4

**Objective:** Comprehensive test coverage with WARD framework.

#### Actions:

**A. Read Testing Standards:**
```bash
read_file(".github/instructions/testing-requirements.instructions.md")
read_file(".github/instructions/tests.instructions.md")
```

**B. Write WARD Tests (Priority Order):**

1. **Integration Tests** (highest priority):
   ```python
   from ward import test, fixture

   @fixture
   async def component():
       """Real component with dependencies"""
       comp = Component(config=test_config)
       await comp.initialize()
       yield comp
       await comp.shutdown()

   @test("component processes request according to contract")
   async def _(comp=component):
       request = create_valid_request()  # From contract examples
       result = await comp.process(request)

       # Contract validation
       assert validate_schema(result, "component_response_schema.json")

       # Performance validation
       assert result.latency_ms < 100  # ADR performance budget
   ```

2. **Contract Validation Tests:**
   ```python
   @test("request conforms to contract schema")
   def _():
       request = create_request()
       assert validate_schema(request, "component_request_schema.json")
   ```

3. **Error Scenario Tests:**
   ```python
   @test("handles missing fields gracefully")
   async def _(comp=component):
       invalid_request = {"incomplete": "data"}
       with raises(ValidationError):
           await comp.process(invalid_request)
   ```

4. **Performance Tests:**
   ```python
   @test("meets P95 latency budget from ADR")
   async def _(comp=component):
       latencies = []
       for _ in range(100):
           start = time.perf_counter()
           await comp.process(request)
           latencies.append((time.perf_counter() - start) * 1000)

       p95 = sorted(latencies)[94]
       assert p95 < 150  # From ADR performance target
   ```

**C. Test Structure:**
```
tests/
├── <layer>/
│   ├── <component>/
│   │   ├── __init__.py
│   │   ├── test_<feature>.py
│   │   ├── test_contracts.py
│   │   ├── test_performance.py
│   │   └── fixtures.py
```

**D. Run Tests:**
```bash
# All tests
python -m ward test --path tests/

# Specific component
python -m ward test --path tests/<layer>/<component>/

# Verbose mode
python -m ward test --verbose

# Search specific tests
python -m ward test --search "<component>"
```

#### Gate 4 Checklist:
- [ ] All tests passing
- [ ] Integration tests cover main flows
- [ ] Contract validation tests included
- [ ] Performance assertions meet ADR budgets
- [ ] Error cases covered
- [ ] No mock/simulation code
- [ ] Real components only

---

### **STEP 5: Memory Documentation** 🚦 GATE 5

**Objective:** Create permanent memory record for future reference.

#### Actions:

**A. Create Memory Entry:**
```python
mem_write(
    project="k1_intelligence",
    title="[MILESTONE] ADR-XXXX Implementation: <Feature Name>",
    content="""
# Implementation: <Feature Name>

## Metadata
- **Epic/Issue**: #<issue_number>
- **Milestone**: M<X>
- **ADRs**: ADR-XXXX, ADR-YYYY
- **Date**: 2025-10-23
- **Status**: COMPLETE

## Architectural Decisions Made
1. **Decision**: <what was decided>
   - **Rationale**: <why this approach>
   - **Alternatives Considered**: <what else was evaluated>
   - **Trade-offs**: <what we gained/lost>

2. **Decision**: <another decision>
   - **Rationale**: <reasoning>
   ...

## Files Touched
- `path/to/file1.py`: Created agent factory with O(1) lookup
- `path/to/file2.py`: Added resource reservation with thermal awareness
- `k1/contracts/api/spec.yaml`: Added 3 new endpoints for dynamic agents
- `k1/contracts/jsonschema/agent_schema.json`: Defined agent creation schema

## Contracts Created/Modified
- `k1/contracts/api/agent_api.yaml`: Agent creation API (v1.1.0)
- `k1/contracts/jsonschema/agent_schema.json`: Agent data schema
- `k1/contracts/jsonschema/examples/agent_creation.json`: Example payload

## Tests Added
- `tests/l3_execution/agents/test_factory.py`:
  - Test O(1) lookup performance
  - Test creation with resource allocation
  - Test concurrent creation handling
- `tests/l3_execution/agents/test_contracts.py`:
  - Validate request/response schemas
  - Test contract compliance

## Performance Impact
- **Agent Creation Latency**: N/A → 95ms (P95, target <100ms) ✅
- **Registry Lookup**: N/A → 0.8ms (P95, target <1ms) ✅
- **Memory Allocation**: +128MB per agent (within budget)

## Architecture Diagram Updates
- Updated `architecture_diagrams/k1/k1_complete_with_flows.mmd`
- Added dynamic_creation module to Layer 3
- Validated diagram: `mmd_validate("k1_complete_with_flows")`

## Related Work
- Builds on ADR-0005 (Agent Lifecycle)
- Integrates with ADR-0012 (Resource Management)
- Enables ADR-0018 (Multi-Agent Coordination)

## Next Steps
- M2: Implement IDLE pool reuse (ADR-0086f)
- M2: Add registry multi-index support (ADR-0086g)
- M2: Complete observability metrics (ADR-0086h)
    """,
    tags=[
        "milestone",
        "adr-0086",
        "implementation",
        "agent-fabric",
        "layer-3",
        "m1-complete"
    ]
)
```

**B. Link Related Memories:**
```python
# Link to parent ADR discussion
mem_link(
    src_id="<new_memory_id>",
    dest_id="<adr_discussion_memory_id>",
    relation="implements"
)

# Link to previous milestone
mem_link(
    src_id="<new_memory_id>",
    dest_id="<previous_milestone_memory_id>",
    relation="follows"
)

# Link to related implementation
mem_link(
    src_id="<new_memory_id>",
    dest_id="<related_component_memory_id>",
    relation="relates_to"
)
```

**C. Update Documentation:**
1. **Architecture Diagrams:**
   ```python
   # If structure changed
   mmd_ingest("<absolute_path_to_updated_diagram>")
   mmd_validate("<diagram_id>")

   # Record usage
   # Add to docs/development/mmd-diagram-usage.md
   ```

2. **Component Documentation:**
   - Update module README
   - Add API documentation
   - Update migration guides if needed

3. **Contract Documentation:**
   ```bash
   # Regenerate API docs
   python k0/automation/generate_api_docs.py

   # Update Postman collection
   # (if contracts evolved)
   ```

#### Gate 5 Checklist:
- [ ] Memory created with all metadata
- [ ] Epic/issue number referenced
- [ ] All architectural decisions documented with rationale
- [ ] Complete list of files touched with descriptions
- [ ] Contract changes documented
- [ ] Test coverage documented
- [ ] Performance impact measured and documented
- [ ] Related memories linked with proper relations
- [ ] Architecture diagrams updated (if needed)
- [ ] Component documentation updated

---

## Architecture Integration Points

### Memory Backbone
- Every service serves or consumes the Memory Module
- Enforce data ownership and family sync rules
- Maintain device-local storage assumptions

### Event Hub Attachment
- Publish via `events/bus.py`
- Configure `events/dispatcher.py` and `events/handlers.py`
- Route into `pipelines/memory_bus.py`
- Never bypass shared event infrastructure

### Pipeline Discipline
- Reuse P01–P20 stages when possible
- For new stages:
  1. Add `pipelines/memory_px.py`
  2. Update `pipelines/memory_registry.py`
  3. Document in contracts and diagrams

### Policy & Safety Hooks
- Thread requests through `policy/memory_decision.py`
- Apply QoS gates
- Integrate safety monitors
- Confirm advisory signals terminate at P04

### Observability
- Emit receipts via `storage/receipts_store.py`
- Use structured logging with `structlog`
- Export Prometheus metrics
- Propagate `cognitive_trace_id`

---

## Common Pitfalls to Avoid

❌ **Skipping ADR validation** → Leads to architectural debt
❌ **Missing contract updates** → Breaking changes at runtime
❌ **Introducing simulation code** → Violates zero-tolerance policy
❌ **Ad hoc queues** → Bypasses event hub architecture
❌ **Forgetting advisory boundaries** → P04 executes, intelligence advises
❌ **Omitting cognitive_trace_id** → Breaks observability chain
❌ **Missing test coverage** → Production bugs
❌ **Skipping memory documentation** → Lost context for future work

---

## Tooling Shortcuts

### ADR & Contract Discovery
```bash
# Find ADRs
grep_search(query="<component>", includePattern="docs/architecture/decisions/**")

# Validate contracts
python k0/automation/lint_schemas.py

# Generate API docs
python k0/automation/generate_api_docs.py
```

### Architecture Navigation
```python
# Load diagram
mmd_ingest("<absolute_path>")

# Get summary
mmd_summary("<diagram_id>")

# Find adjacency
kg_neighbors(diagram="<diagram_id>", node_id="<node>")

# Trace flows
kg_paths(diagram="<diagram_id>", src="<src>", dst="<dst>", max_hops=6)
```

### Testing
```bash
# Run all tests
python -m ward test --path tests/

# Run component tests
python -m ward test --path tests/<layer>/<component>/

# Verbose output
python -m ward test --verbose

# Search tests
python -m ward test --search "<pattern>"
```

### Memory Operations
```python
# Search memories
mem_find(query="<search_term>", project="k1_intelligence")

# Read memories
mem_read_many(ids=["<id1>", "<id2>"])

# Link memories
mem_link(src_id="<src>", dest_id="<dst>", relation="<type>")
```

---

## Summary: The 5 Gates

1. **🚦 GATE 1**: ADR exists and is valid → Proceed to contracts
2. **🚦 GATE 2**: Contracts exist and validate → Proceed to implementation
3. **🚦 GATE 3**: Implementation matches contracts → Proceed to testing
4. **🚦 GATE 4**: Tests pass and cover requirements → Proceed to documentation
5. **🚦 GATE 5**: Memory documented and linked → Work complete ✅

**REMEMBER**: Each gate is a **BLOCKER**. Do NOT skip gates or proceed without validation.

```
