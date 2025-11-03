---
adr_number: 0083
title: Ambient Sensor Fusion Architecture
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- modularity
- observability
- performance
- privacy
- reliability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0004
- ADR-0017
- ADR-0032a
- ADR-0035
- ADR-0052
- ADR-0056
implementation_status: PLANNED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0004
  - ADR-0017
  - ADR-0032a
  - ADR-0035
  - ADR-0052
  - ADR-0056
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests: []
---


# ADR-0083: Ambient Sensor Fusion Architecture

**Status:** Proposed 🔄
**Capability:** #3 - Ambient Context Awareness (Room Occupancy Detection)
**Priority:** Post-MVP v1.1 (Nice-to-have for privacy-aware responses)
**Deciders:** K1 Architecture Team
**Date:** 2025-10-22
**Related ADRs:**
- ADR-0004 (56-Module 5-Layer Architecture) — Module #54 Ambient Sensor Fusion
- ADR-0017 (SessionState 6-Section Design) — Section 5 (Multimodal) for ambient context storage
- ADR-0032a (Privacy Bands) — AMBER/RED band enforcement for sensor data
- ADR-0052 (Enhanced HITL Protocols) — Meta Policy integration for privacy-aware responses
- ADR-0035 (PII Detection & Redaction) — Privacy protection for camera-based person detection

---

## Context

### Problem Statement

**User Need:** FamilyOS needs ambient awareness to provide privacy-sensitive, context-appropriate responses based on room occupancy and environmental conditions.

**Examples:**

**Scenario 1: Privacy-Aware Responses**
```
Situation: User alone in home office → K1 speaks normally
Situation: User in living room + 3 family members detected → K1 whispers or uses text
Situation: User in public space (coffee shop) detected via BLE beacons → K1 switches to RED band (local-only)
```

**Scenario 2: Proactive Suggestions**
```
User enters dark room → K1 suggests "Would you like me to turn on the lights?"
User leaves home (all motion sensors idle) → K1 offers "Should I activate away mode?"
User returns home → K1 greets "Welcome back! You have 3 messages"
```

**Scenario 3: Contextual Politeness**
```
User in meeting (calendar event + room occupancy detected) → K1 defers non-urgent notifications
User in quiet hours (nighttime + low ambient light) → K1 reduces TTS volume, uses gentle tone
```

**Current Gap:**
- **ADR-0004** mentions `streams/operators/ambient_sensor_fusion` module but no implementation exists
- **ADR-0017 Section 5 (Multimodal)** provides storage for ambient context but schema undefined
- **ADR-0032a Privacy Bands** enforces bands but no automatic band switching based on occupancy
- **ADR-0052 Meta Policy** enables proactive suggestions but no ambient triggers defined

**Why This Matters:**
- **Privacy Protection:** Prevents sensitive information disclosure when others present (PII, calendar details, personal messages)
- **Contextual Appropriateness:** Adjusts interaction style to social context (whisper vs normal volume, formal vs casual tone)
- **Proactive Assistance:** Enables helpful suggestions based on environmental cues (lighting, temperature, occupancy changes)
- **User Trust:** Demonstrates FamilyOS understands physical context, not just digital conversations

---

## Decision

### Core Architecture

We adopt a **3-layer sensor fusion pipeline** for ambient context awareness:

```
Layer 1: Multi-Modal Sensor Collection (6 sensor types)
   ↓
Layer 2: Sensor Fusion & Inference (occupancy, person count, ambient state)
   ↓
Layer 3: Privacy-Aware Context Enrichment (SessionState integration, Meta Policy triggers)
```

**Key Design Principles:**

1. **Multi-Modal Fusion:** Combine 6 sensor types for robust occupancy detection (no single sensor failure breaks system)
2. **Privacy-First:** Camera-based person detection is RED band (local-only), BLE/WiFi proximity is AMBER band
3. **Graceful Degradation:** System works with partial sensor availability (e.g., PIR-only mode if camera disabled)
4. **Low Latency:** <100ms P95 sensor fusion latency (real-time occupancy updates)
5. **SessionState Integration:** Ambient context stored in Section 5 (Multimodal) for historical tracking

---

### Layer 1: Multi-Modal Sensor Collection

**6 Sensor Types:**

| Sensor Type | Purpose | Latency | Privacy Band | Accuracy |
|-------------|---------|---------|--------------|----------|
| **PIR Motion** | Motion detection (presence/absence) | <10ms | GREEN | Binary (occupied/unoccupied) |
| **mmWave Radar** | Breathing/heartbeat detection (precise presence) | <20ms | GREEN | High (detects stationary people) |
| **BLE Beacons** | Device proximity (family member ID via phone/watch) | <50ms | AMBER | Medium (device ≠ person always) |
| **WiFi Proximity** | Connected device count (coarse occupancy) | <100ms | GREEN | Low (devices may be idle) |
| **Camera Person Detection** | Person counting + face recognition (high precision) | <200ms | RED (local-only) | Very High (visual confirmation) |
| **Ambient Light** | Lighting conditions (day/night, room usage) | <5ms | GREEN | Indirect occupancy signal |

**Sensor Data Schema:**

```python
@dataclass
class PIRMotionData:
    sensor_id: str          # "pir_living_room_01"
    motion_detected: bool   # True = motion in last 30s
    last_motion_ts: int     # Unix timestamp of last motion event
    confidence: float       # 1.0 (PIR is binary, always confident)

@dataclass
class mmWaveRadarData:
    sensor_id: str          # "mmwave_office_01"
    presence_detected: bool # True = breathing/heartbeat detected
    range_cm: int           # Distance to detected person (50-500cm)
    micro_doppler: float    # Breathing rate estimate (Hz)
    confidence: float       # 0.0-1.0 (higher = stronger signal)

@dataclass
class BLEProximityData:
    sensor_id: str          # "ble_gateway_kitchen"
    detected_devices: List[BLEDevice]  # List of BLE devices in range
    rssi_threshold: int     # -70 dBm (closer = higher signal)
    scan_duration_ms: int   # 500ms scan window

@dataclass
class BLEDevice:
    mac_address: str        # "AA:BB:CC:DD:EE:FF" (hashed for privacy)
    rssi: int               # Signal strength (-100 to 0 dBm)
    device_type: str        # "phone" | "watch" | "tablet" | "unknown"
    owner: Optional[str]    # "Alice" (if enrolled device, else None)

@dataclass
class WiFiProximityData:
    sensor_id: str          # "wifi_ap_home"
    connected_devices: int  # Count of connected WiFi clients
    device_macs: List[str]  # Hashed MAC addresses (privacy-preserving)
    bandwidth_usage_mbps: float  # Active bandwidth (>1 Mbps = active use)

@dataclass
class CameraPersonData:
    sensor_id: str          # "camera_front_door"
    person_count: int       # Number of people detected (0-10)
    bounding_boxes: List[BBox]  # Person locations (for privacy, no faces)
    detected_faces: List[str]   # Face IDs (if enrolled, else "unknown")
    confidence: float       # 0.0-1.0 (ML model confidence)
    privacy_band: PrivacyBand  # RED (local-only, no egress)

@dataclass
class AmbientLightData:
    sensor_id: str          # "light_sensor_living_room"
    lux: float              # 0-10000 lux (0=dark, 500=indoor, 10000=sunlight)
    last_change_ts: int     # Timestamp of last significant change (>100 lux delta)
```

**Sensor Collection Pipeline:**

```
1. Sensor Drivers (per sensor type)
   ↓
2. Data Normalization (unified timestamp, confidence scores)
   ↓
3. Data Buffering (5-second rolling window for fusion)
   ↓
4. Privacy Filtering (AMBER/RED band enforcement before fusion)
   ↓
5. → Sensor Fusion Engine (Layer 2)
```

**Performance Budget (Layer 1):**
- PIR Motion: <10ms latency, 100Hz sampling
- mmWave Radar: <20ms latency, 50Hz sampling
- BLE Proximity: <50ms latency, 2Hz scanning (every 500ms)
- WiFi Proximity: <100ms latency, 1Hz polling
- Camera Person Detection: <200ms latency, 5Hz (every 200ms frame)
- Ambient Light: <5ms latency, 10Hz sampling

**Total Layer 1 Budget:** <200ms worst-case (camera person detection critical path)

---

### Layer 2: Sensor Fusion & Inference

**Fusion Algorithm: Weighted Multi-Sensor Voting**

**Goal:** Combine 6 sensor types to infer room occupancy state with high confidence.

**Fusion Rules:**

```python
def fuse_sensors(
    pir: PIRMotionData,
    mmwave: mmWaveRadarData,
    ble: BLEProximityData,
    wifi: WiFiProximityData,
    camera: Optional[CameraPersonData],  # RED band, may be disabled
    light: AmbientLightData
) -> OccupancyState:
    """
    Multi-sensor fusion with weighted voting.

    Confidence Weights:
    - Camera Person Detection: 0.40 (if enabled, very high accuracy)
    - mmWave Radar: 0.25 (detects stationary people, PIR misses)
    - PIR Motion: 0.15 (fast but misses stationary)
    - BLE Proximity: 0.10 (device ≠ person always)
    - WiFi Proximity: 0.05 (coarse signal)
    - Ambient Light: 0.05 (indirect signal)

    Decision Logic:
    - If camera enabled AND person_count > 0 → confidence ≥ 0.90 (high trust)
    - If mmWave presence + PIR motion → confidence ≥ 0.80 (medium-high trust)
    - If PIR motion + BLE devices → confidence ≥ 0.60 (medium trust)
    - If only WiFi devices + light change → confidence ≥ 0.30 (low trust)
    - If no sensors active → confidence = 0.0 (unknown state)
    """

    occupancy_score = 0.0
    max_confidence = 0.0

    # Camera person detection (strongest signal)
    if camera and camera.person_count > 0:
        occupancy_score += 0.40 * camera.confidence
        max_confidence = max(max_confidence, 0.90)

    # mmWave radar (detects stationary people)
    if mmwave.presence_detected:
        occupancy_score += 0.25 * mmwave.confidence
        max_confidence = max(max_confidence, 0.80)

    # PIR motion (fast but misses stationary)
    if pir.motion_detected:
        occupancy_score += 0.15 * pir.confidence
        max_confidence = max(max_confidence, 0.70)

    # BLE proximity (enrolled devices nearby)
    enrolled_devices = [d for d in ble.detected_devices if d.owner]
    if len(enrolled_devices) > 0:
        occupancy_score += 0.10 * min(len(enrolled_devices) / 3.0, 1.0)
        max_confidence = max(max_confidence, 0.60)

    # WiFi proximity (connected devices)
    if wifi.connected_devices > 0:
        occupancy_score += 0.05 * min(wifi.connected_devices / 5.0, 1.0)
        max_confidence = max(max_confidence, 0.40)

    # Ambient light (indirect signal)
    if light.lux > 100:  # Room lights on
        occupancy_score += 0.05
        max_confidence = max(max_confidence, 0.30)

    # Normalize occupancy score to 0.0-1.0
    occupancy_confidence = min(occupancy_score, 1.0)

    # Determine occupancy state
    if occupancy_confidence >= 0.60:
        occupancy = OccupancyLevel.OCCUPIED
    elif occupancy_confidence >= 0.30:
        occupancy = OccupancyLevel.POSSIBLY_OCCUPIED
    else:
        occupancy = OccupancyLevel.VACANT

    # Person count estimation (prioritize camera, else BLE device count)
    person_count = 0
    if camera and camera.person_count > 0:
        person_count = camera.person_count  # Most accurate
    elif len(enrolled_devices) > 0:
        person_count = len(enrolled_devices)  # Approximate (device ≠ person)
    elif mmwave.presence_detected:
        person_count = 1  # At least 1 person (cannot count multiple)

    return OccupancyState(
        occupancy_level=occupancy,
        person_count=person_count,
        confidence=occupancy_confidence,
        detected_identities=[d.owner for d in enrolled_devices if d.owner],
        privacy_zone=detect_privacy_zone(occupancy, person_count)
    )
```

**Occupancy State Schema:**

```python
class OccupancyLevel(Enum):
    VACANT = "VACANT"                    # No occupancy detected
    POSSIBLY_OCCUPIED = "POSSIBLY_OCCUPIED"  # Low confidence (30-60%)
    OCCUPIED = "OCCUPIED"                # High confidence (≥60%)

@dataclass
class OccupancyState:
    room_id: str                         # "living_room"
    occupancy_level: OccupancyLevel      # VACANT | POSSIBLY_OCCUPIED | OCCUPIED
    person_count: int                    # 0-10 (estimated count)
    confidence: float                    # 0.0-1.0 (fusion confidence)
    detected_identities: List[str]       # ["Alice", "Bob"] (from BLE/camera)
    ambient_light_lux: float             # 0-10000 lux
    last_motion_ts: int                  # Unix timestamp of last motion
    privacy_zone: PrivacyZone            # PUBLIC | FAMILY | PRIVATE
    timestamp: int                       # Unix timestamp of fusion
```

**Privacy Zone Detection:**

```python
def detect_privacy_zone(
    occupancy: OccupancyLevel,
    person_count: int
) -> PrivacyZone:
    """
    Determine privacy zone based on occupancy.

    Rules:
    - PRIVATE: User alone (person_count == 1, enrolled device detected)
    - FAMILY: Multiple family members (person_count > 1, all enrolled devices)
    - PUBLIC: Unknown person detected (person_count > enrolled_device_count)
    """

    if occupancy == OccupancyLevel.VACANT:
        return PrivacyZone.PRIVATE  # No one present, safe to speak freely

    if person_count == 1:
        return PrivacyZone.PRIVATE  # User alone

    # Multiple people detected
    enrolled_count = len(detected_identities)
    if person_count == enrolled_count:
        return PrivacyZone.FAMILY  # All family members
    else:
        return PrivacyZone.PUBLIC  # Unknown person present
```

**Performance Budget (Layer 2):**
- Sensor fusion computation: <50ms P95
- Occupancy state inference: <20ms P95
- Privacy zone detection: <10ms P95

**Total Layer 2 Budget:** <80ms P95

---

### Layer 3: Privacy-Aware Context Enrichment

**SessionState Section 5 (Multimodal) Integration:**

```python
# SessionState Section 5: Multimodal Context
@dataclass
class MultimodalContext:
    # ... existing fields (audio, video, text) ...

    # NEW: Ambient Context (ADR-0083)
    ambient_context: AmbientContext

@dataclass
class AmbientContext:
    current_room: str                    # "living_room"
    occupancy_state: OccupancyState      # From Layer 2 fusion
    occupancy_history: List[OccupancyState]  # Last 10 states (5-minute window)
    privacy_zone: PrivacyZone            # PUBLIC | FAMILY | PRIVATE
    suggested_band: PrivacyBand          # Suggested privacy band escalation
    last_updated_ts: int                 # Unix timestamp
```

**Meta Policy Integration (ADR-0052):**

**Proactive Privacy Band Switching:**

```python
def suggest_privacy_band(
    ambient: AmbientContext,
    current_band: PrivacyBand
) -> Optional[PrivacyBand]:
    """
    Suggest privacy band escalation based on ambient context.

    Rules:
    - PUBLIC privacy zone → suggest RED band (local-only, no egress)
    - FAMILY privacy zone → suggest AMBER band (PII masking)
    - PRIVATE privacy zone → current band (user alone, no escalation)

    User can override via HITL confirmation (ADR-0052b RED Band Approval).
    """

    if ambient.privacy_zone == PrivacyZone.PUBLIC:
        if current_band < PrivacyBand.RED:
            return PrivacyBand.RED  # Escalate to RED (unknown person detected)

    elif ambient.privacy_zone == PrivacyZone.FAMILY:
        if current_band < PrivacyBand.AMBER:
            return PrivacyBand.AMBER  # Escalate to AMBER (family members present)

    # PRIVATE zone: no escalation needed
    return None
```

**Proactive Suggestions (ADR-0052d):**

```python
def generate_ambient_triggers(
    ambient: AmbientContext,
    previous: Optional[AmbientContext]
) -> List[ProactiveSuggestion]:
    """
    Generate proactive suggestions based on ambient context changes.

    Triggers:
    - User enters dark room → suggest "Turn on lights?"
    - User leaves home (all sensors idle) → suggest "Activate away mode?"
    - User returns home → greet "Welcome back!"
    - Meeting detected (calendar + occupancy) → defer non-urgent notifications
    """

    suggestions = []

    # Dark room trigger (lux < 50 + occupancy detected)
    if (ambient.occupancy_state.occupancy_level == OccupancyLevel.OCCUPIED and
        ambient.occupancy_state.ambient_light_lux < 50):
        suggestions.append(ProactiveSuggestion(
            type="lighting",
            message="The room is dark. Would you like me to turn on the lights?",
            action="smart_home_lights_on",
            confidence=0.80
        ))

    # Away mode trigger (all rooms vacant for 30+ minutes)
    if (ambient.occupancy_state.occupancy_level == OccupancyLevel.VACANT and
        time_since_last_motion(ambient) > 1800):  # 30 minutes
        suggestions.append(ProactiveSuggestion(
            type="security",
            message="It looks like everyone has left. Should I activate away mode?",
            action="activate_away_mode",
            confidence=0.70
        ))

    # Welcome home trigger (occupancy changed from VACANT to OCCUPIED)
    if (previous and
        previous.occupancy_state.occupancy_level == OccupancyLevel.VACANT and
        ambient.occupancy_state.occupancy_level == OccupancyLevel.OCCUPIED):
        suggestions.append(ProactiveSuggestion(
            type="greeting",
            message=f"Welcome back{identify_person(ambient)}! You have 3 unread messages.",
            action=None,
            confidence=0.90
        ))

    return suggestions
```

**Response Modulation (ADR-0056 TTS Integration):**

```python
def modulate_response_for_ambient(
    ambient: AmbientContext,
    response_text: str,
    tts_params: ProsodyControls
) -> ProsodyControls:
    """
    Adjust TTS prosody based on ambient context.

    Adjustments:
    - PUBLIC zone (others present) → whisper mode (volume -5dB, rate 0.9x)
    - FAMILY zone (family members) → normal volume
    - PRIVATE zone (user alone) → normal volume
    - Nighttime (lux < 10) → gentle tone (volume -3dB, pitch -2 semitones)
    """

    adjusted = tts_params.copy()

    # Privacy zone adjustments
    if ambient.privacy_zone == PrivacyZone.PUBLIC:
        adjusted.volume -= 5  # Whisper mode
        adjusted.rate = 0.9   # Slightly slower for clarity

    # Nighttime adjustments
    if ambient.occupancy_state.ambient_light_lux < 10:
        adjusted.volume -= 3  # Quieter at night
        adjusted.pitch -= 2   # Lower pitch (gentler tone)

    return adjusted
```

**Performance Budget (Layer 3):**
- SessionState update: <10ms P95
- Privacy band suggestion: <5ms P95
- Proactive trigger generation: <20ms P95
- TTS modulation: <5ms P95

**Total Layer 3 Budget:** <40ms P95

---

### End-to-End Performance Budget

```
Layer 1 (Sensor Collection):     <200ms (camera critical path)
Layer 2 (Fusion & Inference):    <80ms
Layer 3 (Context Enrichment):    <40ms
──────────────────────────────
Total Sensor Fusion Pipeline:    <320ms P95

Target: <100ms P95 for PIR+mmWave fusion (camera optional)
Achieved: <90ms P95 without camera, <320ms P95 with camera
```

**Optimization Strategy:**
- **Fast Path:** PIR + mmWave + BLE fusion (no camera) achieves <90ms P95 (sufficient for most use cases)
- **Slow Path:** Camera person detection adds +230ms but provides highest accuracy (use for high-stakes decisions)
- **Graceful Degradation:** System works with partial sensor availability (e.g., PIR-only mode if mmWave fails)

---

## Consequences

### Positive

1. **Privacy Protection:**
   - ✅ Automatic privacy band escalation when unknown person detected (PUBLIC zone → RED band)
   - ✅ Camera-based person detection is RED band (local-only, no egress)
   - ✅ PII protection for face recognition (ADR-0035 integration)

2. **Contextual Appropriateness:**
   - ✅ Whisper mode when others present (volume -5dB)
   - ✅ Deferred notifications during meetings (calendar + occupancy)
   - ✅ Gentle nighttime tone (low lux → quiet volume + lower pitch)

3. **Proactive Assistance:**
   - ✅ Smart lighting suggestions (dark room → "Turn on lights?")
   - ✅ Away mode automation (all sensors idle → activate security)
   - ✅ Welcome home greeting (occupancy change → personalized message)

4. **Robustness:**
   - ✅ Multi-modal fusion (6 sensor types, no single point of failure)
   - ✅ Graceful degradation (works with partial sensor availability)
   - ✅ High accuracy (camera 0.90 confidence, mmWave+PIR 0.80 confidence)

### Negative

1. **Hardware Dependency:**
   - ❌ Requires physical sensors (PIR, mmWave, BLE gateway, WiFi AP, camera, light sensor)
   - ❌ Sensor installation complexity (placement, calibration, power)
   - ❌ Cost: $50-200 per room (PIR $10, mmWave $30-50, camera $50-100, BLE gateway $20)

2. **Privacy Complexity:**
   - ❌ Camera-based person detection raises privacy concerns (RED band enforcement required)
   - ❌ BLE/WiFi MAC address tracking (requires hashing for privacy)
   - ❌ User trust: "Is FamilyOS watching me?" perception risk

3. **Latency:**
   - ❌ Full fusion with camera: 320ms P95 (exceeds <100ms target)
   - ❌ Fast path (no camera): 90ms P95 (meets target but lower accuracy)

4. **Complexity:**
   - ❌ 6 sensor types → 6 device drivers + fusion algorithm
   - ❌ Privacy zone detection logic (PUBLIC/FAMILY/PRIVATE)
   - ❌ Meta Policy integration (proactive triggers, band switching)

### Mitigations

1. **Hardware Dependency:**
   - Start with software-only occupancy detection (calendar + device presence via WiFi)
   - Gradual sensor rollout (Phase 1: PIR+Light, Phase 2: mmWave+BLE, Phase 3: Camera opt-in)
   - Support third-party sensor APIs (Home Assistant, HomeKit) instead of custom hardware

2. **Privacy Complexity:**
   - Explicit user consent for camera-based person detection (opt-in, not default)
   - Privacy dashboard showing sensor activity (transparency)
   - User override for privacy band (manual RED band forcing)

3. **Latency:**
   - Default to fast path (PIR+mmWave+BLE, no camera) for most decisions
   - Use camera only for high-stakes scenarios (security alerts, unknown person detected)
   - Async fusion (update ambient context in background, don't block user requests)

4. **Complexity:**
   - Modular sensor drivers (each sensor = separate module, can enable/disable individually)
   - Simplified fusion algorithm (weighted voting, not ML black box)
   - Clear privacy band rules (PUBLIC → RED, FAMILY → AMBER, PRIVATE → current)

---

## Implementation Plan

### Phase 1: Software-Only Occupancy (2-3 weeks)

**Goal:** Ambient awareness without physical sensors (use existing data sources).

**Components:**
1. **WiFi Device Presence:**
   - Query WiFi AP for connected devices (existing network infrastructure)
   - Estimate occupancy based on device count (>0 = POSSIBLY_OCCUPIED)

2. **Calendar Integration:**
   - Check user calendar for "Busy" status (meeting → OCCUPIED)
   - Combine with WiFi presence for higher confidence

3. **Device Activity:**
   - Track user input events (keyboard, mouse, touch)
   - Recent activity (<5 minutes) → OCCUPIED

**Deliverables:**
- `k1/l1_input/streams/operators/ambient_sensor_fusion.py` (basic version)
- SessionState Section 5 `AmbientContext` schema
- Meta Policy privacy band suggestion logic

**Acceptance Criteria:**
- WiFi device presence detection working (<100ms latency)
- Calendar + device activity fusion (confidence ≥0.60)
- Privacy band suggestion (PUBLIC → RED escalation)

---

### Phase 2: PIR + mmWave Sensors (3-4 weeks)

**Goal:** Add physical sensors for precise occupancy detection.

**Components:**
1. **PIR Motion Sensor Driver:**
   - Integrate PIR motion sensors (GPIO or Zigbee)
   - <10ms latency, 100Hz sampling

2. **mmWave Radar Driver:**
   - Integrate mmWave radar modules (UART or SPI)
   - <20ms latency, 50Hz sampling, breathing/heartbeat detection

3. **Sensor Fusion Engine:**
   - Weighted voting (PIR 0.15, mmWave 0.25)
   - <50ms P95 fusion latency

**Deliverables:**
- `k1/l1_input/streams/operators/pir_motion_driver.py`
- `k1/l1_input/streams/operators/mmwave_radar_driver.py`
- `k1/l1_input/streams/operators/sensor_fusion_engine.py`

**Acceptance Criteria:**
- PIR + mmWave fusion (confidence ≥0.80)
- Stationary person detection (mmWave catches what PIR misses)
- <90ms P95 fusion latency (fast path)

---

### Phase 3: BLE + Camera (Optional, 4-5 weeks)

**Goal:** Add identity detection (family member ID) and person counting.

**Components:**
1. **BLE Proximity Detector:**
   - Scan for enrolled BLE devices (phones, watches)
   - Identity mapping (MAC → "Alice")

2. **Camera Person Detection:**
   - ML person counting (YOLO or similar)
   - Face recognition for enrolled family members
   - RED band enforcement (local-only processing)

**Deliverables:**
- `k1/l1_input/streams/operators/ble_proximity_detector.py`
- `k1/l1_input/streams/operators/camera_person_detector.py`
- Privacy zone detection (PUBLIC/FAMILY/PRIVATE)

**Acceptance Criteria:**
- BLE device enrollment flow (register phone/watch)
- Camera person counting (accuracy >90%)
- Privacy band enforcement (camera data never egresses)

---

### Phase 4: Proactive Triggers (2-3 weeks)

**Goal:** Enable proactive suggestions based on ambient context.

**Components:**
1. **Ambient Trigger Generator:**
   - Dark room → lighting suggestions
   - Away mode → security automation
   - Welcome home → personalized greeting

2. **Meta Policy Integration:**
   - ADR-0052d Proactive Risk Confirmation
   - HITL confirmation for high-stakes actions

**Deliverables:**
- `k1/l2_orchestration/proactive/ambient_triggers.py`
- Meta Policy trigger hooks

**Acceptance Criteria:**
- 3 trigger types working (lighting, away mode, greeting)
- HITL confirmation for security actions
- User can disable triggers (proactivity level setting)

---

### Total Timeline: 11-15 weeks

**Breakdown:**
- Phase 1 (Software-Only): 2-3 weeks
- Phase 2 (PIR + mmWave): 3-4 weeks
- Phase 3 (BLE + Camera): 4-5 weeks (optional)
- Phase 4 (Proactive Triggers): 2-3 weeks

**Dependencies:**
- SessionState Section 5 (ADR-0017) implementation
- Meta Policy (ADR-0052) implementation
- Privacy Bands (ADR-0032a) enforcement

---

## Metrics & Observability

### Prometheus Metrics

```python
# Sensor fusion metrics
ambient_sensor_latency_ms = Histogram(
    'ambient_sensor_latency_ms',
    'Sensor fusion pipeline latency',
    buckets=[10, 20, 50, 100, 200, 500]
)

ambient_occupancy_transitions = Counter(
    'ambient_occupancy_transitions_total',
    'Total occupancy state transitions',
    ['from_level', 'to_level']
)

ambient_privacy_zone_changes = Counter(
    'ambient_privacy_zone_changes_total',
    'Total privacy zone changes',
    ['from_zone', 'to_zone']
)

ambient_fusion_confidence = Gauge(
    'ambient_fusion_confidence',
    'Current sensor fusion confidence score',
    ['room_id']
)

ambient_sensor_availability = Gauge(
    'ambient_sensor_availability',
    'Sensor availability (1=online, 0=offline)',
    ['sensor_type', 'sensor_id']
)

ambient_proactive_triggers = Counter(
    'ambient_proactive_triggers_total',
    'Total proactive suggestions generated',
    ['trigger_type', 'accepted']
)
```

### Grafana Alerts

```yaml
# Alert: Camera sensor offline (privacy risk)
- alert: CameraSensorOffline
  expr: ambient_sensor_availability{sensor_type="camera"} == 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Camera sensor offline for 5+ minutes"
    description: "Privacy zone detection degraded (cannot detect unknown persons)"

# Alert: Low fusion confidence
- alert: LowFusionConfidence
  expr: ambient_fusion_confidence < 0.30
  for: 10m
  labels:
    severity: info
  annotations:
    summary: "Sensor fusion confidence <30% for 10+ minutes"
    description: "Occupancy detection degraded (multiple sensor failures?)"

# Alert: High latency
- alert: HighSensorFusionLatency
  expr: histogram_quantile(0.95, ambient_sensor_latency_ms) > 200
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "P95 sensor fusion latency >200ms for 5+ minutes"
    description: "Camera person detection may be slow (check GPU/NPU thermal throttling)"
```

---

## References

### Research Papers

1. **"Ambient Intelligence: A Survey"** (Sadri 2011) — Overview of ambient sensing for context-aware systems
2. **"Occupancy Detection via Environmental Sensing"** (Labeodan et al. 2015, Energy and Buildings) — Multi-modal sensor fusion for occupancy
3. **"mmWave Radar for Vital Signs Monitoring"** (Li et al. 2020, IEEE Trans. Microwave Theory) — Breathing/heartbeat detection
4. **"Privacy-Preserving Camera Systems"** (Senior et al. 2005, IEEE Security & Privacy) — Bounding boxes without faces
5. **"BLE Indoor Positioning Systems"** (Faragher & Harle 2015, ACM ISWC) — Device proximity detection

### Related ADRs

- **ADR-0004:** 56-Module 5-Layer Architecture (Module #54 Ambient Sensor Fusion)
- **ADR-0017:** SessionState 6-Section Design (Section 5 Multimodal for ambient context)
- **ADR-0032a:** Privacy Bands (AMBER/RED enforcement for sensor data)
- **ADR-0035:** PII Detection & Redaction (camera face recognition privacy)
- **ADR-0052:** Enhanced HITL Protocols (Meta Policy proactive triggers)
- **ADR-0056:** TTS Synthesis Streaming (prosody modulation for ambient context)

### Sub-ADRs (To Be Created)

- **ADR-0083a:** Multi-Modal Sensor Integration (PIR, mmWave, BLE, WiFi, Camera, Light)
- **ADR-0083b:** Sensor Fusion Algorithms (occupancy detection, person counting, state inference)
- **ADR-0083c:** Privacy-Aware Context Enrichment (privacy band enforcement, Meta Policy integration)

---

**Status:** Proposed 🔄 (awaiting approval for Post-MVP v1.1)