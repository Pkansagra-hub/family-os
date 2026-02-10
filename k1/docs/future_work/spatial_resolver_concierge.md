# Spatial Resolver -- End-to-End Process (Concierge Integration)

**Status**: Extension work (zero core rewrites)
**Foundation ADR**: ADR-0085a (Device Presence Detection and Location Awareness)
**Depends on**: ADR-0042 (Privacy Classification), ADR-0050 (Multi-Device Sync)
**Diagram refs**: k1_cognitive_architecture_skeleton.mmd (SPATIAL_RESOLUTION subgraph), concierge.mmd (SPATIAL_RESOLUTION subgraph)

---

## 1. Problem Statement

The Concierge understands WHAT the user said (NLP pipeline) and WHEN they said it (Temporal Resolution Engine), but not WHERE they are physically. Without spatial awareness, the system cannot:

- Distinguish "turn off the lights" at home from at work
- Suppress notifications when the user is driving
- Adapt formality when the user is in a meeting room vs on the couch
- Trigger proactive context ("you are near the grocery store -- reminder: you need milk")

Two parallel spatial signals exist:

1. **Conversation-mentioned locations** -- NER LOC entities extracted from user text ("the kitchen", "mom's house"). Already implemented in `beliefs_active.mentioned_location` as a `MentionedLocation` dataclass with raw_text, location_type, entity_id, and confidence.
2. **Device physical location** -- GPS/WiFi/IP sensor data flowing through ADR-0085a's LocationTracker. NOT yet represented in SessionState.

This document specifies the end-to-end process that resolves device physical location into semantic spatial context within the Concierge, and identifies the SessionState plug-in point.

---

## 2. Data Flow Overview

```
  PATH A: Device Location               PATH B: Conversation Location
  (WHERE IS THE USER)                    (WHAT LOCATION DID THE USER MENTION)

+---------------------+               +---------------------------+
| Device Sensors       |               | User Utterance            |
| GPS, WiFi, IP, BLE   |               | "Smit is in San Francisco"|
| (ADR-0085a)          |               |                           |
+---------------------+               +---------------------------+
      |                                        |
      v                                        v
+---------------------+               +---------------------------+
| LocationTracker      |               | UltraBERT NER Pipeline    |
| (ADR-0085a)          |               | LOC entity extraction     |
| GPS->WiFi->IP        |               | (extracts "San Francisco")|
| fallback chain       |               +---------------------------+
+---------------------+                        |
      |                                        | MentionedLocation
      | CoarseLocation                         | {raw_text, type, entity_id}
      | {band, zone, motion}                   |
      v                                        v
+---------------------+               +---------------------------+
| SPATIAL ENGINE       |               | beliefs_active            |
| (Concierge)          |               | .mentioned_location       |
| 5-stage pipeline     |               | (already implemented)     |
+---------------------+               +---------------------------+
      |                                        |
      | DeviceSpatialContext                    |
      v                                        v
+---------------------+               +---------------------------+
| SessionState         |               | SessionState              |
| NEW: multimodal      |               | beliefs_active (8KB HOT)  |
| section (4KB HOT)    |               |                           |
| zone: "texas_home"   |               | loc: "San Francisco"      |
+---------------------+               +---------------------------+
      |                                        |
      +----------------+-----------------------+
                       |
                       v
           +------------------------+
           | LLM (via SessionState)  |
           | Sees BOTH independently |
           | Reasons: user is in TX, |
           | talking about someone   |
           | in SF -- no fusion      |
           +------------------------+
```

The two paths are **strictly independent**. They write to different SessionState sections, have different lifecycles, and are NEVER fused or cross-referenced by the Concierge. The LLM receives the full SessionState (including both `multimodal.spatial_context` and `beliefs_active.mentioned_location`) and performs its own reasoning. A user in Texas talking about Smit in San Francisco does not mean San Francisco is relevant to the device context.

---

## 3. ADR-0085a Foundation (What Already Exists)

ADR-0085a defines the full sensor-to-classifier pipeline. Key components:

### 3.1 LocationTracker

- **Fallback chain**: GPS (high accuracy) -> WiFi fingerprint (medium) -> IP geolocation (coarse)
- **Update interval**: 30-second heartbeat when active, 5-minute when backgrounded
- **Output**: `LocationReading(lat, lng, accuracy_m, source, timestamp_ms)`
- **Privacy**: Raw coordinates are RED band -- never stored in HOT/WARM, only processed through privacy transforms

### 3.2 CoarseLocationClassifier

- **Input**: LocationReading (RED band)
- **Output**: CoarseLocation (GREEN/AMBER band) -- semantic zone, not coordinates
- **Privacy transform**: `(lat, lng)` -> `{zone: "home", confidence: 0.95}` or `{zone: "work", motion: "stationary"}`
- **Zone types**: home, work, school, transit, known_place, unknown
- **Classification method**: Geofence matching against user-defined places (stored in K0)

### 3.3 DeviceHeartbeatProtocol

- **Cadence**: 30s active, 5min background, battery-aware backoff
- **Payload**: device_id, zone, motion_state, battery_level, connectivity
- **Transport**: Local bus event -> K0 sync (optional, per ADR-0050)

### 3.4 Privacy Bands for Location

| Band | Contains | Example | Retention |
|------|----------|---------|-----------|
| RED | Raw coordinates | (47.6062, -122.3321) | Ephemeral only, never persisted |
| AMBER | Named place | "Woodinville QFC" | Session-scoped, evictable |
| GREEN | Semantic zone | "grocery_store" | Persistent, syncable |

---

## 4. Spatial Engine Pipeline (5 Stages)

The Spatial Engine is a 5-component subgraph within the Concierge, parallel to the existing Temporal Resolution Engine.

### Stage 1: LOCATION_INGRESS

- **Input**: Raw `LocationReading` from ADR-0085a LocationTracker
- **Responsibility**: Rate limiting, deduplication, staleness check
- **Output**: Validated `LocationReading` (still RED band)
- **Invariant**: No RED-band data leaves this stage without privacy transform

### Stage 2: LOCATION_RESOLVER

- **Input**: Validated LocationReading (from Ingress -- device sensors ONLY)
- **Responsibility**: Resolve device coordinates against Place Registry to produce a semantic zone. Does NOT read or cross-reference `beliefs_active.mentioned_location` -- that is conversation context handled by the NER pipeline independently.
- **Output**: `ResolvedLocation(zone, place_name, confidence, source)`
- **Key principle**: This stage answers ONLY "where is the device right now?" It never attempts to merge conversation-mentioned locations with device location. The LLM handles that reasoning when it reads both SessionState sections.

### Stage 3: PLACE_REGISTRY

- **Input**: Lookup requests from Location Resolver
- **Responsibility**: Maintains known places (geofences, semantic labels, associated entities)
- **Storage**: K0 storage table `st_places` (synced across devices per ADR-0050)
- **Entity shape**:

  ```
  Place {
    place_id: string
    label: string          # "home", "John's school", "QFC Woodinville"
    zone_type: string      # home, work, school, transit, commercial, unknown
    geofence: GeoCircle    # center + radius_m (RED band, K0 only)
    user_label: string     # User-given name (optional)
    associated_entities: [entity_id]  # family members, devices
    privacy_band: GREEN    # Zone type is always GREEN
    created_ms: int64
    last_confirmed_ms: int64
  }
  ```

### Stage 4: MOTION_CLASSIFIER

- **Input**: Sequence of LocationReadings (last N readings from Ingress buffer)
- **Responsibility**: Classify motion state: stationary, walking, driving, transit
- **Output**: `MotionState(state, confidence, speed_estimate_kmh)`
- **Method**: Delta distance / delta time over sliding window. Thresholds: stationary < 0.5 km/h, walking 0.5-6 km/h, driving > 30 km/h, transit = driving + on known route.
- **Value**: Enables suppression of non-urgent notifications while driving, shortens responses during walking.

### Stage 5: SPATIAL_ANCHOR

- **Input**: ResolvedLocation + MotionState
- **Responsibility**: Produce final `DeviceSpatialContext` and write to SessionState
- **Output**: `DeviceSpatialContext` written to `multimodal.spatial_context` in HOT CORE
- **Write target**: NEW `multimodal` section (see Section 5 below)
- **Staleness**: Context expires after 5 minutes of no sensor update; section marks `stale: true`

---

## 5. SessionState Plug-In Point

### 5.1 Current State

SessionState has 12 sections across 2 tiers:

**HOT CORE (8 sections, 44KB of 48KB budget)**:

| Section | Budget | Purpose |
|---------|--------|---------|
| control | 8KB | Leases, turn lock, flow state |
| beliefs_active | 8KB | Facts needed this turn (includes MentionedLocation from NER) |
| scoreboard | 6KB | Referents, QUD, salience |
| history_active | 8KB | Last 10 turns, full fidelity |
| clarifications | 4KB | Open gaps this turn |
| affective_now | 4KB | Current emotion snapshot |
| narrative_active | 4KB | One active thread |
| meta | 2KB | Session ID, band, timestamps |

**WARM TIER (4 sections, 48KB of 48KB budget)**: Full.

**Remaining HOT budget**: 48KB - 44KB = **4KB available**.

### 5.2 Recommendation: New `multimodal` HOT Section (4KB)

Add a 9th HOT section: `multimodal` at 4KB, filling HOT CORE to its 48KB cap.

**Why a new section instead of extending beliefs_active?**:

- `beliefs_active` holds conversation-derived beliefs (NER facts, mentioned entities, mentioned time, mentioned location). It is keyed to the current turn and demoted to `beliefs_history` after turn completion.
- Device spatial context is NOT conversation-derived. It persists across turns (the user does not stop being at home between utterances). It should not demote with turn beliefs.
- Separation of concerns: conversation context vs device context. Different lifecycles, different staleness rules, different eviction strategies.

**Why HOT, not WARM?**:

- Spatial context is needed EVERY turn for context inference. If warm-evicted, the system loses awareness mid-session.
- 4KB is the exact remaining HOT budget -- fits perfectly.
- Motion state and zone influence response generation (shorter responses while driving, location-aware answers). This is hot-path data.

### 5.3 Proposed `multimodal` Section Schema

```
multimodal (4KB HOT)
  header: SectionHeader
  spatial_context: DeviceSpatialContext
    zone: string              # "home", "work", "transit" (GREEN band)
    zone_confidence: float    # 0.0 - 1.0
    place_label: string       # "QFC Woodinville" (AMBER band, optional)
    motion_state: string      # "stationary", "walking", "driving"
    motion_confidence: float
    last_sensor_ms: int64     # timestamp of last sensor reading
    stale: bool               # true if > 5 min since last sensor update
    source: string            # "gps", "wifi", "ip", "fused"
  device_state: DeviceState
    device_id: string
    battery_pct: uint8
    connectivity: string      # "wifi", "cellular", "offline"
    screen_state: string      # "on", "off", "locked"
    audio_state: string       # "silent", "vibrate", "normal"
  updated_ms: int64
```

**Size estimate**: ~200-400 bytes typical. 4KB budget provides ample headroom for future multimodal signals (ambient noise level, light sensor, etc.).

### 5.4 Lifecycle Rules

| Rule | Behavior |
|------|----------|
| Eviction | NEVER (same as control) -- spatial context is always needed |
| Staleness | Mark `stale: true` after 5 min of no sensor update |
| Turn demotion | Does NOT demote with turn -- persists across turns |
| Session end | Cleared (no cross-session persistence in HOT) |
| Cold archive | No. Device context is ephemeral by design |
| Privacy | zone/motion = GREEN, place_label = AMBER, raw coords = never stored |

### 5.5 Diagram Update Required

`sessionstate_internal.mmd` currently has 8 HOT sections. After adding `multimodal`:

```
H_MULTIMODAL["multimodal (<=4KB)<br/>spatial context, device state"]:::hot
```

This brings HOT CORE to 9 sections, 48KB (full). The invariant `I_HOT["HOT <= 48KB"]` remains satisfied.

---

## 6. Why the Two Paths Stay Separate (LLM Reasoning)

The two spatial channels are **never fused or cross-referenced** by the Concierge. Both land in SessionState as independent sections. The LLM receives the full SessionState and reasons over both signals with its own world knowledge.

### 6.1 Why Not Fuse?

Conversation-mentioned locations often refer to **someone or something else**, not the user's physical position:

- "Smit is in San Francisco" -- user is in Texas, Smit is in SF. Fusing would incorrectly associate SF with the device.
- "I left my bag at the office" -- user is at home. The office is a reference, not the user's location.
- "Book a restaurant near Central Park" -- user may be planning a future trip, not currently there.

Only the LLM has enough conversational context to understand WHO or WHAT a mentioned location refers to. Hard-coded fusion logic in the Concierge would produce wrong answers.

### 6.2 What the LLM Sees in SessionState

When the LLM receives SessionState, it gets both independently:

```
multimodal.spatial_context:
  zone: "home"                    # Device is at user's home in Texas
  motion_state: "stationary"
  last_sensor_ms: 1738972800000

beliefs_active.mentioned_location:
  raw_text: "San Francisco"       # User mentioned SF in conversation
  location_type: "city"
  entity_id: "loc-sf-001"
  confidence: 0.95
```

The LLM reads both and reasons: "The user is physically at home (Texas). They are talking about San Francisco in the context of Smit. I should answer about Smit's situation in SF, not assume the user is in SF."

### 6.3 Example Scenarios

**Scenario A: "Smit is in San Francisco, what is the weather there?"**

- `multimodal.spatial_context` = {zone: "home", Texas}
- `beliefs_active.mentioned_location` = {raw_text: "San Francisco"}
- LLM reasons: "there" refers to San Francisco (Smit's location). Return SF weather, not Texas weather.

**Scenario B: "What is the weather like?"**

- `multimodal.spatial_context` = {zone: "transit", motion: "driving"}
- `beliefs_active.mentioned_location` = None
- LLM reasons: No conversation location mentioned. Use device location for weather. User is driving, prefer short response.

**Scenario C: "Turn off the kitchen lights"**

- `multimodal.spatial_context` = {zone: "home"}
- `beliefs_active.mentioned_location` = {raw_text: "the kitchen", location_type: "room"}
- LLM reasons: User is at home and mentions "the kitchen" -- likely means THIS home's kitchen. Route to home automation.

**Scenario D: "I left my bag at mom's house"**

- `multimodal.spatial_context` = {zone: "work"}
- `beliefs_active.mentioned_location` = {raw_text: "mom's house", entity_id: "place-mom-001"}
- LLM reasons: User is at work, referring to mom's house (a different place). No spatial fusion needed -- these are different locations for different purposes.

---

## 7. Concierge Integration Points

The Spatial Engine plugs into the Concierge at these points:

### 7.1 Ingress (Receives)

| Source | Event/Signal | Frequency |
|--------|-------------|-----------|
| ADR-0085a LocationTracker | `location.reading` | Every 30s (active) |
| ADR-0085a Heartbeat | `device.heartbeat` | Every 30s |
| K0 Place Registry | `place.lookup` response | On demand |

### 7.2 Egress (Produces)

| Target | Data | Frequency |
|--------|------|-----------|
| SessionState multimodal | DeviceSpatialContext | Every sensor update |
| SessionState multimodal | DeviceState | Every heartbeat |
| Proactive Trigger Engine | Zone transition events | On zone change |

### 7.3 Events Emitted

| Event | Topic | Payload |
|-------|-------|---------|
| `spatial.zone_changed` | `k1.concierge.spatial` | {old_zone, new_zone, confidence, timestamp_ms} |
| `spatial.motion_changed` | `k1.concierge.spatial` | {old_state, new_state, confidence} |
| `spatial.stale` | `k1.concierge.spatial` | {last_sensor_ms, staleness_s} |
| `spatial.place_resolved` | `k1.concierge.spatial` | {place_id, label, zone_type} |

---

## 8. Relationship to Existing Components

### 8.1 vs beliefs_active.mentioned_location (Already Built)

`beliefs_active` already implements `MentionedLocation`:

```python
@dataclass
class MentionedLocation:
    raw_text: str           # "the kitchen", "mom's house"
    location_type: str      # "room", "address", "zone"
    entity_id: str          # Link to entity if resolved
    confidence: float       # NER confidence
```

This is **conversation text extraction** (NER LOC entities). It answers "what location did the user mention?" It demotes with the turn to `beliefs_history`.

The Spatial Engine's `DeviceSpatialContext` is **sensor-derived physical awareness**. It answers "where is the device right now?" It persists across turns in `multimodal`.

Both are needed. They serve different purposes and have different lifecycles.

### 8.2 vs Temporal Resolution Engine (Already in Concierge)

Temporal Resolution Engine resolves "when" from conversation text ("tomorrow", "next week") into epoch timestamps. It writes to `beliefs_active.mentioned_time`.

Spatial Engine resolves "where is the device" from device sensors into semantic zones. It writes to `multimodal.spatial_context` ONLY. It does NOT read or modify `beliefs_active.mentioned_location` -- that is the NER pipeline's domain.

They are strictly parallel engines in the Concierge. Both write to separate SessionState sections. The LLM reads both and performs its own reasoning -- no intermediate fusion step exists.

### 8.3 vs ADR-0050 Multi-Device Sync

ADR-0050 provides the data sync layer for Place Registry across devices (CRDT, E2EE). The Spatial Engine uses ADR-0050 to sync known places, but ADR-0050 does not process spatial signals or produce spatial context. It is infrastructure, not intelligence.

---

## 9. Implementation Sequence (When Ready)

1. **FlatBuffer schema**: Create `multimodal_section.fbs` with DeviceSpatialContext and DeviceState tables
2. **Generate bindings**: Generate Python FlatBuffer bindings
3. **Section implementation**: `k1/sessionstate/sections/multimodal.py` -- read/write/serialize/deserialize
4. **Kernel registration**: Register multimodal as 9th HOT section in SessionState kernel
5. **Update invariants**: HOT cap remains 48KB, section count becomes 9
6. **Spatial Engine stages**: Implement 5 stages as Concierge sub-components
7. **Event wiring**: Register `k1.concierge.spatial` topic, wire zone/motion change events
8. **LLM prompt design**: Ensure SessionState serialization presents `multimodal.spatial_context` and `beliefs_active.mentioned_location` as clearly separate sections so the LLM can reason over them independently
9. **Tests**: Integration tests for full sensor -> SessionState path
10. **Diagram updates**: Update `sessionstate_internal.mmd` to include multimodal section

---

## 10. Open Questions

1. **HOT budget full after multimodal**: With 9 sections at 48KB, there is zero remaining HOT headroom. Any future HOT section requires either (a) reducing an existing section's budget, or (b) raising the 48KB cap. Is 48KB the absolute ceiling?
2. **Ambient signals**: Should multimodal also hold ambient noise level, light level, or other sensor data? The 4KB budget has room, but scope needs bounding.
3. **Place learning**: Should the Place Registry learn new places automatically from repeated visits, or only accept user-defined places? Auto-learning has privacy implications.
4. **Cross-device spatial fusion**: If a user has a phone (GPS) and a laptop (WiFi only), which spatial signal wins? ADR-0085a defines fallback for single device but not multi-device fusion.
5. **Zone transition debounce**: GPS can oscillate at geofence boundaries. What debounce interval prevents spurious zone_changed events? Candidate: 60s dwell time before confirming transition.
