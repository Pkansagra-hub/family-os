# ADR-0061b: RED Metrics & Alerts for Backpressure Monitoring

**Status:** Proposed
**Date:** 2025-10-15
**Parent:** [ADR-0061: 3-Tier Backpressure Cascade](0061-3-tier-backpressure-cascade.md)
**Tier:** 1

## Context

Backpressure monitoring requires comprehensive observability to diagnose bottlenecks, measure degradation impact, and trigger timely operator intervention. The challenge: **how do we instrument the 3-tier cascade to provide actionable metrics and alerts without overwhelming operators with noise?**

**Problem Statement:**

Traditional monitoring approaches fail for backpressure systems:
- **Counter-only metrics**: Total requests rejected (no rate, duration, or error context)
- **Alert fatigue**: Too many low-priority alerts, operators ignore critical pages
- **No drill-down**: Can't identify which stream, stage, or operation caused backpressure
- **No historical context**: Can't correlate current backpressure with past incidents

**Industry Best Practice: RED Method**

RED methodology (Tom Wilkie, Prometheus/Grafana):
- **Rate**: Requests per second (throughput)
- **Errors**: Error rate (failed requests / total requests)
- **Duration**: Latency distribution (P50, P95, P99)

**K1 Requirement:** Apply RED to all 3 tiers (per-stream watermarks, voice pipeline stages, global limits) with drill-down capability from alert → dashboard → trace → root cause.

---

## Decision

We adopt **RED methodology** for backpressure observability with 3-tier instrumentation (Prometheus metrics → Grafana dashboards → Alertmanager rules → runbooks).

### **Core Principles**

**1. RED at Every Tier**
- Per-stream watermarks: Rate (queue additions/s), Errors (overflows), Duration (time in DEGRADE)
- Voice pipeline: Rate (audio frames/s), Errors (dropped frames), Duration (ASR latency)
- Global limits: Rate (total queue additions/s), Errors (OOM events), Duration (sustained backpressure)

**2. Cardinality Control (No Label Explosion)**
- Stream labels: `audio_frames`, `agent_mailbox`, `k0_outbox`, `sse_subscribers` (4 values)
- Stage labels: `asr_input`, `intent_queue`, `tool_executor`, `tts_queue`, `audio_output` (5 values)
- Level labels: `NORMAL`, `WARN`, `DEGRADE`, `REJECT` (4 values)
- **Total cardinality**: 4 streams × 4 levels = 16 series (manageable)

**3. Alert Severity Hierarchy**
- **INFO**: WARN watermark breached (log only, no page)
- **WARNING**: DEGRADE watermark breached (Slack notification)
- **CRITICAL**: REJECT watermark breached (PagerDuty page)
- **EMERGENCY**: Sustained REJECT >10s (PagerDuty page + escalation)

**4. Runbook-Driven Alerts**
- Every alert links to runbook with diagnosis steps
- Runbooks include: symptom → diagnosis → mitigation → root cause analysis
- Example: "BackpressureReject_AudioFrames" → Runbook #BPR-001

---

## Prometheus Metrics Specification

### **Tier 1: Per-Stream Watermarks (RED)**

**Rate Metrics:**

```python
# Queue additions per second (rate)
backpressure_queue_additions_total = Counter(
    'backpressure_queue_additions_total',
    'Total items added to queue',
    ['stream']  # audio_frames, agent_mailbox, k0_outbox, sse_subscribers
)

# Query: rate(backpressure_queue_additions_total[1m])
# Example: audio_frames at 80 additions/sec
```

**Error Metrics:**

```python
# Queue overflows (errors)
backpressure_overflows_total = Counter(
    'backpressure_overflows_total',
    'Total queue overflow events',
    ['stream', 'action']  # action: drop_oldest, block_sender, merge_deltas, disconnect_slow
)

# Error rate: rate(backpressure_overflows_total[1m]) / rate(backpressure_queue_additions_total[1m])
# Example: 5 overflows / 80 additions = 6.25% error rate
```

**Duration Metrics:**

```python
# Time spent in watermark levels (duration)
backpressure_watermark_duration_seconds = Histogram(
    'backpressure_watermark_duration_seconds',
    'Time spent in each watermark level',
    ['stream', 'level'],  # level: WARN, DEGRADE, REJECT
    buckets=[0.01, 0.1, 1.0, 5.0, 10.0, 30.0, 60.0]  # 10ms to 60s
)

# Query: histogram_quantile(0.95, rate(backpressure_watermark_duration_seconds_bucket[5m]))
# Example: P95 time in DEGRADE = 2.3 seconds
```

**Gauge Metrics (Current State):**

```python
# Current queue depth (snapshot)
backpressure_queue_depth = Gauge(
    'backpressure_queue_depth',
    'Current queue depth',
    ['stream']
)

# Current watermark level (0=NORMAL, 1=WARN, 2=DEGRADE, 3=REJECT)
backpressure_watermark_level = Gauge(
    'backpressure_watermark_level',
    'Current watermark level',
    ['stream']
)

# Queue utilization percentage
backpressure_queue_utilization_pct = Gauge(
    'backpressure_queue_utilization_pct',
    'Queue utilization (depth / max_depth)',
    ['stream']
)
```

---

### **Tier 2: Voice Pipeline (RED)**

**Rate Metrics:**

```python
# Audio frames ingested per second
voice_asr_frames_ingested_total = Counter(
    'voice_asr_frames_ingested_total',
    'Total audio frames ingested by ASR',
    ['session_id']
)

# Intents processed per second
voice_intents_processed_total = Counter(
    'voice_intents_processed_total',
    'Total intents processed',
    ['priority']  # CRITICAL, REALTIME, INTERACTIVE, BACKGROUND
)

# Tool calls per second
voice_tools_executed_total = Counter(
    'voice_tools_executed_total',
    'Total tools executed',
    ['tool_name', 'result']  # result: success, timeout, killed
)
```

**Error Metrics:**

```python
# ASR frame drops (errors)
voice_asr_frames_dropped_total = Counter(
    'voice_asr_frames_dropped_total',
    'Total ASR frames dropped due to backpressure',
    ['reason']  # partial_drop, downsample, pause
)

# Intent queue drops (errors)
voice_intents_dropped_total = Counter(
    'voice_intents_dropped_total',
    'Total intents dropped',
    ['priority', 'reason']  # reason: duplicate_merged, priority_shed, queue_full
)

# Tool kills (errors)
voice_tools_killed_total = Counter(
    'voice_tools_killed_total',
    'Total tools killed due to backpressure',
    ['tool_name', 'reason']  # reason: long_running, ephemeral_shed
)

# TTS degradation events (errors)
voice_tts_degraded_total = Counter(
    'voice_tts_degraded_total',
    'Total TTS quality degradation events',
    ['degradation_type']  # concatenative, speedup, truncate
)
```

**Duration Metrics:**

```python
# ASR processing latency
voice_asr_latency_ms = Histogram(
    'voice_asr_latency_ms',
    'ASR processing latency in milliseconds',
    buckets=[10, 25, 50, 100, 200, 500]  # 10ms to 500ms
)

# Intent classification latency
voice_intent_latency_ms = Histogram(
    'voice_intent_latency_ms',
    'Intent classification latency',
    buckets=[5, 10, 25, 50, 100, 200]  # 5ms to 200ms, target <50ms P95
)

# Tool execution latency
voice_tool_latency_ms = Histogram(
    'voice_tool_latency_ms',
    'Tool execution latency',
    ['tool_name'],
    buckets=[50, 100, 250, 500, 1000, 2000, 5000]  # 50ms to 5s
)

# TTS synthesis latency
voice_tts_latency_ms = Histogram(
    'voice_tts_latency_ms',
    'TTS synthesis latency',
    buckets=[50, 100, 200, 500, 1000]  # 50ms to 1s
)
```

**Gauge Metrics (Voice Pipeline State):**

```python
# ASR buffer length (milliseconds)
voice_asr_buffer_ms = Gauge(
    'voice_asr_buffer_ms',
    'ASR input buffer length in milliseconds',
    ['session_id']
)

# Intent queue size
voice_intent_queue_size = Gauge(
    'voice_intent_queue_size',
    'Current intent queue size'
)

# Active tool count
voice_tool_executor_active = Gauge(
    'voice_tool_executor_active',
    'Number of currently executing tools'
)

# TTS queue buffer (milliseconds)
voice_tts_buffer_ms = Gauge(
    'voice_tts_buffer_ms',
    'TTS queue buffer length in milliseconds'
)

# Audio output buffer (milliseconds)
voice_audio_output_buffer_ms = Gauge(
    'voice_audio_output_buffer_ms',
    'Audio output buffer length in milliseconds'
)
```

---

### **Tier 3: Global Limits (RED)**

**Rate Metrics:**

```python
# Total queue additions across all streams
backpressure_global_additions_total = Counter(
    'backpressure_global_additions_total',
    'Total queue additions across all streams'
)

# Rate: rate(backpressure_global_additions_total[1m])
```

**Error Metrics:**

```python
# Global backpressure events
backpressure_global_events_total = Counter(
    'backpressure_global_events_total',
    'Total global backpressure events',
    ['event_type']  # memory_critical, queue_critical, sustained_backpressure
)

# OOM near-miss events
backpressure_oom_near_miss_total = Counter(
    'backpressure_oom_near_miss_total',
    'OOM near-miss events (>95% memory)'
)
```

**Duration Metrics:**

```python
# Sustained backpressure duration
backpressure_sustained_duration_seconds = Gauge(
    'backpressure_sustained_duration_seconds',
    'Duration of sustained backpressure (>10s continuous)'
)

# Time to recovery (histogram)
backpressure_recovery_time_seconds = Histogram(
    'backpressure_recovery_time_seconds',
    'Time from REJECT to NORMAL state',
    ['stream'],
    buckets=[1, 5, 10, 30, 60, 300]  # 1s to 5min
)
```

**Gauge Metrics (Global State):**

```python
# Total in-flight memory
backpressure_global_memory_mb = Gauge(
    'backpressure_global_memory_mb',
    'Total in-flight memory across all queues (MB)'
)

# Total queue items
backpressure_global_queue_items = Gauge(
    'backpressure_global_queue_items',
    'Total queue items across all streams'
)

# Global memory utilization percentage
backpressure_global_memory_pct = Gauge(
    'backpressure_global_memory_pct',
    'Global memory utilization (memory_mb / 512MB max)'
)

# Global queue utilization percentage
backpressure_global_queue_pct = Gauge(
    'backpressure_global_queue_pct',
    'Global queue utilization (items / 5000 max)'
)
```

---

## Grafana Dashboard Specification

### **Dashboard 1: Backpressure Overview (Executive View)**

**Purpose:** High-level system health for operators.

**Panels:**

1. **Global Memory Utilization (Gauge)**
   - Query: `backpressure_global_memory_pct`
   - Thresholds: Green (<80%), Yellow (80-90%), Red (>90%)
   - Target: <80% P95

2. **Global Queue Utilization (Gauge)**
   - Query: `backpressure_global_queue_pct`
   - Thresholds: Green (<80%), Yellow (80-90%), Red (>90%)
   - Target: <80% P95

3. **Active Backpressure Streams (Stat)**
   - Query: `count(backpressure_watermark_level > 1)`
   - Shows: Number of streams in WARN/DEGRADE/REJECT

4. **Sustained Backpressure Duration (Stat)**
   - Query: `backpressure_sustained_duration_seconds`
   - Alert: Page if >10s

5. **Per-Stream Queue Depth (Time Series)**
   - Query: `backpressure_queue_depth`
   - Legend: `{{stream}}`
   - Y-axis: Queue depth (items)

6. **Per-Stream Watermark Level (Heatmap)**
   - Query: `backpressure_watermark_level`
   - Colors: Green (NORMAL), Yellow (WARN), Orange (DEGRADE), Red (REJECT)
   - X-axis: Time, Y-axis: Stream

---

### **Dashboard 2: Per-Stream Drill-Down (Diagnostic View)**

**Purpose:** Detailed analysis of specific stream bottlenecks.

**Panels (per stream):**

1. **Queue Depth Over Time (Time Series)**
   - Query: `backpressure_queue_depth{stream="audio_frames"}`
   - Annotations: Mark WARN/DEGRADE/REJECT thresholds

2. **Queue Addition Rate (Time Series)**
   - Query: `rate(backpressure_queue_additions_total{stream="audio_frames"}[1m])`
   - Y-axis: Items/second

3. **Overflow Error Rate (Time Series)**
   - Query: `rate(backpressure_overflows_total{stream="audio_frames"}[1m])`
   - Y-axis: Errors/second
   - Target: <0.1% error rate

4. **Time in DEGRADE (Histogram)**
   - Query: `histogram_quantile(0.95, rate(backpressure_watermark_duration_seconds_bucket{stream="audio_frames", level="DEGRADE"}[5m]))`
   - Stat: P95 duration in DEGRADE state

5. **Overflow Actions Breakdown (Pie Chart)**
   - Query: `sum by (action) (backpressure_overflows_total{stream="audio_frames"})`
   - Shows: drop_oldest vs block_sender vs merge_deltas vs disconnect_slow

---

### **Dashboard 3: Voice Pipeline Health (Voice-Specific View)**

**Purpose:** Monitor voice processing stages end-to-end.

**Panels:**

1. **Voice Pipeline Latency (Time Series, Stacked)**
   - Queries:
     - ASR: `histogram_quantile(0.95, rate(voice_asr_latency_ms_bucket[5m]))`
     - Intent: `histogram_quantile(0.95, rate(voice_intent_latency_ms_bucket[5m]))`
     - Tool: `histogram_quantile(0.95, rate(voice_tool_latency_ms_bucket[5m]))`
     - TTS: `histogram_quantile(0.95, rate(voice_tts_latency_ms_bucket[5m]))`
   - Target: Total E2E <2000ms P95

2. **ASR Frame Drops (Counter)**
   - Query: `sum by (reason) (rate(voice_asr_frames_dropped_total[5m]))`
   - Legend: partial_drop, downsample, pause

3. **Intent Queue Drops (Counter)**
   - Query: `sum by (priority, reason) (rate(voice_intents_dropped_total[5m]))`
   - Target: CRITICAL priority drops = 0

4. **Tool Executor Utilization (Gauge)**
   - Query: `(voice_tool_executor_active / 20) * 100`
   - Threshold: Red if >90% (18/20 tools active)

5. **TTS Quality Degradation (Counter)**
   - Query: `sum by (degradation_type) (rate(voice_tts_degraded_total[5m]))`
   - Shows: concatenative, speedup, truncate events

6. **Audio Output Buffer Health (Time Series)**
   - Query: `voice_audio_output_buffer_ms`
   - Thresholds: Yellow (>340ms), Red (>380ms)

---

## Alerting Rules (Prometheus Alertmanager)

### **Alert Severity Levels**

| Severity | Trigger Condition | Notification | Response Time |
|----------|------------------|--------------|---------------|
| **INFO** | WARN watermark breached | Log only | Monitor |
| **WARNING** | DEGRADE watermark breached | Slack #k1-alerts | 15 minutes |
| **CRITICAL** | REJECT watermark breached | PagerDuty page | 5 minutes |
| **EMERGENCY** | Sustained REJECT >10s | PagerDuty page + escalation | Immediate |

---

### **Alerting Rules Configuration**

**alert_backpressure.yml:**

```yaml
groups:
  - name: backpressure_alerts
    interval: 10s  # Evaluate every 10s

    rules:
      # ===== TIER 1: PER-STREAM WATERMARKS =====

      - alert: BackpressureWarn_AudioFrames
        expr: backpressure_watermark_level{stream="audio_frames"} >= 1
        for: 1m
        labels:
          severity: info
          tier: 1
          stream: audio_frames
        annotations:
          summary: "Audio frames queue at 80% capacity"
          description: "audio_frames queue depth: {{ $value }} (WARN threshold breached)"
          runbook: "https://runbooks.k1.dev/BPR-001"

      - alert: BackpressureDegrade_AudioFrames
        expr: backpressure_watermark_level{stream="audio_frames"} >= 2
        for: 30s
        labels:
          severity: warning
          tier: 1
          stream: audio_frames
        annotations:
          summary: "Audio frames queue degrading (drop_oldest active)"
          description: "audio_frames dropping oldest frames to prevent overflow"
          runbook: "https://runbooks.k1.dev/BPR-001"
          action: "Check ASR ingestion rate, consider rate limiting"

      - alert: BackpressureReject_AudioFrames
        expr: backpressure_watermark_level{stream="audio_frames"} >= 3
        for: 10s
        labels:
          severity: critical
          tier: 1
          stream: audio_frames
        annotations:
          summary: "CRITICAL: Audio frames queue rejecting new frames"
          description: "audio_frames at 95% capacity, blocking new audio"
          runbook: "https://runbooks.k1.dev/BPR-001"
          action: "IMMEDIATE: Pause ASR ingestion, shed background work"

      # ===== AGENT MAILBOX ALERTS =====

      - alert: BackpressureDegrade_AgentMailbox
        expr: backpressure_watermark_level{stream="agent_mailbox"} >= 2
        for: 30s
        labels:
          severity: warning
          tier: 1
          stream: agent_mailbox
        annotations:
          summary: "Agent mailbox blocking senders (503 responses)"
          description: "agent_mailbox returning 503 Service Unavailable"
          runbook: "https://runbooks.k1.dev/BPR-002"
          action: "Check agent processing latency, review message rate"

      - alert: BackpressureReject_AgentMailbox
        expr: backpressure_watermark_level{stream="agent_mailbox"} >= 3
        for: 10s
        labels:
          severity: critical
          tier: 1
          stream: agent_mailbox
        annotations:
          summary: "CRITICAL: Agent mailbox at capacity"
          description: "Control message delivery failing, coordination at risk"
          runbook: "https://runbooks.k1.dev/BPR-002"
          action: "IMMEDIATE: Review agent state, check for deadlock"

      # ===== K0 OUTBOX ALERTS =====

      - alert: BackpressureDegrade_K0Outbox
        expr: backpressure_watermark_level{stream="k0_outbox"} >= 2
        for: 1m
        labels:
          severity: warning
          tier: 1
          stream: k0_outbox
        annotations:
          summary: "K0 outbox merging deltas (compression active)"
          description: "k0_outbox merging StateDelta messages to reduce pressure"
          runbook: "https://runbooks.k1.dev/BPR-003"
          action: "Check K0 bridge throughput, review receipt batching"

      - alert: BackpressureReject_K0Outbox
        expr: backpressure_watermark_level{stream="k0_outbox"} >= 3
        for: 30s
        labels:
          severity: critical
          tier: 1
          stream: k0_outbox
        annotations:
          summary: "CRITICAL: K0 outbox at capacity"
          description: "Receipt delivery stalled, SessionState persistence at risk"
          runbook: "https://runbooks.k1.dev/BPR-003"
          action: "IMMEDIATE: Check K0 connectivity, review network latency"

      # ===== TIER 2: VOICE PIPELINE =====

      - alert: VoiceASRFrameDrops
        expr: rate(voice_asr_frames_dropped_total[1m]) > 5
        for: 30s
        labels:
          severity: warning
          tier: 2
          pipeline_stage: asr_input
        annotations:
          summary: "ASR dropping frames (>5/sec)"
          description: "Audio quality degraded, {{ $value }} frames/sec dropped"
          runbook: "https://runbooks.k1.dev/VOICE-001"
          action: "Check ASR latency, consider downsampling to 8kHz"

      - alert: VoiceIntentQueueOverload
        expr: (voice_intent_queue_size / 50) * 100 > 85
        for: 1m
        labels:
          severity: warning
          tier: 2
          pipeline_stage: intent_queue
        annotations:
          summary: "Intent queue at {{ $value }}% capacity"
          description: "Intent classification backlog, dropping BACKGROUND intents"
          runbook: "https://runbooks.k1.dev/VOICE-002"
          action: "Review intent classifier latency, check for duplicate intents"

      - alert: VoiceToolExecutorSaturation
        expr: (voice_tool_executor_active / 20) * 100 > 90
        for: 30s
        labels:
          severity: critical
          tier: 2
          pipeline_stage: tool_executor
        annotations:
          summary: "Tool executor saturated ({{ $value }}% utilization)"
          description: "18+ tools executing concurrently, killing long-running tools"
          runbook: "https://runbooks.k1.dev/VOICE-003"
          action: "IMMEDIATE: Shed ephemeral tools, kill >2000ms executions"

      - alert: VoiceTTSQualityDegraded
        expr: rate(voice_tts_degraded_total[1m]) > 2
        for: 30s
        labels:
          severity: warning
          tier: 2
          pipeline_stage: tts_queue
        annotations:
          summary: "TTS quality degraded (>2 events/sec)"
          description: "Voice quality reduced: {{ $labels.degradation_type }}"
          runbook: "https://runbooks.k1.dev/VOICE-004"
          action: "Check TTS queue depth, review synthesis latency"

      # ===== TIER 3: GLOBAL LIMITS =====

      - alert: BackpressureGlobalMemoryCritical
        expr: backpressure_global_memory_pct > 95
        for: 10s
        labels:
          severity: critical
          tier: 3
        annotations:
          summary: "CRITICAL: Global memory at {{ $value }}% (OOM risk)"
          description: "Total in-flight memory approaching 512MB limit"
          runbook: "https://runbooks.k1.dev/BPR-GLOBAL-001"
          action: "IMMEDIATE: Shed background work, disconnect slow SSE clients"

      - alert: BackpressureGlobalQueueCritical
        expr: backpressure_global_queue_items > 4750
        for: 10s
        labels:
          severity: critical
          tier: 3
        annotations:
          summary: "CRITICAL: Global queue items at {{ $value }} (cascade risk)"
          description: "Total queue items approaching 5000 limit"
          runbook: "https://runbooks.k1.dev/BPR-GLOBAL-002"
          action: "IMMEDIATE: Apply cascading degradation (Stage 1-4)"

      - alert: BackpressureSustained
        expr: backpressure_sustained_duration_seconds > 10
        for: 0s  # Fire immediately (duration already >10s)
        labels:
          severity: emergency
          tier: 3
        annotations:
          summary: "EMERGENCY: Sustained backpressure {{ $value }}s (capacity crisis)"
          description: "System under continuous load, cascading failure imminent"
          runbook: "https://runbooks.k1.dev/BPR-SUSTAINED"
          action: "ESCALATE: Ops lead + Platform eng, consider emergency capacity scaling"
```

---

## Runbooks

### **Runbook #BPR-001: Audio Frames Backpressure**

**Symptom:** `BackpressureDegrade_AudioFrames` alert firing

**Diagnosis Steps:**

1. Check ASR ingestion rate:
   ```promql
   rate(voice_asr_frames_ingested_total[1m])
   ```
   - Normal: 50-80 fps
   - High: >90 fps (exceeds processing capacity)

2. Check ASR processing latency:
   ```promql
   histogram_quantile(0.95, rate(voice_asr_latency_ms_bucket[5m]))
   ```
   - Target: <100ms P95
   - Degraded: >200ms P95

3. Check frame drop reason:
   ```promql
   sum by (reason) (rate(voice_asr_frames_dropped_total[5m]))
   ```
   - `partial_drop`: Normal (interim frames)
   - `downsample`: High load (8kHz fallback)
   - `pause`: Critical (ASR paused)

**Mitigation:**

1. **Immediate (DEGRADE state)**:
   - Apply ASR downsampling (16kHz → 8kHz)
   - Drop partial frames (keep final frames only)
   - Monitor queue depth recovery

2. **Short-term (REJECT state)**:
   - Pause ASR ingestion (show "thinking..." spinner)
   - Shed background work (drop BACKGROUND intents)
   - Disconnect slowest SSE clients (bottom 5%)

3. **Long-term (prevent recurrence)**:
   - Review ASR model performance (check for regression)
   - Tune watermark thresholds (increase WARN from 80 → 85)
   - Consider horizontal scaling (add ASR worker)

**Root Cause Analysis (RCA) Template:**

```markdown
# RCA: Audio Frames Backpressure (Incident #2025-10-15-001)

## Timeline
- 14:30 UTC: WARN alert fired (80% capacity)
- 14:32 UTC: DEGRADE alert fired (90% capacity, drop_oldest active)
- 14:35 UTC: Mitigation applied (downsample to 8kHz)
- 14:37 UTC: Queue depth recovered to 60% (NORMAL)

## Root Cause
ASR ingestion rate spike from 70 fps → 120 fps due to:
- Voice barge-in bug (duplicate frames submitted)
- Hotfix deployed to prevent duplicate submissions

## Action Items
1. [ ] Fix barge-in duplicate frame bug (#1234)
2. [ ] Add unit test for barge-in frame deduplication
3. [ ] Tune WARN watermark from 80 → 85 frames (reduce false positives)
```

---

### **Runbook #BPR-SUSTAINED: Sustained Backpressure**

**Symptom:** `BackpressureSustained` alert firing (>10s continuous)

**Diagnosis Steps:**

1. Identify affected streams:
   ```promql
   backpressure_watermark_level > 1
   ```

2. Check global utilization:
   ```promql
   backpressure_global_memory_pct
   backpressure_global_queue_pct
   ```

3. Review sustained duration:
   ```promql
   backpressure_sustained_duration_seconds
   ```

**Mitigation (4-Stage Cascading Degradation):**

**Stage 1: Drop BACKGROUND Priority**
```bash
curl -X POST http://localhost:8080/admin/degradation/stage1
```
- Drop all BACKGROUND intents
- Shed ephemeral tools (weather, news, stocks)
- Expected recovery: 50% of sustained cases

**Stage 2: Drop INTERACTIVE Priority**
```bash
curl -X POST http://localhost:8080/admin/degradation/stage2
```
- Drop INTERACTIVE intents (non-user-facing)
- Kill long-running tools (>2000ms)
- Expected recovery: 80% of sustained cases

**Stage 3: Throttle REALTIME Priority**
```bash
curl -X POST http://localhost:8080/admin/degradation/stage3
```
- Rate limit REALTIME to 10 msg/s
- Disconnect slowest 10% SSE clients
- Expected recovery: 95% of sustained cases

**Stage 4: CRITICAL Only (Emergency Mode)**
```bash
curl -X POST http://localhost:8080/admin/degradation/stage4
```
- Accept CRITICAL priority only (RED band, safety checks)
- All other requests rejected with 503
- **This is emergency mode, requires ops lead approval**

**Escalation:**
- Notify ops lead (PagerDuty escalation policy)
- Notify platform engineering (capacity planning)
- Consider emergency capacity scaling (add K1 instance)

---

## Consequences

### **Positive**

✅ **Actionable metrics**: RED methodology provides Rate/Errors/Duration for diagnosis
✅ **Drill-down capability**: Alert → Dashboard → Trace → Root cause
✅ **Runbook-driven**: Every alert links to specific runbook with steps
✅ **Cardinality control**: 16 series per stream (manageable, no label explosion)

### **Negative**

⚠️ **Alert complexity**: 15+ alert rules require careful tuning
⚠️ **Runbook maintenance**: Runbooks must stay current with code changes
⚠️ **Grafana expertise**: Operators need training on dashboard drill-down

---

## References

- [ADR-0061: 3-Tier Backpressure Cascade](0061-3-tier-backpressure-cascade.md) — Parent ADR
- [ADR-0061a: Watermark Thresholds](0061a-watermark-thresholds.md) — Threshold calculations
- Tom Wilkie, "The RED Method" (Prometheus/Grafana best practices)
- Google SRE Book, Chapter 6: Monitoring Distributed Systems
- Prometheus Alerting Best Practices: https://prometheus.io/docs/practices/alerting/

---

**Status:** Proposed
**Implementation:** Phase 4 (Week 4) - Observability & tuning
