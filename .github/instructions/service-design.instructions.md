# Code Development Workflow (Universal)

## Scope: ALL Code Changes

This workflow applies to EVERY code change, regardless of size:

- New feature (large or small)
- Small bug fix
- New service/module
- Existing service modification
- New function/class
- Configuration changes
- Any production code path

If you are writing or modifying production code → **follow the 5-step gated process.**

### Examples of What This Covers

| Scenario                                  | Lines Changed | Follow 5-Step Process? |
|-------------------------------------------|---------------|------------------------|
| New service with API                      | 10,000        | Yes                    |
| Add new endpoint to existing service      | 200           | Yes                    |
| Fix bug in existing function              | 10            | Yes                    |
| Add new helper function                   | 50            | Yes                    |
| Refactor existing module                  | 500           | Yes                    |
| Add new configuration file                | 20            | Yes                    |
| Update data schema                        | 5             | Yes                    |
| Add new class/component                   | 300           | Yes                    |

**Exception:** Changes that only update documentation or comments (and do not change logic, data structures, configs, or behavior) may skip the full process.

---

## Purpose

Provide a **mandatory 5-step gated workflow** for all code development so that:

- Architectural decisions are explicit and discoverable.
- API/data contracts exist before implementation.
- Code matches contracts and system constraints.
- Comprehensive tests exist and actually run.
- Knowledge is preserved and traceable for future work.

## Baseline Reference Types (Conceptual)

Every codebase should have (even if organized differently):

- **Architectural decision records (ADRs)** — “Why is it built this way?”
- **Contracts** — API definitions, data schemas, policies, observability contracts.
- **Architecture diagrams** — High-level and component-level views.
- **Knowledge/Discovery system** — Could be a knowledge graph, search index, or curated index; used to find ADRs, contracts, modules, and relationships.
- **Testing standards** — What “good enough” looks like for tests.
- **Production policy** — Zero-tolerance rules (no simulation code, no undocumented behavior, etc.).

---

## 🚦 5-Step Gated Workflow (MANDATORY)

Each step is a **gate**.
You **do not proceed** until the current gate is satisfied.

---

### STEP 1: Architectural Decision Discovery & Validation — 🚦 GATE 1

**Objective:** Ensure there is a solid architectural foundation before changing or adding code.

#### Actions

1. **Discover relevant architectural decisions:**
   - Use whatever discovery you have: knowledge graph, full-text search, internal docs index, or ADR catalog.
   - Look for decisions tied to:
     - The component or feature you are touching.
     - The layer (e.g., API, orchestration, storage, infra).
     - Non-functional aspects (performance, security, reliability).

2. **Validate coverage:**
   - Does an ADR (or equivalent) exist for this feature/component?
   - Is its status active/accepted (not deprecated or superseded)?
   - Have you read any parent or related decisions?

3. **Understand context:**
   - How this component interacts with others.
   - Which decisions it depends on.
   - How changes could ripple through the system.

#### Decision Point

- ✅ Architectural decision exists, is current, and matches the intended change → proceed to Step 2.
- ❌ No architectural decision found, or it is clearly outdated → **STOP.**

#### If ADR/Decision Is Missing

- Capture the fact that work is blocked by a missing decision.
- Work with the architect or product owner to:
  - Define the problem and constraints.
  - List alternatives and trade-offs.
  - Decide on performance/security/operational targets.
- Write or update the architectural decision record.
- Only then return to Step 1 and validate again.

#### Gate 1 Checklist

- [ ] Relevant architectural decisions identified.
- [ ] Status is active/accepted.
- [ ] Related decisions reviewed.
- [ ] Decision(s) align with the requested work.

---

### STEP 2: Contract Discovery & Validation — 🚦 GATE 2

**Objective:** Ensure API/data/behavior contracts exist before implementation.

#### Actions

1. **Identify applicable contracts:**
   - Data schemas (requests, responses, events, storage records).
   - API definitions (endpoints, message formats, error codes).
   - Policy/permissions rules (who can do what).
   - Observability expectations (metrics, traces, logs required).

2. **Locate existing definitions:**
   - Use your discovery system to find specifications and schemas.
   - Reference any standard patterns used for similar components.

3. **Validate contracts:**
   - Check that the contracts are internally consistent.
   - Check that they match the current architecture decisions.
   - Confirm examples exist for key flows (happy path and typical errors).

#### Decision Point

- ✅ Contracts exist and match the architectural decisions → proceed to Step 3.
- ❌ Contracts are missing, incomplete, or clearly wrong → **STOP.**

#### If Contracts Are Missing or Incomplete

- Define the data and API shapes needed for this change.
- Create or update:
  - Data schemas.
  - API specifications.
  - Policy/permission rules.
  - Observability expectations (required metrics, traces, logs).
- Ensure examples are written for each critical interaction.
- Get contracts reviewed and accepted.
- Only then return to Step 2 and validate again.

#### Gate 2 Checklist

- [ ] All required contracts identified.
- [ ] Contracts clearly reference relevant decisions.
- [ ] Schemas are coherent and validated.
- [ ] Examples exist for main flows and error cases.
- [ ] Contract versioning or change tracking is updated.

---

### STEP 3: Implementation with Contract Compliance — 🚦 GATE 3

**Objective:** Write production-ready code that aligns with decisions and contracts.

#### Actions

1. **Pre-implementation understanding:**
   - Review architecture overviews and module maps.
   - Understand dependencies and ownership boundaries.
   - Identify which modules you may impact by changing this one.

2. **Follow established patterns:**
   - Respect layering (e.g., API → orchestration → domain → infrastructure).
   - Use existing patterns for concurrency, error handling, and retries.
   - Keep responsibilities aligned: no “God classes” or cross-cutting hacks.

3. **Implementation standards:**
   - No simulation code (no fake delays or dummy branches).
   - No hidden behavior not reflected in contracts.
   - Add appropriate observability:
     - Structured logs.
     - Trace/operation IDs propagated end-to-end.
     - Metrics where relevant (latency, error count, etc.).
   - Reference relevant architectural decisions in comments or module headers.

4. **Check for contract deviations:**
   - Compare implementation against contracts:
     - Any new fields?
     - Changed types or semantics?
     - New error conditions?
   - If anything deviates from the contract, update the contract and re-align, not just the code.

#### Decision Point

- ✅ Implementation matches contracts and decisions → proceed to Step 4.
- ⚠️ Deviations found → update contracts and decisions first, then continue.

#### Gate 3 Checklist

- [ ] Implementation adheres to all relevant contracts.
- [ ] No undocumented deviations.
- [ ] Observability is present and meaningful.
- [ ] Architectural decisions referenced where appropriate.
- [ ] Module boundaries and layering are respected.
- [ ] No simulation or “temporary hack” logic.

---

### STEP 4: Test Implementation — 🚦 GATE 4

**Objective:** Ensure behavior, contracts, and performance are verified.

#### Actions

1. **Review testing standards:**
   - Understand what is required (integration, unit, performance, property-based, etc.).
   - Check expected coverage levels and critical-path requirements.

2. **Design tests in this order of priority:**
   - **Integration tests** for real flows across components.
   - **Contract tests** that validate inputs/outputs against schemas.
   - **Error and edge-case tests** (invalid data, timeouts, failures).
   - **Performance tests** for latency and throughput where relevant.

3. **Organize tests clearly:**
   - Group by component and feature.
   - Keep fixtures realistic and reusable.
   - Avoid mocks unless testing specific failure scenarios or boundaries.

4. **Run the full suite (or relevant subset):**
   - All tests related to the feature.
   - Regression tests for nearby or dependent components.
   - Confirm that performance and resource goals are not regressing.

#### Gate 4 Checklist

- [ ] All new functionality covered by tests.
- [ ] Integration tests cover primary flows.
- [ ] Contract validation tests in place.
- [ ] Error paths and edge cases tested.
- [ ] Performance requirements tested (where applicable).
- [ ] All relevant tests pass.

---

### STEP 5: Memory & Documentation — 🚦 GATE 5

**Objective:** Preserve knowledge so future work is faster and safer.

#### Actions

1. **Record the change in the project knowledge base:**
   - Link to:
     - The feature or issue.
     - The architectural decisions used or updated.
     - The modules and files changed.
     - The contracts and tests involved.
   - Summarize:
     - The problem.
     - The decisions and trade-offs.
     - The impact on performance, security, or operations.

2. **Update architecture views where needed:**
   - Diagrams for components, flows, or dependencies.
   - Module or layer overviews.
   - Any cross-cutting documentation affected by the change.

3. **Verify coherence:**
   - Ensure there are no “orphan” elements (e.g., new modules with no documentation).
   - Ensure no new circular dependencies or unwanted couplings have been introduced.
   - Confirm that the recorded knowledge is discoverable (tagged, linked, indexed).

#### Gate 5 Checklist

- [ ] Change is documented with clear metadata (who/what/when/why).
- [ ] Files and components involved are listed.
- [ ] Contracts and tests added/changed are noted.
- [ ] Performance impact recorded (if applicable).
- [ ] Architecture diagrams updated if structure changed.
- [ ] Documentation is linked into the broader knowledge system.

---

## Architecture Integration Considerations (General)

When integrating with the broader system:

- Respect **data ownership** and boundaries between services and modules.
- Use shared messaging or event infrastructure instead of ad-hoc channels.
- Reuse existing pipeline stages or patterns when possible instead of inventing new ones.
- Ensure that policy, safety, and quality-of-service checks remain in the path.
- Maintain end-to-end **traceability** using shared identifiers.

---

## Common Pitfalls to Avoid

- Skipping architectural review → leads to incoherent system design.
- “Just changing one field” without updating contracts → fragile integrations.
- Using simulation/stub logic → drift between test and production behavior.
- Bypassing shared infrastructure (events, storage, policy) → unobservable and unsafe paths.
- Forgetting trace IDs or observability hooks → blind spots in debugging and operations.
- Not updating tests or documentation → future changes break silently.

---

## Knowledge & Discovery (Generalized)

If you have a knowledge graph, search index, or documentation hub, use it to:

- Find related architectural decisions for a component or feature.
- Discover which modules depend on the one you are changing.
- See which tests, contracts, or services relate to a given decision.
- Detect missing documentation (“orphan” components) or circular dependencies.

Use this discovery capability actively in:

- **Gate 1:** To find and validate architectural decisions.
- **Gate 2:** To find related contracts and examples.
- **Gate 3:** To understand dependencies and impact.
- **Gate 4:** To find existing test patterns and related coverage.
- **Gate 5:** To ensure the architecture and documentation remain coherent.

---

## Summary: The 5 Gates

1. **Gate 1 — Architecture:** A clear decision exists and is valid.
2. **Gate 2 — Contracts:** The interfaces and schemas are defined and current.
3. **Gate 3 — Implementation:** Code matches decisions and contracts.
4. **Gate 4 — Testing:** Behavior and performance are verified.
5. **Gate 5 — Memory:** The change is documented and linked into the system knowledge.

Each gate is a **hard blocker**.
If a gate fails → **do not proceed** until it is resolved.
