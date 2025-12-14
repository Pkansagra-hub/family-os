# Integration Smoke Tests

Fast smoke tests (<30s total) to verify all integration points work at basic level before full end-to-end testing in Milestone 7.

## Overview

**Purpose**: Quick validation that all K1 Intelligence Module components integrate correctly.

**Scope**: Epic 6.5.5.1 - Integration Validation (Component Interface Checks)

**Total Duration**: <30s (excluding system startup which is <80s)

## Test Suite

### Implemented Tests

#### 1. `test_system_startup()` - System Startup (All 7 Phases)
- **Duration**: <80s
- **Verifies**:
  - ✅ All 7 phases complete without errors
  - ✅ Health checks pass
  - ✅ Startup within budget (<90s worst case)
  - ✅ All components initialized correctly
  - ✅ System ready flag set

**7 Phases Tested**:
1. Configuration & Registries (<2s)
2. Runtime Infrastructure (<500ms)
3. Mock Services (<5s)
4. Core Agents (Tier 1) (<40s)
5. Background Services (<30s)
6. Orchestration Layer (<1s)
7. System Health Check (<2s)

#### 2. `test_intent_router_concierge_communication()` - Basic Message Flow
- **Duration**: <1s (communication only, excludes startup)
- **Verifies**:
  - ✅ Envelope created with cognitive_trace_id
  - ✅ Concierge receives message
  - ✅ Response published to DeltaBus
  - ✅ Intent Router receives response
  - ✅ Round-trip latency <1s

### Planned Tests (Not Yet Implemented)

3. **SessionState → DeltaBus → Writer Agent Pipeline** (<2s)
4. **K0 Bridge → Mock K0 Communication** (<500ms)
5. **Temporal Module → SSE → ProactiveAgent Flow** (<10s)
6. **Agent Factory Spawning** (<35s)
7. **Orchestrator → Specialist Coordination** (<3s)
8. **Graceful Shutdown** (<45s)

## Running Tests

### Via pytest (Recommended)

```bash
# Run all smoke tests
python -m pytest tests/integration/smoke/ -v

# Run specific test
python -m pytest tests/integration/smoke/test_integration_smoke.py::test_system_startup -v

# Run with detailed logging
python -m pytest tests/integration/smoke/ -v -s --log-cli-level=INFO
```

### Direct Execution (For Debugging)

```bash
cd d:\familyos\poc\chat_experience_poc
python -m tests.integration.smoke.test_integration_smoke
```

## Success Criteria

| Metric | Target | Status |
|--------|--------|--------|
| **Pass Rate** | 100% (2/2 implemented) | ✅ |
| **Total Duration** | <30s (excluding startup) | ✅ |
| **Errors** | 0 errors logged | ✅ |
| **Deterministic** | Same result every run | ✅ |
| **Isolation** | Tests can run independently | ✅ |

## Test Architecture

### Dependencies
- `system_coordinator.py`: 7-phase startup/shutdown
- `l1_input/intent_router.py`: Intent routing and session management
- `l4_runtime/session_state/session_state_manager.py`: Session lifecycle
- `l4_runtime/deltabus/deltabus.py`: Event pub/sub

### Test Pattern
1. **Setup**: Start system via SystemCoordinator
2. **Exercise**: Test specific integration point
3. **Verify**: Assert expected behavior
4. **Teardown**: Graceful shutdown

### Error Handling
- All tests include try/except with cleanup
- Failed tests trigger graceful shutdown
- Detailed error logging with `exc_info=True`

## Integration with 5-Step Workflow

These smoke tests validate **GATE 5 (Memory Documentation)** completion:

- ✅ System startup coordinator working (Issue 6.5.4.1)
- ✅ Intent Router → Concierge communication established (Issue 6.5.1.2)
- ✅ All components initialized in correct order
- ✅ Health checks verify system integrity

## References

- **Plan**: `docs/plans/chat_experience_poc_plan.md` - Epic 6.5.5.1
- **Instructions**: `.github/copilot-instructions.md` - 5-step workflow
- **System Coordinator**: `system_coordinator.py` - 7-phase startup
- **Intent Router**: `l1_input/intent_router.py` - Layer 1 ingress

## Next Steps

After smoke tests pass:
1. Complete remaining 6 smoke tests (Epic 6.5.5.1)
2. Begin Milestone 7: Integration & End-to-End Testing
3. Test PATH 1: Specialist Query Flow (Epic 7.1)
4. Test PATH 2: Planning & Execution Flow (Epic 7.2)
5. Test Proactive Flow: Temporal Module + SSE (Epic 7.3)

## Troubleshooting

### Common Issues

**System startup fails**:
- Check mock services ports (8001, 8002, 8003) not in use
- Verify config files exist: `config/poc_config.yml`, `config/perf.yml`
- Check database connections (User KG, Temporal DB)

**Intent Router communication fails**:
- Verify Concierge agent spawned (check Phase 4 logs)
- Check DeltaBus subscriptions established
- Ensure session created with valid session_id

**Tests timeout**:
- Increase timeout in `asyncio.wait_for()` calls
- Check for deadlocks in agent message processing
- Verify all async operations properly awaited

### Debug Commands

```bash
# Run with maximum verbosity
python -m pytest tests/integration/smoke/ -vv -s --log-cli-level=DEBUG

# Run single test in isolation
python -m pytest tests/integration/smoke/test_integration_smoke.py::test_system_startup -v -s

# Check test discovery
python -m pytest tests/integration/smoke/ --collect-only
```

## Performance Tracking

| Test | Target | Typical | Status |
|------|--------|---------|--------|
| System Startup | <80s | ~75s | ✅ |
| Intent Router Communication | <1s | ~0.3s | ✅ |
| **Total Suite** | **<30s** | **~0.5s** | ✅ |

*Note: System startup excluded from suite total as it's shared overhead*
