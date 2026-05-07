"""Single source of truth for HIL bus topics.

After E7, the following legacy constants are DELETED:
  - k1.planner.events.TOPIC_HIL_CLARIFICATION
  - k1.planner.events.TOPIC_HIL_APPROVAL_REQ
  - k1.planner.events.TOPIC_HIL_CLARIFICATION_RESP
  - k1.planner.events.TOPIC_HIL_APPROVAL_RESP
  - k1.orchestrator.events.HIL_OVERRIDE_RESPONSE
  - k1.orchestrator.events.HIL_FALLBACK_RESPONSE
  - All k1.hitl.* concierge audit topics (consolidated into k1.hil.audit.v1)
"""

from __future__ import annotations

# All outbound to user (Front bridge subscribes; payload = HILEnvelope.to_dict())
TOPIC_HIL_REQUEST = "k1.hil.request.v1"

# All inbound from user (HumanInTheLoopService subscribes; payload = HILResponseEnvelope.to_dict())
TOPIC_HIL_RESPONSE = "k1.hil.response.v1"

# Optional observability stream (requested / resolved / timed_out / blocked)
TOPIC_HIL_AUDIT = "k1.hil.audit.v1"


# Caller-key namespaces (convention, not enforced):
#   planner:<plan_id>          -- planner SKETCH / VALIDATE
#   concierge:<task_id>        -- concierge Back -> FSM
#   orchestrator:<plan_id>     -- orchestrator constraint resolver
#   fabric:<capability_name>   -- fabric pre-execution gate
