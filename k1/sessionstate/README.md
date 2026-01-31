# K1 SessionState Kernel

## Overview

The SessionState kernel is the central working memory system for the K1 cognitive architecture, providing a survivable, tiered memory model that prevents memory-related failures through strict guard rails and emergency modes. It serves as the single source of truth for all K1 agents, maintaining session coherence while enforcing hard memory limits.

## Integration with K1 Cognitive Architecture

SessionState operates as **Layer 5: Shared SessionState (Central Working Memory)** in the K1 cognitive architecture, as detailed in `k1_cognitive_architecture_skeleton.mmd`. It integrates with:

- **Layer 1 (Concierge)**: Receives mutations via the Concierge FSM for deterministic state updates.
- **Layer 2 (Orchestrator)**: Provides read-only access for multi-reader agents.
- **Layer 2.5 (Capability Fabric)**: Supplies context for capability invocations and tool executions.
- **Layer 3 (Planner)**: Reads planning state and constraints.
- **Layer 4 (Sub-Agents)**: Emits state deltas via the Delta Bus for aggregation.
- **K0 Kernel**: Archives evicted data to cold storage and reconstructs state with <100ms SLA.

Key flows include:

- Delta emission to the Event Bus for proactive decisions and SSE notifications.
- Memory writes and checkpoints routed through the K0-K1 Bridge.
- Feedback signals and learning updates integrated via the Delta Bus and Memory Writer Agents.

This ensures SessionState acts as the cohesive hub for session-wide state management, enabling coordinated agent behavior while maintaining performance bounds.

## Architecture

### Tiered Memory Model

The SessionState implements a three-tier memory hierarchy with strict size limits:

- **🔥 HOT CORE (≤48KB, NEVER evict)**: Critical session state that must remain resident
- **🌡️ WARM TIER (≤48KB, evictable)**: Recent data that can be evicted with summarization
- **❄️ COLD SHADOW (K0-backed)**: Reconstructible archives outside session limits
- **TOTAL ≤96KB (hard boundary)**: Absolute limit with emergency mode triggers

### Memory Sections

#### HOT CORE (8 sections, ≤48KB total)

1. **control (≤8KB)**: Agent leases, turn lock, flow state - **NEVER EVICTED**
2. **beliefs_active (≤8KB)**: Facts needed for current turn
3. **scoreboard (≤6KB)**: Referents, Questions Under Discussion (QUD), salience
4. **clarifications (≤4KB)**: Open gaps for current turn
5. **affective_now (≤4KB)**: Current emotion snapshot
6. **mental_now (≤4KB)**: Current user knowledge/load delta
7. **narrative_active (≤4KB)**: Single active conversation thread
8. **meta (≤2KB)**: Session ID, timestamps, basic metadata

#### WARM TIER (4 sections, ≤48KB total)

1. **beliefs_history (≤12KB)**: Recent facts with capping, archived to K0
2. **history (≤12KB)**: Last 5 conversation turns only, lossy summaries
3. **persona (≤8KB)**: Personality traits, style, voice controls
4. **telemetry (≤8KB)**: Token counts, costs, counters (lossy compression)
## Corrected 12-Section Design Analysis

### Harsh Truth Check

The design prioritizes survivability over features. This is a survivable system, not a feature bucket.

### Survivability First: The Kernel Contract

#### Real Numbers (Not Fantasy)
```
SessionState (48KB HARD HOT, 96KB WARM, ∞ COLD)
├── HOT CORE (≤48KB, never evict)        → Orchestration survives
├── WARM TIER (≤48KB, evictable)         → Graceful degradation  
└── COLD SHADOW (K0-backed)              → Reconstructible
```

#### The Rules (Non-negotiable)

1. **HOT CORE (48KB)** = What's needed **right now** for this turn
2. **WARM TIER** = What might be needed next turn
3. **COLD SHADOW** = Everything else (K0)

### Corrected 12-Section Mapping

```
🔥 HOT CORE (≤48KB, NEVER thrash)
├── 1. control (8KB)          — Active leases, turn lock
├── 2. beliefs_active (8KB)   — Active facts THIS turn
├── 3. scoreboard (6KB)       — Current discourse state
├── 4. clarifications (4KB)   — Open gaps THIS turn
├── 5. affective_now (4KB)    — Current emotion
├── 6. mental_now (4KB)       — Current user model
├── 7. narrative_active (4KB) — ONE active thread
└── 8. meta (2KB)             — Session basics

🌡️ WARM TIER (≤48KB, evictable)
├── 9. beliefs_history (12KB) — Recent facts (capped)
├── 10. history (12KB)        — LAST 5 turns ONLY
├── 11. persona (8KB)         — Personality (static)
└── 12. telemetry (8KB)       — Metrics (lossy)

❄️ COLD SHADOW (K0 only)
├── beliefs_archive            — Everything else
├── history_archive            — Everything else  
├── multimodal_raw             — Blobs, embeddings
└── narrative_archive          — Inactive threads
```

## Kernel Contract (Python Reality)

```python
class SessionKernel:
    """Session Kernel - NOT Working Memory"""
    
    # ---------- INVARIANTS (ENFORCED) ----------
    _MAX_HOT_KB = 48      # Never exceed
    _MAX_WARM_KB = 48     # Evictable
    _MAX_TOTAL_KB = 96    # Hard limit
    
    def __init__(self):
        self._hot_size_kb = 0
        self._warm_size_kb = 0
        self._eviction_count = 0
        
    # ---------- MUTATION GUARDS ----------
    def _guard_mutation(self, section: str, estimated_kb: int) -> bool:
        """REJECT writes that would break invariants"""
        
        # 1. Check per-section caps (NO EXCEPTIONS)
        section_caps = {
            'control': 8, 'beliefs_active': 8, 'scoreboard': 6,
            'clarifications': 4, 'affective_now': 4, 'mental_now': 4,
            'narrative_active': 4, 'meta': 2,
            'beliefs_history': 12, 'history': 12, 'persona': 8, 'telemetry': 8
        }
        
        if estimated_kb > section_caps.get(section, 0):
            return False  # REJECTED
        
        # 2. Check HOT/WARM tier caps
        if section in ['control', 'beliefs_active', 'scoreboard', 'clarifications',
                      'affective_now', 'mental_now', 'narrative_active', 'meta']:
            new_hot = self._hot_size_kb + estimated_kb
            if new_hot > self._MAX_HOT_KB:
                self._evict_warm_aggressively()  # Make room
                return False if new_hot > self._MAX_HOT_KB else True
        else:
            new_warm = self._warm_size_kb + estimated_kb
            if new_warm > self._MAX_WARM_KB:
                return False  # WARM full, reject
        
        # 3. Check total cap
        total = (self._hot_size_kb + self._warm_size_kb + estimated_kb)
        if total > self._MAX_TOTAL_KB:
            return False
        
        return True  # Approved
    
    # ---------- HISTORY RULES (CAPS ENFORCED) ----------
    def add_turn(self, user_msg: str, agent_resp: str) -> bool:
        """CAP: Only last 5 turns in WARM"""
        
        # 1. Enforce lossy compression
        if len(self.history.turns) >= 5:
            # Evict oldest, keep summary
            oldest = self.history.turns.pop(0)
            self.history.summaries.append(self._summarize_turn(oldest))
        
        # 2. Size check BEFORE add
        turn_kb = self._estimate_turn_kb(user_msg, agent_resp)
        if not self._guard_mutation('history', turn_kb):
            return False  # REJECTED
        
        # 3. Add (if approved)
        self.history.turns.append(Turn(user_msg, agent_resp))
        return True
```

## FlatBuffers Schema (Survivable)

```flatbuffers
// k1/contracts/flatbuffers/session_kernel.fbs
namespace K1.SessionKernel;

// ----- HOT CORE (48KB cap) -----
table HotCore {
    control: ControlSection;            // 8KB max
    beliefs_active: ActiveBeliefs;      // 8KB max  
    scoreboard: ScoreboardSection;      // 6KB max
    clarifications: Clarifications;     // 4KB max
    affective_now: CurrentAffect;       // 4KB max
    mental_now: CurrentMentalModel;     // 4KB max
    narrative_active: ActiveThread;     // 4KB max
    meta: MetaSection;                  // 2KB max
}

// ----- WARM TIER (48KB cap) -----
table WarmTier {
    beliefs_history: BeliefHistory;     // 12KB max
    history: TurnHistory;               // 12KB max (5 turns!)
    persona: PersonaSection;            // 8KB max  
    telemetry: TelemetrySection;        // 8KB max
}

// ----- SESSION KERNEL (96KB TOTAL) -----
table SessionKernel {
    // Version 2: Clear tier separation
    hot: HotCore (required);
    warm: WarmTier (required);
    
    // Size tracking (enforced at runtime)
    hot_size_kb: int;
    warm_size_kb: int;
    total_size_kb: int;
    
    // Eviction state
    eviction_count: int;
    last_eviction_ms: long;
}
```

## Corrected Section APIs (With Guards)

### HistorySection (Corrected)
```python
class HistorySection:
    """5 TURNS MAX. NO EXCEPTIONS."""
    
    MAX_TURNS = 5
    MAX_KB = 12
    
    def __init__(self):
        self.turns: List[Turn] = []           # Last 5 turns
        self.summaries: List[str] = []        # Evicted turns summary
        self._size_kb = 0
    
    def add_turn(self, turn: Turn) -> bool:
        # 1. SIZE CHECK FIRST
        turn_kb = self._estimate_turn_kb(turn)
        if self._size_kb + turn_kb > self.MAX_KB:
            return False  # REJECT
        
        # 2. CAP ENFORCEMENT
        if len(self.turns) >= self.MAX_TURNS:
            # Evict oldest, keep summary
            oldest = self.turns.pop(0)
            self.summaries.append(self._summarize(oldest))
            self._size_kb -= self._estimate_turn_kb(oldest)
        
        # 3. Add (if approved)
        self.turns.append(turn)
        self._size_kb += turn_kb
        return True
    
    def get_context(self, window: int = 5) -> List[Turn]:
        """Returns at most 5 turns"""
        return self.turns[-window:] if window <= 5 else self.turns
```

### BeliefsSection (Tiered)
```python
class BeliefsSection:
    """Tiered: Active (HOT) vs History (WARM)"""
    
    def __init__(self):
        self.active: Dict[str, Fact] = {}     # HOT: Current turn facts
        self.history: List[Fact] = []         # WARM: Recent facts (capped)
        self.archive_ids: List[str] = []      # COLD: K0 pointers
    
    def add_fact(self, key: str, value: str, confidence: float) -> bool:
        # 1. HOT check (8KB cap)
        fact_kb = len(key) + len(value) + 8
        if not self._hot_has_room(fact_kb):
            # Move oldest active to history
            self._demote_oldest_active()
        
        # 2. History cap (12KB)
        if len(self.history) * 32 > 12288:  # 12KB
            # Archive to K0
            oldest = self.history.pop(0)
            self.archive_ids.append(self._archive_to_k0(oldest))
        
        # 3. Add if room exists
        return self._add_with_guards(key, value, confidence)
```

## Implementation Status

### Current State
- ✅ **Architecture finalized**: All diagrams and specifications complete
- ✅ **Guard rails designed**: MutationGuard, SizeTracker, and emergency modes specified
- ✅ **Integration mapped**: Connections to K0 cold storage and agent fabric defined
- 🚧 **Code implementation**: Kernel services and section management pending

### Build Order (Survivability First)

#### Phase 0: Guard Rails (Week 1)
- Implement SizeTracker (per-section byte counting)
- Implement MutationGuard (rejects violations)
- Implement EvictionEngine (tier-aware)
- Test: "What happens at 49KB HOT?"

#### Phase 1: HOT CORE Only (Weeks 2-4)
- Week 2: control + meta (orchestration survives)
- Week 3: beliefs_active + scoreboard (cognition works)
- Week 4: clarifications + affective_now (gaps+emotion)

#### Phase 2: WARM TIER (Weeks 5-6)
- Week 5: history (5-turn cap ENFORCED)
- Week 6: persona + telemetry (static + metrics)

#### Phase 3: Integration (Week 7)
- Cross-tier migration testing
- Load testing at 96KB boundary
- Failure recovery testing

### Implementation Phases

#### Phase 0: Guard Rails (High Priority)
- Implement SizeTracker with per-section accounting
- Build MutationGuard with preflight rejection API
- Add emergency mode triggers and handlers
- Unit tests for boundary conditions (49KB HOT, 96KB total)

#### Phase 1: Core Kernel
- Section data structures with FlatBuffers serialization
- MigrationEngine for HOT↔WARM transitions
- EvictionEngine with summarization logic
- Reconstruction from K0 with SLA compliance

#### Phase 2: Agent Integration
- Single-writer/multi-reader concurrency model
- Delta emission for agent coordination
- Session persistence and recovery
- Performance optimization and monitoring

## Survivability Checklist

### Must Pass Before Production
- [ ] HOT CORE never exceeds 48KB in stress tests
- [ ] System survives 1000 concurrent sessions
- [ ] MutationGuard rejects 100% of overflow attempts
- [ ] History never grows beyond 5 turns
- [ ] FlatBuffers serialization <1ms at 96KB
- [ ] Eviction causes no orchestration crashes
- [ ] K0 reconstruction works for all COLD data

### Failure Models (Accepted)
1. **Memory pressure** → Evict WARM, preserve HOT
2. **Mutation rejected** → Agent gets "retry with less data"
3. **History full** → Oldest turn summarized, not lost
4. **Serialization timeout** → Delta-only serialization

### Unacceptable Failures
1. HOT CORE eviction during turn
2. Orchestration state corruption
3. Unbounded memory growth
4. Silent data loss

## Final Verdict

**Proceed with 12-section design IF AND ONLY IF:**

1. You implement **tiering** (HOT/WARM/COLD)
2. You enforce **byte caps per section**
3. You implement **MutationGuard** (rejects violations)
4. You cap **history at 5 turns**
5. You treat this as a **kernel**, not a bucket

**Otherwise, stick with 6 sections.**

The choice is between:
- **6 sections**: Simple, survivable, limited
- **12 sections**: Powerful, survivable **only with discipline**

You're building a **cognitive microkernel**. Treat it with kernel-level rigor, or it will fail.
### Kernel Services

#### Core Enforcement

- **SizeTracker**: Per-section byte accounting with real-time monitoring
- **MutationGuard**: Preflight API that estimates size impact and rejects oversized mutations
  - API: `preflight(section, operation, data) → Approval`
- **EvictionEngine**: Tier-aware eviction with intelligent summarization
- **MigrationEngine**: HOT↔WARM demotion/promotion for pressure relief
- **Snapshot API**: Size breakdown, health status, and pressure metrics

#### Emergency Modes (≥95KB trigger)

- **Emergency Summarization**: Aggressive compression of telemetry and history
- **Read-Only Mode**: Temporary rejection of write operations, allowing critical reads
- **Priority-Based Shedding**: Evict WARM data by priority while preserving HOT control

### Cross-Section Dependencies

The kernel maintains referential integrity across sections during eviction:

- `beliefs_active` → `beliefs_history`: Active facts reference historical context
- `control` → `beliefs_active`: Leases depend on current factual state
- `scoreboard` → `history`: Referents require conversational context
- `narrative_active` → `conversation_threads`: Active thread references full thread history

### Reconstruction SLA

When data must be reconstructed from K0 cold storage:

- **Maximum latency**: <100ms
- **Partial hydration**: HOT sections prioritized first
- **Degraded operation**: System continues with missing WARM data

## Implementation Status

### Current State

- ✅ **Architecture finalized**: All diagrams and specifications complete
- ✅ **Guard rails designed**: MutationGuard, SizeTracker, and emergency modes specified
- ✅ **Integration mapped**: Connections to K0 cold storage and agent fabric defined
- 🚧 **Code implementation**: Kernel services and section management pending

### Implementation Phases

#### Phase 0: Guard Rails (High Priority)

- Implement SizeTracker with per-section accounting
- Build MutationGuard with preflight rejection API
- Add emergency mode triggers and handlers
- Unit tests for boundary conditions (49KB HOT, 96KB total)

#### Phase 1: Core Kernel

- Section data structures with FlatBuffers serialization
- MigrationEngine for HOT↔WARM transitions
- EvictionEngine with summarization logic
- Reconstruction from K0 with SLA compliance

#### Phase 2: Agent Integration

- Single-writer/multi-reader concurrency model
- Delta emission for agent coordination
- Session persistence and recovery
- Performance optimization and monitoring

## Files

- `sessionstate.mmd`: Full runtime diagram with flows, emergency modes, and K0 integration
- `sessionstate_internal.mmd`: Internal structure diagram focusing on kernel invariants
- `README.md`: This documentation

## Design Principles

1. **Survivability First**: Hard limits prevent memory exhaustion failures
2. **Graceful Degradation**: Emergency modes maintain operation under pressure
3. **Referential Integrity**: Dependencies respected during eviction
4. **Performance Bounds**: <100ms reconstruction SLA
5. **Single Source of Truth**: All agents read from SessionState
6. **Guard Rails**: Preflight rejection prevents invalid mutations

## Testing Strategy

- **Boundary Testing**: Validate rejection at 49KB HOT and 96KB total
- **Emergency Mode Testing**: Verify graceful degradation under overload
- **Reconstruction Testing**: Confirm <100ms SLA from cold storage
- **Concurrency Testing**: Single-writer/multi-reader safety
- **Integration Testing**: End-to-end with agent fabric and K0

## Related Components

- **K0 Cold Storage**: Backing store for evicted data and reconstruction
- **Agent Fabric**: Single-writer orchestration through Concierge FSM
- **Delta Bus**: Change notification system for multi-reader agents
- **FlatBuffers**: Serialization format for <1ms performance

## Architecture Decision Records

- ADR-K0-0018: SessionState Memory Limits
- ADR-K0-XXXX: Mutation Guard API Design
- ADR-K0-XXXX: Emergency Mode Specifications
- ADR-K0-XXXX: Reconstruction SLA Requirements
