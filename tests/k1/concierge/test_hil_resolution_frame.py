"""M2 typed HIL resolution frame tests."""

from __future__ import annotations

import json
from typing import Any

from k1.concierge.actors.frames import HILResolutionFrame
from k1.concierge.actors.front import (
    _build_resolution,
    _build_resolution_frame,
    emit_task_resume,
)


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list[Any] = []

    def publish(self, envelope: Any) -> None:
        self.published.append(envelope)


def _payload(envelope: Any) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


def test_build_resolution_frame_preserves_typed_hil_metadata() -> None:
    frame = _build_resolution_frame(
        {
            "task_id": "task-1",
            "pending_hil_id": "hil-1",
            "hil_type": "approval",
            "user_answer": "yes, approve it",
            "legacy_bridge": True,
        }
    )

    assert frame.task_id == "task-1"
    assert frame.hil_request_id == "hil-1"
    assert frame.kind == "approval"
    assert frame.approval is True
    assert frame.raw_user_text == "yes, approve it"
    assert frame.legacy_bridge is True
    assert frame.command_summary() == {
        "kind": "approval",
        "selected_option": "approve",
        "approval": True,
    }


def test_build_resolution_stays_legacy_dict_compatible() -> None:
    out = _build_resolution(
        {"task_id": "task-1", "hil_type": "capability_gate", "user_answer": "allow"}
    )

    assert out["_frame_type"] == "hil_resolution"
    assert out["approval"] is True
    assert out["additional_info"] == "allow"


def test_emit_task_resume_includes_resolution_frame() -> None:
    bus = _RecordingBus()
    frame = HILResolutionFrame(
        task_id="task-1",
        hil_request_id="hil-1",
        kind="clarification",
        raw_user_text="Paris",
        selected_option="answered",
        additional_info="Paris",
    )

    emit_task_resume(
        bus=bus,  # type: ignore[arg-type]
        task_id="task-1",
        user_answer=json.dumps(frame.to_resolution_dict()),
        resolution=frame.to_resolution_dict(),
        resolution_frame=frame.to_dict(),
    )

    out = _payload(bus.published[0])
    assert out["resolution"]["_frame_type"] == "hil_resolution"
    assert out["resolution_frame"]["raw_user_text"] == "Paris"
