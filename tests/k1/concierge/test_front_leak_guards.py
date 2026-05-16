"""M2 Front leak guard tests."""

from __future__ import annotations

from k1.concierge.actors.front import _strip_leaked_back_frame


def test_strip_leaked_back_frame_removes_thinking_json_and_tool_traces() -> None:
    text = """
<think>I should expose my scratchpad.</think>
Here is the useful answer.
{"task_id": "task-1", "final_answer": "internal", "tool_call_summaries": []}
tool_call_summaries: [{"tool": "secret"}]
scratchpad: hidden state
"""

    cleaned = _strip_leaked_back_frame(text)

    assert "Here is the useful answer." in cleaned
    assert "<think>" not in cleaned
    assert "task_id" not in cleaned
    assert "tool_call_summaries" not in cleaned
    assert "scratchpad" not in cleaned
