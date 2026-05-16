from __future__ import annotations

from k1.concierge.prompt.back_profiles import (
    render_back_execution_profile_block,
    select_back_execution_profiles,
)


def test_selects_calendar_profile_from_domain_and_action() -> None:
    selection = select_back_execution_profiles(
        {
            "task_id": "task-1",
            "intents": [
                {
                    "action": "create an event for Riley soccer practice",
                    "domain": "calendar",
                    "params": {"start": "2026-06-01T17:00:00"},
                }
            ],
        }
    )

    assert selection.reason == "matched"
    assert selection.profile_ids[0] == "calendar.v1"


def test_task_domain_beats_schedule_word_for_task_profile() -> None:
    selection = select_back_execution_profiles(
        {
            "task_id": "task-1",
            "intents": [
                {
                    "action": "schedule the insurance paperwork task",
                    "domain": "tasks",
                    "params": {"due_at": "tomorrow"},
                }
            ],
        }
    )

    assert selection.profile_ids[0] == "tasks.v1"
    assert "calendar.v1" not in selection.profile_ids[:1]


def test_bundled_calendar_and_reminder_selects_multiple_profiles() -> None:
    selection = select_back_execution_profiles(
        {
            "task_id": "task-1",
            "intents": [
                {"action": "create calendar event", "domain": "calendar"},
                {"action": "remind Nana the day before", "domain": "reminders"},
            ],
        }
    )

    assert "calendar.v1" in selection.profile_ids
    assert "reminders.v1" in selection.profile_ids


def test_existing_execution_profile_metadata_wins_for_resume() -> None:
    selection = select_back_execution_profiles(
        {
            "task_id": "task-1",
            "execution_profiles": [
                {
                    "profile_id": "reminders.v1",
                    "score": 99,
                    "evidence": ["resume"],
                }
            ],
            "intents": [{"action": "create calendar event", "domain": "calendar"}],
        }
    )

    assert selection.reason == "task_metadata"
    assert selection.profile_ids == ("reminders.v1",)


def test_rendered_profile_block_is_bounded_and_non_authorizing() -> None:
    selection = select_back_execution_profiles(
        {
            "task_id": "task-1",
            "intents": [{"action": "complete task", "domain": "tasks"}],
        }
    )
    block = render_back_execution_profile_block(selection, max_chars=650)

    assert "== EXECUTION PROFILES ==" in block
    assert "tasks.v1" in block
    assert "They do not grant tools or authority" in block
    assert "Registry schemas" in block
    assert len(block) <= 650


def test_weak_generic_record_action_falls_back_to_generic_profile() -> None:
    selection = select_back_execution_profiles(
        {"task_id": "task-1", "intents": [{"action": "update the record"}]}
    )

    assert selection.profile_ids == ("system_of_record.generic.v1",)
