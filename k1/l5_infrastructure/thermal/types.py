"""
Shared thermal types and enums for the thermal management system.

This module contains common types used across thermal monitoring and placement components.
"""

from enum import Enum


class ThermalZone(Enum):
    """Thermal state zones as defined in ADR-0026a."""

    COOL = 0  # < 70°C (relaxed for gaming)
    WARM = 1  # 70-80°C (relaxed for gaming)
    HOT = 2  # 80-90°C (relaxed for gaming)
    CRITICAL = 3  # 90-100°C (relaxed for gaming)
    EMERGENCY = 4  # > 100°C (relaxed for gaming)


class SensorType(Enum):
    """Types of thermal sensors."""

    CPU = "cpu"
    GPU = "gpu"
    NPU = "npu"
    SOC = "soc"
    BATTERY = "battery"
    SKIN = "skin"
