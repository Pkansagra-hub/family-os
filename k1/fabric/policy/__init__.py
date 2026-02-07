"""
k1.fabric.policy -- Policy Engine subsystem (Epic 3.2).

Re-exports public symbols from all policy dimensions and ports.

Modules:
  ports                  -- ISessionStateReader Protocol
  security_context       -- SecurityContext hard gate (3.2.1)
  affective_routing      -- AffectiveRouting soft score (3.2.2)
  cognitive_load_routing -- CognitiveLoadRouting soft score (3.2.3)
  qos_integration        -- QoSIntegration soft score (3.2.4)
  policy_engine          -- PolicyEngine composite (3.2.5)
  tool_scope             -- ToolScope enforcement (3.2.6)
"""

from k1.fabric.policy.affective_routing import AffectiveRouting, AffectiveScore
from k1.fabric.policy.cognitive_load_routing import CognitiveLoadRouting, CognitiveScore
from k1.fabric.policy.policy_engine import PolicyEngine
from k1.fabric.policy.ports import ISessionStateReader
from k1.fabric.policy.qos_integration import QoSIntegration, QoSScore
from k1.fabric.policy.security_context import (
    AccessDeniedError,
    SecurityCheckResult,
    SecurityContext,
    SecurityContextError,
)
from k1.fabric.policy.tool_scope import ToolScope, ToolScopeError

__all__ = [
    # Ports
    "ISessionStateReader",
    # 3.2.1 -- SecurityContext
    "SecurityContext",
    "SecurityCheckResult",
    "SecurityContextError",
    "AccessDeniedError",
    # 3.2.2 -- AffectiveRouting
    "AffectiveRouting",
    "AffectiveScore",
    # 3.2.3 -- CognitiveLoadRouting
    "CognitiveLoadRouting",
    "CognitiveScore",
    # 3.2.4 -- QoSIntegration
    "QoSIntegration",
    "QoSScore",
    # 3.2.5 -- PolicyEngine
    "PolicyEngine",
    # 3.2.6 -- ToolScope
    "ToolScope",
    "ToolScopeError",
]
