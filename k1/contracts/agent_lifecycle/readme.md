# Agent Lifecycle FSM Contracts

**Source ADR:** [ADR-0005: Agent Lifecycle FSM](https://github.com/your-repo/docs/architecture/decisions/0005-agent-lifecycle-fsm.md)

## Overview

This directory contains contracts for K1's Agent Lifecycle management, implementing the **6-state Finite State Machine (FSM)** that governs agent behavior from creation to termination. The FSM supports both AI agents (with LLM reasoning) and pure actors (deterministic logic).

## Contracts Included

### 1. Lifecycle FSM Contract (`lifecycle_fsm.yml`)
- 6-state FSM: PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
- State definitions with entry/exit actions
- AI agent vs pure actor distinctions
- Supervisor authority model with monotonic clocks

### 2. State Transitions Contract (`state_transitions.yml`)
- Valid transition matrix
- Transition guards and preconditions
- Emergency transitions (any state → TERMINATED)
- Timing constraints and deadlines

### 3. Warming State Contract (`warming_state.yml`)
- AI agent warming: Model loading, KV cache init, prompt loading, tool registration
- Pure actor warming: Config loading, mailbox initialization
- Performance budgets: AI agents <250ms, pure actors <50ms
- Failure handling and timeouts

### 4. Idle Pooling Contract (`idle_pooling.yml`)
- Resource retention policies (model weights kept, caches minimal)
- Reactivation latency target: <50ms (IDLE → ACTIVE)
- TTL management and memory pressure handling
- Quiescence detection (200ms mailbox silence)

### 5. Draining Shutdown Contract (`draining_shutdown.yml`)
- Graceful shutdown process: Finish current task, flush state, revoke capabilities
- Idempotent state flush to K0 with delta compression
- MPST drain enforcement (no new task assignments)
- Timeout policies and forced termination

### 6. Performance Budgets Contract (`performance_budgets.yml`)
- P95 targets for all lifecycle operations
- AI agent vs pure actor performance differences
- Memory budgets and thermal placement
- Observability requirements

## Supervisor Monitoring & Blacklist Contracts

**Source ADR:** [ADR-0005d: Supervisor Monitoring & Blacklist Management](https://github.com/your-repo/docs/architecture/decisions/0005d-supervisor-blacklist.md)

The `supervisor/` subdirectory contains contracts implementing comprehensive supervisor monitoring and blacklist management to prevent cascading failures and ensure system stability.

### 1. Health Monitoring Contract (`supervisor/health_monitoring.yml`)
- Heartbeat monitoring protocol (1Hz checks, 3s timeout)
- Multiple health check types: heartbeat, active ping, event loop monitoring
- Health states: healthy, degraded, critical, dead
- Performance budgets: <1% CPU overhead, <100ms detection latency

### 2. Crash Detection Contract (`supervisor/crash_detection.yml`)
- 6 crash types: OOM, timeout, exceptions, protocol violations, resource exhaustion, thermal overshoot
- <100ms crash detection with immediate reporting
- Recovery procedures: immediate restart, fast recovery, blacklist escalation
- Crash history tracking and pattern analysis

### 3. Blacklist Policy Contract (`supervisor/blacklist_policy.yml`)
- Circuit breaker pattern: 3 crashes in 10-minute window → 1-hour blacklist
- Version-aware blacklisting (agent type + version hash)
- Automatic expiry and manual override capabilities
- Effectiveness: 88% reduction in repeated crashes

### 4. Resource Monitoring Contract (`supervisor/resource_monitoring.yml`)
- Per-agent resource tracking: memory (256MB soft/512MB hard), CPU (80% soft/95% hard)
- 1Hz sampling with pressure thresholds and eviction policies
- Memory leak detection using linear regression
- Fair resource allocation and starvation prevention

### 5. Rollback Strategy Contract (`supervisor/rollback_strategy.yml`)
- 3-phase termination: preparation (100ms), graceful shutdown (5s), force termination (<100ms)
- State preservation and transfer during overlap window
- Complete resource cleanup (memory, handles, connections, IPC)
- Recovery orchestration with zero-downtime replacement

## Supervisor Integration

The supervisor contracts extend the basic lifecycle FSM with robust monitoring and failure management:

- **Health monitoring** ensures agents remain responsive
- **Crash detection** provides fast failure identification
- **Blacklist policy** prevents cascading failures from broken agent types
- **Resource monitoring** maintains system stability under load
- **Rollback strategy** enables clean termination and fast recovery

Together, these contracts implement the "Supervisor as Pure Actor" pattern with comprehensive observability and automatic recovery capabilities.

## Agent Personality & Capabilities Contracts

**Source ADR:** [ADR-0005e: Agent Personality & Capability System](https://github.com/your-repo/docs/architecture/decisions/0005e-agent-personality-capabilities.md)

The `personality/` subdirectory contains contracts implementing comprehensive agent personality definitions and capability-based security for all 58 agents (4 AI agents + 54 pure actors).

### 1. Capability Tokens Contract (`personality/capability_tokens.yml`)
- Unforgeable capability tokens: TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL, NETWORK_ACCESS
- <1ms runtime enforcement with hash table lookups
- Principle of least privilege implementation
- 0.03% capability denial rate (correct configuration)

### 2. Persona Prompts Contract (`personality/persona_prompts.yml`)
- Jinja2 prompt templates for 4 AI agents only (Concierge, Planner, Researcher, Safety Watch)
- Personality-driven prompt engineering with LLM budget enforcement
- Template variables: user_input, session_context, agent_capabilities
- 97-99% LLM calls within budget (50ms-5000ms P95)

### 3. Personality Traits Contract (`personality/personality_traits.yml`)
- Quantitative personality traits: formality (0.0-1.0), verbosity (0.0-1.0), empathy (0.0-1.0)
- AI agents: LLM-based trait expression via prompt injection
- Pure actors: Template-based trait expression via response formatting
- User preference learning and cultural adaptation

### 4. Capability Assignment Contract (`personality/capability_assignment.yml`)
- Role-based capability distribution for all 58 agents
- Least privilege principle: minimum necessary capabilities per agent
- Security rationale documented for each assignment
- Dynamic capability management (revocation, borrowing, conditional access)

### 5. Agent Registry Schema Contract (`personality/agent_registry_schema.yml`)
- YAML schema for complete agent specifications
- JSON Schema validation with business logic rules
- Registry management: loading, validation, versioning
- <10ms registry load time with caching

## Personality System Integration

The personality contracts extend the basic lifecycle FSM with rich agent characterization:

- **Capability tokens** enable fine-grained security enforcement
- **Persona prompts** define AI agent behavior and LLM budgets
- **Personality traits** create consistent, differentiated agent experiences
- **Capability assignments** implement role-based access control
- **Registry schema** provides standardized agent configuration

Together, these contracts implement the "4 AI Personalities + 54 Pure Actors" architecture with comprehensive security and behavioral controls.

## Agent Lifecycle States

Based on ADR-0005, the 6-state FSM supports both AI agents (4 agents: Concierge, Planner, Researcher, Safety Watch) and pure actors (54 deterministic components).

```yaml
lifecycle_states:
  PENDING:
    description: Agent registered in roster but not yet initialized
    entry_actions:
      - Allocate agent_id (UUID)
      - Create AgentLease (caps, bands, budgets, TTL)
      - Add to roster with state=PENDING
    exit_condition: Supervisor invokes agent initialization
    timeout: 5s → TERMINATED (initialization deadlock)
    typical_duration: <10ms

  WARMING:
    description: Agent loading AI models, initializing KV cache, registering tools
    ai_agent_actions:
      - Load LLM/SLM model weights (150-200ms)
      - Load agent persona prompts (5-10ms)
      - Initialize KV cache buffers (20-30ms)
      - Register tools and sandboxes (10-20ms)
      - Run warmup LLM inferences (30-50ms)
    pure_actor_actions:
      - Load configuration from YAML (10-20ms)
      - Initialize mailbox MPSC queue (5ms)
      - Register with supervisor (5ms)
    exit_condition: Warmup complete → ACTIVE
    timeout: 5s → TERMINATED (warmup failed)
    typical_duration:
      ai_agents: 150-250ms (laptop), 300-500ms (phone)
      pure_actors: 20-50ms

  ACTIVE:
    description: Agent ready to accept and execute tasks
    ai_agent_processing: Mailbox receive → LLM reasoning via Model Hub → response
    pure_actor_processing: Mailbox receive → deterministic logic → response
    exit_conditions:
      - No tasks for 60s + mailbox quiescent (200ms) → IDLE
      - FIRE message from orchestrator → DRAINING
      - Crash detected → TERMINATED
    typical_duration: Variable (seconds to minutes)

  IDLE:
    description: Agent has no tasks but remains loaded for fast reactivation
    actions:
      - Reduce non-essential memory (prompt cache, intermediate buffers)
      - Keep model weights and KV cache resident
      - Monitor mailbox for reactivation
      - Periodic health checks (every 1s)
    exit_conditions:
      - New task assigned → ACTIVE (<50ms reactivation)
      - TTL expired (configurable, default 5 min) → DRAINING
      - Memory pressure (>80% heap) → DRAINING (largest RSS first)
      - Thermal overshoot (>T_hot) → DRAINING (thermal contribution)
    typical_duration: 1-5 minutes

  DRAINING:
    description: Agent finishing current task before termination
    actions:
      - Reject new task announcements
      - Complete in-progress work (tool calls, model inference)
      - Flush state to K0 with idempotent deltas
      - Revoke capabilities and leases
      - Notify supervisor of completion
    exit_conditions:
      - Current task complete + state flushed → TERMINATED
      - Timeout (10s) → Forced TERMINATED with warning
    typical_duration: 1-5s (depends on current task)

  TERMINATED:
    description: Agent removed from roster, all resources released
    actions:
      - Unload model weights from NPU/GPU memory
      - Release KV cache buffers
      - Close mailbox and drain queues
      - Remove from active roster
      - Revoke capabilities (including revocation-on-crash)
      - Log termination event to K0
      - Check blacklist threshold (3 crashes in 10 min → 1 hour blacklist)
    exit_condition: None (final state)
    typical_duration: Instantaneous (<50ms)
```

## State Transition Diagram

```
PENDING → WARMING → ACTIVE ⇄ IDLE
    ↓         ↓         ↓       ↓
TERMINATED ←────── DRAINING ←───
    ↑             ↑
    └─────────────┘
  (crash/timeout/kill)
```

**Key Transitions:**
- **PENDING → WARMING:** Supervisor invokes initialization
- **WARMING → ACTIVE:** Warmup complete (AI agents: model loaded, KV cache ready; Pure actors: config loaded)
- **ACTIVE → IDLE:** No tasks for 60s + mailbox quiescent (200ms silence)
- **IDLE → ACTIVE:** New task assigned (<50ms reactivation)
- **ACTIVE/IDLE → DRAINING:** FIRE message, TTL expired, memory pressure, thermal overshoot
- **DRAINING → TERMINATED:** State flushed, capabilities revoked
- **Any state → TERMINATED:** Crash, timeout, kill signal (emergency termination)

## Authority & Clock Model

**CRITICAL:** All lifecycle transitions initiated by Supervisor (single-writer pattern). Agents publish intents/events; Supervisor owns timers using monotonic clocks.

- **Monotonic Clocks:** Prevent timer skew from system clock adjustments
- **Intent-Based:** Agents emit `ready`, `idle_candidate`, `drain_ready`; Supervisor decides transitions
- **Supervisor Authority:** Sole timer owner prevents double-fire bugs

## AI Agent vs Pure Actor Distinctions

| Aspect | AI Agents (4) | Pure Actors (54) |
|--------|---------------|------------------|
| **WARMING Duration** | 150-250ms | 20-50ms |
| **Resource Footprint** | 150MB (model + KV cache) | <10MB (config + mailbox) |
| **ACTIVE Processing** | LLM reasoning via Model Hub | Deterministic logic |
| **Crash Recovery** | Complex (model state, KV cache) | Simple (config reload) |
| **Tool Usage** | ✅ MCP/WASM sandboxes | ✅ Deterministic connectors only (no inference) |
| **Model Hub Integration** | ✅ Required | ❌ NEVER calls Model Hub |

---

**Last Updated:** 2025-10-15
