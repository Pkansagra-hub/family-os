"""Back LLM Frame Extraction Benchmark v2 — Domain-Agnostic. 50 scenarios.

PRINCIPLE:
  - Back receives: raw user utterance + full rich context (self model, roster,
    available services, grounding, beliefs, task state). No chat history.
  - LLM extracts structured intents, person refs, resource refs, time hints.
  - 50 scenarios across 5 domains x 10 scenarios each:
      FamilyOS (household management), Enterprise (workplace tools),
      Government (civic services), Agriculture (farm management),
      Healthcare (clinical/patient).
  - Prompt is principle-based. No keyword hints per service.
  - Evaluator checks 6 dimensions: operation, resource, person, time, completeness, disambiguation.
  - By-domain score breakdown.

Usage:
  python scripts/probe_back_llm_frame_benchmark_v2.py
  # Mode 1: dry-run analysis. Mode 2: live LLM benchmark.
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
# DOMAIN CONTEXT FIXTURES — 5 domains
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


# ── Domain 1: FamilyOS ───────────────────────────────────

FAMILY_CONTEXT = DomainContext(
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
            "description": "Recurring household responsibilities. Gamified with rewards. Completion tracked. Parents verify. Progress viewable.",
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
            {"task_id": "t0", "summary": "Book soccer field for practice", "status": "completed"}
        ],
    },
)

# ── Domain 2: Enterprise ─────────────────────────────────

ENTERPRISE_CONTEXT = DomainContext(
    domain_id="enterprise",
    domain_label="Enterprise — Workplace Productivity",
    self_model={
        "actor_id": "person.pat_smith",
        "display_name": "Pat Smith",
        "role": "engineering_manager",
        "department": "Platform Engineering",
        "reports_to": "person.ceo_chen",
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
        {
            "subject": "Platform Engineering",
            "predicate": "has_deadline",
            "object": "Q2 OKRs due",
            "temporal": "2026-06-30",
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

# ── Domain 3: Government ─────────────────────────────────

GOVERNMENT_CONTEXT = DomainContext(
    domain_id="government",
    domain_label="Government — Civic Services",
    self_model={
        "actor_id": "person.clerk_maria",
        "display_name": "Maria Clerk",
        "role": "city_clerk",
        "department": "Permits & Licensing",
        "jurisdiction": "City of Springfield",
        "preferences": {
            "working_hours": "8am-4:30pm CT",
            "case_management_style": "first_in_first_out",
        },
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
        "citizens_nearby": [
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
        "completed": [
            {
                "task_id": "t19",
                "summary": "Issue parade permit for July 4th committee",
                "status": "completed",
            }
        ],
    },
)

# ── Domain 4: Agriculture ────────────────────────────────

AGRICULTURE_CONTEXT = DomainContext(
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
        "preferences": {
            "planting_method": "no_till",
            "irrigation": "center_pivot",
            "weather_source": "noaa_ag",
        },
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
                "clinic": "County Animal Hospital",
            },
            {
                "person_id": "person.agronomist_raj",
                "display_name": "Raj Agronomist",
                "role": "agronomist",
                "aliases": ["Raj", "Agronomist"],
                "external": True,
                "company": "AgriConsult Inc",
            },
        ],
        "equipment": [
            {"equip_id": "tractor_jd_8220", "label": "John Deere 8220", "status": "operational"},
            {
                "equip_id": "combine_case_8250",
                "label": "Case IH 8250 Combine",
                "status": "needs_maintenance",
            },
            {"equip_id": "sprayer_hardi", "label": "Hardi Sprayer 3000", "status": "operational"},
        ],
    },
    services=[
        {
            "service_id": "field_planner",
            "label": "Field Planner",
            "description": "Crop rotation planning, planting schedules, field mapping. Tracks soil conditions, yield history, cover crops. Planting and harvest windows.",
            "resource_kinds": ["planting_plan", "field", "crop_schedule"],
        },
        {
            "service_id": "livestock",
            "label": "Livestock Manager",
            "description": "Herd tracking, vaccination schedules, breeding records, feed orders, weight tracking. Health alerts and vet visit scheduling.",
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
            "description": "Field-level weather forecasts, growing degree days, frost alerts, precipitation tracking. 10-day outlook, severe weather warnings.",
            "resource_kinds": ["weather_forecast", "frost_alert"],
        },
        {
            "service_id": "inventory",
            "label": "Farm Inventory",
            "description": "Seed, fertilizer, chemical, and feed inventory. Tracks quantities, lot numbers, reorder thresholds. Supplier ordering.",
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
        {"subject": "Field 12", "predicate": "showing", "object": "signs of nitrogen deficiency"},
        {"subject": "Weather", "predicate": "forecast", "object": "possible thunderstorm Friday"},
    ],
    task_state={
        "active": [
            {"task_id": "t30", "summary": "Order hydraulic hose for combine", "status": "pending"},
            {
                "task_id": "t31",
                "summary": "Schedule vet visit for herd vaccinations",
                "status": "pending",
            },
        ],
        "completed": [
            {
                "task_id": "t29",
                "summary": "Apply side-dress nitrogen to Field 12",
                "status": "completed",
            }
        ],
    },
)

# ── Domain 5: Healthcare ─────────────────────────────────

HEALTHCARE_CONTEXT = DomainContext(
    domain_id="healthcare",
    domain_label="Healthcare — Clinical Practice",
    self_model={
        "actor_id": "person.dr_patel",
        "display_name": "Dr. Amara Patel",
        "role": "primary_care_physician",
        "specialty": "Family Medicine",
        "practice": "Oakwood Family Health Center",
        "license": "MD-45921",
        "preferences": {
            "appointment_duration": "20 min standard / 40 min physical",
            "lab_preference": "Quest Diagnostics",
            "pharmacy_preference": "local",
        },
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
                "practice": "Heart Care Associates",
            },
        ],
        "patients_nearby": [
            {
                "patient_id": "pt.robert_kim",
                "display_name": "Robert Kim",
                "aliases": ["Robert", "Bob", "Mr. Kim"],
                "age": 67,
                "conditions": ["hypertension", "type_2_diabetes"],
                "last_visit": "2026-05-15",
            },
            {
                "patient_id": "pt.maria_garcia",
                "display_name": "Maria Garcia",
                "aliases": ["Maria", "Ms. Garcia"],
                "age": 34,
                "conditions": ["asthma"],
                "last_visit": "2026-04-20",
            },
            {
                "patient_id": "pt.james_wilson",
                "display_name": "James Wilson",
                "aliases": ["James", "Jim", "Mr. Wilson"],
                "age": 52,
                "conditions": ["hyperlipidemia", "gerd"],
                "last_visit": "2026-05-28",
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
            "description": "Patient appointments, follow-ups, physicals, specialist referrals. Has time slots, visit types, room assignments, waitlist.",
            "resource_kinds": ["appointment", "follow_up", "referral"],
        },
        {
            "service_id": "prescriptions",
            "label": "E-Prescribing",
            "description": "Medication orders, refills, prior authorizations, drug interaction checks. Pharmacy routing, formulary checking.",
            "resource_kinds": ["prescription", "refill", "prior_auth"],
        },
        {
            "service_id": "labs",
            "label": "Lab Orders",
            "description": "Lab test ordering, specimen tracking, result review. CBC, metabolic panels, lipid panels, A1C, cultures.",
            "resource_kinds": ["lab_order", "lab_result"],
        },
        {
            "service_id": "messaging",
            "label": "Patient Messaging",
            "description": "Secure patient portal messages, staff messages, specialist consults. HIPAA compliant. Has urgency levels.",
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
            {"task_id": "t40", "summary": "Review Robert Kim's lab results", "status": "pending"},
            {
                "task_id": "t41",
                "summary": "Send James Wilson's records to Dr. Smith",
                "status": "pending",
            },
        ],
        "completed": [
            {
                "task_id": "t39",
                "summary": "Complete Maria Garcia's asthma checkup",
                "status": "completed",
            }
        ],
    },
)

ALL_DOMAIN_CONTEXTS: dict[str, DomainContext] = {
    "family": FAMILY_CONTEXT,
    "enterprise": ENTERPRISE_CONTEXT,
    "government": GOVERNMENT_CONTEXT,
    "agriculture": AGRICULTURE_CONTEXT,
    "healthcare": HEALTHCARE_CONTEXT,
}

# ═══════════════════════════════════════════════════════════════════
# 50 DOMAIN-AGNOSTIC TEST SCENARIOS (10 per domain)
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
    # ═══════════════ FAMILY (F01-F10) ═══════════════
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
        ["me"],
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
        ["Morgan", "me"],
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
        "Cross-person calendar conflict check, 2 intents (one per person)",
        ["list"],
        ["calendar_event"],
        ["Casey", "Morgan"],
        False,
        2,
    ),
    # ═══════════════ ENTERPRISE (E01-E10) ═══════════
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
        ["me"],
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
    # ═══════════════ GOVERNMENT (G01-G10) ═══════════
    FrameScenario(
        "G01",
        "government",
        "Look up the building permit for 123 Main Street",
        "Read permit by address",
        ["list"],
        ["permit"],
        ["me"],
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
        ["me"],
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
        ["me"],
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
        ["me"],
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
        ["me"],
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
        ["me"],
        False,
        1,
    ),
    # ═══════════════ AGRICULTURE (A01-A10) ═══════════
    FrameScenario(
        "A01",
        "agriculture",
        "Order more soybean seeds for Field 5 — running low",
        "Create supply order",
        ["create"],
        ["seed_inventory"],
        ["me"],
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
        ["me"],
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
        ["me"],
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
        ["me"],
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
        ["me"],
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
        ["me"],
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
        ["me"],
        False,
        1,
    ),
    # ═══════════════ HEALTHCARE (H01-H10) ═══════════
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
        ["me"],
        False,
        1,
    ),
]

# ═══════════════════════════════════════════════════════════════════
# PROMPT BUILDER — PURELY PRINCIPLE-BASED, NO KEYWORD HINTS
# ═══════════════════════════════════════════════════════════════════


def build_context_block(ctx: DomainContext) -> str:
    """Render a domain context block. NO keyword hints per service — just descriptions."""
    parts: list[str] = []

    # ── Self Model ──
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

    # ── Roster ──
    parts.append("\n== PEOPLE AROUND YOU ==")
    roster = ctx.roster
    if "members" in roster:
        for m in roster["members"]:
            aliases_str = ", ".join(m.get("aliases", []))
            parts.append(
                f"  {m['display_name']} ({m['role']}, {m.get('age_band', '')}): known as [{aliases_str}]"
            )
    if "workers" in roster:
        for w in roster["workers"]:
            aliases_str = ", ".join(w.get("aliases", []))
            ext = " [external]" if w.get("external") else ""
            skills = f": {', '.join(w.get('skills', []))}" if w.get("skills") else ""
            parts.append(
                f"  {w['display_name']} ({w['role']}{ext}){skills}: known as [{aliases_str}]"
            )
        if roster.get("equipment"):
            parts.append("Equipment:")
            for e in roster["equipment"]:
                parts.append(f"  {e['label']}: {e['status']}")
    if roster.get("citizens_nearby"):
        parts.append("Citizens:")
        for c in roster["citizens_nearby"]:
            parts.append(f"  {c['display_name']}: {c.get('address', '')}")
    if roster.get("patients_nearby"):
        parts.append("Patients:")
        for p in roster["patients_nearby"]:
            conds = ", ".join(p.get("conditions", []))
            parts.append(
                f"  {p['display_name']} (age {p.get('age', '?')}): {conds}. Last visit: {p.get('last_visit', 'unknown')}"
            )
    if roster.get("staff"):
        for m in roster["staff"]:
            aliases_str = ", ".join(m.get("aliases", []))
            ext = " [external]" if m.get("external") else ""
            parts.append(f"  {m['display_name']} ({m['role']}{ext}): known as [{aliases_str}]")

    # ── Available Services ──
    parts.append("\n== AVAILABLE SERVICES ==")
    parts.append(
        "These are the services connected to your account. Each has a description of what it does."
    )
    parts.append("Map the user's intent to the appropriate service based on meaning, not keywords.")
    for svc in ctx.services:
        parts.append(f"\n  [{svc['service_id'].upper()}] {svc['label']}")
        parts.append(f"    {svc['description']}")

    # ── Grounding ──
    g = ctx.grounding
    parts.append("\n== TIME AND PLACE (GROUNDING) ==")
    parts.append(f"Right now: {g['now_local']} ({g['timezone']})")
    parts.append(f"Time of day: {g['time_of_day']} | Day: {g['day_of_week']}")
    parts.append(f"You are at: {g['place_label']}")
    parts.append(f"Device: {g['device_surface']}")
    if g.get("growing_season"):
        parts.append(f"Growing season: {g['growing_season']}")
    parts.append("Time windows:")
    for k, v in g.get("windows", {}).items():
        parts.append(f"  {k}: {v}")

    # ── Beliefs ──
    parts.append("\n== WHAT WE KNOW (BELIEFS) ==")
    for b in ctx.beliefs:
        t = f" [{b.get('temporal', '')}]" if b.get("temporal") else ""
        parts.append(f"  {b['subject']} {b['predicate']} {b['object']}{t}")

    # ── Task State ──
    parts.append("\n== ACTIVE WORK ==")
    for t in ctx.task_state.get("active", []):
        parts.append(f"  [{t['status']}] {t['summary']}")
    for t in ctx.task_state.get("completed", []):
        parts.append(f"  [completed] {t['summary']}")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — PURELY PRINCIPLE-BASED, NO HINTS PER SERVICE
# ═══════════════════════════════════════════════════════════════════

FRAME_EXTRACTION_SYSTEM_PROMPT = """You are a domain-agnostic structured intent extraction engine. Your ONLY job is to convert a natural language utterance into a single JSON object describing what the user wants to do, who it involves, what service it targets, and when it should happen.

== YOUR INPUT ==
You receive:
  1. A CONTEXT BLOCK describing the user's world — their identity, the people around them, the available services (with descriptions of what each does), the current time/place, known facts, and active work.
  2. The USER'S LATEST UTTERANCE wrapped in <CURRENT_UTTERANCE> tags.

== YOUR OUTPUT — A SINGLE JSON OBJECT ==
Output EXACTLY one JSON object. Never an array, markdown, or explanation.

{
  "intents": [
    {
      "action": "what the user wants to accomplish, in plain English",
      "domain": "which service this targets — infer from the AVAILABLE SERVICES descriptions",
      "operation_hint": "the kind of operation — infer from the user's language",
      "resource_kind_hint": "the type of thing being acted on — infer from service descriptions",
      "subject_hint": "a short label for this intent",
      "params": {
        "person_hint": "who this involves — exact name/alias from context",
        "time_hint": "any time mentioned — keep in user's own words",
        "title": "title if specified",
        "query": "search terms if this is a lookup"
      }
    }
  ],
  "person_refs": [
    {
      "raw": "the person reference as the user said it, or 'me' for self",
      "confidence": "high|medium|low",
      "needs_resolution": true or false
    }
  ],
  "resource_refs": [
    {
      "raw": "how the user referred to the resource",
      "resource_kind_hint": "inferred type — match to a service's resource_kinds",
      "confidence": "high|medium|low",
      "needs_resolution": true or false
    }
  ],
  "time_window_hint": {
    "raw_phrase": "the time the user mentioned, or 'unspecified' if needed but missing",
    "confidence": "high|medium|low"
  } or null,
  "disambiguation_notes": null or a string explaining why a person reference is ambiguous
}

== THE RULES — FOLLOW THESE EXACTLY ==

RULE 1 — REAL OPERATIONS ONLY:
operation_hint MUST be: create, list, update, delete.
View/see/check/find/show/search/lookup → "list".
Make/add/schedule/create/order/book/log/prescribe → "create".
Change/move/edit/mark/complete/process/assign/share/send → "update".
Remove/cancel/delete → "delete".

RULE 2 — EVERY PERSON GETS A person_ref:
For EVERY person referenced by name or alias:
  - raw = EXACT text the user used.
  - Check the PEOPLE section. If the name matches multiple people → needs_resolution=true + disambiguation_notes.
  - "me"/"my"/"I"/"we"/"our" → raw="me".
  - Even for self-directed actions, STILL add raw="me".

RULE 3 — EVERY INTENT GETS A resource_ref:
For EACH distinct service the user targets:
  - resource_kind_hint = which kind of resource from the service descriptions.
  - Use natural names. The downstream resolver handles exact matching.

RULE 4 — SPLIT COMPOUND UTTERANCES:
"And" connecting two DIFFERENT actions → two intents.
Two DIFFERENT people for the same action → ONE intent PER person.
ONE action → ONE intent.

RULE 5 — TIME:
User mentions ANY time → include time_window_hint with raw_phrase = exact words.
Future action with NO time given → {"raw_phrase": "unspecified", "confidence": "low"}.
Queries about current state with no time context → time_window_hint = null.

RULE 6 — USE CONTEXT FOR CREATIVE LANGUAGE:
Indirect phrasing ("Has X been good?", "Make sure X does Y", "What should we do?")
→ use BELIEFS and service descriptions to infer the right service and operation.

RULE 7 — CONFIDENCE REFLECTS EVIDENCE:
"high" = explicit words. "medium" = reasonable inference. "low" = guessing.

RULE 8 — NEVER INVENT:
Use raw values as they appear. Never generate IDs. Downstream handles lookup.

RULE 9 — EMPTY OR NOISE:
Empty/meaningless utterance → one intent with operation_hint="compute", resource_kind_hint=null, empty person_refs, empty resource_refs, time_window_hint=null.
Otherwise ALWAYS pick a real domain and operation.

RULE 10 — OUTPUT FORMAT IS NON-NEGOTIABLE:
Your ENTIRE response must be a single JSON object starting with { and ending with }.
No markdown fences. No leading/trailing text. No explanation."""


# ═══════════════════════════════════════════════════════════════════
# EVALUATORS (6-dimension framework)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DimensionResult:
    passed: bool
    expected: Any
    actual: Any
    detail: str


@dataclass
class ScenarioResult:
    scenario_id: str
    domain_id: str
    utterance: str
    passed: bool
    dimensions: dict[str, DimensionResult]
    raw_output: dict[str, Any]
    latency_ms: float


def _resource_kind_matches(actual: str | None, expected: str | None) -> bool:
    """Fuzzy resource kind matching."""
    if actual == expected:
        return True
    if actual is None and expected is None:
        return True
    if not actual or not expected:
        return False
    a, e = str(actual).lower().strip(), str(expected).lower().strip()
    if a in e or e in a:
        return True
    a_words = set(a.replace("_", " ").replace("-", " ").split())
    e_words = set(e.replace("_", " ").replace("-", " ").split())
    if a_words & e_words:
        return True
    _SEMANTIC_ALIASES: dict[str, str] = {
        "appointment": "calendar_event",
        "event": "calendar_event",
        "meeting": "calendar_event",
        "schedule": "calendar_event",
        "booking": "calendar_event",
        "todo": "task",
        "assignment": "task",
        "groceries": "shopping_item",
        "grocery": "shopping_item",
        "notification": "reminder",
        "alert": "reminder",
        "nudge": "reminder",
        "bug": "task",
        "feature": "task",
        "issue": "task",
        "message": "reminder",
        "forecast": "weather_forecast",
        "weather": "weather_forecast",
        "frost": "frost_alert",
        "supply": "supply_order",
        "order": "supply_order",
        "repair": "repair_ticket",
        "maintenance": "maintenance_log",
        "inspection": "permit",
        "hearing": "meeting",
        "case": "violation",
        "foia": "record",
        "prescription": "prescription",
        "medication": "prescription",
        "refill": "refill",
        "lab": "lab_order",
        "labs": "lab_order",
        "result": "lab_result",
        "chart": "patient_record",
        "note": "progress_note",
        "consult": "consult",
        "followup": "follow_up",
        "follow-up": "follow_up",
        "assign": "task",
        "share": "document",
    }
    if _SEMANTIC_ALIASES.get(a) == e or _SEMANTIC_ALIASES.get(e) == a:
        return True
    return False


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


def evaluate_dimensions(
    scenario: FrameScenario, output: dict[str, Any]
) -> dict[str, DimensionResult]:
    dims: dict[str, DimensionResult] = {}

    if isinstance(output, list):
        output = {"intents": output} if output else {"intents": []}
    if not isinstance(output, dict):
        output = {"intents": []}

    intents = output.get("intents") or []
    person_refs = output.get("person_refs") or []
    time_hint = output.get("time_window_hint")
    disamb = output.get("disambiguation_notes")

    # 1. Operation accuracy
    actual_ops = [_normalize_op(i.get("operation_hint", "")) for i in intents]
    expected_ops = [_normalize_op(o) for o in scenario.expected_operations]
    while len(actual_ops) < len(expected_ops):
        actual_ops.append("")
    while len(expected_ops) < len(actual_ops):
        expected_ops.append("")
    op_match = all(a == e for a, e in zip(actual_ops, expected_ops))
    dims["operation"] = DimensionResult(
        passed=op_match,
        expected=expected_ops,
        actual=actual_ops,
        detail=f"Expected {expected_ops}, got {actual_ops}",
    )

    # 2. Resource accuracy (fuzzy)
    actual_rk = [i.get("resource_kind_hint") for i in intents]
    expected_rk = scenario.expected_resource_kinds
    while len(actual_rk) < len(expected_rk):
        actual_rk.append(None)
    while len(expected_rk) < len(actual_rk):
        expected_rk.append(None)
    rk_match = all(_resource_kind_matches(a, e) for a, e in zip(actual_rk, expected_rk))
    dims["resource"] = DimensionResult(
        passed=rk_match,
        expected=expected_rk,
        actual=actual_rk,
        detail=f"Expected {expected_rk}, got {actual_rk}",
    )

    # 3. Person accuracy
    actual_persons = [p.get("raw", "") for p in person_refs]
    expected_persons = [p for p in scenario.expected_persons if p]
    person_match = True
    for ep in expected_persons:
        found = any(
            ep.lower() in ap.lower()
            or (ep.lower() == "me" and ap.lower() in ("me", "my", "i", "we", "us", ""))
            for ap in actual_persons
        )
        if not found:
            person_match = False
            break
    dims["person"] = DimensionResult(
        passed=person_match,
        expected=expected_persons,
        actual=actual_persons,
        detail=f"Expected {expected_persons}, got {actual_persons}",
    )

    # 4. Time accuracy
    has_time = time_hint is not None and len(str(time_hint.get("raw_phrase", ""))) > 0
    time_passed = (scenario.expected_time_required and has_time) or (
        not scenario.expected_time_required
    )
    dims["time"] = DimensionResult(
        passed=time_passed,
        expected="time required" if scenario.expected_time_required else "no time required",
        actual=f"time_hint={'present' if time_hint else 'missing'}",
        detail=str(time_hint)[:100] if time_hint else "No time hint",
    )

    # 5. Completeness (intent count)
    count_match = len(intents) >= scenario.intent_count
    dims["completeness"] = DimensionResult(
        passed=count_match,
        expected=scenario.intent_count,
        actual=len(intents),
        detail=f"Expected at least {scenario.intent_count} intents, got {len(intents)}",
    )

    # 6. Disambiguation
    if scenario.needs_disambiguation:
        disamb_passed = bool(disamb) and len(str(disamb)) > 5
    else:
        disamb_passed = True
    dims["disambiguation"] = DimensionResult(
        passed=disamb_passed,
        expected=(
            "disambiguation required"
            if scenario.needs_disambiguation
            else "no disambiguation needed"
        ),
        actual=str(disamb)[:100] if disamb else "No disambiguation notes",
        detail=scenario.disambiguation_reason if scenario.needs_disambiguation else "",
    )

    return dims


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════════


async def run_scenario(
    client: ModelClient,
    scenario: FrameScenario,
    context_block: str,
) -> ScenarioResult:
    system_prompt = FRAME_EXTRACTION_SYSTEM_PROMPT + "\n\n" + context_block
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"<CURRENT_UTTERANCE>\n{scenario.utterance}\n</CURRENT_UTTERANCE>\n\nConvert this utterance to structured JSON as specified.",
        },
    ]

    start = time.perf_counter()
    try:
        response = await client.chat(
            messages=messages,
            tools=[],
            tool_choice="none",
            temperature=0.0,
            max_tokens=2048,
        )
        elapsed = (time.perf_counter() - start) * 1000
        content = (response.content or "").strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    parsed = {"error": "json_parse_failed", "raw": content[:500]}
            else:
                parsed = {"error": "json_parse_failed", "raw": content[:500]}
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        parsed = {"error": str(exc)}

    dims = evaluate_dimensions(scenario, parsed)
    all_pass = all(d.passed for d in dims.values())

    return ScenarioResult(
        scenario_id=scenario.id,
        domain_id=scenario.domain_id,
        utterance=scenario.utterance,
        passed=all_pass,
        dimensions=dims,
        raw_output=parsed,
        latency_ms=round(elapsed, 2),
    )


async def run_benchmark(client: ModelClient | None = None) -> dict[str, Any]:
    if client is None:
        client = create_model_client_from_env()

    provider = os.environ.get("LLM_PROVIDER", "unknown")
    print(f"Provider: {provider} | Model: {client.model_id}")
    print(f"Scenarios: {len(SCENARIOS)} across {len(ALL_DOMAIN_CONTEXTS)} domains")
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
            f"[{i+1:02d}/{len(SCENARIOS)}] {scenario.id} [{scenario.domain_id}]: {scenario.utterance[:70]}"
        )
        result = await run_scenario(client, scenario, ctx_block)
        results.append(result)

        dim_summary = " | ".join(
            f"{k}={'✓' if v.passed else '✗'}" for k, v in result.dimensions.items()
        )
        status = "PASS" if result.passed else "FAIL"
        print(f"         {status} | {dim_summary} | {result.latency_ms:.0f}ms")

        if not result.passed:
            for dim_name, dim in result.dimensions.items():
                if not dim.passed:
                    print(f"         ✗ {dim_name}: {dim.detail}")

    # ── Aggregate ──
    dimension_names = ["operation", "resource", "person", "time", "completeness", "disambiguation"]
    dim_scores: dict[str, float] = {}
    for dim_name in dimension_names:
        dim_results = [r.dimensions[dim_name] for r in results]
        passed = sum(1 for d in dim_results if d.passed)
        dim_scores[dim_name] = round(passed / len(dim_results), 4)

    overall = sum(1 for r in results if r.passed)
    overall_score = round(overall / len(results), 4)
    avg_latency = statistics.mean([r.latency_ms for r in results])

    # ── By-domain breakdown ──
    domain_scores: dict[str, dict[str, Any]] = {}
    for domain_id in ALL_DOMAIN_CONTEXTS:
        domain_results = [r for r in results if r.domain_id == domain_id]
        if domain_results:
            passed = sum(1 for r in domain_results if r.passed)
            domain_scores[domain_id] = {
                "label": ALL_DOMAIN_CONTEXTS[domain_id].domain_label,
                "total": len(domain_results),
                "passed": passed,
                "score": round(passed / len(domain_results), 4),
            }

    print(f"\n{'='*70}")
    print("BENCHMARK RESULTS — Back LLM Frame Extraction v2 (Domain-Agnostic)")
    print(f"{'='*70}")
    print(f"Provider: {provider} | Model: {client.model_id}")
    print(f"Overall pass rate: {overall}/{len(results)} ({overall_score:.0%})")
    print(f"Avg latency: {avg_latency:.0f}ms")
    print()
    for dim_name in dimension_names:
        score = dim_scores[dim_name]
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  {dim_name:<18} {bar} {score:.0%}")
    print()
    print("By domain:")
    for domain_id in ["family", "enterprise", "government", "agriculture", "healthcare"]:
        ds = domain_scores.get(domain_id, {})
        label = ds.get("label", domain_id)
        score = ds.get("score", 0)
        bar = "█" * int(score * 15) + "░" * (15 - int(score * 15))
        print(f"  {label:<50} {bar} {score:.0%}")

    # Per-scenario table
    print(f"\n{'─'*80}")
    print(f"{'ID':<7} {'Domain':<12} {'Utterance':<42} {'Pass':<6}")
    print(f"{'─'*80}")
    for r in results:
        status = "✓" if r.passed else "✗"
        print(f"{r.scenario_id:<7} {r.domain_id:<12} {r.utterance[:40]:<42} {status:<6}")
    print(f"{'─'*80}")

    return {
        "provider": provider,
        "model": client.model_id,
        "overall_score": overall_score,
        "dimension_scores": dim_scores,
        "domain_scores": domain_scores,
        "total_scenarios": len(results),
        "passed": overall,
        "avg_latency_ms": round(avg_latency, 1),
        "results": [
            {
                "id": r.scenario_id,
                "domain": r.domain_id,
                "utterance": r.utterance,
                "passed": r.passed,
                "dimensions": {k: v.passed for k, v in r.dimensions.items()},
                "latency_ms": r.latency_ms,
            }
            for r in results
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# DRY-RUN (offline analysis — no LLM calls)
# ═══════════════════════════════════════════════════════════════════


def dry_run_analysis() -> dict[str, Any]:
    """Analyze prompts and scenarios without LLM calls."""
    domain_stats: dict[str, dict] = {}
    for domain_id, ctx in ALL_DOMAIN_CONTEXTS.items():
        ctx_block = build_context_block(ctx)
        prompt = FRAME_EXTRACTION_SYSTEM_PROMPT + "\n\n" + ctx_block
        scenario_count = len([s for s in SCENARIOS if s.domain_id == domain_id])
        domain_stats[domain_id] = {
            "label": ctx.domain_label,
            "context_chars": len(ctx_block),
            "prompt_chars": len(prompt),
            "approx_tokens": len(prompt) // 4,
            "scenarios": scenario_count,
        }

    print("=" * 60)
    print("DRY RUN ANALYSIS — Prompt Structure Review (v2 Domain-Agnostic)")
    print("=" * 60)
    print(f"\nDomains: {len(ALL_DOMAIN_CONTEXTS)}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print()

    for domain_id, stats in domain_stats.items():
        print(f"  {stats['label']}:")
        print(
            f"    Context: {stats['context_chars']:,} chars (~{stats['context_chars']//4:,} tokens)"
        )
        print(
            f"    Full prompt: {stats['prompt_chars']:,} chars (~{stats['approx_tokens']:,} tokens)"
        )
        print(f"    Scenarios: {stats['scenarios']}")

    print("\nNo chat history — pure query + context model.")
    print("Prompt is principle-based (10 rules). No keyword hints per service.")

    # Scenario distribution
    print("\n--- SCENARIO DISTRIBUTION ---")
    by_op: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    for s in SCENARIOS:
        by_domain[s.domain_id] = by_domain.get(s.domain_id, 0) + 1
        for op in s.expected_operations:
            by_op[op] = by_op.get(op, 0) + 1
    for domain_id, count in sorted(by_domain.items()):
        print(f"  {domain_id}: {count}")
    for op, count in sorted(by_op.items()):
        print(f"  op:{op}: {count}")

    return {
        "domains": len(ALL_DOMAIN_CONTEXTS),
        "scenarios": len(SCENARIOS),
        "domain_stats": domain_stats,
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════════╗
║   Back LLM Frame Extraction Benchmark v2            ║
║   Domain-Agnostic — 50 scenarios across 5 domains   ║
╠══════════════════════════════════════════════════════╣
║  1. Dry-run analysis (review prompts, no LLM)       ║
║  2. Run with env-configured LLM provider            ║
║  0. Exit                                            ║
╚══════════════════════════════════════════════════════╝"""


def main() -> int:
    print(MENU)
    choice = input("Select benchmark [1-2, 0]: ").strip()

    if choice == "1":
        result = dry_run_analysis()
        out_path = Path("data/llm_frame_bench/dry_run_v2.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved to {out_path}")
        return 0

    if choice == "2":
        try:
            client = create_model_client_from_env()
        except Exception as exc:
            print(f"\nERROR: Cannot create model client: {exc}")
            print("Set these env vars:")
            print(
                "  For Vertex:  $env:LLM_PROVIDER='vertex'; $env:GOOGLE_CLOUD_PROJECT='...'; $env:GOOGLE_CLOUD_LOCATION='global'"
            )
            return 1

        provider = os.environ.get("LLM_PROVIDER", "unknown")
        print(f"\nUsing provider: {provider}")
        print(f"Model: {client.model_id}")
        print()

        result = asyncio.run(run_benchmark(client=client))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_slug = client.model_id.replace("/", "_").replace("-", "_")
        out_path = Path(f"data/llm_frame_bench/results_v2_{provider}_{model_slug}_{ts}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved to {out_path}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
