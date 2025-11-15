# 🧭 Intelligence Kernel — Rules of Engagement

**This is the governing rulebook for developing, modifying, or extending the intelligence kernel.**
**Proof-of-concept code is exempt from full process unless explicitly required.**
**No emojis in code files or commit messages.**

---

# 📋 Pre-Implementation: Design Workflow

**When designing modules, pipelines, or major architectural components, refer to:**

→ **`.github/instructions/design-workflow.instructions.md`** — Module & Pipeline Design Workflow

This covers the **5-step design process** BEFORE implementation:
1. Create Architectural Decision Records (ADRs)
2. Create Module Repository Structure
3. Write Authoritative Module README (13 sections)
4. Register Module in `whiteboard_module.md`
5. Link Module to Pipelines in `whiteboard.md`

**Key Artifacts:**
- `k0/pipelines/whiteboard.md` — Pipeline catalog, event bus architecture, topic registry
- `k0/pipelines/whiteboard_module.md` — Module template and registry
- `k0/modules/<module>/README.md` — Authoritative module specification
- `docs/architecture/decisions-K0/` — ADRs

**Use design workflow when:**
- Designing new modules (hippocampus, workspace, affect, arbitrator, etc.)
- Designing new pipelines (P01-P20)
- Adding features requiring architectural changes
- Creating reusable components for multiple pipelines

**After design is complete and ADRs are accepted:**
→ Proceed to the 5-Gate Implementation Workflow below (starting at GATE 1)

---

# 🚫 Zero-Tolerance Rules

* **No unrequested documentation** — Create design documents *only* when explicitly required.
* **No simulation code** — Do not fake timing, behavior, delays, or functionality.
* **No mock theater** — Use real components, real execution paths, and real tests.
* **Architecture Decisions Required** — Any code change must be backed by a formal architectural decision.
* **Seek clarity** — Ask questions instead of assuming intent.
* **Violations block acceptance** — Missing decisions, missing tests, excessive docs, or simulated behavior lead to rejection.

---

# 1️⃣ Universal Development Workflow (5-Gate System)

**Applies to every change**, regardless of complexity.

Use this gated process:

---

## 🚦 GATE 1 — Architectural Decision Validation

* Identify all architectural decisions relevant to the proposed change.
* If any are missing, unclear, or outdated → STOP and clarify or create new decisions.
* Verify that the change aligns with accepted and active decisions.
* Do not proceed without validated architectural grounding.

---

## 🚦 GATE 2 — Contract Discovery & Validation

* Identify all schema, interface, and protocol contracts that govern the change.
* Validate that contracts exist, are current, and accurately describe expected behavior.
* If gaps exist → STOP and create/update contracts before writing any production code.
* Ensure all contracts are consistent across system boundaries.

---

## 🚦 GATE 3 — Implementation (Contract-Aligned)

* Implement the feature to strictly comply with validated decisions and contracts.
* Do not write simulated, temporary, or mocked behavior.
* Ensure all logic includes observability hooks (tracing identifiers, structured logs, etc.).
* Re-check contracts during implementation; update if any divergences appear.
* Maintain correct dependency boundaries and avoid circular structures.

---

## 🚦 GATE 4 — Test Implementation

* Write integration-oriented tests that exercise real components.
* Avoid isolated mocking unless testing error boundaries or exceptional paths.
* Validate performance expectations and error handling.
* All tests must pass cleanly before moving to next gate.

---

## 🚦 GATE 5 — Documentation of Change

* Document:

  * The problem
  * Decisions made
  * Architectural impact
  * Files changed
  * Tests added
  * Performance characteristics
* Link change records with architectural decisions.
* Update architecture diagrams and module overviews when the change affects structure.

---

# Workflow Enforcement

Each gate is a blocker:

| Gate   | If Missing                                               |
| ------ | -------------------------------------------------------- |
| GATE 1 | Cannot continue (no decisions = no grounding)            |
| GATE 2 | Cannot implement (no contract clarity)                   |
| GATE 3 | Cannot test (implementation incomplete or non-compliant) |
| GATE 4 | Cannot finalize (tests failing or incomplete)            |
| GATE 5 | Work considered incomplete                               |

---

# 2️⃣ Architecture Overview (Generalized)

**Purpose of the Kernel:**
A production-ready orchestration system that manages agents, planning, execution, protocol adherence, and adaptation.
Built on strong architectural principles: actor-based concurrency, capability security, protocol validation, staged execution, and fault isolation.

### Core Components (General)

* **Agent Fabric** — Manages lifecycle, health, concurrency, and scheduling.
* **Orchestrator** — Multi-phase coordination across decision stages.
* **Planner** — Structured transformation pipeline (sketching → expansion → verification → commitment).
* **Protocol Compliance Layer** — Ensures components follow message-passing and behavioral contracts.
* **Learning Loop** — Captures outcomes and adjusts system behavior.

### Performance Goals

* Fast first response
* Predictable end-to-end latency
* Bounded memory footprint
* Deterministic behavior under load

---

# 3️⃣ Development Standards (Generalized)

### Coding Standards

* Follow consistent formatting and style conventions.
* Use explicit, structured error handling.
* Ensure code is traceable and readable with clear intent.
* Organize imports and modules with clarity and predictability.

### Version Control Standards

* Use clear branch naming conventions.
* PRs must include:

  * architecture impact
  * diagrams (if changed)
  * tests
  * references to architectural decisions
  * performance notes

### Testing Standards

* Prefer integration tests over unit tests.
* Avoid mocks except for boundary behavior.
* Validate performance characteristics.
* Maintain test isolation and repeatability.

### Observability Standards

* Include trace identifiers in all operations.
* Provide structured logs.
* Emit metrics for critical operations.
* Include tracing at component boundaries.

### Security & Privacy

* Use least-privilege access patterns.
* Enforce capability boundaries.
* Respect privacy classification levels.
* Log sensitive events with explicit audit semantics.
* Mask or redact identifiable data in logs.

### Configuration & Environment

* Centralize configuration.
* Use environment variables or configuration files for runtime settings.
* Do not hardcode secrets or environment-specific logic.

### Schema/Interface Generation

* Keep schemas separate from generated code.
* Ensure generated objects follow correct namespace patterns.
* Avoid import hacks; maintain clean module imports.
* Follow a consistent naming pattern for schema files and generated outputs.

---

# 4️⃣ Diagram and Documentation Playbook (Generalized)

### Diagram Guidance

* Keep diagrams syntactically valid.
* Include purpose and architectural context.
* Maintain consistent naming and file structure.
* Diagrams must pass validation before commit.
* Update usage trackers when diagrams change.

### Documentation Guidelines

* Create documentation **only when explicitly needed**.
* Keep architectural decisions in a single indexed location.
* Keep design references, diagrams, and change records discoverable.
* Avoid unnecessary text, verbose explanations, or duplicate documents.

---

# 5️⃣ Quick Reference Rules

### Root Directory

* Allowed: core configuration files, essential readme, license
* Forbidden: unstructured code or documentation

### Common Failures

| Problem                | Fix                                              |
| ---------------------- | ------------------------------------------------ |
| Architectural mismatch | Review decisions and realign                     |
| Failing tests          | Fix logic, not tests                             |
| Performance regression | Optimize blocking operations                     |
| Unclear ADR            | Rewrite with context, alternatives, consequences |

---

# 6️⃣ Instruction File Workflow (Generalized)

When uncertain:

1. Start with the main rules of engagement.
2. Use architectural decision documents for foundational logic.
3. Use service-design and contract guidelines for gated development.
4. Use test guidelines before writing tests.
5. Use documentation standards before writing docs.
6. Use diagram guidelines before editing diagrams.

---
