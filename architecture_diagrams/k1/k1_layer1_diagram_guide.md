# K1 Layer 1 Architecture Diagram — Usage Guide

**Diagram Location:** `architecture_diagrams/k1/k1_layer1_architecture.mmd`
**Diagram ID:** `f81e301d-1cab-4fc8-90ae-c2c5e5390942`
**Created:** 2025-10-23
**Status:** ✅ Validated (no issues)

---

## 📊 Diagram Statistics

- **Nodes:** 31 components
- **Edges:** 44 data flows
- **Subgraphs:** 10 logical groupings
- **Top Hubs (by connectivity):**
  1. **EventBus** (9 connections) — Central communication backbone
  2. **Dispatcher** (8 connections) — Input routing hub
  3. **ContextEnricher** (5 connections) — Sensor fusion point
  4. **WebSocket** (5 connections) — External bidirectional interface
  5. **MetaPolicy** (4 connections) — Privacy enforcement gateway

---

## 🎯 Key Insights from Diagram

### 1. **Bidirectional I/O Flow**

- ✅ **Input Path:** User → WebSocket/REST → Dispatcher → Operators → EventBus → Layer 2
- ✅ **Output Path:** Layer 2 → EventBus → TTS/TokenStream → WebSocket → User
- ✅ **Barge-in Loop:** User speech during TTS triggers immediate interruption

### 2. **API Surface Boundaries**

- 📥 **INPUT APIs:** WebSocket `/ws/audio`, REST `/input/text`, Sensor drivers
- 📤 **OUTPUT APIs:** WebSocket audio/tokens, SSE `/events`, Event Bus topics

### 3. **Privacy Enforcement**

- 🔒 **MetaPolicy** acts as gateway before EventBus publication
- 🔒 **Privacy Bands:** RED (GPS), AMBER (WiFi/BLE hashed), GREEN (IP geo)
- 🔒 **ContextEnricher** aggregates sensor data with privacy-aware fusion

### 4. **Performance Critical Paths**

- ⚡ **Hot Path:** WebSocket → Dispatcher → VAD → ASR → IntentRouter → EventBus (<10ms P95)
- ⚡ **TTS Path:** EventBus → TTS → Prosody → WebSocket (<300ms P95)
- ⚡ **Token Streaming:** EventBus → TokenStream → WebSocket (<10ms per token)

---

## 🔍 How to Use This Diagram

### For Architecture Review

```bash
# View diagram summary
mmd_summary f81e301d-1cab-4fc8-90ae-c2c5e5390942

# Find connections between components
mmd_neighbors f81e301d-1cab-4fc8-90ae-c2c5e5390942 EventBus both

# Trace data flow paths
mmd_paths f81e301d-1cab-4fc8-90ae-c2c5e5390942 User L2Orchestrator
```

### For API Design

- **Identify exposed endpoints:** Look for `InputAPI` and `OutputAPI` subgraphs
- **Trace data flow:** Follow edges from external systems to EventBus
- **Verify privacy:** Ensure all paths go through `MetaPolicy` before EventBus

### For Performance Analysis

- **Critical path:** User → Dispatcher → VAD → ASR → IntentRouter → MetaPolicy → EventBus
- **Bottleneck risks:** ASR (<80ms), TTS (<300ms), EventBus publish (<1ms)
- **Optimization targets:** Zero-copy FlatBuffers, async operators, stream pipelining

### For Testing

- **Input Path Test:** Mock WebSocket → verify EventBus receives `UserInputEvent`
- **Output Path Test:** Publish `ResponseEvent` → verify WebSocket delivers TTS audio
- **Barge-in Test:** Send barge-in signal during TTS → verify immediate stop

---

## 📚 Companion Documentation

| Document | Purpose |
|----------|---------|
| **LAYER1_API_SPECIFICATION.md** | Detailed API schemas, performance SLOs, integration points |
| **layer1_adr_map.md** | 91 ADRs mapped to Layer 1 modules |
| **README_STRUCTURE.md** | Folder structure, development guidelines |
| **ADR-0004** | 5-layer architecture definition |
| **ADR-0004a** | Event Bus (L1↔L2) specification |
| **ADR-0015** | WebSocket Binary Protocol |
| **ADR-0024** | Performance Budgets (<10ms P95) |

---

## 🚀 Next Steps

1. **Implement Stream Switch:** Create `Dispatcher`, `SessionMgr`, `TransitionMgr` (ADR-0004, 0015)
2. **Implement Voice Pipeline:** VAD, ASR, TTS, Speaker ID (ADR-0056a/d/f, 0073)
3. **Implement Sensor Fusion:** Location, Motion, BLE operators (ADR-0085, 0083a, 0044)
4. **Implement EventBus Integration:** FlatBuffers zero-copy publish/subscribe (ADR-0004a, 0011)
5. **Implement Privacy Enforcement:** MetaPolicy with RED/AMBER/GREEN bands (ADR-0044)
6. **Test End-to-End Flow:** User input → Layer 2 → TTS output with <10ms P95 latency

---

## ✅ Validation Status

- ✅ **Mermaid Syntax:** No issues (validated with `mmd_validate`)
- ✅ **Node Count:** 31 components (matches structure)
- ✅ **Edge Count:** 44 data flows (comprehensive coverage)
- ✅ **Subgraph Depth:** 2 levels (clear hierarchy)
- ✅ **ADR Alignment:** 15+ ADRs referenced in diagram header

**Ready for implementation!** 🎯
