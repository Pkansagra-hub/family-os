"""HIL-local minimal ports (E1.M1.7).

Defined here (not reused from fabric/planner) to avoid circular imports
when those subsystems depend on the HIL service.
"""

from __future__ import annotations

from k1.hil.ports.event_port import IEventPort, SubscriptionHandle
from k1.hil.ports.llm_port import ILLMPort

__all__ = ["IEventPort", "ILLMPort", "SubscriptionHandle"]
