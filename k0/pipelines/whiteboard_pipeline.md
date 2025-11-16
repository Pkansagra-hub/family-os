# Pipeline Whiteboard — Cognitive Architecture Reference

**Purpose**: Architectural reference for how cognition flows through the 20-pipeline system
**Status**: Incremental construction from architecture diagrams
**Last Updated**: 2025-11-15

---

## 🧠 Memory-Centric Architecture Principles

This document captures **how cognition works** across the pipeline architecture, extracted from the Family OS architecture diagrams.

### Core Principles (Diagram 1)

1. **Memory as Backbone** — Memory Module serves as central nervous system for all Family AI
2. **Device-Local Storage** — Memory resides on user devices with E2EE family sync
3. **3 API Planes** — Agent (LLM), Tool (Apps), Control (Admin) all serve Memory operations
4. **User-Controlled** — Simple permissions with explicit commands for sensitive operations
5. **Family Intelligence** — Emerges from Memory sync across devices, not separate systems
6. **Sophisticated Servants** — Cognitive, Intelligence, Infrastructure systems serve Memory backbone

---

## 🏗️ Cognitive Orchestration Layer

### Memory Steward Service (Two-Layer Hippocampal Architecture)

**Layer 1: Orchestration Layer (Policy & Workflow)**

- **Memory Steward** (`memory_steward/__init__.py`) — 585 lines of unified orchestrator
  - WriteIntent → WriteDecision pipeline
  - Space resolution + PII redaction
  - Deduplication + UoW commit
  - Receipt generation + event emission

**Integrated Components:**

- **Space Resolver** — Policy-driven space management, family boundary enforcement
- **Redaction Coordinator** — PII detection & protection, privacy-first content filtering
- **Deduplication Engine** — Content similarity detection, intelligent merge strategies
- **Commit Manager** — ACID transaction coordination, UnitOfWork completion
- **Receipt Generator** — Proof-of-storage creation, cryptographic validation

**Layer 2: Hippocampus Layer (Brain-Inspired Processing)**

- **Hippocampus API** (`hippocampus/api.py`) — 383 lines of brain-inspired memory
  - `encode_event()` — DG→CA1→Storage flow
  - `recall_by_cue()` — CA3 pattern completion

**Brain Regions (Hippocampal Architecture):**

- **Dentate Gyrus** (`hippocampus/separator.py`) — Pattern separation & sparse encoding
- **CA3 Region** (`hippocampus/completer.py`) — Content-addressable completion
- **CA1 Bridge** (`hippocampus/bridge.py`) — Semantic projection to Knowledge Graph

### Attention Gate (Thalamus)

**Brain-Inspired Attention Control** (`attention_gate/gate_service.py`)

**4 Decision Modes:**

- **ADMIT** — High salience/confidence, immediate processing
- **DEFER** — Queue for later processing
- **BOOST** — Priority elevation for urgent items
- **DROP** — Resource protection, reject low-value requests

**Derivations:**

- `PROSPECTIVE_SCHEDULE` — Trigger-based reminders (P05)
- `LEARNING_TICK` — Pattern recognition updates (P06)
- `AFFECT_ANALYZE` — Emotional intelligence processing

**Components:**

- **Salience Scoring** (`attention_gate/salience.py`) — Content importance evaluation
- **Backpressure Control** (`attention_gate/backpressure.py`) — Queue depth & throttling
- **Intent Classification** (`attention_gate/intent_rules.py`) — Processing intent derivation

### Context Bundle Builder (Hybrid Recall Assembly)

**Multi-Store Coordination** (`context_bundle/orchestrator.py`)

**Components:**

- **Store Fanout** (`context_bundle/store_fanout.py`) — Parallel store queries
- **Result Fuser** (`context_bundle/result_fuser.py`) — Cross-store result fusion
- **MMR Diversifier** (`context_bundle/mmr_diversifier.py`) — Maximal Marginal Relevance
- **Provenance Tracer** (`context_bundle/provenance_tracer.py`) — Source & confidence tracking
- **Budget Enforcer** (`context_bundle/budget_enforcer.py`) — Performance budget control

### Working Memory Manager (Hierarchical Cache System)

**3-Tier Cache Architecture** (`working_memory/cache.py`)

**Cache Hierarchy:**

- **L1 Cache** — Ultra-fast in-memory (100ms eviction timeout), immediate access patterns
- **L2 Cache** — Session-local (5min eviction timeout), recent access promotion
- **L3 Cache** — Persistent storage (24hr+ retention), long-term working memory

**Management:**

- **Working Memory Manager** (`working_memory/manager.py`)
  - Automatic promotion/demotion
  - UoW integration for persistence
  - Cognitive load-aware eviction
- **Working Memory Store** (`working_memory/store.py`)
  - StoreProtocol compliance
  - Transaction support

**Cognitive Control:**

- **Admission Controller** (`working_memory/admission_controller.py`) — Salience-based admission
- **Load Monitor** (`working_memory/load_monitor.py`) — Cognitive load monitoring

### Cognitive Event Router

**Smart-Path Processing** (`cognitive_events/dispatcher.py`)

**Components:**

- **Topic Routing** — Cognitive event namespace management
- **Consumer Groups** (`cognitive_events/consumer_groups.py`) — Pipeline consumer management
- **Backpressure Handler** (`cognitive_events/backpressure_handler.py`) — Cross-module flow control
- **DLQ Manager** (`cognitive_events/dlq_manager.py`) — Failed cognitive processing recovery

**Shared Infrastructure:**

- **Idempotency Ledger** (`shared/idempotency_ledger.py`)
  - Global operation deduplication
  - Keys: `(actor_id, device_id, envelope_hash)`

---

## 📡 Cognitive Event Topics

### Memory Formation Events (`cognitive.memory.write.*`)

All events carry **`cognitive_trace_id`** for cross-namespace correlation.

- `cognitive.memory.write.initiated` — Memory write request received
- `cognitive.memory.write.space_resolved` — Space/family boundary determined
- `cognitive.memory.write.redacted` — PII detection & redaction complete
- `cognitive.memory.write.committed` — Memory persisted to storage
- `cognitive.memory.write.failed` — Memory write failure

### Context Assembly Events (`cognitive.recall.*`)

- `cognitive.recall.context.requested` — Context bundle request initiated
- `cognitive.recall.stores.queried` — Multi-store fanout complete
- `cognitive.recall.results.fused` — Cross-store result fusion complete
- `cognitive.recall.bundle.assembled` — Context bundle ready for consumption
- `cognitive.recall.bundle.failed` — Context assembly failure

### Decision Making Events (`cognitive.arbitration.*`)

- `cognitive.arbitration.decision.requested` — Decision point reached
- `cognitive.arbitration.habit.evaluated` — Habit system consulted
- `cognitive.arbitration.planner.evaluated` — Planner system consulted
- `cognitive.arbitration.decision.made` — Final decision committed
- `cognitive.arbitration.decision.failed` — Decision pipeline failure

### Learning & Adaptation Events (`cognitive.learning.*`)

- `cognitive.learning.outcome.received` — Learning signal captured
- `cognitive.learning.habit.updated` — Habit system updated
- `cognitive.learning.planner.updated` — Planner system updated
- `cognitive.learning.self_model.updated` — Self-model adapted

### Attention & Working Memory Events (`cognitive.attention.*`, `cognitive.working_memory.*`)

- `cognitive.attention.gate.admit` — Request admitted for processing
- `cognitive.attention.gate.defer` — Request deferred to queue
- `cognitive.attention.gate.boost` — Request priority elevated
- `cognitive.attention.gate.drop` — Request rejected
- `cognitive.working_memory.updated` — Working memory state changed
- `cognitive.working_memory.evicted` — Working memory item evicted

---

## 🚦 Pipeline Cognitive Flows

### P01: Memory Recall/Read

**Cognitive Role**: Memory retrieval operations
**Flow**: `← FROM Memory Backbone`
**Trigger**: Context Bundle Builder → P01 (optional evented read)
**Components**:

- Query Broker (`retrieval/query_broker.py`)
- Query Services (`retrieval/services.py`)
- Storage Read Indices

**Events**:

- Consumes: `cognitive.recall.bundle.assembled`
- Produces: `memory.recall.*` events

---

### P02: Memory Write/Ingest

**Cognitive Role**: Memory storage operations
**Flow**: `→ TO Memory Backbone`
**Trigger**: Memory Steward → Hippocampus API → P02
**Components**:

- P02 Pipeline (`pipelines/p02.py`)
- Hippocampus API (`hippocampus/api.py`)
- Dentate Gyrus → CA3 → CA1 → Storage

**Events**:

- Consumes: `cognitive.memory.write.committed`
- Produces: `memory.formation.*` events
- Correlation: All events share `cognitive_trace_id`

**Integration**:

```
Memory Steward (Orchestration Layer)
  ↓
Hippocampus API (Brain-Inspired Layer)
  ↓
P02 Pipeline (Event-Driven)
  ↓
Storage (Persistence)
```

---

### P03: Memory Consolidation

**Cognitive Role**: Memory strengthening & integration
**Flow**: `→ WITHIN Memory Backbone`
**Trigger**: Experience synthesis, memory strengthening
**Components**:

- Consolidation Engine (`pipelines/memory_p03.py`)

**Events**:

- Consumes: `memory.formation.*`, `cognitive.learning.*`
- Produces: `memory.consolidation.*` events

---

### P04: Memory Action Selection

**Cognitive Role**: Memory-driven decision making
**Flow**: `← FROM Memory Backbone`
**Trigger**: Cognitive Event Router → P04
**Components**:

- Action Runner (`action/runner.py`)
- Unit of Work (`services/uow.py`)
- Outbox Pattern (`events/outbox_drainer.py`)

**Events**:

- Consumes: `cognitive.arbitration.decision.made`
- Produces: `ACTION_DECISION` events

**Flow**:

```
P04 → ACTION_DECISION → Action Runner → UoW
  ↓
Single Transaction:
  - st_receipts (Receipts Store)
  - st_outbox (Outbox Store - Transactional)
  ↓
Outbox Drainer → Event Bus
```

---

### P05: Memory Triggers

**Cognitive Role**: Memory-based event detection
**Flow**: `← FROM Memory Backbone`
**Trigger**: Attention Gate → `PROSPECTIVE_SCHEDULE`
**Components**:

- Prospective Engine
- Trigger Detection

**Events**:

- Consumes: `cognitive.attention.gate.admit` (prospective)
- Produces: `prospective.*` events

---

### P06: Memory Learning

**Cognitive Role**: Memory pattern recognition
**Flow**: `→ TO Memory Backbone`
**Trigger**: Attention Gate → `LEARNING_TICK`
**Components**:

- Learning Engine
- Pattern Recognition
- Self-Model Updates

**Events**:

- Consumes: `cognitive.learning.outcome.received`
- Produces: `cognitive.learning.*` events

---

### P07: Memory Sync/CRDT

**Cognitive Role**: Cross-device Memory synchronization
**Flow**: `↔ Memory Backbone Sync`
**Components**:

- CRDT Merge Engine
- Memory Sync Engine

**Events**:

- Consumes: `memory.sync.*` events
- Produces: `memory.coordination.*` events

---

### P08: Memory Embedding

**Cognitive Role**: Memory vectorization operations
**Flow**: `→ TO Memory Backbone`
**Components**:

- Embedding Lifecycle Manager
- Semantic Memory Encoding

**Events**:

- Consumes: `memory.formation.*` events
- Produces: `memory.embedding.*` events

---

### P09: Memory Ingestion

**Cognitive Role**: Multi-source Memory capture
**Flow**: `→ TO Memory Backbone`
**Components**:

- Connector Ingestion Pipeline
- Sensor-to-Memory Bridge

**Events**:

- Consumes: `integration.*` events
- Produces: `memory.formation.*` events

---

### P10: Memory Privacy/PII

**Cognitive Role**: Memory content protection
**Flow**: `↔ Memory Protection`
**Components**:

- Redaction Coordinator (part of Memory Steward)
- PII Detection Engine
- Policy-Driven Redaction

**Events**:

- Consumes: `cognitive.memory.write.initiated`
- Produces: `cognitive.memory.write.redacted`

**Integration**:

```
Memory Steward → Redaction Coordinator → PII Engine → P10
```

---

### P11-P20: Infrastructure Pipelines

**P11: Memory DSAR/GDPR** — Memory data rights, user memory access control
**P12: Memory Device Security** — Device memory trust levels, encryption keys
**P13: Memory Index Rebuild** — Memory organization updates, structure maintenance
**P14: Memory Deduplication** — Memory experience fusion, cross-perspective synthesis
**P15: Memory Summaries** — Memory narrative generation, experience story creation
**P16: Memory A/B Testing** — Memory feature experiments, operation testing
**P17: Memory QoS/Cost** — Memory operation governance, performance tiers
**P18: Memory Safety** — Memory content protection, age-appropriate access
**P19: Memory Personalization** — Memory-driven preferences, experience-based recommendations
**P20: Memory Procedures** — Memory-driven habit tracking, experience-based routines

---

## 🔄 Cognitive Processing Flows

### Fast Lane (High-Confidence Path)

```
API Gateway → Auth → PEP → QoS → Safety → Ingress
  ↓
Command Bus → Idempotency Ledger → Event Validation
  ↓
Event Bus → Pipeline Bus → P01-P20
```

**Conditions**:

- Valid intent ∧ high-confidence ∧ no blocking obligations
- Direct routing to Event Bus without cognitive orchestration

### Smart Lane (Cognitive Processing Path)

```
API Gateway → Auth → PEP → QoS → Safety → Ingress
  ↓
Command Bus → Intent Router (unset/low-confidence ∨ obligations present)
  ↓
Attention Gate (Thalamus)
  ↓
├─ ADMIT → Memory Steward | Context Builder | Cognitive Event Router
├─ DEFER → Queue for later
├─ BOOST → Priority elevation
└─ DROP → Reject request
  ↓
Cognitive Event Router → Event Bus → Pipeline Bus → P01-P20
```

**Conditions**:

- Unset/low-confidence `agent_intent`
- High-risk operations
- Obligations present (privacy, policy, consent)

---

## 🧠 Memory Backbone Architecture

### Memory Core Components

**Memory Engine** — Central processing unit

- Working memory operations
- Real-time memory access

**Memory Spaces** — 4 memory types

- **Episodic** — Life experiences
- **Semantic** — Knowledge & facts
- **Procedural** — Skills & habits
- **Working** — Active processing

**Memory Index**

- Semantic search
- Relationship mapping
- Relevance scoring

### Device-Local Memory

**Device Storage**

- Local SQLite + Vector DB
- E2EE at rest
- Instant access

**Memory Sync Engine**

- CRDT-based synchronization
- End-to-end encryption
- Family memory sharing

**Memory Cache** (3-tier)

- L1: Active memories
- L2: Recent access
- L3: Warm storage

### Family Memory Network

**Family Memory Graph**

- Relationship mapping
- Shared experiences
- Individual perspectives

**Memory Permissions**

- User-controlled access
- Explicit commands for sensitive data
- Age-appropriate filtering

**Memory Consensus**

- Cross-device validation
- Conflict resolution
- Temporal coherence

---

## 🎯 Policy Framework Integration

### Memory-Driven Family Intelligence

**Family Memory Intelligence** (`policy/family_memory_intelligence.py`)

- Memory-driven family coordination
- Shared experience intelligence
- Memory-based relationship dynamics

**Relationship Intelligence** (`policy/memory_relationship_intelligence.py`)

- Memory-aware authority models
- Experience-based conflict resolution
- Memory-driven age-appropriate access

**Emergency Intelligence** (`policy/memory_emergency_intelligence.py`)

- Memory-driven crisis management
- Experience-based emergency protocols
- Memory-aware device procedures

**Subscription Intelligence** (`policy/memory_subscription_intelligence.py`)

- Memory-driven feature access
- Usage pattern intelligence
- Family memory tier management

### Cognitive-Memory Integration

**Cognitive Policy** (`policy/memory_cognitive.py`)

- Memory-driven cognitive decisions
- Experience-based intelligence

**Attention Policy** (`policy/memory_attention.py`)

- Memory-aware attention control
- Experience-prioritized access

**Memory Lifecycle** (`policy/memory_lifecycle.py`)

- Memory formation & retention policies
- Experience-based memory management

**Memory Coordination** (`policy/memory_coordination.py`)

- Cross-device memory intelligence
- Family memory consensus protocols

---

## 📊 Event Bus Architecture

### Event Infrastructure

**Event Bus** (`events/bus.py`)

- Central message broker
- Topic-based routing
- Cognitive trace correlation

**Event Types** (`events/types.py`)

- Envelope + `cognitive_trace_id`
- Cross-namespace correlation: `cognitive.*` ↔ `intelligence.*` ↔ `events.*`

**Event Validation** (`events/validation.py`)

- Schema validation
- Correlation tracking
- Reject sink (`validation_rejects.log`)

**Event Persistence**

- WAL (JSONL) (`events/persistence.py`)
- Consumer Offsets
- Dead Letter Queue

### Event Routing

**Dispatcher** (`events/dispatcher.py`) — Fast routing
**Handlers** (`events/handlers.py`) — Pipeline integration
**Middleware** (`events/middleware.py`) — Interceptors
**Filters** (`events/filters.py`) — Advanced filtering
**Subscription** (`events/subscription.py`) — Registry management

---

## 🔗 Cross-Diagram Connections

**Diagram 2: Cognitive Core** — Memory Steward, Hippocampus, Working Memory
**Diagram 3: Intelligence Systems** — P04, P06, P20
**Diagram 4: Infrastructure** — P03, P05, P07, P08, P10-P19

---

## 🧠 DIAGRAM 2: COGNITIVE CORE — DETAILED ARCHITECTURE

### Overview: Memory Backbone Servants

All cognitive systems **serve the Memory Backbone** from Diagram 1. They coordinate memory formation, retrieval, consolidation, and conscious access.

---

## 🧠 Enhanced Hippocampus — Memory Formation System

### Two-Layer Architecture Detailed

**Purpose**: Memory formation servant FOR Memory Backbone
**Output**: Consolidated memories TO Memory Backbone
**Brain Regions**: Dentate Gyrus → CA3 → CA1

### Dentate Gyrus (Pattern Separation)

**Purpose**: Pattern separation FOR Memory encoding

**Components**:

- **Separator** (`hippocampus/dentate_gyrus/separator.py`)
  - Orthogonalization of inputs → Memory encoding
  - Sparse coding → Memory formation
  - Novelty detection → Memory prioritization
  - **SERVES**: Memory Backbone formation

- **Neurogenesis** (`hippocampus/dentate_gyrus/neurogenesis.py`)
  - Adult neurogenesis simulation
  - **SERVES**: Memory Backbone plasticity

- **Gating** (`hippocampus/dentate_gyrus/gating.py`)
  - Information gating control
  - **SERVES**: Memory Backbone quality

### CA3 Region (Pattern Completion)

**Purpose**: Content-addressable memory retrieval FROM Memory Backbone

**Components**:

- **Pattern Completer** (`hippocampus/ca3/pattern_completer.py`)
  - Autoassociative memory → Memory retrieval
  - Partial cue retrieval → Memory access
  - Sequence completion → Memory navigation
  - **SERVES**: Memory Backbone retrieval

- **Recurrent Network** (`hippocampus/ca3/recurrent_network.py`)
  - Recurrent connectivity FOR Memory associations
  - **SERVES**: Memory Backbone relationships

- **Consolidation Coordinator** (`hippocampus/ca3/consolidation_coordinator.py`)
  - Memory consolidation initiation FOR Memory Backbone
  - **SERVES**: Memory Backbone strengthening

### CA1 Region (Memory Output)

**Purpose**: Memory output TO Memory Backbone

**Components**:

- **Cortical Bridge** (`hippocampus/ca1/cortical_bridge.py`)
  - Hippocampal-Memory Backbone binding
  - Memory formatting FOR Memory Backbone
  - Context integration INTO Memory Backbone
  - **OUTPUT**: Formatted memories TO Memory Backbone

- **Novelty Comparator** (`hippocampus/ca1/novelty_comparator.py`)
  - Novelty detection FOR Memory prioritization
  - **SERVES**: Memory Backbone importance

- **Theta Rhythm** (`hippocampus/ca1/theta_rhythm.py`)
  - Theta rhythm FOR Memory coordination
  - **SERVES**: Memory Backbone timing

### Hippocampal Services

**Memory Formation Workflow** (`hippocampus/memory_orchestrator.py`)

- Coordinates: Memory Backbone formation
- Integrates with: Dentate Gyrus → CA3 → CA1 pipeline

**Episodic Encoder** (`hippocampus/episodic_encoder.py`)

- Episode encoding FOR Memory Backbone
- Outputs to: `st_hipp_store`, `st_epi`, `st_sem`

**Retrieval Coordinator** (`hippocampus/retrieval_coordinator.py`)

- Memory retrieval coordination FROM Memory Backbone
- Fast retrieval operations

**Consolidation Scheduler** (`hippocampus/consolidation_scheduler.py`)

- Consolidation scheduling FOR Memory Backbone
- Connects to: Infrastructure (Diagram 4)

**Flow**:

```
Intent Router → Attention Gate (ADMIT) → Memory Orchestrator
  ↓
Dentate Gyrus (Pattern Separation)
  ↓
CA3 (Pattern Completion + Consolidation)
  ↓
CA1 (Cortical Bridge → Memory Backbone)
  ↓
Storage: st_hipp_store, st_epi, st_sem, st_kg_dom
```

---

## 👁️ Enhanced Family Attention Gate — Thalamus Analog

### Memory Focus Management

**Purpose**: Memory-focused attention control
**Brain Analog**: Thalamus (relay station, sensory gating)
**File**: `attention_gate/family_gate_service.py`

### 4 Decision Modes (Brain-Inspired)

1. **ADMIT** — High Memory relevance + family importance → Immediate processing
2. **DEFER** — Queue for Memory processing → Later processing
3. **BOOST** — Memory priority elevation → Urgent processing
4. **DROP** — Memory resource protection → Reject request

**Family Memory Awareness**:

- Device Memory capability consideration
- Family relationship context
- Subscription tier enforcement

**Components**:

- **Salience Evaluator** (`attention_gate/family_salience_evaluator.py`)
  - Memory importance & family relevance evaluation
  - Memory operation prioritization
  - **SERVES**: Memory Backbone salience

- **Admission Controller** (`attention_gate/family_admission_controller.py`)
  - Memory cognitive load management
  - Device Memory capability consideration
  - **SERVES**: Memory Backbone admission

- **Intent Analyzer** (`attention_gate/family_intent_analyzer.py`)
  - Memory processing intent derivation
  - Memory operation context awareness
  - **SERVES**: Memory Backbone intent routing

### Thalamic Relay Circuits (4 Relays)

**Memory Relay** (`attention_gate/family_memory_relay.py`)

- **Direction**: TO Memory Backbone
- Memory formation relay
- Memory operation coordination

**Recall Relay** (`attention_gate/family_recall_relay.py`)

- **Direction**: FROM Memory Backbone
- Memory retrieval relay
- Memory access coordination

**Executive Relay** (`attention_gate/family_executive_relay.py`)

- **Direction**: THROUGH Memory Backbone
- Memory decision-making relay
- Memory-driven decision coordination

**Learning Relay** (`attention_gate/family_learning_relay.py`)

- **Direction**: TO Memory Backbone
- Memory adaptation signal relay
- Memory learning coordination

### Attention Mechanisms (4 Types)

**Spatial Attention** (`attention_gate/family_spatial_attention.py`)

- Memory space-based attention
- Device Memory location awareness
- **SERVES**: Memory Backbone spatial focus

**Temporal Attention** (`attention_gate/family_temporal_attention.py`)

- Memory time-based attention
- Memory milestone awareness (anniversaries, routines)
- **SERVES**: Memory Backbone temporal focus

**Feature Attention** (`attention_gate/family_feature_attention.py`)

- Memory content-based attention
- Memory feature awareness (topics, entities)
- **SERVES**: Memory Backbone feature focus

**Object Attention** (`attention_gate/family_object_attention.py`)

- Memory entity-based attention
- Family Memory entity recognition
- **SERVES**: Memory Backbone object focus

**Flow**:

```
Intent Router → Attention Gate
  ↓
Salience Evaluator → Admission Controller → Intent Analyzer
  ↓
Decision: ADMIT | DEFER | BOOST | DROP
  ↓
Relay Circuits (Memory | Recall | Executive | Learning)
  ↓
Attention Mechanisms (Spatial | Temporal | Feature | Object)
  ↓
Working Memory Manager | Hippocampus | Global Workspace
```

---

## 🧮 Working Memory — Memory Backbone Active Buffer

### Brain Analog: Prefrontal Cortex (Active Maintenance)

**Purpose**: Active memory context FOR Memory Backbone operations
**Architecture**: 3-tier cache system (L1/L2/L3 from Diagram 1)

**Working Memory Manager** (`core/family_working_memory_manager.py`)

- Active memory context FOR Memory Backbone
- Memory operation workspace
- Priority-aware Memory access
- Family Memory context awareness
- **SERVES**: Memory Backbone active operations

**Working Memory Buffer** (`core/family_working_memory_buffer.py`)

- Active Memory context maintenance FOR Memory Backbone
- Cross-device Memory sync coordination
- **BUFFERS**: Memory Backbone operations
- Fast access pattern

**Working Memory Attention** (`core/family_working_memory_attention.py`)

- Attentional control FOR Memory operations
- Memory-focused attention coordination
- **SERVES**: Memory Backbone attention

**Working Memory Executive** (`core/family_working_memory_executive.py`)

- Executive function FOR Memory coordination
- Memory operation authority management
- **SERVES**: Memory Backbone executive control

**Integration**:

```
Attention Gate → Working Memory Manager
  ↓
Working Memory Buffer (L1/L2/L3 Cache)
  ↓
├─ Working Memory Attention ↔ Attention Gate
├─ Working Memory Executive ↔ Cognitive Control
└─ Global Workspace Broadcast
```

**Connections**:

- **TO**: Global Workspace (consciousness)
- **FROM**: Attention Gate (admitted items)
- **WITH**: Cognitive Control (executive function)
- **SERVES**: Memory Backbone buffering

---

## 🌐 Global Workspace — Memory-Mediated Consciousness

### Brain Analog: Global Workspace Theory (Conscious Access)

**Purpose**: Memory-mediated consciousness, cross-module communication

**Global Broadcaster** (`workspace/family_global_broadcaster.py`)

- Conscious access THROUGH Memory Backbone
- Cross-module communication VIA Memory
- Coalition formation FROM Memory experiences
- Family consciousness sharing THROUGH Memory sync
- **SERVES**: Memory Backbone consciousness

**Coalition Manager** (`workspace/family_coalition_manager.py`)

- Memory-driven process arbitration
- Experience-based priority balancing
- **SERVES**: Memory Backbone arbitration

**Attention Router** (`workspace/attention_router.py`)

- Memory-aware attentional routing
- **SERVES**: Memory Backbone attention routing

**Consciousness Gateway** (`workspace/consciousness_gateway.py`)

- Memory-mediated conscious access control
- **SERVES**: Memory Backbone consciousness gateway

**Flow**:

```
Working Memory Buffer → Global Broadcaster
  ↓
Coalition Manager (process arbitration)
  ↓
Attention Router (routing decisions)
  ↓
Consciousness Gateway (access control)
  ↓
└─ Broadcasts to: Intelligence Systems (D3), Infrastructure (D4)
```

**Integration**:

- **FROM**: Working Memory (active context)
- **TO**: All cognitive modules (broadcast)
- **WITH**: Cognitive Control (monitoring)
- **SERVES**: Memory-mediated consciousness

---

## ⚙️ Cognitive Control — Anterior Cingulate Analog

### Brain Analog: Anterior Cingulate Cortex (Conflict Monitoring)

**Purpose**: Performance monitoring, error detection, control adjustment

**Cognitive Monitor** (`core/cognitive_monitor.py`)

- **CONFLICT MONITORING**:
  - Performance monitoring
  - Error detection
  - Control adjustment
- Monitors: Working Memory Executive
- Feeds: Cognitive Controller

**Cognitive Controller** (`core/cognitive_controller.py`)

- Control signal generation
- Adjusts: Working Memory, Global Workspace
- Responds to: Monitor feedback

**Adaptive Controller** (`core/adaptive_controller.py`)

- Learning-based adaptation
- Connects to: Intelligence Systems (D3)

**Flow**:

```
Cognitive Monitor (detects conflicts/errors)
  ↓
Cognitive Controller (generates control signals)
  ↓
Adaptive Controller (learns from outcomes)
  ↓
└─ Adjusts: Working Memory Executive, Global Workspace
```

---

## 🧩 Enhanced Cognitive Services — Memory Operation Coordinators

### Memory Operation Coordination Services

**Memory Adapter Service** (`services/memory_adapter_service.py`)

- **MEMORY BACKBONE ADAPTER**:
  - Routes TO Memory Backbone (D1)
  - Memory operation coordination
  - Memory policy integration
- **COORDINATES**: Memory Backbone operations
- Connects to: Hippocampus Orchestrator, Working Memory Manager

**Context Adapter Service** (`services/context_adapter_service.py`)

- **MEMORY CONTEXT ADAPTER**:
  - Routes TO Memory context systems (D1)
  - Memory context coordination
  - Memory operation optimization
- **COORDINATES**: Memory Backbone context
- Connects to: Retrieval Context Adapter, Working Memory Buffer

**Attention Service** (`services/attention_service.py`)

- **MEMORY ATTENTION COORDINATION**:
  - Memory salience evaluation
  - Memory resource allocation
  - Memory priority management
- **COORDINATES**: Memory Backbone attention
- Connects to: Attention Gate, Salience Evaluator

**Affect Integration Service** (`services/affect_integration_service.py`)

- **MEMORY-EMOTION COORDINATION**:
  - Affect-Memory integration
  - Emotional Memory state management
  - Memory bias detection & correction
- **COORDINATES**: Memory Backbone emotions
- Connects to: Affect State, Affect Classifier

### Memory Supporting Services

**Service Manager** (`services/service_manager.py`)

- Enhanced with Memory awareness
- **SERVES**: Memory Backbone coordination

**Cognitive Architecture** (`services/cognitive_architecture.py`)

- Memory-inspired coordination
- **SERVES**: Memory Backbone architecture

**Write Service** (`services/write_service.py`)

- Memory formation coordination FOR Memory Backbone
- **SERVES**: Memory Backbone writing
- Fast-path processing

**Retrieval Service** (`services/retrieval_service.py`)

- Context assembly FROM Memory Backbone
- **SERVES**: Memory Backbone retrieval
- Fast-path processing

**Consolidation Service** (`services/consolidation_service.py`)

- Memory processing FOR Memory Backbone
- **SERVES**: Memory Backbone consolidation

**Indexing Service** (`services/indexing_service.py`)

- Memory organization FOR Memory Backbone
- **SERVES**: Memory Backbone indexing
- Fast-path processing

**Personal Identity Service** (`services/personal_identity_service.py`)

- Self-model maintenance IN Memory Backbone
- **SERVES**: Memory Backbone identity

### Service Integration Layer

**Event Coordinator** (`services/event_coordinator.py`)

- Memory event orchestration
- **COORDINATES**: Memory Backbone events
- Connects to: Infrastructure (D4)

**Workflow Manager** (`services/workflow_manager.py`)

- Memory service workflows
- **COORDINATES**: Memory Backbone workflows

**Performance Monitor** (`services/performance_monitor.py`)

- Memory cognitive load monitoring
- **MONITORS**: Memory Backbone performance

---

## 💝 Affect-Aware Processing — Limbic Integration

### Brain Analog: Amygdala & Limbic System (Emotional Intelligence)

**Purpose**: Emotional intelligence, threat detection, memory modulation

### Amygdala Analog (Threat & Salience)

**Threat Detector** (`affect/threat_detector.py`)

- **THREAT DETECTION**:
  - Safety signal generation
  - Arousal modulation
  - Priority interrupts
- Connects to: Attention Gate, Salience Evaluator

**Emotional Salience** (`affect/emotional_salience.py`)

- Emotional importance scoring
- Enhances: Memory prioritization

**Memory Modulation** (`affect/memory_modulation.py`)

- Emotion-memory interaction
- Connects to: Hippocampus Orchestrator

### Affective Processing

**Realtime Classifier** (`affect/realtime_classifier.py`)

- **EMOTION RECOGNITION**:
  - Real-time emotion detection
  - Valence & arousal computation
  - Context-aware calibration

**Affect State** (`affect/affect_state.py`)

- Emotional state tracking

**Emotion Regulation** (`affect/emotion_regulation.py`)

- Emotional regulation strategies

**Emotional Contagion** (`affect/emotional_contagion.py`)

- Social emotion processing

### Cognitive-Affective Integration

**Attention Bias** (`affect/attention_bias.py`)

- Emotion-attention interaction
- Connects to: Working Memory Attention

**Memory Bias** (`affect/memory_bias.py`)

- Emotion-memory interaction
- Connects to: Hippocampus

**Decision Bias** (`affect/decision_bias.py`)

- Emotion-decision interaction
- Connects to: Cognitive Control

**Affective Learning** (`affect/affective_learning.py`)

- Emotion-based learning
- Connects to: Intelligence Systems (D3)

**Flow**:

```
Perception → Realtime Classifier
  ↓
Affect State → Emotion Regulation
  ↓
Integration Layer:
  ├─ Attention Bias → Working Memory
  ├─ Memory Bias → Hippocampus
  ├─ Decision Bias → Cognitive Control
  └─ Affective Learning → Intelligence Systems (D3)
```

---

## 🔎 Enhanced Retrieval — Context Assembly & Fusion

### Purpose: Multi-store context assembly FROM Memory Backbone

**Context Adapter** (`retrieval/context_adapter.py`)

- **CONTEXT ADAPTER**:
  - Delegates to `context_bundle/*` (D1)
  - Working memory integration
  - Local affect-aware ranking only
- Connects to: Context Bundle Builder (D1)

**Enhanced Broker** (`retrieval/enhanced_broker.py`)

- Store orchestration & fanout
- Multi-store coordination

**Fusion Engine** (`retrieval/fusion_engine.py`)

- Cross-store result fusion
- Integrates: FTS, Vector, Knowledge Graph, Episodic

**MMR Engine** (`retrieval/mmr_engine.py`)

- Maximal Marginal Relevance
- Diversity optimization

### Cognitive Retrieval Features

**Working Memory Boost** (`retrieval/working_memory_boost.py`)

- Active context amplification
- Fast-path integration with L1/L2 cache

**Affective Bias** (`retrieval/affective_bias.py`)

- Emotion-aware retrieval
- Connects to: Affect State

**Temporal Bias** (`retrieval/temporal_bias.py`)

- Recency & frequency bias

**Social Bias** (`retrieval/social_bias.py`)

- Social context awareness

### Traditional Retrieval

**QoS Gate** (`retrieval/qos_gate.py`)

- Performance & budget control
- Fast-path optimization

**Features** (`retrieval/features.py`)

- Feature extraction

**Ranker** (`retrieval/ranker.py`)

- Relevance ranking
- Connects to: Cortex Prediction (calibration)

**Calibration** (`retrieval/calibration.py`)

- Confidence calibration

**Trace Builder** (`retrieval/trace_builder.py`)

- Provenance tracking

### Store Adapters (4 Types)

**FTS Adapter** (`retrieval/stores/fts_adapter.py`)

- Full-text search
- Connects to: `st_fts`

**Vector Adapter** (`retrieval/stores/vector_adapter.py`)

- Semantic similarity
- Connects to: `st_vec`

**Knowledge Graph Adapter** (`retrieval/stores/kg_adapter.py`)

- Knowledge graph traversal
- Connects to: `st_kg_dom`

**Episodic Adapter** (`retrieval/stores/episodic_adapter.py`)

- Episodic memory retrieval
- Connects to: `st_epi`

**Flow**:

```
Attention Gate (Recall Relay) → Context Adapter
  ↓
Enhanced Broker → Store Fanout (parallel queries)
  ↓
├─ FTS Adapter → st_fts
├─ Vector Adapter → st_vec
├─ KG Adapter → st_kg_dom
└─ Episodic Adapter → st_epi
  ↓
Fusion Engine → Result Fuser
  ↓
MMR Engine → Diversification
  ↓
Cognitive Retrieval Features:
  ├─ Working Memory Boost (L1/L2 cache)
  ├─ Affective Bias (emotion weighting)
  ├─ Temporal Bias (recency/frequency)
  └─ Social Bias (family context)
  ↓
Ranker → Calibration → Trace Builder
  ↓
Context Bundle (ready for consumption)
```

---

## 👀 Perception & 📦 Episodic

### Perception

**Purpose**: Sensory input processing

**Components**:

- `perception/api.py` — Perception API
- `perception/sensors.py` — Sensor integration
- `perception/fusion.py` — Multi-sensor fusion
- `perception/preattentive.py` — Preattentive processing

**Flow**:

```
Sensors → Sensor Fusion → Preattentive Processing
  ↓
Working Memory Buffer + Affect Classifier
```

### Episodic

**Purpose**: Episodic memory storage

**Components**:

- `episodic/service.py` — Episodic service
- `episodic/store.py` — Episodic store
- `episodic/sequences.py` — Sequence tracking
- `episodic/types.py` — Type definitions
- `episodic/utils.py` — Utilities

**Storage**: `st_epi`, `st_seq`

---

## 🧠 Cortex / Prediction

**Purpose**: Predictive modeling, calibration

**Components**:

- `cortex/predictive_model.py` — Predictive model
- `cortex/bandit.py` — Multi-armed bandit
- `cortex/calibration.py` — Confidence calibration
- `cortex/features.py` — Feature engineering

**Connects to**: Retrieval Ranker (calibration feedback)

---

## 🔤 Embeddings (Core Memory)

**Purpose**: Vector embeddings for semantic memory

**Components**:

- `embeddings/service.py` — Embedding service
- `embeddings/embedding_service.py` — Embedding implementation
- `embeddings/index.py` — Embedding index
- `embeddings/store.py` — Embedding store
- `embeddings/types.py` — Type definitions

**Integrations**:

- Hippocampus Encoder (episode embeddings)
- Retrieval Context Adapter (semantic search)
- Storage: `st_emb`, `st_vec`

**Flow**:

```
Hippocampus Encoder → Embedding Service
  ↓
Embedding Implementation → Embedding Index
  ↓
Embedding Store → st_emb, st_vec
  ↓
Retrieval Context Adapter (semantic search)
```

---

## 🪩 Workflows & Events (Core)

### Workflows

**Purpose**: Orchestrated cognitive workflows

**Components**:

- `workflows/workflow_base.py` — Workflow base class
- `workflows/store.py` — Workflow store
- `workflows/recall_workflow.py` — Recall workflow
- `workflows/sequence_flow_workflow.py` — Sequence workflow

**Connects to**:

- Retrieval Broker (recall workflow)
- Episodic Sequences (sequence workflow)
- Workspace Store (workflow state)

### Events

**Purpose**: Cognitive event coordination

**Components**:

- `events/bus.py` — Event bus
- `events/handlers.py` — Event handlers
- `events/types.py` — Event type definitions
- `events/write_handler.py` — Write event handler

**Cognitive Events**:

- `SENSORY_FRAME` — Sensory input event
- `WORKSPACE_BROADCAST` — Global workspace broadcast
- `METACOG_REPORT` — Metacognition report
- `DRIVE_TICK` — Drive/motivation signal
- `BELIEF_UPDATE` — Belief update event
- `SIMULATION_REQUEST` — Simulation request
- `SIMULATION_RESULT` — Simulation result
- `ACTION_DECISION` — Action decision
- `ACTION_EXECUTED` — Action execution
- `HIPPO_ENCODE` — Hippocampus encoding
- `NREM/REM START/END` — Sleep cycle events
- `NEUROM_TICK` — Neuromodulation signal
- `DSAR_EXPORT` — DSAR export request
- `REINDEX_REQUEST` — Reindex request
- `ML_RUN_EVENT` — ML run event

**Event Definitions**: `events/cognitive_events.py`

---

## 💾 Storage (Edge SQLite + Files)

### Storage Infrastructure

**Purpose**: Device-local storage FOR Memory Backbone

**Components**:

- `storage/unit_of_work.py` — UnitOfWork pattern (ACID transactions)
- `storage/episodic_store.py` — Episodic memory store
- `storage/fts_store.py` — Full-text search store
- `storage/vector_store.py` — Vector embedding store
- `storage/embeddings_store.py` — Embeddings management
- `storage/semantic_store.py` — Semantic memory store
- `storage/blob_store.py` — Blob/file storage
- `storage/receipts_store.py` — Receipt storage
- `storage/secure_store.py` — Encrypted storage
- `storage/kg_store.py` — Knowledge graph store
- `storage/pattern_detector.py` — Pattern detection
- `storage/interfaces.py` — Storage interfaces
- `storage/workspace_store.py` — Workspace state
- `storage/hippocampus_store.py` — Hippocampus staging (`st_hipp_store`)
- `storage/sqlite_util.py` — SQLite utilities
- `storage/base_store.py` — Base store class

**Episodic Sequences**: `episodic/sequences.py` → `st_seq`

**Storage Flow**:

```
Hippocampus Encoder → st_hipp_store, st_epi, st_sem
CA1 Bridge → st_sem, st_kg_dom
Retrieval Fusion → st_fts, st_vec, st_sem, st_epi
Receipts → st_receipts → Infrastructure (D4)
```

---

## 🔄 Core Processing Systems

**Purpose**: Core cognitive operations

**Components**:

- `core/writer.py` — Enhanced with Working Memory integration
- `core/curator.py` — Content curation & filtering
- `core/salience_processor.py` — Importance computation
- `core/goal_manager.py` — Goal tracking & prioritization

**Integrations**:

- Writer → Working Memory Manager
- Salience Processor → Attention Gate
- Goal Manager → Cognitive Control

---

## 🔗 Cognitive Integration Flows

### Fast Lane vs Smart Lane (Refined)

**Fast Lane** (High-confidence path):

```
Intent Router → Valid & Confident Intent
  ↓
├─ Write Service (memory formation)
├─ Retrieval Service (memory access)
├─ Indexing Service (memory organization)
└─ Consolidation Service (memory processing)
  ↓
Direct execution without cognitive orchestration
```

**Smart Lane** (Cognitive processing path):

```
Intent Router → Unset/Low-Confidence Intent | High-Risk | Obligations
  ↓
Attention Gate (Thalamus)
  ↓
Decision: ADMIT | DEFER | BOOST | DROP
  ↓
├─ ADMIT → Working Memory Manager
├─ Working Memory → Global Workspace
├─ Global Workspace → Consciousness Gateway
└─ Consciousness Gateway → Cognitive processing
  ↓
Full cognitive orchestration with monitoring
```

### Memory Formation Flow (Detailed)

```
API Request → Intent Router
  ↓
Attention Gate (Memory Relay) → ADMIT
  ↓
Working Memory Manager (buffering)
  ↓
Hippocampus Memory Orchestrator
  ↓
Dentate Gyrus (pattern separation)
  ↓
CA3 (pattern completion + consolidation)
  ↓
CA1 (cortical bridge)
  ↓
Hippocampus Encoder
  ↓
Storage: st_hipp_store, st_epi, st_sem
  ↓
Event Bus: HIPPO_ENCODE event
  ↓
Pipeline P02 (Write/Ingest) — See Diagram 1
```

### Memory Retrieval Flow (Detailed)

```
API Request → Intent Router
  ↓
Attention Gate (Recall Relay) → ADMIT
  ↓
Working Memory Manager (check L1/L2 cache)
  ↓
Context Adapter (delegates to Context Bundle Builder D1)
  ↓
Enhanced Broker → Store Fanout (parallel)
  ├─ FTS Adapter → st_fts
  ├─ Vector Adapter → st_vec
  ├─ KG Adapter → st_kg_dom
  └─ Episodic Adapter → st_epi
  ↓
Fusion Engine (cross-store fusion)
  ↓
MMR Engine (diversification)
  ↓
Cognitive Retrieval Features:
  ├─ Working Memory Boost
  ├─ Affective Bias
  ├─ Temporal Bias
  └─ Social Bias
  ↓
Ranker → Calibration → Trace Builder
  ↓
Context Bundle → Pipeline P01 (Recall/Read) — See Diagram 1
```

### Consciousness & Decision Flow

```
Working Memory Buffer → Global Broadcaster
  ↓
Coalition Manager (process arbitration)
  ↓
Attention Router (routing decisions)
  ↓
Consciousness Gateway (access control)
  ↓
Broadcast to all cognitive modules
  ↓
Cognitive Control Monitor (conflict detection)
  ↓
Cognitive Controller (control signals)
  ↓
Adaptive Controller (learning)
  ↓
Intelligence Systems (D3) for action selection
```

---

## 🧠 Memory Backbone Connections (Diagram 2 → Diagram 1)

### TO Memory Backbone (Formation)

- Hippocampus Orchestrator → Memory Formation
- Hippocampus Encoder → Episodic Memories
- Hippocampus Consolidation → Consolidated Memories
- CA1 Bridge → Formatted Memories
- Working Memory Manager → Active Memory Context
- Working Memory Buffer → Memory Operations
- Working Memory Executive → Memory Control
- Attention Gate → Filtered for Memory
- Memory Relay → Memory Formation Relay
- Global Broadcaster → Memory-Mediated Consciousness
- Cognitive Services (Memory Adapter) → Memory Operations
- Cognitive Services (Write Service) → Memory Formation
- Cognitive Services (Consolidation Service) → Memory Consolidation

### FROM Memory Backbone (Retrieval)

- Recall Relay → Memory Retrieval
- Consciousness Gateway → Conscious Memory Access
- Cognitive Services (Recall Service) → Memory Retrieval

### Integration Points

All Diagram 2 components are **servants of Memory Backbone (D1)**:

- Hippocampus → Memory formation servant
- Attention Gate → Memory focus management servant
- Working Memory → Memory Backbone active buffer
- Global Workspace → Memory-mediated consciousness
- Cognitive Services → Memory operation coordinators

---

## 📊 Cross-Diagram Connections

### TO Intelligence Systems (Diagram 3)

- Affective Learning
- Cognitive Adaptation
- Working Memory Manager
- Global Consciousness
- Retrieval Context Adapter

### TO Infrastructure (Diagram 4)

- Hippocampus Consolidation
- Event Coordinator
- Global Consciousness
- Consolidation Service
- Receipts → `st_receipts`

---

## 🧠 DIAGRAM 3: INTELLIGENCE SYSTEMS — ADVISORY LAYER

### Overview: Memory-Driven Intelligence (Advisory Only)

**Critical Architectural Boundary**: Intelligence Systems provide **ADVISORY SIGNALS ONLY**. P04 (Arbitration/Action Pipeline) is the **SOLE action executor**. Family relationship context respected in all decisions.

All intelligence systems are **memory-driven** and serve Memory Backbone operations.

---

## ⚠️ Architectural Boundary: Advisory-Only Intelligence

### Key Principles

1. **Advisory Only** — Intelligence systems emit signals → P04; never execute actions directly
2. **Memory-Driven** — All intelligence FROM Memory Backbone experiences
3. **Family-Aware** — Family relationship context in all processing
4. **Cross-Device** — Intelligence coordination across family devices
5. **Observability** — All intelligence events carry `cognitive_trace_id`

### Intelligence → P04 Flow

```
Intelligence Systems (Advisory Signals)
  ↓
Intelligence Guards (Policy/QoS/Safety)
  ↓
intelligence.advisory.* events
  ↓
P04 (Arbitration/Action Pipeline) — SOLE EXECUTOR
  ↓
Action execution with Memory context
```

---

## 🧠 Memory-Driven Intelligence Infrastructure

### Memory Intelligence Coordinator

**Purpose**: Memory Backbone intelligence orchestration
**File**: Memory Intelligence Coordinator service

**Responsibilities**:

- Memory-driven cross-system coordination
- Memory resource management for intelligence
- Memory-informed performance optimization
- **SERVES**: Memory Backbone intelligence operations

### Memory Backbone Intelligence Manager

**Purpose**: Memory intelligence coordination
**Responsibilities**:

- Memory-aware working memory coordination
- Memory consolidation handoff for intelligence
- Memory-driven intelligence state management
- **SERVES**: Memory Backbone intelligence storage

### Memory Intelligence Event Processor

**Purpose**: Memory intelligence events with `cognitive_trace_id` correlation
**Responsibilities**:

- Memory-aware signal routing
- Memory-driven state synchronization
- Memory `cognitive_trace_id` correlation
- **SERVES**: Memory Backbone intelligence coordination

### Memory-Enhanced Traditional Systems

**Memory-Aware Social Cognition**

- Social intelligence FROM Memory Backbone
- **SERVES**: Memory Backbone social insights

**Memory-Driven Metacognition**

- Self-reflection THROUGH Memory Backbone
- **SERVES**: Memory Backbone self-awareness

**Memory-Informed Drives**

- Motivation FROM Memory experiences
- **SERVES**: Memory Backbone motivation

**Memory-Enhanced Affect**

- Emotions integrated WITH Memory Backbone
- **SERVES**: Memory Backbone emotional intelligence

**Memory-Guided Action**

- Actions informed BY Memory Backbone
- **SERVES**: Memory Backbone action intelligence

**Memory-Driven Learning**

- Learning coordinated THROUGH Memory Backbone
- **SERVES**: Memory Backbone adaptive intelligence

**Memory-Powered Imagination**

- Creativity FROM Memory experiences
- **SERVES**: Memory Backbone creative intelligence

---

## 🔄 Memory-Driven Learning Loop & Adaptive Intelligence

### Memory Backbone Learning Core

**Memory Learning Coordinator** — Central orchestrator

- Memory-driven learning coordination
- Memory experience integration
- Memory-informed adaptation strategies
- **COORDINATES**: Memory Backbone learning

**Memory-Informed Predictive Learning**

- Predictions FROM Memory experiences
- **SERVES**: Memory Backbone predictions

**Memory-Driven Adaptive Controller**

- Adaptation THROUGH Memory insights
- **SERVES**: Memory Backbone adaptation
- Connects to: P06 (Learning/Neuromod)

**Memory Learning Feedback Integration**

- Feedback integrated WITH Memory Backbone
- **SERVES**: Memory Backbone feedback loops

**Learning Flow**:

```
Memory Learning Coordinator
  ↓
Memory-Informed Predictive Learning
  ↓
Memory-Driven Adaptive Controller
  ↓
Memory Learning Feedback Integration
  ↓
Loop back to Coordinator
```

**Integrations**:

- Feedback → Reward Prediction
- Feedback → Metacognitive Performance Monitoring
- Adaptive Controller → Action Selection
- Adaptive Controller → Habit Modification

### Memory-Enhanced Specialized Learning

**Memory-Driven Procedural Learning**

- Skills learned THROUGH Memory patterns
- **SERVES**: Memory Backbone skill development
- Connects to: Habit Formation, Skill Acquisition

**Memory Backbone Declarative Learning**

- Facts integrated INTO Memory knowledge
- **SERVES**: Memory Backbone knowledge base

**Memory-Informed Reinforcement Learning**

- Rewards evaluated THROUGH Memory context
- **SERVES**: Memory Backbone reward learning
- Connects to: Reward Prediction, Incentive Learning

**Memory-Enhanced Social Learning**

- Social learning FROM Memory relationships
- Family Memory social intelligence
- **SERVES**: Memory Backbone social development
- Connects to: Social Imitation → Theory of Mind

### Memory-Driven Meta-Learning & Transfer

**Memory Meta-Learning**

- Learning about learning FROM Memory patterns
- **SERVES**: Memory Backbone meta-intelligence

**Memory-Based Transfer Learning**

- Knowledge transfer THROUGH Memory connections
- **SERVES**: Memory Backbone knowledge transfer
- Connects to: Creativity Insight, Skill Transfer

**Memory-Driven Curiosity Learning**

- Curiosity guided BY Memory gaps
- **SERVES**: Memory Backbone exploration
- Connects to: Curiosity Drive, Forward Simulation

**Flow**:

```
Memory Meta-Learning
  ↓
Memory-Based Transfer Learning
  ↓
Memory-Driven Curiosity Learning
  ↓
Drives: Curiosity Drive, Forward Simulation
```

---

## 🤝 Family Memory-Aware Social Cognition

### Memory-Driven Theory of Mind Core

**Memory-Based Belief Attribution**

- Understanding others THROUGH Memory relationships
- Family belief modeling FROM Memory
- **SERVES**: Memory Backbone social understanding

**Memory-Informed Intention Recognition**

- Intentions understood THROUGH Memory patterns
- Family intention awareness FROM Memory
- **SERVES**: Memory Backbone intention intelligence

**Memory-Enhanced Emotion Attribution**

- Emotional understanding FROM Memory experiences
- Family emotional intelligence THROUGH Memory
- **SERVES**: Memory Backbone emotional understanding

**Memory Knowledge Attribution**

- Others' knowledge modeled IN Memory Backbone
- Family knowledge awareness THROUGH Memory
- **SERVES**: Memory Backbone knowledge modeling

**Flow**:

```
Memory-Based Belief Attribution
  ↓
Memory-Informed Intention Recognition
  ↓
Memory-Enhanced Emotion Attribution
  ↓
Memory Knowledge Attribution
```

**Connections**:

- Belief Attribution → Decision Evaluation
- Belief Attribution → Empathy
- Belief Attribution → Social Imitation

### Memory-Enhanced Social Reasoning

**Memory-Based Social Norms**

- Social rules learned FROM Memory experiences
- Family norms stored IN Memory Backbone
- **SERVES**: Memory Backbone social intelligence

**Memory Relationship Modeling**

- Relationships tracked IN Memory Backbone
- Family dynamics FROM Memory patterns
- **SERVES**: Memory Backbone relationship intelligence

**Memory-Informed Communication Intent**

- Communication understanding THROUGH Memory context
- Family communication patterns FROM Memory
- **SERVES**: Memory Backbone communication intelligence

**Memory-Driven Cooperation & Competition**

- Social strategies FROM Memory experiences
- Family cooperation patterns THROUGH Memory
- **SERVES**: Memory Backbone social coordination

**Bidirectional Flows**:

```
Memory-Based Social Norms ↔ Memory Relationship Modeling
  ↔
Memory-Informed Communication Intent ↔ Memory-Driven Cooperation
```

### Memory-Enhanced Social Learning & Adaptation

**Memory-Informed Imitation Learning**

- Social learning THROUGH Memory examples
- Family behavior learning FROM Memory
- **SERVES**: Memory Backbone social development
- Connects to: Theory of Mind Beliefs

**Memory Social Feedback**

- Social feedback integrated INTO Memory Backbone
- Family feedback patterns IN Memory
- **SERVES**: Memory Backbone social improvement
- Publishes: `intelligence.social.*` events

**Memory Perspective Switching**

- Perspective taking FROM Memory experiences
- Family perspective understanding THROUGH Memory
- **SERVES**: Memory Backbone empathy intelligence

---

## 🪞 Metacognitive Feedback Systems

### Brain Analog: Anterior Prefrontal Cortex (aPFC) + Anterior Cingulate (ACC)

**Purpose**: Self-monitoring, confidence assessment, cognitive regulation

### Metacognitive Monitoring

**Confidence Assessment**

- Evaluates certainty of beliefs, decisions, memories
- Connects to: Decision Evaluation, Memory Retrieval

**Performance Monitoring**

- Tracks task success, error detection
- Connects to: Learning Feedback, Conflict Detection
- Feeds: Metacognitive Store (`st_metacog`)

**Knowledge Assessment**

- Evaluates what is known vs. unknown
- Guides learning priorities

**Strategy Monitoring**

- Tracks effectiveness of cognitive strategies
- Adapts approaches based on outcomes

**Flow**:

```
Confidence Assessment → Performance Monitoring
  ↓
Knowledge Assessment → Strategy Monitoring
```

### Metacognitive Control

**Cognitive Regulation**

- Adjusts cognitive resources allocation
- Connects to: Emotion Regulation, Cognitive Control

**Metacognitive Planning**

- Plans cognitive strategies
- Connects to: P05 (Prospective/Triggers)

**Reflective Processing**

- Deep self-reflection on experiences
- Publishes: `intelligence.metacog.*` events
- Connects to: P04 (advisory signals)

**Flow**:

```
Cognitive Regulation → Metacognitive Planning → Reflective Processing
```

### Self-Model & Identity

**Self-Concept**

- Core identity representation
- Bidirectional with: Self-Efficacy, Self-Awareness

**Self-Efficacy**

- Beliefs about own capabilities
- Bidirectional with: Self-Concept, Self-Awareness

**Self-Awareness**

- Conscious self-knowledge
- Bidirectional with: Self-Concept, Self-Efficacy

**Connections**:

```
Self-Concept ↔ Self-Efficacy ↔ Self-Awareness
```

---

## 🔥 Reward Systems & Motivation

### Brain Analog: Ventral Tegmental Area (VTA) + Striatum

**Purpose**: Reward prediction, motivation, drive management

### Core Reward Processing

**Reward Prediction**

- Predicts future rewards FROM Memory experiences
- Connects to: Reinforcement Learning, Incentive Learning

**Prediction Error**

- Computes difference between predicted/actual rewards
- **Critical for learning**: Drives reinforcement learning
- Connects to: Learning Reinforcement, Action Outcomes

**Value Assessment**

- Evaluates worth of options, states, actions
- Connects to: Decision Evaluation, Personalization (P19 input)

**Flow**:

```
Reward Prediction → Prediction Error → Value Assessment
```

### Motivational Systems

**Homeostatic Drives**

- Basic needs (energy, rest, comfort)
- Connects to: Incentive Salience

**Curiosity Drive**

- Exploration motivation
- Connects to: Memory-Driven Curiosity Learning, Incentive Salience

**Achievement Drive**

- Goal pursuit motivation
- Connects to: Incentive Salience

**Social Drive**

- Social connection motivation
- Connects to: Incentive Salience

**All drives feed into**: Incentive Salience

### Incentive Processing

**Incentive Salience**

- "Wanting" signal for motivation
- Input from: All drive systems

**Incentive Learning**

- Learning what to want
- Input from: Reward Prediction, Salience

**Motivation Regulation**

- Balances competing motivations
- Output: Regulated motivation signals

**Flow**:

```
Drives → Incentive Salience → Incentive Learning → Motivation Regulation
```

---

## 🧠 Procedural Memory & Habits

### Brain Analog: Basal Ganglia + Motor Cortex

**Purpose**: Habit formation, skill learning, automatic action control

### Habit Formation System

**Habit Formation**

- Creates automatic behavioral sequences
- Input from: Procedural Learning

**Habit Execution**

- Executes learned habits automatically
- Output to: Action Coordination (advisory), Motor Acquisition

**Habit Modification**

- Updates existing habits
- Input from: Adaptive Controller

**Flow**:

```
Habit Formation → Habit Execution → Habit Modification
```

### Skill Learning & Motor Programs

**Skill Acquisition**

- Initial skill learning
- Input from: Procedural Learning
- Feeds: Procedural Store (`st_procedural`)

**Skill Refinement**

- Improves skill precision
- Output from: Skill Acquisition

**Skill Transfer**

- Applies skills to new contexts
- Input from: Memory-Based Transfer Learning

**Flow**:

```
Skill Acquisition → Skill Refinement → Skill Transfer
```

### Action Selection & Control

**Action Selection**

- Chooses actions based on context
- **Advisory only** → Connects to: Action Coordination (signals to P04)
- Input from: Adaptive Controller

**Action Inhibition**

- Suppresses inappropriate actions
- Bidirectional with: Action Selection, Action Switching
- Output: Inhibition Signal (monitor)

**Action Switching**

- Switches between action sequences
- Bidirectional with: Action Selection, Action Inhibition

**Bidirectional Flow**:

```
Action Selection ↔ Action Inhibition ↔ Action Switching
```

---

## 🧠 Imagination & Simulation

### Brain Analog: Default Mode Network (DMN)

**Purpose**: Mental simulation, creativity, dreaming, offline processing

### Mental Simulation Engine

**Forward Simulation**

- Simulates future scenarios FROM Memory
- Connects to: Decision Evaluation, Plan Formation, Curiosity Drive

**Counterfactual Thinking**

- "What if" alternative scenarios
- Bidirectional with: Forward Simulation, Episodic Simulation

**Episodic Simulation**

- Reconstructs/constructs episodic scenarios
- Bidirectional with: Forward Simulation, Counterfactual Thinking

**Bidirectional Flow**:

```
Forward Simulation ↔ Counterfactual Thinking ↔ Episodic Simulation
```

### Creative & Generative Processes

**Divergent Thinking**

- Generates multiple creative solutions
- Bidirectional with: Convergent Thinking

**Convergent Thinking**

- Narrows to best solution
- Bidirectional with: Divergent Thinking
- Output to: Creativity Insight

**Insight Generation**

- "Aha!" moments, creative breakthroughs
- Input from: Memory-Based Transfer Learning

**Flow**:

```
Divergent Thinking ↔ Convergent Thinking → Insight Generation
```

### Dreaming & Offline Processing

**Memory Consolidation**

- Offline memory strengthening during sleep
- Connects to: P04 (advisory), Dream Exploration

**Explorative Dreaming**

- Creative exploration during sleep
- Bidirectional with: Memory Consolidation, Mental Rehearsal

**Mental Rehearsal**

- Practice without execution
- Bidirectional with: Memory Consolidation, Explorative Dreaming

**Bidirectional Flow**:

```
Memory Consolidation ↔ Explorative Dreaming ↔ Mental Rehearsal
```

---

## 🎮 Action Systems (Advisory Signals Only)

### ⚠️ Critical: Advisory Only — P04 is Sole Executor

**Purpose**: Action planning, motor learning, action monitoring — **ALL ADVISORY**

### Action Planning (Advisory)

**Goal Formation**

- Generates goal representations
- **ADVISORY** → Signals to P04
- Input from: Memory Backbone

**Action Planning**

- Plans action sequences
- **ADVISORY** → Signals to P04

**Coordination Advisory**

- Coordinates action timing/sequencing
- **ADVISORY** → Signals to P04
- Input from: Habit Execution, Action Selection

**Flow**:

```
Goal Formation → Action Planning → Coordination Advisory
  ↓
All send advisory signals → P04
```

### Motor Learning & Adaptation

**Motor Acquisition**

- Learns new motor skills
- Input from: Habit Execution, Memory-Guided Action

**Motor Adaptation**

- Adapts motor programs to context

**Motor Expertise**

- Achieves expert-level motor skill

**Flow**:

```
Motor Acquisition → Motor Adaptation → Motor Expertise
```

### Action Monitoring & Control

**Action Feedback**

- Monitors action execution outcomes
- Input from: Action Coordination

**Inhibition Signal (Monitor)**

- Monitors inhibition effectiveness
- Input from: Action Inhibition

**Outcome Evaluation**

- Evaluates action results
- Input from: Prediction Error (reward system)

---

## ⚖️ Arbitration & Decision (Advisory → P04)

### ⚠️ Critical: Advisory Only — P04 Makes Final Decisions

**Purpose**: Decision-making, strategic planning, conflict resolution — **ALL ADVISORY**

### Decision Architecture (Advisory)

**Option Generation**

- Generates decision options
- **ADVISORY** → Signals to P04

**Option Evaluation**

- Evaluates option quality
- **ADVISORY** → Signals to P04
- Input from: Reward Valuation, Metacognitive Confidence, Theory of Mind, Forward Simulation, P19 (Personalization)

**Decision Recommendation**

- Recommends best option
- **ADVISORY** → Signals to P04
- Connects to: Intelligence Guards → `intelligence.advisory.*` → P04
- Output from: Workspace Broadcast
- Publishes: `intelligence.decision.*` events

**Flow**:

```
Option Generation → Option Evaluation → Decision Recommendation
  ↓
Intelligence Guards (Policy/QoS/Safety)
  ↓
intelligence.advisory.* events
  ↓
P04 (Final Decision & Execution)
```

### Strategic Planning (Advisory)

**Plan Formation**

- Creates strategic plans
- **ADVISORY** → Signals to P04
- Input from: Forward Simulation
- Connects to: P05 (Prospective/Triggers)

**Plan Monitoring**

- Monitors plan execution
- **ADVISORY** → Signals to P04

**Plan Assessment**

- Evaluates plan effectiveness
- **ADVISORY** → Signals to P04

**Flow**:

```
Plan Formation → Plan Monitoring → Plan Assessment
  ↓
All advisory signals → P04
```

### Conflict Resolution & Control

**Conflict Detection**

- Detects decision conflicts
- Input from: Metacognitive Performance Monitoring

**Conflict Arbitration**

- Resolves competing goals/actions

**Cognitive Control**

- Exerts top-down control
- Connects to: Emotion Regulation

**Flow**:

```
Conflict Detection → Conflict Arbitration → Cognitive Control
```

---

## 💖 Affect & Emotional Intelligence

### Purpose: Emotional processing, empathy, emotional memory

### Emotional Processing Core

**Emotion Recognition**

- Recognizes emotions in self/others
- Connects to: Memory-Enhanced Affect

**Emotion Generation**

- Generates emotional responses

**Emotion Regulation**

- Regulates emotional intensity
- Connects to: Metacognitive Regulation, Cognitive Control

**Flow**:

```
Emotion Recognition → Emotion Generation → Emotion Regulation
```

### Social Emotional Intelligence

**Empathy Systems**

- Emotional understanding of others
- Bidirectional with: Theory of Mind Emotions, Social Cooperation
- Connects to: Emotional Communication

**Emotional Communication**

- Communicates emotions effectively
- Bidirectional with: Empathy, Emotional Memory

**Emotional Memory**

- Emotion-tagged memory access
- Bidirectional with: Emotional Communication
- Connects to: Memory Backbone Intelligence Manager

**Bidirectional Flow**:

```
Empathy ↔ Emotional Communication ↔ Emotional Memory
```

---

## 🛡️ Intelligence Guards (Advisory Only)

### Purpose: Policy/QoS/Safety enforcement for advisory signals

**Intelligence Policy Guard** (`policy/intelligence_guard.py`)

- ABAC/consent/redaction enforcement (advisory context)
- Filters intelligence signals before P04

**Intelligence QoS Guard** (`retrieval/qos_gate.py`)

- Budget enforcement on planning/advice computation
- Connects to: P17 (QoS/Cost Governance)

**Intelligence Safety Monitor** (`policy/safety.py`)

- Harm/abuse heuristics on advisory content
- Connects to: P18 (Safety/Abuse)

**Guard Chain**:

```
Decision Recommendation | Action Coordination | Action Selection
  ↓
Intelligence Policy Guard
  ↓
Intelligence QoS Guard
  ↓
Intelligence Safety Monitor
  ↓
intelligence.advisory.* events
  ↓
P04 (Final Executor)
```

---

## 💾 Intelligence Storage & Events

### Specialized Storage

**Learning Store** (`ST_LEARNING`)

- Stores learning traces, feedback
- Input from: Learning Feedback

**Social Store** (`ST_SOCIAL`)

- Stores social relationships, norms
- Input from: Social Relationship Modeling

**Metacognitive Store** (`ST_METACOG`)

- Stores metacognitive assessments
- Input from: Metacognitive Performance Monitoring

**Procedural Store** (`ST_PROCEDURAL`)

- Stores procedural skills, habits
- Input from: Skill Acquisition

### Intelligence Events (`cognitive_trace_id` correlation)

**intelligence.learning.*** (`EV_LEARNING`)

- Learning system events
- Input from: Adaptive Controller

**intelligence.social.*** (`EV_SOCIAL`)

- Social cognition events
- Input from: Social Feedback

**intelligence.metacog.*** (`EV_METACOG`)

- Metacognitive events
- Input from: Metacognitive Reflection

**intelligence.decision.*** (`EV_DECISION`)

- Decision events
- Input from: Decision Recommendation

**Event Flow**:

```
EV_LEARNING | EV_SOCIAL | EV_METACOG | EV_DECISION
  ↓
intelligence.* (generic events)
  ↓
Intelligence Event Processor
  ↓
├─ intelligence.trace.* → Infrastructure (D4) observability
└─ intelligence.* → SSE ACL (sanitized for clients)
```

---

## 📡 Intelligence Topics & Pipeline Integration

### Intelligence Event Topics

**intelligence.***— Generic intelligence events
**intelligence.advisory.*** — Advisory signals to P04
**intelligence.trace.*** — Observability/tracing events

### Pipeline Connections

**TO P04 (Actions)** — Advisory signals ONLY

- Learning Coordinator → P04
- Metacognitive Reflection → P04
- Decision Recommendation → P04
- Dream Consolidation → P04
- Intelligence Event Processor → P04

**TO P05 (Prospective/Triggers)** — Advisory

- Metacognitive Planning → P05
- Plan Formation → P05

**TO P06 (Learning/Neuromod)** — Signals

- Adaptive Controller → P06

**TO P17 (QoS/Cost Governance)** — Budgets

- Intelligence Coordinator → P17

**TO P18 (Safety/Abuse)** — Policy hooks

- Intelligence Safety Monitor → P18

**FROM P19 (Personalization/Reco)** — Profiles

- P19 → Decision Evaluation
- P19 → Reward Valuation

**TO SSE** — Sanitized intelligence events

- intelligence.* → SSE ACL (filtered for clients)

**FROM Workspace** — Global Workspace broadcasts

- workspace.* → Memory Backbone Intelligence Manager
- workspace.* → Decision Recommendation

---

## 🔄 Intelligence Integration Flows

### Memory-Driven Learning Loop (Detailed)

```
Memory Backbone (experiences) → Learning Coordinator
  ↓
Predictive Learning (forecast outcomes)
  ↓
Adaptive Controller (adjust strategies)
  ↓
Learning Feedback (evaluate results)
  ↓
Specialized Learning:
  ├─ Procedural Learning → Habits/Skills
  ├─ Declarative Learning → Facts/Knowledge
  ├─ Reinforcement Learning → Rewards
  └─ Social Learning → Social Imitation → Theory of Mind
  ↓
Meta-Learning (learn to learn)
  ↓
Transfer Learning (generalize)
  ↓
Curiosity Learning (explore gaps)
  ↓
Loop back to Coordinator + Feed P06 (Learning/Neuromod)
```

### Social Cognition Flow (Detailed)

```
Memory Backbone (social experiences) → Theory of Mind
  ↓
Belief Attribution (understand beliefs)
  ↓
Intention Recognition (infer intentions)
  ↓
Emotion Attribution (recognize emotions)
  ↓
Knowledge Attribution (model knowledge)
  ↓
Social Reasoning:
  ├─ Social Norms (learn rules)
  ├─ Relationship Modeling (track dynamics)
  ├─ Communication Intent (understand messages)
  └─ Cooperation/Competition (social strategies)
  ↓
Social Learning:
  ├─ Imitation Learning (copy behaviors)
  ├─ Social Feedback (improve)
  └─ Perspective Switching (empathy)
  ↓
Social Store + intelligence.social.* events
```

### Decision & Arbitration Flow (Advisory)

```
Memory Backbone + Cognitive Core → Option Generation
  ↓
Option Evaluation (multi-criteria):
  ├─ Reward Valuation (worth)
  ├─ Metacognitive Confidence (certainty)
  ├─ Theory of Mind (social context)
  ├─ Forward Simulation (outcomes)
  └─ P19 Personalization (preferences)
  ↓
Decision Recommendation (best option)
  ↓
Intelligence Guards:
  ├─ Policy Guard (ABAC/consent)
  ├─ QoS Guard (budget)
  └─ Safety Monitor (harm detection)
  ↓
intelligence.advisory.* events
  ↓
P04 (Final Decision & Execution)
```

### Metacognitive Monitoring Flow

```
Cognitive Core (working memory, attention) → Metacognition
  ↓
Monitoring:
  ├─ Confidence Assessment (certainty)
  ├─ Performance Monitoring (success/error)
  ├─ Knowledge Assessment (known/unknown)
  └─ Strategy Monitoring (effectiveness)
  ↓
Control:
  ├─ Cognitive Regulation (resource allocation)
  ├─ Metacognitive Planning (strategy planning)
  └─ Reflective Processing (self-reflection)
  ↓
Self-Model:
  ├─ Self-Concept (identity)
  ├─ Self-Efficacy (capability beliefs)
  └─ Self-Awareness (conscious knowledge)
  ↓
Metacognitive Store + intelligence.metacog.* events
```

### Reward & Motivation Flow

```
Memory Backbone (experiences) → Reward Prediction
  ↓
Prediction Error (actual - predicted)
  ↓
Value Assessment (option worth)
  ↓
Motivational Systems (drives):
  ├─ Homeostatic Drives
  ├─ Curiosity Drive
  ├─ Achievement Drive
  └─ Social Drive
  ↓
Incentive Processing:
  ├─ Incentive Salience ("wanting")
  ├─ Incentive Learning (what to want)
  └─ Motivation Regulation (balance)
  ↓
Connects to: Decision Evaluation, Reinforcement Learning
```

### Imagination & Simulation Flow

```
Memory Backbone (episodic memories) → Simulation Engine
  ↓
Mental Simulation:
  ├─ Forward Simulation (future scenarios)
  ├─ Counterfactual Thinking (alternatives)
  └─ Episodic Simulation (reconstructed events)
  ↓
Creative Processes:
  ├─ Divergent Thinking (many solutions)
  ├─ Convergent Thinking (best solution)
  └─ Insight Generation (breakthroughs)
  ↓
Dreaming (offline):
  ├─ Memory Consolidation (strengthen)
  ├─ Explorative Dreaming (explore)
  └─ Mental Rehearsal (practice)
  ↓
Outputs to: Decision Evaluation, Plan Formation, P04 (advisory)
```

---

## 🧠 Memory Backbone Connections (Diagram 3 → Diagrams 1 & 2)

### FROM Memory Backbone (D1)

- Intelligence Coordinator ← Memory experiences
- Learning Coordinator ← Memory patterns
- Action Goals ← Memory context

### FROM Cognitive Core (D2)

- Metacognitive Confidence ← Working Memory, Attention state
- Theory of Mind Beliefs ← Global Workspace, Social context

### TO Memory Backbone (D1)

- Intelligence insights (social knowledge, learning traces)
- Learning updates (adaptive strategies)
- Social knowledge (relationships, norms)

### TO P04 Actions (D4 — Infrastructure)

**Advisory signals ONLY** (never direct execution):

- Learning Coordinator → P04
- Metacognitive Reflection → P04
- Decision Recommendation → P04
- Dream Consolidation → P04
- Intelligence Event Processor → P04

### TO Infrastructure (D4)

- Intelligence metrics (performance, learning rates)
- Learning traces (observability)
- Social analytics (relationship graphs)
- `intelligence.trace.*` events → Observability stack

---

## 📊 Cross-Diagram Integration Summary

### Diagram 1 (API & Pipeline) Connections

- P04 (Arbitration/Action) ← Advisory signals from ALL intelligence systems
- P05 (Prospective/Triggers) ← Metacognitive Planning, Plan Formation
- P06 (Learning/Neuromod) ← Adaptive Controller
- P17 (QoS/Cost) ← Intelligence Coordinator budgets
- P18 (Safety/Abuse) ← Intelligence Safety Monitor
- P19 (Personalization) → Decision Evaluation, Reward Valuation
- SSE ACL ← `intelligence.*` events (sanitized)

### Diagram 2 (Cognitive Core) Connections

- Working Memory → Metacognitive Confidence
- Global Workspace → Decision Recommendation, Memory Intelligence Manager
- Affect State → Emotion Recognition, Empathy
- Hippocampus → Emotional Memory
- Attention Gate → Theory of Mind processing

### Key Integration Principles

1. **Memory-Driven**: All intelligence FROM Memory Backbone
2. **Advisory Only**: Intelligence signals → P04 (sole executor)
3. **Event Correlation**: All events carry `cognitive_trace_id`
4. **Family-Aware**: Family relationships in social cognition
5. **Cross-Device**: Intelligence coordination across family devices

---

---

## 🏗️ DIAGRAM 4: INFRASTRUCTURE — MEMORY BACKBONE RUNTIME FOUNDATION

### Overview: Infrastructure Support FOR Memory Backbone Operations

**Purpose**: Runtime infrastructure that **serves Memory Backbone operations** — consolidation, storage, sync, security, observability.

All infrastructure systems provide **foundational support FOR Memory operations** across devices and cognitive systems.

---

## 🧠 Memory Backbone Infrastructure Connections

### FROM Memory Backbone (D1)

- Memory operations requiring infrastructure support
- Memory metrics & traces
- Memory security policies

### FROM Cognitive Core (D2)

- Working memory consolidation
- Attention state persistence
- Cognitive processes requiring infrastructure

### FROM Intelligence Systems (D3)

- Learning traces
- Social analytics
- Decision records

### TO Memory Backbone (D1)

- Consolidated memories
- Knowledge graphs
- Performance insights

### TO Production Deployment

- Memory-powered Family AI deployment
- Cross-device Memory sync
- Family Memory coordination

---

## 🌙 Memory Backbone Consolidation & Replay

### Purpose: Memory strengthening, sleep-like consolidation, replay coordination

### Memory-Driven Sleep Coordination

**Memory Sleep Scheduler** — Consolidation timing

- Memory-driven consolidation scheduling
- Memory load-based sleep triggers
- Memory optimization timing
- **SERVES**: Memory Backbone consolidation timing

**Memory Sleep State Machine** — Sleep cycle management

- Memory consolidation state management
- **SERVES**: Memory Backbone sleep cycles
- Output to: Production Deployment

**Memory Sleep Triggers** — Optimization initiation

- Memory-based consolidation initiation
- **SERVES**: Memory Backbone optimization triggers

**Flow**:

```
Memory Sleep Scheduler → Memory Sleep State Machine
  ↓
Memory Sleep Triggers → loop back to Scheduler
  ↓
State Machine triggers consolidation processes
```

### Memory Backbone Consolidation Processes

**Memory Hippocampal Replay**

- **MEMORY BACKBONE HIPPOCAMPAL REPLAY**:
  - Memory pattern replay FOR Memory strengthening
  - Memory sequence consolidation
  - Memory importance weighting
- **SERVES**: Memory Backbone strengthening
- Connects to: Memory Episodic Consolidation, Knowledge Graph Temporal Engine
- Input from: Memory Backbone, Sleep State Machine

**Memory Neocortical Integration**

- Memory integration INTO long-term knowledge
- **SERVES**: Memory Backbone knowledge integration
- Connects to: Memory Semantic Consolidation, Knowledge Graph Concept Evolution
- Input from: Cognitive Core, Sleep State Machine

**Memory Synaptic Homeostasis**

- Memory connection optimization
- **SERVES**: Memory Backbone connection health
- Connects to: Memory Procedural Consolidation, Memory Emotional Consolidation

**Flow**:

```
Sleep State Machine → Consolidation Processes
  ├─ Hippocampal Replay (pattern strengthening)
  ├─ Neocortical Integration (knowledge formation)
  └─ Synaptic Homeostasis (connection optimization)
```

### Memory Backbone Consolidation Types

**Memory Episodic Consolidation**

- Episode consolidation FOR Memory Backbone
- **SERVES**: Memory Backbone episodes
- Output to: `st_episodic`, Causal Indexing events, P03, Memory Backbone

**Memory Semantic Consolidation**

- Knowledge consolidation INTO Memory Backbone
- **SERVES**: Memory Backbone knowledge
- Output to: `st_semantic`, Knowledge Graph Relation Discovery, P03, Memory Backbone

**Memory Procedural Consolidation**

- Skill consolidation THROUGH Memory Backbone
- **SERVES**: Memory Backbone skills
- Output to: `st_semantic`, ML Continual Learning, Memory Backbone

**Memory Emotional Consolidation**

- Emotional memory strengthening IN Memory Backbone
- Family emotional memories
- **SERVES**: Memory Backbone emotional intelligence
- Output to: Policy Dynamic Consent, Memory Backbone

**Flow**:

```
Consolidation Processes → Consolidation Types
  ├─ Episodic (episodes) → st_episodic
  ├─ Semantic (knowledge) → st_semantic
  ├─ Procedural (skills) → st_semantic
  └─ Emotional (feelings) → Policy Dynamic Consent
  ↓
All outputs → Memory Backbone (D1)
```

### Memory-Enhanced Legacy Consolidation

**Memory Consolidation Compactor**

- Memory-driven compaction FOR Memory Backbone
- **SERVES**: Memory Backbone optimization

**Memory Consolidation Rollups**

- Memory summary generation FOR Memory Backbone
- **SERVES**: Memory Backbone summaries
- Connects to: P15 (Rollups/Summaries)

**Memory Consolidation Replay**

- Memory replay coordination FOR Memory Backbone
- **SERVES**: Memory Backbone replay

**Pipeline Connections**:

- P03 (Consolidation/Forgetting) — Primary consolidation pipeline
- P15 (Rollups/Summaries) — Summary generation

**Event Topics**:

- `infra.consolidation.*` — Consolidation events with `cognitive_trace_id`

---

## 🕸️ Temporal Knowledge Graph & Reasoning

### Purpose: Semantic knowledge representation, temporal reasoning, causal analysis

**Temporal Reasoning Engine** — Core temporal reasoning

- Time-aware knowledge graph queries
- Temporal consistency enforcement
- Input from: Memory Backbone, Cognitive Core

**Knowledge Versioning** — Version control for knowledge

- Tracks knowledge evolution over time
- Bidirectional with: Temporal Reasoning Engine, Causal Graph

**Causal Graph** — Cause-effect relationships

- Models causal relationships in knowledge
- Bidirectional with: Knowledge Versioning
- Connects to: Prospective Cue Monitoring, Observability Causal Analysis

**Concept Evolution** — Concept tracking over time

- Tracks how concepts change
- Connects to: Relation Discovery
- Input from: Neocortical Integration, Cognitive Core

**Relation Discovery** — Discovers new relationships

- Automatically finds new knowledge connections
- Connects to: Inconsistency Resolution
- Input from: Semantic Consolidation, Intelligence Systems

**Inconsistency Resolution** — Resolves knowledge conflicts

- Handles contradictory knowledge

**Sensory Grounding** — Links knowledge to sensory experiences

- Bidirectional with: Linguistic Mapping

**Linguistic Mapping** — Maps language to knowledge

- Bidirectional with: Sensory Grounding, Procedural Linking

**Procedural Linking** — Links knowledge to procedures

- Bidirectional with: Linguistic Mapping

**Legacy Components**:

- `kg/temporal.py` — Temporal knowledge graph implementation
- `consolidation/kg_jobs.py` — Knowledge graph consolidation jobs
- `st_kg` — Knowledge graph storage

**Flow**:

```
Temporal Reasoning Engine ↔ Knowledge Versioning ↔ Causal Graph
  ↓
Concept Evolution → Relation Discovery → Inconsistency Resolution
  ↓
Sensory Grounding ↔ Linguistic Mapping ↔ Procedural Linking
  ↓
st_kg (storage)
```

**Pipeline Connections**:

- Consolidation processes → Knowledge Graph updates
- Knowledge Graph → Memory Backbone (D1)

**Event Topics**:

- `infra.kg.*` — Knowledge graph events with `cognitive_trace_id`

---

## 🔮 Prospective Memory State Machine

### Purpose: Future intentions, reminders, time/event/activity-based triggers

**Brain Analog**: Prefrontal cortex (future planning), hippocampus (episodic future thinking)

### Prospective Memory Core

**Intention Formation** — Creates future intentions

- Forms prospective memory intentions
- Input from: Intelligence Systems, Memory Backbone

**Cue Monitoring** — Watches for trigger conditions

- Monitors time/events/activities for triggers
- Input from: Knowledge Graph Causal Graph

**Retrieval Engine** — Retrieves intentions when triggered

- Activates intentions at the right moment

**Execution Control** — Controls intention execution

- Manages intention execution timing
- Output to: Pattern Storage events, Observability Behavioral Analytics
- Connects to: P05 (Prospective/Triggers), Memory Backbone

**Flow**:

```
Intention Formation → Cue Monitoring → Retrieval Engine → Execution Control
```

### Prospective Memory Types

**Time-Based** — Scheduled intentions (e.g., "at 3pm")

- Input from: Knowledge Graph Temporal Engine

**Event-Based** — Triggered by events (e.g., "when I see John")

**Activity-Based** — Triggered by activities (e.g., "when I'm at the store")

**All types feed into**: Priority Manager

### Prospective Memory Management

**Priority Manager** — Manages intention priorities

- Balances competing intentions

**Interference Control** — Prevents intention interference

- Ensures intentions don't conflict

**Forgetting Prevention** — Prevents intention loss

- Ensures important intentions aren't forgotten

**Flow**:

```
Time-Based | Event-Based | Activity-Based → Priority Manager
  ↓
Interference Control → Forgetting Prevention
```

**Legacy Components**:

- `prospective/engine.py` — Prospective memory engine
- `prospective/scheduler.py` — Prospective memory scheduler
- `prospective/state_machine.py` — Prospective memory state machine

**Pipeline Connections**:

- P05 (Prospective/Triggers) — Primary prospective memory pipeline
- P20 (Procedures/Habits) — Routine-based prospective memory
- Intelligence Systems (D3) → Intention Formation

**Event Topics**:

- `infra.prospective.*` — Prospective memory events with `cognitive_trace_id`

---

## 🌐 Edge Computing & P2P Sync

### Purpose: Cross-device sync, conflict resolution, distributed coordination

**Cognitive Sync Router** — Intelligent sync routing

- Routes sync operations across devices
- Bidirectional with: Conflict Resolution, Adaptive Strategy
- Input from: Memory Backbone, Cognitive Core

**Conflict Resolution** — Resolves sync conflicts

- CRDT-based conflict resolution
- Bidirectional with: Cognitive Sync Router, Adaptive Strategy
- Input from: MLS Band Control (security)

**Adaptive Strategy** — Adapts sync strategy

- Learns optimal sync patterns
- Bidirectional with: Cognitive Sync Router, Conflict Resolution
- Input from: Observability Cognitive Metrics

**Edge Cognitive Cache** — Device-local caching

- Caches frequently accessed data
- Connects to: Federated Learning

**Federated Learning** — Cross-device learning

- Learns from distributed data without centralization
- Connects to: Offline Intelligence

**Offline Intelligence** — Offline operation capability

- Enables AI operation without connectivity

**Flow**:

```
Cognitive Sync Router ↔ Conflict Resolution ↔ Adaptive Strategy
  ↓
Edge Cognitive Cache → Federated Learning → Offline Intelligence
```

**Legacy Components**:

- `sync/sync_manager.py` — Sync manager
- `sync/replicator.py` — Replication engine
- `sync/crdt.py` — CRDT implementation

**Pipeline Connections**:

- P07 (Sync/CRDT) — Primary sync pipeline
- Cross-device Memory coordination

**Event Topics**:

- `infra.sync.*` — Sync events with `cognitive_trace_id`

---

## 🤖 Machine Learning & Adaptation

### Purpose: ML model training, adaptation, continual learning

**Continual Learning** — Continuous model updates

- Learns from new experiences without forgetting
- Input from: Memory Backbone, Procedural Consolidation, Intelligence Systems

**Meta-Learning** — Learning to learn

- Learns optimal learning strategies
- Input from: Cognitive Core

**Self-Supervised** — Learns without labels

- Discovers patterns autonomously

**User Modeling** — Models user preferences

- Builds personalized user models
- Output to: `st_ml_artifacts`, Memory Backbone, Policy Dynamic Consent

**Contextual Adaptation** — Context-aware adaptation

- Adapts to changing contexts
- Output to: Memory Backbone

**Feedback Learning** — Learns from feedback

- Incorporates user/system feedback

**Flow**:

```
Continual Learning → Meta-Learning → Self-Supervised
  ↓
User Modeling → Contextual Adaptation → Feedback Learning
```

**Legacy Components**:

- `ml_capsule/runs/runner.py` — ML run executor
- `ml_capsule/stress/harness.py` — Stress testing harness
- `ml_capsule/models/registry.py` — Model registry
- `st_ml_artifacts` — ML artifact storage

**Pipeline Connections**:

- P19 (Personalization/Reco) — Personalization via User Modeling
- P06 (Learning/Neuromod) — Learning coordination
- Observability → ML training feedback

**Event Topics**:

- `infra.ml.*` — ML events with `cognitive_trace_id`

---

## 🛡️ Security & Safety

### Purpose: Threat detection, encryption, zero-trust enforcement, MLS classification

### Security Core

**Threat Detection** — Identifies security threats

- Monitors for malicious behavior

**Adaptive Defense** — Adapts security measures

- Responds to detected threats dynamically
- Connects to: Observability Anomaly Detection

**Zero Trust** — Zero-trust security model

- Never trust, always verify

**Flow**:

```
Threat Detection → Adaptive Defense (with Zero Trust principles)
```

### Multi-Level Security (MLS)

**Classification** — Data classification

- Assigns security levels to data

**Enforcement** — Policy enforcement

- Enforces security policies
- Connects to: Security events

**Band Control** — Privacy band management

- Manages privacy bands (GREEN, YELLOW, ORANGE, RED)
- Connects to: Sync Conflict Resolution

**Flow**:

```
Classification → Enforcement → Band Control
```

### End-to-End Encryption (E2EE)

**Key Management** — Cryptographic key management

- Manages encryption keys
- Input from: HSM/TEE Attestation, Ratchet Service

**MLS Groups** — Messaging Layer Security groups

- Manages encrypted group communication

**Selective Sharing** — Controlled data sharing

- Fine-grained sharing controls

**Flow**:

```
Key Management → MLS Groups → Selective Sharing
```

**Supporting Services**:

- **HSM/TEE Attestation** — Hardware security module attestation
- **Ratchet Service** — Forward secrecy via ratcheting

**Legacy Components**:

- `security/key_manager.py` — Key manager
- `security/encryptor.py` — Encryption service
- `security/mls_group.py` — MLS group manager

**Pipeline Connections**:

- P12 (Device/E2EE) — Device encryption and key management
- P18 (Safety/Abuse) — Safety enforcement
- Security events → Observability

**Event Topics**:

- `infra.security.*` — Security events with `cognitive_trace_id`

---

## ⚖️ Policy, PII Minimization & Governance

### Purpose: Policy enforcement, PII detection/redaction, compliance tracking

### Policy Core

**Policy Rules Engine** — Policy evaluation

- Evaluates policy rules
- Input from: Intelligence Systems

**Compliance Tracking** — Compliance monitoring

- Tracks regulatory compliance

**Policy Decision Cache** — Caches policy decisions

- Optimizes repeated policy evaluations

**Dynamic Consent** — User consent management

- Manages user consent dynamically
- Input from: Emotional Consolidation, User Modeling

**Privacy Budget** — Privacy budget tracking

- Tracks privacy expenditure

**Data Minimization** — Minimizes data collection

- Reduces data footprint

**Flow**:

```
Policy Rules Engine → Compliance Tracking → Policy Decision Cache
  ↓
Dynamic Consent → Privacy Budget → Data Minimization
```

### P10 Concrete Implementation

**PII Minimizer Service** — PII detection and minimization

- Detects and redacts PII
- Connects to: PII Schema Registry, `st_pii_map`

**PII Schema Registry** — PII pattern definitions

- Registry of PII patterns

**Redaction Coordinator** — Coordinates redaction

- Manages redaction across systems
- Output to: `st_redaction_log`

**Flow**:

```
PII Minimizer → PII Schema Registry
  ↓
PII Minimizer → st_pii_map
  ↓
Redaction Coordinator → st_redaction_log
```

**Pipeline Connections**:

- P10 (PII/Minimization) — PII detection and redaction
- P11 (DSAR/GDPR) — Data subject access requests
- Privacy events → SSE ACL

**Event Topics**:

- `privacy.*` — Privacy events with `cognitive_trace_id`

---

## 🔭 Memory Backbone Observability & Intelligence Monitoring

### Purpose: Cognitive metrics, distributed tracing, behavioral analytics, predictive insights

### Memory Backbone Cognitive Metrics

**Memory Cognitive Metrics**

- **MEMORY BACKBONE COGNITIVE MONITORING**:
  - Memory operation performance tracking
  - Memory formation & retrieval metrics
  - Memory quality & accuracy measurements
- **MONITORS**: Memory Backbone cognitive health

**Memory Backbone Analytics**

- Memory analytics FOR Memory optimization
- **MONITORS**: Memory Backbone performance
- Output to: ML Continual Learning, Memory Backbone

**Memory Intelligence Dashboard**

- Intelligence metrics FROM Memory operations
- **MONITORS**: Memory Backbone intelligence
- Output to: Production Deployment, Intelligence Systems
- Input from: `st_receipts`, Intelligence Systems

**Flow**:

```
Memory Cognitive Metrics → Memory Backbone Analytics
  ↓
Memory Intelligence Dashboard
```

### Memory Backbone Distributed Monitoring

**Memory Distributed Tracing**

- Memory operation tracing ACROSS Memory Backbone
- Cross-device Memory coordination tracking
- **MONITORS**: Memory Backbone distribution
- Output to: Memory Backbone

**Memory Adaptive Sampling**

- Memory-aware sampling FOR Memory insights
- **MONITORS**: Memory Backbone sampling

**Memory Anomaly Detection**

- Memory operation anomaly detection
- **MONITORS**: Memory Backbone health
- Input from: Adaptive Defense (security)

**Flow**:

```
Memory Distributed Tracing → Memory Adaptive Sampling → Memory Anomaly Detection
```

### Memory Backbone Behavioral Analytics

**Memory Behavioral Analytics**

- Memory usage pattern analysis
- Family Memory behavior insights
- **MONITORS**: Memory Backbone usage patterns
- Input from: Prospective Execution Control, Memory Backbone
- Output to: Memory Backbone

**Memory Causal Analysis**

- Memory relationship causality analysis
- **MONITORS**: Memory Backbone relationships
- Input from: Knowledge Graph Causal Graph

**Memory Predictive Insights**

- Memory-driven predictive analytics
- **MONITORS**: Memory Backbone predictions
- Output to: Memory Backbone, Intelligence Systems

**Flow**:

```
Memory Behavioral Analytics → Memory Causal Analysis → Memory Predictive Insights
```

### Memory Observability Infrastructure

**Memory Metric Sink**

- Memory metrics aggregation FOR Memory Backbone
- **SERVES**: Memory Backbone metrics
- Output to: Memory Backbone

**Pipeline Connections**:

- P17 (QoS/Cost Governance) — Cost tracking and governance
- All pipelines → Observability metrics
- Observability → Memory Backbone insights

**Event Topics**:

- `infra.observability.*` — Observability events with `cognitive_trace_id`

---

## 🧠 Embeddings & Indexes (P08/P13)

### Purpose: Vector embeddings, index building, reindexing

**Embedding Orchestrator** — Coordinates embedding generation

- Orchestrates embedding workflows
- Connects to: P08 (Embedding Lifecycle)

**Embedding Builder** — Generates embeddings

- Creates vector embeddings
- Output to: `st_vector`

**Vector Index Builder** — Builds vector indexes

- Creates searchable vector indexes
- Output to: `st_vector`

**FTS Indexer Service** — Full-text search indexing

- Builds full-text search indexes
- Output to: `st_fts`

**Reindex Scheduler** — Schedules reindexing

- Schedules index rebuilds
- Connects to: P13 (Index Rebuild)

**Reindex Worker** — Executes reindexing

- Rebuilds indexes
- Output to: `st_vector`, `st_fts`

**Flow**:

```
Embedding Orchestrator → Embedding Builder → st_vector
  ↓
Vector Index Builder → st_vector
  ↓
FTS Indexer Service → st_fts
  ↓
Reindex Scheduler → Reindex Worker → st_vector, st_fts
```

**Pipeline Connections**:

- P08 (Embedding Lifecycle) — Embedding generation and management
- P13 (Index Rebuild) — Index rebuilding and maintenance

**Event Topics**:

- `infra.ml.*` — ML/embedding events

---

## 🔌 Connector Infrastructure (P09)

### Purpose: External connector integration, OAuth, webhooks

**Connector Registry** — Registered connectors

- Storage: `st_connectors`

**OAuth Vault** — OAuth token storage

- Storage: `st_oauth_vault`

**Webhook Ingest** — Webhook receiver

- Receives external webhook events
- Connects to: Connector Registry

**Token Rotator** — Rotates OAuth tokens

- Manages token lifecycle
- Connects to: OAuth Vault

**Flow**:

```
Webhook Ingest → Connector Registry
Token Rotator → OAuth Vault
```

**Pipeline Connections**:

- P09 (Connector Ingestion) — External data ingestion

---

## 🗓️ Workflows & Backup/Restore

### Purpose: Workflow orchestration, snapshot management, disaster recovery

**Workflow Engine** — Executes workflows

- Orchestrates multi-step workflows

**Workflow Scheduler** — Schedules workflows

- Triggers workflows on schedule
- Connects to: Workflow Engine

**Backup Scheduler** — Schedules backups

- Triggers backup operations

**Snapshot Manager** — Creates snapshots

- Creates point-in-time snapshots
- Storage: `st_snapshots`

**Restore Manager** — Restores from snapshots

- Recovers from backups
- Input from: `st_snapshots`

**Flow**:

```
Workflow Scheduler → Workflow Engine
Backup Scheduler → Snapshot Manager → st_snapshots
Restore Manager → st_snapshots
```

**Pipeline Connections**:

- P13 (Index Rebuild) — Workflow-based index rebuilding

---

## 🧯 Safety & Abuse Operations

### Purpose: Safety enforcement, abuse detection, content flagging

**Safety Queue** — Safety processing queue

- Queues content for safety checks

**Safety Worker** — Processes safety checks

- Executes safety policies

**Flagged Store** — Flagged content storage

- Storage: `st_flagged_content`

**Flow**:

```
Safety Queue → Safety Worker → st_flagged_content
```

**Pipeline Connections**:

- P18 (Safety/Abuse) — Safety and abuse detection

---

## 📡 Events Bus & Internals

### Purpose: Event routing, persistence, durability, schema validation

**Events Bus** — Central event bus

- Core message broker

**Schema Validation** — Validates event schemas

- Ensures event structure correctness
- Connects to: Event Persistence

**Event Persistence** — Persists events

- Write-Ahead Log (WAL) + Consumer offsets
- Storage: `st_wal`, `st_offsets`
- Bidirectional with: Event Dispatcher

**Event Dispatcher** — Routes events to consumers

- Bidirectional with: Event Persistence, Event Subscriptions, Event Middleware

**Event Subscriptions** — Manages subscriptions

- Bidirectional with: Event Dispatcher

**Event Middleware** — Event interceptors

- Bidirectional with: Event Dispatcher

**Outbox Drainer** — Reliable event publishing

- Drains `st_outbox` to Event Bus
- Input from: `st_outbox`

**DLQ Replayer** — Replays failed events

- Recovers from Dead Letter Queue
- Bidirectional with: `st_dlq`

**Flow**:

```
Schema Validation → Event Persistence (WAL/offsets)
  ↓
Event Dispatcher ↔ Event Subscriptions
  ↓
Event Dispatcher ↔ Event Middleware
  ↓
Outbox Drainer (st_outbox) → Events Bus
  ↓
DLQ Replayer (st_dlq) → Events Bus
```

**Event Topics**:

- `infra.*` — Infrastructure events
- `privacy.*` — Privacy events
- `infra.consolidation.*` — Consolidation events
- `infra.kg.*` — Knowledge graph events
- `infra.prospective.*` — Prospective memory events
- `infra.sync.*` — Sync events
- `infra.security.*` — Security events
- `infra.observability.*` — Observability events
- `infra.ml.*` — ML/embedding events

**All topics carry**: `cognitive_trace_id` for correlation

**Helper Systems**:

- `events.semantic_filters` — Semantic event filtering
- `events.causal_indexing` — Causal event indexing
- `events.pattern_storage` — Event pattern storage

---

## 💾 Core Storage & Durability

### Purpose: Persistent storage for all system components

**Storage Systems**:

- **st_episodic** — Episodic memory storage
- **st_semantic** — Semantic memory storage
- **st_vector** — Vector embedding storage
- **st_fts** — Full-text search index storage
- **st_blob** — Binary large object storage
- **st_kg** — Knowledge graph storage
- **st_receipts** — Receipt storage (proof of operations)
- **st_outbox** — Outbox pattern storage (transactional events)
- **st_wal** — Write-Ahead Log (event durability)
- **st_offsets** — Consumer offset tracking
- **st_dlq** — Dead Letter Queue (failed events)
- **st_snapshots** — Snapshot storage (backups)
- **st_pii_map** — PII mapping storage
- **st_redaction_log** — Redaction log storage
- **st_regs** — Registry storage (tools, prompts, agents)
- **st_ml_artifacts** — ML model/artifact storage
- **st_connectors** — Connector registry storage
- **st_oauth_vault** — OAuth token storage
- **st_flagged_content** — Safety-flagged content storage

**All storage systems support**:

- ACID transactions (via UnitOfWork)
- SQLite local storage
- E2EE at rest
- Cross-device sync (CRDT-based)

---

## 📇 Registries

### Purpose: Tool, prompt, and agent registration

**Tool Registry** (`registry/tools`)

- Registers available tools
- Storage: `st_regs`
- Input from: Memory Backbone

**Prompt Registry** (`registry/prompts`)

- Registers prompt templates
- Storage: `st_regs`
- Input from: Memory Backbone

**Agent Registry** (`registry/agents`)

- Registers AI agents
- Storage: `st_regs`
- Input from: Memory Backbone

---

## 🔄 Infrastructure Integration Flows

### Consolidation Flow (Detailed)

```
Memory Backbone (experiences) → Memory Sleep Scheduler
  ↓
Sleep State Machine (manages sleep cycles)
  ↓
Sleep Triggers (initiates consolidation)
  ↓
Consolidation Processes:
  ├─ Hippocampal Replay (pattern strengthening)
  ├─ Neocortical Integration (knowledge formation)
  └─ Synaptic Homeostasis (connection optimization)
  ↓
Consolidation Types:
  ├─ Episodic (episodes) → st_episodic
  ├─ Semantic (knowledge) → st_semantic
  ├─ Procedural (skills) → st_semantic
  └─ Emotional (feelings) → Policy Dynamic Consent
  ↓
Knowledge Graph Updates:
  ├─ Temporal Engine (time-aware knowledge)
  ├─ Concept Evolution (concept tracking)
  └─ Relation Discovery (new connections)
  ↓
Output to: Memory Backbone (D1), P03 (pipeline)
```

### Knowledge Graph Flow (Detailed)

```
Consolidation Processes → Knowledge Graph
  ↓
Temporal Reasoning Engine ↔ Knowledge Versioning ↔ Causal Graph
  ↓
Concept Evolution (tracks changes)
  ↓
Relation Discovery (finds connections)
  ↓
Inconsistency Resolution (resolves conflicts)
  ↓
Multimodal Grounding:
  ├─ Sensory Grounding (links to senses)
  ├─ Linguistic Mapping (links to language)
  └─ Procedural Linking (links to procedures)
  ↓
Storage: st_kg
  ↓
Outputs to: Prospective Cue Monitoring, Observability Causal Analysis, Memory Backbone
```

### Prospective Memory Flow (Detailed)

```
Intelligence Systems (goals) → Intention Formation
  ↓
Cue Monitoring (watches for triggers)
  ├─ Time-Based (scheduled)
  ├─ Event-Based (event-triggered)
  └─ Activity-Based (activity-triggered)
  ↓
Priority Manager (balances intentions)
  ↓
Interference Control (prevents conflicts)
  ↓
Forgetting Prevention (ensures retention)
  ↓
Retrieval Engine (activates intentions)
  ↓
Execution Control (executes intentions)
  ↓
Outputs to: Pattern Storage events, Behavioral Analytics, P05, P20, Memory Backbone
```

### Sync Flow (Detailed)

```
Memory Backbone (cross-device) → Cognitive Sync Router
  ↓
Conflict Resolution (CRDT-based)
  ↓
Adaptive Strategy (learns optimal patterns)
  ↓
Edge Cognitive Cache (device-local caching)
  ↓
Federated Learning (cross-device learning)
  ↓
Offline Intelligence (offline operation)
  ↓
Outputs to: P07 (Sync/CRDT)
```

### Observability Flow (Detailed)

```
Memory Backbone operations → Memory Cognitive Metrics
  ↓
Memory Backbone Analytics (optimization insights)
  ↓
Memory Intelligence Dashboard (intelligence metrics)
  ↓
Distributed Monitoring:
  ├─ Distributed Tracing (cross-device tracking)
  ├─ Adaptive Sampling (intelligent sampling)
  └─ Anomaly Detection (health monitoring)
  ↓
Behavioral Analytics:
  ├─ Behavioral Analytics (usage patterns)
  ├─ Causal Analysis (relationship causality)
  └─ Predictive Insights (forecasting)
  ↓
Memory Metric Sink (aggregation)
  ↓
Outputs to: Memory Backbone, Intelligence Systems, Production Deployment, P17
```

### ML & Adaptation Flow (Detailed)

```
Memory Backbone (experiences) → Continual Learning
  ↓
Meta-Learning (learning to learn)
  ↓
Self-Supervised (pattern discovery)
  ↓
User Modeling (preference learning) → st_ml_artifacts
  ↓
Contextual Adaptation (context-aware)
  ↓
Feedback Learning (incorporates feedback)
  ↓
Outputs to: Memory Backbone, P19 (Personalization), Policy Dynamic Consent
```

### Security Flow (Detailed)

```
Threat Detection (monitors threats)
  ↓
Adaptive Defense (responds to threats)
  ↓
MLS Classification → MLS Enforcement → MLS Band Control
  ↓
E2EE Key Management (HSM/TEE + Ratchet)
  ↓
MLS Groups (encrypted communication)
  ↓
Selective Sharing (controlled access)
  ↓
Outputs to: P12 (Device/E2EE), P18 (Safety/Abuse), Security events
```

### Policy & Privacy Flow (Detailed)

```
Intelligence Systems → Policy Rules Engine
  ↓
Compliance Tracking → Policy Decision Cache
  ↓
Dynamic Consent (user consent management)
  ↓
Privacy Budget → Data Minimization
  ↓
P10 Implementation:
  ├─ PII Minimizer → PII Schema Registry
  ├─ PII Minimizer → st_pii_map
  └─ Redaction Coordinator → st_redaction_log
  ↓
Outputs to: P10 (PII/Minimization), P11 (DSAR/GDPR), Privacy events
```

---

## 🔗 Pipeline Hand-Offs (Infrastructure → Pipelines)

**P03 (Consolidation/Forgetting)**:

- Memory Backbone Consolidation (all types)
- Memory Consolidation Rollups

**P05 (Prospective/Triggers)**:

- Prospective Memory (all components)
- Knowledge Graph Temporal Engine

**P07 (Sync/CRDT)**:

- Edge Sync, CRDT implementation

**P08 (Embedding Lifecycle)**:

- Embedding Orchestrator, Builder

**P09 (Connector Ingestion)**:

- Connector Infrastructure

**P10 (PII/Minimization)**:

- Policy Governance (PII Minimizer)

**P11 (DSAR/GDPR)**:

- Policy Governance (Compliance Tracking)

**P12 (Device/E2EE)**:

- Security & Safety (E2EE, MLS)

**P13 (Index Rebuild)**:

- Embedding Lifecycle (Reindex Scheduler/Worker)
- Workflows & Backup

**P14 (Near-Duplicate/Canon)**:

- (Implicit: Consolidation handles deduplication)

**P15 (Rollups/Summaries)**:

- Memory Consolidation Rollups

**P16 (Feature Flags/A-B)**:

- Registries (Tool/Prompt/Agent)

**P17 (QoS/Cost Governance)**:

- Memory Backbone Observability

**P18 (Safety/Abuse)**:

- Security & Safety
- Safety & Abuse Operations

**P19 (Personalization/Reco)**:

- ML Adaptation (User Modeling)

**P20 (Procedures/Habits)**:

- Prospective Memory (Activity-Based)

---

## 📊 Cross-Diagram Integration Summary

### FROM Diagram 1 (API & Pipeline)

- P03-P20 pipelines consume infrastructure services
- SSE ACL streams `infra.*` and `privacy.*` events (sanitized)

### FROM Diagram 2 (Cognitive Core)

- Working Memory → Consolidation (Neocortical Integration)
- Hippocampus → Consolidation (Hippocampal Replay)
- Attention State → Sync (Cognitive Sync Router)
- Global Workspace → Knowledge Graph (Concept Evolution)

### FROM Diagram 3 (Intelligence Systems)

- Learning traces → ML Adaptation
- Social analytics → Observability
- Decision records → Knowledge Graph
- Intelligence metrics → Observability Dashboard

### TO Diagram 1 (Memory Backbone)

- Consolidated memories (Episodic, Semantic, Procedural, Emotional)
- Knowledge graphs (Temporal, Causal, Relational)
- Performance insights (Observability Analytics)
- User models (ML User Modeling)

### TO Production Deployment

- Sleep State Machine → Deployment coordination
- Intelligence Dashboard → Production monitoring
- Cross-device Memory sync
- Family Memory coordination

---

## 🧠 Key Infrastructure Principles

1. **Memory-Driven**: All infrastructure serves Memory Backbone operations
2. **Cross-Device**: Infrastructure coordinates across family devices
3. **Event-Driven**: All infrastructure events carry `cognitive_trace_id`
4. **Family-Aware**: Infrastructure respects family relationships and boundaries
5. **Security-First**: E2EE, MLS, Zero Trust throughout
6. **Observable**: Comprehensive cognitive metrics and distributed tracing
7. **Adaptive**: ML-driven adaptation and optimization
8. **Resilient**: Outbox pattern, WAL, DLQ for durability

---

## 📝 Complete Architecture Overview

- ~~Diagram 1: API & Pipeline Architecture~~ ✅
- ~~Diagram 2: Cognitive Core~~ ✅
- ~~Diagram 3: Intelligence Systems~~ ✅
- ~~Diagram 4: Infrastructure~~ ✅
- Diagrams 5-8: (to be provided)

---

**End of Diagram 4 Processing**

---

---

# 🔌 CROSS-CUTTING CONNECTION CIRCUITS

## Overview: Wiring Between Architectural Layers

These diagrams show the **connection circuits** between the four architectural layers documented above. They reveal:

- **Fast vs. Smart paths** (teal solid = fast, orange dashed = smart/deliberative)
- **Shared components** (EventBus, Attention Gate, Working Memory)
- **Advisory boundaries** (Intelligence → P04 only)
- **Event correlation** (cognitive_trace_id throughout)
- **Storage flows** (specialized → canonical stores)

**Three Connection Circuits**:

1. **D1 ↔ D2**: API/Cognitive Core Connection (Diagram 5)
2. **D2 ↔ D3**: Cognitive/Intelligence Connection (Diagram 6)
3. **D3 ↔ D4**: Intelligence/Infrastructure Connection (Diagram 7)

---

---

# 🔌 Diagram 5 — D1 ↔ D2 Connection Circuit

## Title: API, Pipelines, Policy ↔ Cognitive Core, Retrieval, Hippocampus

### Purpose: How API requests flow through Cognitive Orchestration into Memory processing

This circuit shows the **dual-path architecture** (fast + smart) from API ingress through cognitive orchestration into hippocampal processing and retrieval.

---

## 🏗️ D1 Anchors (API & Cognitive Orchestration)

### 🛡️ API Ingress & Ports

**api/routers/agents_tools.py (Agents Plane)**

- Purpose: Agent API endpoints
- Connects to: CommandBusPort
- Classification: plane

**api/routers/app_frontend.py (App Plane)**

- Purpose: Application frontend API
- Connects to: QueryFacadePort, SSEHubPort
- Classification: plane

**api/routers/admin_index_security.py (Control Plane)**

- Purpose: Admin/control endpoints
- Connects to: CommandBusPort
- Classification: plane

**CommandBusPort**

- Purpose: Command bus interface
- Output to: Intent Router
- Classification: bus

**QueryFacadePort**

- Purpose: Query interface (fast path)
- Output to: Retrieval Adapter
- Classification: fast

**SSEHubPort**

- Purpose: Server-Sent Events streaming
- Output to: Global Broadcaster
- Classification: fast

### 🧭 Intent Router & Gate Hook

**intent/router.py**

- Purpose: Routes intents to fast or smart paths
- **Fast path** (valid & confident): → Memory Steward, Context Bundle
- **Smart path** (unset/low-confidence/obligations): → Attention Gate (D2)
- Classification: mid

### 🧠 Cognitive Orchestration (D1 Side)

**attention_gate/gate_service.py (D1)**

- Purpose: Gate service (D1 perspective)
- Equivalence: Same class/API as D2 Attention Gate
- Classification: gate

**memory_steward/orchestrator.py**

- Purpose: Memory operation orchestrator
- Fast path: Handles confident write workflows
- Output to: Hippocampus Orchestrator (D2)
- Classification: mid

**context_bundle/orchestrator.py**

- Purpose: Context bundling orchestrator
- Fast path: Handles confident recall
- Output to: Retrieval Adapter (D2)
- Classification: mid

**working_memory/manager.py (D1)**

- Purpose: Working Memory manager (D1 perspective)
- Bidirectional: ↔ Working Memory Manager (D2)
- Classification: mid

### 📡 Events & Pipelines

**events/bus.py (EventBus) — shared**

- Purpose: Shared event bus between D1 and D2
- Equivalence: Same instance as D2 EventBus
- Classification: bus

**pipelines/bus.py**

- Purpose: Pipeline bus
- Connects to: P01, P02, P04 (and others)
- Classification: bus

**P01 Recall/Read**

- Purpose: Memory recall pipeline
- Connects from: Pipeline Bus
- Classification: card

**P02 Write/Ingest**

- Purpose: Memory write pipeline
- Connects from: Pipeline Bus
- Classification: card

**P04 Arbitration/Action**

- Purpose: Action execution pipeline
- Connects from: Pipeline Bus
- Classification: card

### 🛡️ Policy

**policy/decision.py (PEP)**

- Purpose: Policy Enforcement Point
- Output to: Cognitive Policy
- Classification: gate

**policy/cognitive_policy.py**

- Purpose: Cognitive policy rules
- Output to: Attention Gate (D1)
- Advisory signals to: Attention Gate (D2)
- Classification: smart

### 💾 Read Indices (Logical)

**storage/* (read indices facade)**

- Purpose: Logical read indices
- Adapters to: D2 storage (st_fts, st_vec, st_sem, st_epi)
- Classification: storage

---

## 🏗️ D2 Anchors (Cognitive Core)

### 👁️ Attention Gate (Thalamus)

**attention_gate/gate_service.py (D2)**

- Purpose: Thalamic relay (smart path gating)
- Equivalence: Same class/API as D1 Attention Gate
- Input from: D1 Intent Router (low-confidence), Policy (admission signals)
- Output to: Working Memory Manager (D2), Cognitive Controller
- Classification: gate

### 🧮 Working Memory & 🌐 Global Workspace

**core/working_memory_manager.py (D2)**

- Purpose: Working Memory state management
- Bidirectional: ↔ Working Memory Manager (D1)
- Input from: Attention Gate (D2)
- Output to: Global Broadcaster
- Classification: mid

**workspace/global_broadcaster.py**

- Purpose: Global Workspace broadcaster
- Input from: SSEHubPort (D1), Working Memory Manager (D2)
- Output to: EventBus (cognitive events)
- Classification: mid

**core/cognitive_controller.py**

- Purpose: Cognitive control (ACC analog)
- Input from: Attention Gate (D2)
- Output to: Working Memory, Attention modulation
- Classification: smart

### 🧠 Hippocampus

**hippocampus/memory_orchestrator.py**

- Purpose: Hippocampal processing (DG→CA3→CA1)
- Input from: Memory Steward (D1) — write workflow
- Output to: EventBus (D2) — cognitive events
- Classification: mid

### 🔎 Retrieval Orchestration

**retrieval/context_adapter.py**

- Purpose: Retrieval context adaptation
- Input from: QueryFacadePort (D1 fast), Context Bundle (D1 smart)
- Output to: Enhanced Broker, EventBus (D2)
- Classification: mid

**retrieval/enhanced_broker.py**

- Purpose: Retrieval broker
- Input from: Context Adapter
- Output to: st_fts, st_vec, st_sem, st_epi
- Classification: mid

### 📡 Events & Workflows

**events/bus.py (EventBus) — shared**

- Purpose: Shared event bus (same instance as D1)
- Classification: bus

**events/types.py (cognitive events)**

- Purpose: Cognitive event types
- Connects to: EventBus (D1 and D2)
- Classification: gate

### 💾 Stores (Edge)

**st_fts (FTS)**

- Purpose: Full-text search storage
- Input from: Retrieval Broker
- Classification: storage

**st_vec (Vector)**

- Purpose: Vector embeddings storage
- Input from: Retrieval Broker
- Classification: storage

**st_sem (Semantic)**

- Purpose: Semantic memory storage
- Input from: Retrieval Broker
- Classification: storage

**st_epi (Episodic)**

- Purpose: Episodic memory storage
- Input from: Retrieval Broker
- Classification: storage

---

## 🔄 D1 → D2 Connection Flows

### 1. API → Ports Flow

```
API Routers → Ports → Intent Router
├─ agents_tools.py → CommandBusPort → Intent Router
├─ app_frontend.py → QueryFacadePort → Retrieval (fast)
├─ app_frontend.py → SSEHubPort → Global Broadcaster
└─ admin_index_security.py → CommandBusPort → Intent Router
```

### 2. Intent Routing (Fast vs. Smart)

```
Intent Router
├─ FAST PATH (valid & confident):
│  ├─ → Memory Steward Orchestrator
│  └─ → Context Bundle Orchestrator
└─ SMART PATH (unset/low-confidence/obligations):
   └─ → Attention Gate (D2)
```

### 3. Gate Equivalence + Feedback

```
Attention Gate (D1) ←→ Attention Gate (D2)
                        [same class/API]

Attention Gate (D2) → Working Memory Manager (D2)
Attention Gate (D2) → Cognitive Controller
```

### 4. Write Path (D1 → D2)

```
Memory Steward (D1)
  → write workflow (smart)
  → Hippocampus Orchestrator (D2)
  → EventBus (D2) [cognitive events]
```

### 5. Recall Path (D1 → D2)

```
QueryFacadePort (D1) → Retrieval Adapter (D2) [fast]
Context Bundle (D1) → Retrieval Adapter (D2) [smart]
Retrieval Adapter → Retrieval Broker
Retrieval Broker → st_fts, st_vec, st_sem, st_epi
Retrieval Adapter → EventBus (D2) [cognitive events]
```

### 6. Working Memory & Workspace

```
Working Memory (D1) ↔ Working Memory (D2) [bidirectional]
SSEHubPort → Global Broadcaster
Global Broadcaster ↔ Working Memory (D2)
Global Broadcaster → EventBus (D2)
```

### 7. Events/Pipelines Bridge

```
EventBus (shared) ↔ Pipeline Bus
EventBus (shared) ↔ Event Types
EventBus (D2) ↔ Event Types
Pipeline Bus → P01, P02, P04 (and others)
```

### 8. Policy Hook into Gate

```
Policy PEP → Cognitive Policy → Attention Gate (D1)
Cognitive Policy → Attention Gate (D2) [admission/risk signals]
```

### 9. Read Indices Bridge

```
Storage Read Indices (D1 logical)
  → adapters
  → st_fts, st_vec, st_sem, st_epi (D2)
```

---

## 🔑 Key D1↔D2 Connection Principles

1. **Dual-Path Architecture**: Fast path (confident) bypasses Gate; smart path (deliberative) goes through Gate
2. **Shared Components**: EventBus, Attention Gate, Working Memory are logically shared
3. **Thalamic Relay**: Attention Gate (D2) acts as thalamic relay for smart path
4. **Write → Hippocampus**: All writes flow through Hippocampus Orchestrator (D2)
5. **Recall → Retrieval**: All recalls flow through Retrieval Adapter/Broker (D2)
6. **Global Workspace**: Broadcasts cognitive state to SSE and EventBus
7. **Event Correlation**: All events carry cognitive_trace_id for tracing
8. **Policy Admission**: Policy signals influence Gate admission decisions

---

## 📊 Cross-Diagram Integration: D1↔D2

### FROM D1 (API & Pipelines)

- API requests (3 planes: Agent, App, Control)
- Intent routing (fast/smart classification)
- Memory Steward workflows (write)
- Context Bundle workflows (recall)
- Pipeline coordination (P01-P20)
- Policy enforcement (PEP + Cognitive Policy)

### TO D2 (Cognitive Core)

- Attention Gate (thalamic relay for smart path)
- Hippocampus (DG→CA3→CA1 processing)
- Retrieval (context adaptation + broker)
- Working Memory (state management)
- Global Workspace (broadcasting)
- Cognitive Controller (ACC analog)
- Cognitive events (via EventBus)

### SHARED BETWEEN D1 & D2

- EventBus (same instance)
- Attention Gate (same class/API)
- Working Memory (bidirectional sync)
- Storage (D1 logical adapters to D2 physical stores)

---

**End of Diagram 5 (D1↔D2 Connection)**

---

---

# 🔌 Diagram 6 — D2 ↔ D3 Connection Circuit

## Title: Cognitive Core ↔ Intelligence Systems (Advisory)

### Purpose: How Cognitive Core feeds Intelligence Systems and receives advisory signals

This circuit shows how the **Cognitive Core** (Attention, Working Memory, Retrieval, Hippocampus, Affect) connects to **Intelligence Systems** (Learning, Social Cognition, Metacognition, Advisory Action) and the **advisory boundary** where intelligence signals are guarded before reaching P04.

---

## 🏗️ D1 (Cognitive/Core) Anchors

### 👁️ Attention Gate

**attention_gate/gate_service.py**

- Purpose: Thalamic relay (salience, admission)
- Output to: Intelligence Policy Guard (salience signals)
- Classification: gate

### 🧮 Working Memory & 🌐 Global Workspace

**core/working_memory_manager.py**

- Purpose: Working Memory state
- Bidirectional: ↔ Intelligence Memory
- Classification: mid

**workspace/global_broadcaster.py**

- Purpose: Global Workspace broadcaster
- Output to: Intelligence Memory, Decision Recommendation
- Classification: mid

### 🔎 Retrieval

**retrieval/context_adapter.py**

- Purpose: Context adaptation
- Output to: Intelligence Coordinator
- Classification: mid

**retrieval/enhanced_broker.py**

- Purpose: Retrieval broker
- Output to: Learning Coordinator
- Classification: mid

### 🧠 Hippocampus

**hippocampus/memory_orchestrator.py**

- Purpose: Hippocampal processing
- Output to: Intelligence Memory
- Classification: mid

### 💝 Affect (Limbic)

**affect/affect_state.py**

- Purpose: Affect state management
- Output to: Learning Adaptive Controller, Decision Recommendation
- Classification: mid

**affect/realtime_classifier.py**

- Purpose: Real-time affect classification
- Output to: Intelligence Memory
- Classification: smart

### 📡 Events & Workflows

**events/bus.py (shared)**

- Purpose: Event bus (shared with D2)
- Connects to: Intelligence Events, intelligence.* topics
- Classification: bus

**events/types.py**

- Purpose: Cognitive event types
- Classification: gate

### 💾 Storage (Edge)

**st_fts, st_vec, st_sem, st_epi**

- Purpose: Core memory stores
- Input from: Retrieval Broker
- Classification: storage

---

## 🏗️ D2 (Intelligence) Anchors

### 🧠 Intelligence Core

**Intelligence Coordinator**

- Purpose: Coordinates intelligence subsystems
- Input from: Retrieval Adapter (D1)
- Output to: P05 (Prospective)
- Classification: brain

**Intelligence Memory**

- Purpose: Intelligence-specific memory management
- Input from: Global Broadcaster (D1), Hippocampus (D1), Affect Classifier (D1)
- Bidirectional: ↔ Working Memory (D1)
- Output to: Storage (Episodic)
- Classification: brain

**Intelligence Events**

- Purpose: Intelligence event processing
- Input from: EventBus (shared)
- Classification: brain

### 🔄 Learning Loop

**Coordinator**

- Purpose: Learning coordination
- Input from: Retrieval Broker (D1)
- Classification: mid

**Adaptive Controller**

- Purpose: Adaptive learning control
- Input from: Affect State (D1)
- Output to: P06 (Learning)
- Classification: mid

### 🤝 Social & 🪞 Metacognition

**Belief Attribution (Theory of Mind)**

- Purpose: Social cognition (belief attribution)
- Classification: mid

**Confidence Assessment (Metacognition)**

- Purpose: Metacognitive confidence
- Classification: mid

### 🎮 Advisory → P04 Only

**Decision Recommendation**

- Purpose: Recommends decisions (advisory only)
- Input from: Global Broadcaster (D1), Affect State (D1)
- Output to: Intelligence Policy Guard
- Classification: mid

**Action Coordination (advisory)**

- Purpose: Coordinates action recommendations
- Output to: Intelligence Policy Guard
- Classification: mid

### 🛡️ Guards on Advice

**policy/intelligence_guard.py**

- Purpose: Guards intelligence advice
- Input from: Attention Gate (D1) salience, Decision Recommendation, Action Coordination
- Output to: Intelligence QoS Gate
- Classification: gate

**retrieval/qos_gate.py (advice budgets)**

- Purpose: QoS gating for advice
- Input from: Intelligence Policy Guard
- Output to: Intelligence Safety
- Classification: smart

**policy/safety.py (advice)**

- Purpose: Safety guard for advice
- Input from: Intelligence QoS Gate
- Output to: intelligence.advisory.* topics
- Classification: smart

### 📡 intelligence.* Topics

**intelligence.***

- Purpose: Intelligence events (general)
- Connects to: EventBus (shared)
- Classification: bus

**intelligence.advisory.***

- Purpose: Advisory signals (guarded)
- Output to: P04 Arbitration/Action
- Classification: bus

**intelligence.trace.***

- Purpose: Intelligence tracing events
- Connects to: EventBus (shared)
- Classification: bus

### 🔗 Pipeline & SSE Anchors

**→ P04 Arbitration/Action (sole executor)**

- Purpose: P04 pipeline anchor (only executor of advisory signals)
- Input from: intelligence.advisory.* topics
- Classification: bus

**→ P06 Learning**

- Purpose: P06 pipeline anchor
- Input from: Learning Adaptive Controller
- Classification: bus

**→ P05 Prospective**

- Purpose: P05 pipeline anchor
- Input from: Intelligence Coordinator
- Classification: bus

**→ SSE: intelligence.* (sanitized)**

- Purpose: SSE streaming (sanitized intelligence events)
- Input from: intelligence.* topics
- Classification: plane

---

## ⚖️ P04 — Arbitration/Action (Executes)

**P04 Arbitration/Action**

- Purpose: Sole executor of advisory signals
- Input from: intelligence.advisory.* topics (guarded)
- Classification: brain

---

## 🔄 D1 → D2 Connection Flows

### 1. Workspace/WM Bridge

```
Global Broadcaster (D1) → Intelligence Memory (D2)
Global Broadcaster (D1) → Decision Recommendation (D2)
Working Memory (D1) ↔ Intelligence Memory (D2) [bidirectional]
```

### 2. Affect Bridge

```
Affect Classifier (D1) → Intelligence Memory (D2)
Affect State (D1) → Learning Adaptive Controller (D2)
Affect State (D1) → Decision Recommendation (D2)
```

### 3. Retrieval/Hippo Influences into Intelligence

```
Retrieval Adapter (D1) → Intelligence Coordinator (D2)
Retrieval Broker (D1) → Learning Coordinator (D2)
Hippocampus Orchestrator (D1) → Intelligence Memory (D2)
EventBus (shared) → Intelligence Events (D2)
```

### 4. Gate/Policy Interplay

```
Attention Gate (D1) → Intelligence Policy Guard (D2) [salience/admission signals]
```

### 5. Intelligence Advisory Out → Guards → Topics → P04

```
Decision Recommendation (D2) → Intelligence Policy Guard
Action Coordination (D2) → Intelligence Policy Guard
Intelligence Policy Guard → Intelligence QoS Gate
Intelligence QoS Gate → Intelligence Safety
Intelligence Safety → intelligence.advisory.* topics
intelligence.advisory.* topics → P04 (sole executor)
```

### 6. Learning/Prospective Hooks

```
Learning Adaptive Controller (D2) → P06 (Learning)
Intelligence Coordinator (D2) → P05 (Prospective)
```

### 7. SSE Exposure

```
intelligence.* topics → SSE: intelligence.* (sanitized)
```

### 8. Storage Adapters

```
Retrieval Broker (D1) → st_fts, st_vec, st_sem, st_epi
```

---

## 🔑 Key D1↔D2 Connection Principles

1. **Advisory Boundary**: Intelligence Systems emit advisory signals only; P04 is sole executor
2. **Guarded Advisory Path**: Decision Recommendation → Policy Guard → QoS Gate → Safety → P04
3. **Workspace Bridge**: Global Broadcaster feeds Intelligence Memory and Decision Recommendation
4. **Affect Integration**: Affect State influences Learning and Decision systems
5. **Salience Signals**: Attention Gate provides salience/admission signals to Policy Guard
6. **Bidirectional WM**: Working Memory syncs between Cognitive Core and Intelligence Memory
7. **Event Correlation**: All intelligence events carry cognitive_trace_id
8. **Learning Feedback**: Learning Adaptive Controller adjusts based on affect and retrieval outcomes

---

## 📊 Cross-Diagram Integration: D1↔D2

### FROM D1 (Cognitive Core)

- Global Workspace broadcasts (state, context)
- Working Memory state (bidirectional)
- Affect signals (state, classification)
- Retrieval context (adapter, broker)
- Hippocampal outputs (memory processing)
- Attention Gate salience (admission signals)
- Cognitive events (via EventBus)

### TO D2 (Intelligence Systems)

- Intelligence Memory (context, affect, hippocampal outputs)
- Intelligence Coordinator (retrieval context)
- Learning Coordinator/Adaptive Controller (retrieval, affect)
- Decision Recommendation (workspace, affect)
- Action Coordination (advisory only)
- Intelligence Policy Guard (salience, advisory signals)
- P04 (sole executor of guarded advisory signals)
- P05 (prospective planning)
- P06 (learning workflows)

### ADVISORY BOUNDARY (D2)

- Decision Recommendation → guarded → P04 only
- Action Coordination → guarded → P04 only
- No direct execution by Intelligence Systems
- Guards: Policy → QoS → Safety → advisory topics

### SHARED BETWEEN D1 & D2

- EventBus (same instance, cognitive_trace_id)
- Working Memory state (bidirectional sync)
- Storage (D1 reads from same stores D2 populates)

---

**End of Diagram 6 (D1↔D2 Connection)**

---

---

# 🔌 Diagram 7 — D3 ↔ D4 Connection Circuit

## Title: Intelligence Systems ↔ Infrastructure (Events, Storage, Policy, Observability)

### Purpose: How Intelligence Systems (advisory) are guarded, routed through Infrastructure (EventBus, Policy, Storage), and exposed to pipelines

This circuit shows the **infrastructure wiring** for Intelligence Systems: how advisory signals are guarded by policy, routed through the EventBus, stored in canonical infrastructure stores, monitored by observability, and handed off to pipelines.

---

## 🏗️ D3 (Intelligence) Anchors

### 🧠 Core Services

**Intelligence Coordinator**

- Purpose: Coordinates intelligence subsystems
- Output to: Registry Tools/Prompts/Agents
- Classification: brain

**Intelligence Memory**

- Purpose: Intelligence-specific memory
- Output to: st_episodic (Infrastructure)
- Classification: brain

**Intelligence Events**

- Purpose: Intelligence event processing
- Output to: EventBus Anchor (Infrastructure)
- Classification: brain

### 🛡️ Guards for Advisory

**policy/intelligence_guard.py**

- Purpose: Guards advisory signals
- Input from: Decision Recommendation, Action Coordination
- Output to: Policy Rules Engine (D4), Privacy Budget (D4), PII Minimizer (D4)
- Classification: gate

**retrieval/qos_gate (advice budgets)**

- Purpose: QoS gating for advice
- Output to: Adaptive Sampling (D4), P17 QoS (D4)
- Classification: gate

**policy/safety (advice)**

- Purpose: Safety guard for advice
- Output to: Adaptive Defense (D4)
- Classification: gate

### 📡 Topics (D3)

**intelligence.***

- Purpose: Intelligence events (general)
- Output to: EventBus Anchor (D4)
- Classification: bus

**intelligence.advisory.***

- Purpose: Advisory signals (guarded)
- Output to: EventBus Anchor (D4)
- Classification: bus

**intelligence.trace.***

- Purpose: Intelligence tracing events
- Output to: EventBus Anchor (D4)
- Classification: bus

### 🎮 Advisory Producers

**Decision Recommendation**

- Purpose: Recommends decisions (advisory)
- Output to: Intelligence Policy Guard → (guards) → intelligence.advisory.*
- Classification: mid

**Action Coordination (advisory)**

- Purpose: Coordinates action recommendations
- Output to: Intelligence Policy Guard → (guards) → intelligence.advisory.*
- Classification: mid

**Learning Adaptive Controller**

- Purpose: Adaptive learning control
- Output to: P06 Learning (D3 anchor)
- Classification: mid

### 🔗 Pipeline/SSE Anchors (D3 Side)

**→ P05 Prospective (from D3)**

- Purpose: D3 anchor to P05
- Classification: bus

**→ P06 Learning (from D3)**

- Purpose: D3 anchor to P06
- Classification: bus

**→ P17 QoS (from D3)**

- Purpose: D3 anchor to P17
- Classification: bus

**→ P18 Safety (from D3)**

- Purpose: D3 anchor to P18
- Classification: bus

**→ SSE: intelligence.* (sanitized)**

- Purpose: D3 SSE exposure
- Classification: plane

### 💾 D3 Specialized Stores

**Learning Store (D3)**

- Purpose: Learning-specific storage
- Output to: st_semantic (D4)
- Classification: storage

**Social Store (D3)**

- Purpose: Social cognition storage
- Output to: st_kg (D4)
- Classification: storage

**Metacog Store (D3)**

- Purpose: Metacognition storage
- Output to: st_semantic (D4)
- Classification: storage

**Procedural Store (D3)**

- Purpose: Procedural memory storage
- Output to: st_semantic (D4)
- Classification: storage

---

## 🏗️ D4 (Infrastructure) Anchors

### 📡 Events Bus & Topics

**events.bus**

- Purpose: Central event bus (shared)
- Input from: Intelligence Events, intelligence.*topics, intelligence.trace.*
- Output to: infra.observability.*, infra.ml.*
- Classification: bus

**events/validation.py**

- Purpose: Event schema validation
- Classification: gate

**infra.observability.***

- Purpose: Observability events
- Output to: Intelligence Dashboard
- Classification: bus

**infra.ml.***

- Purpose: ML adaptation events
- Classification: bus

**privacy.***

- Purpose: Privacy events
- Classification: bus

### 🔗 Pipeline Anchors (D4 Side)

**→ P05 Prospective (D4)**

- Purpose: D4 anchor from P05 (D3)
- Classification: bus

**→ P06 Learning (D4)**

- Purpose: D4 anchor from P06 (D3)
- Classification: bus

**→ P17 QoS (D4)**

- Purpose: D4 anchor from P17 (D3)
- Classification: bus

**→ P18 Safety (D4)**

- Purpose: D4 anchor from P18 (D3)
- Classification: bus

**→ SSE: infra.* & privacy.***

- Purpose: D4 SSE exposure
- Classification: plane

### ⚖️ Policy, PII & Governance

**Policy Rules Engine**

- Purpose: Policy decision engine
- Input from: Intelligence Policy Guard (D3)
- Classification: gate

**Privacy Budget**

- Purpose: Privacy budget tracking
- Input from: Intelligence Policy Guard (D3)
- Classification: gate

**pii_minimizer_service (P10)**

- Purpose: PII minimization (P10 implementation)
- Input from: Intelligence Policy Guard (D3)
- Output to: st_pii_map
- Classification: gate

**redaction_coordinator**

- Purpose: Coordinates PII redaction
- Input from: Intelligence Policy Guard (D3)
- Output to: st_redaction_log
- Classification: gate

### 🛡️ Security & Safety

**Adaptive Defense**

- Purpose: Adaptive threat defense
- Input from: Intelligence Safety Monitor (D3)
- Classification: gate

### 🔭 Observability

**Intelligence Dashboard**

- Purpose: Intelligence metrics dashboard
- Input from: infra.observability.* topics
- Classification: mid

**obs/metric_sink**

- Purpose: Metric collection sink
- Input from: EventBus
- Classification: mid

**Adaptive Sampling**

- Purpose: Adaptive trace sampling
- Input from: Intelligence QoS Guard (D3)
- Classification: mid

### 💾 Core Storage

**st_semantic**

- Purpose: Semantic memory storage (canonical)
- Input from: Learning Store (D3), Metacog Store (D3), Procedural Store (D3)
- Classification: storage

**st_episodic**

- Purpose: Episodic memory storage (canonical)
- Input from: Intelligence Memory (D3)
- Classification: storage

**st_kg**

- Purpose: Knowledge graph storage (canonical)
- Input from: Social Store (D3)
- Classification: storage

**st_vector**

- Purpose: Vector embeddings storage
- Classification: storage

**st_pii_map**

- Purpose: PII mapping storage
- Input from: PII Minimizer
- Classification: storage

**st_redaction_log**

- Purpose: Redaction audit log
- Input from: Redaction Coordinator
- Classification: storage

### 📇 Registries

**registry/tools**

- Purpose: Tool registry
- Input from: Intelligence Coordinator (D3)
- Classification: mid

**registry/prompts**

- Purpose: Prompt registry
- Input from: Intelligence Coordinator (D3)
- Classification: mid

**registry/agents**

- Purpose: Agent registry
- Input from: Intelligence Coordinator (D3)
- Classification: mid

---

## 🔄 D3 → D4 Connection Flows

### 1. Advisory Path (Guarded) → Bus → Pipelines

```
Decision Recommendation (D3)
  → Intelligence Policy Guard (D3)
  → Intelligence QoS Guard (D3)
  → Intelligence Safety Monitor (D3)
  → intelligence.advisory.* topics

Action Coordination (D3)
  → Intelligence Policy Guard (D3)
  → (same guard chain)

intelligence.advisory.* topics → EventBus Anchor (D4)
```

### 2. Pipeline Hand-Offs (D3 → D4)

```
→ P05 Prospective (D3) → → P05 Prospective (D4)
→ P06 Learning (D3) → → P06 Learning (D4)
→ P17 QoS (D3) → → P17 QoS (D4)
→ P18 Safety (D3) → → P18 Safety (D4)
```

### 3. Intelligence Events/Trace → EventBus → Observability/ML

```
Intelligence Events (D3) → EventBus Anchor (D4)
intelligence.* topics → EventBus Anchor (D4)
intelligence.trace.* topics → EventBus Anchor (D4)

EventBus (D4) → infra.observability.* → Intelligence Dashboard
EventBus (D4) → Metric Sink
EventBus (D4) → infra.ml.* topics
```

### 4. Guards ↔ Policy/Safety/Governance

```
Intelligence Policy Guard (D3)
  → Policy Rules Engine (D4)
  → Privacy Budget (D4)
  → PII Minimizer (D4) → st_pii_map
  → Redaction Coordinator (D4) → st_redaction_log

Intelligence Safety Monitor (D3) → Adaptive Defense (D4)
Intelligence QoS Guard (D3) → Adaptive Sampling (D4)
Intelligence QoS Guard (D3) → P17 (D4)
```

### 5. SSE Exposure

```
→ SSE: intelligence.* (D3) → → SSE: infra.* & privacy.* (D4)
```

### 6. Specialized Intelligence Stores → Infra Stores (Canonical)

```
Learning Store (D3) → st_semantic (D4)
Metacog Store (D3) → st_semantic (D4)
Procedural Store (D3) → st_semantic (D4)
Social Store (D3) → st_kg (D4)
Intelligence Memory (D3) → st_episodic (D4)
```

### 7. Coordination/Registries Linkage

```
Intelligence Coordinator (D3)
  → registry/tools (D4)
  → registry/prompts (D4)
  → registry/agents (D4)
```

---

## 🔑 Key D3↔D4 Connection Principles

1. **Advisory Guarded**: All advisory signals pass through Policy → QoS → Safety guards before EventBus
2. **EventBus Central**: EventBus (D4) is the central nervous system for intelligence.* topics
3. **Canonical Storage**: Specialized D3 stores flow into canonical D4 stores (semantic, episodic, kg)
4. **Observability Integration**: intelligence.*and intelligence.trace.* topics feed Intelligence Dashboard
5. **Policy Enforcement**: Intelligence Policy Guard connects to Policy Rules Engine, Privacy Budget, PII Minimizer
6. **Safety Monitoring**: Intelligence Safety Monitor connects to Adaptive Defense
7. **QoS Gating**: Intelligence QoS Guard connects to Adaptive Sampling and P17 QoS
8. **SSE Sanitization**: intelligence.*topics sanitized and exposed as infra.* and privacy.* topics
9. **Registry Coordination**: Intelligence Coordinator registers tools/prompts/agents in Infrastructure registries
10. **Event Correlation**: All events carry cognitive_trace_id for end-to-end tracing

---

## 📊 Cross-Diagram Integration: D3↔D4

### FROM D3 (Intelligence Systems)

- Advisory signals (Decision Recommendation, Action Coordination) — guarded
- Intelligence events (intelligence.*, intelligence.trace.*)
- Learning traces → infra.ml.*
- Social analytics → st_kg
- Metacognition → st_semantic
- Procedural memory → st_semantic
- Intelligence Memory → st_episodic
- Pipeline anchors (P05, P06, P17, P18)
- Tool/Prompt/Agent coordination

### TO D4 (Infrastructure)

- EventBus (central routing for intelligence.* topics)
- Policy Rules Engine (advisory guard enforcement)
- Privacy Budget (advisory privacy tracking)
- PII Minimizer (P10 implementation)
- Redaction Coordinator (PII audit)
- Adaptive Defense (safety enforcement)
- Adaptive Sampling (observability QoS)
- Intelligence Dashboard (metrics visualization)
- Canonical storage (st_semantic, st_episodic, st_kg, st_vector, st_pii_map, st_redaction_log)
- Registries (tools, prompts, agents)
- SSE exposure (sanitized infra.*and privacy.* topics)

### GUARDED ADVISORY PATH (D3 → D4)

- Decision/Action → Intelligence Guards (Policy, QoS, Safety)
- Guarded signals → intelligence.advisory.* topics
- EventBus → Pipeline anchors (P05, P06, P17, P18)

### EVENT CORRELATION (D3 ↔ D4)

- cognitive_trace_id on all intelligence.* topics
- Enables end-to-end tracing from Cognitive Core → Intelligence → Infrastructure → Pipelines

---

**End of Diagram 7 (D3↔D4 Connection)**

---

---

# 🔌 Diagram 8 — D1 ↔ D3 Connection Circuit

## Title: API, Pipelines, Policy ↔ Intelligence Systems (Direct Path)

### Purpose: Direct connections between API/Pipeline layer and Intelligence Systems, bypassing Cognitive Core for specific intelligence workflows

This circuit shows the **direct wiring** between API/Pipelines (D1) and Intelligence Systems (D3), revealing how certain intelligence workflows connect directly to pipelines without flowing through the full Cognitive Core (D2). This includes learning feedback loops, prospective planning, QoS governance, and safety monitoring.

---

## 🏗️ D1 Anchors (API & Pipelines)

### 🛡️ API Ingress & Command/Query

**api/routers/agents_tools.py (Agents Plane)**
- Purpose: Agent API endpoints
- Direct connection to: Intelligence Coordinator (tool/agent registration)
- Classification: plane

**api/routers/admin_index_security.py (Control Plane)**
- Purpose: Admin/control endpoints
- Direct connection to: Intelligence Policy Guard (admin overrides)
- Classification: plane

**CommandBusPort**
- Purpose: Command bus interface
- Direct connection to: Intelligence Events
- Classification: bus

**QueryFacadePort**
- Purpose: Query interface
- Direct connection to: Intelligence Metadata queries
- Classification: fast

**SSEHubPort**
- Purpose: Server-Sent Events streaming
- Direct connection to: Intelligence topics (intelligence.*, sanitized)
- Classification: fast

### 📡 Events & Pipelines

**events/bus.py (EventBus) — shared**
- Purpose: Central event bus (shared across D1, D2, D3, D4)
- Direct connection to: intelligence.* topics
- Classification: bus

**pipelines/bus.py**
- Purpose: Pipeline bus
- Direct connection to: P04, P05, P06, P17, P18, P19
- Classification: bus

**P01 Recall/Read**
- Purpose: Memory recall
- Intelligence connection: Learning traces (read patterns)
- Classification: card

**P02 Write/Ingest**
- Purpose: Memory write
- Intelligence connection: Learning traces (write patterns)
- Classification: card

**P04 Arbitration/Action**
- Purpose: Action execution (sole executor)
- Intelligence connection: Receives guarded advisory signals from Intelligence
- Classification: card

**P05 Prospective Memory**
- Purpose: Prospective planning
- Intelligence connection: Receives intentions from Intelligence Coordinator
- Classification: card

**P06 Learning**
- Purpose: Learning workflows
- Intelligence connection: Receives learning signals from Adaptive Controller
- Classification: card

**P17 QoS/Cost Governance**
- Purpose: QoS and cost tracking
- Intelligence connection: Receives QoS signals from Intelligence QoS Guard
- Classification: card

**P18 Safety/Abuse**
- Purpose: Safety monitoring
- Intelligence connection: Receives safety alerts from Intelligence Safety Monitor
- Classification: card

**P19 Observability**
- Purpose: Observability and metrics
- Intelligence connection: Receives intelligence.* events for dashboard
- Classification: card

### 🛡️ Policy & Security

**policy/decision.py (PEP)**
- Purpose: Policy Enforcement Point
- Direct connection to: Intelligence Policy Guard (policy sync)
- Classification: gate

**policy/cognitive_policy.py**
- Purpose: Cognitive policy rules
- Direct connection to: Intelligence Policy Guard (policy updates)
- Classification: smart

**security/mls.py**
- Purpose: MLS classification/enforcement
- Direct connection to: Intelligence Safety Monitor (MLS band violations)
- Classification: gate

### 🔍 Query & Metadata

**query/facade.py**
- Purpose: Query facade
- Direct connection to: Intelligence Metadata (learning stats, social graphs, metacog confidence)
- Classification: fast

### 📊 Observability

**obs/metric_sink**
- Purpose: Metric collection
- Direct connection to: Intelligence Dashboard (intelligence.* metrics)
- Classification: mid

**obs/distributed_tracing**
- Purpose: Distributed tracing
- Direct connection to: Intelligence trace events (intelligence.trace.*)
- Classification: mid

---

## 🏗️ D3 (Intelligence) Anchors

### 🧠 Intelligence Core

**Intelligence Coordinator**
- Purpose: Coordinates intelligence subsystems
- Input from: API Agents Plane (tool/agent registration), Query Facade (metadata queries)
- Output to: P05 (Prospective), Registry coordination
- Classification: brain

**Intelligence Memory**
- Purpose: Intelligence-specific memory
- Direct query access from: Query Facade (intelligence metadata)
- Classification: brain

**Intelligence Events**
- Purpose: Intelligence event processing
- Input from: CommandBusPort, EventBus
- Output to: intelligence.* topics → EventBus
- Classification: brain

### 🔄 Learning Loop

**Learning Coordinator**
- Purpose: Learning coordination
- Input from: P01/P02 traces (read/write patterns)
- Output to: P06 (Learning workflows)
- Classification: mid

**Learning Adaptive Controller**
- Purpose: Adaptive learning control
- Input from: P01/P02 outcomes
- Output to: P06 (Learning signals)
- Classification: mid

**Learning Trace Collector**
- Purpose: Collects traces from pipelines
- Input from: P01-P20 (all pipeline traces)
- Output to: Learning Coordinator
- Classification: mid

### 🤝 Social Cognition

**Social Graph Builder**
- Purpose: Builds family social graphs
- Query access from: Query Facade (social relationships)
- Classification: mid

**Theory of Mind Engine**
- Purpose: Belief attribution
- Query access from: Query Facade (belief states)
- Classification: mid

### 🪞 Metacognition

**Confidence Assessor**
- Purpose: Confidence assessment
- Query access from: Query Facade (confidence scores)
- Output to: P04 (confidence signals for arbitration)
- Classification: mid

**Monitoring/Control**
- Purpose: Metacognitive monitoring
- Input from: P04 outcomes (action success/failure)
- Output to: Learning Coordinator (strategy adjustments)
- Classification: mid

### 🎮 Advisory Systems

**Decision Recommendation**
- Purpose: Recommends decisions (advisory)
- Output to: Intelligence Policy Guard → P04 only
- Classification: mid

**Action Coordination (advisory)**
- Purpose: Coordinates action recommendations
- Output to: Intelligence Policy Guard → P04 only
- Classification: mid

### 🛡️ Intelligence Guards

**policy/intelligence_guard.py**
- Purpose: Guards intelligence advisory signals
- Input from: Policy PEP (D1), Cognitive Policy (D1), Admin API (D1), Decision/Action (D3)
- Output to: Intelligence QoS Guard
- Classification: gate

**retrieval/qos_gate.py (advice budgets)**
- Purpose: QoS gating for advice
- Input from: Intelligence Policy Guard
- Output to: P17 QoS (cost tracking), Intelligence Safety
- Classification: smart

**policy/safety.py (advice)**
- Purpose: Safety guard for advice
- Input from: Intelligence QoS Guard, MLS violations (D1)
- Output to: P18 Safety, intelligence.advisory.*
- Classification: smart

### 🔬 Prospective & Imagination

**Intention Formation**
- Purpose: Forms prospective intentions
- Output to: P05 (Prospective Memory)
- Classification: mid

**Prospective Simulator**
- Purpose: Simulates future scenarios
- Input from: Query Facade (context queries)
- Output to: P05 (simulation results)
- Classification: mid

### 📡 Intelligence Topics

**intelligence.***
- Purpose: Intelligence events (general)
- Output to: EventBus (D1) → SSE (sanitized), P19 Observability
- Classification: bus

**intelligence.advisory.***
- Purpose: Advisory signals (guarded)
- Output to: P04 only
- Classification: bus

**intelligence.trace.***
- Purpose: Intelligence tracing
- Output to: EventBus (D1) → Distributed Tracing (D1)
- Classification: bus

**intelligence.learning.***
- Purpose: Learning signals
- Output to: P06 (Learning)
- Classification: bus

**intelligence.prospective.***
- Purpose: Prospective planning signals
- Output to: P05 (Prospective)
- Classification: bus

### 📊 Intelligence Metadata

**Intelligence Metadata Service**
- Purpose: Provides intelligence metadata queries
- Query access from: Query Facade (D1)
- Metadata types: Learning stats, social graphs, metacog confidence, reward signals, procedural habits
- Classification: fast

---

## 🔄 D1 → D3 Connection Flows

### 1. API → Intelligence Coordination

```
API Agents Plane
  → Intelligence Coordinator
  → Tool/Agent/Prompt registration

API Control Plane
  → Intelligence Policy Guard
  → Admin overrides, policy updates
```

### 2. Pipeline Traces → Learning Loop

```
P01 (Recall) → Learning Trace Collector → Learning Coordinator
P02 (Write) → Learning Trace Collector → Learning Coordinator
P03-P20 (All) → Learning Trace Collector → Learning patterns

Learning Coordinator
  → Learning Adaptive Controller
  → P06 (Learning workflows)
```

### 3. Query Facade → Intelligence Metadata

```
Query Facade (D1)
  → Intelligence Metadata Service (D3)
  ├─ Learning stats (episodic → semantic consolidation rates)
  ├─ Social graphs (family relationships, shared attention)
  ├─ Metacognitive confidence (per context)
  ├─ Reward signals (goal salience, motivation)
  └─ Procedural habits (skill mastery, habit strength)
```

### 4. Advisory Path (Guarded) → P04

```
Decision Recommendation (D3)
  → Intelligence Policy Guard (D3)
  → Intelligence QoS Guard (D3)
  → Intelligence Safety (D3)
  → intelligence.advisory.* topics
  → P04 Arbitration/Action (D1) [sole executor]
```

### 5. Prospective Planning → P05

```
Intention Formation (D3)
  → Prospective Simulator (D3)
  → intelligence.prospective.* topics
  → P05 Prospective Memory (D1)
```

### 6. QoS Signals → P17

```
Intelligence QoS Guard (D3)
  → QoS budget signals
  → P17 QoS/Cost Governance (D1)
```

### 7. Safety Alerts → P18

```
Intelligence Safety Monitor (D3)
  → Safety alerts (MLS violations, threat detection)
  → P18 Safety/Abuse (D1)
```

### 8. Intelligence Events → SSE & Observability

```
intelligence.* topics (D3)
  → EventBus (D1)
  ├─ SSEHubPort → Apps/Agents (sanitized)
  └─ P19 Observability → Intelligence Dashboard

intelligence.trace.* (D3)
  → EventBus (D1)
  → Distributed Tracing (D1)
  → cognitive_trace_id correlation
```

### 9. Policy Sync (Bidirectional)

```
Policy PEP (D1)
  ↔ Intelligence Policy Guard (D3)
  [policy updates, admin overrides, MLS enforcement]

Cognitive Policy (D1)
  → Intelligence Policy Guard (D3)
  [cognitive policy rules]
```

### 10. Metacognitive Feedback → P04

```
P04 outcomes (D1)
  → Metacognitive Monitoring (D3)
  → Confidence Assessor (D3)
  → Learning Coordinator (D3)
  → Strategy adjustments

Confidence Assessor (D3)
  → P04 (confidence signals for arbitration)
```

---

## 🔑 Key D1↔D3 Connection Principles

1. **Direct Pipeline Feedback**: P01-P20 pipelines provide traces directly to Learning Loop (bypassing D2)
2. **Advisory Boundary Enforcement**: Intelligence advisory signals must pass through guards before reaching P04
3. **Metadata Query Access**: Query Facade provides direct access to Intelligence Metadata (fast path)
4. **Tool/Agent Registration**: API Agents Plane directly registers tools/agents with Intelligence Coordinator
5. **Policy Synchronization**: Policy PEP (D1) and Intelligence Policy Guard (D3) stay synchronized
6. **QoS Governance**: Intelligence QoS Guard directly signals P17 for cost/budget tracking
7. **Safety Monitoring**: Intelligence Safety directly alerts P18 for threat/abuse detection
8. **Prospective Planning**: Intelligence Coordinator directly signals P05 for prospective workflows
9. **Observability Integration**: intelligence.* topics flow to P19 and SSE for real-time visibility
10. **Event Correlation**: All D1↔D3 events carry cognitive_trace_id for end-to-end tracing

---

## 📊 Cross-Diagram Integration: D1↔D3

### FROM D1 (API & Pipelines)
- API Agents Plane (tool/agent registration)
- API Control Plane (admin overrides, policy updates)
- Pipeline traces (P01-P20 → Learning Loop)
- Query Facade (intelligence metadata queries)
- Policy PEP (policy synchronization)
- MLS enforcement (safety signals)
- SSE streaming (intelligence.* exposure)
- Observability (intelligence.* metrics)

### TO D3 (Intelligence Systems)
- Intelligence Coordinator (tool/agent registration, prospective planning)
- Learning Loop (trace collection, adaptive learning)
- Intelligence Metadata (query responses: learning stats, social graphs, confidence)
- Intelligence Policy Guard (policy sync, admin overrides)
- Intelligence QoS Guard (budget tracking)
- Intelligence Safety (threat alerts)
- Advisory Systems (decision/action recommendations → guarded → P04)

### FROM D3 (Intelligence Systems)
- Advisory signals (guarded) → P04 (sole executor)
- Learning signals → P06 (Learning workflows)
- Prospective intentions → P05 (Prospective Memory)
- QoS budget signals → P17 (Cost Governance)
- Safety alerts → P18 (Safety/Abuse)
- intelligence.* events → SSE, P19 Observability
- Intelligence metadata responses → Query Facade
- Metacognitive confidence → P04 (arbitration confidence)

### ADVISORY BOUNDARY (D1↔D3)
- Decision/Action (D3) → Guards (Policy → QoS → Safety) → P04 (D1) only
- No direct execution by Intelligence Systems
- P04 outcomes feed back to Metacognition (D3) for strategy adjustments

### DIRECT PATHS (BYPASSING D2)
- **Learning traces**: P01-P20 → Learning Loop (no D2 Cognitive Core intermediary)
- **Metadata queries**: Query Facade → Intelligence Metadata (no D2 Working Memory)
- **Tool registration**: API → Intelligence Coordinator (no D2 Gate)
- **Prospective planning**: Intelligence → P05 (no D2 Global Workspace)
- **QoS/Safety**: Intelligence Guards → P17/P18 (no D2 Policy intermediary)

### EVENT CORRELATION (D1↔D3)
- cognitive_trace_id on all intelligence.* topics
- Enables tracing: API → Intelligence → Pipelines → Outcomes
- Distributed tracing captures D1↔D3 latency and throughput

---

## 🔍 Why D1↔D3 Direct Connections Matter

### 1. **Learning Efficiency**
- Pipeline traces flow directly to Learning Loop without Cognitive Core overhead
- Reduces latency for episodic → semantic consolidation feedback
- Enables real-time learning adaptation

### 2. **Metadata Performance**
- Query Facade provides fast access to intelligence metadata
- Avoids Working Memory state synchronization overhead
- Critical for UI responsiveness (learning progress, confidence scores)

### 3. **Administrative Control**
- Admin API directly controls Intelligence Policy Guard
- Enables rapid policy updates, overrides, emergency shutdowns
- Bypasses Cognitive Core gating for admin operations

### 4. **Prospective Planning**
- Intelligence Coordinator directly signals P05 for prospective workflows
- Avoids Global Workspace broadcast overhead
- Enables efficient intention formation and cue monitoring

### 5. **QoS & Safety**
- Intelligence Guards directly signal P17 (QoS) and P18 (Safety)
- Ensures rapid response to cost overruns and safety threats
- Critical for production reliability

### 6. **Observability**
- intelligence.* topics flow directly to P19 and SSE
- Enables real-time intelligence monitoring without D2 intermediary
- Critical for debugging and performance optimization

---

**End of Diagram 8 (D1↔D3 Connection)**

---

---

# 📝 Complete Architecture Overview

## ✅ All 8 Diagrams Processed! 🎉

- ✅ **Diagram 1**: API & Pipeline Architecture (Memory Backbone, 20 Pipelines, Events Bus)
- ✅ **Diagram 2**: Cognitive Core (Hippocampus, Attention Gate, Working Memory, Global Workspace)
- ✅ **Diagram 3**: Intelligence Systems (Learning, Social Cognition, Metacognition, Advisory Action)
- ✅ **Diagram 4**: Infrastructure (Consolidation, Knowledge Graph, Sync, Security, Observability)
- ✅ **Diagram 5**: D1↔D2 Connection Circuit (API/Cognitive Core wiring)
- ✅ **Diagram 6**: D2↔D3 Connection Circuit (Cognitive/Intelligence wiring)
- ✅ **Diagram 7**: D3↔D4 Connection Circuit (Intelligence/Infrastructure wiring)
- ✅ **Diagram 8**: D1↔D3 Connection Circuit (API/Intelligence direct path)

---

## 🧠 Complete Cognitive Architecture Summary

### Memory-Centric Foundation (D1)

- **Memory Backbone**: Device-local SQLite with E2EE sync
- **3 API Planes**: Agent, Tool, Control — all serve Memory operations
- **20 Pipelines**: P01-P20 coordinate cognitive workflows
- **Events Bus**: Central nervous system with cognitive_trace_id correlation
- **Policy Framework**: MLS bands, family-aware, PII minimization

### Cognitive Processing Core (D2)

- **Hippocampus**: DG (pattern separation) → CA3 (pattern completion) → CA1 (memory formation)
- **Attention Gate (Thalamus)**: 4 modes (Monitor, Focus, Exploration, Task-Switch) with family-aware salience
- **Working Memory (Prefrontal Cortex)**: 3 tiers (High/Medium/Low priority) with 7±2 capacity
- **Global Workspace**: Broadcasts cognitive state to agents/apps via SSE
- **Cognitive Control (ACC)**: Conflict monitoring, task prioritization, attention modulation
- **Affect Processing (Limbic)**: Real-time affect classification, valence/arousal, affect-aware retrieval

### Intelligence Layer (D3 — Advisory Only)

- **Learning Loop**: Episodic → Semantic consolidation, meta-learning, feedback-driven adaptation
- **Social Cognition**: Theory of Mind (belief attribution), perspective-taking, shared attention
- **Metacognition**: Confidence assessment, monitoring/control, strategy selection
- **Reward Systems**: Dopaminergic reward prediction, goal salience, motivation
- **Procedural Memory**: Skill learning, habit formation, context-dependent execution
- **Imagination (DMN)**: Prospective simulation, counterfactual reasoning, creative exploration
- **Advisory Action**: Decision recommendation + action coordination → **P04 only** (guarded: Policy → QoS → Safety)
- **Affect Intelligence**: Emotional regulation strategies, empathy modeling, mood tracking

### Infrastructure Support (D4)

- **Consolidation & Replay**: Sleep-coordinated consolidation (Episodic, Semantic, Procedural, Emotional), hippocampal replay
- **Knowledge Graph**: Temporal reasoning, causal graph, concept evolution, relation discovery
- **Prospective Memory**: Intention formation, cue monitoring, 3 types (Time/Event/Activity-Based)
- **Edge Sync**: CRDT conflict resolution, federated learning, offline intelligence
- **ML Adaptation**: Continual learning, meta-learning, user modeling
- **Security & Safety**: Threat detection, MLS enforcement, E2EE, Zero Trust
- **Policy & Privacy**: Policy Rules Engine, Privacy Budget, PII Minimizer (P10), redaction
- **Observability**: Cognitive Metrics, Intelligence Dashboard, Distributed Tracing, Behavioral Analytics

### Cross-Cutting Connections (D5-D7)

- **D1↔D2 (Diagram 5)**: Dual-path (fast/smart), API → Cognitive Core, Write → Hippocampus, Recall → Retrieval
- **D2↔D3 (Diagram 6)**: Cognitive Core → Intelligence Memory, Advisory signals (guarded) → P04 only
- **D3↔D4 (Diagram 7)**: Intelligence → EventBus → Infrastructure, Specialized stores → Canonical stores, Observability integration

---

## 🔑 Unified Architectural Principles (D1-D7)

1. **Memory-Centric**: All systems serve Memory Backbone operations (device-local SQLite + E2EE sync)
2. **Brain-Inspired**: Hippocampus (DG→CA3→CA1), Thalamus (Attention Gate), Prefrontal Cortex (Working Memory), ACC (Cognitive Control), Limbic (Affect), DMN (Imagination)
3. **Dual-Path Processing**: Fast path (confident) + Smart path (deliberative/gated)
4. **Advisory Intelligence**: Intelligence Systems emit advisory signals only; P04 is sole executor (guarded: Policy → QoS → Safety)
5. **Event-Driven**: All systems communicate via EventBus with cognitive_trace_id correlation
6. **Family-Aware**: Family relationships, MLS bands, shared attention respected throughout
7. **Observable**: Comprehensive tracing (cognitive_trace_id), metrics (Cognitive Dashboard), behavioral analytics
8. **Secure & Private**: E2EE, MLS, Zero Trust, PII minimization (P10), redaction audit logs
9. **Adaptive**: ML-driven adaptation (continual learning, meta-learning, user modeling)
10. **Resilient**: Outbox pattern, WAL, DLQ, conflict resolution (CRDT), offline intelligence

---

🎉 **7 diagrams complete!** The architecture now covers the full cognitive stack from API to Infrastructure, plus all cross-cutting connection circuits.

**Ready for Diagram 8 (final) when provided!** 🚀
