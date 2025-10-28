"""
Thermal Sensors - Multi-Platform Temperature & Power Monitoring

This module provides cross-platform thermal sensor APIs for monitoring device
temperature and power consumption. It supports CPU, GPU, and SoC package
measurements across Linux, Windows, and macOS platforms.

Use Cases:
    1. Real-time temperature monitoring for thermal management (1Hz polling)
    2. Power consumption tracking for performance budgeting
    3. Multi-core and multi-GPU system support
    4. Graceful degradation when sensors unavailable

Performance Targets:
    - Sensor read (cached): <1ms P95
    - Sensor read (fresh): <10ms P95 (NVIDIA SMI subprocess)
    - Poll interval: 100ms (10Hz) for responsive thermal management
    - Overhead: <0.1% CPU utilization

Platform Support:
    - **Linux**: /sys/class/thermal/ (thermal zones), Intel RAPL, NVIDIA SMI
    - **Windows**: WMI (Windows Management Instrumentation), Intel RAPL
    - **macOS**: IOKit (IOHIDEventType), NVIDIA SMI

Measurements:
    - **Temperature**: CPU package, GPU die, SoC thermal zones (°C)
    - **Power**: CPU package, GPU board power (W)

Integration:
    - ThermalPlacementController: Uses sensor data for placement decisions
    - Hysteresis FSM: Temperature triggers state transitions
    - Performance budgets: Power consumption tracking

ADR References:
    - ADR-0026: Thermal Hysteresis Matrix
    - ADR-0026a: Thermal Sensor Monitoring & State Detection
"""

import platform
from enum import Enum
from typing import Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class ThermalZone(Enum):
    """Thermal zones to monitor"""

    CPU = "CPU"
    GPU = "GPU"
    SOC = "SOC"  # System-on-Chip (mobile devices, Apple Silicon)
    BATTERY = "BATTERY"
    SKIN = "SKIN"  # Surface temperature (mobile devices)


class ThermalState(Enum):
    """Thermal states based on temperature (from ADR-0026)"""

    COOL = "COOL"  # <60°C - optimal performance
    WARM = "WARM"  # 60-75°C - normal operation
    HOT = "HOT"  # 75-85°C - throttling recommended
    CRITICAL = "CRITICAL"  # 85-95°C - aggressive throttling
    EMERGENCY = "EMERGENCY"  # >95°C - emergency shutdown


class ThermalSensors:
    """
    Multi-platform thermal sensor APIs with caching and graceful fallback.

    This class provides unified APIs for reading temperature and power measurements
    across different platforms (Linux, Windows, macOS). It uses platform-specific
    backends (sysfs, WMI, IOKit) and caches readings for efficiency.

    Features:
        - **100ms cache**: Reduces overhead (<1ms cached reads vs <10ms fresh reads)
        - **Multi-sensor aggregation**: Max temperature rule for thermal state
        - **Graceful fallback**: Continue with available sensors if some fail
        - **Platform detection**: Automatic platform-specific backend selection
        - **Power monitoring**: CPU package power (Intel RAPL), GPU power (NVIDIA SMI)

    Supported Platforms:
        - **Linux**: /sys/class/thermal/thermal_zone*/temp (CPU, GPU, SoC)
                    /sys/class/powercap/intel-rapl:0/energy_uj (CPU power)
                    nvidia-smi --query-gpu=temperature.gpu,power.draw (NVIDIA GPU)
        - **Windows**: WMI Win32_PerfRawData_Counters_ThermalZoneInformation
                      WMI Win32_PerfFormattedData_Counters_PowerMeter (Intel RAPL)
        - **macOS**: IOKit kIOHIDEventTypeTemperature (CPU proximity: TC0P, GPU: TG0P)

    Thermal State Classification (ADR-0026):
        - COOL (<60°C): Optimal performance, all tiers available
        - WARM (60-75°C): Normal operation, hysteresis band
        - HOT (75-85°C): Throttling recommended, GPU/CPU/Remote only
        - CRITICAL (85-95°C): Aggressive throttling, CPU/Remote only
        - EMERGENCY (>95°C): Emergency shutdown, Remote only

    Example Usage:
        ```python
        # Initialize sensors
        sensors = ThermalSensors(poll_interval_ms=100)

        # Get CPU temperature (cached if <100ms old)
        cpu_temp = sensors.get_cpu_temperature()
        if cpu_temp:
            print(f"CPU: {cpu_temp:.1f}°C")

        # Get GPU temperature (NVIDIA SMI)
        gpu_temp = sensors.get_gpu_temperature()
        if gpu_temp:
            print(f"GPU: {gpu_temp:.1f}°C")

        # Get CPU power consumption (Intel RAPL)
        cpu_power = sensors.get_cpu_power()
        if cpu_power:
            print(f"CPU Power: {cpu_power:.1f}W")

        # Get all metrics at once (efficient)
        metrics = sensors.get_all_metrics()
        print(f"CPU: {metrics['cpu_temp']:.1f}°C, {metrics['cpu_power']:.1f}W")
        print(f"GPU: {metrics['gpu_temp']:.1f}°C, {metrics['gpu_power']:.1f}W")

        # Get thermal state for placement decisions
        state = sensors.get_thermal_state()
        if state == ThermalState.HOT:
            print("Thermal state: HOT - Consider downgrading placement")
        ```

    WARD Test Examples:
        ```python
        # Test 1: Read CPU temperature (Linux sysfs)
        @ward.test("sensors reads CPU temperature from sysfs")
        def test_sensors_cpu_temp_linux():
            sensors = ThermalSensors()
            temp = sensors.get_cpu_temperature()

            if temp is not None:
                ward.assert_greater_than(temp, 0.0)  # Realistic temp
                ward.assert_less_than(temp, 150.0)   # Sanity check

        # Test 2: Cache efficiency (100ms cache)
        @ward.test("sensors caches readings for 100ms")
        def test_sensors_caching():
            sensors = ThermalSensors(poll_interval_ms=100)

            # First read (fresh)
            start = time.perf_counter()
            temp1 = sensors.get_cpu_temperature()
            duration1 = (time.perf_counter() - start) * 1000

            # Second read (cached, <100ms later)
            start = time.perf_counter()
            temp2 = sensors.get_cpu_temperature()
            duration2 = (time.perf_counter() - start) * 1000

            ward.assert_equal(temp1, temp2)  # Same value
            ward.assert_less_than(duration2, 1.0)  # <1ms cached read

        # Test 3: Thermal state classification
        @ward.test("sensors classifies thermal state correctly")
        def test_sensors_thermal_state():
            sensors = ThermalSensors()

            # Mock temperatures
            sensors._cached_metrics = {
                "cpu_temp": 82.0,  # HOT (75-85°C)
                "gpu_temp": 65.0,  # WARM (60-75°C)
            }

            state = sensors.get_thermal_state()
            ward.assert_equal(state, ThermalState.HOT)  # Max temp rule

        # Test 4: Graceful fallback (missing sensors)
        @ward.test("sensors continues with partial sensors")
        def test_sensors_graceful_fallback():
            sensors = ThermalSensors()

            metrics = sensors.get_all_metrics()
            # Should return metrics for available sensors only
            # None for unavailable sensors (e.g., no GPU)
            ward.assert_is_not_none(metrics)
        ```

    TODO List:
        - TODO(@platform-team): Implement Linux sysfs thermal zone discovery
        - TODO(@platform-team): Add Windows WMI temperature reading
        - TODO(@platform-team): Add macOS IOKit temperature reading
        - TODO(@platform-team): Implement NVIDIA SMI GPU temperature
        - TODO(@platform-team): Implement Intel RAPL power monitoring
        - TODO(@platform-team): Add AMD SMI GPU power monitoring
        - TODO(@platform-team): Implement 100ms caching mechanism
        - TODO(@platform-team): Add Prometheus metrics (sensor_temp_celsius, sensor_power_watts)
        - TODO(@platform-team): Add thermal state classification logic
        - TODO(@platform-team): Implement graceful fallback for missing sensors

    ADR References:
        - ADR-0026: Thermal Hysteresis Matrix
        - ADR-0026a: Thermal Sensor Monitoring & State Detection
    """

    # Constants
    DEFAULT_POLL_INTERVAL_MS = 100  # 100ms cache (10Hz polling)
    CACHE_TIMEOUT_MS = 100  # Cache timeout
    SENSOR_TIMEOUT_MS = 10  # Sensor read timeout (NVIDIA SMI)

    # Thermal state thresholds (°C, from ADR-0026)
    COOL_THRESHOLD = 60.0
    WARM_THRESHOLD = 75.0
    HOT_THRESHOLD = 85.0
    CRITICAL_THRESHOLD = 95.0

    def __init__(self, poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS):
        """
        Initialize thermal sensors.

        Args:
            poll_interval_ms: Cache poll interval in milliseconds (default: 100ms)

        Implementation:
            1. Detect platform (Linux/Windows/macOS)
            2. Initialize platform-specific backends
            3. Discover available sensors (CPU, GPU, SoC)
            4. Setup cache (100ms timeout)
            5. Initialize Prometheus metrics

        Performance:
            - Initialization: <50ms (sensor discovery)
            - Platform detection: <1ms

        ADR: ADR-0026 (Thermal Sensing)
        """
        # TODO(@platform-team): Initialize thermal sensors
        # 1. Detect OS: platform.system() → "Linux", "Windows", "Darwin"
        # 2. Initialize backend:
        #    - Linux: LinuxThermalBackend()
        #    - Windows: WindowsWMIBackend()
        #    - macOS: MacOSIOKitBackend()
        # 3. Discover sensors: self.backend.discover_sensors()
        # 4. Initialize cache: self._cached_metrics = {}
        # 5. Initialize Prometheus metrics:
        #    - sensor_temp_celsius (Gauge, labels: zone)
        #    - sensor_power_watts (Gauge, labels: zone)
        #    - sensor_read_duration_ms (Histogram)

        self.poll_interval_ms = poll_interval_ms
        self.platform = platform.system()  # "Linux", "Windows", "Darwin"
        self._cached_metrics: Dict[str, Optional[float]] = {}
        self._cache_timestamp_ms = 0

        logger.info(
            "[ThermalSensors] Initialized thermal sensors",
            platform=self.platform,
            poll_interval_ms=poll_interval_ms,
        )

    def get_cpu_temperature(self) -> Optional[float]:
        """
        Get CPU package temperature (°C).

        Returns:
            Temperature in Celsius or None if unavailable

        Performance:
            - Cached read: <1ms P95
            - Fresh read: <5ms P95 (sysfs/WMI)

        Platforms:
            - **Linux**: /sys/class/thermal/thermal_zone0/temp (millidegrees C)
            - **Windows**: WMI Win32_PerfRawData_Counters_ThermalZoneInformation
            - **macOS**: IOKit kIOHIDEventTypeTemperature (TC0P proximity sensor)

        Caching:
            - Returns cached value if <100ms old
            - Queries fresh value otherwise

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement CPU temperature read
        # 1. Check cache: if (now_ms - self._cache_timestamp_ms) < self.poll_interval_ms:
        #                    return self._cached_metrics.get("cpu_temp")
        # 2. Query platform-specific API:
        #    - Linux: cat /sys/class/thermal/thermal_zone0/temp (millidegrees)
        #    - Windows: WMI query MSAcpi_ThermalZoneTemperature
        #    - macOS: IOKit TC0P proximity sensor
        # 3. Convert to Celsius:
        #    - Linux: temp_c = millidegrees / 1000.0
        #    - Windows: temp_c = (kelvin_tenths / 10.0) - 273.15
        # 4. Update cache: self._cached_metrics["cpu_temp"] = temp_c
        # 5. Emit metric: sensor_temp_celsius.labels(zone="cpu").set(temp_c)
        # 6. Return temperature or None

        logger.debug("[ThermalSensors] Get CPU temperature")
        return None  # TODO: Replace with actual implementation

    def get_gpu_temperature(self) -> Optional[float]:
        """
        Get GPU temperature (°C).

        Returns:
            Temperature in Celsius or None if no GPU

        Performance:
            - NVIDIA SMI: <10ms (subprocess call)
            - Cached: <1ms

        Platforms:
            - **NVIDIA**: nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits
            - **AMD**: amd-smi metric -t (JSON output)
            - **Intel Arc**: intel_gpu_frequency (if available)
            - **Apple Metal**: IOKit TG0P proximity sensor

        Caching:
            - Returns cached value if <100ms old
            - Queries fresh value otherwise

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement GPU temperature read
        # 1. Check cache (same as CPU)
        # 2. Probe GPU vendor:
        #    - NVIDIA: subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"])
        #    - AMD: subprocess.run(["amd-smi", "metric", "-t"])
        #    - Intel: Check intel_gpu_frequency interface
        #    - Apple: IOKit TG0P sensor
        # 3. Parse output (csv for NVIDIA, JSON for AMD)
        # 4. Update cache: self._cached_metrics["gpu_temp"] = temp_c
        # 5. Emit metric: sensor_temp_celsius.labels(zone="gpu").set(temp_c)
        # 6. Return temperature or None

        logger.debug("[ThermalSensors] Get GPU temperature")
        return None  # TODO: Replace with actual implementation

    def get_cpu_power(self) -> Optional[float]:
        """
        Get CPU package power consumption (W).

        Returns:
            Power in Watts or None if unavailable

        Performance:
            - Intel RAPL: <1ms (kernel interface)
            - Cached: <1ms

        Platforms:
            - **Intel**: /sys/class/powercap/intel-rapl:0/energy_uj (Linux)
                        WMI Win32_PerfFormattedData_Counters_PowerMeter (Windows)
            - **AMD**: amd-smi metric -P (power metrics)
            - **Apple Silicon**: NVRAM power metrics (IOKit)

        Caching:
            - Returns cached value if <100ms old
            - Queries fresh value otherwise

        Notes:
            - Intel RAPL reports energy in microjoules (µJ)
            - Power = ΔEnergy / ΔTime (sample twice, 100ms apart)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement CPU power read
        # 1. Check cache
        # 2. Query platform-specific API:
        #    - Intel RAPL (Linux): Read /sys/class/powercap/intel-rapl:0/energy_uj twice (100ms apart)
        #      power_w = (energy2 - energy1) / (time2 - time1) / 1_000_000
        #    - Windows: WMI Win32_PerfFormattedData_Counters_PowerMeter
        #    - AMD: amd-smi metric -P (JSON output)
        # 3. Update cache: self._cached_metrics["cpu_power"] = power_w
        # 4. Emit metric: sensor_power_watts.labels(zone="cpu").set(power_w)
        # 5. Return power or None

        logger.debug("[ThermalSensors] Get CPU power")
        return None  # TODO: Replace with actual implementation

    def get_gpu_power(self) -> Optional[float]:
        """
        Get GPU power consumption (W).

        Returns:
            Power in Watts or None if unavailable

        Performance:
            - NVIDIA SMI: <10ms (subprocess)
            - Cached: <1ms

        Platforms:
            - **NVIDIA**: nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits
            - **AMD**: amd-smi metric -P (power metrics)
            - **Intel Arc**: intel_gpu_frequency power interface

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement GPU power read
        # 1. Check cache
        # 2. Probe GPU vendor:
        #    - NVIDIA: subprocess.run(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"])
        #    - AMD: subprocess.run(["amd-smi", "metric", "-P"])
        # 3. Parse output (csv for NVIDIA, JSON for AMD)
        # 4. Update cache: self._cached_metrics["gpu_power"] = power_w
        # 5. Emit metric: sensor_power_watts.labels(zone="gpu").set(power_w)
        # 6. Return power or None

        logger.debug("[ThermalSensors] Get GPU power")
        return None  # TODO: Replace with actual implementation

    def get_all_metrics(self) -> Dict[str, Optional[float]]:
        """
        Get all thermal metrics at once.

        Returns:
            Dict with keys:
                - cpu_temp: CPU temperature (°C) or None
                - gpu_temp: GPU temperature (°C) or None
                - cpu_power: CPU power consumption (W) or None
                - gpu_power: GPU power consumption (W) or None

        Performance:
            - All cached: <1ms P95
            - All fresh: <20ms P95 (parallel queries)

        Efficiency:
            - Single cache check for all metrics
            - Batch Prometheus metric updates
            - Reduces overhead vs individual calls

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement batch read
        # 1. Check cache timestamp
        # 2. If cache valid (<100ms): return cached metrics
        # 3. If cache stale: query all sensors:
        #    a. cpu_temp = self._read_cpu_temp_fresh()
        #    b. gpu_temp = self._read_gpu_temp_fresh()
        #    c. cpu_power = self._read_cpu_power_fresh()
        #    d. gpu_power = self._read_gpu_power_fresh()
        # 4. Update cache: self._cached_metrics = {...}
        # 5. Update cache timestamp: self._cache_timestamp_ms = now_ms
        # 6. Emit batch metrics
        # 7. Return dict

        return {
            "cpu_temp": None,
            "gpu_temp": None,
            "cpu_power": None,
            "gpu_power": None,
        }  # TODO: Replace with actual implementation

    def get_thermal_state(self) -> ThermalState:
        """
        Get current thermal state based on max temperature.

        Returns:
            ThermalState enum (COOL, WARM, HOT, CRITICAL, EMERGENCY)

        Classification (ADR-0026):
            - COOL: <60°C - Optimal performance
            - WARM: 60-75°C - Normal operation
            - HOT: 75-85°C - Throttling recommended
            - CRITICAL: 85-95°C - Aggressive throttling
            - EMERGENCY: >95°C - Emergency shutdown

        Aggregation Policy:
            - Max temperature rule: state = max(cpu_temp, gpu_temp)
            - Conservative approach prevents any component from overheating

        Performance:
            - State classification: <0.2ms

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement thermal state classification
        # 1. Get all metrics: metrics = self.get_all_metrics()
        # 2. Find max temperature:
        #    temps = [t for t in [metrics["cpu_temp"], metrics["gpu_temp"]] if t is not None]
        #    max_temp = max(temps) if temps else 0.0
        # 3. Classify state:
        #    if max_temp >= self.CRITICAL_THRESHOLD: return ThermalState.EMERGENCY
        #    if max_temp >= self.HOT_THRESHOLD: return ThermalState.CRITICAL
        #    if max_temp >= self.WARM_THRESHOLD: return ThermalState.HOT
        #    if max_temp >= self.COOL_THRESHOLD: return ThermalState.WARM
        #    return ThermalState.COOL
        # 4. Return state

        logger.debug("[ThermalSensors] Get thermal state")
        return ThermalState.COOL  # TODO: Replace with actual implementation

    def _is_cache_valid(self) -> bool:
        """
        Check if cache is valid (<100ms old).

        Returns:
            True if cache valid, False otherwise

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement cache validation
        # now_ms = int(time.time() * 1000)
        # return (now_ms - self._cache_timestamp_ms) < self.poll_interval_ms
        return False

    def _read_linux_thermal_zone(self, zone_path: str) -> Optional[float]:
        """
        Read temperature from Linux thermal zone.

        Args:
            zone_path: Path to thermal zone (e.g., /sys/class/thermal/thermal_zone0/temp)

        Returns:
            Temperature in Celsius or None

        Format:
            - Linux reports temperature in millidegrees Celsius
            - Example: 72000 = 72.0°C

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement Linux thermal zone read
        # 1. Check if path exists: Path(zone_path).exists()
        # 2. Read file: with open(zone_path, "r") as f: millidegrees = int(f.read().strip())
        # 3. Convert: celsius = millidegrees / 1000.0
        # 4. Return temperature or None
        return None

    def _run_nvidia_smi(self, query: str) -> Optional[str]:
        """
        Run NVIDIA SMI command and return output.

        Args:
            query: Query string (e.g., "temperature.gpu", "power.draw")

        Returns:
            Command output (stripped) or None if failed

        Performance:
            - Subprocess call: <10ms

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement NVIDIA SMI wrapper
        # 1. Run subprocess: result = subprocess.run(
        #      ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
        #      capture_output=True, text=True, timeout=self.SENSOR_TIMEOUT_MS / 1000
        #    )
        # 2. Check return code: if result.returncode != 0: return None
        # 3. Return output: return result.stdout.strip()
        return None


# Expected lint errors (documented):
# - Unused imports: platform, subprocess (used in sensor implementations)
# - Unused imports: time (used for cache timeout checks)
# - structlog not resolved (dependency not installed yet)
# - Path not imported (from pathlib import Path needed for Linux sysfs)
# These will be resolved when dependencies are installed and implementation is complete.
# These will be resolved when dependencies are installed and implementation is complete.
