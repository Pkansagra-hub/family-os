---
adr_number: '0085a'
title: Device Presence Detection & Location Awareness
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l1_input.device_presence.location
- k1.l1_input.device_presence.detector
- k1.l4_runtime.session_state.device_location
- k0.kernel.device_tracking.presence
concerns:
- architecture
- observability
- performance
- privacy
- scalability
- security
- testing
implementation_status: PLANNED
implementation_phase: Phase 5 (Cross-Device Extensions)
implementation_date: '2025-11-03'
propagation:
  affected_adrs:
  - ADR-0017
  - ADR-0032
  - ADR-0050
  - ADR-0085
  affected_contracts:
  - k0/contracts/api/device/location_tracking.yml
  - k0/contracts/api/device/presence_metadata.yml
  - k1/contracts/flatbuffers/layer1_input/device_location.fbs
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests:
  - tests/k1/l1_input/test_location_tracking.py
  - tests/k1/l1_input/test_presence_detector.py
  - tests/k0/kernel/test_device_presence.py
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
related_adrs:
- ADR-0017
- ADR-0017e
- ADR-0032
- ADR-0050
- ADR-0085
- ADR-0085a
- ADR-0085b
- ADR-0085c
related_contracts: []
related_diagrams: []
research_citations:
- "Location Privacy (Krumm, 2009)"
- "Indoor Localization (Liu et al., 2007)"
- "Context-Aware Systems (Dey, 2001)"
---

# ADR-0085a: Device Presence Detection & Location Awareness

**Status:** Proposed 🔄
**Parent ADR:** ADR-0085 (Embodied Awareness & Device Presence)
**Last Updated:** 2025-01-22

---

## Context

**From ADR-0085:** Embodied Awareness Layer requires **device presence tracking** and **location awareness** to enable context-aware multi-device experiences.

**Key Requirements:**

1. **Device Presence:** Track which devices online/offline, detect when user switches devices
2. **Location Tracking:** GPS (mobile), WiFi triangulation (indoor), IP geolocation (fallback)
3. **Location Privacy:** RED precise GPS local-only, AMBER WiFi hashed, GREEN city-level
4. **Coarse Location:** Detect home vs work vs traveling for contextual adaptations

**Integration:** Extends ADR-0050 Multi-Device Family Sync (K0 P07) with presence metadata

---

## Decision

Implement **two-layer presence architecture**:

### Layer 1: Device Presence (Online/Offline + Heartbeat)
### Layer 2: Location Awareness (GPS + WiFi + IP Geolocation)

**Privacy-First:** Location data classified by precision → RED/AMBER/GREEN bands

---

## Layer 1: Device Presence Detection

### Heartbeat Protocol

**Goal:** Detect online/offline devices via periodic heartbeats.

```python
class DeviceHeartbeatProtocol:
    """
    Broadcast presence heartbeat every 30 seconds via mDNS + K0 P07.

    Extends: ADR-0050 Multi-Device Family Sync Phase 1 (LAN-First mDNS)
    """

    def __init__(self, device_id: str, k0_bridge_p07):
        self.device_id = device_id
        self.k0_bridge = k0_bridge_p07
        self.heartbeat_interval_seconds = 30
        self.offline_threshold_seconds = 90  # 3 missed heartbeats

    async def broadcast_heartbeat(self):
        """
        Broadcast heartbeat continuously.

        Heartbeat payload (FlatBuffers schema):
        - device_id: UUID (unique device identifier)
        - device_type: Enum (PHONE, TABLET, LAPTOP, WATCH, SPEAKER)
        - device_name: String (user-friendly: "Alice's iPhone")
        - platform: String ("iOS 17.1", "macOS 14.2", "Android 14")
        - app_version: String ("FamilyOS 1.0.0-beta.3")
        - timestamp_ms: Int64 (UTC epoch milliseconds)
        - ip_address: String (for direct TCP connection)
        - port: Int (K0 Bridge P07 TCP port: 8765)
        - capabilities: Flags (HAS_GPS, HAS_CAMERA, HAS_BLE, HAS_MICROPHONE)
        """
        while True:
            heartbeat = DeviceHeartbeat(
                device_id=self.device_id,
                device_type=self.get_device_type(),
                device_name=self.get_device_name(),
                platform=self.get_platform_info(),
                app_version=get_app_version(),
                timestamp_ms=now_ms(),
                ip_address=get_local_ip(),
                port=self.k0_bridge.port,
                capabilities=self.get_device_capabilities()
            )

            # Broadcast via mDNS (LAN discovery, ADR-0050 Phase 1)
            await self.mdns_broadcast(heartbeat)

            # Publish to K0 P07 sync channel (CRDT Last-Write-Wins)
            await self.k0_bridge.publish_presence(heartbeat)

            logger.debug(
                "heartbeat_broadcast",
                device_id=self.device_id,
                device_type=heartbeat.device_type,
                timestamp_ms=heartbeat.timestamp_ms
            )

            # Wait 30 seconds
            await asyncio.sleep(self.heartbeat_interval_seconds)
```

### Online/Offline State Management

```python
class DeviceRegistry:
    """
    Track online/offline state for all family devices.

    States:
    - ONLINE: Heartbeat received within 90 seconds
    - OFFLINE: No heartbeat for >90 seconds
    - UNKNOWN: Device never seen before
    """

    def __init__(self):
        self.devices = {}  # device_id → DeviceState
        self.offline_threshold_ms = 90000  # 90 seconds

    async def process_heartbeat(self, heartbeat: DeviceHeartbeat):
        """
        Update device state from heartbeat.
        """
        device_id = heartbeat.device_id

        if device_id not in self.devices:
            # New device discovered
            self.devices[device_id] = DeviceState(
                device_id=device_id,
                device_type=heartbeat.device_type,
                device_name=heartbeat.device_name,
                platform=heartbeat.platform,
                status=DeviceStatus.ONLINE,
                last_heartbeat_ts=heartbeat.timestamp_ms,
                capabilities=heartbeat.capabilities,
                ip_address=heartbeat.ip_address,
                port=heartbeat.port
            )

            await self.emit_event("device.discovered", device_id=device_id)

        else:
            # Update existing device
            device = self.devices[device_id]
            previous_status = device.status
            device.last_heartbeat_ts = heartbeat.timestamp_ms
            device.ip_address = heartbeat.ip_address
            device.status = DeviceStatus.ONLINE

            # Detect status transitions
            if previous_status == DeviceStatus.OFFLINE:
                await self.emit_event("device.online", device_id=device_id)

    async def check_offline_devices(self):
        """
        Periodically check for offline devices (no heartbeat >90s).

        Run every 10 seconds.
        """
        while True:
            current_time = now_ms()

            for device_id, device in self.devices.items():
                time_since_heartbeat = current_time - device.last_heartbeat_ts

                if time_since_heartbeat > self.offline_threshold_ms:
                    if device.status == DeviceStatus.ONLINE:
                        # Device went offline
                        device.status = DeviceStatus.OFFLINE

                        await self.emit_event("device.offline", device_id=device_id)

                        logger.warning(
                            "device_offline",
                            device_id=device_id,
                            device_name=device.device_name,
                            time_since_heartbeat_ms=time_since_heartbeat
                        )

            await asyncio.sleep(10)
```

### Device Switch Detection

```python
def detect_device_switch(
    self,
    previous_active: str,
    current_active: str
) -> DeviceSwitch:
    """
    Detect when user switches between devices.

    Criteria:
    1. Previous device becomes inactive (screen off OR no input >30s)
    2. Current device becomes active (screen on AND recent input <5s)
    3. Switch occurs within 60 seconds (likely same user)
    4. Devices in proximity (BLE NEAR/MEDIUM zone, optional)

    Returns: DeviceSwitch with confidence score (0.0-1.0)
    """
    if previous_active == current_active:
        return None  # No switch

    prev_device = self.devices.get(previous_active)
    curr_device = self.devices.get(current_active)

    if not prev_device or not curr_device:
        return None

    # Calculate confidence score
    confidence = 0.0

    # Factor 1: Timing (switch within 60s → +0.40 confidence)
    time_diff = curr_device.became_active_ts - prev_device.became_inactive_ts
    if time_diff < 60000:  # 60 seconds
        confidence += 0.40

    # Factor 2: Proximity (devices NEAR → +0.30 confidence)
    proximity = self.get_device_proximity(previous_active, current_active)
    if proximity == ProximityZone.NEAR:
        confidence += 0.30
    elif proximity == ProximityZone.MEDIUM:
        confidence += 0.15

    # Factor 3: Device sequence (common switch pattern → +0.30 confidence)
    if self.is_common_switch_pattern(previous_active, current_active):
        confidence += 0.30

    return DeviceSwitch(
        from_device=previous_active,
        to_device=current_active,
        timestamp=curr_device.became_active_ts,
        confidence=confidence
    )
```

---

## Layer 2: Location Awareness

### Location Tracking Architecture

**Three-tier fallback system:**

1. **GPS** (mobile only): High precision (<10m), RED privacy band
2. **WiFi triangulation** (all devices): Medium precision (<50m), AMBER privacy band
3. **IP geolocation** (fallback): City-level precision (~5km), GREEN privacy band

```python
class LocationTracker:
    """
    Track device location via GPS, WiFi, or IP geolocation.

    Privacy bands:
    - GPS: RED (never leaves device, sync coarse city-level only)
    - WiFi BSSID: AMBER (hash before sync)
    - WiFi SSID: AMBER (hash before sync)
    - IP geolocation: GREEN (sync freely)
    """

    def __init__(self):
        self.current_location = None
        self.location_history = []  # Last 100 locations
        self.known_places = {}      # SSID → Place mapping (home, work, etc.)

    async def update_location(self) -> Optional[Location]:
        """
        Update device location using best available method.

        Priority:
        1. GPS (if available + permission granted)
        2. WiFi triangulation (if WiFi enabled)
        3. IP geolocation (always available)

        Returns: Location with privacy_band classification
        """
        location = None

        # Try GPS (mobile devices only)
        if self.has_gps_capability() and self.gps_permission_granted():
            location = await self.get_gps_location()

        # Fallback to WiFi triangulation
        if location is None and self.has_wifi_capability():
            location = await self.get_wifi_location()

        # Fallback to IP geolocation
        if location is None:
            location = await self.get_ip_location()

        if location:
            self.current_location = location
            self.append_to_history(location)

            # Detect significant location change (>100m)
            if self.is_significant_change(location):
                await self.handle_location_change(location)

        return location
```

### GPS Location (High Precision, RED Band)

```python
async def get_gps_location(self) -> Optional[Location]:
    """
    Get GPS location (high precision <10m).

    Platform APIs:
    - iOS: CoreLocation (CLLocationManager)
    - Android: FusedLocationProviderClient
    - Desktop: Not typically available

    Privacy: RED band (precise location never synced, only coarse city-level)
    """
    # Request GPS permission if not granted
    if not self.gps_permission_granted():
        await self.request_gps_permission()
        return None

    # Query platform GPS API
    gps_data = await platform_get_gps()  # Platform-specific implementation

    if gps_data is None:
        logger.debug("gps_unavailable")
        return None

    location = Location(
        source=LocationSource.GPS,
        latitude=gps_data.latitude,
        longitude=gps_data.longitude,
        altitude=gps_data.altitude,
        accuracy_meters=gps_data.accuracy,
        timestamp=now(),
        privacy_band=PrivacyBand.RED
    )

    logger.info(
        "gps_location_acquired",
        latitude=round(gps_data.latitude, 2),  # Log with reduced precision
        longitude=round(gps_data.longitude, 2),
        accuracy_meters=gps_data.accuracy,
        privacy_band="RED"
    )

    return location
```

### WiFi Location (Medium Precision, AMBER Band)

```python
async def get_wifi_location(self) -> Optional[Location]:
    """
    Get WiFi-based location via BSSID triangulation or SSID matching.

    Method 1: BSSID triangulation (medium precision <50m)
    - Scan WiFi networks, collect BSSIDs + signal strengths
    - Query WiFi positioning service (e.g., Google Geolocation API)
    - Returns lat/lng estimate

    Method 2: SSID matching (coarse precision, building-level)
    - Match detected SSID against known places ("HomeWiFi" → home location)
    - Use pre-configured SSID → place mapping

    Privacy: AMBER band (hash SSID/BSSID before sync)
    """
    # Scan WiFi networks
    wifi_networks = await scan_wifi_networks()

    if not wifi_networks:
        logger.debug("no_wifi_networks_detected")
        return None

    # Try BSSID triangulation first (more accurate)
    location = await self.triangulate_wifi_bssids(wifi_networks)

    if location:
        logger.info(
            "wifi_bssid_location_acquired",
            accuracy_meters=location.accuracy_meters,
            privacy_band="AMBER"
        )
        return location

    # Fallback to SSID matching for known networks
    for network in wifi_networks:
        ssid = network.ssid

        if ssid in self.known_places:
            place = self.known_places[ssid]

            location = Location(
                source=LocationSource.WIFI_SSID,
                place_name=place.name,
                place_category=place.category,  # HOME, WORK, GYM, etc.
                latitude=place.latitude,
                longitude=place.longitude,
                accuracy_meters=50,  # Building-level accuracy
                timestamp=now(),
                privacy_band=PrivacyBand.AMBER
            )

            logger.info(
                "wifi_ssid_location_matched",
                ssid_hash=hash_ssid(ssid),  # Log hash only
                place_name=place.name,
                place_category=place.category,
                privacy_band="AMBER"
            )

            return location

    return None

async def triangulate_wifi_bssids(
    self,
    wifi_networks: List[WiFiNetwork]
) -> Optional[Location]:
    """
    Triangulate location from WiFi BSSIDs.

    Uses: Google Geolocation API or Mozilla Location Service (MLS)

    Request format:
    {
      "wifiAccessPoints": [
        {"macAddress": "00:11:22:33:44:55", "signalStrength": -65},
        {"macAddress": "AA:BB:CC:DD:EE:FF", "signalStrength": -72}
      ]
    }

    Response: {"location": {"lat": 47.6, "lng": -122.3}, "accuracy": 30}
    """
    # Build WiFi access point list
    wifi_aps = [
        {
            "macAddress": network.bssid,
            "signalStrength": network.rssi
        }
        for network in wifi_networks
    ]

    # Query geolocation service
    response = await http_post(
        url="https://www.googleapis.com/geolocation/v1/geolocate",
        params={"key": self.google_api_key},
        json={"wifiAccessPoints": wifi_aps}
    )

    if response.status_code != 200:
        logger.warning("wifi_triangulation_failed", status=response.status_code)
        return None

    data = response.json()

    location = Location(
        source=LocationSource.WIFI_BSSID,
        latitude=data["location"]["lat"],
        longitude=data["location"]["lng"],
        accuracy_meters=data["accuracy"],
        timestamp=now(),
        privacy_band=PrivacyBand.AMBER
    )

    return location
```

### IP Geolocation (Coarse Precision, GREEN Band)

```python
async def get_ip_location(self) -> Optional[Location]:
    """
    Get IP-based location (city-level precision ~5km).

    Uses: MaxMind GeoLite2 database (embedded, no external API calls)

    Privacy: GREEN band (coarse location safe to sync)
    """
    # Get public IP address
    ip_address = await get_public_ip()

    # Query GeoIP database (local lookup, no external API)
    geo_data = self.geoip_database.lookup(ip_address)

    if geo_data is None:
        logger.debug("geoip_lookup_failed", ip=ip_address)
        return None

    location = Location(
        source=LocationSource.IP_GEOLOCATION,
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
        "ip_geolocation_acquired",
        city=geo_data.city,
        region=geo_data.region,
        country=geo_data.country,
        privacy_band="GREEN"
    )

    return location
```

---

## Coarse Location Detection

**Goal:** Classify location into categories for contextual responses.

```python
class CoarseLocationClassifier:
    """
    Classify location into coarse categories.

    Categories:
    - HOME: At home location (WiFi SSID match or GPS within 100m)
    - WORK: At work location (WiFi SSID match or GPS within 100m)
    - TRAVELING: Far from home/work (>10km from both)
    - UNKNOWN: Cannot determine
    """

    def __init__(self):
        self.known_places = {
            "home": None,  # User-configured home location
            "work": None   # User-configured work location
        }

    def classify_location(self, location: Location) -> PlaceCategory:
        """
        Classify location into category.

        Priority:
        1. Direct SSID match (home/work WiFi)
        2. GPS proximity check (within 100m of home/work)
        3. Traveling detection (>10km from both)
        """
        # Direct SSID match (most reliable)
        if location.source == LocationSource.WIFI_SSID:
            if location.place_category:
                return location.place_category  # Already classified

        # GPS proximity check
        if location.source == LocationSource.GPS:
            home_distance = self.distance_to_place(location, "home")
            work_distance = self.distance_to_place(location, "work")

            if home_distance is not None and home_distance < 100:
                return PlaceCategory.HOME

            if work_distance is not None and work_distance < 100:
                return PlaceCategory.WORK

            # Check if traveling (>10km from both)
            if home_distance and work_distance:
                if home_distance > 10000 and work_distance > 10000:
                    return PlaceCategory.TRAVELING

        return PlaceCategory.UNKNOWN

    def distance_to_place(
        self,
        location: Location,
        place_name: str
    ) -> Optional[float]:
        """
        Calculate distance to known place (meters).

        Uses: Haversine formula for lat/lng distance
        """
        place = self.known_places.get(place_name)

        if place is None:
            return None

        return haversine_distance(
            location.latitude, location.longitude,
            place.latitude, place.longitude
        )
```

---

## Privacy Enforcement

### Location Privacy Transform

```python
def apply_location_privacy(location: Location) -> Location:
    """
    Apply privacy transformations before syncing to other devices.

    RED → Degrade to GREEN city-level before sync
    AMBER → Hash SSID/BSSID before sync
    GREEN → Sync as-is
    """
    if location.privacy_band == PrivacyBand.RED:
        # RED: Degrade GPS to city-level (GREEN) for sync
        city = geocode_to_city(location.latitude, location.longitude)

        return Location(
            source=LocationSource.GPS_COARSE,
            city=city.name,
            region=city.region,
            country=city.country,
            latitude=city.latitude,
            longitude=city.longitude,
            accuracy_meters=5000,  # City-level accuracy
            timestamp=location.timestamp,
            privacy_band=PrivacyBand.GREEN
        )

    elif location.privacy_band == PrivacyBand.AMBER:
        # AMBER: Hash SSID/BSSID before sync
        if location.source == LocationSource.WIFI_SSID:
            location.place_name = hash_ssid(location.place_name)

        return location

    else:
        # GREEN: Sync as-is
        return location

def hash_ssid(ssid: str) -> str:
    """
    Hash WiFi SSID for privacy.

    Algorithm: SHA256(ssid + family_salt)[:16]

    Preserves equality (same SSID → same hash) within family
    Prevents external correlation (different families → different hash)
    """
    family_salt = get_family_salt()
    hash_input = f"{ssid}{family_salt}".encode('utf-8')
    hash_full = hashlib.sha256(hash_input).hexdigest()

    return hash_full[:16]  # 16-char hash
```

---

## K0 P07 Presence Metadata Sync

**Extend ADR-0050 K0 Bridge P07 sync payload:**

```python
# Presence metadata synced via K0 P07 CRDT (Last-Write-Wins)
presence_metadata = {
    "device_id": "device-abc123",
    "device_type": "PHONE",
    "device_name": "Alice's iPhone",
    "timestamp_ms": 1730000000000,

    # Device presence
    "online": True,
    "last_heartbeat_ts": 1730000000000,
    "ip_address": "192.168.1.10",
    "port": 8765,

    # Location (privacy-aware)
    "location": {
        "source": "WIFI_SSID",
        "place_name": "a3f8c9d21e4b6a7c",  # Hashed SSID
        "place_category": "HOME",
        "accuracy_meters": 50,
        "timestamp": 1730000000000,
        "privacy_band": "AMBER"
    },

    # Or coarse GPS (RED degraded to GREEN for sync)
    "location_coarse": {
        "source": "GPS_COARSE",
        "city": "Seattle",
        "region": "Washington",
        "country": "USA",
        "accuracy_meters": 5000,
        "privacy_band": "GREEN"
    }
}
```

---

## SessionState Storage

**Extend SessionState Section 5 (Multimodal) with device context:**

```python
class MultimodalContext:
    # Existing multimodal fields (ADR-0017)
    active_modality: Modality  # TEXT, VOICE, IMAGE, VIDEO
    modality_history: List[Modality]

    # NEW: Device presence fields
    active_device: str          # device_id of most recently active device
    all_devices: List[DevicePresenceState]  # All family devices + metadata
    device_switch_timestamp: int  # Timestamp of last device switch (epoch ms)

    # NEW: Location context fields
    current_location: Optional[Location]  # Current device location
    location_history: List[Location]      # Last 10 locations
    coarse_location: PlaceCategory        # HOME, WORK, TRAVELING, UNKNOWN
```

---

## Performance Characteristics

| Operation | Target Latency (P95) | Notes |
|-----------|---------------------|-------|
| Heartbeat broadcast | <100ms | mDNS multicast + K0 P07 publish |
| Online/offline detection | <10 seconds | Check every 10s |
| Device switch detection | <5 seconds | Active state transition |
| GPS location update | <2 seconds | Platform API |
| WiFi BSSID triangulation | <3 seconds | External API call |
| WiFi SSID matching | <50ms | Local lookup |
| IP geolocation | <100ms | Local GeoIP database |
| Presence metadata sync | <50ms | K0 P07 LAN TCP (ADR-0050) |

---

## Observability

### Metrics

```python
device_presence_online = Gauge(
    'device_presence_online',
    'Number of online devices',
    ['device_type']
)

device_presence_heartbeat_latency_ms = Histogram(
    'device_presence_heartbeat_latency_ms',
    'Heartbeat broadcast latency'
)

location_update_total = Counter(
    'location_update_total',
    'Location updates by source',
    ['source', 'privacy_band']
)

location_update_latency_ms = Histogram(
    'location_update_latency_ms',
    'Location update latency by source',
    ['source']
)
```

### Events

```
device.discovered         — New device seen
device.online             — Device came online
device.offline            — Device went offline
device.switch             — User switched devices
location.updated          — Location updated
location.coarse.changed   — Coarse location category changed (HOME → WORK)
```

---

## Related ADRs

- **ADR-0085:** Embodied Awareness & Device Presence (parent)
- **ADR-0050:** Multi-Device Family Sync (K0 P07 foundation)
- **ADR-0032:** Privacy Bands (location privacy enforcement)
- **ADR-0017:** SessionState 6-Section Design (Section 5 extension)

---

## End of ADR-0085a
