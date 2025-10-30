---
title: "TEST0001: K0 Bootstrap Verification Harness"
status: "DRAFT"
date: "2025-10-30"
revises: []
supersedes: []
authors:
  - "Cascade Assistant"
tags:
  - "k0"
  - "testing"
  - "observability"
  - "contracts"
---

## Context

FamilyOS requires on-device verification that the K0 kernel wiring (migrations, WAL replay, admission gate, QoS scheduler, observability, driver dispatch) initializes correctly before exposing privileged ports. Manual request crafting is slow, error-prone, and leaves gaps in audit coverage because the provisioning ledger, schema registry, and device keys must be seeded coherently before any /k0 routes accept traffic.

The existing `k0ctl` CLI applies migrations and runs the kernel, but there is no contract-backed harness for local or CI smoke tests that seeds a temporary SQLite database, installs schemas/devices/keys, executes sample command/query/driver/SSE flows, and captures logs+metrics for assertion. Engineers currently craft bespoke scripts that bypass policy logging and do not guarantee readiness semantics.

## Decision

Authorize a disposable “bootstrap verification harness” that:

1. Seeds a temporary kernel database with:
   - schema_registry rows matching the contract below,
   - provisioned device and ACTIVE key pairs,
   - optional QoS overrides for deterministic budgets.
2. Boots the kernel (reusing the existing `create_app` factory) inside the process, waiting for `/readyz` to report migrations_applied and wal_replay_complete.
3. Issues contract-driven requests against `/k0/command.submit`, `/k0/query.recall`, `/k0/driver.handshake`, and `/k0/sse.subscribe`, collecting:
   - HTTP status/envelope bodies,
   - admission audit records,
   - emitted metrics snapshot and OTEL spans.
4. Emits a structured verification report summarizing which subsystems reached the expected state. The harness exits non-zero if any contract clause fails (e.g., WAL not written, metrics missing, SSE counters stagnant).

The automation must run entirely on-device, use only repository dependencies, and clean up temporary files. It may be invoked ad hoc in development or as part of CI smoke suites, but it never ships in production builds.

## Consequences

- **Positive**: Developers gain a repeatable, contract-backed check that the kernel wiring is intact before deeper tests. Observability gaps are surfaced early via the consolidated report.
- **Positive**: CI pipelines can reuse the harness to validate migrations and WAL replay on fresh environments without bespoke scripts.
- **Neutral**: Adds maintenance for the test contract when schema URIs or envelope shapes evolve. The harness must track those deltas via updates to the YAML contract.
- **Negative**: Slight increase in repo footprint and execution time (depends on migrations + WAL replay), but bounded by local hardware.
- **Negative**: Requires keeping the harness updated with future Admission Gate or QoS policy changes; failing to do so will block smoke tests by design.

## Status & Follow-up

- Initial version lands with the accompanying YAML contract under `scripts/contracts/`.
- Future enhancements (e.g., FlatBuffers payloads, driver pool assertions) should revise this ADR and bump the contract version.
- Once validated, promote status to ACCEPTED and link to CI job documentation.
