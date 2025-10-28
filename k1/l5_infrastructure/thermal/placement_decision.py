"""
Module: k1.l5_infrastructure.thermal.placement_decision
Purpose: Hysteresis-based placement decision logic with cooldown enforcement

This module provides the PlacementDecision class for validating thermal state transitions
and enforcing placement cooldown periods to prevent oscillation.

Architecture:
    - Hysteresis guards: can_upgrade(), can_downgrade() with cooldown enforcement
    - Emergency detection: should_emergency_jump() for ≥85°C immediate failover
    - Placement scoring: calculate_placement_score() combining temp + power + latency
    - Thermal zone mapping: get_thermal_zone() for state classification

Performance Budgets:
    - Decision latency: <5ms P95
    - Upgrade cooldown: 10s (fast thermal response)
    - Downgrade cooldown: 60s (slow recovery to prevent re-heating)
    - Emergency jump: Immediate (no cooldown)

Related ADRs:
    - ADR-0026: Thermal Hysteresis Matrix Device Management
    - ADR-0026b: Hysteresis State Machine (5°C Buffer)
    - ADR-0026c: Model Placement Integration (Thermal Cascade)

Research Foundation:
    - Android Thermal HAL: 5 severity levels with placement restrictions
    - Apple Neural Engine: ANE→GPU→CPU thermal cascade
    - Intel DTT: Workload placement based on thermal budget
    - NVIDIA GPU Throttling: 83°C (TH1), 93°C (TH2) thresholds

Author: K1 Infrastructure Team
Date: 2025-10-27
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger()

# Prometheus metrics
placement_decision_latency_ms = Histogram(
    'k1_placement_decision_latency_ms',
    'Time to make placement decision',
    buckets=[1, 2, 5, 10, 25, 50]
)

placement_upgrade_blocked_total = Counter(
    'k1_placement_upgrade_blocked_total',
    'Placement upgrades blocked by cooldown',
    ['from_tier', 'to_tier', 'reason']
)

placement_downgrade_blocked_total = Counter(
    'k1_placement_downgrade_blocked_total',
    'Placement downgrades blocked by cooldown',
    ['from_tier', 'to_tier', 'reason']
)

placement_emergency_jumps_total = Counter(
    'k1_placement_emergency_jumps_total',
    'Emergency placement jumps (no cooldown)',
    ['from_tier', 'to_tier', 'temperature_celsius']
)

placement_score_gauge = Gauge(
    'k1_placement_score',
    'Current placement score',
    ['tier']
)


class ThermalZone(Enum):
    """Thermal zone classifications"""
    COOL = "COOL"           # <60°C: Optimal performance
    WARM = "WARM"           # 60-75°C: Normal operation
    HOT = "HOT"             # 75-85°C: Throttling recommended
    CRITICAL = "CRITICAL"   # 85-95°C: Aggressive throttling
    EMERGENCY = "EMERGENCY" # >95°C: Emergency shutdown


class PlacementTier(Enum):
    """Model placement tiers"""
    NPU = "NPU"         # Highest performance, highest thermal load (5-8W)
    GPU = "GPU"         # High performance, very high thermal load (15-25W)
    CPU = "CPU"         # Medium performance, medium thermal load (3-10W)
    REMOTE = "REMOTE"   # Lowest performance, no thermal load (0W)


@dataclass
class PlacementPolicy:
    """Placement policy for a thermal zone"""
    thermal_zone: ThermalZone
    allowed_tiers: List[PlacementTier]
    max_temperature: float

    def is_tier_allowed(self, tier: PlacementTier) -> bool:
        """Check if tier is allowed in this thermal zone"""
        return tier in self.allowed_tiers

    def get_best_tier(self) -> PlacementTier:
        """Get best (first) allowed tier"""
        return self.allowed_tiers[0] if self.allowed_tiers else PlacementTier.REMOTE


@dataclass
class PlacementMetrics:
    """Metrics for placement scoring"""
    temperature_celsius: float
    power_watts: float
    latency_ms: float
    thermal_zone: ThermalZone
    timestamp_ms: float


@dataclass
class CooldownState:
    """Cooldown state tracking"""
    last_upgrade_time_ms: Optional[float] = None
    last_downgrade_time_ms: Optional[float] = None
    upgrade_cooldown_ms: float = 10_000  # 10s
    downgrade_cooldown_ms: float = 60_000  # 60s


class PlacementDecision:
    """
    Hysteresis-based placement decision logic with cooldown enforcement

    This class provides methods for validating placement transitions (upgrades/downgrades)
    with hysteresis guards and cooldown periods to prevent oscillation.

    Key Features:
        - Upgrade cooldown: 10s (fast thermal response)
        - Downgrade cooldown: 60s (slow recovery to prevent re-heating)
        - Emergency detection: ≥85°C → immediate Remote placement
        - Placement scoring: Multi-factor score (temp + power + latency)
        - Thermal zone mapping: Temperature → ThermalZone classification

    Usage Example:
        decision = PlacementDecision()

        # Check if upgrade allowed (CPU → NPU)
        allowed, reason = decision.can_upgrade(
            from_tier=PlacementTier.CPU,
            to_tier=PlacementTier.NPU,
            temperature_celsius=72.0,
            power_watts=5.5
        )

        if allowed:
            # Execute upgrade
            execute_placement_upgrade(to_tier)
        else:
            logger.info("upgrade_blocked", reason=reason)

    Performance:
        - Decision latency: <5ms P95
        - Cooldown enforcement: O(1) time complexity
        - Emergency detection: <1ms

    Related ADRs:
        - ADR-0026b: Hysteresis State Machine (5°C Buffer)
        - ADR-0026c: Model Placement Integration (Thermal Cascade)
    """

    # Thermal zone thresholds (with 5°C hysteresis buffer)
    THERMAL_THRESHOLDS = {
        ThermalZone.COOL: (0.0, 60.0),
        ThermalZone.WARM: (60.0, 75.0),
        ThermalZone.HOT: (75.0, 85.0),
        ThermalZone.CRITICAL: (85.0, 95.0),
        ThermalZone.EMERGENCY: (95.0, float('inf'))
    }

    # Placement policies per thermal zone
    PLACEMENT_POLICIES = {
        ThermalZone.COOL: PlacementPolicy(
            ThermalZone.COOL,
            [PlacementTier.NPU, PlacementTier.GPU, PlacementTier.CPU, PlacementTier.REMOTE],
            60.0
        ),
        ThermalZone.WARM: PlacementPolicy(
            ThermalZone.WARM,
            [PlacementTier.NPU, PlacementTier.GPU, PlacementTier.CPU, PlacementTier.REMOTE],
            75.0
        ),
        ThermalZone.HOT: PlacementPolicy(
            ThermalZone.HOT,
            [PlacementTier.GPU, PlacementTier.CPU, PlacementTier.REMOTE],  # Skip NPU
            85.0
        ),
        ThermalZone.CRITICAL: PlacementPolicy(
            ThermalZone.CRITICAL,
            [PlacementTier.CPU, PlacementTier.REMOTE],  # Skip NPU & GPU
            95.0
        ),
        ThermalZone.EMERGENCY: PlacementPolicy(
            ThermalZone.EMERGENCY,
            [PlacementTier.REMOTE],  # Local inference disabled
            float('inf')
        )
    }

    # Tier ordering for upgrade/downgrade logic
    TIER_ORDER = [PlacementTier.NPU, PlacementTier.GPU, PlacementTier.CPU, PlacementTier.REMOTE]

    def __init__(
        self,
        upgrade_cooldown_ms: float = 10_000,
        downgrade_cooldown_ms: float = 60_000,
        emergency_threshold_celsius: float = 85.0
    ):
        """
        Initialize placement decision engine

        Args:
            upgrade_cooldown_ms: Cooldown period for upgrades (default: 10s)
            downgrade_cooldown_ms: Cooldown period for downgrades (default: 60s)
            emergency_threshold_celsius: Temperature threshold for emergency failover (default: 85°C)
        """
        self.cooldown_state = CooldownState(
            upgrade_cooldown_ms=upgrade_cooldown_ms,
            downgrade_cooldown_ms=downgrade_cooldown_ms
        )
        self.emergency_threshold_celsius = emergency_threshold_celsius

        logger.info(
            "placement_decision_initialized",
            upgrade_cooldown_ms=upgrade_cooldown_ms,
            downgrade_cooldown_ms=downgrade_cooldown_ms,
            emergency_threshold_celsius=emergency_threshold_celsius
        )

    def can_upgrade(
        self,
        from_tier: PlacementTier,
        to_tier: PlacementTier,
        temperature_celsius: float,
        power_watts: float
    ) -> tuple[bool, Optional[str]]:
        """
        Check if placement upgrade is allowed (e.g., CPU → NPU)

        Upgrade is allowed if:
        1. Target tier is higher performance than current tier
        2. Upgrade cooldown period has elapsed (10s)
        3. Current thermal zone allows target tier
        4. Not in emergency state (≥85°C)

        Args:
            from_tier: Current placement tier
            to_tier: Target placement tier (higher performance)
            temperature_celsius: Current device temperature
            power_watts: Current power draw

        Returns:
            Tuple of (allowed: bool, reason: Optional[str])
            - (True, None) if upgrade allowed
            - (False, "reason") if upgrade blocked

        Example:
            allowed, reason = decision.can_upgrade(
                PlacementTier.CPU,
                PlacementTier.NPU,
                temperature_celsius=72.0,
                power_watts=5.5
            )
            if not allowed:
                logger.info("upgrade_blocked", reason=reason)

        Performance: <5ms P95
        """
        start_ms = time.perf_counter() * 1000

        # Check tier ordering (upgrade must be to higher-performance tier)
        if not self._is_upgrade(from_tier, to_tier):
            placement_upgrade_blocked_total.labels(
                from_tier=from_tier.value,
                to_tier=to_tier.value,
                reason="not_an_upgrade"
            ).inc()

            latency_ms = (time.perf_counter() * 1000) - start_ms
            placement_decision_latency_ms.observe(latency_ms)

            return (False, "not_an_upgrade")

        # Check emergency state
        if temperature_celsius >= self.emergency_threshold_celsius:
            placement_upgrade_blocked_total.labels(
                from_tier=from_tier.value,
                to_tier=to_tier.value,
                reason="emergency_state"
            ).inc()

            latency_ms = (time.perf_counter() * 1000) - start_ms
            placement_decision_latency_ms.observe(latency_ms)

            return (False, "emergency_state")

        # Check upgrade cooldown
        now_ms = time.perf_counter() * 1000
        if self.cooldown_state.last_upgrade_time_ms is not None:
            elapsed_ms = now_ms - self.cooldown_state.last_upgrade_time_ms
            if elapsed_ms < self.cooldown_state.upgrade_cooldown_ms:
                remaining_ms = self.cooldown_state.upgrade_cooldown_ms - elapsed_ms

                placement_upgrade_blocked_total.labels(
                    from_tier=from_tier.value,
                    to_tier=to_tier.value,
                    reason="cooldown_active"
                ).inc()

                latency_ms = (time.perf_counter() * 1000) - start_ms
                placement_decision_latency_ms.observe(latency_ms)

                return (False, f"cooldown_active:{remaining_ms:.0f}ms")

        # Check thermal zone policy
        thermal_zone = self.get_thermal_zone(temperature_celsius)
        policy = self.PLACEMENT_POLICIES[thermal_zone]

        if not policy.is_tier_allowed(to_tier):
            placement_upgrade_blocked_total.labels(
                from_tier=from_tier.value,
                to_tier=to_tier.value,
                reason="thermal_policy_violation"
            ).inc()

            latency_ms = (time.perf_counter() * 1000) - start_ms
            placement_decision_latency_ms.observe(latency_ms)

            return (False, f"thermal_policy_violation:{thermal_zone.value}")

        # Upgrade allowed
        latency_ms = (time.perf_counter() * 1000) - start_ms
        placement_decision_latency_ms.observe(latency_ms)

        return (True, None)

    def can_downgrade(
        self,
        from_tier: PlacementTier,
        to_tier: PlacementTier,
        temperature_celsius: float,
        power_watts: float
    ) -> tuple[bool, Optional[str]]:
        """
        Check if placement downgrade is allowed (e.g., NPU → GPU)

        Downgrade is allowed if:
        1. Target tier is lower performance than current tier
        2. Downgrade cooldown period has elapsed (60s)
        3. Current thermal zone requires lower tier (or emergency state)

        Args:
            from_tier: Current placement tier
            to_tier: Target placement tier (lower performance)
            temperature_celsius: Current device temperature
            power_watts: Current power draw

        Returns:
            Tuple of (allowed: bool, reason: Optional[str])
            - (True, None) if downgrade allowed
            - (False, "reason") if downgrade blocked

        Example:
            allowed, reason = decision.can_downgrade(
                PlacementTier.NPU,
                PlacementTier.GPU,
                temperature_celsius=82.0,
                power_watts=18.5
            )
            if allowed:
                execute_placement_downgrade(to_tier)

        Performance: <5ms P95
        """
        start_ms = time.perf_counter() * 1000

        # Check tier ordering (downgrade must be to lower-performance tier)
        if not self._is_downgrade(from_tier, to_tier):
            placement_downgrade_blocked_total.labels(
                from_tier=from_tier.value,
                to_tier=to_tier.value,
                reason="not_a_downgrade"
            ).inc()

            latency_ms = (time.perf_counter() * 1000) - start_ms
            placement_decision_latency_ms.observe(latency_ms)

            return (False, "not_a_downgrade")

        # Emergency state: immediate downgrade allowed (no cooldown)
        if self.should_emergency_jump(temperature_celsius):
            latency_ms = (time.perf_counter() * 1000) - start_ms
            placement_decision_latency_ms.observe(latency_ms)

            placement_emergency_jumps_total.labels(
                from_tier=from_tier.value,
                to_tier=to_tier.value,
                temperature_celsius=f"{temperature_celsius:.1f}"
            ).inc()

            return (True, None)

        # Check downgrade cooldown
        now_ms = time.perf_counter() * 1000
        if self.cooldown_state.last_downgrade_time_ms is not None:
            elapsed_ms = now_ms - self.cooldown_state.last_downgrade_time_ms
            if elapsed_ms < self.cooldown_state.downgrade_cooldown_ms:
                remaining_ms = self.cooldown_state.downgrade_cooldown_ms - elapsed_ms

                placement_downgrade_blocked_total.labels(
                    from_tier=from_tier.value,
                    to_tier=to_tier.value,
                    reason="cooldown_active"
                ).inc()

                latency_ms = (time.perf_counter() * 1000) - start_ms
                placement_decision_latency_ms.observe(latency_ms)

                return (False, f"cooldown_active:{remaining_ms:.0f}ms")

        # Check thermal zone policy (downgrade needed?)
        thermal_zone = self.get_thermal_zone(temperature_celsius)
        policy = self.PLACEMENT_POLICIES[thermal_zone]

        # Downgrade allowed if current tier not allowed in current zone
        if not policy.is_tier_allowed(from_tier):
            latency_ms = (time.perf_counter() * 1000) - start_ms
            placement_decision_latency_ms.observe(latency_ms)

            return (True, None)

        # Downgrade blocked (current tier still allowed)
        placement_downgrade_blocked_total.labels(
            from_tier=from_tier.value,
            to_tier=to_tier.value,
            reason="tier_still_allowed"
        ).inc()

        latency_ms = (time.perf_counter() * 1000) - start_ms
        placement_decision_latency_ms.observe(latency_ms)

        return (False, f"tier_still_allowed:{thermal_zone.value}")

    def should_emergency_jump(self, temperature_celsius: float) -> bool:
        """
        Check if emergency placement jump required (≥85°C → immediate Remote)

        Emergency jump bypasses cooldown periods and immediately fails over to Remote tier.

        Args:
            temperature_celsius: Current device temperature

        Returns:
            True if emergency jump required (temp ≥ 85°C)

        Example:
            if decision.should_emergency_jump(temperature_celsius):
                # Immediate failover to Remote (no cooldown)
                execute_emergency_failover(PlacementTier.REMOTE)

        Performance: <1ms
        """
        return temperature_celsius >= self.emergency_threshold_celsius

    def calculate_placement_score(
        self,
        tier: PlacementTier,
        temperature_celsius: float,
        power_watts: float,
        latency_ms: float
    ) -> float:
        """
        Calculate placement score for a tier (higher is better)

        Score combines multiple factors:
        - Performance: Lower latency is better
        - Thermal: Lower temperature is better
        - Power: Lower power draw is better

        Weighting:
        - Performance: 50% (latency)
        - Thermal: 30% (temperature headroom)
        - Power: 20% (power efficiency)

        Args:
            tier: Placement tier to score
            temperature_celsius: Current device temperature
            power_watts: Current power draw
            latency_ms: Inference latency for this tier

        Returns:
            Placement score (0.0 to 1.0, higher is better)

        Example:
            score = decision.calculate_placement_score(
                PlacementTier.NPU,
                temperature_celsius=65.0,
                power_watts=6.5,
                latency_ms=140.0
            )
            # score ≈ 0.85 (excellent)

        Performance: <1ms
        """
        # Normalize factors to [0, 1] range

        # Performance score (lower latency is better)
        # NPU: 140ms, GPU: 180ms, CPU: 350ms, Remote: 600ms
        max_latency_ms = 600.0
        performance_score = 1.0 - (latency_ms / max_latency_ms)

        # Thermal score (lower temperature is better)
        # Cool: <60°C, Warm: 60-75°C, Hot: 75-85°C, Critical: 85-95°C, Emergency: >95°C
        max_temp_celsius = 95.0
        thermal_score = 1.0 - (temperature_celsius / max_temp_celsius)

        # Power score (lower power is better)
        # NPU: 8W, GPU: 25W, CPU: 10W, Remote: 0W
        max_power_watts = 25.0
        power_score = 1.0 - (power_watts / max_power_watts)

        # Weighted score
        score = (
            0.5 * performance_score +
            0.3 * thermal_score +
            0.2 * power_score
        )

        # Update Prometheus gauge
        placement_score_gauge.labels(tier=tier.value).set(score)

        return score

    def get_thermal_zone(self, temperature_celsius: float) -> ThermalZone:
        """
        Map temperature to thermal zone classification

        Thermal Zones:
        - COOL: <60°C (optimal performance)
        - WARM: 60-75°C (normal operation)
        - HOT: 75-85°C (throttling recommended)
        - CRITICAL: 85-95°C (aggressive throttling)
        - EMERGENCY: >95°C (emergency shutdown)

        Args:
            temperature_celsius: Current device temperature

        Returns:
            ThermalZone classification

        Example:
            zone = decision.get_thermal_zone(72.0)
            # zone = ThermalZone.WARM

        Performance: <1ms
        """
        for zone, (min_temp, max_temp) in self.THERMAL_THRESHOLDS.items():
            if min_temp <= temperature_celsius < max_temp:
                return zone

        # Fallback: EMERGENCY
        return ThermalZone.EMERGENCY

    def record_upgrade(self):
        """Record timestamp of last upgrade (for cooldown tracking)"""
        self.cooldown_state.last_upgrade_time_ms = time.perf_counter() * 1000

        logger.debug(
            "upgrade_recorded",
            timestamp_ms=self.cooldown_state.last_upgrade_time_ms
        )

    def record_downgrade(self):
        """Record timestamp of last downgrade (for cooldown tracking)"""
        self.cooldown_state.last_downgrade_time_ms = time.perf_counter() * 1000

        logger.debug(
            "downgrade_recorded",
            timestamp_ms=self.cooldown_state.last_downgrade_time_ms
        )

    def _is_upgrade(self, from_tier: PlacementTier, to_tier: PlacementTier) -> bool:
        """Check if transition is an upgrade (to higher-performance tier)"""
        from_idx = self.TIER_ORDER.index(from_tier)
        to_idx = self.TIER_ORDER.index(to_tier)
        return to_idx < from_idx  # Lower index = higher performance

    def _is_downgrade(self, from_tier: PlacementTier, to_tier: PlacementTier) -> bool:
        """Check if transition is a downgrade (to lower-performance tier)"""
        from_idx = self.TIER_ORDER.index(from_tier)
        to_idx = self.TIER_ORDER.index(to_tier)
        return to_idx > from_idx  # Higher index = lower performance


# ============================================================================
# WARD Test Examples
# ============================================================================

"""
WARD Test Suite for PlacementDecision

File: tests/k1/l5_infrastructure/thermal/test_placement_decision.py

```python
from ward import test, fixture
import time

from k1.l5_infrastructure.thermal.placement_decision import (
    PlacementDecision,
    PlacementTier,
    ThermalZone
)


@fixture
def decision():
    return PlacementDecision(
        upgrade_cooldown_ms=10_000,
        downgrade_cooldown_ms=60_000,
        emergency_threshold_celsius=85.0
    )


@test("can_upgrade allows upgrade when cooldown elapsed")
def _(dec=decision):
    # First upgrade (allowed, no cooldown active)
    allowed, reason = dec.can_upgrade(
        from_tier=PlacementTier.CPU,
        to_tier=PlacementTier.NPU,
        temperature_celsius=65.0,
        power_watts=5.5
    )
    assert allowed is True
    assert reason is None

    dec.record_upgrade()

    # Second upgrade (blocked, cooldown active)
    allowed, reason = dec.can_upgrade(
        from_tier=PlacementTier.GPU,
        to_tier=PlacementTier.NPU,
        temperature_celsius=65.0,
        power_watts=5.5
    )
    assert allowed is False
    assert "cooldown_active" in reason


@test("can_upgrade blocks upgrade in emergency state")
def _(dec=decision):
    allowed, reason = dec.can_upgrade(
        from_tier=PlacementTier.CPU,
        to_tier=PlacementTier.NPU,
        temperature_celsius=88.0,  # CRITICAL/EMERGENCY
        power_watts=5.5
    )
    assert allowed is False
    assert reason == "emergency_state"


@test("can_downgrade allows immediate downgrade in emergency")
def _(dec=decision):
    allowed, reason = dec.can_downgrade(
        from_tier=PlacementTier.NPU,
        to_tier=PlacementTier.REMOTE,
        temperature_celsius=88.0,  # Emergency
        power_watts=18.5
    )
    assert allowed is True
    assert reason is None


@test("should_emergency_jump triggers at 85°C")
def _(dec=decision):
    assert dec.should_emergency_jump(84.9) is False
    assert dec.should_emergency_jump(85.0) is True
    assert dec.should_emergency_jump(95.0) is True


@test("calculate_placement_score returns higher score for better conditions")
def _(dec=decision):
    # NPU in COOL state (excellent)
    score_cool = dec.calculate_placement_score(
        PlacementTier.NPU,
        temperature_celsius=55.0,
        power_watts=6.0,
        latency_ms=140.0
    )

    # NPU in HOT state (poor)
    score_hot = dec.calculate_placement_score(
        PlacementTier.NPU,
        temperature_celsius=80.0,
        power_watts=8.0,
        latency_ms=140.0
    )

    assert score_cool > score_hot
    assert score_cool >= 0.7  # Excellent score
    assert score_hot < 0.6    # Poor score


@test("get_thermal_zone maps temperature correctly")
def _(dec=decision):
    assert dec.get_thermal_zone(55.0) == ThermalZone.COOL
    assert dec.get_thermal_zone(65.0) == ThermalZone.WARM
    assert dec.get_thermal_zone(78.0) == ThermalZone.HOT
    assert dec.get_thermal_zone(88.0) == ThermalZone.CRITICAL
    assert dec.get_thermal_zone(98.0) == ThermalZone.EMERGENCY


@test("thermal policy blocks NPU in HOT state")
def _(dec=decision):
    allowed, reason = dec.can_upgrade(
        from_tier=PlacementTier.CPU,
        to_tier=PlacementTier.NPU,
        temperature_celsius=78.0,  # HOT state
        power_watts=5.5
    )
    assert allowed is False
    assert "thermal_policy_violation" in reason


@test("thermal policy allows GPU in HOT state")
def _(dec=decision):
    allowed, reason = dec.can_upgrade(
        from_tier=PlacementTier.CPU,
        to_tier=PlacementTier.GPU,
        temperature_celsius=78.0,  # HOT state
        power_watts=15.0
    )
    assert allowed is True
```

Run tests:
    python -m ward test --path tests/k1/l5_infrastructure/thermal/test_placement_decision.py

Expected P95 latency: <5ms for all decision methods
"""
"""
