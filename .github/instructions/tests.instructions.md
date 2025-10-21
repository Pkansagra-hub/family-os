---
description: Test layout, coverage, and contract/integration expectations.
applyTo: "tests/**/*.py"
---
# ✅ Testing Standards — WARD

## 1) Structure & Naming
- Mirror the source tree under `tests/` (e.g., `tests/api/test_routes_users.py`).
- Use `@test("description")` decorator for test functions; one behavior per test.

## 2) Types of Tests (write all that apply)
- **Unit** — focus on pure logic; ≥ **70%** of touched logic must be covered.
- **Integration** — exercise real I/O paths (API ↔ events ↔ storage). Use test containers or in-memory stores as declared by repo.
- **Contract** — any change under `contracts/**` must be validated against JSON Schema/OpenAPI (envelope invariants, topics, routes).
- **Performance** — benchmark hot paths; set budgets and assert via thresholds.

## 3) Tooling & Conventions
- Framework: **WARD**. Use `@test("test description")` and `@fixture` decorators.
- Fixtures: prefer function-scoped for isolation; provide factories for envelope/events.
- Determinism: freeze time, seed RNG, isolate FS with temp paths.
- No network calls unless explicitly marked and sandboxed.

## 4) What to Assert
- **Behavioral outcomes** first; then fields; then side effects (events, storage writes, metrics).
- Validate **redaction** and **policy/PEP** outcomes for protected flows.
- Ensure **observability** signals exist (metrics/spans/logs emitted).

## 5) Contract Tests Checklist
- Updated **OpenAPI** and/or **JSON Schemas** under `contracts/**`.
- Examples validated (`additionalProperties: false` where applicable).
- Envelope invariants: `band`, `policy_version`, `actor/device/space_id`, `qos`, `id/ts`.

## 6) Running
- `python -m ward test --path tests/` for quick checks; include `--fail-limit=1` in CI.
- Include coverage in CI; fail if coverage drops for touched areas.
