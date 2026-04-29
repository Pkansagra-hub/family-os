# K1 Flows — Section 3 (Tool Execution) Current State

**Source-of-truth design doc:** [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md) §3 (lines 1403–1881)
**Inventory:** [K1_FLOWS_ENUMERATED.md](K1_FLOWS_ENUMERATED.md) §3
**Companions:** [K1_FLOWS_SECTION1_CURRENT.md](K1_FLOWS_SECTION1_CURRENT.md) · [K1_FLOWS_SECTION2_CURRENT.md](K1_FLOWS_SECTION2_CURRENT.md)
**Verification basis:** subagent code-scan with **mandatory kernel-side wiring inspection** (`k1/kernel/service.py`, `k1/kernel/bootstrap.py`, `k1/kernel/adapters/`, `k1/kernel/ports/`)
**Empirical proof:** P1.1+P1.2 weather-prompt trace — Front called `discover_capabilities` then `invoke_capability(weather_forecast)` and composed text in 3 ReAct iterations
**Date:** 2026-04-24

Legend: ✅ wired · ⚠️ partial · ❌ missing · 🔵 stub-only / aspirational

---

## Section 3 Status Summary

| F# | Name | Status | One-line gap |
|---|---|---|---|
| F33 | Capability Fabric Tool Invocation | ✅ wired | Full hexagonal chain from Front → IDispatchPort → FabricDispatchAdapter → CapabilityFabric.execute, smoke-proven |
| F34 | MCP Tool Execution | ⚠️ partial | `MCPProvider` + `IMCPTransport` exist; **kernel never injects a transport in production** → MCPProvider can't be built |
| F35 | K0 Memory Operation | ⚠️ partial | `BridgeProvider` wired; bridge runs in **`SinkBridgeAdapter` mode (outbox file, not live K0)**; `recall_memory` uses separate `recall_fn` path |
| F36 | WASM Sandbox Execution | ⚠️ partial | `WASMProvider` wired; "WASM" runtimes are **pure-Python adapters**, no actual `.wasm`/`wasmtime`/`wasmer` anywhere; kernel injects no runtime |
| F37 | Tool Result Return | ✅ wired | `ToolResult` envelope flows back into ReAct loop messages; `k1.capability.completed.v1` event not emitted at concierge layer |
| F38 | Tool Result → LLM Context Staging | ⚠️ partial | No `ContextStager` class; flat `messages.append(_tool_result_to_msg(...))` in ReAct loop; no tier-aware buffer |
| F39 | K0 Query Port Recall | ⚠️ partial | **K1 side fully wired** (`RecallMemoryAdapter` → `build_recall_fn` → `bridge_client.query`); K0 `/k0/query.recall` endpoint undeployed → returns empty |
| F40 | WAL Driver Query | ❌ missing | No K0 WAL query driver — only the K0 bus event log exists |
| F41 | Vector Semantic Search | ❌ missing | No `IEmbeddingPort`, no `VectorIndex`, `data/faiss_union/` orphaned |
| F42 | Context Budget Application | ❌ missing | No `ContextBudgeter` class anywhere; only MW invariants and orchestrator routing have token budgets |

### Headline counts

| Status | Count | Flows |
|---|---|---|
| ✅ wired | **2** | F33, F37 |
| ⚠️ partial | **5** | F34, F35, F36, F38, F39 |
| ❌ missing | **3** | F40, F41, F42 |

**Headline finding:** the **K1 hexagonal wiring is solid for the local Fabric path** (F33, F37). The K1→K0 side has the **kernel wiring complete (F39 RecallMemoryAdapter)** but the K0-side endpoint is undeployed (MS-3 milestone), so all recall returns empty in production today. Tier 2 capability-provider plumbing (MCP/WASM) is structurally present but **the kernel never constructs concrete transports** for production — they only fire under test injection.

---

## F33 — Capability Fabric Tool Invocation ✅ wired

**End-to-end chain (verified hexagonal wiring):**

1. Front LLM picks `invoke_capability` → `execute_invoke_capability` at [k1/concierge/tools/implementations.py#L1221](../../k1/concierge/tools/implementations.py#L1221)
2. `ctx.dispatch.dispatch_direct(CapabilityRequest)` — `dispatch` is `IDispatchPort`
3. `FabricDispatchAdapter.dispatch_direct()` → `self._fabric.execute(request)` at [k1/concierge/adapters/fabric_dispatch.py#L31](../../k1/concierge/adapters/fabric_dispatch.py#L31)
4. **Kernel constructs the adapter** at [k1/kernel/service.py#L1420–L1424](../../k1/kernel/service.py#L1420): `FabricDispatchAdapter(fabric_port=session_fabric, orchestrator=...)`
5. Per-session `CapabilityFabric` built via `FabricFactory.create_with_ports(...)` at [k1/kernel/service.py#L1398](../../k1/kernel/service.py#L1398)
6. `discover_capabilities` mirrors via `ctx.dispatch.discover_capabilities(...)` at [implementations.py#L1098](../../k1/concierge/tools/implementations.py#L1098)

**Smoke-proven:** P1.1 weather trace — `discover_capabilities` → `invoke_capability(tool.execute.weather_forecast)` → composed text. `dispatched=0`, `tool_calls=0` post-loop.

---

## F34 — MCP Tool Execution ⚠️ partial

- `MCPProvider` + `IMCPTransport` exist at [k1/fabric/providers/mcp_provider.py](../../k1/fabric/providers/mcp_provider.py)
- `FabricFactory` accepts `mcp_transport=` kwarg, wires into `ProviderFactory` at [k1/fabric/factory.py#L368, L643–L661](../../k1/fabric/factory.py#L368)
- **Test fallback:** `TestMCPTransport(connected=True)` at [factory.py#L650–L651](../../k1/fabric/factory.py#L650)
- **Kernel never injects a production transport.** `KernelService._startup_tier1()` and `_create_session_tier2()` call `FabricFactory.create_shared()` / `create_with_ports()` with NO `mcp_transport=` arg
- `AutoDiscoveryMCPTransport` is mentioned in factory comments and `kernel.md` but **never imported or constructed** by `KernelService`
- Result: in production, `effective_mcp_transport=None` → `ProviderFactory` raises `ValueError("MCPProvider requires mcp_transport in port_deps")` if any MCP capability is attempted

**Gap:** wire an `AutoDiscoveryMCPTransport` (or any concrete `IMCPTransport`) at kernel construction. `k1/tools/mcp_servers/` directory would also need to exist for auto-discovery.

---

## F35 — K0 Memory Operation ⚠️ partial

Two parallel paths converge on K0:

**Path A — Fabric BridgeProvider** (the documented F35 path):
- `BridgeProvider` at [k1/fabric/providers/bridge_provider.py](../../k1/fabric/providers/bridge_provider.py) — supports `memory.recall`, `memory.store`, `memory.delta`, `checkpoint`, `feedback.signal`
- `BridgeConnectionAdapter(client=bridge_client)` wired into both shared and per-session Fabric at [k1/kernel/service.py#L1010](../../k1/kernel/service.py#L1010)
- `self._bridge` is either `SinkBridgeAdapter` (`bridge_enabled=True`) or `OfflineBridgeAdapter` at [service.py#L1003–L1009](../../k1/kernel/service.py#L1003)
- **`SinkBridgeAdapter` writes to an outbox file — NOT a live K0 HTTP connection.** Live transport would need `bridge.client.BridgeClient` (HTTP + HMAC/Ed25519)

**Path B — `recall_memory` tool**:
- [k1/concierge/tools/implementations.py#L932–L956](../../k1/concierge/tools/implementations.py#L932) — uses `ctx.recall_fn` (NOT `ctx.dispatch`)
- `recall_fn` wired by `RecallMemoryAdapter` (see F39)

**Gap:** live K0 round-trip needs HTTP `BridgeClient` instead of `SinkBridgeAdapter`. Both paths exist but neither hits live K0 today.

---

## F36 — WASM Sandbox Execution ⚠️ partial (functionally pure-Python)

- `WASMProvider` + `IWASMRuntime` at [k1/fabric/providers/wasm_provider.py](../../k1/fabric/providers/wasm_provider.py)
- Two existing "WASM" modules are **pure-Python adapters wrapping Python logic** — they implement `IWASMRuntime` structurally but execute no `.wasm` binary:
  - [k1/tools/wasm_modules/unit_convert/runtime.py](../../k1/tools/wasm_modules/unit_convert/runtime.py)
  - [k1/tools/wasm_modules/date_calc/runtime.py](../../k1/tools/wasm_modules/date_calc/runtime.py)
- No `wasmtime` / `wasmer` dependency anywhere in the codebase
- `FabricFactory` accepts `wasm_runtime=` kwarg; test fallback `TestWASMRuntime(available=True)` at [factory.py#L652](../../k1/fabric/factory.py#L652)
- **Kernel never injects a `wasm_runtime` in production** — same gap shape as MCP

**Gap:** True WASM isolation (memory, CPU, filesystem) does not exist. The "sandbox" is currently just an extra port boundary around in-process Python. Acceptable for the two modules' functions but the documented isolation guarantees are untrue.

---

## F37 — Tool Result Return ✅ wired (post-P1.1 path)

- `ToolResult` dataclass at [k1/concierge/tools/result_protocol.py](../../k1/concierge/tools/result_protocol.py)
- `execute_invoke_capability` returns `ToolResult(tool_name="invoke_capability", status="ok", data={"result": k1_result.data, ...})` at [implementations.py#L1221–L1245](../../k1/concierge/tools/implementations.py#L1221)
- ReAct loop collects `(ToolCall, ToolResult)` pairs → `_result_to_dict()` → `_tool_result_to_msg()` → `messages.append(...)` at [k1/concierge/react/loop.py#L898, L950](../../k1/concierge/react/loop.py#L898)
- `FabricDispatchAdapter.dispatch_direct()` returns `CapabilityResult`; mapped into `ToolResult.data` envelope at the tool boundary
- **`k1.capability.completed.v1` event:** NOT emitted at the concierge layer. May fire inside `CapabilityFabric.execute()` but unconfirmed
- Doc's two-path routing (`COMPANIONING` direct vs Orchestrator aggregation): post-P1.1 the LOW path goes Front-direct (no COMPANIONING node); MED/HIGH still flow through Orchestrator's `dispatch_envelope`

**Gap:** verify `k1.capability.completed.v1` emission inside `CapabilityFabric.execute()` if telemetry needs it.

---

## F38 — Tool Result → LLM Context Staging ⚠️ partial

- **No `ContextStager` / `TOOL_RESULT_BUFFER` class anywhere in `k1/`.** Doc invented it.
- Reality: flat `messages.append(_tool_result_to_msg(tc, _result_to_dict(result)))` in ReAct loop at [k1/concierge/react/loop.py#L950](../../k1/concierge/react/loop.py#L950)
- `tool_result_to_message` at [loop.py#L33](../../k1/concierge/react/loop.py#L33) — converts `ToolCallResult` + dict → `ModelMessage(role="tool", ...)`
- **No tier-differentiated buffer** (LOW ~500 vs MEDIUM/HIGH 2-8K). The messages list is shared across all iterations and passed to the LLM as-is

**Gap:** token-budget enforcement per-tier at tool-result inclusion time does not exist. Could add a budget pass before each LLM call if needed; current behavior is "let context window fill up naturally."

---

## F39 — K0 Query Port Recall ⚠️ partial (K1 wired, K0 undeployed)

**K1 side is fully hexagonal:**
1. [k1/kernel/service.py#L1435](../../k1/kernel/service.py#L1435) — `memory=RecallMemoryAdapter(build_recall_fn(self._bridge.get_client()))` — kernel wires per-session
2. [k1/concierge/adapters/recall_memory.py#L55](../../k1/concierge/adapters/recall_memory.py#L55) — `build_recall_fn(bridge_client)` builds closure calling `bridge_client.query(QueryEnvelope)` with `RecallSelector` list
3. [k1/concierge/tools/implementations.py#L790](../../k1/concierge/tools/implementations.py#L790) — `execute_recall_memory` uses `ctx.recall_fn` if wired

**K0 side is undeployed:**
- [bridge/client.py#L201](../../bridge/client.py#L201) — `SinkBridgeClient.query()` returns `RecallBundle.empty()` always (offline mode)
- [bridge/kernel/query_port.py#L30](../../bridge/kernel/query_port.py#L30) — `KernelQueryPort` exists, posts to `/k0/query.recall`; comment confirms **"K0 query endpoint does not exist yet"** (Issue 3.9.3 MS-3)
- `KernelQueryPort` (live HTTP transport) **never instantiated** by `KernelService` — `SinkBridgeClient` is the only bridge client

**Gap:** entire K0 query layer (`/k0/query.recall` endpoint, QUERY_AGG, WAL+VECTOR fanout) waits on MS-3 deployment. K1 needs zero changes once K0 ships — just swap `SinkBridgeClient` for `KernelQueryPort` (HTTP) in `KernelService._bridge` construction.

---

## F40 — WAL Driver Query ❌ missing

- No `WAL_DRIVER` class found in `k0/` or `bridge/`
- K0 has a WAL-mode bus (`k0/bus/`, `stream=wal`) for **persistence**, not a queryable episodic memory driver
- [bridge/kernel/query_port.py#L29](../../bridge/kernel/query_port.py#L29) — `_QUERY_PATH = "/k0/query.recall"` confirmed unimplemented on K0 side

**Gap:** K0 P02 episodic store + WAL recall endpoint not built. Recall always returns empty until built.

---

## F41 — Vector Semantic Search ❌ missing

- **No `IEmbeddingPort`, `VectorIndex`, or FAISS integration anywhere in `k1/` or `bridge/`**
- `data/faiss_union/` directory exists on disk (vector data at rest) but **no K1/bridge code reads it** — orphaned
- K0 has an `EmbeddingWorker` (tests at `k0/workers/embedding_worker.py`) for **async indexing**, not querying
- `k1/kernel/ports/` listed: bridge, bus, fabric, lifecycle, model_hub, orchestrator, planner, session_manager. **No `vector_port` or `embedding_port`**
- `build_recall_fn` sends `type="semantic"` selectors to `bridge_client.query()` → returns empty
- No `KernelQueryPort` routing to FAISS anywhere in kernel bootstrap

**Gap:** entire P08 Embedding Management + vector driver layer is undocumented code. Requires new port interface, kernel adapter, and K0-side FAISS integration.

---

## F42 — Context Budget Application ❌ missing

- **No `ContextBudgeter` class anywhere in `k1/`** (zero matches)
- Token budgeting in `k1/` is localized to:
  - MW's `budget_tokens` invariant ([k1/memory_writer/invariants.py#L183](../../k1/memory_writer/invariants.py#L183))
  - Orchestrator tier planner token budget ([k1/concierge/orchestrator/routing.py#L74](../../k1/concierge/orchestrator/routing.py#L74))
  - Neither is the documented F42 component
- Front actor assembles prompt via `DynamicPromptBuilder` ([k1/concierge/actors/front.py](../../k1/concierge/actors/front.py)) but no post-recall budget trimming
- `summarize_context` tool exists ([implementations.py](../../k1/concierge/tools/implementations.py)) — character-level truncation stub, not token-aware
- Since recall returns `[]` (F39/F40/F41), there's nothing to budget today anyway

**Gap:** no token-counting, no recency+relevance scoring, no 128K enforcement. Becomes urgent only after F39/F41 ship and recall starts returning real data.

---

## Cross-cutting findings

1. **K1 hexagonal wiring is healthier than it looks.** F33/F37 are end-to-end clean. F39 is K1-complete. The kernel correctly constructs adapters per-session. The "everything looks standalone" worry was right to verify — but the kernel-side ties hold up.
2. **MCP and WASM provider plumbing exists but is dormant.** Both have `Fabric` providers, port interfaces, and factory hooks. The kernel just doesn't construct concrete transports for production. Adding a single `mcp_transport=...` and `wasm_runtime=...` arg at the `FabricFactory.create_*` call sites would activate both.
3. **K0 is the dominant blocker for F39–F42.** All four flows depend on K0-side endpoints/services (`/k0/query.recall`, WAL driver, vector index) that are tracked under MS-3 but not yet deployed. K1's job is essentially done for F39.
4. **`k1.capability.completed.v1` event** is unverified at the concierge layer. If observability/audit needs it, confirm Fabric-internal emission.
5. **WASM "sandbox" is misleading.** The two existing modules are pure-Python; the documented isolation guarantees are aspirational. Decision needed: ship a real `wasmtime` adapter or rename the boundary to "computation port."
6. **Doc components that don't exist as classes:** `ContextStager`, `TOOL_RESULT_BUFFER`, `ContextBudgeter`, `WAL_DRIVER`, `VectorIndex`, `IEmbeddingPort`, `CAPABILITY_CONTEXT_BUILDER` — most are work-not-yet-done, not architectural fictions.

---

## Recommended next actions (priority order)

| Pri | Action | Touches | Source |
|---|---|---|---|
| P0 | Wait on or accelerate K0 MS-3 (`/k0/query.recall` + WAL + FAISS) — unblocks F39/F40/F41 | F39, F40, F41 | unchanged |
| P1 | Inject `AutoDiscoveryMCPTransport` (or any concrete `IMCPTransport`) at `KernelService._startup_tier1` Fabric construction | F34 | new |
| P1 | Decide WASM strategy: ship real `wasmtime` runtime OR rename port to remove "Sandbox" misnomer | F36 | new |
| P2 | Once F39/F41 return real data: introduce a `ContextBudgeter` (token-aware, recency+relevance) before LLM message assembly | F38, F42 | new |
| P2 | Swap `SinkBridgeClient` for `KernelQueryPort` (HTTP) when K0 endpoint ships | F35, F39 | unchanged |
| P3 | Update K1_FLOWS.md §3 to mark `ContextStager`, `TOOL_RESULT_BUFFER`, `WAL_DRIVER`, `VectorIndex`, `IEmbeddingPort`, `CAPABILITY_CONTEXT_BUILDER` as "not yet built" rather than implying they exist | doc | new |
| P3 | Confirm or wire `k1.capability.completed.v1` event emission inside `CapabilityFabric.execute()` if needed for telemetry | F37 | optional |

---

**Section 3 complete. Next:** §4 Orchestrator Flows (F43–F52) — 10 flows. F45 (DAGExecutor), F46 (Saga) and F50–F52 (workflows) are the heavy ones.
