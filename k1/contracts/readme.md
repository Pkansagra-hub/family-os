# K1 Intelligence Module - Contracts Directory

**Purpose:** This directory contains all formal contracts defined in ADRs (Architecture Decision Records) and sub-ADRs. Contracts define interfaces, protocols, schemas, and behavioral agreements between K1 components.

---

## 📋 Contract Categories

### 1. **Core Protocol Contracts** (`protocols/`)
- **Source:** ADR-0003, ADR-0003a-d
- Multiparty Session Type (MPST) protocol definitions
- 6 core protocols: Agent Hire, Task Execution, Clarification, Barge-In, Tool Call, Saga Rollback
- Protocol Definition Language (PDL) specifications in YAML

### 2. **FlatBuffers Schemas** (`flatbuffers/`)
- **Source:** ADR-0011, ADR-0012, ADR-0012a-e
- 76 FlatBuffers schemas across all 5 layers
- Zero-copy serialization contracts for all K1 components
- Schema versioning and evolution contracts

### 3. **K0-K1 Bridge Contracts** (`k0_bridge/`)
- **Source:** ADR-0001a, ADR-0044, ADR-0044a-d
- K1↔K0 communication protocol specifications
- 20 port definitions (P01-P20)
- Dual protocol support: JSON (primary) + FlatBuffers (optimization)
- Batching, compression, and backpressure contracts

### 4. **Actor Model Contracts** (`actor_model/`)
- **Source:** ADR-0002, ADR-0002a-d
- Mailbox message envelope specifications
- Supervisor health check protocols
- Router admission control contracts
- Observability schema for actor messaging

### 5. **Agent Lifecycle Contracts** (`agent_lifecycle/`)
- **Source:** ADR-0005, ADR-0005a-e
- 6-state FSM transitions (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
- Agent personality and capability contracts
- Supervisor monitoring and blacklist contracts
- Agent hiring score calculation contracts

### 6. **Orchestration Contracts** (`orchestration/`)
- **Source:** ADR-0006, ADR-0006a-e
- 3-phase orchestration (Negotiation → Selection → Execution)
- Contract Net Protocol message formats
- Multi-criteria scoring contracts
- DAG execution and saga integration contracts

### 7. **Planning Pipeline Contracts** (`planning/`)
- **Source:** ADR-0007, ADR-0007a-d
- 4-stage planning pipeline (Sketch → Expand → Validate → Commit)
- LLM prompt templates and tool registry contracts
- Plan validation rules and arbiter contracts
- K0 WAL integration contracts

### 8. **Security & Capability Contracts** (`security/`)
- **Source:** ADR-0010, ADR-0010a-d, ADR-0032-0038
- Capability token specifications
- Band-based egress rules (GREEN/AMBER/RED)
- PII detection and redaction contracts
- E2EE and JWT authentication contracts
- Audit trail and receipt contracts

### 9. **Tool Execution Contracts** (`tools/`)
- **Source:** ADR-0033, ADR-0034, ADR-0034a-d
- MCP (Model Context Protocol) specifications
- Tool sandboxing contracts (MCP, WASM, Process)
- Circuit breaker integration for tools
- Tool call/result schemas

### 10. **SessionState Contracts** (`sessionstate/`)
- **Source:** ADR-0017, ADR-0017a-f, ADR-0019, ADR-0050
- 6-section SessionState structure
- Delta serialization contracts
- 3-tier eviction strategy contracts
- Coherence guarantees (Read-Your-Writes, Monotonic Reads/Writes)

### 11. **Storage Contracts** (`storage/`)
- **Source:** ADR-0020, ADR-0021, ADR-0022, ADR-0023
- Multi-tier storage (Hot/Warm/Cold)
- Turn history retention policies
- K0 bridge batching contracts
- Cursor-based pagination contracts

### 12. **Performance & Resource Contracts** (`performance/`)
- **Source:** ADR-0024-0031
- Performance budgets (P95 targets)
- KV cache management contracts
- Thermal management and placement contracts
- WFQ scheduler contracts
- Cost tracking and budget enforcement contracts

### 13. **API Contracts** (`api/`)
- **Source:** ADR-0014, ADR-0015, ADR-0016, ADR-0040, ADR-0041
- REST API contracts (JSON + FlatBuffers)
- WebSocket protocol contracts
- SSE (Server-Sent Events) schemas
- OpenAPI 3.1 specifications

### 14. **Observability Contracts** (`observability/`)
- **Source:** ADR-0029, ADR-0030
- Prometheus metrics (RED Method)
- Trace sampling strategy contracts
- Alerting rules and dashboard contracts

### 15. **Error Recovery Contracts** (`error_recovery/`)
- **Source:** ADR-0008, ADR-0008a-d, ADR-0009, ADR-0009a-c
- Saga pattern compensating transaction contracts
- Circuit breaker FSM contracts
- Timeout and deadlock handling contracts

### 16. **K0 SSE Event Streaming Contracts** (`k0_sse/`)
- **Source:** ADR-0042, ADR-0042a-e, ADR-0043, ADR-0043a-d
- K0 SSE event production and consumption contracts
- SSE reconnection and replay contracts
- Topic-based routing and subscription contracts
- Device storage tier contracts for SSE persistence

### 17. **Bridge Integration Contracts** (`bridge_integration/`)
- **Source:** ADR-0044, ADR-0044a-d, ADR-0045, ADR-0045a-d, ADR-0046
- HTTP/2 multiplexing contracts for K0 Bridge
- FlatBuffers serialization strategy contracts
- Agent-agent SSE coordination contracts
- K1 internal event bus pub/sub contracts
- SSE-WebSocket bridge contracts

### 18. **API Specification Contracts** (`api_specs/`)
- **Source:** ADR-0047
- OpenAPI 3.1 REST specifications
- Auto-generated API documentation contracts
- Endpoint versioning and deprecation contracts

### 19. **Internal Event Bus Contracts** (`event_bus/`)
- **Source:** ADR-0048
- K1 internal event bus message contracts
- Event routing and filtering contracts
- Event delivery guarantees

### 20. **Router Policy Contracts** (`router_policies/`)
- **Source:** ADR-0049
- Fast/Smart lane router policy contracts
- Lane selection scoring algorithms
- Performance optimization contracts

### 21. **Coherence Contracts** (`coherence/`)
- **Source:** ADR-0050
- SessionState coherence guarantee contracts
- Read-Your-Writes consistency contracts
- Monotonic Reads/Writes contracts
- Bounded staleness contracts

### 22. **Contract Testing Infrastructure** (`testing/`)
- **Source:** ADR-0013d
- Consumer-driven contract testing (Pact-style)
- Forward/backward compatibility validation
- Multi-version compatibility matrix (228-380 tests)
- CI/CD integration for schema validation
- Breaking change detection before production

---

## 🔗 Contract Dependency Map

```
Core Protocol Contracts (ADR-0003)
    ├── Actor Model Contracts (ADR-0002) ← Message envelope
    ├── FlatBuffers Schemas (ADR-0011) ← Message serialization
    └── Agent Lifecycle Contracts (ADR-0005) ← State transitions

K0-K1 Bridge Contracts (ADR-0001a)
    ├── FlatBuffers Schemas (ADR-0012) ← Port message schemas
    ├── SessionState Contracts (ADR-0017) ← StateDelta serialization
    └── Storage Contracts (ADR-0022) ← Batching strategy

Orchestration Contracts (ADR-0006)
    ├── Core Protocol Contracts (ADR-0003) ← Agent Hire protocol
    ├── Planning Pipeline Contracts (ADR-0007) ← Task execution
    └── Error Recovery Contracts (ADR-0008) ← Saga integration

Security Contracts (ADR-0010)
    ├── Actor Model Contracts (ADR-0002) ← Capability verification
    └── Tool Execution Contracts (ADR-0033) ← Sandbox permissions

API Contracts (ADR-0014-0016)
    ├── FlatBuffers Schemas (ADR-0011) ← Binary serialization
    └── SessionState Contracts (ADR-0017) ← State synchronization
```

---

## 📖 How to Use This Directory

### For Developers

1. **Find relevant contract:** Navigate to category folder (e.g., `protocols/`)
2. **Read contract specification:** Review YAML/JSON/FlatBuffers schema
3. **Check ADR reference:** Each contract links back to source ADR
4. **Validate implementation:** Use contract tests to verify compliance

### For Architects

1. **Review contract dependencies:** Check dependency map above
2. **Verify schema evolution:** Check versioning in FlatBuffers contracts
3. **Validate protocol compliance:** Review MPST protocol definitions
4. **Document new contracts:** Add new contracts with ADR references

### For QA/Testing

1. **Contract testing:** Use schemas for Pact/contract tests
2. **Protocol validation:** Test against PDL specifications
3. **Performance validation:** Verify against performance contracts
4. **Security testing:** Validate against capability and band contracts

---

## ✅ Contract Validation

All contracts in this directory must:

- **Reference source ADR:** Link to ADR document
- **Include schema version:** Semantic versioning (v1.0.0)
- **Provide examples:** Include usage examples
- **Document dependencies:** List contract dependencies
- **Specify validation rules:** Define compliance checks

---

## 🔄 Contract Evolution

Contracts follow **semantic versioning** (ADR-0013):

- **MAJOR:** Breaking changes (remove fields, change types)
- **MINOR:** Backward-compatible additions (new optional fields)
- **PATCH:** Documentation or clarification updates

**Deprecation policy:** 90-day notice before breaking changes (ADR-0013c)

---

## 📁 Directory Structure

```
contracts/
├── README.md                    # This file
├── protocols/                   # Core protocol contracts (ADR-0003)
│   ├── agent_hire.pdl.yml
│   ├── task_execution.pdl.yml
│   ├── clarification.pdl.yml
│   ├── barge_in.pdl.yml
│   ├── tool_call.pdl.yml
│   └── saga_rollback.pdl.yml
├── flatbuffers/                 # FlatBuffers schemas (ADR-0011, ADR-0012)
│   ├── layer1_kernel/           # 15 schemas
│   ├── layer2_state/            # 18 schemas
│   ├── layer3_execution/        # 16 schemas
│   ├── layer4_ingress/          # 14 schemas
│   └── layer5_infrastructure/   # 13 schemas
├── k0_bridge/                   # K0-K1 communication (ADR-0001a, ADR-0044)
│   ├── ports/                   # P01-P20 port specifications
│   ├── batching/                # Batching strategy contracts
│   └── examples/                # Usage examples
├── actor_model/                 # Actor messaging (ADR-0002)
│   ├── message_envelope.yaml
│   ├── mailbox_contract.yaml
│   ├── supervisor_protocol.yaml
│   └── router_admission.yaml
├── agent_lifecycle/             # Agent lifecycle (ADR-0005)
│   ├── fsm_transitions.yaml
│   ├── hiring_score.yaml
│   ├── warming_contract.yaml
│   └── draining_contract.yaml
├── orchestration/               # Orchestration (ADR-0006)
│   ├── contract_net_protocol.yaml
│   ├── scoring_criteria.yaml
│   └── dag_execution.yaml
├── planning/                    # Planning pipeline (ADR-0007)
│   ├── sketch_stage.yaml
│   ├── expand_stage.yaml
│   ├── validation_stage.yaml
│   └── commit_stage.yaml
├── security/                    # Security & capabilities (ADR-0010, ADR-0032-0038)
│   ├── capability_token.yaml
│   ├── privacy_bands.yaml
│   ├── pii_detection.yaml
│   └── e2ee_contract.yaml
├── tools/                       # Tool execution (ADR-0033, ADR-0034)
│   ├── mcp_protocol.json
│   ├── sandbox_matrix.yaml
│   └── tool_schemas/
├── sessionstate/                # SessionState (ADR-0017, ADR-0019)
│   ├── 6_section_structure.yaml
│   ├── delta_serialization.yaml
│   └── eviction_strategy.yaml
├── storage/                     # Storage (ADR-0020-0023)
│   ├── multi_tier_storage.yaml
│   ├── retention_policies.yaml
│   └── pagination_contract.yaml
├── performance/                 # Performance (ADR-0024-0031)
│   ├── performance_budgets.yaml
│   ├── kv_cache_management.yaml
│   ├── thermal_management.yaml
│   └── cost_tracking.yaml
├── api/                         # API contracts (ADR-0014-0016, ADR-0040-0041)
│   ├── rest/
│   ├── websocket/
│   └── sse/
├── observability/               # Observability (ADR-0029-0030)
│   ├── prometheus_metrics.yaml
│   ├── trace_sampling.yaml
│   └── alerting_rules.yaml
├── error_recovery/              # Error recovery (ADR-0008-0009)
│   ├── saga_compensation.yaml
│   └── circuit_breaker.yaml
├── k0_sse/                      # K0 SSE streaming (ADR-0042-0043)
│   ├── event_production.yaml
│   ├── event_consumption.yaml
│   ├── topic_hierarchy.yaml
│   └── device_storage.yaml
├── bridge_integration/          # Bridge integration (ADR-0044-0046)
│   ├── http2_multiplexing.yaml
│   ├── agent_sse_coordination.yaml
│   └── sse_websocket_bridge.yaml
├── api_specs/                   # API specifications (ADR-0047)
│   ├── openapi_3_1_specs/
│   └── endpoint_versioning.yaml
├── event_bus/                   # Internal event bus (ADR-0048)
│   ├── event_schemas.yaml
│   └── delivery_guarantees.yaml
├── router_policies/             # Router policies (ADR-0049)
│   ├── fast_smart_lane.yaml
│   └── lane_scoring.yaml
└── coherence/                   # Coherence contracts (ADR-0050)
    ├── read_your_writes.yaml
    ├── monotonic_consistency.yaml
    └── bounded_staleness.yaml
```

---

## 🔍 Contract Search Index

### By ADR Number

| ADR | Contract Location | Contract Type |
|-----|-------------------|---------------|
| ADR-0001a | `k0_bridge/` | Bridge protocol |
| ADR-0002 | `actor_model/` | Actor messaging |
| ADR-0003 | `protocols/` | MPST protocols |
| ADR-0005 | `agent_lifecycle/` | Lifecycle FSM |
| ADR-0006 | `orchestration/` | Orchestration |
| ADR-0007 | `planning/` | Planning pipeline |
| ADR-0008 | `error_recovery/saga_compensation.yaml` | Saga pattern |
| ADR-0009 | `error_recovery/circuit_breaker.yaml` | Circuit breaker |
| ADR-0010 | `security/capability_token.yaml` | Capabilities |
| ADR-0011 | `flatbuffers/` | Serialization |
| ADR-0014-0016 | `api/` | REST/WS/SSE |
| ADR-0017 | `sessionstate/` | SessionState |
| ADR-0020-0023 | `storage/` | Storage tiers |
| ADR-0024-0031 | `performance/` | Performance |
| ADR-0032-0038 | `security/` | Security |
| ADR-0033-0034 | `tools/` | Tool execution |
| ADR-0040-0041 | `api/` | API endpoints |
| ADR-0042-0043 | `k0_sse/` | K0 SSE streaming |
| ADR-0044-0046 | `bridge_integration/` | Bridge integration |
| ADR-0047 | `api_specs/` | OpenAPI specs |
| ADR-0048 | `event_bus/` | K1 event bus |
| ADR-0049 | `router_policies/` | Router policies |
| ADR-0050 | `coherence/` | Coherence guarantees |

### By Component

| Component | Contract Location |
|-----------|-------------------|
| Orchestrator | `orchestration/`, `protocols/agent_hire.pdl.yml` |
| Planner Agent | `planning/`, `protocols/task_execution.pdl.yml` |
| Model Hub | `flatbuffers/layer3_execution/model_hub_*.fbs` |
| Tool Runner | `tools/`, `protocols/tool_call.pdl.yml` |
| SessionState | `sessionstate/`, `flatbuffers/layer2_state/sessionstate.fbs` |
| K0 Bridge | `k0_bridge/`, `flatbuffers/layer5_infrastructure/bridge_*.fbs` |
| Protocol Monitor | `protocols/`, `actor_model/router_admission.yaml` |
| Supervisor | `agent_lifecycle/`, `actor_model/supervisor_protocol.yaml` |

---

## 📊 Contract Statistics

- **Total Contract Categories:** 22 (including Contract Testing)
- **Core Protocol Contracts:** 6 PDL files (ADR-0003)
- **FlatBuffers Schemas:** 76 schemas across 5 layers (ADR-0012)
- **K0 Bridge Ports:** 20 port specifications (ADR-0001a)
- **Consumer Contracts:** 76 schemas × 3-5 versions = 228-380 contracts (ADR-0013d)
- **API Contracts:** REST, WebSocket, SSE (ADR-0014-0016, 0040-0041)
- **Security Contracts:** 9 security-related contract types (ADR-0010, 0032-0038)
- **Performance Contracts:** 8 performance-related contract types (ADR-0024-0031)
- **Integration Contracts:** K0 SSE, Bridge, Event Bus (ADR-0042-0048)
- **Consistency Contracts:** 4 coherence guarantee types (ADR-0050)
- **Contract Testing:** Pact-style consumer-driven testing (ADR-0013d)

---

## �📚 Additional Resources

- **ADR Master Reference:** `docs/architecture/decisions/ADR_MASTER_REFERENCE.md`
- **Sub-ADR Plan:** `docs/sub_adr_plan.md`
- **Architecture Diagrams:** `architecture_diagrams/`
- **Implementation Guidelines:** `docs/development/contribution-guide.md`

---

## 🤝 Contributing

When adding new contracts:

1. Create contract in appropriate category folder
2. Reference source ADR in contract header
3. Include schema version and changelog
4. Provide usage examples
5. Update this README with new contract entry
6. Run contract validation tests
7. Submit PR with ADR reference

---

**Last Updated:** 2025-10-13
**Maintainer:** K1 Architecture Team
**Status:** Active Development
