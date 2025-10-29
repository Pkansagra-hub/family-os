---
description: Explore the repo's layer folder (defaults to `l5_infrastructure` under `k1/`),scan stubs, infer dependencies, and produce a single-developer, strictly sequential end-to-end implementation plan (Milestones → Epics → Issues).
auto_execution_mode: 3
---

# Planner Enhanced Trial

## 0 Parse intent & layer (FAST)

1. Take `<layer_name>`; if omitted, use `l5_infrastructure`
2. Echo: "Planning from stubs for `<layer_name>` (fast path)"

## 1 Load repo rules (no fluff)

1. Read `.windsurfrules`
2. Acknowledge non-negotiables: **no simulation code**, **contracts-first**, **privacy bands**, **no stray .md**

## 2 Locate the layer folder

1. Resolve candidate paths (first match wins):
   - `k1/<layer_name>/`
   - `k1/l5_infrastructure/` (fallback when `<layer_name>` ≈ l5)
   - `k1/**/<layer_name>*/` (broad fallback)
2. If not found, ask user to provide the exact path and stop

## 3 Inventory & classify the stubs

1. Print a concise tree (depth ≤ 4) and a **component inventory** table with columns:
   - `Component` | `Type (service/adapter/model/contract/test)` | `Path` | `Status (STUB/IMPL)` | `Notes`
2. Classify files by heuristics:
   - **STUB markers**: `STUB`, `NEEDS_IMPLEMENTATION`, `raise NotImplementedError`, `pass`, "🚧"
   - **Contracts**: files under `contracts/`, `*.json`, `*.yaml`, `*.fbs`, `openapi.*`
   - **Models**: `model/` folders, `schemas/`
   - **Adapters/Ports**: `client`, `bridge`, `transport`, `http2`, `sse`
   - **Runtime**: schedulers, mailbox, batching, connection manager
   - **Tests**: `tests/**`, `test_*.py`
3. Extract lightweight deps by scanning `import`/`from` lines and local relative imports to build a **local dep map**

## 4 Optional drift ping (non-blocking)

1. If `adr_family_map.md` exists, quickly match any component names seen in the map (no deep read)
2. If obvious drift (e.g., K1 implementing K0 pipelines, wrong envelope, missing `cognitive_trace_id`) is detected, print a **DRIFT PING** list and **ask if you want to fix in-plan**
   - Do **not** halt

## 5 Build the execution order (single-dev, strictly sequential)

Use this default ordering and topological constraints from the dep map:

1. **Contracts & Config**
2. **Models**
3. **Core Runtime** (queues/schedulers/batching/conn-mgr)
4. **Adapters/Bridge Clients** (HTTP/2, SSE, Observability)
5. **Integrations**
6. **Observability** (metrics, traces, logs)
7. **Security/Policy hooks**
8. **Hardening & Perf**
9. **Docs touchpoints** (minimal)

> **Note**: Always ensure `cognitive_trace_id` propagation and **no simulation code**

## 6 Emit the plan (Milestones → Epics → Issues)

> Output a plan where **each Issue unlocks the next**. One Issue == one file (or tiny set) with explicit Done criteria

### Milestones

Example template (tailor to actual inventory):

- **M1**: Contracts & Models Ready
- **M2**: Core Runtime Online (Batching, Schedulers, Mailbox hooks)
- **M3**: Bridge/Transport (HTTP/2, SSE, Observability Port)
- **M4**: Observability + Security (metrics/traces/bands/PEP touchpoints)
- **M5**: Hardening (Perf budgets, edge cases, retries, watermarks/hysteresis)

### For each Milestone, create 2–4 Epics

- Name, goal, acceptance criteria, affected components list from inventory

### For each Epic, create 5–15 Issues (strictly sequential)

Each Issue must include:

- **Why**: what this unlocks next
- **Inputs**: files/paths + any contract(s)
- **Steps**: exact edits (function/class names if present)
- **Observability**: metrics/traces to add
- **Perf/Policy**: budget checks, band/PEP notes if relevant
- **Done**: tests pass (`pytest -k <component>`), lints/validators green, zero TODO/NotImplemented

Also generate:

- **Dependency chain** like: `I1 → I2 → I3 → …` (no branches unless unavoidable)
- **Blocked-by note** if an Issue depends on a previous file finishing

## 7 Tests & budgets (baked into Issues)

1. For each runtime component Issue, pair a test Issue right after it:
   - Integration-first, real components
   - Forbid `sleep()`
   - Verify counters/timers and P95 guardrails where applicable
2. Provide the exact `pytest` commands to run

## 8 Optional: Create skeletons

1. Ask: "Create minimal code/test skeletons for **Issue #1 only**?"
   - If **Yes**, create just what's needed to start (no extra docs)

## 9 Final review

1. Summarize totals: components, stubs, Issues, Epics, Milestones
2. Reprint the strict sequence and first three commands/files to edit
3. Ask: "Proceed with Issue #1 now?"

---

**Notes**

- This is the **fast path**; it intentionally skips deep ADR reading
- Use `/plan-layer` (strict) if you later want ADR-aligned planning
- Honors `.windsurfrules`: no stray docs, no simulation code, contracts-first posture while staying pragmatic
