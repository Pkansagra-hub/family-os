"""k1.planner.services -- Planner support services [F25, F26].

Layer 2 services that support the pipeline stage services
(SketchService, ExpandService, ValidateService, CommitService).

Services
--------
- ``ToolCallRouter`` [F25]: deterministic dispatch of 4 read-only
  discovery tools to 3 backend ports with PLAN-05 budget enforcement.
- ``HILCoordinator`` [F26]: Human-in-the-Loop clarification and
  approval coordination with event pub/sub and PLAN-10 budget.

Import graph (Layer 2)
----------------------
k1.planner.services
  -> k1.planner.services.tool_call_router  (ToolCallRouter)
  -> k1.planner.services.hil_coordinator   (HILCoordinator) [Epic 4.2]
"""

from k1.planner.services.hil_coordinator import HILCoordinator

from k1.planner.services.tool_call_router import ToolCallRouter

__all__ = [
    "HILCoordinator",
    "ToolCallRouter",
]
