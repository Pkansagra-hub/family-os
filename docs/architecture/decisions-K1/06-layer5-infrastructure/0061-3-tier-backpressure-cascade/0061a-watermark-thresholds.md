---
adr_number: 0061a
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l4_runtime.watermark_monitor
- k1.l5_infrastructure.threshold_controller
- k1.l1_input.stream_monitor
authors:
- K1 Architecture Team
concerns:
- architecture
- observability
- performance
- privacy
- reliability
- scalability
- security
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_phase: Phase 4 (Performance Optimization)
implementation_status: IN_PROGRESS
related_adrs:
- ADR-0061
- ADR-0061b
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer3_execution/model_request.fbs
research_citations:
- Adaptive Threshold Management (Abdelzaher et al., 1999)
- Queue Length Monitoring (Kleinrock, 1976)
- Early Warning Systems (Floyd & Jacobson, 1993)
status: PROPOSED
title: Watermark Thresholds (80/90/95%)
---

# ADR-0061a: Watermark Thresholds (80/90/95%)

**Status:** Proposed
**Date:** 2025-10-15
**Parent:** [ADR-0061: 3-Tier Backpressure Cascade](0061-3-tier-backpressure-cascade.md)
**Tier:** 1

## Context

Per-stream watermark monitoring requires precise threshold configuration to achieve graceful degradation without false positives. The challenge: **how do we determine the right watermark percentages (80%, 90%, 95%) to trigger warn/degrade/reject actions across diverse stream types (audio, agents, K0 bridge, SSE)?**

**Problem Statement:**

Different stream types have different characteristics:
- **Audio frames**: High throughput (50-100 fps), latency-sensitive (<50ms), lossy compression acceptable
- **Agent mailbox**: Low throughput (5-20 msg/s), reliability-critical (control messages), no loss acceptable
- **K0 outbox**: Medium throughput (100-500 receipts/s), compression-friendly (delta merging), moderate latency tolerance
- **SSE subscribers**: Variable throughput (1-50 events/s per client), client-specific (slow clients exist), disconnection acceptable

**Current Industry Practice:**

- **TCP Congestion Control**: RED (Random Early Detection) uses 25%/75% min/max thresholds
- **WebRTC**: Voice/video buffering uses 50%/75%/90% thresholds for quality degradation
- **Kafka**: Broker quotas use 80%/90%/95% thresholds for throttling/rejection
- **Envoy Proxy**: Circuit breakers use 80%/90%/95% for connection pools

**K1 Requirement:** Balance early warning (avoid false positives) with safety margin (avoid OOM).

---

## Decision

We adopt **80% WARN, 90% DEGRADE, 95% REJECT** as standard watermarks across all stream types, with per-stream tuning for special cases.

### **Watermark Calculation Formula**

For a stream with maximum depth `N`:
- **WARN threshold** = `0.80 * N` (80%) → Alert only, no action
- **DEGRADE threshold** = `0.90 * N` (90%) → Apply degradation action
- **REJECT threshold** = `0.95 * N` (95%) → Block new items, force shedding

**Rationale for 80/90/95:**

1. **80% WARN**: Provides 5-10s lead time for operators to respond before critical threshold
2. **90% DEGRADE**: Safety margin of 10% before rejection, allows graceful quality reduction
3. **95% REJECT**: Final 5% buffer prevents overflow, hard limit enforcement

**Safety Margin Analysis:**

- **Below 80%**: Normal operation, no backpressure
- **80-89%**: Warning zone, monitor closely, no user impact
- **90-94%**: Degradation zone, reduced quality, user may notice slower responses
- **95-100%**: Rejection zone, block new work, emergency shedding

---

### **Per-Stream Watermark Configuration**

#### **1. Audio Frames (Ring Buffer)**

**Characteristics:**
- Ring buffer, fixed size (100 frames max)
- High throughput (50-100 fps at 16kHz)
- Latency-sensitive (<50ms end-to-end)
- Lossy compression acceptable (interim frames droppable)

**Configuration:**
```yaml
audio_frames:
  high: 100           # Max frames
  warn: 80            # 80 frames (80%)
  degrade: 90         # 90 frames (90%)
  reject: 95          # 95 frames (95%)
  action: drop_oldest # Drop oldest frames first
  recovery_low: 60    # Resume normal at 60 frames (60%)
```

**Overflow Action: `drop_oldest`**
- Drop oldest frames in ring buffer
- Newest frames most relevant for real-time processing
- Audio quality degrades (skips) but continues

**Recovery Policy:**
- Resume normal operation when depth drops below 60% (60 frames)
- Hysteresis prevents flapping (oscillation between DEGRADE and NORMAL)

---

#### **2. Agent Mailbox (MPSC Queue)**

**Characteristics:**
- MPSC (multi-producer, single-consumer) queue
- Low throughput (5-20 msg/s per agent)
- Reliability-critical (control messages for coordination)
- No loss acceptable (agent protocol requires all messages)

**Configuration:**
```yaml
agent_mailbox:
  high: 50                # Max messages per agent
  warn: 40                # 40 messages (80%)
  degrade: 45             # 45 messages (90%)
  reject: 48              # 48 messages (95%)
  action: block_sender    # Return 503 to sender
  recovery_low: 30        # Resume normal at 30 messages (60%)
```

**Overflow Action: `block_sender`**
- Return 503 Service Unavailable to sender with `Retry-After: 100ms`
- Sender backs off, preventing further overload
- No message loss (sender retries)

**Recovery Policy:**
- Resume accepting messages when depth drops below 60% (30 messages)
- Retry-After header guides sender backoff strategy

---

#### **3. K0 Outbox (Priority Queue)**

**Characteristics:**
- Priority queue (CRITICAL → REALTIME → INTERACTIVE → BACKGROUND)
- High throughput (100-500 receipts/s)
- Compression-friendly (multiple state deltas mergeable)
- Moderate latency tolerance (100-200ms acceptable)

**Configuration:**
```yaml
k0_outbox:
  high: 1000              # Max receipts
  warn: 800               # 800 receipts (80%)
  degrade: 900            # 900 receipts (90%)
  reject: 950             # 950 receipts (95%)
  action: merge_deltas    # Merge consecutive StateDelta messages
  recovery_low: 600       # Resume normal at 600 receipts (60%)
  merge_window_ms: 500    # Merge deltas within 500ms window
  max_merge_count: 10     # Merge up to 10 deltas per operation
```

**Overflow Action: `merge_deltas`**
- Combine multiple `StateDelta` messages for same entity
- Reduces queue depth by 2-3× (typical compression ratio)
- No data loss (deltas are associative)

**Example Delta Merging:**
```python
# Before merging (3 messages)
StateDelta(entity="agent_123", field="memory_mb", value=100)
StateDelta(entity="agent_123", field="memory_mb", value=120)
StateDelta(entity="agent_123", field="memory_mb", value=150)

# After merging (1 message)
StateDelta(entity="agent_123", field="memory_mb", value=150)  # Last value wins
```

**Recovery Policy:**
- Resume normal operation at 60% (600 receipts)
- Continue merging until below 60% to prevent flapping

---

#### **4. SSE Subscribers (Per-Client Buffer)**

**Characteristics:**
- Per-client buffer (200 events max per subscriber)
- Variable throughput (1-50 events/s per client)
- Client-specific (slow clients exist, fast clients unaffected)
- Disconnection acceptable (clients can reconnect)

**Configuration:**
```yaml
sse_subscribers:
  high: 200                     # Max events per client
  warn: 150                     # 150 events (75%)
  degrade: 180                  # 180 events (90%)
  reject: 190                   # 190 events (95%)
  action: disconnect_slow       # Disconnect slowest clients
  recovery_low: 100             # Resume normal at 100 events (50%)
  disconnect_threshold: 200     # Disconnect if ≥200 buffered
  slow_client_percentile: 95    # Disconnect bottom 5% (slowest)
```

**Overflow Action: `disconnect_slow_clients`**
- Identify slowest clients (95th percentile buffer depth)
- Disconnect slowest 5% of clients
- Fast clients unaffected
- Slow clients can reconnect and catch up

**Recovery Policy:**
- Resume normal operation at 50% (100 events)
- Lower threshold than other streams (prevents oscillation)

---

### **Watermark Tuning Strategy**

**Phase 1: Initial Deployment (Weeks 1-2)**
- Use default 80/90/95 thresholds
- Collect baseline metrics (queue depths, watermark breaches, false positives)
- Monitor Grafana dashboards for patterns

**Phase 2: Analysis (Week 3)**
- Analyze false positive rate (WARN alerts with no follow-up DEGRADE)
- Identify streams with frequent breaches (candidates for tuning)
- Calculate optimal thresholds using queuing theory (M/M/1 model)

**Phase 3: Tuning (Week 4)**
- Adjust per-stream thresholds based on analysis
- Example: If `audio_frames` shows 50% false positive rate at 80%, increase WARN to 85%
- Re-deploy and measure improvement

**Phase 4: Continuous Monitoring (Ongoing)**
- Weekly review of watermark breach metrics
- Quarterly re-tuning based on production workload changes

**Queuing Theory Formula (M/M/1):**

For a stream with:
- Arrival rate λ (requests/sec)
- Service rate μ (requests/sec)
- Utilization ρ = λ/μ

Optimal WARN threshold: `WARN = N * ρ + 2 * sqrt(N * ρ * (1 - ρ))`

**Example (audio_frames):**
- λ = 80 fps (arrival rate)
- μ = 100 fps (service rate, max throughput)
- ρ = 0.8 (80% utilization)
- N = 100 (max buffer size)

`WARN = 100 * 0.8 + 2 * sqrt(100 * 0.8 * 0.2) = 80 + 2 * 4 = 88 frames`

**Result:** Tune WARN from 80 → 88 frames based on queuing theory.

---

### **Recovery Policies (Hysteresis)**

**Why Hysteresis?**

Without hysteresis, watermark states oscillate rapidly:
```
Time 0: depth=89 → WARN (emit alert)
Time 1: depth=79 → NORMAL (clear alert)
Time 2: depth=81 → WARN (emit alert again)
Time 3: depth=78 → NORMAL (clear alert again)
```

Result: Alert storm, operator fatigue, no useful signal.

**Hysteresis Solution:**

Add recovery threshold below action threshold:
```yaml
warn: 80        # Trigger WARN at 80%
recovery_low: 60  # Clear WARN at 60%
```

With hysteresis:
```
Time 0: depth=81 → WARN (emit alert)
Time 1: depth=79 → WARN (stay in WARN, no new alert)
Time 2: depth=59 → NORMAL (clear alert, depth dropped below 60%)
```

Result: Stable states, meaningful alerts, no flapping.

**Per-Stream Recovery Thresholds:**

| Stream | WARN | DEGRADE | REJECT | Recovery Low | Hysteresis Gap |
|--------|------|---------|--------|--------------|----------------|
| audio_frames | 80 | 90 | 95 | 60 | 20% |
| agent_mailbox | 40 | 45 | 48 | 30 | 10 msg |
| k0_outbox | 800 | 900 | 950 | 600 | 200 receipts |
| sse_subscribers | 150 | 180 | 190 | 100 | 50 events |

**Hysteresis Gap Rationale:**
- **Larger gap**: Reduces flapping, but slower recovery signal
- **Smaller gap**: Faster recovery signal, but more oscillation
- **K1 choice**: 20-25% gap (balance stability vs responsiveness)

---

### **Watermark State Machine**

**4 States:**
1. **NORMAL**: depth < WARN threshold
2. **WARN**: WARN ≤ depth < DEGRADE
3. **DEGRADE**: DEGRADE ≤ depth < REJECT
4. **REJECT**: depth ≥ REJECT

**State Transitions:**

```
       ┌───────────────────────────────────────┐
       │                                       │
       ▼           depth ≥ 80              ┌────────┐
┌──────────┐   ─────────────────────────>  │  WARN  │
│  NORMAL  │                                └────────┘
└──────────┘   <──────────────────────────     │
       ▲           depth < 60                   │
       │                                        │ depth ≥ 90
       │                                        ▼
       │                                   ┌──────────┐
       │           depth < 60              │ DEGRADE  │
       └───────────────────────────────────┤          │
                                           └──────────┘
                                                │
                                                │ depth ≥ 95
                                                ▼
                                           ┌──────────┐
                   depth < 60              │  REJECT  │
           ────────────────────────────────┤          │
                                           └──────────┘
```

**Transition Rules:**

1. **NORMAL → WARN**: depth ≥ WARN threshold (80%)
2. **WARN → DEGRADE**: depth ≥ DEGRADE threshold (90%)
3. **DEGRADE → REJECT**: depth ≥ REJECT threshold (95%)
4. **REJECT → NORMAL**: depth < recovery_low (60%)
5. **DEGRADE → NORMAL**: depth < recovery_low (60%)
6. **WARN → NORMAL**: depth < recovery_low (60%)

**Key Property**: All recovery transitions go directly to NORMAL (no intermediate states on recovery).

---

### **Implementation Pseudocode**

```python
# k1/infrastructure/backpressure/watermark_checker.py
from dataclasses import dataclass
from enum import Enum

class WatermarkLevel(Enum):
    NORMAL = 0
    WARN = 1
    DEGRADE = 2
    REJECT = 3

@dataclass
class WatermarkState:
    current_level: WatermarkLevel
    current_depth: int
    last_transition_ms: int
    breach_count: int  # For sustained breach detection

class WatermarkChecker:
    """Evaluate watermarks for a single stream"""

    def __init__(self, stream_config: StreamConfig):
        self.config = stream_config
        self.state = WatermarkState(
            current_level=WatermarkLevel.NORMAL,
            current_depth=0,
            last_transition_ms=0,
            breach_count=0
        )

    def evaluate(self, current_depth: int) -> tuple[WatermarkLevel, str | None]:
        """
        Evaluate watermark level and return (level, action)

        Args:
            current_depth: Current queue depth

        Returns:
            (WatermarkLevel, action_name | None)
        """
        prev_level = self.state.current_level
        new_level = self._calculate_level(current_depth)
        action = None

        # State transition
        if new_level != prev_level:
            self.state.last_transition_ms = time.time_ns() // 1_000_000

            if new_level == WatermarkLevel.WARN:
                self.emit_alert("watermark_warn", depth=current_depth)

            elif new_level == WatermarkLevel.DEGRADE:
                action = self.config.action
                self.emit_alert("watermark_degrade", depth=current_depth, action=action)

            elif new_level == WatermarkLevel.REJECT:
                action = self.config.action
                self.emit_critical("watermark_reject", depth=current_depth, action=action)

            elif new_level == WatermarkLevel.NORMAL and prev_level != WatermarkLevel.NORMAL:
                self.emit_recovery("watermark_recovered", depth=current_depth)
                self.state.breach_count = 0  # Reset sustained breach counter

        # Sustained breach detection
        if new_level in [WatermarkLevel.DEGRADE, WatermarkLevel.REJECT]:
            self.state.breach_count += 1
            if self.state.breach_count >= 100:  # 100ms at 1kHz poll = sustained
                self.emit_sustained("watermark_sustained", level=new_level, duration_ms=100)
        else:
            self.state.breach_count = 0

        self.state.current_level = new_level
        self.state.current_depth = current_depth

        return (new_level, action)

    def _calculate_level(self, current_depth: int) -> WatermarkLevel:
        """Calculate watermark level with hysteresis"""

        # Check thresholds (with hysteresis on recovery)
        if current_depth >= self.config.reject:
            return WatermarkLevel.REJECT

        elif current_depth >= self.config.degrade:
            return WatermarkLevel.DEGRADE

        elif current_depth >= self.config.warn:
            return WatermarkLevel.WARN

        elif current_depth < self.config.recovery_low:
            # Recovery: Drop to NORMAL if below recovery threshold
            return WatermarkLevel.NORMAL

        else:
            # In-between zone: Stay in current state (hysteresis)
            return self.state.current_level
```

---

### **Metrics & Alerting**

**Prometheus Metrics:**

```python
# Queue depth (gauge)
backpressure_queue_depth = Gauge(
    'backpressure_queue_depth',
    'Current queue depth',
    ['stream']
)

# Watermark level (gauge, 0=NORMAL, 1=WARN, 2=DEGRADE, 3=REJECT)
backpressure_watermark_level = Gauge(
    'backpressure_watermark_level',
    'Current watermark level',
    ['stream']
)

# Watermark breaches (counter)
backpressure_watermark_breaches_total = Counter(
    'backpressure_watermark_breaches_total',
    'Total watermark breaches',
    ['stream', 'level']
)

# Actions taken (counter)
backpressure_actions_total = Counter(
    'backpressure_actions_total',
    'Total backpressure actions',
    ['stream', 'action']
)

# Sustained breaches (counter)
backpressure_sustained_breaches_total = Counter(
    'backpressure_sustained_breaches_total',
    'Sustained watermark breaches (>100ms)',
    ['stream', 'level']
)
```

**Grafana Alerts:**

```yaml
# Alert: Watermark WARN
- alert: BackpressureWarn
  expr: backpressure_watermark_level{level="WARN"} == 1
  for: 1m
  annotations:
    summary: "Stream {{ $labels.stream }} at 80% capacity"
    description: "Queue depth approaching limit, monitor closely"

# Alert: Watermark DEGRADE
- alert: BackpressureDegrade
  expr: backpressure_watermark_level{level="DEGRADE"} == 1
  for: 30s
  annotations:
    summary: "Stream {{ $labels.stream }} degrading service"
    description: "Quality reduction active, investigate bottleneck"

# Alert: Watermark REJECT (PAGE)
- alert: BackpressureReject
  expr: backpressure_watermark_level{level="REJECT"} == 1
  for: 10s
  annotations:
    summary: "CRITICAL: Stream {{ $labels.stream }} rejecting requests"
    description: "System overloaded, immediate action required"
    severity: page
```

---

## Consequences

### **Positive**

✅ **Predictable degradation**: 80/90/95 thresholds provide clear warning stages
✅ **Stream-specific tuning**: Per-stream configuration handles diverse characteristics
✅ **Hysteresis stability**: Recovery thresholds prevent flapping
✅ **Queuing theory foundation**: M/M/1 model provides scientific basis for tuning

### **Negative**

⚠️ **Tuning complexity**: Requires 4-week tuning period per stream
⚠️ **False positives**: Conservative 80% WARN may alert too frequently
⚠️ **Per-stream overhead**: Each stream requires separate configuration and monitoring

---

## References

- [ADR-0061: 3-Tier Backpressure Cascade](0061-3-tier-backpressure-cascade.md) — Parent ADR
- `architecture_diagrams/k1_backpressure_cascade.mmd` — Watermark visualization
- RFC 2309: Random Early Detection (RED) gateways for congestion control
- RFC 8033: Proportional Integral Controller Enhanced (PIE) for Active Queue Management
- Kafka KIP-13: Broker Quotas (80/90/95 thresholds)

---

**Status:** Proposed
**Implementation:** Phase 1 (Week 1) - Watermark checker core logic