"""
Thermal-Aware Model Placement Planner

Purpose: Choose optimal accelerator (NPU/GPU/CPU/Remote) based on device thermal state
Location: k1/l5_infrastructure/thermal/placement_planner.py
Performance: <10ms placement decision

Primary ADRs:
- ADR-0026: Thermal Management (hysteresis matrix, 4-tier placement)
- ADR-0026a: Thermal Zones (5 zones: COOL/WARM/HOT/CRITICAL/EMERGENCY)
- ADR-0026b: Hysteresis FSM (state transitions, dead zone, persistence)
- ADR-0026c: Hysteresis Matrix (asymmetric thresholds, cooldown periods)
- ADR-0026d: Throttling (HOT/CRITICAL/EMERGENCY state degradation)
- ADR-0027: Model Placement Cascade (NPU→GPU→CPU→Remote)

Related ADRs:
- ADR-0024: Performance Budgets (placement <10ms)
- ADR-0029: Prometheus Metrics (device temperature, placement decisions)
- ADR-0009: Circuit Breaker (failure detection integration)
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

# Prometheus metrics (optional)
try:
    from prometheus_client import CollectorRegistry, Counter, Histogram

    prometheus_available = True
except ImportError:
    # Create dummy classes to avoid runtime errors
    class DummyMetric:
        def __init__(self, *args, **kwargs):
            pass

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def set(self, *args, **kwargs):
            pass

    class DummyRegistry:
        pass

    Counter = DummyMetric
    Histogram = DummyMetric
    CollectorRegistry = DummyRegistry
    prometheus_available = False

# Import shared types
from .types import ThermalZone


class Accelerator(Enum):
    """Available accelerators in 4-tier cascade."""

    NPU = "npu"
    GPU = "gpu"
    CPU = "cpu"
    REMOTE = "remote"


@dataclass
class AcceleratorProfile:
    """Performance and thermal characteristics of each accelerator."""

    latency_ms: float
    power_watts: float
    thermal_limit_celsius: float
    supported_thermal_zones: List[ThermalZone]
    cost_per_token: float


@dataclass
class PlacementDecision:
    """Result of placement decision."""

    accelerator: Accelerator
    thermal_zone: ThermalZone
    confidence: float
    reasoning: str
    timestamp_ms: int


class HysteresisFSM:
    """
    Thermal hysteresis state machine with asymmetric thresholds and cooldowns.

    Implements ADR-0026b hysteresis FSM with 5°C buffer and state persistence.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Import authoritative thresholds from ADR-0077
        from .types import THERMAL_THRESHOLDS

        # Current state
        self.current_zone: ThermalZone = ThermalZone.COOL
        self.last_transition_time: float = time.time()

        # Cooldown timers
        self.upgrade_cooldown_until: float = 0
        self.downgrade_cooldown_until: float = 0

        # State persistence
        self.state_entry_time: float = time.time()
        self.min_state_duration_seconds: int = 10

        # Hysteresis thresholds (ADR-0077 M3 Epic 2)
        self.upgrade_thresholds = {
            ThermalZone.COOL: THERMAL_THRESHOLDS[
                ThermalZone.COOL
            ],  # COOL → WARM at 70°C
            ThermalZone.WARM: THERMAL_THRESHOLDS[
                ThermalZone.WARM
            ],  # WARM → HOT at 75°C
            ThermalZone.HOT: THERMAL_THRESHOLDS[
                ThermalZone.HOT
            ],  # HOT → CRITICAL at 85°C
            ThermalZone.CRITICAL: THERMAL_THRESHOLDS[
                ThermalZone.CRITICAL
            ],  # CRITICAL → EMERGENCY at 95°C
        }

        self.downgrade_thresholds = {
            ThermalZone.WARM: THERMAL_THRESHOLDS[ThermalZone.COOL]
            - 5,  # WARM → COOL at 65°C (70-5)
            ThermalZone.HOT: THERMAL_THRESHOLDS[ThermalZone.WARM]
            - 0,  # HOT → WARM at 75°C (no hysteresis, matches WARM threshold)
            ThermalZone.CRITICAL: THERMAL_THRESHOLDS[ThermalZone.HOT]
            - 0,  # CRITICAL → HOT at 85°C (no hysteresis)
            ThermalZone.EMERGENCY: THERMAL_THRESHOLDS[ThermalZone.CRITICAL]
            - 5,  # EMERGENCY → CRITICAL at 90°C (95-5)
        }

        # Cooldown durations (ADR-0026b)
        self.upgrade_cooldown_seconds: int = 10
        self.downgrade_cooldown_seconds: Dict[ThermalZone, int] = {
            ThermalZone.WARM: 30,
            ThermalZone.HOT: 60,
            ThermalZone.CRITICAL: 30,
            ThermalZone.EMERGENCY: 10,
        }

    def update_temperature(self, temperature_celsius: float) -> Optional[ThermalZone]:
        """
        Update FSM with new temperature reading.

        Returns new thermal zone if state changed, None otherwise.
        """
        current_time = time.time()

        # Check minimum state duration
        if (current_time - self.state_entry_time) < self.min_state_duration_seconds:
            return None

        # Check cooldown timers
        if (
            current_time < self.upgrade_cooldown_until
            or current_time < self.downgrade_cooldown_until
        ):
            return None

        # Determine if upgrade or downgrade is possible
        new_zone = self._calculate_target_zone(temperature_celsius)

        if new_zone != self.current_zone:
            # Validate transition
            if self._can_transition(self.current_zone, new_zone, temperature_celsius):
                old_zone = self.current_zone
                self.current_zone = new_zone
                self.last_transition_time = current_time
                self.state_entry_time = current_time

                # Set cooldown timer
                if new_zone.value > old_zone.value:  # Upgrade
                    self.upgrade_cooldown_until = (
                        current_time + self.upgrade_cooldown_seconds
                    )
                else:  # Downgrade
                    cooldown_duration = self.downgrade_cooldown_seconds.get(
                        new_zone, 30
                    )
                    self.downgrade_cooldown_until = current_time + cooldown_duration

                self.logger.info(
                    f"Thermal zone transition: {old_zone.name} → {new_zone.name} "
                    f"(temp: {temperature_celsius:.1f}°C)"
                )
                return new_zone

        return None

    def _calculate_target_zone(self, temperature_celsius: float) -> ThermalZone:
        """Calculate target zone based on temperature and hysteresis (ADR-0077)."""
        from .types import THERMAL_THRESHOLDS

        # Emergency override (no hysteresis)
        if temperature_celsius >= THERMAL_THRESHOLDS[ThermalZone.CRITICAL]:
            return ThermalZone.EMERGENCY
        elif temperature_celsius >= THERMAL_THRESHOLDS[ThermalZone.HOT]:
            return ThermalZone.CRITICAL
        elif temperature_celsius >= THERMAL_THRESHOLDS[ThermalZone.WARM]:
            return ThermalZone.HOT
        elif temperature_celsius >= THERMAL_THRESHOLDS[ThermalZone.COOL]:
            return ThermalZone.WARM
        else:
            return ThermalZone.COOL

    def _can_transition(
        self, from_zone: ThermalZone, to_zone: ThermalZone, temperature_celsius: float
    ) -> bool:
        """Check if transition is allowed based on hysteresis thresholds."""
        if from_zone == to_zone:
            return False

        # Emergency transitions bypass hysteresis
        if to_zone == ThermalZone.EMERGENCY:
            return temperature_celsius >= self.upgrade_thresholds[ThermalZone.CRITICAL]

        # Upgrade transitions (immediate)
        if to_zone.value > from_zone.value:
            threshold = self.upgrade_thresholds.get(from_zone)
            return threshold is not None and temperature_celsius >= threshold

        # Downgrade transitions (with hysteresis)
        else:
            threshold = self.downgrade_thresholds.get(to_zone)
            return threshold is not None and temperature_celsius <= threshold

    def force_emergency_jump(self) -> bool:
        """Force immediate transition to EMERGENCY zone (bypasses all timers)."""
        if self.current_zone != ThermalZone.EMERGENCY:
            self.current_zone = ThermalZone.EMERGENCY
            self.last_transition_time = time.time()
            self.state_entry_time = time.time()
            # Clear cooldowns for emergency
            self.upgrade_cooldown_until = 0
            self.downgrade_cooldown_until = 0
            self.logger.warning("Emergency thermal jump activated")
            return True
        return False

    def get_current_zone(self) -> ThermalZone:
        """Get current thermal zone."""
        return self.current_zone

    def get_state_info(self) -> Dict[str, Any]:
        """Get detailed state information for debugging."""
        current_time = time.time()
        return {
            "current_zone": self.current_zone.name,
            "state_duration_seconds": current_time - self.state_entry_time,
            "upgrade_cooldown_remaining": max(
                0, self.upgrade_cooldown_until - current_time
            ),
            "downgrade_cooldown_remaining": max(
                0, self.downgrade_cooldown_until - current_time
            ),
            "last_transition_seconds_ago": current_time - self.last_transition_time,
        }


class PlacementPlanner:
    """
    Thermal-aware model placement planner with hysteresis FSM.

    Implements ADR-0026c 4-tier placement cascade with thermal constraints.
    """

    def __init__(self, thermal_monitor: Optional[Any] = None):
        self.logger = logging.getLogger(__name__)
        self.thermal_monitor = thermal_monitor

        # Hysteresis FSM
        self.hysteresis_fsm = HysteresisFSM()

        # Accelerator profiles (ADR-0026c, ADR-0027, relaxed for gaming)
        self.accelerator_profiles = {
            Accelerator.NPU: AcceleratorProfile(
                latency_ms=30,
                power_watts=10,
                thermal_limit_celsius=80,  # Relaxed from 75°C
                supported_thermal_zones=[ThermalZone.COOL, ThermalZone.WARM],
                cost_per_token=0.0001,
            ),
            Accelerator.GPU: AcceleratorProfile(
                latency_ms=50,
                power_watts=12,
                thermal_limit_celsius=95,  # Relaxed from 85°C
                supported_thermal_zones=[
                    ThermalZone.COOL,
                    ThermalZone.WARM,
                    ThermalZone.HOT,
                ],
                cost_per_token=0.0002,
            ),
            Accelerator.CPU: AcceleratorProfile(
                latency_ms=120,
                power_watts=15,
                thermal_limit_celsius=105,  # Relaxed from 95°C
                supported_thermal_zones=[
                    ThermalZone.COOL,
                    ThermalZone.WARM,
                    ThermalZone.HOT,
                    ThermalZone.CRITICAL,
                ],
                cost_per_token=0.0005,
            ),
            Accelerator.REMOTE: AcceleratorProfile(
                latency_ms=500,
                power_watts=5,
                thermal_limit_celsius=110,  # Relaxed from 100°C
                supported_thermal_zones=[
                    ThermalZone.COOL,
                    ThermalZone.WARM,
                    ThermalZone.HOT,
                    ThermalZone.CRITICAL,
                    ThermalZone.EMERGENCY,
                ],
                cost_per_token=0.002,
            ),
        }

        # Prometheus metrics
        if prometheus_available:
            self._setup_prometheus_metrics()

        # State tracking
        self.last_placement_decision: Optional[PlacementDecision] = None

    def _setup_prometheus_metrics(self):
        """Initialize Prometheus metrics."""
        if not prometheus_available:
            return

        # Use custom registry to avoid conflicts in tests
        self._prometheus_registry = CollectorRegistry()

        self.placement_decisions_total = Counter(
            "thermal_placement_decisions_total",
            "Total placement decisions by accelerator and thermal zone",
            ["accelerator", "thermal_zone"],
            registry=self._prometheus_registry,
        )
        self.placement_latency_ms = Histogram(
            "thermal_placement_latency_ms",
            "Placement decision latency",
            buckets=[1, 5, 10, 25, 50, 100],
            registry=self._prometheus_registry,
        )
        self.emergency_jumps_total = Counter(
            "thermal_emergency_jumps_total",
            "Total emergency placement jumps to remote",
            registry=self._prometheus_registry,
        )

    def choose_accelerator(
        self, model_requirements: Optional[Dict[str, Any]] = None
    ) -> PlacementDecision:
        """
        Choose optimal accelerator based on current thermal state.

        Args:
            model_requirements: Optional model requirements (quantization, memory, etc.)

        Returns:
            PlacementDecision with chosen accelerator and reasoning
        """
        start_time = time.time()

        # Get current thermal zone from hysteresis FSM (not monitor)
        if self.thermal_monitor:
            current_temp = self.thermal_monitor.get_temperature("MAX")
            if current_temp is not None:
                # Update hysteresis FSM with current temperature
                new_zone = self.hysteresis_fsm.update_temperature(current_temp)
                if new_zone:
                    self.logger.info(f"Thermal zone updated to {new_zone.name}")

        # Use hysteresis FSM zone for stable placement decisions
        thermal_zone = self.hysteresis_fsm.get_current_zone()

        # Emergency jump check (ADR-0026c)
        if thermal_zone in [ThermalZone.CRITICAL, ThermalZone.EMERGENCY]:
            if self._should_emergency_jump(thermal_zone):
                self.hysteresis_fsm.force_emergency_jump()
                thermal_zone = ThermalZone.EMERGENCY
                if prometheus_available:
                    self.emergency_jumps_total.inc()

        # 4-tier cascade selection (ADR-0026c)
        chosen_accelerator = self._select_accelerator_cascade(
            thermal_zone, model_requirements
        )

        # Create decision
        decision = PlacementDecision(
            accelerator=chosen_accelerator,
            thermal_zone=thermal_zone,
            confidence=1.0,  # Deterministic selection
            reasoning=self._get_placement_reasoning(chosen_accelerator, thermal_zone),
            timestamp_ms=int(time.time() * 1000),
        )

        # Update metrics
        if prometheus_available:
            self.placement_decisions_total.labels(
                accelerator=chosen_accelerator.value, thermal_zone=thermal_zone.name
            ).inc()
            self.placement_latency_ms.observe((time.time() - start_time) * 1000)

        self.last_placement_decision = decision
        return decision

    def _should_emergency_jump(self, thermal_zone: ThermalZone) -> bool:
        """Check if emergency jump to Remote is needed."""
        return thermal_zone in [ThermalZone.CRITICAL, ThermalZone.EMERGENCY]

    def _select_accelerator_cascade(
        self, thermal_zone: ThermalZone, model_requirements: Optional[Dict[str, Any]]
    ) -> Accelerator:
        """
        Select accelerator using 4-tier cascade based on thermal zone.

        Cascade order: NPU → GPU → CPU → Remote
        """
        # Define cascade order by thermal zone (relaxed for gaming)
        cascade_by_zone = {
            ThermalZone.COOL: [
                Accelerator.NPU,
                Accelerator.GPU,
                Accelerator.CPU,
                Accelerator.REMOTE,
            ],
            ThermalZone.WARM: [
                Accelerator.NPU,
                Accelerator.GPU,
                Accelerator.CPU,
                Accelerator.REMOTE,
            ],
            ThermalZone.HOT: [Accelerator.GPU, Accelerator.CPU, Accelerator.REMOTE],
            ThermalZone.CRITICAL: [Accelerator.CPU, Accelerator.REMOTE],
            ThermalZone.EMERGENCY: [Accelerator.REMOTE],
        }

        cascade = cascade_by_zone.get(thermal_zone, [Accelerator.REMOTE])

        # Return first available accelerator in cascade
        for accelerator in cascade:
            profile = self.accelerator_profiles[accelerator]
            if thermal_zone in profile.supported_thermal_zones:
                return accelerator

        # Fallback to Remote
        return Accelerator.REMOTE

    def _get_placement_reasoning(
        self, accelerator: Accelerator, thermal_zone: ThermalZone
    ) -> str:
        """Generate human-readable reasoning for placement decision."""
        profile = self.accelerator_profiles[accelerator]

        if thermal_zone == ThermalZone.EMERGENCY:
            return f"Emergency: Forced Remote placement due to {thermal_zone.name} thermal state"
        elif thermal_zone == ThermalZone.CRITICAL:
            return f"Critical: CPU/Remote only in {thermal_zone.name} state ({profile.latency_ms}ms latency)"
        else:
            return (
                f"Optimal: {accelerator.value.upper()} selected for {thermal_zone.name} state "
                f"({profile.latency_ms}ms latency, {profile.power_watts}W power)"
            )

    def should_migrate(self, current_accelerator: Accelerator) -> bool:
        """
        Check if current placement should migrate due to thermal state change.

        Returns True if migration is recommended.
        """
        if not self.last_placement_decision:
            return False

        # Get current optimal placement
        current_optimal = self.choose_accelerator()

        # Check if different from current
        should_migrate = current_optimal.accelerator != current_accelerator

        if should_migrate:
            self.logger.info(
                f"Migration recommended: {current_accelerator.value} → "
                f"{current_optimal.accelerator.value} "
                f"(thermal zone: {current_optimal.thermal_zone.name})"
            )

        return should_migrate

    def get_thermal_zone(self) -> ThermalZone:
        """Get current thermal zone from hysteresis FSM."""
        return self.hysteresis_fsm.get_current_zone()

    def get_hysteresis_state_info(self) -> Dict[str, Any]:
        """Get detailed hysteresis FSM state for debugging."""
        return self.hysteresis_fsm.get_state_info()

    def force_emergency_jump(self) -> bool:
        """Force emergency jump to Remote accelerator."""
        return self.hysteresis_fsm.force_emergency_jump()
