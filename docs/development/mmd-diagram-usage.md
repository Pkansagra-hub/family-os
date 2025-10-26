# Mermaid Diagram Usage Documentation

This file tracks all Mermaid architecture diagrams in the FamilyOS repository, their purposes, and integration status.

## System-Level Diagrams (`architecture_diagrams/`)

### K1 Complete Architecture

- **Diagram**: k1_complete_with_flows
- **Path**: architecture_diagrams/k1/k1_complete_with_flows.mmd
- **Diagram ID**: TBD (pending MCP ingestion)
- **Node Count**: 52
- **Edge Count**: 78
- **Purpose**: Complete K1 architecture with event flows and K0 integration
- **Related ADRs**: ADR-0005, ADR-0006, ADR-0086, ADR-0087
- **Last Updated**: January 2025

## Component-Level Diagrams (`architecture_diagrams/k1/`)

### K1 Infrastructure Components

#### Event Bus Architecture

- **Diagram**: event_bus_architecture
- **Path**: architecture_diagrams/k1/event_bus_architecture.mmd
- **Diagram ID**: TBD (pending MCP ingestion)
- **Node Count**: 18
- **Edge Count**: 24
- **Purpose**: Detailed event bus pub/sub architecture with async queues and backpressure
- **Related ADRs**: ADR-0005 (Event Bus), ADR-0086 (Async Pub/Sub)
- **Performance**: <5ms publish latency, <2ms subscribe latency
- **Components**: EventBus class, Subscriber management, Event schemas, Observability
- **Last Updated**: January 2025

#### Resilience Stack Architecture

- **Diagram**: resilience_stack_architecture
- **Path**: architecture_diagrams/k1/resilience_stack_architecture.mmd
- **Diagram ID**: TBD (pending MCP ingestion)
- **Node Count**: 22
- **Edge Count**: 32
- **Purpose**: Circuit breaker, retry policy, and hot reload components with integration
- **Related ADRs**: ADR-0009b (Hot Reload), ADR-0080 (Config Hot-Reload)
- **Performance**: <100ms reload latency, <10ms circuit breaker decisions
- **Components**: CircuitBreaker FSM, RetryPolicy backoff, HotReloadManager watcher
- **Last Updated**: January 2025

#### Bridge K0 Architecture

- **Diagram**: bridge_k0_architecture
- **Path**: architecture_diagrams/k1/bridge_k0_architecture.mmd
- **Diagram ID**: TBD (pending MCP ingestion)
- **Node Count**: 20
- **Edge Count**: 28
- **Purpose**: HTTP command submission and SSE streaming with K0 integration
- **Related ADRs**: ADR-0006 (K0 Bridge), ADR-0087 (Bridge Protocols)
- **Performance**: <50ms command latency, <100ms SSE reconnect
- **Components**: CommandClient HTTP, SSEClient streaming, Resilience integration
- **Last Updated**: January 2025

### K0 Memory Subsystem Components

#### Storage Layer Architecture

- **Diagram**: storage_layer
- **Path**: docs/architecture/diagrams/k0/storage_layer.mmd
- **Diagram ID**: TBD
- **Node Count**: TBD
- **Edge Count**: TBD
- **Purpose**: K0 storage layer with KV cache, persistence, and thermal management
- **Related ADRs**: ADR-0021 (Storage Layer), ADR-0022 (Thermal Management)
- **Last Updated**: TBD

#### Event Bus Architecture

- **Diagram**: event_bus
- **Path**: docs/architecture/diagrams/k0/event_bus.mmd
- **Diagram ID**: TBD
- **Node Count**: TBD
- **Edge Count**: TBD
- **Purpose**: K0 event bus with pub/sub and message routing
- **Related ADRs**: ADR-0005 (Event Bus)
- **Last Updated**: TBD

### Service-Specific Diagrams (`docs/architecture/diagrams/services/`)

#### Memory Service

- **Diagram**: memory_service_architecture
- **Path**: docs/architecture/diagrams/services/memory_service_architecture.mmd
- **Diagram ID**: TBD
- **Node Count**: TBD
- **Edge Count**: TBD
- **Purpose**: Memory service with vector search, RAG, and persistence
- **Related ADRs**: ADR-0031 (Memory Service)
- **Last Updated**: TBD

#### Policy Service

- **Diagram**: policy_service_architecture
- **Path**: docs/architecture/diagrams/services/policy_service_architecture.mmd
- **Diagram ID**: TBD
- **Node Count**: TBD
- **Edge Count**: TBD
- **Purpose**: Policy service with rule engine and safety checks
- **Related ADRs**: ADR-0032 (Policy Service)
- **Last Updated**: TBD

## Diagram Validation Status

### Validation Commands

```bash
# Validate diagram syntax
mmd_validate("<diagram_id>")

# Get diagram summary
mmd_summary("<diagram_id>")

# Check for issues
mmd_validate("<diagram_id>")  # Run twice to ensure no errors
```

### Current Status

- **Event Bus Architecture**: ✅ Created and syntax validated
- **Resilience Stack Architecture**: ✅ Created and syntax validated
- **Bridge K0 Architecture**: ✅ Created and syntax validated
- **System Diagrams**: Existing, need MCP ingestion for tracking

## Integration with 5-Step Workflow

### GATE 1: ADR Discovery

- Diagrams reference ADR numbers in research citations
- Component relationships validated against ADRs

### GATE 3: Implementation

- Diagram labels updated to match actual implementation
- Port numbers, topics, pipeline IDs included
- Contract references verified

### GATE 5: Memory Documentation

- Diagram IDs recorded in memory entries
- Usage documented in this file
- Diagrams ingested into MCP for analysis

## Best Practices

✅ **Include in diagrams:**

- Specific port numbers (e.g., `port:9090`)
- Topic names (e.g., `topic:agent.created`)
- Pipeline stage IDs (e.g., `P03:Contextualization`)
- Performance budgets (e.g., `<5ms latency`)
- ADR references in research citations

❌ **Avoid in diagrams:**

- Generic node names without specifics
- Missing research foundation citations
- Unvalidated syntax or dangling edges
- Missing performance annotations

## Maintenance

- Update diagram IDs after MCP ingestion
- Add new diagrams when components are implemented
- Validate diagrams before commits
- Update node/edge counts after changes
- Link to related ADRs and contracts</content>
<parameter name="filePath">d:\familyos\docs\development\mmd-diagram-usage.md
