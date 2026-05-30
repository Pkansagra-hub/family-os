"""M8.E1 Back execution plan coverage."""

from __future__ import annotations

import pytest

from k1.concierge.fsm.task_bridge import TaskBridge
from k1.concierge.ledger.writer import LedgerWriter
from k1.concierge.react.back_execution_plan import BackExecutionPlan


def _task() -> dict:
    return {
        "task_id": "task-1",
        "intents": [
            {"action": "create task", "domain": "tasks", "params": {"title": "Pack"}},
            {
                "action": "create calendar event",
                "domain": "calendar",
                "params": {"title": "Dentist"},
            },
        ],
    }


def test_plan_seeds_one_work_item_per_dispatch_intent() -> None:
    plan = BackExecutionPlan.from_task(_task())

    assert plan.task_id == "task-1"
    assert [item.action for item in plan.work_items] == [
        "create task",
        "create calendar event",
    ]
    assert plan.can_submit_complete() is False


def test_plan_records_discovery_and_invocation_per_intent() -> None:
    plan = BackExecutionPlan.from_task(_task())

    plan.record_discovery(
        {"intent": "create task", "domain": "tasks"},
        {"capabilities": [{"name": "tool.execute.tasks.create_task"}], "count": 1},
    )
    plan.record_authority_result(
        tool_name="invoke_capability",
        args={
            "capability_name": "tool.execute.tasks.create_task",
            "domain": "tasks",
        },
        data={"status": "success", "result": {"task_id": "t1"}},
        tool_ok=True,
    )

    assert plan.work_items[0].status == "succeeded"
    assert plan.work_items[1].status == "pending"
    assert plan.can_submit_complete() is False
    assert plan.submit_rejection_payload()["pending_intents"][0]["domain"] == "calendar"


def test_plan_matches_compound_family_task_capability_without_domain_arg() -> None:
    plan = BackExecutionPlan.from_task(_task())

    plan.record_authority_result(
        tool_name="invoke_capability",
        args={"capability_name": "tool.read.family_tasks.list_tasks", "params": {}},
        data={"status": "success", "result": {"tasks": []}},
        tool_ok=True,
    )

    assert plan.work_items[0].status == "succeeded"
    assert plan.work_items[1].status == "pending"


def test_plan_round_trips_through_checkpoint_scratchpad_payload() -> None:
    plan = BackExecutionPlan.from_task(_task())
    plan.record_authority_result(
        tool_name="batch_invoke_capabilities",
        args={
            "invocations": [
                {"capability_name": "tool.execute.tasks.create_task", "domain": "tasks"},
                {
                    "capability_name": "tool.execute.calendar.create_event",
                    "domain": "calendar",
                },
            ]
        },
        data={
            "results": [
                {"capability_name": "tool.execute.tasks.create_task", "status": "success"},
                {"capability_name": "tool.execute.calendar.create_event", "status": "success"},
            ]
        },
        tool_ok=True,
    )

    restored = BackExecutionPlan.from_dict(plan.to_dict())

    assert restored.can_submit_complete() is True
    assert restored.merge_submit_args({"result_type": "complete"})["facts"] == [
        item.fact() for item in restored.work_items
    ]


def test_workflow_authority_can_cover_bundled_intents_without_per_intent_args() -> None:
    plan = BackExecutionPlan.from_task(_task())

    plan.record_authority_result(
        tool_name="execute_workflow",
        args={"workflow_name": "family_household_plan"},
        data={"status": "success", "result": {"workflow_id": "wf-1"}},
        tool_ok=True,
    )

    assert plan.can_submit_complete() is True
    assert [item.attempted_capabilities for item in plan.work_items] == [
        ["family_household_plan"],
        ["family_household_plan"],
    ]


def test_back_execution_plan_does_not_mutate_lifecycle_ledger_or_task_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("BackExecutionPlan must not own lifecycle mutation")

    monkeypatch.setattr(LedgerWriter, "append_sync", forbidden)
    monkeypatch.setattr(TaskBridge, "complete_task", forbidden)
    monkeypatch.setattr(TaskBridge, "suspend_task", forbidden)

    plan = BackExecutionPlan.from_task(_task())
    plan.record_discovery(
        {"intent": "create task", "domain": "tasks"},
        {"capabilities": [{"name": "tool.execute.tasks.create_task"}], "count": 1},
    )
    plan.record_authority_result(
        tool_name="batch_invoke_capabilities",
        args={
            "invocations": [
                {"capability_name": "tool.execute.tasks.create_task", "domain": "tasks"},
                {
                    "capability_name": "tool.execute.calendar.create_event",
                    "domain": "calendar",
                },
            ]
        },
        data={
            "results": [
                {"capability_name": "tool.execute.tasks.create_task", "status": "success"},
                {"capability_name": "tool.execute.calendar.create_event", "status": "success"},
            ]
        },
        tool_ok=True,
    )
    merged = plan.merge_submit_args({"result_type": "complete"})

    assert plan.can_submit_complete() is True
    assert merged["execution_plan"]["complete"] is True
