from __future__ import annotations

from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch
from k1.concierge.task.intent import TaskIntent


def test_task_dispatch_round_trips_execution_profiles() -> None:
    dispatch = TaskDispatch(
        task_id="task-profile-1",
        intents=[TaskIntent(action="create event", domain="calendar")],
        tier=ComplexityTier.LOW,
        execution_profiles=[
            {
                "profile_id": "calendar.v1",
                "score": 100,
                "evidence": ["domain:calendar"],
            }
        ],
    )

    restored = TaskDispatch.from_dict(dispatch.to_dict())

    assert restored.execution_profiles == [
        {
            "profile_id": "calendar.v1",
            "score": 100,
            "evidence": ["domain:calendar"],
        }
    ]
    assert restored.to_dict()["execution_profiles"][0]["profile_id"] == "calendar.v1"


def test_task_dispatch_omits_execution_profiles_when_absent() -> None:
    dispatch = TaskDispatch(
        task_id="task-profile-2",
        intents=[TaskIntent(action="recall prep notes", domain="memory")],
        tier=ComplexityTier.LOW,
    )

    payload = dispatch.to_dict()
    restored = TaskDispatch.from_dict(payload)

    assert "execution_profiles" not in payload
    assert payload["safety_band"] == "GREEN"
    assert restored.execution_profiles is None
