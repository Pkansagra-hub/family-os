---
adr_number: 0084a
affected_layers:
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k0.bus.pipeline.consolidation.replay
- k0.kernel.memory.hippocampal_replay
- k0.storage.episodic_memory
- k1.l3_execution.learning_loop
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- testing
- usability
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: '2025-11-03'
implementation_phase: Phase 3 (Memory Consolidation)
implementation_status: COMPLETED
propagation:
  affected_adrs:
  - ADR-0084
  - ADR-0084a
  - ADR-0084b
  - ADR-0084c
  - ADR-0084d
  affected_contracts:
  - k0/contracts/api/memory/memory_replay.yml
  - k0/contracts/api/memory/pattern_strengthening.yml
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_chunk.fbs
  affected_tests:
  - tests/k0/bus/test_memory_replay.py
  - tests/k0/kernel/test_hippocampal_replay.py
  - tests/k0/storage/test_episodic_replay_patterns.py
  triggers:
  - Modifying system architecture
  - Performance requirement changes
related_adrs:
- ADR-0084
- ADR-0084a
- ADR-0084b
- ADR-0084c
- ADR-0084d
related_contracts: []
related_diagrams: []
research_citations:
- Memory Replay (Wilson & McNaughton, 1994)
- Synaptic Consolidation (Dudai et al., 2015)
- Hippocampal Sequence Replay (Carr et al., 2011)
status: ACCEPTED
title: Sleep-Cycle Memory Replay Algorithms — Hippocampal Pattern Strengthening
---

# ADR-0084a: Sleep-Cycle Memory Replay Algorithms — Hippocampal Pattern Strengthening

**Status:** Proposed 🔄
**Parent ADR:** ADR-0084 (K0 Memory Consolidation Pipeline)
**Last Updated:** 2025-01-22

---

## Context

**From ADR-0084:** K0 P03 Consolidation Pipeline requires **biologically-inspired memory replay mechanisms** that strengthen synaptic connections through offline pattern reactivation during sleep-like states.

**Neuroscience Foundation:**

During slow-wave sleep (NREM), the hippocampus replays experiences at **10-20x accelerated speed** (Wilson & McNaughton 1994). This replay:
- **Strengthens synaptic connections** through Hebbian learning ("neurons that fire together, wire together")
- **Consolidates episodic traces** into more stable representations
- **Extracts statistical regularities** from repeated patterns
- **Coordinates with theta oscillations** (4-8 Hz) for timing synchronization

**Architecture Context (from K0 diagrams):**

- **CA3_CONSOLIDATION** (`ca3/consolidation_coordinator.py`) — Initiates consolidation during NREM
- **CA3_RECURRENT** (`ca3/recurrent_network.py`) — Recurrent associations for memory linking
- **CA3_COMPLETER** (`ca3/pattern_completer.py`) — Pattern completion from partial cues
- **CA1_THETA** (`ca1/theta_rhythm.py`) — Theta rhythm for encoding/retrieval mode switching
- **affect_memory_mod** (`affect/memory_modulation.py`) — Emotional memory prioritization

---

## Decision

Implement **three-phase memory replay algorithm** inspired by hippocampal neurophysiology:

### Phase 1: Pattern Identification (CA3 Pattern Completion)
### Phase 2: Sequence Replay (CA3 Recurrent Activation)
### Phase 3: Synaptic Strengthening (Hebbian Weight Updates)

---

## Replay Algorithm Architecture

### Algorithm Overview

```python
class HippocampalReplayEngine:
    """
    Sleep-cycle memory replay engine implementing CA3 pattern strengthening.

    Research basis:
    - Wilson & McNaughton (1994): Reactivation during sleep
    - Buzsáki (2015): Hippocampal replay at 10-20x speed
    - Káli & Dayan (2004): Replay role in consolidation
    """

    def __init__(self, ca3_coordinator, ca3_recurrent, ca1_theta):
        self.ca3_coordinator = ca3_coordinator
        self.ca3_recurrent = ca3_recurrent
        self.ca1_theta = ca1_theta
        self.replay_speed = 10.0  # 10x real-time (configurable)

    async def execute_replay_cycle(self, nrem_phase: NREMPhase):
        """
        Execute one NREM replay cycle.

        NREM Phase Duration: 45-60 minutes
        Replay cycles per NREM: ~100-200 cycles (one cycle every 15-30 seconds)
        """
        # Phase 1: Identify patterns to replay
        candidate_memories = await self.identify_replay_candidates(nrem_phase)

        # Phase 2: Execute replay sequences
        for memory_sequence in candidate_memories:
            await self.replay_sequence(memory_sequence)

        # Phase 3: Synaptic strengthening
        await self.strengthen_associations()
```

---

## Phase 1: Pattern Identification

**Goal:** Select memory sequences for replay based on importance, recency, and emotional salience.

### Selection Criteria

```python
async def identify_replay_candidates(self, nrem_phase: NREMPhase) -> List[MemorySequence]:
    """
    Select memories for replay prioritizing:
    1. Emotional salience (affect_memory_mod)
    2. Access frequency (recently accessed)
    3. Recency (last 24 hours)
    4. User-marked priority (priority_marker=true)
    5. Unresolved patterns (incomplete sequences)
    """
    # Query episodic memories from last 24 hours
    recent_memories = await self.query_episodic_memories(
        time_window_hours=24,
        min_access_count=0
    )

    # Score each memory for replay priority
    scored_memories = []
    for memory in recent_memories:
        score = self.calculate_replay_priority(memory)
        scored_memories.append((memory, score))

    # Sort by priority score (descending)
    scored_memories.sort(key=lambda x: x[1], reverse=True)

    # Select top N% for replay (default: top 30%)
    replay_percentage = 0.30
    num_to_replay = int(len(scored_memories) * replay_percentage)

    return [mem for mem, score in scored_memories[:num_to_replay]]
```

### Priority Scoring Function

```python
def calculate_replay_priority(self, memory: EpisodicMemory) -> float:
    """
    Calculate replay priority score (0.0 - 1.0).

    Factors:
    - Emotional salience: 0.40 weight (from affect_memory_mod)
    - Access frequency: 0.25 weight (normalized access_count)
    - Recency: 0.20 weight (inverse age_hours)
    - Priority marker: 0.15 weight (binary: 1.0 if marked, 0.0 otherwise)
    """
    # Emotional salience (0.0 - 1.0 from affect_memory_mod)
    emotional_score = memory.emotional_salience * 0.40

    # Access frequency (normalize by max access count)
    max_access = 10.0  # Assume max 10 accesses in 24 hours
    access_score = min(memory.access_count / max_access, 1.0) * 0.25

    # Recency (exponential decay: recent memories score higher)
    age_hours = (now() - memory.created_ts).total_seconds() / 3600
    recency_score = math.exp(-age_hours / 24.0) * 0.20

    # Priority marker (binary)
    priority_score = (1.0 if memory.priority_marker else 0.0) * 0.15

    return emotional_score + access_score + recency_score + priority_score
```

### Emotional Salience Integration

**Module:** `affect/memory_modulation.py` (affect_memory_mod)

```python
def get_emotional_salience(memory: EpisodicMemory) -> float:
    """
    Retrieve emotional salience from affect modulation system.

    Salience factors:
    - Valence extremity (|valence| → higher salience for very positive/negative)
    - Arousal level (high arousal → higher salience)
    - Novelty (unexpected events → higher salience)

    Returns: 0.0 (neutral) to 1.0 (highly salient)
    """
    affect_state = query_affect_state(memory.cognitive_trace_id)

    # Valence extremity: Distance from neutral (0.0)
    valence_extremity = abs(affect_state.valence)  # 0.0 - 1.0

    # Arousal: Direct from affect state
    arousal = affect_state.arousal  # 0.0 - 1.0

    # Novelty: Inversely proportional to pattern frequency
    novelty = compute_novelty(memory)  # 0.0 - 1.0

    # Weighted combination
    salience = (
        valence_extremity * 0.40 +
        arousal * 0.40 +
        novelty * 0.20
    )

    return salience
```

**Emotional Memory Prioritization:**
- Memories with **emotional_salience ≥ 0.70** receive **2x replay cycles**
- Examples: Family events, stressful moments, joyful celebrations

---

## Phase 2: Sequence Replay

**Goal:** Reactivate memory sequences at accelerated speed (10-20x) to strengthen CA3 recurrent connections.

### Replay Execution

```python
async def replay_sequence(self, memory: EpisodicMemory):
    """
    Replay memory sequence at accelerated speed.

    Steps:
    1. Load episodic sequence from storage
    2. Activate CA3 pattern completion (retrieve associations)
    3. Traverse sequence nodes in temporal order
    4. Strengthen recurrent connections (Hebbian learning)
    5. Emit replay events for observability

    Timing:
    - Real-time memory duration: e.g., 5 minutes
    - Replay duration: 30 seconds (10x speedup)
    - Inter-node delay: 50-100ms (simulate synaptic delays)
    """
    # Load sequence from K0::st_sqlite[episodic_memories]
    sequence = await self.load_episode_sequence(memory.id)

    # Activate CA3 pattern completion to retrieve associations
    associations = await self.ca3_recurrent.retrieve_associations(sequence)

    # Theta rhythm coordination (NREM: 4-6 Hz slow theta)
    theta_phase = await self.ca1_theta.get_current_phase()

    # Replay sequence nodes
    for i, node in enumerate(sequence.nodes):
        # Activate node in CA3 recurrent network
        await self.ca3_recurrent.activate_node(node)

        # Strengthen associations with co-activated nodes
        for associated_node in associations[node]:
            await self.strengthen_connection(node, associated_node)

        # Inter-node delay (simulated synaptic propagation)
        await asyncio.sleep(0.05)  # 50ms delay

        # Emit replay event
        emit_event(
            topic="infra.consolidation.replay.node",
            data={
                "episode_id": memory.id,
                "node_index": i,
                "node_id": node.id,
                "replay_speed": self.replay_speed,
                "theta_phase": theta_phase,
                "cognitive_trace_id": memory.cognitive_trace_id
            }
        )

    # Log replay completion
    logger.info(
        "replay_complete",
        episode_id=memory.id,
        sequence_length=len(sequence.nodes),
        duration_ms=(len(sequence.nodes) * 50),
        cognitive_trace_id=memory.cognitive_trace_id
    )
```

### CA3 Recurrent Association Retrieval

**Module:** `ca3/recurrent_network.py` (CA3_RECURRENT)

```python
async def retrieve_associations(self, sequence: MemorySequence) -> Dict[Node, List[Node]]:
    """
    Retrieve recurrent associations for each node in sequence.

    CA3 recurrent connectivity:
    - Each memory node connects to ~5-10 associated nodes
    - Associations based on:
      1. Temporal proximity (co-occurred within 5 minutes)
      2. Semantic similarity (embedding cosine similarity ≥ 0.75)
      3. Causal relationships (from K0::st_kg causal graph)

    Returns: Dict mapping each node to its associated nodes
    """
    associations = {}

    for node in sequence.nodes:
        # Query associations from CA3 recurrent store
        associated_nodes = await self.query_associations(
            node_id=node.id,
            max_associations=10
        )

        # Sort by association strength (weight)
        associated_nodes.sort(key=lambda n: n.weight, reverse=True)

        associations[node] = associated_nodes

    return associations
```

### Replay Speed Modulation

```python
def calculate_replay_speed(self, memory: EpisodicMemory) -> float:
    """
    Dynamically adjust replay speed based on memory characteristics.

    Speed factors:
    - Emotional memories: Slower replay (5-8x) for deeper processing
    - Complex sequences: Slower replay (8-10x) for accuracy
    - Simple patterns: Faster replay (15-20x) for efficiency

    Returns: Replay speed multiplier (relative to real-time)
    """
    base_speed = 10.0  # Default 10x speedup

    # Emotional memories: Reduce speed for deeper processing
    if memory.emotional_salience >= 0.70:
        base_speed *= 0.70  # Slow down to 7x

    # Complex sequences: Reduce speed
    if len(memory.sequence.nodes) > 50:
        base_speed *= 0.80  # Slow down to 8x

    # Simple patterns: Increase speed
    if len(memory.sequence.nodes) < 10:
        base_speed *= 1.50  # Speed up to 15x

    return base_speed
```

---

## Phase 3: Synaptic Strengthening

**Goal:** Strengthen synaptic connections using Hebbian learning ("neurons that fire together, wire together").

### Hebbian Weight Update

```python
async def strengthen_connection(self, src_node: Node, dst_node: Node):
    """
    Strengthen synaptic connection between co-activated nodes.

    Hebbian learning rule:
        Δw = η * (activation_src * activation_dst)

    Where:
    - η (eta): Learning rate (0.01 - 0.05)
    - activation_src: Source node activation (0.0 - 1.0)
    - activation_dst: Destination node activation (0.0 - 1.0)

    Constraints:
    - Maximum weight: 1.0 (prevents runaway strengthening)
    - Minimum weight: 0.0 (never negative)
    - Saturation: Asymptotic approach to max weight
    """
    # Retrieve current weight from CA3_RECURRENT
    current_weight = await self.ca3_recurrent.get_weight(src_node.id, dst_node.id)

    # Learning rate (configurable)
    eta = 0.03  # 3% weight increase per replay

    # Activation levels (1.0 during replay)
    activation_src = 1.0
    activation_dst = 1.0

    # Hebbian weight delta
    delta_weight = eta * (activation_src * activation_dst)

    # Update weight with saturation (asymptotic to 1.0)
    new_weight = current_weight + delta_weight * (1.0 - current_weight)
    new_weight = min(new_weight, 1.0)  # Cap at 1.0

    # Store updated weight
    await self.ca3_recurrent.set_weight(src_node.id, dst_node.id, new_weight)

    # Emit strengthening event
    emit_event(
        topic="infra.consolidation.strengthen",
        data={
            "src_node": src_node.id,
            "dst_node": dst_node.id,
            "old_weight": current_weight,
            "new_weight": new_weight,
            "delta": delta_weight
        }
    )
```

### Long-Term Potentiation (LTP) Simulation

```python
def apply_ltp(self, weight: float, replay_count: int) -> float:
    """
    Simulate Long-Term Potentiation (LTP) for frequently replayed connections.

    LTP: Persistent strengthening after repeated activation
    - Threshold: 3+ replays within 24 hours
    - Effect: +10% permanent weight boost
    - Decay: LTP bonus decays over 30 days if not replayed
    """
    if replay_count >= 3:
        # Apply LTP bonus (10% boost)
        ltp_bonus = 0.10
        weight_with_ltp = min(weight + ltp_bonus, 1.0)

        logger.info(
            "ltp_applied",
            old_weight=weight,
            new_weight=weight_with_ltp,
            replay_count=replay_count
        )

        return weight_with_ltp

    return weight
```

---

## Theta Rhythm Coordination

**Goal:** Synchronize replay with theta oscillations for optimal encoding/retrieval mode switching.

**Module:** `ca1/theta_rhythm.py` (CA1_THETA)

### Theta Oscillation Implementation

```python
class ThetaRhythmGenerator:
    """
    Generate theta oscillations (4-8 Hz) for consolidation timing.

    Theta phases:
    - Encoding phase (theta trough): Optimal for memory formation
    - Retrieval phase (theta peak): Optimal for memory replay

    Research: Hasselmo et al. (2002) - Theta phase precession
    """

    def __init__(self):
        self.nrem_frequency = 5.0  # 5 Hz (slow theta for consolidation)
        self.rem_frequency = 7.0   # 7 Hz (fast theta for exploration)
        self.current_phase = 0.0   # 0.0 - 2π

    async def advance_theta_cycle(self, dt: float):
        """
        Advance theta oscillation by time delta.

        Args:
            dt: Time delta in seconds
        """
        # Angular frequency (radians per second)
        omega = 2 * math.pi * self.nrem_frequency

        # Advance phase
        self.current_phase += omega * dt

        # Wrap phase to [0, 2π]
        self.current_phase %= (2 * math.pi)

    def get_current_phase(self) -> float:
        """
        Get current theta phase (0.0 - 2π).

        Phase interpretation:
        - 0.0 - π: Retrieval phase (replay memories)
        - π - 2π: Encoding phase (consolidate patterns)
        """
        return self.current_phase

    def is_retrieval_phase(self) -> bool:
        """Check if current phase is optimal for retrieval (replay)."""
        return 0.0 <= self.current_phase < math.pi

    def is_encoding_phase(self) -> bool:
        """Check if current phase is optimal for encoding (consolidation)."""
        return math.pi <= self.current_phase < (2 * math.pi)
```

### Theta-Gated Replay

```python
async def theta_gated_replay(self, memory: EpisodicMemory):
    """
    Execute replay synchronized with theta rhythm.

    Strategy:
    - Wait for retrieval phase (theta peak) before starting replay
    - Pause replay during encoding phase (theta trough)
    - Resume replay on next retrieval phase
    """
    # Wait for retrieval phase
    while not self.ca1_theta.is_retrieval_phase():
        await asyncio.sleep(0.01)  # 10ms polling interval

    # Execute replay during retrieval phase
    await self.replay_sequence(memory)
```

---

## Performance Characteristics

### Replay Timing Budgets

| Operation | Target Duration (P95) | Notes |
|-----------|----------------------|-------|
| Pattern identification | <5 seconds | Score 1000s of memories |
| Single memory replay | <200ms per memory | 10x speedup (2-second memory → 200ms) |
| Association retrieval | <50ms per node | CA3_RECURRENT query |
| Weight update | <10ms per connection | Hebbian learning |
| Full NREM cycle | 45-60 minutes | 100-200 replay cycles |

### Throughput

- **Memories replayed per NREM:** ~100-200 memories
- **Nodes activated per replay:** ~10-50 nodes per memory
- **Connections strengthened per NREM:** ~1000-5000 connections
- **Replay rate:** ~2-3 memories/minute

### Resource Usage

- **CPU:** <5% average (low priority background task)
- **Memory:** <100 MB (batch processing)
- **Disk I/O:** <1 MB/s (read episodic memories, write weight updates)

---

## Observability

### Metrics

```python
# Prometheus metrics
replay_cycles_total = Counter(
    'consolidation_replay_cycles_total',
    'Total replay cycles executed',
    ['nrem_phase']
)

replay_duration_seconds = Histogram(
    'consolidation_replay_duration_seconds',
    'Duration of single memory replay',
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
)

synaptic_weights_updated = Counter(
    'consolidation_synaptic_weights_updated_total',
    'Total synaptic weight updates'
)

emotional_memories_replayed = Counter(
    'consolidation_emotional_memories_replayed_total',
    'Emotional memories replayed (salience ≥ 0.70)'
)
```

### Events

```
infra.consolidation.replay.start       — Replay cycle started
infra.consolidation.replay.node        — Node activated in replay
infra.consolidation.strengthen         — Synaptic connection strengthened
infra.consolidation.ltp_applied        — LTP bonus applied
infra.consolidation.replay.complete    — Replay cycle finished
```

### Traces

```python
@traced(span_name="consolidation.replay_cycle")
async def execute_replay_cycle(self, nrem_phase: NREMPhase):
    with tracer.start_as_current_span("identify_candidates"):
        candidates = await self.identify_replay_candidates(nrem_phase)

    with tracer.start_as_current_span("replay_sequences"):
        for memory in candidates:
            await self.replay_sequence(memory)

    with tracer.start_as_current_span("strengthen_associations"):
        await self.strengthen_associations()
```

---

## Neuroscience Research Citations

1. **Wilson, M. A., & McNaughton, B. L. (1994).** *Reactivation of hippocampal ensemble memories during sleep.* Science, 265(5172), 676-679.
   - First demonstration of hippocampal replay during sleep
   - Showed 10-20x acceleration of replay sequences

2. **Buzsáki, G. (2015).** *Hippocampus.* Annual Review of Neuroscience, 38, 1-24.
   - Comprehensive review of hippocampal function
   - Detailed analysis of theta oscillations and replay

3. **Káli, S., & Dayan, P. (2004).** *Off-line replay maintains declarative memories in a model of hippocampal-neocortical interactions.* Nature Neuroscience, 7(3), 286-294.
   - Computational model of sleep-dependent consolidation
   - Showed replay role in stabilizing memories

4. **Hasselmo, M. E., Bodelón, C., & Wyble, B. P. (2002).** *A proposed function for hippocampal theta rhythm: Separate phases of encoding and retrieval enhance reversal of prior learning.* Neural Computation, 14(4), 793-817.
   - Theta phase precession theory
   - Encoding/retrieval mode switching

5. **Tononi, G., & Cirelli, C. (2014).** *Sleep and the price of plasticity: From synaptic and cellular homeostasis to memory consolidation and integration.* Neuron, 81(1), 12-34.
   - Synaptic homeostasis hypothesis
   - Downscaling weak connections during sleep

---

## Related ADRs

- **ADR-0084:** K0 Memory Consolidation Pipeline (parent)
- **ADR-0084b:** Offline Consolidation Scheduler (sleep state machine)
- **ADR-0084c:** Knowledge Graph Consolidation (entity extraction)
- **ADR-0084d:** Dream-Like Exploration & Reflection (REM phase)

---

**End of ADR-0084a**