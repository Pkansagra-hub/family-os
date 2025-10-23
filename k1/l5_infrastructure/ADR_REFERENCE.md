# ADR Reference Guide: Layer 5 - Infrastructure

**Generated:** Auto-generated from ADR family map  
**Purpose:** Quick reference for ADRs relevant to Layer 5 - Infrastructure development

## Overview

This layer provides infrastructure services (event bus, metrics, storage).

**Total Relevant ADRs:** 165

---

## Quick Reference: All ADRs for Layer 5 - Infrastructure

| ADR | Title | Family |
|-----|-------|--------|
| [ADR-0001](../../docs/architecture/decisions/0001-*.md) | 0001 Memory Kernel | K0 Core |
| [ADR-0001a](../../docs/architecture/decisions/0001a-*.md) | 0001A K0 Communication | Bridge |
| [ADR-0001f](../../docs/architecture/decisions/0001f-*.md) | 0001F K0 Communication | Bridge |
| [ADR-0002d](../../docs/architecture/decisions/0002d-*.md) | 0002D Metrics | Observability |
| [ADR-0004](../../docs/architecture/decisions/0004-*.md) | 0004 Architecture | K1 Core |
| [ADR-0004a](../../docs/architecture/decisions/0004a-*.md) | 0004A Event Bus | K1 Core |
| [ADR-0004b](../../docs/architecture/decisions/0004b-*.md) | 0004B Dependencies | K1 Core |
| [ADR-0004c](../../docs/architecture/decisions/0004c-*.md) | 0004C Documentation | ADR Notes |
| [ADR-0004d](../../docs/architecture/decisions/0004d-*.md) | 0004D Testing | K1 Core |
| [ADR-0007d](../../docs/architecture/decisions/0007d-*.md) | 0007D Stage 4 Commit | 4-Stage Planning |
| [ADR-0008a](../../docs/architecture/decisions/0008a-*.md) | 0008A Idempotency | Saga Error Recovery |
| [ADR-0008c](../../docs/architecture/decisions/0008c-*.md) | 0008C Distributed State | Saga Error Recovery |
| [ADR-0009](../../docs/architecture/decisions/0009-*.md) | 0009 Core FSM | Circuit Breaker |
| [ADR-0009a](../../docs/architecture/decisions/0009a-*.md) | 0009A State Handlers | Circuit Breaker |
| [ADR-0009b](../../docs/architecture/decisions/0009b-*.md) | 0009B Configuration | Circuit Breaker |
| [ADR-0009c](../../docs/architecture/decisions/0009c-*.md) | 0009C Observability | Circuit Breaker |
| [ADR-0010c](../../docs/architecture/decisions/0010c-*.md) | 0010C Runtime Enforcement | Capability Security |
| [ADR-0010d](../../docs/architecture/decisions/0010d-*.md) | 0010D Audit Trail | Capability Security |
| [ADR-0011](../../docs/architecture/decisions/0011-*.md) | 0011 Serialization Core | FlatBuffers |
| [ADR-0011a](../../docs/architecture/decisions/0011a-*.md) | 0011A Schema Design | FlatBuffers |
| [ADR-0011b](../../docs/architecture/decisions/0011b-*.md) | 0011B Code Generation | FlatBuffers |
| [ADR-0011c](../../docs/architecture/decisions/0011c-*.md) | 0011C Performance | FlatBuffers |
| [ADR-0011d](../../docs/architecture/decisions/0011d-*.md) | 0011D Schema Evolution | FlatBuffers |
| [ADR-0012](../../docs/architecture/decisions/0012-*.md) | 0012 Schema Taxonomy | FlatBuffers Schemas |
| [ADR-0012e](../../docs/architecture/decisions/0012e-*.md) | 0012E Layer 5 Schemas | FlatBuffers Schemas |
| [ADR-0013](../../docs/architecture/decisions/0013-*.md) | 0013 SemVer Policy | Schema Versioning |
| [ADR-0013a](../../docs/architecture/decisions/0013a-*.md) | 0013A Version Registry | Schema Versioning |
| [ADR-0013b](../../docs/architecture/decisions/0013b-*.md) | 0013B CI/CD Automation | Schema Versioning |
| [ADR-0013c](../../docs/architecture/decisions/0013c-*.md) | 0013C Deprecation Workflow | Schema Versioning |
| [ADR-0013d](../../docs/architecture/decisions/0013d-*.md) | 0013D Contract Testing | Schema Versioning |
| [ADR-0014a](../../docs/architecture/decisions/0014a-*.md) | 0014A Content Negotiation | REST API Dual Format |
| [ADR-0014b](../../docs/architecture/decisions/0014b-*.md) | 0014B OpenAPI Generation | REST API Dual Format |
| [ADR-0014d](../../docs/architecture/decisions/0014d-*.md) | 0014D Client SDKs | REST API Dual Format |
| [ADR-0015](../../docs/architecture/decisions/0015-*.md) | 0015 Protocol Design | WebSocket Binary Protocol |
| [ADR-0015a](../../docs/architecture/decisions/0015a-*.md) | 0015A Protocol Design | WebSocket Binary Protocol |
| [ADR-0015b](../../docs/architecture/decisions/0015b-*.md) | 0015B Flow Control | WebSocket Binary Protocol |
| [ADR-0015c](../../docs/architecture/decisions/0015c-*.md) | 0015C Reconnection | WebSocket Binary Protocol |
| [ADR-0015d](../../docs/architecture/decisions/0015d-*.md) | 0015D Streaming | WebSocket Binary Protocol |
| [ADR-0015e](../../docs/architecture/decisions/0015e-*.md) | 0015E Client SDK | WebSocket Binary Protocol |
| [ADR-0016](../../docs/architecture/decisions/0016-*.md) | 0016 Event Taxonomy | SSE Event Schemas |
| [ADR-0016a](../../docs/architecture/decisions/0016a-*.md) | 0016A Event Taxonomy | SSE Event Schemas |
| [ADR-0016c](../../docs/architecture/decisions/0016c-*.md) | 0016C Filtering | SSE Event Schemas |
| [ADR-0016d](../../docs/architecture/decisions/0016d-*.md) | 0016D Browser Integration | SSE Event Schemas |
| [ADR-0019](../../docs/architecture/decisions/0019-*.md) | 0019 Serialization Core | FlatBuffers SessionState Serialization |
| [ADR-0019a](../../docs/architecture/decisions/0019a-*.md) | 0019A Schema Definition | FlatBuffers SessionState Serialization |
| [ADR-0019c](../../docs/architecture/decisions/0019c-*.md) | 0019C K0 WAL Integration | FlatBuffers SessionState Serialization |
| [ADR-0020](../../docs/architecture/decisions/0020-*.md) | 0020 Storage Architecture | Multi-Tier Storage |
| [ADR-0020b](../../docs/architecture/decisions/0020b-*.md) | 0020B Warm Tier (L2 SSD) | Multi-Tier Storage |
| [ADR-0021](../../docs/architecture/decisions/0021-*.md) | 0021 Retention Policies | Turn History Retention |
| [ADR-0021a](../../docs/architecture/decisions/0021a-*.md) | 0021A Policy Engine | Turn History Retention |
| [ADR-0021b](../../docs/architecture/decisions/0021b-*.md) | 0021B Privacy Band Overrides | Turn History Retention |
| [ADR-0021c](../../docs/architecture/decisions/0021c-*.md) | 0021C Compliance | Turn History Retention |
| [ADR-0022](../../docs/architecture/decisions/0022-*.md) | 0022 Batching Core | K0 Bridge Batching |
| [ADR-0022a](../../docs/architecture/decisions/0022a-*.md) | 0022A Batching Algorithm | K0 Bridge Batching |
| [ADR-0022b](../../docs/architecture/decisions/0022b-*.md) | 0022B HTTP/2 Integration | K0 Bridge Batching |
| [ADR-0022c](../../docs/architecture/decisions/0022c-*.md) | 0022C Backpressure | K0 Bridge Batching |
| [ADR-0022d](../../docs/architecture/decisions/0022d-*.md) | 0022D FlatBuffers Schema | K0 Bridge Batching |
| [ADR-0023c](../../docs/architecture/decisions/0023c-*.md) | 0023C K0 WAL Query | Cursor-Based Pagination |
| [ADR-0024](../../docs/architecture/decisions/0024-*.md) | 0024 Turn-Level Budgets | Performance Budgets |
| [ADR-0024a](../../docs/architecture/decisions/0024a-*.md) | 0024A Turn-Level Budgets | Performance Budgets |
| [ADR-0024b](../../docs/architecture/decisions/0024b-*.md) | 0024B Component-Level Budgets | Performance Budgets |
| [ADR-0024c](../../docs/architecture/decisions/0024c-*.md) | 0024C Memory Budgets | Performance Budgets |
| [ADR-0024d](../../docs/architecture/decisions/0024d-*.md) | 0024D Graceful Degradation | Performance Budgets |
| [ADR-0025](../../docs/architecture/decisions/0025-*.md) | 0025 Global Allocator | KV Cache Management |
| [ADR-0025a](../../docs/architecture/decisions/0025a-*.md) | 0025A Global Allocator | KV Cache Management |
| [ADR-0025b](../../docs/architecture/decisions/0025b-*.md) | 0025B Hybrid Eviction | KV Cache Management |
| [ADR-0025c](../../docs/architecture/decisions/0025c-*.md) | 0025C Cache Warming | KV Cache Management |
| [ADR-0025d](../../docs/architecture/decisions/0025d-*.md) | 0025D Compression | KV Cache Management |
| [ADR-0025e](../../docs/architecture/decisions/0025e-*.md) | 0025E Protection | KV Cache Management |
| [ADR-0026](../../docs/architecture/decisions/0026-*.md) | 0026 Thermal Management | Graceful Degradation |
| [ADR-0026a](../../docs/architecture/decisions/0026a-*.md) | 0026A Thermal Zones | Thermal Management |
| [ADR-0026b](../../docs/architecture/decisions/0026b-*.md) | 0026B Hysteresis FSM | Thermal Management |
| [ADR-0026c](../../docs/architecture/decisions/0026c-*.md) | 0026C Hysteresis Matrix | Thermal Management |
| [ADR-0026d](../../docs/architecture/decisions/0026d-*.md) | 0026D Throttling | Thermal Management |
| [ADR-0027](../../docs/architecture/decisions/0027-*.md) | 0027 Model Placement | Graceful Degradation |
| [ADR-0029](../../docs/architecture/decisions/0029-*.md) | 0029 RED Method | Prometheus Metrics |
| [ADR-0029a](../../docs/architecture/decisions/0029a-*.md) | 0029A RED Method | Prometheus Metrics |
| [ADR-0029d](../../docs/architecture/decisions/0029d-*.md) | 0029D Infrastructure | Prometheus Metrics |
| [ADR-0029e](../../docs/architecture/decisions/0029e-*.md) | 0029E Alerting | Prometheus Metrics |
| [ADR-0030](../../docs/architecture/decisions/0030-*.md) | 0030 Head-Based Sampling | Trace Sampling |
| [ADR-0030a](../../docs/architecture/decisions/0030a-*.md) | 0030A Head-Based Sampling | Trace Sampling |
| [ADR-0030b](../../docs/architecture/decisions/0030b-*.md) | 0030B Tail-Based Sampling | Trace Sampling |
| [ADR-0030c](../../docs/architecture/decisions/0030c-*.md) | 0030C Adaptive Sampling | Trace Sampling |
| [ADR-0030d](../../docs/architecture/decisions/0030d-*.md) | 0030D Jaeger Integration | Trace Sampling |
| [ADR-0031](../../docs/architecture/decisions/0031-*.md) | 0031 Per-Session | Cost Tracking |
| [ADR-0031a](../../docs/architecture/decisions/0031a-*.md) | 0031A Per-Session | Cost Tracking |
| [ADR-0031b](../../docs/architecture/decisions/0031b-*.md) | 0031B Per-Session | Cost Tracking |
| [ADR-0031c](../../docs/architecture/decisions/0031c-*.md) | 0031C Fallback | Cost Tracking |
| [ADR-0031d](../../docs/architecture/decisions/0031d-*.md) | 0031D Observability | Cost Tracking |
| [ADR-0032](../../docs/architecture/decisions/0032-*.md) | 0032 Network | Egress Control |
| [ADR-0032a](../../docs/architecture/decisions/0032a-*.md) | 0032A Network | Egress Control |
| [ADR-0032b](../../docs/architecture/decisions/0032b-*.md) | 0032B Filesystem | Egress Control |
| [ADR-0032c](../../docs/architecture/decisions/0032c-*.md) | 0032C Resources | Egress Control |
| [ADR-0032d](../../docs/architecture/decisions/0032d-*.md) | 0032D Violation Logging | Egress Control |
| [ADR-0035](../../docs/architecture/decisions/0035-*.md) | 0035 Hybrid Detection | PII Detection |
| [ADR-0035a](../../docs/architecture/decisions/0035a-*.md) | 0035A Regex Patterns | PII Detection |
| [ADR-0035b](../../docs/architecture/decisions/0035b-*.md) | 0035B ML-based NER | PII Detection |
| [ADR-0036c](../../docs/architecture/decisions/0036c-*.md) | 0036C Selective Encryption | E2EE |
| [ADR-0039a](../../docs/architecture/decisions/0039a-*.md) | 0039A Tier Triggers | Backpressure Cascade |
| [ADR-0039b](../../docs/architecture/decisions/0039b-*.md) | 0039B Signal Propagation | Backpressure Cascade |
| [ADR-0039c](../../docs/architecture/decisions/0039c-*.md) | 0039C Recovery | Backpressure Cascade |
| [ADR-0042](../../docs/architecture/decisions/0042-*.md) | 0042 Durable Events Foundation | K0 SSE Event Streaming |
| [ADR-0042a](../../docs/architecture/decisions/0042a-*.md) | 0042A Event Production | K0 SSE Event Streaming |
| [ADR-0042b](../../docs/architecture/decisions/0042b-*.md) | 0042B Event Consumption | K0 SSE Event Streaming |
| [ADR-0042c](../../docs/architecture/decisions/0042c-*.md) | 0042C Reconnection | K0 SSE Event Streaming |
| [ADR-0042d](../../docs/architecture/decisions/0042d-*.md) | 0042D Backpressure | K0 SSE Event Streaming |
| [ADR-0042e](../../docs/architecture/decisions/0042e-*.md) | 0042E Device Tiers | K0 SSE Event Streaming |
| [ADR-0043](../../docs/architecture/decisions/0043-*.md) | 0043 K0 Durable Topics | SSE Topic Taxonomy |
| [ADR-0043a](../../docs/architecture/decisions/0043a-*.md) | 0043A Topic Hierarchy | SSE Topic Taxonomy |
| [ADR-0043b](../../docs/architecture/decisions/0043b-*.md) | 0043B Subscription Patterns | SSE Topic Taxonomy |
| [ADR-0043c](../../docs/architecture/decisions/0043c-*.md) | 0043C Topic Routing | SSE Topic Taxonomy |
| [ADR-0043d](../../docs/architecture/decisions/0043d-*.md) | 0043D Topic Access Control | SSE Topic Taxonomy |
| [ADR-0044](../../docs/architecture/decisions/0044-*.md) | 0044 Bridge Client | K0 Bridge |
| [ADR-0044a](../../docs/architecture/decisions/0044a-*.md) | 0044A Transport Protocol | K0 Bridge HTTP/2 |
| [ADR-0044b](../../docs/architecture/decisions/0044b-*.md) | 0044B Serialization | K0 Bridge HTTP/2 |
| [ADR-0044c](../../docs/architecture/decisions/0044c-*.md) | 0044C Batching | K0 Bridge HTTP/2 |
| [ADR-0044d](../../docs/architecture/decisions/0044d-*.md) | 0044D Error Handling | K0 Bridge HTTP/2 |
| [ADR-0046](../../docs/architecture/decisions/0046-*.md) | 0046 SSE Subscription | SSE-WebSocket Bridge |
| [ADR-0047](../../docs/architecture/decisions/0047-*.md) | 0047 SDK Generation | OpenAPI 3.1 Specs |
| [ADR-0048](../../docs/architecture/decisions/0048-*.md) | 0048 Bus Architecture | K1 Internal Event Bus |
| [ADR-0049](../../docs/architecture/decisions/0049-*.md) | 0049 Router Policy | Fast/Smart Lane Router |
| [ADR-0050](../../docs/architecture/decisions/0050-*.md) | 0050 Sync Strategy | Multi-Device Family Sync |
| [ADR-0050a](../../docs/architecture/decisions/0050a-*.md) | 0050A SessionState Coherence | Multi-Device Family Sync |
| [ADR-0050b](../../docs/architecture/decisions/0050b-*.md) | 0050B CRDT Merge | Multi-Device Family Sync |
| [ADR-0050c](../../docs/architecture/decisions/0050c-*.md) | 0050C Phase 1 LAN Sync | Multi-Device Family Sync |
| [ADR-0050d](../../docs/architecture/decisions/0050d-*.md) | 0050D Phase 2 Internet Sync | Multi-Device Family Sync |
| [ADR-0052](../../docs/architecture/decisions/0052-*.md) | 0052 Observability | Enhanced HITL Protocols |
| [ADR-0052a](../../docs/architecture/decisions/0052a-*.md) | 0052A Step-by-Step Approval | Enhanced HITL Protocols |
| [ADR-0052b](../../docs/architecture/decisions/0052b-*.md) | 0052B RED Band Approval | Enhanced HITL Protocols |
| [ADR-0052c](../../docs/architecture/decisions/0052c-*.md) | 0052C Nested Clarifications | Enhanced HITL Protocols |
| [ADR-0052d](../../docs/architecture/decisions/0052d-*.md) | 0052D Proactive Confirmation | Enhanced HITL Protocols |
| [ADR-0053](../../docs/architecture/decisions/0053-*.md) | 0053 Main | Message Queue & Coalescing |
| [ADR-0053a](../../docs/architecture/decisions/0053a-*.md) | 0053A Coalesce Window | Message Queue & Coalescing |
| [ADR-0053b](../../docs/architecture/decisions/0053b-*.md) | 0053B Rate Limits | Message Queue & Coalescing |
| [ADR-0053c](../../docs/architecture/decisions/0053c-*.md) | 0053C Cancel Path | Message Queue & Coalescing |
| [ADR-0054](../../docs/architecture/decisions/0054-*.md) | 0054 Main | Turn Boundary Management |
| [ADR-0054a](../../docs/architecture/decisions/0054a-*.md) | 0054A Implicit Pause | Turn Boundary Management |
| [ADR-0054b](../../docs/architecture/decisions/0054b-*.md) | 0054B Explicit Submit | Turn Boundary Management |
| [ADR-0054c](../../docs/architecture/decisions/0054c-*.md) | 0054C MPST Transitions | Turn Boundary Management |
| [ADR-0056](../../docs/architecture/decisions/0056-*.md) | 0056 Pipeline Architecture | Voice Pipeline Implementation |
| [ADR-0056a](../../docs/architecture/decisions/0056a-*.md) | 0056A ASR Ingress | Voice Pipeline Implementation |
| [ADR-0056d](../../docs/architecture/decisions/0056d-*.md) | 0056D TTS Synthesis | Voice Pipeline Implementation |
| [ADR-0056e](../../docs/architecture/decisions/0056e-*.md) | 0056E Audio Output | Voice Pipeline Implementation |
| [ADR-0057](../../docs/architecture/decisions/0057-*.md) | 0057 Cascade Core | Voice Backpressure |
| [ADR-0061](../../docs/architecture/decisions/0061-*.md) | 0061 Backpressure | Graceful Degradation |
| [ADR-0061a](../../docs/architecture/decisions/0061a-*.md) | 0061A Watermark Thresholds | 3-Tier Backpressure Cascade |
| [ADR-0061b](../../docs/architecture/decisions/0061b-*.md) | 0061B RED Metrics & Alerts | 3-Tier Backpressure Cascade |
| [ADR-0061c](../../docs/architecture/decisions/0061c-*.md) | 0061C Privacy Band Overrides | 3-Tier Backpressure Cascade |
| [ADR-0061d](../../docs/architecture/decisions/0061d-*.md) | 0061D Fairness & Anti-Starvation | 3-Tier Backpressure Cascade |
| [ADR-0074](../../docs/architecture/decisions/0074-*.md) | 0074 Module Discovery | Module System |
| [ADR-0075](../../docs/architecture/decisions/0075-*.md) | 0075 Extension Points | Layer 5 Extensibility |
| [ADR-0080](../../docs/architecture/decisions/0080-*.md) | 0080 Change Detection | Config Hot-Reload |
| [ADR-0081](../../docs/architecture/decisions/0081-*.md) | 0081 Knowledge Graph | K0 Core |
| [ADR-0081a](../../docs/architecture/decisions/0081a-*.md) | 0081A Knowledge Graph | K0 Core |
| [ADR-0081b](../../docs/architecture/decisions/0081b-*.md) | 0081B Knowledge Graph | K0 Core |
| [ADR-0081c](../../docs/architecture/decisions/0081c-*.md) | 0081C Knowledge Graph | K0 Core |
| [ADR-0081d](../../docs/architecture/decisions/0081d-*.md) | 0081D Knowledge Graph | K0 Core |
| [ADR-0084](../../docs/architecture/decisions/0084-*.md) | 0084 Core Architecture | K0 Memory Consolidation |
| [ADR-0084a](../../docs/architecture/decisions/0084a-*.md) | 0084A Hippocampal Replay | K0 Memory Consolidation |
| [ADR-0084b](../../docs/architecture/decisions/0084b-*.md) | 0084B Sleep State Machine | K0 Memory Consolidation |
| [ADR-0084c](../../docs/architecture/decisions/0084c-*.md) | 0084C Knowledge Graph Consol. | K0 Memory Consolidation |
| [ADR-0084d](../../docs/architecture/decisions/0084d-*.md) | 0084D Dream Exploration | K0 Memory Consolidation |
| [ADR-0085](../../docs/architecture/decisions/0085-*.md) | 0085 Core Architecture | Embodied Awareness |
| [ADR-0085a](../../docs/architecture/decisions/0085a-*.md) | 0085A Device Presence | Embodied Awareness |
| [ADR-0085c](../../docs/architecture/decisions/0085c-*.md) | 0085C Context Sharing | Embodied Awareness |

---

## Detailed Breakdown by Family

### 3-Tier Backpressure Cascade

#### [ADR-0061](../../docs/architecture/decisions/0061-*.md): 0061 Backpressure

**Components:**

- **Core System** → Cascade Manager
  - File: `k1/l5_infrastructure/backpressure/cascade_manager.py`
  - 3-tier cascade: Tier 1 per-stream 80/90/95%, Tier 2 voice pipeline 80/90/95%, Tier 3 global limits, WatermarkChecker VoicePipelineMonitor GlobalLimitsEnforcer

- **Core System** → Watermark Checker
  - File: `k1/l5_infrastructure/backpressure/watermark_checker.py`
  - Per-stream watermarks, 80% warning 90% degrade 95% reject, hysteresis 5%, backoff 5s

- **Core System** → Voice Pipeline Monitor
  - File: `k1/l5_infrastructure/backpressure/voice_pipeline_monitor.py`
  - Voice-specific monitoring, ASR frame drop TTS degradation, barge-in preemption, load calculation

- **Core System** → Global Limits Enforcer
  - File: `k1/l5_infrastructure/backpressure/global_limits_enforcer.py`
  - System-wide limits enforcement, max agents 3 per session, CPU/memory thresholds, session rejection

- **Core System** → Cascading Decision
  - File: `k1/l5_infrastructure/backpressure/cascade_decision.py`
  - make_decision logic, tier evaluation order, action selection ALLOW/WARN/DEGRADE/REJECT

#### [ADR-0061a](../../docs/architecture/decisions/0061a-*.md): 0061A Watermark Thresholds

**Components:**

- **Watermark Thresholds** → Threshold Config
  - File: `k1/config/backpressure_watermarks.yml`
  - 80/90/95% watermarks, hysteresis 5%, recovery time 5s/10s/30s, RED metrics alerts

- **Watermark Thresholds** → Hysteresis Logic
  - File: `k1/l5_infrastructure/backpressure/hysteresis.py`
  - HysteresisController 5% hysteresis bands, prevent flapping, time-based recovery, state tracking

- **Watermark Thresholds** → Recovery Policies
  - File: `k1/l5_infrastructure/backpressure/recovery_policies.py`
  - RecoveryPolicy: exponential backoff 5/10/30s, quality restoration steps, gradual recovery

- **Watermark Thresholds** → Thermal Integration
  - File: `k1/l5_infrastructure/backpressure/thermal_integration.py`
  - Thermal multipliers COOL 1.0 WARM 1.1 HOT 1.2 CRITICAL 1.3, adjusted watermarks

#### [ADR-0061b](../../docs/architecture/decisions/0061b-*.md): 0061B RED Metrics & Alerts

**Components:**

- **RED Metrics & Alerts** → Prometheus Metrics
  - File: `observability/metrics/backpressure_metrics.py`
  - Rate requests/s, Errors failures/s, Duration latency P95, RED methodology, 15 counters/histograms

- **RED Metrics & Alerts** → Rate Metrics
  - File: `observability/metrics/backpressure_metrics.py`
  - backpressure_requests_total by tier action, requests per second calculation

- **RED Metrics & Alerts** → Error Metrics
  - File: `observability/metrics/backpressure_metrics.py`
  - backpressure_rejections_total by tier reason, errors per second calculation

- **RED Metrics & Alerts** → Duration Metrics
  - File: `observability/metrics/backpressure_metrics.py`
  - backpressure_latency_ms histogram, P50 P95 P99 tracking, 5/10/50/100/500ms buckets

- **RED Metrics & Alerts** → Grafana Dashboards
  - File: `observability/dashboards/backpressure_red.json`
  - 3 dashboards: RED overview, watermark timeline, rejection rate, Prometheus queries

- **RED Metrics & Alerts** → Alert Rules
  - File: `observability/alerts/backpressure_alerts.yml`
  - 15 rules: rejection rate >10%, tier stuck 5m, latency P95 >100ms, recovery failure 3/5m

#### [ADR-0061c](../../docs/architecture/decisions/0061c-*.md): 0061C Privacy Band Overrides

**Components:**

- **Privacy Band Overrides** → Bypass Logic
  - File: `k1/l5_infrastructure/backpressure/privacy_bypass.py`
  - RED band override, capability-based verification, emergency bypass, audit logging

- **Privacy Band Overrides** → Emergency Paths
  - File: `k1/l5_infrastructure/backpressure/emergency_paths.py`
  - EmergencyPathManager: RED band fast-path, skip backpressure checks, capability validation

- **Privacy Band Overrides** → Audit Trail
  - File: `k1/l5_infrastructure/backpressure/audit_trail.py`
  - Log bypass events, trace_id tracking, 7-year retention, security compliance

#### [ADR-0061d](../../docs/architecture/decisions/0061d-*.md): 0061D Fairness & Anti-Starvation

**Components:**

- **Fairness & Anti-Starvation** → WFQ Scheduler
  - File: `k1/l5_infrastructure/backpressure/wfq_scheduler.py`
  - Weighted Fair Queuing, priority levels 1-5, quantum allocation, weight calculation

- **Fairness & Anti-Starvation** → Aging Policies
  - File: `k1/l5_infrastructure/backpressure/aging_policies.py`
  - Priority boost aging, wait time tracking, starvation detection threshold 10s, automatic escalation

- **Fairness & Anti-Starvation** → Priority Inheritance
  - File: `k1/l5_infrastructure/backpressure/priority_inheritance.py`
  - Inherit priority from waiting high-priority tasks, blocked resource handling

- **Fairness & Anti-Starvation** → Starvation Detection
  - File: `k1/l5_infrastructure/backpressure/starvation_detection.py`
  - Monitor wait times, detect starvation >10s, alert system, forced scheduling


### 4-Stage Planning

#### [ADR-0007d](../../docs/architecture/decisions/0007d-*.md): 0007D Stage 4 Commit

**Components:**

- **Stage 4 Commit** → K0 WAL Write
  - File: `k1/bridge_k0/wal_writer.py`
  - PLAN_COMMITTED topic, HTTP POST, idempotency key, <5ms

- **Stage 4 Commit** → STATE_DELTA Emission
  - File: `k1/bridge_k0/state_delta_emitter.py`
  - K0 sync, field_path (control.current_flow), old/new value, <2ms


### ADR Notes

#### [ADR-0004c](../../docs/architecture/decisions/0004c-*.md): 0004C Documentation

**Components:**

- **Documentation** → Module READMEs
  - File: `tools/k1_doc_gen.py`
  - k1-doc-gen, README template, auto-generation, docstring extraction, metadata parsing, CI enforcement


### Backpressure Cascade

#### [ADR-0039a](../../docs/architecture/decisions/0039a-*.md): 0039A Tier Triggers

**Components:**

- **Tier Triggers** → Watermark Thresholds
  - File: `k1/l5_infrastructure/backpressure/watermark_manager.py`
  - Tier 1 (reject new): queue depth >50, E2E P95 >2500ms, active turns >80; Tier 2 (cancel background): queue >100, memory >450MB, CPU >85%; Tier 3 (emergency): queue >200, memory >480MB

- **Tier Triggers** → Hysteresis Buffer
  - File: `k1/l5_infrastructure/backpressure/watermark_manager.py`
  - 10% gap between activation/deactivation prevents oscillation, Deactivation: queue <45 (Tier 1), <90 (Tier 2), <180 (Tier 3)

#### [ADR-0039b](../../docs/architecture/decisions/0039b-*.md): 0039B Signal Propagation

**Components:**

- **Signal Propagation** → Actor Model Messaging
  - File: `k1/l5_infrastructure/backpressure/signal_propagator.py`
  - Event-based backpressure propagation, <50ms propagation guarantee (5% of TTFT budget), BackpressureSignal FlatBuffers message broadcast

- **Signal Propagation** → Tier Priority
  - File: `k1/l5_infrastructure/backpressure/types.py`
  - BackpressureTier enum (NORMAL=0, TIER_1=1, TIER_2=2, TIER_3=3), Higher tier preempts lower tier (EMERGENCY > REJECT_NEW)

#### [ADR-0039c](../../docs/architecture/decisions/0039c-*.md): 0039C Recovery

**Components:**

- **Recovery** → Stepwise Gradual Resume
  - File: `k1/l5_infrastructure/backpressure/recovery_manager.py`
  - Tier 3→2→1→Normal (one step at a time), Sustained stability (10-30s below deactivation watermarks), Rate limiting (10% admission increase every 5s), ~2min total recovery

- **Recovery** → Health Checks
  - File: `k1/l5_infrastructure/backpressure/recovery_manager.py`
  - Verify metrics stable at each step, Automatic rollback if metrics degrade during recovery, Prevent thundering herd (synchronized client retry)


### Bridge

#### [ADR-0001a](../../docs/architecture/decisions/0001a-*.md): 0001A K0 Communication

**Components:**

- **K0 Communication** → Bridge Client
  - File: `k1/bridge_k0/command_client.py`
  - JSON (PRIMARY), FlatBuffers (SECONDARY), HTTP/2, TLS 1.3

- **K0 Communication** → Dual Protocol
  - File: `k1/bridge_k0/protocol.py`
  - JSON envelopes (K0 native), FlatBuffers (K1 optimization), format negotiation

- **K0 Communication** → External Ports
  - File: `k1/bridge_k0/ports/`
  - Command (writes), Query (reads), SSE (events), Observability (metrics/logs)

- **K0 Communication** → Lane Processing
  - File: `k1/bridge_k0/lanes.py`
  - Fast Lane (GREEN <50ms), Smart Lane (AMBER/RED <200ms), Hippocampus DG→CA3→CA1

- **K0 Communication** → Multi-Store Retrieval
  - File: `k1/bridge_k0/retrieval.py`
  - FTS + Vector + KG + Episodic, fusion, MMR, cognitive enhancements

#### [ADR-0001f](../../docs/architecture/decisions/0001f-*.md): 0001F K0 Communication

**Components:**

- **K0 Communication** → Batch Client
  - File: `k1/bridge_k0/batch_client.py`
  - SessionState delta batching (250ms), P02 MemoryWrite, receipts


### Capability Security

#### [ADR-0010c](../../docs/architecture/decisions/0010c-*.md): 0010C Runtime Enforcement

**Components:**

- **Runtime Enforcement** → K0 Bridge Enforcement
  - File: `k1/bridge_k0/capability_check.py`
  - K0 WAL capability validation, K0_WAL resource type, write permission

#### [ADR-0010d](../../docs/architecture/decisions/0010d-*.md): 0010D Audit Trail

**Components:**

- **Audit Trail** → Audit Logger
  - File: `k1/bridge_k0/capability_audit.py`
  - K0 WAL logging, 6 event types (GRANTED, VALIDATED, DENIED, REVOKED, EXPIRED, ESCALATION_REQUEST)

- **Audit Trail** → Audit Event Schema
  - File: `k1/l5_infrastructure/serialization/audit_event.py`
  - CapabilityAuditEvent FlatBuffers, 30-day retention, 7-year S3 backup, compliance tags

- **Audit Trail** → Elasticsearch Integration
  - File: `observability/elasticsearch/capability_audit.py`
  - Audit log indexing, searchable events, incident investigation, compliance queries


### Circuit Breaker

#### [ADR-0009](../../docs/architecture/decisions/0009-*.md): 0009 Core FSM

**Components:**

- **Core FSM** → Circuit Breaker Manager
  - File: `k1/l5_infrastructure/resilience/circuit_breaker_manager.py`
  - CircuitBreaker class, 3-state FSM (CLOSED/OPEN/HALF_OPEN), Nygard 2007

- **Core FSM** → State Machine
  - File: `k1/l5_infrastructure/resilience/circuit_fsm.py`
  - CircuitState enum, state transitions, transition guards, failure threshold tracking

- **Core FSM** → Call Wrapper
  - File: `k1/l5_infrastructure/resilience/call_wrapper.py`
  - circuit.call, fail-fast, fallback invocation, latency tracking, metrics emission

- **Core FSM** → Failure Recording
  - File: `k1/l5_infrastructure/resilience/failure_recorder.py`
  - _record_failure, failure_count increment, state transition logic, last_failure_time

#### [ADR-0009a](../../docs/architecture/decisions/0009a-*.md): 0009A State Handlers

**Components:**

- **State Handlers** → CLOSED State
  - File: `k1/l5_infrastructure/resilience/states/closed.py`
  - Normal operation, failure tracking, threshold check, transition to OPEN

- **State Handlers** → OPEN State
  - File: `k1/l5_infrastructure/resilience/states/open.py`
  - Fail-fast mode, request rejection, timeout tracking, transition to HALF_OPEN

- **State Handlers** → HALF_OPEN State
  - File: `k1/l5_infrastructure/resilience/states/half_open.py`
  - Testing recovery, single probe, success tracking, transition to CLOSED/OPEN

- **State Handlers** → State Transitions
  - File: `k1/l5_infrastructure/resilience/state_transition.py`
  - _transition_to_open/closed/half_open, logging, metrics, time tracking

- **Fallback Strategies** → Default Value Fallback
  - File: `k1/l5_infrastructure/resilience/fallbacks/default_value.py`
  - Return empty list/None, read-only operations, <1ms latency, graceful degradation

- **Fallback Strategies** → Cached Result Fallback
  - File: `k1/l5_infrastructure/resilience/fallbacks/cached_result.py`
  - Redis cache lookup, 5-minute TTL, LLM response caching, stale-but-correct

- **Fallback Strategies** → Alternate Service Fallback
  - File: `k1/l5_infrastructure/resilience/fallbacks/alternate_service.py`
  - Local→remote LLM fallback, alternate_service config, service routing

- **Fallback Strategies** → Raise Error Fallback
  - File: `k1/l5_infrastructure/resilience/fallbacks/raise_error.py`
  - CircuitOpenError, no fallback (critical path), K0 bridge, streaming engine

#### [ADR-0009b](../../docs/architecture/decisions/0009b-*.md): 0009B Configuration

**Components:**

- **Configuration** → Config Manager
  - File: `k1/l5_infrastructure/resilience/config_manager.py`
  - Load circuit_breakers.yml, get_circuit_config, default config, per-service

- **Configuration** → Tool Runner Config
  - File: `k1/config/circuit_breakers.yml`
  - failure_threshold 5, 30s timeout, 5s slow call, default_value fallback

- **Configuration** → Model Hub Local Config
  - File: `k1/config/circuit_breakers.yml`
  - failure_threshold 3, 10s timeout, 1s slow call, alternate_model fallback

- **Configuration** → Model Hub Remote Config
  - File: `k1/config/circuit_breakers.yml`
  - failure_threshold 5, 60s timeout, 10s slow call, cached_result fallback

- **Configuration** → K0 Bridge Config
  - File: `k1/config/circuit_breakers.yml`
  - failure_threshold 3, 5s timeout, 100ms slow call, raise_error fallback

- **Configuration** → MCP Gateway Config
  - File: `k1/config/circuit_breakers.yml`
  - failure_threshold 5, 30s timeout, 3s slow call, default_value fallback

- **Configuration** → Streaming Engine Config
  - File: `k1/config/circuit_breakers.yml`
  - failure_threshold 3, 10s timeout, 5s slow call, raise_error fallback

- **Configuration** → Hot Reload
  - File: `k1/l5_infrastructure/resilience/hot_reload.py`
  - reload_configs, file watcher, asyncio reload, <100ms latency

#### [ADR-0009c](../../docs/architecture/decisions/0009c-*.md): 0009C Observability

**Components:**

- **Observability** → Prometheus Metrics
  - File: `observability/metrics/circuit_breaker.py`
  - 6 metrics (state, transitions, calls, failures, fallbacks, latency), Prometheus

- **Observability** → State Gauge
  - File: `observability/metrics/circuit_breaker.py`
  - circuit_breaker_state, 0=CLOSED/1=OPEN/2=HALF_OPEN, per-service

- **Observability** → Transitions Counter
  - File: `observability/metrics/circuit_breaker.py`
  - circuit_breaker_transitions_total, from_state/to_state labels, flapping detection

- **Observability** → Calls Counter
  - File: `observability/metrics/circuit_breaker.py`
  - circuit_breaker_calls_total, success/failure/rejected results, success rate

- **Observability** → Failures Counter
  - File: `observability/metrics/circuit_breaker.py`
  - circuit_breaker_failures_total, timeout/slow_call/exception types, failure analysis

- **Observability** → Fallbacks Counter
  - File: `observability/metrics/circuit_breaker.py`
  - circuit_breaker_fallbacks_total, fallback_strategy labels, usage tracking

- **Observability** → Latency Histogram
  - File: `observability/metrics/circuit_breaker.py`
  - circuit_breaker_latency_ms, per-state latency, P95/P99 tracking, heatmap visualization

- **Observability** → Structured Logging
  - File: `observability/logging/circuit_breaker.py`
  - 4 log events (opened, closed, transition, fallback), JSON format, trace_id

- **Observability** → Grafana Dashboards
  - File: `observability/dashboards/circuit_breaker.json`
  - 3 dashboards (state timeline, failure rate, latency P95), alerting

- **Observability** → Prometheus Alerts
  - File: `observability/alerts/circuit_breaker.yml`
  - 5 alerts (stuck OPEN 5m, flapping 10/5m, success <50%, timeout >10/min, fallback >50%)


### Config Hot-Reload

#### [ADR-0080](../../docs/architecture/decisions/0080-*.md): 0080 Change Detection

**Components:**

- **Change Detection** → ConfigChangeDetector
  - File: `k1/l5_infrastructure/config/change_detector.py`
  - watchdog file observer, YAML parsing, <100ms P95 detection, change callbacks, M5 milestone

- **Change Detection** → ConfigValidator
  - File: `k1/l5_infrastructure/config/validator.py`
  - JSON schema validation + semantic validation, config-specific validators (agent_fabric orchestrator learning_loop thermal performance_budgets), <50ms P95 validation

- **Config Application** → ConfigApplicationEngine
  - File: `k1/l5_infrastructure/config/application_engine.py`
  - Zero-downtime config apply, atomic updates, component updaters registration, drain in-flight ops, <100ms P95 application

- **Config Application** → ConfigRollback
  - File: `k1/l5_infrastructure/config/rollback.py`
  - Automatic rollback on error, restore previous state, <200ms rollback latency, audit trail with trace_id


### Cost Tracking

#### [ADR-0031](../../docs/architecture/decisions/0031-*.md): 0031 Per-Session

**Components:**

- **Per-Session** → Budget Enforcement
  - File: `k1/cost_tracking/budget_enforcer.py`
  - $0.10 session default, <1ms budget check, 50%/80%/95% alert thresholds, Block remote at 100%, Automatic fallback at 80%

- **Per-Session** → Cost Recording
  - File: `k1/cost_tracking/cost_recorder.py`
  - <0.5ms record per operation, Token costs (input/output × price), Tool costs (per-call price), Compute costs (local inference)

- **Per-Session** → Session Aggregation
  - File: `k1/cost_tracking/session_aggregator.py`
  - Per-conversation cost totals, Cost breakdown (tokens/tools/compute), Model attribution (GPT-4o/Claude/Gemma), Tool attribution (web_search/image_gen)

- **Hierarchical Budgets** → Daily Budget
  - File: `k1/cost_tracking/daily_budget.py`
  - $5/day per user default, <1ms daily check, Aggregate across sessions, Reset at midnight UTC, Power user prevention

- **Hierarchical Budgets** → Monthly Budget
  - File: `k1/cost_tracking/monthly_budget.py`
  - $50/month per family space, <2ms monthly check, Aggregate across users, Department rollup, Finance chargeback reports

- **Hierarchical Budgets** → Corporate Governance
  - File: `k1/cost_tracking/corporate_budgets.yml`
  - 3-tier hierarchy (Session→Daily→Monthly), Department/team budgets, IT admin configuration, Budget override permissions, Audit trail

- **Pricing** → Provider Pricing Config
  - File: `k1/config/cost_model.yml`
  - OpenAI/Anthropic/Google pricing, Input/output token costs, Tool per-call pricing, Monthly rate updates, Volume discount support

- **Pricing** → Cost Calculation
  - File: `k1/cost_tracking/cost_calculator.py`
  - <0.5ms calculation per operation, Token costs (input/output × provider rate), Tool costs (per-call × provider rate), Compute costs (NPU/GPU/CPU time × rate)

- **Pricing** → Volume Discounts
  - File: `k1/cost_tracking/volume_discounts.py`
  - Enterprise contract pricing, Tiered volume pricing (>1M tokens), Custom rate cards, Discount application (<0.1ms lookup)

- **Fallback** → 4-Tier Fallback Strategy
  - File: `k1/cost_tracking/fallback_strategy.py`
  - NORMAL (0-50%), WARNING (50-80%), COST_OPTIMIZED (80-95%), LOCAL_ONLY (95-100%), BLOCKED (100%+), Fallback decision <5ms

- **Fallback** → Model Selection
  - File: `k1/cost_tracking/fallback_strategy.py`
  - Automatic switch GPT-4o→GPT-4o-mini at 80%, GPT-4o-mini→Gemma-2-9B at 95%, Model load latency <500ms, Quality threshold (80% task adequacy)

- **Fallback** → User Notifications
  - File: `k1/cost_tracking/user_notifier.py`
  - Warning at 80% ("Switching to local models soon"), Notification at 95% ("Using local models"), Display <100ms, Graceful UX degradation

- **Fallback** → Admin Override
  - File: `k1/cost_tracking/admin_override.py`
  - Critical task override (with approval), Manual model selection (within budget), Power user bypass (with audit), Override logging

- **Observability** → Prometheus Metrics
  - File: `k1/cost_tracking/metrics_exporter.py`
  - Cost_total_usd counter (by department/user/model), Inference_cost_usd counter, Tool_cost_usd counter, Budget_utilization_ratio gauge (0.0-1.0), <1ms export overhead

- **Observability** → Grafana Dashboards
  - File: `observability/grafana/dashboards/cost_tracking.json`
  - IT Admin dashboard (real-time budget monitoring, alerts at 80%), Finance dashboard (MTD spending, chargeback reports), Compliance dashboard (audit trails, usage reports), Executive dashboard (trend...

- **Observability** → Audit Trail
  - File: `k1/cost_tracking/audit_logger.py`
  - Immutable cost logs (7 years retention), Per-operation cost attribution, User/department/project tracking, SOC2/ISO27001 compliance, Exportable reports (<10s monthly report generation)

- **Observability** → Cost Attribution
  - File: `k1/cost_tracking/cost_attribution.py`
  - Department-level rollup, Project-level attribution, User-level breakdown, Model/tool attribution, Chargeback report generation

- **Storage** → Cost History
  - File: `k1/cost_tracking/storage/cost_history.db`
  - 90 days detailed history, 2 years aggregated, 10MB/month storage, Per-operation granularity, Query API (<500ms response)

- **Storage** → Budget State
  - File: `k1/cost_tracking/storage/budget_state.db`
  - Current budget utilization, 100KB per department (1K users × 100 bytes), In-memory cache (<0.1ms lookup), Persistent backup

- **Integration** → Remote LLM Costs
  - File: `k1/cost_tracking/remote_costs.py`
  - GPT-4o ($0.005/$0.015 per 1K tokens), Claude ($0.003/$0.015 per 1K), Gemini ($0.0005/$0.0015 per 1K), Token counting (tiktoken), API response parsing

- **Integration** → Local Inference Costs
  - File: `k1/cost_tracking/local_costs.py`
  - Gemma-2-9B ($0.0001 per 1K tokens), Phi-3 ($0.00005 per 1K), NPU/GPU/CPU time tracking, Energy cost estimation, Amortized hardware costs

- **Integration** → Tool Call Costs
  - File: `k1/cost_tracking/tool_costs.py`
  - Web search ($0.002 per call), Image generation ($0.04 per call), API call tracking, Provider rate lookup (<0.1ms), Tool-specific pricing

#### [ADR-0031a](../../docs/architecture/decisions/0031a-*.md): 0031A Per-Session

**Components:**

- **Per-Session** → Budget Enforcement
  - File: `k1/cost_tracking/budget_enforcer.py`
  - $0.10 session default, <1ms budget check, 50%/80%/95% alert thresholds, Block remote at 100%, Automatic fallback at 80%

- **Hierarchical Budgets** → Daily Budget
  - File: `k1/cost_tracking/daily_budget.py`
  - $5/day per user default, <1ms daily check, Aggregate across sessions, Reset at midnight UTC, Power user prevention

- **Hierarchical Budgets** → Monthly Budget
  - File: `k1/cost_tracking/monthly_budget.py`
  - $50/month per family space, <2ms monthly check, Aggregate across users, Department rollup, Finance chargeback reports

- **Hierarchical Budgets** → Corporate Governance
  - File: `k1/cost_tracking/corporate_budgets.yml`
  - 3-tier hierarchy (Session→Daily→Monthly), Department/team budgets, IT admin configuration, Budget override permissions, Audit trail

#### [ADR-0031b](../../docs/architecture/decisions/0031b-*.md): 0031B Per-Session

**Components:**

- **Per-Session** → Cost Recording
  - File: `k1/cost_tracking/cost_recorder.py`
  - <0.5ms record per operation, Token costs (input/output × price), Tool costs (per-call price), Compute costs (local inference)

- **Pricing** → Provider Pricing Config
  - File: `k1/config/cost_model.yml`
  - OpenAI/Anthropic/Google pricing, Input/output token costs, Tool per-call pricing, Monthly rate updates, Volume discount support

- **Pricing** → Cost Calculation
  - File: `k1/cost_tracking/cost_calculator.py`
  - <0.5ms calculation per operation, Token costs (input/output × provider rate), Tool costs (per-call × provider rate), Compute costs (NPU/GPU/CPU time × rate)

- **Pricing** → Volume Discounts
  - File: `k1/cost_tracking/volume_discounts.py`
  - Enterprise contract pricing, Tiered volume pricing (>1M tokens), Custom rate cards, Discount application (<0.1ms lookup)

#### [ADR-0031c](../../docs/architecture/decisions/0031c-*.md): 0031C Fallback

**Components:**

- **Fallback** → 4-Tier Fallback Strategy
  - File: `k1/cost_tracking/fallback_strategy.py`
  - NORMAL (0-50%), WARNING (50-80%), COST_OPTIMIZED (80-95%), LOCAL_ONLY (95-100%), BLOCKED (100%+), Fallback decision <5ms

- **Fallback** → Model Selection
  - File: `k1/cost_tracking/fallback_strategy.py`
  - Automatic switch GPT-4o→GPT-4o-mini at 80%, GPT-4o-mini→Gemma-2-9B at 95%, Model load latency <500ms, Quality threshold (80% task adequacy)

- **Fallback** → User Notifications
  - File: `k1/cost_tracking/user_notifier.py`
  - Warning at 80% ("Switching to local models soon"), Notification at 95% ("Using local models"), Display <100ms, Graceful UX degradation

- **Fallback** → Admin Override
  - File: `k1/cost_tracking/admin_override.py`
  - Critical task override (with approval), Manual model selection (within budget), Power user bypass (with audit), Override logging

#### [ADR-0031d](../../docs/architecture/decisions/0031d-*.md): 0031D Observability

**Components:**

- **Observability** → Prometheus Metrics
  - File: `k1/cost_tracking/metrics_exporter.py`
  - Cost_total_usd counter (by department/user/model), Inference_cost_usd counter, Tool_cost_usd counter, Budget_utilization_ratio gauge (0.0-1.0), <1ms export overhead

- **Observability** → Grafana Dashboards
  - File: `observability/grafana/dashboards/cost_tracking.json`
  - IT Admin dashboard (real-time budget monitoring, alerts at 80%), Finance dashboard (MTD spending, chargeback reports), Compliance dashboard (audit trails, usage reports), Executive dashboard (trend...

- **Observability** → Audit Trail
  - File: `k1/cost_tracking/audit_logger.py`
  - Immutable cost logs (7 years retention), Per-operation cost attribution, User/department/project tracking, SOC2/ISO27001 compliance, Exportable reports (<10s monthly report generation)

- **Observability** → Cost Attribution
  - File: `k1/cost_tracking/cost_attribution.py`
  - Department-level rollup, Project-level attribution, User-level breakdown, Model/tool attribution, Chargeback report generation


### Cursor-Based Pagination

#### [ADR-0023c](../../docs/architecture/decisions/0023c-*.md): 0023C K0 WAL Query

**Components:**

- **K0 WAL Query** → SQLite Index
  - File: `k0/wal_storage/indexes.sql`
  - CREATE INDEX idx_session_turn ON turns (session_id, turn_id), <50ms P95 indexed query


### E2EE

#### [ADR-0036c](../../docs/architecture/decisions/0036c-*.md): 0036C Selective Encryption

**Components:**

- **Selective Encryption** → Band Detection
  - File: `k1/l5_infrastructure/privacy/band_detector.py`
  - Detect privacy band (GREEN/AMBER/RED/BLACK) from SessionState metadata, Apply E2EE only to RED band, GREEN/AMBER bypass encryption (0ms overhead)

- **Selective Encryption** → Section Selection
  - File: `k1/l5_infrastructure/privacy/section_selector.py`
  - Encrypt beliefs/scoreboard/control (sensitive data), Don't encrypt persona (public config) / meta (timestamps/counters), Multimodal (embeddings encrypted separately)

- **Selective Encryption** → Performance Optimization
  - File: `k1/l5_infrastructure/privacy/selective_e2ee.py`
  - 90% sessions (GREEN/AMBER) bypass encryption (0ms overhead), 10% sessions (RED) encrypted (<1ms overhead), Parallel encryption (3 sections concurrent), Async execution (no blocking)

- **Selective Encryption** → Production Metrics
  - File: `k1/l5_infrastructure/privacy/metrics.py`
  - 1.08M GREEN/AMBER sessions (0ms overhead), 120K RED sessions (0.8ms avg overhead), 90% performance optimization, 0 encryption failures in 6 months


### Egress Control

#### [ADR-0032](../../docs/architecture/decisions/0032-*.md): 0032 Network

**Components:**

- **Network** → Privacy Band Policies
  - File: `k1/security/egress/network_policies.yml`
  - GREEN (internet whitelist), AMBER (PII masking), RED (local-only 127.0.0.1), BLACK (no network), Default-deny policy, 100% RED local-only enforcement

- **Network** → iptables Enforcement
  - File: `k1/security/egress/iptables_manager.py`
  - Process-specific rules (--pid-owner), Domain whitelist per tool, Private IP blocking (192.168.*, 10.*, 172.16.*), Rule setup <5ms, Rule cleanup <2ms

- **Network** → Port Blocking
  - File: `k1/security/egress/network_policies.yml`
  - SMTP ports blocked (25/587/465), Dangerous ports blocked (23 telnet, 3389 RDP), Localhost port whitelist (8080/9000 K1 ports), Per-band port rules

- **Filesystem** → chroot Jail
  - File: `k1/security/egress/chroot_manager.py`
  - Per-tool jail (/var/k1/jails/session_id/), Read-only paths (/tmp/input, /usr/lib, /usr/bin), Writable paths (/tmp/output only), Setup <3ms, 100% path traversal prevention

- **Filesystem** → seccomp Filter
  - File: `k1/security/egress/seccomp_filter.py`
  - Syscall blocking (mount/ptrace/reboot/setuid), SECCOMP_RET_KILL enforcement, Filter load <1ms, 100% dangerous syscall prevention, Whitelist approach (211 safe syscalls)

- **Filesystem** → Path Restrictions
  - File: `k1/security/egress/filesystem_policies.yml`
  - Block /home, /root, /etc/shadow, /dev, /proc, /sys, Read-only system libraries, Max file size limits (100MB GREEN, 50MB AMBER, 10MB RED), Ephemeral jail cleanup <100ms

- **Resources** → cgroups Limits
  - File: `k1/security/egress/cgroups_manager.py`
  - CPU quota (4 cores GREEN, 2 cores AMBER, 1 core RED), Memory limit (2GB GREEN, 1GB AMBER, 512MB RED), PID limit (100/50/25), I/O throttling (10GB/s write), Setup <2ms

- **Resources** → OOM Killer Integration
  - File: `k1/security/egress/oom_handler.py`
  - Kill tool (not K1) on OOM, Hard memory limits enforced, Soft limit warnings (1.5GB→2GB GREEN), Zero resource leakage, <1% CPU accounting overhead

- **Resources** → Execution Timeouts
  - File: `k1/security/egress/resource_policies.yml`
  - 5 minutes GREEN, 3 minutes AMBER, 1 minute RED, SIGTERM→SIGKILL cascade (10s grace), Timeout violations logged, Prevent infinite loops

- **Violation Logging** → ToolReceipt Audit
  - File: `k1/security/egress/violation_logger.py`
  - K0 ToolReceipt integration, <1ms logging overhead, 100 events/sec batch writes, K0 forward latency <10ms, Append-only immutable logs

- **Violation Logging** → Violation Schema
  - File: `k1/security/egress/violation_schema.py`
  - Network/filesystem/resource violation types, Severity levels (low/medium/high/critical), Attempted destination/path/resource, Blocked_by mechanism (iptables/chroot/seccomp/cgroups)

- **Violation Logging** → Real-Time Alerting
  - File: `k1/security/egress/alert_manager.py`
  - <1 second alert latency, Security team notifications, Critical violations escalated, Slack/PagerDuty/email integration, 1,000 violations/day capacity

- **Violation Logging** → Compliance Retention
  - File: `k1/security/egress/audit_storage.py`
  - 7-year retention (ISO27001/SOC2/PCI-DSS), Tamper-proof logs, 500 bytes/event, 180MB/year storage, 1.3GB total (7 years)

- **Integration** → Band Classifier
  - File: `k1/security/egress/band_classifier.py`
  - GREEN/AMBER/RED/BLACK classification, PII detection integration (ADR-0035), Egress policy lookup (<0.1ms), Dynamic band upgrades (AMBER→RED on PII)

- **Integration** → OS Abstraction
  - File: `k1/security/egress/os_abstraction.py`
  - Linux (iptables/chroot/seccomp/cgroups), macOS (pfctl/sandbox-exec), Windows (Firewall API/job objects/AppContainer), Unified API across platforms

- **Integration** → Security Incidents
  - File: `k1/security/egress/incident_tracker.py`
  - 92% incident reduction (1,200→96/month), 100% RED local-only compliance, 98% filesystem tampering prevention, 95% resource abuse prevention, 100% audit coverage

#### [ADR-0032a](../../docs/architecture/decisions/0032a-*.md): 0032A Network

**Components:**

- **Network** → Privacy Band Policies
  - File: `k1/security/egress/network_policies.yml`
  - GREEN (internet whitelist), AMBER (PII masking), RED (local-only 127.0.0.1), BLACK (no network), Default-deny policy, 100% RED local-only enforcement

- **Network** → iptables Enforcement
  - File: `k1/security/egress/iptables_manager.py`
  - Process-specific rules (--pid-owner), Domain whitelist per tool, Private IP blocking (192.168.*, 10.*, 172.16.*), Rule setup <5ms, Rule cleanup <2ms

- **Network** → Port Blocking
  - File: `k1/security/egress/network_policies.yml`
  - SMTP ports blocked (25/587/465), Dangerous ports blocked (23 telnet, 3389 RDP), Localhost port whitelist (8080/9000 K1 ports), Per-band port rules

#### [ADR-0032b](../../docs/architecture/decisions/0032b-*.md): 0032B Filesystem

**Components:**

- **Filesystem** → chroot Jail
  - File: `k1/security/egress/chroot_manager.py`
  - Per-tool jail (/var/k1/jails/session_id/), Read-only paths (/tmp/input, /usr/lib, /usr/bin), Writable paths (/tmp/output only), Setup <3ms, 100% path traversal prevention

- **Filesystem** → seccomp Filter
  - File: `k1/security/egress/seccomp_filter.py`
  - Syscall blocking (mount/ptrace/reboot/setuid), SECCOMP_RET_KILL enforcement, Filter load <1ms, 100% dangerous syscall prevention, Whitelist approach (211 safe syscalls)

- **Filesystem** → Path Restrictions
  - File: `k1/security/egress/filesystem_policies.yml`
  - Block /home, /root, /etc/shadow, /dev, /proc, /sys, Read-only system libraries, Max file size limits (100MB GREEN, 50MB AMBER, 10MB RED), Ephemeral jail cleanup <100ms

#### [ADR-0032c](../../docs/architecture/decisions/0032c-*.md): 0032C Resources

**Components:**

- **Resources** → cgroups Limits
  - File: `k1/security/egress/cgroups_manager.py`
  - CPU quota (4 cores GREEN, 2 cores AMBER, 1 core RED), Memory limit (2GB GREEN, 1GB AMBER, 512MB RED), PID limit (100/50/25), I/O throttling (10GB/s write), Setup <2ms

- **Resources** → OOM Killer Integration
  - File: `k1/security/egress/oom_handler.py`
  - Kill tool (not K1) on OOM, Hard memory limits enforced, Soft limit warnings (1.5GB→2GB GREEN), Zero resource leakage, <1% CPU accounting overhead

- **Resources** → Execution Timeouts
  - File: `k1/security/egress/resource_policies.yml`
  - 5 minutes GREEN, 3 minutes AMBER, 1 minute RED, SIGTERM→SIGKILL cascade (10s grace), Timeout violations logged, Prevent infinite loops

#### [ADR-0032d](../../docs/architecture/decisions/0032d-*.md): 0032D Violation Logging

**Components:**

- **Violation Logging** → ToolReceipt Audit
  - File: `k1/security/egress/violation_logger.py`
  - K0 ToolReceipt integration, <1ms logging overhead, 100 events/sec batch writes, K0 forward latency <10ms, Append-only immutable logs

- **Violation Logging** → Violation Schema
  - File: `k1/security/egress/violation_schema.py`
  - Network/filesystem/resource violation types, Severity levels (low/medium/high/critical), Attempted destination/path/resource, Blocked_by mechanism (iptables/chroot/seccomp/cgroups)

- **Violation Logging** → Real-Time Alerting
  - File: `k1/security/egress/alert_manager.py`
  - <1 second alert latency, Security team notifications, Critical violations escalated, Slack/PagerDuty/email integration, 1,000 violations/day capacity

- **Violation Logging** → Compliance Retention
  - File: `k1/security/egress/audit_storage.py`
  - 7-year retention (ISO27001/SOC2/PCI-DSS), Tamper-proof logs, 500 bytes/event, 180MB/year storage, 1.3GB total (7 years)


### Embodied Awareness

#### [ADR-0085](../../docs/architecture/decisions/0085-*.md): 0085 Core Architecture

**Components:**

- **Core Architecture** → Multi-Device Presence
  - File: `k1/l1_input/streams/operators/device_presence.py`
  - 7 presence mechanisms (device presence, location awareness, BLE proximity, active session, motion sensors, power state, cross-device sharing), K0 P07 CRDT sync integration (ADR-0050), SessionState ...

#### [ADR-0085a](../../docs/architecture/decisions/0085a-*.md): 0085A Device Presence

**Components:**

- **Device Presence** → Heartbeat Protocol
  - File: `k1/l5_infrastructure/presence/heartbeat.py`
  - mDNS multicast + K0 P07 TCP, 30-second interval, 90-second offline threshold (3 missed heartbeats), FlatBuffers payload (device_id, device_type, device_name, platform, timestamp, IP, port, capabili...

- **Device Presence** → Device Registry
  - File: `k1/l5_infrastructure/presence/device_registry.py`
  - Track ONLINE/OFFLINE/UNKNOWN states, 90-second offline detection, device discovery events (device.discovered, device.online, device.offline), device capability flags (HAS_GPS, HAS_CAMERA, HAS_BLE, ...

#### [ADR-0085c](../../docs/architecture/decisions/0085c-*.md): 0085C Context Sharing

**Components:**

- **Context Sharing** → Presence Syncer
  - File: `k1/l5_infrastructure/presence/context_syncer.py`
  - K0 P07 CRDT sync (ADR-0050), 30-second broadcast interval, presence metadata (online_status, location, proximity_devices, active_session, motion_context, battery_level, charging_status, power_mode)...


### Enhanced HITL Protocols

#### [ADR-0052](../../docs/architecture/decisions/0052-*.md): 0052 Observability

**Components:**

- **Observability** → Clarification Metrics
  - File: `observability/metrics/hitl_clarifications.py`
  - clarification_requests_total (by type/result), nested_depth histogram, timeout_rate, completion_rate

- **Observability** → HITL Success Metrics
  - File: `observability/dashboards/hitl_success.json`
  - % clarifications answered >80%, RED band approval success >90%, proactive acceptance 60-80%, rollback <10%

- **Research Foundation** → Grounding Theory
  - File: `docs/research/clark_brennan_1991_grounding.md`
  - Common ground theory (Clark & Brennan 1991), clarification as grounding act, HITL builds common ground

- **Research Foundation** → Error Prevention
  - File: `docs/research/norman_1988_design.md`
  - Forcing functions (Norman 1988), explicit confirmation prevents accidental actions, RED band approval design

- **Research Foundation** → Swiss Cheese Model
  - File: `docs/research/reason_1990_human_error.md`
  - Defense-in-depth safety layers (Reason 1990), multi-layered HITL prevents failures (anomaly + risk + explicit)

- **Research Foundation** → Session Types Validation
  - File: `docs/research/honda_2008_mpst.md`
  - Multiparty Session Types (Honda 2008), protocol validation for nested HITL interactions

- **Audit Trail** → 7-Year Retention
  - File: `k0/receipts/hitl_audit_log.py`
  - RED band approvals logged to K0 receipts, 7-year retention (SOC2/ISO27001 compliance)

- **Audit Trail** → HITL Audit Schema
  - File: `k1/schemas/flatbuffers/hitl_audit_record.fbs`
  - Full audit trail: who approved, when, what phrase, risk score, outcome (1KB per approval)

- **Testing** → WARD Integration Tests
  - File: `tests/integration/test_hitl_extensions.py`
  - Comprehensive HITL tests: step-by-step rollback, RED band phrases, nested go-back, proactive confidence

#### [ADR-0052a](../../docs/architecture/decisions/0052a-*.md): 0052A Step-by-Step Approval

**Components:**

- **Step-by-Step Approval** → Observability
  - File: `observability/metrics/step_by_step.py`
  - workflow_started_total, workflow_completed_total (status), workflow_rollback_total (option)

#### [ADR-0052b](../../docs/architecture/decisions/0052b-*.md): 0052B RED Band Approval

**Components:**

- **RED Band Approval** → Observability
  - File: `observability/metrics/red_band_approval.py`
  - red_band_approval_requests_total (result), phrase_mismatch_total (attempt), two_person_latency_seconds

- **RED Band Approval** → Audit Trail
  - File: `k0/receipts/red_band_audit.py`
  - 7-year retention to K0 receipts (ADR-0038), SOC2/ISO27001 compliance, immutable append-only logs

- **RED Band Approval** → RedBandAuditRecord
  - File: `k1/schemas/flatbuffers/red_band_audit.fbs`
  - Full audit: approval_id, operation, confidence_factors, phrase match result, approver IDs, execution result (1KB)

- **RED Band Approval** → Norman's Forcing Functions
  - File: `docs/research/norman_1988_forcing_functions.md`
  - Design of Everyday Things (Norman 1988), explicit phrase typing forces conscious confirmation

- **RED Band Approval** → Swiss Cheese Model
  - File: `docs/research/reason_1990_swiss_cheese.md`
  - Defense-in-depth (Reason 1990), RED band approval is one safety layer among many

#### [ADR-0052c](../../docs/architecture/decisions/0052c-*.md): 0052C Nested Clarifications

**Components:**

- **Nested Clarifications** → Observability
  - File: `observability/metrics/nested_clarifications.py`
  - nested_clarification_depth histogram (1-3), go_back_total (depth), max_depth_exceeded_total

- **Nested Clarifications** → Grounding Theory
  - File: `docs/research/clark_brennan_1991_grounding.md`
  - Grounding in Communication (Clark & Brennan 1991), nested clarifications build common ground incrementally

- **Nested Clarifications** → QUD Theory
  - File: `docs/research/roberts_1996_qud.md`
  - Questions Under Discussion (Roberts 1996), QUD stack = hierarchical question structure

- **Nested Clarifications** → Multi-Turn Dialogue
  - File: `docs/research/jurafsky_martin_2020_dialogue.md`
  - Dialogue state tracking (Jurafsky & Martin 2020), ClarificationHistory is dialogue state for HITL chains

#### [ADR-0052d](../../docs/architecture/decisions/0052d-*.md): 0052D Proactive Confirmation

**Components:**

- **Proactive Confirmation** → Prometheus Metrics
  - File: `observability/metrics/proactive_confirmations.py`
  - 7 metrics: confirmations_total (outcome/tier), user_decisions (decision/tier), confidence_histogram, outcome_feedback

- **Proactive Confirmation** → Weekly Accuracy Report
  - File: `observability/reports/proactive_accuracy.py`
  - Agent correctness tracking: % was_right (target >85%), trending analysis, action type breakdown

- **Proactive Confirmation** → User Fatigue Monitoring
  - File: `observability/alerts/user_fatigue.py`
  - Alert if false positive rate >5% (excessive confirmations), click-through rate >95% (habitual proceed)

- **Proactive Confirmation** → ProactiveConfirmationRecord
  - File: `k1/schemas/flatbuffers/proactive_confirmation.fbs`
  - K0 receipts audit: decision_id, confidence_score, reasoning, user_response (proceeded/retried/cancelled), outcome, feedback_signal

- **Proactive Confirmation** → Feedback Signals
  - File: `k0/learning/feedback_integration.py`
  - 1.0 (agent was right), 0.5 (partial correctness), 0.0 (agent was wrong), feed to Learning Loop (ADR-0059)


### Fast/Smart Lane Router

#### [ADR-0049](../../docs/architecture/decisions/0049-*.md): 0049 Router Policy

**Components:**

- **Router Policy** → Lane Scoring Engine
  - File: `k1/bridge_k0/router.py`
  - 4-factor score (privacy 0-80, obligation 0-50, payload 0-30, time_budget -20-10), <5ms CPU

- **Router Policy** → Fast Lane Criteria
  - File: `k1/bridge_k0/router.py`
  - score <40 AND queue depth <70%, GREEN band, <50ms P95 target

- **Router Policy** → Smart Lane Criteria
  - File: `k1/bridge_k0/router.py`
  - score ≥40 OR AMBER/RED band, Hippocampus pipelines, 150-200ms P95

- **Router Policy** → Privacy Weights
  - File: `k1/bridge_k0/router.py`
  - GREEN=0, AMBER=40, RED=80, privacy band determines lane preference

- **Router Policy** → Obligation Weights
  - File: `k1/bridge_k0/router.py`
  - +50 if consolidation/dedup/compliance/saga/cross-family, force Smart Lane

- **Router Policy** → Override Flags
  - File: `k1/bridge_k0/router.py`
  - Force Smart Lane for saga durable ordering, orchestrator control

- **Configuration** → Backpressure Integration
  - File: `k1/bridge_k0/backpressure_router.py`
  - Watermark integration (ADR-0039), protect Fast Lane saturation

- **Observability** → Router Metrics
  - File: `observability/metrics/router.py`
  - k1_k0_router_fast_total, k1_k0_router_smart_total, k1_k0_router_score_bucket, k1_k0_router_misroute_total

- **Observability** → Audit Trail
  - File: `k1/bridge_k0/router_audit.py`
  - Lane decision logging, score breakdown, cognitive_trace_id, K0 receipts validation

- **Configuration** → Router Config
  - File: `k1/config/k0_bridge.yml`
  - Configurable weights, hot-reload via Config Manager, feature flag lane_router.enabled


### FlatBuffers

#### [ADR-0011](../../docs/architecture/decisions/0011-*.md): 0011 Serialization Core

**Components:**

- **Serialization Core** → Serializer
  - File: `k1/l5_infrastructure/serialization/serializer.py`
  - Zero-copy serialization, <1ms P95, binary format, 1x size vs JSON 3x

- **Serialization Core** → Deserializer
  - File: `k1/l5_infrastructure/serialization/deserializer.py`
  - Zero-copy deserialization, <0.1ms P95, direct buffer access, no parsing

- **Serialization Core** → Buffer Pool
  - File: `k1/l5_infrastructure/serialization/buffer_pool.py`
  - Thread-local pools, 5 size classes (256B-64KB), eviction policy, 1.4× speedup

- **Serialization Core** → Memory Alignment
  - File: `k1/l5_infrastructure/serialization/alignment.py`
  - 4-byte/8-byte/16-byte alignment, SIMD optimization, force_align attribute

#### [ADR-0011a](../../docs/architecture/decisions/0011a-*.md): 0011A Schema Design

**Components:**

- **Schema Design** → Schema Validator
  - File: `tools/schema_validator.py`
  - Schema validation, file identifier checks, root type validation, compile-time errors

- **Schema Design** → Naming Conventions
  - File: `contracts/flatbuffers/naming.yml`
  - PascalCase tables, snake_case fields, UPPER_SNAKE_CASE enums, 4-char file IDs

- **Schema Design** → Type System
  - File: `contracts/flatbuffers/type_system.yml`
  - Scalars, vectors, strings, tables, unions, enums, structs, value types

- **Schema Design** → Forward Compatibility
  - File: `contracts/flatbuffers/compatibility.yml`
  - Optional fields, default values, no removals, union polymorphism

- **Schema Design** → Deprecation Policy
  - File: `contracts/flatbuffers/deprecation.yml`
  - 3-release grace period, (deprecated) attribute, migration guides

- **Schema Design** → Schema Registry
  - File: `k1/schemas/SCHEMA_VERSIONS.md`
  - 76 schemas, file ID→version mapping, introduced/deprecated/removed tracking

#### [ADR-0011b](../../docs/architecture/decisions/0011b-*.md): 0011B Code Generation

**Components:**

- **Code Generation** → flatc Compiler
  - File: `tools/flatc/wrapper.py`
  - v23.5.26, Python/C++/Rust bindings, --gen-object-api, <100ms compilation

- **Code Generation** → Python Bindings
  - File: `k1/schemas/generated/python/`
  - AgentState, TaskAnnouncement, SessionState, 76 generated modules

- **Code Generation** → C++ Bindings
  - File: `k1/schemas/generated/cpp/`
  - agent_state_generated.h, FlatBufferBuilder, C++17 concepts

- **Code Generation** → Rust Bindings
  - File: `k1/schemas/generated/rust/`
  - Cargo crate, flatbuffers::FlatBufferBuilder, Rust 1.70

- **Code Generation** → Build Integration
  - File: `CMakeLists.txt`
  - CMake add_custom_target, Bazel flatbuffer_library, setup.py build_py

- **Code Generation** → Type Stubs
  - File: `k1/schemas/types.py`
  - Python type hints, mypy support, IDE autocomplete, type-safe APIs

- **Code Generation** → CI Validation
  - File: `ci/validate_schemas.sh`
  - Schema compilation checks, breaking change detection, pre-commit hooks

#### [ADR-0011c](../../docs/architecture/decisions/0011c-*.md): 0011C Performance

**Components:**

- **Performance** → Zero-Copy Access
  - File: `k1/l5_infrastructure/serialization/zero_copy.py`
  - Memory-map buffers, vtable offsets, pointer arithmetic, 150× faster vs JSON

- **Performance** → Vtable Compression
  - File: `k1/l5_infrastructure/serialization/vtable.py`
  - Vtable sharing, deduplication, 6.2% memory savings, <1ms overhead

- **Performance** → String Deduplication
  - File: `k1/l5_infrastructure/serialization/string_dedup.py`
  - Reuse string offsets, 72% savings for repeated strings, offset reuse

- **Performance** → SIMD Optimization
  - File: `k1/l5_infrastructure/serialization/simd.py`
  - 16-byte alignment, SSE/AVX vectorization, 3× speedup for audio frames

- **Performance** → Benchmarks
  - File: `tests/performance/flatbuffers_bench.py`
  - SessionState 64KB <1ms serialize, <0.1ms deserialize, 11× throughput vs JSON

#### [ADR-0011d](../../docs/architecture/decisions/0011d-*.md): 0011D Schema Evolution

**Components:**

- **Schema Evolution** → Version Registry
  - File: `k1/schemas/SCHEMA_VERSIONS.md`
  - major.minor versioning, introduced/deprecated/removed tracking, 4-char file IDs

- **Schema Evolution** → Backward Compatibility
  - File: `contracts/flatbuffers/backward_compat.yml`
  - Add optional fields, new enum values, new tables, deprecation allowed

- **Schema Evolution** → Forward Compatibility
  - File: `contracts/flatbuffers/forward_compat.yml`
  - Ignore unknown fields, default values, unknown enum handling

- **Schema Evolution** → Migration Scripts
  - File: `scripts/migrate_schema.py`
  - Automated migration, field renaming, type changes, 3-release timeline

- **Schema Evolution** → Schema Diff Tool
  - File: `scripts/schema_diff.py`
  - Detect changes, breaking change alerts, version comparison


### FlatBuffers Schemas

#### [ADR-0012](../../docs/architecture/decisions/0012-*.md): 0012 Schema Taxonomy

**Components:**

- **Schema Taxonomy** → Complete Inventory
  - File: `k1/schemas/SCHEMA_INVENTORY.md`
  - 76 schemas total, 9 categories, hybrid architecture coverage (pure actors + AI agents)

- **Schema Taxonomy** → Category Organization
  - File: `k1/schemas/`
  - Base Types 5, K0 Pipelines 20, Agent Contracts 8, State 6, Model Hub 7, Tools 5, Protocol 6, Observability 5, WebSocket 7, Infrastructure 7

- **Schema Taxonomy** → File Structure
  - File: `k1/schemas/{category}/{entity}.fbs`
  - PascalCase tables, snake_case fields, 4-char file IDs, category-based organization

- **Schema Taxonomy** → Decision Matrix
  - File: `docs/architecture/decisions/0012-76-flatbuffers-schemas.md`
  - 76 schemas selected 9/10 vs 5 alternatives (fewer 3/10, Protobuf 6/10, more 5/10, monolithic 2/10)

- **Schema Taxonomy** → Design Patterns
  - File: `k1/schemas/PATTERNS.md`
  - 6 patterns: Request/Response Pairs, Agent Messages, SessionState, StateDelta, Protocol Events, Observability

- **File Identifiers** → Registry
  - File: `k1/schemas/FILE_IDENTIFIERS.md`
  - 76 4-char codes (AGST, TASK, PROP, SEST, BLFS, TDEF, MREQ, HREQ, AUDF, CFGS, METS, BPSG, etc.)

- **File Identifiers** → Validation
  - File: `k1/schemas/validators/file_id_validator.py`
  - File ID uniqueness checks, collision detection, identifier format validation

- **Schema Versioning** → Version Strategy
  - File: `k1/schemas/VERSIONING.md`
  - v1.0-v1.2, forward/backward compatibility, 3-release deprecation window

- **Schema Versioning** → Evolution Rules
  - File: `contracts/flatbuffers/evolution.yml`
  - Optional fields, default values, no removals, union polymorphism, migration scripts

- **Schema Versioning** → Breaking Changes
  - File: `docs/architecture/SCHEMA_CHANGES.md`
  - Change tracking, impact analysis, migration guides, CI validation

- **Performance** → Serialization Budgets
  - File: `k1/schemas/PERFORMANCE.md`
  - <0.5-3.2ms serialize (depends on size), <0.1-0.5ms deserialize, zero-copy optimization

- **Performance** → Size Efficiency
  - File: `k1/schemas/BENCHMARKS.md`
  - 1× FlatBuffers vs JSON 3×, 64KB SessionState, 256B-64KB typical schemas, 150× faster

- **Code Generation** → flatc Compiler
  - File: `tools/flatc/k1_compile_schemas.py`
  - v23.5.26, <10s compilation for all 76 schemas, --gen-object-api flag

- **Code Generation** → Python Bindings
  - File: `k1/schemas/generated/python/`
  - 228 generated files (76 schemas × 3 files/schema avg), imports, type hints

- **Code Generation** → C++ Bindings
  - File: `k1/schemas/generated/cpp/`
  - *_generated.h headers, FlatBufferBuilder, C++17 concepts, constexpr support

- **Code Generation** → Rust Bindings
  - File: `k1/schemas/generated/rust/`
  - Cargo crate flatbuffers-k1, FlatBufferBuilder, Rust 1.70+, future support

- **Code Generation** → Build Scripts
  - File: `scripts/generate_schemas.py`
  - CI integration, pre-commit hooks, incremental compilation, dependency tracking

- **Testing** → Contract Testing
  - File: `tests/schemas/test_contracts.py`
  - Schema round-trip tests, compatibility tests, breaking change detection

- **Testing** → Schema Fixtures
  - File: `tests/schemas/fixtures/`
  - Sample data for all 76 schemas, valid/invalid cases, edge cases

- **Testing** → Performance Tests
  - File: `tests/schemas/test_performance.py`
  - Serialization latency tests, memory usage tests, benchmark regression detection

- **Documentation** → Schema Catalog
  - File: `docs/schemas/CATALOG.md`
  - Complete reference: all 76 schemas, fields, types, examples, use cases

- **Documentation** → Integration Guide
  - File: `docs/schemas/INTEGRATION.md`
  - How to use schemas in K1 modules, best practices, common patterns, anti-patterns

#### [ADR-0012e](../../docs/architecture/decisions/0012e-*.md): 0012E Layer 5 Schemas

**Components:**

- **Layer 5 Schemas** → Config Manager
  - File: `k1/l5_infrastructure/config_manager/schemas/`
  - ConfigSnapshot CFGS, ConfigReloadEvent CFGR, ConfigValidationResult CFGV

- **Layer 5 Schemas** → Observability
  - File: `k1/l5_infrastructure/observability/schemas/`
  - MetricSample METS, TraceSpan TRSP, LogEntry LOGE, HealthCheckResult HLTH

- **Layer 5 Schemas** → Thermal Manager
  - File: `k1/l5_infrastructure/thermal/schemas/`
  - ThermalPlacement THPL, ThermalMetrics THMT, ThermalMigration THMG

- **Layer 5 Schemas** → Backpressure
  - File: `k1/l5_infrastructure/backpressure/schemas/`
  - BackpressureSignal BPSG, BackpressureAction BPAC, QueueMetrics QMET


### FlatBuffers SessionState Serialization

#### [ADR-0019](../../docs/architecture/decisions/0019-*.md): 0019 Serialization Core

**Components:**

- **Serialization Core** → K0 Bridge Batching
  - File: `k1/bridge_k0/session_state_batcher.py`
  - Batch multiple SessionState updates, <5ms batch latency, delta batching every 250ms

- **Serialization Core** → Schema Validation
  - File: `k1/schemas/session_state/validator.py`
  - Compile-time type safety, FlatBuffers compiler, 18 bugs caught

#### [ADR-0019a](../../docs/architecture/decisions/0019a-*.md): 0019A Schema Definition

**Components:**

- **Schema Definition** → Root Schema
  - File: `k1/schemas/session_state/session_state_root.fbs`
  - SessionStateRoot container, all 6 sections + metadata, schema_version SemVer 2.0

- **Schema Definition** → Delta Schema
  - File: `k1/schemas/session_state/session_state_delta.fbs`
  - SessionStateDelta, nullable sections (only changed), changed_sections array

- **Schema Definition** → Beliefs Section Schema
  - File: `k1/schemas/session_state/sections/beliefs_section.fbs`
  - Fact storage (key-value with confidence), LRU order, privacy band, 10-20KB size

- **Schema Definition** → Scoreboard Section Schema
  - File: `k1/schemas/session_state/sections/scoreboard_section.fbs`
  - Entity tracking (referents, salience), QUD stack, common ground, 4-8KB size

- **Schema Definition** → Control Section Schema
  - File: `k1/schemas/session_state/sections/control_section.fbs`
  - Agent leases (30s expiry), flow state (3-phase), turn lock, budget tracker, 8-12KB size

- **Schema Definition** → Persona Section Schema
  - File: `k1/schemas/session_state/sections/persona_section.fbs`
  - Personality traits (Big Five OCEAN), communication style (tone, verbosity, humor), voice continuity (prosody controls, voice history, emotional state), self-model (capabilities, consistency validat...

- **Schema Definition** → Multimodal Section Schema
  - File: `k1/schemas/session_state/sections/multimodal_section.fbs`
  - Audio buffers (K0 blob pointers), vision embeddings (CLIP 512-dim), streaming state, ambient context (room occupancy, PIR/mmWave sensors), multi-party conversations (active speakers, voice biometri...

- **Schema Definition** → Meta Section Schema
  - File: `k1/schemas/session_state/sections/meta_section.fbs`
  - Telemetry (session duration, turn counts), performance metrics (TTFT, E2E), Prometheus export, 2-4KB size

- **Schema Definition** → Type Definitions
  - File: `k1/schemas/session_state/types/`
  - Fact, Entity, AgentLease, PersonalityTrait, AudioBuffer, VisionEmbedding, PerformanceMetrics

- **Schema Definition** → Enum Definitions
  - File: `k1/schemas/session_state/enums/`
  - PrivacyBand (GREEN, AMBER, RED), AgentState (PENDING, ACTIVE, etc.), FlowPhase (NEGOTIATION, SELECTION, EXECUTION)

#### [ADR-0019c](../../docs/architecture/decisions/0019c-*.md): 0019C K0 WAL Integration

**Components:**

- **K0 WAL Integration** → K0 Bridge WAL Append
  - File: `k1/bridge_k0/k0_bridge.py`
  - HTTP/2 POST /k0/wal/append, FlatBuffers payload, <5ms P95 K0 local disk write


### Graceful Degradation

#### [ADR-0026](../../docs/architecture/decisions/0026-*.md): 0026 Thermal Management

**Components:**

- **Thermal Management** → Thermal Placement Manager
  - File: `k1/l5_infrastructure/thermal/placement_manager.py`
  - Asymmetric hysteresis (upgrade +5°C, downgrade -2°C, 7°C band), cooldown periods (10s upgrade, 30-60s downgrade), 4-tier placement (NPU→GPU→CPU→Remote), emergency jump (≥85°C), Khalil 2002 hysteresis

- **Thermal Management** → Device Capability Detection
  - File: `k1/l5_infrastructure/thermal/device_capability.py`
  - Form factor detection (laptop/phone/desktop/server), thermal capacity estimation, baseline temperature calculation (laptop 75°C, phone 65°C, desktop 82°C)

- **Thermal Management** → Thermal Sensor APIs
  - File: `k1/l5_infrastructure/thermal/sensors.py`
  - Cross-platform sensors (Linux thermal zones, Windows WMI, macOS IOKit), power measurement (Intel RAPL, NVIDIA SMI, AMD uProf), <1ms sensor read

- **Thermal Management** → Placement Decision Logic
  - File: `k1/l5_infrastructure/thermal/placement_decision.py`
  - State transition validation (hysteresis band check, cooldown period enforcement), placement scoring (temperature + power + latency + availability), emergency escalation (critical temperature → imme...

- **Thermal Management** → Thermal Metrics
  - File: `k1/l5_infrastructure/thermal/metrics.py`
  - Temperature tracking (P50/P95/P99), placement change rate (68/hour target), cooldown violation tracking (0 violations), thermal zone distribution (cool/warm/hot/critical time percentages)

#### [ADR-0027](../../docs/architecture/decisions/0027-*.md): 0027 Model Placement

**Components:**

- **Model Placement** → Model Placement Cascade
  - File: `k1/l5_infrastructure/placement/cascade_engine.py`
  - 4-tier cascade (NPU→GPU→CPU→Remote), automatic fallback, privacy enforcement (RED local only, AMBER local preferred, GREEN any), max 2 retries per tier, 5s total timeout, Netflix Hystrix 2012

- **Model Placement** → Circuit Breaker Manager
  - File: `k1/l5_infrastructure/placement/circuit_breaker.py`
  - State machine (closed→open→half-open), failure threshold (5 consecutive failures → open), automatic recovery (30s timeout → half-open, 3 successes → closed), per-adapter circuit state

- **Model Placement** → Capability Matcher
  - File: `k1/l5_infrastructure/placement/capability_matcher.py`
  - Accelerator capability detection (NPU: Gemma 2B/7B INT8, GPU: Llama 8B FP16, CPU: same as GPU), model requirement matching (model size ≤ device memory), placement scoring (latency + availability + ...

- **Model Placement** → Cost Tracker
  - File: `k1/l5_infrastructure/placement/cost_tracker.py`
  - Per-turn cost tracking ($0.001-0.01 per remote turn), daily budget enforcement ($5/day default), cost alerts (80% budget → warning, 100% budget → block remote)

- **Model Placement** → Placement Metrics
  - File: `k1/l5_infrastructure/placement/metrics.py`
  - Placement distribution (NPU 65%, GPU 27%, CPU 7%, Remote 1%), cascade fallback rate (35% require fallback), circuit breaker state tracking, privacy compliance rate (100% RED local only)

#### [ADR-0061](../../docs/architecture/decisions/0061-*.md): 0061 Backpressure

**Components:**

- **Backpressure** → Tier 1 Watermark Checker
  - File: `k1/l5_infrastructure/backpressure/watermark_checker.py`
  - Per-stream watermark monitoring (80% warn, 90% degrade, 95% reject), 10% hysteresis (prevents oscillation), overflow actions (drop_oldest, block_sender, merge_deltas, disconnect_slow), SEDA Welsh 2001

- **Backpressure** → Tier 2 Voice Pipeline Monitor
  - File: `k1/l5_infrastructure/backpressure/voice_pipeline_monitor.py`
  - 5-stage voice pipeline (ASR input, intent queue, tool executor, TTS queue, audio output), stage-specific degradation (frame drop, TTS simplification, barge-in preemption), <50ms signal propagation

- **Backpressure** → Tier 3 Global Limits Enforcer
  - File: `k1/l5_infrastructure/backpressure/global_limits_enforcer.py`
  - Global resource monitoring (512MB memory limit, 5000 queue items max), sustained backpressure detection (3-30s depending on tier), cascading degradation policies (Tier 1 reject new → Tier 2 cancel ...

- **Backpressure** → Backpressure Coordinator
  - File: `k1/l5_infrastructure/backpressure/cascade_coordinator.py`
  - Event bus for signal broadcast, <50ms propagation to all components, component registration (API Gateway, Orchestrator, Agent Fabric, Tool Runner), BackpressureSignal (tier, timestamp, reason, trac...

- **Backpressure** → Privacy Band Overrides
  - File: `k1/l5_infrastructure/backpressure/privacy_overrides.py`
  - RED band bypass logic (arbiter approval, emergency safety always pass), AMBER degradation (local only, no remote fallback), GREEN rejection (503 Service Unavailable at capacity)

- **Backpressure** → Backpressure Metrics
  - File: `k1/l5_infrastructure/backpressure/metrics.py`
  - backpressure_tier_gauge (NORMAL/TIER_1/TIER_2/TIER_3), watermark_breaches_total (counter), tier_transitions_total (counter), hysteresis_gap_ms (time in hysteresis zone), <5ms check overhead


### K0 Bridge

#### [ADR-0044](../../docs/architecture/decisions/0044-*.md): 0044 Bridge Client

**Components:**

- **Bridge Client** → HTTP/2 Client
  - File: `k1/bridge_k0/k0_bridge_client.py`
  - HTTP/2 connection management, 1 connection per K0 port, connection pooling, <10ms round-trip latency, 1,680 lines implementation

- **Batching Layer** → Batch Accumulator
  - File: `k1/bridge_k0/batching/batch_accumulator.py`
  - Max 50 items per batch, 250ms timeout, 95% batch efficiency (avg 47.5 items/batch), automatic flush on timeout

- **Reliability** → Retry Handler
  - File: `k1/bridge_k0/reliability/retry_handler.py`
  - Exponential backoff 1s→16s, max 5 retries, 99.9% retry success rate, idempotency keys

- **Reliability** → Circuit Breaker
  - File: `k1/bridge_k0/reliability/circuit_breaker.py`
  - 3 failures→open, 30s timeout, half-open testing, per-port circuit state, automatic recovery

- **Port Clients** → P01 Command Port
  - File: `k1/bridge_k0/ports/p01_command_client.py`
  - Port 8081, write operations (Turn, Event, CRDT), FlatBuffers serialization, batch support, 4.2M turns written in production

- **Port Clients** → P02 Query Port
  - File: `k1/bridge_k0/ports/p02_query_client.py`
  - Port 8082, read operations, query optimization, caching integration, <10ms read latency

- **Port Clients** → P03 SSE Port
  - File: `k1/bridge_k0/ports/p03_sse_client.py`
  - Port 8083, event streaming, topic subscription, SSE connection management, backpressure handling

- **Port Clients** → P04 CRDT Port
  - File: `k1/bridge_k0/ports/p04_crdt_client.py`
  - Port 8084, CRDT sync operations, multi-device coordination, conflict resolution, eventual consistency

- **Port Clients** → P06 Job Port
  - File: `k1/bridge_k0/ports/p06_job_client.py`
  - Port 8086, background jobs, async task submission, job status polling, completion callbacks


### K0 Bridge Batching

#### [ADR-0022](../../docs/architecture/decisions/0022-*.md): 0022 Batching Core

**Components:**

- **Batching Core** → 3-Trigger Flush
  - File: `k1/bridge_k0/batching_engine.py`
  - Time 250ms OR size 64KB OR count 100, adaptive batching, flush when ANY trigger met

- **Batching Core** → Bounded Memory
  - File: `k1/bridge_k0/batching_engine.py`
  - 1000 pending receipts max (5MB bounded), prevent OOM, drop oldest background receipts

- **Batching Core** → Bounded Latency
  - File: `k1/bridge_k0/batching_engine.py`
  - 250ms max batch time, <250ms P95 flush latency, guaranteed responsiveness

- **Batching Core** → Priority Queue
  - File: `k1/bridge_k0/batching_engine.py`
  - 4 priority classes (CRITICAL, REALTIME, INTERACTIVE, BACKGROUND), <1ms priority sort

- **Batching Core** → Backpressure Cascade
  - File: `k1/bridge_k0/batching_engine.py`
  - K0 overload triggers backpressure, drop oldest background, preserve CRITICAL/REALTIME

#### [ADR-0022a](../../docs/architecture/decisions/0022a-*.md): 0022A Batching Algorithm

**Components:**

- **Batching Algorithm** → Batch Size Range
  - File: `k1/bridge_k0/batching_engine.py`
  - 10 min, 50 max (adaptive), increase under high load, decrease under low load

- **Batching Algorithm** → Timeout Trigger
  - File: `k1/bridge_k0/batching_engine.py`
  - 100ms max wait, flush partial batch on timeout, balance latency vs throughput

- **Batching Algorithm** → Fairness Queue
  - File: `k1/bridge_k0/batching_engine.py`
  - Round-robin per session, max 5 messages per session per batch, prevent monopolization

- **Batching Algorithm** → Adaptive Sizing
  - File: `k1/bridge_k0/batching_engine.py`
  - Increase batch size under >100 msgs/sec, decrease under <50 msgs/sec, load-responsive

- **Batching Algorithm** → Throughput Optimization
  - File: `k1/bridge_k0/batching_engine.py`
  - 5000+ msgs/sec batched (vs 100 msgs/sec individual), 50× improvement, HTTP/2 amortization

#### [ADR-0022b](../../docs/architecture/decisions/0022b-*.md): 0022B HTTP/2 Integration

**Components:**

- **HTTP/2 Integration** → Connection Pooling
  - File: `k1/bridge_k0/http2_client.py`
  - Persistent HTTP/2 connections, connection reuse, multiplexing, <5ms connection overhead

- **HTTP/2 Integration** → Multiplexing
  - File: `k1/bridge_k0/http2_client.py`
  - Multiple streams per connection, concurrent requests, stream priority, HTTP/2 streams

- **HTTP/2 Integration** → Keepalive
  - File: `k1/bridge_k0/http2_client.py`
  - HTTP/2 PING frames (30s interval), detect stale connections, auto-reconnect, health check

- **HTTP/2 Integration** → TLS Session Reuse
  - File: `k1/bridge_k0/http2_client.py`
  - TLS session resumption, avoid handshake overhead, <1ms vs 50ms full handshake, performance

#### [ADR-0022c](../../docs/architecture/decisions/0022c-*.md): 0022C Backpressure

**Components:**

- **Backpressure** → Queue Depth Monitoring
  - File: `k1/bridge_k0/backpressure_monitor.py`
  - Monitor K0 queue depth, >80% triggers backpressure, <1ms depth check, upstream cascade

- **Backpressure** → Drop Oldest Policy
  - File: `k1/bridge_k0/backpressure_monitor.py`
  - Drop oldest background receipts first, preserve CRITICAL/REALTIME, graceful degradation

- **Backpressure** → Upstream Cascade
  - File: `k1/bridge_k0/backpressure_monitor.py`
  - Propagate backpressure to K1 kernel (<50ms), slow down receipt generation, flow control

- **Backpressure** → Recovery Logic
  - File: `k1/bridge_k0/backpressure_monitor.py`
  - Resume batching when queue <60%, hysteresis (avoid oscillation), smooth recovery

#### [ADR-0022d](../../docs/architecture/decisions/0022d-*.md): 0022D FlatBuffers Schema

**Components:**

- **FlatBuffers Schema** → Compression Support
  - File: `k1/bridge_k0/batch_compressor.py`
  - zstd level 3 for batches >1KB, 2-3× size reduction, <1ms compression overhead

- **FlatBuffers Schema** → Batch Schema
  - File: `k1/schemas/k0_bridge/batch.fbs`
  - ReceiptBatch table, array of receipts, compression flag, batch_id, sequence_number

- **FlatBuffers Schema** → Zero-Copy Batch
  - File: `k1/schemas/k0_bridge/batch.fbs`
  - Zero-copy deserialization, direct buffer access, <0.1ms deserialize, 150× faster vs JSON

- **FlatBuffers Schema** → Batch Metadata
  - File: `k1/schemas/k0_bridge/batch.fbs`
  - batch_id, sequence_number, receipt_count, total_size_bytes, compression_algorithm, timestamp_ms


### K0 Bridge HTTP/2

#### [ADR-0044a](../../docs/architecture/decisions/0044a-*.md): 0044A Transport Protocol

**Components:**

- **Transport Protocol** → HTTP/2 Connection Manager
  - File: `k1/bridge_k0/http2/connection_manager.py`
  - 1 persistent HTTP/2 connection per K0 port (5 ports: P01 Command, P02 Query, P03 SSE, P04 CRDT, P06 Job), max 100 concurrent streams per connection

- **Transport Protocol** → Stream Multiplexing
  - File: `k1/bridge_k0/http2/multiplexing.py`
  - Up to 100 concurrent streams per connection, binary framing (efficient protocol), header compression (HPACK), flow control per stream, <10ms round-trip vs 50ms HTTP/1.1

- **Transport Protocol** → Connection Health
  - File: `k1/bridge_k0/http2/health_monitor.py`
  - PING frames every 10s (keep-alive), detect stale connections, auto-reconnect on connection loss, exponential backoff (1s → 60s cap)

- **Transport Protocol** → TLS 1.3 Security
  - File: `k1/bridge_k0/http2/tls.py`
  - TLS 1.3 only (no TLS 1.2), mutual authentication (client cert + server cert), certificate pinning (prevent MITM), verify hostname

#### [ADR-0044b](../../docs/architecture/decisions/0044b-*.md): 0044B Serialization

**Components:**

- **Serialization** → FlatBuffers Schema
  - File: `k1/schemas/k0_bridge/`
  - Schema-first design (.fbs files), code generation (flatc compiler), version schemas with SemVer, optional fields for backward compatibility

- **Serialization** → Zero-Copy Deserialization
  - File: `k1/bridge_k0/http2/flatbuffers_deserializer.py`
  - Direct buffer access (no parsing), no memory allocation on read, read fields on-demand (lazy evaluation), <1ms deserialization vs 5ms JSON

- **Serialization** → Type Safety
  - File: `k1/bridge_k0/http2/flatbuffers_types.py`
  - Generated Python classes, type hints for all fields, compile-time schema validation, IDE autocomplete support

- **Serialization** → Schema Evolution
  - File: `k1/bridge_k0/http2/schema_evolution.py`
  - Add new optional fields (backward compatible), deprecate old fields (forward compatible), version field in root table (schema_version: string), compatibility matrix tracking

#### [ADR-0044c](../../docs/architecture/decisions/0044c-*.md): 0044C Batching

**Components:**

- **Batching** → Multi-Trigger Batching
  - File: `k1/bridge_k0/http2/batching_engine.py`
  - Time-bounded (250ms), size-bounded (64KB), count-bounded (50 items), whichever comes first wins, 98% request reduction (50:1 ratio)

- **Batching** → Per-Session Cooldown
  - File: `k1/bridge_k0/http2/session_cooldown.py`
  - Min 50ms between flushes per session, prevents rapid-fire batches from single session, fair multiplexing across sessions

- **Batching** → Priority-Based Overflow
  - File: `k1/bridge_k0/http2/overflow_protection.py`
  - Max 1000 pending items across all sessions, drop oldest BACKGROUND tasks first, preserve REALTIME/URGENT tasks, emit warnings to monitoring

- **Batching** → Compression
  - File: `k1/bridge_k0/http2/compression.py`
  - zstd compression for payloads >4KB, compression level 3 (balance speed/ratio), 40-60% compression ratio typical

#### [ADR-0044d](../../docs/architecture/decisions/0044d-*.md): 0044D Error Handling

**Components:**

- **Error Handling** → Exponential Backoff Retry
  - File: `k1/bridge_k0/http2/retry_handler.py`
  - Base delay 1s, exponential 2^attempt (1s → 2s → 4s → 8s → 16s max), max 3 attempts, jitter ±500ms (prevent thundering herd)

- **Error Handling** → Circuit Breaker
  - File: `k1/bridge_k0/http2/circuit_breaker.py`
  - Failure threshold 3 consecutive failures, state machine (CLOSED → OPEN → HALF_OPEN), recovery timeout 30s, half-open test (1 request allowed), fail fast when K0 down

- **Error Handling** → Idempotency Keys
  - File: `k1/bridge_k0/http2/idempotency.py`
  - Write idempotency key {session_id}/{turn_id}, K0 deduplicates on this key (24-hour window), safe to retry without duplicates

- **Error Handling** → Dead Letter Queue
  - File: `k1/bridge_k0/http2/dlq.py`
  - Store failed batches with full context (trace_id, error reason, payload), 7-day retention, manual resubmit capability, alert on DLQ growth

- **Error Handling** → Error Classification
  - File: `k1/bridge_k0/http2/error_classifier.py`
  - Retryable (network errors, timeouts, 503 Service Unavailable, 429 Rate Limit), non-retryable (4xx client errors except 429, schema validation errors, 401 Unauthorized)


### K0 Core

#### [ADR-0001](../../docs/architecture/decisions/0001-*.md): 0001 Memory Kernel

**Components:**

- **Memory Kernel** → P01-P20 Pipelines
  - File: `k0/pipelines/`
  - RecallQuery, MemoryWrite, AttentionGate, Hippocampus, FeedbackIntegration, SelfModelUpdate

- **Memory Kernel** → Durable Storage
  - File: `k0/storage/`
  - WAL, receipts, SQLite (hot), Parquet (cold), ACID guarantees

#### [ADR-0001f](../../docs/architecture/decisions/0001f-*.md): 0001F K0 Communication

**Components:**

- **Memory Kernel** → Multi-Store
  - File: `k0/stores/`
  - Episodic, semantic, procedural, snapshots, affect, self-model, social

#### [ADR-0081](../../docs/architecture/decisions/0081-*.md): 0081 Knowledge Graph

**Components:**

- **Knowledge Graph** → Graph Schema
  - File: `k0/drivers/sqlite_kg.py`
  - 3-table design (nodes, edges, temporal_edges), entity types (Person, Location, Event, Organization, Thing), relationship types (parent, child, sibling, spouse, friend, employed_by, located_at, part...

- **Knowledge Graph** → Temporal Edges
  - File: `k0/kg/temporal_edges.py`
  - Relationship evolution tracking, bitemporal support (valid_from/valid_to for relationship evolution, created_at for insertion time), historical relationship queries, timeline queries ("Who was Alic...

- **Knowledge Graph** → Query API
  - File: `k0/query/kg_temporal.py`
  - 4 query categories (entity lookup, relationship queries, temporal queries, graph traversal), timeline queries with temporal edge filtering, entity lookup <10ms P95, relationship traversal <50ms P95...

- **Knowledge Graph** → Graph Traversal
  - File: `k0/kg/traversal.py`
  - BFS (Breadth-First Search) for shortest path in unweighted graphs O(V+E), DFS (Depth-First Search) for cycle detection and reachability O(V+E), Dijkstra for shortest path in weighted graphs O((V+E)...

- **Knowledge Graph** → Episodic Integration
  - File: `k0/kg/episodic_integration.py`
  - 4-stage extraction pipeline (NER → relationship extraction → entity resolution → KG update), P03 Consolidation integration (episodic → semantic → KG), spaCy en_core_web_lg model (96% accuracy), con...

- **Knowledge Graph** → Entity Extractor
  - File: `k0/kg/entity_extractor.py`
  - spaCy NER integration for Named Entity Recognition (PERSON, GPE, DATE, ORG), dependency parsing for relationship identification (nsubj, dobj, prep), pattern matching for relationship extraction, en...

- **Knowledge Graph** → Visualization
  - File: `k0/kg/visualization.py`
  - Mermaid export (graph LR format for ADRs and design docs), GraphML export (XML format for Gephi/Cytoscape/yEd), JSON export (structured format for API responses and programmatic access), debugging ...

- **Knowledge Graph** → KG Metrics
  - File: `k0/kg/metrics.py`
  - Real-time metrics (node count, edge count, query latency P50/P95/P99, entity resolution accuracy), historical trends (graph growth over time, query performance degradation), alerts (query latency >...

#### [ADR-0081a](../../docs/architecture/decisions/0081a-*.md): 0081A Knowledge Graph

**Components:**

- **Knowledge Graph** → Graph Schema
  - File: `k0/drivers/sqlite_kg.py`
  - 3-table design (nodes, edges, temporal_edges), entity types (Person, Location, Event, Organization, Thing), relationship types (parent, child, sibling, spouse, friend, employed_by, located_at, part...

- **Knowledge Graph** → Temporal Edges
  - File: `k0/kg/temporal_edges.py`
  - Relationship evolution tracking, bitemporal support (valid_from/valid_to for relationship evolution, created_at for insertion time), historical relationship queries, timeline queries ("Who was Alic...

#### [ADR-0081b](../../docs/architecture/decisions/0081b-*.md): 0081B Knowledge Graph

**Components:**

- **Knowledge Graph** → Query API
  - File: `k0/query/kg_temporal.py`
  - 4 query categories (entity lookup, relationship queries, temporal queries, graph traversal), timeline queries with temporal edge filtering, entity lookup <10ms P95, relationship traversal <50ms P95...

- **Knowledge Graph** → Graph Traversal
  - File: `k0/kg/traversal.py`
  - BFS (Breadth-First Search) for shortest path in unweighted graphs O(V+E), DFS (Depth-First Search) for cycle detection and reachability O(V+E), Dijkstra for shortest path in weighted graphs O((V+E)...

#### [ADR-0081c](../../docs/architecture/decisions/0081c-*.md): 0081C Knowledge Graph

**Components:**

- **Knowledge Graph** → Episodic Integration
  - File: `k0/kg/episodic_integration.py`
  - 4-stage extraction pipeline (NER → relationship extraction → entity resolution → KG update), P03 Consolidation integration (episodic → semantic → KG), spaCy en_core_web_lg model (96% accuracy), con...

- **Knowledge Graph** → Entity Extractor
  - File: `k0/kg/entity_extractor.py`
  - spaCy NER integration for Named Entity Recognition (PERSON, GPE, DATE, ORG), dependency parsing for relationship identification (nsubj, dobj, prep), pattern matching for relationship extraction, en...

#### [ADR-0081d](../../docs/architecture/decisions/0081d-*.md): 0081D Knowledge Graph

**Components:**

- **Knowledge Graph** → Visualization
  - File: `k0/kg/visualization.py`
  - Mermaid export (graph LR format for ADRs and design docs), GraphML export (XML format for Gephi/Cytoscape/yEd), JSON export (structured format for API responses and programmatic access), debugging ...

- **Knowledge Graph** → KG Metrics
  - File: `k0/kg/metrics.py`
  - Real-time metrics (node count, edge count, query latency P50/P95/P99, entity resolution accuracy), historical trends (graph growth over time, query performance degradation), alerts (query latency >...


### K0 Memory Consolidation

#### [ADR-0084](../../docs/architecture/decisions/0084-*.md): 0084 Core Architecture

**Components:**

- **Core Architecture** → 3-Layer Pipeline
  - File: `k0/consolidation/`
  - 5 consolidation processes (Hippocampal replay, Neocortical integration, Synaptic homeostasis, KG consolidation, Dream exploration), 90-minute sleep cycles (NREM Phase 1 45min, NREM Phase 2 30min, R...

- **Core Architecture** → Sleep Coordination
  - File: `k0/consolidation/scheduler.py`
  - SLEEP_SCHEDULER idle detection (CPU <5% for 15min, 2AM-5AM preferred, battery >30%), SLEEP_STATE_MACHINE (IDLE→NREM1→NREM2→REM→WAKING→IDLE), SLEEP_TRIGGER event coordination, K0 Offsets progress tr...

- **Core Architecture** → P03 Pipeline Integration
  - File: `k0/pipelines/p03_consolidation.py`
  - K0 WAL (evt_wal) → P03 fan-out, batch processing (1000 events/batch), priority LOW (nice +10), pausable on user activity, 5 consolidation handlers (CONS_HIPPOCAMPAL, CONS_NEOCORTICAL, CONS_SYNAPTIC...

- **Neocortical Integration** → Episodic→Semantic Transform
  - File: `k0/consolidation/neocortical_integration.py`
  - Pattern extraction (temporal patterns, location sequences, entity generalizations), embedding clustering (threshold 0.85), frequency threshold (≥3 occurrences), confidence scoring (≥0.70 to qualify...

- **Neocortical Integration** → Semantic Memory Creation
  - File: `k0/storage/semantic_memories.py`
  - K0::st_sqlite[semantic_memories] storage, pattern types (routine, preference, habit, concept), common entities/actions/temporal context extraction, source episode references, consolidation criteria...

- **Synaptic Homeostasis** → Forgetting & Pruning
  - File: `k0/consolidation/synaptic_homeostasis.py`
  - Stale data detector (last_accessed_ts >90 days, access_count=0, emotional_salience <0.30), Ebbinghaus exponential decay (retention = base^(-time/half_life), base=0.5, half_life=30 days), weak conne...

- **Synaptic Homeostasis** → Archival & Compression
  - File: `k0/storage/archived_memories.py`
  - K0::st_sqlite[archived_memories] table, archive criteria (>90 days, access_count=0, low salience), LZ4 compression, rollups/summaries (P15 integration), SQLite VACUUM every 30 days, ≥30% storage re...

#### [ADR-0084a](../../docs/architecture/decisions/0084a-*.md): 0084A Hippocampal Replay

**Components:**

- **Hippocampal Replay** → Pattern Strengthening
  - File: `k0/consolidation/hippocampal_replay.py`
  - CA3_CONSOLIDATION coordinator, 10-20x accelerated replay, 100-150 memories/NREM Phase 1, emotional salience prioritization (2x replay cycles for salience ≥0.70), access frequency weighting, recency...

- **Hippocampal Replay** → CA3 Recurrent Activation
  - File: `k0/ca3/recurrent_network.py`
  - CA3_RECURRENT association retrieval (~5-10 associated nodes per memory), temporal proximity (co-occurred within 5min), semantic similarity (embedding cosine ≥0.75), causal relationships (from KG_CA...

- **Hippocampal Replay** → Synaptic Strengthening
  - File: `k0/consolidation/synaptic_strengthening.py`
  - Hebbian learning (Δw = η *activation_src* activation_dst, η=0.03), Long-Term Potentiation (LTP) simulation (3+ replays →+10% weight boost), max weight 1.0, asymptotic saturation, replay speed modul...

- **Hippocampal Replay** → Theta Rhythm Coordination
  - File: `k0/ca1/theta_rhythm.py`
  - CA1_THETA oscillation generator (4-8 Hz), NREM theta 4-6 Hz (slow, consolidation), REM theta 6-8 Hz (fast, exploration), theta phase precession (encoding phase π-2π, retrieval phase 0-π), theta-gat...

#### [ADR-0084b](../../docs/architecture/decisions/0084b-*.md): 0084B Sleep State Machine

**Components:**

- **Sleep State Machine** → Idle Detection
  - File: `k0/consolidation/scheduler.py`
  - CPU <5% for 15min window, preferred 2AM-5AM, no user input (keyboard/mouse/touchscreen), battery >30%, Command Port queue <10 entries, fallback (any 3-hour idle), manual trigger (k0ctl consolidate ...

- **Sleep State Machine** → State Orchestration
  - File: `k0/consolidation/state_machine.py`
  - 5 states (IDLE, NREM_PHASE_1, NREM_PHASE_2, REM_PHASE, WAKING), 90-minute ultradian cycles, state durations (NREM1 45min, NREM2 30min, REM 15min, Waking 5min), interruption handling (pause on user ...

- **Sleep State Machine** → NREM Phase 1 Handler
  - File: `k0/consolidation/nrem_phase_1_handler.py`
  - Hippocampal replay execution (ADR-0084a integration), CA3_CONSOLIDATION coordination, 100-150 memories replayed, theta rhythm 4-6 Hz (slow theta), 45-minute phase duration, 2-3 memories/minute repl...

- **Sleep State Machine** → NREM Phase 2 Handler
  - File: `k0/consolidation/nrem_phase_2_handler.py`
  - Synaptic homeostasis (pruning), neocortical integration (episodic→semantic), 50-100 patterns extracted, 500-1000 connections pruned, knowledge graph consolidation, 30-minute phase duration, paralle...

- **Sleep State Machine** → REM Phase Handler
  - File: `k0/consolidation/rem_phase_handler.py`
  - Dream exploration (ADR-0084d integration), theta rhythm 6-8 Hz (fast theta), 5-10 insights generated, 3-5 counterfactuals, 5-10 skills rehearsed, 3-5 reflection prompts, 15-minute phase duration, c...

- **Sleep State Machine** → Waking Phase Handler
  - File: `k0/consolidation/waking_phase_handler.py`
  - Flush pending writes, P13 Index Rebuild integration, consolidation summary generation, infra.consolidation.complete event emission (cycle stats: memories_consolidated, patterns_extracted, insights_...

- **Resource Management** → CPU Priority & Affinity
  - File: `k0/consolidation/resource_limits.py`
  - Nice +10 (low CPU priority), ionice idle (Linux), CPU affinity (last 2 cores), BELOW_NORMAL_PRIORITY_CLASS (Windows), <5% average CPU usage, pausable on user activity, yield to user processes

- **Resource Management** → Memory & Disk Limits
  - File: `k0/consolidation/resource_limits.py`
  - Memory cap 256 MB (resource.setrlimit), batch size 1000 events (prevents memory spikes), disk I/O <5 MB/s, ionice idle class, async writes, fsync every 5min, pause if battery <30%, reduce frequency...

#### [ADR-0084c](../../docs/architecture/decisions/0084c-*.md): 0084C Knowledge Graph Consol.

**Components:**

- **Knowledge Graph Consol.** → Entity Extraction
  - File: `k0/consolidation/kg_consolidation.py`
  - 7 entity types (PERSON, PLACE, ORGANIZATION, CONCEPT, EVENT, TEMPORAL, OBJECT), Named Entity Recognition (NER) via linguistic_mapping, embedding clustering (threshold 0.85), canonical entity creati...

- **Knowledge Graph Consol.** → Relationship Inference
  - File: `k0/kg/relation_discovery.py`
  - 6 relationship types (CAUSAL, TEMPORAL, ASSOCIATIVE, HIERARCHICAL, POSSESSIVE, SOCIAL), co-occurrence detection (≥3 instances, temporal proximity <5min), KG_CAUSAL_GRAPH integration, PMI associatio...

- **Knowledge Graph Consol.** → Schema Evolution
  - File: `k0/kg/concept_evolution.py`
  - KG_CONCEPT_EVOLUTION engine, schema change detection (new entity/relation types ≥10/5 instances), concept merge/split, version control (K0::st_kg[schema_versions]), migration with rollback support,...

- **Knowledge Graph Consol.** → Temporal Reasoning
  - File: `k0/kg/temporal.py`
  - KG_TEMPORAL_ENGINE, time-stamped snapshots (node_id, timestamp, properties), 365-day retention, historical state queries ("What were Alice's interests last month?"), temporal range queries (track c...

#### [ADR-0084d](../../docs/architecture/decisions/0084d-*.md): 0084D Dream Exploration

**Components:**

- **Dream Exploration** → Explorative Dreaming
  - File: `k0/consolidation/dream_exploration.py`
  - DREAM_EXPLORATION semantic space random walks, K0::st_vector traversal, temperature-based sampling (0.70 balanced exploration/exploitation), 50 steps per REM phase, novel association detection (sem...

- **Dream Exploration** → Counterfactual Thinking
  - File: `k0/consolidation/counterfactual_simulator.py`
  - SIM_COUNTERFACTUAL integration, decision point identification, alternative sequence generation, KG_CAUSAL_GRAPH outcome prediction, 3-5 scenarios per REM Phase, counterfactual learning (better alte...

- **Dream Exploration** → Mental Rehearsal
  - File: `k0/consolidation/mental_rehearsal.py`
  - DREAM_REHEARSAL motor skill practice, K0::st_sqlite[motor_programs] simulation, procedural memory strengthening (rehearsal_count++, execution_speed *= 0.95, error_rate*= 0.90), 5-10 skills rehearse...

- **Dream Exploration** → Reflection Prompts
  - File: `k0/consolidation/reflection_prompt_generator.py`
  - 5 prompt types (MEMORY_GAP, UNRESOLVED_THREAD, GOAL_PROGRESS, EMOTIONAL_TREND, HABIT_INSIGHT), memory gap detection (expected events not logged), unresolved thread analysis (goals without progress)...


### K0 SSE Event Streaming

#### [ADR-0042](../../docs/architecture/decisions/0042-*.md): 0042 Durable Events Foundation

**Components:**

- **Durable Events Foundation** → K0 to K1 Boundary
  - File: `k1/bridge_k0/sse/event_consumer.py`
  - W3C Server-Sent Events (2015) for durable persistent events (config hot-reload, receipt ACKs, learning feedback, CRDT sync), <10ms notification vs 10s polling (1000× faster)

- **Durable Events Foundation** → Cursor-Based Replay
  - File: `k1/bridge_k0/sse/replay_manager.py`
  - Cursor-based replay from K0 WAL for K1 restart recovery (last_processed_offset), durable events never lost, multi-consumer fanout (1-to-N horizontal scaling)

- **Durable Events Foundation** → Backpressure Management
  - File: `k1/bridge_k0/sse/backpressure.py`
  - Slow K1 consumers disconnected at 10K unACKed events (protects K0 from memory exhaustion), lagging instances catch up via replay

#### [ADR-0042a](../../docs/architecture/decisions/0042a-*.md): 0042A Event Production

**Components:**

- **Event Production** → WALReader Cursor-Based
  - File: `k0/sse/wal_reader.py`
  - Reads durable events from K0 WAL (config, receipts, learning, CRDT), 10ms polling interval, continuous background task, batch reading (max 100 events)

- **Event Production** → FanoutManager 1-to-N
  - File: `k0/sse/fanout_manager.py`
  - 1-to-N broadcasting (single K0 event → N K1 instances), topic-based filtering (wildcard patterns), <10ms delivery latency

- **Event Production** → TopicFilter Wildcard
  - File: `k0/sse/topic_filter.py`
  - Wildcard pattern matching (k0.config.* matches all config events), subscription filtering, future-proof subscriptions

- **Event Production** → EventBatcher Compression
  - File: `k0/sse/event_batcher.py`
  - Compression + batching for event delivery, zstd compression level 3, reduces bandwidth 40-60%

#### [ADR-0042b](../../docs/architecture/decisions/0042b-*.md): 0042B Event Consumption

**Components:**

- **Event Consumption** → K1SSESubscriber
  - File: `k1/bridge_k0/sse/subscriber.py`
  - Subscribe to K0 SSE topics (HTTP EventSource-style), long-lived connection, cursor tracking (last_offset per consumer_group), route events to handlers

- **Event Consumption** → Cursor Tracking
  - File: `k1/bridge_k0/sse/cursor_tracker.py`
  - Track last processed offset per consumer group, persist to disk (K1 restart recovery), POST /k0/sse/ack with offset

- **Event Consumption** → Event Routing
  - File: `k1/bridge_k0/sse/event_router.py`
  - Route SSE events to handlers (topic → handler mapping), ConfigManager.on_config_changed, LearningLoop.on_feedback, CRDTManager.on_merge

- **Event Consumption** → ACK Mechanism
  - File: `k1/bridge_k0/sse/ack_manager.py`
  - ACK events to K0 (POST /k0/sse/ack), backpressure control (K0 knows if K1 processed), at-least-once delivery guarantee

#### [ADR-0042c](../../docs/architecture/decisions/0042c-*.md): 0042C Reconnection

**Components:**

- **Reconnection** → K1SSEReconnector
  - File: `k1/bridge_k0/sse/reconnector.py`
  - Automatic reconnection with exponential backoff (1s, 2s, 4s, 8s, 16s, 32s, 60s max), detect connection failures (HTTP errors, timeouts)

- **Reconnection** → Cursor-Based Resume
  - File: `k1/bridge_k0/sse/cursor_resume.py`
  - Resume from cursor (Last-Event-ID pattern), replay missed events since last ACK, zero data loss on K1 crash/restart

- **Reconnection** → Idempotent Handlers
  - File: `k1/bridge_k0/sse/idempotency.py`
  - Deduplication via event_id (detect replayed duplicates), idempotent event handlers required, at-least-once delivery semantics

- **Reconnection** → Replay Metrics
  - File: `k1/bridge_k0/sse/replay_metrics.py`
  - Missed event count tracking, replay latency measurement (1200 events/s throughput), observability for replay operations

#### [ADR-0042d](../../docs/architecture/decisions/0042d-*.md): 0042D Backpressure

**Components:**

- **Backpressure** → K0BackpressureMonitor
  - File: `k0/sse/backpressure_monitor.py`
  - Detect slow consumers (>10K unACKed events OR >30s lag), track lag time (latest event - last ACK timestamp), emit backpressure metrics

- **Backpressure** → ConsumerDisconnector
  - File: `k0/sse/consumer_disconnector.py`
  - Graceful disconnect with reason (backpressure exceeded), protect K0 from slow consumers, K1 reconnects and catches up via replay

- **Persistence** → WALRetentionManager Cloud
  - File: `k0/wal/retention_manager_cloud.py`
  - Cloud Tier: 7-90 day retention policy (77GB WAL), daily compaction, delete old events (reclaim disk space)

- **Persistence** → WALCompactor
  - File: `k0/wal/compactor.py`
  - Delete old events from K0 WAL, reclaim disk space, efficient storage, optimize replay performance

#### [ADR-0042e](../../docs/architecture/decisions/0042e-*.md): 0042E Device Tiers

**Components:**

- **Device Tiers** → Mobile Storage Tier
  - File: `k1/bridge_k0/sse/device_tiers/mobile.py`
  - 512MB constraint (device deployment), 3-day retention (k0.config), prioritize recent events, aggressive eviction (LRU), cloud-backed replay fallback

- **Device Tiers** → Desktop Storage Tier
  - File: `k1/bridge_k0/sse/device_tiers/desktop.py`
  - 5GB constraint (desktop deployment), 14-day retention, balanced retention policies, moderate eviction

- **Device Tiers** → Cloud Storage Tier
  - File: `k1/bridge_k0/sse/device_tiers/cloud.py`
  - 77GB capacity (cloud deployment), 90-day retention, long retention policies, minimal eviction, full history available


### K1 Core

#### [ADR-0001](../../docs/architecture/decisions/0001-*.md): 0001 Memory Kernel

**Components:**

- **Architecture** → Dual-Kernel
  - File: `contracts/architecture/k0_k1_split.yml`
  - K0 (memory, P01-P20), K1 (intelligence, 52 modules), hybrid architecture, pure actors vs AI agents

#### [ADR-0004](../../docs/architecture/decisions/0004-*.md): 0004 Architecture

**Components:**

- **Architecture** → Layer Definitions
  - File: `contracts/architecture/layer_dependencies.yml`
  - Layer 1-5 structure, 52-module organization, microkernel design, hot path optimization, fault isolation, industry patterns

- **Architecture** → Module Manifest
  - File: `contracts/architecture/module_manifest.yml`
  - 58 modules, 5 layers, module boundaries, single responsibility, component classification, Actor Model

- **Dependencies** → Layer Rules
  - File: `contracts/architecture/layer_dependencies.yml`
  - L1→L5 only, L2→all, L3→L4+L5, L4→L5, L5→none, dependency direction

#### [ADR-0004a](../../docs/architecture/decisions/0004a-*.md): 0004A Event Bus

**Components:**

- **Event Bus** → Layer 1-2 Communication
  - File: `k1/l5_infrastructure/event_bus/event_bus.py`
  - EventBus, Event, EventTopic, pub/sub pattern, async delivery, zero-copy

- **Event Bus** → Event Schemas
  - File: `k1/l5_infrastructure/event_bus/schemas.py`
  - IntentDetected, UserInput, VoiceCommand, BargeIn, event payload, cognitive_trace_id

#### [ADR-0004b](../../docs/architecture/decisions/0004b-*.md): 0004B Dependencies

**Components:**

- **Dependencies** → Import Linting
  - File: `.importlinter`
  - import-linter, layering contracts, pre-commit hooks, CI enforcement, forbidden imports, escape hatches

- **Dependencies** → Layer Rules
  - File: `contracts/architecture/layer_dependencies.yml`
  - L1→L5 only, L2→all, L3→L4+L5, L4→L5, L5→none, dependency direction

#### [ADR-0004d](../../docs/architecture/decisions/0004d-*.md): 0004D Testing

**Components:**

- **Testing** → Integration Tests
  - File: `tests/integration/layer_test_base.py`
  - Layer-specific test suites, WARD framework, contract validation, performance budgets, P95 latency

- **Testing** → Layer 1 Tests
  - File: `tests/integration/layer1/`
  - Event publish, intent classification, stream processing, 3-tier routing, <50ms budget

- **Testing** → Layer 2 Tests
  - File: `tests/integration/layer2/`
  - 3-phase orchestration, planning pipeline, protocol validation, <250ms budget

- **Testing** → Layer 3 Tests
  - File: `tests/integration/layer3/`
  - Agent lifecycle, tool execution, Model Hub, <600ms hire, <3000ms tool call

- **Testing** → Layer 4 Tests
  - File: `tests/integration/layer4/`
  - SessionState serialization, learning loop, saga rollback, <1ms serialize

- **Testing** → Layer 5 Tests
  - File: `tests/integration/layer5/`
  - Event bus delivery, backpressure, thermal placement, <5ms delivery

- **Testing** → End-to-End Tests
  - File: `tests/integration/end_to_end/`
  - User turn, barge-in, multi-agent, <2000ms P95


### K1 Internal Event Bus

#### [ADR-0048](../../docs/architecture/decisions/0048-*.md): 0048 Bus Architecture

**Components:**

- **Bus Architecture** → Event Bus Core
  - File: `k1/l5_infrastructure/event_bus/k1_event_bus.py`
  - In-memory pub/sub, <2ms latency, 1000s events/sec throughput, k1.* namespace

- **Bus Architecture** → Broadcast Pub/Sub
  - File: `k1/l5_infrastructure/event_bus/broadcast.py`
  - 1-to-N fanout, task announcements, FSM transitions, <1ms per event

- **Bus Architecture** → Backpressure Management
  - File: `k1/l5_infrastructure/event_bus/backpressure.py`
  - Mailbox size limits, slow consumer detection (>90% full), graceful degradation

- **K0/K1 Separation** → No K0 Boundary Crossing
  - File: `k1/l5_infrastructure/event_bus/k0_boundary_guard.py`
  - 100% K1-internal, no K0 storage writes, no K0 SSE fanout

- **Performance** → Low Latency
  - File: `k1/l5_infrastructure/event_bus/performance.py`
  - <2ms pub/sub, <1ms mailbox send, no network/serialization overhead

- **Performance** → High Throughput
  - File: `k1/l5_infrastructure/event_bus/throughput.py`
  - 1000s events/sec, high-frequency coordination, no K0 bottleneck

- **Observability** → Prometheus Metrics
  - File: `observability/metrics/k1_event_bus.py`
  - k1_event_bus_published_total, k1_event_bus_latency_ms, k1_event_bus_backpressure_total

- **K0/K1 Separation** → K1 Ephemeral Only
  - File: `docs/architecture/k0_k1_event_separation.md`
  - K1 events ephemeral (no persistence), K0 SSE durable (config, receipts, learning)


### KV Cache Management

#### [ADR-0025](../../docs/architecture/decisions/0025-*.md): 0025 Global Allocator

**Components:**

- **Global Allocator** → Global Budget
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - 512MB device-wide budget, enforce hard limit across all sessions, prevent OOM, <2ms allocation

- **Global Allocator** → Per-Session Min
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - 32MB guaranteed per active session, fairness, prevent starvation, first-come-first-served

- **Global Allocator** → Per-Session Max
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - 256MB cap per session, prevent monopolization, allow growth within limit

- **Global Allocator** → Fragmentation Prevention
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - Track contiguous memory blocks, <3% fragmentation target, defragmentation on high fragmentation

- **Global Allocator** → Allocation Rejection
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - Reject allocation when budget full, trigger eviction, return error to caller

- **Hybrid Eviction** → LRU Component
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - 60% recency weight, evict least recently used sessions, recency_score = (now - last_access) / MAX_AGE

- **Hybrid Eviction** → LFU Component
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - 40% frequency weight, evict least frequently used sessions, frequency_score = 1 / (access_count + 1)

- **Hybrid Eviction** → Eviction Score
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - Combined score = 0.6 *recency + 0.4* frequency, sort by score DESC, <5ms eviction decision

- **Hybrid Eviction** → Eviction Threshold
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - Trigger eviction at 90% full (460MB / 512MB), batch size = 2 sessions, prevent thrashing

- **Hybrid Eviction** → Hit Rate Target
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - >75% cache hit rate after eviction, track hits vs misses, miss penalty = 100-200ms

- **Cache Warming** → Resume Detection
  - File: `k1/l5_infrastructure/kv_cache/cache_warmer.py`
  - Detect session inactive >5 minutes, trigger warming, async prefetch

- **Cache Warming** → Prefetch Strategy
  - File: `k1/l5_infrastructure/kv_cache/cache_warmer.py`
  - Prefetch last 3 turns from K0 WAL, <50ms budget, 30ms K0 query + 15ms KV reconstruction

- **Cache Warming** → Async Warming
  - File: `k1/l5_infrastructure/kv_cache/cache_warmer.py`
  - Background warming (non-blocking), warm before first turn, incremental loading

- **Cache Warming** → Cache Reconstruction
  - File: `k1/l5_infrastructure/kv_cache/cache_warmer.py`
  - Rebuild KV cache from turn context, compute attention tensors, restore session state

- **Compression** → zstd Level 3
  - File: `k1/l5_infrastructure/kv_cache/cache_compressor.py`
  - 70% size reduction (128MB → 38MB), <15ms compression, 200 MB/s throughput

- **Compression** → Compression Trigger
  - File: `k1/l5_infrastructure/kv_cache/cache_compressor.py`
  - Compress sessions inactive >10 minutes, free uncompressed memory (90MB savings), trigger at 85% full

- **Compression** → Decompression
  - File: `k1/l5_infrastructure/kv_cache/cache_compressor.py`
  - On-demand decompression <20ms when session resumes, 500-800 MB/s throughput

- **Compression** → FlatBuffers Serialization
  - File: `k1/l5_infrastructure/kv_cache/cache_compressor.py`
  - Serialize KV tensors to binary format, <5ms serialization, zero-copy deserialization

- **Protection** → Never Evict Tier
  - File: `k1/l5_infrastructure/kv_cache/protection_manager.py`
  - Active turn in progress (user waiting), safety monitoring agent, eviction_score = -∞

- **Protection** → Low Priority Tier
  - File: `k1/l5_infrastructure/kv_cache/protection_manager.py`
  - Recently used (<5 min), frequently used (>10 accesses), eviction_score = 0.0-0.3

- **Protection** → Normal Eviction Tier
  - File: `k1/l5_infrastructure/kv_cache/protection_manager.py`
  - Inactive (5-30 min), moderate use (2-10 accesses), eviction_score = 0.3-0.7

- **Protection** → High Priority Tier
  - File: `k1/l5_infrastructure/kv_cache/protection_manager.py`
  - Inactive >30 min, rarely used (<2 accesses), eviction_score = 0.7-1.0

- **Monitoring** → Hit Rate Tracker
  - File: `k1/l5_infrastructure/kv_cache/hit_rate_monitor.py`
  - Track cache hits vs misses, target >75% hit rate, emit Prometheus metrics

- **Monitoring** → Miss Penalty Tracker
  - File: `k1/l5_infrastructure/kv_cache/hit_rate_monitor.py`
  - Measure latency increase on cache miss (100-200ms penalty), 80-90% slower

- **Monitoring** → Adaptive Tuner
  - File: `k1/l5_infrastructure/kv_cache/adaptive_tuner.py`
  - Adjust eviction weights based on hit rate, 60/40 baseline, tune ±10% based on observed metrics

#### [ADR-0025a](../../docs/architecture/decisions/0025a-*.md): 0025A Global Allocator

**Components:**

- **Global Allocator** → Global Budget
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - 512MB device-wide budget, enforce hard limit across all sessions, prevent OOM, <2ms allocation

- **Global Allocator** → Per-Session Min
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - 32MB guaranteed per active session, fairness, prevent starvation, first-come-first-served

- **Global Allocator** → Per-Session Max
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - 256MB cap per session, prevent monopolization, allow growth within limit

- **Global Allocator** → Fragmentation Prevention
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - Track contiguous memory blocks, <3% fragmentation target, defragmentation on high fragmentation

- **Global Allocator** → Allocation Rejection
  - File: `k1/l5_infrastructure/kv_cache/global_allocator.py`
  - Reject allocation when budget full, trigger eviction, return error to caller

#### [ADR-0025b](../../docs/architecture/decisions/0025b-*.md): 0025B Hybrid Eviction

**Components:**

- **Hybrid Eviction** → LRU Component
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - 60% recency weight, evict least recently used sessions, recency_score = (now - last_access) / MAX_AGE

- **Hybrid Eviction** → LFU Component
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - 40% frequency weight, evict least frequently used sessions, frequency_score = 1 / (access_count + 1)

- **Hybrid Eviction** → Eviction Score
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - Combined score = 0.6 *recency + 0.4* frequency, sort by score DESC, <5ms eviction decision

- **Hybrid Eviction** → Eviction Threshold
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - Trigger eviction at 90% full (460MB / 512MB), batch size = 2 sessions, prevent thrashing

- **Hybrid Eviction** → Hit Rate Target
  - File: `k1/l5_infrastructure/kv_cache/hybrid_eviction_policy.py`
  - >75% cache hit rate after eviction, track hits vs misses, miss penalty = 100-200ms

#### [ADR-0025c](../../docs/architecture/decisions/0025c-*.md): 0025C Cache Warming

**Components:**

- **Cache Warming** → Resume Detection
  - File: `k1/l5_infrastructure/kv_cache/cache_warmer.py`
  - Detect session inactive >5 minutes, trigger warming, async prefetch

- **Cache Warming** → Prefetch Strategy
  - File: `k1/l5_infrastructure/kv_cache/cache_warmer.py`
  - Prefetch last 3 turns from K0 WAL, <50ms budget, 30ms K0 query + 15ms KV reconstruction

- **Cache Warming** → Async Warming
  - File: `k1/l5_infrastructure/kv_cache/cache_warmer.py`
  - Background warming (non-blocking), warm before first turn, incremental loading

- **Cache Warming** → Cache Reconstruction
  - File: `k1/l5_infrastructure/kv_cache/cache_warmer.py`
  - Rebuild KV cache from turn context, compute attention tensors, restore session state

#### [ADR-0025d](../../docs/architecture/decisions/0025d-*.md): 0025D Compression

**Components:**

- **Compression** → zstd Level 3
  - File: `k1/l5_infrastructure/kv_cache/cache_compressor.py`
  - 70% size reduction (128MB → 38MB), <15ms compression, 200 MB/s throughput

- **Compression** → Compression Trigger
  - File: `k1/l5_infrastructure/kv_cache/cache_compressor.py`
  - Compress sessions inactive >10 minutes, free uncompressed memory (90MB savings), trigger at 85% full

- **Compression** → Decompression
  - File: `k1/l5_infrastructure/kv_cache/cache_compressor.py`
  - On-demand decompression <20ms when session resumes, 500-800 MB/s throughput

- **Compression** → FlatBuffers Serialization
  - File: `k1/l5_infrastructure/kv_cache/cache_compressor.py`
  - Serialize KV tensors to binary format, <5ms serialization, zero-copy deserialization

#### [ADR-0025e](../../docs/architecture/decisions/0025e-*.md): 0025E Protection

**Components:**

- **Protection** → Never Evict Tier
  - File: `k1/l5_infrastructure/kv_cache/protection_manager.py`
  - Active turn in progress (user waiting), safety monitoring agent, eviction_score = -∞

- **Protection** → Low Priority Tier
  - File: `k1/l5_infrastructure/kv_cache/protection_manager.py`
  - Recently used (<5 min), frequently used (>10 accesses), eviction_score = 0.0-0.3

- **Protection** → Normal Eviction Tier
  - File: `k1/l5_infrastructure/kv_cache/protection_manager.py`
  - Inactive (5-30 min), moderate use (2-10 accesses), eviction_score = 0.3-0.7

- **Protection** → High Priority Tier
  - File: `k1/l5_infrastructure/kv_cache/protection_manager.py`
  - Inactive >30 min, rarely used (<2 accesses), eviction_score = 0.7-1.0

- **Monitoring** → Hit Rate Tracker
  - File: `k1/l5_infrastructure/kv_cache/hit_rate_monitor.py`
  - Track cache hits vs misses, target >75% hit rate, emit Prometheus metrics

- **Monitoring** → Miss Penalty Tracker
  - File: `k1/l5_infrastructure/kv_cache/hit_rate_monitor.py`
  - Measure latency increase on cache miss (100-200ms penalty), 80-90% slower

- **Monitoring** → Adaptive Tuner
  - File: `k1/l5_infrastructure/kv_cache/adaptive_tuner.py`
  - Adjust eviction weights based on hit rate, 60/40 baseline, tune ±10% based on observed metrics


### Layer 5 Extensibility

#### [ADR-0075](../../docs/architecture/decisions/0075-*.md): 0075 Extension Points

**Components:**

- **Extension Points** → ConfigProvider
  - File: `k1/l5_infrastructure/extensions/config_provider.py`
  - Custom config sources, validation hooks, default merging, environment overrides

- **Extension Points** → MetricsExporter
  - File: `k1/l5_infrastructure/extensions/metrics_exporter.py`
  - Prometheus/StatsD/CloudWatch exporters, custom metrics, aggregation strategies

- **Extension Points** → TraceExporter
  - File: `k1/l5_infrastructure/extensions/trace_exporter.py`
  - OpenTelemetry/Jaeger/Zipkin exporters, span attributes, sampling strategies

- **Extension Points** → LogHandler
  - File: `k1/l5_infrastructure/extensions/log_handler.py`
  - Structured logging, log levels, formatters JSON/plaintext, log rotation

- **Extension Points** → ThermalPolicy
  - File: `k1/l5_infrastructure/extensions/thermal_policy.py`
  - Device thermal state classification, cooling strategies, temperature thresholds, power management

- **Extension Points** → PlacementStrategy
  - File: `k1/l5_infrastructure/extensions/placement_strategy.py`
  - Agent-to-device placement, load balancing, affinity rules, constraint satisfaction

- **Extension Points** → CachePolicy
  - File: `k1/l5_infrastructure/extensions/cache_policy.py`
  - KV cache compression selection, eviction priority, thermal adjustment, memory budget enforcement

- **Extension Points** → BackpressureHandler
  - File: `k1/l5_infrastructure/extensions/backpressure_handler.py`
  - Queue management, flow control, rate limiting, degradation strategies

- **Extension Points** → ErrorInterceptor
  - File: `k1/l5_infrastructure/extensions/error_interceptor.py`
  - Error transformation, circuit breaker integration, retry policies, fallback strategies

- **Extension Points** → HealthCheckProvider
  - File: `k1/l5_infrastructure/extensions/health_check_provider.py`
  - Health check endpoints, dependency checks, liveness/readiness probes, graceful degradation


### Message Queue & Coalescing

#### [ADR-0053](../../docs/architecture/decisions/0053-*.md): 0053 Main

**Components:**

- **Main** → Prometheus Metrics
  - File: `observability/metrics/message_queue.py`
  - queue_depth, messages_coalesced, coalesce_window_duration, rate_limit_rejections, cancellation_latency, burst_tokens_remaining

- **Main** → Research Foundation
  - File: `docs/research/message_queue_research.md`
  - Nagle's Algorithm (TCP 1984), SEDA (2001), Token Bucket, Cooperative Cancellation (Go/Rust), Turn-taking pauses (2-3s)

#### [ADR-0053a](../../docs/architecture/decisions/0053a-*.md): 0053A Coalesce Window

**Components:**

- **Coalesce Window** → Coalescing Efficiency Target
  - File: `observability/metrics/message_queue.py`
  - ≥30% reduction in LLM calls (baseline 40% fragmentation rate), tracked via messages_coalesced / total_messages

- **Coalesce Window** → Window Duration Target
  - File: `observability/metrics/message_queue.py`
  - P50 <1.5s (below 2s limit), users typing naturally, coalesce_window_duration_ms histogram

- **Coalesce Window** → Queue Depth Target
  - File: `observability/metrics/message_queue.py`
  - Average 2.5 messages (below 5 limit), no memory pressure, coalesce_queue_depth gauge per session

- **Coalesce Window** → Bypass Rate Target
  - File: `observability/metrics/message_queue.py`
  - <10% of messages bypass coalescing, bypass_total counter by reason (red_band/explicit_submit/context_switch/voice)

- **Coalesce Window** → Metrics
  - File: `observability/metrics/message_queue.py`
  - messages_coalesced_total, coalesce_window_duration_ms (histogram), coalesce_queue_depth (gauge), bypass_total (counter by reason)

- **Coalesce Window** → Grafana Dashboard
  - File: `observability/dashboards/message_queue.json`
  - Efficiency panel (30% target), window duration (P50 <1.5s), queue depth (<3 average), bypass rate (<10%)

- **Coalesce Window** → Rollout Strategy
  - File: `docs/rollout/message_queue_rollout.md`
  - Week 1 internal testing, Week 2 5% canary, Week 3-4 gradual to 100% (72h soak each stage)

- **Coalesce Window** → Future Work
  - File: `docs/roadmap/coalescing_enhancements.md`
  - Adaptive windows per user typing speed, context-aware coalescing (longer for complex), predictive flush (ML model)

#### [ADR-0053b](../../docs/architecture/decisions/0053b-*.md): 0053B Rate Limits

**Components:**

- **Rate Limits** → Rate Limit Check Latency Target
  - File: `observability/metrics/rate_limiting.py`
  - <1ms P95, no user-visible impact, rate_limit_check_latency_ms histogram (buckets 0.1/0.5/1.0/2.0/5.0)

- **Rate Limits** → Rejection Rate Target
  - File: `observability/metrics/rate_limiting.py`
  - <0.1% of messages rejected, legitimate users unaffected, alert if >1% for >5 minutes

- **Rate Limits** → Bypass Rate Target
  - File: `observability/metrics/rate_limiting.py`
  - <1% of messages bypass rate limit, rate_limit_bypass_total counter by reason (red_band/system/cancellation)

- **Rate Limits** → Metrics
  - File: `observability/metrics/rate_limiting.py`
  - rate_limit_rejections_total (session_id, reason), rate_limit_tokens_remaining (gauge), rate_limit_bypass_total (reason), rate_limit_check_latency_ms

- **Rate Limits** → Future Work
  - File: `docs/roadmap/rate_limiting_enhancements.md`
  - Distributed rate limiting (Redis cross-instance), adaptive per-user limits (fast typers 7 msg/sec), per-tier system (premium/free), smart retry SDK

#### [ADR-0053c](../../docs/architecture/decisions/0053c-*.md): 0053C Cancel Path

**Components:**

- **Cancel Path** → Metrics
  - File: `observability/metrics/cancellation.py`
  - cancellation_latency_ms (histogram P95 ≤120ms), cancellations_total (trigger), cancellation_stage_latency_ms (stage), cancellation_failures_total, resource_cleanup_latency_ms (resource_type)

- **Cancel Path** → K0 Bridge Integration
  - File: `k1/bridge_k0/k0_bridge_client.py`
  - rollback method (WAL transaction abort), pending_writes dict, logger.info k0_rollback (session_id, write_id)

- **Cancel Path** → Future Work
  - File: `docs/roadmap/cancellation_enhancements.md`
  - Predictive cancellation (ML model), partial result preservation (resume interrupted), cancellation batching (reduce overhead), cross-instance cancellation (distributed Redis)


### Module System

#### [ADR-0074](../../docs/architecture/decisions/0074-*.md): 0074 Module Discovery

**Components:**

- **Module Discovery** → ModuleRegistry
  - File: `k1/l5_infrastructure/module_registry.py`
  - metadata.yml discovery, versioning semver, dependency graph validation, <500ms load latency, M2 milestone

- **Module Loading** → ModuleLoader
  - File: `k1/l5_infrastructure/module_loader.py`
  - Dynamic import, isolation boundary, PluginInterface base class, capability binding, hot-reload support


### Multi-Device Family Sync

#### [ADR-0050](../../docs/architecture/decisions/0050-*.md): 0050 Sync Strategy

**Components:**

- **Sync Strategy** → Network-Aware Routing
  - File: `k1/l5_infrastructure/sync/network_aware_router.py`
  - LAN preferred (mDNS discovery), internet fallback (P2P E2EE), automatic detection

- **Observability** → Sync Metrics
  - File: `observability/metrics/multi_device_sync.py`
  - device_discovery_time_ms, sync_latency_ms (LAN/Internet), crdt_conflicts_total, merge_duration_ms

- **Sync Strategy** → Hybrid Strategy
  - File: `docs/architecture/multi_device_sync_strategy.md`
  - Phase 1 (LAN <1ms), Phase 2 (Internet <500ms), device-first privacy

- **Sync Strategy** → Device Autonomy
  - File: `docs/architecture/device_autonomy.md`
  - Each device runs K0+K1 full dual-kernel, no cloud intermediary, privacy-first

#### [ADR-0050a](../../docs/architecture/decisions/0050a-*.md): 0050A SessionState Coherence

**Components:**

- **SessionState Coherence** → Bounded Staleness
  - File: `k1/bridge_k0/bounded_staleness.py`
  - K0 Bridge mirrors in-memory state within 250ms P95, 500ms P99, propagation target

#### [ADR-0050b](../../docs/architecture/decisions/0050b-*.md): 0050B CRDT Merge

**Components:**

- **CRDT Merge** → Last-Write-Wins
  - File: `k1/l5_infrastructure/sync/crdt_lww.py`
  - LWW conflict resolution, device ID ordering (ipad < iphone < laptop), deterministic merge

- **CRDT Merge** → Vector Clock
  - File: `k1/l5_infrastructure/sync/vector_clock.py`
  - Causal ordering per device, detect concurrent writes, <10ms merge latency

- **CRDT Merge** → Conflict Detection
  - File: `k1/l5_infrastructure/sync/conflict_detector.py`
  - Same timestamp detection, device ID tiebreaker, convergence guarantee

#### [ADR-0050c](../../docs/architecture/decisions/0050c-*.md): 0050C Phase 1 LAN Sync

**Components:**

- **Phase 1 LAN Sync** → mDNS Discovery
  - File: `k1/l5_infrastructure/sync/mdns_discovery.py`
  - Zeroconf service announcement (familyos-{device-id}._tcp.local), <100ms discovery

- **Phase 1 LAN Sync** → TCP Peer Connection
  - File: `k1/l5_infrastructure/sync/tcp_peer.py`
  - Direct device-to-device TCP over LAN, P07 channel, <1ms latency

- **Phase 1 LAN Sync** → LAN Broadcast
  - File: `k1/l5_infrastructure/sync/lan_broadcast.py`
  - K0 Bridge P07 broadcast changes, <50ms fanout to 6-10 devices

#### [ADR-0050d](../../docs/architecture/decisions/0050d-*.md): 0050D Phase 2 Internet Sync

**Components:**

- **Phase 2 Internet Sync** → Device Certificates
  - File: `k1/l5_infrastructure/sync/device_certificates.py`
  - Ed25519 signing + X25519 encryption, E2EE per device, 90-day rotation

- **Phase 2 Internet Sync** → P2P E2EE Tunnel
  - File: `k1/l5_infrastructure/sync/p2p_tunnel.py`
  - Encrypted device-to-device tunnel, <500ms P95 internet latency, no intermediary

- **Phase 2 Internet Sync** → NAT Traversal
  - File: `k1/l5_infrastructure/sync/nat_traversal.py`
  - Automatic firewall/NAT handling, STUN/TURN fallback if needed


### Multi-Tier Storage

#### [ADR-0020](../../docs/architecture/decisions/0020-*.md): 0020 Storage Architecture

**Components:**

- **Storage Architecture** → 3-Tier Strategy
  - File: `k1/l5_infrastructure/storage/tier_manager.py`
  - Hot (RAM <1ms), Warm (SSD <50ms), Cold (S3 <500ms), automatic lifecycle, 160× cost reduction

- **Storage Architecture** → Memory Budgets
  - File: `k1/l5_infrastructure/storage/tier_manager.py`
  - Hot 56MB (1000 sessions), Warm 100MB (2000 sessions 30 days), Cold unlimited (years), per-tier quotas

- **Storage Architecture** → Tier Coordinator
  - File: `k1/l5_infrastructure/storage/tier_manager.py`
  - Transparent tier selection, fallback chain (Hot → Warm → Cold), cache invalidation, <0.1ms routing

- **Storage Architecture** → Performance Targets
  - File: `k1/l5_infrastructure/storage/tier_manager.py`
  - Hot <1ms, Warm <50ms, Cold <500ms, TTFT <150ms budget, E2E <2000ms budget

- **Storage Architecture** → Cost Optimization
  - File: `k1/l5_infrastructure/storage/tier_manager.py`
  - $0.52/month vs $84/month RAM-only (99.4% cheaper), Hot $4.80, Warm $0.01, Cold $0.08 per 1000 sessions

- **Lifecycle Management** → Automatic Tiering
  - File: `k1/l5_infrastructure/storage/lifecycle_manager.py`
  - No manual intervention, lifecycle policies (60min/30day/1year), background tasks, policy engine

- **Lifecycle Management** → Transparent Retrieval
  - File: `k1/l5_infrastructure/storage/tier_manager.py`
  - K1 queries abstraction, tier routing (Hot → Warm → Cold fallback), <0.1ms routing overhead

- **Observability** → Prometheus Metrics
  - File: `observability/metrics/storage_tiering.py`
  - storage_access_total (by tier), storage_access_duration_ms, storage_cost_usd, tier_capacity_bytes

- **Observability** → Grafana Dashboard
  - File: `observability/dashboards/storage_tiering.json`
  - Tier capacity, access latency P95, migration frequency, cost breakdown, cache hit rate

- **Observability** → Cache Hit Rate
  - File: `observability/metrics/storage_tiering.py`
  - Hot 96% (active sessions), Warm 3.8% (recent turns), Cold 0.2% (historical), optimal distribution

#### [ADR-0020b](../../docs/architecture/decisions/0020b-*.md): 0020B Warm Tier (L2 SSD)

**Components:**

- **Warm Tier (L2 SSD)** → K0Bridge Integration
  - File: `k1/bridge_k0/k0_bridge.py`
  - HTTP/2 query_wal(session_id), retrieve deltas, <15ms P95 SSD I/O, FlatBuffers deserialization


### Observability

#### [ADR-0002d](../../docs/architecture/decisions/0002d-*.md): 0002D Metrics

**Components:**

- **Metrics** → Prometheus Exporter
  - File: `observability/metrics.py`
  - 20+ metrics, mailbox depth, crashes, admissions, service time, blacklist

- **Tracing** → OpenTelemetry Spans
  - File: `observability/tracing.py`
  - actor.send/recv, router.admission, mailbox.enq/deq, 1% sampling, cognitive_trace_id

- **Logging** → Structured Logs
  - File: `observability/logging.py`
  - JSON format, 6 event types, cognitive_trace_id propagation, <10MB/hour

- **Dashboards** → Grafana Dashboards
  - File: `observability/dashboards/`
  - 4 dashboards (Mailbox Health, Admission Control, Supervisor, Message Flow)

- **Alerting** → Prometheus Alerts
  - File: `observability/alerts.yml`
  - 9 alerts (MailboxDepthHigh, CrashRateHigh, RateLimitHitsHigh, DLQFull, TTLExpiredHigh)


### OpenAPI 3.1 Specs

#### [ADR-0047](../../docs/architecture/decisions/0047-*.md): 0047 SDK Generation

**Components:**

- **SDK Generation** → OpenAPI Generator Config
  - File: `.openapi-generator/config.yml`
  - TypeScript (typescript-axios), Python (python), Go (go), package names, output dirs

- **SDK Generation** → TypeScript SDK
  - File: `sdks/typescript/`
  - Auto-generated from openapi.json, axios HTTP client, type-safe interfaces

- **SDK Generation** → Python SDK
  - File: `sdks/python/`
  - Auto-generated from openapi.json, requests HTTP client, type hints

- **SDK Generation** → Go SDK
  - File: `sdks/go/`
  - Auto-generated from openapi.json, net/http client, struct definitions

- **Security Schemes** → Bearer JWT
  - File: `k1/api/rest/security.py`
  - bearerAuth security scheme, Authorization header, JWT format, token validation

- **CI/CD** → OpenAPI Validation
  - File: `.github/workflows/openapi-validation.yml`
  - swagger-validator-action, validate spec on push/PR, fail if invalid schema

- **CI/CD** → SDK Generation Test
  - File: `.github/workflows/openapi-validation.yml`
  - Generate TypeScript SDK, test compilation, ensure SDK builds without errors


### PII Detection

#### [ADR-0035](../../docs/architecture/decisions/0035-*.md): 0035 Hybrid Detection

**Components:**

- **Hybrid Detection** → Regex + ML Combined
  - File: `k1/l5_infrastructure/privacy/hybrid_detector.py`
  - Regex first (structured PII, 85% recall, <1ms), ML second (unstructured PII, +10% recall, <5ms), 95% total recall, <5ms total overhead

- **Hybrid Detection** → False Positives
  - File: `k1/l5_infrastructure/privacy/hybrid_detector.py`
  - <1% false positives, 99% precision, Validation logic (Luhn algorithm for credit cards, checksum for others)

- **Redaction** → Placeholder Replacement
  - File: `k1/l5_infrastructure/privacy/redactor.py`
  - Replace PII with placeholders ([SSN], [CREDIT_CARD], [EMAIL], [PHONE]), 100% PII removal from SessionState/LLM/logs

- **Redaction** → Defense in Depth
  - File: `k1/l5_infrastructure/privacy/redactor.py`
  - Filter in K1 (Layer 5), Vault in K0 (Layer 2), No plaintext PII in SessionState/LLM prompts/observability logs

- **Integration** → Privacy Bands
  - File: `k1/l5_infrastructure/privacy/privacy_bands.py`
  - AMBER band PII masking enforcement (ties to ADR-0032 Egress Control), 100% PII protection in logs/SessionState/LLM prompts

- **Integration** → Real-Time Filtering
  - File: `k1/l5_infrastructure/privacy/filter.py`
  - <5ms detection overhead per request, Async processing (no blocking LLM call), Batch processing (detect multiple PII types in single pass)

#### [ADR-0035a](../../docs/architecture/decisions/0035a-*.md): 0035A Regex Patterns

**Components:**

- **Regex Patterns** → SSN Pattern
  - File: `k1/l5_infrastructure/privacy/regex_patterns.py`
  - \d{3}-\d{2}-\d{4} format, 100% precision, <1ms detection, Precompiled at startup

- **Regex Patterns** → Email Pattern
  - File: `k1/l5_infrastructure/privacy/regex_patterns.py`
  - RFC5322 compliance, 100% precision, <1ms detection, Handles complex formats

- **Regex Patterns** → Phone Pattern
  - File: `k1/l5_infrastructure/privacy/regex_patterns.py`
  - E.164 international format, (555) 123-4567 US format, <1ms detection

- **Regex Patterns** → Credit Card Pattern
  - File: `k1/l5_infrastructure/privacy/regex_patterns.py`
  - Luhn algorithm validation, Visa/MasterCard/Amex/Discover support, <1ms detection

- **Regex Patterns** → 12 Structured Patterns
  - File: `k1/l5_infrastructure/privacy/regex_patterns.py`
  - SSN/email/phone/credit card/address/IP/driver license/passport/IBAN/MAC/insurance/tax ID, 85% recall, 100% precision with validation

- **Regex Patterns** → Performance
  - File: `k1/l5_infrastructure/privacy/regex_patterns.py`
  - <1ms per pattern, Precompiled at startup (lazy_static/once_cell), Zero runtime overhead

#### [ADR-0035b](../../docs/architecture/decisions/0035b-*.md): 0035B ML-based NER

**Components:**

- **ML-based NER** → BERT-NER Model
  - File: `k1/l5_infrastructure/privacy/bert_ner.py`
  - 110M parameters, ONNX Runtime, INT8 quantization (4× speedup), <5ms inference, <100MB memory footprint

- **ML-based NER** → BIO Tagging
  - File: `k1/l5_infrastructure/privacy/bert_ner.py`
  - CoNLL-2003 benchmark, B-PERSON (begin), I-PERSON (inside), O (outside), 92.8% F1-score

- **ML-based NER** → Unstructured PII Detection
  - File: `k1/l5_infrastructure/privacy/bert_ner.py`
  - Names (John Doe), Addresses (123 Main St), Organizations (Acme Corp), 95% recall, 99% precision

- **ML-based NER** → Confidence Threshold
  - File: `k1/l5_infrastructure/privacy/bert_ner.py`
  - 0.8 configurable per PII type, Post-processing merges adjacent tokens (B-PERSON + I-PERSON → full name)

- **ML-based NER** → Performance
  - File: `k1/l5_infrastructure/privacy/bert_ner.py`
  - <5ms NER inference, <500ms model loading at startup, ONNX optimized kernels


### Performance Budgets

#### [ADR-0024](../../docs/architecture/decisions/0024-*.md): 0024 Turn-Level Budgets

**Components:**

- **Turn-Level Budgets** → TTFT Target
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - Time to First Token <150ms P95, ASR 80ms + intent 50ms + orchestrator 20ms, user perceives instant

- **Turn-Level Budgets** → E2E Turn Target
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - End-to-end <2000ms P95, TTFT 150ms + inference 1500ms + TTS 300ms + playback 50ms

- **Turn-Level Budgets** → Barge-In Target
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - Cancel latency <120ms P95, cancel signal 20ms + stop inference 50ms + stop TTS 30ms + stop audio 20ms

- **Turn-Level Budgets** → Cold Start Target
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - Agent hire → first token <500ms P95, includes agent WARMING → ACTIVE transition

- **Turn-Level Budgets** → Budget Decomposition
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - Composable budgets, E2E = sum of component budgets, hierarchical tracking

- **Component-Level Budgets** → Config Reload
  - File: `k1/l5_infrastructure/config/reload.py`
  - <100ms P95 budget, hot-reload YAML, 200ms timeout, atomic updates

- **Memory Budgets** → K1 Total Memory
  - File: `k1/l5_infrastructure/performance/memory_budget_tracker.py`
  - <500MB P95 budget, OS + Python runtime ~180MB, 480MB OOM threshold (96%)

- **Energy Budgets** → CPU Idle Target
  - File: `k1/l5_infrastructure/performance/energy_tracker.py`
  - <10% CPU utilization when idle, background processing throttled

- **Energy Budgets** → CPU Speech Target
  - File: `k1/l5_infrastructure/performance/energy_tracker.py`
  - <35% CPU utilization during speech processing, ASR + TTS load

- **Energy Budgets** → Wakeup Rate Limit
  - File: `k1/l5_infrastructure/performance/energy_tracker.py`
  - <10 wakeups/min, voice activity detection throttling, battery awareness

- **Enforcement** → PerformanceBudgetEnforcer
  - File: `k1/l5_infrastructure/performance/enforcer.py`
  - Track latency, BudgetResult dataclass, BudgetStatus enum, deadline tracking

- **Enforcement** → Budget Warnings
  - File: `k1/l5_infrastructure/performance/enforcer.py`
  - >80% budget → warning log, >105% budget → alert, early warning system

- **Enforcement** → Timeout Enforcement
  - File: `k1/l5_infrastructure/performance/enforcer.py`
  - Cancel operations exceeding timeout, return partial results, prevent cascading delays

- **Enforcement** → Alert Rules
  - File: `observability/prometheus/alerts.yml`
  - Prometheus alerts when P95 exceeds 105% of budget, alert manager integration

- **Monitoring** → Prometheus Metrics
  - File: `observability/metrics.py`
  - Histograms for TTFT, E2E, component latencies, P50/P95/P99 quantiles

- **Monitoring** → Grafana Dashboard
  - File: `observability/dashboards/performance_budgets.json`
  - Visualization of all budgets, trend analysis, budget violations

- **Monitoring** → Trace Integration
  - File: `k1/l5_infrastructure/observability/tracing.py`
  - cognitive_trace_id for end-to-end tracking, OpenTelemetry spans

- **Graceful Degradation** → Degradation Manager
  - File: `k1/l5_infrastructure/performance/degradation_manager.py`
  - DegradationLevel enum (GREEN/AMBER/RED/CRITICAL), adaptive policies, auto-enable

- **Graceful Degradation** → Recovery Policy
  - File: `k1/l5_infrastructure/performance/degradation_manager.py`
  - Resume normal when P95 <157ms for 2 minutes, hysteresis, prevent flapping

#### [ADR-0024a](../../docs/architecture/decisions/0024a-*.md): 0024A Turn-Level Budgets

**Components:**

- **Turn-Level Budgets** → TTFT Target
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - Time to First Token <150ms P95, ASR 80ms + intent 50ms + orchestrator 20ms, user perceives instant

- **Turn-Level Budgets** → E2E Turn Target
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - End-to-end <2000ms P95, TTFT 150ms + inference 1500ms + TTS 300ms + playback 50ms

- **Turn-Level Budgets** → Barge-In Target
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - Cancel latency <120ms P95, cancel signal 20ms + stop inference 50ms + stop TTS 30ms + stop audio 20ms

- **Turn-Level Budgets** → Cold Start Target
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - Agent hire → first token <500ms P95, includes agent WARMING → ACTIVE transition

- **Turn-Level Budgets** → Budget Decomposition
  - File: `k1/l5_infrastructure/performance/budget_tracker.py`
  - Composable budgets, E2E = sum of component budgets, hierarchical tracking

- **Enforcement** → Alert Rules
  - File: `observability/prometheus/alerts.yml`
  - Prometheus alerts when P95 exceeds 105% of budget, alert manager integration

#### [ADR-0024b](../../docs/architecture/decisions/0024b-*.md): 0024B Component-Level Budgets

**Components:**

- **Component-Level Budgets** → Config Reload
  - File: `k1/l5_infrastructure/config/reload.py`
  - <100ms P95 budget, hot-reload YAML, 200ms timeout, atomic updates

- **Enforcement** → Timeout Enforcement
  - File: `k1/l5_infrastructure/performance/enforcer.py`
  - Cancel operations exceeding timeout, return partial results, prevent cascading delays

#### [ADR-0024c](../../docs/architecture/decisions/0024c-*.md): 0024C Memory Budgets

**Components:**

- **Memory Budgets** → K1 Total Memory
  - File: `k1/l5_infrastructure/performance/memory_budget_tracker.py`
  - <500MB P95 budget, OS + Python runtime ~180MB, 480MB OOM threshold (96%)

- **Energy Budgets** → CPU Idle Target
  - File: `k1/l5_infrastructure/performance/energy_tracker.py`
  - <10% CPU utilization when idle, background processing throttled

- **Energy Budgets** → CPU Speech Target
  - File: `k1/l5_infrastructure/performance/energy_tracker.py`
  - <35% CPU utilization during speech processing, ASR + TTS load

- **Energy Budgets** → Wakeup Rate Limit
  - File: `k1/l5_infrastructure/performance/energy_tracker.py`
  - <10 wakeups/min, voice activity detection throttling, battery awareness

#### [ADR-0024d](../../docs/architecture/decisions/0024d-*.md): 0024D Graceful Degradation

**Components:**

- **Graceful Degradation** → Degradation Manager
  - File: `k1/l5_infrastructure/performance/degradation_manager.py`
  - DegradationLevel enum (GREEN/AMBER/RED/CRITICAL), adaptive policies, auto-enable

- **Graceful Degradation** → Recovery Policy
  - File: `k1/l5_infrastructure/performance/degradation_manager.py`
  - Resume normal when P95 <157ms for 2 minutes, hysteresis, prevent flapping


### Prometheus Metrics

#### [ADR-0029](../../docs/architecture/decisions/0029-*.md): 0029 RED Method

**Components:**

- **RED Method** → Rate Metrics
  - File: `observability/prometheus/red_metrics.py`
  - Requests per second (15 rate counters), Counter type (monotonic), Requests_total suffix, Rate() Prometheus query

- **RED Method** → Error Metrics
  - File: `observability/prometheus/red_metrics.py`
  - Errors per second (15 error counters), Counter type (cumulative), Errors_total suffix, Error rate calculation

- **RED Method** → Duration Metrics
  - File: `observability/prometheus/red_metrics.py`
  - P50/P95/P99 latency (15 histogram metrics), Histogram type (percentiles), Duration_seconds suffix, Server-side quantiles

- **RED Method** → Metric Naming
  - File: `observability/prometheus/schema.py`
  - Component_metric_unit format, Standardized units (ms/s/total/rate), Label standards (component/status/error_type), High cardinality prevention

- **Infrastructure** → Thermal Metrics
  - File: `k1/l5_infrastructure/thermal/thermal_metrics.py`
  - Thermal_state gauge (0-4: COOL/WARM/HOT/CRITICAL/EMERGENCY), Thermal_temperature_celsius (NPU/GPU/CPU), Thermal_throttling_events_total, Thermal_placement_decisions_total (NPU/GPU/CPU/Remote)

- **Infrastructure** → CPU Metrics
  - File: `k1/l5_infrastructure/system_monitor/cpu_metrics.py`
  - Cpu_utilization_percent gauge (90% budget), Per-core utilization tracking, CPU throttling detection, Process CPU usage

- **Infrastructure** → Cost Metrics
  - File: `k1/l5_infrastructure/cost_tracker/cost_metrics.py`
  - Cost_per_turn_usd histogram ($0.10 soft/$0.20 hard budget), Cost_budget_exceeded_total counter, Per-token cost tracking, Monthly burn rate calculation

- **Alerting** → SLO Alerts
  - File: `observability/prometheus/alerts/slo_alerts.yml`
  - 10 alert rule groups (Turn/Agent/Orchestrator/Planner/Tool/KV Cache/Thermal/Memory/Cost/Synthetic), TTFT >157ms P95, E2E >2100ms P95, Error rate >1%, PagerDuty (CRITICAL), Slack (WARNING)

- **Alerting** → Alert Routing
  - File: `observability/prometheus/alerts/routing.yml`
  - Severity routing (CRITICAL→PagerDuty, WARNING→Slack, INFO→Grafana annotations), Response time SLAs (immediate/30min/logged), Escalation policy (15min→manager, 1hr→critical upgrade)

- **Dashboards** → Turn Overview Dashboard
  - File: `observability/grafana/dashboards/turn_overview.json`
  - 12 panels (TTFT/E2E histograms, error rate, success rate, barge-in latency), User experience visualization, SLO compliance tracking, Real-time turn metrics

- **Dashboards** → Component Health Dashboard
  - File: `observability/grafana/dashboards/component_health.json`
  - 18 panels (Agent states, orchestration phases, planner validation, tool execution), FSM state visualization, Component latency tracking, Error drill-down

- **Dashboards** → Infrastructure Dashboard
  - File: `observability/grafana/dashboards/infrastructure.json`
  - 15 panels (KV cache hit rate/size, thermal states, memory usage, CPU utilization), Resource capacity tracking, Thermal placement visualization, Cost burn rate

- **Dashboards** → Incident Response Dashboard
  - File: `observability/grafana/dashboards/incident_response.json`
  - 5 panels (Active alerts, recent traces, error logs, runbook links), Root cause analysis, Trace correlation, Runbook automation

- **Export** → Prometheus Endpoint
  - File: `observability/prometheus/exporter.py`
  - HTTP scrape endpoint (<http://localhost:9090/metrics>), 15s scrape interval, <10ms scrape latency, <1MB payload size, <1000 time series per metric

- **Export** → Histogram Buckets
  - File: `observability/prometheus/buckets.py`
  - Latency buckets (10/50/100/150/250/500/1000/2000/5000ms), Size buckets (1KB/10KB/64KB/256KB/1MB/10MB), Custom bucket configuration, Budget-aligned buckets

- **Integration** → USE Method
  - File: `observability/prometheus/use_metrics.py`
  - Utilization metrics (CPU/memory/queue %), Saturation metrics (queue depth/backlog), Errors (resource errors), Infrastructure-focused complement to RED

- **Integration** → OpenTelemetry
  - File: `observability/otel/metrics_bridge.py`
  - OTLP metrics export, Semantic conventions compliance, Vendor-neutral metrics, Integration with Prometheus/Grafana/Jaeger

#### [ADR-0029a](../../docs/architecture/decisions/0029a-*.md): 0029A RED Method

**Components:**

- **RED Method** → Rate Metrics
  - File: `observability/prometheus/red_metrics.py`
  - Requests per second (15 rate counters), Counter type (monotonic), Requests_total suffix, Rate() Prometheus query

- **RED Method** → Error Metrics
  - File: `observability/prometheus/red_metrics.py`
  - Errors per second (15 error counters), Counter type (cumulative), Errors_total suffix, Error rate calculation

- **RED Method** → Duration Metrics
  - File: `observability/prometheus/red_metrics.py`
  - P50/P95/P99 latency (15 histogram metrics), Histogram type (percentiles), Duration_seconds suffix, Server-side quantiles

- **RED Method** → Metric Naming
  - File: `observability/prometheus/schema.py`
  - Component_metric_unit format, Standardized units (ms/s/total/rate), Label standards (component/status/error_type), High cardinality prevention

- **Export** → Histogram Buckets
  - File: `observability/prometheus/buckets.py`
  - Latency buckets (10/50/100/150/250/500/1000/2000/5000ms), Size buckets (1KB/10KB/64KB/256KB/1MB/10MB), Custom bucket configuration, Budget-aligned buckets

#### [ADR-0029d](../../docs/architecture/decisions/0029d-*.md): 0029D Infrastructure

**Components:**

- **Infrastructure** → Thermal Metrics
  - File: `k1/l5_infrastructure/thermal/thermal_metrics.py`
  - Thermal_state gauge (0-4: COOL/WARM/HOT/CRITICAL/EMERGENCY), Thermal_temperature_celsius (NPU/GPU/CPU), Thermal_throttling_events_total, Thermal_placement_decisions_total (NPU/GPU/CPU/Remote)

- **Infrastructure** → CPU Metrics
  - File: `k1/l5_infrastructure/system_monitor/cpu_metrics.py`
  - Cpu_utilization_percent gauge (90% budget), Per-core utilization tracking, CPU throttling detection, Process CPU usage

- **Infrastructure** → Cost Metrics
  - File: `k1/l5_infrastructure/cost_tracker/cost_metrics.py`
  - Cost_per_turn_usd histogram ($0.10 soft/$0.20 hard budget), Cost_budget_exceeded_total counter, Per-token cost tracking, Monthly burn rate calculation

- **Integration** → USE Method
  - File: `observability/prometheus/use_metrics.py`
  - Utilization metrics (CPU/memory/queue %), Saturation metrics (queue depth/backlog), Errors (resource errors), Infrastructure-focused complement to RED

#### [ADR-0029e](../../docs/architecture/decisions/0029e-*.md): 0029E Alerting

**Components:**

- **Alerting** → SLO Alerts
  - File: `observability/prometheus/alerts/slo_alerts.yml`
  - 10 alert rule groups (Turn/Agent/Orchestrator/Planner/Tool/KV Cache/Thermal/Memory/Cost/Synthetic), TTFT >157ms P95, E2E >2100ms P95, Error rate >1%, PagerDuty (CRITICAL), Slack (WARNING)

- **Alerting** → Alert Routing
  - File: `observability/prometheus/alerts/routing.yml`
  - Severity routing (CRITICAL→PagerDuty, WARNING→Slack, INFO→Grafana annotations), Response time SLAs (immediate/30min/logged), Escalation policy (15min→manager, 1hr→critical upgrade)

- **Dashboards** → Turn Overview Dashboard
  - File: `observability/grafana/dashboards/turn_overview.json`
  - 12 panels (TTFT/E2E histograms, error rate, success rate, barge-in latency), User experience visualization, SLO compliance tracking, Real-time turn metrics

- **Dashboards** → Component Health Dashboard
  - File: `observability/grafana/dashboards/component_health.json`
  - 18 panels (Agent states, orchestration phases, planner validation, tool execution), FSM state visualization, Component latency tracking, Error drill-down

- **Dashboards** → Infrastructure Dashboard
  - File: `observability/grafana/dashboards/infrastructure.json`
  - 15 panels (KV cache hit rate/size, thermal states, memory usage, CPU utilization), Resource capacity tracking, Thermal placement visualization, Cost burn rate

- **Dashboards** → Incident Response Dashboard
  - File: `observability/grafana/dashboards/incident_response.json`
  - 5 panels (Active alerts, recent traces, error logs, runbook links), Root cause analysis, Trace correlation, Runbook automation


### REST API Dual Format

#### [ADR-0014a](../../docs/architecture/decisions/0014a-*.md): 0014A Content Negotiation

**Components:**

- **Content Negotiation** → Format Metrics
  - File: `observability/metrics/content_negotiation.py`
  - content_negotiation_format_total{format, endpoint}, FlatBuffers adoption %

#### [ADR-0014b](../../docs/architecture/decisions/0014b-*.md): 0014B OpenAPI Generation

**Components:**

- **OpenAPI Generation** → FlatBuffers Parser
  - File: `tools/flatbuffers_parser.py`
  - Parse .fbs files, extract tables/enums/unions, regex-based parsing

- **OpenAPI Generation** → JSON Schema Mapper
  - File: `tools/json_schema_mapper.py`
  - FlatBuffers types → JSON Schema types, union → oneOf discriminator, 100% coverage

- **OpenAPI Generation** → OpenAPI 3.1 Spec
  - File: `api/openapi.json`
  - 8,450 lines auto-generated, 40 REST API schemas, paths + schemas + examples

- **OpenAPI Generation** → CI/CD Validation
  - File: `scripts/validate_openapi_spec.py`
  - Fail build if spec out of sync with schemas, <30s generation, 100% accuracy

#### [ADR-0014d](../../docs/architecture/decisions/0014d-*.md): 0014D Client SDKs

**Components:**

- **Client SDKs** → Python SDK (JSON)
  - File: `sdk/python/k1_client.py`
  - K1Client class, requests library, create_session/start_turn/recall/invoke_tool methods

- **Client SDKs** → Python SDK (FlatBuffers)
  - File: `sdk/python/k1_client_fb.py`
  - K1ClientFlatBuffers class, zero-copy deserialization, 50-100ms faster vs JSON

- **Client SDKs** → TypeScript SDK (JSON)
  - File: `sdk/typescript/k1-client.ts`
  - K1Client class, fetch API, browser + Node.js compatible, type-safe interfaces

- **Client SDKs** → TypeScript SDK (FlatBuffers)
  - File: `sdk/typescript/k1-client-fb.ts`
  - FlatBuffers npm package, Buffer serialization, axios for Node.js

- **Client SDKs** → curl Examples
  - File: `docs/api/curl_examples.md`
  - All 20 REST endpoints, JSON payloads, copy-paste ready, Accept/Content-Type headers

- **Client SDKs** → Migration Guide
  - File: `docs/api/MIGRATION_GUIDE.md`
  - When to use FlatBuffers, performance benchmarks (JSON 50ms vs FlatBuffers 5ms), trade-offs

- **Client SDKs** → Postman Collection
  - File: `api/postman_collection.json`
  - Auto-generated from OpenAPI spec, 20 endpoints, environment variables, examples

- **Client SDKs** → Performance Benchmarks
  - File: `benchmarks/json_vs_flatbuffers.py`
  - 1KB-10KB payloads, latency/size comparison, 50-100ms JSON vs 5-10ms FlatBuffers


### SSE Event Schemas

#### [ADR-0016](../../docs/architecture/decisions/0016-*.md): 0016 Event Taxonomy

**Components:**

- **Event Taxonomy** → Event Types
  - File: `k1/schemas/sse/event_envelope.fbs`
  - 17 event types, 5 categories, EventEnvelope, EventPayload union

- **Event Taxonomy** → Agent Lifecycle Events
  - File: `k1/schemas/sse/agent_events.fbs`
  - AgentHired, AgentFired, AgentCrashed, AgentRestarted (4 events)

- **Event Taxonomy** → Turn Events
  - File: `k1/schemas/sse/turn_events.fbs`
  - TurnStarted, TurnCompleted, TurnFailed, TurnInterrupted (4 events)

- **Event Taxonomy** → Tool Events
  - File: `k1/schemas/sse/tool_events.fbs`
  - ToolCallStarted, ToolCallCompleted, ToolCallFailed, ToolApprovalRequired (4 events)

- **Event Taxonomy** → Session Events
  - File: `k1/schemas/sse/session_events.fbs`
  - SessionCreated, SessionTerminated, SessionCrashed (3 events)

- **Event Taxonomy** → System Events
  - File: `k1/schemas/sse/system_events.fbs`
  - Heartbeat, Error (2 events, keepalive + notifications)

#### [ADR-0016a](../../docs/architecture/decisions/0016a-*.md): 0016A Event Taxonomy

**Components:**

- **Event Taxonomy** → Event Types
  - File: `k1/schemas/sse/event_envelope.fbs`
  - 17 event types, 5 categories, EventEnvelope, EventPayload union

- **Event Taxonomy** → Agent Lifecycle Events
  - File: `k1/schemas/sse/agent_events.fbs`
  - AgentHired, AgentFired, AgentCrashed, AgentRestarted (4 events)

- **Event Taxonomy** → Turn Events
  - File: `k1/schemas/sse/turn_events.fbs`
  - TurnStarted, TurnCompleted, TurnFailed, TurnInterrupted (4 events)

- **Event Taxonomy** → Tool Events
  - File: `k1/schemas/sse/tool_events.fbs`
  - ToolCallStarted, ToolCallCompleted, ToolCallFailed, ToolApprovalRequired (4 events)

- **Event Taxonomy** → Session Events
  - File: `k1/schemas/sse/session_events.fbs`
  - SessionCreated, SessionTerminated, SessionCrashed (3 events)

- **Event Taxonomy** → System Events
  - File: `k1/schemas/sse/system_events.fbs`
  - Heartbeat, Error (2 events, keepalive + notifications)

#### [ADR-0016c](../../docs/architecture/decisions/0016c-*.md): 0016C Filtering

**Components:**

- **Filtering** → Event Bus
  - File: `k1/l5_infrastructure/event_bus/sse_event_bus.py`
  - EventBus, pub/sub, server-side filtering, asyncio.Queue

- **Filtering** → Event Subscriber
  - File: `k1/l5_infrastructure/event_bus/event_subscriber.py`
  - EventSubscriber, topic+session filters, queue maxsize=1000

- **Filtering** → Topic Mappings
  - File: `k1/config/sse_topics.yml`
  - 5 topics (agent_lifecycle, turn_execution, tool_execution, session_lifecycle, system_health)

- **Filtering** → Bandwidth Savings
  - File: `docs/architecture/sse_bandwidth_analysis.md`
  - 60-70% savings with topic filtering, all topics 6.5KB → filtered 2.2KB

#### [ADR-0016d](../../docs/architecture/decisions/0016d-*.md): 0016D Browser Integration

**Components:**

- **Browser Integration** → Native EventSource
  - File: `docs/api/sse_examples/vanilla_js.js`
  - Vanilla JS, browser-native, auto-reconnect, no SDK, Last-Event-ID

- **Browser Integration** → React Hook
  - File: `sdk/typescript/use_sse_events.ts`
  - useSSEEvents hook, connection state, onEvent callback, useEffect cleanup

- **Browser Integration** → TypeScript SDK
  - File: `sdk/typescript/k1_sse_client.ts`
  - K1SSEClient, Node.js eventsource polyfill, auth headers, reconnect

- **Browser Integration** → Connection State
  - File: `sdk/typescript/connection_state.ts`
  - CONNECTING/CONNECTED/DISCONNECTED/CLOSED, exponential backoff 3s→30s


### SSE Topic Taxonomy

#### [ADR-0043](../../docs/architecture/decisions/0043-*.md): 0043 K0 Durable Topics

**Components:**

- **K0 Durable Topics** → Config Hot-Reload
  - File: `k1/bridge_k0/sse/topics/config.py`
  - k0.config.* topics (config.changed, config.hot_reload, config.validated, config.rollback), wildcard subscription support

- **K0 Durable Topics** → Receipt Acknowledgments
  - File: `k1/bridge_k0/sse/topics/receipt.py`
  - k0.receipt.* topics (receipt.finalized, receipt.persisted), K0 WAL finalization notifications to K1

- **K0 Durable Topics** → Learning Feedback
  - File: `k1/bridge_k0/sse/topics/learning.py`
  - k0.learning.* topics (learning.feedback, learning.drift_detected), explicit user feedback propagation to all K1 instances

- **K0 Durable Topics** → CRDT Synchronization
  - File: `k1/bridge_k0/sse/topics/crdt.py`
  - k0.crdt.* topics (crdt.merge, crdt.sync), conflict-free replicated data type broadcasts for SessionState

#### [ADR-0043a](../../docs/architecture/decisions/0043a-*.md): 0043A Topic Hierarchy

**Components:**

- **Topic Hierarchy** → Hierarchical Naming
  - File: `k1/bridge_k0/sse/hierarchy/naming.py`
  - Dot notation (k0.category.subcategory.event), lowercase_with_underscores, max 4 levels, k0.* prefix mandatory (K0/K1 separation)

- **Topic Hierarchy** → Wildcard Subscription
  - File: `k1/bridge_k0/sse/subscription/wildcard.py`
  - k0.config.*matches all config events (future-proof subscriptions), multi-level wildcard k0.config.**(matches all descendants), k0.* matches all K0 durable events

- **Topic Hierarchy** → 60+ Topic Registry
  - File: `k1/bridge_k0/sse/registry/topic_registry.py`
  - Complete topic registry (8 major categories: config/receipt/learning/CRDT/policy/audit/family/ui), 60+ K0 SSE topics organized hierarchically

#### [ADR-0043b](../../docs/architecture/decisions/0043b-*.md): 0043B Subscription Patterns

**Components:**

- **Subscription Patterns** → Exact Match
  - File: `k1/bridge_k0/sse/subscription/exact.py`
  - Subscribe to specific topic only (k0.config.changed), single topic matching, critical event subscriptions

- **Subscription Patterns** → Wildcard Single Level
  - File: `k1/bridge_k0/sse/subscription/wildcard_single.py`
  - k0.config.* matches one level deep (k0.config.changed, k0.config.validated), category group subscriptions

- **Subscription Patterns** → Multi-Level Wildcard
  - File: `k1/bridge_k0/sse/subscription/wildcard_multi.py`
  - k0.config.** matches all descendants (k0.config.hot_reload.completed), recursive category matching

- **Subscription Patterns** → Filter Expressions
  - File: `k1/bridge_k0/sse/subscription/filters.py`
  - Subscribe with filters (user_id, family_id), conditional matching (k0.receipt.* where user_id=user_123), scoped subscriptions

- **Subscription Patterns** → Consumer Groups
  - File: `k1/bridge_k0/sse/subscription/consumer_groups.py`
  - Round-robin load balancing across K1 instances, consumer group (k1_instances), each event to ONE instance only

#### [ADR-0043c](../../docs/architecture/decisions/0043c-*.md): 0043C Topic Routing

**Components:**

- **Topic Routing** → K0TopicRouter
  - File: `k0/sse/topic_router.py`
  - Route events from producers to consumers, subscription lookup, fanout strategy (broadcast vs consumer group), delivery tracking

- **Topic Routing** → At-Least-Once Delivery
  - File: `k0/sse/delivery_guarantees.py`
  - Cursor-based ACK for at-least-once delivery, retry on failure (exponential backoff), dead letter queue (DLQ) for terminal failures after 3 retries

- **Topic Routing** → Fanout Strategies
  - File: `k0/sse/fanout_strategies.py`
  - Broadcast all (all consumers receive event), consumer group one (load balance to one), routing metrics (delivery success rate, latency per topic)

- **Topic Routing** → Dead Letter Queue
  - File: `k0/sse/dlq_manager.py`
  - Store failed events (3 retries exhausted), 7-day DLQ retention, max 10K DLQ entries, supervisor alerts for DLQ overflow

#### [ADR-0043d](../../docs/architecture/decisions/0043d-*.md): 0043D Topic Access Control

**Components:**

- **Topic Access Control** → 4-Level Access Control
  - File: `k1/bridge_k0/sse/acl/access_levels.py`
  - Admin topics (k0.config.*, k0.policy.*, k0.audit.*), user topics (k0.receipt.* with user_id scope), family topics (k0.family.* with family_id scope), system topics (internal only)

- **Topic Access Control** → ACL Enforcement
  - File: `k1/bridge_k0/sse/acl/enforcer.py`
  - Validate permissions before subscribe/publish, category-level ACLs (k0.policy.*= admin only, k0.learning.* = user scope, ui.* = public sanitized payloads), role-based policies

- **Topic Access Control** → Topic-Level Scoping
  - File: `k1/bridge_k0/sse/acl/scoping.py`
  - User_id filters (user sees own receipts only), family_id filters (family members see family events only), no cross-user data leakage

- **Topic Access Control** → Audit Logging
  - File: `k1/bridge_k0/sse/acl/audit.py`
  - Track access to sensitive topics (k0.policy.*, k0.audit.*), 365-day audit log retention, GDPR compliance (Article 15 right to access)


### SSE-WebSocket Bridge

#### [ADR-0046](../../docs/architecture/decisions/0046-*.md): 0046 SSE Subscription

**Components:**

- **SSE Subscription** → K1SSESubscriber
  - File: `k1/bridge_k0/sse_subscriber.py`
  - Register handlers for UI-relevant topics, cursor tracking, event routing

- **Observability** → Prometheus Metrics
  - File: `k1/api/websocket/metrics.py`
  - sse_bridge_events_forwarded_total, transform_latency_ms, broadcast_latency_ms, connections_active, backpressure_drops_total

- **Observability** → Bridge Monitoring
  - File: `observability/dashboards/sse_bridge.json`
  - Grafana dashboard (latency P95, connections, backpressure drops, event throughput)

- **Configuration** → Bridge Config
  - File: `k1/config/sse_bridge.yml`
  - Subscribed topics, max connections (10K), send_queue_size (100), backpressure_threshold (90%)


### Saga Error Recovery

#### [ADR-0008a](../../docs/architecture/decisions/0008a-*.md): 0008A Idempotency

**Components:**

- **Idempotency** → Redis Integration
  - File: `k1/l5_infrastructure/redis/client.py`
  - Redis GET/SETEX, 5-minute TTL, <1ms latency, duplicate prevention

- **Audit Trail** → K0 WAL Logging
  - File: `k1/bridge_k0/saga_logger.py`
  - CompensationLog FlatBuffers, SAGA_LOG topic, 7-day retention, <5ms write

#### [ADR-0008c](../../docs/architecture/decisions/0008c-*.md): 0008C Distributed State

**Components:**

- **Distributed State** → K0 Persistence
  - File: `k1/bridge_k0/saga_persistence.py`
  - update_saga_log, SAGA_LOG topic, real-time writes, 7-day retention, <5ms


### Schema Versioning

#### [ADR-0013](../../docs/architecture/decisions/0013-*.md): 0013 SemVer Policy

**Components:**

- **SemVer Policy** → Version Bump Rules
  - File: `k1/config/versioning_policy.yml`
  - MAJOR (breaking: field removal/type change), MINOR (new optional field), PATCH (documentation)

- **SemVer Policy** → 90-Day Deprecation
  - File: `k1/config/deprecation_policy.yml`
  - 90-day minimum window, email/Slack/ADR notifications, (deprecated) attribute

- **SemVer Policy** → Breaking Changes
  - File: `docs/architecture/BREAKING_CHANGES.md`
  - Field removal, type change, new required field, field rename → MAJOR bump

- **SemVer Policy** → Backward Compatibility
  - File: `docs/architecture/COMPATIBILITY.md`
  - MINOR/PATCH versions backward-compatible, old clients ignore new optional fields

#### [ADR-0013a](../../docs/architecture/decisions/0013a-*.md): 0013A Version Registry

**Components:**

- **Version Registry** → Central Registry
  - File: `k1/config/schema_registry.yml`
  - 76 schemas × 3-5 versions = 228+ entries, version metadata, changelog, compatibility matrix

- **Version Registry** → Compatibility Matrix
  - File: `k1/config/schema_registry.yml`
  - Auto-generated: same MAJOR compatible, different MAJOR incompatible, forward/backward rules

- **Version Registry** → Deprecation Schedule
  - File: `k1/config/schema_registry.yml`
  - 90-day countdown per field, usage percentage, migration guide links, removal dates

- **Version Registry** → CLI Tool
  - File: `tools/k1_schema_version.py`
  - k1-schema-version check/deprecations/validate, <100ms latency, cached registry

#### [ADR-0013b](../../docs/architecture/decisions/0013b-*.md): 0013B CI/CD Automation

**Components:**

- **CI/CD Automation** → Schema Diff Analysis
  - File: `scripts/schema_diff_analyzer.py`
  - Parse old/new .fbs files, compute diff, detect MAJOR/MINOR/PATCH changes, <10s analysis

- **CI/CD Automation** → Version Bump Validation
  - File: `ci/validate_version_bump.py`
  - Fail build if version bump incorrect, <30s CI/CD latency, >95% accuracy

- **CI/CD Automation** → Changelog Generation
  - File: `scripts/generate_changelog.py`
  - Auto-generate CHANGELOG.md from schema diff, Git commit messages

- **CI/CD Automation** → GitHub Actions Workflow
  - File: `.github/workflows/schema-version-validation.yml`
  - Run on PR, validate version bumps, fail if incorrect, clear error messages

#### [ADR-0013c](../../docs/architecture/decisions/0013c-*.md): 0013C Deprecation Workflow

**Components:**

- **Deprecation Workflow** → Runtime Alerts
  - File: `k1/l5_infrastructure/observability/deprecation_logger.py`
  - Log warning when deprecated field accessed, <1ms overhead, log once per session

- **Deprecation Workflow** → FlatBuffers Annotations
  - File: `k1/schemas/**/*.fbs`
  - // DEPRECATED (date): reason, REMOVAL DATE, MIGRATION, [deprecated] attribute

- **Deprecation Workflow** → CI/CD Extraction
  - File: `scripts/extract_deprecations.py`
  - Daily cron job, parse .fbs files, extract DEPRECATED fields, update registry

- **Deprecation Workflow** → Email Notifications
  - File: `scripts/send_deprecation_emails.py`
  - 90/60/30/7 days before removal, <k1-dev@example.com>, clear migration guidance

- **Deprecation Workflow** → Slack Bot
  - File: `scripts/slack_deprecation_bot.py`
  - @K1-Schema-Bot, #schema-changes channel, interactive buttons, weekly digest

- **Deprecation Workflow** → Grafana Dashboard
  - File: `observability/dashboards/schema_deprecations.json`
  - Deprecation timeline, usage metrics %, 30-day alerts, top deprecated fields

#### [ADR-0013d](../../docs/architecture/decisions/0013d-*.md): 0013D Contract Testing

**Components:**

- **Contract Testing** → Pact-Style Tests
  - File: `tests/schemas/contract_tests.py`
  - Consumer-driven contracts, forward/backward compatibility tests, 228+ test cases

- **Contract Testing** → Forward Compatibility
  - File: `tests/schemas/test_forward_compat.py`
  - Old client v2.0.0 + new schema v2.1.0 → ✅, new optional fields ignored

- **Contract Testing** → Backward Compatibility
  - File: `tests/schemas/test_backward_compat.py`
  - New client v2.1.0 + old schema v2.0.0 → ✅, missing optional fields handled gracefully

- **Contract Testing** → Breaking Change Detection
  - File: `tests/schemas/test_breaking_changes.py`
  - Detect field removal, type change, new required field → fail tests

- **Contract Testing** → Multi-Version Matrix
  - File: `tests/schemas/test_matrix_generator.py`
  - 76 schemas × 3 versions × 2 directions = 456 test cases, parallelized <20 min

- **Contract Testing** → CI/CD Integration
  - File: `.github/workflows/schema-contract-tests.yml`
  - Run on schema PR, fail if breaking change without MAJOR bump


### Thermal Management

#### [ADR-0026](../../docs/architecture/decisions/0026-*.md): 0026 Thermal Management

**Components:**

- **Hysteresis Matrix** → Asymmetric Thresholds
  - File: `k1/l5_infrastructure/thermal/hysteresis_matrix.py`
  - Upgrade at +5°C above baseline, downgrade at -2°C below baseline, 7°C hysteresis band, prevents flapping

- **Hysteresis Matrix** → Cooldown Periods
  - File: `k1/l5_infrastructure/thermal/hysteresis_matrix.py`
  - Upgrade cooldown 10s (fast degradation), downgrade cooldown 30-60s (slow recovery), 3:1 to 6:1 ratio

- **Hysteresis Matrix** → 4-Tier Placement
  - File: `k1/l5_infrastructure/thermal/thermal_placement.py`
  - NPU (30ms, 10W) → GPU (50ms, 12W) → CPU (120ms, 15W) → Remote (500ms, 5W), graceful degradation

- **Hysteresis Matrix** → Emergency Jump
  - File: `k1/l5_infrastructure/thermal/thermal_placement.py`
  - Critical temperature ≥85°C → immediate jump to Remote, skip GPU/CPU, <10ms emergency placement

- **Hysteresis Matrix** → Combined Metrics
  - File: `k1/l5_infrastructure/thermal/hysteresis_matrix.py`
  - Temperature (°C) OR Power (W) trigger upgrade, AND condition for downgrade, prevents premature recovery

- **Thermal Zones** → Cool Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - <70°C, all accelerators available, optimal performance, no throttling

- **Thermal Zones** → Warm Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - 70-74°C, all accelerators available, normal operation, no throttling

- **Thermal Zones** → Hot Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - 75-84°C, skip NPU, reduce batch frequency 20%, defer background tasks

- **Thermal Zones** → Critical Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - 85-95°C, CPU/Remote only, skip optional processing (persona, grounding, vision)

- **Thermal Zones** → Emergency Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - >95°C, Remote only, reject new turns, notify user "Device cooling down"

- **Sensor Monitoring** → Multi-Sensor Aggregation
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - Monitor CPU, NPU, GPU thermal zones, max temperature rule, 1-second polling frequency, <1ms per poll

- **Sensor Monitoring** → Cross-Platform Support
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - Linux thermal zones (/sys/class/thermal/), Windows WMI, macOS IOKit, graceful degradation on sensor failure

- **Sensor Monitoring** → State Detection
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - Map temperatures to 5 thermal states, real-time monitoring, ThermalSnapshot dataclass, <0.2ms zone classification

- **Hysteresis FSM** → State Transitions
  - File: `k1/l5_infrastructure/thermal/hysteresis_fsm.py`
  - 5°C buffer prevents oscillation, upward transition >threshold+5°C, downward transition <threshold-5°C

- **Hysteresis FSM** → Dead Zone
  - File: `k1/l5_infrastructure/thermal/hysteresis_fsm.py`
  - Temperatures in dead zone maintain current state (e.g., 70-80°C at WARM/HOT boundary), no rapid switching

- **Hysteresis FSM** → State Persistence
  - File: `k1/l5_infrastructure/thermal/hysteresis_fsm.py`
  - Minimum 10-second state duration, prevents thermal transients, exception for EMERGENCY (immediate transition)

- **Thermal Placement** → State-Aware Policies
  - File: `k1/l5_infrastructure/thermal/thermal_placement.py`
  - COOL/WARM (all), HOT (GPU/CPU/Remote), CRITICAL (CPU/Remote), EMERGENCY (Remote only)

- **Thermal Placement** → Automatic Failover
  - File: `k1/l5_infrastructure/thermal/thermal_placement.py`
  - Running models migrate on thermal state change, KV cache transfer <30ms, model loading <50ms, <100ms total failover

- **Thermal Placement** → KV Cache Preservation
  - File: `k1/l5_infrastructure/thermal/thermal_placement.py`
  - Copy cached key/value tensors to new accelerator, maintain turn context, state preservation during migration

- **Throttling** → HOT State
  - File: `k1/l5_infrastructure/thermal/thermal_throttler.py`
  - Increase batch interval 20% (100ms → 120ms), defer background tasks, reduce inference frequency

- **Throttling** → CRITICAL State
  - File: `k1/l5_infrastructure/thermal/thermal_throttler.py`
  - Skip persona customization, skip grounding updates, skip vision processing, simplified responses

- **Throttling** → EMERGENCY State
  - File: `k1/l5_infrastructure/thermal/thermal_throttler.py`
  - Reject new turns, notify user "Device cooling down", block local inference, service unavailable

- **User Notifications** → Developer Logs
  - File: `k1/l5_infrastructure/thermal/thermal_throttler.py`
  - HOT/CRITICAL/EMERGENCY state logs, throttling action logs, structured logging with thermal_state field

#### [ADR-0026a](../../docs/architecture/decisions/0026a-*.md): 0026A Thermal Zones

**Components:**

- **Thermal Zones** → Cool Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - <70°C, all accelerators available, optimal performance, no throttling

- **Thermal Zones** → Warm Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - 70-74°C, all accelerators available, normal operation, no throttling

- **Thermal Zones** → Hot Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - 75-84°C, skip NPU, reduce batch frequency 20%, defer background tasks

- **Thermal Zones** → Critical Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - 85-95°C, CPU/Remote only, skip optional processing (persona, grounding, vision)

- **Thermal Zones** → Emergency Zone
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - >95°C, Remote only, reject new turns, notify user "Device cooling down"

- **Sensor Monitoring** → Multi-Sensor Aggregation
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - Monitor CPU, NPU, GPU thermal zones, max temperature rule, 1-second polling frequency, <1ms per poll

- **Sensor Monitoring** → Cross-Platform Support
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - Linux thermal zones (/sys/class/thermal/), Windows WMI, macOS IOKit, graceful degradation on sensor failure

- **Sensor Monitoring** → State Detection
  - File: `k1/l5_infrastructure/thermal/thermal_sensors.py`
  - Map temperatures to 5 thermal states, real-time monitoring, ThermalSnapshot dataclass, <0.2ms zone classification

#### [ADR-0026b](../../docs/architecture/decisions/0026b-*.md): 0026B Hysteresis FSM

**Components:**

- **Hysteresis FSM** → State Transitions
  - File: `k1/l5_infrastructure/thermal/hysteresis_fsm.py`
  - 5°C buffer prevents oscillation, upward transition >threshold+5°C, downward transition <threshold-5°C

- **Hysteresis FSM** → Dead Zone
  - File: `k1/l5_infrastructure/thermal/hysteresis_fsm.py`
  - Temperatures in dead zone maintain current state (e.g., 70-80°C at WARM/HOT boundary), no rapid switching

- **Hysteresis FSM** → State Persistence
  - File: `k1/l5_infrastructure/thermal/hysteresis_fsm.py`
  - Minimum 10-second state duration, prevents thermal transients, exception for EMERGENCY (immediate transition)

#### [ADR-0026c](../../docs/architecture/decisions/0026c-*.md): 0026C Hysteresis Matrix

**Components:**

- **Hysteresis Matrix** → 4-Tier Placement
  - File: `k1/l5_infrastructure/thermal/thermal_placement.py`
  - NPU (30ms, 10W) → GPU (50ms, 12W) → CPU (120ms, 15W) → Remote (500ms, 5W), graceful degradation

- **Thermal Placement** → State-Aware Policies
  - File: `k1/l5_infrastructure/thermal/thermal_placement.py`
  - COOL/WARM (all), HOT (GPU/CPU/Remote), CRITICAL (CPU/Remote), EMERGENCY (Remote only)

- **Thermal Placement** → Automatic Failover
  - File: `k1/l5_infrastructure/thermal/thermal_placement.py`
  - Running models migrate on thermal state change, KV cache transfer <30ms, model loading <50ms, <100ms total failover

- **Thermal Placement** → KV Cache Preservation
  - File: `k1/l5_infrastructure/thermal/thermal_placement.py`
  - Copy cached key/value tensors to new accelerator, maintain turn context, state preservation during migration

#### [ADR-0026d](../../docs/architecture/decisions/0026d-*.md): 0026D Throttling

**Components:**

- **Throttling** → HOT State
  - File: `k1/l5_infrastructure/thermal/thermal_throttler.py`
  - Increase batch interval 20% (100ms → 120ms), defer background tasks, reduce inference frequency

- **Throttling** → CRITICAL State
  - File: `k1/l5_infrastructure/thermal/thermal_throttler.py`
  - Skip persona customization, skip grounding updates, skip vision processing, simplified responses

- **Throttling** → EMERGENCY State
  - File: `k1/l5_infrastructure/thermal/thermal_throttler.py`
  - Reject new turns, notify user "Device cooling down", block local inference, service unavailable

- **User Notifications** → Developer Logs
  - File: `k1/l5_infrastructure/thermal/thermal_throttler.py`
  - HOT/CRITICAL/EMERGENCY state logs, throttling action logs, structured logging with thermal_state field


### Trace Sampling

#### [ADR-0030](../../docs/architecture/decisions/0030-*.md): 0030 Head-Based Sampling

**Components:**

- **Head-Based Sampling** → Baseline Sampling
  - File: `observability/tracing/head_sampler.py`
  - 1% random sampling for statistical baseline, Hash-based decision (<0.2ms), W3C Trace Context propagation, Cognitive_trace_id generation

- **Head-Based Sampling** → Error Sampling
  - File: `observability/tracing/head_sampler.py`
  - 100% error sampling (turn_status==ERROR), <0.5ms error detection, All failures traced, Debug coverage guarantee

- **Head-Based Sampling** → Slow Request Sampling
  - File: `observability/tracing/head_sampler.py`
  - 100% sampling for >P95 latency (TTFT >150ms, E2E >2000ms), <1ms latency check, Bottleneck identification, Performance debugging

- **Head-Based Sampling** → Privacy Band Sampling
  - File: `observability/tracing/head_sampler.py`
  - 100% RED band sampling (sensitive operations), Audit compliance, Privacy-aware tracing, Regulatory requirements

- **Head-Based Sampling** → W3C Trace Context
  - File: `observability/tracing/trace_context.py`
  - Version-traceid-parentid-flags format (00-{32hex}-{16hex}-01), 128-bit trace ID (cognitive_trace_id), 64-bit parent ID, Trace flags (sampled bit)

- **Tail-Based Sampling** → Span Buffering
  - File: `observability/tracing/tail_sampler.py`
  - 60s span buffer (<50MB memory), BatchSpanProcessor, Post-decision sampling, Buffer all spans until turn completion

- **Tail-Based Sampling** → Post-Decision Logic
  - File: `observability/tracing/tail_sampler.py`
  - Decision after turn completion (<100ms latency), Evaluate final status/latency/privacy, KEEP (export) or DISCARD (drop), Context-aware retention

- **Tail-Based Sampling** → Memory Management
  - File: `observability/tracing/tail_sampler.py`
  - <50MB buffer budget (10,000 turns × 50 spans × 100 bytes), TTL-based eviction, Buffer overflow protection, Memory pressure monitoring

- **Adaptive Sampling** → Rate Adjustment FSM
  - File: `observability/tracing/adaptive_sampler.py`
  - 3 states (NORMAL 1%, DEGRADATION 10%, CRITICAL 50%), Health-based triggers (TTFT/error rate/backpressure), Gradual recovery (50%→25%→10%→5%→1%), Hysteresis (10% margin)

- **Adaptive Sampling** → Health Indicators
  - File: `observability/tracing/adaptive_sampler.py`
  - TTFT P95 target (150ms, degrade at 157ms), E2E P95 target (2000ms, degrade at 2100ms), Error rate threshold (<0.1% normal, >1% degrade), Backpressure tier detection

- **Adaptive Sampling** → State Transitions
  - File: `observability/tracing/adaptive_sampler.py`
  - NORMAL→DEGRADATION (TTFT >157ms 5s sustained OR error >1%), DEGRADATION→CRITICAL (TTFT >210ms 10s OR error >5%), Recovery downgrade (metrics normal 60s), Oscillation prevention

- **Jaeger Integration** → OTLP Exporter
  - File: `observability/tracing/otlp_exporter.py`
  - gRPC OTLP protocol (localhost:4317), Batch export (512 spans, 5s timeout), Non-blocking async export (<5ms latency), Span serialization

- **Jaeger Integration** → Badger Storage
  - File: `infrastructure/jaeger/badger_backend.yaml`
  - Embedded key-value store (no external DB), Hot storage (7 days all traces), Warm storage (30 days errors/critical), TTL-based eviction

- **Jaeger Integration** → Query API
  - File: `infrastructure/jaeger/query_service.yaml`
  - REST API (port 16686/api), gRPC API (port 16685), Trace search (by trace_id/session_id/error/latency), <1s query performance

- **Jaeger Integration** → Web UI
  - File: `infrastructure/jaeger/ui_config.yaml`
  - Jaeger web UI (port 16686), Trace timeline visualization, Dependency graph, Service map, Trace filtering

- **Storage** → Retention Policy
  - File: `observability/tracing/retention_policy.py`
  - Hot 7 days (all sampled traces), Warm 30 days (errors/SLO violations/RED band), Cold archive (>30 days to S3, optional), Cost target <$50/month

- **Storage** → Volume Estimates
  - File: `observability/tracing/volume_calculator.py`
  - 10K turns/day × 1% baseline = 100 traces/day, 50 spans/turn × 5KB/span = 25MB/day, 7-day hot storage = 175MB, 30-day warm = 750MB, 97% cost reduction vs 100% tracing

- **Export** → Span Creation
  - File: `observability/tracing/span_factory.py`
  - OpenTelemetry Span API, Span attributes (component/status/error_type), Span events (timestamps), Context propagation (W3C), <1ms span creation overhead

- **Export** → Cognitive Trace ID
  - File: `observability/tracing/trace_id_generator.py`
  - 128-bit unique ID (32 hex chars), UUID v4 generation, Propagation through Actor messages, FlatBuffers integration, Cross-component correlation (K0→K1→Agents→Tools)

#### [ADR-0030a](../../docs/architecture/decisions/0030a-*.md): 0030A Head-Based Sampling

**Components:**

- **Head-Based Sampling** → Baseline Sampling
  - File: `observability/tracing/head_sampler.py`
  - 1% random sampling for statistical baseline, Hash-based decision (<0.2ms), W3C Trace Context propagation, Cognitive_trace_id generation

- **Head-Based Sampling** → Error Sampling
  - File: `observability/tracing/head_sampler.py`
  - 100% error sampling (turn_status==ERROR), <0.5ms error detection, All failures traced, Debug coverage guarantee

- **Head-Based Sampling** → Slow Request Sampling
  - File: `observability/tracing/head_sampler.py`
  - 100% sampling for >P95 latency (TTFT >150ms, E2E >2000ms), <1ms latency check, Bottleneck identification, Performance debugging

- **Head-Based Sampling** → Privacy Band Sampling
  - File: `observability/tracing/head_sampler.py`
  - 100% RED band sampling (sensitive operations), Audit compliance, Privacy-aware tracing, Regulatory requirements

- **Head-Based Sampling** → W3C Trace Context
  - File: `observability/tracing/trace_context.py`
  - Version-traceid-parentid-flags format (00-{32hex}-{16hex}-01), 128-bit trace ID (cognitive_trace_id), 64-bit parent ID, Trace flags (sampled bit)

#### [ADR-0030b](../../docs/architecture/decisions/0030b-*.md): 0030B Tail-Based Sampling

**Components:**

- **Tail-Based Sampling** → Span Buffering
  - File: `observability/tracing/tail_sampler.py`
  - 60s span buffer (<50MB memory), BatchSpanProcessor, Post-decision sampling, Buffer all spans until turn completion

- **Tail-Based Sampling** → Post-Decision Logic
  - File: `observability/tracing/tail_sampler.py`
  - Decision after turn completion (<100ms latency), Evaluate final status/latency/privacy, KEEP (export) or DISCARD (drop), Context-aware retention

- **Tail-Based Sampling** → Memory Management
  - File: `observability/tracing/tail_sampler.py`
  - <50MB buffer budget (10,000 turns × 50 spans × 100 bytes), TTL-based eviction, Buffer overflow protection, Memory pressure monitoring

#### [ADR-0030c](../../docs/architecture/decisions/0030c-*.md): 0030C Adaptive Sampling

**Components:**

- **Adaptive Sampling** → Rate Adjustment FSM
  - File: `observability/tracing/adaptive_sampler.py`
  - 3 states (NORMAL 1%, DEGRADATION 10%, CRITICAL 50%), Health-based triggers (TTFT/error rate/backpressure), Gradual recovery (50%→25%→10%→5%→1%), Hysteresis (10% margin)

- **Adaptive Sampling** → Health Indicators
  - File: `observability/tracing/adaptive_sampler.py`
  - TTFT P95 target (150ms, degrade at 157ms), E2E P95 target (2000ms, degrade at 2100ms), Error rate threshold (<0.1% normal, >1% degrade), Backpressure tier detection

- **Adaptive Sampling** → State Transitions
  - File: `observability/tracing/adaptive_sampler.py`
  - NORMAL→DEGRADATION (TTFT >157ms 5s sustained OR error >1%), DEGRADATION→CRITICAL (TTFT >210ms 10s OR error >5%), Recovery downgrade (metrics normal 60s), Oscillation prevention

#### [ADR-0030d](../../docs/architecture/decisions/0030d-*.md): 0030D Jaeger Integration

**Components:**

- **Jaeger Integration** → OTLP Exporter
  - File: `observability/tracing/otlp_exporter.py`
  - gRPC OTLP protocol (localhost:4317), Batch export (512 spans, 5s timeout), Non-blocking async export (<5ms latency), Span serialization

- **Jaeger Integration** → Badger Storage
  - File: `infrastructure/jaeger/badger_backend.yaml`
  - Embedded key-value store (no external DB), Hot storage (7 days all traces), Warm storage (30 days errors/critical), TTL-based eviction

- **Jaeger Integration** → Query API
  - File: `infrastructure/jaeger/query_service.yaml`
  - REST API (port 16686/api), gRPC API (port 16685), Trace search (by trace_id/session_id/error/latency), <1s query performance

- **Jaeger Integration** → Web UI
  - File: `infrastructure/jaeger/ui_config.yaml`
  - Jaeger web UI (port 16686), Trace timeline visualization, Dependency graph, Service map, Trace filtering

- **Storage** → Retention Policy
  - File: `observability/tracing/retention_policy.py`
  - Hot 7 days (all sampled traces), Warm 30 days (errors/SLO violations/RED band), Cold archive (>30 days to S3, optional), Cost target <$50/month


### Turn Boundary Management

#### [ADR-0054](../../docs/architecture/decisions/0054-*.md): 0054 Main

**Components:**

- **Main** → Metrics
  - File: `observability/metrics/turn_boundary.py`
  - turn_boundary_detected_total (signal_type), turn_duration_ms (histogram), turn_message_count (histogram), turn_signal_ratio (gauge)

- **Main** → Research Foundation
  - File: `docs/research/turn_taking_research.md`
  - Sacks et al. 1974 turn-taking, TRP pauses 0.5-2.5s, Google/Alexa 1.5-2.5s thresholds, natural conversation flow

#### [ADR-0054a](../../docs/architecture/decisions/0054a-*.md): 0054A Implicit Pause

**Components:**

- **Implicit Pause** → Performance Targets
  - File: `observability/metrics/turn_boundary.py`
  - Pause detection <50ms after 2s threshold, timer overhead <2ms per message, no user-visible latency

- **Implicit Pause** → Metrics
  - File: `observability/metrics/turn_boundary.py`
  - implicit_pause_detected_total (counter), pause_duration_ms (histogram buckets 1500/2000/2500/3000/5000)

- **Implicit Pause** → Research Foundation
  - File: `docs/research/turn_taking_research.md`
  - Sacks et al. 1974 TRP 0.5-2.5s, Google 1.5-2.0s, Alexa 2.0-2.5s, Siri 1.8-2.2s silence thresholds

- **Implicit Pause** → Human Perception
  - File: `docs/research/turn_taking_research.md`
  - <1s pause mid-thought (don't interrupt), 1-2s ambiguous, >2s clear turn end (expect response)

- **Implicit Pause** → Future Work
  - File: `docs/roadmap/turn_boundary_enhancements.md`
  - Adaptive pause threshold per user typing speed (fast 1.5s, slow 2.5s), linguistic completeness detection (LLM check)

#### [ADR-0054b](../../docs/architecture/decisions/0054b-*.md): 0054B Explicit Submit

**Components:**

- **Explicit Submit** → Metrics
  - File: `observability/metrics/turn_boundary.py`
  - explicit_submit_total (counter by method: enter_key/send_button/voice_command), submit_method_ratio (gauge, target 30-40% explicit)

- **Explicit Submit** → Implementation Phases
  - File: `docs/implementation/explicit_submit_rollout.md`
  - Phase 1: WebSocket protocol, Phase 2: Desktop UI, Phase 3: Mobile UI, Phase 4: Voice commands

- **Explicit Submit** → UX Tests
  - File: `tests/ui/test_explicit_submit.py`
  - Send button click triggers submit, Enter key triggers submit, Shift+Enter triggers submit, voice "Send" command triggers submit

#### [ADR-0054c](../../docs/architecture/decisions/0054c-*.md): 0054C MPST Transitions

**Components:**

- **MPST Transitions** → Metrics
  - File: `observability/metrics/protocol_monitor.py`
  - protocol_transitions_total (from_state/to_state/event), invalid_transitions_total, protocol_timeouts_total (state), state_duration_ms (histogram by state)


### Turn History Retention

#### [ADR-0021](../../docs/architecture/decisions/0021-*.md): 0021 Retention Policies

**Components:**

- **Retention Policies** → Privacy Band Tiers
  - File: `k1/l5_infrastructure/storage/retention_policies.yml`
  - GREEN 395 days, AMBER 395 days, RED 97 days, BLACK 0 days (ephemeral), GDPR compliance

- **Retention Policies** → Multi-Tier Retention
  - File: `k1/l5_infrastructure/storage/retention_policy.py`
  - Hot 7 days, Warm 30 days, Cold 365 days, automated deletion, cost optimization

- **Retention Policies** → Cost Optimization
  - File: `k1/l5_infrastructure/storage/retention_policy.py`
  - 95% cost reduction ($0.08/GB vs $1.60/GB over 5 years), automated deletion, 365-day limit

#### [ADR-0021a](../../docs/architecture/decisions/0021a-*.md): 0021A Policy Engine

**Components:**

- **Policy Engine** → RetentionPolicyEngine
  - File: `k1/l5_infrastructure/storage/retention_policy.py`
  - Background task (24h interval), enforce retention across 3 tiers, batch deletion, audit trail

- **Policy Engine** → Hot Tier Enforcement
  - File: `k1/l5_infrastructure/storage/retention_policy.py`
  - Delete turns >7 days from SessionState, <5s for 1000 sessions, in-memory deletion

- **Policy Engine** → Warm Tier Enforcement
  - File: `k1/l5_infrastructure/storage/retention_policy.py`
  - Query K0 WAL for turns >30 days, batch delete 1000 turns, <15s P95

- **Policy Engine** → Cold Tier Enforcement
  - File: `k1/l5_infrastructure/storage/retention_policy.py`
  - Query S3 for sessions >7 years (2555 days), batch delete 100 sessions, <30s P95

- **Policy Engine** → Audit Logging
  - File: `k1/l5_infrastructure/storage/retention_audit_logger.py`
  - Log all deletion events, session_id + turn_id + tier + reason, compliance audits, forensics

#### [ADR-0021b](../../docs/architecture/decisions/0021b-*.md): 0021B Privacy Band Overrides

**Components:**

- **Privacy Band Overrides** → RED Band Retention
  - File: `k1/l5_infrastructure/storage/privacy_band_policies.yml`
  - 7 days warm, 90 days cold, 97 days total, sensitive data, GDPR Article 5

- **Privacy Band Overrides** → BLACK Band Ephemeral
  - File: `k1/l5_infrastructure/storage/privacy_band_policies.yml`
  - 0 days retention, ephemeral only, no persistence, end-to-end encrypted, user-controlled

- **Privacy Band Overrides** → GREEN/AMBER Baseline
  - File: `k1/l5_infrastructure/storage/privacy_band_policies.yml`
  - 30 days warm, 365 days cold, 395 days total, standard retention, GDPR baseline

- **Privacy Band Overrides** → Retention Override Logic
  - File: `k1/l5_infrastructure/storage/retention_policy.py`
  - Check privacy_band first, apply shorter retention for RED, enforce ephemeral for BLACK

#### [ADR-0021c](../../docs/architecture/decisions/0021c-*.md): 0021C Compliance

**Components:**

- **Compliance** → Audit Trail
  - File: `k1/l5_infrastructure/storage/compliance_audit.py`
  - All deletion events logged, K0 receipts, compliance audits, immutable log

- **Compliance** → GDPR Article 5(e)
  - File: `docs/compliance/gdpr_retention.md`
  - "No longer than necessary", time-limited retention, 365-day baseline, legal rationale

- **Compliance** → GDPR Article 17
  - File: `docs/compliance/gdpr_deletion.md`
  - Right to erasure, 30-day grace period, user deletion API, compliance reporting

- **Compliance** → Retention Reports
  - File: `reports/retention_compliance.py`
  - Monthly compliance reports, deletion statistics, policy adherence, audit evidence


### Voice Backpressure

#### [ADR-0057](../../docs/architecture/decisions/0057-*.md): 0057 Cascade Core

**Components:**

- **Cascade Core** → 3-Tier Watermarks
  - File: `k1/l5_infrastructure/backpressure/voice_cascade.py`
  - 3-tier backpressure: ASR drop 80%, TTS degrade 90%, reject 95%, load calculation ASR 60% + TTS 40%

- **Cascade Core** → ASR Backpressure
  - File: `k1/l5_infrastructure/backpressure/voice_cascade.py`
  - ASRBackpressure class, frame_queue management, selective frame dropping strategy, load monitoring

- **Cascade Core** → TTS Backpressure
  - File: `k1/l5_infrastructure/backpressure/voice_cascade.py`
  - TTSBackpressure class, QUALITY_LEVELS 0-4, degradation ladder, thermal integration

- **Cascade Core** → Barge-in Coordination
  - File: `k1/l5_infrastructure/backpressure/voice_cascade.py`
  - BargeInHandler, stop TTS <120ms, preserve context, cancel tools, 4-step protocol

- **Cascade Core** → Performance Targets
  - File: `k1/l5_infrastructure/backpressure/voice_cascade.py`
  - frame_drop_decision <5ms, barge_in_stop <120ms, watermark enforcement 80/90/95%

- **Cascade Core** → Integration Points
  - File: `k1/l5_infrastructure/backpressure/voice_cascade.py`
  - ADR-0039 general backpressure, ADR-0027 thermal placement, multi-stage coordination


### Voice Pipeline Implementation

#### [ADR-0056](../../docs/architecture/decisions/0056-*.md): 0056 Pipeline Architecture

**Components:**

- **Pipeline Architecture** → K0ASRPipeline
  - File: `k0/pipelines/p11_asr/asr_pipeline.py`
  - K0 P11 pipeline: ASR frame buffering, VAD, ASR model inference (Whisper), partial transcript streaming

- **Pipeline Architecture** → K0TTSPipeline
  - File: `k0/pipelines/p12_tts/tts_pipeline.py`
  - K0 P12 pipeline: SSML generation, TTS model inference (VITS), audio streaming synthesis, opus/pcm codec

- **Pipeline Architecture** → ASR Frame Processing
  - File: `k0/pipelines/p11_asr/frame_processor.py`
  - 20ms frames, 80ms ring buffer, VAD energy calculation, partial transcript emission

- **Pipeline Architecture** → VAD Integration
  - File: `k0/pipelines/p11_asr/vad_detector.py`
  - 2s silence threshold (ADR-0054 turn boundary), energy_threshold_db=-50, RMS energy calculation

- **Pipeline Architecture** → Partial Transcript Streaming
  - File: `k0/pipelines/p11_asr/asr_pipeline.py`
  - return_partials=True flag, emit intermediate ASR results for typing indicator style, is_partial flag in transcript

- **Pipeline Architecture** → TTS Streaming Synthesis
  - File: `k0/pipelines/p12_tts/tts_pipeline.py`
  - synthesize_streaming method: text → SSML → TTS model → audio chunks, streaming response (async iterator)

- **Pipeline Architecture** → Prosody Controls
  - File: `k0/pipelines/p12_tts/prosody_controller.py`
  - response.prosody: pitch (Hz), rate (words/min), emphasis (stress patterns), SSML generation

- **Performance Budgets** → ASR Latency
  - File: `k0/pipelines/p11_asr/config.yml`
  - asr_frame_processing_ms: 100 (P95 target), asr_final_transcript_ms: 300 (end of speech → final transcript)

- **Performance Budgets** → TTS Latency
  - File: `k0/pipelines/p12_tts/config.yml`
  - tts_synthesis_first_chunk_ms: 200 (TTFA Time to First Audio), tts_synthesis_streaming_ms: 50 (subsequent chunks)

- **Metrics** → ASR Metrics
  - File: `observability/metrics/voice_pipeline_metrics.py`
  - asr_frame_processing_latency_ms histogram (buckets 10/50/100/200/500), K0 P11 owner

- **Metrics** → TTS Metrics
  - File: `observability/metrics/voice_pipeline_metrics.py`
  - tts_synthesis_latency_ms histogram (buckets 50/100/200/500/1000), K0 P12 owner

- **ASR Ingress** → Frame Handling
  - File: `k0/pipelines/p11_asr/frame_handler.py`
  - ADR-0056a: 20ms audio frames, buffering strategy, frame drop policy at 80% capacity

- **ASR Ingress** → VAD Processing
  - File: `k0/pipelines/p11_asr/vad_processor.py`
  - ADR-0056a: Voice Activity Detection, energy threshold -50dB, 2s silence threshold, RMS energy calculation

- **ASR Ingress** → Partial Results
  - File: `k0/pipelines/p11_asr/partial_result_emitter.py`
  - ADR-0056a: Stream intermediate ASR transcripts, is_partial flag, typing indicator UX, final transcript on turn boundary

- **TTS Synthesis** → Prosody Controls
  - File: `k0/pipelines/p12_tts/prosody_generator.py`
  - ADR-0056d: Pitch control (Hz), rate control (words/min), emphasis patterns (stress), SSML generation

- **TTS Synthesis** → SSML Generation
  - File: `k0/pipelines/p12_tts/ssml_generator.py`
  - ADR-0056d: Convert text + prosody to SSML, <prosody> tags, <emphasis> tags, <break> pauses

- **TTS Synthesis** → Streaming Audio
  - File: `k0/pipelines/p12_tts/streaming_synthesizer.py`
  - ADR-0056d: Chunk-based TTS synthesis, 40ms audio chunks, async iterator, VITS model

- **Audio Output** → Buffer Management
  - File: `k0/pipelines/p12_tts/audio_buffer_manager.py`
  - ADR-0056e: Jitter buffer (80ms), frame reordering, packet loss recovery, adaptive buffering

#### [ADR-0056a](../../docs/architecture/decisions/0056a-*.md): 0056A ASR Ingress

**Components:**

- **ASR Ingress** → Frame Handling
  - File: `k0/pipelines/p11_asr/frame_handler.py`
  - ADR-0056a: 20ms audio frames, buffering strategy, frame drop policy at 80% capacity

- **ASR Ingress** → VAD Processing
  - File: `k0/pipelines/p11_asr/vad_processor.py`
  - ADR-0056a: Voice Activity Detection, energy threshold -50dB, 2s silence threshold, RMS energy calculation

- **ASR Ingress** → Partial Results
  - File: `k0/pipelines/p11_asr/partial_result_emitter.py`
  - ADR-0056a: Stream intermediate ASR transcripts, is_partial flag, typing indicator UX, final transcript on turn boundary

#### [ADR-0056d](../../docs/architecture/decisions/0056d-*.md): 0056D TTS Synthesis

**Components:**

- **TTS Synthesis** → Prosody Controls
  - File: `k0/pipelines/p12_tts/prosody_generator.py`
  - ADR-0056d: Pitch control (Hz), rate control (words/min), emphasis patterns (stress), SSML generation

- **TTS Synthesis** → SSML Generation
  - File: `k0/pipelines/p12_tts/ssml_generator.py`
  - ADR-0056d: Convert text + prosody to SSML, <prosody> tags, <emphasis> tags, <break> pauses

- **TTS Synthesis** → Streaming Audio
  - File: `k0/pipelines/p12_tts/streaming_synthesizer.py`
  - ADR-0056d: Chunk-based TTS synthesis, 40ms audio chunks, async iterator, VITS model

#### [ADR-0056e](../../docs/architecture/decisions/0056e-*.md): 0056E Audio Output

**Components:**

- **Audio Output** → Buffer Management
  - File: `k0/pipelines/p12_tts/audio_buffer_manager.py`
  - ADR-0056e: Jitter buffer (80ms), frame reordering, packet loss recovery, adaptive buffering


### WebSocket Binary Protocol

#### [ADR-0015](../../docs/architecture/decisions/0015-*.md): 0015 Protocol Design

**Components:**

- **Protocol Design** → Message Envelope
  - File: `k1/schemas/websocket/message_envelope.fbs`
  - MessageEnvelope, 17 message types, protocol_version, sequence_number, trace_id

- **Protocol Design** → Message Types
  - File: `k1/schemas/websocket/message_types.fbs`
  - TURN_START, TOKEN_CHUNK, TOOL_CALL, BARGE_IN, PING/PONG (17 types)

- **Protocol Design** → Client→Server Messages
  - File: `k1/schemas/websocket/client_messages.fbs`
  - TurnStart, TurnChunk, BargeIn, ToolApproval (4 types)

- **Protocol Design** → Server→Client Messages
  - File: `k1/schemas/websocket/server_messages.fbs`
  - TokenChunk, ToolCall, ToolResult, StateDelta, GroundingCommit (7 types)

#### [ADR-0015a](../../docs/architecture/decisions/0015a-*.md): 0015A Protocol Design

**Components:**

- **Protocol Design** → Message Envelope
  - File: `k1/schemas/websocket/message_envelope.fbs`
  - MessageEnvelope, 17 message types, protocol_version, sequence_number, trace_id

- **Protocol Design** → Message Types
  - File: `k1/schemas/websocket/message_types.fbs`
  - TURN_START, TOKEN_CHUNK, TOOL_CALL, BARGE_IN, PING/PONG (17 types)

#### [ADR-0015b](../../docs/architecture/decisions/0015b-*.md): 0015B Flow Control

**Components:**

- **Flow Control** → ACK Protocol
  - File: `k1/schemas/websocket/ack.fbs`
  - ACK message, ack_seqno, batch 5 messages or 1s, <5% overhead

- **Flow Control** → ACK Manager Client
  - File: `sdk/typescript/ack_manager.ts`
  - AckManager, batched ACKs, unackedCount, lastAckTime tracking

#### [ADR-0015c](../../docs/architecture/decisions/0015c-*.md): 0015C Reconnection

**Components:**

- **Reconnection** → Resume Protocol
  - File: `k1/schemas/websocket/resume.fbs`
  - RESUME message, last_recv_seqno, ResumeResponse, 5 status codes

- **Reconnection** → Client Reconnect Manager
  - File: `sdk/typescript/reconnect_manager.ts`
  - ReconnectManager, exponential backoff 1s→16s, max 5 attempts

- **Reconnection** → Deduplication Manager
  - File: `sdk/typescript/dedup_manager.ts`
  - DeduplicationManager, 2000 seqno cache, skip replayed messages

#### [ADR-0015d](../../docs/architecture/decisions/0015d-*.md): 0015D Streaming

**Components:**

- **Streaming** → Token Schema
  - File: `k1/schemas/websocket/token_chunk.fbs`
  - TOKEN_CHUNK, chunk_index, logprob, finish_reason, model_id, tokens_generated

#### [ADR-0015e](../../docs/architecture/decisions/0015e-*.md): 0015E Client SDK

**Components:**

- **Client SDK** → TypeScript SDK Core
  - File: `sdk/typescript/k1_websocket.ts`
  - K1WebSocket class, binary WebSocket, FlatBuffers bindings, 1800 lines

- **Client SDK** → Reconnect Manager
  - File: `sdk/typescript/reconnect_manager.ts`
  - ReconnectManager, exponential backoff, RESUME message, 5 attempts max

- **Client SDK** → ACK Manager
  - File: `sdk/typescript/ack_manager.ts`
  - AckManager, batch 5 messages or 1s, flow control, periodic timer

- **Client SDK** → Deduplication Manager
  - File: `sdk/typescript/dedup_manager.ts`
  - DeduplicationManager, Set<number> cache, max 2000 entries, eviction

- **Client SDK** → React Hooks
  - File: `sdk/typescript/use_k1_websocket.ts`
  - useK1WebSocket, useTokenStreaming hooks, connection state, useEffect cleanup

- **Client SDK** → Message Serialization
  - File: `sdk/typescript/serialization.ts`
  - serializeEnvelope, deserializeEnvelope, FlatBuffers builder/reader, ArrayBuffer


---

## Usage Guidelines

1. **Before Development**: Review relevant ADRs to understand architectural decisions and constraints
2. **During Development**: Reference specific ADR sections for implementation details and patterns
3. **Code Reviews**: Verify implementations align with ADR specifications
4. **Updates**: If you modify an ADR, regenerate this file using `python scripts/generate_layer_adr_references.py`

## Legend

- **Family**: High-level architectural area (e.g., Actor Fabric, Bridge, K0 Core)
- **Components**: Specific implementation components covered by the ADR
- **File**: Python module path where component is implemented
- **N/A ADRs**: Cross-cutting concerns that apply to all layers

---

*This file is auto-generated. Do not edit manually. Regenerate using:*
```bash
python scripts/generate_layer_adr_references.py
```