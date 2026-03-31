# M0 E0.3 — POC File Classification: COPY / STAY / DROP

**Date**: 2026-03-30
**Total .py files in poc/k1_poc/**: 310 (excl. `__pycache__/`)

---

## Classification Summary

| Tag | Count | Description |
|---|---:|---|
| **COPY** | 267 | Production code → `k1/concierge/` |
| **STAY** | 33 | Demo harness + test infrastructure (remains in `poc/`) |
| **DROP** | 2 | Dead code candidates |
| **Total** | **310** | (includes `__init__.py` files) |

---

## STAY — Demo Files (`poc/k1_poc/demo/`) — 16 files

These remain in `poc/` as the standalone demo harness. NOT production code.

| File | Rationale |
|---|---|
| `__init__.py` | Package marker |
| `coordinator.py` | Demo orchestrator (Smith family scenario) |
| `coordinator_old.py` | Superseded coordinator (kept for reference) |
| `display.py` | Terminal display formatter |
| `interactive.py` | Interactive CLI harness |
| `iot_stubs.py` | Simulated IoT devices |
| `output_channel.py` | Bus-to-display adapter |
| `preloaded_memories.py` | Smith family seed data |
| `runner.py` | Demo entry point |
| `smith_family.py` | Smith family profile data |
| `spinner.py` | CLI spinner |
| `_e2e_smoke.py` | Quick demo smoke test |
| `web/__init__.py` | Web demo package |
| `web/__main__.py` | Web demo entry point |
| `web/app.py` | FastAPI web demo |
| `web/renderer.py` | HTML renderer |

Also includes static assets: `web/static/app.js`, `web/static/index.html`, `web/static/styles.css`

## STAY — Test Infrastructure (`poc/k1_poc/testing/`) — 14 files

Internal harness tests. Reference `tests/poc/` post-migration.

| File | Rationale |
|---|---|
| `__init__.py` | Package marker |
| `fixtures.py` | Shared test fixtures |
| `harness/__init__.py` | Harness package |
| `harness/conftest.py` | Pytest conftest |
| `harness/engine.py` | System-level test engine |
| `harness/run.py` | Harness runner |
| `harness/README.md` | Harness documentation |
| `harness/test_arbiter.py` | Arbiter system tests |
| `harness/test_delta.py` | Delta system tests |
| `harness/test_e2e.py` | E2E system tests |
| `harness/test_fsm.py` | FSM system tests |
| `harness/test_hitl.py` | HITL system tests |
| `harness/test_ledger_deadletter.py` | Ledger system tests |
| `harness/test_opp_patterns.py` | OPP pattern tests |
| `harness/test_opp_pipeline.py` | OPP pipeline tests |
| `harness/test_phase1_frontlock.py` | Phase1/FrontLock tests |
| `harness/test_weave.py` | Weave system tests |

## STAY — Root Entry Points — 3 files

| File | Rationale |
|---|---|
| `poc/k1_poc/__init__.py` | POC package root — STAY for demo imports |
| `poc/k1_poc/main.py` | POC entry point — STAY (k1/concierge gets its own entry) |
| `poc/k1_poc/docs/` | POC design docs — STAY for historical reference |

## DROP — Dead Code Candidates — 2 files

| File | Evidence | Justification |
|---|---|---|
| `demo/coordinator_old.py` | Superseded by `coordinator.py`; never imported | Dead code — old coordinator version |
| `demo/_e2e_smoke.py` | Orphan; quick smoke test, not part of any harness | Candidate for drop or merge into harness |

**Note**: Both DROP candidates are in `demo/` (STAY), so they don't affect the COPY set. They can be cleaned up independently.

## COPY — Production Directories (22 folders, 267 files)

All files below migrate to `k1/concierge/<folder>/` during M5 Big Copy.

| Folder | .py Files | Key Modules |
|---|---:|---|
| `actors/` | 7 | Front, Back handlers, shared utilities |
| `bus/` | 5 | Setup, builders, topics, deserialize |
| `compression/` | 2 | Compressor |
| `config/` | 3 | Loader, `__init__`, defaults.yaml (non-.py) |
| `delta/` | 9 | Aggregator, applicator, emitters |
| `events/` | 10 | Event types, registry, validators |
| `experience/` | 8 | Experience layer |
| `fabric/` | 5 | Capability registry, bridges |
| `fsm/` | 19 | Controller, arbiter, states, task_bridge |
| `identity/` | 2 | Dynamic persona |
| `kernel/` | 3 | Bootstrap, runner, `__init__` |
| `ledger/` | 5 | Idempotency, writer, projections, recovery |
| `llm/` | 7 | Model port, adapters, validator, types |
| `obs/` | 4 | Metrics, react_metrics |
| `orchestrator/` | 7 | Simple POC orchestrator |
| `prompt/` | 9 | PromptBuilder, modes, sections |
| `protocols/` | 20 | OPP, HITL, Weave, Suspension, Cancel |
| `react/` | 3 | Loop, history |
| `scheduler/` | 2 | Proactive scheduler |
| `sessionstate/` | 129 | Manager, tiers, sections, ports, adapters, FlatBuffers |
| `task/` | 12 | Task model, lifecycle, topics |
| `tools/` | 7 | Dispatcher, schemas, implementations |

### Orphan Analysis (False Positives)

The orphan scan found 86 files "not imported by anything." After classification:

| Category | Count | Verdict |
|---|---:|---|
| `demo/` files (already STAY) | 5 | Expected — entry points, not imported |
| `testing/` files (already STAY) | 12 | Expected — test files discovered by pytest, not imported |
| `sessionstate/generated/flatbuffers/**` | 42 | Expected — generated code, loaded dynamically by FlatBuffers runtime |
| `sessionstate/` internals (manager, sections, adapters, etc.) | 22 | **False positive** — imported via `sessionstate/__init__.py` re-exports or `sessionstate/factory.py` |
| `sessionstate/scripts/` | 2 | Expected — build scripts, not runtime imports |
| `kernel/runner.py` | 1 | Entry point (like `main.py`) — not imported, executed directly |
| **True orphans (DROP candidates)** | **2** | `coordinator_old.py`, `_e2e_smoke.py` (both in demo/) |
