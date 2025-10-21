# K0 Test Harness Overview

## Purpose

This guide explains how the Milestone 9 harness is organised, how to run each suite, and how the upcoming refactor will standardise environment setup through the deployment scripts introduced by ADR-003. Pair this with `docs/development/e2e-harness-gap-analysis.md` for the detailed inventory and gap log.

## Directory Layout

```
tests/
├── cli/              # k0ctl workflows (schema registry, DLQ)
├── deployment/       # Pulumi bundle + script orchestration tests
├── integration/      # End-to-end HTTP + kernel coverage
├── performance/      # Placeholder for Issue 9.1.3 scenario runner
├── sdk/              # Shared HTTP client used by integration suites
├── security/         # Gate/QoS/telemetry hardening suites
├── snapshots/        # Replay + snapshot determinism
└── telemetry/        # Dashboard and alert rendering checks
```

## Execution Patterns

| Suite | Typical Command (PowerShell) | Typical Command (POSIX) | Notes |
| --- | --- | --- | --- |
| Integration (all) | `python -m ward test --path tests/integration` | `python -m ward test --path tests/integration` | Boots FastAPI in-process per test using temporary SQLite + SDK client |
| Selected integration flow | `python -m ward test --path tests/integration/test_e2e_flows.py --search "command submit"` | same as PowerShell | Use `--search` to narrow by description when debugging |
| CLI workflows | `python -m ward test --path tests/cli` | same | Passes `--set database.path=...` arguments internally; no external services |
| Deployment smoke | `python -m ward test --path tests/deployment` | same | Exercises Pulumi mock exports and timeline generation |
| Security fuzz shard | `python -m ward test --path tests/security --tags security-fuzz` | `python -m ward test --path tests/security --tags security-fuzz` | Ensures QoS and signature guards stay deterministic |

> **Heads up:** Ward tag discipline will expand in Issue 9.1.2 once `ward.config.toml` lands. Expect new tags such as `integration-harness`, `multi-node`, and `telemetry` so we can shard Windows vs Linux agents cleanly.

## Environment Setup → Deployment Scripts First

End-to-end and future perf/chaos suites must rely on the deployment automation added in ADR-003:

- **Mock smoke validation (Windows):**

  ```powershell
  .\k0\deployment\scripts\smoke.ps1 -Stack local-single-node -Mock
  ```

- **Mock smoke validation (POSIX shells):**

  ```bash
  ./k0/deployment/scripts/smoke.sh -Stack local-single-node -Mock
  ```

These commands generate the telemetry snapshots and timeline JSON that Milestone 9 treats as canonical harness inputs. When the refactor lands, shared fixtures inside `tests/integration/support/` will call these scripts automatically before issuing CLI or SDK traffic. Until then, run smoke locally when debugging integration tests to mirror CI artefacts.

## Configuration Expectations

- All suites consume schema + storage definitions from `k0/contracts/sql/storage.sql`; no ad-hoc schemas allowed.
- Integration fixtures disable external OTEL endpoints by default; telemetry assertions will switch to reading the artifacts under `artifacts/telemetry/` once Issue 9.1.2 ships.
- CLI tests rely on `k0ctl` parameter overrides (e.g., `--set database.path=`). Keep new CLI options wired through the same mechanism so tests remain hermetic.

## Pending Harness Work (Issue 9.1.x)

- Introduce `tests/integration/support/` helpers that wrap `k0ctl`/SDK calls and drive environment setup exclusively via deployment smoke scripts.
- Populate `tests/performance/` with the scenario runner described in Issue 9.1.3, exporting metrics with consistent labels for dashboards.
- Add chaos drill scaffolding that toggles the `k0/chaos/` module and validates alert firing/clearing without simulation code.

For a full gap checklist and owner roster, see `docs/development/e2e-harness-gap-analysis.md`. When adding new suites, update both this guide and the gap analysis to keep Milestone 9 traceability intact.
