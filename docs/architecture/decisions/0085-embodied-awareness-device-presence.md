---
adr_number: 0085
title: Embodied Awareness & Device Presence — Cross-Device Presence Sensing
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer4_runtime
affected_modules: []
concerns:
- architecture
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0004
- ADR-0017
- ADR-0032
- ADR-0050
- ADR-0065b
- ADR-0085a
- ADR-0085b
- ADR-0085c
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
  - ADR-0032
  - ADR-0050
  - ADR-0065b
  - ADR-0085a
  - ADR-0085b
  - ADR-0085c
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  affected_tests: []
---


# ADR-0085: Embodied Awareness & Device Presence — Cross-Device Presence Sensing

**Status:** Proposed 🔄
**Last Updated:** 2025-01-22
**Capability:** #34 - Embodied Awareness Layer

---

## Context

**Problem:** FamilyOS operates across multiple devices (phones, tablets, laptops, smart speakers, watches) but lacks awareness of **device presence, location, and active usage**. This creates poor multi-device UX:

- User switches from phone to laptop → system doesn't detect handoff, forces manual context re-establishment
- Notifications sent to all devices → user annoyed by duplicate alerts (phone buzzes while actively using laptop)
- Location-unaware responses → system can't adapt to context ("Turn on lights" doesn't know which room)
- No proximity sensing → system can't detect when user present via multiple devices (phone + watch = user nearby)

**From Capability #34 Analysis:**

**Inputs:** Device GPS, WiFi triangulation, BLE proximity, Active sessions, Screen state, Motion sensors, Power state

**Status:** Partially available (ADR-0050 Multi-Device Family Sync provides foundation via K0 P07 CRDT sync + mDNS discovery)

**Missing Components:**

1. **Device presence detection** (track online/offline, detect device switches)
2. **Location awareness** (GPS on mobile, WiFi triangulation for indoor positioning)
3. **BLE proximity sensing** (detect nearby devices: phone + watch = user present)
4. **Active session tracking** (detect actively used device: screen on, recent input, foreground app)
5. **Motion sensor integration** (phone in pocket vs on desk vs being held)
6. **Power state monitoring** (charging status, battery level)
7. **Cross-device context sharing** (coordinate notifications, prefer active device)

**Timeline:** ADR-0050 Phase 1 (4-5 weeks) + embodied awareness features (3-4 weeks) = 7-9 weeks

**Priority:** ⚠️ Post-MVP (v1.1) - Valuable for cross-device UX but not critical for launch

---

## Decision

Implement **Embodied Awareness Layer** with 7 presence detection mechanisms that extend ADR-0050 Multi-Device Family Sync:

### 1. Device Presence Detection (Online/Offline Tracking)
### 2. Location Awareness (GPS + WiFi Triangulation)
### 3. BLE Proximity Sensing (Near/Medium/Far Zones)
### 4. Active Session Tracking (Screen State + Input Events)
### 5. Motion Sensor Integration (Accelerometer + Gyroscope)
### 6. Power State Monitoring (Battery Level + Charging Status)
### 7. Cross-Device Context Sharing (Notification Coordination + Device Preference)

**Integration:** Extend K0 P07 (Multi-Device Sync) presence metadata, store in SessionState Section 5 (Multimodal)

---

## Architecture Overview

### System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                    EMBODIED AWARENESS LAYER                      │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Device A   │  │   Device B   │  │   Device C   │          │
│  │   (Phone)    │  │   (Laptop)   │  │   (Watch)    │          │
│  │              │  │              │  │              │          │
│  │ GPS: 47.6N   │  │ WiFi: Home   │  │ BLE: Near    │          │
│  │ Screen: ON   │  │ Screen: ON   │  │ Motion: LOW  │          │
│  │ Battery: 45% │  │ Input: 5s    │  │ Battery: 80% │          │
│  │ Active: YES  │  │ Active: YES  │  │ Active: NO   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                  │
│                            │                                     │
│                   ┌────────▼─────────┐                          │
│                   │  K0 P07 Sync     │                          │
│                   │  (Presence CRDT) │                          │
│                   └────────┬─────────┘                          │
│                            │                                     │
│                   ┌────────▼─────────┐                          │
│                   │  Presence Store  │                          │
│                   │  (SessionState)  │                          │
│                   └────────┬─────────┘                          │
│                            │                                     │
│         ┌──────────────────┼──────────────────┐                 │
│         │                  │                  │                 │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼───────┐         │
│  │ Notification │  │   Device     │  │   Location   │         │
│  │ Coordinator  │  │  Preference  │  │   Context    │         │
│  │              │  │   Learner    │  │   Provider   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

### Core Components

**1. Presence Detection Module** (`k1/l1_input/streams/operators/device_presence.py`)
- Monitor local device sensors (screen, input, motion, battery)
- Publish presence updates to K0 P07 sync channel
- Subscribe to presence updates from other devices
- Maintain presence state in SessionState

**2. Location Tracker** (`k1/l1_input/streams/operators/location_tracker.py`)
- GPS tracking for mobile devices (latitude, longitude, altitude, accuracy)
- WiFi SSID/BSSID triangulation for indoor positioning
- IP geolocation fallback for desktop devices
- Coarse location detection (home vs work vs traveling)

**3. BLE Proximity Sensor** (`k1/l1_input/streams/operators/ble_proximity.py`)
- Advertise BLE beacons (family-scoped UUIDs)
- Scan for nearby family devices
- Estimate distance via RSSI (Received Signal Strength Indicator)
- Proximity zones: NEAR (<2m), MEDIUM (2-10m), FAR (>10m)

**4. Active Session Monitor** (`k1/l1_input/streams/operators/active_session.py`)
- Screen state detection (on/off, brightness, locked/unlocked)
- Input event tracking (keyboard, mouse, touch, voice)
- Foreground app detection (active window, app bundle ID)
- Idle detection (last input timestamp, screen saver active)

**5. Motion Sensor Integrator** (`k1/l1_input/streams/operators/motion_sensor.py`)
- Accelerometer (detect movement: stationary, walking, running, in-vehicle)
- Gyroscope (detect orientation: upright, face-down, tilted)
- Device context inference (in-pocket, on-desk, being-held, in-bag)

**6. Power State Monitor** (`k1/l1_input/streams/operators/power_monitor.py`)
- Battery level tracking (0-100%)
- Charging status (charging, discharging, full)
- Power mode (low-power mode, normal, high-performance)
- Battery health metrics (cycle count, capacity percentage)

**7. Presence Context Sharer** (`k1/l2_orchestration/presence/context_sharer.py`)
- Aggregate presence data from all devices
- Determine "active device" (most recently used with screen on)
- Coordinate notification delivery (suppress inactive devices)
- Provide presence context to L3 Dialogue Management

---

## Mechanism 1: Device Presence Detection

**Goal:** Track which devices are online, offline, and detect device switches.

### Online/Offline Detection

```python
class DevicePresenceDetector:
    """
    Track device online/offline status via mDNS heartbeats.

    Integration: Extends ADR-0050 Multi-Device Family Sync
    """

    def __init__(self, device_id: str, k0_bridge_p07):
        self.device_id = device_id
        self.k0_bridge = k0_bridge_p07
        self.heartbeat_interval = 30  # 30 seconds
        self.offline_threshold = 90   # 90 seconds (3 missed heartbeats)

    async def start_heartbeat(self):
        """
        Broadcast presence heartbeat every 30 seconds.

        Heartbeat includes:
        - device_id (UUID)
        - device_type (phone, laptop, tablet, watch, speaker)
        - device_name (user-friendly: "Alice's iPhone")
        - timestamp (UTC epoch milliseconds)
        - ip_address (for direct connection)
        - port (K0 Bridge P07 TCP port)
        """
        while True:
            heartbeat = DeviceHeartbeat(
                device_id=self.device_id,
                device_type=get_device_type(),
                device_name=get_device_name(),
                timestamp=now_ms(),
                ip_address=get_local_ip(),
                port=self.k0_bridge.port
            )

            # Broadcast via mDNS (ADR-0050 Phase 1)
            await self.mdns_broadcast(heartbeat)

            # Publish to K0 P07 sync channel
            await self.k0_bridge.publish_presence(heartbeat)

            # Wait 30 seconds
            await asyncio.sleep(self.heartbeat_interval)

    async def monitor_devices(self):
        """
        Monitor other devices, mark offline if no heartbeat >90s.

        Device states:
        - ONLINE: Received heartbeat within 90 seconds
        - OFFLINE: No heartbeat for >90 seconds
        - UNKNOWN: Never seen before
        """
        while True:
            current_time = now_ms()

            for device_id, device in self.known_devices.items():
                time_since_heartbeat = current_time - device.last_heartbeat_ts

                if time_since_heartbeat > self.offline_threshold * 1000:
                    if device.status != DeviceStatus.OFFLINE:
                        # Device went offline
                        device.status = DeviceStatus.OFFLINE

                        await self.emit_presence_event(
                            event_type="device.offline",
                            device_id=device_id,
                            device_name=device.device_name
                        )

                        logger.info(
                            "device_offline",
                            device_id=device_id,
                            device_name=device.device_name,
                            time_since_heartbeat_ms=time_since_heartbeat
                        )
                else:
                    if device.status != DeviceStatus.ONLINE:
                        # Device came online
                        device.status = DeviceStatus.ONLINE

                        await self.emit_presence_event(
                            event_type="device.online",
                            device_id=device_id,
                            device_name=device.device_name
                        )

            # Check every 10 seconds
            await asyncio.sleep(10)
```

### Device Switch Detection

```python
def detect_device_switch(self, previous_device: str, current_device: str):
    """
    Detect when user switches devices.

    Triggers:
    - Previous device becomes inactive (screen off, no input >30s)
    - Current device becomes active (screen on, recent input)
    - Devices in close proximity (BLE NEAR zone)

    Actions:
    - Emit device.switch event
    - Suggest session handoff ("You switched from phone to laptop, resuming here")
    - Update "preferred device" for current context
    """
    if previous_device == current_device:
        return  # No switch

    # Check if devices in proximity (likely same user)
    if self.are_devices_nearby(previous_device, current_device):
        await self.emit_presence_event(
            event_type="device.switch",
            from_device=previous_device,
            to_device=current_device,
            proximity="NEAR"
        )

        # Suggest handoff via L3 Dialogue Management
        await self.suggest_session_handoff(
            from_device=previous_device,
            to_device=current_device
        )

        logger.info(
            "device_switch_detected",
            from_device=previous_device,
            to_device=current_device
        )
```

---

## Mechanism 2: Location Awareness

**Goal:** Track device location for context-aware responses.

### Location Tracking Architecture

```python
class LocationTracker:
    """
    Track device location via GPS, WiFi triangulation, or IP geolocation.

    Location hierarchy (precision):
    1. GPS: High precision (<10m) - RED privacy band
    2. WiFi BSSID: Medium precision (<50m) - AMBER privacy band
    3. WiFi SSID: Coarse precision (building-level) - AMBER privacy band
    4. IP Geolocation: City-level precision - GREEN privacy band
    """

    def __init__(self):
        self.current_location = None
        self.location_history = []
        self.known_places = {}  # home, work, gym, etc.

    async def update_location(self):
        """
        Update device location using best available method.

        Priority:
        1. GPS (if available and user consented)
        2. WiFi triangulation (if WiFi enabled)
        3. IP geolocation (fallback)
        """
        location = None

        # Try GPS (mobile devices only)
        if self.has_gps_capability():
            location = await self.get_gps_location()

        # Fallback to WiFi triangulation
        if location is None and self.has_wifi_capability():
            location = await self.get_wifi_location()

        # Fallback to IP geolocation
        if location is None:
            location = await self.get_ip_location()

        if location:
            self.current_location = location
            self.location_history.append(location)

            # Detect significant location change
            if self.is_significant_change(location):
                await self.handle_location_change(location)

        return location

    async def get_gps_location(self) -> Optional[Location]:
        """
        Get GPS location (high precision).

        Privacy: RED band (precise location never leaves device)

        Returns: Location(latitude, longitude, altitude, accuracy, timestamp)
        """
        if not self.gps_permission_granted():
            return None

        gps_data = await get_device_gps()  # Platform-specific API

        if gps_data:
            location = Location(
                source="GPS",
                latitude=gps_data.latitude,
                longitude=gps_data.longitude,
                altitude=gps_data.altitude,
                accuracy_meters=gps_data.accuracy,
                timestamp=now(),
                privacy_band=PrivacyBand.RED
            )

            logger.info(
                "gps_location_acquired",
                accuracy_meters=gps_data.accuracy,
                privacy_band="RED"
            )

            return location

        return None

    async def get_wifi_location(self) -> Optional[Location]:
        """
        Get WiFi-based location (medium precision).

        Privacy: AMBER band (WiFi SSID hashed before sync)

        Methods:
        1. BSSID triangulation (query WiFi positioning service with BSSIDs + signal strengths)
        2. SSID matching (match against known SSID → place mapping: "HomeWiFi" → home location)
        """
        wifi_networks = await scan_wifi_networks()

        if not wifi_networks:
            return None

        # Try BSSID triangulation first (more accurate)
        location = await self.triangulate_wifi_bssids(wifi_networks)

        if location:
            return location

        # Fallback to SSID matching for known networks
        for network in wifi_networks:
            if network.ssid in self.known_places:
                place = self.known_places[network.ssid]
                location = Location(
                    source="WIFI_SSID",
                    place_name=place.name,
                    latitude=place.latitude,
                    longitude=place.longitude,
                    accuracy_meters=50,  # Building-level accuracy
                    timestamp=now(),
                    privacy_band=PrivacyBand.AMBER
                )

                logger.info(
                    "wifi_location_matched",
                    ssid_hash=hash_ssid(network.ssid),
                    place_name=place.name,
                    privacy_band="AMBER"
                )

                return location

        return None

    async def get_ip_location(self) -> Optional[Location]:
        """
        Get IP-based location (city-level precision).

        Privacy: GREEN band (coarse location safe to sync)

        Uses: GeoIP database (MaxMind GeoLite2) for IP → city mapping
        """
        ip_address = await get_public_ip()

        # Query GeoIP database
        geo_data = geoip_database.lookup(ip_address)

        if geo_data:
            location = Location(
                source="IP_GEOLOCATION",
                city=geo_data.city,
                region=geo_data.region,
                country=geo_data.country,
                latitude=geo_data.latitude,
                longitude=geo_data.longitude,
                accuracy_meters=5000,  # City-level accuracy (~5km)
                timestamp=now(),
                privacy_band=PrivacyBand.GREEN
            )

            logger.info(
                "ip_location_acquired",
                city=geo_data.city,
                country=geo_data.country,
                privacy_band="GREEN"
            )

            return location

        return None
```

### Coarse Location Detection

```python
def detect_coarse_location(self, location: Location) -> PlaceCategory:
    """
    Detect coarse location category (home, work, traveling).

    Categories:
    - HOME: Device at home location (WiFi SSID match or GPS within 100m of home)
    - WORK: Device at work location (WiFi SSID match or GPS within 100m of work)
    - TRAVELING: Device far from home/work (>10km from both)
    - UNKNOWN: Cannot determine location

    Uses:
    - Enable location-aware responses ("You're at home, turning on living room lights")
    - Adjust privacy settings (more permissive at home, stricter in public)
    """
    if location.source == "WIFI_SSID":
        # Direct SSID match
        if location.place_name == "home":
            return PlaceCategory.HOME
        elif location.place_name == "work":
            return PlaceCategory.WORK

    # GPS-based proximity check
    if location.source == "GPS" and self.known_places:
        home_location = self.known_places.get("home")
        work_location = self.known_places.get("work")

        if home_location:
            distance_to_home = haversine_distance(
                location.latitude, location.longitude,
                home_location.latitude, home_location.longitude
            )

            if distance_to_home < 100:  # Within 100 meters
                return PlaceCategory.HOME

        if work_location:
            distance_to_work = haversine_distance(
                location.latitude, location.longitude,
                work_location.latitude, work_location.longitude
            )

            if distance_to_work < 100:  # Within 100 meters
                return PlaceCategory.WORK

        # Check if traveling (>10km from both)
        if distance_to_home > 10000 and distance_to_work > 10000:
            return PlaceCategory.TRAVELING

    return PlaceCategory.UNKNOWN
```

---

## Mechanism 3: BLE Proximity Sensing

**Goal:** Detect nearby family devices via Bluetooth Low Energy beacons.

### BLE Beacon Protocol

```python
class BLEProximitySensor:
    """
    Advertise and scan for BLE beacons to detect nearby devices.

    Use case: Detect when user present via multiple devices
    - Phone + watch both NEAR → user likely present
    - Phone NEAR + laptop MEDIUM → user at desk
    - All devices FAR → user away from devices
    """

    def __init__(self, device_id: str, family_id: str):
        self.device_id = device_id
        self.family_id = family_id
        self.beacon_uuid = self.generate_beacon_uuid()
        self.nearby_devices = {}

    def generate_beacon_uuid(self) -> str:
        """
        Generate family-scoped BLE beacon UUID.

        Format: familyos-<family_id>-<device_id>
        Example: familyos-family123-device456

        Privacy: Family-scoped (only family devices can decode)
        """
        return f"familyos-{self.family_id}-{self.device_id}"

    async def start_advertising(self):
        """
        Advertise BLE beacon continuously.

        Beacon payload:
        - UUID: familyos-<family_id>-<device_id>
        - Major: Device type (1=phone, 2=tablet, 3=laptop, 4=watch, 5=speaker)
        - Minor: Battery level (0-100)
        - TX Power: -59 dBm (reference RSSI at 1 meter)
        """
        beacon_payload = BLEBeacon(
            uuid=self.beacon_uuid,
            major=self.get_device_type_code(),
            minor=get_battery_level(),
            tx_power=-59
        )

        await ble_advertise(beacon_payload)

        logger.info(
            "ble_advertising_started",
            uuid=self.beacon_uuid,
            device_type=self.get_device_type_code()
        )

    async def scan_for_beacons(self):
        """
        Scan for family BLE beacons every 5 seconds.

        Proximity estimation:
        - RSSI -50 to -65 dBm → NEAR (<2m)
        - RSSI -65 to -80 dBm → MEDIUM (2-10m)
        - RSSI -80 to -95 dBm → FAR (>10m)
        - RSSI <-95 dBm → OUT_OF_RANGE
        """
        while True:
            # Scan for 3 seconds
            beacons = await ble_scan(duration_seconds=3)

            for beacon in beacons:
                if beacon.uuid.startswith(f"familyos-{self.family_id}"):
                    # Family device detected
                    device_id = self.extract_device_id(beacon.uuid)
                    proximity = self.estimate_proximity(beacon.rssi)

                    self.nearby_devices[device_id] = NearbyDevice(
                        device_id=device_id,
                        device_type=beacon.major,
                        battery_level=beacon.minor,
                        rssi=beacon.rssi,
                        proximity=proximity,
                        last_seen=now()
                    )

                    logger.debug(
                        "ble_device_detected",
                        device_id=device_id,
                        rssi=beacon.rssi,
                        proximity=proximity.value
                    )

            # Wait 5 seconds before next scan
            await asyncio.sleep(5)

    def estimate_proximity(self, rssi: int) -> ProximityZone:
        """
        Estimate distance from RSSI.

        Formula: distance = 10 ^ ((TX_POWER - RSSI) / (10 * N))
        Where N = path loss exponent (2.0 for open space, 3.0-4.0 for indoor)

        Simplified thresholds:
        - NEAR: RSSI > -65 dBm (<2m)
        - MEDIUM: -80 < RSSI ≤ -65 dBm (2-10m)
        - FAR: -95 < RSSI ≤ -80 dBm (>10m)
        - OUT_OF_RANGE: RSSI ≤ -95 dBm
        """
        if rssi > -65:
            return ProximityZone.NEAR
        elif rssi > -80:
            return ProximityZone.MEDIUM
        elif rssi > -95:
            return ProximityZone.FAR
        else:
            return ProximityZone.OUT_OF_RANGE
```

---

## Mechanism 4: Active Session Tracking

**Goal:** Detect which device user actively using.

### Active Session Detection

```python
class ActiveSessionMonitor:
    """
    Monitor device activity to determine if actively used.

    Active criteria:
    - Screen on (not locked, not in screen saver)
    - Recent input (keyboard, mouse, touch, voice within last 30s)
    - Foreground app (not idle, not background)
    """

    def __init__(self):
        self.screen_state = ScreenState.OFF
        self.last_input_timestamp = 0
        self.foreground_app = None
        self.idle_threshold = 30000  # 30 seconds

    async def monitor_activity(self):
        """
        Monitor device activity continuously.

        Update SessionState with activity metrics.
        """
        while True:
            # Check screen state
            self.screen_state = await get_screen_state()

            # Check input events
            input_events = await get_recent_input_events(since_ms=1000)
            if input_events:
                self.last_input_timestamp = now_ms()

            # Check foreground app
            self.foreground_app = await get_foreground_app()

            # Determine if device active
            is_active = self.is_device_active()

            # Update presence state
            await self.update_presence_state(is_active)

            # Wait 1 second
            await asyncio.sleep(1)

    def is_device_active(self) -> bool:
        """
        Determine if device currently active.

        Active if ALL conditions met:
        1. Screen is ON (not locked, not screen saver)
        2. Recent input (within 30 seconds)
        3. Foreground app active (not idle screen)
        """
        if self.screen_state != ScreenState.ON:
            return False

        time_since_input = now_ms() - self.last_input_timestamp
        if time_since_input > self.idle_threshold:
            return False

        if self.foreground_app and self.foreground_app.is_idle_screen:
            return False

        return True
```

---

## Mechanism 5: Motion Sensor Integration

**Goal:** Infer device context from accelerometer/gyroscope.

### Motion Pattern Detection

```python
class MotionSensorIntegrator:
    """
    Detect device context from motion sensors.

    Context inference:
    - STATIONARY: Device on desk, charging (accel variance low)
    - IN_POCKET: Device upright, periodic walking motion (accel variance medium)
    - BEING_HELD: Device orientation changing, frequent small movements (gyro variance high)
    - IN_BAG: Device flat, occasional bumps (accel variance medium, gyro variance low)
    - IN_VEHICLE: Sustained acceleration, periodic vibrations (accel sustained >0.3g)
    """

    def __init__(self):
        self.accelerometer_buffer = []
        self.gyroscope_buffer = []
        self.buffer_size = 100  # 10 seconds @ 10 Hz

    async def monitor_motion(self):
        """
        Monitor accelerometer and gyroscope at 10 Hz.
        """
        while True:
            # Read sensors
            accel = await read_accelerometer()  # (x, y, z) in m/s²
            gyro = await read_gyroscope()        # (x, y, z) in rad/s

            # Add to buffers
            self.accelerometer_buffer.append(accel)
            self.gyroscope_buffer.append(gyro)

            # Keep only last 100 samples
            if len(self.accelerometer_buffer) > self.buffer_size:
                self.accelerometer_buffer.pop(0)
            if len(self.gyroscope_buffer) > self.buffer_size:
                self.gyroscope_buffer.pop(0)

            # Infer context every 10 samples (1 second)
            if len(self.accelerometer_buffer) % 10 == 0:
                context = self.infer_device_context()
                await self.update_motion_context(context)

            # Wait 100ms (10 Hz)
            await asyncio.sleep(0.1)

    def infer_device_context(self) -> DeviceContext:
        """
        Infer device context from motion patterns.
        """
        # Calculate acceleration variance (0-10 seconds)
        accel_variance = self.calculate_variance(self.accelerometer_buffer)

        # Calculate gyroscope variance
        gyro_variance = self.calculate_variance(self.gyroscope_buffer)

        # Stationary: Low accel variance (<0.1), low gyro variance (<0.1)
        if accel_variance < 0.1 and gyro_variance < 0.1:
            return DeviceContext.STATIONARY

        # In pocket: Medium accel variance (0.1-0.5), device upright
        if 0.1 <= accel_variance <= 0.5 and self.is_device_upright():
            return DeviceContext.IN_POCKET

        # Being held: High gyro variance (>0.5), frequent orientation changes
        if gyro_variance > 0.5:
            return DeviceContext.BEING_HELD

        # In vehicle: Sustained acceleration (>0.3g for >5 seconds)
        if self.is_sustained_acceleration():
            return DeviceContext.IN_VEHICLE

        # Default: In bag
        return DeviceContext.IN_BAG
```

---

## Mechanism 6: Power State Monitoring

**Goal:** Track battery level and charging status.

```python
class PowerStateMonitor:
    """
    Monitor device power state (battery, charging).

    Use cases:
    - Reduce consolidation frequency when battery low
    - Pause background tasks when <20% battery
    - Prefer charging devices for compute-heavy tasks
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
            # Read battery level
            self.battery_level = await get_battery_level()

            # Read charging status
            self.charging_status = await get_charging_status()

            # Determine power mode
            self.power_mode = self.determine_power_mode()

            # Update presence state
            await self.update_power_state()

            # Wait 60 seconds
            await asyncio.sleep(60)

    def determine_power_mode(self) -> PowerMode:
        """
        Determine power mode from battery level.

        Modes:
        - LOW_POWER: Battery <20%, reduce background tasks
        - NORMAL: Battery 20-80%, normal operations
        - HIGH_PERFORMANCE: Battery >80% or charging, enable all features
        """
        if self.battery_level < 20:
            return PowerMode.LOW_POWER
        elif self.battery_level > 80 or self.charging_status == ChargingStatus.CHARGING:
            return PowerMode.HIGH_PERFORMANCE
        else:
            return PowerMode.NORMAL
```

---

## Mechanism 7: Cross-Device Context Sharing

**Goal:** Coordinate notifications and prefer active device.

### Notification Coordination

```python
class NotificationCoordinator:
    """
    Coordinate notifications across devices.

    Rules:
    1. If one device active → send notification only to active device
    2. If multiple devices active → send to most recently used
    3. If no devices active → send to all devices
    4. If phone in-pocket + laptop active → suppress phone notification
    """

    def __init__(self, presence_store):
        self.presence_store = presence_store

    async def send_notification(self, notification: Notification):
        """
        Send notification to appropriate device(s).
        """
        # Get all online devices
        online_devices = self.presence_store.get_online_devices()

        if not online_devices:
            logger.warning("no_online_devices", notification_id=notification.id)
            return

        # Get active devices (screen on + recent input)
        active_devices = [d for d in online_devices if d.is_active]

        if len(active_devices) == 1:
            # Only one active device → send there
            await self.send_to_device(active_devices[0], notification)
            logger.info(
                "notification_sent_to_active",
                device=active_devices[0].device_name,
                notification_id=notification.id
            )

        elif len(active_devices) > 1:
            # Multiple active → send to most recently used
            most_recent = max(active_devices, key=lambda d: d.last_input_timestamp)
            await self.send_to_device(most_recent, notification)
            logger.info(
                "notification_sent_to_recent",
                device=most_recent.device_name,
                notification_id=notification.id
            )

        else:
            # No active devices → send to all
            for device in online_devices:
                await self.send_to_device(device, notification)
            logger.info(
                "notification_sent_to_all",
                device_count=len(online_devices),
                notification_id=notification.id
            )
```

### Device Preference Learning

```python
class DevicePreferenceLearner:
    """
    Learn which device user prefers for different tasks.

    Patterns:
    - Long responses → user prefers laptop (larger screen)
    - Quick queries → user uses phone
    - Media playback → user prefers speaker/tablet
    - Voice commands → user uses phone/watch
    """

    def __init__(self):
        self.preference_history = []

    async def learn_preference(self, task_type: str, selected_device: str):
        """
        Record device preference for task type.
        """
        self.preference_history.append(TaskPreference(
            task_type=task_type,
            selected_device=selected_device,
            timestamp=now()
        ))

        # Keep last 1000 preferences
        if len(self.preference_history) > 1000:
            self.preference_history.pop(0)

    def predict_preferred_device(self, task_type: str) -> Optional[str]:
        """
        Predict preferred device for task type.

        Algorithm: Most frequently used device for task in last 30 days
        """
        cutoff = now() - timedelta(days=30)

        recent_prefs = [
            p for p in self.preference_history
            if p.task_type == task_type and p.timestamp > cutoff
        ]

        if not recent_prefs:
            return None

        # Count device frequencies
        device_counts = Counter([p.selected_device for p in recent_prefs])

        # Return most common
        return device_counts.most_common(1)[0][0]
```

---

## Integration with Existing Systems

### K0 P07 Multi-Device Sync Extension

**Extend ADR-0050 presence metadata:**

```python
# Add to K0 Bridge P07 sync payload
presence_metadata = {
    "device_id": "device-123",
    "device_type": "phone",
    "device_name": "Alice's iPhone",
    "online": True,
    "last_heartbeat_ts": 1730000000000,

    # Location (privacy-aware)
    "location": {
        "source": "WIFI_SSID",
        "place_name": "home",
        "privacy_band": "AMBER",
        "timestamp": 1730000000000
    },

    # BLE Proximity
    "nearby_devices": [
        {"device_id": "device-456", "proximity": "NEAR", "rssi": -60}
    ],

    # Active Session
    "is_active": True,
    "screen_state": "ON",
    "last_input_ts": 1730000005000,
    "foreground_app": "com.familyos.app",

    # Motion Context
    "motion_context": "STATIONARY",

    # Power State
    "battery_level": 75,
    "charging_status": "DISCHARGING",
    "power_mode": "NORMAL"
}
```

### SessionState Section 5 (Multimodal) Extension

**Add device context to SessionState:**

```python
# SessionState Section 5: Multimodal + Device Context
class MultimodalContext:
    # Existing multimodal fields (ADR-0017)
    active_modality: Modality  # TEXT, VOICE, IMAGE, VIDEO
    modality_history: List[Modality]

    # NEW: Device context fields
    active_device: str          # device_id of most recently active device
    all_devices: List[DevicePresence]  # All family devices with presence metadata
    device_switch_timestamp: int  # Timestamp of last device switch
    preferred_device: Optional[str]  # Learned device preference for current task
```

---

## Performance Characteristics

### Presence Update Latency

| Operation | Target Latency (P95) | Notes |
|-----------|---------------------|-------|
| Device heartbeat broadcast | <100ms | mDNS multicast |
| Presence state sync (LAN) | <50ms | K0 P07 TCP (ADR-0050) |
| BLE beacon scan | <3 seconds | Scan duration |
| Location update (GPS) | <2 seconds | Platform API |
| Active session detection | <1 second | Local polling |
| Notification coordination | <200ms | Presence lookup + routing |

### Resource Usage

- **CPU:** <2% average (background monitoring)
- **Memory:** <50 MB (presence state + device list)
- **Network:** <1 KB/s (heartbeat + presence sync)
- **Battery:** <1% per hour (BLE + GPS combined)

---

## Privacy & Security

### Privacy Bands (ADR-0032)

| Data Type | Privacy Band | Sync Behavior | Storage |
|-----------|-------------|---------------|---------|
| GPS coordinates | RED | Never leaves device | Local only |
| WiFi BSSID | AMBER | SHA256 hash before sync | K0 encrypted |
| WiFi SSID | AMBER | SHA256 hash before sync | K0 encrypted |
| IP geolocation (city) | GREEN | Syncs freely | K0 encrypted |
| Device online/offline | GREEN | Syncs freely | SessionState |
| Battery level | GREEN | Syncs freely | SessionState |
| Screen state | GREEN | Syncs freely | SessionState |

### Location Privacy

```python
def apply_location_privacy(location: Location) -> Location:
    """
    Apply privacy transformations before sync.

    RED: Keep precise GPS local, sync coarse city-level only
    AMBER: Hash WiFi SSID/BSSID before sync
    GREEN: Sync as-is
    """
    if location.privacy_band == PrivacyBand.RED:
        # Degrade to city-level for sync
        return Location(
            source="GPS_COARSE",
            city=geocode_to_city(location.latitude, location.longitude),
            accuracy_meters=5000,
            privacy_band=PrivacyBand.GREEN
        )

    elif location.privacy_band == PrivacyBand.AMBER:
        # Hash SSID before sync
        if location.source == "WIFI_SSID":
            location.place_name = hash_ssid(location.place_name)

        return location

    else:
        # GREEN: No transformation needed
        return location
```

---

## Observability

### Metrics

```python
# Prometheus metrics
device_presence_online_total = Gauge(
    'device_presence_online_total',
    'Number of online devices',
    ['device_type']
)

device_presence_heartbeat_latency_ms = Histogram(
    'device_presence_heartbeat_latency_ms',
    'Heartbeat broadcast latency',
    buckets=[10, 25, 50, 100, 250, 500]
)

device_presence_switch_total = Counter(
    'device_presence_switch_total',
    'Total device switches detected',
    ['from_device_type', 'to_device_type']
)

ble_proximity_devices_detected = Gauge(
    'ble_proximity_devices_detected',
    'Number of nearby devices detected via BLE',
    ['proximity_zone']
)

notification_coordination_suppressed_total = Counter(
    'notification_coordination_suppressed_total',
    'Notifications suppressed due to active device',
    ['suppressed_device_type']
)
```

### Events

```
device.online              — Device came online (heartbeat received)
device.offline             — Device went offline (heartbeat timeout)
device.switch              — User switched devices
location.updated           — Device location updated
ble.proximity.near         — Device detected in NEAR zone
session.active             — Device became active (screen on + input)
session.inactive           — Device became inactive (idle timeout)
notification.coordinated   — Notification routed to preferred device
```

---

## Implementation Plan

**Phase 1: Device Presence (Week 1-2)**
- Implement device heartbeat (mDNS + K0 P07)
- Online/offline detection
- Device switch detection
- SessionState Section 5 extension

**Phase 2: Location & BLE (Week 2-3)**
- GPS location tracking (mobile)
- WiFi triangulation (all devices)
- BLE beacon advertising/scanning
- Location privacy enforcement

**Phase 3: Session Monitoring (Week 3-4)**
- Active session detection (screen + input + foreground app)
- Motion sensor integration (accelerometer + gyroscope)
- Power state monitoring (battery + charging)

**Phase 4: Context Sharing (Week 4-5)**
- Notification coordination
- Device preference learning
- Cross-device handoff suggestions
- Integration testing

---

## Consequences

### Positive

1. **Seamless device handoff** (user switches devices without manual re-establishment)
2. **Smart notification coordination** (no duplicate alerts, prefer active device)
3. **Location-aware responses** ("You're at home, turning on living room lights")
4. **Proximity-based presence** (phone + watch = user present)
5. **Device preference learning** (laptop for long tasks, phone for quick queries)
6. **Privacy-preserving location** (RED GPS local-only, GREEN city-level synced)
7. **Battery-aware operations** (reduce tasks when battery low)

### Negative

1. **Privacy concerns** (location tracking requires careful user consent)
2. **Battery drain** (BLE + GPS continuous monitoring)
3. **Complexity** (7 presence mechanisms, extensive integration)
4. **False positives** (device detected as active when user away)
5. **Network overhead** (continuous heartbeat + presence sync)

### Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Location privacy leak** | RED band GPS never leaves device, AMBER WiFi hashed, user opt-in |
| **Battery drain** | Adjust polling intervals based on power mode, pause in low-power |
| **False active detection** | Combine screen + input + motion for high-confidence active state |
| **Notification suppression error** | Fallback to "send to all" if presence state uncertain |
| **BLE interference** | Use family-scoped UUIDs, validate beacon format |

---

## Related ADRs

- **ADR-0050:** Multi-Device Family Sync (K0 P07 foundation)
- **ADR-0017:** SessionState 6-Section Design (Section 5 extension)
- **ADR-0032:** Privacy Bands (location privacy enforcement)
- **ADR-0004:** Stream Switch (multi-modal input integration)
- **ADR-0065b:** Session Continuity Device Handoff (UX contracts)

**Sub-ADRs:**
- **ADR-0085a:** Device Presence Detection & Location Awareness (detailed location algorithms)
- **ADR-0085b:** BLE Proximity & Active Session Tracking (BLE protocol + session detection)
- **ADR-0085c:** Cross-Device Context Sharing & Presence-Aware Features (notification coordination + device preference)

---

## End of ADR-0085