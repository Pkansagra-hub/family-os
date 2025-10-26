"""
Shared thermal types and enums for the thermal management system.

This module contains common types used across thermal monitoring and placement components.
"""

from enum import Enum


class ThermalZone(Enum):
    """Thermal state zones as defined in ADR-0077 (M3 Epic 2)."""

    COOL = 0  # <70°C
    WARM = 1  # 70-74°C
    HOT = 2  # 75-84°C
    CRITICAL = 3  # 85-94°C
    EMERGENCY = 4  # ≥95°C


# ADR-0077 (M3 Epic 2) authoritative thermal thresholds
# Single source of truth for all thermal zone boundaries
THERMAL_THRESHOLDS = {
    ThermalZone.COOL: 70,  # COOL → WARM at 70°C
    ThermalZone.WARM: 75,  # WARM → HOT at 75°C
    ThermalZone.HOT: 85,  # HOT → CRITICAL at 85°C
    ThermalZone.CRITICAL: 95,  # CRITICAL → EMERGENCY at 95°C
}


class SensorType(Enum):
    """Types of thermal sensors."""

    CPU = "cpu"
    GPU = "gpu"
    NPU = "npu"
    SOC = "soc"
    BATTERY = "battery"
    SKIN = "skin"
