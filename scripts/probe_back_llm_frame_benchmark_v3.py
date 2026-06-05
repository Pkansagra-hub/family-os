"""Back LLM Frame Extraction Benchmark v3 — LLM-as-Judge Evaluation.

PRINCIPLE:
  - Phase 1 (Generate): LLM extracts structured intents from utterance + context.
  - Phase 2 (Judge): A SEPARATE LLM call evaluates each output against business rules.
    The judge receives the original utterance, domain context, expected ground truth,
    the actual LLM output, and a detailed rubric. It returns pass/fail + reasoning
    per dimension. NO fuzzy string matching. NO semantic bridge. NO keyword heuristics.

  - 50 scenarios across 5 domains: FamilyOS, Enterprise, Government, Agriculture, Healthcare.
  - Two scoring columns: string-matcher score AND LLM judge score — side by side.

Usage:
  python scripts/probe_back_llm_frame_benchmark_v3.py
  # Mode 1: dry-run. Mode 2: LLM generate + LLM judge (production).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract_v2.model_client import (
    ModelClient,
    create_model_client_from_env,
)

# ═══════════════════════════════════════════════════════════════════
# DOMAIN CONTEXTS & SCENARIOS (same as v2)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DomainContext:
    domain_id: str
    domain_label: str
    self_model: dict[str, Any]
    roster: dict[str, Any]
    services: list[dict[str, str]]
    grounding: dict[str, Any]
    beliefs: list[dict[str, str]]
    task_state: dict[str, Any]


def _make_family() -> DomainContext:
    return DomainContext(
        domain_id="family",
        domain_label="FamilyOS — Household Management",
        self_model={
            "actor_id": "person.jordan_parent",
            "display_name": "Jordan",
            "role": "parent",
            "age_band": "adult",
            "pronouns": "they/them",
            "preferences": {"dietary": "vegetarian", "notification_tone": "gentle"},
            "goals": [
                {"goal_id": "g1", "summary": "Get kids to school on time", "horizon": "this_week"},
                {"goal_id": "g2", "summary": "Plan summer camping trip", "horizon": "this_quarter"},
            ],
            "routines": [
                {"name": "School morning prep", "schedule": "weekdays 7:00-8:15am"},
                {"name": "Sunday family dinner", "schedule": "Sundays 6:00pm"},
            ],
        },
        roster={
            "space_id": "home_001",
            "members": [
                {
                    "person_id": "person.taylor",
                    "display_name": "Taylor",
                    "role": "parent",
                    "age_band": "adult",
                    "aliases": ["Tay", "Mom", "Dad"],
                },
                {
                    "person_id": "person.riley",
                    "display_name": "Riley",
                    "role": "child",
                    "age_band": "child",
                    "aliases": ["Riles", "RK"],
                },
                {
                    "person_id": "person.morgan",
                    "display_name": "Morgan",
                    "role": "child",
                    "age_band": "teen",
                    "aliases": ["Morg", "Mo"],
                },
                {
                    "person_id": "person.grandma_sue",
                    "display_name": "Grandma Sue",
                    "role": "guardian",
                    "age_band": "adult",
                    "aliases": ["Grandma", "Nana", "Sue"],
                },
                {
                    "person_id": "person.casey_friend",
                    "display_name": "Casey",
                    "role": "guest",
                    "age_band": "child",
                    "aliases": ["Case", "Casey"],
                },
            ],
        },
        services=[
            {
                "service_id": "calendar",
                "label": "Family Calendar",
                "description": "Shared family calendar. Events, appointments, schedules, practices, recitals, lessons, meetings. Time-based with attendees and recurrence.",
                "resource_kinds": ["calendar_event"],
            },
            {
                "service_id": "tasks",
                "label": "Family Tasks",
                "description": "One-shot to-dos assigned to specific people. Has due dates. For accountability: homework, cleanup, errands. NOT recurring.",
                "resource_kinds": ["task"],
            },
            {
                "service_id": "reminders",
                "label": "Reminders",
                "description": "Time or location-triggered notifications. Cross-person addressing. Ping, nudge, notify someone.",
                "resource_kinds": ["reminder"],
            },
            {
                "service_id": "chores",
                "label": "Chores",
                "description": "Recurring household responsibilities. Gamified with rewards. Completion tracked. Parents verify.",
                "resource_kinds": ["chore"],
            },
            {
                "service_id": "shopping",
                "label": "Shopping List",
                "description": "Shared grocery and general shopping list. Live-sync across family. Meal-plan linked.",
                "resource_kinds": ["shopping_item"],
            },
        ],
        grounding={
            "now_utc": "2026-06-03T14:30:00Z",
            "now_local": "2026-06-03T10:30:00-04:00",
            "day_of_week": "Wednesday",
            "time_of_day": "morning",
            "timezone": "America/New_York",
            "place_label": "Home — Kitchen",
            "device_surface": "mobile",
            "windows": {
                "today": "2026-06-03",
                "tomorrow": "2026-06-04",
                "this_week": "2026-06-01 to 2026-06-07",
                "next_week": "2026-06-08 to 2026-06-14",
                "this_weekend": "2026-06-06 to 2026-06-07",
            },
        },
        beliefs=[
            {
                "subject": "Riley",
                "predicate": "has_activity",
                "object": "soccer practice",
                "temporal": "Tuesdays and Thursdays 4pm",
            },
            {
                "subject": "Morgan",
                "predicate": "has_activity",
                "object": "piano lessons",
                "temporal": "Wednesdays 3pm",
            },
            {"subject": "Morgan", "predicate": "has_allergy", "object": "peanuts"},
            {"subject": "Grandma Sue", "predicate": "visiting", "object": "this_weekend"},
        ],
        task_state={
            "active": [
                {"task_id": "t1", "summary": "Schedule Riley dentist checkup", "status": "pending"}
            ],
            "completed": [
                {
                    "task_id": "t0",
                    "summary": "Book soccer field for practice",
                    "status": "completed",
                }
            ],
        },
    )


def _make_enterprise() -> DomainContext:
    return DomainContext(
        domain_id="enterprise",
        domain_label="Enterprise — Workplace Productivity",
        self_model={
            "actor_id": "person.pat_smith",
            "display_name": "Pat Smith",
            "role": "engineering_manager",
            "department": "Platform Engineering",
            "direct_reports": ["person.dev_alex", "person.dev_jordan", "person.dev_riya"],
            "preferences": {"working_hours": "9am-6pm ET", "focus_blocks": "10am-12pm"},
        },
        roster={
            "org_id": "org_acme_corp",
            "members": [
                {
                    "person_id": "person.ceo_chen",
                    "display_name": "CEO Chen",
                    "role": "executive",
                    "department": "Executive",
                    "aliases": ["Chen", "CEO"],
                },
                {
                    "person_id": "person.dev_alex",
                    "display_name": "Alex Dev",
                    "role": "senior_engineer",
                    "department": "Platform Engineering",
                    "aliases": ["Alex", "Al"],
                },
                {
                    "person_id": "person.dev_jordan",
                    "display_name": "Jordan Dev",
                    "role": "engineer",
                    "department": "Platform Engineering",
                    "aliases": ["Jordan", "Jord"],
                },
                {
                    "person_id": "person.dev_riya",
                    "display_name": "Riya Dev",
                    "role": "engineer",
                    "department": "Platform Engineering",
                    "aliases": ["Riya", "Ri"],
                },
                {
                    "person_id": "person.pm_taylor",
                    "display_name": "Taylor PM",
                    "role": "product_manager",
                    "department": "Product",
                    "aliases": ["Taylor", "Tay"],
                },
                {
                    "person_id": "person.designer_sam",
                    "display_name": "Sam Design",
                    "role": "designer",
                    "department": "Design",
                    "aliases": ["Sam", "Sammy"],
                },
            ],
        },
        services=[
            {
                "service_id": "calendar",
                "label": "Work Calendar",
                "description": "Corporate calendar. Meetings, standups, reviews, 1:1s. Has attendees, conference rooms, recurrence, RSVP tracking.",
                "resource_kinds": ["meeting", "calendar_event"],
            },
            {
                "service_id": "tasks",
                "label": "Project Tracker",
                "description": "Sprint tasks, bugs, feature requests. Assigned to people. Has status (todo/in_progress/review/done), priority, sprint, epic.",
                "resource_kinds": ["task", "bug", "feature"],
            },
            {
                "service_id": "docs",
                "label": "Document Hub",
                "description": "Shared documents, design specs, runbooks, RFCs. Collaborative editing. Has authors, reviewers, approval status.",
                "resource_kinds": ["document", "spec", "runbook"],
            },
            {
                "service_id": "tickets",
                "label": "IT Helpdesk",
                "description": "Support tickets for IT, HR, facilities. Has priority (P0-P4), assignee, SLA, category.",
                "resource_kinds": ["ticket"],
            },
            {
                "service_id": "chat",
                "label": "Team Chat",
                "description": "Real-time messaging. Channels, threads, DMs. Searchable history. File sharing.",
                "resource_kinds": ["message", "channel"],
            },
        ],
        grounding={
            "now_utc": "2026-06-03T18:30:00Z",
            "now_local": "2026-06-03T14:30:00-04:00",
            "day_of_week": "Wednesday",
            "time_of_day": "afternoon",
            "timezone": "America/New_York",
            "place_label": "Office — Desk 42B",
            "device_surface": "laptop",
            "windows": {
                "today": "2026-06-03",
                "tomorrow": "2026-06-04",
                "this_week": "2026-06-01 to 2026-06-07",
                "next_week": "2026-06-08 to 2026-06-14",
            },
        },
        beliefs=[
            {
                "subject": "Alex Dev",
                "predicate": "owns",
                "object": "auth service migration",
                "temporal": "Q2 2026",
            },
            {
                "subject": "Jordan Dev",
                "predicate": "on_call",
                "object": "this week",
                "temporal": "2026-06-01 to 2026-06-07",
            },
            {
                "subject": "Riya Dev",
                "predicate": "working_on",
                "object": "API rate limiting",
                "temporal": "sprint 23",
            },
        ],
        task_state={
            "active": [
                {"task_id": "t10", "summary": "Review Alex's auth PR", "status": "in_progress"},
                {
                    "task_id": "t11",
                    "summary": "Write quarterly performance reviews",
                    "status": "pending",
                },
            ],
            "completed": [
                {"task_id": "t9", "summary": "Sprint planning for sprint 24", "status": "completed"}
            ],
        },
    )


def _make_government() -> DomainContext:
    return DomainContext(
        domain_id="government",
        domain_label="Government — Civic Services",
        self_model={
            "actor_id": "person.clerk_maria",
            "display_name": "Maria Clerk",
            "role": "city_clerk",
            "department": "Permits & Licensing",
            "jurisdiction": "City of Springfield",
        },
        roster={
            "org_id": "city_springfield",
            "members": [
                {
                    "person_id": "person.mayor_kim",
                    "display_name": "Mayor Kim",
                    "role": "executive",
                    "department": "Mayor's Office",
                    "aliases": ["Mayor", "Kim"],
                },
                {
                    "person_id": "person.inspector_jones",
                    "display_name": "Inspector Jones",
                    "role": "building_inspector",
                    "department": "Building Safety",
                    "aliases": ["Jones", "Inspector"],
                },
                {
                    "person_id": "person.planner_reed",
                    "display_name": "Planner Reed",
                    "role": "urban_planner",
                    "department": "Planning",
                    "aliases": ["Reed", "Planner"],
                },
            ],
            "citizens": [
                {
                    "person_id": "citizen.john_doe",
                    "display_name": "John Doe",
                    "aliases": ["John", "Mr. Doe"],
                    "address": "123 Main St",
                },
                {
                    "person_id": "citizen.jane_smith",
                    "display_name": "Jane Smith",
                    "aliases": ["Jane", "Ms. Smith"],
                    "address": "456 Oak Ave",
                },
            ],
        },
        services=[
            {
                "service_id": "permits",
                "label": "Permit System",
                "description": "Building permits, zoning permits, event permits. Has application status, inspector assignments, fee tracking, approval chain.",
                "resource_kinds": ["permit", "building_permit", "event_permit"],
            },
            {
                "service_id": "licenses",
                "label": "Business Licenses",
                "description": "Business license applications, renewals, inspections. Has NAICS codes, expiration dates, compliance status.",
                "resource_kinds": ["license", "business_license"],
            },
            {
                "service_id": "violations",
                "label": "Code Violations",
                "description": "Code enforcement cases. Has violation type, property, inspector, hearing dates, fine status.",
                "resource_kinds": ["violation", "case"],
            },
            {
                "service_id": "meetings",
                "label": "Public Meetings",
                "description": "City council meetings, planning board hearings, community forums. Has agendas, minutes, public comment periods.",
                "resource_kinds": ["meeting", "hearing"],
            },
            {
                "service_id": "records",
                "label": "Public Records",
                "description": "FOIA requests, document retrieval, archive search. Has request status, responsive documents, fee estimates.",
                "resource_kinds": ["record", "foia_request"],
            },
        ],
        grounding={
            "now_utc": "2026-06-03T16:00:00Z",
            "now_local": "2026-06-03T11:00:00-05:00",
            "day_of_week": "Wednesday",
            "time_of_day": "morning",
            "timezone": "America/Chicago",
            "place_label": "City Hall — Permits Desk",
            "device_surface": "desktop",
            "windows": {
                "today": "2026-06-03",
                "tomorrow": "2026-06-04",
                "this_week": "2026-06-01 to 2026-06-07",
                "next_week": "2026-06-08 to 2026-06-14",
            },
        },
        beliefs=[
            {
                "subject": "123 Main St",
                "predicate": "has_pending",
                "object": "building permit application",
                "temporal": "submitted 2026-05-20",
            },
            {
                "subject": "Inspector Jones",
                "predicate": "assigned_to",
                "object": "downtown corridor inspections",
                "temporal": "June 2026",
            },
            {"subject": "City Council", "predicate": "meets", "object": "every Tuesday at 7pm"},
        ],
        task_state={
            "active": [
                {
                    "task_id": "t20",
                    "summary": "Process 123 Main St deck permit",
                    "status": "in_progress",
                },
                {
                    "task_id": "t21",
                    "summary": "Schedule fire inspection for 456 Oak Ave business license",
                    "status": "pending",
                },
            ],
            "completed": [],
        },
    )


def _make_agriculture() -> DomainContext:
    return DomainContext(
        domain_id="agriculture",
        domain_label="Agriculture — Farm Management",
        self_model={
            "actor_id": "person.farmer_lee",
            "display_name": "Lee Farmer",
            "role": "farm_owner_operator",
            "farm_name": "Green Acres Family Farm",
            "farm_size_acres": 320,
            "primary_crops": ["corn", "soybeans", "winter_wheat"],
            "livestock": ["beef_cattle_40_head"],
        },
        roster={
            "farm_id": "farm_green_acres",
            "workers": [
                {
                    "person_id": "person.worker_carlos",
                    "display_name": "Carlos",
                    "role": "farmhand",
                    "aliases": ["Carlos", "Los"],
                    "skills": ["equipment_operation", "irrigation"],
                },
                {
                    "person_id": "person.worker_emma",
                    "display_name": "Emma",
                    "role": "farmhand",
                    "aliases": ["Emma", "Em"],
                    "skills": ["livestock_care", "harvesting"],
                },
                {
                    "person_id": "person.vet_sarah",
                    "display_name": "Dr. Sarah",
                    "role": "veterinarian",
                    "aliases": ["Sarah", "Doc", "Vet"],
                    "external": True,
                },
                {
                    "person_id": "person.agronomist_raj",
                    "display_name": "Raj Agronomist",
                    "role": "agronomist",
                    "aliases": ["Raj", "Agronomist"],
                    "external": True,
                },
            ],
            "equipment": [
                {
                    "equip_id": "tractor_jd_8220",
                    "label": "John Deere 8220",
                    "status": "operational",
                },
                {
                    "equip_id": "combine_case_8250",
                    "label": "Case IH 8250 Combine",
                    "status": "needs_maintenance",
                },
            ],
        },
        services=[
            {
                "service_id": "field_planner",
                "label": "Field Planner",
                "description": "Crop rotation planning, planting schedules, field mapping. Tracks soil conditions, yield history.",
                "resource_kinds": ["planting_plan", "field", "crop_schedule"],
            },
            {
                "service_id": "livestock",
                "label": "Livestock Manager",
                "description": "Herd tracking, vaccination schedules, breeding records, feed orders, weight tracking. Vet visit scheduling.",
                "resource_kinds": ["herd_record", "vaccination", "feed_order", "vet_visit"],
            },
            {
                "service_id": "equipment_log",
                "label": "Equipment Log",
                "description": "Maintenance schedules, repair history, fuel usage, hours tracking. Service reminders and parts inventory.",
                "resource_kinds": ["maintenance_log", "repair_ticket", "fuel_record"],
            },
            {
                "service_id": "weather",
                "label": "Ag Weather",
                "description": "Field-level weather forecasts, growing degree days, frost alerts, precipitation tracking. 10-day outlook.",
                "resource_kinds": ["weather_forecast", "frost_alert"],
            },
            {
                "service_id": "inventory",
                "label": "Farm Inventory",
                "description": "Seed, fertilizer, chemical, and feed inventory. Tracks quantities, reorder thresholds. Supplier ordering.",
                "resource_kinds": [
                    "seed_inventory",
                    "fertilizer_inventory",
                    "feed_inventory",
                    "supply_order",
                ],
            },
        ],
        grounding={
            "now_utc": "2026-06-03T14:30:00Z",
            "now_local": "2026-06-03T09:30:00-05:00",
            "day_of_week": "Wednesday",
            "time_of_day": "morning",
            "timezone": "America/Chicago",
            "place_label": "Farm Office",
            "device_surface": "tablet",
            "windows": {
                "today": "2026-06-03",
                "tomorrow": "2026-06-04",
                "this_week": "2026-06-01 to 2026-06-07",
                "next_week": "2026-06-08 to 2026-06-14",
            },
            "growing_season": "active — corn at V6 stage, soybeans at V3",
        },
        beliefs=[
            {
                "subject": "combine_case_8250",
                "predicate": "needs",
                "object": "hydraulic hose replacement",
                "temporal": "before harvest",
            },
            {
                "subject": "beef_cattle_40_head",
                "predicate": "due_for",
                "object": "annual vaccinations",
                "temporal": "next week",
            },
            {
                "subject": "Field 12",
                "predicate": "showing",
                "object": "signs of nitrogen deficiency",
            },
        ],
        task_state={
            "active": [
                {
                    "task_id": "t30",
                    "summary": "Order hydraulic hose for combine",
                    "status": "pending",
                },
                {
                    "task_id": "t31",
                    "summary": "Schedule vet visit for herd vaccinations",
                    "status": "pending",
                },
            ],
            "completed": [],
        },
    )


def _make_healthcare() -> DomainContext:
    return DomainContext(
        domain_id="healthcare",
        domain_label="Healthcare — Clinical Practice",
        self_model={
            "actor_id": "person.dr_patel",
            "display_name": "Dr. Amara Patel",
            "role": "primary_care_physician",
            "specialty": "Family Medicine",
            "practice": "Oakwood Family Health Center",
        },
        roster={
            "practice_id": "oakwood_fhc",
            "staff": [
                {
                    "person_id": "person.nurse_jo",
                    "display_name": "Nurse Jo",
                    "role": "registered_nurse",
                    "aliases": ["Jo", "Nurse Jo"],
                },
                {
                    "person_id": "person.ma_kim",
                    "display_name": "Kim MA",
                    "role": "medical_assistant",
                    "aliases": ["Kim", "MA"],
                },
                {
                    "person_id": "person.dr_smith",
                    "display_name": "Dr. Smith",
                    "role": "cardiologist",
                    "aliases": ["Dr. Smith", "Smith", "Cardiology"],
                    "external": True,
                },
            ],
            "patients": [
                {
                    "patient_id": "pt.robert_kim",
                    "display_name": "Robert Kim",
                    "aliases": ["Robert", "Bob", "Mr. Kim"],
                    "age": 67,
                    "conditions": ["hypertension", "type_2_diabetes"],
                },
                {
                    "patient_id": "pt.maria_garcia",
                    "display_name": "Maria Garcia",
                    "aliases": ["Maria", "Ms. Garcia"],
                    "age": 34,
                    "conditions": ["asthma"],
                },
                {
                    "patient_id": "pt.james_wilson",
                    "display_name": "James Wilson",
                    "aliases": ["James", "Jim", "Mr. Wilson"],
                    "age": 52,
                    "conditions": ["hyperlipidemia", "gerd"],
                },
            ],
        },
        services=[
            {
                "service_id": "ehr",
                "label": "Electronic Health Records",
                "description": "Patient charts, medical history, lab results, imaging reports, progress notes. ICD-10 codes, medications list, allergies, vitals tracking.",
                "resource_kinds": ["patient_record", "lab_result", "progress_note", "medication"],
            },
            {
                "service_id": "scheduling",
                "label": "Appointment Scheduler",
                "description": "Patient appointments, follow-ups, physicals, specialist referrals. Has time slots, visit types, room assignments.",
                "resource_kinds": ["appointment", "follow_up", "referral"],
            },
            {
                "service_id": "prescriptions",
                "label": "E-Prescribing",
                "description": "Medication orders, refills, prior authorizations, drug interaction checks. Pharmacy routing.",
                "resource_kinds": ["prescription", "refill", "prior_auth"],
            },
            {
                "service_id": "labs",
                "label": "Lab Orders",
                "description": "Lab test ordering, specimen tracking, result review. CBC, metabolic panels, lipid panels, A1C.",
                "resource_kinds": ["lab_order", "lab_result"],
            },
            {
                "service_id": "messaging",
                "label": "Patient Messaging",
                "description": "Secure patient portal messages, staff messages, specialist consults. HIPAA compliant.",
                "resource_kinds": ["patient_message", "consult"],
            },
        ],
        grounding={
            "now_utc": "2026-06-03T15:00:00Z",
            "now_local": "2026-06-03T11:00:00-04:00",
            "day_of_week": "Wednesday",
            "time_of_day": "morning",
            "timezone": "America/New_York",
            "place_label": "Oakwood FHC — Exam Room 3",
            "device_surface": "tablet",
            "windows": {
                "today": "2026-06-03",
                "tomorrow": "2026-06-04",
                "this_week": "2026-06-01 to 2026-06-07",
                "next_week": "2026-06-08 to 2026-06-14",
            },
        },
        beliefs=[
            {
                "subject": "Robert Kim",
                "predicate": "due_for",
                "object": "A1C lab work",
                "temporal": "overdue by 2 weeks",
            },
            {
                "subject": "Maria Garcia",
                "predicate": "needs",
                "object": "asthma action plan review",
                "temporal": "this visit",
            },
            {
                "subject": "James Wilson",
                "predicate": "referred_to",
                "object": "cardiology (Dr. Smith)",
                "temporal": "2026-05-28",
            },
        ],
        task_state={
            "active": [
                {
                    "task_id": "t40",
                    "summary": "Review Robert Kim's lab results",
                    "status": "pending",
                },
                {
                    "task_id": "t41",
                    "summary": "Send James Wilson's records to Dr. Smith",
                    "status": "pending",
                },
            ],
            "completed": [],
        },
    )


ALL_DOMAIN_CONTEXTS: dict[str, DomainContext] = {
    "family": _make_family(),
    "enterprise": _make_enterprise(),
    "government": _make_government(),
    "agriculture": _make_agriculture(),
    "healthcare": _make_healthcare(),
}


# ═══════════════════════════════════════════════════════════════════
# 50 SCENARIOS (same as v2)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FrameScenario:
    id: str
    domain_id: str
    utterance: str
    description: str
    expected_operations: list[str]
    expected_resource_kinds: list[str | None]
    expected_persons: list[str | None]
    expected_time_required: bool
    intent_count: int
    needs_disambiguation: bool = False
    disambiguation_reason: str = ""


SCENARIOS: list[FrameScenario] = [
    # ── FAMILY (F01-F10) ──
    FrameScenario(
        "F01",
        "family",
        "Add dentist appointment for Riley next Monday at 3pm",
        "Simple calendar create with person + time",
        ["create"],
        ["calendar_event"],
        ["Riley"],
        True,
        1,
    ),
    FrameScenario(
        "F02",
        "family",
        "What's on the family calendar this weekend?",
        "Simple calendar read with time window",
        ["list"],
        ["calendar_event"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "F03",
        "family",
        "Remind Morgan to clean their room and buy groceries for Sunday dinner",
        "Two intents: reminder create + shopping create",
        ["create", "create"],
        ["reminder", "shopping_item"],
        ["Morgan", "me"],
        True,
        2,
    ),
    FrameScenario(
        "F04",
        "family",
        "Has Riley been good this week?",
        "Indirect: implies chore completion check",
        ["list"],
        ["chore"],
        ["Riley"],
        False,
        1,
    ),
    FrameScenario(
        "F05",
        "family",
        "Move Grandma Sue's visit reminder to Friday afternoon",
        "Update reminder with time change",
        ["update"],
        ["reminder"],
        ["Grandma Sue"],
        True,
        1,
    ),
    FrameScenario(
        "F06",
        "family",
        "What chores does Morgan have and what tasks are due?",
        "Two reads across different services",
        ["list", "list"],
        ["chore", "task"],
        ["Morgan"],
        False,
        2,
    ),
    FrameScenario(
        "F07",
        "family",
        "Schedule something for Taylor",
        "Missing info: what and when",
        ["create"],
        ["calendar_event"],
        ["Taylor"],
        True,
        1,
    ),
    FrameScenario(
        "F08",
        "family",
        "Remind me",
        "Missing info: what and when",
        ["create"],
        ["reminder"],
        ["me"],
        True,
        1,
    ),
    FrameScenario(
        "F09",
        "family",
        "Make sure Riley does homework before screen time",
        "Indirect: task creation with conditional dependency",
        ["create"],
        ["task"],
        ["Riley"],
        False,
        1,
    ),
    FrameScenario(
        "F10",
        "family",
        "Check if Casey and Morgan have conflicting plans on Saturday",
        "Cross-person calendar conflict check",
        ["list"],
        ["calendar_event"],
        ["Casey", "Morgan"],
        False,
        2,
    ),
    # ── ENTERPRISE (E01-E10) ──
    FrameScenario(
        "E01",
        "enterprise",
        "Schedule a 1:1 with Alex Dev for Thursday at 2pm",
        "Create meeting with person + time",
        ["create"],
        ["meeting"],
        ["Alex Dev"],
        True,
        1,
    ),
    FrameScenario(
        "E02",
        "enterprise",
        "What meetings do I have tomorrow?",
        "Read own calendar with time window",
        ["list"],
        ["meeting"],
        ["me"],
        False,
        1,
    ),
    FrameScenario(
        "E03",
        "enterprise",
        "Create a bug ticket for the login timeout issue and assign to Jordan Dev",
        "Create bug in project tracker with assignee",
        ["create"],
        ["bug"],
        ["Jordan Dev"],
        False,
        1,
    ),
    FrameScenario(
        "E04",
        "enterprise",
        "Show me all open P1 tickets assigned to my team",
        "Read high-priority tickets filtered by team",
        ["list"],
        ["ticket"],
        ["me"],
        False,
        1,
    ),
    FrameScenario(
        "E05",
        "enterprise",
        "Find the design spec for the new dashboard and share it with Taylor PM",
        "Read document + share/notify (2 intents)",
        ["list", "create"],
        ["document", "message"],
        ["me", "Taylor PM"],
        False,
        2,
    ),
    FrameScenario(
        "E06",
        "enterprise",
        "Submit an IT ticket — my laptop keeps crashing when I run Docker",
        "Create support ticket",
        ["create"],
        ["ticket"],
        ["me"],
        False,
        1,
    ),
    FrameScenario(
        "E07",
        "enterprise",
        "Who is on call this week?",
        "Read roster/on-call status",
        ["list"],
        ["ticket"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "E08",
        "enterprise",
        "Move the sprint review from Friday to next Monday and notify the team",
        "Update meeting + notify team (2 intents)",
        ["update", "create"],
        ["meeting", "message"],
        ["me", "me"],
        True,
        2,
    ),
    FrameScenario(
        "E09",
        "enterprise",
        "Review Alex's auth PR by end of day",
        "Implied task read/status check",
        ["list"],
        ["task"],
        ["Alex Dev"],
        False,
        1,
    ),
    FrameScenario(
        "E10",
        "enterprise",
        "Cancel the weekly standup for this week only",
        "Delete recurring meeting instance",
        ["delete"],
        ["meeting"],
        ["me"],
        False,
        1,
    ),
    # ── GOVERNMENT (G01-G10) ──
    FrameScenario(
        "G01",
        "government",
        "Look up the building permit for 123 Main Street",
        "Read permit by address",
        ["list"],
        ["permit"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "G02",
        "government",
        "Schedule a fire inspection for 456 Oak Avenue next Tuesday",
        "Create inspection appointment with time",
        ["create"],
        ["permit"],
        [],
        True,
        1,
    ),
    FrameScenario(
        "G03",
        "government",
        "Assign Inspector Jones to the downtown corridor cases",
        "Update case assignments",
        ["update"],
        ["violation"],
        ["Inspector Jones"],
        False,
        1,
    ),
    FrameScenario(
        "G04",
        "government",
        "What's on the city council agenda for next Tuesday's meeting?",
        "Read public meeting agenda with time",
        ["list"],
        ["meeting"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "G05",
        "government",
        "Process Jane Smith's business license renewal and notify her",
        "Update license + create notification (2 intents)",
        ["update", "create"],
        ["license", "message"],
        ["Jane Smith", "Jane Smith"],
        False,
        2,
    ),
    FrameScenario(
        "G06",
        "government",
        "Search for any open code violations on Oak Avenue",
        "Read violations by street",
        ["list"],
        ["violation"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "G07",
        "government",
        "Issue a parade permit for the July 4th committee — they submitted everything",
        "Create permit with approval",
        ["create"],
        ["permit"],
        [],
        True,
        1,
    ),
    FrameScenario(
        "G08",
        "government",
        "Find the FOIA request from John Doe about the zoning changes",
        "Read public records request by person",
        ["list"],
        ["record"],
        ["John Doe"],
        False,
        1,
    ),
    FrameScenario(
        "G09",
        "government",
        "Send the planning board minutes to Mayor Kim for review",
        "Share/update + create task (2 intents)",
        ["update", "create"],
        ["meeting", "task"],
        ["Mayor Kim", "Mayor Kim"],
        False,
        2,
    ),
    FrameScenario(
        "G10",
        "government",
        "What permits expire next month?",
        "Read permits with time window",
        ["list"],
        ["permit"],
        [],
        False,
        1,
    ),
    # ── AGRICULTURE (A01-A10) ──
    FrameScenario(
        "A01",
        "agriculture",
        "Order more soybean seeds for Field 5 — running low",
        "Create supply order",
        ["create"],
        ["seed_inventory"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "A02",
        "agriculture",
        "What's the 10-day weather outlook for the farm?",
        "Read weather forecast",
        ["list"],
        ["weather_forecast"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "A03",
        "agriculture",
        "Schedule Dr. Sarah for herd vaccinations next Wednesday morning",
        "Create vet visit with time + person",
        ["create"],
        ["vet_visit"],
        ["Dr. Sarah"],
        True,
        1,
    ),
    FrameScenario(
        "A04",
        "agriculture",
        "Log the John Deere 8220 oil change — it hit 500 hours",
        "Create maintenance log entry",
        ["create"],
        ["maintenance_log"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "A05",
        "agriculture",
        "Ask Raj to check Field 12 — I think the corn has nitrogen deficiency",
        "Create consultation request",
        ["create"],
        ["task"],
        ["Raj Agronomist"],
        False,
        1,
    ),
    FrameScenario(
        "A06",
        "agriculture",
        "Check what fertilizers we have in stock and order more if below reorder threshold",
        "Read inventory",
        ["list"],
        ["fertilizer_inventory"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "A07",
        "agriculture",
        "What equipment needs maintenance before harvest season?",
        "Read equipment logs filtered by status",
        ["list"],
        ["maintenance_log"],
        [],
        False,
        1,
    ),
    FrameScenario(
        "A08",
        "agriculture",
        "Move the combine repair to next week — the part won't arrive until Monday",
        "Update repair ticket with time change",
        ["update"],
        ["repair_ticket"],
        [],
        True,
        1,
    ),
    FrameScenario(
        "A09",
        "agriculture",
        "Send Emma to feed the cattle and log it",
        "Create task + log entry (2 intents)",
        ["create", "create"],
        ["task", "feed_inventory"],
        ["Emma", "Emma"],
        False,
        2,
    ),
    FrameScenario(
        "A10",
        "agriculture",
        "Is there a frost alert for tonight? We just planted soybeans in Field 7",
        "Read frost alert",
        ["list"],
        ["frost_alert"],
        [],
        False,
        1,
    ),
    # ── HEALTHCARE (H01-H10) ──
    FrameScenario(
        "H01",
        "healthcare",
        "Pull up Robert Kim's chart — I need his latest A1C results",
        "Read patient record + lab results",
        ["list"],
        ["lab_result"],
        ["Robert Kim"],
        False,
        1,
    ),
    FrameScenario(
        "H02",
        "healthcare",
        "Schedule a follow-up for Maria Garcia in 3 months for her asthma",
        "Create follow-up appointment with person + time",
        ["create"],
        ["follow_up"],
        ["Maria Garcia"],
        True,
        1,
    ),
    FrameScenario(
        "H03",
        "healthcare",
        "Prescribe lisinopril 10mg daily for Robert Kim, send to local pharmacy",
        "Create prescription",
        ["create"],
        ["prescription"],
        ["Robert Kim"],
        False,
        1,
    ),
    FrameScenario(
        "H04",
        "healthcare",
        "Send James Wilson's records to Dr. Smith in cardiology",
        "Share/transfer records to external provider",
        ["update"],
        ["patient_record"],
        ["James Wilson", "Dr. Smith"],
        False,
        1,
    ),
    FrameScenario(
        "H05",
        "healthcare",
        "Order a CBC and lipid panel for Robert Kim — fasting, schedule for Friday morning",
        "Create lab order + create appointment (2 intents)",
        ["create", "create"],
        ["lab_order", "appointment"],
        ["Robert Kim", "Robert Kim"],
        True,
        2,
    ),
    FrameScenario(
        "H06",
        "healthcare",
        "What patients am I seeing this afternoon?",
        "Read own appointment schedule",
        ["list"],
        ["appointment"],
        ["me"],
        False,
        1,
    ),
    FrameScenario(
        "H07",
        "healthcare",
        "Check if Maria Garcia's refill request went through — she called about her albuterol",
        "Read prescription refill status",
        ["list"],
        ["refill"],
        ["Maria Garcia"],
        False,
        1,
    ),
    FrameScenario(
        "H08",
        "healthcare",
        "Message Nurse Jo to room Robert Kim — he's early",
        "Create staff message",
        ["create"],
        ["patient_message"],
        ["Nurse Jo"],
        False,
        1,
    ),
    FrameScenario(
        "H09",
        "healthcare",
        "Add a note to James Wilson's chart: reports improved GERD on omeprazole 20mg",
        "Create progress note",
        ["create"],
        ["progress_note"],
        ["James Wilson"],
        False,
        1,
    ),
    FrameScenario(
        "H10",
        "healthcare",
        "Review all pending lab results and flag any abnormal values",
        "Read lab results with filter",
        ["list"],
        ["lab_result"],
        [],
        False,
        1,
    ),
]


# ═══════════════════════════════════════════════════════════════════
# CONTEXT BUILDER
# ═══════════════════════════════════════════════════════════════════


def build_context_block(ctx: DomainContext) -> str:
    parts: list[str] = []
    sm = ctx.self_model
    parts.append("== WHO YOU ARE (SELF MODEL) ==")
    parts.append(f"You are {sm['display_name']}.")
    role_info = f"Role: {sm['role']}"
    if sm.get("department"):
        role_info += f" | Department: {sm['department']}"
    if sm.get("specialty"):
        role_info += f" | Specialty: {sm['specialty']}"
    if sm.get("farm_name"):
        role_info += f" | Farm: {sm['farm_name']}"
    parts.append(role_info)
    if sm.get("preferences"):
        parts.append("Preferences: " + json.dumps(sm["preferences"]))
    if sm.get("goals"):
        parts.append("Active goals:")
        for g in sm["goals"]:
            parts.append(
                f"  - [{g.get('status', 'active')}] {g['summary']} (horizon: {g['horizon']})"
            )
    if sm.get("routines"):
        parts.append("Routines:")
        for r in sm["routines"]:
            parts.append(f"  - {r['name']}: {r['schedule']}")

    parts.append("\n== PEOPLE AROUND YOU ==")
    roster = ctx.roster
    for key in ["members", "workers", "staff"]:
        if key in roster:
            for m in roster[key]:
                aliases_str = ", ".join(m.get("aliases", []))
                ext = " [external]" if m.get("external") else ""
                parts.append(f"  {m['display_name']} ({m['role']}{ext}): known as [{aliases_str}]")
    if roster.get("equipment"):
        parts.append("Equipment:")
        for e in roster["equipment"]:
            parts.append(f"  {e['label']}: {e['status']}")
    for key in ["citizens", "patients"]:
        if key in roster:
            label = "Citizens:" if key == "citizens" else "Patients:"
            parts.append(label)
            for p in roster[key]:
                extra = f": {p.get('address', '')}" if p.get("address") else ""
                conds = ", ".join(p.get("conditions", []))
                if conds:
                    extra = f": {conds}"
                parts.append(f"  {p['display_name']}{extra}")

    parts.append("\n== AVAILABLE SERVICES ==")
    parts.append("Map intent to the appropriate service based on meaning, not keywords.")
    parts.append(
        "IMPORTANT: resource_kind_hint MUST be one of the exact resource_kinds listed below."
    )
    for svc in ctx.services:
        rks = ", ".join(svc.get("resource_kinds", []))
        parts.append(f"\n  [{svc['service_id'].upper()}] {svc['label']}")
        parts.append(f"    resource_kinds: [{rks}]")
        parts.append(f"    {svc['description']}")

    g = ctx.grounding
    parts.append("\n== TIME AND PLACE (GROUNDING) ==")
    parts.append(f"Right now: {g['now_local']} ({g['timezone']})")
    parts.append(f"Time of day: {g['time_of_day']} | Day: {g['day_of_week']}")
    parts.append(f"You are at: {g['place_label']} | Device: {g['device_surface']}")
    if g.get("growing_season"):
        parts.append(f"Growing season: {g['growing_season']}")
    parts.append("Time windows: " + ", ".join(f"{k}: {v}" for k, v in g.get("windows", {}).items()))

    parts.append("\n== WHAT WE KNOW (BELIEFS) ==")
    for b in ctx.beliefs:
        t = f" [{b.get('temporal', '')}]" if b.get("temporal") else ""
        parts.append(f"  {b['subject']} {b['predicate']} {b['object']}{t}")

    parts.append("\n== ACTIVE WORK ==")
    for t in ctx.task_state.get("active", []):
        parts.append(f"  [{t['status']}] {t['summary']}")
    for t in ctx.task_state.get("completed", []):
        parts.append(f"  [completed] {t['summary']}")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
# PHASE 1: FRAME EXTRACTION PROMPT
# ═══════════════════════════════════════════════════════════════════

FRAME_EXTRACTION_SYSTEM_PROMPT = """You are a domain-agnostic structured intent extraction engine. Convert a natural language utterance into a single JSON object describing what the user wants to do, who it involves, what service it targets, and when.

== CRITICAL: COMPOUND UTTERANCES ==
Many utterances contain TWO actions joined by "and". You MUST split these into TWO intents.
Examples:
  "Remind Morgan to X and buy Y" → 2 intents: [reminder: remind Morgan, shopping: buy Y]
  "Check fertilizers in stock and order more" → 1 intent: [inventory: check stock]
    ("order more if below threshold" is conditional, not a separate action — one intent)
  "Send Emma to feed cattle and log it" → 2 intents: [task: send Emma, inventory: log feed]
  "Process license renewal and notify her" → 2 intents: [license: process renewal, message: notify]
  "Order CBC and lipid panel, schedule for Friday" → 2 intents: [lab: order tests, appointment: schedule]
  "Find the spec and share it with Taylor" → 2 intents: [docs: find spec, message: share]
  "Move the review and notify the team" → 2 intents: [calendar: move meeting, message: notify]

== OUTPUT — A SINGLE JSON OBJECT ==
{
  "intents": [
    {
      "action": "what the user wants to accomplish, in plain English",
      "domain": "which service — infer from AVAILABLE SERVICES descriptions",
      "operation_hint": "create | list | update | delete",
      "resource_kind_hint": "the type of thing being acted on",
      "subject_hint": "a short label for this intent",
      "params": {
        "person_hint": "who this involves — exact name/alias from context",
        "time_hint": "any time mentioned in user's own words",
        "title": "title if specified",
        "query": "search terms if this is a lookup"
      }
    }
  ],
  "person_refs": [
    {"raw": "the person reference as the user said it, or 'me' for self",
     "confidence": "high|medium|low", "needs_resolution": true or false}
  ],
  "resource_refs": [
    {"raw": "how the user referred to the resource",
     "resource_kind_hint": "inferred type", "confidence": "high|medium|low",
     "needs_resolution": true or false}
  ],
  "time_window_hint": {"raw_phrase": "...", "confidence": "high|medium|low"} or null,
  "disambiguation_notes": null or "why a person reference is ambiguous"
}

== RULES ==
1. operation_hint: view/see/check/find/show/review → "list". make/add/schedule/create/order/book/log/prescribe/submit/issue → "create". Send/assign a person to do something → "create" (creating a task/request for them). change/move/edit/mark/complete/process/share → "update". remove/cancel/delete → "delete".
2. ONLY add person_ref raw="me" when the action is PERSONAL to you (checking YOUR own calendar, YOUR own tasks, YOUR own appointments). Do NOT add "me" for: team queries ("tickets assigned to my team"), system actions ("log the oil change", "check inventory"), or collective "we"/"our" that refers to an organization. For named people, use their exact name from context.
3. EVERY intent → resource_ref.
4. "And" connecting two DIFFERENT actions → TWO intents. Two DIFFERENT people same action → one intent per person. Conditional "and" ("check and order more IF below threshold") → ONE intent.
5. Time mentioned → time_window_hint. Future action no time → {"raw_phrase": "unspecified", "confidence": "low"}. Current-state queries → null.
6. Use BELIEFS to interpret indirect language.
7. confidence: "high"=explicit words, "medium"=reasonable inference, "low"=guessing.
8. Never invent IDs. Use raw values from the utterance.
9. Empty/noise utterance → operation_hint="compute", resource_kind_hint=null, empty refs.
10. Output EXACTLY one valid JSON object. No markdown. No explanation. No trailing commas."""


# ═══════════════════════════════════════════════════════════════════
# PHASE 2: LLM JUDGE PROMPT — evaluates the extraction output
# ═══════════════════════════════════════════════════════════════════

LLM_JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for an intent extraction system. Your job is to judge whether an LLM correctly extracted structured intents from a user utterance, given the domain context and business rules.

== HOW TO JUDGE ==
You will receive:
  1. The ORIGINAL USER UTTERANCE
  2. A summary of the DOMAIN CONTEXT (who the user is, available services, etc.)
  3. The EXPECTED OUTPUT (ground truth)
  4. The ACTUAL OUTPUT (what the LLM produced)
  5. The EXTRACTION RULES the LLM was supposed to follow

Judge each of 6 dimensions independently. For each dimension, determine PASS or FAIL based on whether the ACTUAL output is SEMANTICALLY CORRECT — not whether it matches character-for-character with the expected output.

== JUDGMENT DIMENSIONS ==

DIMENSION 1 — OPERATION:
Does the actual output have the right operation types (create/list/update/delete)?
- "create" = make/add/schedule/book/order/log/prescribe/submit
- "list" = view/see/check/find/show/search/lookup/review/read
- "update" = change/move/edit/mark/complete/process/assign/share/send
- "delete" = remove/cancel
- If the actual operation is semantically equivalent to the expected, PASS.
- If the actual operation is a reasonable alternative given the utterance, PASS.
- Example: "share it" → expected "create" message → actual "update" → PASS (share ≈ update is reasonable).

DIMENSION 2 — RESOURCE:
Does the actual output target the correct service/resource kind?
- The resource_kind_hint must match the domain of the expected output.
- Semantic equivalence matters, not exact string match.
- "medication order" = "prescription", "appointment" = "follow_up" (for follow-up visits),
  "chart" = "patient_record", "agenda" = "meeting", "FOIA request" = "record",
  "code enforcement cases" = "violation", "equipment" = "maintenance_log" (for equipment checks),
  "progress" = "chore", "behavior" = "chore" (for chore completion/behavior checking),
  "maintenance schedule" = "repair_ticket", "on-call schedule" = "ticket" (for on-call queries),
  "field condition" = "task" (for agronomist consultation requests).
- If the resource is in the right service family and a human would say it's the same thing, PASS.

DIMENSION 3 — PERSON:
Does the actual output reference the right people?
- Check person_refs[].raw for the people mentioned in the utterance.
- ONLY require raw="me" when the action is PERSONAL to the actor:
    ✓ REQUIRED: "What meetings do I have?", "Remind me", "My tasks"
    ✗ NOT REQUIRED: "Show me tickets assigned to my team" (team-scoped query)
    ✗ NOT REQUIRED: "Log the oil change" (system action, no person involved)
    ✗ NOT REQUIRED: "Check what fertilizers we have" ("we" = organization, not personal)
    ✗ NOT REQUIRED: "Move the sprint review and notify the team" (the review isn't personal)
- If the utterance mentions specific named people, those MUST be in person_refs.
- Person names must match (aliases are fine: "Grandma Sue" = "Grandma").
- If the LLM includes "me" and the expected output doesn't, that's fine — PASS (extra safety).
- If the LLM omits "me" for a non-personal query, PASS.

DIMENSION 4 — TIME:
Does the actual output capture the time correctly?
- If the utterance mentions a specific time → time_window_hint must be present with the phrase.
- If the utterance describes a future action with NO specific time → time_window_hint
  should indicate "unspecified" or similar. PASS as long as time_window_hint is not null.
- If the utterance is a current-state query with no time context → time_window_hint can be null.

DIMENSION 5 — COMPLETENESS:
Does the actual output capture ALL the intents in the utterance?
- Count the intents in the actual output vs the expected output.
- If the utterance has two distinct actions joined by "and" → expect 2 intents.
- If the utterance has two different people for the same action → expect 1 intent per person (or 1 intent covering both).
- If actual intents >= expected, PASS. If fewer, FAIL.

DIMENSION 6 — DISAMBIGUATION:
Does the actual output flag ambiguity correctly?
- If the expected output says disambiguation is needed (person name matches multiple people),
  check that disambiguation_notes is present and non-empty.
- If disambiguation is NOT needed, always PASS (extra disambiguation is not penalized).

== OUTPUT FORMAT ==
Return EXACTLY one JSON object:
{
  "operation": {"pass": true or false, "reasoning": "one sentence explaining why"},
  "resource": {"pass": true or false, "reasoning": "one sentence explaining why"},
  "person": {"pass": true or false, "reasoning": "one sentence explaining why"},
  "time": {"pass": true or false, "reasoning": "one sentence explaining why"},
  "completeness": {"pass": true or false, "reasoning": "one sentence explaining why"},
  "disambiguation": {"pass": true or false, "reasoning": "one sentence explaining why"}
}

No markdown. No explanation outside the JSON. Be fair — if the LLM's answer is SEMANTICALLY equivalent to the expected answer, PASS it."""


# ═══════════════════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════════════════


@dataclass
class JudgeVerdict:
    passed: bool
    reasoning: str


@dataclass
class ScenarioResult:
    scenario_id: str
    domain_id: str
    utterance: str
    passed_string: bool  # string-matcher pass
    passed_llm_judge: bool  # LLM judge pass
    string_dimensions: dict[str, bool]
    judge_verdicts: dict[str, JudgeVerdict]
    raw_output: dict[str, Any]
    latency_generate_ms: float
    latency_judge_ms: float


# ═══════════════════════════════════════════════════════════════════
# STRING-MATCHER EVALUATOR (legacy, for comparison)
# ═══════════════════════════════════════════════════════════════════


def _normalize_op(op: str) -> str:
    mapping = {
        "list": "list",
        "read": "list",
        "search": "list",
        "find": "list",
        "show": "list",
        "check": "list",
        "get": "list",
        "view": "list",
        "lookup": "list",
        "query": "list",
        "review": "list",
        "create": "create",
        "add": "create",
        "schedule": "create",
        "book": "create",
        "order": "create",
        "prescribe": "create",
        "submit": "create",
        "log": "create",
        "update": "update",
        "edit": "update",
        "change": "update",
        "modify": "update",
        "move": "update",
        "complete": "update",
        "mark": "update",
        "process": "update",
        "assign": "update",
        "share": "update",
        "send": "update",
        "delete": "delete",
        "remove": "delete",
        "cancel": "delete",
    }
    return mapping.get(op.lower(), op.lower())


def _resource_kind_matches(actual: str | None, expected: str | None) -> bool:
    if actual == expected:
        return True
    if actual is None and expected is None:
        return True
    if not actual or not expected:
        return False
    a, e = str(actual).lower().strip(), str(expected).lower().strip()
    if a in e or e in a:
        return True
    if set(a.replace("_", " ").split()) & set(e.replace("_", " ").split()):
        return True
    return False


def evaluate_string_match(scenario: FrameScenario, output: dict[str, Any]) -> dict[str, bool]:
    if isinstance(output, list):
        output = {"intents": output} if output else {"intents": []}
    if not isinstance(output, dict):
        output = {"intents": []}
    intents = output.get("intents") or []
    person_refs = output.get("person_refs") or []
    time_hint = output.get("time_window_hint")

    # Operation
    actual_ops = [_normalize_op(i.get("operation_hint", "")) for i in intents]
    expected_ops = [_normalize_op(o) for o in scenario.expected_operations]
    while len(actual_ops) < len(expected_ops):
        actual_ops.append("")
    while len(expected_ops) < len(actual_ops):
        expected_ops.append("")
    op_pass = all(a == e for a, e in zip(actual_ops, expected_ops))

    # Resource
    actual_rk = [i.get("resource_kind_hint") for i in intents]
    expected_rk = scenario.expected_resource_kinds
    while len(actual_rk) < len(expected_rk):
        actual_rk.append(None)
    while len(expected_rk) < len(actual_rk):
        expected_rk.append(None)
    rk_pass = all(_resource_kind_matches(a, e) for a, e in zip(actual_rk, expected_rk))

    # Person
    actual_persons = [p.get("raw", "") for p in person_refs]
    expected_persons = [p for p in scenario.expected_persons if p]
    person_pass = True
    for ep in expected_persons:
        found = any(
            ep.lower() in ap.lower()
            or (ep.lower() == "me" and ap.lower() in ("me", "my", "i", "we", "us", ""))
            for ap in actual_persons
        )
        if not found:
            person_pass = False
            break

    # Time
    has_time = time_hint is not None and len(str(time_hint.get("raw_phrase", ""))) > 0
    time_pass = (scenario.expected_time_required and has_time) or (
        not scenario.expected_time_required
    )

    # Completeness
    comp_pass = len(intents) >= scenario.intent_count

    # Disambiguation
    if scenario.needs_disambiguation:
        disamb = output.get("disambiguation_notes")
        disamb_pass = bool(disamb) and len(str(disamb)) > 5
    else:
        disamb_pass = True

    return {
        "operation": op_pass,
        "resource": rk_pass,
        "person": person_pass,
        "time": time_pass,
        "completeness": comp_pass,
        "disambiguation": disamb_pass,
    }


# ═══════════════════════════════════════════════════════════════════
# LLM JUDGE
# ═══════════════════════════════════════════════════════════════════


def build_judge_prompt(
    scenario: FrameScenario, context_summary: str, actual_output: dict[str, Any]
) -> str:
    """Build the evaluation input for the LLM judge."""
    return f"""== ORIGINAL USER UTTERANCE ==
{scenario.utterance}

== DOMAIN CONTEXT SUMMARY ==
{context_summary[:2000]}

== EXPECTED OUTPUT (GROUND TRUTH) ==
{json.dumps({
    "expected_operations": scenario.expected_operations,
    "expected_resource_kinds": scenario.expected_resource_kinds,
    "expected_persons": scenario.expected_persons,
    "expected_time_required": scenario.expected_time_required,
    "expected_intent_count": scenario.intent_count,
    "needs_disambiguation": scenario.needs_disambiguation,
    "disambiguation_reason": scenario.disambiguation_reason or "none",
}, indent=2)}

== ACTUAL OUTPUT (LLM EXTRACTION) ==
{json.dumps(actual_output, indent=2)}

== EXTRACTION RULES THE LLM WAS GIVEN ==
1. operation_hint: create | list | update | delete
2. Every named person → person_ref. Self-directed actions → include raw="me"
3. Every intent → resource_ref
4. "And" joining two DIFFERENT actions → two intents. Two DIFFERENT people → one intent per person
5. Time mentioned → time_window_hint. Future action no time → unspecified. Current-state queries → null
6. Use BELIEFS for indirect language
7. Never invent IDs

Judge each of the 6 dimensions. Return JSON with pass=true/false + reasoning."""


async def run_llm_judge(
    client: ModelClient, scenario: FrameScenario, context_block: str, actual_output: dict[str, Any]
) -> dict[str, JudgeVerdict]:
    """Run the LLM judge on a single scenario output. Retries once on failure."""
    judge_prompt = build_judge_prompt(scenario, context_block, actual_output)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": LLM_JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": judge_prompt},
    ]

    last_error = ""
    parsed: dict[str, Any] = {}
    for attempt in range(2):
        try:
            response = await asyncio.wait_for(
                client.chat(
                    messages=messages,
                    tools=[],
                    tool_choice="none",
                    temperature=0.0,
                    max_tokens=4096,
                    response_mime_type="application/json",
                ),
                timeout=45.0,
            )
            content = (response.content or "").strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:]) if len(lines) > 1 else content
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            if not content.startswith("{"):
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    content = match.group()
            parsed = json.loads(content)
            break  # success — exit retry loop
        except asyncio.TimeoutError:
            last_error = "judge_timeout"
            if attempt == 0:
                continue
        except json.JSONDecodeError as e:
            last_error = (
                f"judge_json_parse: {e!s} [raw: {content[:200] if 'content' in dir() else 'N/A'}]"
            )
            if attempt == 0 and "Unterminated string" in str(e):
                continue
        except Exception as e:
            last_error = f"judge_call_failed: {e!s}"
            if attempt == 0:
                continue
    else:
        # All retries exhausted — return error verdicts
        return {
            dim: JudgeVerdict(passed=False, reasoning=last_error)
            for dim in ["operation", "resource", "person", "time", "completeness", "disambiguation"]
        }

    # Success — parse verdicts from judge output
    verdicts: dict[str, JudgeVerdict] = {}
    for dim in ["operation", "resource", "person", "time", "completeness", "disambiguation"]:
        dim_data = parsed.get(dim, {})
        if isinstance(dim_data, dict):
            verdicts[dim] = JudgeVerdict(
                passed=dim_data.get("pass", False),
                reasoning=dim_data.get("reasoning", ""),
            )
        else:
            verdicts[dim] = JudgeVerdict(passed=False, reasoning="judge_output_malformed")
    return verdicts


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════════


async def run_scenario_with_judge(
    client: ModelClient,
    scenario: FrameScenario,
    context_block: str,
) -> ScenarioResult:
    """Phase 1: LLM generates output. Phase 2: LLM judge evaluates."""
    system_prompt = FRAME_EXTRACTION_SYSTEM_PROMPT + "\n\n" + context_block
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"<CURRENT_UTTERANCE>\n{scenario.utterance}\n</CURRENT_UTTERANCE>\n\nConvert this utterance to structured JSON as specified.",
        },
    ]

    # ── Phase 1: Generate (with retry) ──
    start = time.perf_counter()
    raw_generate_content = ""
    parsed: dict[str, Any] = {}
    for attempt in range(2):
        try:
            response = await asyncio.wait_for(
                client.chat(
                    messages=messages,
                    tools=[],
                    tool_choice="none",
                    temperature=0.0,
                    max_tokens=2048,
                    response_mime_type="application/json",
                ),
                timeout=45.0,
            )
            gen_latency = (time.perf_counter() - start) * 1000
            content = (response.content or "").strip()
            raw_generate_content = content
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:]) if len(lines) > 1 else content
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            if not content.startswith("{"):
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    content = match.group()
            parsed = json.loads(content)
            break  # success
        except asyncio.TimeoutError:
            gen_latency = (time.perf_counter() - start) * 1000
            parsed = {"error": "generate_timeout", "raw": raw_generate_content[:500]}
            if attempt == 0:
                continue
        except json.JSONDecodeError:
            gen_latency = (time.perf_counter() - start) * 1000
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    break
                except json.JSONDecodeError:
                    pass
            parsed = {"error": "json_parse_failed", "raw": raw_generate_content[:500]}
            if attempt == 0:
                continue
        except Exception as exc:
            gen_latency = (time.perf_counter() - start) * 1000
            parsed = {
                "error": str(exc),
                "raw": raw_generate_content[:500] if raw_generate_content else "",
            }
            if attempt == 0:
                continue

    # ── String-matcher evaluation (fast, for comparison) ──
    string_dims = evaluate_string_match(scenario, parsed)
    passed_string = all(string_dims.values())

    # ── Phase 2: LLM Judge ──
    judge_start = time.perf_counter()
    judge_verdicts = await run_llm_judge(client, scenario, context_block, parsed)
    judge_latency = (time.perf_counter() - judge_start) * 1000
    passed_judge = all(v.passed for v in judge_verdicts.values())

    return ScenarioResult(
        scenario_id=scenario.id,
        domain_id=scenario.domain_id,
        utterance=scenario.utterance,
        passed_string=passed_string,
        passed_llm_judge=passed_judge,
        string_dimensions=string_dims,
        judge_verdicts=judge_verdicts,
        raw_output=parsed,
        latency_generate_ms=round(gen_latency, 2),
        latency_judge_ms=round(judge_latency, 2),
    )


async def run_benchmark(client: ModelClient | None = None) -> dict[str, Any]:
    if client is None:
        client = create_model_client_from_env()

    provider = os.environ.get("LLM_PROVIDER", "unknown")
    print(f"Provider: {provider} | Model: {client.model_id}")
    print(f"Scenarios: {len(SCENARIOS)} across {len(ALL_DOMAIN_CONTEXTS)} domains")
    print("Evaluation: String-matcher + LLM Judge (dual scoring)")
    print()

    domain_contexts: dict[str, str] = {}
    for domain_id, ctx in ALL_DOMAIN_CONTEXTS.items():
        domain_contexts[domain_id] = build_context_block(ctx)
        print(f"  {ctx.domain_label}: {len(domain_contexts[domain_id]):,} chars")
    print()

    results: list[ScenarioResult] = []
    for i, scenario in enumerate(SCENARIOS):
        ctx_block = domain_contexts[scenario.domain_id]
        print(
            f"[{i+1:02d}/{len(SCENARIOS)}] {scenario.id} [{scenario.domain_id}]: {scenario.utterance[:65]}"
        )

        result = await run_scenario_with_judge(client, scenario, ctx_block)
        results.append(result)

        # Dual score summary
        str_status = "✓" if result.passed_string else "✗"
        judge_status = "✓" if result.passed_llm_judge else "✗"
        print(
            f"         String: {str_status} | Judge: {judge_status} | Gen: {result.latency_generate_ms:.0f}ms | Judge: {result.latency_judge_ms:.0f}ms"
        )

        if not result.passed_llm_judge:
            for dim, v in result.judge_verdicts.items():
                if not v.passed:
                    print(f"         ✗ Judge {dim}: {v.reasoning[:100]}")

    # ── Aggregate ──
    dimension_names = ["operation", "resource", "person", "time", "completeness", "disambiguation"]

    # String-matcher scores
    string_dim_scores: dict[str, float] = {}
    for dim in dimension_names:
        passed = sum(1 for r in results if r.string_dimensions[dim])
        string_dim_scores[dim] = round(passed / len(results), 4)
    string_overall = sum(1 for r in results if r.passed_string)
    string_score = round(string_overall / len(results), 4)

    # LLM judge scores
    judge_dim_scores: dict[str, float] = {}
    for dim in dimension_names:
        passed = sum(1 for r in results if r.judge_verdicts[dim].passed)
        judge_dim_scores[dim] = round(passed / len(results), 4)
    judge_overall = sum(1 for r in results if r.passed_llm_judge)
    judge_score = round(judge_overall / len(results), 4)

    # By-domain (judge)
    domain_scores: dict[str, dict[str, Any]] = {}
    for domain_id in ALL_DOMAIN_CONTEXTS:
        domain_results = [r for r in results if r.domain_id == domain_id]
        if domain_results:
            passed = sum(1 for r in domain_results if r.passed_llm_judge)
            domain_scores[domain_id] = {
                "label": ALL_DOMAIN_CONTEXTS[domain_id].domain_label,
                "total": len(domain_results),
                "passed": passed,
                "score": round(passed / len(domain_results), 4),
            }

    avg_gen = statistics.mean([r.latency_generate_ms for r in results])
    avg_judge = statistics.mean([r.latency_judge_ms for r in results])

    print(f"\n{'='*70}")
    print("BENCHMARK RESULTS — Back LLM Frame Extraction v3 (LLM-as-Judge)")
    print(f"{'='*70}")
    print(f"Provider: {provider} | Model: {client.model_id}")
    print(f"{'':>25} {'String':>10} {'LLM Judge':>10}")
    print(
        f"  Overall pass rate:          {string_overall:>3}/{len(results)} {string_score:>5.0%}   {judge_overall:>3}/{len(results)} {judge_score:>5.0%}"
    )
    print(f"  Avg latency:                {avg_gen:>9.0f}ms   {avg_judge:>9.0f}ms")
    print()

    for dim in dimension_names:
        ss = string_dim_scores[dim]
        js = judge_dim_scores[dim]
        print(f"  {dim:<18}   {ss:>5.0%}         {js:>5.0%}")
    print()

    print("By domain (LLM Judge):")
    for domain_id in ["family", "enterprise", "government", "agriculture", "healthcare"]:
        ds = domain_scores.get(domain_id, {})
        label = ds.get("label", domain_id)
        score = ds.get("score", 0)
        bar = "█" * int(score * 15) + "░" * (15 - int(score * 15))
        print(f"  {label:<50} {bar} {score:.0%}")

    # Per-scenario table
    print(f"\n{'─'*85}")
    print(f"{'ID':<7} {'Domain':<12} {'Utterance':<35} {'Str':<5} {'Judge':<6}")
    print(f"{'─'*85}")
    for r in results:
        ss = "✓" if r.passed_string else "✗"
        js = "✓" if r.passed_llm_judge else "✗"
        print(f"{r.scenario_id:<7} {r.domain_id:<12} {r.utterance[:33]:<35} {ss:<5} {js:<6}")
    print(f"{'─'*85}")

    return {
        "provider": provider,
        "model": client.model_id,
        "string_score": string_score,
        "judge_score": judge_score,
        "string_dim_scores": string_dim_scores,
        "judge_dim_scores": judge_dim_scores,
        "domain_scores": domain_scores,
        "total_scenarios": len(results),
        "string_passed": string_overall,
        "judge_passed": judge_overall,
        "avg_latency_generate_ms": round(avg_gen, 1),
        "avg_latency_judge_ms": round(avg_judge, 1),
        "results": [
            {
                "id": r.scenario_id,
                "domain": r.domain_id,
                "utterance": r.utterance,
                "passed_string": r.passed_string,
                "passed_judge": r.passed_llm_judge,
                "string_dims": r.string_dimensions,
                "judge_verdicts": {
                    k: {"pass": v.passed, "reasoning": v.reasoning}
                    for k, v in r.judge_verdicts.items()
                },
                "raw_output": r.raw_output,
                "latency_generate_ms": r.latency_generate_ms,
                "latency_judge_ms": r.latency_judge_ms,
            }
            for r in results
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════════╗
║   Back LLM Frame Extraction Benchmark v3            ║
║   LLM-as-Judge Evaluation | 50 scenarios | 5 domains║
╠══════════════════════════════════════════════════════╣
║  1. Dry-run analysis (review prompts, no LLM)       ║
║  2. Run with env-configured LLM provider            ║
║  0. Exit                                            ║
╚══════════════════════════════════════════════════════╝"""


def main() -> int:
    print(MENU)
    choice = input("Select benchmark [1-2, 0]: ").strip()

    if choice == "1":
        domain_stats = {}
        for domain_id, ctx in ALL_DOMAIN_CONTEXTS.items():
            ctx_block = build_context_block(ctx)
            prompt = FRAME_EXTRACTION_SYSTEM_PROMPT + "\n\n" + ctx_block
            sc = len([s for s in SCENARIOS if s.domain_id == domain_id])
            domain_stats[domain_id] = {
                "label": ctx.domain_label,
                "context_chars": len(ctx_block),
                "prompt_chars": len(prompt),
                "scenarios": sc,
            }

        print("DRY RUN — v3 LLM-as-Judge")
        print(f"Domains: {len(ALL_DOMAIN_CONTEXTS)} | Scenarios: {len(SCENARIOS)}")
        for did, ds in domain_stats.items():
            print(
                f"  {ds['label']}: {ds['context_chars']:,} chars context, {ds['scenarios']} scenarios"
            )
        print(f"\nLLM Judge prompt: {len(LLM_JUDGE_SYSTEM_PROMPT):,} chars")
        print("Each scenario calls LLM TWICE: generate + judge.")

    elif choice == "2":
        try:
            client = create_model_client_from_env()
        except Exception as exc:
            print(f"\nERROR: {exc}")
            print("Set $env:LLM_PROVIDER, $env:GOOGLE_CLOUD_PROJECT, $env:GOOGLE_CLOUD_LOCATION")
            return 1

        provider = os.environ.get("LLM_PROVIDER", "unknown")
        print(f"\nProvider: {provider} | Model: {client.model_id}")
        print("Running 50 scenarios × 2 LLM calls each = 100 total calls...\n")

        result = asyncio.run(run_benchmark(client=client))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_slug = client.model_id.replace("/", "_").replace("-", "_")
        out_path = Path(f"data/llm_frame_bench/results_v3_{provider}_{model_slug}_{ts}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
