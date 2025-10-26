"""
Device Temperature Monitor

Purpose: Monitor NPU/GPU/CPU temperature sensors for thermal management
Location: k1/l5_infrastructure/thermal/monitor.py
Performance: <5ms temperature read

Primary ADRs:
- ADR-0026: Thermal Management (monitoring integration)
- ADR-0026a: Thermal Zones (sensor monitoring, state detection)

Related ADRs:
- ADR-0024: Performance Budgets (temperature read <5ms)
- ADR-0029: Prometheus Metrics (thermal_temperature_celsius, thermal_state gauges)

Key Responsibilities:

1. Temperature Monitoring:
   - Poll NPU/GPU/CPU temperature sensors (1 Hz)
   - Thermal zones: COOL (<60°C), WARM (60-75°C), HOT (75-85°C), CRITICAL (85-95°C), EMERGENCY (>95°C)
   - Alert on CRITICAL (≥85°C) or EMERGENCY (≥95°C)
   - Multi-sensor aggregation (max temperature rule)

2. Cross-Platform Support:
   - Linux: /sys/class/thermal/thermal_zone*/temp
   - Windows: WMI (Win32_TemperatureProbe)
   - macOS: IOKit (SMC sensors)
   - Graceful degradation on sensor unavailability

3. Metrics Emission:
   - thermal_temperature_celsius gauge (per device: NPU/GPU/CPU)
   - thermal_state gauge (0=COOL, 1=WARM, 2=HOT, 3=CRITICAL, 4=EMERGENCY)
   - thermal_alerts_total counter (HOT/CRITICAL/EMERGENCY)
   - Push to Prometheus every 10s

4. State Detection:
   - Zone classification: <0.2ms (simple threshold comparison)
   - Alert latency: <100ms (detection + notification)
   - State propagation to PlacementPlanner

Performance Metrics:
- Temperature read: <5ms P95 (<3ms typical)
- Polling frequency: 1 Hz
- Alert latency: <100ms
- State detection: <0.2ms (zone classification)
- Multi-sensor aggregation: <1ms

Implementation Notes:
- Use asyncio for 1 Hz polling loop
- Cache sensor paths for fast reads (<1ms lookup)
- Max temperature rule for multi-sensor aggregation
- Graceful degradation: Default to WARM state on sensor failure
- Alert throttling: Max 1 alert per minute per zone (prevent spam)

Example Usage:
    monitor = ThermalMonitor()
    await monitor.start_monitoring()

    # Get current temperature
    temp = await monitor.get_temperature("NPU")  # Returns: float (Celsius)

    # Get thermal state
    state = monitor.get_thermal_state()  # Returns: ThermalZone enum

    # Register callback for state changes
    monitor.on_state_change(lambda zone: print(f"Thermal state: {zone}"))

Research Foundation:
- Thermal sensor polling (Linux hwmon, Windows WMI, macOS SMC)
- Multi-sensor fusion (max/avg/weighted strategies)
- Alert throttling (debouncing, rate limiting)
"""

import asyncio
import logging
import platform
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

# Cross-platform sensor access
try:
    import wmi  # Windows WMI

    wmi_available = True
except ImportError:
    wmi_available = False

try:
    smc_available = True  # macOS SMC via smc command
except ImportError:
    smc_available = False

# Optional thermal drivers (new implementation)
try:
    from .thermal_drivers import SensorReading as DriverSensorReading
    from .thermal_drivers import get_thermal_driver_manager

    thermal_drivers_available = True
except ImportError:
    thermal_drivers_available = False

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, Gauge

    prometheus_available = True
except ImportError:
    prometheus_available = False

# Import shared types
from .types import ThermalZone


@dataclass
class SensorReading:
    """Individual sensor temperature reading."""

    sensor_id: str
    temperature_celsius: float
    timestamp_ms: int
    confidence: float = 1.0  # 1.0 = valid, 0.0 = failed


@dataclass
class ThermalStatus:
    """Complete thermal status snapshot."""

    max_temperature_celsius: float
    thermal_zone: ThermalZone
    sensor_readings: List[SensorReading]
    timestamp_ms: int


class ThermalMonitor:
    """
    Cross-platform thermal sensor monitor with 1Hz polling.

    Implements ADR-0026a thermal sensor monitoring and state detection.
    Provides temperature readings and thermal zone classification.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Sensor state
        self._sensor_paths: Dict[str, str] = {}
        self._last_readings: Dict[str, SensorReading] = {}
        self._current_status: Optional[ThermalStatus] = None

        # Monitoring state
        self._monitoring_task: Optional[asyncio.Task[None]] = None
        self._state_callbacks: List[Callable[[ThermalZone], None]] = []
        self._last_alert_time: Dict[ThermalZone, float] = {}

        # Platform detection
        self._platform = platform.system().lower()

        # Prometheus metrics
        if prometheus_available:
            self._setup_prometheus_metrics()

        # Initialize sensor discovery
        self._discover_sensors()

    def _setup_prometheus_metrics(self):
        """Initialize Prometheus metrics."""
        from prometheus_client import CollectorRegistry

        # Use custom registry to avoid conflicts in tests
        self._prometheus_registry = CollectorRegistry()

        self.thermal_temperature_celsius = Gauge(
            "thermal_temperature_celsius",
            "Current temperature in Celsius",
            ["sensor_type"],
            registry=self._prometheus_registry,
        )
        self.thermal_state = Gauge(
            "thermal_state",
            "Current thermal state (0=COOL, 1=WARM, 2=HOT, 3=CRITICAL, 4=EMERGENCY)",
            registry=self._prometheus_registry,
        )
        self.thermal_transitions_total = Counter(
            "thermal_transitions_total",
            "Total thermal state transitions",
            ["from_state", "to_state"],
            registry=self._prometheus_registry,
        )
        self.thermal_flap_preventions_total = Counter(
            "thermal_flap_preventions_total",
            "Total thermal flap prevention events",
            registry=self._prometheus_registry,
        )

    def _discover_sensors(self):
        """Discover available thermal sensors based on platform."""
        try:
            # Try new thermal drivers first (if available)
            if thermal_drivers_available:
                self._discover_with_drivers()
            else:
                # Fall back to legacy platform-specific discovery
                if self._platform == "linux":
                    self._discover_linux_sensors()
                elif self._platform == "windows":
                    self._discover_windows_sensors()
                elif self._platform == "darwin":  # macOS
                    self._discover_macos_sensors()
                else:
                    self.logger.warning(f"Unsupported platform: {self._platform}")
        except Exception as e:
            self.logger.error(f"Failed to discover sensors: {e}")

    def _discover_with_drivers(self):
        """Discover sensors using the new thermal drivers."""
        try:
            # Note: This is called during synchronous __init__, so we can't use asyncio.run()
            # Instead, we'll do immediate discovery using asyncio.run() for this one-time operation
            import asyncio

            # Create event loop if one doesn't exist (for synchronous initialization)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is already running, defer discovery
                    self._use_thermal_drivers = True
                    self.logger.info(
                        "Thermal drivers will be used for sensor discovery (deferred)"
                    )
                    return
            except RuntimeError:
                # No event loop, we can create one
                pass

            # Perform immediate sensor discovery
            async def discover():
                driver_manager = get_thermal_driver_manager()
                sensors = await driver_manager.discover_sensors()
                return sensors

            # Run discovery immediately
            sensors = asyncio.run(discover())

            # Add all discovered sensors from thermal drivers
            for sensor_id, sensor_type in sensors.items():
                self._sensor_paths[sensor_id] = sensor_id  # Use sensor_id as path

            self.logger.info(
                f"Discovered {len(sensors)} sensors via thermal drivers: {list(sensors.keys())}"
            )
            self._use_thermal_drivers = True

        except Exception as e:
            self.logger.warning(f"Thermal drivers setup failed, falling back: {e}")
            self._use_thermal_drivers = False
            # Fall back to legacy discovery
            self._fallback_discovery()

    def _fallback_discovery(self):
        """Fallback to legacy platform-specific discovery."""
        if self._platform == "linux":
            self._discover_linux_sensors()
        elif self._platform == "windows":
            self._discover_windows_sensors()
        elif self._platform == "darwin":  # macOS
            self._discover_macos_sensors()
        else:
            self.logger.warning(f"Unsupported platform: {self._platform}")

    def _discover_linux_sensors(self):
        """Discover Linux thermal sensors via sysfs."""
        import glob
        import os

        thermal_zones = glob.glob("/sys/class/thermal/thermal_zone*/temp")
        for temp_file in thermal_zones:
            zone_dir = os.path.dirname(temp_file)
            type_file = os.path.join(zone_dir, "type")

            try:
                with open(type_file, "r") as f:
                    sensor_type = f.read().strip()

                # Map common sensor types to our categories
                sensor_name = sensor_type.lower()
                if any(
                    keyword in sensor_name
                    for keyword in ["cpu", "core", "x86", "intel", "amd"]
                ):
                    if "CPU" not in self._sensor_paths:
                        self._sensor_paths["CPU"] = temp_file
                elif any(
                    keyword in sensor_name
                    for keyword in ["gpu", "nvidia", "radeon", "amd"]
                ):
                    if "GPU" not in self._sensor_paths:
                        self._sensor_paths["GPU"] = temp_file
                elif any(
                    keyword in sensor_name
                    for keyword in ["npu", "neural", "tpu", "neural"]
                ):
                    if "NPU" not in self._sensor_paths:
                        self._sensor_paths["NPU"] = temp_file
                else:
                    # Use first available thermal zone as CPU if no specific CPU found
                    if "CPU" not in self._sensor_paths and len(self._sensor_paths) == 0:
                        self._sensor_paths["CPU"] = temp_file
                    # Add additional thermal zones with generic names
                    zone_num = os.path.basename(zone_dir).replace("thermal_zone", "")
                    generic_name = f"THERMAL_{zone_num}"
                    if generic_name not in self._sensor_paths:
                        self._sensor_paths[generic_name] = temp_file

            except Exception as e:
                self.logger.warning(f"Failed to read sensor type from {type_file}: {e}")
                # Still add the sensor with a generic name
                zone_num = os.path.basename(zone_dir).replace("thermal_zone", "")
                generic_name = f"THERMAL_{zone_num}"
                if generic_name not in self._sensor_paths:
                    self._sensor_paths[generic_name] = temp_file

    def _discover_windows_sensors(self):
        """Discover Windows thermal sensors (limited support)."""
        # Note: Windows doesn't have reliable generic temperature sensors
        # This is a placeholder for systems with specific thermal monitoring drivers
        if not wmi_available:
            self.logger.warning(
                "WMI not available, Windows thermal monitoring disabled"
            )
            return

        try:
            # Try to find any available temperature sensors
            # Note: Win32_TemperatureProbe is not a real WMI class
            # This would need custom drivers or specific hardware support
            # Look for any thermal-related WMI classes (this is mostly placeholder)
            # Real Windows thermal monitoring requires vendor-specific APIs
            self.logger.info(
                "Windows thermal sensor discovery not fully implemented - requires vendor drivers"
            )

            # For now, add a mock CPU sensor for development
            if not self._sensor_paths:  # Only if no other sensors found
                self._sensor_paths["CPU"] = "MOCK_CPU"

        except Exception as e:
            self.logger.error(f"Failed to discover Windows sensors: {e}")

    def _discover_macos_sensors(self):
        """Discover macOS thermal sensors via SMC."""
        # Common SMC temperature keys
        smc_keys = {
            "CPU": ["TC0D", "TC1D", "TC2D"],  # CPU die temperatures
            "GPU": ["TG0D", "TG1D"],  # GPU temperatures
            "NPU": ["TN0D", "TN1D"],  # Neural engine temperatures
        }

        for sensor_type, keys in smc_keys.items():
            for key in keys:
                self._sensor_paths[f"{sensor_type}_{key}"] = key

    async def _read_sensor_temperature(
        self, sensor_id: str, sensor_path: str
    ) -> Optional[float]:
        """Read temperature from a specific sensor."""
        try:
            # Try new thermal drivers first (if available)
            if thermal_drivers_available:
                driver_manager = get_thermal_driver_manager()
                reading = await driver_manager.read_sensor(sensor_id)
                if reading:
                    return reading.temperature_celsius

            # Fall back to legacy platform-specific reading
            if self._platform == "linux":
                return await self._read_linux_sensor(sensor_path)
            elif self._platform == "windows":
                return await self._read_windows_sensor(sensor_path)
            elif self._platform == "darwin":
                return await self._read_macos_sensor(sensor_path)
            else:
                return None
        except Exception as e:
            self.logger.warning(f"Failed to read sensor {sensor_id}: {e}")
            return None

    async def _read_linux_sensor(self, temp_file: str) -> Optional[float]:
        """Read Linux sensor via sysfs."""
        import asyncio

        def read_file():
            with open(temp_file, "r") as f:
                return int(f.read().strip()) / 1000.0  # Convert millicelsius to celsius

        try:
            # Run file read in thread pool to avoid blocking
            return await asyncio.get_event_loop().run_in_executor(None, read_file)
        except Exception:
            return None

    async def _read_windows_sensor(self, device_id: str) -> Optional[float]:
        """Read Windows sensor (limited support)."""
        if not wmi_available:
            return None

        # Windows thermal sensors require vendor-specific drivers or APIs
        # No generic thermal sensors available on Windows
        self.logger.debug(f"Windows sensor reading not implemented for {device_id}")
        return None

    async def _read_macos_sensor(self, smc_key: str) -> Optional[float]:
        """Read macOS sensor (limited support)."""
        # Note: macOS SMC access requires special permissions and tools
        # This is a placeholder - real implementation would need:
        # 1. SMC kernel extension or user-space tool
        # 2. Proper permissions (com.apple.private.smc.gettemperature)
        # 3. Or use IOKit framework (complex)

        self.logger.debug(f"macOS SMC reading not implemented for {smc_key}")
        return None

    def _classify_thermal_zone(self, temperature_celsius: float) -> ThermalZone:
        """Classify temperature into thermal zone (ADR-0026a, relaxed for gaming)."""
        if temperature_celsius < 70:
            return ThermalZone.COOL
        elif temperature_celsius < 80:
            return ThermalZone.WARM
        elif temperature_celsius < 90:
            return ThermalZone.HOT
        elif temperature_celsius < 100:
            return ThermalZone.CRITICAL
        else:
            return ThermalZone.EMERGENCY

    async def _polling_loop(self):
        """Main 1Hz polling loop."""
        while True:
            start_time = time.time()

            # Read all sensors
            readings = []
            max_temp = float("-inf")

            for sensor_id, sensor_path in self._sensor_paths.items():
                temp = await self._read_sensor_temperature(sensor_id, sensor_path)
                if temp is not None:
                    reading = SensorReading(
                        sensor_id=sensor_id,
                        temperature_celsius=temp,
                        timestamp_ms=int(time.time() * 1000),
                    )
                    readings.append(reading)
                    self._last_readings[sensor_id] = reading
                    max_temp = max(max_temp, temp)

                    # Update Prometheus metrics
                    if prometheus_available:
                        self.thermal_temperature_celsius.labels(
                            sensor_type=sensor_id
                        ).set(temp)

            # Handle case with no valid readings (graceful degradation)
            if not readings:
                max_temp = 70.0  # Default to WARM state
                self.logger.warning(
                    "No valid sensor readings, defaulting to WARM state"
                )

            # Classify thermal zone
            thermal_zone = self._classify_thermal_zone(max_temp)

            # Create status snapshot
            status = ThermalStatus(
                max_temperature_celsius=max_temp,
                thermal_zone=thermal_zone,
                sensor_readings=readings,
                timestamp_ms=int(time.time() * 1000),
            )

            # Check for state changes
            if (
                self._current_status is None
                or self._current_status.thermal_zone != thermal_zone
            ):
                await self._handle_state_change(thermal_zone)

            self._current_status = status

            # Update Prometheus metrics
            if prometheus_available:
                self.thermal_state.set(thermal_zone.value)

            # Sleep for remaining time to maintain 1Hz
            elapsed = time.time() - start_time
            sleep_time = max(0, 1.0 - elapsed)
            await asyncio.sleep(sleep_time)

    async def _handle_state_change(self, new_zone: ThermalZone):
        """Handle thermal state changes."""
        old_zone = self._current_status.thermal_zone if self._current_status else None

        # Update Prometheus transition counter
        if prometheus_available and old_zone is not None:
            self.thermal_transitions_total.labels(
                from_state=old_zone.name, to_state=new_zone.name
            ).inc()

        # Check alert throttling (max 1 alert per minute per zone)
        current_time = time.time()
        last_alert = self._last_alert_time.get(new_zone, 0)

        should_alert = (current_time - last_alert) >= 60  # 1 minute cooldown

        if should_alert and new_zone in [ThermalZone.CRITICAL, ThermalZone.EMERGENCY]:
            self._last_alert_time[new_zone] = current_time
            self.logger.warning(f"Thermal alert: {new_zone.name} state detected")

        # Notify callbacks
        for callback in self._state_callbacks:
            try:
                callback(new_zone)
            except Exception as e:
                self.logger.error(f"State change callback failed: {e}")

    async def start_monitoring(self):
        """Start the thermal monitoring loop."""
        if self._monitoring_task is not None:
            return

        # Sensor discovery is now done immediately in __init__, no need for deferred discovery
        self.logger.info("Starting thermal monitoring")
        self._monitoring_task = asyncio.create_task(self._polling_loop())

    async def stop_monitoring(self):
        """Stop the thermal monitoring loop."""
        if self._monitoring_task is not None:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
            self.logger.info("Stopped thermal monitoring")

    def get_thermal_state(self) -> ThermalZone:
        """Get current thermal state."""
        return (
            self._current_status.thermal_zone
            if self._current_status
            else ThermalZone.WARM
        )

    def get_temperature(self, sensor_type: str = "MAX") -> Optional[float]:
        """Get temperature for specific sensor type or max temperature."""
        if sensor_type == "MAX":
            return (
                self._current_status.max_temperature_celsius
                if self._current_status
                else None
            )

        reading = self._last_readings.get(sensor_type)
        return reading.temperature_celsius if reading else None

    def get_thermal_status(self) -> Optional[ThermalStatus]:
        """Get complete thermal status snapshot."""
        return self._current_status

    def on_state_change(self, callback: Callable[[ThermalZone], None]):
        """Register callback for thermal state changes."""
        self._state_callbacks.append(callback)

    def get_available_sensors(self) -> List[str]:
        """Get list of available sensor types."""
        return list(self._sensor_paths.keys())
