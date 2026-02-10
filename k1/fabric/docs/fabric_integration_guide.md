# Fabric Integration Guide -- How Tools, Prompts, and Providers Connect

> Living reference for the Capability Fabric integration architecture.
> Covers every registration path, execution path, and adapter pattern.

---

## 1. The Two Planes

Fabric operates on two separate planes that are often confused:

| Plane | Purpose | Core Component |
|-------|---------|----------------|
| **Contract Plane** | "What capabilities exist?" -- names, schemas, safety bands, versions | `CapabilityRegistry` via `ModuleLoader` |
| **Execution Plane** | "How to actually run it?" -- transport routing, runtime dispatch | `ProviderFactory` -> Provider -> Transport/Runtime |

A capability must be registered on BOTH planes to execute:
- Contract Plane: `ModuleLoader` loads YAML -> `CapabilityRegistry`
- Execution Plane: `_auto_register_providers()` scans contracts -> `ProviderRegistry`

The bridge between them is `_auto_register_providers()` in `factory.py` (Step 20b),
which reads every contract's `provider_id` and creates a `ProviderConfig` entry in
the `ProviderRegistry`.

---

## 2. Contract Registration (3 Paths)

### Path 1: YAML Contract Scan (startup)

```
k1/contracts/tools/*.yaml      -+
k1/contracts/agents/*.yaml       +-> ModuleLoader.scan_directory()
k1/contracts/prompts/*.yaml      |     -> parse_contract() + ContractValidator
k1/contracts/workflows/*.yaml  -+     -> CapabilityRegistry.register()
```

- Scans 4 subdirs: `tools/`, `agents/`, `prompts/`, `workflows/`
- Default root: `k1/contracts/` (set in `factory.py` as `_DEFAULT_CONTRACTS_DIR`)
- Called at `factory.py` Step 20 via `module_loader.start(watch=False)`
- Currently: **15 tool contracts** in `k1/contracts/tools/`
- No `agents/`, `prompts/`, or `workflows/` subdirs exist yet

### Path 2: YAML Hot-Reload (runtime, daemon thread)

```
File change on disk -> ModuleLoader._watch_loop()
  -> _poll_once() detects new/modified/deleted YAML
  -> parse_contract() + validate -> registry.register() or .unregister()
  -> emits k1.fabric.module.contract_hot_reloaded.v1
```

- Daemon thread polling at 2s intervals (`_poll_interval_s`)
- Detects create / modify / delete
- Started by `module_loader.start(watch=True)` (currently `watch=False` in factory)
- Hot-swap: modified files unregister old contract, register new one

### Path 3: Programmatic Dict Registration (runtime, dynamic)

```
Dict payload -> ModuleLoader.register_from_dict(dict, contract_type=...)
  -> parse_contract_body() + ContractValidator
  -> CapabilityRegistry.register()
```

- Designed for runtime tool discovery (MCP tools from external sources)
- Used by `ProactiveGapDetector._handle_mcp_tool_discovered()`
- Also usable by any code that needs to inject a contract dynamically

---

## 3. Execution Routing (6 Provider Types)

After a contract is registered, `fabric.execute(request)` resolves it to a provider.
The `ProviderFactory` has 6 registered handler types:

| Provider Type | Provider Class | Key Dependencies | Purpose |
|--------------|----------------|------------------|---------|
| **MCP** | `MCPProvider` | `IMCPTransport` | External tool calls via MCP protocol |
| **WASM** | `WASMProvider` | `IWASMRuntime` | Sandboxed computation modules |
| **BRIDGE** | `BridgeProvider` | `IBridgePort` | Cross-kernel calls (K0<->K1) and IFL |
| **AGENT** | `AgentProvider` | `IModelGateway` + `IStateReader` + `IDeltaBus` + `ContextBuilder` | LLM-based agent execution |
| **WORKFLOW** | `WorkflowProvider` | `workflow_registry` + `capability_lookup` + `orchestrator` | Multi-step workflow orchestration |
| **CONCIERGE** | `ConciergeProvider` | `concierge_router` | User-facing concierge routing |

Handler registration happens at `factory.py` Step 9 via `_register_provider_handlers()`.

### Execution Pipeline (fabric.execute)

```
CapabilityRequest
  -> Step 1: Resolver.resolve() (registry lookup + provider matching + selection)
  -> Step 2: PolicyEngine (security, affective, cognitive, QoS checks)
  -> Step 3: CircuitBreaker check
  -> Step 4: ContextBuilder.build() (for agents)
  -> Step 5: Provider.execute(params) -- actual execution
  -> Step 6: OutputValidationPipeline.validate() (structural -> schema -> semantic)
  -> Step 7: Coercion (if schema validation soft-fails)
  -> Step 8: Learning signal emission
  -> Step 9: Return CapabilityResult
```

---

## 4. MCP Tools -- Full Integration (2 Layers)

### Layer 1: Contract (what the tool IS)

YAML files in `k1/contracts/tools/`:

```yaml
tool_contract:
  name: "tool.read.weather_forecast"   # 3-segment: tool.<verb>.<name>
  provider_type: "MCP"
  provider_id: "weather_mcp_sse"
```

Current MCP tool contracts (10):
- `tool.read.weather_forecast`, `tool.read.weather_current` (weather_mcp_sse)
- `tool.read.calendar_list_events`, `tool.write.calendar_create_event`, `tool.write.calendar_delete_event` (calendar_mcp_stdio)
- `tool.read.notes_list`, `tool.read.notes_search`, `tool.write.notes_create` (notes_mcp_stdio)
- `tool.read.recipe_search`, `tool.write.recipe_meal_plan` (recipes_mcp_sse)

### Layer 2: Transport (how to CALL it)

Two `IMCPTransport` implementations:

| Transport | Class | File | Purpose |
|-----------|-------|------|---------|
| **TestMCPTransport** | `TestMCPTransport` | `adapters/test_mcp_transport.py` | Testing -- canned responses via `add_response()` |
| **AutoDiscoveryMCPTransport** | `AutoDiscoveryMCPTransport` | `adapters/auto_mcp_transport.py` | Production -- auto-discovers MCP servers |

### AutoDiscoveryMCPTransport: 3 Dispatch Patterns

Scans `k1/tools/mcp_servers/` at construction time.

| Priority | Pattern | Detection | Dispatch |
|----------|---------|-----------|----------|
| 1 | **Handler** | `register_handler(tool_name, async_fn)` | Direct async call |
| 2 | **JSON-RPC** | Class ending in `MCPServer` + `TOOLS` list + `handle_message()` | JSON-RPC envelope -> `handle_message()` |
| 3 | **FastMCP** | `FastMCP` instance + `@mcp.tool()` decorators | Direct function call with `**kwargs` |

Current MCP servers (4 auto-discovered):

| Server | Pattern | Location | Tools |
|--------|---------|----------|-------|
| calendar | JSON-RPC | `k1/tools/mcp_servers/calendar/` | list_events, create_event, delete_event |
| weather | JSON-RPC | `k1/tools/mcp_servers/weather/` | current, forecast |
| notes | FastMCP | `k1/tools/mcp_servers/notes/` | list, search, create |
| recipes | FastMCP | `k1/tools/mcp_servers/recipes/` | search, meal_plan |

Internal/meta handlers (registered post-construction, not auto-discovered):
- `tool.write.build_agent` -- Agent builder
- `tool.read.discover_capabilities` -- Capability discovery
- `tool.read.find_prompts` -- Prompt finder

### Name Resolution

`_strip_tool_prefix()` converts Fabric capability names to MCP function names:
```
"tool.read.notes_list"  -> "notes_list"   (used for FastMCP routing)
"tool.read.weather_forecast" -> kept as-is (used for JSON-RPC routing)
```

---

## 5. WASM Tools -- Full Integration (2 Layers)

### Layer 1: Contract (YAML)

```yaml
tool_contract:
  name: "tool.execute.date_calc"
  provider_type: "WASM"
  provider_id: "date_calc_wasm"
```

Current WASM tool contracts (2):
- `tool.execute.date_calc` (date_calc_wasm)
- `tool.execute.unit_convert` (unit_convert_wasm)

### Layer 2: Runtime

Two `IWASMRuntime` implementations:

| Runtime | Class | File | Purpose |
|---------|-------|------|---------|
| **TestWASMRuntime** | `TestWASMRuntime` | `adapters/test_wasm_runtime.py` | Testing -- canned results via `add_executor()` |
| **AutoDiscoveryWASMRuntime** | `AutoDiscoveryWASMRuntime` | `adapters/auto_wasm_runtime.py` | Production -- auto-discovers executors |

### AutoDiscoveryWASMRuntime

Scans `k1/tools/wasm_modules/` for subdirectories with `executor.py` exporting
`execute(params: dict) -> dict`.

Current WASM modules (2):
- `k1/tools/wasm_modules/date_calc/executor.py`
- `k1/tools/wasm_modules/unit_convert/executor.py`

---

## 6. BRIDGE Provider -- Cross-Kernel and IFL

`BridgeProvider` handles two distinct use cases via `IBridgePort`:

### Use Case 1: K0 Communication

Cross-kernel memory, queries, and commands:
```
BridgeProvider -> IBridgePort.send_command(topic, body)  -- one-way
BridgeProvider -> IBridgePort.query(selectors)           -- request/response
```

### Use Case 2: IFL (Interkernel Fabric Language) -- External World

ALL external services and IoT devices route through the Bridge IFL layer:

```
Fabric execute(tool.execute.home.hue.set_brightness)
  -> BridgeProvider
  -> IBridgePort
  -> ConnectorGateway (security, auth, rate limiting)
  -> IFL Runtime (manifest, protocol translation)
  -> IFL Adapter Dispatch
     -> Company-Hosted: HTTP/2 to com.philips.hue endpoint
     -> WASM-Sandboxed: Local WASM execution (offline capable)
```

See: `architecture_diagrams/bridge/interkernel_fabric_layer.mmd` for full IFL design.

---

## 7. Prompt System -- Dual Identity

Prompts have two independent integration points:

### System 1: Prompt as Capability Contract

```
k1/contracts/prompts/*.yaml -> ModuleLoader -> CapabilityRegistry
```

- Prompt contracts are registered as capabilities (like tools)
- Found via `RetrievalEngine.find_relevant_prompts()`
- Have names like `invitation_drafter_v1` (simpler naming pattern)
- Currently: **no YAML files exist** in `k1/contracts/prompts/`

### System 2: Prompt Template System (Port)

```
IPromptSystemPort protocol:
  resolve(template_name) -> PromptTemplate
  compile(template, variables) -> str
```

- Used by `ContextBuilder` (factory.py Step 8) to build agent context
- Completely separate from the contract registry
- Two implementations:

| Adapter | Class | File | Purpose |
|---------|-------|------|---------|
| **TestPromptSystemAdapter** | `TestPromptSystemAdapter` | `adapters/test_prompt_system.py` | In-memory dict of PromptTemplate objects |
| **Production adapter** | TBD (5.2) | -- | Would connect to a real prompt store |

---

## 8. Dynamic Discovery -- ProactiveGapDetector

`ProactiveGapDetector` (in `events/event_emitter.py`) subscribes to 4 events
and reacts to runtime changes:

| Event | Handler | Action |
|-------|---------|--------|
| `k1.fabric.capability.registered.v1` | `_handle_registered` | Emits `contract_updated` (breaking=False) |
| `k1.fabric.capability.unregistered.v1` | `_handle_unregistered` | Emits `contract_updated` (breaking=True) |
| `k1.fabric.capability.version_conflict.v1` | `_handle_version_conflict` | Emits `contract_updated` (breaking depends on resolution) |
| `k1.mcp.tool.discovered.v1` | `_handle_mcp_tool_discovered` | Attempts `register_from_dict()` |

### Known Bug: `_mcp_tool_to_contract_dict()`

The MCP tool discovery path generates invalid contracts:

| Bug | Generated | Expected |
|-----|-----------|----------|
| 4-segment name | `tool.execute.mcp.get_weather` | `tool.execute.get_weather` (3 segments) |
| Wrong output key | `output_schema` | `output` |
| Extra field in inputs | `required: true/false` per input | Not part of InputSpec |

Impact: Dormant. The Orchestrator does not yet emit `k1.mcp.tool.discovered.v1` events.
All current tools are registered via YAML (Path 1).

---

## 9. Factory Construction -- 20-Step Bootstrap

`_construct_fabric()` in `factory.py` builds everything in dependency-safe order:

| Step | Component | Dependencies |
|------|-----------|-------------|
| 2 | ContractValidator | None |
| 3 | CapabilityRegistry | validator, event_port |
| 4 | ModuleLoader | registry, contracts_dir, event_port, validator |
| 5 | PolicyEngine | state_reader (security, affective, cognitive, QoS) |
| 6 | ProviderRegistry | event_port |
| 7 | CircuitBreakers | shared dict |
| 8 | ContextBuilder | state_reader, prompt_system |
| 9 | ProviderFactory | all port deps (bridge, model_gateway, mcp_transport, wasm_runtime, ...) |
| 10 | Resolution chain | registry, provider_registry, provider_factory, policy_engine |
| 11 | RetrievalEngine | embedding_index, hard_filter, soft_ranker, top_k, embedding_port |
| 12 | OutputValidationPipeline | state_reader, event_port |
| 13 | HealthChecker + AvailabilityTracker | provider_registry, event_port |
| 14 | Wire bidirectional callbacks | -- |
| 15 | FabricDispatcher (production only) | event_port |
| 16 | EventEmitter | event_port |
| 17 | CapabilityFabric (facade) | resolver, context_builder, validation, event_emitter, registry, ... |
| 18 | FabricRetrieval | retrieval_engine |
| 19 | CapabilityRegistryAPI | registry |
| 20 | Bootstrap: scan contracts + auto-register providers + wire ProactiveGapDetector |

### Three Factory Methods

| Method | Transport | Events | Use |
|--------|-----------|--------|-----|
| `create_standalone()` | TestMCPTransport, TestWASMRuntime | No capture | Development, examples |
| `create_for_testing()` | Test or injected | Capture mode | Integration tests |
| `create_with_ports()` | Injected | Injected | Production |

---

## 10. Adding a New Tool (Quickstart)

### MCP Tool (server-based)

1. Create server: `k1/tools/mcp_servers/<name>/server.py`
   - JSON-RPC: class `*MCPServer` + `TOOLS` list + `handle_message()`
   - FastMCP: `FastMCP` instance + `@mcp.tool()` decorators
2. Create contract: `k1/contracts/tools/<name>.yaml`
   - `name: "tool.<verb>.<name>"` (3 segments, lowercase)
   - `provider_type: "MCP"`
   - `provider_id: "<name>_mcp_<transport>"` (stdio or sse)
3. Done. `AutoDiscoveryMCPTransport` finds the server; `ModuleLoader` loads the contract.

### WASM Tool (computation module)

1. Create executor: `k1/tools/wasm_modules/<name>/executor.py`
   - Must export `execute(params: dict) -> dict`
2. Create contract: `k1/contracts/tools/<name>.yaml`
   - `name: "tool.execute.<name>"` (3 segments)
   - `provider_type: "WASM"`
   - `provider_id: "<name>_wasm"`
3. Done. `AutoDiscoveryWASMRuntime` finds the executor; `ModuleLoader` loads the contract.

### IFL Tool (external service / IoT)

The IFL path is architecturally designed but not yet fully implemented:

1. Company publishes IFL adapter with signed manifest
2. User connects adapter via OAuth in FamilyOS app
3. `ManifestTranslator` auto-generates tool contracts from manifest
4. Contracts auto-registered in Capability Registry
5. Execution routes through: Fabric -> BridgeProvider -> ConnectorGateway -> IFL Runtime -> Adapter

Tool names for IFL follow a 5-segment pattern:
`tool.<verb>.<category>.<adapter>.<action>`
Example: `tool.execute.home.hue.set_brightness`

---

## 11. Name Convention Summary

| Contract Type | Pattern | Example |
|--------------|---------|---------|
| Tool (current) | `tool.<verb>.<name>` | `tool.read.weather_forecast` |
| Tool (IFL future) | `tool.<verb>.<category>.<adapter>.<action>` | `tool.execute.home.hue.set_brightness` |
| Agent | `agent.<verb>.<name>` | `agent.execute.curiosity_agent` |
| Prompt | `<name>(_v<N>)?` | `invitation_drafter_v1` |
| Workflow | `workflow.run.<name>` | `workflow.run.morning_routine` |

Validated by `_NAME_PATTERNS` in `core/contract_validator.py`.

**Note:** The IFL 5-segment pattern (`tool.<verb>.<category>.<adapter>.<action>`) is
defined in the architecture diagrams but the current `ContractValidator` only allows
3 segments. This will need a validator update when IFL goes live.

---

## 12. File Reference

| Component | File |
|-----------|------|
| Factory (composition root) | `k1/fabric/factory.py` |
| CapabilityFabric (facade) | `k1/fabric/fabric.py` |
| ModuleLoader | `k1/fabric/core/module_loader.py` |
| ContractValidator | `k1/fabric/core/contract_validator.py` |
| CapabilityRegistry | `k1/fabric/core/registry.py` |
| ProviderFactory | `k1/fabric/provider_resolution/provider_factory.py` |
| ProviderRegistry | `k1/fabric/provider_resolution/provider_registry.py` |
| Resolver | `k1/fabric/provider_resolution/resolver.py` |
| MCPProvider | `k1/fabric/providers/mcp_provider.py` |
| WASMProvider | `k1/fabric/providers/wasm_provider.py` |
| BridgeProvider | `k1/fabric/providers/bridge_provider.py` |
| AgentProvider | `k1/fabric/providers/agent_provider.py` |
| WorkflowProvider | `k1/fabric/providers/workflow_provider.py` |
| ConciergeProvider | `k1/fabric/providers/concierge_provider.py` |
| AutoDiscoveryMCPTransport | `k1/fabric/adapters/auto_mcp_transport.py` |
| AutoDiscoveryWASMRuntime | `k1/fabric/adapters/auto_wasm_runtime.py` |
| TestMCPTransport | `k1/fabric/adapters/test_mcp_transport.py` |
| TestWASMRuntime | `k1/fabric/adapters/test_wasm_runtime.py` |
| TestPromptSystemAdapter | `k1/fabric/adapters/test_prompt_system.py` |
| EventEmitter + ProactiveGapDetector | `k1/fabric/events/event_emitter.py` |
| OutputValidationPipeline | `k1/fabric/validation/pipeline.py` |
| IPromptSystemPort | `k1/fabric/ports/prompt_system.py` |
| Bridge Architecture | `architecture_diagrams/bridge/bridge_architecture.mmd` |
| IFL Architecture | `architecture_diagrams/bridge/interkernel_fabric_layer.mmd` |
