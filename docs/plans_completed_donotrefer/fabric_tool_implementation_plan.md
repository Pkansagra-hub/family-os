# Fabric Tool Implementation Plan — MCP Servers, WASM Tools, E2E Validation

> **Status**: SKELETON
> **Created**: 2025-01-XX
> **Scope**: Phase 1-3 tool implementation for Fabric end-to-end validation
> **Depends on**: M1-M5 (ALL DONE, 2417 tests passing)

---

## 1. Goal

Build concrete MCP servers and WASM tools that exercise every Fabric subsystem end-to-end.
Tools selected to cover all 13 FAB invariants, both transport types (stdio/SSE), and WASM sandboxing.

---

## 2. Phase Overview

| Phase | Tools | Transport | FAB Coverage | Effort |
|-------|-------|-----------|-------------|--------|
| **P1** | mcp-calendar (local stdio) + date_calc (WASM) | stdio + WASM | FAB-01,02,03,04,05,06,07,09,10,11 | 2 weeks |
| **P2** | mcp-weather (remote SSE) + unit_convert (WASM) | SSE + WASM | FAB-04,08,12,13 + remote circuit-breaker | 1.5 weeks |
| **P3** | mcp-notes (local stdio) + mcp-recipes (remote SSE) | stdio + SSE | Agent composition, batch execution, multi-tool DAG | 2 weeks |

---

## 3. Phase 1: Calendar + Date Calculator

### 3.1 mcp-calendar (Local MCP Server — stdio)

**Purpose**: Family calendar management. Tests the full MCP stdio pipeline from contract to execution.

#### 3.1.1 Contracts

Create YAML contracts in `k1/contracts/tools/`:

| Contract File | Capability Name | Band | Description |
|---------------|----------------|------|-------------|
| `calendar_list_events.yaml` | `tool.read.calendar.list_events` | GREEN | List events by date range |
| `calendar_create_event.yaml` | `tool.write.calendar.create_event` | AMBER | Create a new calendar event |
| `calendar_delete_event.yaml` | `tool.write.calendar.delete_event` | AMBER | Delete an event by ID |

#### 3.1.2 MCP Server Implementation

Location: `k1/tools/mcp_servers/calendar/`

```
k1/tools/mcp_servers/calendar/
    __init__.py
    server.py          # MCP server entry point (stdio)
    handlers.py        # Tool handler functions
    storage.py         # SQLite backend (local, on-device)
    models.py          # CalendarEvent dataclass
```

**server.py**: Registers 3 tools with the MCP runtime. Reads/writes from local SQLite.
Communicates via stdio JSON-RPC.

**Key decisions**:
- Storage: SQLite file at `~/.familyos/calendar.db`
- No network access — pure local tool
- Transport: stdio (subprocess spawned by MCPProvider)
- Max latency: 200ms (local disk I/O)

#### 3.1.3 Fabric Wiring

1. Contract YAML scanned by ModuleLoader on startup (auto-discovery)
2. ProviderConfig entries map capability names to the calendar MCP server:
   - `provider_type: MCP`
   - `transport: STDIO`
   - `endpoint: python -m k1.tools.mcp_servers.calendar.server`
3. MCPProvider receives `IMCPTransport` (stdio variant) from FabricFactory
4. CircuitBreaker: 10s timeout, 3 failures/min

#### 3.1.4 Tests

| Test | Type | Validates |
|------|------|-----------|
| Contract parsing + registration | Unit | ModuleLoader scan, ContractValidator |
| Calendar CRUD via Fabric.execute() | Integration | Full 9-step pipeline |
| Schema validation on create_event output | Integration | OutputValidationPipeline |
| Safety band enforcement (GREEN read, AMBER write) | Integration | PolicyEngine |
| Circuit breaker trip on server crash | Integration | CircuitBreaker + HealthChecker |
| Event emission (invoked, completed, learning) | Integration | EventEmitter assertions |

---

### 3.2 date_calc (WASM Tool)

**Purpose**: Pure date arithmetic (days between dates, add/subtract days, weekday calculation).
Tests WASM sandbox pipeline.

#### 3.2.1 Contract

| Contract File | Capability Name | Band | Description |
|---------------|----------------|------|-------------|
| `date_calc.yaml` | `tool.execute.date_calc` | GREEN | Date arithmetic operations |

#### 3.2.2 WASM Module Implementation

Location: `k1/tools/wasm_modules/date_calc/`

```
k1/tools/wasm_modules/date_calc/
    src/
        lib.rs          # Rust source (or AssemblyScript/C)
    build/
        date_calc.wasm  # Compiled WASM binary
    README.md
```

**Operations** (via `operation` param):
- `days_between(start_date, end_date)` -> integer
- `add_days(date, days)` -> date string
- `weekday(date)` -> string ("Monday", etc.)
- `is_weekend(date)` -> boolean

**Sandbox constraints**:
- Memory: 4MB (dates need minimal memory)
- Timeout: 1s
- No network, no filesystem

#### 3.2.3 Fabric Wiring

1. Contract YAML auto-discovered by ModuleLoader
2. ProviderConfig:
   - `provider_type: WASM`
   - `module_path: k1/tools/wasm_modules/date_calc/build/date_calc.wasm`
   - `sandbox_memory_mb: 4`
   - `max_execution_ms: 1000`
3. WASMProvider receives `IWASMRuntime` port from FabricFactory
4. Module cached after first load

#### 3.2.4 Tests

| Test | Type | Validates |
|------|------|-----------|
| Contract parsing | Unit | WASM contract format |
| date_calc operations via Fabric.execute() | Integration | Full WASM sandbox pipeline |
| Memory limit enforcement | Integration | WASMSandboxConfig |
| Timeout enforcement | Integration | ProviderTimeoutError |
| Output schema validation | Integration | OutputValidationPipeline |

---

## 4. Phase 2: Weather + Unit Converter

### 4.1 mcp-weather (Remote MCP Server — SSE)

**Purpose**: Weather data retrieval. Tests remote MCP transport (SSE), circuit-breaker for network failures, and retry logic.

#### 4.1.1 Contracts

| Contract File | Capability Name | Band | Description |
|---------------|----------------|------|-------------|
| `weather_current.yaml` | `tool.read.weather.current` | GREEN | Current weather for a location |
| `weather_forecast.yaml` | `tool.read.weather.forecast` | GREEN | Multi-day forecast |

#### 4.1.2 MCP Server Implementation

Location: `k1/tools/mcp_servers/weather/`

```
k1/tools/mcp_servers/weather/
    __init__.py
    server.py          # MCP server entry point (SSE/HTTP)
    handlers.py        # Tool handler functions
    api_client.py      # Weather API client (OpenWeatherMap / weatherapi.com)
    cache.py           # Response cache (5-min TTL)
    models.py          # WeatherData, Forecast dataclasses
```

**Key decisions**:
- Transport: SSE (Server-Sent Events) for streaming support
- External API: weatherapi.com (free tier, 1M calls/month)
- Caching: 5-minute TTL to reduce API calls
- Endpoint: `https://weather.familyos.local/sse` (or localhost for dev)
- Max latency: 2s (network + API call)

#### 4.1.3 Fabric Wiring

1. Contracts auto-discovered by ModuleLoader
2. ProviderConfig:
   - `provider_type: MCP`
   - `transport: SSE`
   - `endpoint: https://weather.familyos.local/sse`
3. MCPProvider receives `IMCPTransport` (SSE variant)
4. CircuitBreaker: 15s timeout, 3 failures/min (remote defaults)
5. Tests must exercise: network failure -> CB open -> half-open -> close

#### 4.1.4 Tests

| Test | Type | Validates |
|------|------|-----------|
| Remote SSE transport connectivity | Integration | IMCPTransport SSE |
| Weather query via Fabric.execute() | Integration | Full remote pipeline |
| Circuit breaker open/half-open/close cycle | Integration | FAB-08 resilience |
| Cache hit (no API call) | Unit | Cache layer |
| Timeout on slow API response | Integration | ProviderTimeoutError |
| Retry logic on transient failure | Integration | FAB-12 retry semantics |

---

### 4.2 unit_convert (WASM Tool)

**Purpose**: Unit conversion (temperature, distance, weight, volume).
Tests WASM with slightly larger computation and validates sandbox isolation.

#### 4.2.1 Contract

| Contract File | Capability Name | Band | Description |
|---------------|----------------|------|-------------|
| `unit_convert.yaml` | `tool.execute.unit_convert` | GREEN | Unit conversion |

#### 4.2.2 WASM Module

Location: `k1/tools/wasm_modules/unit_convert/`

**Operations** (via `category` + `from_unit` + `to_unit` + `value`):
- Temperature: C/F/K
- Distance: km/mi/m/ft
- Weight: kg/lb/oz/g
- Volume: L/gal/ml/cup

**Sandbox**: 4MB, 1s, no network

#### 4.2.3 Tests

| Test | Type | Validates |
|------|------|-----------|
| All conversion categories | Integration | WASM execution correctness |
| Invalid unit pair rejection | Integration | Error propagation |
| Concurrent WASM executions | Integration | FAB-13 isolation |

---

## 5. Phase 3: Notes + Recipes (Composition)

### 5.1 mcp-notes (Local MCP Server — stdio)

**Purpose**: Notes and lists management. Tests a second local MCP server to validate multi-provider routing.

#### 5.1.1 Contracts

| Contract File | Capability Name | Band | Description |
|---------------|----------------|------|-------------|
| `notes_list.yaml` | `tool.read.notes.list` | GREEN | List notes |
| `notes_create.yaml` | `tool.write.notes.create` | AMBER | Create a note |
| `notes_search.yaml` | `tool.read.notes.search` | GREEN | Search notes by keyword |

#### 5.1.2 MCP Server

Location: `k1/tools/mcp_servers/notes/`
Storage: SQLite at `~/.familyos/notes.db`
Transport: stdio

---

### 5.2 mcp-recipes (Remote MCP Server — SSE)

**Purpose**: Recipe discovery and meal planning. Tests a second remote MCP to validate multi-remote routing.

#### 5.2.1 Contracts

| Contract File | Capability Name | Band | Description |
|---------------|----------------|------|-------------|
| `recipe_search.yaml` | `tool.read.recipes.search` | GREEN | Search recipes |
| `recipe_meal_plan.yaml` | `tool.write.recipes.meal_plan` | AMBER | Generate meal plan |

#### 5.2.2 MCP Server

Location: `k1/tools/mcp_servers/recipes/`
External API: Spoonacular or similar
Transport: SSE

---

### 5.3 Phase 3 Composition Tests

These tests validate multi-tool, multi-provider execution:

| Test | Type | Validates |
|------|------|-----------|
| execute_batch() PARALLEL: calendar + weather | Integration | BatchStrategy.PARALLEL |
| execute_batch() SEQUENTIAL: create note then search | Integration | BatchStrategy.SEQUENTIAL |
| execute_batch() DAG: search recipes -> create calendar event | Integration | BatchStrategy.DAG |
| Cross-provider resolution: 2 MCP + 1 WASM in batch | Integration | Resolver + multi-provider |
| Learning signal aggregation across batch | Integration | FAB-09 learning loop |

---

## 6. Directory Structure (Complete)

```
k1/
  contracts/
    tools/
      # Existing
      build_agent.yaml
      discover_capabilities.yaml
      find_prompts.yaml
      # Phase 1
      calendar_list_events.yaml
      calendar_create_event.yaml
      calendar_delete_event.yaml
      date_calc.yaml
      # Phase 2
      weather_current.yaml
      weather_forecast.yaml
      unit_convert.yaml
      # Phase 3
      notes_list.yaml
      notes_create.yaml
      notes_search.yaml
      recipe_search.yaml
      recipe_meal_plan.yaml

  tools/
    mcp_servers/
      calendar/
        __init__.py
        server.py
        handlers.py
        storage.py
        models.py
      weather/
        __init__.py
        server.py
        handlers.py
        api_client.py
        cache.py
        models.py
      notes/
        __init__.py
        server.py
        handlers.py
        storage.py
        models.py
      recipes/
        __init__.py
        server.py
        handlers.py
        api_client.py
        models.py
    wasm_modules/
      date_calc/
        src/lib.rs
        build/date_calc.wasm
        README.md
      unit_convert/
        src/lib.rs
        build/unit_convert.wasm
        README.md

tests/
  fabric/
    tools/
      test_calendar_contracts.py
      test_calendar_e2e.py
      test_weather_contracts.py
      test_weather_e2e.py
      test_notes_contracts.py
      test_notes_e2e.py
      test_recipes_contracts.py
      test_recipes_e2e.py
      test_date_calc_e2e.py
      test_unit_convert_e2e.py
      test_batch_composition.py
```

---

## 7. FAB Invariant Coverage Matrix

| Invariant | Phase 1 | Phase 2 | Phase 3 |
|-----------|---------|---------|---------|
| FAB-01 Immutable Request | calendar, date_calc | weather, unit_convert | notes, recipes |
| FAB-02 Contract Validation | calendar contracts | weather contracts | notes, recipe contracts |
| FAB-03 Stateless Execution | calendar CRUD | weather queries | batch CRUD |
| FAB-04 Timeout Enforcement | calendar 10s, date_calc 1s | weather 15s | batch timeouts |
| FAB-05 Safety Band | calendar GREEN/AMBER | weather GREEN | notes AMBER, recipes AMBER |
| FAB-06 Schema Validation | calendar output | weather output | notes output |
| FAB-07 Provider Resolution | stdio MCP + WASM | SSE MCP + WASM | multi-provider |
| FAB-08 Circuit Breaker | calendar crash test | weather network fail | batch failure cascade |
| FAB-09 Learning Signal | calendar signals | weather signals | batch aggregation |
| FAB-10 Event Emission | calendar events | weather events | batch events |
| FAB-11 Policy Engine | calendar safety check | weather routing | cross-provider policy |
| FAB-12 Retry Semantics | — | weather transient retry | batch retry |
| FAB-13 Sandbox Isolation | date_calc memory limit | unit_convert concurrent | — |

---

## 8. Implementation Order (Per Phase)

For each tool, follow this exact sequence:

1. **Contract YAML** — Write and validate via `ContractValidator`
2. **Models** — Define input/output dataclasses
3. **Server/Module** — Implement MCP server or WASM module
4. **Handlers** — Wire tool logic to MCP protocol or WASM exports
5. **ProviderConfig** — Register provider configuration
6. **Integration Test** — Test via `FabricFactory.create_for_testing()`
7. **Circuit Breaker Test** — Failure modes and recovery
8. **Event Assertion Test** — Verify lifecycle events emitted

---

## 9. Prerequisites

- [ ] M1-M5 production code (DONE, 2417 tests)
- [ ] IMCPTransport stdio adapter (exists in mcp_provider.py as Protocol)
- [ ] IMCPTransport SSE adapter (exists in mcp_provider.py as Protocol)
- [ ] IWASMRuntime adapter (exists in wasm_provider.py as Protocol)
- [ ] Test adapters for all ports (exist in factory.py create_standalone)

---

## 10. Success Criteria

- All 16 tool contracts parse and register without errors
- All tools execute via `Fabric.execute()` with correct results
- All 13 FAB invariants exercised by at least one test
- `execute_batch()` works with PARALLEL, SEQUENTIAL, and DAG strategies
- Circuit breakers trip and recover correctly for both local and remote
- Total regression stays green (2417 + new tests)
