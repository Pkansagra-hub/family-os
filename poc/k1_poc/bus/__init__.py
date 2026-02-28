"""
poc.k1_poc.bus -- Bus integration layer for the K1 POC.

Re-exports the public API from submodules:
    - topics:   28 topic constants, subscription groups, classification sets
    - setup:    Factory functions for bus, router, adapter, actor registration
    - builders: Envelope builder functions (one per topic)

Usage::

    from poc.k1_poc.bus import create_poc_bus, create_poc_router, register_poc_actors
    from poc.k1_poc.bus import TOPIC_USER_INPUT, build_user_input
"""

from poc.k1_poc.bus.builders import (  # noqa: F401
    BUILDERS,
    BuilderEntry,
    build_affect_update,
    build_artifact_created,
    build_clarification_out,
    build_clarification_request,
    build_clarification_response,
    build_dag_completed,
    build_final_response,
    build_findings_ready,
    build_hil_request,
    build_hil_response,
    build_orchestration_delta,
    build_plan_ready,
    build_proactive_fill,
    build_state_updated,
    build_task_accepted,
    build_task_cancel,
    build_task_complete,
    build_task_dispatch,
    build_task_failed,
    build_task_resume,
    build_task_suspended,
    build_tool_completed,
    build_tool_started,
    build_turn_completed,
    build_turn_started,
    build_user_input,
    build_weave_batch,
    get_builder_registry,
)
from poc.k1_poc.bus.setup import (  # noqa: F401; V3 E0.2.3: POC_MAILBOX_CAPACITY and POC_GAP_TIMEOUT_MS removed.; Use get_config().bus.mailbox_capacity / .gap_timeout_ms instead.
    ACTOR_BACK,
    ACTOR_FRONT,
    create_poc_bus,
    create_poc_router,
    create_poc_session_adapter,
    register_poc_actors,
)
from poc.k1_poc.bus.topics import (  # noqa: F401
    ALL_TOPICS,
    BACK_SUBSCRIPTIONS,
    FRONT_SUBSCRIPTIONS,
    RELAXED_TOPICS,
    STRICT_TOPICS,
    TOPIC_AFFECT_UPDATE,
    TOPIC_ARTIFACT_CREATED,
    TOPIC_CLARIFICATION_OUT,
    TOPIC_CLARIFICATION_REQUEST,
    TOPIC_CLARIFICATION_RESPONSE,
    TOPIC_DAG_COMPLETED,
    TOPIC_FINAL_RESPONSE,
    TOPIC_FINDINGS_READY,
    TOPIC_HIL_REQUEST,
    TOPIC_HIL_RESPONSE,
    TOPIC_ORCHESTRATION_DELTA,
    TOPIC_PLAN_READY,
    TOPIC_PROACTIVE_FILL,
    TOPIC_STATE_UPDATED,
    TOPIC_TASK_ACCEPTED,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_TURN_COMPLETED,
    TOPIC_TURN_STARTED,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
    URGENT_TOPICS,
    get_priority,
)
