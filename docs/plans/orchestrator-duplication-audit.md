# Orchestrator Plan Duplication Audit

**Date**: 2025-01-XX
**Source**: `docs/plans/orchestrator-implementation-plan.md` (1320 lines, 9 milestones)
**Audited Against**: Fabric codebase, Planner.mmd, Concierge.mmd

---

## Executive Summary

The orchestrator plan is **narcissistic** -- it pulls responsibilities into the Orchestrator that are explicitly owned by Fabric, Concierge, and Planner per the authoritative `.mmd` architecture specs and already-built code. The plan is approximately **75-80% legitimate** (M1-M4 core, M6 adapters, M7-M9 test/ops infrastructure is mostly correct) but contains **significant overreach** concentrated in M5 and scattered across types, configs, ADRs, factory construction, tests, and documentation.

**Severity Scale**:
- **CRITICAL**: Entire milestone/epic duplicates existing module. DELETE.
- **HIGH**: Plan issue creates types/code that belong to another module. TRANSFER or DELETE.
- **MEDIUM**: Plan issue blurs ownership boundary. REWRITE to delegate.
- **LOW**: Plan issue references another module's concept -- acceptable if thin wrapper, problematic if re-implementing.

---

## CRITICAL: M5 Connector Ecosystem (7 issues) -- ENTIRE MILESTONE IS FABRIC'S JOB

**Severity**: CRITICAL -- DELETE ENTIRE MILESTONE

The plan's Service #6 "ConnectorManager" (lines ~635-696) creates a full MCP lifecycle manager inside Orchestrator. Fabric ALREADY owns and has built ALL of this:

| Plan Issue | What It Creates | Fabric Already Has |
|---|---|---|
| 5.1.1 MCPToolDiscovery | Scan `mcp_servers.yaml`, discover MCP tools | `k1/fabric/adapters/auto_mcp_transport.py` (597 lines) -- `AutoDiscoveryMCPTransport` scans `k1/tools/mcp_servers/` at construction, zero-config |
| 5.1.2 MCPCapabilityRegistrar | Register discovered tools into Fabric | `auto_mcp_transport.py` builds routing table automatically; `provider_registry.py` (369 lines) manages provider registration |
| 5.1.3 MCPProviderFactory | Create MCP provider instances per server | `k1/fabric/providers/mcp_provider.py` (516 lines) -- full `MCPProvider` with stdio/SSE/streamable-HTTP transport |
| 5.1.4 ConnectorSandbox | CPU/memory/timeout limits per MCP server | `breaker_config.py` -- per-provider CB configs (MCP_LOCAL 10s timeout, MCP_REMOTE 15s). `concurrency/timeout.py` handles execution limits |
| 5.1.5 ConnectorManager | Orchestrate discovery + registration + factory + sandbox | `k1/fabric/factory.py` -- `FabricFactory` wires all providers, CB, health, resolution at startup |
| 5.1.6 Re-Discovery Loop | Periodic MCP re-scan for new/removed servers | `k1/fabric/health/health_checker.py` (767 lines) -- periodic health checks with CB integration, availability tracking |
| 5.1.7 K0ProxyClient | Route IFL commands through Bridge | This is a Bridge concern, NOT Orchestrator |

**Evidence**:
- `mcp_provider.py` exports: `MCPProvider`, `MCPRequest`, `MCPResponse`, `IMCPTransport`, error hierarchy
- `auto_mcp_transport.py` exports: `AutoDiscoveryMCPTransport` with `_scan_mcp_servers()`, `_build_routing_table()`, auto-registration of JSON-RPC and FastMCP servers
- Tests proving real execution: `test_auto_discovery.py`, `test_weather_e2e.py`, `test_smoke_real_tools.py`

**Action**: Delete M5 entirely. Delete `M5-connector-ecosystem-worktickets.md`. Remove Service #6 from plan executive summary. Orchestrator should call `fabric_port.execute()` and trust Fabric to handle MCP.

---

## HIGH: Types/Config That Belong to Other Modules

### H1: Issue 1.2.14 -- ConnectorHealthStatus type

**Severity**: HIGH -- DELETE

Plan creates `ConnectorHealthStatus` (server_name, url, status, tools_count, last_health_check, circuit_breaker_state) inside Orchestrator types. This is Fabric's health data.

- Fabric already has: `ProviderHealth` in `types.py`, `HealthCheckResult` in `health_checker.py`, `ProviderStatus` enum
- Orchestrator has NO business tracking MCP server health details

**Action**: Delete. If Orchestrator needs health info, read it via `fabric_port.query_health()`.

### H2: Issue 1.2.22 -- OrchestratorConfig MCP fields

**Severity**: HIGH -- REMOVE MCP FIELDS

Plan defines `OrchestratorConfig` with these MCP-specific fields:
- `mcp_discovery_interval_ms: int = 60000`
- `mcp_max_servers: int = 20`

These are Fabric configuration values. Fabric's `HealthCheckerConfig` already controls check intervals. Fabric's `FabricFactory` controls max provider limits.

**Action**: Remove `mcp_discovery_interval_ms` and `mcp_max_servers` from OrchestratorConfig. Keep the rest (mailbox_depth, max_dag_steps, etc.) which are legitimately Orchestrator config.

### H3: Issue 1.2.23 -- CircuitBreakerConfig/State ownership confusion

**Severity**: HIGH -- REWRITE

Plan defines `CircuitBreakerConfig` and `CircuitBreakerState` types inside Orchestrator with 4 named CBs:
- `CB_PLANNER`
- `CB_FABRIC`
- `CB_MCP`
- `CB_BRIDGE`

**Who actually owns these CBs per concierge.mmd (the authoritative source)?**

| CB | Owner per concierge.mmd | Plan Claims |
|---|---|---|
| CB_ORCHESTRATOR | `FabricOrchestratorAdapter` in Concierge | Plan doesn't mention (correct!) |
| CB_PLANNER | `FabricOrchestratorAdapter` in Concierge | Plan puts it in Orchestrator (WRONG) |
| CB_FABRIC | `FabricOrchestratorAdapter` in Concierge | Plan puts it in Orchestrator (WRONG) |
| CB_MCP | `FabricOrchestratorAdapter` in Concierge | Plan puts it in Orchestrator (WRONG) |
| CB_SESSIONSTATE | `SessionKernelAdapter` in Concierge | N/A |
| CB_SSE | `SSEOutputAdapter` in Concierge | N/A |
| CB_MODEL | `UltraBERTAdapter`/`ModelGatewayAdapter` in Concierge | N/A |

Additionally, Fabric has its OWN per-provider CB system: `k1/fabric/circuit_breaker/breaker.py` (663 lines) with `CircuitBreakerConfig`, `CircuitBreakerState`, per-provider configs in `breaker_config.py` (201 lines).

**The architecture**:
- **Concierge** owns the inter-module CBs (CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC, CB_MCP) via `FabricOrchestratorAdapter`
- **Fabric** owns the per-provider internal CBs (per MCP server, per agent, per WASM, etc.)
- **Orchestrator** should own ZERO circuit breakers

**Action**: Remove all CB type definitions from Orchestrator. Orchestrator's `ErrorRouter` can classify errors FROM Fabric that indicate CB states, but it must NOT own/manage CBs. Rewrite ErrorRouter to consume CB state events, not manage CB instances.

### H4: Issue 1.1.10 -- ADR "MCP Connector Security Model"

**Severity**: HIGH -- TRANSFER TO FABRIC

This ADR defines MCP tool isolation, sandboxing, and capability scoping. All MCP security is Fabric's domain since Fabric owns the providers, transport layer, and execution.

**Action**: Move this ADR to Fabric's ADR set. Orchestrator should reference Fabric's security guarantees, not define its own.

---

## HIGH: Factory Construction Steps That Build Fabric's Infrastructure

### H5: Issue 6.2.1 Factory Step 15 -- ConnectorManager construction

**Severity**: HIGH -- DELETE

Plan's `OrchestratorFactory` step 15 constructs:
```
ConnectorManager(
    mcp_discovery=MCPToolDiscovery(...),
    capability_registrar=MCPCapabilityRegistrar(...),
    provider_factory=MCPProviderFactory(...),
    sandbox=ConnectorSandbox(...),
    config=OrchestratorConfig.mcp_*
)
```

All of these are Fabric's classes. ConnectorManager should not exist in Orchestrator.

**Action**: Delete step 15 entirely. Orchestrator factory should have ~14 steps, not 15.

### H6: Issue 6.2.2 init() Step 4 -- `connector_manager.discover_and_register()`

**Severity**: HIGH -- DELETE

Plan's `OrchestratorService.init()` step 4 calls `connector_manager.discover_and_register()`. This is Fabric's job at Fabric startup (via `FabricFactory` + `AutoDiscoveryMCPTransport`).

**Action**: Delete step 4 from init(). Renumber remaining steps.

---

## HIGH: Test Issues That Test Fabric's Code

### H7: Issue 7.1.6 -- ConnectorManager unit tests (~35 tests)

**Severity**: HIGH -- DELETE

Tests MCP discovery, registration, provider factory, sandbox, re-discovery, K0 proxy -- all Fabric functionality.

**Action**: Delete entirely. These tests belong in `tests/k1/fabric/`.

### H8: Issue 7.3A.4 -- MCP re-discovery e2e tests (~10 tests)

**Severity**: HIGH -- DELETE or REWRITE

Tests MCP server crash -> CB_MCP opens -> tools marked UNAVAILABLE -> re-discovery -> tools re-registered. This entire lifecycle is Fabric's responsibility.

**If kept**: Rewrite to test Orchestrator's RESPONSE to Fabric reporting capability unavailability (via ConstraintResolver), NOT to test MCP re-discovery itself.

### H9: Issue 9.2.6 -- MCP server disconnect chaos tests (~8 tests)

**Severity**: HIGH -- REWRITE

Tests MCP server failure mid-step. The MCP connection handling is Fabric's job. What Orchestrator should test: "Fabric returns error for step -> ErrorRouter classifies -> retry/fail path."

**Action**: Rewrite to test from Orchestrator's perspective (Fabric returns error), not MCP transport layer.

---

## HIGH: Documentation That Documents Fabric's Domain

### H10: Issue 9.3.4 -- Connector Administration Guide

**Severity**: HIGH -- TRANSFER TO FABRIC

Documents `mcp_servers.yaml` schema, sandbox config, K0 proxy settings, MCP server troubleshooting, health monitoring. ALL Fabric's operational domain.

**Action**: Move to `k1/fabric/docs/`. Orchestrator's docs should reference Fabric's connector guide, not duplicate it.

---

## MEDIUM: Tier Degradation Ownership Confusion

### M1: Issue 7.1.7 tests (items 13-16) + 7.3A.2 -- Tier degradation cascade

**Severity**: MEDIUM -- REWRITE

Plan defines tier degradation logic inside Orchestrator's ErrorRouter:
- CB_PLANNER OPEN -> HIGH degrades to MEDIUM
- CB_ORCHESTRATOR OPEN -> MEDIUM degrades to LOW
- CB_FABRIC OPEN -> emit DEGRADED result

Per **concierge.mmd**: tier degradation is Concierge's `FabricOrchestratorAdapter` responsibility:
```
TIER_DEGRADATION: HIGH->MED->LOW->canned
```

Concierge owns: `CB_ORCHESTRATOR + CB_PLANNER + CB_FABRIC + CB_MCP` per FabricOrchestratorAdapter definition.

**The split should be**:
- **Concierge** decides tier degradation (owns the CBs, knows the fallback chain)
- **Orchestrator** can report "Planner unavailable" to Concierge, but should NOT auto-degrade tiers
- Exception: Orchestrator's ErrorRouter can classify errors and return appropriate error codes so Concierge can decide degradation

**Action**: Rewrite ErrorRouter tests to verify error CLASSIFICATION (correct), but remove tier degradation DECISIONS from Orchestrator. Tier degradation is Concierge's FSM responsibility.

---

## MEDIUM: Observability Gauge for MCP

### M2: Issue 8.2.1 item 16 -- `orchestrator.mcp.connected_servers` gauge

**Severity**: MEDIUM -- DELETE

Orchestrator should NOT track MCP server connection count. Fabric already has health tracking and metrics.

**Action**: Delete this gauge. Orchestrator metrics should track: DAG, mailbox, workflow, pending_plans, pending_hil. Not MCP servers.

### M3: Issue 8.4.1 item 12 -- MCPServerDisconnect alert

**Severity**: MEDIUM -- DELETE or TRANSFER

Alert for MCP server disconnection belongs in Fabric's alerting, not Orchestrator's.

**Action**: Delete from Orchestrator alerts. Add to Fabric's alert definitions if not already there.

---

## MEDIUM: Plan Concepts That Blur Boundaries

### M4: Plan Executive Summary Service #6 "ConnectorManager"

**Severity**: MEDIUM -- DELETE SERVICE

Plan lists 6 services in executive summary. Service #6 is:
```
ConnectorManager: MCP discovery, registration, provider factory, sandbox, re-discovery (~35 tests)
```

Orchestrator should have 5 services, not 6.

**Action**: Remove Service #6 from summary. Update service count and test count projections (~530 - 35 = ~495 tests).

### M5: Issue 9.4.1 Production Checklist -- MCP references

**Severity**: MEDIUM -- CLEANUP

Production checklist references:
- "MCP re-discovery" under feature validation
- ConnectorManager tests under test validation
- Connector guide under documentation validation

**Action**: Remove all MCP/Connector references from the production checklist.

---

## LOW: Acceptable Boundary Interactions (NOT duplications)

These plan items correctly DELEGATE to other modules via ports:

| Plan Issue | What It Does | Status |
|---|---|---|
| 2.1.3 dispatch_medium | Uses `fabric_port.execute()` | CORRECT -- delegates to Fabric |
| 3.1.2 check_capabilities | Uses `fabric_port.query_registry()` | CORRECT -- reads from Fabric |
| 2.3.1 ErrorRouter | Classifies errors FROM Fabric adapters | CORRECT -- consumes Fabric errors |
| 7.2.5 MicroReplanCheckpoint | Sends `MicroReplanRequest` to `planner_port` | CORRECT -- delegates to Planner |
| 7.5.1 Fabric integration tests | Wires real Fabric via `create_with_ports()` | CORRECT -- cross-module test |
| 3.2.1 OutputSchemaGuard | Validates step output against schema | CORRECT -- Orchestrator's guard pipeline, different from Fabric's output_validation |

**Note on OutputSchemaGuard vs Fabric's output_validation**: These are NOT duplicates. Fabric's `output_validation/pipeline.py` validates PROVIDER output (structural/schema/semantic). Orchestrator's OutputSchemaGuard validates STEP output against the PLAN's expected schema. Different layers, different concerns.

---

## Summary: Impact by Milestone

| Milestone | Issues | Duplications Found | Action |
|---|---|---|---|
| M1 Foundation | 53 | 4 (1.1.10, 1.2.14, 1.2.22 partial, 1.2.23) | Fix 4 issues |
| M2 Core DAG | 19 | 0 | Clean |
| M3 Constraints | 15 | 0 | Clean |
| M4 Workflows | 13 | 0 | Clean |
| **M5 Connectors** | **7** | **7 (ALL)** | **DELETE ENTIRE MILESTONE** |
| M6 Adapters/Factory | ~12 | 2 (6.2.1 step 15, 6.2.2 step 4) | Fix 2 steps |
| M7 Testing | ~30 | 3 (7.1.6, 7.3A.4, part of 7.1.7) | Delete 1 test file, rewrite 2 |
| M8 Observability | ~4 | 2 (gauge 16, alert 12) | Delete 2 items |
| M9 Production | ~4 | 2 (9.3.4, 9.4.1 references) | Transfer 1 doc, cleanup 1 checklist |

**Total duplication count**: ~20 items across the plan
**Clean items**: ~80% of the plan is legitimate Orchestrator work(M1 types/contracts, M2 DAG executor, M3 guards, M4 workflows, M6 adapter wiring, M7 testing infrastructure, M8 metrics/tracing, M9 load/chaos)

---

## Recommended Fix Sequence

1. **Delete M5 entirely** (7 issues + worktickets file)
2. **Remove Service #6** from executive summary
3. **Fix M1 types**: Delete 1.2.14, strip MCP fields from 1.2.22, rewrite 1.2.23 to remove CB ownership
4. **Transfer ADR 1.1.10** to Fabric
5. **Fix M6 factory**: Delete step 15, delete init step 4
6. **Fix M7 tests**: Delete 7.1.6, rewrite 7.3A.4, strip tier degradation decisions from 7.1.7
7. **Fix M8**: Delete gauge 16, delete alert 12
8. **Transfer 9.3.4** connector guide to Fabric docs
9. **Cleanup 9.4.1** production checklist
10. **Update test count** projections (~495 tests, not ~530)
