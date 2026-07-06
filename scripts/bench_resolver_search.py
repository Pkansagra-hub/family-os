"""
Benchmark: resolver search accuracy — Tiered by LLM hallucination severity.

Tiers:
  EASY       — LLM gives perfect domain / resource_family / operation_hint.
               The 5-stage pipeline should work flawlessly. Baseline accuracy.
  MEDIUM     — Same perfect hints, but action text uses natural language
               variants (indirect phrasing, synonyms, conversational tone).
               Tests FTS5 robustness to vocabulary drift.
  HARD       — LLM hallucinates ONE field (wrong domain, OR wrong resource_family,
               OR wrong operation_hint).  Resolver must still find the right
               connector despite one poisoned hint.
  ULTRAHARD  — LLM hallucinates TWO+ fields.  Wrong domain AND wrong
               resource_family, or empty domain + wrong op_hint.
               Only action text is reliable.
  HARDEST    — Adversarial.  ALL hints wrong, empty, or nonsensical.
               LLM says domain="healthcare" for a shopping query.
               Resolver must fall back to FTS5-only search on action text.
               Also includes multi-intent frames with hallucinated intents.

Each query has:
  - action:               ground-truth user utterance (what the user actually said)
  - domain:               what the LLM extracted (may be WRONG in hard+ tiers)
  - resource_family:      what the LLM extracted (may be WRONG)
  - operation_hint:       what the LLM extracted (may be WRONG)
  - expected_connector:   the ground-truth connector that SHOULD be returned
  - expected_capability:  exact capability name, or "?" if Back chooses
  - difficulty:           tier label
  - hallucination_profile: what the LLM got wrong (human-readable)

Usage:
  $env:LLM_PROVIDER="vertex"
  $env:GOOGLE_CLOUD_PROJECT="..."
  $env:GOOGLE_CLOUD_LOCATION="global"
  python scripts/bench_resolver_search.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# TIERED TEST CORPUS (~100 queries)
# ═══════════════════════════════════════════════════════════════════════════

# ── EASY (20 queries): Perfect LLM hints ─────────────────────────────────
# Ground truth: domain/resource_family/operation_hint all correct.
# These test the baseline 5-stage pipeline accuracy.

EASY_CORPUS: list[dict[str, Any]] = [
    # Calendar
    {
        "id": "easy-cal-01",
        "action": "what does my calendar look like this week",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "read",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-cal-02",
        "action": "show me my appointments for tomorrow",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "read",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-cal-03",
        "action": "create a dentist appointment for Riley on Monday at 3pm",
        "expected_connector": "family.calendar",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "create",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-cal-04",
        "action": "add Riley's soccer practice Saturday 9am to 11am",
        "expected_connector": "family.calendar",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "create",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    # Shopping
    {
        "id": "easy-shop-01",
        "action": "add eggs to my shopping list",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "create",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-shop-02",
        "action": "what's on my grocery list",
        "expected_connector": "family.shopping",
        "expected_capability": "tool.read.shopping.list_items",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "read",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-shop-03",
        "action": "what shopping lists do we have",
        "expected_connector": "family.shopping",
        "expected_capability": "tool.read.shopping.list_lists",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "read",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-shop-04",
        "action": "check off bread from the shopping list",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "update",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    # Tasks
    {
        "id": "easy-task-01",
        "action": "what tasks do I have this week",
        "expected_connector": "family.tasks",
        "expected_capability": "tool.read.tasks.list_tasks",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-task-02",
        "action": "create a task to pick up Riley from school Thursday 3pm",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "create",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-task-03",
        "action": "delete the old grocery run task",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "delete",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    # Chores
    {
        "id": "easy-chore-01",
        "action": "what chores are assigned this week",
        "expected_connector": "family.chores",
        "expected_capability": "tool.read.chores.list_chores",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "read",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-chore-02",
        "action": "assign kitchen cleanup to Riley every Saturday",
        "expected_connector": "family.chores",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "create",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-chore-03",
        "action": "complete the vacuum chore",
        "expected_connector": "family.chores",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "update",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    # Reminders
    {
        "id": "easy-rem-01",
        "action": "what reminders do I have today",
        "expected_connector": "family.reminders",
        "expected_capability": "tool.read.reminders.list_reminders",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "read",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-rem-02",
        "action": "remind me to take medicine at 8pm",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "create",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-rem-03",
        "action": "dismiss the trash reminder",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "update",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    # Family Settings
    {
        "id": "easy-set-01",
        "action": "what feature flags are enabled",
        "expected_connector": "family.family_settings",
        "expected_capability": "tool.read.family_settings.list_feature_flags",
        "domain": "family",
        "resource_family": "setting",
        "operation_hint": "read",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-set-02",
        "action": "update visibility policy for the family",
        "expected_connector": "family.family_settings",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "setting",
        "operation_hint": "update",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
    {
        "id": "easy-set-03",
        "action": "show me the current visibility settings",
        "expected_connector": "family.family_settings",
        "expected_capability": "tool.read.family_settings.get_visibility_policy",
        "domain": "family",
        "resource_family": "setting",
        "operation_hint": "read",
        "difficulty": "easy",
        "hallucination_profile": "none",
    },
]

# ── MEDIUM (20 queries): Natural language variance, hints still correct ───
# Same correct hints as easy, but action text uses indirect phrasing,
# synonyms, conversational tone, or non-standard vocabulary.
# Tests FTS5 robustness to vocabulary drift.

MEDIUM_CORPUS: list[dict[str, Any]] = [
    # Calendar — indirect/vague phrasing
    {
        "id": "med-cal-01",
        "action": "what's happening this weekend",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "read",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-cal-02",
        "action": "do I have anything scheduled for Friday afternoon",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "read",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-cal-03",
        "action": "pencil in a checkup with Dr. Patel next Tuesday morning",
        "expected_connector": "family.calendar",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "create",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-cal-04",
        "action": "scratch that board meeting from Thursday",
        "expected_connector": "family.calendar",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "delete",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    # Shopping — indirect/vague
    {
        "id": "med-shop-01",
        "action": "I need to pick up some milk and bread",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "create",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-shop-02",
        "action": "what are we running low on",
        "expected_connector": "family.shopping",
        "expected_capability": "tool.read.shopping.list_items",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "read",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-shop-03",
        "action": "grab some stuff for the party this weekend",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "create",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-shop-04",
        "action": "tick off the eggs, we already have those",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "update",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    # Tasks — indirect/vague
    {
        "id": "med-task-01",
        "action": "what's on my plate this week",
        "expected_connector": "family.tasks",
        "expected_capability": "tool.read.tasks.list_tasks",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-task-02",
        "action": "set up a reminder-type thing to grab the dry cleaning",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "create",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-task-03",
        "action": "that homework thing is done, wrap it up",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "update",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    # Chores — indirect/vague
    {
        "id": "med-chore-01",
        "action": "who's doing what around the house this week",
        "expected_connector": "family.chores",
        "expected_capability": "tool.read.chores.list_chores",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "read",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-chore-02",
        "action": "Riley needs to handle the kitchen stuff every Saturday",
        "expected_connector": "family.chores",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "create",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-chore-03",
        "action": "the vacuum thing is done for this week",
        "expected_connector": "family.chores",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "update",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    # Reminders — indirect/vague
    {
        "id": "med-rem-01",
        "action": "anything I need to remember today",
        "expected_connector": "family.reminders",
        "expected_capability": "tool.read.reminders.list_reminders",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "read",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-rem-02",
        "action": "nudge me about the meds tonight at 8",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "create",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-rem-03",
        "action": "push that dinner heads-up by half an hour",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "update",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    # Family Settings — indirect/vague
    {
        "id": "med-set-01",
        "action": "what toggles are currently flipped on",
        "expected_connector": "family.family_settings",
        "expected_capability": "tool.read.family_settings.list_feature_flags",
        "domain": "family",
        "resource_family": "setting",
        "operation_hint": "read",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    {
        "id": "med-set-02",
        "action": "change who can see what in the family",
        "expected_connector": "family.family_settings",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "setting",
        "operation_hint": "update",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
    # Cross-connector ambiguity
    {
        "id": "med-cross-01",
        "action": "make sure I don't forget to buy milk",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "create",
        "difficulty": "medium",
        "hallucination_profile": "none",
    },
]

# ── HARD (20 queries): LLM hallucinates ONE field ────────────────────────
# One of {domain, resource_family, operation_hint} is WRONG.
# Action text is the ground truth.  Resolver must overcome one poisoned hint.

HARD_CORPUS: list[dict[str, Any]] = [
    # ── Wrong DOMAIN (LLM says "healthcare" instead of "family") ──
    {
        "id": "hard-cal-01",
        "action": "show me my calendar for this week",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "healthcare",
        "resource_family": "event",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_domain",
    },
    {
        "id": "hard-shop-01",
        "action": "add bananas to the grocery list",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "enterprise",
        "resource_family": "item",
        "operation_hint": "create",
        "difficulty": "hard",
        "hallucination_profile": "wrong_domain",
    },
    {
        "id": "hard-task-01",
        "action": "what are my tasks for today",
        "expected_connector": "family.tasks",
        "expected_capability": "tool.read.tasks.list_tasks",
        "domain": "government",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_domain",
    },
    {
        "id": "hard-rem-01",
        "action": "remind me to call the plumber at 3pm",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "agriculture",
        "resource_family": "reminder",
        "operation_hint": "create",
        "difficulty": "hard",
        "hallucination_profile": "wrong_domain",
    },
    # ── Wrong RESOURCE_FAMILY ──
    {
        "id": "hard-cal-02",
        "action": "what does my calendar look like tomorrow",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_resource_family",
    },
    {
        "id": "hard-shop-02",
        "action": "what items are on the costco list",
        "expected_connector": "family.shopping",
        "expected_capability": "tool.read.shopping.list_items",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_resource_family",
    },
    {
        "id": "hard-task-02",
        "action": "create a todo for fixing the garage door",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "create",
        "difficulty": "hard",
        "hallucination_profile": "wrong_resource_family",
    },
    {
        "id": "hard-chore-01",
        "action": "list all chores for this month",
        "expected_connector": "family.chores",
        "expected_capability": "tool.read.chores.list_chores",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_resource_family",
    },
    {
        "id": "hard-rem-02",
        "action": "set a reminder for trash day Tuesday 7am",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "create",
        "difficulty": "hard",
        "hallucination_profile": "wrong_resource_family",
    },
    {
        "id": "hard-set-01",
        "action": "what feature flags are active",
        "expected_connector": "family.family_settings",
        "expected_capability": "tool.read.family_settings.list_feature_flags",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_resource_family",
    },
    # ── Wrong OPERATION_HINT (LLM says "read" for create, "create" for delete, etc.) ──
    {
        "id": "hard-cal-03",
        "action": "schedule a parent-teacher meeting for Wednesday",
        "expected_connector": "family.calendar",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_operation_hint",
    },
    {
        "id": "hard-shop-03",
        "action": "remove the expired coupons from the list",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "create",
        "difficulty": "hard",
        "hallucination_profile": "wrong_operation_hint",
    },
    {
        "id": "hard-task-03",
        "action": "mark the science project as finished",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_operation_hint",
    },
    {
        "id": "hard-chore-02",
        "action": "Riley is done with dishes this week",
        "expected_connector": "family.chores",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_operation_hint",
    },
    {
        "id": "hard-rem-03",
        "action": "cancel all my morning reminders",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "create",
        "difficulty": "hard",
        "hallucination_profile": "wrong_operation_hint",
    },
    {
        "id": "hard-set-02",
        "action": "turn off the experimental grocery predictor",
        "expected_connector": "family.family_settings",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "setting",
        "operation_hint": "read",
        "difficulty": "hard",
        "hallucination_profile": "wrong_operation_hint",
    },
    # ── Wrong DOMAIN + unrelated but real-sounding domain ──
    {
        "id": "hard-cal-04",
        "action": "cancel the dentist appointment next Monday",
        "expected_connector": "family.calendar",
        "expected_capability": "?",
        "domain": "wellness",
        "resource_family": "event",
        "operation_hint": "delete",
        "difficulty": "hard",
        "hallucination_profile": "wrong_domain",
    },
    {
        "id": "hard-shop-04",
        "action": "make a new list for holiday gifts",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "retail",
        "resource_family": "item",
        "operation_hint": "create",
        "difficulty": "hard",
        "hallucination_profile": "wrong_domain",
    },
    {
        "id": "hard-chore-03",
        "action": "skip lawn mowing this Saturday",
        "expected_connector": "family.chores",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "update",
        "difficulty": "hard",
        "hallucination_profile": "wrong_resource_family",
    },
    {
        "id": "hard-task-04",
        "action": "reassign the budget review to Morgan",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "update",
        "difficulty": "hard",
        "hallucination_profile": "wrong_resource_family",
    },
]

# ── ULTRAHARD (20 queries): LLM hallucinates TWO+ fields ──────────────────
# Two or more hints are wrong.  Only action text is reliable.
# Resolver must fall back to FTS5 text matching.

ULTRAHARD_CORPUS: list[dict[str, Any]] = [
    # Wrong domain + wrong resource_family
    {
        "id": "uh-cal-01",
        "action": "what's on my calendar for next week",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "healthcare",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_domain+resource_family",
    },
    {
        "id": "uh-shop-01",
        "action": "add laundry detergent to the shopping list",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "enterprise",
        "resource_family": "event",
        "operation_hint": "create",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_domain+resource_family",
    },
    {
        "id": "uh-task-01",
        "action": "show me all tasks assigned to Riley",
        "expected_connector": "family.tasks",
        "expected_capability": "tool.read.tasks.list_tasks",
        "domain": "government",
        "resource_family": "reminder",
        "operation_hint": "read",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_domain+resource_family",
    },
    {
        "id": "uh-chore-01",
        "action": "who is doing vacuuming this week",
        "expected_connector": "family.chores",
        "expected_capability": "tool.read.chores.list_chores",
        "domain": "agriculture",
        "resource_family": "item",
        "operation_hint": "read",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_domain+resource_family",
    },
    {
        "id": "uh-rem-01",
        "action": "ping me when it's time to leave for soccer",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "wellness",
        "resource_family": "event",
        "operation_hint": "create",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_domain+resource_family",
    },
    # Wrong resource_family + wrong operation_hint
    {
        "id": "uh-cal-02",
        "action": "put Riley's ballet recital on the calendar for Friday",
        "expected_connector": "family.calendar",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_resource_family+operation_hint",
    },
    {
        "id": "uh-shop-02",
        "action": "take toilet paper off the costco list",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "create",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_resource_family+operation_hint",
    },
    {
        "id": "uh-task-02",
        "action": "check off the car maintenance todo",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "read",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_resource_family+operation_hint",
    },
    {
        "id": "uh-chore-02",
        "action": "nobody needs to do gutters this month",
        "expected_connector": "family.chores",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "read",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_resource_family+operation_hint",
    },
    {
        "id": "uh-rem-02",
        "action": "delete the weekly standup nudge",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "create",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_resource_family+operation_hint",
    },
    # Wrong domain + wrong operation_hint
    {
        "id": "uh-cal-03",
        "action": "move my haircut to Thursday 4pm",
        "expected_connector": "family.calendar",
        "expected_capability": "?",
        "domain": "retail",
        "resource_family": "event",
        "operation_hint": "read",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_domain+operation_hint",
    },
    {
        "id": "uh-shop-03",
        "action": "start a new list for camping supplies",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "education",
        "resource_family": "item",
        "operation_hint": "read",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_domain+operation_hint",
    },
    {
        "id": "uh-task-03",
        "action": "Jordan should handle the tax paperwork",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "finance",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_domain+operation_hint",
    },
    {
        "id": "uh-chore-03",
        "action": "the bathroom cleaning is done for this weekend",
        "expected_connector": "family.chores",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "delete",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_resource_family+operation_hint",
    },
    {
        "id": "uh-rem-03",
        "action": "let me know 10 minutes before Riley's practice ends",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "delete",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_resource_family+operation_hint",
    },
    # Wrong domain + wrong resource_family + wrong operation_hint (all three)
    {
        "id": "uh-cal-04",
        "action": "show my appointments for today",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "healthcare",
        "resource_family": "chore",
        "operation_hint": "create",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_all_three",
    },
    {
        "id": "uh-shop-04",
        "action": "what's on the grocery list",
        "expected_connector": "family.shopping",
        "expected_capability": "tool.read.shopping.list_items",
        "domain": "government",
        "resource_family": "reminder",
        "operation_hint": "delete",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_all_three",
    },
    {
        "id": "uh-task-04",
        "action": "list my pending tasks",
        "expected_connector": "family.tasks",
        "expected_capability": "tool.read.tasks.list_tasks",
        "domain": "enterprise",
        "resource_family": "event",
        "operation_hint": "create",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_all_three",
    },
    {
        "id": "uh-chore-04",
        "action": "what housework is pending",
        "expected_connector": "family.chores",
        "expected_capability": "tool.read.chores.list_chores",
        "domain": "agriculture",
        "resource_family": "item",
        "operation_hint": "delete",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_all_three",
    },
    {
        "id": "uh-rem-04",
        "action": "anything I should be reminded about today",
        "expected_connector": "family.reminders",
        "expected_capability": "tool.read.reminders.list_reminders",
        "domain": "wellness",
        "resource_family": "setting",
        "operation_hint": "update",
        "difficulty": "ultrahard",
        "hallucination_profile": "wrong_all_three",
    },
]

# ── HARDEST (20 queries): Adversarial — all hints wrong/empty/nonsensical ─
# Empty domain, empty resource_family, empty operation_hint.
# FTS5-only resolution.  Also includes multi-intent frames.

HARDEST_CORPUS: list[dict[str, Any]] = [
    # ── All hints empty ──
    {
        "id": "hs-cal-01",
        "action": "calendar this week",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "",
        "resource_family": "",
        "operation_hint": "",
        "difficulty": "hardest",
        "hallucination_profile": "all_empty",
    },
    {
        "id": "hs-shop-01",
        "action": "shopping list",
        "expected_connector": "family.shopping",
        "expected_capability": "tool.read.shopping.list_items",
        "domain": "",
        "resource_family": "",
        "operation_hint": "",
        "difficulty": "hardest",
        "hallucination_profile": "all_empty",
    },
    {
        "id": "hs-task-01",
        "action": "my tasks",
        "expected_connector": "family.tasks",
        "expected_capability": "tool.read.tasks.list_tasks",
        "domain": "",
        "resource_family": "",
        "operation_hint": "",
        "difficulty": "hardest",
        "hallucination_profile": "all_empty",
    },
    {
        "id": "hs-chore-01",
        "action": "chores this month",
        "expected_connector": "family.chores",
        "expected_capability": "tool.read.chores.list_chores",
        "domain": "",
        "resource_family": "",
        "operation_hint": "",
        "difficulty": "hardest",
        "hallucination_profile": "all_empty",
    },
    {
        "id": "hs-rem-01",
        "action": "reminders today",
        "expected_connector": "family.reminders",
        "expected_capability": "tool.read.reminders.list_reminders",
        "domain": "",
        "resource_family": "",
        "operation_hint": "",
        "difficulty": "hardest",
        "hallucination_profile": "all_empty",
    },
    {
        "id": "hs-set-01",
        "action": "family settings",
        "expected_connector": "family.family_settings",
        "expected_capability": "tool.read.family_settings.list_feature_flags",
        "domain": "",
        "resource_family": "",
        "operation_hint": "",
        "difficulty": "hardest",
        "hallucination_profile": "all_empty",
    },
    # ── Completely nonsensical hints ──
    {
        "id": "hs-cal-02",
        "action": "what does my week look like in terms of scheduled events",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "xyzzy",
        "resource_family": "plumbus",
        "operation_hint": "fleeb",
        "difficulty": "hardest",
        "hallucination_profile": "nonsensical_hints",
    },
    {
        "id": "hs-shop-02",
        "action": "put paper towels on the grocery run",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "narnia",
        "resource_family": "wardrobe",
        "operation_hint": "aslan",
        "difficulty": "hardest",
        "hallucination_profile": "nonsensical_hints",
    },
    {
        "id": "hs-task-02",
        "action": "I need to remember to file the insurance claim",
        "expected_connector": "family.tasks",
        "expected_capability": "?",
        "domain": "blarg",
        "resource_family": "snozzberry",
        "operation_hint": "gobblefunk",
        "difficulty": "hardest",
        "hallucination_profile": "nonsensical_hints",
    },
    {
        "id": "hs-chore-02",
        "action": "the floors need mopping this Saturday",
        "expected_connector": "family.chores",
        "expected_capability": "?",
        "domain": "",
        "resource_family": "floor_wax",
        "operation_hint": "polish",
        "difficulty": "hardest",
        "hallucination_profile": "nonsensical_hints",
    },
    {
        "id": "hs-rem-02",
        "action": "buzz me when it hits 6pm for dinner",
        "expected_connector": "family.reminders",
        "expected_capability": "?",
        "domain": "",
        "resource_family": "buzzer",
        "operation_hint": "vibrate",
        "difficulty": "hardest",
        "hallucination_profile": "nonsensical_hints",
    },
    # ── Multi-intent: one correct intent + one hallucinated intent ──
    # (RequestFrame with 2 intents; one is good, one is garbage)
    {
        "id": "hs-multi-01",
        "action": "add milk to shopping list AND schedule dentist for Friday",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "create",
        "difficulty": "hardest",
        "hallucination_profile": "multi_intent_mixed",
        "multi_intent": True,
        "intents": [
            {
                "action": "add milk to shopping list",
                "domain": "family",
                "resource_family": "item",
                "operation_hint": "create",
            },
            {
                "action": "schedule dentist for Friday",
                "domain": "healthcare",
                "resource_family": "plumbus",
                "operation_hint": "fleeb",
            },
        ],
    },
    {
        "id": "hs-multi-02",
        "action": "what tasks do I have AND remind me to call mom",
        "expected_connector": "family.tasks",
        "expected_capability": "tool.read.tasks.list_tasks",
        "domain": "family",
        "resource_family": "task",
        "operation_hint": "read",
        "difficulty": "hardest",
        "hallucination_profile": "multi_intent_mixed",
        "multi_intent": True,
        "intents": [
            {
                "action": "what tasks do I have",
                "domain": "family",
                "resource_family": "task",
                "operation_hint": "read",
            },
            {
                "action": "remind me to call mom",
                "domain": "xyzzy",
                "resource_family": "nonsense",
                "operation_hint": "garbage",
            },
        ],
    },
    {
        "id": "hs-multi-03",
        "action": "show chores AND what's on the shopping list",
        "expected_connector": "family.chores",
        "expected_capability": "tool.read.chores.list_chores",
        "domain": "family",
        "resource_family": "chore",
        "operation_hint": "read",
        "difficulty": "hardest",
        "hallucination_profile": "multi_intent_mixed",
        "multi_intent": True,
        "intents": [
            {
                "action": "show chores",
                "domain": "family",
                "resource_family": "chore",
                "operation_hint": "read",
            },
            {
                "action": "what's on the shopping list",
                "domain": "blarg",
                "resource_family": "",
                "operation_hint": "",
            },
        ],
    },
    {
        "id": "hs-multi-04",
        "action": "what reminders are set AND create a task for oil change",
        "expected_connector": "family.reminders",
        "expected_capability": "tool.read.reminders.list_reminders",
        "domain": "family",
        "resource_family": "reminder",
        "operation_hint": "read",
        "difficulty": "hardest",
        "hallucination_profile": "multi_intent_mixed",
        "multi_intent": True,
        "intents": [
            {
                "action": "what reminders are set",
                "domain": "family",
                "resource_family": "reminder",
                "operation_hint": "read",
            },
            {
                "action": "create a task for oil change",
                "domain": "",
                "resource_family": "",
                "operation_hint": "",
            },
        ],
    },
    # ── Vocabulary robustness (typos from original corpus, moved to hardest) ──
    {
        "id": "hs-vocab-01",
        "action": "what my calander look like in next 15 days",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "family",
        "resource_family": "event",
        "operation_hint": "read",
        "difficulty": "hardest",
        "hallucination_profile": "typo",
    },
    {
        "id": "hs-vocab-02",
        "action": "add cranberry winfus water to shopping",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "create",
        "difficulty": "hardest",
        "hallucination_profile": "typo",
    },
    {
        "id": "hs-vocab-03",
        "action": "add 2 loafs bread to groceries",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "family",
        "resource_family": "item",
        "operation_hint": "create",
        "difficulty": "hardest",
        "hallucination_profile": "typo",
    },
    # ── Empty string hints with clear action text ──
    {
        "id": "hs-cal-03",
        "action": "what appointments do I have tomorrow morning",
        "expected_connector": "family.calendar",
        "expected_capability": "tool.read.calendar.list_events",
        "domain": "",
        "resource_family": "",
        "operation_hint": "",
        "difficulty": "hardest",
        "hallucination_profile": "all_empty",
    },
    {
        "id": "hs-shop-03",
        "action": "add orange juice to the grocery store list",
        "expected_connector": "family.shopping",
        "expected_capability": "?",
        "domain": "",
        "resource_family": "",
        "operation_hint": "",
        "difficulty": "hardest",
        "hallucination_profile": "all_empty",
    },
]

# ── Combined corpus ──
TEST_CORPUS: list[dict[str, Any]] = (
    EASY_CORPUS + MEDIUM_CORPUS + HARD_CORPUS + ULTRAHARD_CORPUS + HARDEST_CORPUS
)

# ── Tier metadata ──
TIER_ORDER = ["easy", "medium", "hard", "ultrahard", "hardest"]
TIER_LABELS = {
    "easy": "EASY (perfect hints)",
    "medium": "MEDIUM (natural lang variance)",
    "hard": "HARD (1 field wrong)",
    "ultrahard": "ULTRAHARD (2+ fields wrong)",
    "hardest": "HARDEST (adversarial / all wrong)",
}


# ── Metrics ─────────────────────────────────────────────────────────────


@dataclass
class BenchmarkResult:
    query_id: str
    action: str
    expected_connector: str
    returned_connector: str | None
    expected_capability: str
    returned_capability: str | None
    returned_capabilities: list[str]
    verdict: str
    sub_reason: str | None
    latency_ms: float
    connector_match: bool
    capability_match: bool
    difficulty: str = ""
    hallucination_profile: str = ""


@dataclass
class BenchmarkReport:
    results: list[BenchmarkResult] = field(default_factory=list)
    total_queries: int = 0
    connector_top1: int = 0
    capability_top1: int = 0
    total_latency_ms: float = 0.0

    @property
    def connector_precision(self) -> float:
        """How often did we return the right connector?"""
        if not self.total_queries:
            return 0.0
        return self.connector_top1 / self.total_queries

    @property
    def capability_precision(self) -> float:
        """How often did we return the exact right capability?"""
        matching = sum(1 for r in self.results if r.capability_match)
        return matching / self.total_queries if self.total_queries else 0.0

    @property
    def mrr(self) -> float:
        """Mean Reciprocal Rank — rank of expected capability in returned list.

        MRR = 1/|Q| * Σ 1/rank_i, where rank_i is the 1-based position of the
        expected capability in ``allowed_capability_names``.  When expected
        capability is "?" we look for the expected connector anywhere in the
        returned capability names (by prefix match).
        """
        if not self.results:
            return 0.0
        total = 0.0
        for r in self.results:
            if not r.returned_capabilities:
                total += 0.0
                continue
            # Exact match
            if r.expected_capability != "?":
                try:
                    rank = r.returned_capabilities.index(r.expected_capability) + 1
                    total += 1.0 / rank
                    continue
                except ValueError:
                    pass
            # Connector-level prefix match (e.g. expected_connector="family.calendar"
            # should match any capability containing "family.calendar").
            for idx, cap_name in enumerate(r.returned_capabilities):
                if r.expected_connector in cap_name:
                    total += 1.0 / (idx + 1)
                    break
        return total / len(self.results)

    @property
    def avg_latency_ms(self) -> float:
        if not self.total_queries:
            return 0.0
        return self.total_latency_ms / self.total_queries

    @property
    def blocked_rate(self) -> float:
        """Rate of hard-blocks (verdict != can_execute AND not missing_required_params)."""
        blocked = sum(
            1
            for r in self.results
            if r.verdict not in ("can_execute", "missing_required_params", "can_execute_with_gate")
        )
        return blocked / self.total_queries if self.total_queries else 0.0


# ── Resolver runner ────────────────────────────────────────────────────


def _build_frame(query: dict) -> Any:
    """Build a proper RequestFrame (not a raw dict).

    For multi-intent queries (``multi_intent=True``), uses the explicit
    ``intents`` list from the query dict.  For single-intent queries,
    builds one intent from the top-level fields.
    """
    from k1.fabric.resolver.request_frame import (
        RequestFrame,
        RequestFrameIntent,
    )

    qid = query["id"]

    if query.get("multi_intent"):
        raw_intents = query.get("intents", [])
    else:
        raw_intents = [
            {
                "action": query["action"],
                "domain": query.get("domain", ""),
                "resource_family": query.get("resource_family", ""),
                "operation_hint": query.get("operation_hint", ""),
            }
        ]

    intents = [
        RequestFrameIntent(
            intent_id=f"intent-{qid}-{i}",
            action=ri.get("action", ""),
            domain=ri.get("domain", ""),
            operation_hint=ri.get("operation_hint", ""),
            resource_kind_hint=ri.get("resource_family", ""),
        )
        for i, ri in enumerate(raw_intents)
    ]

    return RequestFrame(
        request_id="req-" + qid,
        task_id="task-" + qid,
        trace_id="trace-" + qid,
        actor_id="alex",
        space_id="family:smith",
        intents=intents,
    )


def _extract_connector(envelope: Any) -> str | None:
    """Extract connector_id from the resolution envelope."""
    bb = envelope.binding_bundle
    if bb is not None and bb.primary is not None:
        return bb.primary.connector_id
    # Fallback: first execution plan step's connector_id
    plan = envelope.execution_plan
    if plan:
        return plan[0].get("connector_id")
    return None


def _extract_primary_capability(envelope: Any) -> str | None:
    bb = envelope.binding_bundle
    if bb is not None and bb.primary is not None:
        return bb.primary.capability_name
    plan = envelope.execution_plan
    if plan:
        return plan[0].get("capability_name")
    return None


def _extract_all_capabilities(envelope: Any) -> list[str]:
    return list(envelope.allowed_capability_names)


def run_benchmark(knobs: Any | None = None, label: str = "") -> BenchmarkReport:
    """Boot kernel, apply knob config, run all test queries through resolve_situation, measure.

    Args:
        knobs: Optional KnobConfig to apply before running. None = baseline.
        label: Human-readable label for the report header.
    """

    # ── Boot kernel ──
    if label:
        print(f"\n{'═'*60}")
        print(f"  {label}")
        print(f"{'═'*60}")
    print("Booting kernel...")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from k1.concierge.config.kernel import KernelConfig
    from k1.kernel.bootstrap import start_kernel

    config = KernelConfig(
        test_mode=False,
        enable_fabric_stores=True,
        enable_family_tools=True,
        bridge_enabled=False,
        family_tool_service_paths=(
            "k1.tools.family.calendar.service:CalendarToolService",
            "k1.tools.family.tasks.service:TasksToolService",
            "k1.tools.family.reminders.service:RemindersToolService",
            "k1.tools.family.chores.service:ChoresToolService",
            "k1.tools.family.shopping.service:ShoppingToolService",
            "k1.tools.family.family_settings.service:FamilySettingsService",
        ),
        global_projection_db_path=":memory:",
    )
    kernel = asyncio.run(start_kernel(config))
    fabric = kernel._service._shared_fabric
    resolver = fabric.situated_resolver
    # Suppress prompt pack builder — benchmark only measures resolution accuracy,
    # not prompt pack integrity.  The builder's redaction check rejects envelopes
    # containing optional_inputs.description (a legitimate security guard), but
    # the resolution envelope itself is already fully constructed by this point.
    resolver.prompt_pack_builder = None

    # ── Apply knob configuration ──
    if knobs is not None:
        resolver.configure(knobs)
        print(
            f"Knobs: domain={knobs.domain_mode} return={knobs.return_mode} "
            f"fallback={knobs.fallback_mode} gate={knobs.gate_mode}"
        )

    print(f"Kernel booted. Resolver: {type(resolver).__name__}")

    report = BenchmarkReport()
    report.total_queries = len(TEST_CORPUS)

    for query in TEST_CORPUS:
        qid = query["id"]
        frame = _build_frame(query)

        t0 = time.perf_counter()
        try:
            from k1.fabric.resolver.situated_resolver import ResolveSituationRequest

            req = ResolveSituationRequest(
                request_id="req-" + qid,
                frame=frame,
                actor_id="alex",
                session_id=f"bench-{qid}",
                space_id="family:smith",
                tier="LOW",
                safety_band="GREEN",
            )
            envelope = resolver.resolve(req)
        except Exception as exc:
            print(f"  {qid}: ERROR — {exc}")
            envelope = None
        latency_ms = (time.perf_counter() - t0) * 1000

        if envelope is None:
            returned_connector = None
            returned_capability = None
            returned_capabilities = []
            verdict = "error"
            sub_reason = "exception"
        else:
            returned_connector = _extract_connector(envelope)
            returned_capability = _extract_primary_capability(envelope)
            returned_capabilities = _extract_all_capabilities(envelope)
            verdict = envelope.verdict
            sub_reason = envelope.sub_reason

        connector_match = returned_connector == query["expected_connector"]
        cap_match = (
            query["expected_capability"] != "?"
            and returned_capability == query["expected_capability"]
        )

        result = BenchmarkResult(
            query_id=qid,
            action=query["action"],
            expected_connector=query["expected_connector"],
            returned_connector=returned_connector,
            expected_capability=query["expected_capability"],
            returned_capability=returned_capability,
            returned_capabilities=returned_capabilities,
            verdict=verdict,
            sub_reason=sub_reason,
            latency_ms=latency_ms,
            connector_match=connector_match,
            capability_match=cap_match,
            difficulty=query.get("difficulty", ""),
            hallucination_profile=query.get("hallucination_profile", ""),
        )
        report.results.append(result)

        if connector_match:
            report.connector_top1 += 1
        if cap_match:
            report.capability_top1 += 1
        report.total_latency_ms += latency_ms

        # Status: tool-level match is primary. Connector-only match (right aisle,
        # wrong product) is ⚠.  Wrong connector is ✗.
        blocked = verdict not in ("can_execute", "missing_required_params", "can_execute_with_gate")
        if blocked:
            status = "✗"
        elif cap_match:
            status = "✓"
        elif connector_match:
            status = "⚠"  # right connector, wrong tool
        else:
            status = "✗"

        tool_str = returned_capability or "NONE"
        # Truncate capability name for display
        if len(tool_str) > 38:
            tool_str = "…" + tool_str[-37:]
        print(
            f"  {status} {qid}: {query['action'][:48]:48s} "
            f"→ {tool_str:38s} "
            f"({latency_ms:5.1f}ms) {verdict}"
        )

    # ── Tier-level breakdown ──
    print("\n── Tier Breakdown (★ = tool accuracy, primary) ──")
    print(
        f"  {'Tier':12s} {'Q':>4s} {'★Tool':>7s} {'Tool%':>7s} {'Conn':>6s} {'Conn%':>7s} {'MRR':>6s} {'ms':>6s} {'Blk':>4s}"
    )
    print(f"  {'─'*12} {'─'*4} {'─'*7} {'─'*7} {'─'*6} {'─'*7} {'─'*6} {'─'*6} {'─'*4}")
    for tier in TIER_ORDER:
        tier_results = [r for r in report.results if r.difficulty == tier]
        if not tier_results:
            continue
        n = len(tier_results)
        tool_ok = sum(1 for r in tier_results if r.capability_match)
        conn_ok = sum(1 for r in tier_results if r.connector_match)
        # Tier-level MRR
        tier_mrr = 0.0
        for r in tier_results:
            if not r.returned_capabilities:
                continue
            found = False
            if r.expected_capability != "?":
                try:
                    rank = r.returned_capabilities.index(r.expected_capability) + 1
                    tier_mrr += 1.0 / rank
                    found = True
                except ValueError:
                    pass
            if not found:
                for idx, cap_name in enumerate(r.returned_capabilities):
                    if r.expected_connector in cap_name:
                        tier_mrr += 1.0 / (idx + 1)
                        break
        tier_mrr = tier_mrr / n if n else 0.0
        avg_lat = sum(r.latency_ms for r in tier_results) / n if n else 0
        blocked = sum(
            1
            for r in tier_results
            if r.verdict not in ("can_execute", "missing_required_params", "can_execute_with_gate")
        )
        label = TIER_LABELS.get(tier, tier)
        print(
            f"  {label:12s} {n:>4d} {tool_ok:>7d} {tool_ok/n*100:>6.1f}% "
            f"{conn_ok:>6d} {conn_ok/n*100:>6.1f}% {tier_mrr:>6.3f} {avg_lat:>6.1f} {blocked:>4d}"
        )

    # ── Per-connector breakdown ──
    print("\n── Per-Connector Breakdown (★ = tool accuracy) ──")
    connectors = sorted(set(q["expected_connector"] for q in TEST_CORPUS))
    for conn in connectors:
        conn_results = [r for r in report.results if r.expected_connector == conn]
        tool_hits = sum(1 for r in conn_results if r.capability_match)
        conn_hits = sum(1 for r in conn_results if r.connector_match)
        avg_lat = sum(r.latency_ms for r in conn_results) / len(conn_results) if conn_results else 0
        blocked = sum(
            1
            for r in conn_results
            if r.verdict not in ("can_execute", "missing_required_params", "can_execute_with_gate")
        )
        print(
            f"  {conn:30s}  ★{tool_hits}/{len(conn_results)} ({tool_hits/len(conn_results)*100:5.1f}%)  "
            f"conn={conn_hits}/{len(conn_results)}  "
            f"avg {avg_lat:5.1f}ms  blocked={blocked}"
        )

    # ── Final report ──
    print("\n═══ BENCHMARK REPORT ═══")
    print(f"  Total queries:           {report.total_queries}")
    print(
        f"  ★ Tool Top-1:             {report.capability_top1}/{report.total_queries} "
        f"({report.capability_precision*100:.1f}%)  ← PRIMARY METRIC"
    )
    print(
        f"    Connector Top-1:        {report.connector_top1}/{report.total_queries} "
        f"({report.connector_precision*100:.1f}%)  ← diagnostic only"
    )
    print(f"    MRR (tool):             {report.mrr:.4f}")
    print(f"    Avg latency:            {report.avg_latency_ms:.1f}ms")
    print(f"    Blocked rate:           {report.blocked_rate*100:.1f}%")
    print("    Verdict distribution:")
    verdicts = Counter(r.verdict for r in report.results)
    for v, c in verdicts.most_common():
        print(f"    {v}: {c}")

    # ── Failures ──
    tool_failures = [r for r in report.results if not r.capability_match]
    conn_failures = [r for r in tool_failures if not r.connector_match]
    aisle_failures = [r for r in tool_failures if r.connector_match]  # right connector, wrong tool

    if tool_failures:
        print(f"\n── Tool Failures ({len(tool_failures)}/{report.total_queries}) ──")
        if conn_failures:
            print(f"  Wrong connector ({len(conn_failures)}):")
            for r in conn_failures:
                print(
                    f"    {r.query_id}: '{r.action[:55]}' → "
                    f"got {r.returned_connector or 'NONE'}, expected {r.expected_connector} "
                    f"[{r.difficulty}] ({r.verdict}: {r.sub_reason})"
                )
        if aisle_failures:
            print(f"  Right connector, wrong tool ({len(aisle_failures)}):")
            for r in aisle_failures:
                print(
                    f"    {r.query_id}: '{r.action[:55]}' → "
                    f"got {r.returned_capability or 'NONE'}, expected {r.expected_capability} "
                    f"[{r.difficulty}] ({r.verdict}: {r.sub_reason})"
                )

    return report


if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path

    # Ensure repo root is on path before any k1 imports
    _repo_root = str(_Path(__file__).resolve().parent.parent)
    if _repo_root not in _sys.path:
        _sys.path.insert(0, _repo_root)

    from k1.fabric.resolver.knobs import BASELINE, HYPOTHESIS_COMBO

    # ── Parse --knobs argument ──
    knob_name = "baseline"
    for arg in _sys.argv[1:]:
        if arg.startswith("--knobs="):
            knob_name = arg.split("=", 1)[1]
        elif arg == "--baseline":
            knob_name = "baseline"
        elif arg == "--hypothesis":
            knob_name = "hypothesis"
        elif arg == "--all":
            knob_name = "all"

    if knob_name == "all":
        # Run both and compare
        baseline_report = run_benchmark(BASELINE, "BASELINE (current production settings)")
        hypo_report = run_benchmark(
            HYPOTHESIS_COMBO, "HYPOTHESIS COMBO (no-domain + all-tools + return-all + advisory)"
        )
        print(f"\n{'═'*60}")
        print("  COMPARISON")
        print(f"{'═'*60}")
        print(f"  {'Metric':30s} {'BASELINE':>12s} {'HYPOTHESIS':>12s} {'Δ':>10s}")
        print(f"  {'─'*30} {'─'*12} {'─'*12} {'─'*10}")
        for metric, base_val, hypo_val in [
            (
                "★ Tool Accuracy",
                baseline_report.capability_precision * 100,
                hypo_report.capability_precision * 100,
            ),
            (
                "  Connector Accuracy",
                baseline_report.connector_precision * 100,
                hypo_report.connector_precision * 100,
            ),
            ("  MRR", baseline_report.mrr, hypo_report.mrr),
            ("  Blocked Rate", baseline_report.blocked_rate * 100, hypo_report.blocked_rate * 100),
        ]:
            delta = hypo_val - base_val
            symbol = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            print(
                f"  {metric:30s} {base_val:>11.1f}% {hypo_val:>11.1f}% {symbol}{abs(delta):>8.1f}%"
            )
    elif knob_name == "hypothesis":
        run_benchmark(
            HYPOTHESIS_COMBO, "HYPOTHESIS COMBO (no-domain + all-tools + return-all + advisory)"
        )
    else:
        run_benchmark(BASELINE, "BASELINE (current production settings)")
