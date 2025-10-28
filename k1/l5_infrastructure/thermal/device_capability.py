"""
Device Capability - Form Factor Detection & Thermal Baseline Establishment

This module detects device form factors (laptop, phone, desktop, server) and
establishes appropriate thermal baselines for safe operation. It probes for
available accelerators (NPU, GPU, CPU) and enumerates GPU types.

Use Cases:
    1. Form factor detection for adaptive thermal thresholds
    2. Accelerator enumeration for model placement decisions
    3. Thermal baseline establishment (laptop: 75°C, phone: 65°C, desktop: 82°C)
    4. GPU vendor detection (NVIDIA, AMD, Intel Arc, Apple Metal)

Performance Targets:
    - Device detection: <50ms (one-time initialization)
    - Capability query: <1ms (cached)
    - Accelerator probing: <100ms (subprocess calls)

Form Factor Thermal Baselines (ADR-0026):
    - **Laptop**: 75°C baseline (limited passive cooling)
    - **Phone**: 65°C baseline (very limited thermal capacity, small form factor)
    - **Desktop**: 82°C baseline (active cooling, tower chassis)
    - **Server**: 85°C baseline (advanced thermal management, data center)
    - **Unknown**: 80°C baseline (conservative fallback)

Integration:
    - ThermalPlacementController: Uses baseline for hysteresis thresholds
    - ModelPlacementAlgorithm: Uses accelerator capabilities for tier selection
    - Performance budgets: Adjusts targets based on form factor

ADR References:
    - ADR-0026: Thermal Hysteresis Matrix
    - ADR-0026a: Thermal Sensor Monitoring & State Detection
"""

import platform
from enum import Enum
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class FormFactor(Enum):
    """Device form factors"""

    LAPTOP = "laptop"
    PHONE = "phone"
    DESKTOP = "desktop"
    SERVER = "server"
    TABLET = "tablet"
    UNKNOWN = "unknown"


class AcceleratorType(Enum):
    """Accelerator types for ML inference"""

    NPU = "NPU"  # Neural Processing Unit
    GPU = "GPU"  # Graphics Processing Unit
    CPU = "CPU"  # Central Processing Unit


class GPUVendor(Enum):
    """GPU vendors"""

    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    QUALCOMM = "qualcomm"
    UNKNOWN = "unknown"


class DeviceCapability:
    """
    Detect device capabilities and thermal baselines.

    This class provides unified APIs for detecting device form factors, available
    accelerators (NPU, GPU, CPU), and establishing appropriate thermal baselines
    for safe operation. It uses platform-specific detection methods and caches
    results for efficiency.

    Features:
        - **Form factor detection**: Laptop, phone, desktop, server, tablet
        - **Thermal baseline**: Adaptive thresholds based on device type
        - **Accelerator enumeration**: NPU, GPU, CPU availability
        - **GPU vendor detection**: NVIDIA, AMD, Intel Arc, Apple Metal, Qualcomm
        - **Hardware specs**: CPU cores, RAM capacity, storage type

    Form Factor Detection:
        - **Linux**: dmidecode chassis type, device tree, model identifier
        - **Windows**: WMI Win32_SystemEnclosure ChassisTypes
        - **macOS**: system_profiler hardware model (MacBook, Mac mini, iMac)
        - **Android**: ro.build.product, devicetree soc/npu detection

    Thermal Baseline Policy (ADR-0026):
        - **Laptop** (75°C): Limited passive cooling, thermal pad contact
        - **Phone** (65°C): Very limited thermal capacity, small form factor, battery proximity
        - **Desktop** (82°C): Active cooling (fans), tower chassis, good airflow
        - **Server** (85°C): Advanced thermal management, data center environment
        - **Unknown** (80°C): Conservative fallback for undetected devices

    Accelerator Detection:
        - **NPU**: /proc/device-tree/soc/npu* (Linux), NNAPI capability (Android), Neural Engine (Apple M1+)
        - **GPU**: nvidia-smi, rocm-smi, intel_gpu_frequency, Metal capabilities
        - **CPU**: lscpu, sysctl, wmic cpu

    Example Usage:
        ```python
        # Initialize device capability detector
        device = DeviceCapability()

        # Get form factor
        form_factor = device.get_form_factor()
        print(f"Device: {form_factor.value}")  # "laptop", "phone", etc.

        # Get thermal baseline for this device
        baseline = device.get_thermal_baseline()
        print(f"Thermal baseline: {baseline}°C")  # 75°C for laptops

        # Check accelerator availability
        has_npu = device.has_npu()
        has_gpu = device.has_gpu()
        print(f"NPU: {has_npu}, GPU: {has_gpu}")

        # Get GPU vendor (if available)
        gpu_vendor = device.get_gpu_vendor()
        if gpu_vendor:
            print(f"GPU: {gpu_vendor.value}")  # "nvidia", "amd", etc.

        # Get all capabilities at once
        capabilities = device.get_capabilities()
        print(f"Form factor: {capabilities['form_factor']}")
        print(f"Thermal baseline: {capabilities['thermal_baseline_c']}°C")
        print(f"Has NPU: {capabilities['has_npu']}")
        print(f"Has GPU: {capabilities['has_gpu']}")
        print(f"GPU vendor: {capabilities['gpu_vendor']}")
        print(f"CPU cores: {capabilities['cpu_cores']}")
        print(f"RAM: {capabilities['total_memory_gb']}GB")
        ```

    WARD Test Examples:
        ```python
        # Test 1: Form factor detection
        @ward.test("device_capability detects form factor")
        def test_device_form_factor():
            device = DeviceCapability()
            form_factor = device.get_form_factor()

            # Should return valid form factor
            ward.assert_in(form_factor, list(FormFactor))

        # Test 2: Thermal baseline mapping
        @ward.test("device_capability maps thermal baseline correctly")
        def test_device_thermal_baseline():
            device = DeviceCapability()

            # Mock laptop detection
            device._form_factor = FormFactor.LAPTOP
            baseline = device.get_thermal_baseline()
            ward.assert_equal(baseline, 75.0)  # Laptop baseline

            # Mock phone detection
            device._form_factor = FormFactor.PHONE
            baseline = device.get_thermal_baseline()
            ward.assert_equal(baseline, 65.0)  # Phone baseline

        # Test 3: Accelerator detection
        @ward.test("device_capability detects GPU availability")
        def test_device_gpu_detection():
            device = DeviceCapability()
            has_gpu = device.has_gpu()

            # Should return boolean
            ward.assert_is_instance(has_gpu, bool)

            if has_gpu:
                # If GPU detected, should have vendor
                vendor = device.get_gpu_vendor()
                ward.assert_is_not_none(vendor)

        # Test 4: Capability aggregation
        @ward.test("device_capability returns complete capabilities")
        def test_device_capabilities():
            device = DeviceCapability()
            caps = device.get_capabilities()

            # Required fields
            ward.assert_in("form_factor", caps)
            ward.assert_in("thermal_baseline_c", caps)
            ward.assert_in("has_npu", caps)
            ward.assert_in("has_gpu", caps)
            ward.assert_in("cpu_cores", caps)
        ```

    TODO List:
        - TODO(@platform-team): Implement Linux dmidecode chassis type detection
        - TODO(@platform-team): Add Windows WMI chassis type detection
        - TODO(@platform-team): Add macOS system_profiler model detection
        - TODO(@platform-team): Implement NPU detection (device tree, NNAPI, Neural Engine)
        - TODO(@platform-team): Implement GPU detection (nvidia-smi, rocm-smi, Metal)
        - TODO(@platform-team): Add GPU vendor detection logic
        - TODO(@platform-team): Implement CPU core count detection
        - TODO(@platform-team): Add RAM capacity detection
        - TODO(@platform-team): Cache detection results (one-time initialization)
        - TODO(@platform-team): Add Prometheus metrics (device_form_factor, device_accelerators)

    ADR References:
        - ADR-0026: Thermal Hysteresis Matrix
        - ADR-0026a: Thermal Sensor Monitoring & State Detection
    """

    # Thermal baseline mapping (°C, from ADR-0026)
    THERMAL_BASELINES = {
        FormFactor.LAPTOP: 75.0,
        FormFactor.PHONE: 65.0,
        FormFactor.DESKTOP: 82.0,
        FormFactor.SERVER: 85.0,
        FormFactor.TABLET: 70.0,
        FormFactor.UNKNOWN: 80.0,  # Conservative fallback
    }

    def __init__(self):
        """
        Initialize device capability detector.

        Implementation:
            1. Detect platform (Linux/Windows/macOS/Android)
            2. Detect form factor (laptop/phone/desktop/server)
            3. Probe for accelerators (NPU, GPU, CPU)
            4. Establish thermal baseline
            5. Cache results

        Performance:
            - Initialization: <50ms (one-time detection)
            - Subsequent queries: <1ms (cached)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Detect device capabilities
        # 1. Detect OS: self.platform = platform.system()
        # 2. Detect form factor: self._form_factor = self._detect_form_factor()
        # 3. Probe accelerators:
        #    - self._has_npu = self._detect_npu()
        #    - self._has_gpu = self._detect_gpu()
        #    - self._gpu_vendor = self._detect_gpu_vendor()
        # 4. Detect hardware specs:
        #    - self._cpu_cores = self._detect_cpu_cores()
        #    - self._total_memory_gb = self._detect_memory()
        # 5. Establish baseline: self._thermal_baseline = self.THERMAL_BASELINES[self._form_factor]
        # 6. Initialize Prometheus metrics:
        #    - device_form_factor (Info, labels: form_factor)
        #    - device_accelerators (Gauge, labels: type)

        self.platform = platform.system()  # "Linux", "Windows", "Darwin"
        self._form_factor: Optional[FormFactor] = None
        self._thermal_baseline: Optional[float] = None
        self._has_npu: Optional[bool] = None
        self._has_gpu: Optional[bool] = None
        self._gpu_vendor: Optional[GPUVendor] = None
        self._cpu_cores: Optional[int] = None
        self._total_memory_gb: Optional[float] = None

        logger.info(
            "[DeviceCapability] Initialized device capability detector",
            platform=self.platform,
        )

    def get_form_factor(self) -> FormFactor:
        """
        Detect device form factor.

        Returns:
            FormFactor enum (LAPTOP, PHONE, DESKTOP, SERVER, TABLET, UNKNOWN)

        Detection Methods:
            - **Linux**: dmidecode -s chassis-type (Notebook, Desktop, Server, Tablet)
                        /proc/device-tree/model (Raspberry Pi, mobile SoC)
            - **Windows**: WMI Win32_SystemEnclosure ChassisTypes
                          (Portable=8-11, Desktop=3-7, Server=17-24)
            - **macOS**: system_profiler SPHardwareDataType | grep "Model Identifier"
                        (MacBook=laptop, Mac mini=desktop, iMac=desktop)
            - **Android**: ro.build.product, devicetree (phone detection)

        Caching:
            - Returns cached value if already detected
            - One-time detection on first call

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement form factor detection
        # 1. Check cache: if self._form_factor: return self._form_factor
        # 2. Detect based on platform:
        #    - Linux: subprocess.run(["dmidecode", "-s", "chassis-type"])
        #      Map output: "Notebook" → LAPTOP, "Desktop" → DESKTOP, etc.
        #    - Windows: wmi query Win32_SystemEnclosure, check ChassisTypes[0]
        #      Map: 8-11 → LAPTOP, 3-7 → DESKTOP, 17-24 → SERVER
        #    - macOS: subprocess.run(["system_profiler", "SPHardwareDataType"])
        #      Parse "Model Identifier": "MacBook*" → LAPTOP, "iMac*" → DESKTOP
        # 3. Cache result: self._form_factor = detected_form_factor
        # 4. Return form factor

        logger.debug("[DeviceCapability] Get form factor")
        return FormFactor.UNKNOWN  # TODO: Replace with actual implementation

    def get_thermal_baseline(self) -> float:
        """
        Get thermal baseline for device (°C).

        Returns:
            Safe baseline temperature in Celsius:
                - Laptop: 75°C (limited passive cooling)
                - Phone: 65°C (very limited thermal capacity)
                - Desktop: 82°C (active cooling)
                - Server: 85°C (advanced thermal management)
                - Tablet: 70°C (moderate thermal capacity)
                - Unknown: 80°C (conservative fallback)

        Thermal Baseline Rationale (ADR-0026):
            - **Laptop**: Limited passive cooling, thermal pad contact to chassis
            - **Phone**: Small form factor, battery proximity, user comfort (<45°C surface)
            - **Desktop**: Tower chassis, multiple fans, good airflow
            - **Server**: Data center environment, rack cooling, high-power CPUs
            - **Unknown**: Conservative baseline for safety

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement baseline lookup
        # 1. Check cache: if self._thermal_baseline: return self._thermal_baseline
        # 2. Get form factor: form_factor = self.get_form_factor()
        # 3. Lookup baseline: baseline = self.THERMAL_BASELINES[form_factor]
        # 4. Cache result: self._thermal_baseline = baseline
        # 5. Return baseline

        logger.debug("[DeviceCapability] Get thermal baseline")
        return 80.0  # TODO: Replace with actual implementation

    def has_npu(self) -> bool:
        """
        Check if device has NPU (Neural Processing Unit).

        Returns:
            True if NPU available, False otherwise

        Detection Methods:
            - **Linux**: Check /proc/device-tree/soc/npu* (Qualcomm Hexagon, MediaTek)
            - **Windows**: Check NNAPI capability (Android subsystem)
            - **macOS**: Check for Neural Engine (M1+, system_profiler SPiBridgeDataType)
            - **Android**: Check for Hexagon DSP, MediaTek NeuroPilot, Kirin NPU

        NPU Examples:
            - Qualcomm Hexagon DSP (Snapdragon 8xx series)
            - MediaTek NeuroPilot APU
            - Apple Neural Engine (M1, M2, M3)
            - Kirin NPU (Huawei)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement NPU detection
        # 1. Check cache: if self._has_npu is not None: return self._has_npu
        # 2. Detect based on platform:
        #    - Linux: Check Path("/proc/device-tree/soc/npu").exists() or similar paths
        #    - macOS: subprocess.run(["system_profiler", "SPiBridgeDataType"]) (check for Neural Engine)
        #    - Android: Check ro.hardware.neuralnetworks (NNAPI)
        # 3. Cache result: self._has_npu = detected
        # 4. Return boolean

        logger.debug("[DeviceCapability] Check NPU availability")
        return False  # TODO: Replace with actual implementation

    def has_gpu(self) -> bool:
        """
        Check if device has GPU (discrete or integrated).

        Returns:
            True if GPU available, False otherwise

        Detection Methods:
            - **NVIDIA**: nvidia-smi (returns 0 if GPU present)
            - **AMD**: rocm-smi (returns 0 if GPU present)
            - **Intel Arc**: intel_gpu_frequency (check for /sys/class/drm/card*/gt_*)
            - **Apple**: Check Metal capabilities (system_profiler SPDisplaysDataType)

        GPU Examples:
            - NVIDIA GeForce RTX, Tesla, Quadro
            - AMD Radeon RX, Instinct
            - Intel Arc A-series, Iris Xe
            - Apple Metal (M1, M2, M3 integrated GPU)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement GPU detection
        # 1. Check cache: if self._has_gpu is not None: return self._has_gpu
        # 2. Probe GPU vendors:
        #    - NVIDIA: subprocess.run(["nvidia-smi", "-L"], capture_output=True)
        #      Check returncode == 0
        #    - AMD: subprocess.run(["rocm-smi", "--showproductname"], capture_output=True)
        #      Check returncode == 0
        #    - Intel: Check Path("/sys/class/drm/card0/gt_cur_freq_mhz").exists()
        #    - Apple: subprocess.run(["system_profiler", "SPDisplaysDataType"])
        #      Check for "Metal" in output
        # 3. Cache result: self._has_gpu = detected
        # 4. Return boolean

        logger.debug("[DeviceCapability] Check GPU availability")
        return False  # TODO: Replace with actual implementation

    def get_gpu_vendor(self) -> Optional[GPUVendor]:
        """
        Get GPU vendor if available.

        Returns:
            GPUVendor enum (NVIDIA, AMD, INTEL, APPLE, QUALCOMM) or None

        Detection Methods:
            - **NVIDIA**: nvidia-smi --query-gpu=name --format=csv
            - **AMD**: rocm-smi --showproductname
            - **Intel Arc**: lspci | grep -i vga | grep -i intel
            - **Apple**: system_profiler SPDisplaysDataType (Metal support)
            - **Qualcomm**: lspci | grep -i adreno (Snapdragon Adreno)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement GPU vendor detection
        # 1. Check cache: if self._gpu_vendor is not None: return self._gpu_vendor
        # 2. Check has_gpu: if not self.has_gpu(): return None
        # 3. Probe vendors in order:
        #    a. NVIDIA: subprocess.run(["nvidia-smi", "--query-gpu=name"])
        #       If success: return GPUVendor.NVIDIA
        #    b. AMD: subprocess.run(["rocm-smi", "--showproductname"])
        #       If success: return GPUVendor.AMD
        #    c. Intel: subprocess.run(["lspci"]) and search for "Intel.*VGA"
        #       If found: return GPUVendor.INTEL
        #    d. Apple: Check platform == "Darwin" and has_gpu
        #       If true: return GPUVendor.APPLE
        # 4. Cache result: self._gpu_vendor = detected_vendor
        # 5. Return vendor or None

        logger.debug("[DeviceCapability] Get GPU vendor")
        return None  # TODO: Replace with actual implementation

    def get_cpu_cores(self) -> int:
        """
        Get CPU core count.

        Returns:
            Number of CPU cores (physical cores)

        Detection Methods:
            - **Linux**: lscpu | grep "^CPU(s):" or /proc/cpuinfo
            - **Windows**: wmic cpu get NumberOfCores
            - **macOS**: sysctl -n hw.physicalcpu

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement CPU core detection
        # 1. Check cache: if self._cpu_cores is not None: return self._cpu_cores
        # 2. Detect based on platform:
        #    - Linux: subprocess.run(["lscpu"]) and parse "CPU(s):"
        #    - Windows: subprocess.run(["wmic", "cpu", "get", "NumberOfCores"])
        #    - macOS: subprocess.run(["sysctl", "-n", "hw.physicalcpu"])
        # 3. Parse output: cores = int(output.strip())
        # 4. Cache result: self._cpu_cores = cores
        # 5. Return cores

        logger.debug("[DeviceCapability] Get CPU cores")
        return 0  # TODO: Replace with actual implementation

    def get_total_memory_gb(self) -> float:
        """
        Get total RAM capacity (GB).

        Returns:
            Total memory in GB

        Detection Methods:
            - **Linux**: free -g | grep "^Mem:" or /proc/meminfo
            - **Windows**: wmic computersystem get TotalPhysicalMemory
            - **macOS**: sysctl -n hw.memsize

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement memory detection
        # 1. Check cache: if self._total_memory_gb is not None: return self._total_memory_gb
        # 2. Detect based on platform:
        #    - Linux: subprocess.run(["free", "-g"]) and parse "Mem:" line
        #    - Windows: subprocess.run(["wmic", "computersystem", "get", "TotalPhysicalMemory"])
        #      Convert bytes to GB: gb = int(output) / (1024**3)
        #    - macOS: subprocess.run(["sysctl", "-n", "hw.memsize"])
        #      Convert bytes to GB: gb = int(output) / (1024**3)
        # 3. Cache result: self._total_memory_gb = gb
        # 4. Return GB

        logger.debug("[DeviceCapability] Get total memory")
        return 0.0  # TODO: Replace with actual implementation

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get all device capabilities.

        Returns:
            Dict with:
                - form_factor: Device type (str)
                - thermal_baseline_c: Safe baseline temperature (float)
                - has_npu: NPU available (bool)
                - has_gpu: GPU available (bool)
                - gpu_vendor: GPU vendor if available (str or None)
                - cpu_cores: CPU core count (int)
                - total_memory_gb: RAM capacity (float)
                - platform: OS platform (str)

        Efficiency:
            - Single call returns all capabilities
            - All values cached from initialization

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement capability aggregation
        # 1. Call all detection methods:
        #    - form_factor = self.get_form_factor()
        #    - thermal_baseline = self.get_thermal_baseline()
        #    - has_npu = self.has_npu()
        #    - has_gpu = self.has_gpu()
        #    - gpu_vendor = self.get_gpu_vendor()
        #    - cpu_cores = self.get_cpu_cores()
        #    - memory_gb = self.get_total_memory_gb()
        # 2. Build dict:
        #    capabilities = {
        #        "form_factor": form_factor.value,
        #        "thermal_baseline_c": thermal_baseline,
        #        "has_npu": has_npu,
        #        "has_gpu": has_gpu,
        #        "gpu_vendor": gpu_vendor.value if gpu_vendor else None,
        #        "cpu_cores": cpu_cores,
        #        "total_memory_gb": memory_gb,
        #        "platform": self.platform
        #    }
        # 3. Return dict

        return {
            "form_factor": FormFactor.UNKNOWN.value,
            "thermal_baseline_c": 80.0,
            "has_npu": False,
            "has_gpu": False,
            "gpu_vendor": None,
            "cpu_cores": 0,
            "total_memory_gb": 0.0,
            "platform": self.platform,
        }  # TODO: Replace with actual implementation


# Expected lint errors (documented):
# - Unused imports: Path (used in NPU/GPU detection, file existence checks)
# - Unused imports: platform, subprocess (used in detection methods)
# - Unused imports: List (used in type hints for future methods)
# - structlog not resolved (dependency not installed yet)
# These will be resolved when dependencies are installed and implementation is complete.
# These will be resolved when dependencies are installed and implementation is complete.
