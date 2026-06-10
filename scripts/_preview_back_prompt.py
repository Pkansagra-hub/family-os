"""Write Back prompt to file for inspection."""

from k1.concierge.prompt.back_prompt import build_back_prompt
from pathlib import Path

prompt = build_back_prompt(
    task={
        "task_id": "task-001",
        "intents": [{"action": "schedule dentist appointment for Riley", "domain": "calendar"}],
        "tier": "LOW",
        "budget_hint": 4,
    },
    temporal_context_block="== TEMPORAL CONTEXT ==\nanchor_id: t1\nnow_utc: 2026-06-09T17:00:00Z\ntimezone: America/Chicago (device)\nlocal_date: 2026-06-09\nday: Tuesday afternoon",
    spatial_context_block="== SPATIAL CONTEXT ==\ndevice: home\nhome: Chicago, IL (123 Main St)",
    selfmodel_context_block="== SELFMODEL ==\nuser prefers morning appointments\nuser is vegan",
    execution_grounding_block='== EXECUTION GROUNDING ==\ngrounding_envelope_id: g-001\ntemporal_anchor_id: ta-1\nresolved_temporal_refs: {"next Monday": "2026-06-15"}',
    execution_profile_block="== EXECUTION PROFILE ==\ncalendar.v1: Family Calendar (backed)\n  Always LIST the calendar first to check for conflicts\n  Check chores and tasks in the same time window",
)

Path("data/_back_prompt_preview.txt").write_text(prompt, encoding="utf-8")
print(f"Written {len(prompt)} chars to data/_back_prompt_preview.txt")
