"""k1.planner.services -- Planner support services [F25].

E5 (HIL Unification): the legacy HILCoordinator and HILCoordinatorLike
have been removed. Planner stages now consume the unified IHILPort
(``k1.kernel.ports.hil_port.IHILPort``) injected by ``PlannerFactory``.
"""

from k1.planner.services.tool_call_router import ToolCallRouter

__all__ = [
    "ToolCallRouter",
]
