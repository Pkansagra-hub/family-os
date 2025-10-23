# Layer 1 - Input Processing

**Complete Layer 1 folder structure with ADR-referenced Python files**

## 📋 Overview

**Layer:** 1 (Input Processing)
**Performance Budget:** <10ms P95
**Modules:** 4 core modules + sensors + location
**Primary Function:** Unified multi-modal input bus + 3-tier intent routing

## 📁 Folder Structure

```
k1/l1_input/
├── ADR_REFERENCE.md                    # Auto-generated ADR inventory (91 ADRs)
├── layer1_adr_map.md                   # Comprehensive ADR mapping
├── README.md                           # This file
├── __init__.py                         # Layer 1 package init
│
├── streams/                            # Stream Processing (ADR-0004, ADR-0004f)
│   ├── __init__.py
│   ├── stream_switch/                  # Multi-Modal Input Bus (<5ms P95)
│   │   ├── __init__.py
│   │   ├── README.md
│   │   ├── bus.py                      # Multi-modal bus (ADR-0004f, ADR-0015)
│   │   ├── transition_manager.py       # Modality transitions (ADR-0004f)
│   │   └── context_preserver.py        # Cross-modal context (ADR-0004f)
│   │
│   └── operators/                      # Stream Operators (ADR-0004, ADR-0024)
│       ├── __init__.py
│       ├── vad_detector.py             # Voice Activity Detection (ADR-0024, ADR-0054a)
│       ├── asr_operator.py             # ASR (<80ms P95) (ADR-0024, ADR-0056a)
│       ├── tts_operator.py             # TTS (<300ms P95) (ADR-0024, ADR-0056d, ADR-0056f)
│       ├── speaker_identifier.py       # Voice biometrics (ADR-0082, ADR-0082a)
│       ├── speaker_enrollment.py       # Speaker enrollment (ADR-0082a)
│       │
│       ├── location/                   # Location Awareness (ADR-0085a)
│       │   ├── __init__.py
│       │   ├── gps_tracker.py          # GPS tracking (RED band)
│       │   ├── wifi_triangulator.py    # WiFi triangulation (AMBER band)
│       │   ├── ip_geolocator.py        # IP geolocation (GREEN band)
│       │   └── coarse_classifier.py    # HOME/WORK/TRAVELING (GREEN band)
│       │
│       ├── ble/                        # BLE Proximity (ADR-0085b)
│       │   ├── __init__.py
│       │   ├── beacon_advertiser.py    # iBeacon advertising
│       │   └── beacon_scanner.py       # BLE proximity detection
│       │
│       └── motion/                     # Motion Context (ADR-0085)
│           ├── __init__.py
│           ├── context_detector.py     # 7 contexts (STATIONARY, IN_POCKET, etc.)
│           └── periodicity_detector.py # FFT walking/running detection
│
├── orchestration/                      # Intent & Policy (ADR-0004, ADR-0024)
│   ├── __init__.py
│   ├── intent_router.py                # 3-tier intent (<50ms P95) (ADR-0024, ADR-0024b)
│   └── meta_policy.py                  # Proactivity & clarification (ADR-0017, ADR-0052c)
│
└── sensors/                            # Ambient Sensors (ADR-0083)
    ├── __init__.py
    ├── pir_motion_driver.py            # PIR motion sensor (ADR-0083a)
    ├── mmwave_radar_driver.py          # mmWave radar sensor (ADR-0083a)
    ├── ble_proximity_driver.py         # BLE proximity detector (ADR-0083a)
    └── sensor_fusion_engine.py         # Weighted Bayesian fusion (ADR-0083b)
```

## 🔑 Key ADR References

### Primary Layer 1 ADRs
- **ADR-0004**: 52-Module 5-Layer Architecture (Layer 1 definition)
- **ADR-0004a**: Layer 1-2 Communication (Event Bus)
- **ADR-0004b**: Layer Dependency Rules (L1→L5 only)
- **ADR-0004d**: Layer 1 Integration Tests
- **ADR-0004f**: Stream Switch (Multi-Modal Bus)

### Performance & Budgets
- **ADR-0024**: Performance budgets (Layer 1: <10ms P95 total)
- **ADR-0024b**: Component-level budgets (T1 10ms, T2 3ms, T3 40ms)

### Voice Pipeline
- **ADR-0056a**: ASR Ingress (frame handling, partial results)
- **ADR-0056d**: TTS Synthesis (prosody controls, SSML)
- **ADR-0056f**: Voice Persona Persistence (per-session continuity)

### Multi-Party Dialogue
- **ADR-0082**: Multi-Party Dialogue - Core Architecture
- **ADR-0082a**: Speaker Diarization - Voice Biometrics

### Ambient Sensors
- **ADR-0083**: Ambient Sensor Fusion - Sensor Drivers
- **ADR-0083a**: Sensor Drivers (PIR, mmWave, BLE)
- **ADR-0083b**: Sensor Fusion (Weighted Bayesian)

### Location & Proximity
- **ADR-0085**: Embodied Awareness - Core Architecture
- **ADR-0085a**: Location Awareness (GPS, WiFi, IP)
- **ADR-0085b**: BLE Proximity (beacon advertising/scanning)

### HITL & UX
- **ADR-0052c**: Nested Clarifications (QUD stack)
- **ADR-0052d**: Proactive Confirmation
- **ADR-0054a**: Implicit Pause (2s silence threshold)
- **ADR-0065a**: Streaming Text & Typing (<16ms)

**See `ADR_REFERENCE.md` for complete list of 91 ADRs**

## 📊 Performance Budgets (ADR-0024)

| Component | Budget | Typical | P95 | ADR |
|-----------|--------|---------|-----|-----|
| stream_switch | 5ms | 2ms | 3ms | ADR-0004 |
| VAD | N/A | 15ms | 20ms | ADR-0024 |
| ASR | N/A | 60ms | 80ms | ADR-0024 |
| TTS (first chunk) | N/A | 200ms | 300ms | ADR-0024 |
| intent_router (T1) | 10ms | 8ms | 10ms | ADR-0024b |
| intent_router (T2) | 3ms | 2ms | 3ms | ADR-0024b |
| intent_router (T3) | 45ms | 35ms | 40ms | ADR-0024b |
| meta_policy | 5ms | 3ms | 5ms | ADR-0004 |
| **Hot Path Total** | **<10ms** | **5ms** | **8ms** | **ADR-0024a** |

**Note:** ASR (80ms) is **NOT** part of hot path. Hot path = stream_switch (5ms) + intent_router T1/T2 (10ms) = **15ms** to Layer 2 EventBus.

## 🔄 Layer 1 → Layer 2 Integration (ADR-0004a)

**Layer 1 publishes events to Layer 2 Orchestration via EventBus:**

```
Layer 1 (Input)                  EventBus (L5)                Layer 2 (Orchestration)
─────────────────                ───────────────              ─────────────────────────
stream_switch    ──publish──>    UserInput event    ──subscribe──>  orchestrator
operators (ASR)  ──publish──>    ASRResult event    ──subscribe──>  dialogue manager
intent_router    ──publish──>    IntentDetected     ──subscribe──>  orchestrator
meta_policy      ──publish──>    ClarificationReq   ──subscribe──>  clarification protocol
operators (VAD)  ──publish──>    BargeIn event      ──subscribe──>  barge-in handler
```

**Key Constraints:**
1. **No direct L1→L2 imports** (enforced by import-linter, ADR-0004b)
2. **Event-driven only** (pub/sub pattern, zero coupling)
3. **Zero-copy** (FlatBuffers serialization, <1ms overhead, ADR-0011)
4. **Async delivery** (non-blocking, <5ms P95, ADR-0004a)

## 🧪 Testing Strategy (ADR-0004d)

**Location:** `tests/integration/layer1/`

1. **Event Publishing Tests:**
   - Verify Layer 1 publishes events to EventBus
   - Verify event schema (FlatBuffers validation)
   - Verify cognitive_trace_id propagation

2. **Intent Classification Tests:**
   - T1 rule-based accuracy (>95%)
   - T2 SLM accuracy (>90%)
   - T3 LLM fallback accuracy (>85%)
   - 3-tier fallback cascade

3. **Stream Processing Tests:**
   - Multi-modal input (audio + text)
   - VAD detection accuracy (>98%)
   - ASR accuracy (>90% WER)
   - TTS quality (MOS >4.0)

4. **Performance Tests:**
   - Layer 1 total budget <10ms P95
   - stream_switch <5ms P95
   - intent_router <50ms P95 (weighted)
   - meta_policy <5ms P95

5. **End-to-End Tests:**
   - User audio → ASR → intent → Layer 2 event
   - User text → intent → Layer 2 event
   - Barge-in → cancel → Layer 2 interrupt

## 📝 Development Guidelines

### Before Implementation

1. **Read Relevant ADRs:**
   - Check `layer1_adr_map.md` for module-specific ADRs
   - Read `ADR_REFERENCE.md` for comprehensive inventory
   - Review cross-cutting ADRs (Actor Model, FlatBuffers, etc.)

2. **Review Contracts:**
   - FlatBuffers schemas: `k1/contracts/flatbuffers/*.fbs`
   - Architecture contracts: `k1/contracts/architecture/*.yml`
   - Layer dependencies: `k1/contracts/architecture/layer_dependencies.yml`

3. **Performance Budgets:**
   - Check component budget in ADR-0024
   - Plan for <10ms P95 Layer 1 total
   - Profile early, optimize hot path

### During Implementation

1. **Follow ADR Patterns:**
   - Actor Model (ADR-0002): Pure actors, deterministic
   - FlatBuffers (ADR-0011): Zero-copy serialization
   - Event Bus (ADR-0004a): Layer 1→2 communication

2. **Add Observability:**
   - Prometheus metrics (ADR-0029): RED method (rate/error/duration)
   - Trace propagation (ADR-0030): cognitive_trace_id
   - Structured logging: Use structlog

3. **Respect Layer Boundaries:**
   - L1→L5 only (ADR-0004b)
   - No direct L1→L2 imports
   - Use EventBus for Layer 2 communication

### After Implementation

1. **Validate Performance:**
   - Run integration tests (ADR-0004d)
   - Verify <10ms P95 Layer 1 budget
   - Profile hot path

2. **Update Documentation:**
   - Update this README if structure changed
   - Update `layer1_adr_map.md` if ADR mappings changed
   - Add component-specific READMEs

3. **Add WARD Tests:**
   - Integration > unit tests
   - Use real components (no mock theater)
   - Test performance budgets

## 🔍 Quick Reference

### Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Import error from L2 | Use EventBus (ADR-0004a), no direct L1→L2 imports |
| Performance budget exceeded | Profile with py-spy, optimize hot path, check KV cache |
| FlatBuffers schema error | Validate schema with `flatc`, check file identifier |
| Event not received in L2 | Verify EventBus subscription, check topic/filter |

### Useful Commands

```bash
# Run Layer 1 integration tests
python -m ward test --path tests/integration/layer1/

# Validate FlatBuffers schemas
flatc --python k1/contracts/flatbuffers/*.fbs

# Check import violations
importlinter

# Profile performance
py-spy top --pid <pid>
```

## 📚 Additional Resources

- **Architecture Docs:** `docs/whiteboard.md` (21K spec)
- **Module Analysis:** `docs/k1_module_analysis.md` (52 modules)
- **Diagrams:** `architecture_diagrams/` (11 validated .mmd files)
- **Contracts:** `k1/contracts/` (FlatBuffers, architecture, API)
- **ADR Master:** `docs/architecture/decisions/` (all ADRs)

---

**Last Updated:** January 2025
**Status:** ✅ Complete folder structure with ADR-referenced files
**Files Created:** 25+ Python files with comprehensive ADR comments
**ADR Coverage:** 91 ADRs across 31 families
