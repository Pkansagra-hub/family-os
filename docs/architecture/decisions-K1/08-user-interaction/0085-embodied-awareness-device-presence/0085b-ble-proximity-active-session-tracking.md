---
adr_number: 0085b
affected_layers:
- layer1_input
- layer4_runtime
affected_modules:
- k1.l1_input.device_presence.ble_proximity
- k1.l1_input.device_presence.session_tracker
- k1.l4_runtime.session_state.active_device
- k0.kernel.device_tracking.proximity
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
- usability
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: '2025-11-03'
implementation_phase: Phase 5 (Cross-Device Extensions)
implementation_status: PLANNED
propagation:
  affected_adrs:
  - ADR-0085
  - ADR-0085a
  - ADR-0085c
  affected_contracts:
  - k0/contracts/api/device/ble_proximity.yml
  - k0/contracts/api/device/active_session.yml
  - k1/contracts/flatbuffers/layer1_input/device_proximity.fbs
  affected_tests:
  - tests/k1/l1_input/test_ble_proximity.py
  - tests/k1/l1_input/test_session_tracker.py
  - tests/k0/kernel/test_proximity_detection.py
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
related_adrs:
- ADR-0017e
- ADR-0050
- ADR-0085
- ADR-0085a
- ADR-0085b
- ADR-0085c
related_contracts: []
related_diagrams: []
research_citations:
- BLE Proximity Detection (Faragher & Harle, 2015)
- Activity Recognition (Bao & Intille, 2004)
- Mobile Context Awareness (Schmidt et al., 1999)
status: ACCEPTED
title: BLE Proximity & Active Session Tracking
---

# ADR-0085b: BLE Proximity & Active Session Tracking

**Status:** Proposed 🔄
**Parent ADR:** ADR-0085 (Embodied Awareness & Device Presence)
**Last Updated:** 2025-01-22

---

## Context

**From ADR-0085:** Embodied Awareness Layer requires **BLE proximity sensing** and **active session tracking** to detect device proximity and determine which device user actively using.

**Key Requirements:**

1. **BLE Proximity:** Detect nearby devices via Bluetooth Low Energy beacons (NEAR/MEDIUM/FAR zones)
2. **Active Session:** Detect actively used device (screen on + recent input + foreground app)
3. **Motion Sensors:** Infer device context (in-pocket, on-desk, being-held, in-vehicle)
4. **Power State:** Track battery level and charging status for resource management

**Use Cases:**

- Detect when user present via multiple devices (phone + watch NEAR → user nearby)
- Prefer active device for notifications (laptop active → suppress phone)
- Adapt behavior based on device context (phone in-pocket → don't show visual content)
- Reduce background tasks when battery low

---

## Decision

Implement **four-component proximity architecture**:

### Component 1: BLE Proximity Sensor (NEAR/MEDIUM/FAR Zones)

### Component 2: Active Session Monitor (Screen + Input + Foreground App)

### Component 3: Motion Sensor Integrator (Accelerometer + Gyroscope Context)

### Component 4: Power State Monitor (Battery Level + Charging Status)

---

## Component 1: BLE Proximity Sensor

### BLE Beacon Protocol

**Goal:** Advertise and scan for family-scoped BLE beacons to detect nearby devices.

```python
class BLEProximitySensor:
    """
    Detect nearby family devices via Bluetooth Low Energy beacons.

    Use cases:
    - User presence detection (phone + watch NEAR → user present)
    - Device switch confirmation (phone NEAR + laptop MEDIUM → user at desk)
    - Privacy zone detection (multiple devices FAR → user away)

    Beacon format: iBeacon compatible
    - UUID: familyos-<family_id>-<device_id>
    - Major: Device type (1=PHONE, 2=TABLET, 3=LAPTOP, 4=WATCH, 5=SPEAKER)
    - Minor: Battery level (0-100)
    - TX Power: -59 dBm (reference RSSI at 1 meter)
    """

    def __init__(self, device_id: str, family_id: str):
        self.device_id = device_id
        self.family_id = family_id
        self.beacon_uuid = self.generate_beacon_uuid()
        self.nearby_devices = {}  # device_id → NearbyDevice
        self.scan_interval_seconds = 5

    def generate_beacon_uuid(self) -> str:
        """
        Generate family-scoped BLE beacon UUID.

        Format: familyos-<family_id_hash>-<device_id_hash>

        Example: familyos-a3f8c9-d21e4b

        Privacy: Family-scoped (only family devices can decode full UUID)
        """
        family_hash = hashlib.sha256(self.family_id.encode()).hexdigest()[:6]
        device_hash = hashlib.sha256(self.device_id.encode()).hexdigest()[:6]

        return f"familyos-{family_hash}-{device_hash}"

    async def start_advertising(self):
        """
        Start BLE beacon advertising (continuous).

        Platform APIs:
        - iOS: CoreBluetooth (CBPeripheralManager)
        - Android: BluetoothLeAdvertiser
        - macOS: CoreBluetooth (CBPeripheralManager)
        - Linux: BlueZ D-Bus API
        """
        beacon_payload = BLEBeacon(
            uuid=self.beacon_uuid,
            major=self.get_device_type_code(),  # 1-5
            minor=get_battery_level(),           # 0-100
            tx_power=-59  # Reference RSSI at 1 meter
        )

        await ble_advertise(beacon_payload)

        logger.info(
            "ble_advertising_started",
            uuid=self.beacon_uuid,
            device_type=beacon_payload.major,
            battery_level=beacon_payload.minor
        )

    async def scan_for_beacons(self):
        """
        Scan for family BLE beacons every 5 seconds.

        Scan duration: 3 seconds (balance between battery + detection latency)
        Scan interval: 5 seconds (battery-friendly)
        """
        while True:
            # Scan for 3 seconds
            beacons = await ble_scan(duration_seconds=3)

            for beacon in beacons:
                # Check if family device
                if beacon.uuid.startswith(f"familyos-{self.get_family_hash()}"):
                    device_id = self.extract_device_id(beacon.uuid)

                    # Skip self
                    if device_id == self.device_id:
                        continue

                    # Estimate proximity from RSSI
                    proximity = self.estimate_proximity(beacon.rssi)
                    distance_meters = self.estimate_distance(beacon.rssi, beacon.tx_power)

                    # Update nearby device registry
                    self.nearby_devices[device_id] = NearbyDevice(
                        device_id=device_id,
                        device_type=beacon.major,
                        battery_level=beacon.minor,
                        rssi=beacon.rssi,
                        proximity=proximity,
                        distance_meters=distance_meters,
                        last_seen=now()
                    )

                    logger.debug(
                        "ble_device_detected",
                        device_id=device_id,
                        rssi=beacon.rssi,
                        proximity=proximity.value,
                        distance_meters=round(distance_meters, 1)
                    )

            # Remove stale devices (not seen >30 seconds)
            self.remove_stale_devices(stale_threshold_seconds=30)

            # Wait 5 seconds before next scan
            await asyncio.sleep(self.scan_interval_seconds)
```

### RSSI-Based Distance Estimation

```python
def estimate_proximity(self, rssi: int) -> ProximityZone:
    """
    Estimate proximity zone from RSSI.

    Zones:
    - NEAR: RSSI > -65 dBm (<2 meters) — User very close
    - MEDIUM: -80 < RSSI ≤ -65 dBm (2-10 meters) — Same room
    - FAR: -95 < RSSI ≤ -80 dBm (>10 meters) — Adjacent room
    - OUT_OF_RANGE: RSSI ≤ -95 dBm — Too far or obstructed

    Note: Indoor environments with walls/obstacles reduce RSSI
    """
    if rssi > -65:
        return ProximityZone.NEAR
    elif rssi > -80:
        return ProximityZone.MEDIUM
    elif rssi > -95:
        return ProximityZone.FAR
    else:
        return ProximityZone.OUT_OF_RANGE

def estimate_distance(self, rssi: int, tx_power: int) -> float:
    """
    Estimate distance in meters from RSSI.

    Formula: distance = 10 ^ ((TX_POWER - RSSI) / (10 * N))

    Where:
    - TX_POWER: Reference RSSI at 1 meter (-59 dBm)
    - RSSI: Measured signal strength (dBm)
    - N: Path loss exponent (2.0 free space, 3.0-4.0 indoor)

    Example:
    - RSSI -59 dBm → 1.0 meter
    - RSSI -69 dBm → 3.2 meters (NEAR)
    - RSSI -79 dBm → 10.0 meters (MEDIUM)
    - RSSI -89 dBm → 31.6 meters (FAR)
    """
    N = 3.0  # Indoor path loss exponent

    distance = 10 ** ((tx_power - rssi) / (10 * N))

    return distance
```

---

## Component 2: Active Session Monitor

### Active Session Detection

**Goal:** Determine if device currently active (user using it).

```python
class ActiveSessionMonitor:
    """
    Monitor device activity to detect active usage.

    Active criteria (ALL must be true):
    1. Screen is ON (not locked, not screen saver)
    2. Recent input (keyboard/mouse/touch/voice within 30s)
    3. Foreground app is active (not idle screen, not lock screen)

    Use cases:
    - Notification routing (send to active device only)
    - Device switch detection (previous active → current active)
    - TTS output coordination (speak on active device only)
    """

    def __init__(self):
        self.screen_state = ScreenState.OFF
        self.last_input_timestamp = 0
        self.foreground_app = None
        self.idle_threshold_ms = 30000  # 30 seconds
        self.is_active = False

    async def monitor_activity(self):
        """
        Monitor device activity continuously (1 Hz).
        """
        while True:
            # Check screen state
            self.screen_state = await self.get_screen_state()

            # Check input events
            input_events = await self.get_recent_input_events(since_ms=1000)
            if input_events:
                self.last_input_timestamp = now_ms()

            # Check foreground app
            self.foreground_app = await self.get_foreground_app()

            # Determine if device active
            previous_active = self.is_active
            self.is_active = self.check_if_active()

            # Detect active state transitions
            if self.is_active != previous_active:
                await self.handle_activity_change(previous_active, self.is_active)

            # Update presence state
            await self.update_presence_state()

            # Wait 1 second
            await asyncio.sleep(1)

    def check_if_active(self) -> bool:
        """
        Check if device currently active.

        Active = Screen ON AND Recent input (<30s) AND Foreground app active
        """
        # Check screen state
        if self.screen_state != ScreenState.ON:
            return False

        # Check recent input
        time_since_input = now_ms() - self.last_input_timestamp
        if time_since_input > self.idle_threshold_ms:
            return False

        # Check foreground app (not idle/lock screen)
        if self.foreground_app and self.foreground_app.is_idle_screen:
            return False

        return True
```

### Platform-Specific Implementations

```python
async def get_screen_state(self) -> ScreenState:
    """
    Get current screen state.

    Platform APIs:
    - iOS: UIScreen.main.brightness > 0 AND !UIDevice.isLocked
    - Android: PowerManager.isInteractive() AND !KeyguardManager.isDeviceLocked()
    - macOS: IODisplayWranglerGetDisplayCount() > 0 AND !CGSessionCopyCurrentDictionary()[kCGSSessionOnConsoleKey]
    - Linux: xset q (X11 DPMS state)

    States:
    - ON: Screen active, not locked
    - OFF: Screen off or device locked
    - SCREEN_SAVER: Screen saver active
    """
    return await platform_get_screen_state()

async def get_recent_input_events(self, since_ms: int) -> List[InputEvent]:
    """
    Get input events since timestamp.

    Platform APIs:
    - iOS: UIEvent.allTouches (touch events)
    - Android: MotionEvent (touch) + KeyEvent (keyboard)
    - macOS: CGEventTapCreate (keyboard, mouse, trackpad)
    - Linux: /dev/input/event* (evdev)

    Event types:
    - KEYBOARD: Key press/release
    - MOUSE: Click, move, scroll
    - TOUCH: Tap, swipe, pinch
    - VOICE: Voice command detected
    """
    return await platform_get_input_events(since_ms)

async def get_foreground_app(self) -> Optional[ForegroundApp]:
    """
    Get currently active foreground app.

    Platform APIs:
    - iOS: UIApplication.shared.keyWindow?.rootViewController
    - Android: ActivityManager.getRunningTasks()[0].topActivity
    - macOS: NSWorkspace.shared.frontmostApplication
    - Linux: _NET_ACTIVE_WINDOW (X11 property)

    Returns:
    - app_bundle_id: String (e.g., "com.familyos.app")
    - app_name: String (e.g., "FamilyOS")
    - is_idle_screen: Bool (lock screen, screen saver, etc.)
    """
    return await platform_get_foreground_app()
```

---

## Component 3: Motion Sensor Integrator

### Device Context Inference

**Goal:** Infer device context from accelerometer + gyroscope patterns.

```python
class MotionSensorIntegrator:
    """
    Infer device context from motion sensor patterns.

    Contexts:
    - STATIONARY: On desk, charging (low accel variance, low gyro variance)
    - IN_POCKET: Upright, periodic walking motion (medium accel, device upright)
    - BEING_HELD: Frequent orientation changes (high gyro variance)
    - IN_BAG: Flat, occasional bumps (medium accel, low gyro)
    - IN_VEHICLE: Sustained acceleration, periodic vibrations (sustained >0.3g)
    - WALKING: Periodic vertical acceleration (1-2 Hz frequency)
    - RUNNING: Faster periodic acceleration (2-3 Hz frequency)
    """

    def __init__(self):
        self.accelerometer_buffer = []  # (x, y, z) samples
        self.gyroscope_buffer = []      # (x, y, z) samples
        self.buffer_size = 100          # 10 seconds @ 10 Hz
        self.current_context = DeviceContext.UNKNOWN

    async def monitor_motion(self):
        """
        Monitor accelerometer + gyroscope at 10 Hz.
        """
        while True:
            # Read sensors
            accel = await read_accelerometer()  # (x, y, z) in m/s²
            gyro = await read_gyroscope()       # (x, y, z) in rad/s

            # Add to circular buffers
            self.accelerometer_buffer.append(accel)
            self.gyroscope_buffer.append(gyro)

            # Keep only last 100 samples (10 seconds)
            if len(self.accelerometer_buffer) > self.buffer_size:
                self.accelerometer_buffer.pop(0)
            if len(self.gyroscope_buffer) > self.buffer_size:
                self.gyroscope_buffer.pop(0)

            # Infer context every 10 samples (1 second)
            if len(self.accelerometer_buffer) % 10 == 0:
                context = self.infer_device_context()

                if context != self.current_context:
                    await self.handle_context_change(self.current_context, context)
                    self.current_context = context

            # Wait 100ms (10 Hz sampling)
            await asyncio.sleep(0.1)

    def infer_device_context(self) -> DeviceContext:
        """
        Infer device context from motion patterns.

        Algorithm:
        1. Calculate accel variance (measure of movement intensity)
        2. Calculate gyro variance (measure of orientation changes)
        3. Detect sustained acceleration (in-vehicle)
        4. Detect periodic patterns (walking, running)
        5. Check device orientation (upright, flat, tilted)
        6. Classify into context
        """
        # Calculate variances
        accel_variance = self.calculate_variance(self.accelerometer_buffer)
        gyro_variance = self.calculate_variance(self.gyroscope_buffer)

        # Detect sustained acceleration (in-vehicle)
        if self.is_sustained_acceleration():
            return DeviceContext.IN_VEHICLE

        # Detect periodic motion (walking, running)
        periodicity = self.detect_periodicity(self.accelerometer_buffer)
        if periodicity:
            if periodicity.frequency > 2.0:
                return DeviceContext.RUNNING
            elif periodicity.frequency > 1.0:
                return DeviceContext.WALKING

        # Stationary: Low accel variance (<0.1), low gyro variance (<0.1)
        if accel_variance < 0.1 and gyro_variance < 0.1:
            return DeviceContext.STATIONARY

        # Being held: High gyro variance (>0.5)
        if gyro_variance > 0.5:
            return DeviceContext.BEING_HELD

        # In pocket: Medium accel (0.1-0.5), device upright
        if 0.1 <= accel_variance <= 0.5 and self.is_device_upright():
            return DeviceContext.IN_POCKET

        # Default: In bag
        return DeviceContext.IN_BAG

    def calculate_variance(self, samples: List[Tuple[float, float, float]]) -> float:
        """
        Calculate variance of 3D vector magnitudes.

        Steps:
        1. Calculate magnitude for each (x, y, z) sample: sqrt(x² + y² + z²)
        2. Calculate mean magnitude
        3. Calculate variance: mean((magnitude - mean)²)
        """
        if not samples:
            return 0.0

        # Calculate magnitudes
        magnitudes = [
            math.sqrt(x**2 + y**2 + z**2)
            for x, y, z in samples
        ]

        # Calculate variance
        mean = sum(magnitudes) / len(magnitudes)
        variance = sum((m - mean)**2 for m in magnitudes) / len(magnitudes)

        return variance

    def is_sustained_acceleration(self) -> bool:
        """
        Detect sustained acceleration (in-vehicle).

        Criteria: Acceleration magnitude >0.3g for >5 seconds
        """
        if len(self.accelerometer_buffer) < 50:  # Need 5 seconds of data
            return False

        # Check last 50 samples (5 seconds)
        recent_samples = self.accelerometer_buffer[-50:]

        sustained_count = 0
        for x, y, z in recent_samples:
            magnitude = math.sqrt(x**2 + y**2 + z**2)

            # Check if acceleration >0.3g (2.94 m/s²)
            if magnitude > 2.94:
                sustained_count += 1

        # Sustained if >80% of samples exceed threshold
        return sustained_count > 40

    def detect_periodicity(
        self,
        samples: List[Tuple[float, float, float]]
    ) -> Optional[Periodicity]:
        """
        Detect periodic patterns in acceleration (walking, running).

        Uses: FFT to find dominant frequency

        Returns:
        - Periodicity(frequency, amplitude) if periodic pattern detected
        - None if no clear periodicity
        """
        if len(samples) < 50:
            return None

        # Extract vertical component (z-axis typically vertical when walking)
        z_values = [z for x, y, z in samples]

        # Apply FFT
        fft_result = np.fft.fft(z_values)
        fft_freqs = np.fft.fftfreq(len(z_values), d=0.1)  # 10 Hz sampling

        # Find dominant frequency (1-3 Hz range for human motion)
        valid_indices = np.where((fft_freqs > 1.0) & (fft_freqs < 3.0))
        if len(valid_indices[0]) == 0:
            return None

        valid_magnitudes = np.abs(fft_result[valid_indices])
        dominant_index = valid_indices[0][np.argmax(valid_magnitudes)]

        frequency = fft_freqs[dominant_index]
        amplitude = valid_magnitudes.max()

        # Require minimum amplitude threshold
        if amplitude < 0.5:
            return None

        return Periodicity(frequency=frequency, amplitude=amplitude)

    def is_device_upright(self) -> bool:
        """
        Check if device is upright (phone in pocket orientation).

        Criteria: Gyroscope indicates device vertical (z-axis up)
        """
        if not self.gyroscope_buffer:
            return False

        # Get recent gyroscope sample
        recent_gyro = self.gyroscope_buffer[-1]
        x, y, z = recent_gyro

        # Device upright if z-component dominant
        return abs(z) > abs(x) and abs(z) > abs(y)
```

---

## Component 4: Power State Monitor

### Battery Tracking

**Goal:** Monitor battery level and charging status for resource management.

```python
class PowerStateMonitor:
    """
    Monitor device power state (battery, charging).

    Use cases:
    - Reduce consolidation frequency when battery low (<20%)
    - Pause background tasks when battery critical (<10%)
    - Prefer charging devices for compute-heavy tasks
    - Adjust BLE scan frequency based on power mode
    """

    def __init__(self):
        self.battery_level = 100
        self.charging_status = ChargingStatus.DISCHARGING
        self.power_mode = PowerMode.NORMAL

    async def monitor_power(self):
        """
        Monitor power state every 60 seconds.
        """
        while True:
            # Read battery level (0-100)
            self.battery_level = await self.get_battery_level()

            # Read charging status
            self.charging_status = await self.get_charging_status()

            # Determine power mode
            previous_power_mode = self.power_mode
            self.power_mode = self.determine_power_mode()

            # Detect power mode transitions
            if self.power_mode != previous_power_mode:
                await self.handle_power_mode_change(previous_power_mode, self.power_mode)

            # Update presence state
            await self.update_power_state()

            # Wait 60 seconds
            await asyncio.sleep(60)

    async def get_battery_level(self) -> int:
        """
        Get battery level (0-100).

        Platform APIs:
        - iOS: UIDevice.current.batteryLevel * 100
        - Android: BatteryManager.BATTERY_PROPERTY_CAPACITY
        - macOS: IOPMPowerSource (pmset -g batt)
        - Linux: /sys/class/power_supply/BAT0/capacity
        """
        return await platform_get_battery_level()

    async def get_charging_status(self) -> ChargingStatus:
        """
        Get charging status.

        Platform APIs:
        - iOS: UIDevice.current.batteryState
        - Android: BatteryManager.BATTERY_PROPERTY_STATUS
        - macOS: IOPMPowerSource (pmset -g batt)
        - Linux: /sys/class/power_supply/BAT0/status

        States:
        - CHARGING: Battery charging
        - DISCHARGING: Battery discharging
        - FULL: Battery full (100% + plugged in)
        - UNKNOWN: Cannot determine
        """
        return await platform_get_charging_status()

    def determine_power_mode(self) -> PowerMode:
        """
        Determine power mode from battery level + charging status.

        Modes:
        - LOW_POWER: Battery <20% + discharging → Reduce background tasks
        - NORMAL: Battery 20-80% + discharging → Normal operations
        - HIGH_PERFORMANCE: Battery >80% OR charging → Enable all features
        """
        if self.battery_level < 20 and self.charging_status == ChargingStatus.DISCHARGING:
            return PowerMode.LOW_POWER

        elif self.battery_level > 80 or self.charging_status == ChargingStatus.CHARGING:
            return PowerMode.HIGH_PERFORMANCE

        else:
            return PowerMode.NORMAL
```

### Device Capability Detection

```python
class DeviceCapabilityDetector:
    """
    Detect device hardware capabilities.

    Capabilities:
    - HAS_GPS: Device has GPS hardware
    - HAS_CAMERA: Device has camera
    - HAS_BLE: Device has Bluetooth LE
    - HAS_MICROPHONE: Device has microphone
    - HAS_SPEAKER: Device has speaker
    - HAS_ACCELEROMETER: Device has accelerometer
    - HAS_GYROSCOPE: Device has gyroscope
    """

    def detect_capabilities(self) -> DeviceCapabilities:
        """
        Detect device hardware capabilities at startup.

        Returns: Bitmask of capabilities
        """
        caps = 0

        if self.has_gps():
            caps |= DeviceCapabilities.HAS_GPS

        if self.has_camera():
            caps |= DeviceCapabilities.HAS_CAMERA

        if self.has_ble():
            caps |= DeviceCapabilities.HAS_BLE

        if self.has_microphone():
            caps |= DeviceCapabilities.HAS_MICROPHONE

        if self.has_speaker():
            caps |= DeviceCapabilities.HAS_SPEAKER

        if self.has_accelerometer():
            caps |= DeviceCapabilities.HAS_ACCELEROMETER

        if self.has_gyroscope():
            caps |= DeviceCapabilities.HAS_GYROSCOPE

        return caps
```

---

## Performance Characteristics

| Operation | Target Latency (P95) | Battery Impact |
|-----------|---------------------|----------------|
| BLE beacon advertising | Continuous | ~0.5% per hour |
| BLE beacon scanning (5s interval) | <3 seconds | ~0.3% per hour |
| Active session detection (1 Hz) | <1 second | <0.1% per hour |
| Motion sensor reading (10 Hz) | <100ms | ~0.2% per hour |
| Power state monitoring (60s interval) | <100ms | Negligible |
| **Total battery impact** | — | **~1.1% per hour** |

---

## Observability

### Metrics

```python
ble_proximity_devices_detected = Gauge(
    'ble_proximity_devices_detected',
    'Nearby devices detected via BLE',
    ['proximity_zone']
)

active_session_state = Gauge(
    'active_session_state',
    'Device active session state (0=inactive, 1=active)'
)

motion_context = Gauge(
    'motion_context',
    'Device motion context',
    ['context']
)

battery_level = Gauge(
    'battery_level',
    'Device battery level (0-100)'
)

charging_status = Gauge(
    'charging_status',
    'Device charging status (0=discharging, 1=charging)'
)
```

### Events

```
ble.proximity.near         — Device detected in NEAR zone
ble.proximity.medium       — Device detected in MEDIUM zone
ble.proximity.far          — Device detected in FAR zone
session.active             — Device became active
session.inactive           — Device became inactive
motion.context.changed     — Motion context changed (STATIONARY → WALKING)
power.mode.changed         — Power mode changed (NORMAL → LOW_POWER)
```

---

## Related ADRs

- **ADR-0085:** Embodied Awareness & Device Presence (parent)
- **ADR-0085a:** Device Presence Detection & Location Awareness
- **ADR-0085c:** Cross-Device Context Sharing & Presence-Aware Features

---

## End of ADR-0085b