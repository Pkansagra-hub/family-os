"""
Capability Matcher - Device Capability Detection and Model Compatibility

Layer: L5 Infrastructure
Component: Model Placement Cascade
Priority: 🟡 MEDIUM (5% of Milestone 7, feature-flagged for Phase 2)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0027: Model Placement Cascade (4-Tier Device Detection)
    - ADR-0027a: Placement Algorithm (Capability Matching)

Feature Flag Status:
    - Phase 1 (TODAY): Minimal use (Remote-first, 95% traffic)
    - Phase 2 (2026): Critical (30% local traffic with dongle/PC)
    - ENABLE_LOCAL_INFERENCE = False (OFF in Phase 1)

Device Capability Categories:
    1. NPU (Neural Processing Unit): 1% TODAY, 15% Phase 2
       - Qualcomm Hexagon (45 TOPS on Snapdragon 8 Gen 3)
       - ASUS ProArt P16 (50 TOPS NPU) ← Capable TODAY
       - Apple Neural Engine (35 TOPS on A17 Pro)
       - MediaTek Dimensity 9300 (40 TOPS)

    2. GPU (Graphics Processing Unit): 1% TODAY, 15% Phase 2
       - NVIDIA RTX 4090 (24GB VRAM)
       - AMD Radeon RX 7900 XTX (24GB VRAM)
       - Intel Arc A770 (16GB VRAM)
       - Apple M3 Max (up to 128GB unified memory)

    3. CPU (Central Processing Unit): 3% TODAY, 10% Phase 2
       - Always available (fallback tier)
       - Intel Core i9 (32 threads)
       - AMD Ryzen 9 (24 threads)
       - Apple M3 (12 performance cores)

    4. Remote (User's API Keys): 95% TODAY, 60% Phase 2
       - Always available (network permitting)
       - No device requirements

Hardware Requirements (Phase 2):
    NPU Tier:
        - Min 50 TOPS (trillion operations per second)
        - 256MB+ dedicated NPU memory
        - Thermal headroom (<80°C sustained)
        - Model size <8GB (quantized INT8/INT4)

    GPU Tier:
        - Min 8GB VRAM (16GB recommended)
        - Thermal headroom (<85°C sustained)
        - Model size <16GB
        - CUDA compute capability 7.0+ or Metal 3

    CPU Tier:
        - Min 4GB RAM available
        - 4+ cores recommended
        - Model size <4GB (quantized)

Dependencies:
    Internal:
        - k1.l5_infrastructure.thermal.monitor (Thermal state detection)
        - k1.l4_runtime.device.detector (Hardware detection)
    External:
        - psutil: System memory/CPU detection
        - py3nvml: NVIDIA GPU detection
        - pyopencl: OpenCL GPU detection (AMD/Intel)

Connects To:
    Upstream:
        - k1.l5_infrastructure.placement.cascade_engine (Tier evaluation)
    Downstream:
        - k1.l5_infrastructure.thermal.monitor (Thermal constraints)
        - k1.l4_runtime.device.detector (Hardware enumeration)

Performance Budgets:
    - check_npu_capable(): <10ms P95
    - check_gpu_capable(): <10ms P95
    - check_cpu_capable(): <5ms P95
    - get_available_memory(): <5ms P95
    - check_model_fits(): <5ms P95

Observability:
    - Metrics: k1_device_capabilities{tier, available} (gauge: 0=unavailable, 1=available)
    - Metrics: k1_device_memory_available_mb{tier} (gauge)
    - Metrics: k1_device_thermal_state{tier, zone} (gauge: 0=nominal, 1=fair, 2=serious, 3=critical)
    - Metrics: k1_capability_checks_total{tier, result}
    - Traces: Span capability_matcher.check_capability
    - Logs: INFO capabilities detected, WARNING tier unavailable, ERROR thermal constraint

References:
    - Whiteboard: docs/whiteboard.md (Section: Device Capability Detection)
    - Test: tests/k1/l5_infrastructure/placement/test_capability_matcher.py
"""

import logging
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
from typing import Any, Optional

# Internal imports
# TODO(@ml-platform-team): Import from existing modules (Issue #L5-7.2.1)
# from k1.l5_infrastructure.thermal.monitor import ThermalMonitor, ThermalZone
# from k1.l4_runtime.device.detector import DeviceDetector
# import psutil  # System memory/CPU
# import py3nvml  # NVIDIA GPU

logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# Minimum hardware requirements (Phase 2)
MIN_NPU_TOPS = 50  # ASUS ProArt P16 has 50 TOPS
MIN_NPU_MEMORY_MB = 256
MIN_GPU_VRAM_GB = 8
MIN_GPU_VRAM_MB = MIN_GPU_VRAM_GB * 1024
MIN_CPU_RAM_GB = 4
MIN_CPU_RAM_MB = MIN_CPU_RAM_GB * 1024

# Thermal thresholds (Celsius)
MAX_NPU_TEMP_C = 80
MAX_GPU_TEMP_C = 85
MAX_CPU_TEMP_C = 90

# Working memory overhead (percentage of model size)
WORKING_MEMORY_OVERHEAD_PCT = 0.2  # 20% overhead for activations/buffers

# Model size limits (MB)
MODEL_SIZE_LIMITS = {
    "npu": 8 * 1024,  # 8GB (quantized INT8)
    "gpu": 16 * 1024,  # 16GB
    "cpu": 4 * 1024,  # 4GB (quantized INT4/INT8)
    "remote": float("inf"),  # No limit (cloud)
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class AcceleratorType(Enum):
    """Hardware accelerator types."""

    NPU = "npu"
    GPU = "gpu"
    CPU = "cpu"
    REMOTE = "remote"


class DeviceFormFactor(Enum):
    """Device form factors."""

    PHONE = "phone"  # Mobile phone
    TABLET = "tablet"  # Tablet
    LAPTOP = "laptop"  # Laptop
    DESKTOP = "desktop"  # Desktop PC
    SERVER = "server"  # Server
    UNKNOWN = "unknown"


@dataclass
class HardwareCapability:
    """
    Hardware capability information.

    Fields:
        accelerator_type: Type of accelerator (NPU/GPU/CPU)
        available: True if accelerator available and usable
        memory_mb: Available memory (MB)
        compute_capability: Device-specific compute capability
        thermal_zone: Current thermal zone (nominal/fair/serious/critical)
        model: Hardware model name
    """

    accelerator_type: AcceleratorType
    available: bool
    memory_mb: float
    compute_capability: Optional[str] = None
    thermal_zone: Optional[str] = None
    model: Optional[str] = None


@dataclass
class DeviceCapabilities:
    """
    Complete device capabilities.

    Fields:
        form_factor: Device type (phone/laptop/desktop/server)
        npu: NPU capability (if available)
        gpu: GPU capability (if available)
        cpu: CPU capability (always available)
        remote: Remote capability (always available if network)
        total_system_memory_mb: Total system RAM
        available_system_memory_mb: Available system RAM
    """

    form_factor: DeviceFormFactor
    npu: Optional[HardwareCapability] = None
    gpu: Optional[HardwareCapability] = None
    cpu: Optional[HardwareCapability] = None
    remote: Optional[HardwareCapability] = None
    total_system_memory_mb: float = 0.0
    available_system_memory_mb: float = 0.0


@dataclass
class CompatibilityResult:
    """
    Model-device compatibility result.

    Fields:
        compatible: True if model can run on device
        reason: Human-readable reason (if incompatible)
        required_memory_mb: Memory required for model + batch
        available_memory_mb: Memory available on device
        thermal_ok: True if thermal constraints satisfied
    """

    compatible: bool
    reason: Optional[str] = None
    required_memory_mb: Optional[float] = None
    available_memory_mb: Optional[float] = None
    thermal_ok: bool = True


# =============================================================================
# SECTION 4: DEVICE CAPABILITY MATCHER
# =============================================================================


class DeviceCapabilityMatcher:
    """
    Device capability detection and model-device compatibility matching.

    Responsibilities:
        - Detect available accelerators (NPU/GPU/CPU)
        - Check model-device compatibility (memory, compute)
        - Validate thermal constraints
        - Report capability mismatches

    Phase 1 (TODAY): Minimal use (Remote-first, 95% traffic)
    Phase 2 (2026): Critical (30% local traffic with dongle/PC)

    Thread Safety: Yes (cached capabilities updated periodically)
    Async Safe: Yes

    Cognitive Trace:
        - Accepts cognitive_trace_id from caller
        - Propagates to thermal monitor, device detector
        - Includes in all logs

    Performance Budget (P95):
        - check_npu_capable(): <10ms
        - check_gpu_capable(): <10ms
        - check_cpu_capable(): <5ms
        - get_available_memory(): <5ms
        - check_model_fits(): <5ms

    Examples:
        >>> matcher = DeviceCapabilityMatcher(thermal_monitor, device_detector)
        >>> capabilities = await matcher.get_capabilities()
        >>> print(capabilities.npu.available, capabilities.gpu.available)
        >>> compatible = await matcher.check_model_fits('gpu', model_size_mb=8000, batch_size=1)
        >>> print(compatible.compatible, compatible.reason)

    References:
        - ADR-0027: Model Placement Cascade (Device Detection)
        - ADR-0027a: Placement Algorithm (Capability Matching)
    """

    def __init__(
        self,
        thermal_monitor: Optional[Any] = None,  # TODO: Type hint ThermalMonitor
        device_detector: Optional[Any] = None,  # TODO: Type hint DeviceDetector
        cache_ttl_seconds: int = 60,
    ):
        """
        Initialize device capability matcher.

        Args:
            thermal_monitor: Thermal monitor (optional, Phase 2)
            device_detector: Device detector (optional, auto-detect if None)
            cache_ttl_seconds: Cache TTL for capability data (default: 60s)

        Side Effects:
            - Detects hardware capabilities (NPU/GPU/CPU)
            - Queries thermal state
            - Caches capability data

        ADR: ADR-0027 (Device Detection)
        Assigned to: Issue #L5-7.2.1
        """
        # TODO(@ml-platform-team): Implement initialization
        # 1. Store dependencies
        # 2. Detect device form factor (phone/laptop/desktop)
        # 3. Enumerate accelerators:
        #    - NPU: Check for Qualcomm Hexagon, Apple Neural Engine, Intel NPU
        #    - GPU: Check NVIDIA (py3nvml), AMD (pyopencl), Intel Arc
        #    - CPU: Always available
        # 4. Query system memory (psutil.virtual_memory())
        # 5. Setup capability cache (TTL: 60s)
        self._logger = logger
        self._thermal_monitor = thermal_monitor
        self._device_detector = device_detector
        self._cache_ttl_seconds = cache_ttl_seconds
        self._capabilities_cache: Optional[DeviceCapabilities] = None
        pass

    async def get_capabilities(
        self,
        cognitive_trace_id: Optional[str] = None,
    ) -> DeviceCapabilities:
        """
        Get complete device capabilities.

        Args:
            cognitive_trace_id: Trace ID for observability

        Returns:
            DeviceCapabilities with NPU/GPU/CPU/Remote info

        Caching:
            - Capabilities cached for cache_ttl_seconds (60s default)
            - Thermal state queried on each call (not cached)
            - Cache invalidated on thermal zone change

        Performance:
            - Cached: <5ms (return cached data)
            - Uncached: <50ms (enumerate hardware)

        Cognitive Trace:
            - Creates span: capability_matcher.get_capabilities
            - Includes: form_factor, accelerators_found, cognitive_trace_id
            - Logs include trace_id

        ADR: ADR-0027 (Capability Enumeration)
        Assigned to: Issue #L5-7.2.1
        """
        # TODO(@ml-platform-team): Implement capability detection
        # 1. Check cache (if TTL not expired)
        # 2. If cached: Update thermal state, return
        # 3. If not cached:
        #    a. Detect form factor (phone/laptop/desktop/server)
        #    b. Detect NPU (if available):
        #       - Check NPU TOPS (min 50)
        #       - Check NPU memory (min 256MB)
        #       - Check thermal state (<80°C)
        #    c. Detect GPU (if available):
        #       - Check VRAM (min 8GB)
        #       - Check CUDA/OpenCL compute capability
        #       - Check thermal state (<85°C)
        #    d. Detect CPU (always available):
        #       - Check available RAM (min 4GB)
        #       - Check thermal state (<90°C)
        #    e. Remote always available (network permitting)
        # 4. Build DeviceCapabilities object
        # 5. Cache result
        # 6. Emit metrics: k1_device_capabilities
        # 7. Return DeviceCapabilities
        pass

    async def check_npu_capable(
        self,
        cognitive_trace_id: Optional[str] = None,
    ) -> bool:
        """
        Check if device has usable NPU capability.

        Args:
            cognitive_trace_id: Trace ID for observability

        Returns:
            True if NPU available and not thermally constrained

        Checks:
            - NPU exists (Qualcomm/Apple/Intel/MediaTek)
            - NPU TOPS >= 50 (ASUS ProArt P16 has 50 TOPS)
            - NPU memory >= 256MB
            - Thermal zone not critical (<80°C)

        Performance:
            - Latency: <10ms P95 (cached capabilities)

        Cognitive Trace:
            - Creates span: capability_matcher.check_npu_capable
            - Includes: npu_available, thermal_zone, cognitive_trace_id
            - Logs include trace_id

        ADR: ADR-0027a (NPU Detection)
        Assigned to: Issue #L5-7.2.1
        """
        # TODO(@ml-platform-team): Implement NPU capability check
        # 1. Get capabilities (cached)
        # 2. Check if npu field present
        # 3. Check npu.available == True
        # 4. Check thermal_zone not 'critical'
        # 5. Return bool
        pass

    async def check_gpu_capable(
        self,
        cognitive_trace_id: Optional[str] = None,
    ) -> bool:
        """
        Check if device has usable GPU capability.

        Args:
            cognitive_trace_id: Trace ID for observability

        Returns:
            True if GPU available and not thermally constrained

        Checks:
            - GPU exists (NVIDIA/AMD/Intel/Apple)
            - GPU VRAM >= 8GB
            - CUDA compute capability >= 7.0 (Volta) or Metal 3
            - Thermal zone not critical (<85°C)

        Performance:
            - Latency: <10ms P95 (cached capabilities)

        Cognitive Trace:
            - Creates span: capability_matcher.check_gpu_capable
            - Includes: gpu_available, vram_gb, thermal_zone, cognitive_trace_id
            - Logs include trace_id

        ADR: ADR-0027a (GPU Detection)
        Assigned to: Issue #L5-7.2.1
        """
        # TODO(@ml-platform-team): Implement GPU capability check
        # 1. Get capabilities (cached)
        # 2. Check if gpu field present
        # 3. Check gpu.available == True
        # 4. Check gpu.memory_mb >= MIN_GPU_VRAM_MB
        # 5. Check thermal_zone not 'critical'
        # 6. Return bool
        pass

    async def check_cpu_capable(
        self,
        cognitive_trace_id: Optional[str] = None,
    ) -> bool:
        """
        Check if device has usable CPU capability.

        Args:
            cognitive_trace_id: Trace ID for observability

        Returns:
            True (CPU always available unless severely thermally constrained)

        Checks:
            - CPU available (always True)
            - Available RAM >= 4GB
            - Thermal zone not critical (<90°C)

        Performance:
            - Latency: <5ms P95 (cached capabilities)

        Cognitive Trace:
            - Creates span: capability_matcher.check_cpu_capable
            - Includes: cpu_available, ram_gb, thermal_zone, cognitive_trace_id
            - Logs include trace_id

        ADR: ADR-0027a (CPU Fallback)
        Assigned to: Issue #L5-7.2.1
        """
        # TODO(@ml-platform-team): Implement CPU capability check
        # 1. Get capabilities (cached)
        # 2. Check cpu.available (always True)
        # 3. Check available_system_memory_mb >= MIN_CPU_RAM_MB
        # 4. Check thermal_zone not 'critical'
        # 5. Return bool
        pass

    async def get_available_memory(
        self,
        tier: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> float:
        """
        Get available memory for tier (MB).

        Args:
            tier: Placement tier (npu/gpu/cpu/remote)
            cognitive_trace_id: Trace ID for observability

        Returns:
            Available memory in MB
                - NPU: 256MB typical (fixed allocation)
                - GPU: 4-24GB VRAM (query CUDA/OpenCL)
                - CPU: System RAM / 2 (leave 50% for OS)
                - Remote: Unlimited (cloud provider)

        Performance:
            - Latency: <5ms P95 (cached capabilities)

        Cognitive Trace:
            - Creates span: capability_matcher.get_available_memory
            - Includes: tier, available_mb, cognitive_trace_id
            - Logs include trace_id

        ADR: ADR-0027a (Memory Availability)
        Assigned to: Issue #L5-7.2.1
        """
        # TODO(@ml-platform-team): Implement memory availability lookup
        # 1. Get capabilities (cached)
        # 2. Match tier:
        #    - 'npu': Return npu.memory_mb (256MB typical)
        #    - 'gpu': Return gpu.memory_mb (8-24GB VRAM)
        #    - 'cpu': Return available_system_memory_mb / 2
        #    - 'remote': Return float('inf')
        # 3. Emit metric: k1_device_memory_available_mb{tier}
        # 4. Return float
        pass

    async def check_model_fits(
        self,
        tier: str,
        model_size_mb: float,
        batch_size: int = 1,
        working_memory_pct: float = WORKING_MEMORY_OVERHEAD_PCT,
        cognitive_trace_id: Optional[str] = None,
    ) -> CompatibilityResult:
        """
        Check if model + batch fits in tier memory.

        Args:
            tier: Target tier (npu/gpu/cpu/remote)
            model_size_mb: Model size in MB
            batch_size: Batch size (default: 1)
            working_memory_pct: Working memory overhead (default: 20%)
            cognitive_trace_id: Trace ID for observability

        Returns:
            CompatibilityResult with compatible flag and reason

        Calculation:
            required_memory = model_size_mb + (batch_size * avg_activation_mb) + working_memory
            avg_activation_mb ≈ model_size_mb * 0.1 (10% of model size per sample)
            working_memory = model_size_mb * working_memory_pct (20% overhead)
            fits = required_memory <= available_memory

        Examples:
            GPT-2 (124M params, 500MB model):
                - Batch 1: 500 + (1 * 50) + 100 = 650MB (fits NPU? NO, GPU? YES)
                - Batch 8: 500 + (8 * 50) + 100 = 1000MB (fits NPU? NO, GPU? YES)

            Llama-3-8B (8B params, 16GB model):
                - Batch 1: 16000 + (1 * 1600) + 3200 = 20800MB (20GB) (fits GPU 24GB? YES)

        Performance:
            - Latency: <5ms P95 (simple calculation)

        Cognitive Trace:
            - Creates span: capability_matcher.check_model_fits
            - Includes: tier, model_size, batch_size, compatible, cognitive_trace_id
            - Logs include trace_id

        ADR: ADR-0027a (Model Compatibility)
        Assigned to: Issue #L5-7.2.1
        """
        # TODO(@ml-platform-team): Implement model fit check
        # 1. Get available memory for tier
        # 2. Calculate required memory:
        #    activation_per_sample = model_size_mb * 0.1
        #    total_activations = batch_size * activation_per_sample
        #    working_memory = model_size_mb * working_memory_pct
        #    required_memory = model_size_mb + total_activations + working_memory
        # 3. Check thermal state (if NPU/GPU)
        # 4. Check tier size limit (MODEL_SIZE_LIMITS)
        # 5. Compare: required_memory <= available_memory
        # 6. Build CompatibilityResult:
        #    - If fits: compatible=True
        #    - If too large: compatible=False, reason="Model size exceeds tier limit"
        #    - If insufficient memory: compatible=False, reason="Insufficient memory"
        #    - If thermal constraint: compatible=False, reason="Thermal constraint"
        # 7. Emit metric: k1_capability_checks_total{tier, result}
        # 8. Return CompatibilityResult
        pass

    async def get_form_factor(self) -> DeviceFormFactor:
        """
        Get device form factor (phone/laptop/desktop/server).

        Returns:
            DeviceFormFactor enum

        Detection Logic:
            - Phone: Battery-powered, <6.7" screen, ARM CPU
            - Tablet: Battery-powered, 7-13" screen, ARM CPU
            - Laptop: Battery-powered, >13" screen, x86/ARM CPU
            - Desktop: AC-powered, x86 CPU, discrete GPU common
            - Server: AC-powered, multiple CPUs, high RAM (>64GB)

        Performance:
            - Latency: <10ms (cached)

        ADR: ADR-0027 (Form Factor Detection)
        Assigned to: Issue #L5-7.2.1
        """
        # TODO(@ml-platform-team): Implement form factor detection
        # 1. Check battery presence (phone/tablet/laptop vs desktop/server)
        # 2. Check CPU architecture (ARM vs x86)
        # 3. Check RAM size (>64GB = server, 16-64GB = desktop, <16GB = laptop/phone)
        # 4. Check GPU type (discrete = desktop, integrated = laptop)
        # 5. Return DeviceFormFactor enum
        pass


# =============================================================================
# SECTION 5: MODULE EXPORTS
# =============================================================================

__all__ = [
    "DeviceCapabilityMatcher",
    "AcceleratorType",
    "DeviceFormFactor",
    "HardwareCapability",
    "DeviceCapabilities",
    "CompatibilityResult",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_device_capabilities{tier, available} (gauge: 0=unavailable, 1=available)
#   - k1_device_memory_available_mb{tier} (gauge)
#   - k1_device_thermal_state{tier, zone} (gauge: 0=nominal, 1=fair, 2=serious, 3=critical)
#   - k1_capability_checks_total{tier, result} (counter: compatible/incompatible)
#   - k1_device_form_factor{type} (gauge: 1 for detected type, 0 otherwise)
#
# Traces to generate:
#   - Span name: capability_matcher.get_capabilities
#   - Attributes: form_factor, npu_available, gpu_available, cpu_available, cognitive_trace_id
#   - Child spans: capability_matcher.check_model_fits
#
# Logs to emit:
#   - Level: INFO (capabilities detected), WARNING (tier unavailable), ERROR (thermal constraint)
#   - Fields: tier, available, memory_mb, thermal_zone, trace_id
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# All async methods accept cognitive_trace_id from caller:
#   1. Create trace span with this ID
#   2. Pass ID to thermal_monitor, device_detector
#   3. Include ID in all log statements
#
# This enables end-to-end request tracing from placement decision → capability check → thermal state.
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/placement/test_capability_matcher.py
#   - Test NPU detection (mock 50 TOPS NPU)
#   - Test GPU detection (mock 8GB VRAM GPU)
#   - Test CPU detection (always available)
#   - Test memory availability (NPU 256MB, GPU 8GB, CPU RAM/2)
#   - Test model fit calculation (various model sizes + batch sizes)
#   - Test thermal constraints (critical zone blocks tier)
#   - Test form factor detection (phone/laptop/desktop/server)
#   - Test capability caching (TTL 60s)
#
# No simulation code allowed:
#   - Use real hardware detection with mock responses
#   - Use ward fixtures for thermal_monitor, device_detector
#   - Integration tests > unit tests
#
# =============================================================================
