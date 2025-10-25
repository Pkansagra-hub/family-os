# Phase 1 Quick Start Guide

**Read this first:** This is your quick reference for Phase 1 implementation.

**Full Plan:** See [Phase_1.md](./Phase_1.md) for complete step-by-step details.

---

## 🚀 Quick Overview

**Duration:** 4 weeks
**Goal:** Build Layer 5 Infrastructure (foundation for all K1 layers)
**Team:** 2-3 engineers

---

## 📅 Weekly Breakdown

### Week 1: K0 Bridge Core
**Build:** 5 clients to communicate with K0 kernel

1. **command_client.py** - Write memories to K0 (<50ms GREEN, <200ms AMBER/RED)
2. **query_client.py** - Read memories from K0 (<100ms)
3. **sse_client.py** - Receive K0 events in real-time (<5ms)
4. **batch_client.py** - Batch SessionState deltas (<10ms)
5. **observability_client.py** - Push metrics/logs to K0 (<20ms)

**Key Context:**
- Read: `docs/architecture/decisions/0001a-k0-bridge-communication-protocol.md`
- Reference: `k0/ports/command.py`, `k0/ports/query.py`, `k0/ports/sse.py`
- Contracts: `k0/contracts/jsonschema/*.json`

### Week 2: Event Bus & Resilience
**Build:** Cross-layer communication and fault tolerance

6. **event_bus.py** - Pub/sub for Layer 1→2 (<5ms delivery)
7. **schemas.py** - Event type definitions
8. **circuit_breaker.py** - 3-state FSM for failure prevention (<10ms)
9. **retry_policy.py** - Exponential backoff (100→400→1600ms)
10. **hot_reload.py** - Config file watcher (<100ms reload)

**Key Context:**
- Read: `docs/architecture/decisions/0004a-layer1-2-event-bus-communication.md`
- Read: `docs/architecture/decisions/0009-circuit-breaker-pattern.md`
- Reference: `k0/bus/core.py` (inspiration, not dependency)

### Week 3: Thermal & Observability
**Build:** Device thermal management and monitoring stack

11. **thermal/monitor.py** - NPU/GPU/CPU temperature polling (<5ms)
12. **thermal/placement_planner.py** - 4-tier cascade (NPU→GPU→CPU→Remote) (<10ms)
13. **observability/metrics.py** - Prometheus metrics (50+ metrics, <10ms)
14. **observability/tracing.py** - OpenTelemetry tracing (<5ms spans)
15. **observability/logging.py** - Structured JSON logs (<5ms)
16. **observability/dashboards.py** - Grafana dashboard definitions

**Key Context:**
- Read: `docs/architecture/decisions/0026-thermal-hysteresis-matrix.md`
- Read: `k1/l5_infrastructure/layer5_adr_map.md` (sections 3-5)

### Week 4: Config & Connectors
**Build:** Configuration management and connection lifecycle

17. **config/loader.py** - YAML config loading (<50ms)
18. **config/schema_validator.py** - JSON schema validation (<10ms)
19. **config/config_manager.py** - Hot reload orchestrator (<100ms)
20. **connectors/k0_connector.py** - HTTP/2 connection pooling (>90% hit rate)
21. **connectors/model_hub_client.py** - Model Hub interface (placeholder)

---

## 📖 Step-by-Step Process Per Module

For **each module** you build:

### 1. Read Context First (30 minutes)
```powershell
# Read the ADR
code docs/architecture/decisions/<relevant_adr>.md

# Read K0 reference implementation (if applicable)
code k0/ports/<relevant_port>.py

# Read contracts
code k0/contracts/jsonschema/<relevant_schema>.json
```

### 2. Create Module File (2-3 hours)
```powershell
# Navigate to module location
cd d:\familyos\k1\l5_infrastructure\<category>

# Create Python file
New-Item -Path <module_name>.py -ItemType File

# Add docstring with:
# - Purpose
# - ADR references
# - K0 references (where to look for context)
# - Performance budget
```

### 3. Implement Core Logic (4-6 hours)
- Follow the implementation steps in [Phase_1.md](./Phase_1.md)
- Reference K0 code for patterns
- Add type hints and docstrings
- Include `cognitive_trace_id` propagation

### 4. Add Observability (1 hour)
```python
# Add metrics
from prometheus_client import Counter, Histogram

<module>_requests_total = Counter(...)
<module>_latency_ms = Histogram(...)

# Add structured logging
import structlog
logger = structlog.get_logger(__name__)

logger.info("<event>", cognitive_trace_id=..., **context)
```

### 5. Write Tests (2-3 hours)
```powershell
# Create test file
New-Item -Path tests/k1/l5_infrastructure/<category>/test_<module>.py

# Write unit tests (>80% coverage target)
# Write integration tests (if applicable)
```

### 6. Run Tests (15 minutes)
```powershell
# Unit tests
python -m ward test --path tests/k1/l5_infrastructure/<category>/

# Integration tests (requires K0 running)
python -m ward test --path tests/k1/l5_infrastructure/integration/ --tags integration
```

### 7. Performance Test (30 minutes)
```python
# Verify performance budget
@pytest.mark.performance
def test_<module>_latency():
    latencies = []
    for _ in range(100):
        start = time.time()
        # ... operation ...
        latencies.append((time.time() - start) * 1000)

    p95 = np.percentile(latencies, 95)
    assert p95 < BUDGET_MS, f"P95 {p95}ms exceeds {BUDGET_MS}ms budget"
```

---

## 🎯 Success Criteria Checklist

### Week 1: K0 Bridge
- [ ] Command client: 200+ writes, <50ms P95 (GREEN)
- [ ] Query client: 100+ queries, <100ms P95
- [ ] SSE client: 1000+ events, <5ms delivery
- [ ] Integration: Write→Query→SSE workflow passes

### Week 2: Event Bus & Resilience
- [ ] Event bus: 1000+ events/sec, <5ms P95
- [ ] Circuit breaker: Opens after 3 failures, closes after recovery
- [ ] All unit tests pass (>80% coverage)

### Week 3: Thermal & Observability
- [ ] Thermal: Read NPU/GPU/CPU temps, 4-tier cascade decisions
- [ ] Observability: 50+ Prometheus metrics, tracing, logging
- [ ] All tests pass

### Week 4: Config & Connectors
- [ ] Config: Load YAML, hot reload <100ms
- [ ] Connectors: K0 pool >90% hit rate
- [ ] All integration tests pass

---

## 📚 Where to Look for Context

### Before Coding ANY Module

**Priority 1 - Architecture Decisions:**
```
docs/architecture/decisions/<relevant_adr>.md
```

**Priority 2 - Layer 5 Module Map:**
```
k1/l5_infrastructure/layer5_adr_map.md
```

### When Implementing K0 Bridge (Week 1)

**K0 Port Implementations (actual running code):**
```
k0/ports/command.py    # Command Port handler
k0/ports/query.py      # Query Port handler
k0/ports/sse.py        # SSE Port handler
```

**K0 API Contracts (schemas):**
```
k0/contracts/openapi.k0.yaml           # OpenAPI spec
k0/contracts/jsonschema/envelope.schema.json  # Command envelope
k0/contracts/jsonschema/query.recall.request.json  # Query request
k0/contracts/jsonschema/receipt.schema.json  # Receipt response
```

**K0 Error Handling:**
```
k0/ports/errors.py     # Error envelope structure
k0/gate.py             # Minimal Gate validation
```

### When Implementing Event Bus (Week 2)

**K0 Event Bus (inspiration only, NOT a dependency):**
```
k0/bus/core.py         # Pub/sub pattern
k0/bus/middleware.py   # Message routing
```

**ADRs:**
```
docs/architecture/decisions/0004a-layer1-2-event-bus-communication.md
docs/architecture/decisions/0002-actor-model-agent-isolation.md
```

### When Implementing Circuit Breaker (Week 2)

**ADRs:**
```
docs/architecture/decisions/0009-circuit-breaker-pattern.md
docs/architecture/decisions/0009a-circuit-breaker-fsm-implementation.md
```

### When Implementing Thermal (Week 3)

**ADRs:**
```
docs/architecture/decisions/0026-thermal-hysteresis-matrix.md
docs/architecture/decisions/0026a-thermal-sensor-monitoring-state-detection.md
docs/architecture/decisions/0026c-model-placement-integration-thermal-cascade.md
```

---

## 🔧 Development Setup

### Prerequisites
```powershell
# 1. Python 3.11+
python --version

# 2. Install K0 dependencies
cd d:\familyos\k0
pip install -r requirements.txt

# 3. Start K0 (separate terminal)
python -m k0.kernel.main

# 4. Verify K0 running
curl http://localhost:5200/k0/health

# 5. Install K1 dependencies
cd d:\familyos\k1
pip install httpx prometheus-client opentelemetry-api structlog pyyaml watchdog
```

### Daily Workflow
```powershell
# 1. Start K0 (terminal 1)
cd d:\familyos\k0
python -m k0.kernel.main

# 2. Run tests (terminal 2)
cd d:\familyos
python -m ward test --path tests/k1/l5_infrastructure/

# 3. Check metrics (browser)
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000
```

---

## 🚨 Common Issues & Solutions

### Issue: K0 Not Running
**Solution:**
```powershell
# Check if K0 is running
curl http://localhost:5200/k0/health

# If not, start K0
cd d:\familyos\k0
python -m k0.kernel.main
```

### Issue: Import Errors
**Solution:**
```powershell
# Add k0 and k1 to PYTHONPATH
$env:PYTHONPATH = "d:\familyos;d:\familyos\k0;d:\familyos\k1"
```

### Issue: Schema Validation Errors
**Solution:**
- Read the JSON schema file in `k0/contracts/jsonschema/`
- Validate your envelope matches exactly
- Check required fields

### Issue: Performance Budget Exceeded
**Solution:**
1. Profile with `py-spy`:
   ```powershell
   pip install py-spy
   py-spy top -- python -m your_module
   ```
2. Check for blocking I/O
3. Verify connection pooling
4. Add caching where appropriate

---

## 📞 Getting Help

### Architecture Questions
- Read the ADR first: `docs/architecture/decisions/`
- Check Layer 5 ADR Map: `k1/l5_infrastructure/layer5_adr_map.md`
- Review K0 implementation: `k0/ports/`, `k0/bus/`, `k0/contracts/`

### Implementation Questions
- Check [Phase_1.md](./Phase_1.md) for step-by-step guidance
- Review K0 code for patterns
- Look at similar modules for reference

### Testing Questions
- See existing tests in `k0/tests/` for patterns
- Check WARD documentation for async testing
- Reference integration test examples in [Phase_1.md](./Phase_1.md)

---

## ✅ Next Steps

1. **Read [Phase_1.md](./Phase_1.md)** - Complete detailed plan
2. **Setup environment** - Prerequisites section
3. **Start Week 1, Issue 1.1.1** - Command client core
4. **Follow step-by-step** - Each issue has detailed steps
5. **Test continuously** - Run tests after each change
6. **Track progress** - Check success criteria weekly

---

**Remember:** Layer 5 is the **foundation**. Take time to do it right. All other layers depend on this infrastructure.

**Full Details:** [Phase_1.md](./Phase_1.md)
