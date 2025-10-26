"""
Layer 5 - Thermal Management Module

This module provides thermal-aware model placement and device temperature monitoring
for K1's 4-tier inference cascade (NPU→GPU→CPU→Remote).

Components:
- placement_planner: Thermal-aware model placement with hysteresis FSM
- monitor: Device temperature monitoring (NPU/GPU/CPU sensors)

Thermal Zones (ADR-0026a):
- COOL (<70°C): All accelerators available
- WARM (70-74°C): All accelerators available
- HOT (75-84°C): NPU disabled, GPU/CPU/Remote available
- CRITICAL (85-95°C): NPU/GPU disabled, CPU/Remote available
- EMERGENCY (>95°C): All local disabled, Remote only

Hysteresis (ADR-0026b, ADR-0026c):
- Asymmetric thresholds: +5°C upgrade, -2°C downgrade (7°C band)
- Cooldown periods: 10s upgrade, 30-60s downgrade (3:1 to 6:1 ratio)
- Dead zone: Temperatures within zone maintain current state
- Emergency jump: CRITICAL → Remote (immediate, skip GPU/CPU)

4-Tier Placement Cascade (ADR-0027):
- NPU (30ms, 10W): Optimal on-device inference
- GPU (50ms, 12W): Fallback for NPU overload
- CPU (120ms, 15W): Fallback for GPU overload
- Remote (500ms, 5W): Cloud inference (last resort)

Performance (ADR-0024):
- Placement decision: <10ms P95
- Temperature read: <5ms P95
- Thermal polling: 1 Hz
- Failover latency: <100ms total

Primary ADRs:
- ADR-0026: Thermal Management (hysteresis matrix, 4-tier placement)
- ADR-0027: Model Placement Cascade (NPU→GPU→CPU→Remote)
- ADR-0024: Performance Budgets (placement <10ms, monitoring <5ms)

Research Foundation:
- Thermal hysteresis control (HVAC systems, embedded computing)
- Dynamic voltage and frequency scaling (DVFS)
- Mobile device thermal throttling (iPhone, Android)
"""

import logging
from typing import Optional

from .monitor import ThermalMonitor
from .placement_planner import PlacementPlanner
from .types import ThermalZone

logger = logging.getLogger(__name__)


class ThermalService:
    """
    K1 Thermal Service Manager

    Manages the lifecycle of thermal monitoring and placement services.
    Provides a unified interface for thermal-aware operations.

    This service should be kept alive throughout K1's runtime to provide
    continuous thermal monitoring for model placement and system health.
    """

    def __init__(self):
        self.monitor: Optional[ThermalMonitor] = None
        self.placement_planner: Optional[PlacementPlanner] = None
        self._running = False

    async def start_service(self):
        """Start the thermal service with monitoring and placement capabilities."""
        if self._running:
            return

        logger.info("Starting K1 Thermal Service...")

        try:
            # Create components (ultra-fast initialization <2ms)
            self.monitor = ThermalMonitor()
            self.placement_planner = PlacementPlanner(self.monitor)

            # Start thermal monitoring (continuous background service)
            await self.monitor.start_monitoring()
            self._running = True

            logger.info("✅ K1 Thermal Service started successfully")
            logger.info(
                f"   Available sensors: {len(self.monitor.get_available_sensors())}"
            )
            logger.info("   Thermal monitoring: ACTIVE (1Hz polling)")

        except Exception as e:
            logger.error(f"Failed to start thermal service: {e}")
            await self.stop_service()
            raise

    async def stop_service(self):
        """Stop the thermal service and cleanup resources."""
        if not self._running:
            return

        logger.info("Stopping K1 Thermal Service...")

        try:
            if self.monitor:
                await self.monitor.stop_monitoring()
                self.monitor = None

            self.placement_planner = None
            self._running = False

            logger.info("✅ K1 Thermal Service stopped")

        except Exception as e:
            logger.error(f"Error stopping thermal service: {e}")

    def is_running(self) -> bool:
        """Check if the thermal service is running."""
        return self._running

    def get_thermal_status(self):
        """Get current thermal status."""
        if self.monitor:
            return self.monitor.get_thermal_status()
        return None

    def get_thermal_zone(self) -> ThermalZone:
        """Get current thermal zone."""
        if self.monitor:
            return self.monitor.get_thermal_state()
        return ThermalZone.WARM

    def choose_accelerator(self):
        """Get thermal-aware accelerator placement decision."""
        if self.placement_planner:
            return self.placement_planner.choose_accelerator()
        return None

    def force_emergency_jump(self) -> bool:
        """Force emergency thermal jump to REMOTE placement."""
        if self.placement_planner:
            return self.placement_planner.force_emergency_jump()
        return False


# Global thermal service instance
_thermal_service: Optional[ThermalService] = None


def get_thermal_service() -> ThermalService:
    """Get the global thermal service instance."""
    global _thermal_service
    if _thermal_service is None:
        _thermal_service = ThermalService()
    return _thermal_service


async def start_thermal_service():
    """Start the global thermal service (called during K1 initialization)."""
    service = get_thermal_service()
    await service.start_service()
    return service


async def stop_thermal_service():
    """Stop the global thermal service (called during K1 shutdown)."""
    global _thermal_service
    if _thermal_service:
        await _thermal_service.stop_service()
        _thermal_service = None


# Convenience functions for common operations
def get_current_thermal_zone() -> ThermalZone:
    """Get current thermal zone (fast synchronous call)."""
    service = get_thermal_service()
    return service.get_thermal_zone()


def get_thermal_aware_placement():
    """Get thermal-aware model placement decision."""
    service = get_thermal_service()
    return service.choose_accelerator()


__all__ = [
    "ThermalService",
    "get_thermal_service",
    "start_thermal_service",
    "stop_thermal_service",
    "get_current_thermal_zone",
    "get_thermal_aware_placement",
    "ThermalMonitor",
    "PlacementPlanner",
    "ThermalZone",
]
