from __future__ import annotations

from k1.concierge.protocols.hitl_wiring import build_resume_context


def test_resume_context_carries_recovery_contract() -> None:
    recovery = {
        "schema_version": "k1.concierge.tool_recovery.v1",
        "action": "ask_human",
        "hil_type": "clarification",
        "capability_name": "tool.execute.tasks.create_task",
        "missing_fields": ["title"],
        "retry_tool": "invoke_capability",
        "retry_args": {
            "capability_name": "tool.execute.tasks.create_task",
            "params": {"assigned_to": "jordan"},
        },
    }

    context = build_resume_context(
        task_id="task-1",
        hil_type="clarification",
        resolution={"additional_info": "Start washer and dryer"},
        recovery=recovery,
    )

    assert context.to_back_context()["recovery"] == recovery
