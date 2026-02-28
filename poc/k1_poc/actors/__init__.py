"""
Actors Package -- Front and Back Handler Entry Points
=======================================================

V2 Design Ref: Section 6 (LLM Actors)

Exports:
  Front Handler (Epic 6.1):
    - front_handler: Main entry point for Front LLM invocation
    - _extract_scenario_data: Mode-specific payload extraction
    - _parse_payload: Envelope payload JSON parser

  Event Subscriptions (Epic 6.2):
    - subscribe_front_events: Wire Front to bus topics

  Event Emissions (Epic 6.3):
    - emit_task_cancel: Publish task.cancel.v1
    - emit_task_resume: Publish task.resume.v1

  HITL Resolution (Epic 6.4.4):
    - _build_resolution: Build resolution dict from HITL answer

  Back Handler (Epic 7.1):
    - back_handler: Main entry point for Back LLM invocation
    - back_resume_handler: Resume a suspended Back task
    - back_cancel_handler: Handle task cancellation

  Back Event Subscriptions (Epic 7.2):
    - subscribe_back_events: Wire Back to bus topics

  Back Event Emissions (Epic 7.3):
    - emit_tool_started: Publish tool.started.v1
    - emit_tool_completed: Publish tool.completed.v1
    - emit_artifact_created: Publish artifact.created.v1

  Back Resume/Cancel (Epic 7.4):
    - store_pending_context: Store ReAct history on suspend

  Shared Actor Utilities (E3.5):
    - parse_envelope_payload: Safely parse JSON bytes from Envelope
    - safe_get_section: Safely read a SessionState section
    - never_cancel: Async no-op cancellation check
"""

from poc.k1_poc.actors.back import (
    _budget_to_iterations,
    _filter_back_tools,
    _summarize_args,
    _summarize_result,
    back_cancel_handler,
    back_handler,
    back_resume_handler,
    emit_artifact_created,
    emit_tool_completed,
    emit_tool_started,
    route_back_envelope,
    store_pending_context,
    subscribe_back_events,
)
from poc.k1_poc.actors.front import (
    _build_resolution,
    _extract_scenario_data,
    _parse_payload,
    emit_task_cancel,
    emit_task_resume,
    front_handler,
    subscribe_front_events,
)

# Shared Actor Utilities (E3.5)
from poc.k1_poc.actors.shared import never_cancel, parse_envelope_payload, safe_get_section

__all__ = [
    # Front
    "front_handler",
    "_extract_scenario_data",
    "_parse_payload",
    "_build_resolution",
    "subscribe_front_events",
    "emit_task_cancel",
    "emit_task_resume",
    # Back
    "back_handler",
    "back_resume_handler",
    "back_cancel_handler",
    "route_back_envelope",
    # subscribe_back_events: deprecated M3 E3.1.5, removal in M8
    "emit_tool_started",
    "emit_tool_completed",
    "emit_artifact_created",
    "store_pending_context",
    "_budget_to_iterations",
    "_filter_back_tools",
    "_summarize_args",
    "_summarize_result",
    # Shared utilities (E3.5)
    "parse_envelope_payload",
    "safe_get_section",
    "never_cancel",
]
