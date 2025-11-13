---
adr_number: 0083b
affected_layers:
- layer1_input
- layer4_runtime
affected_modules:
- k1.l1_input.sensor_fusion.algorithms
- k1.l1_input.sensor_fusion.bayesian_fusion
- k1.l4_runtime.occupancy_state
- k0.kernel.sensor_processing.fusion
authors:
- K1 Architecture Team
concerns:
- architecture
- modularity
- performance
- privacy
- reliability
- security
- usability
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: '2025-11-03'
implementation_phase: Phase 5 (Ambient Context)
implementation_status: PLANNED
propagation:
  affected_adrs:
  - ADR-0083
  - ADR-0083b
  affected_contracts:
  - k0/contracts/api/sensors/fusion_algorithm.yml
  - k0/contracts/api/sensors/occupancy_inference.yml
  - k1/contracts/flatbuffers/layer1_input/sensor_fusion_state.fbs
  affected_tests:
  - tests/k1/l1_input/test_fusion_algorithms.py
  - tests/k1/l1_input/test_bayesian_fusion.py
  - tests/k0/kernel/test_occupancy_inference.py
  triggers:
  - Updating API contracts or schemas
related_adrs:
- ADR-0017
- ADR-0083
- ADR-0083b
- ADR-0083c
related_contracts: []
related_diagrams: []
research_citations:
- Bayesian Sensor Fusion (Durrant-Whyte & Henderson, 2008)
- Occupancy Detection (Erickson et al., 2014)
- Multi-Sensor Data Fusion (Hall & Llinas, 1997)
status: ACCEPTED
title: Sensor Fusion Algorithms
---

# ADR-0083b: Sensor Fusion Algorithms

**Status:** Proposed 🔄
**Parent ADR:** ADR-0083 (Ambient Sensor Fusion)
**Capability:** #3 - Ambient Context Awareness
**Priority:** Post-MVP v1.1
**Date:** 2025-10-22

---

## Context

### Problem Statement

**Parent ADR Challenge:** ADR-0083 defines weighted multi-sensor voting but doesn't specify fusion algorithm details, occupancy state inference, or person counting logic.

**Key Questions:**
1. How do we combine 6 sensor types with different confidence levels and latencies?
2. How do we infer occupancy state (VACANT/POSSIBLY_OCCUPIED/OCCUPIED) from sensor readings?
3. How do we estimate person count when sensors give conflicting signals?
4. How do we handle temporal patterns (room just vacated vs occupied for hours)?

**Current Gap:**
- Fusion algorithm pseudo-code only (ADR-0083), no implementation details
- No temporal smoothing (prevent flapping between states)
- No person count conflict resolution (camera says 3, BLE says 1)
- No confidence decay over time (stale sensor readings)

---

## Decision

### Core Algorithm: Weighted Bayesian Sensor Fusion

**Why Bayesian?**
- Handles sensor uncertainty naturally (each sensor has confidence score)
- Supports incremental updates (add new sensor reading without recomputing all)
- Provides probabilistic occupancy estimate (not binary yes/no)

**Fusion Formula:**

```
P(Occupied | Sensors) = Weighted Vote of 6 Sensors

occupancy_score = Σ (weight_i × confidence_i × sensor_signal_i)

where:
- weight_i = sensor type weight (Camera 0.40, mmWave 0.25, PIR 0.15, BLE 0.10, WiFi 0.05, Light 0.05)
- confidence_i = sensor reading confidence (0.0-1.0)
- sensor_signal_i = normalized sensor signal (0.0=absent, 1.0=present)
```

---

### Algorithm Implementation

```python
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
import time

class OccupancyLevel(Enum):
    VACANT = "VACANT"                    # occupancy_score < 0.30
    POSSIBLY_OCCUPIED = "POSSIBLY_OCCUPIED"  # 0.30 ≤ score < 0.60
    OCCUPIED = "OCCUPIED"                # score ≥ 0.60

@dataclass
class FusionConfig:
    """Fusion algorithm configuration"""
    # Sensor weights (sum to 1.0)
    camera_weight: float = 0.40
    mmwave_weight: float = 0.25
    pir_weight: float = 0.15
    ble_weight: float = 0.10
    wifi_weight: float = 0.05
    light_weight: float = 0.05

    # Occupancy thresholds
    occupied_threshold: float = 0.60
    possibly_occupied_threshold: float = 0.30

    # Temporal smoothing (prevent flapping)
    smoothing_window_s: int = 5  # 5-second averaging window
    min_confidence_delta: float = 0.10  # Require 10% confidence change to update state

    # Confidence decay
    stale_reading_threshold_s: int = 60  # Readings >60s old decay to 50% confidence

class SensorFusionEngine:
    """
    Multi-modal sensor fusion with weighted Bayesian voting.

    Algorithm:
    1. Normalize sensor signals to 0.0-1.0 (absent → present)
    2. Apply sensor type weights (camera highest, light lowest)
    3. Compute weighted occupancy score
    4. Apply temporal smoothing (5-second rolling average)
    5. Determine occupancy level (VACANT/POSSIBLY/OCCUPIED)
    6. Estimate person count (camera > BLE > mmWave fallback)
    """

    def __init__(self, config: FusionConfig = FusionConfig()):
        self.config = config
        self.occupancy_history: List[float] = []  # Last 5 seconds of scores
        self.last_occupancy_level: Optional[OccupancyLevel] = None
        self.last_update_ts: int = 0

    def fuse(
        self,
        pir: Optional[SensorReading],
        mmwave: Optional[SensorReading],
        ble: Optional[SensorReading],
        wifi: Optional[SensorReading],
        camera: Optional[SensorReading],
        light: Optional[SensorReading]
    ) -> OccupancyState:
        """
        Fuse 6 sensor types into occupancy state.

        Returns:
            OccupancyState with level, person_count, confidence, privacy_zone
        """

        now_ms = int(time.time() * 1000)

        # Step 1: Normalize sensor signals (extract 0.0-1.0 presence signal)
        camera_signal, camera_conf = self._extract_signal(camera, "Camera", now_ms)
        mmwave_signal, mmwave_conf = self._extract_signal(mmwave, "mmWave", now_ms)
        pir_signal, pir_conf = self._extract_signal(pir, "PIR", now_ms)
        ble_signal, ble_conf = self._extract_signal(ble, "BLE", now_ms)
        wifi_signal, wifi_conf = self._extract_signal(wifi, "WiFi", now_ms)
        light_signal, light_conf = self._extract_signal(light, "Light", now_ms)

        # Step 2: Compute weighted occupancy score
        occupancy_score = (
            self.config.camera_weight * camera_signal * camera_conf +
            self.config.mmwave_weight * mmwave_signal * mmwave_conf +
            self.config.pir_weight * pir_signal * pir_conf +
            self.config.ble_weight * ble_signal * ble_conf +
            self.config.wifi_weight * wifi_signal * wifi_conf +
            self.config.light_weight * light_signal * light_conf
        )

        # Step 3: Temporal smoothing (5-second rolling average)
        self.occupancy_history.append(occupancy_score)
        if len(self.occupancy_history) > 5:  # Keep last 5 seconds
            self.occupancy_history.pop(0)

        smoothed_score = sum(self.occupancy_history) / len(self.occupancy_history)

        # Step 4: Determine occupancy level
        occupancy_level = self._determine_level(smoothed_score)

        # Step 5: State change hysteresis (prevent flapping)
        if self.last_occupancy_level:
            # Require 10% confidence delta to change state
            last_score = self.occupancy_history[-2] if len(self.occupancy_history) > 1 else smoothed_score
            confidence_delta = abs(smoothed_score - last_score)

            if confidence_delta < self.config.min_confidence_delta:
                occupancy_level = self.last_occupancy_level  # Keep previous state

        self.last_occupancy_level = occupancy_level
        self.last_update_ts = now_ms

        # Step 6: Estimate person count
        person_count = self._estimate_person_count(camera, ble, mmwave)

        # Step 7: Detect privacy zone
        detected_identities = self._extract_identities(ble, camera)
        privacy_zone = self._detect_privacy_zone(occupancy_level, person_count, detected_identities)

        return OccupancyState(
            room_id="default_room",  # TODO: Multi-room support
            occupancy_level=occupancy_level,
            person_count=person_count,
            confidence=smoothed_score,
            detected_identities=detected_identities,
            ambient_light_lux=light.normalized_data.get("lux", 0.0) if light else 0.0,
            last_motion_ts=pir.normalized_data.get("last_motion_ts", 0) if pir else 0,
            privacy_zone=privacy_zone,
            timestamp=now_ms
        )

    def _extract_signal(
        self,
        reading: Optional[SensorReading],
        sensor_type: str,
        now_ms: int
    ) -> tuple[float, float]:
        """
        Extract 0.0-1.0 presence signal and confidence from sensor reading.

        Returns:
            (signal, confidence) where signal=0.0 (absent) to 1.0 (present)
        """

        if not reading:
            return 0.0, 0.0  # Sensor offline

        # Apply confidence decay for stale readings
        age_s = (now_ms - reading.timestamp_ms) / 1000.0
        confidence = reading.confidence

        if age_s > self.config.stale_reading_threshold_s:
            confidence *= 0.5  # 50% confidence decay for >60s old readings

        # Extract presence signal (sensor-specific logic)
        if sensor_type == "Camera":
            person_count = reading.normalized_data.get("person_count", 0)
            signal = min(person_count / 5.0, 1.0)  # 0-5 people → 0.0-1.0

        elif sensor_type == "mmWave":
            presence = reading.normalized_data.get("presence_detected", False)
            signal = 1.0 if presence else 0.0

        elif sensor_type == "PIR":
            motion = reading.normalized_data.get("motion_detected", False)
            signal = 1.0 if motion else 0.0

        elif sensor_type == "BLE":
            enrolled_count = reading.normalized_data.get("enrolled_count", 0)
            signal = min(enrolled_count / 3.0, 1.0)  # 0-3 devices → 0.0-1.0

        elif sensor_type == "WiFi":
            devices = reading.normalized_data.get("connected_devices", 0)
            signal = min(devices / 5.0, 1.0)  # 0-5 devices → 0.0-1.0

        elif sensor_type == "Light":
            lux = reading.normalized_data.get("lux", 0.0)
            signal = 1.0 if lux > 100 else 0.0  # >100 lux = lights on

        else:
            signal = 0.0

        return signal, confidence

    def _determine_level(self, score: float) -> OccupancyLevel:
        """Map occupancy score to level (VACANT/POSSIBLY/OCCUPIED)"""
        if score >= self.config.occupied_threshold:
            return OccupancyLevel.OCCUPIED
        elif score >= self.config.possibly_occupied_threshold:
            return OccupancyLevel.POSSIBLY_OCCUPIED
        else:
            return OccupancyLevel.VACANT

    def _estimate_person_count(
        self,
        camera: Optional[SensorReading],
        ble: Optional[SensorReading],
        mmwave: Optional[SensorReading]
    ) -> int:
        """
        Estimate person count with sensor priority: Camera > BLE > mmWave.

        Rules:
        - Camera person_count (most accurate)
        - BLE enrolled_count (approximate, device ≠ person)
        - mmWave presence (binary, at least 1 person)
        - Default: 0 (vacant)
        """

        # Priority 1: Camera (highest accuracy)
        if camera:
            person_count = camera.normalized_data.get("person_count", 0)
            if person_count > 0:
                return person_count

        # Priority 2: BLE enrolled devices (medium accuracy)
        if ble:
            enrolled_count = ble.normalized_data.get("enrolled_count", 0)
            if enrolled_count > 0:
                return enrolled_count

        # Priority 3: mmWave presence (at least 1 person)
        if mmwave:
            presence = mmwave.normalized_data.get("presence_detected", False)
            if presence:
                return 1

        # Default: vacant
        return 0

    def _extract_identities(
        self,
        ble: Optional[SensorReading],
        camera: Optional[SensorReading]
    ) -> List[str]:
        """
        Extract detected family member identities.

        Sources:
        - BLE enrolled devices (device owner)
        - Camera face recognition (detected_faces)
        """

        identities = []

        # BLE enrolled devices
        if ble:
            devices = ble.normalized_data.get("detected_devices", [])
            for device in devices:
                if device.get("owner"):
                    identities.append(device["owner"])

        # Camera face recognition
        if camera:
            faces = camera.normalized_data.get("detected_faces", [])
            identities.extend([f for f in faces if f != "unknown"])

        # Deduplicate
        return list(set(identities))

    def _detect_privacy_zone(
        self,
        occupancy: OccupancyLevel,
        person_count: int,
        identities: List[str]
    ) -> PrivacyZone:
        """
        Detect privacy zone (PUBLIC/FAMILY/PRIVATE).

        Rules:
        - VACANT → PRIVATE (no one present)
        - person_count == 1 → PRIVATE (user alone)
        - person_count == len(identities) → FAMILY (all family members)
        - person_count > len(identities) → PUBLIC (unknown person)
        """

        if occupancy == OccupancyLevel.VACANT:
            return PrivacyZone.PRIVATE

        if person_count == 1:
            return PrivacyZone.PRIVATE

        if person_count == len(identities) and len(identities) > 0:
            return PrivacyZone.FAMILY

        # Unknown person detected
        return PrivacyZone.PUBLIC
```

---

### Temporal Smoothing: Anti-Flapping Mechanism

**Problem:** Sensors have noise (PIR false positives, mmWave multi-path reflections). Without smoothing, occupancy state flaps rapidly (VACANT ↔ OCCUPIED every second).

**Solution: 5-Second Rolling Average + Hysteresis**

```python
def apply_temporal_smoothing(
    current_score: float,
    history: List[float],
    window_s: int = 5
) -> float:
    """
    Rolling average over last 5 seconds.

    Example:
    - t=0s: score=0.80 → avg=0.80 (OCCUPIED)
    - t=1s: score=0.20 → avg=0.50 (POSSIBLY) ← noise spike
    - t=2s: score=0.75 → avg=0.58 (POSSIBLY)
    - t=3s: score=0.85 → avg=0.65 (OCCUPIED) ← stable now
    - t=4s: score=0.90 → avg=0.74 (OCCUPIED)
    - t=5s: score=0.85 → avg=0.80 (OCCUPIED) ← fully smoothed
    """

    history.append(current_score)
    if len(history) > window_s:
        history.pop(0)

    return sum(history) / len(history)

def apply_hysteresis(
    new_level: OccupancyLevel,
    prev_level: Optional[OccupancyLevel],
    confidence_delta: float,
    min_delta: float = 0.10
) -> OccupancyLevel:
    """
    Prevent state flapping: require 10% confidence delta to change state.

    Example:
    - prev=OCCUPIED (score=0.62)
    - new=POSSIBLY (score=0.58) ← delta=0.04 < 0.10 → stay OCCUPIED
    - new=VACANT (score=0.25) ← delta=0.37 > 0.10 → change to VACANT
    """

    if not prev_level:
        return new_level  # First reading, no hysteresis

    if confidence_delta < min_delta:
        return prev_level  # Keep previous state

    return new_level  # Confidence delta sufficient, change state
```

**Result:**
- Noise spikes filtered (single PIR false positive doesn't trigger OCCUPIED)
- State transitions smooth (no rapid flapping)
- Latency acceptable (5-second window = max 5s delay to detect occupancy change)

---

### Person Count Conflict Resolution

**Problem:** Sensors give conflicting person counts:
- Camera: 3 people
- BLE: 1 enrolled device (Alice's phone)
- mmWave: 1 presence detected

**Solution: Sensor Priority Hierarchy**

```python
def resolve_person_count_conflict(
    camera_count: int,
    ble_count: int,
    mmwave_presence: bool
) -> int:
    """
    Prioritize camera > BLE > mmWave.

    Examples:
    1. Camera=3, BLE=1 → return 3 (camera most accurate)
    2. Camera=0, BLE=2 → return 2 (BLE approximate)
    3. Camera=0, BLE=0, mmWave=True → return 1 (at least 1 person)
    4. All sensors=0 → return 0 (vacant)
    """

    if camera_count > 0:
        return camera_count  # Camera is ground truth

    if ble_count > 0:
        return ble_count  # BLE approximate (device ≠ person)

    if mmwave_presence:
        return 1  # At least 1 person (mmWave binary)

    return 0  # Vacant
```

**Rationale:**
- **Camera (highest accuracy):** Visual confirmation, can count multiple people
- **BLE (medium accuracy):** Enrolled devices approximate person count (assumes 1 device = 1 person)
- **mmWave (binary):** Detects presence but cannot count (presence = at least 1 person)

---

### Confidence Decay for Stale Readings

**Problem:** Sensor readings become stale over time (PIR last motion was 2 minutes ago, but person may still be present and stationary).

**Solution: Exponential Confidence Decay**

```python
def apply_confidence_decay(
    confidence: float,
    age_s: float,
    decay_threshold_s: int = 60
) -> float:
    """
    Decay confidence for stale readings.

    Rules:
    - age < 60s: no decay (confidence unchanged)
    - age ≥ 60s: 50% confidence (reading is stale)

    Examples:
    - PIR motion detected 10s ago → confidence=1.0 (fresh)
    - PIR motion detected 90s ago → confidence=0.5 (stale, person may have left)
    - BLE device seen 120s ago → confidence=0.5 (stale, device may have disconnected)
    """

    if age_s < decay_threshold_s:
        return confidence  # Fresh reading, no decay

    # Stale reading: 50% confidence decay
    return confidence * 0.5
```

**Impact on Fusion:**
- Fresh readings (age <60s) have full confidence weight
- Stale readings (age ≥60s) contribute 50% confidence → lower occupancy score
- Very stale readings (age >5 minutes) effectively ignored (confidence → 0)

---

## Consequences

### Positive

1. **Robust Fusion:** Weighted voting handles sensor conflicts gracefully
2. **Temporal Smoothing:** 5-second rolling average prevents flapping
3. **Confidence Decay:** Stale readings automatically downweighted
4. **Person Count Priority:** Camera > BLE > mmWave hierarchy resolves conflicts

### Negative

1. **Latency:** 5-second smoothing window adds max 5s delay to state changes
2. **Complexity:** Bayesian fusion requires tuning weights (camera 0.40 vs mmWave 0.25)

---

## Implementation

**File:** `k1/l1_input/streams/operators/ambient_sensor_fusion.py`

**Modules:**
- `sensor_fusion_engine.py` (core fusion algorithm)
- `temporal_smoother.py` (rolling average + hysteresis)
- `person_count_resolver.py` (conflict resolution)
- `confidence_decay.py` (stale reading handling)

---

**Status:** Proposed 🔄 (awaiting approval for Post-MVP v1.1)