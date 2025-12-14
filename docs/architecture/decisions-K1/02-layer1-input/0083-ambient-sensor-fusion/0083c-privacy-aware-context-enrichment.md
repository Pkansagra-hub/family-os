---
adr_number: 0083c
affected_layers:
- layer1_input
- layer2_orchestration
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l2_orchestration.context_enrichment
- k0.kernel.privacy.context_filter
- k1.l4_runtime.session_state.multimodal
- k0.security.privacy_bands
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
- testing
- usability
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: '2025-11-03'
implementation_phase: Phase 5 (Ambient Context)
implementation_status: PLANNED
propagation:
  affected_adrs:
  - ADR-0017
  - ADR-0032a
  - ADR-0035
  - ADR-0052
  - ADR-0056
  - ADR-0083
  - ADR-0083a
  - ADR-0083b
  affected_contracts:
  - k0/contracts/api/privacy/context_enrichment.yml
  - k0/contracts/api/privacy/privacy_bands.yml
  - k1/contracts/flatbuffers/layer2_orchestration/enriched_context.fbs
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests:
  - tests/k1/l2_orchestration/test_context_enrichment.py
  - tests/k0/kernel/test_privacy_context_filter.py
  - tests/k0/security/test_privacy_bands.py
  triggers:
  - Modifying system architecture
  - Updating API contracts or schemas
related_adrs:
- ADR-0017
- ADR-0032a
- ADR-0035
- ADR-0052
- ADR-0052d
- ADR-0056
- ADR-0056d
- ADR-0083
- ADR-0083a
- ADR-0083b
- ADR-0083c
related_contracts: []
related_diagrams: []
research_citations:
- Privacy-Preserving Context (Langheinrich, 2001)
- Context-Aware Computing (Dey, 2001)
- Privacy Bands (Lederer et al., 2004)
status: ACCEPTED
title: Privacy-Aware Context Enrichment
---

# ADR-0083c: Privacy-Aware Context Enrichment

**Status:** Proposed 🔄
**Parent ADR:** ADR-0083 (Ambient Sensor Fusion)
**Capability:** #3 - Ambient Context Awareness
**Priority:** Post-MVP v1.1
**Date:** 2025-10-22
**Related ADRs:**
- ADR-0017 (SessionState Section 5 Multimodal)
- ADR-0032a (Privacy Bands GREEN/AMBER/RED/BLACK)
- ADR-0035 (PII Detection & Redaction)
- ADR-0052 (Enhanced HITL Protocols)
- ADR-0056 (TTS Synthesis Streaming)

---

## Context

### Problem Statement

**Parent ADR Challenge:** ADR-0083 defines occupancy detection and privacy zone classification but doesn't specify SessionState integration, privacy band enforcement, or Meta Policy triggers.

**Key Questions:**
1. How do we store ambient context in SessionState Section 5 (Multimodal)?
2. How do we enforce privacy bands (Camera=RED, BLE=AMBER) before data egress?
3. How do we trigger proactive suggestions (dark room → lighting, away mode → security)?
4. How do we modulate TTS prosody based on ambient context (whisper mode when others present)?

**Current Gap:**
- SessionState Section 5 schema undefined for ambient context
- No privacy band enforcement pipeline (camera data could egress to cloud)
- No Meta Policy integration for proactive triggers
- No TTS modulation for privacy-aware responses

---

## Decision

### Architecture: 3-Layer Privacy Enforcement

```
Layer 1: SessionState Integration (ambient context storage)
   ↓
Layer 2: Privacy Band Enforcement (AMBER/RED filtering before egress)
   ↓
Layer 3: Meta Policy Triggers (proactive suggestions + TTS modulation)
```

---

### Layer 1: SessionState Section 5 Integration

**SessionState Section 5 Extension:**

```python
# SessionState Section 5: Multimodal Context
@dataclass
class MultimodalContext:
    # Existing fields (audio, video, text)
    audio_context: Optional[AudioContext] = None
    video_context: Optional[VideoContext] = None
    text_context: Optional[TextContext] = None

    # NEW: Ambient Context (ADR-0083)
    ambient_context: AmbientContext = field(default_factory=AmbientContext)

@dataclass
class AmbientContext:
    """
    Ambient sensor fusion context (ADR-0083).

    Storage:
    - Current room state (occupancy, person count, privacy zone)
    - 5-minute occupancy history (300 samples at 1Hz = last 300 states)
    - Last motion timestamp (for away mode detection)
    - Ambient light level (for nighttime detection)
    """

    current_room: str = "default_room"
    occupancy_state: Optional[OccupancyState] = None
    occupancy_history: List[OccupancyState] = field(default_factory=list)  # Last 300 states
    last_motion_ts: int = 0
    ambient_light_lux: float = 0.0
    privacy_zone: PrivacyZone = PrivacyZone.PRIVATE
    suggested_band: Optional[PrivacyBand] = None
    last_updated_ts: int = 0

    def add_occupancy_state(self, state: OccupancyState) -> None:
        """
        Add occupancy state to history (5-minute rolling window).

        Retention Policy:
        - Keep last 300 states (5 minutes at 1Hz sampling)
        - Purge older states to prevent memory bloat
        """
        self.occupancy_state = state
        self.occupancy_history.append(state)

        # Keep last 300 states (5 minutes)
        if len(self.occupancy_history) > 300:
            self.occupancy_history.pop(0)

        # Update derived fields
        self.last_motion_ts = state.last_motion_ts
        self.ambient_light_lux = state.ambient_light_lux
        self.privacy_zone = state.privacy_zone
        self.last_updated_ts = state.timestamp

    def get_occupancy_trend(self, window_s: int = 60) -> str:
        """
        Analyze occupancy trend over time window.

        Returns:
        - "STABLE_OCCUPIED": Occupied for entire window
        - "STABLE_VACANT": Vacant for entire window
        - "TRANSITIONING": Occupancy changing (entering/leaving)
        """

        if not self.occupancy_history:
            return "UNKNOWN"

        # Get states from last N seconds
        now_ms = int(time.time() * 1000)
        window_states = [
            s for s in self.occupancy_history
            if (now_ms - s.timestamp) < (window_s * 1000)
        ]

        if not window_states:
            return "UNKNOWN"

        # Count occupied vs vacant states
        occupied_count = sum(1 for s in window_states if s.occupancy_level == OccupancyLevel.OCCUPIED)
        vacant_count = sum(1 for s in window_states if s.occupancy_level == OccupancyLevel.VACANT)

        occupied_ratio = occupied_count / len(window_states)

        if occupied_ratio > 0.80:
            return "STABLE_OCCUPIED"
        elif occupied_ratio < 0.20:
            return "STABLE_VACANT"
        else:
            return "TRANSITIONING"

    def time_since_last_motion_s(self) -> int:
        """Return seconds since last motion detected"""
        now_ms = int(time.time() * 1000)
        return (now_ms - self.last_motion_ts) // 1000
```

---

### Layer 2: Privacy Band Enforcement

**Privacy Band Policy (ADR-0032a Compliance):**

| Sensor Type | Privacy Band | Egress Policy | Rationale |
|-------------|--------------|---------------|-----------|
| PIR Motion | GREEN | Allowed | Binary motion (no PII) |
| mmWave Radar | GREEN | Allowed | Range + micro-doppler (no visual PII) |
| BLE Proximity | AMBER | Masked | MAC addresses are PII (hash before egress) |
| WiFi Proximity | GREEN | Allowed | Device count only (no MAC addresses) |
| Camera Person | RED | Blocked | Visual data (local-only processing) |
| Ambient Light | GREEN | Allowed | Lux value (no PII) |

**Privacy Enforcement Pipeline:**

```python
class AmbientPrivacyEnforcer:
    """
    Enforce privacy bands for ambient sensor data.

    Responsibilities:
    - Block RED band data egress (camera frames, bounding boxes)
    - Mask AMBER band data (BLE MAC addresses → hashed)
    - Allow GREEN band data egress (PIR, mmWave, WiFi count, Light)
    """

    @staticmethod
    def filter_for_egress(
        occupancy_state: OccupancyState,
        target_band: PrivacyBand
    ) -> OccupancyState:
        """
        Filter occupancy state for network egress based on privacy band.

        Rules:
        - RED band: Remove all visual data (camera frames, bounding boxes, faces)
        - AMBER band: Hash PII (BLE MAC addresses, detected identities)
        - GREEN band: Allow all data
        """

        filtered = copy.deepcopy(occupancy_state)

        if target_band == PrivacyBand.RED:
            # Remove all camera-derived data
            filtered.detected_identities = []  # No face IDs
            # Note: Camera person count still allowed (aggregate, no visual PII)

        if target_band >= PrivacyBand.AMBER:
            # Hash detected identities (names → SHA256)
            filtered.detected_identities = [
                hashlib.sha256(identity.encode()).hexdigest()[:8]
                for identity in filtered.detected_identities
            ]

        return filtered

    @staticmethod
    def suggest_privacy_band(
        ambient: AmbientContext,
        current_band: PrivacyBand
    ) -> Optional[PrivacyBand]:
        """
        Suggest privacy band escalation based on ambient context.

        Rules (from ADR-0083):
        - PUBLIC zone (unknown person detected) → suggest RED band
        - FAMILY zone (family members only) → suggest AMBER band
        - PRIVATE zone (user alone) → no escalation
        """

        if not ambient.occupancy_state:
            return None  # No ambient data available

        privacy_zone = ambient.occupancy_state.privacy_zone

        if privacy_zone == PrivacyZone.PUBLIC:
            # Unknown person detected → escalate to RED (local-only)
            if current_band < PrivacyBand.RED:
                return PrivacyBand.RED

        elif privacy_zone == PrivacyZone.FAMILY:
            # Family members present → escalate to AMBER (PII masking)
            if current_band < PrivacyBand.AMBER:
                return PrivacyBand.AMBER

        # PRIVATE zone: no escalation needed
        return None
```

---

### Layer 3: Meta Policy Proactive Triggers

**Trigger Types (from ADR-0083):**

1. **Dark Room Trigger:** Occupancy detected + lux <50 → "Turn on lights?"
2. **Away Mode Trigger:** All rooms vacant >30 minutes → "Activate away mode?"
3. **Welcome Home Trigger:** Occupancy changed VACANT → OCCUPIED → "Welcome back!"
4. **Meeting Detected Trigger:** Calendar + occupancy → defer non-urgent notifications
5. **Nighttime Quiet Trigger:** Lux <10 + late hours → reduce TTS volume

**Proactive Trigger Generator:**

```python
class AmbientTriggerGenerator:
    """
    Generate proactive suggestions based on ambient context changes.

    Integration: ADR-0052d Proactive Risk Confirmation
    """

    def __init__(self):
        self.previous_context: Optional[AmbientContext] = None

    def generate_triggers(
        self,
        current: AmbientContext
    ) -> List[ProactiveSuggestion]:
        """
        Detect ambient context changes and generate proactive suggestions.

        Returns:
            List of ProactiveSuggestion (type, message, action, confidence)
        """

        suggestions = []

        # Trigger 1: Dark Room (occupancy + low light)
        if (current.occupancy_state and
            current.occupancy_state.occupancy_level == OccupancyLevel.OCCUPIED and
            current.ambient_light_lux < 50):

            suggestions.append(ProactiveSuggestion(
                type="lighting",
                message="The room is dark. Would you like me to turn on the lights?",
                action="smart_home_lights_on",
                confidence=0.80,
                privacy_band=PrivacyBand.GREEN  # Lighting suggestion is GREEN
            ))

        # Trigger 2: Away Mode (all rooms vacant >30 minutes)
        time_since_motion = current.time_since_last_motion_s()
        if (current.occupancy_state and
            current.occupancy_state.occupancy_level == OccupancyLevel.VACANT and
            time_since_motion > 1800):  # 30 minutes

            suggestions.append(ProactiveSuggestion(
                type="security",
                message="It looks like everyone has left. Should I activate away mode?",
                action="activate_away_mode",
                confidence=0.70,
                privacy_band=PrivacyBand.AMBER  # Security action requires approval
            ))

        # Trigger 3: Welcome Home (occupancy transition VACANT → OCCUPIED)
        if (self.previous_context and
            self.previous_context.occupancy_state and
            current.occupancy_state and
            self.previous_context.occupancy_state.occupancy_level == OccupancyLevel.VACANT and
            current.occupancy_state.occupancy_level == OccupancyLevel.OCCUPIED):

            # Identify person if possible
            identities = current.occupancy_state.detected_identities
            greeting = f"Welcome back{' ' + identities[0] if identities else ''}!"

            suggestions.append(ProactiveSuggestion(
                type="greeting",
                message=f"{greeting} You have 3 unread messages.",
                action=None,  # No action, just greeting
                confidence=0.90,
                privacy_band=PrivacyBand.GREEN
            ))

        # Trigger 4: Meeting Detected (calendar + occupancy)
        # TODO: Integrate with calendar API (requires ADR for calendar integration)

        # Trigger 5: Nighttime Quiet (low light + late hours)
        if current.ambient_light_lux < 10:
            # Note: Nighttime detection handled in TTS modulation (see below)
            pass

        # Update previous context for next comparison
        self.previous_context = copy.deepcopy(current)

        return suggestions

@dataclass
class ProactiveSuggestion:
    """Proactive suggestion from ambient triggers"""
    type: str                    # "lighting" | "security" | "greeting" | "meeting"
    message: str                 # User-facing message
    action: Optional[str]        # Action to execute (or None for info-only)
    confidence: float            # 0.0-1.0 (suggestion confidence)
    privacy_band: PrivacyBand    # Required privacy band for action
```

---

### TTS Modulation for Privacy-Aware Responses

**Prosody Adjustment (ADR-0056 Integration):**

```python
class AmbientTTSModulator:
    """
    Modulate TTS prosody based on ambient context.

    Integration: ADR-0056d TTS Synthesis Streaming
    """

    @staticmethod
    def modulate_prosody(
        ambient: AmbientContext,
        base_prosody: ProsodyControls
    ) -> ProsodyControls:
        """
        Adjust TTS prosody based on ambient context.

        Adjustments:
        - PUBLIC zone (others present) → whisper mode (volume -5dB, rate 0.9x)
        - FAMILY zone (family members) → normal volume
        - PRIVATE zone (user alone) → normal volume
        - Nighttime (lux <10) → gentle tone (volume -3dB, pitch -2 semitones)
        """

        adjusted = copy.deepcopy(base_prosody)

        if not ambient.occupancy_state:
            return adjusted  # No ambient data, no modulation

        privacy_zone = ambient.occupancy_state.privacy_zone

        # Privacy zone adjustments
        if privacy_zone == PrivacyZone.PUBLIC:
            # Others present → whisper mode
            adjusted.volume -= 5  # -5dB (whisper)
            adjusted.rate = 0.9   # Slightly slower for clarity
            logger.info("TTS modulation: Whisper mode (PUBLIC zone)")

        elif privacy_zone == PrivacyZone.FAMILY:
            # Family members present → normal volume
            # No adjustment needed
            pass

        # Nighttime adjustments (low ambient light)
        if ambient.ambient_light_lux < 10:
            # Nighttime → gentle tone
            adjusted.volume -= 3  # -3dB (quieter)
            adjusted.pitch -= 2   # -2 semitones (lower pitch, calmer)
            logger.info("TTS modulation: Nighttime mode (lux <10)")

        return adjusted
```

**TTS Modulation Pipeline Integration:**

```python
# In TTS synthesis pipeline (ADR-0056d)
def synthesize_with_ambient_modulation(
    text: str,
    base_prosody: ProsodyControls,
    session_state: SessionState
) -> bytes:
    """
    Synthesize TTS with ambient context modulation.

    Pipeline:
    1. Load ambient context from SessionState Section 5
    2. Modulate prosody based on privacy zone + lighting
    3. Synthesize TTS with adjusted prosody
    """

    # Load ambient context
    ambient = session_state.multimodal.ambient_context

    # Modulate prosody
    modulator = AmbientTTSModulator()
    adjusted_prosody = modulator.modulate_prosody(ambient, base_prosody)

    # Synthesize TTS (existing ADR-0056d pipeline)
    audio_bytes = tts_synthesizer.synthesize(text, adjusted_prosody)

    return audio_bytes
```

---

## Consequences

### Positive

1. **SessionState Integration:** Ambient context stored in Section 5 (5-minute history, occupancy trends)
2. **Privacy Enforcement:** RED band blocks camera data egress, AMBER hashes identities
3. **Proactive Triggers:** 5 trigger types (lighting, away mode, greeting, meeting, nighttime)
4. **TTS Modulation:** Whisper mode when others present, gentle tone at nighttime

### Negative

1. **Storage Overhead:** 300 occupancy states (5 minutes) in SessionState (~50KB)
2. **Latency:** TTS modulation adds <5ms overhead (prosody adjustment)

---

## Implementation

### Phase 1: SessionState Integration (1 week)

**Deliverables:**
- Extend `SessionState.multimodal.ambient_context` schema
- Implement `AmbientContext.add_occupancy_state()` (5-minute rolling window)
- Implement `AmbientContext.get_occupancy_trend()` (trend analysis)

**Files:**
- `k1/l4_runtime/session_state/multimodal_context.py`
- `k1/l4_runtime/session_state/ambient_context.py`

---

### Phase 2: Privacy Enforcement (1 week)

**Deliverables:**
- Implement `AmbientPrivacyEnforcer.filter_for_egress()` (RED/AMBER/GREEN filtering)
- Implement `AmbientPrivacyEnforcer.suggest_privacy_band()` (escalation logic)
- Unit tests for privacy band enforcement (camera data blocked, BLE hashed)

**Files:**
- `k1/l1_input/streams/operators/ambient_privacy_enforcer.py`
- `tests/l1_input/test_ambient_privacy.py`

---

### Phase 3: Proactive Triggers (2 weeks)

**Deliverables:**
- Implement `AmbientTriggerGenerator.generate_triggers()` (5 trigger types)
- Integrate with Meta Policy (ADR-0052d Proactive Risk Confirmation)
- HITL confirmation flow for security actions (away mode)

**Files:**
- `k1/l2_orchestration/proactive/ambient_triggers.py`
- `k1/l1_input/meta_policy/hitl_confirmation.py` (ADR-0052 integration)

---

### Phase 4: TTS Modulation (1 week)

**Deliverables:**
- Implement `AmbientTTSModulator.modulate_prosody()` (whisper mode, nighttime tone)
- Integrate with TTS synthesis pipeline (ADR-0056d)
- A/B testing for prosody adjustments (user preference tuning)

**Files:**
- `k1/l1_input/streams/operators/ambient_tts_modulator.py`
- `k1/l1_input/streams/operators/tts_pipeline.py` (ADR-0056d integration)

---

### Total Timeline: 5 weeks

**Dependencies:**
- SessionState Section 5 implementation (ADR-0017)
- Meta Policy HITL (ADR-0052)
- TTS Synthesis (ADR-0056)
- Privacy Bands (ADR-0032a)

---

## Metrics & Observability

### Prometheus Metrics

```python
# Privacy enforcement metrics
ambient_privacy_escalations_total = Counter(
    'ambient_privacy_escalations_total',
    'Total privacy band escalations',
    ['from_band', 'to_band', 'trigger']
)

ambient_data_filtered_total = Counter(
    'ambient_data_filtered_total',
    'Total data filtered for privacy',
    ['sensor_type', 'privacy_band']
)

# Proactive trigger metrics
ambient_proactive_triggers_total = Counter(
    'ambient_proactive_triggers_total',
    'Total proactive suggestions generated',
    ['trigger_type', 'accepted']
)

# TTS modulation metrics
ambient_tts_modulations_total = Counter(
    'ambient_tts_modulations_total',
    'Total TTS prosody modulations',
    ['modulation_type']  # "whisper" | "nighttime"
)
```

### Grafana Alerts

```yaml
# Alert: Privacy band escalation failing
- alert: PrivacyEscalationFailure
  expr: rate(ambient_privacy_escalations_total[5m]) == 0 AND ambient_occupancy_transitions_total{to_level="PUBLIC"} > 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Privacy band escalation not working (PUBLIC zone detected but no RED band escalation)"
    description: "Camera data may be egressing to cloud (privacy violation)"

# Alert: TTS modulation not applying
- alert: TTSModulationNotApplying
  expr: rate(ambient_tts_modulations_total[5m]) == 0 AND ambient_occupancy_transitions_total{to_level="PUBLIC"} > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "TTS whisper mode not applying (PUBLIC zone detected)"
    description: "FamilyOS speaking at normal volume with others present"
```

---

## References

### Related ADRs

- **ADR-0017:** SessionState 6-Section Design (Section 5 Multimodal for ambient context)
- **ADR-0032a:** Privacy Bands (GREEN/AMBER/RED/BLACK enforcement)
- **ADR-0035:** PII Detection & Redaction (BLE MAC hashing, face ID protection)
- **ADR-0052:** Enhanced HITL Protocols (Proactive Risk Confirmation for triggers)
- **ADR-0056:** TTS Synthesis Streaming (prosody modulation)
- **ADR-0083:** Ambient Sensor Fusion (parent ADR, occupancy detection)
- **ADR-0083a:** Multi-Modal Sensor Integration (sensor drivers)
- **ADR-0083b:** Sensor Fusion Algorithms (occupancy state inference)

---

**Status:** Proposed 🔄 (awaiting approval for Post-MVP v1.1)