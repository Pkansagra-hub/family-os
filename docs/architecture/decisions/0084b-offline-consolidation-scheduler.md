---
adr_number: 0084b
title: Offline Consolidation Scheduler — Sleep State Machine & NREM/REM Cycles
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer4_runtime
affected_modules: []
concerns:
- architecture
- observability
- performance
- privacy
- scalability
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0084
- ADR-0084a
- ADR-0084c
- ADR-0084d
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0084
  - ADR-0084a
  - ADR-0084c
  - ADR-0084d
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  affected_tests: []
---


# ADR-0084b: Offline Consolidation Scheduler — Sleep State Machine & NREM/REM Cycles

**Status:** Proposed 🔄
**Parent ADR:** ADR-0084 (K0 Memory Consolidation Pipeline)
**Last Updated:** 2025-01-22

---

## Context

**From ADR-0084:** K0 P03 Consolidation Pipeline requires **sleep-cycle-inspired scheduler** that detects system idle periods and orchestrates NREM/REM consolidation phases.

**Biological Inspiration:**

Human sleep architecture follows **90-minute ultradian cycles** with distinct stages:
- **NREM Stage 1-2 (Light Sleep):** Initial consolidation, memory stabilization
- **NREM Stage 3 (Slow-Wave Sleep):** Deep consolidation, synaptic homeostasis
- **REM Sleep:** Creative exploration, emotional processing, skill rehearsal

**Architecture Context (from K0 diagrams):**

- **SLEEP_SCHEDULER** (`k0/consolidation/scheduler.py`) — Idle detection & trigger coordination
- **SLEEP_STATE_MACHINE** (`k0/consolidation/state_machine.py`) — NREM/REM cycle orchestration
- **SLEEP_TRIGGER** — Consolidation initiation from Hippocampus
- **P03 Pipeline** — Consolidation job distribution to handlers

---

## Decision

Implement **five-state sleep scheduler** that mimics biological sleep cycles:

### States: IDLE → NREM_PHASE_1 → NREM_PHASE_2 → REM_PHASE → WAKING → IDLE

### Transitions: Time-based (90-minute cycles) + interruption handling

---

## Sleep Scheduler Architecture

### Idle Detection

**Goal:** Detect system idle periods suitable for consolidation without disrupting user workflows.

```python
class SleepScheduler:
    """
    Idle detection and consolidation trigger coordinator.

    Triggers:
    1. Time-based: Preferred 2AM-5AM (configurable)
    2. Activity-based: CPU <5% for 15 minutes
    3. Event-based: After >1000 episodic entries
    4. Manual: User-initiated consolidation
    """

    def __init__(self):
        self.preferred_hours = (2, 5)  # 2AM-5AM
        self.cpu_threshold = 0.05      # 5% CPU
        self.idle_duration = 900       # 15 minutes (seconds)
        self.entry_threshold = 1000    # Episodic entries

    async def monitor_idle_state(self):
        """
        Monitor system activity and trigger consolidation when idle.

        Monitoring loop:
        - Check every 60 seconds
        - Log CPU usage, memory pressure, battery level
        - Evaluate trigger conditions
        - Initiate sleep state machine if conditions met
        """
        while True:
            # Sample system metrics
            cpu_usage = await get_cpu_usage()
            memory_pressure = await get_memory_pressure()
            battery_level = await get_battery_level()
            current_hour = datetime.now().hour

            # Check trigger conditions
            time_preferred = self.preferred_hours[0] <= current_hour < self.preferred_hours[1]
            cpu_idle = cpu_usage < self.cpu_threshold
            memory_ok = memory_pressure < 0.80  # <80% memory usage
            battery_ok = battery_level > 0.30   # >30% battery

            # Check idle duration
            if cpu_idle:
                self.idle_time += 60  # Accumulate idle seconds
            else:
                self.idle_time = 0    # Reset on activity

            idle_long_enough = self.idle_time >= self.idle_duration

            # Trigger consolidation if all conditions met
            if time_preferred and idle_long_enough and memory_ok and battery_ok:
                logger.info(
                    "idle_detected",
                    cpu_usage=cpu_usage,
                    idle_duration=self.idle_time,
                    battery_level=battery_level,
                    current_hour=current_hour
                )

                await self.trigger_consolidation()

            # Sleep 60 seconds before next check
            await asyncio.sleep(60)

    async def trigger_consolidation(self):
        """
        Initiate consolidation by starting sleep state machine.

        Steps:
        1. Emit trigger event
        2. Initialize state machine in NREM_PHASE_1
        3. Schedule 90-minute cycle
        4. Set resource limits (CPU nice, memory cap, ionice)
        """
        # Emit trigger event
        emit_event(
            topic="infra.consolidation.trigger",
            data={
                "trigger_type": "auto",
                "timestamp": now(),
                "conditions": {
                    "cpu_idle": True,
                    "time_preferred": True,
                    "battery_ok": True
                }
            }
        )

        # Start sleep state machine
        await self.state_machine.transition_to(SleepState.NREM_PHASE_1)

        logger.info("consolidation_triggered", trigger_type="auto")
```

### Manual Trigger

```python
async def manual_trigger_consolidation(self):
    """
    User-initiated consolidation (e.g., via K0 CLI command).

    Command: k0ctl consolidate --now

    Overrides idle detection and starts consolidation immediately.
    """
    logger.info("consolidation_triggered", trigger_type="manual")

    await self.state_machine.transition_to(SleepState.NREM_PHASE_1)
```

### Event-Based Trigger

```python
async def check_entry_threshold(self):
    """
    Trigger consolidation after N new episodic entries.

    Threshold: 1000 entries (configurable)

    Prevents memory overflow from excessive episodic accumulation.
    """
    entry_count = await count_unconsolidated_entries()

    if entry_count >= self.entry_threshold:
        logger.warning(
            "entry_threshold_exceeded",
            entry_count=entry_count,
            threshold=self.entry_threshold
        )

        await self.trigger_consolidation()
```

---

## Sleep State Machine

**Goal:** Orchestrate NREM/REM cycles with proper timing and interruption handling.

### State Definitions

```python
class SleepState(Enum):
    """
    Sleep cycle states.

    Durations (90-minute cycle):
    - IDLE: Awake, no consolidation
    - NREM_PHASE_1: 45 minutes (light consolidation)
    - NREM_PHASE_2: 30 minutes (deep consolidation)
    - REM_PHASE: 15 minutes (creative exploration)
    - WAKING: Transition back to IDLE (5 minutes)
    """
    IDLE = "IDLE"
    NREM_PHASE_1 = "NREM_PHASE_1"
    NREM_PHASE_2 = "NREM_PHASE_2"
    REM_PHASE = "REM_PHASE"
    WAKING = "WAKING"
```

### State Machine Implementation

```python
class SleepStateMachine:
    """
    Sleep state machine for consolidation orchestration.

    Cycle: IDLE → NREM1 (45m) → NREM2 (30m) → REM (15m) → WAKING (5m) → IDLE
    """

    def __init__(self):
        self.current_state = SleepState.IDLE
        self.state_start_time = None
        self.interruption_count = 0

        # State durations (seconds)
        self.durations = {
            SleepState.NREM_PHASE_1: 2700,  # 45 minutes
            SleepState.NREM_PHASE_2: 1800,  # 30 minutes
            SleepState.REM_PHASE: 900,       # 15 minutes
            SleepState.WAKING: 300           # 5 minutes
        }

    async def transition_to(self, new_state: SleepState):
        """
        Transition to new state with event emission.

        Side effects:
        - Emit state transition event
        - Log state change
        - Update state start time
        - Initialize state-specific handlers
        """
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = now()

        # Emit transition event
        emit_event(
            topic=f"infra.consolidation.{new_state.value.lower()}_start",
            data={
                "from_state": old_state.value,
                "to_state": new_state.value,
                "timestamp": self.state_start_time
            }
        )

        logger.info(
            "state_transition",
            from_state=old_state.value,
            to_state=new_state.value
        )

        # Initialize state-specific processing
        await self.initialize_state_handlers(new_state)

    async def run_cycle(self):
        """
        Execute full 90-minute sleep cycle.

        Flow:
        1. NREM_PHASE_1 (45 min): Hippocampal replay, pattern strengthening
        2. NREM_PHASE_2 (30 min): Synaptic homeostasis, pruning
        3. REM_PHASE (15 min): Dream exploration, creative insights
        4. WAKING (5 min): Finalize consolidation, emit stats
        5. Return to IDLE
        """
        # Phase 1: NREM_PHASE_1 (Light consolidation)
        await self.transition_to(SleepState.NREM_PHASE_1)
        await self.run_nrem_phase_1()

        # Phase 2: NREM_PHASE_2 (Deep consolidation)
        await self.transition_to(SleepState.NREM_PHASE_2)
        await self.run_nrem_phase_2()

        # Phase 3: REM_PHASE (Exploration)
        await self.transition_to(SleepState.REM_PHASE)
        await self.run_rem_phase()

        # Phase 4: WAKING (Finalize)
        await self.transition_to(SleepState.WAKING)
        await self.run_waking_phase()

        # Return to IDLE
        await self.transition_to(SleepState.IDLE)

    async def initialize_state_handlers(self, state: SleepState):
        """
        Initialize consolidation handlers for current state.

        Handler mappings:
        - NREM_PHASE_1: CONS_HIPPOCAMPAL (replay)
        - NREM_PHASE_2: CONS_SYNAPTIC (homeostasis), CONS_NEOCORTICAL (integration)
        - REM_PHASE: DREAM_EXPLORATION, DREAM_REHEARSAL
        """
        if state == SleepState.NREM_PHASE_1:
            # Initialize hippocampal replay
            await self.hippocampal_replay_handler.initialize()

        elif state == SleepState.NREM_PHASE_2:
            # Initialize synaptic homeostasis & neocortical integration
            await self.synaptic_homeostasis_handler.initialize()
            await self.neocortical_integration_handler.initialize()

        elif state == SleepState.REM_PHASE:
            # Initialize dream exploration
            await self.dream_exploration_handler.initialize()
```

### NREM Phase 1: Hippocampal Replay

```python
async def run_nrem_phase_1(self):
    """
    Execute NREM Phase 1: Hippocampal replay and pattern strengthening.

    Duration: 45 minutes

    Activities:
    - Replay episodic sequences (ADR-0084a)
    - Strengthen CA3 recurrent connections
    - Theta rhythm coordination (4-6 Hz slow theta)

    Performance:
    - Target: 100-150 memories replayed
    - Replay rate: ~2-3 memories/minute
    """
    phase_duration = self.durations[SleepState.NREM_PHASE_1]
    start_time = now()
    memories_replayed = 0

    while (now() - start_time).total_seconds() < phase_duration:
        # Check for interruption
        if await self.check_interruption():
            await self.handle_interruption()
            return

        # Execute one replay cycle
        await self.hippocampal_replay_handler.execute_replay_cycle(
            nrem_phase=NREMPhase.PHASE_1
        )

        memories_replayed += 1

        # Yield to other tasks (low priority)
        await asyncio.sleep(1)

    logger.info(
        "nrem_phase_1_complete",
        duration_seconds=(now() - start_time).total_seconds(),
        memories_replayed=memories_replayed
    )
```

### NREM Phase 2: Synaptic Homeostasis & Integration

```python
async def run_nrem_phase_2(self):
    """
    Execute NREM Phase 2: Synaptic homeostasis and neocortical integration.

    Duration: 30 minutes

    Activities:
    - Prune weak connections (synaptic homeostasis)
    - Extract episodic→semantic patterns
    - Knowledge graph consolidation

    Performance:
    - Target: 50-100 patterns extracted
    - Pruning: 500-1000 connections pruned
    """
    phase_duration = self.durations[SleepState.NREM_PHASE_2]
    start_time = now()

    patterns_extracted = 0
    connections_pruned = 0

    while (now() - start_time).total_seconds() < phase_duration:
        # Check for interruption
        if await self.check_interruption():
            await self.handle_interruption()
            return

        # Synaptic homeostasis (pruning)
        pruned = await self.synaptic_homeostasis_handler.prune_weak_connections()
        connections_pruned += pruned

        # Neocortical integration (episodic→semantic)
        extracted = await self.neocortical_integration_handler.extract_patterns()
        patterns_extracted += extracted

        # Yield to other tasks
        await asyncio.sleep(1)

    logger.info(
        "nrem_phase_2_complete",
        duration_seconds=(now() - start_time).total_seconds(),
        patterns_extracted=patterns_extracted,
        connections_pruned=connections_pruned
    )
```

### REM Phase: Dream Exploration

```python
async def run_rem_phase(self):
    """
    Execute REM Phase: Dream-like exploration and creative insights.

    Duration: 15 minutes

    Activities:
    - Explorative dreaming (semantic space random walks)
    - Counterfactual thinking (what-if scenarios)
    - Mental rehearsal (skill practice)
    - Reflection prompt generation

    Performance:
    - Target: 5-10 insights generated
    - Reflection prompts: 3-5 prompts
    """
    phase_duration = self.durations[SleepState.REM_PHASE]
    start_time = now()

    insights_generated = 0
    prompts_generated = 0

    while (now() - start_time).total_seconds() < phase_duration:
        # Check for interruption
        if await self.check_interruption():
            await self.handle_interruption()
            return

        # Dream exploration
        insights = await self.dream_exploration_handler.explore()
        insights_generated += len(insights)

        # Generate reflection prompts
        prompts = await self.dream_exploration_handler.generate_reflection_prompts()
        prompts_generated += len(prompts)

        # Yield to other tasks
        await asyncio.sleep(1)

    logger.info(
        "rem_phase_complete",
        duration_seconds=(now() - start_time).total_seconds(),
        insights_generated=insights_generated,
        prompts_generated=prompts_generated
    )
```

### Waking Phase: Finalization

```python
async def run_waking_phase(self):
    """
    Execute WAKING Phase: Finalize consolidation and emit statistics.

    Duration: 5 minutes

    Activities:
    - Flush pending writes to storage
    - Rebuild indexes (P13 Index Rebuild)
    - Generate consolidation summary
    - Emit completion event
    """
    phase_duration = self.durations[SleepState.WAKING]
    start_time = now()

    # Flush pending writes
    await self.flush_pending_writes()

    # Rebuild indexes for consolidated memories
    await self.rebuild_indexes()

    # Generate consolidation summary
    summary = await self.generate_consolidation_summary()

    # Emit completion event
    emit_event(
        topic="infra.consolidation.complete",
        data={
            "cycle_duration_seconds": (now() - start_time).total_seconds(),
            "memories_consolidated": summary['memories_consolidated'],
            "patterns_extracted": summary['patterns_extracted'],
            "insights_generated": summary['insights_generated'],
            "storage_freed_bytes": summary['storage_freed_bytes']
        }
    )

    logger.info("consolidation_complete", summary=summary)
```

---

## Interruption Handling

**Goal:** Handle user activity during consolidation without data loss.

### Interruption Detection

```python
async def check_interruption(self) -> bool:
    """
    Check if user activity requires pausing consolidation.

    Interruption triggers:
    - CPU usage >10% (user activity detected)
    - User input (keyboard, mouse, touchscreen)
    - New episodic entry (ongoing interaction)
    - Battery level <30% (preserve power)

    Returns: True if interruption detected, False otherwise
    """
    cpu_usage = await get_cpu_usage()
    user_input = await detect_user_input()
    battery_level = await get_battery_level()

    if cpu_usage > 0.10:
        logger.info("interruption_detected", reason="cpu_usage", cpu=cpu_usage)
        return True

    if user_input:
        logger.info("interruption_detected", reason="user_input")
        return True

    if battery_level < 0.30:
        logger.info("interruption_detected", reason="battery_low", battery=battery_level)
        return True

    return False
```

### Interruption Handler

```python
async def handle_interruption(self):
    """
    Pause consolidation and save progress.

    Strategy:
    - Save current state to K0 Offsets (resumable)
    - Emit interruption event
    - Transition to IDLE state
    - Schedule resume attempt in 30 minutes
    """
    # Save progress via K0 Offsets
    await self.save_consolidation_progress()

    # Emit interruption event
    emit_event(
        topic="infra.consolidation.interrupted",
        data={
            "state": self.current_state.value,
            "progress_pct": await self.calculate_progress_percentage(),
            "interruption_count": self.interruption_count
        }
    )

    self.interruption_count += 1

    # Transition to IDLE
    await self.transition_to(SleepState.IDLE)

    # Schedule resume attempt
    await self.schedule_resume(delay_minutes=30)

    logger.info(
        "consolidation_paused",
        interruption_count=self.interruption_count,
        resume_in_minutes=30
    )
```

### Resume Logic

```python
async def resume_consolidation(self):
    """
    Resume paused consolidation from saved progress.

    Steps:
    1. Load progress from K0 Offsets
    2. Check if idle conditions met
    3. Resume from saved state
    4. Continue consolidation cycle
    """
    # Load progress
    progress = await self.load_consolidation_progress()

    if progress is None:
        logger.warning("no_progress_found", action="skip_resume")
        return

    # Check idle conditions
    if not await self.check_idle_conditions():
        logger.info("not_idle", action="reschedule_resume")
        await self.schedule_resume(delay_minutes=30)
        return

    # Resume from saved state
    await self.transition_to(progress['state'])

    logger.info("consolidation_resumed", from_state=progress['state'].value)
```

---

## Resource Management

### CPU Priority

```python
def set_low_priority():
    """
    Set consolidation process to low CPU priority (nice +10).

    Platform-specific:
    - Linux: nice +10, ionice idle
    - Windows: BELOW_NORMAL_PRIORITY_CLASS
    - macOS: nice +10
    """
    if platform.system() == "Linux":
        os.nice(10)  # Increase niceness (lower priority)
        # Set I/O priority to idle
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())])

    elif platform.system() == "Windows":
        import win32process
        win32process.SetPriorityClass(
            win32api.GetCurrentProcess(),
            win32process.BELOW_NORMAL_PRIORITY_CLASS
        )
```

### Memory Cap

```python
def set_memory_limit(limit_mb: int = 256):
    """
    Limit consolidation process memory usage.

    Limit: 256 MB (configurable)

    Uses resource.setrlimit() on POSIX systems.
    """
    if platform.system() in ["Linux", "Darwin"]:
        import resource
        limit_bytes = limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
```

### CPU Affinity

```python
def set_cpu_affinity():
    """
    Restrict consolidation to last 2 CPU cores.

    Example (8-core system):
    - User processes: Cores 0-5
    - Consolidation: Cores 6-7
    """
    if platform.system() == "Linux":
        import psutil
        p = psutil.Process()
        cpu_count = psutil.cpu_count()

        # Assign to last 2 cores
        p.cpu_affinity([cpu_count - 2, cpu_count - 1])
```

---

## Performance Characteristics

### Cycle Timing

| Phase | Duration | Activities | Performance Target |
|-------|----------|------------|-------------------|
| NREM Phase 1 | 45 minutes | Hippocampal replay | 100-150 memories replayed |
| NREM Phase 2 | 30 minutes | Synaptic homeostasis, Integration | 50-100 patterns, 500-1000 pruned |
| REM Phase | 15 minutes | Dream exploration | 5-10 insights, 3-5 prompts |
| WAKING | 5 minutes | Finalization | Index rebuild, summary |
| **Total** | **95 minutes** | **Full cycle** | **<90 min target** |

### Resource Usage

- **CPU:** <5% average (nice +10 low priority)
- **Memory:** <256 MB (hard limit)
- **Disk I/O:** <5 MB/s (ionice idle)
- **Battery:** Pause if <30%

---

## Observability

### Metrics

```python
# Prometheus metrics
consolidation_cycle_duration_seconds = Histogram(
    'consolidation_cycle_duration_seconds',
    'Full consolidation cycle duration',
    buckets=[3600, 4500, 5400, 6000, 7200]  # 60-120 minutes
)

consolidation_interruptions_total = Counter(
    'consolidation_interruptions_total',
    'Total interruptions during consolidation'
)

consolidation_state_duration_seconds = Histogram(
    'consolidation_state_duration_seconds',
    'Duration in each state',
    ['state']
)
```

### Events

```
infra.consolidation.trigger             — Consolidation started
infra.consolidation.nrem_phase_1_start  — NREM Phase 1 started
infra.consolidation.nrem_phase_2_start  — NREM Phase 2 started
infra.consolidation.rem_phase_start     — REM Phase started
infra.consolidation.waking_start        — Waking phase started
infra.consolidation.interrupted         — Consolidation paused
infra.consolidation.resumed             — Consolidation resumed
infra.consolidation.complete            — Cycle finished
```

---

## Related ADRs

- **ADR-0084:** K0 Memory Consolidation Pipeline (parent)
- **ADR-0084a:** Sleep-Cycle Memory Replay Algorithms (NREM replay)
- **ADR-0084c:** Knowledge Graph Consolidation (NREM Phase 2)
- **ADR-0084d:** Dream-Like Exploration & Reflection (REM Phase)

---

## End of ADR-0084b