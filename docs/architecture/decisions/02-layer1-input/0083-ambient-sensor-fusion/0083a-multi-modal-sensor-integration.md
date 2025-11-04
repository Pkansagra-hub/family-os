---
adr_number: 0083a
affected_layers:
- layer1_input
- layer4_runtime
affected_modules:
- k1.l1_input.streams.sensor_drivers
- k1.l1_input.sensor_fusion.integration
- k1.l4_runtime.sensor_state
- k0.drivers.sensor_abstraction
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- modularity
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
  - ADR-0083
  - ADR-0083a
  affected_contracts:
  - k0/contracts/api/sensors/sensor_driver.yml
  - k0/contracts/api/sensors/sensor_data_schema.yml
  - k1/contracts/flatbuffers/layer1_input/sensor_input.fbs
  affected_tests:
  - tests/k1/l1_input/test_sensor_drivers.py
  - tests/k1/l1_input/test_multi_modal_integration.py
  - tests/k0/drivers/test_sensor_abstraction.py
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
related_adrs:
- ADR-0017
- ADR-0083
- ADR-0083a
- ADR-0083c
related_contracts: []
related_diagrams: []
research_citations:
- Sensor Abstraction Layers (Bonnet et al., 2008)
- IoT Device Integration (Guinard et al., 2011)
- Heterogeneous Sensor Networks (Akyildiz et al., 2002)
status: ACCEPTED
title: Multi-Modal Sensor Integration
---

# ADR-0083a: Multi-Modal Sensor Integration

**Status:** Proposed 🔄
**Parent ADR:** ADR-0083 (Ambient Sensor Fusion)
**Capability:** #3 - Ambient Context Awareness
**Priority:** Post-MVP v1.1
**Date:** 2025-10-22

---

## Context

### Problem Statement

**Parent ADR Challenge:** ADR-0083 defines 6 sensor types for ambient awareness but doesn't specify driver architecture, data normalization, or sensor abstraction layer.

**Key Questions:**
1. How do we integrate heterogeneous sensors (PIR GPIO, mmWave UART, BLE HCI, WiFi API, Camera USB, Light I2C)?
2. How do we normalize sensor data into unified schema for fusion algorithm?
3. How do we handle sensor failures gracefully (driver crashes, hardware disconnects)?
4. How do we ensure <200ms latency budget (sensor collection critical path)?

**Current Gap:**
- No sensor driver abstraction layer defined
- No unified sensor data schema
- No error handling strategy for sensor failures
- No driver lifecycle management (start/stop/restart)

---

## Decision

### Architecture: 3-Layer Sensor Integration

```
Layer 1: Sensor Drivers (6 types, hardware-specific)
   ↓
Layer 2: Data Normalization (unified schema, timestamp sync)
   ↓
Layer 3: Sensor Registry (discovery, lifecycle, health monitoring)
```

---

### Layer 1: Sensor Drivers

**Driver Interface (Abstract Base Class):**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any
import time

@dataclass
class SensorReading:
    """Unified sensor reading format (post-normalization)"""
    sensor_id: str              # "pir_living_room_01"
    sensor_type: str            # "PIR" | "mmWave" | "BLE" | "WiFi" | "Camera" | "Light"
    timestamp_ms: int           # Unix timestamp (milliseconds)
    raw_data: Any               # Driver-specific raw data
    normalized_data: dict       # Normalized key-value pairs
    confidence: float           # 0.0-1.0 (driver's confidence in reading)
    privacy_band: PrivacyBand   # GREEN | AMBER | RED
    latency_ms: float           # Time from hardware event to reading creation

class SensorDriver(ABC):
    """Abstract sensor driver interface"""

    def __init__(self, sensor_id: str, config: dict):
        self.sensor_id = sensor_id
        self.config = config
        self.is_running = False
        self.last_reading: Optional[SensorReading] = None
        self.error_count = 0

    @abstractmethod
    async def start(self) -> bool:
        """Initialize hardware, start sampling. Returns True if successful."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop sampling, release hardware resources."""
        pass

    @abstractmethod
    async def read(self) -> Optional[SensorReading]:
        """Read current sensor value. Returns None if error."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if sensor hardware is responsive. Returns True if healthy."""
        pass

    def get_latency_budget_ms(self) -> int:
        """Return driver's latency budget (see ADR-0083 performance budgets)"""
        latency_budgets = {
            "PIR": 10,
            "mmWave": 20,
            "BLE": 50,
            "WiFi": 100,
            "Camera": 200,
            "Light": 5
        }
        return latency_budgets.get(self.sensor_type, 100)
```

---

### Driver Implementations

#### 1. PIR Motion Sensor Driver

```python
class PIRMotionDriver(SensorDriver):
    """
    PIR (Passive Infrared) motion sensor driver.

    Hardware: HC-SR501 PIR sensor via GPIO
    Interface: Digital input (HIGH=motion, LOW=no motion)
    Latency Budget: <10ms
    Privacy Band: GREEN (binary motion, no PII)
    """

    def __init__(self, sensor_id: str, config: dict):
        super().__init__(sensor_id, config)
        self.sensor_type = "PIR"
        self.gpio_pin = config["gpio_pin"]  # e.g., 17
        self.gpio = None
        self.last_motion_ts = 0

    async def start(self) -> bool:
        """Initialize GPIO pin for input"""
        try:
            import RPi.GPIO as GPIO  # Raspberry Pi GPIO library
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio_pin, GPIO.IN)
            self.gpio = GPIO
            self.is_running = True
            logger.info(f"PIR driver started: {self.sensor_id} on GPIO {self.gpio_pin}")
            return True
        except Exception as e:
            logger.error(f"PIR driver start failed: {e}")
            return False

    async def stop(self) -> None:
        """Release GPIO resources"""
        if self.gpio:
            self.gpio.cleanup(self.gpio_pin)
        self.is_running = False

    async def read(self) -> Optional[SensorReading]:
        """Read GPIO pin state (motion detected = HIGH)"""
        if not self.is_running:
            return None

        start_time = time.time()

        try:
            motion_detected = self.gpio.input(self.gpio_pin) == GPIO.HIGH

            if motion_detected:
                self.last_motion_ts = int(time.time() * 1000)

            reading = SensorReading(
                sensor_id=self.sensor_id,
                sensor_type="PIR",
                timestamp_ms=int(time.time() * 1000),
                raw_data={"gpio_state": motion_detected},
                normalized_data={
                    "motion_detected": motion_detected,
                    "last_motion_ts": self.last_motion_ts
                },
                confidence=1.0,  # PIR is binary, always confident
                privacy_band=PrivacyBand.GREEN,
                latency_ms=(time.time() - start_time) * 1000
            )

            self.last_reading = reading
            return reading

        except Exception as e:
            logger.error(f"PIR read error: {e}")
            self.error_count += 1
            return None

    def health_check(self) -> bool:
        """Check if GPIO is accessible"""
        try:
            self.gpio.input(self.gpio_pin)
            return True
        except:
            return False
```

---

#### 2. mmWave Radar Driver

```python
class mmWaveRadarDriver(SensorDriver):
    """
    mmWave (millimeter-wave) radar sensor for presence detection.

    Hardware: LD2410 or HLK-LD2410 mmWave module
    Interface: UART (9600 baud)
    Latency Budget: <20ms
    Privacy Band: GREEN (range + micro-doppler, no visual PII)
    """

    def __init__(self, sensor_id: str, config: dict):
        super().__init__(sensor_id, config)
        self.sensor_type = "mmWave"
        self.uart_port = config["uart_port"]  # "/dev/ttyUSB0"
        self.baud_rate = config.get("baud_rate", 9600)
        self.serial = None

    async def start(self) -> bool:
        """Open UART serial connection"""
        try:
            import serial
            self.serial = serial.Serial(
                port=self.uart_port,
                baudrate=self.baud_rate,
                timeout=0.02  # 20ms timeout matches latency budget
            )
            self.is_running = True
            logger.info(f"mmWave driver started: {self.sensor_id} on {self.uart_port}")
            return True
        except Exception as e:
            logger.error(f"mmWave driver start failed: {e}")
            return False

    async def stop(self) -> None:
        """Close UART connection"""
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.is_running = False

    async def read(self) -> Optional[SensorReading]:
        """Read mmWave radar data (LD2410 protocol)"""
        if not self.is_running:
            return None

        start_time = time.time()

        try:
            # LD2410 protocol: 0xFD FC FB FA (header) + payload + checksum
            data = self.serial.read(23)  # LD2410 frame size

            if len(data) < 23 or data[:4] != b'\xFD\xFC\xFB\xFA':
                return None  # Invalid frame

            # Parse LD2410 data (simplified)
            presence_detected = data[6] != 0x00
            range_cm = int.from_bytes(data[7:9], 'little')
            micro_doppler = data[10] / 100.0  # Breathing rate (Hz)

            reading = SensorReading(
                sensor_id=self.sensor_id,
                sensor_type="mmWave",
                timestamp_ms=int(time.time() * 1000),
                raw_data={"frame": data.hex()},
                normalized_data={
                    "presence_detected": presence_detected,
                    "range_cm": range_cm,
                    "micro_doppler": micro_doppler
                },
                confidence=0.90 if presence_detected else 0.95,  # High confidence
                privacy_band=PrivacyBand.GREEN,
                latency_ms=(time.time() - start_time) * 1000
            )

            self.last_reading = reading
            return reading

        except Exception as e:
            logger.error(f"mmWave read error: {e}")
            self.error_count += 1
            return None

    def health_check(self) -> bool:
        """Check if UART is responsive"""
        try:
            return self.serial and self.serial.is_open
        except:
            return False
```

---

#### 3. BLE Proximity Driver

```python
class BLEProximityDriver(SensorDriver):
    """
    BLE (Bluetooth Low Energy) proximity detector.

    Hardware: BLE adapter (built-in or USB dongle)
    Interface: HCI (Host Controller Interface) via bluez/bleak
    Latency Budget: <50ms
    Privacy Band: AMBER (MAC addresses require hashing)
    """

    def __init__(self, sensor_id: str, config: dict):
        super().__init__(sensor_id, config)
        self.sensor_type = "BLE"
        self.scan_duration_ms = config.get("scan_duration_ms", 500)
        self.rssi_threshold = config.get("rssi_threshold", -70)  # -70 dBm
        self.scanner = None
        self.enrolled_devices = config.get("enrolled_devices", {})  # MAC → owner

    async def start(self) -> bool:
        """Initialize BLE scanner"""
        try:
            from bleak import BleakScanner
            self.scanner = BleakScanner()
            self.is_running = True
            logger.info(f"BLE driver started: {self.sensor_id}")
            return True
        except Exception as e:
            logger.error(f"BLE driver start failed: {e}")
            return False

    async def stop(self) -> None:
        """Stop BLE scanning"""
        self.is_running = False

    async def read(self) -> Optional[SensorReading]:
        """Scan for BLE devices in range"""
        if not self.is_running:
            return None

        start_time = time.time()

        try:
            # Scan for BLE devices (500ms window)
            devices = await self.scanner.discover(timeout=self.scan_duration_ms / 1000.0)

            detected_devices = []
            for device in devices:
                if device.rssi >= self.rssi_threshold:
                    # Hash MAC address for privacy (AMBER band)
                    mac_hash = hashlib.sha256(device.address.encode()).hexdigest()[:16]
                    owner = self.enrolled_devices.get(device.address, None)

                    detected_devices.append({
                        "mac_hash": mac_hash,
                        "rssi": device.rssi,
                        "device_type": infer_device_type(device.name),
                        "owner": owner
                    })

            reading = SensorReading(
                sensor_id=self.sensor_id,
                sensor_type="BLE",
                timestamp_ms=int(time.time() * 1000),
                raw_data={"device_count": len(devices)},
                normalized_data={
                    "detected_devices": detected_devices,
                    "enrolled_count": len([d for d in detected_devices if d["owner"]])
                },
                confidence=0.70,  # Medium confidence (device ≠ person always)
                privacy_band=PrivacyBand.AMBER,  # MAC addresses are PII
                latency_ms=(time.time() - start_time) * 1000
            )

            self.last_reading = reading
            return reading

        except Exception as e:
            logger.error(f"BLE read error: {e}")
            self.error_count += 1
            return None

    def health_check(self) -> bool:
        """Check if BLE adapter is available"""
        try:
            import bluetooth
            bluetooth.discover_devices(duration=1, lookup_names=False)
            return True
        except:
            return False
```

---

#### 4. WiFi Proximity Driver

```python
class WiFiProximityDriver(SensorDriver):
    """
    WiFi proximity detector (connected device count).

    Hardware: WiFi Access Point API (Router admin API)
    Interface: HTTP REST API or SNMP
    Latency Budget: <100ms
    Privacy Band: GREEN (device count only, no MAC addresses)
    """

    def __init__(self, sensor_id: str, config: dict):
        super().__init__(sensor_id, config)
        self.sensor_type = "WiFi"
        self.ap_url = config["ap_url"]  # "http://192.168.1.1/api"
        self.api_key = config.get("api_key", None)

    async def start(self) -> bool:
        """Test WiFi AP API connectivity"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.ap_url}/status", timeout=1.0) as resp:
                    if resp.status == 200:
                        self.is_running = True
                        logger.info(f"WiFi driver started: {self.sensor_id}")
                        return True
            return False
        except Exception as e:
            logger.error(f"WiFi driver start failed: {e}")
            return False

    async def stop(self) -> None:
        """No cleanup needed for HTTP API"""
        self.is_running = False

    async def read(self) -> Optional[SensorReading]:
        """Query WiFi AP for connected device count"""
        if not self.is_running:
            return None

        start_time = time.time()

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                async with session.get(f"{self.ap_url}/devices", headers=headers, timeout=0.1) as resp:
                    data = await resp.json()

                    connected_devices = len(data.get("devices", []))
                    bandwidth_usage = sum(d.get("bandwidth_mbps", 0) for d in data.get("devices", []))

                    reading = SensorReading(
                        sensor_id=self.sensor_id,
                        sensor_type="WiFi",
                        timestamp_ms=int(time.time() * 1000),
                        raw_data=data,
                        normalized_data={
                            "connected_devices": connected_devices,
                            "bandwidth_usage_mbps": bandwidth_usage
                        },
                        confidence=0.50,  # Low confidence (devices may be idle)
                        privacy_band=PrivacyBand.GREEN,
                        latency_ms=(time.time() - start_time) * 1000
                    )

                    self.last_reading = reading
                    return reading

        except Exception as e:
            logger.error(f"WiFi read error: {e}")
            self.error_count += 1
            return None

    def health_check(self) -> bool:
        """Check if WiFi AP API is reachable"""
        try:
            import requests
            resp = requests.get(f"{self.ap_url}/status", timeout=1.0)
            return resp.status_code == 200
        except:
            return False
```

---

#### 5. Camera Person Detection Driver

```python
class CameraPersonDriver(SensorDriver):
    """
    Camera-based person detection (ML person counting + face recognition).

    Hardware: USB camera or IP camera
    Interface: OpenCV + YOLO/MobileNet person detection
    Latency Budget: <200ms
    Privacy Band: RED (visual data, local-only processing)
    """

    def __init__(self, sensor_id: str, config: dict):
        super().__init__(sensor_id, config)
        self.sensor_type = "Camera"
        self.camera_index = config.get("camera_index", 0)
        self.model_path = config.get("model_path", "yolov5s.pt")
        self.cap = None
        self.model = None

    async def start(self) -> bool:
        """Initialize camera and ML model"""
        try:
            import cv2
            import torch

            # Open camera
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                return False

            # Load YOLO person detection model (RED band, local-only)
            self.model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
            self.model.classes = [0]  # Filter to "person" class only

            self.is_running = True
            logger.info(f"Camera driver started: {self.sensor_id}")
            return True
        except Exception as e:
            logger.error(f"Camera driver start failed: {e}")
            return False

    async def stop(self) -> None:
        """Release camera resources"""
        if self.cap:
            self.cap.release()
        self.is_running = False

    async def read(self) -> Optional[SensorReading]:
        """Capture frame and detect persons (YOLO inference)"""
        if not self.is_running:
            return None

        start_time = time.time()

        try:
            # Capture frame
            ret, frame = self.cap.read()
            if not ret:
                return None

            # YOLO person detection
            results = self.model(frame)
            detections = results.pandas().xyxy[0]  # Bounding boxes

            person_count = len(detections)
            bounding_boxes = detections[['xmin', 'ymin', 'xmax', 'ymax']].values.tolist()

            reading = SensorReading(
                sensor_id=self.sensor_id,
                sensor_type="Camera",
                timestamp_ms=int(time.time() * 1000),
                raw_data={"frame_shape": frame.shape},  # No frame data (privacy)
                normalized_data={
                    "person_count": person_count,
                    "bounding_boxes": bounding_boxes,
                    "detected_faces": []  # Face recognition optional
                },
                confidence=0.95 if person_count > 0 else 0.90,
                privacy_band=PrivacyBand.RED,  # LOCAL-ONLY (no egress)
                latency_ms=(time.time() - start_time) * 1000
            )

            self.last_reading = reading
            return reading

        except Exception as e:
            logger.error(f"Camera read error: {e}")
            self.error_count += 1
            return None

    def health_check(self) -> bool:
        """Check if camera is accessible"""
        try:
            ret, _ = self.cap.read()
            return ret
        except:
            return False
```

---

#### 6. Ambient Light Sensor Driver

```python
class AmbientLightDriver(SensorDriver):
    """
    Ambient light sensor (lux measurement).

    Hardware: TSL2561 or BH1750 I2C light sensor
    Interface: I2C (smbus)
    Latency Budget: <5ms
    Privacy Band: GREEN (no PII)
    """

    def __init__(self, sensor_id: str, config: dict):
        super().__init__(sensor_id, config)
        self.sensor_type = "Light"
        self.i2c_address = config.get("i2c_address", 0x23)  # BH1750 default
        self.bus = None

    async def start(self) -> bool:
        """Initialize I2C bus"""
        try:
            import smbus2
            self.bus = smbus2.SMBus(1)  # I2C bus 1 on Raspberry Pi
            self.is_running = True
            logger.info(f"Light sensor started: {self.sensor_id}")
            return True
        except Exception as e:
            logger.error(f"Light sensor start failed: {e}")
            return False

    async def stop(self) -> None:
        """Close I2C bus"""
        if self.bus:
            self.bus.close()
        self.is_running = False

    async def read(self) -> Optional[SensorReading]:
        """Read lux value from BH1750"""
        if not self.is_running:
            return None

        start_time = time.time()

        try:
            # BH1750 continuous high-res mode
            data = self.bus.read_i2c_block_data(self.i2c_address, 0x10, 2)
            lux = (data[1] + (256 * data[0])) / 1.2

            reading = SensorReading(
                sensor_id=self.sensor_id,
                sensor_type="Light",
                timestamp_ms=int(time.time() * 1000),
                raw_data={"raw_value": data},
                normalized_data={"lux": lux},
                confidence=1.0,  # Light sensor is reliable
                privacy_band=PrivacyBand.GREEN,
                latency_ms=(time.time() - start_time) * 1000
            )

            self.last_reading = reading
            return reading

        except Exception as e:
            logger.error(f"Light sensor read error: {e}")
            self.error_count += 1
            return None

    def health_check(self) -> bool:
        """Check if I2C device responds"""
        try:
            self.bus.read_byte(self.i2c_address)
            return True
        except:
            return False
```

---

### Layer 2: Data Normalization

**Normalization Pipeline:**

```python
class SensorNormalizer:
    """
    Normalize heterogeneous sensor readings into unified schema.

    Responsibilities:
    - Timestamp synchronization (all readings use system clock)
    - Confidence score normalization (0.0-1.0)
    - Privacy band enforcement (GREEN/AMBER/RED)
    - Data validation (schema compliance)
    """

    @staticmethod
    def normalize(reading: SensorReading) -> SensorReading:
        """
        Validate and normalize sensor reading.

        Checks:
        - Timestamp within reasonable bounds (not future, not >1 hour old)
        - Confidence score 0.0-1.0
        - Privacy band matches sensor type
        - Latency within budget
        """

        # Timestamp validation
        now_ms = int(time.time() * 1000)
        if reading.timestamp_ms > now_ms:
            reading.timestamp_ms = now_ms  # Fix future timestamp

        if now_ms - reading.timestamp_ms > 3600000:  # >1 hour old
            logger.warning(f"Stale reading: {reading.sensor_id}, age={now_ms - reading.timestamp_ms}ms")

        # Confidence normalization
        reading.confidence = max(0.0, min(1.0, reading.confidence))

        # Privacy band enforcement
        expected_band = {
            "PIR": PrivacyBand.GREEN,
            "mmWave": PrivacyBand.GREEN,
            "BLE": PrivacyBand.AMBER,
            "WiFi": PrivacyBand.GREEN,
            "Camera": PrivacyBand.RED,
            "Light": PrivacyBand.GREEN
        }

        if reading.privacy_band != expected_band.get(reading.sensor_type):
            logger.error(f"Privacy band mismatch: {reading.sensor_id}, expected {expected_band.get(reading.sensor_type)}, got {reading.privacy_band}")

        # Latency budget check
        budget = SensorDriver.get_latency_budget_ms(reading.sensor_type)
        if reading.latency_ms > budget:
            logger.warning(f"Latency exceeded: {reading.sensor_id}, {reading.latency_ms}ms > {budget}ms budget")

        return reading
```

---

### Layer 3: Sensor Registry

**Registry for Driver Lifecycle Management:**

```python
class SensorRegistry:
    """
    Centralized sensor driver registry with lifecycle management.

    Responsibilities:
    - Driver discovery and registration
    - Start/stop all drivers
    - Health monitoring (1Hz polling)
    - Automatic restart on failure (max 3 retries)
    - Metrics export (driver status, error counts)
    """

    def __init__(self):
        self.drivers: Dict[str, SensorDriver] = {}
        self.health_monitor_task = None

    def register(self, driver: SensorDriver) -> None:
        """Register sensor driver"""
        self.drivers[driver.sensor_id] = driver
        logger.info(f"Registered driver: {driver.sensor_id} ({driver.sensor_type})")

    async def start_all(self) -> None:
        """Start all registered drivers"""
        for sensor_id, driver in self.drivers.items():
            success = await driver.start()
            if success:
                logger.info(f"Started driver: {sensor_id}")
            else:
                logger.error(f"Failed to start driver: {sensor_id}")

        # Start health monitoring
        self.health_monitor_task = asyncio.create_task(self.health_monitor_loop())

    async def stop_all(self) -> None:
        """Stop all drivers"""
        if self.health_monitor_task:
            self.health_monitor_task.cancel()

        for sensor_id, driver in self.drivers.items():
            await driver.stop()
            logger.info(f"Stopped driver: {sensor_id}")

    async def health_monitor_loop(self) -> None:
        """Monitor driver health (1Hz polling)"""
        while True:
            for sensor_id, driver in self.drivers.items():
                if not driver.health_check():
                    logger.error(f"Driver unhealthy: {sensor_id}, errors={driver.error_count}")

                    # Restart if error count <3
                    if driver.error_count < 3:
                        logger.info(f"Restarting driver: {sensor_id}")
                        await driver.stop()
                        await asyncio.sleep(1)
                        await driver.start()
                    else:
                        logger.error(f"Driver failed permanently: {sensor_id}, errors={driver.error_count}")

            await asyncio.sleep(1.0)  # 1Hz health check

    async def read_all(self) -> List[SensorReading]:
        """Read all sensors and return normalized readings"""
        readings = []

        for sensor_id, driver in self.drivers.items():
            reading = await driver.read()
            if reading:
                normalized = SensorNormalizer.normalize(reading)
                readings.append(normalized)

        return readings
```

---

## Consequences

### Positive

1. **Unified Interface:** All 6 sensor types implement same `SensorDriver` API (start/stop/read/health_check)
2. **Privacy Enforcement:** Privacy bands enforced at driver level (Camera = RED, BLE = AMBER)
3. **Graceful Degradation:** Driver failures don't crash system (registry handles restarts)
4. **Low Latency:** Each driver respects latency budget (<200ms total)

### Negative

1. **Hardware Complexity:** 6 different hardware interfaces (GPIO, UART, HCI, HTTP, USB, I2C)
2. **Driver Maintenance:** Each driver needs platform-specific implementation (Raspberry Pi vs x86)

---

## Implementation

**File:** `k1/l1_input/streams/operators/ambient_sensor_fusion.py`

**Modules:**
- `sensor_drivers/pir_motion.py`
- `sensor_drivers/mmwave_radar.py`
- `sensor_drivers/ble_proximity.py`
- `sensor_drivers/wifi_proximity.py`
- `sensor_drivers/camera_person.py`
- `sensor_drivers/ambient_light.py`
- `sensor_normalizer.py`
- `sensor_registry.py`

---

**Status:** Proposed 🔄 (awaiting approval for Post-MVP v1.1)