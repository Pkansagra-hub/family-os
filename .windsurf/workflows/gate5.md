---
description: # 5-Gate Gated Process (HARD BLOCKERS) — Windsurf Workflow
auto_execution_mode: 3
---

# 5-Gate Gated Process (HARD BLOCKERS) — Windsurf Workflow

## GATE 1 — ADR DISCOVERY & VALIDATION (STOP on fail)

**Goal:** Every change maps to an accepted ADR.

**Do**

1. Read stub file and find related ADR's
2. Locate ADRs in `docs/architecture/decisions/`.
3. Verify each has problem → options → decision → consequences; status is `ACCEPTED`/`IMPLEMENTED`.
4. Map ADR IDs to affected modules/files.

**Checks**

* Aligns with Spaces/Bands/Envelope model.
* ADR refs added to commit/PR template.

**Artifacts**

* ADR list with one-line mapping.

**Pass**

* All work items governed by accepted ADR(s).
  **Fail → STOP:** Missing/ambiguous ADR.

---

## GATE 2 — CONTRACT DISCOVERY & VALIDATION (STOP on fail)

**Goal:** Specs exist and validate before code.

**Do**

1. Discover/author contracts in `k1/contracts/**` or `k0/contracts/**` (OpenAPI/AsyncAPI/JSON Schema/FlatBuffers/policies).
2. Run validators/codegen; bump versions/changelogs.

**Checks**

* Envelope includes `cognitive_trace_id`, band, caps, policy_version.
* K1 does **not** implement K0 pipelines.

**Artifacts**

* Validation logs (green), contract versions, generated stubs (if any).

**Pass**

* Contracts valid, no drift from ADRs.
  **Fail → STOP:** Missing/invalid/drifting contracts.

---

## GATE 3 — IMPLEMENTATION (Contract-Compliant) (STOP on drift)

**Goal:** Code strictly matches ADRs/contracts; no simulation code.

**Do**

1. Implement only what specs authorize.
2. Propagate `cognitive_trace_id` across boundaries.
3. Enforce PEP/PDP, bands, capability checks.

**Checks**

* No `sleep()`/mock theater in prod paths.
* Bridge honors dual protocol (JSON primary, FlatBuffers secondary) and HTTP/2/batching where specified.

**Artifacts**

* Diffs with ADR/contract IDs in comments.

**Pass**

* Implementation mirrors contracts/ADRs; privacy/band guards present.
  **Fail → STOP:** Any spec/code drift—fix specs first.

---

## GATE 4 — TESTS (Integration > Unit; Budgets enforced) (STOP on fail)

**Goal:** Prove correctness + performance budgets.

**Do**

1. Write integration-first tests hitting K0 ports & K1 flows (avoid over-mocking; forbid `sleep()`).
2. Assert schema conformance and perf guardrails (TTFT ≤150 ms, E2E ≤2000 ms; K0 WAL ≤100 ms typical; mailbox p50 20–50 µs).

**Checks**

* Prometheus counters/histograms and OpenTelemetry spans present on critical paths.
* Privacy/band tests included.

**Artifacts**

* Green test run, coverage snapshot, perf summary (P50/P95).

**Pass**

* All tests pass; budgets respected.
  **Fail → STOP:** Failing tests or perf regressions.

---

## GATE 5 — MEMORY & DIAGRAMS (STOP if missing)

**Goal:** Commit the change to institutional memory and architecture views.

**Do**

1. Record concise change summary (epic/issue, ADRs, files, tests, perf deltas).
2. Update `.mmd` diagrams in `architecture_diagrams/` and validate.
3. Wire observability dashboards for new metrics/traces.

**Checks**

* No forbidden repo artifacts (stray docs/scripts).
* Bridge metrics present (queue depth, watermarks, batch latency, retries).

**Artifacts**

* Memory entry + validated diagram diffs.

**Pass**

* Memory + diagrams updated and validated.
  **Fail → STOP:** Missing updates.

---
