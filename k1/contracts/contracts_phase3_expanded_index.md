# Phase 3 Expanded Contracts Index
**Status:** Production-Ready Specifications | **Last Updated:** 2025-10-16 | **Total Contracts:** 30 | **Total Lines:** ~30,000

---

## 🎯 Quick Navigation

### Layer Organization
- **Layer 1: Core K1 Kernel** - 9 contracts (agent fabric, orchestrator, planner, protocol monitor, learning loop, session state, KV cache, tool runner, streaming)
- **Layer 2: State & Persistence** - 6 contracts (receipts, K0 bridge, memory mgmt, saga pattern, config mgmt, observability)
- **Layer 3: Execution & Tools** - 3 contracts (model hub, MCP gateway, context manager)
- **Layer 4: Ingress & Voice** - 3 contracts (API gateway, WebSocket, voice pipeline)
- **Layer 5: Infrastructure** - 6 contracts (thermal manager, backpressure, circuit breaker, performance budget, barge-in, N/A)
- **Privacy & Security** - 4 contracts (hybrid detection, AES-256-GCM encryption, AWS KMS key mgmt, vault operations)

---

## Layer 1: Core K1 Kernel (9 Contracts)

### 1. C_K1_AGENT_FABRIC_001 - Agent Lifecycle FSM
**File:** `/contracts/kernel/agent_fabric_lifecycle_fsm.yml`

**Purpose:** Define 6-state agent lifecycle (PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED) with supervisor functions and health monitoring.

**Key Content:**
- 4 supervisor functions: init_agent, monitor_health, health_check, deanimate_agent
- State transition rules with 80ms timeout
- Hiring score calculation (capability match + thermal score)
- 3-strike crash detection (600ms window)
- Performance budget: <2ms supervisor overhead per agent
- Error handling: Automatic deanimate on 3 crashes

**Compliance Refs:** Actor Model (Hewitt 1973), Capabilities (Dennis & Van Horn 1966)

**Integration Points:**
- Orchestrator (hiring agents for tasks)
- Learning loop (advisor feedback on hiring decisions)
- Thermal manager (resource constraints)
- Performance monitoring (P95 latency <10ms)

---

### 2. C_K1_ORCHESTRATOR_3PHASE_002 - Contract Net Protocol
**File:** `/contracts/kernel/orchestrator_3phase_coordination.yml`

**Purpose:** Implement Contract Net Protocol for multi-agent task coordination with ranked fallback chain.

**Key Content:**
- Phase 1 Negotiation: Score agents (capability + thermal), rank by score
- Phase 2 Selection: Choose top-ranked agent, or fallback to next in chain
- Phase 3 Execution: Execute task, collect results, handle failures
- Fallback chain: Up to 5 agents can attempt same task
- E2E latency budget: 2000ms P95
- Error handling: Task rejection, agent failure, timeout recovery

**Compliance Refs:** Contract Net Protocol (Smith 1980), Multi-agent Coordination

**Integration Points:**
- Agent fabric (hiring agents)
- Planner (generating tasks)
- Protocol monitor (validating execution protocol)
- Performance tracking (E2E latency monitoring)

---

### 3. C_K1_PLANNER_4STAGE_003 - LLM + Deterministic Planning
**File:** `/contracts/kernel/planner_4stage_pipeline.yml`

**Purpose:** Define 4-stage planning pipeline (Sketch→Expand→Validate→Commit) with LLM + deterministic validation.

**Key Content:**
- Stage 1 Sketch: LLM generates plan outline (1000-5000 tokens, 100ms budget)
- Stage 2 Expand: Deterministic decomposition into subtasks (max 8 subtasks)
- Stage 3 Validate: Rule-based constraints + arbiter fallback for conflicts
- Stage 4 Commit: Update SessionState with committed plan
- Error handling: Fallback to generic plan, retry with simpler prompt
- Performance: Total <500ms for plan generation

**Compliance Refs:** Planning theory, LLM reasoning, constraints

**Integration Points:**
- Model hub (LLM selection + fallback)
- Context manager (prompt construction)
- Session state (plan storage)
- Arbitration (conflict resolution)

---

### 4. C_K1_PROTOCOL_MONITOR_004 - MPST/Scribble Validation
**File:** `/contracts/kernel/protocol_monitor_mpst_validation.yml`

**Purpose:** Validate 6 core protocols with MPST (Multiparty Session Types) to ensure interaction safety.

**Key Content:**
- 6 Core Protocols:
  1. Agent Hire (120s timeout): Negotiation → Hiring
  2. Task Execution (Per-task timeout): Execute → Complete
  3. Clarification (30s timeout): Query → Response
  4. Barge-In (5s timeout): Detection → Interruption
  5. Tool Call (3s timeout): Invoke → Result
  6. Saga Rollback (5min timeout): Compensation sequence
- MPST validation: Sequence checks, property checks, timeout enforcement
- Error handling: Protocol violations logged as SECURITY_INCIDENT
- Performance: <1ms overhead for protocol validation

**Compliance Refs:** MPST (Honda et al. 2008), Session Types, Protocol Safety

**Integration Points:**
- All interaction protocols
- Security monitor (incident logging)
- Timeout manager (deadline enforcement)

---

### 5. C_K1_LEARNING_LOOP_005 - Adaptive Intelligence
**File:** `/contracts/kernel/learning_loop_adaptive_intelligence.yml`

**Purpose:** Implement feedback collection and adaptive learning with config hot-reload.

**Key Content:**
- Feedback signals:
  - Explicit: User ratings (weight 1.0)
  - Implicit: Task completion (weight 0.5)
  - Behavioral: Token patterns (weight 0.2)
- Model update: Monthly with A/B testing (2% rollout)
- Gradual rollout: 2% → 5% → 10% → 100% with error rate monitoring
- Auto-rollback: If error rate > 2% at any stage
- Drift detection: Statistical comparison to baseline
- Performance: <10ms to evaluate feedback signal

**Compliance Refs:** Reinforcement Learning (Sutton & Barto 2018), Adaptive systems

**Integration Points:**
- Config manager (hot-reload)
- Observability (drift detection metrics)
- Model hub (model selection)

---

### 6. C_K1_SESSION_STATE_006 - 6-Section Memory Structure
**File:** `/contracts/kernel/session_state_6section_memory.yml`

**Purpose:** Define SessionState with 6 sections (beliefs, scoreboard, control, persona, multimodal, meta) and 3-tier memory eviction.

**Key Content:**
- 6 Sections:
  1. Beliefs: User intent, conversation history, inferred preferences
  2. Scoreboard: Metrics (correct answers, latency), decisions made
  3. Control: Current plan, execution state, next action
  4. Persona: User context, conversation style, preferences
  5. Multimodal: Embeddings, images, voice characteristics
  6. Meta: trace_id, timing info, error flags
- 3-Tier Eviction:
  1. LRU: Ephemeral session data (oldest first)
  2. Priority: Important user preferences (keep longer)
  3. Persistent: Critical beliefs (never evict)
- Load/save latency: <1ms with FlatBuffers
- Size budget: 64KB soft / 100KB hard per session

**Compliance Refs:** Memory management, Actor state, Isolation

**Integration Points:**
- KV cache (placement of hot data)
- Memory manager (eviction coordination)
- Observability (session size monitoring)

---

### 7. C_K1_KV_CACHE_MGMT_007 - KV Cache Thermal Placement
**File:** `/contracts/kernel/kv_cache_thermal_placement.yml`

**Purpose:** Manage KV cache placement across thermal tiers (NPU>GPU>CPU>Remote) with hit rate optimization.

**Key Content:**
- Thermal Tiers:
  1. NPU (fastest, ~2MB): Embeddings, recent traces
  2. GPU (fast, ~10MB): Active sessions, model weights
  3. CPU (medium, ~40MB): Warm sessions, recent queries
  4. Remote (slow, ~76MB): Cold sessions, archived data
- Hit rate target: 75%
- Placement policy: Frequency + recency (LFU + LRU hybrid)
- Eviction strategy: Tier-based (evict from coldest first)
- Latency: Hit <1ms, Miss 10-100ms (tier dependent)
- Total budget: 128MB across all tiers

**Integration Points:**
- Session state (data placement)
- Observability (hit rate monitoring)
- Thermal manager (resource constraints)

---

### 8. C_K1_TOOL_RUNNER_008 - Tool Execution Lifecycle
**File:** `/contracts/kernel/tool_runner_execution_lifecycle.yml`

**Purpose:** Define tool execution with pre-execution checks, timeout enforcement, and post-execution validation.

**Key Content:**
- Pre-execution:
  - Permission check (capability matrix)
  - Input validation (JSON schema)
  - Authorization verify (user context)
- Execution:
  - Timeout: 3s budget per tool
  - Error recovery: Retry with backoff (3 attempts)
  - Streaming: Results streamed as available
- Post-execution:
  - Output validation (schema compliance)
  - Result caching (60s TTL)
  - Audit logging (tool calls logged)
- Performance: <100ms overhead per tool call

**Integration Points:**
- MCP gateway (tool discovery/invocation)
- Authorization layer (permission checks)
- Streaming engine (result streaming)

---

### 9. C_K1_STREAMING_ENGINE_009 - Token Streaming
**File:** `/contracts/kernel/streaming_engine_token_delivery.yml`

**Purpose:** Stream LLM tokens to client with latency guarantees and backpressure handling.

**Key Content:**
- Streaming: Token delivered every 100ms (10 tokens/sec baseline)
- Latency budget: 100ms per token delivery
- Backpressure cascade: If client slow, apply cascade rules
- Format: JSON lines ({"token": "...", "timestamp": "..."})
- Connection handling: Graceful shutdown on disconnect
- Performance: <2ms overhead per token

**Integration Points:**
- Model hub (token generation)
- WebSocket gateway (delivery transport)
- Backpressure cascade (flow control)

---

## Layer 2: State & Persistence (6 Contracts)

### 10. C_K1_RECEIPT_SYSTEM_010 - Distributed Tracing & Receipts
**File:** `/contracts/state_persistence/receipt_system_tracing.yml`

**Purpose:** Create immutable receipts (decision records) for audit trail and debugging.

**Key Content:**
- Receipt structure:
  - Receipt ID: UUID
  - Decision: Decision made (SHA-256 hash)
  - Outcome: Result achieved
  - Timestamp: When made
  - Trace ID: Request trace
- Receipt ledger: Append-only log
- Queries: By trace_id for full decision path
- Retention: 90 days (compliance archive)
- Performance: Insert <1ms, Query <10ms

**Integration Points:**
- Protocol monitor (receipt generation on protocol completion)
- Observability (audit trail queries)
- Compliance (decision audit trail)

---

### 11. C_K1_K0_BRIDGE_011 - K0 Integration & Batching
**File:** `/contracts/state_persistence/k0_bridge_integration.yml`

**Purpose:** Integrate K1 with K0 intelligence backend using batching and backpressure.

**Key Content:**
- Batching:
  - Max batch size: 100 operations
  - Max latency: 50ms
  - Trigger: Either condition met first
- Polling: 500ms heartbeat for K0 availability
- Backpressure: Circuit breaker at 95% K0 capacity
- Error handling: Retry with exponential backoff (3 attempts)
- Performance: Batching reduces latency by 10-20x vs. individual calls

**Integration Points:**
- Any K0 calls from K1
- Circuit breaker (capacity monitoring)
- Observability (batch metrics)

---

### 12. C_K1_MEMORY_MANAGER_012 - Memory Eviction Policies
**File:** `/contracts/state_persistence/memory_manager_eviction.yml`

**Purpose:** Implement 3-tier memory eviction (LRU/Priority/Persistent) with threshold-based triggering.

**Key Content:**
- Tier 1 LRU: Session ephemeral data (oldest first)
- Tier 2 Priority: Important user preferences (keep longer)
- Tier 3 Persistent: Critical beliefs (never evict)
- Eviction triggered: At 85% memory threshold
- Eviction amount: 10% of memory per trigger
- Performance: Eviction <100ms

**Integration Points:**
- Session state (data classification by tier)
- KV cache (affected by eviction)
- Thermal manager (memory monitoring)

---

### 13. C_K1_SAGA_PATTERN_013 - Distributed Transaction Management
**File:** `/contracts/state_persistence/saga_pattern_compensation.yml`

**Purpose:** Implement Saga pattern for distributed transactions with forward rollback.

**Key Content:**
- Forward rollback strategy (vs. backward): Undo via compensation
- Saga structure:
  - Steps: Up to 10 steps per saga
  - Compensation: Reverse action for each step
  - Timeout: 30s per step, 5min total
- Execution: Sequential or parallel (per saga config)
- Error handling: On failure, execute all compensation steps in reverse
- Audit logging: Full saga_log table with all steps
- Performance: <50ms overhead for saga coordination

**Compliance Refs:** Saga Pattern (Garcia-Molina 1987), distributed transactions

**Integration Points:**
- Any multi-step operations (tool chains, workflows)
- Protocol monitor (saga protocol validation)
- Audit logging

---

### 14. C_K1_CONFIG_MGMT_014 - Configuration Hot-Reload
**File:** `/contracts/state_persistence/config_mgmt_hot_reload.yml`

**Purpose:** Enable config hot-reload with gradual rollout and auto-rollback on errors.

**Key Content:**
- Config validation:
  - Schema validation (JSON Schema)
  - Rule validation (custom rules)
- Gradual rollout:
  - Stage 1: 2% of requests
  - Stage 2: 5% of requests
  - Stage 3: 10% of requests
  - Stage 4: 100% rollout
  - Monitor 5min at each stage
- Auto-rollback: If error rate > 2% at any stage
- Performance: <100ms config load time

**Integration Points:**
- Learning loop (model config updates)
- All K1 components (config consumers)
- Observability (error rate monitoring)

---

### 15. C_K1_OBSERVABILITY_015 - Metrics, Traces, Logs
**File:** `/contracts/state_persistence/observability_metrics_tracing.yml`

**Purpose:** Comprehensive observability with Prometheus metrics, OpenTelemetry traces, and structured logging.

**Key Content:**
- Prometheus Metrics:
  - Counters: agent_transitions_total, tool_calls_total, errors_total
  - Histograms: latency_ms, token_count, model_latency_ms
  - Gauges: active_agents, memory_usage_mb, cache_hit_rate
- OpenTelemetry Traces:
  - Span per major operation (orchestration, planning, tool calls)
  - Trace ID: cognitive_trace_id in all logs
- Structured Logging:
  - JSON format with trace_id, user_id, component, level
  - Debug level includes full state snapshots

**Integration Points:**
- All K1 components (instrumentation)
- Monitoring dashboards (Grafana)
- Alerting (error rate, latency)

---

## Layer 3: Execution & Tools (3 Contracts)

### 16. C_K1_MODEL_HUB_016 - Model Selection & Fallback
**File:** `/contracts/execution_tools/model_hub_fallback_chain.yml`

**Purpose:** Manage model selection with automatic fallback chain based on latency and errors.

**Key Content:**
- Primary model: GPT-4o (latency budget: 100ms)
- Fallback 1: Claude-Opus (latency budget: 125ms)
- Fallback 2: Local 7B model (latency budget: 200ms)
- Selection criteria:
  - Try primary first
  - On error/timeout, try fallback 1
  - On error/timeout, try fallback 2
  - If all fail, return error
- Performance tracking: Latency histograms per model
- A/B testing: Can test new models in 2% rollout

**Integration Points:**
- Planner (LLM usage)
- Context manager (prompt optimization)
- Observability (model performance metrics)

---

### 17. C_K1_MCP_GATEWAY_017 - Tool Protocol Integration
**File:** `/contracts/execution_tools/mcp_gateway_tool_protocol.yml`

**Purpose:** Gateway for MCP (Model Context Protocol) tool discovery and invocation.

**Key Content:**
- Tool discovery: Dynamic tool list from MCP servers
- Tool invocation: JSON-RPC 2.0 protocol
- Timeout enforcement: 3s per tool call
- Result handling:
  - Parse JSON response
  - Validate against schema
  - Return to model
- Error handling: Tool errors returned as structured JSON

**Integration Points:**
- Tool runner (execution wrapper)
- Context manager (tool selection)
- Observability (tool performance)

---

### 18. C_K1_CONTEXT_MANAGER_018 - LLM Context Window Optimization
**File:** `/contracts/execution_tools/context_manager_window_optimization.yml`

**Purpose:** Optimize LLM context selection (recent, relevant, dense) within token budget.

**Key Content:**
- Context selection strategy:
  1. Recent (highest priority): Last N messages
  2. Relevant (semantic): Top-k similar from memory bank
  3. Dense (summary): Compressed history if needed
- Token budget: 6000/8000 tokens reserved for output
- Retrieval: Semantic search in memory bank
- Performance: <50ms to construct context

**Integration Points:**
- Session state (conversation history)
- Memory manager (semantic search)
- Model hub (token counting)

---

## Layer 4: Ingress & Voice (3 Contracts)

### 19. C_K1_API_GATEWAY_019 - REST API Gateway
**File:** `/contracts/ingress_voice/api_gateway_rest_protocol.yml`

**Purpose:** Handle REST API requests with rate limiting, validation, and error responses.

**Key Content:**
- Rate limiting: 100 req/sec per user (token bucket)
- Request validation: JSON Schema validation
- Response serialization: JSON format
- Error response: Structured error with error_code + message
- Authentication: Bearer token validation
- Performance: <10ms overhead per request

**Integration Points:**
- Any REST consumers
- Rate limiting layer
- Error handling layer

---

### 20. C_K1_WEBSOCKET_GATEWAY_020 - WebSocket Protocol
**File:** `/contracts/ingress_voice/websocket_gateway_streaming.yml`

**Purpose:** Handle WebSocket connections for streaming responses and real-time interaction.

**Key Content:**
- Connection lifecycle:
  - Handshake: Upgrade to WebSocket
  - Keepalive: Ping every 30s
  - Messages: Text/binary frames
  - Close: Graceful shutdown with close frame
- Timeout: 1 hour connection idle timeout
- Performance: <1ms frame processing

**Integration Points:**
- Streaming engine (token delivery)
- Session state (per-connection state)

---

### 21. C_K1_VOICE_PIPELINE_021 - Voice Input/Output
**File:** `/contracts/ingress_voice/voice_pipeline_speech_io.yml`

**Purpose:** Handle voice input (speech recognition) and output (TTS synthesis).

**Key Content:**
- Speech recognition (Whisper API):
  - Latency budget: 2s
  - Error: Fallback to text input
- Voice activity detection (VAD):
  - Detect silence (< -40dB threshold)
  - Timeout: 3s of silence ends recording
- TTS synthesis (ElevenLabs API):
  - Latency budget: 1s
  - Voice selection: Per-user preference
- Performance: 2s recognition + 1s synthesis = 3s total

**Integration Points:**
- Ingress (audio input)
- Response generation (text to speech)

---

## Layer 5: Infrastructure (6 Contracts)

### 22. C_K1_THERMAL_MANAGER_022 - Resource Thermal Management
**File:** `/contracts/infrastructure/thermal_manager_resource_scaling.yml`

**Purpose:** Monitor and manage system thermal state (CPU, memory, GPU) with scaling decisions.

**Key Content:**
- Thermal thresholds:
  - CPU >80%: Scale out agents
  - Memory >85%: Trigger memory eviction
  - GPU >90%: Reject new model requests
  - Network >75%: Slow down ingress (backpressure L1)
- Actions:
  - Scale: Spin up new agents, add cache capacity
  - Evict: Trigger memory eviction
  - Throttle: Reduce incoming requests
- Performance: <1ms to evaluate thermal state

**Integration Points:**
- Agent fabric (agent scaling)
- Memory manager (eviction trigger)
- Backpressure cascade (throttling)
- Observability (thermal_level metric)

---

### 23. C_K1_BACKPRESSURE_CASCADE_023 - Cascading Backpressure
**File:** `/contracts/infrastructure/backpressure_cascade_flowcontrol.yml`

**Purpose:** Implement 4-level backpressure cascade for overload protection.

**Key Content:**
- Level 1 (Ingress): Slow API acceptance (100→50 req/s)
- Level 2 (Tool Queue): Increase timeout tolerance, prioritize high-value tasks
- Level 3 (Model Queue): Fallback to faster models
- Level 4 (Emergency): Reject non-critical requests (keep only critical intent types)
- Trigger: Thermal manager detects threshold exceeded
- Recovery: Gradually restore when thermal state normalizes

**Integration Points:**
- Thermal manager (trigger)
- API gateway (rate limiting adjustment)
- Tool runner (queue management)
- Model hub (model fallback)

---

### 24. C_K1_CIRCUIT_BREAKER_024 - Failure Recovery
**File:** `/contracts/infrastructure/circuit_breaker_resilience.yml`

**Purpose:** Implement circuit breaker pattern for resilience to cascading failures.

**Key Content:**
- States:
  - CLOSED (normal): Requests pass through
  - OPEN (failures detected): Reject requests, fail fast
  - HALF_OPEN (recovery): Test with limited requests
- Open threshold: 5 failures in 60s
- Half-open timeout: 30s (after which back to CLOSED if successful)
- Reset: On successful request in HALF_OPEN state
- Performance: <1ms state check

**Integration Points:**
- K0 bridge (external system calls)
- KMS gateway (external service calls)
- Model hub (LLM API calls)

---

### 25. C_K1_PERFORMANCE_BUDGET_025 - Performance Governance
**File:** `/contracts/infrastructure/performance_budget_governance.yml`

**Purpose:** Define and enforce performance budgets for all latency-critical operations.

**Key Content:**
- Budgets (P95 targets):
  - TTFT (Time to First Token): 150ms
  - E2E Turn Latency: 2000ms
  - Intent Classification: 50ms
  - Tool Call: 3000ms
  - Config Reload: 100ms
  - Barge-in Latency: 120ms
- Memory budgets:
  - SessionState: 64KB soft / 100KB hard
  - KV Cache: 128MB total
  - K1 Memory: 500MB total
- Tracking: Prometheus histograms with automated alerts

**Integration Points:**
- All latency-sensitive components
- Observability (metrics tracking)
- Alerting (budget violations)

---

### 26. C_K1_BARGE_IN_026 - Interruption Handling
**File:** `/contracts/infrastructure/barge_in_interruption_handling.yml`

**Purpose:** Handle user interruption (barge-in) with <120ms latency.

**Key Content:**
- Detection: User speech during agent turn
- Latency budget: <120ms from detection to response
- Actions:
  - Cancel in-flight operations (model generation, tool calls)
  - Rollback session state to pre-operation
  - Queue new request for processing
- Fallback: If cannot interrupt, queue new request
- Performance: <50ms state rollback

**Integration Points:**
- Voice pipeline (speech detection)
- Session state (state management)
- Protocol monitor (barge-in protocol validation)

---

## Privacy & Security Layer (4 Contracts)

### 27. C_PRIVACY_HYBRID_DETECTION_027 - PII Detection at Inference
**File:** `/contracts/privacy/hybrid_detection/pii_detection_hybrid_realtime.yml`

**Purpose:** Real-time PII detection using regex + ML model hybrid approach.

**Key Content:**
- Detection method:
  - Regex patterns (patterns for SSN, email, phone, etc.)
  - ML model (BERT-based classifier for context)
  - Ensemble: Combined confidence score
- PII types (8 classes):
  - SSN (Social Security Number)
  - Email, Phone, Name, Address, DOB (Date of Birth), Credit Card, Misc
- Entity extraction:
  - Location in text (character offsets)
  - Confidence scores
- Performance budget: <10ms per turn
- Accuracy targets: 99.5% precision, 95% recall

**Compliance Refs:** GDPR (Article 32), HIPAA (164.312), PII protection

**Integration Points:**
- Inference pipeline (post-generation detection)
- Vault operations (storage of detected PII)
- Session state (redaction in logs)

---

### 28. C_PRIVACY_AES256GCM_ENCRYPTION_028 - AES-256-GCM Encryption
**File:** `/contracts/privacy/encryption/aes256gcm_encryption_specification.yml`

**Purpose:** Specify AES-256-GCM encryption for PII at rest and in transit.

**Key Content:**
- Algorithm: AES-256-GCM (authenticated encryption)
- Nonce: 96-bit random (12 bytes) per encryption
- Ciphertext: Variable length (same as plaintext)
- Auth tag: 16 bytes (GCM authentication tag)
- Key source: AWS KMS (never stored locally)
- Performance: <2ms for encrypt/decrypt
- Error handling: Auth tag validation on decrypt (detects tampering)

**Compliance Refs:** NIST SP 800-38D (GCM specification)

**Integration Points:**
- Vault operations (encryption of stored PII)
- KMS integration (key derivation)

---

### 29. C_PRIVACY_AWS_KMS_KEY_MGMT_029 - AWS KMS Key Management
**File:** `/contracts/privacy/key_management/aws_kms_key_management.yml`

**Purpose:** Manage master and data keys using AWS KMS for defense in depth.

**Key Content:**
- Master key: Stored in AWS KMS HSM (never leaves HSM)
- Data keys: Ephemeral (derived per operation)
- Key rotation: Annual (automated)
- Key material export: Prohibited (policy enforced)
- Audit logging:
  - All key operations logged to CloudTrail
  - Accessible via AWS console + API
- Performance: 40-60ms for KMS API calls

**Compliance Refs:** NIST SP 800-57 (key management), AWS KMS best practices

**Integration Points:**
- Vault operations (encryption/decryption)
- Audit logging (KMS operations)

---

### 30. C_PRIVACY_VAULT_OPS_STORE_RETRIEVE_DELETE_030 - Vault Operations
**File:** `/contracts/privacy/vault/vault_operations_store_retrieve_delete.yml`

**Purpose:** Core vault operations (Store/Retrieve/Delete) with GDPR compliance.

**Key Content:**

#### Store Operation
- Process: Generate nonce → Request data key → Encrypt PII → Insert to vault
- Inputs: pii_value, pii_type, user_id, space_id, trace_id
- Output: vault_key (e.g., 'ssn_user001_abc123_1697486565000')
- Latency: 55ms total (KMS 50ms + encrypt 1.8ms + DB 2.5ms + audit 0.5ms)
- Error handling: KMS retry (3×), vault_key collision retry (1×)

#### Retrieve Operation
- Process: Lookup vault entry → Authorization check → KMS decrypt → Decrypt PII → Update audit trail
- Inputs: vault_key, user_id, space_id, trace_id
- Output: Plaintext PII value
- Latency: 53.6ms total (KMS 50ms + decrypt 0.9ms + DB 1.5ms + audit 0.5ms)
- Authorization: Must own PII (user_id match)
- Error handling: Authorization failure logs SECURITY_INCIDENT

#### Delete Operation (GDPR Right to Erasure)
- Process: Verify authorization → Soft delete (set deleted_at) → Audit log
- Grace period: 30 days (soft delete) → Hard delete (automated)
- Latency: 2.8ms total
- Error handling: Already deleted is idempotent (returns success)
- Recovery: Contact support within 30 days to undo deletion

**Compliance:** GDPR Article 17 (right to erasure), HIPAA (encryption + audit trail)

**Integration Points:**
- Hybrid detector (identifies PII to be vaulted)
- Session state (stores vault_key, not plaintext)
- Audit logging (compliance reporting)

---

## 📊 Quick Reference Table

| Contract ID | Layer | Name | File | Latency Budget | Key Integration |
|---|---|---|---|---|---|
| C_K1_AGENT_FABRIC_001 | L1 | Agent Lifecycle FSM | agent_fabric_lifecycle_fsm.yml | <2ms/agent | Orchestrator |
| C_K1_ORCHESTRATOR_3PHASE_002 | L1 | 3-Phase Coordination | orchestrator_3phase_coordination.yml | 2000ms E2E | Agent Fabric |
| C_K1_PLANNER_4STAGE_003 | L1 | 4-Stage Planning | planner_4stage_pipeline.yml | <500ms | Model Hub |
| C_K1_PROTOCOL_MONITOR_004 | L1 | Protocol Validation | protocol_monitor_mpst_validation.yml | <1ms | All interactions |
| C_K1_LEARNING_LOOP_005 | L1 | Adaptive Learning | learning_loop_adaptive_intelligence.yml | <10ms | Config Mgmt |
| C_K1_SESSION_STATE_006 | L1 | Memory Structure | session_state_6section_memory.yml | <1ms | All components |
| C_K1_KV_CACHE_MGMT_007 | L1 | Cache Management | kv_cache_thermal_placement.yml | Hit <1ms | Session State |
| C_K1_TOOL_RUNNER_008 | L1 | Tool Execution | tool_runner_execution_lifecycle.yml | <100ms | MCP Gateway |
| C_K1_STREAMING_ENGINE_009 | L1 | Token Streaming | streaming_engine_token_delivery.yml | 100ms/token | WebSocket Gateway |
| C_K1_RECEIPT_SYSTEM_010 | L2 | Audit Trail | receipt_system_tracing.yml | <1ms insert | All protocols |
| C_K1_K0_BRIDGE_011 | L2 | K0 Integration | k0_bridge_integration.yml | <50ms batch | K0 calls |
| C_K1_MEMORY_MANAGER_012 | L2 | Memory Eviction | memory_manager_eviction.yml | <100ms | Session State |
| C_K1_SAGA_PATTERN_013 | L2 | Transactions | saga_pattern_compensation.yml | 30s/step | Multi-step ops |
| C_K1_CONFIG_MGMT_014 | L2 | Hot Reload | config_mgmt_hot_reload.yml | <100ms | All components |
| C_K1_OBSERVABILITY_015 | L2 | Metrics/Traces | observability_metrics_tracing.yml | <1ms | All components |
| C_K1_MODEL_HUB_016 | L3 | Model Selection | model_hub_fallback_chain.yml | 100-200ms | Planner |
| C_K1_MCP_GATEWAY_017 | L3 | Tool Gateway | mcp_gateway_tool_protocol.yml | 3s/tool | Tool Runner |
| C_K1_CONTEXT_MANAGER_018 | L3 | Context Optimization | context_manager_window_optimization.yml | <50ms | Model Hub |
| C_K1_API_GATEWAY_019 | L4 | REST API | api_gateway_rest_protocol.yml | <10ms | External clients |
| C_K1_WEBSOCKET_GATEWAY_020 | L4 | WebSocket | websocket_gateway_streaming.yml | <1ms frame | Streaming Engine |
| C_K1_VOICE_PIPELINE_021 | L4 | Voice I/O | voice_pipeline_speech_io.yml | 3s total | Ingress/Response |
| C_K1_THERMAL_MANAGER_022 | L5 | Resource Scaling | thermal_manager_resource_scaling.yml | <1ms eval | Agent Fabric |
| C_K1_BACKPRESSURE_CASCADE_023 | L5 | Flow Control | backpressure_cascade_flowcontrol.yml | Level-dependent | Thermal Manager |
| C_K1_CIRCUIT_BREAKER_024 | L5 | Resilience | circuit_breaker_resilience.yml | <1ms check | External calls |
| C_K1_PERFORMANCE_BUDGET_025 | L5 | Budget Governance | performance_budget_governance.yml | Per-component | Observability |
| C_K1_BARGE_IN_026 | L5 | Interruption | barge_in_interruption_handling.yml | <120ms | Voice Pipeline |
| C_PRIVACY_HYBRID_DETECTION_027 | Security | PII Detection | pii_detection_hybrid_realtime.yml | <10ms | Inference Pipeline |
| C_PRIVACY_AES256GCM_ENCRYPTION_028 | Security | Encryption | aes256gcm_encryption_specification.yml | <2ms | Vault Ops |
| C_PRIVACY_AWS_KMS_KEY_MGMT_029 | Security | Key Management | aws_kms_key_management.yml | 40-60ms | Vault Ops |
| C_PRIVACY_VAULT_OPS_STORE_RETRIEVE_DELETE_030 | Security | Vault Ops | vault_operations_store_retrieve_delete.yml | 55ms store / 54ms get / 3ms delete | All PII handling |

---

## 🔗 Integration Matrix

### Critical Integration Paths

**Path 1: Task Execution (End-to-End)**
```
API Gateway (REST input)
  ↓
Protocol Monitor (interaction validation)
  ↓
Planner (4-stage planning)
  ↓
Orchestrator (3-phase negotiation → selection → execution)
  ↓
Agent Fabric (hire agent for task)
  ↓
Tool Runner (execute tool calls)
  ↓
Streaming Engine (return results)
  ↓
WebSocket Gateway (stream to client)
```

**Path 2: PII Handling (Detection → Encryption → Vault)**
```
Inference Pipeline (generate response)
  ↓
Hybrid Detector (detect PII in generated text)
  ↓
Vault Store (encrypt detected PII)
  ↓
Session State (store vault_key, redact plaintext)
  ↓
Audit Log (compliance trail)
```

**Path 3: Backpressure Cascade (Overload Protection)**
```
API Gateway (high request rate detected)
  ↓
Thermal Manager (evaluate CPU/memory/GPU)
  ↓
Backpressure Cascade (trigger L1/L2/L3/L4)
  ↓
Tool Queue / Model Queue (reduce throughput)
  ↓
Recovery (gradually normalize)
```

---

## 📋 Implementation Roadmap

### Phase 1: Core Kernel (L1 Contracts)
- [ ] Agent Fabric lifecycle FSM
- [ ] Orchestrator 3-phase protocol
- [ ] Planner 4-stage pipeline
- [ ] Protocol Monitor MPST validation
- [ ] Session State 6-section memory

### Phase 2: State & Execution (L2 + L3)
- [ ] Receipts + audit trail
- [ ] K0 Bridge integration
- [ ] Tool Runner lifecycle
- [ ] Model Hub fallback
- [ ] Context Manager optimization

### Phase 3: Ingress & Infrastructure (L4 + L5)
- [ ] API Gateway + WebSocket
- [ ] Thermal Manager + Backpressure
- [ ] Voice Pipeline
- [ ] Performance budgets enforcement
- [ ] Barge-in interruption

### Phase 4: Privacy & Security (All privacy contracts)
- [ ] Hybrid PII detection
- [ ] AES-256-GCM encryption
- [ ] AWS KMS integration
- [ ] Vault operations (store/retrieve/delete)
- [ ] GDPR/HIPAA compliance

---

## 📝 Notes

- **Total lines of specification:** ~30,000 across 30 contracts
- **Performance data:** All latency budgets specified with P95 targets
- **Error handling:** Every contract includes failure scenarios and recovery strategies
- **Compliance:** Privacy/security contracts fully GDPR/HIPAA compliant
- **Testing:** Each contract includes unit + integration + performance test strategies
- **Integration:** Every contract specifies integration points with related systems

---

**Status:** Ready for implementation handoff to engineering teams
**Last Updated:** 2025-10-16
**Maintained By:** K1 Architecture Team