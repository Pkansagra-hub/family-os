"""
Module: k1.l5_infrastructure.thermal.placement_manager
Purpose: Orchestration of thermal-aware model placement with automatic failover

This module provides the ThermalPlacementManager class for managing model placement
across accelerators (NPU/GPU/CPU/Remote) based on thermal state with automatic failover.

Architecture:
    - Sensor polling: 100ms intervals (10Hz) for thermal monitoring
    - Decision orchestration: <5ms P95 placement decisions
    - Tier transitions: Automatic failover on thermal state changes
    - KV cache preservation: <30ms cache transfer during failover
    - Model migration: <100ms total failover latency

Performance Budgets:
    - Poll interval: 100ms (10Hz sensor polling)
    - Decision latency: <5ms P95
    - Failover latency: <100ms (unload 10ms + load 50ms + KV cache 30ms)
    - Placement selection: <50µs

Related ADRs:
    - ADR-0026: Thermal Hysteresis Matrix Device Management
    - ADR-0026b: Hysteresis State Machine (5°C Buffer)
    - ADR-0026c: Model Placement Integration (Thermal Cascade)
    - ADR-0027: Model Placement Cascade (NPU→GPU→CPU→Remote)

Research Foundation:
    - Android Thermal HAL: ML workload migration (TPU→GPU→CPU)
    - Apple Neural Engine: ANE→GPU→CPU thermal cascade
    - Intel DTT: Thermal budget-based workload placement
    - NVIDIA GPU Thermal Throttling: 83°C/93°C thresholds

Author: K1 Infrastructure Team
Date: 2025-10-27
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import structlog
from prometheus_client import Counter, Gauge, Histogram

from k1.l5_infrastructure.thermal.device_capability import DeviceCapability
from k1.l5_infrastructure.thermal.placement_decision import (PlacementDecision,
                                                             PlacementTier)
from k1.l5_infrastructure.thermal.sensors import ThermalSensors

logger = structlog.get_logger()

# Prometheus metrics
thermal_failover_total = Counter(
    'k1_thermal_failover_total',
    'Thermal failover events',
    ['from_tier', 'to_tier', 'thermal_zone']
)

thermal_placement_latency_ms = Histogram(
    'k1_thermal_placement_latency_ms',
    'Time to select/failover accelerator',
    buckets=[1, 5, 10, 25, 50, 100, 250]
)

thermal_accelerator_usage = Gauge(
    'k1_thermal_accelerator_usage',
    'Current accelerator usage by thermal state',
    ['accelerator', 'thermal_zone']
)

thermal_poll_latency_ms = Histogram(
    'k1_thermal_poll_latency_ms',
    'Time to poll thermal sensors',
    buckets=[1, 5, 10, 25, 50, 100]
)

thermal_failover_latency_ms = Histogram(
    'k1_thermal_failover_latency_ms',
    'Time to execute failover (unload + load + KV cache)',
    buckets=[10, 25, 50, 75, 100, 150, 200, 250]
)

placement_transitions_total = Counter(
    'k1_placement_transitions_total',
    'Total placement transitions',
    ['transition_type', 'from_tier', 'to_tier']
)


@dataclass
class PlacementStats:
    """Statistics for placement manager"""
    total_failovers: int = 0
    total_upgrades: int = 0
    total_downgrades: int = 0
    total_emergency_jumps: int = 0
    last_failover_time_ms: Optional[float] = None
    last_failover_latency_ms: Optional[float] = None
    current_tier_uptime_ms: float = 0.0

    def record_failover(self, latency_ms: float):
        """Record failover event"""
        self.total_failovers += 1
        self.last_failover_time_ms = time.perf_counter() * 1000
        self.last_failover_latency_ms = latency_ms

    def record_upgrade(self):
        """Record upgrade event"""
        self.total_upgrades += 1

    def record_downgrade(self):
        """Record downgrade event"""
        self.total_downgrades += 1

    def record_emergency_jump(self):
        """Record emergency jump event"""
        self.total_emergency_jumps += 1


class ThermalPlacementManager:
    """
    Orchestrates thermal-aware model placement with automatic failover

    This class manages model placement across accelerators (NPU/GPU/CPU/Remote) based on
    current thermal state, enforcing placement policies and executing automatic failover
    when thermal conditions change.

    Key Features:
        - Sensor polling: 100ms intervals (10Hz) for continuous thermal monitoring
        - Decision orchestration: <5ms P95 placement decisions using PlacementDecision
        - Automatic failover: Transparent migration on thermal state changes
        - KV cache preservation: Cached state transferred during failover (<30ms)
        - Thermal cascade: NPU→GPU→CPU→Remote placement restrictions per state

    Thermal Placement Policies:
        - COOL (<60°C): All accelerators available (NPU, GPU, CPU, Remote)
        - WARM (60-75°C): All accelerators available
        - HOT (75-85°C): Skip NPU (highest thermal load) → GPU, CPU, Remote
        - CRITICAL (85-95°C): Skip NPU & GPU → CPU, Remote only
        - EMERGENCY (>95°C): Local inference disabled → Remote only

    Usage Example:
        sensors = ThermalSensors()
        capability = DeviceCapability()
        manager = ThermalPlacementManager(sensors, capability)

        # Get placement tier for model
        tier = manager.get_placement_tier("llama-7b", preferred=PlacementTier.NPU)

        # Check if failover needed
        if manager.should_transition_tier("llama-7b"):
            await manager.transition_tier("llama-7b")

        # Get placement statistics
        stats = manager.get_placement_stats()

    Performance:
        - Sensor polling: 100ms intervals (10Hz)
        - Placement selection: <50µs
        - Decision latency: <5ms P95
        - Failover latency: <100ms (unload 10ms + load 50ms + KV cache 30ms)

    Related ADRs:
        - ADR-0026c: Model Placement Integration (Thermal Cascade)
        - ADR-0027: Model Placement Cascade (NPU→GPU→CPU→Remote)
    """

    def __init__(
        self,
        thermal_sensors: ThermalSensors,
        device_capability: DeviceCapability,
        poll_interval_ms: float = 100.0,
        enable_auto_failover: bool = True
    ):
        """
        Initialize thermal placement manager

        Args:
            thermal_sensors: ThermalSensors instance for temperature monitoring
            device_capability: DeviceCapability instance for accelerator detection
            poll_interval_ms: Sensor polling interval (default: 100ms)
            enable_auto_failover: Enable automatic failover on thermal transitions (default: True)
        """
        self.thermal_sensors = thermal_sensors
        self.device_capability = device_capability
        self.poll_interval_ms = poll_interval_ms
        self.enable_auto_failover = enable_auto_failover

        # Initialize placement decision engine
        self.decision = PlacementDecision(
            upgrade_cooldown_ms=10_000,
            downgrade_cooldown_ms=60_000,
            emergency_threshold_celsius=85.0
        )

        # Track current placements (model_id -> tier)
        self.current_placements: Dict[str, PlacementTier] = {}

        # Track placement entry times (model_id -> timestamp_ms)
        self.placement_entry_times: Dict[str, float] = {}

        # Detect available accelerators
        self.available_accelerators = self._detect_available_accelerators()

        # Placement statistics
        self.stats = PlacementStats()

        # Polling task
        self._polling_task: Optional[asyncio.Task] = None
        self._polling_active = False

        logger.info(
            "thermal_placement_manager_initialized",
            available_accelerators=[acc.value for acc in self.available_accelerators],
            poll_interval_ms=poll_interval_ms,
            enable_auto_failover=enable_auto_failover
        )

    def _detect_available_accelerators(self) -> List[PlacementTier]:
        """
        Detect which accelerators are available on this device

        Returns:
            List of available PlacementTier options

        Performance: <50ms on initialization
        """
        available = []

        # Check NPU availability
        if self.device_capability.has_npu():
            available.append(PlacementTier.NPU)
            logger.info("accelerator_detected", type="NPU")

        # Check GPU availability
        if self.device_capability.has_gpu():
            available.append(PlacementTier.GPU)
            logger.info("accelerator_detected", type="GPU")

        # CPU always available
        available.append(PlacementTier.CPU)

        # Remote always available (fallback)
        available.append(PlacementTier.REMOTE)

        return available

    def get_placement_tier(
        self,
        model_id: str,
        preferred: Optional[PlacementTier] = None
    ) -> PlacementTier:
        """
        Get best placement tier for model given current thermal state

        Selects best available accelerator based on:
        1. Current thermal state (COOL/WARM/HOT/CRITICAL/EMERGENCY)
        2. Thermal placement policies (allowed tiers per state)
        3. Available accelerators on device
        4. Preferred tier (if thermally allowed)

        Args:
            model_id: Model identifier
            preferred: Preferred placement tier (if thermally allowed)

        Returns:
            Selected PlacementTier

        Example:
            tier = manager.get_placement_tier("llama-7b", preferred=PlacementTier.NPU)
            if tier == PlacementTier.NPU:
                load_model_on_npu("llama-7b")

        Performance: <50µs
        """
        start_ms = time.perf_counter() * 1000

        # Get current thermal state
        metrics = self.thermal_sensors.get_all_metrics()
        temperature_celsius = max(
            metrics.get('cpu_temperature', 0.0),
            metrics.get('gpu_temperature', 0.0)
        )

        # Get thermal zone
        thermal_zone = self.decision.get_thermal_zone(temperature_celsius)

        # Get placement policy for current thermal zone
        policy = self.decision.PLACEMENT_POLICIES[thermal_zone]

        # Try preferred tier first (if thermally allowed)
        if preferred and policy.is_tier_allowed(preferred) and preferred in self.available_accelerators:
            selected = preferred
        else:
            # Select best available tier from policy
            selected = None
            for tier in policy.allowed_tiers:
                if tier in self.available_accelerators:
                    selected = tier
                    break

            if not selected:
                logger.error(
                    "no_available_accelerator",
                    thermal_zone=thermal_zone.value,
                    available=[acc.value for acc in self.available_accelerators]
                )
                selected = PlacementTier.REMOTE  # Ultimate fallback

        # Track placement
        old_placement = self.current_placements.get(model_id)
        self.current_placements[model_id] = selected

        # Record entry time if new placement
        if model_id not in self.placement_entry_times:
            self.placement_entry_times[model_id] = time.perf_counter() * 1000

        # Log failover if placement changed
        if old_placement and old_placement != selected:
            logger.info(
                "thermal_failover_detected",
                model_id=model_id,
                from_tier=old_placement.value,
                to_tier=selected.value,
                thermal_zone=thermal_zone.value,
                temperature_celsius=temperature_celsius
            )

            thermal_failover_total.labels(
                from_tier=old_placement.value,
                to_tier=selected.value,
                thermal_zone=thermal_zone.value
            ).inc()

        latency_ms = (time.perf_counter() * 1000) - start_ms
        thermal_placement_latency_ms.observe(latency_ms)

        # Update usage gauge
        thermal_accelerator_usage.labels(
            accelerator=selected.value,
            thermal_zone=thermal_zone.value
        ).inc()

        return selected

    def should_transition_tier(self, model_id: str) -> bool:
        """
        Check if model needs tier transition due to thermal state change

        Returns True if:
        1. Current placement violates thermal policy (e.g., NPU in HOT state)
        2. Emergency state requires immediate failover

        Args:
            model_id: Model identifier

        Returns:
            True if tier transition needed, False otherwise

        Example:
            if manager.should_transition_tier("llama-7b"):
                await manager.transition_tier("llama-7b")

        Performance: <5ms P95
        """
        if model_id not in self.current_placements:
            return False

        current_tier = self.current_placements[model_id]

        # Get current thermal state
        metrics = self.thermal_sensors.get_all_metrics()
        temperature_celsius = max(
            metrics.get('cpu_temperature', 0.0),
            metrics.get('gpu_temperature', 0.0)
        )
        power_watts = metrics.get('cpu_power', 0.0) + metrics.get('gpu_power', 0.0)

        # Check emergency state (immediate failover)
        if self.decision.should_emergency_jump(temperature_celsius):
            logger.warning(
                "emergency_failover_required",
                model_id=model_id,
                current_tier=current_tier.value,
                temperature_celsius=temperature_celsius
            )
            return True

        # Get thermal zone and policy
        thermal_zone = self.decision.get_thermal_zone(temperature_celsius)
        policy = self.decision.PLACEMENT_POLICIES[thermal_zone]

        # Check if current tier is still allowed
        if not policy.is_tier_allowed(current_tier):
            logger.warning(
                "thermal_failover_required",
                model_id=model_id,
                current_tier=current_tier.value,
                thermal_zone=thermal_zone.value,
                temperature_celsius=temperature_celsius
            )
            return True

        return False

    async def transition_tier(
        self,
        model_id: str,
        kv_cache: Optional[Dict] = None
    ) -> bool:
        """
        Execute tier transition (failover) for model

        Failover steps:
        1. Determine target tier based on thermal state
        2. Unload model from source accelerator (<10ms)
        3. Load model on target accelerator (<50ms)
        4. Transfer KV cache state (<30ms)
        5. Update placement tracking

        Args:
            model_id: Model to migrate
            kv_cache: KV cache state to transfer (optional)

        Returns:
            True if transition succeeded, False otherwise

        Example:
            success = await manager.transition_tier("llama-7b", kv_cache=cached_state)
            if success:
                logger.info("transition_complete")

        Performance: <100ms P95
        """
        start_ms = time.perf_counter() * 1000

        if model_id not in self.current_placements:
            logger.error("transition_failed_no_placement", model_id=model_id)
            return False

        from_tier = self.current_placements[model_id]

        # Determine target tier
        to_tier = self.get_placement_tier(model_id)

        if from_tier == to_tier:
            logger.debug(
                "transition_not_needed",
                model_id=model_id,
                tier=from_tier.value
            )
            return True

        try:
            logger.info(
                "transition_started",
                model_id=model_id,
                from_tier=from_tier.value,
                to_tier=to_tier.value
            )

            # Step 1: Unload model from source accelerator
            await self._unload_model(model_id, from_tier)

            # Step 2: Load model on target accelerator
            await self._load_model(model_id, to_tier)

            # Step 3: Transfer KV cache (if provided)
            if kv_cache:
                await self._transfer_kv_cache(model_id, kv_cache, to_tier)

            # Update placement tracking
            self.current_placements[model_id] = to_tier
            self.placement_entry_times[model_id] = time.perf_counter() * 1000

            # Update statistics
            latency_ms = (time.perf_counter() * 1000) - start_ms
            self.stats.record_failover(latency_ms)

            # Check transition type
            if self.decision._is_upgrade(from_tier, to_tier):
                self.stats.record_upgrade()
                self.decision.record_upgrade()
                transition_type = "upgrade"
            elif self.decision._is_downgrade(from_tier, to_tier):
                self.stats.record_downgrade()
                self.decision.record_downgrade()
                transition_type = "downgrade"
            else:
                transition_type = "lateral"

            # Check emergency jump
            metrics = self.thermal_sensors.get_all_metrics()
            temperature_celsius = max(
                metrics.get('cpu_temperature', 0.0),
                metrics.get('gpu_temperature', 0.0)
            )
            if self.decision.should_emergency_jump(temperature_celsius):
                self.stats.record_emergency_jump()

            logger.info(
                "transition_completed",
                model_id=model_id,
                from_tier=from_tier.value,
                to_tier=to_tier.value,
                transition_type=transition_type,
                latency_ms=latency_ms
            )

            # Update metrics
            thermal_failover_latency_ms.observe(latency_ms)
            placement_transitions_total.labels(
                transition_type=transition_type,
                from_tier=from_tier.value,
                to_tier=to_tier.value
            ).inc()

            return True

        except Exception as e:
            logger.error(
                "transition_failed",
                model_id=model_id,
                from_tier=from_tier.value,
                to_tier=to_tier.value,
                error=str(e)
            )
            return False

    async def _unload_model(self, model_id: str, tier: PlacementTier):
        """
        Unload model from accelerator

        TODO: Integrate with ModelHub for actual unload

        Performance: <10ms target
        """
        # Placeholder: Real implementation would call ModelHub.unload()
        await asyncio.sleep(0.01)

        logger.debug(
            "model_unloaded",
            model_id=model_id,
            tier=tier.value
        )

    async def _load_model(self, model_id: str, tier: PlacementTier):
        """
        Load model on accelerator

        TODO: Integrate with ModelHub for actual load

        Performance: <50ms target (cached in RAM)
        """
        # Placeholder: Real implementation would call ModelHub.load()
        await asyncio.sleep(0.05)

        logger.debug(
            "model_loaded",
            model_id=model_id,
            tier=tier.value
        )

    async def _transfer_kv_cache(self, model_id: str, kv_cache: Dict, tier: PlacementTier):
        """
        Transfer KV cache to new accelerator

        TODO: Integrate with KV Cache Manager (ADR-0025)

        Performance: <30ms target
        """
        # Placeholder: Real implementation would transfer cached tensors
        await asyncio.sleep(0.03)

        logger.debug(
            "kv_cache_transferred",
            model_id=model_id,
            tier=tier.value,
            cache_size_kb=len(str(kv_cache)) / 1024
        )

    async def start_polling(self):
        """
        Start thermal sensor polling task

        Polls sensors at poll_interval_ms (default: 100ms) and triggers
        automatic failover if thermal state changes require it.

        Example:
            await manager.start_polling()
            # Polling runs in background...
        """
        if self._polling_active:
            logger.warning("polling_already_active")
            return

        self._polling_active = True
        self._polling_task = asyncio.create_task(self._polling_loop())

        logger.info(
            "polling_started",
            poll_interval_ms=self.poll_interval_ms,
            enable_auto_failover=self.enable_auto_failover
        )

    async def stop_polling(self):
        """
        Stop thermal sensor polling task

        Example:
            await manager.stop_polling()
        """
        if not self._polling_active:
            return

        self._polling_active = False

        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        logger.info("polling_stopped")

    async def _polling_loop(self):
        """
        Thermal sensor polling loop

        Continuously polls sensors and triggers auto-failover if needed.
        """
        while self._polling_active:
            try:
                start_ms = time.perf_counter() * 1000

                # Poll thermal sensors
                metrics = self.thermal_sensors.get_all_metrics()

                poll_latency_ms = (time.perf_counter() * 1000) - start_ms
                thermal_poll_latency_ms.observe(poll_latency_ms)

                # Check if any models need failover
                if self.enable_auto_failover:
                    for model_id in list(self.current_placements.keys()):
                        if self.should_transition_tier(model_id):
                            await self.transition_tier(model_id)

                # Sleep until next poll
                await asyncio.sleep(self.poll_interval_ms / 1000.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("polling_error", error=str(e))
                await asyncio.sleep(self.poll_interval_ms / 1000.0)

    def get_placement_stats(self) -> PlacementStats:
        """
        Get placement statistics

        Returns:
            PlacementStats with failover counts, latencies, uptime

        Example:
            stats = manager.get_placement_stats()
            logger.info(
                "placement_stats",
                total_failovers=stats.total_failovers,
                total_upgrades=stats.total_upgrades,
                total_downgrades=stats.total_downgrades
            )
        """
        return self.stats

    def get_current_placement(self, model_id: str) -> Optional[PlacementTier]:
        """
        Get current placement tier for model

        Args:
            model_id: Model identifier

        Returns:
            Current PlacementTier or None if not placed
        """
        return self.current_placements.get(model_id)

    def get_placement_uptime_ms(self, model_id: str) -> float:
        """
        Get uptime (duration) of current placement

        Args:
            model_id: Model identifier

        Returns:
            Uptime in milliseconds, or 0.0 if not placed
        """
        if model_id not in self.placement_entry_times:
            return 0.0

        entry_time_ms = self.placement_entry_times[model_id]
        now_ms = time.perf_counter() * 1000
        return now_ms - entry_time_ms


# ============================================================================
# WARD Test Examples
# ============================================================================

"""
WARD Test Suite for ThermalPlacementManager

File: tests/k1/l5_infrastructure/thermal/test_placement_manager.py

```python
from ward import test, fixture
import asyncio

from k1.l5_infrastructure.thermal.placement_manager import (
    ThermalPlacementManager,
    PlacementTier,
    PlacementStats
)
from k1.l5_infrastructure.thermal.sensors import ThermalSensors
from k1.l5_infrastructure.thermal.device_capability import DeviceCapability


@fixture
async def manager():
    sensors = ThermalSensors()
    capability = DeviceCapability()
    mgr = ThermalPlacementManager(
        sensors,
        capability,
        poll_interval_ms=100.0,
        enable_auto_failover=True
    )
    yield mgr
    await mgr.stop_polling()


@test("get_placement_tier returns NPU in COOL state")
async def _(mgr=manager):
    # Mock sensors to return COOL temperature
    mgr.thermal_sensors._cache['cpu_temperature'] = (55.0, 0.0)
    mgr.thermal_sensors._cache['gpu_temperature'] = (50.0, 0.0)

    tier = mgr.get_placement_tier("llama-7b", preferred=PlacementTier.NPU)
    assert tier == PlacementTier.NPU


@test("get_placement_tier blocks NPU in HOT state")
async def _(mgr=manager):
    # Mock sensors to return HOT temperature
    mgr.thermal_sensors._cache['cpu_temperature'] = (78.0, 0.0)
    mgr.thermal_sensors._cache['gpu_temperature'] = (75.0, 0.0)

    tier = mgr.get_placement_tier("llama-7b", preferred=PlacementTier.NPU)
    assert tier != PlacementTier.NPU
    assert tier in [PlacementTier.GPU, PlacementTier.CPU, PlacementTier.REMOTE]


@test("should_transition_tier detects thermal policy violation")
async def _(mgr=manager):
    # Initial: COOL state, model on NPU
    mgr.thermal_sensors._cache['cpu_temperature'] = (55.0, 0.0)
    mgr.current_placements["llama-7b"] = PlacementTier.NPU

    assert mgr.should_transition_tier("llama-7b") is False

    # Transition to HOT state (NPU not allowed)
    mgr.thermal_sensors._cache['cpu_temperature'] = (78.0, 0.0)

    assert mgr.should_transition_tier("llama-7b") is True


@test("transition_tier executes failover")
async def _(mgr=manager):
    # Initial placement: NPU
    mgr.current_placements["llama-7b"] = PlacementTier.NPU
    mgr.placement_entry_times["llama-7b"] = 0.0

    # Set HOT temperature (NPU not allowed)
    mgr.thermal_sensors._cache['cpu_temperature'] = (78.0, 0.0)
    mgr.thermal_sensors._cache['gpu_temperature'] = (75.0, 0.0)

    # Execute transition
    success = await mgr.transition_tier("llama-7b")

    assert success is True
    assert mgr.get_current_placement("llama-7b") != PlacementTier.NPU


@test("transition_tier records statistics")
async def _(mgr=manager):
    mgr.current_placements["llama-7b"] = PlacementTier.NPU
    mgr.thermal_sensors._cache['cpu_temperature'] = (78.0, 0.0)

    await mgr.transition_tier("llama-7b")

    stats = mgr.get_placement_stats()
    assert stats.total_failovers == 1
    assert stats.last_failover_latency_ms is not None
    assert stats.last_failover_latency_ms < 100.0  # <100ms budget


@test("start_polling initiates background polling")
async def _(mgr=manager):
    await mgr.start_polling()

    assert mgr._polling_active is True
    assert mgr._polling_task is not None

    # Let polling run for a few cycles
    await asyncio.sleep(0.3)

    await mgr.stop_polling()
    assert mgr._polling_active is False


@test("auto_failover triggers on thermal transition")
async def _(mgr=manager):
    # Initial: COOL state, model on NPU
    mgr.thermal_sensors._cache['cpu_temperature'] = (55.0, 0.0)
    mgr.current_placements["llama-7b"] = PlacementTier.NPU

    await mgr.start_polling()

    # Wait for polling to stabilize
    await asyncio.sleep(0.15)

    # Transition to HOT state
    mgr.thermal_sensors._cache['cpu_temperature'] = (78.0, 0.0)

    # Wait for auto-failover
    await asyncio.sleep(0.25)

    # Check failover occurred
    assert mgr.get_current_placement("llama-7b") != PlacementTier.NPU

    await mgr.stop_polling()


@test("emergency state triggers immediate failover to REMOTE")
async def _(mgr=manager):
    mgr.current_placements["llama-7b"] = PlacementTier.NPU
    mgr.thermal_sensors._cache['cpu_temperature'] = (88.0, 0.0)  # CRITICAL

    assert mgr.should_transition_tier("llama-7b") is True

    await mgr.transition_tier("llama-7b")

    # Emergency state should force REMOTE
    mgr.thermal_sensors._cache['cpu_temperature'] = (98.0, 0.0)  # EMERGENCY
    tier = mgr.get_placement_tier("llama-7b")
    assert tier == PlacementTier.REMOTE


@test("get_placement_uptime_ms tracks placement duration")
async def _(mgr=manager):
    mgr.current_placements["llama-7b"] = PlacementTier.NPU
    mgr.placement_entry_times["llama-7b"] = 0.0

    await asyncio.sleep(0.1)

    uptime_ms = mgr.get_placement_uptime_ms("llama-7b")
    assert uptime_ms >= 100.0  # At least 100ms
```

Run tests:
    python -m ward test --path tests/k1/l5_infrastructure/thermal/test_placement_manager.py

Expected performance:
    - Sensor polling: 100ms intervals
    - Placement selection: <50µs
    - Decision latency: <5ms P95
    - Failover latency: <100ms P95
"""
"""
