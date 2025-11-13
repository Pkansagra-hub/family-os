# Temporal Module ↔ P05 Prospectives Integration Plan

## Executive Summary

**Problem**: Writer Agents write P05 (prospective) deltas to K0 Backend, but Temporal Module only queries local SQLite DB. This creates a gap where prospectives are written but not discovered by the scheduler.

**Solution**: Add K0 P05 query capability to Temporal Module so it discovers writer-generated prospectives and fires them as SSE events.

**Impact**: Enables complete proactive trigger flow:
```
User: "Remind me to drink water in 4 hours"
  ↓
SessionStateDelta → DeltaBus
  ↓
MemoryWriterAgent analyzes → Extracts P05 prospective with fire_time
  ↓
WriterCommand → MockCommandPort → BackendStorage (local K0 mock)
  ↓
Temporal Module scheduler queries Mock K0 P05 endpoint
  ↓
Discovers: prospective with fire_time="2025-11-08T18:00:00Z"
  ↓
Fire trigger → SSE event to Mock K0 SSE Server
  ↓
ProactiveAgent receives tick via SSE subscription
  ↓
Notifies user: "Time to drink water!"
```

---

## 1. Architecture Overview

### Current State (Gap)
```
┌─────────────────────────────────────────────────┐
│ Writer Agents                                   │
│ ├─ MemoryWriterAgent (P05: prospectives)        │
│ ├─ LearningExtractorAgent (P06: learning)       │
│ └─ SemanticEnricherAgent (P02: semantic)        │
└──────────────────┬──────────────────────────────┘
                   │ WriterCommand
                   ↓
        ┌──────────────────────────┐
        │ BackendStorage (local)   │
        │ ├─ episodic              │
        │ ├─ prospective ← P05 HERE│  ← MockCommandPort
        │ ├─ learning              │
        │ ├─ semantic              │
        │ └─ trace                 │
        └──────────────────────────┘
                   ↑
              K0 Backend
            (MockCommandPort)

┌─────────────────────────────────────────────────┐
│ Temporal Module (DISCONNECTED)                  │
│ ├─ Local SQLite DB (temporal_triggers.db)       │
│ ├─ Scheduler query: Only local triggers         │ ← GAP: Doesn't see P05!
│ ├─ Fire triggers → SSE events                   │
│ └─ Reschedule recurring                         │
└─────────────────────────────────────────────────┘

ProactiveAgent ← SSE listener (inactive without triggers)
```

### Target State (Integrated)
```
┌─────────────────────────────────────────────────┐
│ Writer Agents                                   │
│ ├─ MemoryWriterAgent → WriterCommand (P05)      │
│ ├─ LearningExtractorAgent → WriterCommand (P06) │
│ └─ SemanticEnricherAgent → WriterCommand (P02)  │
└──────────────┬──────────────────────────────────┘
               │
               ↓
   ┌───────────────────────────┐
   │ MockCommandPort           │
   │ ├─ Store WriterCommand    │
   │ └─ Persist to BackendStorage
   └───────────────────────────┘
               ↑
        ┌──────┴──────┐
        │             │
    Local DB     Mock K0 Backend
  (triggers)       (P05s)

┌──────────────────────────────────────────┐
│ Temporal Module (INTEGRATED)             │
│                                          │
│ Scheduler Loop (60s tick):               │
│ 1. Query local triggers (existing)       │
│ 2. NEW: Query Mock K0 P05 endpoint       │
│    ├─ Fetch active prospectives          │
│    ├─ Filter: fire_time <= NOW()         │
│    └─ Merge with local triggers          │
│ 3. Fire all due triggers → SSE events    │
│ 4. Reschedule recurring                  │
└──────────────────────────────────────────┘
                   ↓
          Mock K0 SSE Server
                   ↓
          ProactiveAgent (active!)
```

---

## 2. Implementation Details

### 2.1 Temporal Module Changes

#### New Method: `_fetch_prospectives_from_k0()`

```python
async def _fetch_prospectives_from_k0(self) -> List[Dict[str, Any]]:
    """
    Fetch active prospectives from Mock K0 P05 endpoint

    Calls: POST http://localhost:8001/k0/query
    Payload: {"query": "P05", "filters": {"active": true, "fire_time_lte": now}}

    Returns:
        List of prospective dicts with:
        - p05_id: str (unique identifier)
        - fire_time: str (ISO 8601)
        - message: str (user-facing text)
        - action: str (what to do)
        - user_id: str (owner)
        - confidence: float (0.0-1.0)
        - writer_id: str (which writer created)
        - metadata: dict (context)

    Performance:
        - Query time: <100ms P95
        - Network overhead: <50ms
        - Timeout: 5s (inherited from http_client)

    Error Handling:
        - Connection error → Log warning, return []
        - Timeout → Log warning, return []
        - Invalid response → Log error, return []
    """
    try:
        now = datetime.utcnow().isoformat() + "Z"

        # Query Mock K0 P05 endpoint
        response = await self.http_client.post(
            f"{self.k0_backend_url}/k0/query",
            json={
                "query": "P05",
                "filters": {
                    "active": True,
                    "fire_time_lte": now,
                    "fire_time_gte": (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
                },
                "limit": 1000
            },
            timeout=5.0
        )

        response.raise_for_status()
        data = response.json()

        # Extract P05 prospectives
        prospectives = data.get("prospectives", [])

        logger.debug(
            "[TemporalModule] Fetched prospectives from K0",
            count=len(prospectives),
            query_time_ms=data.get("query_time_ms", 0)
        )

        return prospectives

    except Exception as e:
        logger.warning(
            "[TemporalModule] Failed to fetch prospectives from K0",
            error=str(e),
            k0_url=self.k0_backend_url
        )
        return []
```

#### Modified Method: `_scheduler_loop()`

```python
async def _scheduler_loop(self):
    """
    Main scheduler loop - UPDATED to include K0 P05 queries

    Runs every 60 seconds:
    1. Query local triggers (existing)
    2. NEW: Query Mock K0 P05 endpoint
    3. Merge and deduplicate
    4. Fire all due triggers
    5. Reschedule recurring
    """
    logger.info("[TemporalModule] Scheduler loop started")

    while self.scheduler_running:
        try:
            start_time = time.time()

            # 1. Query local triggers (existing)
            local_triggers = self._get_due_triggers()

            # 2. NEW: Query K0 P05 prospectives
            k0_prospectives = await self._fetch_prospectives_from_k0()

            # 3. Convert K0 prospectives to trigger-like objects
            k0_triggers = self._prospectives_to_triggers(k0_prospectives)

            # 4. Merge (deduplicate by p05_id/trigger_id)
            all_triggers = self._merge_triggers(local_triggers, k0_triggers)

            logger.debug(
                "[TemporalModule] Scheduler tick",
                local_triggers=len(local_triggers),
                k0_prospectives=len(k0_prospectives),
                total_due=len(all_triggers)
            )

            # 5. Fire all triggers
            for trigger in all_triggers:
                await self._fire_trigger(trigger)

            # Calculate next tick
            elapsed = time.time() - start_time
            sleep_time = max(0, self.tick_interval - elapsed)

            logger.debug(
                "[TemporalModule] Scheduler tick complete",
                elapsed_ms=int(elapsed * 1000),
                sleep_time_s=int(sleep_time)
            )

            await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("[TemporalModule] Scheduler loop cancelled")
            break
        except Exception as e:
            logger.error("[TemporalModule] Scheduler loop error", error=str(e), exc_info=True)
            await asyncio.sleep(10)
```

#### New Helper Methods

```python
def _prospectives_to_triggers(self, prospectives: List[Dict]) -> List[Trigger]:
    """Convert K0 P05 prospectives to Trigger objects"""
    triggers = []

    for p05 in prospectives:
        try:
            trigger = Trigger(
                trigger_id=f"k0_p05_{p05['p05_id']}",  # Namespace to avoid conflicts
                trigger_type=TriggerType.TIME_BASED,
                fire_time=datetime.fromisoformat(p05["fire_time"].replace("Z", "")),
                message=p05["message"],
                action=p05["action"],
                user_id=p05["user_id"],
                metadata={
                    "source": "k0_p05",
                    "p05_id": p05["p05_id"],
                    "confidence": p05.get("confidence", 0.8),
                    "writer_id": p05.get("writer_id"),
                }
            )
            triggers.append(trigger)
        except Exception as e:
            logger.warning(
                "[TemporalModule] Failed to convert P05 to trigger",
                p05_id=p05.get("p05_id"),
                error=str(e)
            )

    return triggers

def _merge_triggers(self, local: List[Trigger], k0: List[Trigger]) -> List[Trigger]:
    """
    Merge local triggers with K0 prospectives

    Deduplication:
    - If trigger_id matches exactly → Use local (it may have updates)
    - If p05_id exists → Skip duplicate K0 prospective
    - Otherwise → Add K0 prospective
    """
    # Index local triggers by ID
    local_by_id = {t.trigger_id: t for t in local}
    k0_p05_ids = {t.metadata.get("p05_id") for t in k0 if t.metadata}

    # Start with all local triggers
    merged = list(local_by_id.values())

    # Add K0 prospectives not already present
    for k0_trigger in k0:
        if k0_trigger.trigger_id not in local_by_id:
            merged.append(k0_trigger)

    return merged
```

### 2.2 Configuration

Add K0 Backend URL to TemporalModule initialization:

```python
def __init__(
    self,
    db_path: Optional[Path] = None,
    sse_url: Optional[str] = None,
    k0_backend_url: Optional[str] = None  # NEW
):
    # ... existing code ...

    # K0 Backend URL for P05 queries
    self.k0_backend_url = k0_backend_url or "http://localhost:8001"

    # HTTP client for K0 and SSE
    self.http_client = httpx.AsyncClient(timeout=5.0)
```

### 2.3 BackgroundServicesManager Integration

Add Temporal Module initialization:

```python
def _init_temporal_module(self):
    """Initialize Temporal Module for prospective trigger scheduling"""
    from l5_infrastructure.temporal import get_temporal_module

    try:
        self.temporal_module = get_temporal_module(
            db_path=self.config.get("temporal_db_path"),
            sse_url=self.config.get("temporal_sse_url", "http://localhost:8002"),
            k0_backend_url=self.config.get("k0_backend_url", "http://localhost:8001")
        )

        logger.info("[BackgroundServicesManager] Temporal Module initialized")
        return True

    except Exception as e:
        logger.error("[BackgroundServicesManager] Failed to initialize Temporal Module", error=str(e))
        return False

async def _start_temporal_module(self):
    """Start Temporal Module scheduler"""
    try:
        if not self.temporal_module:
            logger.warning("[BackgroundServicesManager] Temporal Module not initialized")
            return False

        await self.temporal_module.start_scheduler()
        logger.info("[BackgroundServicesManager] Temporal Module scheduler started")
        return True

    except Exception as e:
        logger.error("[BackgroundServicesManager] Failed to start Temporal Module", error=str(e))
        return False

async def _stop_temporal_module(self):
    """Stop Temporal Module scheduler"""
    try:
        if self.temporal_module and self.temporal_module.scheduler_running:
            await self.temporal_module.stop_scheduler()
            logger.info("[BackgroundServicesManager] Temporal Module scheduler stopped")
    except Exception as e:
        logger.error("[BackgroundServicesManager] Error stopping Temporal Module", error=str(e))
```

Add to `start_all()` phases:

```python
async def start_all(self) -> bool:
    """Start all background services in correct order"""
    try:
        # GATE: Validate dependencies
        if not self._validate_dependencies():
            return False

        # Phase 1: Init K0 Bridge
        if not self._init_k0_bridge():
            return False

        # Phase 2: Init Temporal Module (NEW)
        if not self._init_temporal_module():
            return False

        # Phase 3: Spawn writer agents
        if not self._spawn_writer_agents():
            return False

        # Phase 4: Subscribe writers to DeltaBus
        if not await self._subscribe_writer_agents():
            return False

        # Phase 5: Start Temporal Module scheduler (NEW)
        if not await self._start_temporal_module():
            return False

        # Phase 6: Health verification
        if not self._verify_health():
            return False

        logger.info("[BackgroundServicesManager] All background services started successfully")
        return True

    except Exception as e:
        logger.error("[BackgroundServicesManager] Error starting all services", error=str(e))
        return False
```

---

## 3. Data Flow Diagrams

### 3.1 Write Flow: Writer → K0 Backend → BackendStorage

```
User Input: "Remind me in 4 hours"
        ↓
   SessionStateDelta
   {timestamp, action, entities, temporal_references}
        ↓
   DeltaBus.emit(delta)
        ↓
   MemoryWriterAgent.process_delta(delta)
        ├─ Groq LLM: Extract temporal triggers
        ├─ fire_time = now() + 4 hours
        └─ Confidence = 0.95
        ↓
   WriterCommand
   {delta_type: "prospective", fire_time, message, action, confidence}
        ↓
   MockCommandPort.handle_command()
        ├─ Validate command
        ├─ Create StoredDelta {trace_id, writer_id, confidence, timestamp}
        └─ Persist to BackendStorage
        ↓
   BackendStorage.prospectives[]
   [{p05_id, fire_time, message, action, user_id, confidence}]
```

### 3.2 Fire Flow: Temporal Module → K0 Query → SSE → ProactiveAgent

```
Scheduler Tick (60s interval)
        ↓
   Temporal Module._scheduler_loop()
        ├─ Local query: temporal_triggers.db
        │  └─ SELECT * WHERE fire_time <= NOW() AND active = 1
        │
        ├─ NEW K0 query: Mock K0 P05 endpoint
        │  ├─ POST http://localhost:8001/k0/query
        │  ├─ Payload: {query: "P05", filters: {fire_time_lte: now}}
        │  └─ Response: [{p05_id, fire_time, message, action, ...}]
        │
        ├─ Merge results (deduplicate)
        │
        ├─ For each due trigger:
        │  ├─ Create SSE event
        │  ├─ POST http://localhost:8002/fire
        │  ├─ Update fire_count and last_fired
        │  └─ Reschedule if recurring
        │
        └─ Log to trigger_history
        ↓
   Mock K0 SSE Server receives event
        ↓
   ProactiveAgent SSE listener
        ├─ Receives: {trigger_id, message, action}
        ├─ Routes to user session
        └─ Display notification: "Time to drink water!"
```

---

## 4. Testing Strategy

### 4.1 Unit Tests: K0 Query

**File**: `tests/integration/test_temporal_k0_integration.py`

```python
def test_fetch_prospectives_from_k0():
    """Test querying Mock K0 P05 endpoint"""
    temporal = get_temporal_module()

    # Mock response
    mock_prospectives = [
        {
            "p05_id": "p05_abc123",
            "fire_time": (datetime.utcnow() + timedelta(minutes=5)).isoformat() + "Z",
            "message": "Drink water",
            "action": "notification",
            "user_id": "user_1",
            "confidence": 0.95,
            "writer_id": "memory_writer_ai"
        }
    ]

    # Query Mock K0
    prospectives = await temporal._fetch_prospectives_from_k0()

    # Verify
    assert len(prospectives) > 0
    assert prospectives[0]["p05_id"] == "p05_abc123"

def test_prospectives_to_triggers():
    """Test converting P05 to Trigger objects"""
    temporal = get_temporal_module()

    prospectives = [
        {
            "p05_id": "p05_abc",
            "fire_time": datetime.utcnow().isoformat() + "Z",
            "message": "Reminder",
            "action": {"type": "notification"},
            "user_id": "user_1",
            "confidence": 0.9,
            "writer_id": "memory_ai"
        }
    ]

    triggers = temporal._prospectives_to_triggers(prospectives)

    assert len(triggers) == 1
    assert triggers[0].trigger_id == "k0_p05_p05_abc"
    assert triggers[0].trigger_type == TriggerType.TIME_BASED

def test_merge_triggers():
    """Test deduplication when merging local + K0 triggers"""
    temporal = get_temporal_module()

    local_trigger = Trigger(
        trigger_id="local_123",
        trigger_type=TriggerType.TIME_BASED,
        fire_time=datetime.utcnow() + timedelta(minutes=5),
        message="Local trigger",
        action="notify",
        user_id="user_1"
    )

    k0_trigger = Trigger(
        trigger_id="k0_p05_abc",
        trigger_type=TriggerType.TIME_BASED,
        fire_time=datetime.utcnow() + timedelta(minutes=3),
        message="K0 prospective",
        action="notify",
        user_id="user_1"
    )

    merged = temporal._merge_triggers([local_trigger], [k0_trigger])

    assert len(merged) == 2
    assert any(t.trigger_id == "local_123" for t in merged)
    assert any(t.trigger_id == "k0_p05_abc" for t in merged)
```

### 4.2 Integration Tests: End-to-End Flow

**File**: `tests/integration/test_temporal_p05_e2e.py`

```python
@pytest.mark.asyncio
async def test_write_p05_prospective_discovered_by_temporal():
    """
    End-to-end: Writer writes P05 → Temporal discovers → Fires trigger → SSE event

    Setup:
    1. Start BackgroundServicesManager (all services)
    2. Create SessionStateDelta
    3. Emit to DeltaBus → MemoryWriterAgent processes
    4. Writer creates WriterCommand with P05
    5. MockCommandPort stores to BackendStorage

    Execute:
    6. Wait for scheduler tick
    7. Temporal Module queries K0 P05 endpoint
    8. Discovers P05 prospective (fire_time in past)

    Verify:
    9. Trigger fired in SSE log
    10. trigger_history updated
    11. SSE event sent to Mock K0 SSE Server
    """
    manager = BackgroundServicesManager()

    # Start all services
    assert await manager.start_all()

    # Get dependencies
    session_state = manager.session_state_manager.get_session_state("user_1", "session_1")
    delta_bus = manager.delta_bus
    backend_storage = manager.k0_bridge.backend_storage
    temporal_module = manager.temporal_module

    # Create delta → trigger P05 extraction
    delta = SessionStateDelta(
        timestamp=datetime.utcnow(),
        action="add_reminder",
        entities=["water", "4_hours"],
        temporal_references=["in 4 hours"],
        context={"reminder_text": "Drink water"}
    )

    # Emit to DeltaBus → MemoryWriterAgent processes
    delta_bus.emit("session_state_changed", delta)

    # Wait for writer to process (adjust as needed)
    await asyncio.sleep(1)

    # Verify WriterCommand was sent → P05 stored
    prospectives = backend_storage.query_by_type("prospective")
    assert len(prospectives) > 0

    # Manually trigger scheduler tick (or wait 60s)
    due_triggers = temporal_module._get_due_triggers()
    k0_prospectives = await temporal_module._fetch_prospectives_from_k0()
    k0_triggers = temporal_module._prospectives_to_triggers(k0_prospectives)

    # Verify K0 prospectives discovered
    assert len(k0_triggers) > 0

    # Fire trigger
    for trigger in k0_triggers:
        await temporal_module._fire_trigger(trigger)

    # Verify SSE event sent
    sse_events = temporal_module._get_sse_events()  # TODO: Add tracking
    assert len(sse_events) > 0

    # Cleanup
    await manager.stop_all()
```

---

## 5. Metrics & Monitoring

### New Metrics

```python
# Temporal Module metrics

## Discovery Metrics
temporal_k0_prospectives_discovered  # Counter: prospectives found per query
temporal_local_triggers_found        # Counter: local triggers per query
temporal_merge_deduplicates          # Counter: duplicates skipped during merge

## Performance Metrics
temporal_k0_query_time_ms            # Histogram: Query to K0 P05 endpoint
temporal_scheduler_tick_duration_ms  # Histogram: Total scheduler tick time
temporal_trigger_fire_duration_ms    # Histogram: Time to fire single trigger

## Event Metrics
temporal_triggers_fired              # Counter: Triggers successfully fired
temporal_sse_events_sent             # Counter: SSE events to Mock K0 SSE Server
temporal_sse_errors                  # Counter: SSE send failures

## Health Metrics
temporal_scheduler_running            # Gauge: Boolean, is scheduler active
temporal_active_triggers              # Gauge: Count of active triggers
temporal_active_k0_prospectives       # Gauge: Count of active K0 P05s
```

### Logging Levels

```
DEBUG: Scheduler tick, prospective counts, merge results
INFO: Trigger fired, scheduler started/stopped
WARNING: K0 query failures, timeout, invalid responses
ERROR: SSE send failures, critical errors
```

---

## 6. Implementation Checklist

### Phase 1: Temporal Module Changes
- [ ] Add `_fetch_prospectives_from_k0()` method
- [ ] Add `_prospectives_to_triggers()` helper
- [ ] Add `_merge_triggers()` deduplication
- [ ] Update `_scheduler_loop()` to call K0 query
- [ ] Add `k0_backend_url` configuration
- [ ] Add metrics exports

### Phase 2: Integration Tests
- [ ] Unit test: K0 query isolation
- [ ] Unit test: P05 → Trigger conversion
- [ ] Unit test: Merge deduplication
- [ ] Integration test: End-to-end flow
- [ ] Integration test: Error handling (K0 down, timeout)
- [ ] Integration test: Performance (query time P95)

### Phase 3: BackgroundServicesManager Integration
- [ ] Add `_init_temporal_module()` method
- [ ] Add `_start_temporal_module()` async method
- [ ] Add `_stop_temporal_module()` async method
- [ ] Add to `start_all()` phase sequence
- [ ] Add to health checks
- [ ] Add to graceful shutdown

### Phase 4: Documentation
- [ ] Memory entry: Design decisions, files touched
- [ ] Update architecture diagrams
- [ ] Add to project plan
- [ ] Update ADR (if new architectural decision needed)

---

## 7. Configuration

### Environment Variables

```bash
# Temporal Module configuration
TEMPORAL_TICK_INTERVAL=60              # Scheduler tick in seconds
TEMPORAL_DB_PATH=/config/temporal_triggers.db
TEMPORAL_SSE_URL=http://localhost:8002
K0_BACKEND_URL=http://localhost:8001   # NEW: For P05 queries

# Logging
LOG_LEVEL=INFO
TEMPORAL_LOG_LEVEL=DEBUG               # Enable scheduler debugging
```

### Config File: `config/temporal_config.yml`

```yaml
temporal:
  tick_interval: 60              # seconds
  db_path: /config/temporal_triggers.db
  sse_url: http://localhost:8002
  k0_backend_url: http://localhost:8001  # NEW

  performance:
    k0_query_timeout: 5.0              # seconds
    prospective_batch_size: 1000        # max P05s per query
    lookback_window: 30                 # days

  health:
    check_interval: 60                 # seconds
    stale_threshold: 300               # seconds
```

---

## 8. Deployment Notes

### Backward Compatibility
- Existing local triggers continue to work unchanged
- K0 query failures are non-fatal (fallback to local only)
- Deduplication prevents double-firing

### Performance Impact
- Scheduler tick increases by ~100ms (K0 query + merge)
- Overall tick: ~60-65s instead of 60s (acceptable)
- Network dependency on Mock K0 (add circuit breaker if needed)

### Rollback
- If K0 query fails: Temporal Module operates on local triggers only
- No data loss (prospectives still in K0 Backend)
- Can be replayed after recovery

---

## 9. Related ADRs & Documents

- **ADR-0086**: Dynamic Agent Creation (MemoryWriterAgent references)
- **ADR-XXXX**: Writer Agent Architecture (CommandPort pattern)
- **Issue 6.5.3.2**: K0 Bridge Implementation (BackendStorage)
- **Issue 6.5.3.3**: Temporal Module Integration (this document)
- **Whiteboard**: Chat Experience PoC Flow

---

## 10. Next Steps

1. **Implement K0 Query** (Temporal Module changes)
2. **Add Integration Tests** (Verify P05 discovery)
3. **Wire to BackgroundServicesManager** (System integration)
4. **Performance Testing** (Verify P95 budgets)
5. **End-to-End PoC** (Complete flow validation)
