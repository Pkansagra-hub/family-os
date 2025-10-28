# Thermal Policy
# Extensible thermal management policy

"""
Thermal Policy - Thermal Management Extensions

Layer: L5 Infrastructure
Component: Extensions
Priority: 🟢 LOW (Thermal management extensibility)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0034: Extensions Framework Design

Thermal Policy Philosophy:
    - Extensible thermal management strategies
    - Temperature monitoring and control
    - Power and performance balancing
    - Hardware protection and optimization

Extension Points:
    - Thermal policies (passive, active cooling, throttling)
    - Temperature monitoring (CPU, GPU, system sensors)
    - Control strategies (fan speed, clock throttling, workload scheduling)
    - Alert thresholds (warning, critical, emergency)

Dependencies:
    Internal:
        - k1.l5_infrastructure.modules (for hot-reload)
    External:
        - psutil (system monitoring)

Connects To:
    Upstream:
        - k1.l4_runtime components (thermal management)
    Downstream:
        - k1.l5_infrastructure.extensions (extension registry)

Observability:
    - Metrics: k1_thermal_policy_temperature_celsius{sensor}
    - Metrics: k1_thermal_policy_throttling_events_total{policy}
    - Logs: WARN temperature threshold exceeded, ERROR thermal emergency

References:
    - Planning: docs/planning/stub_generation_plan_layer5.md (Milestone 14)
    - Test: tests/k1/l5_infrastructure/extensions/test_thermal_policy.py
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class ThermalReading:
    """
    Thermal sensor reading.

    TODO(@extensions-team): Implement thermal reading structure
    """
    pass


class ThermalAction:
    """
    Thermal management action.

    TODO(@extensions-team): Implement thermal action structure
    """
    pass


class ThermalPolicy(ABC):
    """
    Abstract thermal policy interface.

    Extensions implement this to provide different thermal management strategies.
    """

    @abstractmethod
    async def evaluate_temperature(self, readings: List[ThermalReading]) -> List[ThermalAction]:
        """
        Evaluate temperature readings and determine actions.

        Args:
            readings: Current thermal sensor readings

        Returns:
            List of thermal actions to take

        TODO(@extensions-team): Implement temperature evaluation
        """
        pass

    @abstractmethod
    async def execute_action(self, action: ThermalAction) -> bool:
        """
        Execute thermal management action.

        Args:
            action: Action to execute

        Returns:
            True if action executed successfully

        TODO(@extensions-team): Implement action execution
        """
        pass

    @abstractmethod
    async def get_thresholds(self) -> Dict[str, float]:
        """
        Get thermal thresholds for this policy.

        Returns:
            Threshold mapping (warning, critical, etc.)

        TODO(@extensions-team): Implement threshold retrieval
        """
        pass


class PassiveThermalPolicy(ThermalPolicy):
    """
    Passive thermal policy.

    Monitors temperature and alerts without active intervention.

    TODO(@extensions-team): Implement passive thermal policy
    """
    pass


class ActiveThermalPolicy(ThermalPolicy):
    """
    Active thermal policy.

    Actively manages temperature through throttling and cooling.

    TODO(@extensions-team): Implement active thermal policy
    """
    pass


class AdaptiveThermalPolicy(ThermalPolicy):
    """
    Adaptive thermal policy.

    Learns optimal thermal management strategies.

    TODO(@extensions-team): Implement adaptive thermal policy
    """
    pass


class ThermalPolicyManager:
    """
    Thermal policy manager with extension support.

    Manages thermal policies and sensor monitoring.

    TODO(@extensions-team): Implement policy manager
    """

    def __init__(self):
        self.policies: Dict[str, ThermalPolicy] = {}

    async def add_policy(self, name: str, policy: ThermalPolicy) -> None:
        """
        Add thermal policy.

        TODO(@extensions-team): Implement policy registration
        """
        pass

    async def monitor_and_control(self) -> List[ThermalAction]:
        """
        Monitor temperatures and execute policies.

        TODO(@extensions-team): Implement thermal monitoring
        """
        pass

    async def get_policy(self, name: str) -> Optional[ThermalPolicy]:
        """
        Get policy by name.

        TODO(@extensions-team): Implement policy retrieval
        """
        pass


# Global thermal policy manager
_thermal_manager: Optional[ThermalPolicyManager] = None


def get_thermal_policy_manager() -> ThermalPolicyManager:
    """
    Get global thermal policy manager instance.

    TODO(@extensions-team): Implement singleton pattern
    """
    global _thermal_manager
    if _thermal_manager is None:
        _thermal_manager = ThermalPolicyManager()
    return _thermal_manager


__all__ = [
    "ThermalReading",
    "ThermalAction",
    "ThermalPolicy",
    "PassiveThermalPolicy",
    "ActiveThermalPolicy",
    "AdaptiveThermalPolicy",
    "ThermalPolicyManager",
    "get_thermal_policy_manager",
]
