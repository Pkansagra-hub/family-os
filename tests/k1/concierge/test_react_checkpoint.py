"""M3 ReAct checkpoint coverage."""

from __future__ import annotations

import pytest

from k1.concierge.actors.back import _deserialize_messages, _serialize_messages
from k1.concierge.llm.types import ModelMessage, ToolCallResult
from k1.concierge.react.checkpoint import ReActCheckpoint, ReActCheckpointVersionError


def test_react_checkpoint_round_trip_json_safe() -> None:
    checkpoint = ReActCheckpoint(
        task_id="task-1",
        messages=[{"role": "user", "content": "go"}],
        tool_history=[
            {
                "tool_name": "invoke_capability",
                "call_id": "call-1",
                "args_hash": "abc123",
                "result_status": "ok",
            }
        ],
        completed_tool_call_ids=["call-1"],
        suspension_count=2,
        budget_remaining=3,
        last_iteration=4,
        scratchpad={"loop_events": [{"event_type": "forced_text"}]},
    )

    restored = ReActCheckpoint.from_dict(checkpoint.to_dict())

    assert restored == checkpoint
    assert restored.to_dict()["version"] == 1


def test_unknown_checkpoint_version_is_typed_error() -> None:
    with pytest.raises(ReActCheckpointVersionError):
        ReActCheckpoint.from_dict({"version": 999, "task_id": "task-1"})


def test_completed_tool_keys_include_successful_tool_arg_hashes_only() -> None:
    checkpoint = ReActCheckpoint(
        task_id="task-1",
        tool_history=[
            {"tool_name": "a", "args_hash": "111", "result_status": "ok"},
            {"tool_name": "b", "args_hash": "222", "result_status": "partial"},
            {"tool_name": "c", "args_hash": "333", "result_status": "error"},
            {"tool_name": "d", "result_status": "ok"},
        ],
    )

    assert checkpoint.completed_tool_keys() == {"a:111", "b:222"}


def test_react_history_round_trip_preserves_assistant_tool_calls() -> None:
    messages = [
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCallResult(
                    id="call-1",
                    name="invoke_capability",
                    arguments={"capability_name": "tool.read.tasks.list_tasks"},
                )
            ],
        ),
        ModelMessage(
            role="tool",
            content='{"ok": true}',
            tool_call_id="call-1",
            name="invoke_capability",
        ),
    ]

    restored = _deserialize_messages(_serialize_messages(messages))

    assert restored[0].tool_calls is not None
    assert restored[0].tool_calls[0].id == "call-1"
    assert restored[0].tool_calls[0].arguments == {"capability_name": "tool.read.tasks.list_tasks"}
