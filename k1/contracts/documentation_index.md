# Contracts Directory - Complete Documentation Index

**Last Updated:** 2025-10-13
**Total Contract Categories:** 22 (including Contract Testing)
**Total README Files:** 36 (main + 35 subdirectory READMEs)
**ADR Coverage:** 0001-0050 (206 total ADRs including sub-ADRs)

## 📋 Quick Navigation

### By Architectural Layer

#### **Layer 1: Core Kernel (6 categories)**
| Category | Path | Key Contracts | ADR Source |
|----------|------|---------------|------------|
| Protocols | `protocols/` | 6 MPST protocols | ADR-0003, 0003a-d |
| Actor Model | `actor_model/` | Mailbox, Supervisor, Router | ADR-0002, 0002a-d |
| Agent Lifecycle | `agent_lifecycle/` | 6-state FSM, Hiring | ADR-0004, 0004a-d |
| Orchestration | `orchestration/` | 3-phase protocol | ADR-0005, 0005a-c |
| Planning | `planning/` | 4-stage pipeline | ADR-0006, 0006a-c |
| Security | `security/` | Capabilities, Privacy | ADR-0007, 0007a-f |

#### **Layer 2: State & Persistence (2 categories)**
| Category | Path | Key Contracts | ADR Source |
|----------|------|---------------|------------|
| SessionState | `sessionstate/` | 6-section structure | ADR-0008, 0008a-e |
| Storage | `storage/` | Multi-store (FTS/Vector/KG) | ADR-0009, 0009a-e |

#### **Layer 3: Execution & Tools (1 category)**
| Category | Path | Key Contracts | ADR Source |
|----------|------|---------------|------------|
| Tools | `tools/` | Tool schemas, MCP | ADR-0010, 0010a-f |

#### **Layer 4: Ingress & Voice (3 categories)**
| Category | Path | Key Contracts | ADR Source |
|----------|------|---------------|------------|
| API (REST) | `api/rest/` | HTTP endpoints | ADR-0044, 0001e |
| API (WebSocket) | `api/websocket/` | Bidirectional streaming | ADR-0044, 0001e |
| API (SSE) | `api/sse/` | Server-Sent Events | ADR-0044, 0001e |

#### **Layer 5: Infrastructure (3 categories)**
| Category | Path | Key Contracts | ADR Source |
|----------|------|---------------|------------|
| Performance | `performance/` | Budgets, KV Cache | ADR-0012, 0012a-d |
| Observability | `observability/` | Logs, Metrics, Traces | ADR-0013, 0013a-d |
| Error Recovery | `error_recovery/` | Circuit Breaker, Saga | ADR-0014, 0014a-e |

### Cross-Layer Components

#### **K0 Bridge (3 READMEs)**
| Component | Path | Coverage | ADR Source |
|-----------|------|----------|------------|
| K0 Bridge Overview | `k0_bridge/README.md` | Protocol, batching, errors | ADR-0001a, 0001f |
| All 20 Ports | `k0_bridge/ports/README.md` | P01-P20 specifications | ADR-0001a |
| Batching Strategies | `k0_bridge/batching/README.md` | Adaptive batching | ADR-0001a |

#### **FlatBuffers Schemas (6 READMEs)**
| Component | Path | Schema Count | ADR Source |
|-----------|------|--------------|------------|
| FlatBuffers Overview | `flatbuffers/README.md` | 76 total schemas | ADR-0001b, 0001c |
| Layer 1 Kernel | `flatbuffers/layer1_kernel/README.md` | 18 schemas | ADR-0001b |
| Layer 2 State | `flatbuffers/layer2_state/README.md` | 16 schemas | ADR-0001b |
| Layer 3 Execution | `flatbuffers/layer3_execution/README.md` | 14 schemas | ADR-0001b |
| Layer 4 Ingress | `flatbuffers/layer4_ingress/README.md` | 14 schemas | ADR-0001b |
| Layer 5 Infrastructure | `flatbuffers/layer5_infrastructure/README.md` | 14 schemas | ADR-0001b |

#### **External APIs (4 READMEs)**
| Component | Path | Coverage | ADR Source |
|-----------|------|----------|------------|
| API Overview | `api/README.md` | All API types | ADR-0044, 0001e |
| REST API | `api/rest/README.md` | HTTP endpoints | ADR-0044 |
| WebSocket API | `api/websocket/README.md` | Bidirectional | ADR-0044 |
| SSE API | `api/sse/README.md` | Server-push | ADR-0044 |

#### **Additional Categories (7 READMEs)**
| Category | Path | Coverage | ADR Source |
|----------|------|----------|------------|
| K0 SSE | `k0_sse/` | K0 event streaming | ADR-0041 |
| Bridge Integration | `bridge_integration/` | HTTP/2, SSE bridge | ADR-0042 |
| API Specs | `api_specs/` | OpenAPI 3.1 | ADR-0044 |
| Event Bus | `event_bus/` | Internal pub/sub | ADR-0045 |
| Router Policies | `router_policies/` | Fast/Smart lanes | ADR-0046 |
| Coherence | `coherence/` | SessionState consistency | ADR-0047 |
| **Contract Testing** | `testing/` | Consumer-driven contracts (Pact-style) | **ADR-0013d** |

## 📊 Documentation Statistics

```yaml
documentation_coverage:
  total_readmes: 36  # Updated to include contract testing
    - main_index: 1 (contracts/README.md)
    - subdirectory_readmes: 35  # Updated from 31

  total_lines: ~12000+  # Updated from ~9000+
    - average_per_readme: 320 lines
    - largest: testing/README.md (550 lines)
    - smallest: event_bus/README.md (200 lines)

  contract_categories: 22  # Updated from 21
  adr_coverage: 206 ADRs (0001-0050 + sub-ADRs)
  flatbuffers_schemas: 76 schemas
  k0_bridge_ports: 20 ports
  mpst_protocols: 6 protocols
  consumer_contracts: 228-380 (76 schemas × 3-5 versions)

documentation_structure:
  sections_per_readme:
    - Overview
    - Contracts Included
    - Key Specifications
    - Performance Requirements
    - Observability (metrics, tracing, logging)
    - Testing Strategies
    - Related Contracts
    - Source ADRs
```

## 🔍 Finding Contracts by Use Case

### Use Case: "I need to add a new agent type"
**Relevant Contracts:**
1. `agent_lifecycle/` - 6-state FSM, hiring, warm-up
2. `actor_model/` - Actor patterns, mailbox, supervisor
3. `orchestration/` - How agent participates in 3-phase protocol
4. `protocols/` - Agent Hire protocol (P1)
5. `flatbuffers/layer1_kernel/` - AgentState schema

### Use Case: "I need to implement a new tool"
**Relevant Contracts:**
1. `tools/` - Tool system, MCP integration
2. `protocols/` - Tool Call protocol (P5)
3. `security/` - Capability checking for tools
4. `flatbuffers/layer3_execution/` - ToolInvocation schema
5. `error_recovery/` - Retry policies, circuit breaker

### Use Case: "I need to add memory storage"
**Relevant Contracts:**
1. `storage/` - Multi-store architecture
2. `k0_bridge/ports/` - P01-P10 memory operations
3. `sessionstate/` - SessionState structure
4. `flatbuffers/layer2_state/` - Memory schemas
5. `performance/` - Memory budgets

### Use Case: "I need to expose a new API endpoint"
**Relevant Contracts:**
1. `api/rest/` - REST API patterns
2. `api/websocket/` - WebSocket if real-time
3. `api/sse/` - SSE if server-push
4. `api_specs/` - OpenAPI 3.1 specification
5. `security/` - Authentication, authorization
6. `observability/` - API metrics

### Use Case: "I need to optimize performance"
**Relevant Contracts:**
1. `performance/` - Performance budgets, KV cache
2. `k0_bridge/batching/` - Batching strategies
3. `flatbuffers/` - Zero-copy serialization
4. `orchestration/` - Parallelism in 3-phase
5. `observability/` - Performance metrics

### Use Case: "I need to handle errors gracefully"
**Relevant Contracts:**
1. `error_recovery/` - Circuit breaker, retry, saga
2. `protocols/` - Saga Rollback protocol (P6)
3. `observability/` - Error metrics, alerts
4. `k0_bridge/` - K0 bridge error handling
5. `api/` - RFC 7807 error format

## 📐 Architectural Patterns Referenced

### By Category
| Pattern | Contracts | Research Source |
|---------|-----------|-----------------|
| Actor Model | `actor_model/`, `agent_lifecycle/` | Hewitt 1973 |
| MPST | `protocols/`, `protocol_monitor/` | Honda et al. 2008 |
| Capabilities | `security/` | Dennis & Van Horn 1966 |
| SEDA | `orchestration/`, `performance/` | Welsh et al. 2001 |
| Saga Pattern | `error_recovery/`, `protocols/` | Garcia-Molina 1987 |
| Contract Net | `orchestration/` | Smith 1980 |
| Circuit Breaker | `error_recovery/`, `k0_bridge/` | Nygard 2007 |
| Zero-Copy | `flatbuffers/` | Google FlatBuffers |

## 🎯 Performance Budget Summary

```yaml
critical_path_latencies:
  ttft: 150ms # Time to First Token
  e2e_turn: 2000ms # End-to-end turn
  k0_recall_query: 200ms # P01 port
  agent_transition: 5ms # Lifecycle FSM
  orchestration_3phase: 250ms # Total coordination

memory_budgets:
  sessionstate_size: 64KB soft limit
  kv_cache_total: 128MB
  k1_memory_total: 500MB
  flatbuffers_message: 64KB max

throughput_targets:
  api_requests: 1000 req/s
  k0_bridge_requests: 10000 req/s
  agent_messages: 50000 msg/s
```

## 🔗 Cross-References Map

### High-Connectivity Contracts (Referenced by 5+ other contracts)
1. **`protocols/`** - Referenced by: actor_model, agent_lifecycle, orchestration, planning, tools, error_recovery
2. **`flatbuffers/`** - Referenced by: All layer contracts, k0_bridge, api
3. **`k0_bridge/`** - Referenced by: sessionstate, storage, performance, api
4. **`sessionstate/`** - Referenced by: storage, k0_bridge, coherence, api
5. **`security/`** - Referenced by: agent_lifecycle, tools, api, k0_bridge

### Dependency Chains (Critical Paths)
```
User Request (API) →
  api/rest/ →
    orchestration/ →
      agent_lifecycle/ →
        actor_model/ →
          protocols/ →
            tools/ →
              k0_bridge/ →
                storage/ →
                  sessionstate/
```

## ✅ Documentation Completeness Checklist

- [x] Main contracts README with 21 categories
- [x] All 21 category directories created
- [x] All 21 category READMEs created
- [x] FlatBuffers overview + 5 layer READMEs
- [x] K0 Bridge overview + ports + batching READMEs
- [x] API overview + REST + WebSocket + SSE READMEs
- [x] All READMEs include:
  - [x] Overview
  - [x] Contracts Included
  - [x] Key Specifications
  - [x] Performance Requirements
  - [x] Observability (metrics, tracing, logging)
  - [x] Testing Strategies
  - [x] Related Contracts
  - [x] Source ADRs

## 🚀 Next Steps: Implementation Phase

### Phase 1: Foundational Schemas (Week 1-2)
- [ ] Create 76 FlatBuffers .fbs files
- [ ] Generate Python bindings
- [ ] Validate serialization performance (<1ms)
- [ ] Create schema evolution tests

### Phase 2: Core Protocols (Week 3-4)
- [ ] Implement 6 MPST protocol definitions (Scribble-like PDL)
- [ ] Create protocol validation tests
- [ ] Integrate with protocol monitor
- [ ] Validate timeout enforcement

### Phase 3: K0 Bridge Contracts (Week 5-6)
- [ ] Create YAML contracts for all 20 ports
- [ ] Implement batching configuration
- [ ] Create circuit breaker configuration
- [ ] Validate latency budgets

### Phase 4: API Specifications (Week 7-8)
- [ ] Create OpenAPI 3.1 master_spec.yaml
- [ ] Generate endpoint-specific YAML files
- [ ] Validate with OpenAPI validator
- [ ] Generate API documentation

### Phase 5: Configuration Files (Week 9-10)
- [ ] Create YAML configs for all contracts
- [ ] Validate against JSON Schema
- [ ] Create config hot-reload tests
- [ ] Document config evolution

## 📞 Support & Contribution

### When Adding New Contracts
1. **Check ADR First:** Ensure architectural decision exists
2. **Update README:** Add to main contracts/README.md
3. **Create Category README:** Follow standard template
4. **Cross-Reference:** Link related contracts
5. **Document Performance:** Include latency/memory budgets
6. **Add Observability:** Metrics, traces, logs

### Documentation Standards
- **Consistency:** Follow existing README structure
- **Completeness:** Include all required sections
- **Examples:** Provide YAML/JSON examples
- **Cross-Links:** Reference related contracts
- **ADR Sources:** Always cite source ADRs

---

**Repository:** K1 Intelligence Module - Agentic Orchestrator Kernel
**Documentation Version:** 1.0
**Coverage:** 100% of ADR-0001-0050 (206 total ADRs)
