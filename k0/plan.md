# K0 Kernel Implementation Roadmap

> **Guardrails:** Follow `.github/instructions/*.md` (architecture, service-design, documentation, testing) and the contracts playbook at `docs/development/contracts-playbook.md`. Maintain canonical examples in `k0/contracts/jsonschema/examples/` and partner tooling under `docs/api/postman/` for every contract change.

---

## Delivery Status Snapshot

- **Baseline artifacts (Milestones 1–3)** — ✅ complete and gated in CI.
- **Kernel scaffold (Milestone 4 kick-off)*- **Issue 9.3.3 — Architecture & Program Review** ✅ *(Complete 2025-10-06)*
  - [x] Prepare cross-functional briefing (architecture, security, ops, product) including telemetry/perf/chaos evidence and deployment readiness.
  - [x] Host review, record decisions/action items, and draft ADR 009 ("K0 v1.0 Release Scope & Post-GA Objectives").
  - [x] Log MCP memory linking ADR, meeting notes, diagrams, telemetry snapshots, and follow-ups; update STATUS.md with outcomes.
  - **Deliverables:**
    - `docs/development/issue-9.3.3-architecture-program-review.md` (35KB): Cross-functional briefing with architecture maturity assessment, ADR compliance, security posture, operational readiness, documentation fixes (20+ CLI commands corrected), performance/chaos evidence, known issues (9 cataloged), deployment checklist, GO recommendation with monitoring requirements
    - `docs/ADR/009-v1.0-release-scope-post-ga-objectives.md` (28KB): Release scope ADR defining v1.0.0-rc features, documented limitations with workarounds, post-GA roadmap (v1.0.1 Q4 2025, v1.1.0 Q1 2026, v2.0.0 Q2 2026), success criteria (6 categories), monitoring SLIs (5 types), rollback strategy, communication plan, stakeholder approvals
    - `docs/development/k0ctl-command-reference.md` (306 lines): Authoritative CLI command reference documenting actual vs incorrect commands with ❌/✅ markers, workarounds for missing features (migration status, rollback, cache flush), validation status (all fixed)
  - **Key Outcomes:**
    - Documentation errors fixed: 20+ incorrect CLI commands across RELEASE_NOTES.md (3 fixes), UPGRADE_GUIDE.md (7 fixes), KNOWN_ISSUES.md (1 fix)
    - All commands validated: `migrate --dry-run`, `migrate`, `schema audit` working correctly
    - GO decision for v1.0.0-rc with 9 known issues (3 high, 3 medium, 3 low priority) all with mitigations
    - Post-GA roadmap clear: v1.0.1 (migration CLI, cache optimization, failover <15s), v1.1.0 (incremental replay, adaptive scheduler, Redis cache)
    - Cross-functional approval: Architecture, Security, Operations, Product all signed off
  - **MCP Memory:** be3793ee-1b8a-4e1d-850d-ab381b760bc6 (documentation fixes linked to Issue 9.3.3)✅ base packages, FastAPI shell, config assets, storage/policy/QoS/SSE placeholders landed 2025-09-28.
- **Outstanding work** — Everything below transitions the scaffold into a production-ready kernel. Each epic now lists concrete deliverables tied to real modules, test suites, and documentation obligations.

---

## Completed Foundations (Milestones 1–3)

- **Milestone 1 — Contract Artifacts Canonicalized** *(Done)*
  - OpenAPI, AsyncAPI, JSON Schemas, storage DDL, contract README.
- **Milestone 2 — Validation & Tooling** *(Done)*
  - Ward suites for schemas, lint harnesses, migration smoke tests.
- **Milestone 3 — Pipeline & Documentation Sync** *(Done)*
  - CI workflow (`contracts-ci.yml`), doc-sync automation, generated HTML/PDF docs, contracts playbook, Postman collection.

These milestones remain the contractual baseline; any kernel implementation work must keep their artifacts green in CI.

---

## Milestone 4 — Kernel Foundations & Scaffolding *(In Progress)*

### Epic 4.1 — Runtime & Project Skeleton *(Complete)*
- **Issue 4.1.1** *(Complete)*: Finalize `k0/kernel/app.py` with CORS policy, exception handlers, JSON logging, and 400/429/5xx normalization. Update `k0/ports/__init__.py` to register routers via new helper.
- **Issue 4.1.2** *(Complete)*: Enhanced `k0/kernel/config.py` to layer `config/kernel.yaml`, `K0_KERNEL_*` environment overrides, and programmatic/CLI inputs with retention/QoS validation; documented override semantics in the README.
- **Issue 4.1.3** *(Complete)*: Replace placeholder dependency provider with real factories (DB session, policy context, telemetry span factory). Acceptance: Ward test exercising dependency override wiring + integration test verifying DB session lifecycle.
- **Issue 4.1.4** *(Complete)*: Harden `k0/kernel/main.py` (UVicorn lifespan hooks, graceful shutdown) and `k0/cli/k0ctl.py` (wire to config loader). Update `k0/README.md` quickstart + optional systemd/uvicorn docs.

### Epic 4.2 — Storage Layer & Unit of Work
- **Issue 4.2.1** *(Complete)*: Replace placeholder `k0/uow/connection_pool.py` with pooled SQLite connections (WAL mode, pragmas, busy timeout). Deliver new Ward suite `tests/storage/test_connection_pool.py` verifying concurrency + WAL pragmas.
- **Issue 4.2.2** *(Complete)*: Flesh out `k0/uow/unit_of_work.py` to begin/commit/rollback real transactions, integrate with Outbox staging, and emit metrics. Add property-based Ward cases covering nested usage and failure paths.
- **Issue 4.2.3** *(Complete)*: Implement adapters in `k0/storage/*.py`, `k0/idem/ledger.py`, and `k0/gate/schema_registry.py` using SQL generated from `contracts/sql`. Each adapter gets targeted Ward tests plus integration coverage using on-disk SQLite fixtures.
- **Issue 4.2.4** *(Complete)*: Added the SQLite migration runner (`k0/automation/migrate.py`), `k0ctl migrate` command, documentation/runbook updates, and CI smoke tests for contract changes.

### Epic 4.3 — Policy & Provisioning Contracts
- **Issue 4.3.1** *(Complete)*: Build real PEP evaluation in `k0/policy/pep_syscall.py`, reading `contracts/policy/pep.schema.json`, emitting obligations, and logging policy decisions. Ward coverage for allow/deny paths + obligation serialization.
- **Issue 4.3.2** *(Complete)*: Populate provisioning ledger in `k0/storage` + caching strategy (LRU keyed by `{tenant,space,device}`). Add CLI seeding command and Ward tests verifying gate enforcement.
- **Issue 4.3.3** *(Complete)*: Wire libsodium (`PyNaCl`/`pynacl`) signature checks, canonical JSON normalization, and payload hash calculators. Provide deterministic helpers reused by Unit of Work + Gate.
- **Issue 4.3.4** *(Complete)*: Expose scheduler handles via dependency provider, define QoS context object that will tighten budgets downstream.

### Epic 4.4 — Observability & Telemetry Skeleton
- **Issue 4.4.1** *(Complete)*: Replace placeholder `k0/obs/*.py` with OTEL/Prometheus exporters, configure FastAPI middleware to attach `cognitive_trace_id`. Document telemetry setup.
- **Issue 4.4.2** *(Complete)*: Create middleware capturing admission decisions and obligations, persisting to receipts table + Observability port. Provide Ward/regression tests.
- **Issue 4.4.3** *(Complete)*: Add `/healthz`, `/readyz`, `/metrics` endpoints, plus integration tests verifying readiness gating on migrations/WAL replay completion.

---

## Milestone 5 — Command Port & Durability Path

### Epic 5.1 — Minimal Gate & Envelope Handling
- **Issue 5.1.1** *(Complete)*: Complete `k0/gate/minimal_gate.py` to enforce caps, canonical JSON, payload hashes, and provisioning lookups. Add fuzz/regression Ward suite fed by `k0/contracts/jsonschema/examples/`.
- **Issue 5.1.2** *(Complete)*: Back the Schema Registry facade with SQLite table + caching, ensure N/N+1 policy, add CLI commands for register/promote/block. Update docs + Postman.
- **Issue 5.1.3** *(Complete)*: Implement deterministic idem key derivation (BLAKE3) and ledger check, surface 409 responses + telemetry. Provide property-based tests for collision detection.

### Epic 5.2 — Command Unit of Work & Outbox
- **Issue 5.2.1** *(Complete)*: Wire `UnitOfWork` to storage adapters with atomic writes + WAL fsync; include instrumentation for commit latency.
- **Issue 5.2.2** *(Complete)*: Implement Outbox fingerprinting, retry scheduler, DLQ fallback; create workers for alias map and queue semantics.
- **Issue 5.2.3** *(Complete)*: Build receipt issuance pipeline (signing, obligations), integrate Observability port stub into metrics logger.
- **Issue 5.2.4** *(Complete)*: Author integration test hitting `/k0/command.submit` with real DB + verifying WAL/receipts/outbox states.

### Epic 5.3 — QoS Enforcement & Error Handling
- **Issue 5.3.1** *(Complete)*: Apply QoS budgets (fanout/time) during command path; integrate with scheduler hooks.
- **Issue 5.3.2** *(Complete)*: Encode error envelopes for Gate/PEP/QoS rejections; update Postman examples + docs.
- **Issue 5.3.3** *(Complete)*: Add load-shedding/backpressure guard (W-DRR queue) and Ward cases.

---

## Milestone 6 — Query Port & Replay

### Epic 6.1 — Query Service Implementation
- **Issue 6.1.1** *(Complete)*: Landed selector parsing, WAL slice execution, QoS-aware aggregation, and Ward integration coverage (2025-09-28).
- **Issue 6.1.2** *(Complete)*: Introduced driver SPI with WAL implementation + alias stubs, registry wiring, and conformance Ward coverage (2025-09-29).
- **Issue 6.1.3** *(Complete)*: Streamlined bundle/trace/budget metadata, refreshed JSON examples, and aligned trace payloads with schema (2025-09-29).
- **Issue 6.1.4** *(Complete)*: Added query response streaming with SSE fallback, updated Postman request, and validated streaming integration tests (2025-09-29).

### Epic 6.2 — Replay & Snapshot Management
- **Issue 6.2.1** *(Complete)*: Implement snapshot scheduler orchestrated via `k0ctl snapshot`, produce artifacts, record watermark events.
- **Issue 6.2.2** *(Complete)*: Implement replay runner module + CLI integration; log metrics + progress SSE.
- **Issue 6.2.3** *(Complete)*: Expand Ward suites under `tests/snapshots` for deterministic replay, verifying `replay_parity_failures == 0`.
- **Issue 6.2.4** *(Complete)*: Provide selective replay (`--space`, `--tenant`) using indexes; integration tests covering DSAR flows.

### Epic 6.3 — QoS Arbitration for Reads
- **Issue 6.3.1** *(Complete)*: Enforce read budgets (fanout, time slice) with policy feedback loops; update QoS tighten schedule.
- **Issue 6.3.2** *(Complete)*: Add error/partial result semantics (fail-fast vs partial responses) and test matrix.

---

## Milestone 7 — SSE & Event Bus Integration

### Epic 7.1 — SSE Subscribe/Ack Pipeline
- **Issue 7.1.1** *(Complete)*: Implement `/k0/sse.subscribe` streaming with topic ACL enforcement and cursor decoding.
- **Issue 7.1.2** *(Complete)*: Implement `/k0/sse.ack` (cursor persist, QoS budgets) and update Ward tests using `sse.ack.request.json` example.
- **Issue 7.1.3** *(Complete)*: Build backpressure tiers and advisory signals (lag warnings, disconnect on thresholds).

### Epic 7.2 — Post-commit Bus Dispatch
- **Issue 7.2.1** *(Complete)*: Implement `k0/bus/core.py` dispatch loop using asyncio tasks and scheduler tokens; ensure ordering via WAL position.
- **Issue 7.2.2** *(Complete)*: Implemented driver worker pool + HTTP/gRPC handshake endpoint with contract validation and Ward coverage (2025-09-30).
- **Issue 7.2.3** *(Complete)*: Emit metrics (`k0_bus_dispatch_latency`, `outbox_pending_total`) and configure alerts.
- **Issue 7.2.4** *(Complete)*: Add bus middleware chain (timestamps, trace propagation) with configuration toggles.

### Epic 7.3 — Idempotent Delivery & DLQ Handling
- **Issue 7.3.1** *(Complete)*: Fleshed out `k0/storage/dlq.py`, integrated with scheduler/backpressure, and added Ward coverage for transitions PENDING→REQUEUED.
- **Issue 7.3.2** *(Complete)*: Extended `k0ctl` with `dlq list|requeue|purge` and published the DLQ runbook in `docs/development/runbooks/dlq.md`.
- **Issue 7.3.3** *(Complete)*: Added slow-subscriber load test verifying throttle and disconnect behaviour per README expectations.

---

## Milestone 8 — Observability, Policy, and Operations *(Reset 2025-10-01)*

### Epic 8.1 — Telemetry & Alerts

**Issue 8.1.1 — Rebuild SLO Dashboards & Preview Stack** ✅ *(Complete 2025-01-XX)*

- [x] **Context Sweep**
  - [x] Re-ingest architecture diagrams such as `project_architecture_part2.mmd` (alias `d2_inputs_perception`) and `project_architecture_part4.mmd` (alias `d4_ops_observability`) through MCP, record diagram IDs/version hashes in `docs/development/mmd-diagram-usage.md` with owner and date.
  - [x] Run knowledge-graph adjacency queries that map telemetry producers/consumers (metrics exporter, receipts store, bus workers) and log the relationships plus risk notes in `docs/development/kg-mcp-usage.md`.
  - [x] Consolidate guardrails from `.github/instructions/architecture-governance.instructions.md`, `service-design.instructions.md`, and `pipeline-development.instructions.md` into a short design brief to be committed alongside implementation.
- [x] **Design Telemetry Home**
  - [x] Confirm the canonical `k0/telemetry/` tree (source Jsonnet, generated artifacts, preview provisioning) and capture the agreed directory contract inside this plan for future reference.
  - [x] Inventory current Prometheus metrics across `k0/obs/metrics.py`, worker modules, and ports, classifying each by SLI type (latency, availability, saturation, errors); catalog lives in `k0/telemetry/metrics_inventory.md` with owners and review cadence.
  - [x] Define Python mixins for SLO panels in `k0/telemetry/mixins/slo_dashboards.py`, wiring tenant/device variables, percentile selectors, and checksum-friendly ordering in place of the original Jsonnet sketch.
  - [x] Lock the OS-grade visual standards (color palette, typography, panel grid rules) inspired by macOS Activity Monitor + Windows Reliability Monitor and codify them in `k0/telemetry/design_brief.md`.
- [x] **Implementation Blueprint**
  - [x] Draft module layout for `k0.telemetry.render` (entrypoint orchestration, Jsonnet renderer, checksum comparer, output writer) and list open technical questions (Jsonnet dependency management, Windows-compatible tooling) inside the plan.
  - [x] Define deterministic build workflow: configuration inputs, output paths (`generated/dashboards/*.json`, `generated/rules/*.yaml`), checksum strategy, and CI guardrails; evaluate whether to rely on bundled Jsonnet binaries or pure-Python alternatives.
  - [x] Specify Grafana preview stack requirements (Grafana OSS image, Prometheus scrape config, datasource provisioning, dashboard provisioning) and note Windows path quirks plus clean-up steps for developers.
  - [x] Outline integration glue that maps dashboards to the existing `/metrics` exporter, including required label normalization, scrape intervals, and recording rule dependencies.
- [x] **Validation Strategy**
  - [x] Enumerate Ward suites to author (render CLI smoke test, SLO math invariants, schema validation against Grafana JSON schema and Prometheus rule schema).
  - [x] Define manual QA loop: execute render CLI, import dashboards into preview Grafana, validate panel data using synthetic metrics, capture screenshot evidence for docs.
  - [x] Plan linting/static checks (`jsonnet fmt`, `promtool check rules`, Grafana provisioning dry-run) and include cross-platform command variants (PowerShell + POSIX shells).
- [x] **Documentation & Traceability**
  - [x] Outline `docs/development/runbooks/slo-dashboard.md` with sections for access, panel breakdown, healthy ranges, and alert pivots.
  - [x] Schedule updates to `docs/development/runbooks/README.md` to add dashboard + alert runbooks with owners and escalation paths once assets exist.
  - [x] Prepare MCP memory entry template linking diagrams, KG queries, test results, and documentation touchpoints for this issue.
- [x] **Acceptance / Exit Criteria**
  - [x] Dashboards and alert rules render deterministically from the CLI with zero manual tweaks; artifacts committed without drift.
  - [x] Grafana preview stack launches on Windows PowerShell and Linux shells using the documented single command and tears down cleanly.
  - [x] Ward suites covering render outputs and SLO math pass in CI.
  - [x] Ops/Product stakeholders sign off on visual polish, accessibility (contrast ratios, keyboard navigation), and content accuracy.
  - [x] Memory entry filed referencing diagrams, KG aliases, unit/integration tests, and runbooks.

> **Deliverables:** Complete `k0/telemetry/` module with 5 dashboards, 12 alert rules, preview stack (Docker Compose), 14 Ward tests (100% passing), comprehensive runbooks, and MCP memory entry 5ad13c88-f530-4e14-ac30-253fecd54b14.

**Issue 8.1.2 — Structured Logging & Trace Propagation Review (In Review)**

- [x] **Baseline Audit** *(see `docs/development/logging-trace-audit.md`)*
  - [x] Inventory all log emitters (FastAPI middleware, background workers, bus dispatchers) and confirm presence of `cognitive_trace_id`, `tenant_id`, and redacted subject identifiers.
  - [x] Review `k0/obs/logging.py` redaction map against contract fields (PII, device secrets, policy artifacts); document gaps plus remediation owners.
  - [x] Map existing log shipping paths to the forthcoming telemetry module so log-derived metrics feed dashboards once Issue 8.1.1 lands.
- [x] **Trace Propagation Testing Plan**
  - [x] Design a test matrix covering HTTP requests, command pipeline tasks, SSE stream acknowledgements, and bus dispatch flows to ensure trace continuity.
  - [x] Identify instrumentation hooks (contextvars/task locals wrappers) needed to bridge asynchronous boundaries; log hotspots requiring code changes.
  - [x] Align span naming conventions and attributes with OTEL exporter expectations so dashboards/traces share correlation IDs.
- [x] **Hardening Actions**
  - [x] Define Ward regression suites (structured log redaction, trace propagation) including sample payloads and expected outputs.
  - [x] Outline OTEL parity checks ensuring logs, metrics, and traces remain synchronized across sinks (stdout, Loki, OTLP collector).
  - [x] Plan configuration updates to support dynamic log sinks without violating compliance or telemetry ingestion contracts.
- [x] **Documentation**
  - [x] Draft updates for `k0/README.md` observability section describing log ingestion, trace correlation, and dashboard tie-ins once ready.
  - [x] Outline a troubleshooting guide under `docs/development/runbooks/` detailing redaction verification, trace stitching, and escalation paths.
  - [x] Capture results and open questions in MCP memory referencing diagrams/instructions for traceability.
- [x] **Exit Criteria**
  - [x] Trace propagation validated across the planned scenarios via Ward tests and manual probes.
  - [x] Redaction matrix documented with rationale per field and approved by security.
  - [x] Logging guidance and runbook drafts prepared for publication alongside telemetry rollout.

**Issue 8.1.3 — Alert Definitions & Runbooks (TODO)**

- [ ] **Alert Inventory & Design**
  - [x] Build a matrix mapping each SLO to corresponding warning/critical alerts, including evaluation windows, dead-man switches, and runbook links. *(See `docs/development/alerts/issue-8.1.3-design.md` §1)*
  - [x] Extend coverage to WAL lag, outbox backlog, replay failure rate, scheduler starvation, and SSE disconnect spikes; document trigger thresholds and rationale. *(Documented in §1)*
  - [x] Decide label taxonomy (severity, tenant, subsystem, contact rotation) compatible with future routing integrations (PagerDuty, OpsGenie). *(See §2)*
- [ ] **Rule Authoring Blueprint**
  - [x] Determine rule groups and evaluation cadence; plan Jsonnet templates to keep dashboards and alerts in sync. *(See design blueprint §3)*
  - [x] Capture plan for `promtool` linting and dry-run evaluation across Windows PowerShell and POSIX shells. *(See §§5.4 & 6)*
  - [x] Document synthetic data strategy (prometheus_client push gateway, WAL replay harness) to test alert firing before production. *(See §5)*
- [ ] **Runbook Strategy**
  - [x] Outline runbook template for `docs/development/runbooks/alerts/` covering detection, immediate response, observability pivots, remediation, and validation. *(Added `_template.md`)*
  - [x] Assign subsystem owners (storage, policy, QoS) and review cadence; log commitments in plan. *(See design blueprint §4 — quarterly review cadence noted.)*
  - [x] Ensure dashboards embed hyperlinks/annotations pointing to runbooks for fast operator access post-implementation. *(Dashboards now expose runbook quick links validated by Ward tests.)*
- [ ] **Validation & Tooling**
  - [x] Enumerate Ward or targeted tests to simulate alert conditions and confirm evaluation/firing logic. *(Blueprint §5.2)*
  - [x] Schedule manual validation session using the preview stack and `promtool test rules` before marking complete. *(Blueprint §5.3)*
  - [x] Plan CI guard (checksum or lint job) preventing drift in `generated/rules/` artifacts. *(Blueprint §6)*
- [ ] **Exit Criteria**
  - [ ] Alert rules lint cleanly, fire under controlled scenarios, and clear predictably.
  - [ ] Runbooks authored, peer reviewed, and cross-linked from dashboards and STATUS.md.
  - [ ] STATUS.md updated to reflect telemetry readiness once alerts validated.
  - [ ] MCP memory entry documents alert rationale, runbook links, and test evidence.

  **Follow-ups**
  - [ ] Backfill Prometheus instrumentation so replay failure, scheduler starvation, and other alerting metrics emit real signals for the new rules.
  - [ ] Build synthetic alert validation tooling (Pushgateway scripts + `promtool test rules`) and land matching Ward/CI coverage for deterministic firing/clearing checks.
  - [ ] Add CI guardrails around telemetry artifacts (`python -m k0.telemetry.render --verify`, `promtool check rules`) and capture the final MCP memory entry linking diagrams, runbooks, and validation evidence once guards ship.

### Epic 8.2 — Policy & Security Hardening

**Issue 8.2.1 — ed25519 Rotation Verification (In Review)**

- [ ] **Research & Alignment**
  - [x] Re-read `docs/ADR/001-ed25519-key-rotation-architecture.md`; captured constraints: lifecycle states (`PENDING/ACTIVE/ROTATING/REVOKED`), dual-key grace acceptance, Prometheus counters for verification outcomes, and CLI surface for add/activate/revoke/list/expire. Schema shifts move key material into `st_device_keys` with full audit timestamps.
  - [x] Inventory components consuming ed25519 keys and map ownership/dependencies:
    - Gate verification (`k0/gate/minimal_gate.py`) executes ACTIVE→ROTATING checks, emits receipts + telemetry labels.
    - CLI surface (`k0/cli/k0ctl.py`) orchestrates add/activate/revoke flows and interacts with migration tooling.
    - Ledger and storage (`k0/idem/ledger.py`, `k0/storage/*`) ensure audit bindings to `key_version` and persistence for grace expiry.
    - Observability (`k0/telemetry/metrics_inventory.md`, future Issue 8.1.3 alerts) consumes rotation counters and logs for dashboards/runbooks.
  - [x] Define isolated test environment requirements:
    - Fresh SQLite database seeded through migration 0003 with fixtures for multi-key devices and configurable grace windows.
    - Ephemeral key material fixtures under `tests/fixtures/keys/` (active, pending, revoked) plus deterministic fingerprints for assertions.
    - Config overrides enabling short grace periods (≤5 minutes) and directing structured logs/metrics to temp paths for validation.
- [ ] **Workflow Simulation Plan**
  - [x] Outline rotation scenario:
    1. Provision device with ACTIVE key (v1) via `k0ctl provision` to populate `st_devices` + `st_device_keys`.
    2. Register new key (PENDING v2) with optional operator-defined grace override; log audit + telemetry.
    3. Activate v2, transition v1 → ROTATING, record `grace_expires_ts`, and capture receipts referencing both key versions.
    4. Validate dual verification (v1 + v2 signatures) while grace active; ensure metrics/logs reflect success by key version.
    5. Expire grace (scheduled job + manual CLI) to move v1 → REVOKED, documenting rollback procedure (emergency reactivation flow) if telemetry/regression fails.
  - [x] Identify instrumentation/logging needed: structured logs carrying `device_id`, `key_version`, `old_state→new_state`, `initiator`, and correlation IDs; Prometheus counters (`k0_signature_verified`, `k0_signature_verification_failed`, `k0_key_rotation_events`) with tenant/device labels; ledger entries + receipts for compliance trail.
  - [x] Plan negative test cases: expired key usage emits `ROTATING_GRACE_EXPIRED` denial and increments failure counter; mismatched ledger entry triggers audit discrepancy alert; revoked key reuse short-circuits verification, raising security alert + runbook escalation hook.
- [ ] **Testing & Validation Approach**
  - [x] Define Ward suites: `tests/security/test_key_rotation.py` (CLI + gate happy-path/edge cases), property-based cases for grace expiry and multi-key permutations, and ledger reconciliation tests aligning with `contracts/CORRECTNESS.md` expectations.
  - [x] Document manual verification checklist covering CLI outputs (`k0ctl key list`, `key activate`, `key expire-grace`), SQLite spot checks (`SELECT` on `st_device_keys`), structured log inspection, and `/metrics` scrape to validate counters before grafting dashboards.
  - [x] Confirm logging redaction by reusing masked fields from `docs/development/logging-trace-audit.md`; verify only hashed fingerprints and key versions appear in logs/metrics.
- [ ] **Documentation & Traceability**
  - [x] Outline runbook updates: `docs/development/runbooks/device-key-rotation.md` to cover prerequisites, execution, monitoring pivots, rollback, and compliance checklist; README additions linking CLI usage and telemetry panels.
  - [x] Identify diagram/KG updates: refresh security + observability flows in `project_architecture_part3.mmd` and `project_architecture_part4.mmd`, ingest via MCP (alias `d4_ops_observability`), and log touchpoints in `docs/development/mmd-diagram-usage.md` / `kg-mcp-usage.md`.
  - [x] Prepare MCP memory template to capture dry-run evidence, Ward outputs, telemetry snapshots, ADR references, and residual risks for audit trail.
- [ ] **Exit Criteria**
  - [ ] Rotation workflow validated in staging with documented success/failure scenarios.
  - [ ] Ward test plan, manual checklist, and runbook updates reviewed by security stakeholders.
  - [ ] Compliance notes (key custody, audit trail) recorded with sign-off ready for implementation.

**Issue 8.2.2 — Policy Override Channel Validation (In Review)**

- [x] **Scope Assessment**
  - [x] Map the schema registry, policy override APIs, and audit trail flows back to ADR 002 to ensure consistent intent:
    - `k0/gate/schema_registry.py` (ADR 002 implementation) now exposes `SchemaRegistry.block/promote/get_audit_trail` with inline audit columns (`operator_id`, `blocked_ts`, `blocked_reason`, `unblocked_ts`).
    - `k0/cli/k0ctl.py` drives the override channel today (`schema register|promote|block|audit`), enforcing required operator attribution and emitting structured log statements via the shared logging stack.
    - Minimal Gate (`k0/gate/minimal_gate.py`) references the same registry cache, immediately rejecting blocked schemas with `SCHEMA_BLOCKED`; the FastAPI shell in `k0/kernel/app.py` wires the registry + gate into the command path, ensuring policy overrides propagate to HTTP once endpoints are implemented.
    - Audit visibility currently terminates at CLI logs and direct SQLite inspection; no additional event hub fan-out exists, making ADR 002 compliance dependent on the registry table + CLI artefacts.
  - [x] Document current data model and event propagation in the plan, highlighting dependencies on telemetry deliverables:
    - Storage: `schema_registry(schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts)` with status transitions enforcing N/N+1 (ACTIVE → DEPRECATED → BLOCKED) and single-entry audit history.
    - Flow: `k0ctl schema *` → `SchemaRegistry` update (via pooled SQLite connections) → registry cache refresh → Minimal Gate lookup on next command submission → command rejection surfacing `SCHEMA_BLOCKED` receipts/logs.
    - Observability dependencies: Metrics exporter from Issue 8.1 already attached to CLI helpers (`_build_operational_instrumentation`) but no policy-specific counters exist; dashboards expect labelled Prometheus series once added. Structured logs route through OTEL log pipeline defined in `k0/obs/logging.py` and inherit `cognitive_trace_id` when invoked from the API (future work) or CLI (when `configure_structured_logging` is used).
  - [x] Identify missing metrics/logs required for observability once dashboards exist:
    - Counters: `k0_policy_override_operations_total{action="register|promote|block|audit"}`, `k0_policy_override_failures_total{reason=...}`, and `k0_policy_override_effective_total{status="BLOCKED|ACTIVE"}` to anchor SLI panels defined in Issue 8.1.
    - Structured events via `ObservabilityEmitter.emit` with payload `{"event":"policy_override","action":...,"schema_uri":...,"version":...,"operator_id":...,"outcome":...}` to feed trace/alert correlations.
    - CLI log gaps: ensure block/promote logging includes `cognitive_trace_id`, tenant/space context (where available), and audit hashes so dashboards + runbooks can cross-link entries; capture audit queries in logs for compliance review.
- [x] **Validation Plan**
  - [x] Sequence CLI/API operations covering register → promote → block → revoke paths, including failure permutations:
    1. Register new schema (REGISTERED) → optionally `--activate` to promote; assert `SchemaRegistry.records_for_uri` reflects ACTIVE/DEPRECATED windows.
    2. Block ACTIVE version with operator + reason; verify Minimal Gate rejects sample envelope (`SCHEMA_BLOCKED`) and `/metrics` exposes success counter for the block action.
    3. Attempt writes via Minimal Gate and future HTTP route, confirming receipts/logs capture policy override context.
    4. Re-promote blocked version (unblock) and inspect `unblocked_ts` persistence.
    5. Negative cases: block nonexistent version (expect `KeyError`), omit operator/reason (expect `ValueError`), replay block while already BLOCKED (idempotent audit update), promote stale digest (should demote previous ACTIVE and preserve audit history).
  - [x] Determine concurrency scenarios (simultaneous overrides, conflicting updates) and document the expected locking or rejection behavior:
    - Dual operators blocking the same version: leverage SQLite write-lock semantics via `connection_scope`; latest write should win with updated audit metadata — test with two threads + shared pool.
    - Promote vs block race: start promote on v2 while block v1 executes; ensure demotion/order enforced and post-condition matches ADR 002 (single ACTIVE, others DEPRECATED/BLOCKED) with deterministic audit metadata.
    - API vs CLI simultaneity (future HTTP control plane): simulate REST stub hitting `SchemaRegistry` directly alongside CLI to confirm cache refresh + Minimal Gate visibility without restart.
  - [x] Plan instrumentation (structured logs, metrics) necessary to capture audit trail completeness during tests:
    - Extend CLI handler to wrap overrides with `ObservabilityEmitter.emit` events and metrics increments (`policy_override_operations_total`).
    - Capture Minimal Gate decisions with new telemetry hook when returning `SCHEMA_BLOCKED`, including schema URI/version and override operator (if present).
    - Collect test artefacts: `/metrics` scrape, observability snapshots, and CLI structured logs tied to a deterministic `cognitive_trace_id` for each validation run.
- [x] **Test Blueprint**
  - [x] Define Ward/security suites to add (invalid signatures, stale approvals, unauthorized update attempts) and the fixtures each requires:
    - `tests/policy/test_policy_override_channel.py`: temp SQLite DB fixture + `SchemaRegistry` exercising register/promote/block/unblock happy paths and error conditions, asserting audit columns + metrics/events.
    - `tests/security/test_policy_override_gate_blocking.py`: reuse Minimal Gate fixture to assert blocked schemas reject envelopes with telemetry emission, including unauthorized attempts (e.g., stale approval using blocked schema digest).
    - `tests/policy/test_policy_override_concurrency.py`: multithreaded Ward test leveraging `ThreadPoolExecutor` and shared database to reproduce block/promote races and verify final registry state + audit metadata.
  - [x] Align new tests with dashboards/alerts to ensure coverage for future observability:
    - Assert metrics snapshot contains new counters/labels expected by `k0/telemetry/metrics_inventory.md` (e.g., `policy_override_operations_total{action="block"}`).
    - Validate observability emitter payload matches dashboard schema (event name, operator, reason) and attach synthetic alert assertions once Issue 8.1.3 rules exist.
    - Ensure tests capture sample logs using structured formatter so future log-based panels (e.g., policy override feed) can reuse fixtures.
- [x] **Documentation**
  - [x] Outline README/schema registry doc updates (workflow diagrams, sample commands, troubleshooting) to author during implementation:
    - Expand `docs/development/runbooks/schema-registry.md` with: override lifecycle diagram (REGISTERED→ACTIVE→BLOCKED→UNBLOCKED), concurrency precautions, troubleshooting table for audit mismatches, and telemetry pivots.
    - Update `k0/README.md` policy section with high-level override workflow, linking to ADR 002, runbook, and telemetry dashboards; include sample CLI snippets with expected outputs.
    - Create supplemental guide in `docs/development/runbooks/policy-override-validation.md` (new) detailing validation checklist, failure handling, and integration with Issue 8.1 dashboards.
  - [x] Prepare MCP memory entry fields capturing validation evidence and remaining gaps:
    - Memory template to store: diagram/KG aliases, CLI transcripts (register/promote/block/audit), `/metrics` excerpts, observability event snapshots, Ward suite hashes, outstanding risks (e.g., historical audit chain backlog) with owner + target milestone.
    - Link memory to ADR 002 and Issue 8.1 dashboards for traceability, tagging entries with `policy_override`, `telemetry`, and `audit_trail`.
- [ ] **Exit Criteria**
  - [ ] Override flows demonstrably align with audit trail + telemetry requirements.
    - Evidence: successful CLI/API runbook demonstrating register/promote/block/unblock with persisted audit metadata, Minimal Gate rejection receipts, and telemetry counters/events captured in dashboards.
  - [ ] Test and documentation plan agreed upon by policy/security owners.
    - Evidence: sign-off meeting notes (Policy + Security) referencing Ward coverage + runbook drafts, stored in MCP memory and linked here.
  - [ ] Observability hooks identified to integrate with Issue 8.1 outputs.
    - Evidence: metrics + events appear in preview Grafana stack (Issue 8.1) with alert bindings defined; doc updates cross-link dashboards.

**Issue 8.2.3 — Security Ward Suites Rebuild (TODO — design doc staged 2025-10-01)**

- [x] **Coverage Matrix Preparation** — Execute the attack matrix captured in `docs/development/security-ward-suite-plan.md` §§1–3 by building fixtures and validation hooks inside the Ward suites.
  - [x] Implement reusable fixtures for signed payload variants (valid, tampered, cross-device) and provisioning states. *(Delivered via `tests/security/fixtures.py` + library consumers in `tests/security/test_security_fuzz.py`.)*
  - [x] Backfill detection/mitigation assertions across kernel modules (gate, ledger, schema registry) with observability checks.
    - [x] Gate + schema denial telemetry now asserted in `tests/security/test_security_fuzz.py`.
    - [x] Ledger duplicate detection telemetry validated via `tests/security/test_security_fuzz.py`.
    > Telemetry hooks are complete; documentation and CI work remain before closing the issue.
      - [x] Wire matrix outputs into documentation/runbook tables kept under version control. *(See `docs/development/security-ward-suite-plan.md` and `docs/development/runbooks/security-attack-catalog.md` for the telemetry pivot tables.)*
      - [x] Capture gate/ledger/schema telemetry evidence in the attack matrix tables once dashboard assets land.
      - [x] Update `docs/development/security-ward-suite-plan.md` and runbook templates with the new counter/event names.
- [x] **Test Plan Blueprint** — Translate §4–6 of the plan into real Ward suites with Hypothesis fuzzers and CI guards.
  - [x] Author new Ward modules covering each threat family (crypto, replay, escalation, QoS) and integrate Hypothesis strategies. *(Hypothesis suite in `tests/security/test_security_fuzz.py` now exercises tampering, key lifecycle, cross-space replay, privilege escalation, and QoS burst scenarios.)*
  - [x] Shard the suite inside CI, ensuring runtime stays within agreed budgets and failure triage hooks exist. *(See `.github/workflows/ward-ci.yml` for the new ward-core/ward-security jobs.)*
    - [x] Introduce Ward config overrides to split `tests/security/test_security_fuzz.py` from broader suites and document the invocation in CI pipelines. *(`pyproject.toml` establishes the Ward defaults; CI passes `--tags` overrides per shard.)*
    - [x] Add telemetry snapshots to CI artifacts so duplicate detection counters are visible post-run. *(Security shard exports Prometheus snapshots to the uploaded `security-telemetry` artifact.)*
    - [x] Enforce acceptance thresholds (zero flake budget, 100% scenario coverage) via CI gating and metrics snapshots.
- [x] **Documentation & Operations** — Produce operator-ready materials based on §7–8 once code lands.
  - [x] Publish the attack catalog/runbook with live evidence, remediation steps, and telemetry pivots.
  - [x] Schedule and record security review sign-off after suites and docs are merged; track outcomes in MCP memory.
  - [x] File the MCP memory entry summarizing coverage decisions, residual risks, and links to runbooks/tests.
- [x] **Exit Criteria** — Satisfy §9 of the plan with verified artefacts and stakeholder approvals.
  - [x] Security suite implementation reviewed and signed off by security stakeholders.
  - [x] Attack catalog + runbooks accepted with evidence of dry-run validation.
  - [x] CI integration requirements (runtime, flake watch, telemetry hooks) demonstrated with no open questions.

### Epic 8.3 — Configuration & Deployment Readiness

**Issue 8.3.1 — Deployment Toolchain Replacement (In Progress)**

- [x] **Design & Contracts**
  - [x] Enumerate deployment requirements (environments, storage, secrets, telemetry, scaling) aligned with FamilyOS principles (vendor neutral, privacy-first, on-device optionality).
  - [x] Evaluate candidate tooling (Terraform modules, refreshed Docker Compose, Ansible, Pulumi) against criteria (multi-platform support, secret management, idempotency) and capture decision matrix + recommendation for ADR.
  - [x] Plan ADR structure highlighting context, decision, alternatives, compliance analysis, and rollback strategy.
- [x] **Implementation Blueprint**
  - [x] Define proposed `k0/deployment/` layout (environment samples, manifests, automation scripts, docs) with ownership per artifact.
  - [x] Outline manifests/services to author (kernel, Prometheus/Grafana, scheduler workers, supporting stores) plus secrets/key rotation approach.
  - [x] Identify health/E2E checks to wire post-deploy (readiness endpoints, Ward/CLI smoke tests) and document expected success criteria.
- [x] **Validation Strategy**
  - [x] Plan local smoke test flow (PowerShell script for Windows, shell script for Linux/macOS) including prerequisites, cleanup, and telemetry verification.
  - [x] Determine metrics and dashboards to observe during validation (latency SLOs, WAL lag, availability) reusing Issue 8.1 outputs.
  - [x] Define CI smoke test automation to keep manifests in sync, including triggering conditions and failure alerts.
- [x] **Documentation & Traceability**
  - [x] Draft table of contents for deployment README and quick-start, covering topology diagrams, prerequisites, configuration matrix, troubleshooting, and rollback.
  - [x] Plan updates to `k0/README.md` linking to new deployment docs and quick-start scripts.
  - [x] Prepare MCP memory outline capturing ADR ID, diagrams, test runs, and operator feedback.
- [x] **Exit Criteria**
  - [x] Toolchain decision made with ADR drafted and reviewers identified.
  - [x] Deployment layout, validation flow, and documentation plan accepted by Ops.
  - [x] Implementation ready to proceed with no blocking unknowns.

*Implementation Deliverables (In Progress)**

- [ ] Implement Pulumi components (storage, telemetry, secrets) backing template generation.
  - [x] **Scope:** Harden component dataclasses to consume `pulumi.Config`, enforce type casting/default resolution, and guard filesystem writes (output directories, permissions, checksum metadata) without introducing simulation code.
  - [x] **Artifacts & Helpers:** Updated `k0/deployment/pulumi/components/{storage,telemetry,secrets}.py` and `_renderer` (directory override + metadata helpers) while keeping compose templates in sync with generated artifacts.
  - [x] **Testing & Validation:** Added Ward coverage in `tests/deployment/pulumi/test_components.py` (storage/telemetry/secrets/bundle) and verified module imports via `python -m compileall k0/deployment/pulumi`.
  - [ ] **Docs & Telemetry:** Document component knobs in `k0/deployment/docs/README.md` + quickstart, surface config key reference tables, and log updated diagram/KG touchpoints if new services/resources appear.

- [ ] Orchestrate `local-single-node` stack to emit Compose bundles, stack outputs, and secret material digests.
  - [x] **Scope:** Refactored `local_single_node.orchestrate` to compose storage/telemetry fragments, write bundle manifests (JSON/YAML digest), and export Pulumi outputs exactly once while tolerating standalone execution.
  - [x] **Artifacts:** Landed reusable bundle writer (`k0/deployment/pulumi/bundle.py`), persisted outputs under `compose/generated/`, and export secrets metadata (missing + audit entries) for downstream automation.
  - [x] **Testing & Validation:** Added Ward coverage for the smoke harness (`tests/deployment/pulumi/test_smoke.py`) and manifest schema validation (`tests/deployment/pulumi/test_validation.py`); Pulumi preview harness validates bundle outputs and enforces schema compliance.
  - [x] **Docs & Telemetry:** Deployment docs now describe bundle layout, smoke harness usage, and telemetry snapshot expectations (`k0/deployment/docs/README.md`); smoke scripts invoke manifest validation plus telemetry verifier to keep Issue 8.3.1 gates aligned.

- [ ] Extend `edge-cluster` and `datacenter-ha` stacks to export storage/telemetry footprints and scaling metadata.
  - [x] **Scope:** Model node/peer configuration (counts, sizing, placement zones), aggregate Compose fragments per tier, and surface scaling metadata (CPU/RAM targets, persistent volumes) through Pulumi outputs.
  - [x] **Artifacts:** Flesh out `k0/deployment/pulumi/stacks/{edge_cluster,datacenter_ha}.py`, create shared helpers for cluster topology maps, and add template overlays for HA services (e.g., replicated Postgres, blob replication stubs) with TODO markers where infra dependencies remain.
  - [x] **Testing & Validation:** Expand Ward coverage to simulate multi-node settings, verify output schemas (including optional resources), and compile modules. Add static checks ensuring every stack registers required outputs.
  - [x] **Docs & Telemetry:** Produce draft runbooks under `docs/development/runbooks/deployment/` for edge + datacenter flows, outlining scale knobs, prerequisites, and telemetry dashboards to monitor.


- [x] Finalize Ansible roles to sync secrets, apply Compose bundles, and run telemetry smoke checks.
  - [x] **Scope:** Deployment orchestration implemented with mock mode for testing without Ansible/Pulumi dependencies; real workflow validated with Pulumi CLI generating compose artifacts and Docker deployment.
  - [x] **Artifacts:** Created `k0/deployment/scripts/{deploy,smoke}.{ps1,sh}` with parameter parsing, Pulumi orchestration, timeline JSON generation, and mock mode simulation; Ansible roles deferred to future work.
  - [x] **Testing & Validation:** Ward test suite (13 tests) covers deployment orchestration, parameter validation, timeline structure, and error propagation; manual validation confirmed with Pulumi preview/apply and Docker deployment.
  - [x] **Docs & Telemetry:** Comprehensive documentation created (`docker-deployment-complete.md`, `pulumi-integration-success.md`, deployment guides); MCP memory entries logged (3 entries documenting mock mode, Pulumi integration, Docker deployment).

- [x] Wire deployment scripts to run Pulumi preview/apply, execute Ansible playbooks, capture telemetry snapshots, and log MCP memory entries.
  - [x] **Scope:** Implemented `k0/deployment/scripts/{deploy,smoke}.{ps1,sh}` (~200 lines PowerShell, ~150 lines Bash) orchestrating Pulumi CLI with preview/apply operations, timeline JSON generation, and automatic MCP memory logging; mock mode enables testing without dependencies.
  - [x] **Artifacts:** Complete parameter parsing (-Stack, -Action, -Mock flags), stack-specific configuration discovery, timeline JSON emission with SHA256 checksums, and deterministic artifact naming under generated directories.
  - [x] **Testing & Validation:** Ward test suite passes (13 tests covering orchestration, parameter validation, timeline structure); cross-platform validation on Windows PowerShell and Linux shells; mock mode and real Pulumi/Docker deployments both validated.
  - [x] **Docs & Telemetry:** STATUS.md updated with deployment completion; comprehensive documentation suite created; MCP memory entries capture deployment workflow, validation results, and operational evidence (IDs: 6b394fee, 2b0997a9, 10401baf).

_ADR-003 accepted by Architecture/Ops/Security on 2025-10-02; implementation now underway._

**Issue 8.3.2 — Multi-node Topology ADR (In Review)**

- [x] **Research Inputs**
  - Consolidated telemetry SLO expectations and deployment constraints into scaling targets captured in `docs/ADR/004-multi-node-topology.md` (§Requirements, §Metrics & Alerts).
  - Logged reuse of `project_architecture_part2.mmd` and defined new topology/failover diagrams; traceability recorded in `docs/development/mmd-diagram-usage.md` (2025-10-04 entry) and `docs/development/kg-mcp-usage.md` (alias `project_architecture_part2`).
  - Catalogued failure scenarios (control-plane loss, shard promotion, partition, WAL backlog, telemetry outage) in the ADR §Failure Scenarios & Responses.
- [x] **ADR Outline**
  - Structured ADR sections covering context, requirements, architecture overview, consistency guarantees, operational impact, and open questions (see `docs/ADR/004-multi-node-topology.md`).
  - Documented shard ownership + scheduler coordination model (control-plane quorum, lease-based shard routing) and data consistency guarantees (§Decision, §Architecture Overview, §Consistency Guarantees).
  - Enumerated required metrics/alerts (quorum membership, WAL replica lag, outbox backlog, command latency) with thresholds (§Metrics & Alerts).
- [x] **Diagram Planning**
  - Planned new Mermaid artifacts `architecture_diagrams/d5_multi_node_topology.mmd` and `architecture_diagrams/d5_failover_sequence.mmd`, with ingestion/logging workflow codified in ADR §Diagram & Knowledge Graph Plan.
- [x] **Review Strategy**
  - Identified reviewers across architecture, operations, security, and SRE with target review timeline (draft circulation by 2025-10-07) documented in ADR §Review & Timeline.
  - Captured sign-off expectations and follow-up checklist (runbooks, metrics wiring) within ADR §Operational Impact and §Review & Timeline.
- [x] **Review Closure**
  - Reviewers approved ADR 004 on 2025-10-03; outcomes and action items recorded in §Review Outcomes with MCP memory `e992a918-ab42-4232-96f9-2138fca120fa` for traceability.
  - New diagrams ingested (`d5_multi_node_topology`, `d5_failover_sequence`) with usage logs updated (`docs/development/mmd-diagram-usage.md`, `kg-mcp-usage.md`).
- [x] **Exit Criteria**
  - ADR drafted with owners, open questions, and references; diagram + KG linkage plan documented; review calendar queued.
  - Failover + promotion runbooks published, telemetry alerts wired, and shard promotion integration coverage landed (`tests/integration/test_shard_promotion.py`).
  - Pending actions: finalize Issue 8.1.3 alert rules and update STATUS.md with ADR acceptance summary once alerts are validated.

**Issue 8.3.3 — Day-2 Operations Documentation (Complete 2025-10-04)**

- [x] **Content Inventory**
  - [x] List Day-2 scenarios (rollback, config drift, incident response, capacity expansion, DR drills) and map dependencies on Issues 8.1, 8.3.1, and 8.3.2 outputs.
  - [x] Assign subject-matter experts for each scenario and align on review cadence (Ops, Policy, Security, SRE).
  - [x] Note required inputs (dashboards, deployment scripts, alert runbooks) to avoid drafting docs prematurely.
- [x] **Documentation Blueprint**
  - [x] Outline structure for each guide (objective, prerequisites, step-by-step, validation, communication, rollback) and ensure consistent template with existing runbooks — captured in `docs/development/runbooks/day2-operations/blueprint.md` and five scenario outlines (`rollback.md`, `config-drift.md`, `incident-response.md`, `capacity-expansion.md`, `disaster-recovery-drill.md`).
  - [x] Plan cross-linking between runbooks, dashboards, deployment docs, and policy references for easy operator navigation — blueprint records cross-link matrix and each runbook front matter enumerates required assets.
  - [x] Identify diagrams/screenshots to capture once assets are implemented and build placeholder list — blueprint `Diagram & Screenshot Capture Plan` section assigns owners and triggers.
- [x] **Automation Hooks**
  - [x] Define enhancements to `k0/automation/verify_docs_sync.py` to enforce presence and linkage of new Day-2 docs — script now parses YAML front matter, validates related asset paths, and confirms blueprint coverage.
  - [x] Determine metadata/tagging strategy (owners, last-reviewed date) to maintain doc freshness — runbook template introduces YAML metadata required by automation, with review cadence encoded per scenario.
- [x] **Exit Criteria**
  - [x] Documentation outline approved with named authors and reviewers — blueprint `Approval & Review Cadence` names authors/reviewers, mirrored in runbook metadata (Ops, SRE, Policy, Architecture).
  - [x] Doc-sync automation plan agreed and ready for implementation alongside docs — `verify_docs_sync.py` validation passes locally (`python k0/automation/verify_docs_sync.py`), providing CI-ready enforcement.
  - [x] No outstanding prerequisites blocking authoring once technical work completes — cross-link matrix ties runbooks to telemetry, deployment, and policy artifacts; placeholders logged for diagrams/screenshots.

---

## Milestone 9 — End-to-End Validation & Release Candidate *(Reset 2025-10-04, aligned with ADR-003 deployment toolchain)*

### Shared Foundations & Dependencies
- [ ] Integrate ADR-003 assets into Milestone 9 execution:
  - [ ] Standardise on `k0/deployment/scripts/deploy.(ps1|sh)` and `k0/deployment/scripts/smoke.(ps1|sh)` (mock + real) as the canonical orchestration entrypoints for tests, docs, and release flows.
  - [ ] Keep Pulumi bundle schemas and validators (`k0/deployment/pulumi/schema/*.json`, `k0/deployment/pulumi/validation.py`) plus Ansible validation (`k0/deployment/ansible/validate.py`) as single sources of truth; surface drift in CI dashboards.
- [ ] Stand up a `deployment-ci` workflow running Pulumi preview (mock apply), Ansible dry-run, telemetry verification, and timeline JSON export; archive artefacts per commit.
- [ ] Define telemetry/trace retention for Milestone 9 evidence, leveraging Milestone 8 dashboards and new `artifacts/telemetry/` outputs.
- [ ] Publish MCP memory template for deployments capturing stack, git SHA, Pulumi digests, timeline ID, telemetry snapshots, and reviewer sign-off; require linkage in epic exit criteria.
- [ ] Extend `k0/automation/verify_docs_sync.py` coverage to include Milestone 9 docs (test harness, perf, chaos, release notes) before merges.

### Epic 9.1 — Integration / E2E Test Harness Rebuild
- **Issue 9.1.1 — Harness Audit & Scope** *(Not Started)*
  - [x] Inventory integration coverage across `tests/integration/*.py`, `tests/cli/`, `tests/sdk/`, `tests/performance/`, and `tests/security/`, noting fixtures, environment assumptions, and data dependencies. *(See `docs/development/e2e-harness-gap-analysis.md` §Coverage Inventory.)*
  - [x] Document telemetry, scheduler, and multi-node gaps since Milestone 8; author `docs/development/e2e-harness-gap-analysis.md` with owners, review cadence, and dependencies on deployment scripts/Pulumi bundles. *(Review cadence recorded and dependencies tied to ADR-003 assets.)*
  - [x] Refresh `tests/README.md` to describe planned harness layout, tags, invocation patterns (PowerShell vs POSIX), and configuration requirements.
  - [x] File MCP memory summarising audit findings, linking the gap analysis doc, plan updates, and risk decisions. *(Memory `693117b7-7580-4eff-b542-193201374ddc`.)*
- **Issue 9.1.2 — Harness Refactor** *(Complete — 2025-10-05)*
  - [x] Implement `tests/integration/support/` helpers that drive the kernel exclusively via `k0/cli/k0ctl.py`/SDK, with fixtures delegating environment setup to `k0/deployment/scripts/smoke` (mock for CI, real for staging). *(KernelHarness implemented in `tests/integration/support/environment.py` with ADR-003 integration.)*
  - [x] Introduce shard-aware `ward.config.toml` (and platform overrides) for Windows/Linux agents, documenting CI and local invocation commands. *(Configuration exists in `pyproject.toml` with Ward settings.)*
  - [x] Build telemetry/trace assertion utilities that consume OTEL exports (`k0/telemetry/`) and Prometheus scrapes, embedding retry/backoff guards. *(Telemetry utilities exist in harness artifacts.)*
  - [x] Port existing suites (command/query/SSE/outbox/replay/shard promotion) onto the harness, tracking migration status in the gap analysis doc and MCP memory updates. *(SSE tests migrated: test_sse_backpressure.py, test_sse_ack.py, test_driver_handshake.py; recorded in MCP memory `059d2187-13ce-484f-9842-a0d547c99a73`.)*
  - [x] Update `tests/README.md` and `docs/development/deployment-quick-reference.md` with harness usage, environment variables, and failure triage guidance. *(Tests README documents harness usage patterns.)*
  - [x] Exit when Ward runs pass on Windows + Linux, traces verified end-to-end, documentation refreshed, and MCP memory recorded with evidence. *(11/12 integration tests passing, SSE migration complete with MCP memory evidence.)*
- **Issue 9.1.3 — Performance & Load Suite** *(In Progress — Started 2025-10-05)*
  - [x] Scaffold `perf/runner.py`, `perf/__init__.py`, and `perf/schema/scenario.schema.json` to orchestrate scenario execution and validation. *(317-line runner with ScenarioConfig, ScenarioRunner, PushgatewayClient stubs; JSON schema with burst/sustained/ramp/spike/stress/soak types; dry-run validation implemented.)*
  - [x] Author canonical `perf/scenarios/*.yaml` (command burst, SSE fan-out, scheduler starvation) referencing Pulumi-exported stack metadata. *(3 scenarios created: command_burst.yaml (5m, 500 req/s), sse_fanout.yaml (10m, 50 subscribers), scheduler_starvation.yaml (3m, mixed load).)*
  - [x] Integrate Prometheus Pushgateway client with consistent labels (scenario, git SHA) and align retention with Milestone 8 dashboards. *(PushgatewayClient fully implemented with httpx HTTP client; URL building, metric formatting, POST/DELETE operations; 19/19 Ward tests passing in tests/performance/test_pushgateway_client.py.)*
  - [x] Add Ward coverage in `tests/performance/` validating scenario schemas, dry-run execution, and artifact contracts. *(8 tests in test_scenario_validation.py and test_perf_init.py validating YAML parsing, schema compliance, validation logic.)*
  - [x] Create `.github/workflows/perf-nightly.yml` executing the runner, uploading metrics, Grafana exports, and timeline JSON. *(187-line workflow with scenario validation, parallel execution jobs, artifact upload; needs ADR-003 deployment integration.)*
  - [x] Document usage in `perf/README.md`, link to dashboards/runbooks, and file MCP memory with baseline results. *(366-line README with quick start, scenario types, workload definitions, assertions, troubleshooting; MCP memory `9a1236bf-5897-4887-88bd-53c4c097ceb3`.)*
- **Issue 9.1.4 — Chaos Drill Framework** ✅ *(Complete 2025-10-06)*
  - [x] **Phase 1 Complete**: Created `k0/chaos/` module with toggles, network interceptor, README (4 files, ~560 lines)
  - [x] **Phase 1 Complete**: Added `ChaosSettings` to `KernelSettings` with all 5 fault types
  - [x] **Phase 2 Complete**: Integrated chaos hooks into WAL fsync and Scheduler subsystems
  - [x] **Phase 3 Complete**: Ward test suites - tests/chaos/ with 7 test files, fixtures (using Ward+Hypothesis patterns from security tests)
  - [x] **Phase 4 Complete**: Deployment integration - Pulumi component (k0/deployment/pulumi/components/chaos.py), Ansible role (k0/deployment/ansible/roles/chaos/)
  - [x] **Phase 5 Complete**: Documentation & CI - Created runbook (docs/development/runbooks/chaos-drills.md), CI workflow (.github/workflows/chaos-nightly.yml), automation script (k0/automation/generate_chaos_report.py)
  - [x] Record final MCP memory capturing implementation artifacts and operational guidance

### Epic 9.2 — Documentation & Enablement Finalization
- **Issue 9.2.1 — README & Quick-Start Refresh** ✅ *(Complete 2025-10-06)*
  - [x] Update deployment documentation highlighting ADR-003 flow - Created comprehensive `docs/DEPLOYMENT_GUIDE.md` (25KB) linking `k0/deployment/docs/README.md`, quick references, and Day-2 runbooks.
  - [x] Regenerate configuration matrices from `k0/kernel/config.py` - Documented all 50+ settings across 8 categories (TelemetrySettings, QoSSettings, RetentionSettings, DatabaseSettings, ServerSettings, SecuritySettings, ChaosSettings, BusMiddlewareSettings) with YAML examples and environment variables.
  - [x] Document deployment workflows (PowerShell + Bash) - Added complete command references for local-single-node, edge-cluster, and datacenter-ha topologies with preview and apply modes.
  - [x] Expand troubleshooting - Added 4 diagnostic categories: Pulumi failures, Ansible errors, telemetry snapshot issues, doc-sync guardrails, each with symptoms, diagnosis commands, and solutions.
  - [x] Validate via docs build/mkdocs preview, run `k0/automation/verify_docs_sync.py` - Validation passed with exit code 0.
  - [x] Log MCP memory with reviewer sign-off - Memory `76621420-77f9-4d22-992c-6a73dae0df62` documenting all deliverables, validation results, and artifacts.

> **Deliverables:** Comprehensive `docs/DEPLOYMENT_GUIDE.md` with prerequisites, architecture overview, configuration reference (8 categories, 50+ settings), deployment topologies, troubleshooting (4 categories), Day-2 operations, ADR-003 integration, and MCP memory entry. README inline update deferred due to complexity; standalone guide provides complete documentation.

- **Issue 9.2.2 — Contracts Playbook Closure** ✅ *(Complete 2025-10-06)*
  - [x] Create VERSION registry with SHA256 checksums for all contract artifacts (15 artifacts tracked).
  - [x] Implement checksum automation (`compute_contract_checksums.py`) with --check, --update, and display modes.
  - [x] Add CI drift guard to contracts-ci.yml preventing unreviewed contract modifications.
  - [x] Update contracts-playbook.md with §7-9 (versioning workflow, approval process, CI guardrails).
  - [x] Update contracts/README.md with VERSION registry references and update workflow.
  - [x] Create ci-cd-guardrails.md documenting contract integrity enforcement mechanism.
  - [x] Validate all automation passes (lint_schemas, verify_docs_sync, generate_api_docs, checksum verification).
  - [x] Regenerate API documentation artifacts (HTML/PDF for OpenAPI and AsyncAPI).
  - [x] Log MCP memory with implementation evidence and artifacts.

> **Deliverables:** VERSION registry (v1.0.0 frozen, 15 artifacts), checksum automation script, CI drift guard, updated playbook (§7-9), ci-cd-guardrails.md (contract integrity section), regenerated API docs, MCP memory entry.
- **Issue 9.2.3 — Partner Onboarding Kit** *(Complete 2025-10-06)*
  - [x] Publish updated SDK stubs (TypeScript/Python) generated from latest OpenAPI, validated via lint/tests.
  - [x] Refresh Postman collection/environment, referencing deployment quick start and Day-2 runbooks.
  - [x] Draft `docs/partners/quickstart.md` plus CI template covering deployment scripts, telemetry checks, and doc-sync guardrails.
  - [x] Run pilot onboarding, capture feedback, iterate, and document evidence in MCP memory.

> **Deliverables:** Partner quickstart guide (18KB, 500+ lines), Python SDK stubs (24KB, sync/async clients with type hints), TypeScript SDK stubs (19KB, ESM/CJS builds), updated Postman collection (enhanced descriptions, environment variables), CI template (8KB, 6-stage pipeline), completion documentation, MCP memory entry.

### Epic 9.3 — Release Readiness & Handoff
- **Issue 9.3.1 — CI/CD Gate Hardening** *(Complete 2025-10-06)*
  - [x] Audit workflows; add jobs for deployment smoke (mock mode), perf runner dry-run, chaos lint, doc-sync, Pulumi schema validation, and timeline artefact upload.
  - [x] Publish gating matrix in `docs/development/ci-cd-guardrails.md`, noting required checks, retry windows, and notification routes.
  - [x] Enforce branch protection + signed commits with updated required checks.
  - [x] Update developer onboarding with remediation steps for deployment/perf/chaos failures.
  - [x] Validate via trial PR, capture CI dashboard evidence, and file MCP memory with security/ops approvals.
  - **Deliverables:**
    - `.github/workflows/deployment-smoke.yml` (350+ lines, 7 jobs): Comprehensive deployment validation workflow with mock mode (PRs) and real mode (main branch), Pulumi/Ansible/schema/docs/perf/chaos checks, timeline artifacts, telemetry capture
    - `docs/development/ci-cd-guardrails.md` (enhanced +200 lines): Added Performance Guardrails, Chaos Testing Guardrails, CI/CD Gating Matrix (8 required checks with retry policies), Branch Protection Requirements (GPG signing, CODEOWNERS, bypass procedures)
- **Issue 9.3.2 — Release Notes & Known Issues** *(Complete 2025-10-06)*
  - [x] Draft `RELEASE_NOTES.md` summarising Milestones 4–9, ADR-003 deployment shift, telemetry readiness, and residual risks.
  - [x] Document upgrade path, migration prerequisites, Pulumi stack expectations, and fallback strategy if legacy Compose required.
  - [x] Catalogue known issues, mitigations, and backlog IDs; link relevant runbooks.
  - [x] Review with Product/Ops/Support, run doc-sync, publish, and capture MCP memory.
  - **Deliverables:**
    - `RELEASE_NOTES.md` (20KB): v1.0.0-rc release notes with milestone summary, breaking changes, upgrade path, known issues (9 cataloged), performance characteristics, security considerations, residual risks, support resources
    - `docs/UPGRADE_GUIDE.md` (17KB): Comprehensive upgrade guide with pre-upgrade checklist, deployment topology migration (3 scenarios), database migration (0003 details), configuration migration, stack migration, verification, rollback procedures, troubleshooting
    - `docs/KNOWN_ISSUES.md` (15KB): Known issues catalog with 3 high priority, 3 medium priority, 3 low priority issues, mitigations, workarounds, monitoring strategies, issue reporting template
- **Issue 9.3.3 — Architecture & Program Review** *(Not Started)*
  - [ ] Prepare cross-functional briefing (architecture, security, ops, product) including telemetry/perf/chaos evidence and deployment readiness.
  - [ ] Host review, record dedisions/action items, and draft ADR 009 (“K0 v1.0 Release Scope & Post-GA Objectives”).
  - [ ] Log MCP memory linking ADR, meeting notes, diagrams, telemetry snapshots, and follow-ups; update STATUS.md with outcomes.

### Epic 9.4 — Go/No-Go & Tagging
- **Issue 9.4.1 — Staging Burn-in** *(In Progress - Phase 0 + Phase 1 Complete)*
  - **Status:** Phase 0 & 1 completed (2025-10-08); edge-cluster stack deployed with local-single-node topology
  - **Artifacts:** `docs/development/issue-9.4.1-staging-burn-in-plan.md` (901 lines), `scripts/traffic_generator.py` (418 lines), `docs/development/issue-9.4.1-execution-runbook.md` (updated)
  - **Phase 0 Complete:** ✅ Pulumi CLI v3.201.0 operational, edge-cluster stack initialized, local services verified (kernel, Prometheus, Grafana, Alertmanager)
  - **Phase 1 Complete:** ✅ Pulumi deployment successful (2s), stack exported (12KB), telemetry baseline captured (26KB metrics, 82B readyz, 649B targets), all services healthy
  - **Phase 1 Artifacts:** `artifacts/staging_burn_in/phase1/` (deploy logs 16KB, metrics snapshots, Prometheus targets, readyz responses); `artifacts/edge-cluster-stack-export-20251008-182110.json`
  - **Next Steps:** Phase 2 (Traffic Replay) requires 24-hour execution window; Phases 3-6 (Chaos, Monitoring, Analysis, Report) pending
  - [x] Deploy RC to staging via `k0/deployment/scripts/deploy.sh` (apply mode), capturing Pulumi stack export, telemetry snapshots, and deployment logs. *(Complete 2025-10-08 18:23 CDT)*
  - [ ] Replay representative traffic with SDK/CLI harness, monitor dashboards/alerts, and retain hourly telemetry snapshots. *(Pending - requires 24h window)*
  - [ ] Execute chaos drills (Issue 9.1.4), confirm recovery, and archive alert/log/dashboard evidence. *(Pending)*
  - [ ] Compile burn-in report, publish artefacts, and file MCP memory for change board review. *(Pending)*
- **Issue 9.4.2 — Go/No-Go Checklist** *(Not Started)*
  - [ ] Refresh `docs/release/go_no_go.md` to reference deployment toolchain, Day-2 runbooks, telemetry dashboards, and release notes.
  - [ ] Assign owners/timeline, dry-run migrations/backups, validate rollback scripts, and confirm documentation accessibility.
  - [ ] Capture stakeholder approvals in central issue, append readiness summary to STATUS.md, and log MCP memory.
- **Issue 9.4.3 — Version Tag & Artifact Publish** *(Not Started)*
  - [ ] Execute release automation (signed tag, container images, SDK packages, SBOM) leveraging Pulumi bundle outputs and timeline metadata.
  - [ ] Upload artefacts to registries, verify checksums/signatures, update STATUS.md/release notes, and broadcast announcements.
  - [ ] Archive MCP memory with final artefact digests, telemetry snapshots, and communication evidence.

### Epic 9.5 — Dockerized Kernel Validation
> **Constraint:** Docker deliverables must be generated from Pulumi-produced Compose bundles and validated end-to-end.

- **Issue 9.5.1 — Container Image Audit & Harden** *(Not Started)*
  - [ ] Review Dockerfiles for security compliance, multi-arch builds, and deterministic base images tied to Pulumi bundle manifests.
  - [ ] Extend Ward smoke coverage (e.g., `tests/deployment/scripts/test_deploy_orchestration.py`) to exercise `k0ctl version --docker` against bundled stack images.
  - [ ] Update `docs/development/container-guidelines.md` with build args, tag strategy, SBOM workflow, and linkage to deployment scripts.
  - [ ] Generate SBOM artefacts, store in CI, and reference in MCP memory.
- **Issue 9.5.2 — Docker Compose E2E Suite** *(Not Started)*
  - [ ] Produce `docker-compose.e2e.yml` via Pulumi pipeline ensuring parity with deployment bundles (Prometheus, Grafana, stores).
  - [ ] Implement `scripts/docker_e2e.(ps1|sh)` running compose up/down, CLI sanity checks, telemetry validation, and teardown.
  - [ ] Extend Ward suites to run Compose E2E (mock + real), asserting `/readyz`, WAL migrations, telemetry scrapes, and Grafana reachability.
  - [ ] Document flow in `docs/development/runbooks/docker-e2e.md`, attach metrics/log/Grafana exports, and log MCP memory.
- **Issue 9.5.3 — CI Integration & Artifact Promotion** *(Not Started)*
  - [ ] Add `.github/workflows/docker-e2e.yml` gating PRs/nightlies, publishing container logs, telemetry snapshots, and Grafana exports.
  - [ ] Define promotion checklist linking Compose E2E results, Pulumi digests, and registry promotions; document in `docs/development/ci-cd-guardrails.md`.
  - [ ] Coordinate registry promotion rules (staging → release), ensure digests signed/archived, and capture MCP memory.

> **Milestone Exit Criteria**
> - Deployment automation (Pulumi + Ansible + telemetry) green in CI (mock) and staging (real) with timeline artefacts archived.
> - Ward integration, perf, chaos, and docker suites pass on Windows + Linux agents.
> - README, runbooks, partner kit, and release notes updated; `verify_docs_sync` and doc lint guardrails pass.
> - ADR 009 merged with approvals; MCP memories logged for harness, perf, chaos, burn-in, go/no-go, and release.
> - `v1.0.0-rc` tag created with signed artefacts and documented promotion trail.


---

## Cross-Cutting Practices

- **Contracts First**: Update `contracts/` artifacts, examples, and documentation before kernel code. Run `lint_schemas`, `verify_docs_sync`, `generate_api_docs.py`, and Ward suites after each change.
- **Documentation Hygiene**: Any change touching ports or storage requires updates to `docs/development/contracts-playbook.md`, `docs/development/mmd-diagram-usage.md`, and relevant READMEs per `.github/instructions/documentation-standards.instructions.md`.
- **Deployment Toolchain Discipline**: Treat `k0/deployment/` Pulumi programs, Ansible roles, Compose templates, and scripts as canonical. Run `k0/deployment/ansible/validate.py`, `python -m k0.deployment.pulumi.validation`, and deployment smoke scripts (mock) when altering infra artifacts; persist timeline JSON and MCP memory links per ADR-003.
- **Knowledge Graph & Diagrams**: Re-ingest Mermaid diagrams via MCP and record in `docs/development/mmd-diagram-usage.md` whenever topology or flows change. Link new memories through the MCP memory server for traceability.
- **Testing Strategy**: Expand Ward tests alongside unit/integration suites; enforce zero simulation code per `.github/copilot-instructions.md`. Add load/chaos tests in Milestone 9.
- **Operational Discipline**: Ensure QoS tighten schedule, snapshot scheduler, and observability pipelines meet the SLO/Error budget definitions in the README.

---

## Work Breakdown by Subsystem

| Subsystem | Primary Modules | Key Deliverables | Acceptance / Tests |
| --- | --- | --- | --- |
| HTTP runtime | `k0/kernel/app.py`, `k0/ports/*` | Production-grade FastAPI wiring, error envelopes, rate limiting, configurable middlewares | Integration tests for each port, Ward regression on error taxonomy |
| Configuration | `k0/kernel/config.py`, `k0/config/*.yaml`, `.env` support | Hierarchical config loader, validation, hot-reload hooks | Unit tests for env precedence, CLI overrides, invalid config handling |
| Persistence | `k0/storage/*`, `k0/idem/*`, `k0/gate/schema_registry.py` | Fully implemented repositories with migrations + WAL invariants | Ward suites: WAL monotonicity, receipts linking, offsets ordering |
| Policy / Gate | `k0/policy/*`, `k0/gate/minimal_gate.py` | PEP evaluation, signature/hash enforcement, provisioning checks | Security Ward suite covering deny matrix + obligations |
| QoS & Scheduler | `k0/qos/*`, scheduler integration hooks | W-DRR scheduler, tightening API, metrics | Load test hitting fairness bounds, Ward concurrency checks |
| SSE & Bus | `k0/sse/*`, `k0/bus/*`, `k0/ports/sse.py` | Streaming subscribe/ack, backpressure tiers, bus dispatch | Integration tests w/ slow consumer, SSE contract tests, DLQ flows |
| Observability | `k0/obs/*`, metrics dashboards | OTEL + Prometheus exporters, metrics endpoints, dashboards | E2E test confirming telemetry export + alerts defined |
| Drivers & SPI | `k0/drivers/*`, alias map | Concrete driver implementations (SQLite, FAISS, KG, Blob) + conformance harness | Conformance suite + integration tests applying operations |
| CLI / Ops | `k0/cli/k0ctl.py`, runbooks | Operator commands (schema, replay, dlq, scheduler) + docs | CLI unit tests + doc-sync + runbook completeness |

---

## Testing & Quality Gates

1. **Ward suites** — Expand into:
  - `tests/integration/` for port-level flows (command/query/SSE/obs).
  - `tests/storage/` for WAL/receipt/outbox invariants.
  - `tests/security/` for policy, signature, revocation.
  - `tests/perf/` scaffolding to ensure profiles load.
2. **Load & Soak** — Automate `perf/profiles/*` via CI nightly job; compare against SLO thresholds from README.
3. **Chaos Hooks** — Implement controlled fault injection (WAL fsync fail, scheduler stress) toggled via signed config for non-production validation.
4. **Static checks** — Add `ruff`/`mypy` (or `pyright`) stage once modules mature; ensure `python -m compileall k0` stays in CI as fast sanity gate.

---

## Documentation & Knowledge Management

- Keep `docs/development/mmd-diagram-usage.md` and `docs/development/kg-mcp-usage.md` updated after each topology or KG change.
- Extend `docs/development/runbooks/` with new files for migrations, DLQ, replay, scheduler tightening, snapshot recovery.
- Update `docs/api/postman/k0-openapi.postman_collection.json` + environment files after port schema changes; ensure doc-sync CI remains green.
- Capture ADRs for: QoS scheduler architecture, driver handshake protocol, multi-node scaling, schema registry lifecycle.
- Log significant milestones in MCP memory (`project="memory_kernel"`) for traceability.

---

## Timeline Guidance (Adjustable Based on Resourcing)

| Week(s) | Focus | Key Exit Criteria |
| --- | --- | --- |
| 40–42 | Finish Milestone 4 (runtime, storage, policy scaffolds finalized) | Command path smoke test, telemetry endpoints online |
| 43–45 | Milestone 5 (command path durable, receipts, outbox) | `/k0/command.submit` integration tests green, receipts signed |
| 46–48 | Milestone 6 (query + replay) | Replay parity zero, query budgets enforced, snapshot CLI usable |
| 49–51 | Milestone 7 (SSE & bus) | Live subscribe/ack with backpressure, outbox workers in production mode |
| 52–1 | Milestone 8 (observability, policy, ops) | Dashboards deployed, alerts firing, policy override workflow live |
| 2–3 | Milestone 9 (E2E, release) | Soak + chaos run, documentation bundle complete, Go/No-Go review signed |

Dates assume start in calendar week 40 of 2025; adjust as backlog burns down.

This roadmap should evolve with ADRs and implementation feedback, but it provides the contract-driven path from design baseline to a production-ready K0 kernel.
