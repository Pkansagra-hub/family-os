# Concierge Scan — Batch 01: Ports, Adapters, Types, Config

> Exhaustive scan of root files + `adapters/` + `types/` + `config/`
> Generated from line-by-line source reading.

---

## 1. `k1/concierge/ports.py` (150 lines)

### Purpose
Central hexagonal port definitions for the Concierge subsystem.
8 total ports: 4 re-exported aliases of existing Protocols + 4 new thin Protocol wrappers.

### Imports (cross-component dependencies)

| Import | Source Package |
|--------|---------------|
| `Envelope` | `k1.bus.envelope` |
| `IBus` | `k1.bus.ports.bus` |
| `IFabricPort` | `k1.concierge.fabric.ports` |
| `Phase1Pipeline`, `Phase1Result` | `k1.concierge.fsm.phase1` |
| `AggregatedResult`, `TaskEnvelope` | `k1.concierge.orchestrator.types` |
| `CapabilityRequest`, `CapabilityResult` | `k1.fabric.types` |
| `IModelHubPort` | `k1.model_hub.ports.hub_port` |
| `HubChunk`, `HubRequest`, `HubResponse` | `k1.model_hub.types` |

### Re-exported Protocol Aliases

| Alias | Canonical Type | Canonical Location |
|-------|---------------|-------------------|
| `IClassificationPort` | `Phase1Pipeline` | `k1.concierge.fsm.phase1` |
| `ILLMPort` | `IModelHubPort` | `k1.model_hub.ports.hub_port` |
| `IDeltaPort` | `IBus` | `k1.bus.ports.bus` |

(`IFabricPort` is imported from `k1.concierge.fabric.ports` but NOT aliased — re-exported directly.)

### New Protocol Definitions

#### `IInputPort(Protocol)` — `@runtime_checkable`
Abstracts transport→bus user input path.

| Method | Params | Return | Async |
|--------|--------|--------|-------|
| `receive()` | `self` | `Envelope` | `async` |
| `has_buffered()` | `self` | `bool` | sync |

#### `IOutputPort(Protocol)` — `@runtime_checkable`
Abstracts front→bus response emission path.

| Method | Params | Return | Async |
|--------|--------|--------|-------|
| `send(envelope)` | `self, envelope: Envelope` | `None` | `async` |

#### `IStatePort(Protocol)` — `@runtime_checkable`
Abstracts SessionState read surface (the `ss: Any` duck-typed object).

| Method | Params | Return | Async |
|--------|--------|--------|-------|
| `get_section(name)` | `self, name: str` | `Any` | sync |
| `get_snapshot()` | `self` | `dict[str, Any]` | sync |

#### `IDispatchPort(Protocol)` — `@runtime_checkable`
Unifies Fabric (LOW tier) + Orchestrator (MED/HIGH tier) dispatch.

| Method | Params | Return | Async |
|--------|--------|--------|-------|
| `dispatch_direct(request)` | `self, request: CapabilityRequest` | `CapabilityResult` | `async` |
| `dispatch_envelope(envelope)` | `self, envelope: TaskEnvelope` | `AggregatedResult` | `async` |

#### `IMemoryPort(Protocol)` — `@runtime_checkable`
Abstracts the `recall_fn: Callable` closure into a proper Protocol.

| Method | Params | Return | Async |
|--------|--------|--------|-------|
| `recall(query, memory_types, max_results)` | `self, query: str, memory_types: list[str] \| None = None, max_results: int = 5` | `list[dict[str, Any]]` | `async` |

### Summary: All 8 Ports

| Port | Type | Protocol Source | Key Method(s) |
|------|------|----------------|--------------|
| `IInputPort` | New Protocol | `ports.py` | `receive() -> Envelope`, `has_buffered() -> bool` |
| `IOutputPort` | New Protocol | `ports.py` | `send(Envelope) -> None` |
| `IClassificationPort` | Alias | `Phase1Pipeline` | `classify(str) -> Phase1Result` |
| `ILLMPort` | Alias | `IModelHubPort` | `execute(HubRequest) -> HubResponse`, `stream_execute() -> AsyncIterator[HubChunk]` |
| `IStatePort` | New Protocol | `ports.py` | `get_section(str) -> Any`, `get_snapshot() -> dict` |
| `IDispatchPort` | New Protocol | `ports.py` | `dispatch_direct(CapabilityRequest) -> CapabilityResult`, `dispatch_envelope(TaskEnvelope) -> AggregatedResult` |
| `IDeltaPort` | Alias | `IBus` | `publish(Envelope)`, `subscribe(pattern, handler) -> SubscriptionHandle`, `unsubscribe(handle)` |
| `IMemoryPort` | New Protocol | `ports.py` | `recall(str, list[str]\|None, int) -> list[dict]` |

---

## 2. `k1/concierge/__init__.py` (0 lines)

Empty file. Namespace package marker only.

---

## 3. `k1/concierge/types/__init__.py` (33 lines)

### Purpose
Re-export hub for types used by Concierge port Protocols. No new types invented.
Single import target for adapters and tests.

### Imports (cross-component dependencies)

| Import | Source Package |
|--------|---------------|
| `Envelope` | `k1.bus.envelope` |
| `SubscriptionHandle` | `k1.bus.ports` |
| `IBus` | `k1.bus.ports.bus` |
| `Phase1Result` | `k1.concierge.fsm.phase1` |
| `AggregatedResult`, `TaskEnvelope` | `k1.concierge.orchestrator.types` |
| `CapabilityRequest`, `CapabilityResult` | `k1.fabric.types` |
| `HubChunk`, `HubRequest`, `HubResponse` | `k1.model_hub.types` |

### `__all__` exports
```python
[
    "AggregatedResult",
    "CapabilityRequest",
    "CapabilityResult",
    "Envelope",
    "HubChunk",
    "HubRequest",
    "HubResponse",
    "IBus",
    "Phase1Result",
    "SubscriptionHandle",
    "TaskEnvelope",
]
```

### Definitions
None — pure re-export module.

---

## 4. `k1/concierge/config/` (3 files)

### 4a. `config/__init__.py` (3 lines)
Re-export shim — delegates entirely to `poc.k1_poc.config`:
```python
from poc.k1_poc.config import *
from poc.k1_poc.config import __all__
```
Cross-component dep: `poc.k1_poc.config`

### 4b. `config/loader.py` (17 lines)
Re-export shim — delegates entirely to `poc.k1_poc.config.loader`.
Uses `sys.modules` patching to make this module a full alias:
```python
import poc.k1_poc.config.loader as _canonical
from poc.k1_poc.config.loader import *
# Then patches all names from _canonical onto this module via setattr loop (x3)
```
Cross-component dep: `poc.k1_poc.config.loader`

### 4c. `config/defaults.yaml` (~30+ lines visible)
YAML configuration defaults. Partial contents:
```yaml
actors:
  back:
    max_iterations:
      LOW: 10
      MEDIUM: 14
      HIGH: 24
    budget_floor: 4
    history_window: 5
    default_safety_band: "AMBER"
    # HITL suspension timeout in seconds (rest truncated)
```

---

## 5. `k1/concierge/adapters/` (22 files)

### 5a. `adapters/__init__.py` (~95 lines)

**Purpose:** Package init that eagerly imports lightweight adapters and defers heavy ones.

**Eagerly imported (in `__all__`):**

| Symbol | Module | Port |
|--------|--------|------|
| `TestInputAdapter` | `test_input` | `IInputPort` |
| `TestOutputAdapter` | `test_output` | `IOutputPort` |
| `StubPhase1Pipeline` | `test_classification` | `IClassificationPort` |
| `InMemoryStateAdapter` | `test_state` | `IStatePort` |
| `MockDispatchAdapter` | `test_dispatch` | `IDispatchPort` |
| `create_test_bus` | `test_delta` | `IDeltaPort` |
| `MockMemoryAdapter` | `test_memory` | `IMemoryPort` |
| `BusInputAdapter` | `bus_input` | `IInputPort` |
| `BusOutputAdapter` | `bus_output` | `IOutputPort` |
| `SSMStateAdapter` | `ssm_state` | `IStatePort` |
| `FabricDispatchAdapter` | `fabric_dispatch` | `IDispatchPort` |
| `RecallMemoryAdapter` | `recall_memory` | `IMemoryPort` |
| `NullSessionStateReaderAdapter` | `null_state_reader` | `ISessionStateReader` |
| `NullDeltaBusAdapter` | `null_delta_bus` | `IDeltaBusPort` |
| `NullEventSubscriptionAdapter` | `null_event_subscription` | `IEventSubscriptionPort` |
| `NullBridgeWriteAdapter` | `null_bridge_write` | `IBridgeWritePort` |
| `SnapshotStateReadAdapter` | `snapshot_state_read` | `IStateReadPort` |

**Deferred (import from individual module):**

| Symbol | Module | Reason |
|--------|--------|--------|
| `TestModelHubBridge` | `test_llm` | Heavy dep chain |
| `ModelHubPOCBridge` | `hub_llm` | Gemini SDK |
| `UltraBERTPhase1Pipeline` | `ultrabert_classification` | UltraBERT DLL |
| `BusFactory` | `local_delta` | (Re-export) |

---

### 5b. Production Adapters

#### `BusInputAdapter` — `adapters/bus_input.py` (~48 lines)
**Implements:** `IInputPort`
**Cross-component imports:**
- `Envelope` from `k1.bus.envelope`
- `IBus` from `k1.bus.ports.bus`
- `TOPIC_USER_INPUT` from `k1.concierge.bus.topics`

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, bus: IBus) -> None` | Subscribes to TOPIC_USER_INPUT, creates async Queue |
| `_on_input` | `(self, envelope: Envelope) -> None` | Bus handler — buffers envelope |
| `receive` | `async (self) -> Envelope` | Blocks until next input envelope |
| `has_buffered` | `(self) -> bool` | True if queue non-empty |
| `close` | `(self) -> None` | Unsubscribes from bus |

**Instance attributes:** `_bus: IBus`, `_queue: asyncio.Queue[Envelope]`, `_handle` (SubscriptionHandle)

---

#### `BusOutputAdapter` — `adapters/bus_output.py` (~32 lines)
**Implements:** `IOutputPort`
**Cross-component imports:**
- `Envelope` from `k1.bus.envelope`
- `IBus` from `k1.bus.ports.bus`

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, bus: IBus) -> None` | Stores bus ref |
| `send` | `async (self, envelope: Envelope) -> None` | Publishes envelope to bus |

**Instance attributes:** `_bus: IBus`

---

#### `FabricDispatchAdapter` — `adapters/fabric_dispatch.py` (~40 lines)
**Implements:** `IDispatchPort`
**Cross-component imports:**
- `AggregatedResult`, `TaskEnvelope` from `k1.concierge.orchestrator.types`
- `CapabilityRequest`, `CapabilityResult` from `k1.fabric.types`

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, fabric_port: Any, orchestrator: Any = None) -> None` | Stores fabric + optional orchestrator |
| `dispatch_direct` | `async (self, request: CapabilityRequest) -> CapabilityResult` | Delegates to `_fabric.execute(request)` |
| `dispatch_envelope` | `async (self, envelope: TaskEnvelope) -> AggregatedResult` | Delegates to `_orchestrator.handle_task(envelope)`, raises RuntimeError if orchestrator is None |

**Instance attributes:** `_fabric: Any`, `_orchestrator: Any`

---

#### `SSMStateAdapter` — `adapters/ssm_state.py` (~43 lines)
**Implements:** `IStatePort`
**Cross-component imports:** None (only `typing`)

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, session_state: Any) -> None` | Wraps SSM instance |
| `get_section` | `(self, name: str) -> Any` | Delegates to `_ss.get_section(name)` |
| `get_snapshot` | `(self) -> dict[str, Any]` | Iterates `_ss.sections` or `_ss._sections`, calls `to_dict()` on each if available |

**Instance attributes:** `_ss: Any`

---

#### `RecallMemoryAdapter` — `adapters/recall_memory.py` (~30 lines)
**Implements:** `IMemoryPort`
**Cross-component imports:** None (only `typing`)

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, recall_fn: Callable[..., Any]) -> None` | Wraps recall_fn closure |
| `recall` | `async (self, query: str, memory_types: list[str] \| None = None, max_results: int = 5) -> list[dict[str, Any]]` | Delegates to `_recall_fn(query, memory_types=..., max_results=...)` |

**Instance attributes:** `_recall_fn: Callable[..., Any]`

---

#### `ModelHubPOCBridge` — `adapters/hub_llm.py` (~11 lines)
**Implements:** `ILLMPort`
**Pure re-export:**
```python
from k1.concierge.llm.model_hub_bridge import ModelHubPOCBridge
```
Cross-component dep: `k1.concierge.llm.model_hub_bridge`

---

#### `UltraBERTPhase1Pipeline` — `adapters/ultrabert_classification.py` (~11 lines)
**Implements:** `IClassificationPort`
**Pure re-export:**
```python
from k1.concierge.fsm.ultrabert_phase1 import UltraBERTPhase1Pipeline
```
Cross-component dep: `k1.concierge.fsm.ultrabert_phase1`

---

#### `BusFactory` — `adapters/local_delta.py` (~14 lines)
**Implements:** `IDeltaPort` (via factory method)
**Pure re-export:**
```python
from k1.bus.factory import BusFactory
```
Usage: `BusFactory.create_local()`, `BusFactory.create_local_ordered()`
Cross-component dep: `k1.bus.factory`

---

### 5c. Test Adapters

#### `TestInputAdapter` — `adapters/test_input.py` (~38 lines)
**Implements:** `IInputPort`
**Cross-component imports:**
- `Envelope` from `k1.bus.envelope`
- `build_user_input` from `k1.concierge.bus.builders`

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self) -> None` | Creates empty async Queue |
| `receive` | `async (self) -> Envelope` | Returns next queued envelope |
| `has_buffered` | `(self) -> bool` | True if queue non-empty |
| `inject` | `(self, envelope: Envelope) -> None` | Push pre-built envelope |
| `inject_text` | `(self, text: str, session_id: str = "test") -> None` | Build & push user-input envelope from text |

**Instance attributes:** `_queue: asyncio.Queue[Envelope]`

---

#### `TestOutputAdapter` — `adapters/test_output.py` (~35 lines)
**Implements:** `IOutputPort`
**Cross-component imports:**
- `Envelope` from `k1.bus.envelope`

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self) -> None` | Creates empty `sent` list |
| `send` | `async (self, envelope: Envelope) -> None` | Appends to `sent` |
| `get_sent` | `(self, topic: str \| None = None) -> list[Envelope]` | Return sent, optionally filtered by topic |
| `last` | `(self) -> Envelope \| None` | Most recently sent envelope |
| `clear` | `(self) -> None` | Reset captured envelopes |

**Instance attributes:** `sent: list[Envelope]`

---

#### `StubPhase1Pipeline` — `adapters/test_classification.py` (~10 lines)
**Implements:** `IClassificationPort`
**Pure re-export:**
```python
from k1.concierge.fsm.phase1 import StubPhase1Pipeline
```
Cross-component dep: `k1.concierge.fsm.phase1`

---

#### `TestModelHubBridge` — `adapters/test_llm.py` (~11 lines)
**Implements:** `ILLMPort`
**Pure re-export:**
```python
from k1.concierge.llm.test_model_hub_bridge import TestModelHubBridge
```
Cross-component dep: `k1.concierge.llm.test_model_hub_bridge`

---

#### `InMemoryStateAdapter` — `adapters/test_state.py` (~37 lines)
**Implements:** `IStatePort`
**Cross-component imports:** None (only `types`, `typing`)

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self) -> None` | Creates empty `_sections` dict |
| `get_section` | `(self, name: str) -> Any` | Returns `_sections.get(name)` |
| `get_snapshot` | `(self) -> dict[str, Any]` | Returns copy of `_sections` |
| `seed` | `(self, name: str, section: Any) -> None` | Seed with arbitrary object |
| `seed_dict` | `(self, name: str, data: dict[str, Any]) -> None` | Seed with SimpleNamespace (supports `.attr` access) |
| `clear` | `(self) -> None` | Remove all sections |

**Instance attributes:** `_sections: dict[str, Any]`

---

#### `MockDispatchAdapter` — `adapters/test_dispatch.py` (~57 lines)
**Implements:** `IDispatchPort`
**Cross-component imports:**
- `AggregatedResult` from `k1.concierge.orchestrator.types`
- `CapabilityResult as POCCapabilityResult` from `k1.concierge.orchestrator.types`
- `TaskEnvelope` from `k1.concierge.orchestrator.types`
- `CapabilityRequest`, `CapabilityResult` from `k1.fabric.types`

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self) -> None` | Creates empty scripted result lists & call logs |
| `dispatch_direct` | `async (self, request: CapabilityRequest) -> CapabilityResult` | Returns scripted or default `CapabilityResult.success_result(...)` |
| `dispatch_envelope` | `async (self, envelope: TaskEnvelope) -> AggregatedResult` | Returns scripted or default `AggregatedResult.from_medium(...)` |
| `script_direct` | `(self, results: list[CapabilityResult]) -> None` | Queue scripted direct results |
| `script_envelope` | `(self, results: list[AggregatedResult]) -> None` | Queue scripted envelope results |

**Instance attributes:** `_direct_results: list[CapabilityResult]`, `_envelope_results: list[AggregatedResult]`, `direct_calls: list[CapabilityRequest]`, `envelope_calls: list[TaskEnvelope]`

---

#### `create_test_bus()` — `adapters/test_delta.py` (~14 lines)
**Implements:** `IDeltaPort`
**Cross-component imports:**
- `BusFactory` from `k1.bus.factory`

| Function | Signature | Description |
|----------|-----------|-------------|
| `create_test_bus` | `() -> (bus instance)` | Creates local in-process bus via `BusFactory.create_local()` |

---

#### `MockMemoryAdapter` — `adapters/test_memory.py` (~40 lines)
**Implements:** `IMemoryPort`
**Cross-component imports:** None (only `typing`)

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, memories: list[dict[str, Any]] \| None = None) -> None` | Seeds with optional memories list |
| `recall` | `async (self, query: str, memory_types: list[str] \| None = None, max_results: int = 5) -> list[dict[str, Any]]` | Returns filtered memories; logs call to `recall_calls` |
| `seed` | `(self, memories: list[dict[str, Any]]) -> None` | Replace all memories |
| `clear` | `(self) -> None` | Clear memories and call log |

**Instance attributes:** `_memories: list[dict[str, Any]]`, `recall_calls: list[tuple[str, list[str] | None, int]]`

---

### 5d. Null / Startup-Tier Adapters (Phase 2)

#### `NullBridgeWriteAdapter` — `adapters/null_bridge_write.py` (~48 lines)
**Satisfies:** `IBridgeWritePort` (from `k1.orchestrator.ports.bridge_write_port`)
**Decision:** SIM-D-33 (Bridge offline fallback)
**Cross-component imports:** None (only `typing`)

| Member | Signature | Description |
|--------|-----------|-------------|
| `submit_audit` | `async (self, run_manifest: Dict[str, Any], trace_id: str) -> None` | Silent drop |
| `write_wal` | `async (self, dag_id: str, entry_type: str, payload: Dict[str, Any], trace_id: str) -> None` | Silent drop |
| `read_wal` | `async (self, dag_id: str) -> Optional[List[Dict[str, Any]]]` | Returns `None` |
| `list_wal_ids` | `async (self) -> List[str]` | Returns `[]` |
| `submit_deferred_result` | `async (self, result: Dict[str, Any], workflow_id: str, trace_id: str) -> None` | Silent drop |

---

#### `NullDeltaBusAdapter` — `adapters/null_delta_bus.py` (~31 lines)
**Satisfies:** `IDeltaBusPort` (from `k1.fabric.ports.delta_bus`)
**Gap:** SIM-GAP-47
**Cross-component imports:** None (only `typing`)

| Member | Signature | Description |
|--------|-----------|-------------|
| `emit_delta` | `(self, agent_id: str, delta_type: str, section: str, data: Dict[str, Any]) -> None` | Silent drop |

---

#### `NullEventSubscriptionAdapter` — `adapters/null_event_subscription.py` (~38 lines)
**Satisfies:** `IEventSubscriptionPort` (from `k1.orchestrator.ports.event_subscription_port`)
**Gap:** SIM-GAP-51
**Cross-component imports:**
- `SubscriptionHandle` from `k1.fabric.ports.event_port`

| Member | Signature | Description |
|--------|-----------|-------------|
| `subscribe` | `(self, topic: str, handler: Callable[[str, Dict[str, Any]], None]) -> SubscriptionHandle` | Returns `SubscriptionHandle(subscription_id="null", topic=topic)` |
| `unsubscribe` | `(self, handle: SubscriptionHandle) -> bool` | Returns `False` |
| `emit` | `(self, topic: str, payload: Dict[str, Any]) -> None` | Silent drop |

---

#### `NullSessionStateReaderAdapter` — `adapters/null_state_reader.py` (~34 lines)
**Satisfies:** `ISessionStateReader` (from `k1.fabric.ports.state_reader`)
**Gap:** SIM-GAP-47
**Cross-component imports:**
- `SessionSnapshot` from `k1.fabric.ports.state_reader`

| Member | Signature | Description |
|--------|-----------|-------------|
| `read_section` | `(self, session_id: str, section: str) -> Optional[Dict[str, Any]]` | Returns `None` |
| `read_sections` | `(self, session_id: str, names: List[str]) -> Dict[str, Any]` | Returns `{}` |
| `get_snapshot` | `(self, session_id: str) -> SessionSnapshot` | Returns `SessionSnapshot(session_id=session_id)` |

---

#### `SnapshotStateReadAdapter` — `adapters/snapshot_state_read.py` (~50 lines)
**Satisfies:** `IStateReadPort` (from `k1.planner.ports.state_read_port`)
**Decision:** SIM-D-38; **Gap:** SIM-GAP-49
**Cross-component imports:**
- `SessionSnapshot` from `k1.fabric.ports.state_reader`

| Member | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self) -> None` | Creates `_snapshot = None` |
| `bind` | `(self, snapshot: Optional[SessionSnapshot]) -> None` | Sets active snapshot before each pipeline run |
| `read_sections` | `async (self, sections: List[str], trace_id: str = "") -> SessionSnapshot` | Returns filtered SessionSnapshot with only requested section names |

**Instance attributes:** `_snapshot: Optional[SessionSnapshot]`

---

## 6. Cross-Component Dependency Summary

### External k1.* package imports across ALL files in this batch:

| Source Package | Used By |
|----------------|---------|
| `k1.bus.envelope` | `ports.py`, `types/`, `bus_input`, `bus_output`, `test_input`, `test_output` |
| `k1.bus.ports.bus` (`IBus`) | `ports.py`, `types/`, `bus_input`, `bus_output` |
| `k1.bus.ports` (`SubscriptionHandle`) | `types/` |
| `k1.bus.factory` (`BusFactory`) | `local_delta`, `test_delta` |
| `k1.concierge.bus.topics` (`TOPIC_USER_INPUT`) | `bus_input` |
| `k1.concierge.bus.builders` (`build_user_input`) | `test_input` |
| `k1.concierge.fabric.ports` (`IFabricPort`) | `ports.py` |
| `k1.concierge.fsm.phase1` (`Phase1Pipeline`, `Phase1Result`, `StubPhase1Pipeline`) | `ports.py`, `types/`, `test_classification` |
| `k1.concierge.fsm.ultrabert_phase1` (`UltraBERTPhase1Pipeline`) | `ultrabert_classification` |
| `k1.concierge.llm.model_hub_bridge` (`ModelHubPOCBridge`) | `hub_llm` |
| `k1.concierge.llm.test_model_hub_bridge` (`TestModelHubBridge`) | `test_llm` |
| `k1.concierge.orchestrator.types` (`AggregatedResult`, `TaskEnvelope`, `CapabilityResult as POCCapabilityResult`) | `ports.py`, `types/`, `fabric_dispatch`, `test_dispatch` |
| `k1.fabric.types` (`CapabilityRequest`, `CapabilityResult`) | `ports.py`, `types/`, `fabric_dispatch`, `test_dispatch` |
| `k1.fabric.ports.event_port` (`SubscriptionHandle`) | `null_event_subscription` |
| `k1.fabric.ports.state_reader` (`SessionSnapshot`) | `null_state_reader`, `snapshot_state_read` |
| `k1.model_hub.ports.hub_port` (`IModelHubPort`) | `ports.py` |
| `k1.model_hub.types` (`HubChunk`, `HubRequest`, `HubResponse`) | `ports.py`, `types/` |
| `poc.k1_poc.config` | `config/__init__.py` |
| `poc.k1_poc.config.loader` | `config/loader.py` |

---

## 7. Adapter → Port Mapping Matrix

| Port Protocol | Production Adapter | Test Adapter | Null/Startup Adapter |
|--------------|-------------------|-------------|---------------------|
| `IInputPort` | `BusInputAdapter` | `TestInputAdapter` | — |
| `IOutputPort` | `BusOutputAdapter` | `TestOutputAdapter` | — |
| `IClassificationPort` | `UltraBERTPhase1Pipeline` (re-export) | `StubPhase1Pipeline` (re-export) | — |
| `ILLMPort` | `ModelHubPOCBridge` (re-export) | `TestModelHubBridge` (re-export) | — |
| `IStatePort` | `SSMStateAdapter` | `InMemoryStateAdapter` | — |
| `IDispatchPort` | `FabricDispatchAdapter` | `MockDispatchAdapter` | — |
| `IDeltaPort` | `BusFactory.create_local()` (re-export) | `create_test_bus()` (same impl) | — |
| `IMemoryPort` | `RecallMemoryAdapter` | `MockMemoryAdapter` | — |
| `ISessionStateReader` (Fabric) | — | — | `NullSessionStateReaderAdapter` |
| `IDeltaBusPort` (Fabric) | — | — | `NullDeltaBusAdapter` |
| `IEventSubscriptionPort` (Orch) | — | — | `NullEventSubscriptionAdapter` |
| `IBridgeWritePort` (Orch) | — | — | `NullBridgeWriteAdapter` |
| `IStateReadPort` (Planner) | — | — | `SnapshotStateReadAdapter` |

---

## 8. Protocol / ABC / Decorator Usage Summary

| Decorator/Pattern | Location | Target |
|-------------------|----------|--------|
| `@runtime_checkable` | `ports.py` | `IInputPort`, `IOutputPort`, `IStatePort`, `IDispatchPort`, `IMemoryPort` |
| `Protocol` (typing) | `ports.py` | All 5 new ports above |
| `@abstractmethod` | None in this batch | — |
| `ABC` | None in this batch | — |
| `TypedDict` | None in this batch | — |
| `NamedTuple` | None in this batch | — |
| `dataclass` | None in this batch | — |
| `Enum` | None in this batch | — |

---

## 9. Constants & Configuration Values

| Constant/Config | Location | Value |
|----------------|----------|-------|
| `TOPIC_USER_INPUT` | imported in `bus_input.py` from `k1.concierge.bus.topics` | (defined elsewhere) |
| `actors.back.max_iterations.LOW` | `defaults.yaml` | `10` |
| `actors.back.max_iterations.MEDIUM` | `defaults.yaml` | `14` |
| `actors.back.max_iterations.HIGH` | `defaults.yaml` | `24` |
| `actors.back.budget_floor` | `defaults.yaml` | `4` |
| `actors.back.history_window` | `defaults.yaml` | `5` |
| `actors.back.default_safety_band` | `defaults.yaml` | `"AMBER"` |

---

## 10. Architectural Notes

1. **Structural subtyping throughout:** All adapters satisfy their ports via duck typing (structural subtyping). No adapter explicitly inherits from a Protocol class. The `@runtime_checkable` decorator enables `isinstance()` checks at runtime.

2. **Two-tier bootstrap pattern (SIM-D-39):** Null adapters exist for shared components (Fabric, Orchestrator, Planner) that are constructed at startup before per-session state is available. These null adapters drop operations silently or return empty defaults.

3. **Re-export strategy:** 4 of 8 ports are pure aliases of existing Protocols. 4 production adapters (`hub_llm`, `ultrabert_classification`, `local_delta`, `test_classification`, `test_llm`, `test_delta`) are pure re-exports from canonical locations.

4. **Config delegation:** Config is entirely delegated to `poc.k1_poc.config` — the k1.concierge.config package is a thin re-export shim.

5. **No new data types:** `k1.concierge.types/` invents nothing — it is purely a re-export convenience hub for types from bus, fabric, model_hub, orchestrator, and fsm.

6. **Write path excluded from IStatePort:** Writes go through `ctx.writer_port` (MutationRequest-based), which is a separate concern from the read-only `IStatePort`.
