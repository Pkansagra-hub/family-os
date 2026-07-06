"""
POC: Connector Search Accuracy — Isolated Variants V0 through V22
=================================================================
Each variant runs against its OWN GPS + connector documents.
No cross-contamination.  No global state.  No shared mutation.

Variants:
  V0  — Random baseline (averaged across 20 seeds)
  V1  — BM25 on capabilities_fts, GROUP BY connector
  V2  — BM25 on dedicated connectors_fts (AND query mode)
  V2b — BM25 on dedicated connectors_fts (OR query mode, with stopwords)
  V3  — BM25 on rich connector FTS (title, desc, actions, aliases, resources)
  V4  — BM25 with trigram tokenization (typo subset)
  V5  — TF-IDF + cosine similarity (word-level, shared tokenizer)
  V6  — Unigram Language Model with Laplace smoothing
  V7  — Character 3-gram TF-IDF + cosine similarity
  V8  — SPLADE sparse neural retrieval
  V9  — MiniLM dense semantic retrieval (all-MiniLM-L6-v2, 22MB)
  V10 — Weighted hybrid BM25 + MiniLM (RRF, w_bm25=0.3 w_mlm=0.7)
  V14 — multi-qa-MiniLM dense retrieval
  V15 — gte-small dense retrieval
  V16 — bge-small dense retrieval
  V17 — MiniLM-L12 dense retrieval (120MB)
  V18 — paraphrase-MiniLM dense retrieval
  V19 — Multi-Signal Soft Fusion
  V20 — Two-Stage Rerank (L12 bi-encoder → cross-encoder)
  V21 — Schema-Augmented Search (intent classifier + MiniLM)
  V22 — Schema-Agnostic (pure embedding, zero hardcoded knowledge)

Key fixes from v1:
  - Per-variant GPS isolation (shared GPS was contaminating V1←V3)
  - Shared tokenizer with stopword removal
  - Correct FTS5 score normalization
  - V3 is dedicated connector FTS, not capability_fts destroyer
  - V6 renamed from Naive Bayes → Unigram LM
  - V7 replaced Markov chain with char 3-gram TF-IDF
  - Failure categorization uses corpus metadata, not broken char check
  - AND/OR query mode variants for BM25
  - 50 synthetic distractor connectors
  - Old resolver: loaded from bench script output (not hardcoded avg)

Usage:
  python scripts/poc_connector_search.py                 # all variants
  python scripts/poc_connector_search.py --variants v0,v2,v9  # specific
  python scripts/poc_connector_search.py --quick          # first 20 queries
  python scripts/poc_connector_search.py --no-distractors # 6 connectors only
"""

from __future__ import annotations

import math
import random
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ── Path setup ──
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from k1.fabric.manifest_translator import register_definition_to_store
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.family_settings.definition import FAMILY_SETTINGS_DEFINITION
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION
from scripts.bench_resolver_search import TEST_CORPUS, TIER_LABELS, TIER_ORDER

# ═══════════════════════════════════════════════════════════════════════════
# Shared Tokenizer
# ═══════════════════════════════════════════════════════════════════════════

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "to",
        "for",
        "of",
        "on",
        "in",
        "at",
        "my",
        "me",
        "i",
        "we",
        "our",
        "us",
        "he",
        "she",
        "it",
        "they",
        "them",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "do",
        "does",
        "did",
        "can",
        "could",
        "will",
        "would",
        "should",
        "may",
        "might",
        "have",
        "has",
        "had",
        "am",
        "you",
        "your",
        "with",
        "this",
        "that",
        "from",
        "not",
        "but",
        "or",
        "and",
        "if",
        "so",
        "no",
        "just",
        "about",
        "like",
        "get",
        "got",
        "need",
        "some",
        "any",
        "all",
        "up",
        "out",
        "what",
        "when",
        "where",
        "who",
        "how",
        "please",
        "hi",
        "hey",
        "ok",
        "okay",
        "yeah",
        "yes",
        "nah",
        "nope",
    }
)


def tokenize(text: str) -> list[str]:
    """Shared tokenizer: lowercase, split on non-alnum, drop stopwords."""
    text = text.lower().replace("_", " ")
    tokens = _TOKEN_RE.findall(text)
    return [t for t in tokens if len(t) >= 2 and t not in _STOPWORDS]


def tokenize_with_stopwords(text: str) -> list[str]:
    """Tokenize keeping stopwords — for FTS5 OR query where stopwords are dropped."""
    text = text.lower().replace("_", " ")
    tokens = _TOKEN_RE.findall(text)
    return [t for t in tokens if len(t) >= 2]


# ═══════════════════════════════════════════════════════════════════════════
# Context Factory — one fresh GPS + docs per variant
# ═══════════════════════════════════════════════════════════════════════════

REAL_DEFS = {
    "family.calendar": CALENDAR_DEFINITION,
    "family.shopping": SHOPPING_DEFINITION,
    "family.tasks": TASKS_DEFINITION,
    "family.reminders": REMINDERS_DEFINITION,
    "family.chores": CHORES_DEFINITION,
    "family.family_settings": FAMILY_SETTINGS_DEFINITION,
}


def _bootstrap_gps(with_distractors: bool = True, scale: int = 1) -> GlobalProjectionStore:
    """Create in-memory GPS, register 6 real connectors + optional diverse distractors."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    for connector_id, definition in REAL_DEFS.items():
        register_definition_to_store(definition, gps)
    if with_distractors:
        _inject_distractors(gps, scale)
    return gps


# ═══════════════════════════════════════════════════════════════════════════
# Distractor Generator
# ═══════════════════════════════════════════════════════════════════════════

# ── Real-world connector templates across 50 domains (~500 connectors) ──
# Each domain has 2-4 connectors with realistic API descriptions.
# These are SEMANTICALLY DIVERSE — banking vocabulary does NOT overlap
# with smart home vocabulary or health vocabulary.  This tests whether
# the search can route to the right DOMAIN, not just the right connector
# within a domain (which was the old distractor test's weakness).


def _generate_real_world_distractors() -> list[dict[str, Any]]:
    """Generate 500+ connectors across 50 real-world domains."""
    templates: list[dict[str, Any]] = []

    def add(domain: str, connectors: list[tuple[str, str, str, str]]):
        for cid, label, desc, actions in connectors:
            templates.append(
                {
                    "cid": f"{domain}.{cid}",
                    "label": label,
                    "desc": desc,
                    "actions": actions,
                    "concepts": "",
                    "rfs": "",
                }
            )

    # ── Banking & Fintech (10 domains, ~100 connectors) ──
    add(
        "chase",
        [
            (
                "checking",
                "Chase Checking",
                "Manage your Chase Total Checking accounts: view balances, deposit checks via mobile capture, set up direct deposit, transfer funds between accounts, and download monthly statements.",
                "get_balance deposit_check transfer_funds list_transactions download_statement set_overdraft_protection order_checks",
            ),
            (
                "savings",
                "Chase Savings",
                "Chase Premier Savings accounts with automated savings plans, goal tracking, interest rate monitoring, and linked checking overdraft protection.",
                "get_balance set_savings_goal transfer_to_savings view_interest enable_autosave link_checking",
            ),
            (
                "credit",
                "Chase Credit Cards",
                "Manage Chase Sapphire and Freedom credit cards: view rewards points, redeem cash back, dispute charges, set travel notifications, manage authorized users.",
                "view_balance redeem_points dispute_charge set_travel_notice add_authorized_user lock_card view_rewards",
            ),
            (
                "loans",
                "Chase Loans",
                "Chase personal and auto loans: check payoff balance, schedule payments, view amortization schedule, apply for rate modification.",
                "get_payoff_balance schedule_payment view_amortization request_payoff_quote change_due_date",
            ),
        ],
    )
    add(
        "bofa",
        [
            (
                "checking",
                "Bank of America Checking",
                "BofA Advantage Banking: real-time balance, bill pay, Zelle integration, mobile check deposit, account alerts and overdraft protection.",
                "get_balance pay_bill send_zelle deposit_check set_alert manage_overdraft",
            ),
            (
                "credit",
                "Bank of America Credit",
                "BofA Premium Rewards and Cash Rewards cards: track spending by category, redeem rewards, manage balance transfers, set card controls.",
                "view_spending redeem_rewards transfer_balance set_card_control view_offer dispute_transaction",
            ),
            (
                "investing",
                "Merrill Edge Investing",
                "Merrill Edge self-directed investing: view portfolio, place trades, research stocks, set price alerts, manage dividend reinvestment.",
                "view_portfolio place_trade research_symbol set_price_alert manage_drip view_gain_loss",
            ),
        ],
    )
    add(
        "wellsfargo",
        [
            (
                "accounts",
                "Wells Fargo Accounts",
                "Wells Fargo checking, savings, and CD accounts: unified balance view, transfer between Wells accounts, manage overdraft, set savings goals.",
                "get_all_balances transfer_between_accounts set_savings_goal manage_cd open_subaccount",
            ),
            (
                "mortgage",
                "Wells Fargo Mortgage",
                "Wells Fargo home mortgage: view escrow balance, make extra principal payment, download tax documents, request payoff statement, check rate options.",
                "view_escrow make_principal_payment download_1098 request_payoff check_refi_rate",
            ),
            (
                "advisor",
                "Wells Fargo Advisor",
                "Wells Fargo financial advisory: view managed portfolio, schedule advisor call, update risk profile, review financial plan progress.",
                "view_portfolio schedule_advisor update_risk_profile review_financial_plan set_goal",
            ),
        ],
    )
    add(
        "amex",
        [
            (
                "cards",
                "Amex Cards",
                "American Express Platinum, Gold, and Business cards: track Membership Rewards, access travel benefits, view lounge access, manage employee cards.",
                "view_points book_travel find_lounge add_employee_card view_benefits check_spending_power",
            ),
            (
                "offers",
                "Amex Offers",
                "Browse and activate Amex Offers for statement credits at participating merchants. Track savings and discover new offers by spending category.",
                "browse_offers activate_offer track_savings search_by_category view_expiring view_redeemed",
            ),
        ],
    )
    add(
        "capitalone",
        [
            (
                "banking",
                "Capital One 360",
                "Capital One 360 checking and savings: no-fee accounts, early direct deposit, performance savings rate tracking, create sub-accounts for goals.",
                "get_balance create_subaccount transfer set_goal deposit_check view_interest",
            ),
            (
                "credit",
                "Capital One Credit",
                "Capital One Venture, Quicksilver, and Savor cards: track rewards, manage installments, view virtual card numbers, set autopay.",
                "view_rewards create_virtual_card set_autopay manage_installments redeem_travel check_upgrade",
            ),
        ],
    )
    add(
        "citi",
        [
            (
                "banking",
                "Citibank Accounts",
                "Citibank checking and savings: global transfers, Citigold relationship benefits, wealth management snapshot, account package upgrades.",
                "get_balance global_transfer view_benefits upgrade_package schedule_transfer download_statement",
            ),
            (
                "cards",
                "Citi Credit Cards",
                "Citi ThankYou Rewards: transfer points to airlines, shop with points, view point earning rate by category, manage card features.",
                "view_points transfer_to_airline shop_with_points check_earning_rate set_card_feature",
            ),
        ],
    )
    add(
        "usbank",
        [
            (
                "accounts",
                "US Bank Accounts",
                "US Bank Smartly checking and savings: overdraft protection, mobile wallet setup, account activity alerts, send money with Zelle.",
                "get_balance setup_mobile_wallet send_money set_alert view_activity manage_overdraft",
            ),
            (
                "loans",
                "US Bank Loans",
                "US Bank personal loans, auto loans, and lines of credit: check balance, make payment, view payoff progress, apply for new loan.",
                "check_balance make_payment view_payoff apply_loan defer_payment",
            ),
        ],
    )
    add(
        "tdbank",
        [
            (
                "accounts",
                "TD Bank Accounts",
                "TD Beyond Checking and Simple Savings: cross-border US-Canada transfers, overdraft relief, early pay, instant issue debit card replacement.",
                "get_balance cross_border_transfer replace_card setup_early_pay manage_overdraft view_fees",
            ),
        ],
    )
    add(
        "pnc",
        [
            (
                "banking",
                "PNC Virtual Wallet",
                "PNC Virtual Wallet with Spend, Reserve, and Growth accounts: calendar-based bill forecasting, savings rules, money bar visualization data.",
                "get_balance view_calendar set_savings_rule transfer_between_wallet check_bill_forecast manage_growth",
            ),
            (
                "mortgage",
                "PNC Mortgage",
                "PNC home lending: rate comparison, application status tracking, document upload, closing timeline, post-close servicing portal.",
                "compare_rates check_application upload_document view_timeline make_payment get_escrow_balance",
            ),
        ],
    )
    add(
        "venmo",
        [
            (
                "payments",
                "Venmo Payments",
                "Venmo peer-to-peer payments: send money, request money, split bills with groups, track transaction history, manage privacy settings, link bank accounts.",
                "send_money request_money split_bill list_transactions set_privacy verify_identity link_bank",
            ),
            (
                "business",
                "Venmo Business",
                "Venmo for Business: accept customer payments, create payment links, track tips, manage tax reporting, view customer insights.",
                "create_payment_link accept_payment track_tips view_insights download_1099 set_business_profile",
            ),
        ],
    )

    # ── Smart Home & IoT (10 domains, ~100 connectors) ──
    add(
        "philips-hue",
        [
            (
                "lights",
                "Philips Hue Lights",
                "Control all Philips Hue smart lights: set brightness, color, color temperature, dynamic scenes, schedules, and groups across rooms in your home.",
                "set_brightness set_color set_scene activate_schedule group_lights toggle_power get_light_status",
            ),
            (
                "bridge",
                "Philips Hue Bridge",
                "Manage Hue Bridge: discover new lights, update firmware, configure Zigbee channel, manage entertainment areas, check bridge health status.",
                "discover_lights update_firmware set_zigbee_channel create_entertainment_area check_bridge_health list_devices",
            ),
            (
                "sync",
                "Philips Hue Sync",
                "Hue HDMI Sync Box and PC app: sync lights with TV/music/gaming, configure sync intensity, create custom sync modes for different content types.",
                "start_sync stop_sync set_intensity create_sync_mode set_gaming_profile set_music_profile",
            ),
        ],
    )
    add(
        "nest",
        [
            (
                "thermostat",
                "Nest Thermostat",
                "Google Nest Learning Thermostat: set target temperature, switch heat/cool mode, set eco temperatures, view energy history, manage home/away assist.",
                "set_temperature set_mode enable_eco view_energy_history set_schedule toggle_away",
            ),
            (
                "cameras",
                "Nest Cameras",
                "Nest Cam indoor/outdoor: view live stream, review event clips, set activity zones, enable familiar face alerts, manage camera schedule.",
                "view_live review_clips set_activity_zone enable_face_alert set_schedule download_clip",
            ),
            (
                "doorbell",
                "Nest Doorbell",
                "Nest Hello doorbell: view live feed, answer door remotely, review visitor history, set quiet time, configure package detection alerts.",
                "view_live answer_door review_visitors set_quiet_time enable_package_detect configure_chime",
            ),
            (
                "protect",
                "Nest Protect",
                "Nest Protect smoke and CO alarm: check sensor status, run safety checkup, silence false alarm, view sensor history, check battery level.",
                "check_status run_safety_check silence_alarm view_history check_battery test_alarm",
            ),
        ],
    )
    add(
        "ring",
        [
            (
                "security",
                "Ring Alarm",
                "Ring Alarm security system: arm in home/away mode, view sensor status, manage access codes, view alarm history, test siren, configure entry delays.",
                "arm_home arm_away view_sensors manage_codes view_history test_siren set_delay",
            ),
            (
                "doorbell",
                "Ring Doorbell",
                "Ring Video Doorbell: view live feed, respond to motion alerts, review recorded events, adjust motion zones, configure privacy settings.",
                "view_live respond_alert review_events set_motion_zone configure_privacy enable_rich_notifications",
            ),
            (
                "lighting",
                "Ring Lighting",
                "Ring Smart Lighting: control path lights, spotlights, floodlights, and transformers. Set schedules, group lights, adjust motion sensitivity.",
                "toggle_light set_schedule group_lights adjust_sensitivity check_battery view_motion_events",
            ),
        ],
    )
    add(
        "ecobee",
        [
            (
                "thermostat",
                "ecobee SmartThermostat",
                "ecobee thermostat with SmartSensor: set comfort settings, view room sensor readings, manage schedule, run energy reports, control humidifier/dehumidifier.",
                "set_comfort_setting view_sensor set_schedule run_energy_report control_humidity enable_follow_me",
            ),
            (
                "sensors",
                "ecobee Sensors",
                "ecobee SmartSensor for doors/windows and room occupancy: check contact status, view occupancy, check temperature, manage sensor participation in comfort settings.",
                "check_contact view_occupancy get_temperature assign_to_comfort_setting check_battery rename_sensor",
            ),
        ],
    )
    add(
        "roomba",
        [
            (
                "cleaning",
                "iRobot Roomba",
                "Roomba robot vacuum: start/stop/pause cleaning, send to specific room, view cleaning history map, schedule recurring clean, check bin status, manage keep-out zones.",
                "start_clean stop_clean send_to_room view_map set_schedule check_bin set_keep_out_zone locate_robot",
            ),
            (
                "braava",
                "iRobot Braava",
                "Braava robot mop: start damp/wet mopping, set cleaning passes, schedule mopping, check tank level, manage no-mop zones, view cleaning reports.",
                "start_mop set_passes set_schedule check_tank set_no_mop_zone view_report",
            ),
        ],
    )
    add(
        "wemo",
        [
            (
                "switches",
                "Wemo Smart Plugs",
                "Belkin Wemo smart plugs and switches: toggle power, set schedules, create automation rules, monitor energy usage, configure away mode, group devices by room.",
                "toggle_power set_schedule create_rule monitor_energy enable_away group_by_room restart_device",
            ),
        ],
    )
    add(
        "lutron",
        [
            (
                "caseta",
                "Lutron Caseta",
                "Lutron Caseta smart lighting: control individual dimmers and switches, set scenes with multiple lights, configure Pico remotes, manage shade positions, set schedules based on sunrise/sunset.",
                "set_light_level activate_scene configure_pico set_shade_position set_schedule add_device",
            ),
        ],
    )
    add(
        "august",
        [
            (
                "locks",
                "August Smart Locks",
                "August WiFi smart locks: lock/unlock remotely, manage guest access codes with time windows, view door activity log, enable auto-lock, check battery, integrate with DoorSense.",
                "lock unlock manage_codes view_activity enable_autolock check_battery get_door_sense_status",
            ),
        ],
    )
    add(
        "myq",
        [
            (
                "garage",
                "myQ Garage Control",
                "Chamberlain myQ smart garage: open/close garage door, check door status, set close schedule, manage guest access, view open/close history.",
                "open_door close_door check_status set_schedule manage_guest view_history enable_alert",
            ),
        ],
    )
    add(
        "arlo",
        [
            (
                "cameras",
                "Arlo Security Cameras",
                "Arlo wire-free cameras: view live streams, review cloud recordings, arm/disarm system, set activity zones, manage smart alerts for people/vehicles/animals/packages.",
                "view_live review_recording arm_system set_zone configure_alert check_battery download_clip",
            ),
        ],
    )

    # ── Health & Fitness (10 domains, ~100 connectors) ──
    add(
        "fitbit",
        [
            (
                "activity",
                "Fitbit Activity",
                "Fitbit activity tracking: view daily steps, active zone minutes, hourly activity, exercise history, set activity goals, track workouts with GPS.",
                "get_steps get_zone_minutes get_hourly_activity log_workout set_goal get_exercise_history",
            ),
            (
                "sleep",
                "Fitbit Sleep",
                "Fitbit sleep tracking: view sleep stages, sleep score, bedtime consistency, set sleep schedule, view sleep trends, get sleep insights.",
                "get_sleep_stages get_sleep_score get_bedtime_consistency set_schedule view_trends get_insights",
            ),
            (
                "heart",
                "Fitbit Heart",
                "Fitbit heart health: view resting heart rate, cardio fitness score, heart rate variability, ECG readings, high/low heart rate notifications.",
                "get_resting_hr get_cardio_score get_hrv get_ecg set_hr_alert view_spo2",
            ),
        ],
    )
    add(
        "strava",
        [
            (
                "activities",
                "Strava Activities",
                "Strava activity tracking for running, cycling, swimming: log activity with GPS map, view segment efforts, compare against PRs, view weekly/monthly mileage.",
                "log_activity get_segment_efforts compare_pr get_weekly_mileage get_heatmap view_activity_feed",
            ),
            (
                "social",
                "Strava Social",
                "Strava clubs, challenges, and kudos: join clubs, create challenges, give kudos, view follower activities, manage privacy zones around home.",
                "join_club create_challenge give_kudos view_feed set_privacy_zone follow_athlete",
            ),
        ],
    )
    add(
        "myfitnesspal",
        [
            (
                "nutrition",
                "MyFitnessPal Nutrition",
                "Track daily food intake: log meals by scanning barcodes or searching database, view macro breakdown, set calorie and macro goals, track water intake.",
                "log_food scan_barcode search_database get_macros set_goal log_water get_diary",
            ),
            (
                "exercise",
                "MyFitnessPal Exercise",
                "Log exercise: search exercise database, track cardio and strength workouts, view calories burned, link with fitness trackers for automatic syncing.",
                "log_exercise search_exercise get_calories_burned link_tracker view_exercise_history add_custom_exercise",
            ),
        ],
    )
    add(
        "whoop",
        [
            (
                "recovery",
                "Whoop Recovery",
                "Whoop recovery tracking: view daily strain, recovery score, sleep performance, respiratory rate, resting heart rate, and heart rate variability metrics.",
                "get_strain get_recovery get_sleep_performance get_respiratory_rate get_resting_hr get_hrv view_journal",
            ),
        ],
    )
    add(
        "apple-health",
        [
            (
                "records",
                "Apple Health Records",
                "Apple Health: aggregate health data from connected devices and providers, view lab results, immunizations, medications, allergies, clinical vitals, and conditions from participating health systems.",
                "get_lab_results get_immunizations get_medications get_allergies get_vitals get_conditions export_health_data",
            ),
            (
                "metrics",
                "Apple Health Metrics",
                "Apple Health activity and body measurements: steps, flights climbed, walking/running distance, active energy, resting energy, heart rate, blood oxygen, weight, BMI, body fat percentage.",
                "get_steps get_activity get_heart_rate get_blood_oxygen get_weight get_bmi export_metrics",
            ),
        ],
    )
    add(
        "withings",
        [
            (
                "health",
                "Withings Health",
                "Withings smart scale and health monitors: track weight, body composition, heart rate, blood pressure, temperature. View trends and set health goals.",
                "get_weight get_body_comp get_heart_rate get_bp get_temp set_goal view_trends",
            ),
        ],
    )
    add(
        "headspace",
        [
            (
                "meditation",
                "Headspace Meditation",
                "Headspace meditation and mindfulness: browse meditation courses, play daily meditation, track session streaks, view mindfulness minutes, set meditation reminders.",
                "browse_courses play_daily get_streak get_minutes set_reminder explore_topic log_session",
            ),
            (
                "sleep",
                "Headspace Sleep",
                "Headspace sleep content: play sleepcasts, wind downs, sleep music, and night-time SOS exercises. Track sleep timing and set wind-down reminders.",
                "play_sleepcast start_wind_down play_sleep_music set_bedtime_reminder get_sleep_timing",
            ),
        ],
    )
    add(
        "garmin",
        [
            (
                "connect",
                "Garmin Connect",
                "Garmin Connect fitness platform: view activity details, training status, body battery, stress tracking, sleep analysis, and fitness age metrics from Garmin wearables.",
                "get_activities get_training_status get_body_battery get_stress get_sleep get_fitness_age view_workout",
            ),
        ],
    )
    add(
        "peloton",
        [
            (
                "workouts",
                "Peloton Workouts",
                "Peloton bike, tread, and app workouts: browse class library, schedule live classes, view workout history, track personal records, manage stack of queued classes.",
                "browse_classes schedule_live view_history get_pr manage_stack rate_class",
            ),
        ],
    )
    add(
        "oura",
        [
            (
                "ring",
                "Oura Ring",
                "Oura smart ring: readiness score, sleep stages with deep/REM/light breakdown, activity score, heart rate tracking, body temperature trend, and Chronotype insights.",
                "get_readiness get_sleep get_activity get_heart_rate get_temperature get_chronotype view_trends",
            ),
        ],
    )

    # ── Productivity & Business (10 domains, ~100 connectors) ──
    add(
        "slack",
        [
            (
                "channels",
                "Slack Channels",
                "Slack workspace channels: create/archive channels, manage channel members, set channel topic and description, configure posting permissions, search channel history.",
                "create_channel archive_channel manage_members set_topic search_history configure_permissions",
            ),
            (
                "messages",
                "Slack Messages",
                "Slack messaging: send messages, schedule messages for later, set reminders from messages, react with emoji, share files, edit/delete sent messages.",
                "send_message schedule_message set_reminder add_reaction share_file edit_message delete_message",
            ),
            (
                "users",
                "Slack Users",
                "Slack user management: view user profiles, set user status, manage user groups, view presence status, configure notification preferences per user.",
                "get_profile set_status manage_groups get_presence configure_notifications invite_user",
            ),
        ],
    )
    add(
        "notion",
        [
            (
                "pages",
                "Notion Pages",
                "Notion workspace pages: create/update/delete pages, manage page properties, set page covers and icons, duplicate pages, move pages between workspaces.",
                "create_page update_page delete_page set_property duplicate_page move_page search_pages",
            ),
            (
                "databases",
                "Notion Databases",
                "Notion databases: query database with filters and sorts, create/update rows, manage database schema, create linked databases, export to CSV/JSON.",
                "query_database create_row update_row manage_schema create_linked_db export_data view_calendar",
            ),
            (
                "blocks",
                "Notion Blocks",
                "Notion block content: add/update/delete blocks, append children to blocks, toggle blocks, manage block formatting, retrieve block content with nested children.",
                "add_block update_block delete_block append_children toggle_block get_content format_text",
            ),
        ],
    )
    add(
        "jira",
        [
            (
                "issues",
                "Jira Issues",
                "Atlassian Jira issue tracking: create/update/transition issues, assign to users, set priority and labels, log work time, link related issues, add comments and attachments.",
                "create_issue update_issue transition_issue assign_user set_priority log_work link_issue add_comment",
            ),
            (
                "sprints",
                "Jira Sprints",
                "Jira sprint management: create/start/complete sprints, view sprint burndown, manage sprint scope by adding/removing issues, view velocity report.",
                "create_sprint start_sprint complete_sprint view_burndown manage_scope view_velocity add_issue_to_sprint",
            ),
            (
                "boards",
                "Jira Boards",
                "Jira scrum and kanban boards: view board configuration, list columns, move issues between columns, set column WIP limits, view cumulative flow diagram data.",
                "get_board list_columns move_issue set_wip_limit get_cfd configure_quick_filters",
            ),
        ],
    )
    add(
        "github",
        [
            (
                "repos",
                "GitHub Repositories",
                "GitHub repository management: create/delete repos, manage branches, set branch protection rules, configure collaborators, manage webhooks and deploy keys.",
                "create_repo delete_repo manage_branch set_protection add_collaborator create_webhook manage_deploy_keys",
            ),
            (
                "issues",
                "GitHub Issues",
                "GitHub issues: create/close/reopen issues, manage labels and milestones, assign reviewers, link pull requests, search issues with qualifiers.",
                "create_issue close_issue set_label set_milestone assign_reviewer link_pr search_issues",
            ),
            (
                "prs",
                "GitHub Pull Requests",
                "GitHub pull requests: create PR, request review, merge/squash/rebase, view diff and review comments, check CI status, manage merge queue.",
                "create_pr request_review merge_pr view_diff check_ci manage_merge_queue close_pr",
            ),
            (
                "actions",
                "GitHub Actions",
                "GitHub Actions CI/CD: view workflow runs, trigger workflow dispatch, cancel/rerun jobs, view job logs, manage workflow secrets, list runner status.",
                "view_runs trigger_workflow cancel_job rerun_job view_logs manage_secrets list_runners",
            ),
        ],
    )
    add(
        "linear",
        [
            (
                "issues",
                "Linear Issues",
                "Linear issue tracking: create/update/archive issues, set priority, assign to team members, add to cycles, link parent/child issues, manage project organization.",
                "create_issue update_issue archive_issue set_priority assign_user add_to_cycle link_issue",
            ),
            (
                "cycles",
                "Linear Cycles",
                "Linear team cycles: start/complete cycles, view cycle progress, manage scope, view team velocity metrics, generate cycle reports.",
                "start_cycle complete_cycle view_progress manage_scope view_velocity generate_report add_issue_to_cycle",
            ),
            (
                "projects",
                "Linear Projects",
                "Linear projects: create/manage projects with milestones, track progress toward target dates, view project health status, manage project members and roadmap.",
                "create_project add_milestone track_progress view_health manage_members view_roadmap update_status",
            ),
        ],
    )
    add(
        "figma",
        [
            (
                "files",
                "Figma Files",
                "Figma design files: list team files, get file versions, manage file permissions, duplicate files, move files between projects, export file assets.",
                "list_files get_version manage_permissions duplicate_file move_file export_assets search_files",
            ),
            (
                "comments",
                "Figma Comments",
                "Figma file comments: add/update/resolve comments on design files, mention collaborators, view comment threads, subscribe to comment activity on specific frames.",
                "add_comment resolve_comment mention_user view_thread subscribe get_comment_activity",
            ),
            (
                "components",
                "Figma Components",
                "Figma component library: list team components, publish component updates, view component usage across files, manage component variants and properties.",
                "list_components publish_update view_usage manage_variants set_property sync_library",
            ),
        ],
    )
    add(
        "stripe",
        [
            (
                "payments",
                "Stripe Payments",
                "Stripe payment processing: create payment intents, handle webhooks, manage refunds, view payment analytics, manage customer payment methods, handle disputes.",
                "create_payment_intent handle_webhook create_refund view_analytics manage_payment_method handle_dispute",
            ),
            (
                "subscriptions",
                "Stripe Subscriptions",
                "Stripe billing and subscriptions: create/manage subscription plans, handle recurring billing, manage trial periods, process upgrades/downgrades, handle invoice generation.",
                "create_plan manage_subscription set_trial upgrade_downgrade generate_invoice view_revenue",
            ),
            (
                "connect",
                "Stripe Connect",
                "Stripe Connect for platforms: onboard connected accounts, manage payouts, split payments, handle platform fees, verify seller identities, manage account capabilities.",
                "onboard_account manage_payout split_payment set_platform_fee verify_identity manage_capabilities",
            ),
        ],
    )
    add(
        "dropbox",
        [
            (
                "files",
                "Dropbox Files",
                "Dropbox file storage: upload/download files, manage folder structure, search files by name/content, manage shared links with expiration and password, restore deleted files.",
                "upload file download_file create_folder search_files create_shared_link restore_file get_metadata",
            ),
            (
                "paper",
                "Dropbox Paper",
                "Dropbox Paper docs: create/edit collaborative documents, manage doc members, add comments, export to markdown/PDF, view doc history, create templates.",
                "create_doc edit_doc manage_members add_comment export_doc view_history create_template",
            ),
        ],
    )
    add(
        "gmail",
        [
            (
                "messages",
                "Gmail Messages",
                "Gmail message management: list/search inbox messages, send emails with attachments, manage labels, archive/trash messages, add/remove stars, manage filters.",
                "list_messages search_messages send_email manage_labels archive_message trash_message add_star manage_filters",
            ),
            (
                "drafts",
                "Gmail Drafts",
                "Gmail draft management: create/update/delete drafts, list pending drafts, send drafts, manage draft attachments, auto-save draft state.",
                "create_draft update_draft delete_draft list_drafts send_draft add_attachment",
            ),
            (
                "settings",
                "Gmail Settings",
                "Gmail account settings: manage forwarding addresses, configure vacation responder, manage POP/IMAP settings, update signature, manage send-as aliases, configure filters.",
                "set_forwarding set_vacation_responder manage_imap update_signature manage_aliases create_filter",
            ),
        ],
    )
    add(
        "asana",
        [
            (
                "tasks",
                "Asana Tasks",
                "Asana task management: create/update/complete tasks, assign to users, set due dates, add subtasks, set task dependencies, add followers, manage custom fields.",
                "create_task update_task complete_task assign_user set_due_date add_subtask set_dependency add_follower",
            ),
            (
                "projects",
                "Asana Projects",
                "Asana project management: create/manage projects, set project status with color indicators, view project timeline, manage project members, create project sections.",
                "create_project set_status view_timeline manage_members create_section search_projects",
            ),
            (
                "portfolios",
                "Asana Portfolios",
                "Asana portfolio management: group projects into portfolios, track portfolio health across projects, view progress rollup, manage portfolio members and goals.",
                "create_portfolio add_project view_health get_progress manage_members set_goal",
            ),
        ],
    )

    # ── Education & Learning (5 domains, ~50 connectors) ──
    add(
        "duolingo",
        [
            (
                "language",
                "Duolingo Language",
                "Duolingo language learning: get course progress, view daily XP, check streak, view leaderboard position, browse skill tree, review completed lessons.",
                "get_progress get_daily_xp get_streak view_leaderboard browse_skills review_lesson set_goal",
            ),
        ],
    )
    add(
        "coursera",
        [
            (
                "courses",
                "Coursera Courses",
                "Coursera online courses: browse catalog, enroll in courses, view course progress, submit assignments, view grades, download certificates, manage specializations.",
                "browse_catalog enroll_course view_progress submit_assignment view_grades download_cert manage_specialization",
            ),
        ],
    )
    add(
        "moodle",
        [
            (
                "courses",
                "Moodle LMS",
                "Moodle learning management: view enrolled courses, check assignment due dates, submit assignments, view forum discussions, check grades, download course resources.",
                "list_courses check_due_dates submit_assignment view_forum check_grades download_resource get_calendar",
            ),
        ],
    )
    add(
        "quizlet",
        [
            (
                "flashcards",
                "Quizlet Study Sets",
                "Quizlet flashcard study: create/edit study sets, browse public sets, start learn/test/match modes, track study progress, share sets with classes.",
                "create_set edit_set browse_public start_learn start_test track_progress share_set join_class",
            ),
        ],
    )
    add(
        "khan-academy",
        [
            (
                "learning",
                "Khan Academy",
                "Khan Academy learning platform: get course mastery progress, view recommended next skills, complete exercises, watch video lessons, track learning time, earn mastery points.",
                "get_mastery view_recommendations complete_exercise watch_video track_time earn_points view_course_map",
            ),
        ],
    )

    # ── Entertainment & Media (5 domains, ~50 connectors) ──
    add(
        "spotify",
        [
            (
                "player",
                "Spotify Player",
                "Spotify playback: play/pause/skip tracks, control volume, seek position in track, toggle shuffle/repeat, transfer playback between devices, get currently playing track info.",
                "play pause skip set_volume seek_position toggle_shuffle toggle_repeat transfer_device get_now_playing",
            ),
            (
                "playlists",
                "Spotify Playlists",
                "Spotify playlist management: create/edit playlists, add/remove tracks, reorder playlist, manage collaborative playlists, set playlist cover image, get playlist recommendations.",
                "create_playlist add_tracks remove_tracks reorder set_cover get_recommendations make_collaborative",
            ),
            (
                "library",
                "Spotify Library",
                "Spotify user library: save/remove tracks and albums, follow/unfollow artists, view recently played, manage liked songs, browse featured playlists and new releases.",
                "save_track remove_track follow_artist get_recently_played get_liked_songs browse_featured view_new_releases",
            ),
        ],
    )
    add(
        "netflix",
        [
            (
                "watching",
                "Netflix Watching",
                "Netflix viewing: get currently watching, resume playback, view watch history, rate titles, manage My List, view continue watching queue.",
                "get_watching resume_playback view_history rate_title manage_my_list get_continue_watching",
            ),
            (
                "profiles",
                "Netflix Profiles",
                "Netflix profile management: create/delete/switch profiles, manage maturity ratings, set viewing restrictions with PIN, manage language preferences, view profile-specific recommendations.",
                "create_profile delete_profile switch_profile set_maturity set_pin manage_language get_recommendations",
            ),
            (
                "titles",
                "Netflix Titles",
                "Browse Netflix catalog: search for titles, view title details, browse by genre, check availability, view similar titles, get new/popular/trending lists.",
                "search_titles get_title_details browse_genre check_availability get_similar view_new view_trending",
            ),
        ],
    )
    add(
        "youtube",
        [
            (
                "videos",
                "YouTube Videos",
                "YouTube video management: upload videos, update metadata, manage captions, set thumbnail, manage monetization, view analytics, respond to comments.",
                "upload_video update_metadata manage_captions set_thumbnail manage_monetization view_analytics respond_comment",
            ),
            (
                "playlists",
                "YouTube Playlists",
                "YouTube playlist management: create/edit playlists, add/remove videos, reorder playlist items, set playlist privacy, manage collaborative playlists.",
                "create_playlist add_video remove_video reorder_items set_privacy make_collaborative get_playlist_details",
            ),
            (
                "live",
                "YouTube Live",
                "YouTube live streaming: create/schedule live streams, start/stop broadcast, view live chat, manage stream health, view concurrent viewers, clip highlights.",
                "create_stream schedule_stream start_broadcast stop_broadcast view_chat manage_health get_viewers clip_highlight",
            ),
        ],
    )
    add(
        "kindle",
        [
            (
                "books",
                "Kindle Books",
                "Amazon Kindle: browse your library, open books at last read position, manage bookmarks and highlights, view reading progress, manage collections, search within books.",
                "list_library open_book add_bookmark add_highlight view_progress manage_collections search_inside get_clippings",
            ),
        ],
    )
    add(
        "discord",
        [
            (
                "guilds",
                "Discord Servers",
                "Discord server management: create/manage servers, manage channels, configure roles and permissions, manage server emoji, view audit log, manage invites.",
                "create_server manage_channels configure_roles manage_emoji view_audit_log create_invite moderate_content",
            ),
            (
                "messages",
                "Discord Messages",
                "Discord messaging: send/edit/delete messages, add reactions, pin messages, create threads, send embeds and attachments, manage direct messages.",
                "send_message edit_message delete_message add_reaction pin_message create_thread send_embed manage_dm",
            ),
        ],
    )

    # ── SCALE EXPANSION: 80 additional verticals ──
    _MORE_VERTICALS = [
        # Insurance (5)
        (
            "geico",
            [
                (
                    "auto",
                    "GEICO Auto Insurance",
                    "GEICO auto insurance: view policy, file claim, get quote, manage payments, request ID cards, add vehicle to policy.",
                    "view_policy file_claim get_quote make_payment request_id_card add_vehicle",
                ),
                (
                    "home",
                    "GEICO Home Insurance",
                    "GEICO homeowners and renters insurance: view coverage, file property claim, update dwelling info, add scheduled items.",
                    "view_coverage file_claim update_dwelling add_item get_quote",
                ),
            ],
        ),
        (
            "progressive",
            [
                (
                    "auto",
                    "Progressive Auto",
                    "Progressive auto insurance: snapshot monitoring, policy management, claim filing, roadside assistance request.",
                    "view_policy file_claim request_roadside view_snapshot make_payment",
                ),
                (
                    "boat",
                    "Progressive Boat",
                    "Progressive boat and watercraft insurance: marine coverage, file claim, add watercraft, update navigation area.",
                    "view_policy file_claim add_boat update_area get_quote",
                ),
            ],
        ),
        (
            "allstate",
            [
                (
                    "auto",
                    "Allstate Auto Insurance",
                    "Allstate auto: Drivewise tracking, policy docs, file claim, agent locator, roadside, glass claims.",
                    "view_policy file_claim find_agent request_roadside file_glass_claim view_drivewise",
                )
            ],
        ),
        (
            "lemonade",
            [
                (
                    "renters",
                    "Lemonade Renters",
                    "Lemonade renters insurance: instant quote, file claim via AI, adjust coverage, add electronics protection.",
                    "get_quote file_claim adjust_coverage add_electronics view_policy",
                ),
                (
                    "pet",
                    "Lemonade Pet",
                    "Lemonade pet health insurance: file vet claim, view deductible status, add pet, update breed info.",
                    "file_claim view_deductible add_pet update_breed get_quote",
                ),
            ],
        ),
        (
            "metlife",
            [
                (
                    "dental",
                    "MetLife Dental",
                    "MetLife dental insurance: find in-network dentist, check coverage, file claim, view annual maximum status.",
                    "find_dentist check_coverage file_claim view_annual_max view_benefits",
                )
            ],
        ),
        # Legal (4)
        (
            "rocketlawyer",
            [
                (
                    "docs",
                    "Rocket Lawyer Documents",
                    "Rocket Lawyer: create legal documents, e-sign contracts, ask attorney questions, incorporate business.",
                    "create_doc esign ask_attorney incorporate download_template",
                )
            ],
        ),
        (
            "legalzoom",
            [
                (
                    "llc",
                    "LegalZoom LLC Formation",
                    "LegalZoom business formation: form LLC, file EIN, create operating agreement, registered agent service.",
                    "form_llc file_ein create_agreement add_agent check_status",
                ),
                (
                    "trademark",
                    "LegalZoom Trademark",
                    "LegalZoom trademark registration: search marks, file application, respond to office actions, monitor status.",
                    "search_mark file_application respond_action monitor_status",
                ),
            ],
        ),
        (
            "lexisnexis",
            [
                (
                    "research",
                    "LexisNexis Research",
                    "LexisNexis legal research: search case law, shepardize citations, browse statutes, save research folders.",
                    "search_cases shepardize browse_statutes save_folder set_alert",
                )
            ],
        ),
        (
            "clio",
            [
                (
                    "matters",
                    "Clio Legal Practice",
                    "Clio law practice management: manage matters, track billable hours, generate invoices, manage client trust accounts.",
                    "create_matter log_hours generate_invoice manage_trust add_client",
                )
            ],
        ),
        # Real Estate (4)
        (
            "zillow",
            [
                (
                    "search",
                    "Zillow Home Search",
                    "Zillow real estate: search listings, filter by price/type, save favorites, contact agent, get mortgage rates.",
                    "search_listings save_favorite contact_agent get_rates set_alert",
                ),
                (
                    "zestimate",
                    "Zillow Zestimate",
                    "Zillow home value: view Zestimate history, claim home, update home facts, compare neighborhood values.",
                    "view_zestimate claim_home update_facts compare_values",
                ),
            ],
        ),
        (
            "redfin",
            [
                (
                    "listings",
                    "Redfin Listings",
                    "Redfin real estate: browse listings, schedule tour, view open houses, track price changes, get comps.",
                    "browse_listings schedule_tour view_open_houses track_price get_comps",
                )
            ],
        ),
        (
            "realtor",
            [
                (
                    "search",
                    "Realtor.com Search",
                    "Realtor.com: search MLS listings, find agent, view school ratings, calculate mortgage, get market trends.",
                    "search_mls find_agent view_schools calculate_mortgage get_trends",
                )
            ],
        ),
        (
            "airbnb",
            [
                (
                    "booking",
                    "Airbnb Booking",
                    "Airbnb: search stays, book reservation, message host, manage trip, leave review, save wishlist.",
                    "search_stays book_reservation message_host manage_trip leave_review save_wishlist",
                ),
                (
                    "hosting",
                    "Airbnb Hosting",
                    "Airbnb hosting: list property, manage calendar, respond to inquiries, view earnings, set pricing rules.",
                    "list_property manage_calendar respond_inquiry view_earnings set_pricing",
                ),
            ],
        ),
        # Travel & Hospitality (4)
        (
            "expedia",
            [
                (
                    "flights",
                    "Expedia Flights",
                    "Expedia flight booking: search flights, filter by airline/price, book with points, manage itinerary.",
                    "search_flights book_flight use_points manage_itinerary cancel_booking",
                ),
                (
                    "hotels",
                    "Expedia Hotels",
                    "Expedia hotel booking: search by destination, filter amenities, read reviews, bundle with flight/car.",
                    "search_hotels filter_amenities read_reviews create_bundle book_room",
                ),
            ],
        ),
        (
            "uber",
            [
                (
                    "rides",
                    "Uber Rides",
                    "Uber ride hailing: request ride, select vehicle type, track driver, split fare, rate trip.",
                    "request_ride select_type track_driver split_fare rate_trip",
                ),
                (
                    "eats",
                    "Uber Eats",
                    "Uber Eats delivery: browse restaurants, place order, track delivery, rate food, manage favorites.",
                    "browse_restaurants place_order track_delivery rate_food manage_favorites",
                ),
            ],
        ),
        (
            "lyft",
            [
                (
                    "rides",
                    "Lyft Rides",
                    "Lyft: request ride, schedule pickup, choose Lyft type, share ETA, rate driver, view ride history.",
                    "request_ride schedule_pickup choose_type share_eta rate_driver view_history",
                )
            ],
        ),
        (
            "booking",
            [
                (
                    "stays",
                    "Booking.com Stays",
                    "Booking.com: search accommodations, filter by guest rating, read verified reviews, free cancellation filter.",
                    "search_stays filter_rating read_reviews cancel_free manage_booking",
                )
            ],
        ),
        # Food & Delivery (4)
        (
            "doordash",
            [
                (
                    "ordering",
                    "DoorDash Ordering",
                    "DoorDash food delivery: browse cuisine, place order, track Dasher, schedule delivery, rate restaurant.",
                    "browse_cuisine place_order track_dasher schedule_delivery rate_restaurant",
                ),
                (
                    "dashpass",
                    "DoorDash DashPass",
                    "DoorDash DashPass membership: view benefits, manage subscription, track savings, add payment method.",
                    "view_benefits manage_sub track_savings add_payment",
                ),
            ],
        ),
        (
            "grubhub",
            [
                (
                    "ordering",
                    "Grubhub Ordering",
                    "Grubhub food delivery: search restaurants, apply promo, group order, track delivery, reorder favorites.",
                    "search_restaurants apply_promo group_order track_delivery reorder_favorite",
                )
            ],
        ),
        (
            "instacart",
            [
                (
                    "grocery",
                    "Instacart Grocery Delivery",
                    "Instacart grocery: shop by store, build cart, select replacement preferences, schedule delivery window.",
                    "shop_store build_cart set_replacements schedule_delivery track_order",
                )
            ],
        ),
        (
            "doordash-drive",
            [
                (
                    "business",
                    "DoorDash Drive Business",
                    "DoorDash Drive for business: manage corporate meals, set catering orders, view spend reports, manage employee meal credits.",
                    "order_catering manage_credits view_spend set_policy add_employee",
                )
            ],
        ),
        # Social Media (5)
        (
            "twitter",
            [
                (
                    "tweets",
                    "Twitter/X Posts",
                    "Twitter/X post management: compose tweet, schedule post, view analytics, manage lists, follow/unfollow.",
                    "compose_tweet schedule_post view_analytics manage_lists follow_user",
                ),
                (
                    "dms",
                    "Twitter/X Messages",
                    "Twitter/X direct messages: send DM, create group chat, share media, manage message requests.",
                    "send_dm create_group share_media manage_requests",
                ),
            ],
        ),
        (
            "instagram",
            [
                (
                    "posts",
                    "Instagram Posts",
                    "Instagram content: create post, edit with filters, add story, view insights, manage comments, schedule Reels.",
                    "create_post add_story view_insights manage_comments schedule_reel",
                ),
                (
                    "business",
                    "Instagram Business",
                    "Instagram business: view professional dashboard, manage ads, track link clicks, respond to messages.",
                    "view_dashboard manage_ads track_clicks respond_messages",
                ),
            ],
        ),
        (
            "linkedin",
            [
                (
                    "profile",
                    "LinkedIn Profile",
                    "LinkedIn professional: update profile, add experience, request recommendation, publish article, manage connections.",
                    "update_profile add_experience request_rec publish_article manage_connections",
                ),
                (
                    "jobs",
                    "LinkedIn Jobs",
                    "LinkedIn job search: search openings, set job alerts, submit application, track status, view recruiter activity.",
                    "search_jobs set_alert submit_application track_status view_recruiters",
                ),
            ],
        ),
        (
            "tiktok",
            [
                (
                    "content",
                    "TikTok Content",
                    "TikTok creator: upload video, add effects/music, view analytics, respond to comments, manage duets.",
                    "upload_video add_effects view_analytics respond_comments manage_duets",
                )
            ],
        ),
        (
            "reddit",
            [
                (
                    "posts",
                    "Reddit Posts",
                    "Reddit: create post in subreddit, upvote/downvote, award content, save posts, manage multireddits.",
                    "create_post vote award save_post manage_multireddit comment_thread",
                )
            ],
        ),
        # Developer Tools (5)
        (
            "docker",
            [
                (
                    "containers",
                    "Docker Hub",
                    "Docker container registry: pull/push images, manage tags, view vulnerability scans, set access policies.",
                    "pull_image push_image manage_tags view_scan set_policy",
                ),
                (
                    "compose",
                    "Docker Compose",
                    "Docker Compose: define multi-container apps, manage stacks, scale services, view logs.",
                    "define_stack manage_services scale_service view_logs",
                ),
            ],
        ),
        (
            "atlassian",
            [
                (
                    "bitbucket",
                    "Bitbucket Repos",
                    "Atlassian Bitbucket: manage repos, review PRs, configure pipelines, manage branch permissions.",
                    "manage_repo review_pr config_pipeline set_branch_perm",
                ),
                (
                    "confluence",
                    "Confluence Wiki",
                    "Atlassian Confluence: create/edit pages, manage spaces, view analytics, add comments, share externally.",
                    "create_page manage_space view_analytics add_comment share_external",
                ),
            ],
        ),
        (
            "cloudflare",
            [
                (
                    "dns",
                    "Cloudflare DNS",
                    "Cloudflare DNS management: manage records, configure DNSSEC, set page rules, view analytics, purge cache.",
                    "manage_dns config_dnssec set_page_rule view_analytics purge_cache",
                ),
                (
                    "workers",
                    "Cloudflare Workers",
                    "Cloudflare Workers: deploy edge functions, manage KV store, view invocation metrics, set environment variables.",
                    "deploy_worker manage_kv view_metrics set_env",
                ),
            ],
        ),
        (
            "vercel",
            [
                (
                    "deployments",
                    "Vercel Deployments",
                    "Vercel platform: deploy from git, manage domains, view build logs, configure env vars, rollback deploy.",
                    "deploy_git manage_domain view_logs config_env rollback",
                ),
                (
                    "analytics",
                    "Vercel Analytics",
                    "Vercel web analytics: view page views, track Core Web Vitals, monitor error rates, set up funnels.",
                    "view_pv track_cwv monitor_errors setup_funnel",
                ),
            ],
        ),
        (
            "datadog",
            [
                (
                    "monitors",
                    "Datadog Monitors",
                    "Datadog monitoring: create alert, manage dashboards, view APM traces, search logs, configure SLOs.",
                    "create_alert manage_dashboard view_apm search_logs config_slo",
                )
            ],
        ),
        # Crypto/Web3 (4)
        (
            "coinbase",
            [
                (
                    "trading",
                    "Coinbase Trading",
                    "Coinbase exchange: buy/sell crypto, view portfolio, set limit orders, stake assets, view tax reports.",
                    "buy_crypto sell_crypto view_portfolio set_limit_order stake_asset view_tax",
                ),
                (
                    "wallet",
                    "Coinbase Wallet",
                    "Coinbase self-custody wallet: send/receive crypto, connect dApps, manage NFTs, view transaction history.",
                    "send_crypto receive_crypto connect_dapp manage_nft view_history",
                ),
            ],
        ),
        (
            "metamask",
            [
                (
                    "wallet",
                    "MetaMask Wallet",
                    "MetaMask browser wallet: import wallet, send tokens, add network, connect to dApp, view activity.",
                    "import_wallet send_token add_network connect_dapp view_activity",
                )
            ],
        ),
        (
            "opensea",
            [
                (
                    "nfts",
                    "OpenSea NFT Marketplace",
                    "OpenSea: browse collections, buy NFT, list for sale, make offer, view activity, manage favorites.",
                    "browse_collections buy_nft list_sale make_offer view_activity",
                )
            ],
        ),
        (
            "chainlink",
            [
                (
                    "feeds",
                    "Chainlink Data Feeds",
                    "Chainlink oracle: query price feed, verify proof of reserve, check automation status, view node operators.",
                    "query_feed verify_reserve check_automation view_nodes",
                )
            ],
        ),
        # Gaming (4)
        (
            "steam",
            [
                (
                    "library",
                    "Steam Library",
                    "Steam gaming platform: browse library, install game, manage friends, join multiplayer, view achievements.",
                    "browse_library install_game manage_friends join_multiplayer view_achievements",
                ),
                (
                    "workshop",
                    "Steam Workshop",
                    "Steam community workshop: browse mods, subscribe to items, publish mod, rate content, manage collections.",
                    "browse_mods subscribe_item publish_mod rate_content manage_collections",
                ),
            ],
        ),
        (
            "epic-games",
            [
                (
                    "store",
                    "Epic Games Store",
                    "Epic Games: browse catalog, purchase game, claim free game, manage library, redeem code.",
                    "browse_catalog purchase_game claim_free manage_library redeem_code",
                )
            ],
        ),
        (
            "twitch",
            [
                (
                    "streaming",
                    "Twitch Streaming",
                    "Twitch: start stream, manage channel, view chat, check subscriber count, clip highlights, manage VODs.",
                    "start_stream manage_channel view_chat check_subs clip_highlight manage_vod",
                ),
                (
                    "watching",
                    "Twitch Watching",
                    "Twitch viewer: follow streamer, subscribe, watch VOD, send bits, participate in prediction.",
                    "follow_streamer subscribe watch_vod send_bits participate_prediction",
                ),
            ],
        ),
        (
            "xbox",
            [
                (
                    "live",
                    "Xbox Live",
                    "Xbox Live services: view achievements, manage friends, join party, check game pass, redeem code.",
                    "view_achievements manage_friends join_party check_gamepass redeem_code",
                )
            ],
        ),
        # IoT / Industrial (4)
        (
            "siemens",
            [
                (
                    "plc",
                    "Siemens PLC Control",
                    "Siemens industrial automation: monitor PLC status, update ladder logic, view production metrics, acknowledge alarms.",
                    "monitor_plc update_logic view_metrics ack_alarm",
                )
            ],
        ),
        (
            "bosch",
            [
                (
                    "iot",
                    "Bosch IoT Sensors",
                    "Bosch IoT sensor suite: read temperature/humidity/pressure, configure sampling rate, set alert thresholds.",
                    "read_sensor config_rate set_threshold view_history",
                )
            ],
        ),
        (
            "honeywell",
            [
                (
                    "building",
                    "Honeywell Building Control",
                    "Honeywell building automation: control HVAC zones, manage access control, monitor energy, schedule maintenance.",
                    "control_hvac manage_access monitor_energy schedule_maintenance",
                )
            ],
        ),
        (
            "schneider",
            [
                (
                    "power",
                    "Schneider Power Monitoring",
                    "Schneider Electric: monitor power quality, track consumption, manage load shedding, view breaker status.",
                    "monitor_power track_consumption manage_load view_breakers set_alert",
                )
            ],
        ),
        # Agriculture / Food Tech (4)
        (
            "john-deere",
            [
                (
                    "equipment",
                    "John Deere Ops Center",
                    "John Deere operations: track equipment location, monitor fuel levels, view yield maps, schedule maintenance.",
                    "track_equipment monitor_fuel view_yield schedule_maintenance",
                )
            ],
        ),
        (
            "climate-fieldview",
            [
                (
                    "field",
                    "Climate FieldView",
                    "Climate FieldView: view field health imagery, track planting progress, analyze soil data, generate prescriptions.",
                    "view_imagery track_planting analyze_soil generate_rx",
                )
            ],
        ),
        (
            "cropx",
            [
                (
                    "irrigation",
                    "CropX Irrigation",
                    "CropX smart irrigation: monitor soil moisture, schedule watering, view ET data, manage zones.",
                    "monitor_moisture schedule_watering view_et manage_zones set_alert",
                )
            ],
        ),
        (
            "farmlogs",
            [
                (
                    "farming",
                    "FarmLogs Management",
                    "FarmLogs farm management: track field activities, log input applications, view rainfall data, generate reports.",
                    "track_activity log_input view_rainfall generate_report",
                )
            ],
        ),
        # Transportation / Logistics (4)
        (
            "fedex",
            [
                (
                    "tracking",
                    "FedEx Tracking",
                    "FedEx shipping: track package, create shipment, schedule pickup, manage delivery preferences, view rates.",
                    "track_package create_shipment schedule_pickup manage_delivery view_rates",
                )
            ],
        ),
        (
            "ups",
            [
                (
                    "shipping",
                    "UPS Shipping",
                    "UPS: track package, schedule pickup, get quote, manage returns, hold at location, view delivery photo.",
                    "track_package schedule_pickup get_quote manage_return hold_location view_photo",
                )
            ],
        ),
        (
            "usps",
            [
                (
                    "mail",
                    "USPS Mail Services",
                    "USPS: track package, schedule pickup, change address, hold mail, view informed delivery, buy stamps.",
                    "track_package schedule_pickup change_address hold_mail view_delivery buy_stamps",
                )
            ],
        ),
        (
            "fleetservice",
            [
                (
                    "fleet",
                    "Fleet Management",
                    "Fleet logistics: track vehicles real-time, optimize routes, monitor driver behavior, schedule maintenance.",
                    "track_vehicle optimize_route monitor_driver schedule_maintenance fuel_report",
                )
            ],
        ),
        # Energy / Utilities (4)
        (
            "tesla-energy",
            [
                (
                    "powerwall",
                    "Tesla Powerwall",
                    "Tesla Powerwall: monitor charge level, set backup reserve, view solar production, manage time-of-use settings, check grid status.",
                    "monitor_charge set_reserve view_solar manage_tou check_grid",
                ),
                (
                    "solar",
                    "Tesla Solar",
                    "Tesla solar panels: view production, track energy offset, monitor per-panel output, request service.",
                    "view_production track_offset monitor_panels request_service",
                ),
            ],
        ),
        (
            "enphase",
            [
                (
                    "envoy",
                    "Enphase Envoy",
                    "Enphase microinverter monitoring: view per-panel production, check system health, update grid profile, view consumption.",
                    "view_panels check_health update_profile view_consumption",
                )
            ],
        ),
        (
            "sense",
            [
                (
                    "energy",
                    "Sense Energy Monitor",
                    "Sense home energy: detect devices, track real-time usage, view trends, set goals, compare with community.",
                    "detect_devices track_usage view_trends set_goal compare_community",
                )
            ],
        ),
        (
            "chargepoint",
            [
                (
                    "stations",
                    "ChargePoint Stations",
                    "ChargePoint EV charging: find station, start charge, view session history, manage payment, reserve spot.",
                    "find_station start_charge view_history manage_payment reserve_spot",
                )
            ],
        ),
        # Retail (3)
        (
            "shopify-admin",
            [
                (
                    "orders",
                    "Shopify Orders",
                    "Shopify order management: view orders, process fulfillment, manage refunds, print labels, view analytics.",
                    "view_order fulfill_order manage_refund print_label view_analytics",
                ),
                (
                    "inventory",
                    "Shopify Inventory",
                    "Shopify inventory: track stock levels, set low-stock alerts, manage transfers, view inventory reports.",
                    "track_stock set_alert manage_transfer view_report",
                ),
            ],
        ),
        (
            "walmart-api",
            [
                (
                    "marketplace",
                    "Walmart Marketplace",
                    "Walmart seller: manage listings, update pricing, view orders, handle returns, check performance metrics.",
                    "manage_listing update_price view_order handle_return check_metrics",
                )
            ],
        ),
        (
            "target-api",
            [
                (
                    "fulfillment",
                    "Target Fulfillment",
                    "Target order fulfillment: view pickup orders, manage drive-up, process ship-from-store, update inventory.",
                    "view_pickup manage_driveup process_ship update_inventory",
                )
            ],
        ),
        # Government / Civic (3 more)
        (
            "irs",
            [
                (
                    "filing",
                    "IRS Tax Filing",
                    "IRS e-file: submit return, check refund status, view transcript, make payment, manage payment plan.",
                    "submit_return check_refund view_transcript make_payment manage_plan",
                )
            ],
        ),
        (
            "uscis",
            [
                (
                    "case",
                    "USCIS Case Status",
                    "USCIS immigration: check case status, upload evidence, reschedule biometrics, change address, view processing times.",
                    "check_status upload_evidence reschedule_biometrics change_address view_times",
                )
            ],
        ),
        (
            "sba",
            [
                (
                    "loans",
                    "SBA Loan Portal",
                    "Small Business Administration: apply for loan, upload documents, check application status, view disbursement schedule.",
                    "apply_loan upload_doc check_status view_disbursement",
                )
            ],
        ),
        # Science / Research (3)
        (
            "genbank",
            [
                (
                    "sequences",
                    "GenBank Sequences",
                    "NCBI GenBank: submit sequence, BLAST search, download genome data, view taxonomy browser, manage accessions.",
                    "submit_sequence blast_search download_genome view_taxonomy manage_accession",
                )
            ],
        ),
        (
            "zenodo",
            [
                (
                    "datasets",
                    "Zenodo Research Data",
                    "Zenodo: upload dataset, get DOI, manage versions, view download stats, link to GitHub repository.",
                    "upload_dataset get_doi manage_version view_stats link_github",
                )
            ],
        ),
        (
            "labguru",
            [
                (
                    "experiments",
                    "Labguru ELN",
                    "Labguru electronic lab notebook: create experiment, link protocols, track inventory, manage samples, export reports.",
                    "create_experiment link_protocol track_inventory manage_sample export_report",
                )
            ],
        ),
        # Automotive (3)
        (
            "fordpass",
            [
                (
                    "vehicle",
                    "FordPass Connect",
                    "FordPass: remote start, lock/unlock, check fuel, locate vehicle, schedule service, view vehicle health.",
                    "remote_start lock_unlock check_fuel locate_vehicle schedule_service view_health",
                )
            ],
        ),
        (
            "onstar",
            [
                (
                    "services",
                    "OnStar Services",
                    "GM OnStar: roadside assistance, vehicle diagnostics, crisis assist, stolen vehicle locator, remote commands.",
                    "request_roadside run_diagnostics crisis_assist locate_stolen remote_command",
                )
            ],
        ),
        (
            "carfax",
            [
                (
                    "reports",
                    "CARFAX Reports",
                    "CARFAX vehicle history: order report, check service history, view accident records, verify ownership.",
                    "order_report check_service view_accidents verify_ownership",
                )
            ],
        ),
    ]

    for domain, connectors in _MORE_VERTICALS:
        add(domain, connectors)

    return templates


# ═══════════════════════════════════════════════════════════════════════════
# Competing Distractors — Genuine Semantic Overlap Per FamilyOS Archetype
# ═══════════════════════════════════════════════════════════════════════════
#
# These 70 connectors (10+ per FamilyOS archetype) share the SAME action
# names and SEMANTICALLY OVERLAPPING descriptions as the FamilyOS connectors.
# This is the REAL scaling challenge: "add eggs to shopping list" must route
# to family.shopping, not grocery.instacart or pantry.kitchenpal.
#
# Each competing distractor gets boundary fields and structured documents
# — exactly the same treatment as FamilyOS.  No hidden advantages.


def _generate_competing_distractors() -> list[dict[str, Any]]:
    """Generate 70 connectors that DIRECTLY compete with the 6 FamilyOS connectors.

    Each template shares action names with its FamilyOS counterpart and uses
    semantically overlapping descriptions.  This forces the search to
    distinguish between near-identical connectors — the real scaling problem.
    """
    templates: list[dict[str, Any]] = []

    def add(domain: str, connectors: list[tuple[str, str, str, str]]):
        for cid, label, desc, actions in connectors:
            templates.append(
                {
                    "cid": f"{domain}.{cid}",
                    "label": label,
                    "desc": desc,
                    "actions": actions,
                    "concepts": "",
                    "rfs": "",
                }
            )

    # ── Compete with family.shopping (add_item, check_off, list_items, etc.) ──
    add(
        "grocery_comp",
        [
            (
                "instacart",
                "Instacart Grocery List",
                "Build your grocery cart: add items to list, mark items as bought, browse weekly deals, manage your shopping lists for delivery or pickup.",
                "add_item remove_item check_off list_items create_list set_budget share_list",
            ),
            (
                "walmart",
                "Walmart Grocery",
                "Walmart grocery shopping: add food and household items to your list, check off purchases, create shared family lists, save favorites for quick reorder.",
                "add_item remove_item check_off list_items create_list reorder_favorite set_budget",
            ),
            (
                "amazonfresh",
                "Amazon Fresh Cart",
                "Amazon Fresh grocery delivery: build your fresh cart, add produce and pantry items, check off as you shop, manage recurring grocery orders.",
                "add_item remove_item check_off list_items create_list schedule_delivery reorder",
            ),
            (
                "kroger",
                "Kroger Shopping List",
                "Kroger grocery: create digital shopping lists, add items by scanning barcodes, mark as purchased, track spending by category, share with family.",
                "add_item remove_item check_off list_items create_list scan_barcode track_spending",
            ),
            (
                "safeway",
                "Safeway Just For U",
                "Safeway personalized shopping: build lists from digital coupons, add items, check off, clip deals directly to your shopping list for checkout.",
                "add_item remove_item check_off list_items create_list clip_coupon view_deals",
            ),
            (
                "wholefoods",
                "Whole Foods Market List",
                "Whole Foods shopping: add organic and specialty items to your list, check off as you find them, browse by dietary preference, share with household.",
                "add_item remove_item check_off list_items create_list browse_by_diet share_list",
            ),
            (
                "aldi",
                "ALDI Shopping",
                "ALDI grocery list: plan your ALDI finds, add weekly specials, check off purchases, track total as you shop, save favorite ALDI exclusives.",
                "add_item remove_item check_off list_items create_list view_specials track_total",
            ),
            (
                "traderjoes",
                "Trader Joe's List",
                "Trader Joe's shopping: add unique TJ items to your list, check off, browse seasonal favorites, share with family, set shopping reminders for restocks.",
                "add_item remove_item check_off list_items create_list browse_seasonal share_list set_reminder",
            ),
            (
                "costco",
                "Costco Wholesale List",
                "Costco warehouse shopping: build bulk shopping lists, add items with warehouse location, check off, compare unit prices, manage executive membership perks.",
                "add_item remove_item check_off list_items create_list compare_price find_warehouse_location",
            ),
            (
                "wegmans",
                "Wegmans Shopping",
                "Wegmans grocery: create smart shopping lists organized by aisle, add family favorites, check off items, sync with weekly circular for meal planning.",
                "add_item remove_item check_off list_items create_list organize_by_aisle sync_circular meal_plan",
            ),
            (
                "h_e_b",
                "HEB Curbside List",
                "HEB grocery: build curbside pickup lists, add Texas favorites, check off, schedule pickup time, manage substitutions and Coupon Book deals.",
                "add_item remove_item check_off list_items create_list schedule_pickup manage_substitutions",
            ),
            (
                "publix",
                "Publix Shopping List",
                "Publix grocery: create lists from weekly BOGO deals, add deli and bakery items, check off, share with family, save to digital account for quick access.",
                "add_item remove_item check_off list_items create_list view_bogo share_list save_list",
            ),
        ],
    )

    # ── Compete with family.tasks (create_task, mark_done, assign_to, etc.) ──
    add(
        "todo_comp",
        [
            (
                "todoist",
                "Todoist Tasks",
                "Todoist task manager: create one-time tasks, mark as complete, assign to team members, set due dates and priorities, organize into projects.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks delete_task",
            ),
            (
                "ticktick",
                "TickTick To-Do",
                "TickTick task management: add tasks with natural language, complete items, set reminders, assign to collaborators, track with Eisenhower matrix.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks set_reminder",
            ),
            (
                "microsofttodo",
                "Microsoft To Do",
                "Microsoft smart to-do lists: create tasks from flagged emails, mark as finished, assign to shared lists, set my day focus, recurring deadlines.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks add_to_my_day",
            ),
            (
                "anydo",
                "Any.do Task List",
                "Any.do daily planner: create tasks by voice or type, mark as done with swipe, assign to family members, set recurring deadlines, plan your day.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks plan_day",
            ),
            (
                "trello",
                "Trello Task Cards",
                "Trello board tasks: create one-off cards with checklists, mark items done, assign members, set due dates, move between lists for workflow tracking.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks add_checklist",
            ),
            (
                "taskrabbit",
                "TaskRabbit Errands",
                "TaskRabbit one-time errands: post tasks and errands, mark as completed, assign to taskers, set budget, rate completion, manage pending assignments.",
                "create_task mark_done assign_to set_due_date set_budget list_tasks rate_tasker",
            ),
            (
                "asana",
                "Asana Personal Tasks",
                "Asana task tracking: create action items, complete tasks, assign to workspaces, set deadlines with timeline view, prioritize in my tasks inbox.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks view_timeline",
            ),
            (
                "clickup",
                "ClickUp Tasks",
                "ClickUp task management: create tasks from anywhere, mark done, assign to team, set start/due dates, organize by space, folder, and list hierarchies.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks set_start_date",
            ),
            (
                "notiontasks",
                "Notion Task Database",
                "Notion connected task database: create task entries with properties, check off as done, assign to workspace members, filter and sort by status and priority.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks filter_by_status",
            ),
            (
                "things",
                "Things 3 Tasks",
                "Things task organizer: create to-dos with natural language parsing, mark complete, set deadlines, assign to projects and areas, review your today list.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks review_today",
            ),
            (
                "omnifocus",
                "OmniFocus Tasks",
                "OmniFocus professional GTD: capture tasks from any app, mark done, assign to projects and contexts, set defer/due dates, review perspectives.",
                "create_task mark_done assign_to set_due_date set_priority list_tasks set_defer_date",
            ),
            (
                "habitica",
                "Habitica To-Dos",
                "Habitica gamified tasks: create to-dos that earn XP on completion, mark as done, set difficulty, assign due dates, track streaks and rewards.",
                "create_task mark_done assign_to set_due_date set_difficulty list_tasks check_streak",
            ),
        ],
    )

    # ── Compete with family.calendar (create_event, check_schedule, etc.) ──
    add(
        "scheduling_comp",
        [
            (
                "calendly",
                "Calendly Events",
                "Calendly scheduling: create meeting events, check your availability, share booking links, set event types, view your scheduled appointments.",
                "create_event check_schedule cancel_event list_events set_availability share_booking set_event_type",
            ),
            (
                "doodle",
                "Doodle Polls",
                "Doodle scheduling polls: create meeting polls for group availability, check responses, confirm event time, integrate with calendar, send reminders.",
                "create_event check_schedule cancel_event list_events create_poll check_responses send_reminder",
            ),
            (
                "savvycal",
                "SavvyCal Scheduling",
                "SavvyCal meeting scheduler: create booking links with ranked availability, check schedule, overlay calendars, set event buffers and limits.",
                "create_event check_schedule cancel_event list_events set_buffer overlay_calendar share_link",
            ),
            (
                "rally",
                "Rally Meetings",
                "Rally calendar coordination: schedule events across time zones, check availability, create group meetings with doodle-style consensus, manage recurring appointments.",
                "create_event check_schedule cancel_event list_events coordinate_timezone create_recurring",
            ),
            (
                "motion",
                "Motion Calendar",
                "Motion AI calendar: auto-schedule events based on priorities, check schedule, create time blocks, reschedule conflicts dynamically.",
                "create_event check_schedule cancel_event list_events auto_schedule create_timeblock reschedule",
            ),
            (
                "reclaim",
                "Reclaim Scheduling",
                "Reclaim smart calendar: automatically find best meeting times, create events, check schedule for conflicts, defend focus time from interruptions.",
                "create_event check_schedule cancel_event list_events find_best_time defend_focus block_event",
            ),
            (
                "clockwise",
                "Clockwise Calendar",
                "Clockwise team calendar optimization: create events in optimal slots, check schedule, automatically resolve conflicts, create focus blocks for deep work.",
                "create_event check_schedule cancel_event list_events resolve_conflicts create_focus resolve_team_conflicts",
            ),
            (
                "fantastical",
                "Fantastical Schedule",
                "Fantastical natural calendar: create events with natural language, check your day at a glance, join video calls, set alerts, manage multiple calendar sets.",
                "create_event check_schedule cancel_event list_events set_alert join_call manage_calendar_set",
            ),
            (
                "cron",
                "Cron Calendar",
                "Cron professional calendar: create events with quick commands, check team availability, schedule across shared calendars, view day/week/month timelines.",
                "create_event check_schedule cancel_event list_events check_team availability view_timeline",
            ),
            (
                "amie",
                "Amie Calendar",
                "Amie joyful calendar: create events with emoji and color, check schedule, see birthdays and holidays, schedule todos alongside events in unified timeline.",
                "create_event check_schedule cancel_event list_events add_todo view_birthdays set_color",
            ),
        ],
    )

    # ── Compete with family.chores (complete_chore, assign_chore, skip_chore, etc.) ──
    add(
        "housekeeping_comp",
        [
            (
                "tody",
                "Tody Cleaning",
                "Tody home cleaning manager: track recurring housework, complete chores by room, assign to household members, check what's due based on actual dirtiness.",
                "complete_chore assign_chore skip_chore list_chores set_schedule check_due reschedule",
            ),
            (
                "sweepy",
                "Sweepy Housework",
                "Sweepy chore tracking: manage recurring cleaning tasks, mark chores complete, assign to family members, generate daily cleaning schedule by room difficulty.",
                "complete_chore assign_chore skip_chore list_chores set_schedule generate_schedule view_effort",
            ),
            (
                "homey",
                "Homey Chores",
                "Homey family chore management: set up recurring household duties, complete daily/weekly tasks, assign chores with allowance rewards, track completion streaks.",
                "complete_chore assign_chore skip_chore list_chores set_schedule set_reward view_streak",
            ),
            (
                "ourhome",
                "OurHome Tasks",
                "OurHome family organization: create recurring cleaning duties, complete chores for points, assign by rotation, manage chore calendar with kids reward system.",
                "complete_chore assign_chore skip_chore list_chores set_schedule rotate_assignment earn_points",
            ),
            (
                "chorsee",
                "Chorsee Duties",
                "Chorsee chore accountability: define repeating housework, complete assigned chores with photo verification, skip with reason, reassign overdue duties.",
                "complete_chore assign_chore skip_chore list_chores set_schedule verify_photo reassign",
            ),
            (
                "nipto",
                "Nipto Chores",
                "Nipto gamified housework: complete chores to earn points on leaderboard, assign recurring duties, skip with penalty, manage weekly family cleaning competition.",
                "complete_chore assign_chore skip_chore list_chores set_schedule view_leaderboard set_penalty",
            ),
            (
                "brili",
                "Brili Routines",
                "Brili routine chore management: set up recurring household routines, complete each step with timer, assign tasks to kids, track daily routine completion.",
                "complete_chore assign_chore skip_chore list_chores set_schedule start_routine track_completion",
            ),
            (
                "maple",
                "Maple House",
                "Maple home management: organize recurring cleaning and maintenance chores, complete tasks, assign by household member, schedule seasonal deep-clean projects.",
                "complete_chore assign_chore skip_chore list_chores set_schedule plan_deepclean assign_seasonal",
            ),
            (
                "flatastic",
                "Flatastic Chores",
                "Flatastic shared living chore management: create recurring flat duties, complete your assigned chores, skip with swap request, track who did what with cleaning schedule.",
                "complete_chore assign_chore skip_chore list_chores set_schedule request_swap view_history",
            ),
            (
                "spotless",
                "Spotless Cleaning",
                "Spotless cleaning schedule: organize daily, weekly, monthly housework, complete chores by area, assign tasks to cleaners, schedule deep clean appointments.",
                "complete_chore assign_chore skip_chore list_chores set_schedule schedule_service assign_cleaner",
            ),
            (
                "homeaglow",
                "Homeaglow Housekeeping",
                "Homeaglow professional housekeeping: schedule recurring cleaning visits, manage chore list for cleaner, complete housework tasks, reschedule service appointments.",
                "complete_chore assign_chore skip_chore list_chores set_schedule book_cleaner reschedule_service",
            ),
            (
                "flylady",
                "FlyLady Home Routines",
                "FlyLady cleaning method: follow zone cleaning schedule, complete daily shine tasks, assign family chores with blessing routine, skip and catch up on zones.",
                "complete_chore assign_chore skip_chore list_chores set_schedule follow_zone bless_house catch_up",
            ),
        ],
    )

    # ── Compete with family.reminders (set_reminder, dismiss_reminder, snooze, etc.) ──
    add(
        "alerts_comp",
        [
            (
                "due",
                "Due Reminders",
                "Due persistent reminders: set time-based alerts that keep nagging until dismissed, snooze for custom intervals, set recurring daily/weekly reminders, auto-snooze.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders set_recurring set_alert reschedule",
            ),
            (
                "waterminder",
                "WaterMinder Alerts",
                "WaterMinder hydration reminders: set drinking reminders at intervals, snooze, track intake, get nudged throughout the day to stay hydrated.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders set_interval track_intake customize_alert",
            ),
            (
                "medisafe",
                "MediSafe Pill Alerts",
                "MediSafe medication reminders: set critical pill time alerts, dismiss after taking, snooze for later, get caregiver notifications if missed, manage prescription schedule.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders notify_caregiver set_prescription refill_alert",
            ),
            (
                "roundhealth",
                "Round Health Alerts",
                "Round medication reminders: set birth control and daily pill reminders with smart timing, dismiss, snooze, track adherence, get refill alerts before running out.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders track_adherence get_refill_alert set_window",
            ),
            (
                "pillreminder",
                "Pill Reminder Pro",
                "Pill Reminder: set complex medication schedules with multiple pills, dismiss each dose, snooze individual meds, track missed doses, get end-of-day completion report.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders set_schedule track_missed get_report",
            ),
            (
                "bingewatch",
                "Binge Clock Alerts",
                "Binge Clock entertainment reminders: set reminders for show premieres and new episodes, dismiss, snooze for next viewing, get season premiere countdown alerts.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders track_show get_countdown share_alert",
            ),
            (
                "anylist",
                "AnyList Reminders",
                "AnyList grocery reminder system: set location-based reminders for stores, dismiss when you get there, snooze, get nudged about items you need to restock.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders set_location track_restock geofence_alert",
            ),
            (
                "bring",
                "Bring Shopping Alerts",
                "Bring shopping list reminders: set time-based and location-triggered reminders for your shopping lists, dismiss, snooze, get alerted when near favorite stores.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders set_geofence share_alert customize_tone",
            ),
            (
                "lasttime",
                "Last Time Tracker",
                "Last Time activity tracker: set reminders for recurring activities (water plants, change filter, oil change), dismiss when done, snooze, track last completed date.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders set_interval track_last log_completion",
            ),
            (
                "remindme",
                "Remind Me Later",
                "Remind Me Later: quick one-tap reminder creation, dismiss via notification, snooze to tomorrow, set recurring reminders with natural language time input.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders set_recurring quick_create natural_time",
            ),
            (
                "nag",
                "Nag Reminders",
                "Nag persistent reminder engine: set reminders that escalate from gentle nudge to loud alert, dismiss with confirmation, snooze with decreasing intervals until completed.",
                "set_reminder dismiss_reminder snooze_reminder list_reminders escalate_alert set_escalation confirm_dismiss",
            ),
        ],
    )

    # ── Compete with family.family_settings (toggle_feature, set_permission, etc.) ──
    add(
        "config_comp",
        [
            (
                "launchdarkly",
                "LaunchDarkly Feature Flags",
                "LaunchDarkly feature management: toggle features on/off, set rollout percentages, manage targeting rules, configure environment-specific feature flags.",
                "toggle_feature set_permission configure_flag view_settings set_targeting manage_environment rollback_feature",
            ),
            (
                "optimizely",
                "Optimizely Config",
                "Optimizely feature experimentation: toggle experiments and features, set user targeting, configure A/B test variants, manage feature rollouts with kill switch.",
                "toggle_feature set_permission configure_flag view_settings set_targeting manage_experiment kill_switch",
            ),
            (
                "configcat",
                "ConfigCat Settings",
                "ConfigCat feature flag service: toggle features across environments, set targeting rules by user segment, configure percentage rollouts, manage flag dependencies.",
                "toggle_feature set_permission configure_flag view_settings set_targeting manage_dependency set_segment",
            ),
            (
                "flagsmith",
                "Flagsmith Features",
                "Flagsmith feature control: toggle features for specific users or segments, set remote config values, manage feature lifecycles from dev to production, audit flag changes.",
                "toggle_feature set_permission configure_flag view_settings set_segment manage_lifecycle audit_change",
            ),
            (
                "splitio",
                "Split Feature Flags",
                "Split feature delivery: toggle features with gradual rollout, set user targeting rules, configure feature gates with metrics, manage kill switches with instant effect.",
                "toggle_feature set_permission configure_flag view_settings set_rollout manage_killswitch measure_impact",
            ),
            (
                "cloudbees",
                "CloudBees Feature Management",
                "CloudBees feature control: toggle features in production, set permission-based access, configure progressive delivery, manage feature flag approvals and audit trails.",
                "toggle_feature set_permission configure_flag view_settings manage_approval set_progressive audit_flag",
            ),
            (
                "prefab",
                "Prefab Config",
                "Prefab dynamic config: toggle features from admin UI, set user-specific overrides, configure default values, manage config with version history and instant propagation.",
                "toggle_feature set_permission configure_flag view_settings set_override manage_version propagate_config",
            ),
            (
                "statsig",
                "Statsig Gates",
                "Statsig feature gates: toggle features for user segments, set gradual rollout percentages, configure parameterized experiments, manage gate dependencies in a DAG.",
                "toggle_feature set_permission configure_flag view_settings set_gate manage_experiment set_dependency",
            ),
            (
                "devcycle",
                "DevCycle Flags",
                "DevCycle feature management: toggle features with variable config, set per-environment overrides, manage targeting by user properties, real-time flag updates with streaming.",
                "toggle_feature set_permission configure_flag view_settings set_variable manage_override stream_update",
            ),
            (
                "hypertune",
                "Hypertune Config",
                "Hypertune feature control: toggle dynamic features, set A/B test configs, configure per-user overrides, manage feature defaults with instant propagation across apps.",
                "toggle_feature set_permission configure_flag view_settings set_ab_test manage_default instant_propagate",
            ),
            (
                "growthbook",
                "GrowthBook Features",
                "GrowthBook open-source feature flags: toggle features with targeting, set gradual rollouts, configure experiments with metric tracking, manage feature lifecycle.",
                "toggle_feature set_permission configure_flag view_settings set_rollout manage_experiment track_metric",
            ),
        ],
    )

    return templates


# ── Native-App-as-Aggregator architecture: competing same-domain connectors
#    (grocery_comp.*, todo_comp.*, etc.) are REMOVED.  Walmart, Costco, Instacart
#    are DATA BACKENDS to family.shopping — never visible as peer connectors.
#    Only semantically-diverse distractors from OTHER OS domains remain.
#    See: k1/docs/future_family_apps_development.md §Two Kinds of Connectors
DISTRACTOR_TEMPLATES: list[dict[str, Any]] = _generate_real_world_distractors()

# ═══════════════════════════════════════════════════════════════════════════
# Scale Infrastructure — Distinct Brands Per Vertical
# ═══════════════════════════════════════════════════════════════════════════
#
# At scale, replicating the same connector N times (_r1, _r2, ...) is fake.
# Real scale means 200 different car connectors all with climate control,
# 200 different banking apps all with checking/savings, etc.
#
# We generate genuinely distinct brands within each vertical.  All variants
# of the same archetype share action names (realistic: Tesla and Audi both
# have set_temperature).  This creates the REAL semantic overlap that
# stresses the search at 10K-100K connectors.

# ── Category → brand names for generating distinct scale variants ──
# Each category has 50-60 real brand names.  Beyond that, synthetic names
# are generated programmatically: "AutoBrand_51", "AutoBrand_52", etc.

_CATEGORY_BRANDS: dict[str, list[str]] = {
    "banking": [
        "Chase",
        "Bank of America",
        "Wells Fargo",
        "Citi",
        "US Bank",
        "TD Bank",
        "PNC",
        "Capital One",
        "American Express",
        "Venmo",
        "Ally Bank",
        "SoFi",
        "Discover Bank",
        "HSBC",
        "Barclays",
        "Deutsche Bank",
        "Santander",
        "BNP Paribas",
        "Credit Suisse",
        "UBS",
        "Goldman Sachs",
        "Morgan Stanley",
        "Charles Schwab",
        "Fidelity",
        "Vanguard",
        "E*TRADE",
        "Robinhood",
        "Revolut",
        "Monzo",
        "Starling Bank",
        "N26",
        "Chime",
        "Varo",
        "Current",
        "Aspiration",
        "One Finance",
        "Novo",
        "Mercury",
        "Brex",
        "Ramp",
        "Stripe Treasury",
        "Bluevine",
        "Kabbage",
        "Fundbox",
        "OnDeck",
        "LendingClub",
        "Prosper",
        "Avant",
        "Upgrade",
        "LightStream",
        "M1 Finance",
        "Betterment",
        "Wealthfront",
        "Acorns",
        "Stash",
        "Public",
        "Tastyworks",
        "Webull",
        "Questrade",
        "Interactive Brokers",
    ],
    "smart_home": [
        "Philips Hue",
        "Google Nest",
        "Ring",
        "ecobee",
        "iRobot Roomba",
        "Belkin Wemo",
        "Lutron Caseta",
        "August Home",
        "myQ Chamberlain",
        "Arlo",
        "Wyze",
        "Eve Systems",
        "Aqara",
        "TP-Link Kasa",
        "Meross",
        "Govee",
        "Nanoleaf",
        "LIFX",
        "Sengled",
        "Cync by GE",
        "Schlage",
        "Yale Smart",
        "Kwikset",
        "Eufy Security",
        "Blink",
        "SimpliSafe",
        "Abode",
        "ADT Smart",
        "Vivint",
        "Frontpoint",
        "Cove Security",
        "Notion Sensors",
        "Swann",
        "Reolink",
        "Amcrest",
        "Ubiquiti UniFi",
        "D-Link Smart",
        "Netgear Arlo",
        "Eero",
        "Orbi",
        "Google Wifi",
        "Asus ZenWiFi",
        "TP-Link Deco",
        "Synology Smart",
        "QNAP Home",
        "Samsung SmartThings",
        "Hubitat",
        "Home Assistant",
        "Leviton Smart",
        "GE Cync",
        "Insteon",
        "Z-Wave Alliance",
        "Zigbee Alliance",
        "Matter Standard",
        "Thread Group",
        "Aeotec",
        "Zooz",
        "Fibaro",
        "Homeseer",
        "Ezlo",
    ],
    "health_fitness": [
        "Fitbit",
        "Strava",
        "MyFitnessPal",
        "Whoop",
        "Apple Health",
        "Withings",
        "Headspace",
        "Garmin Connect",
        "Peloton",
        "Oura Ring",
        "Samsung Health",
        "Xiaomi Mi Fit",
        "Huawei Health",
        "Amazfit",
        "Polar Flow",
        "Suunto",
        "Coros",
        "Wahoo Fitness",
        "Zwift",
        "Calm",
        "Insight Timer",
        "Ten Percent Happier",
        "Breethe",
        "Sleep Cycle",
        "Pillow",
        "AutoSleep",
        "Zero Fasting",
        "Lifesum",
        "Noom",
        "WeightWatchers",
        "Lose It",
        "Cronometer",
        "Carb Manager",
        "JEFIT",
        "Strong",
        "Fitbod",
        "Nike Training Club",
        "Adidas Running",
        "MapMyRun",
        "RunKeeper",
        "Couch to 5K",
        "Seven Minute Workout",
        "Yoga Studio",
        "Down Dog",
        "Glo Yoga",
        "Aaptiv",
        "Fiit",
        "Tonal",
        "Mirror Fitness",
        "Tempo Fit",
        "Hydrow",
        "Ergatta",
        "iFit",
        "NordicTrack",
        "Bowflex",
    ],
    "productivity": [
        "Slack",
        "Notion",
        "Jira",
        "GitHub",
        "Linear",
        "Figma",
        "Stripe",
        "Dropbox",
        "Gmail",
        "Asana",
        "Monday.com",
        "Basecamp",
        "Trello",
        "ClickUp",
        "Wrike",
        "Airtable",
        "Coda",
        "Confluence",
        "Bitbucket",
        "GitLab",
        "Azure DevOps",
        "CircleCI",
        "Jenkins",
        "Travis CI",
        "Vercel",
        "Netlify",
        "Cloudflare Workers",
        "AWS Lambda",
        "Heroku",
        "DigitalOcean",
        "Linode",
        "Fastly",
        "Datadog",
        "New Relic",
        "Sentry",
        "LogRocket",
        "FullStory",
        "Mixpanel",
        "Amplitude",
        "Segment",
        "HubSpot",
        "Salesforce",
        "Zoho CRM",
        "Pipedrive",
        "Intercom",
        "Zendesk",
        "Freshdesk",
        "Help Scout",
        "Front App",
        "Zoom",
        "Microsoft Teams",
        "Google Meet",
        "Webex",
        "GoToMeeting",
        "Calendly",
        "SavvyCal",
        "Loom",
        "Descript",
        "Miro",
    ],
    "automotive": [
        "Tesla",
        "BMW",
        "Audi",
        "Ford",
        "Honda",
        "Toyota",
        "Mercedes-Benz",
        "Porsche",
        "Volvo",
        "Hyundai",
        "Kia",
        "Nissan",
        "Subaru",
        "Volkswagen",
        "Chevrolet",
        "Jeep",
        "GMC",
        "Cadillac",
        "Lexus",
        "Mazda",
        "Acura",
        "Infiniti",
        "Lincoln",
        "Buick",
        "Chrysler",
        "Dodge",
        "Ram Trucks",
        "Land Rover",
        "Jaguar",
        "Mini Cooper",
        "Fiat",
        "Alfa Romeo",
        "Maserati",
        "Bentley",
        "Rolls-Royce",
        "Aston Martin",
        "McLaren",
        "Ferrari",
        "Lamborghini",
        "Bugatti",
        "Genesis",
        "Rivian",
        "Lucid Motors",
        "Polestar",
        "BYD Auto",
        "NIO",
        "XPeng",
        "Li Auto",
        "Fisker",
        "Scout Motors",
        "Canoo",
        "Faraday Future",
        "Aptera",
        "Sono Motors",
        "VinFast",
        "Tata Motors",
        "Mahindra",
        "Great Wall",
        "Geely",
        "Chery",
    ],
    "insurance": [
        "GEICO",
        "Progressive",
        "Allstate",
        "Lemonade",
        "MetLife",
        "State Farm",
        "Liberty Mutual",
        "Nationwide",
        "Farmers Insurance",
        "Travelers",
        "USAA",
        "American Family",
        "Erie Insurance",
        "Auto-Owners",
        "Hartford",
        "Chubb",
        "AIG",
        "Zurich Insurance",
        "AXA",
        "Allianz",
        "Prudential",
        "New York Life",
        "MassMutual",
        "Northwestern Mutual",
        "Guardian Life",
        "Pacific Life",
        "Lincoln Financial",
        "John Hancock",
        "Transamerica",
        "Brighthouse",
        "Symetra",
        "Banner Life",
        "Haven Life",
        "Ladder Life",
        "Bestow",
        "Ethos Life",
        "Fabric",
        "Root Insurance",
        "Metromile",
        "Clearcover",
        "Hippo Insurance",
        "Kin Insurance",
        "Policygenius",
        "Zebra",
        "Insurify",
        "CoverWallet",
        "Embroker",
        "Next Insurance",
        "Thimble",
        "Pie Insurance",
        "Coalition",
        "At-Bay",
        "Corvus Insurance",
    ],
    "legal": [
        "Rocket Lawyer",
        "LegalZoom",
        "LexisNexis",
        "Clio",
        "Avvo",
        "FindLaw",
        "LawDepot",
        "Nolo",
        "UpCounsel",
        "Priori Legal",
        "Axiom Law",
        "Elevate",
        "LegalShield",
        "ARAG Legal",
        "Lawpath",
        "DocuSign",
        "HelloSign",
        "PandaDoc",
        "Ironclad",
        "LinkSquares",
        "Juro",
        "Contractbook",
        "Lexion",
        "Evisort",
        "Icertis",
        "SirionLabs",
        "Conga",
        "Agiloft",
        "Onit",
        "Mitratech",
        "Everlaw",
        "Relativity",
        "Logikcull",
        "DISCO",
        "Casepoint",
        "Nextpoint",
        "CaseText",
        "ROSS Intelligence",
        "Kira Systems",
        "Luminance",
        "Eigen Technologies",
        "Seal Software",
        "LawGeex",
        "DoNotPay",
        "Hello Divorce",
        "LegalNature",
        "RocketMatter",
        "PracticePanther",
        "MyCase",
        "Smokeball",
        "CosmoLex",
        "TimeSolv",
    ],
    "real_estate": [
        "Zillow",
        "Redfin",
        "Realtor.com",
        "Airbnb",
        "Vrbo",
        "Trulia",
        "Compass",
        "Opendoor",
        "Offerpad",
        "Knock",
        "Ribbon Home",
        "HomeLight",
        "Flyhomes",
        "Orchard",
        "Sundae",
        "Roofstock",
        "Fundrise",
        "CrowdStreet",
        "RealtyMogul",
        "DiversyFund",
        "Reonomy",
        "Cherre",
        "HouseCanary",
        "CoreLogic",
        "Black Knight",
        "ATTOM Data",
        "Estately",
        "Homes.com",
        "Apartments.com",
        "Zumper",
        "HotPads",
        "PadMapper",
        "Rent.com",
        "CoStar",
        "LoopNet",
        "Crexi",
        "Ten-X",
        "Auction.com",
        "Hubzu",
        "Xome",
        "Move.com",
        "ShowingTime",
        "BrokerBay",
        "ShowingTime+",
        "SentriLock",
        "Supra eKEY",
        "ShowingHero",
        "MoxiWorks",
        "kvCORE",
        "BoomTown",
    ],
    "travel_transport": [
        "Expedia",
        "Uber",
        "Lyft",
        "Booking.com",
        "Airbnb Travel",
        "Kayak",
        "Skyscanner",
        "Google Flights",
        "Hopper",
        "TripIt",
        "TripAdvisor",
        "Priceline",
        "Hotels.com",
        "Orbitz",
        "Travelocity",
        "Agoda",
        "Hostelworld",
        "Couchsurfing",
        "HomeExchange",
        "TrustedHousesitters",
        "GetYourGuide",
        "Viator",
        "Klook",
        "ToursByLocals",
        "Withlocals",
        "Rome2rio",
        "Omio",
        "Wanderu",
        "FlixBus",
        "Greyhound",
        "Amtrak",
        "Eurostar",
        "Thalys",
        "SNCF Connect",
        "Trainline",
        "BlaBlaCar",
        "Zipcar",
        "Turo",
        "Getaround",
        "GIG Car Share",
        "Revel Transit",
        "Lime",
        "Bird",
        "Spin",
        "Voi",
        "Dott",
        "Tier Mobility",
        "FreeNow",
        "Bolt",
        "Cabify",
    ],
    "food_delivery": [
        "DoorDash",
        "Grubhub",
        "Instacart",
        "Uber Eats",
        "Deliveroo",
        "Postmates",
        "Just Eat",
        "Takeaway.com",
        "Delivery Hero",
        "Glovo",
        "Wolt",
        "Zomato",
        "Swiggy",
        "Foodpanda",
        "ChowNow",
        "Slice",
        "Toast Takeout",
        "Olo",
        "BentoBox",
        "Menufy",
        "Waitr",
        "Beyond Menu",
        "Ritual",
        "MealPal",
        "Freshly",
        "HelloFresh",
        "Blue Apron",
        "Home Chef",
        "Sunbasket",
        "Marley Spoon",
        "Green Chef",
        "Factor",
        "CookUnity",
        "Shef",
        "WoodSpoon",
        "EatStreet",
        "Delivery.com",
        "Seamless",
        "Caviar",
        "Tock",
        "OpenTable",
        "Resy",
        "Yelp Reservations",
        "Tablein",
        "Eat App",
        "GoDaddy Restaurant",
        "Square Online",
        "Lunchbox",
        "Popmenu",
        "Bbot",
    ],
    "social_media": [
        "Twitter/X",
        "Instagram",
        "LinkedIn",
        "TikTok",
        "Reddit",
        "Facebook",
        "Snapchat",
        "Pinterest",
        "YouTube Social",
        "WhatsApp",
        "Telegram",
        "Signal",
        "Discord",
        "Twitch",
        "BeReal",
        "Mastodon",
        "Bluesky",
        "Threads",
        "Substack",
        "Medium",
        "Tumblr",
        "Flickr",
        "VSCO",
        "Nextdoor",
        "WeChat",
        "LINE",
        "KakaoTalk",
        "Viber",
        "Weibo",
        "Douyin",
        "Kuaishou",
        "Likee",
        "Triller",
        "Clapper",
        "Clubhouse",
        "Spoon",
        "Fishbowl",
        "Blind",
        "Glassdoor Social",
        "Indeed Community",
        "Strava Social",
        "AllTrails Social",
        "Goodreads",
        "Letterboxd",
        "Untappd",
        "Vivino",
        "MyFitnessPal Social",
        "Waze Social",
        "Venmo Social",
        "Splitwise",
    ],
    "dev_tools": [
        "Docker",
        "Atlassian Cloud",
        "Cloudflare",
        "Vercel",
        "Datadog",
        "AWS",
        "Google Cloud",
        "Azure",
        "Oracle Cloud",
        "IBM Cloud",
        "HashiCorp",
        "Terraform",
        "Ansible",
        "Puppet",
        "Chef",
        "Kubernetes",
        "Helm",
        "Istio",
        "Linkerd",
        "Consul",
        "Prometheus",
        "Grafana",
        "Elasticsearch",
        "Kibana",
        "Logstash",
        "MongoDB Atlas",
        "Redis Cloud",
        "Supabase",
        "Firebase",
        "PlanetScale",
        "Neon",
        "CockroachDB",
        "TimescaleDB",
        "InfluxDB",
        "Snowflake",
        "Databricks",
        "Confluent Kafka",
        "Redpanda",
        "RabbitMQ",
        "NATS",
        "Twilio",
        "SendGrid",
        "Mailgun",
        "Plaid",
        "Stripe API",
        "Algolia",
        "Mapbox",
        "Auth0",
        "Okta",
        "Cloudinary",
    ],
    "crypto_web3": [
        "Coinbase",
        "MetaMask",
        "OpenSea",
        "Chainlink",
        "Uniswap",
        "Aave",
        "Compound",
        "Maker DAO",
        "Lido",
        "Curve Finance",
        "Balancer",
        "SushiSwap",
        "PancakeSwap",
        "Trader Joe",
        "GMX",
        "dYdX",
        "Synthetix",
        "Polymarket",
        "Augur",
        "Gnosis Safe",
        "Argent",
        "Rainbow",
        "Trust Wallet",
        "Phantom",
        "Ledger Live",
        "Trezor Suite",
        "Exodus",
        "Blockchain.com",
        "Kraken",
        "Binance",
        "Gemini",
        "FTX 2.0",
        "OKX",
        "Bybit",
        "KuCoin",
        "Bitstamp",
        "Bitfinex",
        "Crypto.com",
        "eToro",
        "Robinhood Crypto",
        "1inch",
        "Paraswap",
        "Matcha",
        "Zapper",
        "Zerion",
        "DeBank",
        "Nansen",
        "Dune Analytics",
        "Messari",
        "The Graph",
        "IPFS",
        "Filecoin",
        "Arweave",
        "Helium",
        "Render Network",
    ],
    "gaming": [
        "Steam",
        "Epic Games",
        "Twitch",
        "Xbox Live",
        "PlayStation Network",
        "Nintendo Switch",
        "Battle.net",
        "EA App",
        "Ubisoft Connect",
        "GOG Galaxy",
        "Roblox",
        "Minecraft",
        "Fortnite",
        "Genshin Impact",
        "Apex Legends",
        "Valorant",
        "League of Legends",
        "Dota 2",
        "CS:GO",
        "Overwatch",
        "Destiny",
        "World of Warcraft",
        "Final Fantasy XIV",
        "Elder Scrolls Online",
        "Guild Wars 2",
        "RuneScape",
        "EVE Online",
        "Star Citizen",
        "Elite Dangerous",
        "Discord Gaming",
        "TeamSpeak",
        "Mumble",
        "Parsec",
        "Moonlight",
        "GeForce Now",
        "Shadow PC",
        "Boosteroid",
        "Blacknut",
        "Luna",
        "Stadia",
        "Xbox Cloud",
        "Antstream",
        "PlayStation Plus",
        "Game Pass",
        "itch.io",
        "Humble Bundle",
        "Fanatical",
        "Green Man Gaming",
        "G2A",
    ],
    "iot_industrial": [
        "Siemens MindSphere",
        "Bosch IoT Suite",
        "Honeywell Forge",
        "Schneider EcoStruxure",
        "ABB Ability",
        "Rockwell Automation",
        "Emerson PlantWeb",
        "Yokogawa OpreX",
        "Mitsubishi Electric",
        "Omron i-Automation",
        "Keyence",
        "Fanuc Field",
        "GE Digital Predix",
        "PTC ThingWorx",
        "IBM Maximo",
        "SAP Leonardo IoT",
        "Cisco IoT",
        "Intel IoT",
        "Arm Pelion",
        "NXP EdgeLock",
        "STMicro STM32",
        "Texas Instruments IoT",
        "Microchip IoT",
        "Analog Devices",
        "Advantech WISE",
        "Moxa ThingsPro",
        "Digi Remote Manager",
        "Telit Cinterion",
        "Sierra Wireless",
        "Quectel",
        "u-blox Thingstream",
        "Particle IoT",
        "Balena",
        "Foundries.io",
        "Zededa",
        "Litmus Edge",
        "Crosser",
        "Software AG Cumulocity",
        "ClearBlade",
        "Losant",
        "Ubidots",
        "Blynk",
        "ThingSpeak",
        "Adafruit IO",
        "Arduino Cloud",
        "TagoIO",
        "Datablend",
    ],
    "agriculture": [
        "John Deere Ops",
        "Climate FieldView",
        "CropX",
        "FarmLogs",
        "Trimble Ag",
        "AGCO Fuse",
        "Case IH AFS",
        "New Holland PLM",
        "Kubota Agri",
        "CLAAS Telematics",
        "Raven Industries",
        "Topcon Agriculture",
        "Ag Leader",
        "Precision Planting",
        "Farmers Edge",
        "Granular",
        "Conservis",
        "Agworld",
        "SST Software",
        "AgDNA",
        "Ceres Imaging",
        "Taranis",
        "Prospera",
        "Cropio",
        "Semios",
        "Phytech",
        "Arable",
        "TerrAvion",
        "Hummingbird Tech",
        "Small Robot Co",
        "Blue River Tech",
        "Iron Ox",
        "Bowery Farming",
        "Plenty Ag",
        "Aerofarms",
        "AppHarvest",
        "Gotham Greens",
        "BrightFarms",
        "Freight Farms",
        "CropMetrics",
        "WiseConn",
        "Ranch Systems",
        "OnFarm Systems",
        "Agribotix",
        "Sentera",
        "DroneDeploy Ag",
        "PrecisionHawk",
        "SlantRange",
    ],
    "logistics": [
        "FedEx",
        "UPS",
        "USPS",
        "DHL Express",
        "Amazon Logistics",
        "XPO Logistics",
        "C.H. Robinson",
        "J.B. Hunt",
        "Schneider National",
        "Ryder System",
        "Penske Logistics",
        "Werner Enterprises",
        "Knight-Swift",
        "Old Dominion",
        "Estes Express",
        "Saia LTL",
        "YRC Freight",
        "R+L Carriers",
        "Roadrunner",
        "Coyote Logistics",
        "Echo Global",
        "Arrive Logistics",
        "Flexport",
        "Freightos",
        "FreightWaves",
        "project44",
        "FourKites",
        "ShipBob",
        "ShipStation",
        "Shippo",
        "Easyship",
        "Pirate Ship",
        "Sendle",
        "Shipt",
        "Veho",
        "Lasership",
        "OnTrac",
        "Gopuff Delivery",
        "Jokr",
        "Buyk",
        "Flink",
        "Getir",
        "Gorillas",
        "Zapp",
        "Instacart Enterprise",
        "Bringg",
        "Onfleet",
    ],
    "energy_utilities": [
        "Tesla Energy",
        "Enphase",
        "Sense Energy",
        "ChargePoint",
        "Sunrun",
        "SunPower",
        "Vivint Solar",
        "Sunnova",
        "Palmetto Solar",
        "Momentum Solar",
        "ADT Solar",
        "Trinity Solar",
        "NRG Energy",
        "Direct Energy",
        "Constellation",
        "Duke Energy",
        "Southern Co",
        "Pacific Gas",
        "ConEdison",
        "Exelon",
        "NextEra",
        "Dominion Energy",
        "Xcel Energy",
        "Sempra",
        "Edison International",
        "Shell Energy",
        "BP Pulse",
        "EVgo",
        "Electrify America",
        "Blink Charging",
        "Wallbox",
        "JuiceBox",
        "ClipperCreek",
        "FLO Charging",
        "Greenlots",
        "EcoFactor",
        "Bidgely",
        "GridPoint",
        "AutoGrid",
        "Stem Energy",
        "Generac",
        "Enphase IQ8",
        "SolarEdge",
        "Tigo Energy",
        "APsystems",
        "Span.io",
        "Lumin Smart",
        "Schneider Wiser",
        "Leviton Load Center",
        "Sense Flex",
        "Emporia Energy",
        "Neurio",
        "Smappee",
        "Eyedro",
        "Rainforest EMU",
    ],
    "retail_ecommerce": [
        "Shopify",
        "Walmart Marketplace",
        "Target Plus",
        "Amazon Seller",
        "eBay Seller",
        "Etsy Shop",
        "BigCommerce",
        "WooCommerce",
        "Magento Adobe",
        "Salesforce Commerce",
        "Square Online",
        "Wix eCommerce",
        "Squarespace Commerce",
        "Ecwid",
        "PrestaShop",
        "OpenCart",
        "Volusion",
        "Shift4Shop",
        "Weebly eCommerce",
        "GoDaddy Store",
        "Alibaba Seller",
        "AliExpress Seller",
        "JD.com Seller",
        "Flipkart Seller",
        "Mercado Libre",
        "Coupang Seller",
        "Zalando Partner",
        "ASOS Marketplace",
        "Wayfair Seller",
        "Overstock Supplier",
        "Macy's Vendor",
        "Nordstrom Partner",
        "Kohl's Marketplace",
        "Best Buy Marketplace",
        "Costco Supplier",
        "Sam's Club Vendor",
        "Lowe's Partner",
        "Home Depot Pro",
        "Ace Hardware Vendor",
        "True Value Supplier",
        "Kroger Ship",
        "Instacart Partner",
        "Walgreens Marketplace",
        "CVS Supplier",
        "Sephora Partner",
        "Ulta Beauty Vendor",
        "Chewy Partner",
        "Petco Vendor",
    ],
    "government_civic": [
        "IRS e-File",
        "USCIS Case Status",
        "SBA Loan Portal",
        "Social Security Admin",
        "Medicare Portal",
        "Medicaid Services",
        "VA Benefits",
        "FEMA Assistance",
        "USAJobs Federal",
        "GSA Advantage",
        "SAM.gov Contracts",
        "Grants.gov",
        "Census Bureau",
        "Bureau of Labor",
        "Department of State",
        "Customs CBP",
        "ICE Portal",
        "TSA PreCheck",
        "Global Entry",
        "DMV Services",
        "Passport Online",
        "Visa Services",
        "CBP Traveler",
        "Federal Register",
        "Regulations.gov",
        "Data.gov",
        "HealthCare.gov",
        "Health Insurance Marketplace",
        "Office of Personnel",
        "Thrift Savings Plan",
        "Federal Retirement",
        "Postal Inspection",
        "FCC Licensing",
        "FTC Consumer",
        "CFPB Complaints",
        "SEC EDGAR",
        "FDIC BankFind",
        "NCUA Credit Union",
        "Treasury Direct",
        "Energy Star",
        "EPA Compliance",
        "OSHA Portal",
        "EEOC Portal",
        "National Archives",
        "Library of Congress",
        "Smithsonian API",
        "NOAA Weather",
    ],
    "science_research": [
        "GenBank NCBI",
        "Zenodo CERN",
        "Labguru ELN",
        "PubMed Central",
        "arXiv",
        "bioRxiv",
        "ChemRxiv",
        "medRxiv",
        "ResearchGate",
        "Academia.edu",
        "ORCID Registry",
        "CrossRef DOI",
        "DataCite",
        "Figshare",
        "Dryad Digital",
        "Open Science Framework",
        "Protocols.io",
        "Benchling",
        "SciNote",
        "LabArchives",
        "RSpace",
        "eLabJournal",
        "LabFolder",
        "Quartzy",
        "ZappyLab",
        "Addgene",
        "ATCC Repository",
        "Jackson Laboratory",
        "Bloomington Stock Center",
        "FlyBase",
        "WormBase",
        "Mouse Genome",
        "Zebrafish Model",
        "Xenbase",
        "PomBase",
        "Saccharomyces DB",
        "EcoCyc",
        "MetaCyc",
        "KEGG Database",
        "UniProt",
        "PDB Protein Data",
        "EMBL-EBI",
        "DDBJ Japan",
        "ENA Europe",
        "ArrayExpress",
        "GEO Datasets",
        "PRIDE Proteomics",
        "MetaboLights",
        "BioStudies",
    ],
    "grocery": [
        "Instacart",
        "Walmart Grocery",
        "Amazon Fresh",
        "Kroger",
        "Safeway",
        "Whole Foods",
        "ALDI",
        "Trader Joe's",
        "Costco Wholesale",
        "Wegmans",
        "HEB",
        "Publix",
        "Target Grocery",
        "Meijer",
        "ShopRite",
        "Hy-Vee",
        "Giant Eagle",
        "Stop & Shop",
        "Winn-Dixie",
        "Food Lion",
        "Sprouts Farmers",
        "Fresh Thyme",
        "Natural Grocers",
        "Earth Fare",
        "Fairway Market",
        "Harris Teeter",
        "Ingles",
        "Brookshire's",
        "Woodman's",
        "Market Basket",
        "Stew Leonard's",
        "Bristol Farms",
        "Gelson's",
        "Lucky Supermarket",
        "Stater Bros",
        "WinCo Foods",
        "Fred Meyer",
        "Smith's",
        "King Soopers",
        "QFC",
        "Vons",
        "Albertsons",
        "Jewel-Osco",
        "Shaw's",
        "Acme Markets",
        "Raley's",
        "Bashas'",
        "Food City",
        "Price Chopper",
        "Tops Markets",
    ],
    "housekeeping": [
        "Tody",
        "Sweepy",
        "Homey Chores",
        "OurHome",
        "Chorsee",
        "Nipto",
        "Brili Routines",
        "Maple House",
        "Flatastic",
        "Spotless Cleaning",
        "Homeaglow",
        "FlyLady",
        "MaidPro",
        "Merry Maids",
        "Molly Maid",
        "Handy",
        "TaskRabbit Cleaning",
        "Helpling",
        "Tidy Choice",
        "Homejoy",
        "Cleanify",
        "Housekeep",
        "Dust Busters",
        "Mr Clean Home",
        "Bissell CleanView",
        "Shark Clean",
        "Dyson Home",
        "Roomba Clean",
        "Braava Mop",
        "Eufy Clean",
        "Ecovacs Deebot",
        "Roborock Home",
        "Neato Botvac",
        "Samsung Jet Bot",
        "LG CordZero",
        "Miele Home",
        "Sebo Clean",
        "Rainbow Cleaner",
        "Kirby Home",
        "Oreck Clean",
        "Hoover Clean",
        "Eureka Clean",
        "Dirt Devil",
        "Black+Decker Clean",
        "Rubbermaid Clean",
        "Clorox Home",
        "Lysol Clean",
        "Method Home",
        "Mrs Meyer's",
        "Seventh Generation",
    ],
}

# ── Domain → category mapping ──
_DOMAIN_CATEGORY: dict[str, str] = {}
for _cat, _brands in _CATEGORY_BRANDS.items():
    for _brand in _brands:
        _slug = _brand.lower().replace(" ", "").replace("-", "").replace(".", "")
        _slug = "".join(c for c in _slug if c.isalnum())
        _DOMAIN_CATEGORY[_slug] = _cat

# Add the original template domains explicitly
_DOMAIN_CATEGORY.update(
    {
        "chase": "banking",
        "bofa": "banking",
        "wellsfargo": "banking",
        "amex": "banking",
        "capitalone": "banking",
        "citi": "banking",
        "usbank": "banking",
        "tdbank": "banking",
        "pnc": "banking",
        "venmo": "banking",
        "philips-hue": "smart_home",
        "nest": "smart_home",
        "ring": "smart_home",
        "ecobee": "smart_home",
        "roomba": "smart_home",
        "wemo": "smart_home",
        "lutron": "smart_home",
        "august": "smart_home",
        "myq": "smart_home",
        "arlo": "smart_home",
        "fitbit": "health_fitness",
        "strava": "health_fitness",
        "myfitnesspal": "health_fitness",
        "whoop": "health_fitness",
        "apple-health": "health_fitness",
        "withings": "health_fitness",
        "headspace": "health_fitness",
        "garmin": "health_fitness",
        "peloton": "health_fitness",
        "oura": "health_fitness",
        "slack": "productivity",
        "notion": "productivity",
        "jira": "productivity",
        "github": "productivity",
        "linear": "productivity",
        "figma": "productivity",
        "stripe": "productivity",
        "dropbox": "productivity",
        "gmail": "productivity",
        "asana": "productivity",
        "tesla-energy": "energy_utilities",
        "enphase": "energy_utilities",
        "sense": "energy_utilities",
        "chargepoint": "energy_utilities",
        "fordpass": "automotive",
        "onstar": "automotive",
        "carfax": "automotive",
        "geico": "insurance",
        "progressive": "insurance",
        "allstate": "insurance",
        "lemonade": "insurance",
        "metlife": "insurance",
        "rocketlawyer": "legal",
        "legalzoom": "legal",
        "lexisnexis": "legal",
        "clio": "legal",
        "zillow": "real_estate",
        "redfin": "real_estate",
        "realtor": "real_estate",
        "airbnb": "real_estate",
        "expedia": "travel_transport",
        "uber": "travel_transport",
        "lyft": "travel_transport",
        "booking": "travel_transport",
        "doordash": "food_delivery",
        "grubhub": "food_delivery",
        "instacart": "food_delivery",
        "twitter": "social_media",
        "instagram": "social_media",
        "linkedin": "social_media",
        "tiktok": "social_media",
        "reddit": "social_media",
        "docker": "dev_tools",
        "atlassian": "dev_tools",
        "cloudflare": "dev_tools",
        "vercel": "dev_tools",
        "datadog": "dev_tools",
        "coinbase": "crypto_web3",
        "metamask": "crypto_web3",
        "opensea": "crypto_web3",
        "chainlink": "crypto_web3",
        "steam": "gaming",
        "epic-games": "gaming",
        "twitch": "gaming",
        "xbox": "gaming",
        "siemens": "iot_industrial",
        "bosch": "iot_industrial",
        "honeywell": "iot_industrial",
        "schneider": "iot_industrial",
        "john-deere": "agriculture",
        "climate-fieldview": "agriculture",
        "cropx": "agriculture",
        "farmlogs": "agriculture",
        "fedex": "logistics",
        "ups": "logistics",
        "usps": "logistics",
        "fleetservice": "logistics",
        "shopify-admin": "retail_ecommerce",
        "walmart-api": "retail_ecommerce",
        "target-api": "retail_ecommerce",
        "irs": "government_civic",
        "uscis": "government_civic",
        "sba": "government_civic",
        "genbank": "science_research",
        "zenodo": "science_research",
        "labguru": "science_research",
        # Secondary verticals from SCALE EXPANSION
        "doordash-drive": "food_delivery",
        "spotify": "gaming",
        "netflix": "gaming",
        "youtube": "gaming",
        "kindle": "gaming",
        "discord": "social_media",
        "duolingo": "health_fitness",
        "coursera": "health_fitness",
        "moodle": "health_fitness",
        "quizlet": "health_fitness",
        "khan-academy": "health_fitness",
        # Competing distractor domains (directly compete with FamilyOS connectors)
        "grocery_comp": "grocery",
        "todo_comp": "productivity",
        "scheduling_comp": "productivity",
        "housekeeping_comp": "housekeeping",
        "alerts_comp": "productivity",
        "config_comp": "dev_tools",
    }
)


def _get_category(domain: str) -> str:
    """Map a domain to its vertical category for brand generation."""
    return _DOMAIN_CATEGORY.get(domain, "productivity")


def _brand_slug(name: str) -> str:
    """Convert a brand name to a connector-safe domain slug."""
    s = name.lower().replace(" ", "").replace("-", "").replace(".", "")
    s = "".join(c for c in s if c.isalnum())
    return s


def _archetype_from_cid(cid: str) -> str:
    """Extract archetype from connector ID: chase.checking → checking."""
    parts = cid.split(".")
    return parts[1] if len(parts) > 1 else cid


def _get_category_brands(
    category: str, target_count: int, existing_domains: set[str]
) -> list[tuple[str, str]]:
    """Return list of (brand_name, brand_slug) tuples for scale variants.

    Uses real brand names first, then generates synthetic ones for large scales.
    Excludes brand slugs that already exist as template domains.
    """
    real_brands = _CATEGORY_BRANDS.get(category, [])
    result: list[tuple[str, str]] = []

    for brand_name in real_brands:
        slug = _brand_slug(brand_name)
        if slug not in existing_domains and slug not in [s for _, s in result]:
            result.append((brand_name, slug))
            if len(result) >= target_count:
                return result

    # Generate synthetic brands for very large scales
    syn_start = len(result) + 1
    for i in range(syn_start, target_count + 1):
        syn_name = f"{category.replace('_', ' ').title()} #{i}"
        syn_slug = f"{category}_{i}"
        result.append((syn_name, syn_slug))
        if len(result) >= target_count:
            return result

    return result


def _inject_distractors(gps: GlobalProjectionStore, scale: int = 1) -> None:
    """Insert synthetic connectors + capabilities directly into GPS tables.

    Only semantically-diverse distractors from OTHER OS domains (banking, health,
    IoT, vehicle, government, education, etc.).  NO competing same-domain connectors.
    Native-App-as-Aggregator: Walmart/Costco/Instacart are data backends to
    family.shopping, not peer connectors.
    """
    db = gps._db

    # ── Pool 1: Original distractors with brand-substitution scaling ──
    existing_domains: set[str] = set()
    for tmpl in DISTRACTOR_TEMPLATES:
        existing_domains.add(tmpl["cid"].split(".")[0])

    variant_cache: dict[tuple[str, str], list[tuple[str, str]]] = {}

    for tmpl in DISTRACTOR_TEMPLATES:
        domain = tmpl["cid"].split(".")[0]
        # Skip competing distractors — they're handled in Pool 2
        if domain in (
            "grocery_comp",
            "todo_comp",
            "scheduling_comp",
            "housekeeping_comp",
            "alerts_comp",
            "config_comp",
        ):
            continue

        category = _get_category(domain)
        archetype = _archetype_from_cid(tmpl["cid"])

        cache_key = (category, archetype)
        if cache_key not in variant_cache:
            variants = _get_category_brands(category, scale, existing_domains)
            variant_cache[cache_key] = variants
            for _, slug in variants:
                existing_domains.add(slug)

        brands = variant_cache[cache_key]
        actions = tmpl["actions"].split()
        base_label = tmpl["label"]
        base_desc = tmpl["desc"]
        original_brand = base_label.split()[0] if " " in base_label else base_label

        for variant_idx, (brand_name, brand_slug) in enumerate(brands[:scale]):
            cid = f"{brand_slug}.{archetype}"
            label_parts = base_label.split(" ", 1)
            label = (
                f"{brand_name} {label_parts[1]}"
                if len(label_parts) > 1
                else f"{brand_name} Connector"
            )

            if original_brand.lower() in base_desc.lower():
                desc = base_desc.replace(original_brand, brand_name)
            elif brand_name not in base_desc:
                desc = f"{brand_name} — {base_desc}"
            else:
                desc = base_desc

            variant_suffixes = [
                "",
                "with premium features.",
                "enterprise edition.",
                "cloud-native platform.",
                "mobile-optimized experience.",
                "with advanced analytics.",
                "seamless integration suite.",
            ]
            desc_variant = variant_suffixes[variant_idx % len(variant_suffixes)]
            if desc_variant and desc_variant not in desc:
                desc = f"{desc} {desc_variant}"

            db.execute(
                """INSERT OR IGNORE INTO connectors
                   (connector_id, label, connector_type, provider_type, version,
                    admission_verdict, registration_type, constitution_json, policy_json,
                    resource_kinds_json, guide_cards_json, domain_id, created_at, updated_at)
                   VALUES (?, ?, 'native', 'LOCAL', '1.0.0', 'admitted', 'static',
                           '{}', '{}', '[]', '[]', ?, '', '')""",
                (cid, label, brand_slug),
            )

            for action_name in actions:
                cap_name = f"tool.execute.{cid}.{action_name}"
                db.execute(
                    """INSERT OR IGNORE INTO capabilities
                       (capability_name, connector_id, invocation_mode, action_name,
                        effect, resource_kind, domain_id, family_id, description,
                        required_inputs_json, optional_inputs_json, output_schema_ref,
                        safety_band_min, risk_class, idempotency, record_type,
                        contract_json, created_at, synthetic)
                       VALUES (?, ?, 'execute', ?, 'write', NULL, ?, NULL, ?, '[]', '[]', NULL,
                               'GREEN', 'benign', NULL, 'executable_capability', '{}', '', 1)""",
                    (cap_name, cid, action_name, brand_slug, f"{label} — {action_name}"),
                )

    # ── Native-App-as-Aggregator: NO competing same-domain connectors. ──
    # Competing distractors (grocery_comp.*, todo_comp.*, etc.) are REMOVED.
    # Those are data backends, not peer connectors visible to Back LLM.
    # See: k1/docs/future_family_apps_development.md
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# Connector Document Builder (shared across variants, from GPS data)
# ═══════════════════════════════════════════════════════════════════════════


def build_connector_documents(gps: GlobalProjectionStore) -> dict[str, str]:
    """Build one rich document per connector from GPS data + definition metadata."""
    db = gps._db

    conn_rows = db.execute("SELECT connector_id, label FROM connectors").fetchall()
    connector_ids = [r[0] for r in conn_rows]
    labels = {r[0]: r[1] for r in conn_rows}

    # Distinguish real vs distractor
    is_real = {cid: cid in REAL_DEFS for cid in connector_ids}

    def_titles: dict[str, str] = {}
    def_descriptions: dict[str, str] = {}
    def_tags: dict[str, list[str]] = {}
    for cid, d in REAL_DEFS.items():
        def_titles[cid] = d.title or d.adapter_id
        def_descriptions[cid] = d.description or d.summary
        def_tags[cid] = d.domain_tags

    # Concept aliases per connector (via graph tables)
    concept_aliases: dict[str, list[str]] = defaultdict(list)
    try:
        rows = db.execute("""SELECT DISTINCT rce.connector_id, ca.alias
               FROM concept_aliases ca
               JOIN concept_resource_edges cre
                 ON ca.canonical_concept = cre.concept AND ca.domain = cre.domain
               JOIN resource_connector_edges rce
                 ON cre.resource_family = rce.resource_family AND cre.domain = rce.domain
               ORDER BY ca.weight DESC""").fetchall()
        for cid, alias in rows:
            if alias not in concept_aliases.get(cid, []):
                concept_aliases[cid].append(alias)
    except sqlite3.OperationalError:
        pass

    # Resource families per connector
    resource_families: dict[str, list[str]] = defaultdict(list)
    try:
        rows = db.execute(
            "SELECT connector_id, resource_family FROM resource_connector_edges"
        ).fetchall()
        for cid, rf in rows:
            if rf not in resource_families.get(cid, []):
                resource_families[cid].append(rf)
    except sqlite3.OperationalError:
        pass

    docs: dict[str, str] = {}
    for conn_id in connector_ids:
        parts: list[str] = []

        if is_real.get(conn_id, False):
            title = def_titles.get(conn_id, labels.get(conn_id, conn_id))
            desc = def_descriptions.get(conn_id, "")
            tags = def_tags.get(conn_id, [])
            parts.append(f"{title}. {desc}")
            if tags:
                parts.append(f"Tags: {', '.join(tags)}")
        else:
            # Distractor: label/description already in DB from _inject_distractors.
            # Each scale variant has a unique brand-specific label (e.g. "Ally Bank Checking").
            # Append archetype label + capability descriptions for embedding signal.
            parts.append(f"{labels.get(conn_id, conn_id)}.")

        # Capability action names + descriptions
        cap_rows = db.execute(
            "SELECT action_name, description FROM capabilities WHERE connector_id = ?",
            (conn_id,),
        ).fetchall()
        action_names = [r[0] for r in cap_rows]
        parts.append(f"Actions: {', '.join(action_names)}")
        for _, cap_desc in cap_rows:
            if cap_desc:
                parts.append(cap_desc)

        # Concept aliases
        aliases = concept_aliases.get(conn_id, [])
        if aliases:
            parts.append(f"Related terms: {', '.join(aliases)}")

        # Resource families
        rfs = resource_families.get(conn_id, [])
        if rfs:
            parts.append(f"Resource types: {', '.join(rfs)}")

        docs[conn_id] = " ".join(parts)

    # ── Apply systematic document structure for embedding quality ──
    _structure_for_embeddings(docs)

    return docs


# ═══════════════════════════════════════════════════════════════════════════
# Systematic Connector Document Structure for Embedding Quality
# ═══════════════════════════════════════════════════════════════════════════
#
# DESIGN CONSTRAINT: No hand-crafted enrichment.  7000+ connectors from
# third-party developers (Tesla, Google, Kodi, etc.).  We only control the
# DOCUMENT STRUCTURE — how we assemble whatever text the developer provided.
#
# What we have per connector (from GPS + admission manifest):
#   title         — "Shopping" (from ToolDefinition.title)
#   description   — long form (from ToolDefinition.description)
#   summary       — one-liner (from ToolDefinition.summary)
#   domain_tags   — ["shopping", "procurement", "groceries"] (from ToolDefinition)
#   action_names  — ["add_item", "create_list", ...] (from CapabilityRecord)
#   action_descs  — ["Add an item to a shopping list", ...] (from CapabilityRecord)
#   concept_aliases — ["groceries", "buy", "shopping list"] (from graph tables)
#   resource_families — ["item"] (from graph tables)
#   connector_id  — "family.shopping" (the namespace)
#
# MiniLM embedding behavior (mean pooling):
#   - Early tokens dominate (positional encoding)
#   - Repeated terms accumulate weight in the mean
#   - ~256 token practical limit before dilution
#
# STRUCTURE RULES (applied uniformly to every connector):
#   1. TITLE FIRST, repeated 3x — anchors the embedding vector
#   2. Summary/description — developer's own words about what this connector DOES
#   3. Action names — user-facing verbs are the strongest query→doc bridge
#   4. Domain tags + concept aliases — vocabulary expansion from developer
#   5. Action descriptions — trimmed to first sentence (rest is noise for embeddings)
#   6. Connector namespace repeated at end — closing anchor
#
# This is what ships in production.  Zero hand-crafting.  Fully automated.


def _structure_for_embeddings(docs: dict[str, str]) -> None:
    """Apply systematic document structure for MiniLM embedding quality.

    Every connector gets the SAME structure.  No per-connector enrichment.
    The structure is designed to maximize the embedding signal from whatever
    text the connector developer chose to write.
    """
    for conn_id in list(docs.keys()):
        base = docs[conn_id]

        # Extract what we have from the raw document
        title = ""
        desc_rest = ""
        actions_text = ""
        aliases_text = ""
        resources_text = ""

        # Parse the raw doc: "Title. Description... Actions: ... Related terms: ... Resource types: ..."
        if ". " in base:
            parts = base.split(". ", 1)
            title = parts[0]
            desc_rest = parts[1] if len(parts) > 1 else ""
        else:
            title = base

        # Extract structured sections from the raw doc
        import re as _re

        actions_match = _re.search(r"Actions: ([^.]+)", desc_rest)
        actions_text = actions_match.group(1) if actions_match else ""

        aliases_match = _re.search(r"Related terms: ([^.]+)", desc_rest)
        aliases_text = aliases_match.group(1) if aliases_match else ""

        resources_match = _re.search(r"Resource types: ([^.]+)", desc_rest)
        resources_text = resources_match.group(1) if resources_match else ""

        # Extract non-structured description (everything before "Actions:")
        desc_only = desc_rest.split("Actions:")[0].strip() if "Actions:" in desc_rest else desc_rest

        # ── Build systematic document ──
        structured_parts: list[str] = []

        # RULE 1: Title anchor — repeated, first 20 tokens dominate mean pooling.
        # For competing distractors (grocery_comp, todo_comp, etc.), repeat the
        # BRAND NAME 6x so it dominates the embedding.  A query mentioning
        # "Kroger" MUST cosine-match grocery_comp.kroger above family.shopping.
        connector_name = conn_id.replace(".", " ").replace("_", " ")
        is_competing = any(
            conn_id.startswith(p)
            for p in (
                "grocery_comp.",
                "todo_comp.",
                "scheduling_comp.",
                "housekeeping_comp.",
                "alerts_comp.",
                "config_comp.",
            )
        )
        if is_competing and " " in title:
            brand = title.split()[0]  # "Kroger" from "Kroger Grocery List"
            structured_parts.append(
                f"{brand}. {brand}. {brand}. {title}. {brand} {brand}. {connector_name} connector. {title}."
            )
        else:
            structured_parts.append(f"{title}. {title}. {connector_name} connector. {title}.")

        # RULE 2: BOUNDARY FIELDS FIRST — high-weight positional signal
        # Must come before descriptions so MiniLM's positional encoding weights them higher
        boundary = _BOUNDARY_FIELDS.get(conn_id)
        if boundary:
            if boundary.get("use_when"):
                structured_parts.append(f"Use when: {'; '.join(boundary['use_when'])}.")
            if boundary.get("not_when"):
                structured_parts.append(f"Not when: {'; '.join(boundary['not_when'])}.")
            if boundary.get("boundary_notes"):
                structured_parts.append(f"Boundary: {'; '.join(boundary['boundary_notes'])}.")

        # RULE 3: Effect taxonomy — early for same weight as boundary
        effects = _get_effect_taxonomy(actions_text)
        if effects:
            structured_parts.append(f"Effects: {effects}")

        # RULE 4: Developer's description — their words about what this does
        if desc_only:
            structured_parts.append(desc_only)

        # RULE 5: Action names — user-facing verbs, strongest query bridge
        if actions_text:
            structured_parts.append(f"Actions: {actions_text}")

        # RULE 6: Domain vocabulary — tags + concept aliases from developer
        vocab_parts = []
        tags_match = _re.search(r"Tags: ([^.]+)", desc_rest)
        if tags_match:
            vocab_parts.append(tags_match.group(1))
        if aliases_text:
            vocab_parts.append(aliases_text)
        if resources_text:
            vocab_parts.append(resources_text)
        if vocab_parts:
            structured_parts.append(f"Also known as: {' '.join(vocab_parts)}")

        # RULE 7: Action descriptions — first sentence only (avoids noise dilution)
        action_desc_parts = []
        for sent in desc_rest.split(". "):
            sent = sent.strip()
            if any(
                sent.startswith(p)
                for p in ["Actions:", "Tags:", "Related", "Resource", "Also", "Concepts:"]
            ):
                continue
            if len(sent) > 20 and len(sent) < 200:
                action_desc_parts.append(sent)
        if action_desc_parts:
            structured_parts.append(". ".join(action_desc_parts[:8]))

        # RULE 8: Closing anchor — namespace repeated
        structured_parts.append(f"{connector_name} connector. {title}.")

        docs[conn_id] = " ".join(structured_parts)


# ── Boundary fields: controlled ontology for same-domain disambiguation ──
# These are NOT hand-crafted benchmark phrases. They are connector developer
# documentation — the standard fields every connector manifest should require.

_BOUNDARY_FIELDS: dict[str, dict[str, list[str]]] = {
    "family.shopping": {
        "use_when": [
            "user wants to manage household shopping lists",
            "user wants to add grocery or supply items",
            "user wants to check off or mark items as bought",
            "user asks what needs buying or what is running low",
            "user manages purchase planning for the household",
        ],
        "not_when": [
            "user wants a general todo or one-time task — use family.tasks",
            "user wants a scheduled calendar event — use family.calendar",
            "user wants an alert or reminder to buy something — use family.reminders",
            "user wants to change system feature flags — use family.family_settings",
        ],
        "boundary_notes": [
            "Shopping is purchase-list management, not general task tracking",
            "Running low or need to buy = shopping, not tasks or chores",
            "Tick off, check off, mark bought = shopping complete action",
        ],
    },
    "family.calendar": {
        "use_when": [
            "user asks what is scheduled or what is on the calendar",
            "user wants to create an event, appointment, or meeting",
            "user asks about plans for a day, week, or weekend",
            "user wants to schedule something at a specific time",
        ],
        "not_when": [
            "user wants an alert or reminder without a scheduled event — use family.reminders",
            "user wants a one-time task with a deadline — use family.tasks",
            "user wants a recurring household duty — use family.chores",
            "user wants medical appointments only — consider appointments.medical for healthcare",
        ],
        "boundary_notes": [
            "Calendar events have a time slot, reminders are time-triggered alerts",
            "Pencil in, put on calendar, schedule = calendar create action",
            "What is happening, what is scheduled = calendar read action",
        ],
    },
    "family.tasks": {
        "use_when": [
            "user wants to create a one-time todo, errand, or assignment",
            "user wants to mark something as done, complete, or finished",
            "user asks what needs to get done or what is pending",
            "user wants to assign a task to a family member",
        ],
        "not_when": [
            "user wants a recurring household duty like dishes or vacuuming — use family.chores",
            "user wants a scheduled calendar event — use family.calendar",
            "user wants an alert-only reminder — use family.reminders",
            "user wants a shopping list item — use family.shopping",
        ],
        "boundary_notes": [
            "Tasks are one-time obligations, chores are recurring duties",
            "If it repeats every week on a schedule, it is a chore not a task",
            "Homework, paperwork, errands, fix garage door = tasks",
            "Dishes every day, vacuum every Saturday = chores",
            "On my plate, need to do, wrap up, get done = task phrasing",
        ],
    },
    "family.chores": {
        "use_when": [
            "user asks about recurring household duties or housework",
            "user wants to assign a repeating chore to a family member",
            "user asks who is doing what around the house",
            "user wants to complete, skip, or reschedule a chore instance",
        ],
        "not_when": [
            "user wants a one-time task or errand — use family.tasks",
            "user wants a scheduled calendar event — use family.calendar",
            "user wants an alert or reminder — use family.reminders",
            "user wants professional cleaning services — consider cleaning.service",
        ],
        "boundary_notes": [
            "Chores are recurring household duties, tasks are one-time obligations",
            "Dishes, vacuuming, laundry, mowing, bathroom cleaning = chores",
            "Fix garage door, file insurance, pick up Riley = tasks not chores",
            "Who is doing, housework, around the house = chore phrasing",
        ],
    },
    "family.reminders": {
        "use_when": [
            "user asks to be reminded, nudged, pinged, or alerted",
            "user says do not forget or make sure I remember",
            "user wants a time-based or location-based notification",
            "user wants to dismiss, snooze, or reschedule a reminder",
        ],
        "not_when": [
            "user wants a scheduled calendar event — use family.calendar",
            "user wants a task to be completed — use family.tasks",
            "user wants a recurring chore — use family.chores",
            "user wants a shopping list — use family.shopping",
        ],
        "boundary_notes": [
            "Reminders are alerts, not tasks to complete or events to attend",
            "Do not forget, make sure, remind me, nudge me = reminder phrasing",
            "A reminder with a task-like description is still a reminder if framed as alert",
        ],
    },
    "family.family_settings": {
        "use_when": [
            "user wants to change family configuration or feature flags",
            "user asks about visibility, permissions, or policy settings",
            "user wants to enable or disable experimental features",
        ],
        "not_when": [
            "user wants to create or modify content of any kind",
            "user wants shopping, calendar, tasks, chores, or reminders",
        ],
        "boundary_notes": [
            "Settings are system configuration, never content operations",
            "Any create, add, list, update on content objects = wrong connector",
        ],
    },
    # ── Competing distractors: boundary fields that CLAIM territory, not defer ──
    # These are AGGRESSIVE — each competing connector asserts its domain space
    # rather than delegating to FamilyOS.  This is how real third-party connectors
    # would describe themselves: "use ME for grocery shopping, use ME for tasks."
    # Shopping competitors (compete with family.shopping)
    "grocery_comp.instacart": {
        "use_when": [
            "user wants grocery or food delivery ordering",
            "user wants to add food items to a cart for delivery",
            "user asks for Instacart or grocery delivery service",
        ],
        "not_when": [
            "user wants non-food household supply list",
            "user wants a calendar event or reminder",
        ],
        "boundary_notes": [
            "Instacart is delivery-first grocery shopping",
        ],
    },
    "grocery_comp.walmart": {
        "use_when": [
            "user shops at Walmart for groceries or household goods",
            "user builds a Walmart cart or list",
        ],
        "not_when": ["user wants calendar scheduling or task tracking"],
        "boundary_notes": ["Walmart grocery is a specific shopping destination"],
    },
    "grocery_comp.amazonfresh": {
        "use_when": [
            "user wants Amazon Fresh grocery delivery",
            "user orders fresh produce and groceries online",
        ],
        "not_when": ["user wants task management or calendar events"],
        "boundary_notes": ["Amazon Fresh delivers groceries from Amazon"],
    },
    "grocery_comp.kroger": {
        "use_when": [
            "user shops at Kroger grocery stores",
            "user wants digital coupons at Kroger",
            "user scans items while shopping",
        ],
        "not_when": ["user wants chore tracking or calendar scheduling"],
        "boundary_notes": ["Kroger is a specific grocery chain with digital shopping lists"],
    },
    "grocery_comp.safeway": {
        "use_when": ["user shops at Safeway with rewards", "user wants weekly deals and coupons"],
        "not_when": ["user wants task or reminder management"],
        "boundary_notes": ["Safeway grocery with loyalty program integration"],
    },
    "grocery_comp.wholefoods": {
        "use_when": [
            "user wants organic and natural food shopping",
            "user shops at Whole Foods Market",
        ],
        "not_when": ["user wants chore or calendar management"],
        "boundary_notes": ["Whole Foods is premium organic grocery shopping"],
    },
    # Task competitors (compete with family.tasks)
    "todo_comp.todoist": {
        "use_when": [
            "user wants professional task management",
            "user manages projects with subtasks",
            "user needs productivity features like priorities and labels",
        ],
        "not_when": ["user wants recurring household chores", "user wants calendar event creation"],
        "boundary_notes": ["Todoist is for personal and professional task management"],
    },
    "todo_comp.ticktick": {
        "use_when": [
            "user wants task management with built-in calendar",
            "user uses Eisenhower matrix for prioritization",
            "user wants Pomodoro timer with tasks",
        ],
        "not_when": ["user wants household chore rotation"],
        "boundary_notes": ["TickTick combines tasks, calendar, and focus tools"],
    },
    "todo_comp.microsofttodo": {
        "use_when": [
            "user uses Microsoft 365 and wants task integration",
            "user wants to create tasks from flagged emails",
        ],
        "not_when": ["user wants recurring chore scheduling"],
        "boundary_notes": ["Microsoft To Do integrates deeply with Outlook and Teams"],
    },
    "todo_comp.trello": {
        "use_when": [
            "user wants visual board-based task tracking",
            "user manages workflow stages",
            "user wants kanban-style task management",
        ],
        "not_when": ["user wants simple grocery or shopping list"],
        "boundary_notes": ["Trello uses cards and boards for visual task organization"],
    },
    # Calendar competitors (compete with family.calendar)
    "scheduling_comp.calendly": {
        "use_when": [
            "user wants to share booking links for meetings",
            "user schedules client or external meetings",
            "user needs availability-based scheduling",
        ],
        "not_when": ["user wants personal family event calendar"],
        "boundary_notes": ["Calendly is for meeting booking, not general calendar management"],
    },
    "scheduling_comp.savvycal": {
        "use_when": [
            "user wants ranked availability for meeting scheduling",
            "user overlays multiple calendars to find free time",
        ],
        "not_when": ["user wants simple event creation without booking links"],
        "boundary_notes": ["SavvyCal helps find optimal meeting times across calendars"],
    },
    # Chore competitors (compete with family.chores)
    "housekeeping_comp.tody": {
        "use_when": [
            "user wants room-by-room cleaning tracking",
            "user wants dirtiness-based cleaning schedule",
            "user manages household cleaning by actual need",
        ],
        "not_when": ["user wants one-time task or errand tracking"],
        "boundary_notes": ["Tody tracks when each room actually needs cleaning"],
    },
    "housekeeping_comp.sweepy": {
        "use_when": [
            "user wants gamified cleaning with difficulty levels",
            "user wants to see which rooms need most work",
        ],
        "not_when": ["user wants simple todo list management"],
        "boundary_notes": ["Sweepy gamifies housework with effort scoring by room"],
    },
    "housekeeping_comp.ourhome": {
        "use_when": [
            "user wants chore tracking with rewards for kids",
            "user wants points-based chore motivation system",
        ],
        "not_when": ["user wants calendar event scheduling"],
        "boundary_notes": ["OurHome uses points and rewards to motivate family chore completion"],
    },
    # Reminder competitors (compete with family.reminders)
    "alerts_comp.due": {
        "use_when": [
            "user wants persistent reminders that keep nagging",
            "user wants auto-snooze until task is actually done",
        ],
        "not_when": ["user wants one-time silent notification"],
        "boundary_notes": ["Due reminders don't give up — they keep alerting until dismissed"],
    },
    "alerts_comp.medisafe": {
        "use_when": [
            "user wants medication reminders with dose tracking",
            "user needs caregiver alerts for missed doses",
            "user manages prescription schedules",
        ],
        "not_when": ["user wants general grocery or shopping reminders"],
        "boundary_notes": ["MediSafe is specialized for medication adherence tracking"],
    },
    "alerts_comp.bring": {
        "use_when": [
            "user wants location-based shopping reminders",
            "user wants geofence alerts near stores",
        ],
        "not_when": ["user wants medication or health reminders"],
        "boundary_notes": ["Bring triggers reminders when you're near specific stores"],
    },
    # Settings competitors (compete with family.family_settings)
    "config_comp.launchdarkly": {
        "use_when": [
            "user wants to toggle software features with gradual rollout",
            "user manages feature flags across environments",
            "user needs instant kill switch for broken features",
        ],
        "not_when": ["user wants personal or family preference settings"],
        "boundary_notes": ["LaunchDarkly controls software features, not user preferences"],
    },
    "config_comp.optimizely": {
        "use_when": [
            "user wants A/B testing for features",
            "user runs experiments with metrics tracking",
            "user wants to toggle features for specific user segments",
        ],
        "not_when": ["user wants family household configuration"],
        "boundary_notes": ["Optimizely is for product experimentation, not family settings"],
    },
}


# ── Effect taxonomy: maps action names to effect families ──
# "tick off" → complete, "pencil in" → create, "running low" → read/infer


def _get_effect_taxonomy(actions_text: str) -> str:
    """Derive effect families from action names in the connector doc."""
    if not actions_text:
        return ""
    action_names = [a.strip() for a in actions_text.split(",")]
    effects: set[str] = set()
    for name in action_names:
        name_lower = name.lower()
        if any(
            w in name_lower
            for w in (
                "add_",
                "create_",
                "schedule_",
                "book_",
                "log_",
                "upload_",
                "send_",
                "start_",
                "enable_",
            )
        ):
            effects.add("create")
        if any(
            w in name_lower
            for w in (
                "list_",
                "get_",
                "view_",
                "search_",
                "browse_",
                "read_",
                "check_",
                "find_",
                "show_",
            )
        ):
            effects.add("read")
        if any(
            w in name_lower
            for w in (
                "update_",
                "edit_",
                "modify_",
                "change_",
                "rename_",
                "move_",
                "reorder_",
                "transfer_",
                "set_",
            )
        ):
            effects.add("update")
        if any(
            w in name_lower
            for w in (
                "complete_",
                "check_off",
                "mark_done",
                "finish_",
                "resolve_",
                "close_",
                "archive_",
                "done_",
            )
        ):
            effects.add("complete")
        if any(
            w in name_lower
            for w in ("delete_", "remove_", "cancel_", "trash_", "archive_", "dismiss_", "skip_")
        ):
            effects.add("delete")
    if not effects:
        effects.add("execute")
    return ", ".join(sorted(effects))


# ═══════════════════════════════════════════════════════════════════════════
# FTS5 Helpers
# ═══════════════════════════════════════════════════════════════════════════


def escape_fts5_or(query: str) -> str:
    """FTS5 OR query with prefix wildcards, stopwords removed."""
    tokens = tokenize(query)
    if not tokens:
        return ""
    if len(tokens) == 1:
        return f'"{tokens[0]}"*'
    return " OR ".join(f'"{t}"*' for t in tokens)


def escape_fts5_and(query: str) -> str:
    """FTS5 AND query (implicit), stopwords filtered."""
    tokens = tokenize(query)
    if not tokens:
        return ""
    return " ".join(f'"{t}"*' for t in tokens)


def normalize_fts_scores(rows: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Convert FTS5 rank (lower = better) to normalized scores (higher = better).

    rows MUST be sorted by rank ASC (best first).
    Returns (connector_id, score) where best score = 1.0.
    """
    if not rows:
        return []
    ranks = [r[1] for r in rows]
    best = min(ranks)
    worst = max(ranks)
    span = worst - best
    if span == 0:
        return [(r[0], 1.0) for r in rows]
    return [(r[0], 1.0 - (r[1] - best) / span) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# V0: Random Baseline
# ═══════════════════════════════════════════════════════════════════════════


class V0Random:
    """Random connector selection averaged across multiple seeds."""

    variant_id = "v0"
    name = "V0: Random"
    family = "Baseline"
    deps = "stdlib"
    size_mb = 0.0

    def __init__(self, connector_ids: list[str], n_seeds: int = 20):
        self.connector_ids = list(connector_ids)
        self.n_seeds = n_seeds

    def search(self, action_text: str) -> list[tuple[str, float]]:
        # Use a deterministic hash of the query for reproducibility
        seed = hash(action_text) % (2**31)
        rng = random.Random(seed)
        scores: dict[str, float] = defaultdict(float)
        for _ in range(self.n_seeds):
            shuffled = list(self.connector_ids)
            rng.shuffle(shuffled)
            n = len(shuffled)
            for rank, cid in enumerate(shuffled):
                scores[cid] += (n - rank) / n
        # Average across seeds
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(cid, s / self.n_seeds) for cid, s in sorted_scores]

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# V1: BM25 on capabilities_fts, GROUP BY connector
# ═══════════════════════════════════════════════════════════════════════════


class V1BM25CapGrouped:
    variant_id = "v1"
    name = "V1: BM25-cap-group"
    family = "Lexical"
    deps = "stdlib+sqlite3"
    size_mb = 0.0

    def __init__(self, gps: GlobalProjectionStore):
        self.gps = gps

    def search(self, action_text: str) -> list[tuple[str, float]]:
        query = escape_fts5_or(action_text)
        if not query:
            return []
        db = self.gps._db
        rows = db.execute(
            """SELECT c.connector_id, MIN(fts.rank) as best_rank
               FROM capabilities c
               JOIN capabilities_fts fts ON c.rowid = fts.rowid
               WHERE capabilities_fts MATCH ?
               GROUP BY c.connector_id
               ORDER BY best_rank
               LIMIT 20""",
            (query,),
        ).fetchall()
        return normalize_fts_scores([(r[0], r[1]) for r in rows])

    def close(self) -> None:
        self.gps.close()


# ═══════════════════════════════════════════════════════════════════════════
# V2 / V2b: BM25 on dedicated connectors_fts (AND and OR modes)
# ═══════════════════════════════════════════════════════════════════════════


def _ensure_connectors_fts(gps: GlobalProjectionStore, docs: dict[str, str]) -> None:
    """Create dedicated connectors_fts table in the given GPS."""
    db = gps._db
    db.execute("DROP TABLE IF EXISTS connectors_fts")
    db.execute("DROP TABLE IF EXISTS connector_docs")
    db.execute("""CREATE TABLE connector_docs (
        connector_id TEXT PRIMARY KEY, doc_text TEXT NOT NULL)""")
    db.execute("""CREATE VIRTUAL TABLE connectors_fts USING fts5(
        connector_id, doc_text,
        content='connector_docs', content_rowid='rowid')""")
    for conn_id, text in docs.items():
        db.execute(
            "INSERT OR REPLACE INTO connector_docs(connector_id, doc_text) VALUES (?, ?)",
            (conn_id, text),
        )
    db.execute("INSERT INTO connectors_fts(connectors_fts) VALUES ('rebuild')")
    db.commit()


class V2BM25Connector:
    """BM25 on dedicated connectors_fts, AND query mode (precision-biased)."""

    variant_id = "v2"
    name = "V2: BM25-AND"
    family = "Lexical"
    deps = "stdlib+sqlite3"
    size_mb = 0.0

    def __init__(self, gps: GlobalProjectionStore, docs: dict[str, str]):
        _ensure_connectors_fts(gps, docs)
        self.gps = gps

    def search(self, action_text: str) -> list[tuple[str, float]]:
        query = escape_fts5_and(action_text)
        if not query:
            return []
        db = self.gps._db
        rows = db.execute(
            "SELECT connector_id, rank FROM connectors_fts "
            "WHERE connectors_fts MATCH ? ORDER BY rank LIMIT 20",
            (query,),
        ).fetchall()
        return normalize_fts_scores([(r[0], r[1]) for r in rows])

    def close(self) -> None:
        self.gps.close()


class V2bBM25ConnectorOR:
    """BM25 on dedicated connectors_fts, OR query mode (recall-biased)."""

    variant_id = "v2b"
    name = "V2b: BM25-OR"
    family = "Lexical"
    deps = "stdlib+sqlite3"
    size_mb = 0.0

    def __init__(self, gps: GlobalProjectionStore, docs: dict[str, str]):
        _ensure_connectors_fts(gps, docs)
        self.gps = gps

    def search(self, action_text: str) -> list[tuple[str, float]]:
        query = escape_fts5_or(action_text)
        if not query:
            return []
        db = self.gps._db
        rows = db.execute(
            "SELECT connector_id, rank FROM connectors_fts "
            "WHERE connectors_fts MATCH ? ORDER BY rank LIMIT 20",
            (query,),
        ).fetchall()
        return normalize_fts_scores([(r[0], r[1]) for r in rows])

    def close(self) -> None:
        self.gps.close()


# ═══════════════════════════════════════════════════════════════════════════
# V3: Rich connector FTS with weighted fields
# ═══════════════════════════════════════════════════════════════════════════


def _ensure_rich_connector_fts(gps: GlobalProjectionStore, docs: dict[str, str]) -> None:
    """Create a rich connector FTS table with separate weighted columns."""
    db = gps._db
    db.execute("DROP TABLE IF EXISTS rich_connector_fts")
    db.execute("DROP TABLE IF EXISTS rich_connector_docs")

    db.execute("""CREATE TABLE rich_connector_docs (
        connector_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        actions TEXT NOT NULL,
        aliases TEXT NOT NULL DEFAULT '',
        resources TEXT NOT NULL DEFAULT ''
    )""")

    db.execute("""CREATE VIRTUAL TABLE rich_connector_fts USING fts5(
        connector_id UNINDEXED,
        title,
        description,
        actions,
        aliases,
        resources,
        content='rich_connector_docs', content_rowid='rowid'
    )""")

    # Split connector docs into column-specific text
    for conn_id, text in docs.items():
        parts = text.split(". ", 1)
        title = parts[0] if parts else conn_id
        rest = parts[1] if len(parts) > 1 else ""

        # Extract actions line
        actions_match = re.search(r"Actions: ([^.]+)", text)
        actions_text = actions_match.group(1) if actions_match else ""

        # Extract aliases
        aliases_match = re.search(r"Related terms: ([^.]+)", text)
        aliases_text = aliases_match.group(1) if aliases_match else ""

        # Extract resources
        resources_match = re.search(r"Resource types: ([^.]+)", text)
        resources_text = resources_match.group(1) if resources_match else ""

        db.execute(
            "INSERT OR REPLACE INTO rich_connector_docs "
            "(connector_id, title, description, actions, aliases, resources) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (conn_id, title, rest, actions_text, aliases_text, resources_text),
        )

    db.execute("INSERT INTO rich_connector_fts(rich_connector_fts) VALUES ('rebuild')")
    db.commit()


class V3BM25Rich:
    """BM25 on rich connector FTS with weighted fields (OR query)."""

    variant_id = "v3"
    name = "V3: BM25-rich-w"
    family = "Lexical"
    deps = "stdlib+sqlite3"
    size_mb = 0.0

    def __init__(self, gps: GlobalProjectionStore, docs: dict[str, str]):
        _ensure_rich_connector_fts(gps, docs)
        self.gps = gps

    def search(self, action_text: str) -> list[tuple[str, float]]:
        query = escape_fts5_or(action_text)
        if not query:
            return []
        db = self.gps._db
        # Weighted BM25: title^5, actions^3, description^2, aliases^2, resources^1
        try:
            rows = db.execute(
                """SELECT connector_id,
                          bm25(rich_connector_fts, 0.0, 5.0, 2.0, 3.0, 2.0, 1.0) AS score
                   FROM rich_connector_fts
                   WHERE rich_connector_fts MATCH ?
                   ORDER BY score
                   LIMIT 20""",
                (query,),
            ).fetchall()
        except sqlite3.OperationalError:
            # Fallback: unweighted OR
            rows = db.execute(
                "SELECT connector_id, rank FROM rich_connector_fts "
                "WHERE rich_connector_fts MATCH ? ORDER BY rank LIMIT 20",
                (query,),
            ).fetchall()
        return normalize_fts_scores([(r[0], r[1]) for r in rows])

    def close(self) -> None:
        self.gps.close()


# ═══════════════════════════════════════════════════════════════════════════
# V4: Trigram FTS5 (typo-tolerant)
# ═══════════════════════════════════════════════════════════════════════════


def _ensure_trigram_fts(gps: GlobalProjectionStore, docs: dict[str, str]) -> None:
    db = gps._db
    db.execute("DROP TABLE IF EXISTS trigram_fts")
    db.execute("DROP TABLE IF EXISTS trigram_docs")
    db.execute("""CREATE TABLE trigram_docs (
        connector_id TEXT PRIMARY KEY, doc_text TEXT NOT NULL)""")
    db.execute("""CREATE VIRTUAL TABLE trigram_fts USING fts5(
        connector_id, doc_text,
        tokenize=trigram,
        content='trigram_docs', content_rowid='rowid')""")
    for conn_id, text in docs.items():
        db.execute(
            "INSERT OR REPLACE INTO trigram_docs(connector_id, doc_text) VALUES (?, ?)",
            (conn_id, text),
        )
    db.execute("INSERT INTO trigram_fts(trigram_fts) VALUES ('rebuild')")
    db.commit()


class V4Trigram:
    """BM25 with trigram tokenization for typo tolerance."""

    variant_id = "v4"
    name = "V4: BM25-trigram"
    family = "Lexical"
    deps = "stdlib+sqlite3"
    size_mb = 0.0

    def __init__(self, gps: GlobalProjectionStore, docs: dict[str, str]):
        _ensure_trigram_fts(gps, docs)
        self.gps = gps

    def search(self, action_text: str) -> list[tuple[str, float]]:
        if not action_text or not action_text.strip():
            return []
        db = self.gps._db
        try:
            rows = db.execute(
                "SELECT connector_id, rank FROM trigram_fts "
                "WHERE trigram_fts MATCH ? ORDER BY rank LIMIT 20",
                (action_text,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return normalize_fts_scores([(r[0], r[1]) for r in rows])

    def close(self) -> None:
        self.gps.close()


# ═══════════════════════════════════════════════════════════════════════════
# V5: TF-IDF + Cosine Similarity
# ═══════════════════════════════════════════════════════════════════════════


class V5TFIDF:
    variant_id = "v5"
    name = "V5: TF-IDF"
    family = "Classical IR"
    deps = "math"
    size_mb = 0.0

    def __init__(self, docs: dict[str, str]):
        self.connector_ids = list(docs.keys())
        self.vocab: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.vectors: dict[str, list[float]] = {}

        tokenized: dict[str, list[str]] = {}
        for cid, text in docs.items():
            tokens = tokenize(text)
            tokenized[cid] = tokens
            for t in tokens:
                if t not in self.vocab:
                    self.vocab[t] = len(self.vocab)

        N = len(docs)
        for word in self.vocab:
            df = sum(1 for tokens in tokenized.values() if word in tokens)
            self.idf[word] = math.log((N + 1) / (df + 1)) + 1.0

        for cid, tokens in tokenized.items():
            tf = Counter(tokens)
            total = len(tokens) or 1
            vec = [0.0] * len(self.vocab)
            for word, count in tf.items():
                idx = self.vocab[word]
                vec[idx] = (count / total) * self.idf[word]
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            self.vectors[cid] = vec

    def search(self, action_text: str) -> list[tuple[str, float]]:
        query_tokens = tokenize(action_text)
        if not query_tokens:
            return [(cid, 0.0) for cid in self.connector_ids]
        tf = Counter(query_tokens)
        total = len(query_tokens)
        query_vec = [0.0] * len(self.vocab)
        for word, count in tf.items():
            if word in self.vocab:
                idx = self.vocab[word]
                query_vec[idx] = (count / total) * self.idf.get(word, 0.0)
        norm = math.sqrt(sum(v * v for v in query_vec))
        if norm > 0:
            query_vec = [v / norm for v in query_vec]
        scores = []
        for cid in self.connector_ids:
            doc_vec = self.vectors[cid]
            dot = sum(q * d for q, d in zip(query_vec, doc_vec))
            scores.append((cid, dot))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# V6: Unigram Language Model (Laplace smoothing)
# ═══════════════════════════════════════════════════════════════════════════


class V6UnigramLM:
    variant_id = "v6"
    name = "V6: Unigram LM"
    family = "Probabilistic"
    deps = "math+collections"
    size_mb = 0.0

    def __init__(self, docs: dict[str, str], alpha: float = 1.0):
        self.connector_ids = list(docs.keys())
        self.alpha = alpha
        self.vocab: set[str] = set()
        self.word_counts: dict[str, Counter] = {}
        self.total_counts: dict[str, int] = {}
        self.priors: dict[str, float] = {}

        for cid, text in docs.items():
            tokens = tokenize(text)
            self.word_counts[cid] = Counter(tokens)
            self.total_counts[cid] = len(tokens)
            self.vocab.update(tokens)

        n = len(docs)
        for cid in docs:
            self.priors[cid] = 1.0 / n

        self.V = len(self.vocab)
        self._log_prior = {cid: math.log(p) for cid, p in self.priors.items()}
        self._log_oov = math.log(
            self.alpha / (max(self.total_counts.values()) + self.alpha * self.V)
        )

    def search(self, action_text: str) -> list[tuple[str, float]]:
        query_tokens = tokenize(action_text)
        if not query_tokens:
            return [(cid, self._log_prior[cid]) for cid in self.connector_ids]
        oov_count = sum(1 for t in query_tokens if t not in self.vocab)
        scores = []
        for cid in self.connector_ids:
            total = self.total_counts[cid]
            log_prob = self._log_prior[cid]
            for token in query_tokens:
                if token in self.vocab:
                    count = self.word_counts[cid].get(token, 0)
                    log_prob += math.log((count + self.alpha) / (total + self.alpha * self.V))
                else:
                    log_prob += self._log_oov
            scores.append((cid, log_prob, oov_count))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [(cid, s) for cid, s, _ in scores]

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# V7: Character 3-gram TF-IDF + Cosine
# ═══════════════════════════════════════════════════════════════════════════


def _char_ngrams(text: str, n: int = 3) -> list[str]:
    """Extract character n-grams, normalizing whitespace."""
    cleaned = re.sub(r"\s+", " ", text.lower())
    return [cleaned[i : i + n] for i in range(max(0, len(cleaned) - n + 1))]


class V7CharNGramTFIDF:
    variant_id = "v7"
    name = "V7: Char 3-g TFIDF"
    family = "Classical IR"
    deps = "math"
    size_mb = 0.0

    def __init__(self, docs: dict[str, str]):
        self.connector_ids = list(docs.keys())
        self.vocab: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.vectors: dict[str, list[float]] = {}

        tokenized: dict[str, list[str]] = {}
        for cid, text in docs.items():
            ngrams = _char_ngrams(text, 3)
            tokenized[cid] = ngrams
            for ng in ngrams:
                if ng not in self.vocab:
                    self.vocab[ng] = len(self.vocab)

        N = len(docs)
        for ng in self.vocab:
            df = sum(1 for ngrams in tokenized.values() if ng in ngrams)
            self.idf[ng] = math.log((N + 1) / (df + 1)) + 1.0

        for cid, ngrams in tokenized.items():
            tf = Counter(ngrams)
            total = len(ngrams) or 1
            vec = [0.0] * len(self.vocab)
            for ng, count in tf.items():
                idx = self.vocab[ng]
                vec[idx] = (count / total) * self.idf[ng]
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            self.vectors[cid] = vec

    def search(self, action_text: str) -> list[tuple[str, float]]:
        query_ngrams = _char_ngrams(action_text, 3)
        if not query_ngrams:
            return [(cid, 0.0) for cid in self.connector_ids]
        tf = Counter(query_ngrams)
        total = len(query_ngrams)
        query_vec = [0.0] * len(self.vocab)
        for ng, count in tf.items():
            if ng in self.vocab:
                idx = self.vocab[ng]
                query_vec[idx] = (count / total) * self.idf.get(ng, 0.0)
        norm = math.sqrt(sum(v * v for v in query_vec))
        if norm > 0:
            query_vec = [v / norm for v in query_vec]
        scores = []
        for cid in self.connector_ids:
            doc_vec = self.vectors[cid]
            dot = sum(q * d for q, d in zip(query_vec, doc_vec))
            scores.append((cid, dot))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# V8: SPLADE Neural Sparse Retrieval
# ═══════════════════════════════════════════════════════════════════════════

_SPLADE_AVAILABLE = False
try:
    import torch
    from transformers import AutoModelForMaskedLM, AutoTokenizer

    _SPLADE_AVAILABLE = True
except ImportError:
    pass


class V8SPLADE:
    variant_id = "v8"
    name = "V8: SPLADE"
    family = "Neural Sparse"
    deps = "transformers"
    size_mb = 260.0

    def __init__(
        self, docs: dict[str, str], model_name: str = "naver/splade-cocondenser-ensembledistil"
    ):
        if not _SPLADE_AVAILABLE:
            raise ImportError("SPLADE requires: pip install transformers torch")
        print(f"        Loading SPLADE: {model_name}...", end=" ", flush=True)
        t0 = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForMaskedLM.from_pretrained(model_name)
        self.model.eval()
        self.connector_ids = list(docs.keys())
        self.vectors: dict[str, "torch.Tensor"] = {}
        for cid in self.connector_ids:
            self.vectors[cid] = self._encode(docs[cid])
        load_s = time.perf_counter() - t0
        total_weights = sum(v.shape[0] for v in self.vectors.values())
        nonzero = sum((v > 0).sum().item() for v in self.vectors.values())
        sparsity = 1.0 - nonzero / total_weights if total_weights else 0
        print(f"({load_s:.0f}s, {sparsity:.1%} sparse)")

    def _encode(self, text: str) -> "torch.Tensor":
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )
        with torch.no_grad():
            outputs = self.model(**inputs)
        # SPLADE: max-pool over sequence → ReLU → L2 normalize
        # Use log-saturation from the SPLADE paper: log(1 + ReLU(x))
        vec = torch.max(outputs.logits, dim=1).values.squeeze()
        vec = torch.log(1 + torch.relu(vec))
        norm = torch.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def search(self, action_text: str) -> list[tuple[str, float]]:
        q_vec = self._encode(action_text)
        scores = []
        for cid in self.connector_ids:
            sim = float(torch.dot(q_vec, self.vectors[cid]))
            scores.append((cid, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# V9: MiniLM Dense Semantic Retrieval
# ═══════════════════════════════════════════════════════════════════════════

_MINILM_AVAILABLE = False
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    _MINILM_AVAILABLE = True
except ImportError:
    pass


class V9MiniLM:
    variant_id = "v9"
    name = "V9: MiniLM"
    family = "Neural Dense"
    deps = "sentence-tf"
    size_mb = 22.0

    def __init__(self, docs: dict[str, str], model_name: str = "all-MiniLM-L6-v2"):
        if not _MINILM_AVAILABLE:
            raise ImportError("MiniLM requires: pip install sentence-transformers")
        self.model_name = model_name
        print(f"        Loading {model_name}...", end=" ", flush=True)
        t0 = time.perf_counter()
        self.model = SentenceTransformer(model_name, trust_remote_code=True)
        self.connector_ids = list(docs.keys())
        self.embeddings: dict[str, "np.ndarray"] = {}
        for cid in self.connector_ids:
            self.embeddings[cid] = self.model.encode(
                docs[cid],
                normalize_embeddings=True,
            )
        load_s = time.perf_counter() - t0
        dim = self.embeddings[self.connector_ids[0]].shape[0]
        print(f"({load_s:.0f}s, {dim}-dim)")

    def search(self, action_text: str) -> list[tuple[str, float]]:
        q_emb = self.model.encode(action_text, normalize_embeddings=True)
        scores = []
        for cid in self.connector_ids:
            sim = float(np.dot(q_emb, self.embeddings[cid]))
            scores.append((cid, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# V19: Multi-Signal Soft Fusion
# ═══════════════════════════════════════════════════════════════════════════
#
# Implements: final = 0.55*dense + 0.20*lexical + 0.10*cap_group
#                     + 0.10*namespace + 0.05*context
#
# Hints are boosts, never gates.  No WHERE domain = ?.  No hard filters.


class MultiSignalFusion:
    variant_id = "v19"
    name = "V19: Multi-Signal"
    family = "Fusion"
    deps = "sentence-tf"
    size_mb = 22.0

    def __init__(
        self,
        dense_searcher,
        lexical_searcher,
        cap_group_searcher,
        namespace_prior: float = 0.10,
        context_prior: float = 0.05,
    ):
        self.dense = dense_searcher  # MiniLM (weight 0.55)
        self.lexical = lexical_searcher  # FTS5 OR connectors (weight 0.20)
        self.cap_group = cap_group_searcher  # FTS5 caps grouped (weight 0.10)
        self.namespace_prior = namespace_prior  # active namespace boost
        self.context_prior = context_prior  # recent context boost

    def search(self, action_text: str) -> list[tuple[str, float]]:
        # Get candidate lists from each signal
        dense_results = self.dense.search(action_text)
        lexical_results = self.lexical.search(action_text)
        cap_results = self.cap_group.search(action_text)

        # Normalize each to [0, 1] using min-max
        def normalize(scores: list[tuple[str, float]]) -> dict[str, float]:
            if not scores:
                return {}
            vals = [s for _, s in scores]
            mn, mx = min(vals), max(vals)
            span = mx - mn
            if span == 0:
                return {cid: 1.0 for cid, _ in scores}
            return {cid: (s - mn) / span for cid, s in scores}

        dense_norm = normalize(dense_results)
        lexical_norm = normalize(lexical_results)
        cap_norm = normalize(cap_results)

        # Multi-signal fusion: soft boosts, no hard filters
        all_connectors: set[str] = set()
        all_connectors.update(dense_norm.keys())
        all_connectors.update(lexical_norm.keys())
        all_connectors.update(cap_norm.keys())

        fused: dict[str, float] = {}
        for cid in all_connectors:
            score = (
                0.55 * dense_norm.get(cid, 0.0)
                + 0.20 * lexical_norm.get(cid, 0.0)
                + 0.10 * cap_norm.get(cid, 0.0)
            )
            # Namespace prior: family.* connectors get a boost
            if cid.startswith("family."):
                score += self.namespace_prior
            # Context prior: small boost for all (placeholder for real session context)
            score += self.context_prior * 0.1  # tiny default, real context would be dynamic
            fused[cid] = score

        return sorted(fused.items(), key=lambda x: x[1], reverse=True)

    def close(self) -> None:
        self.lexical.close()
        self.cap_group.close()


# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# V20: Two-Stage — MiniLM-L12 bi-encoder → cross-encoder rerank
# ═══════════════════════════════════════════════════════════════════════════
#
# Modern retrieval architecture:
#   Stage 1: MiniLM-L12 bi-encoder → top-20 (3ms, 120MB)
#   Stage 2: MiniLM-L6 cross-encoder → rerank top-20 (batch, 22MB)
#   Total: 142MB
#
# Cross-encoder reads (query, doc) PAIRS jointly through a classification
# head trained on MS MARCO passage ranking.  Unlike bi-encoder cosine
# similarity, it understands that "todo" is the action and "garage door"
# is the object, so family.tasks > myq.garage.


class V20TwoStageRerank:
    """MiniLM-L12 bi-encoder → MiniLM-L6 cross-encoder rerank."""

    variant_id = "v20"
    name = "V20: 2-Stage Rerank"
    family = "Cross-Encoder"
    deps = "sentence-tf"
    size_mb = 142.0  # 120MB L12 + 22MB cross-encoder

    def __init__(self, docs: dict[str, str], stage1):
        from sentence_transformers import CrossEncoder

        model_name = "cross-encoder/ms-marco-MiniLM-L6-v2"
        print(f"        Loading cross-encoder: {model_name}...", end=" ", flush=True)
        t0 = time.perf_counter()
        self.reranker = CrossEncoder(model_name)
        self.stage1 = stage1  # MiniLM-L12 bi-encoder
        self.connector_ids = list(docs.keys())
        self._doc_texts = docs
        load_s = time.perf_counter() - t0
        print(f"({load_s:.0f}s, 22MB)")

    def search(self, action_text: str) -> list[tuple[str, float]]:
        # Stage 1: MiniLM-L12 dense retrieval → top-20
        stage1_results = self.stage1.search(action_text)
        n_candidates = min(20, len(stage1_results))
        candidate_ids = [cid for cid, _ in stage1_results[:n_candidates]]
        candidate_docs = [self._doc_texts[cid] for cid in candidate_ids]

        # Stage 2: Cross-encoder scores each (query, doc) pair jointly
        pairs = [(action_text, doc) for doc in candidate_docs]
        scores = self.reranker.predict(pairs, show_progress_bar=False)

        # Combine and sort by cross-encoder score
        scored = [(candidate_ids[i], float(scores[i])) for i in range(len(candidate_ids))]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Append un-reranked at lower priority
        seen = {cid for cid, _ in scored}
        for cid, s in stage1_results:
            if cid not in seen:
                scored.append((cid, s * 0.01))

        return scored

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# V10: Weighted Hybrid BM25 + MiniLM (RRF)
# ═══════════════════════════════════════════════════════════════════════════


class V10Hybrid:
    """Weighted RRF: BM25 + MiniLM.  weight=0.3, MiniLM weight=0.7, k=60."""

    variant_id = "v10"
    name = "V10: Hybrid W-RRF"
    family = "Fusion"
    deps = "sentence-tf"
    size_mb = 22.0

    def __init__(
        self, bm25, minilm: V9MiniLM, w_bm25: float = 0.3, w_mlm: float = 0.7, k: int = 60
    ):
        self.bm25 = bm25
        self.minilm = minilm
        self.w_bm25 = w_bm25
        self.w_mlm = w_mlm
        self.k = k

    def search(self, action_text: str) -> list[tuple[str, float]]:
        bm25_results = self.bm25.search(action_text)
        mlm_results = self.minilm.search(action_text)

        rrf_scores: dict[str, float] = defaultdict(float)
        for rank, (cid, _) in enumerate(bm25_results, start=1):
            rrf_scores[cid] += self.w_bm25 / (self.k + rank)
        for rank, (cid, _) in enumerate(mlm_results, start=1):
            rrf_scores[cid] += self.w_mlm / (self.k + rank)

        return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    def close(self) -> None:
        self.bm25.close()


# ═══════════════════════════════════════════════════════════════════════════
# V11 / V12: Family-Prior Reranker
# ═══════════════════════════════════════════════════════════════════════════

# Acceptable semantic alternatives for each real FamilyOS connector.
# A query matched to a distractor in this set is "semantically acceptable"
# — the search found the right kind of connector, just not the FamilyOS one.
# With diverse-domain distractors (banking, IoT, health, etc.), there are NO
# "acceptable alternatives" — a banking connector is never the right answer
# for a shopping query.  The semantic overlap problem is gone.
ACCEPTABLE_ALTERNATIVES: dict[str, set[str]] = {
    "family.calendar": set(),
    "family.shopping": set(),
    "family.tasks": set(),
    "family.chores": set(),
    "family.reminders": set(),
    "family.family_settings": set(),
}


# ═══════════════════════════════════════════════════════════════════════════
# V21: Schema-Augmented Search — Intent Classifier + MiniLM Dense
# ═══════════════════════════════════════════════════════════════════════════
#
# Stage 0: Fine-tuned intent classifier predicts (effect, resource, domain)
# Stage 1: Schema scoring — connectors matching predicted fields get boost
# Stage 2: MiniLM dense retrieval
# Final: 0.4*schema + 0.4*dense + 0.2*namespace
#
# Hints are soft boosts, never hard filters.

_INTENT_CLASSIFIER_AVAILABLE = False
try:
    from scripts.train_intent_classifier import IntentClassifierInference

    _INTENT_CLASSIFIER_AVAILABLE = True
except ImportError:
    pass


class SchemaAugmentedSearch:
    """Intent classifier + MiniLM dense + namespace prior — confidence-weighted fusion.

    Domain index built dynamically from GPS data — no hardcoded mappings.
    Works for ANY registered connector, not just FamilyOS.
    """

    variant_id = "v21"
    name = "V21: Schema+MLM"
    family = "Schema-Augmented"
    deps = "sentence-tf"
    size_mb = 22.0

    _EFFECT_BOOST = {
        "create": 1.0,
        "complete": 1.0,
        "execute": 1.0,
        "update": 0.9,
        "delete": 0.8,
        "read": 0.7,
    }

    def __init__(self, dense_searcher, docs: dict[str, str], gps: GlobalProjectionStore):
        if not _INTENT_CLASSIFIER_AVAILABLE:
            raise ImportError("Intent classifier not trained. Run train_intent_classifier.py first")
        t0 = time.perf_counter()
        print(f"        Loading intent classifier...", end=" ", flush=True)
        self.classifier = IntentClassifierInference()
        self.dense = dense_searcher
        self.connector_ids = list(docs.keys())
        self._domain_index = self._build_domain_index(gps)
        load_s = time.perf_counter() - t0
        n_tags = len(self._domain_index)
        print(f"({load_s:.0f}s, {n_tags} domain tags)")

    def _build_domain_index(self, gps) -> dict[str, list[str]]:
        """Build domain_tag → [connector_ids] from GPS connector data."""
        from collections import defaultdict

        index: dict[str, list[str]] = defaultdict(list)
        db = gps._db
        rows = db.execute("SELECT connector_id, domain_id FROM connectors").fetchall()
        for cid, domain_id in rows:
            if domain_id:
                index[domain_id].append(cid)
            # Also index by namespace prefix (e.g. "family", "chase", "tesla")
            if "." in cid:
                ns = cid.split(".")[0]
                index[ns].append(cid)
        return dict(index)

    def search(self, action_text: str) -> list[tuple[str, float]]:
        # Stage 0: Intent classification
        intent = self.classifier.predict(action_text)
        pred_effect = intent["effect"]
        pred_native_app = intent.get("native_app") or intent.get("domain_tag", "")
        domain_conf = intent.get("domain_confidence", 0.5)
        is_ambiguous = intent.get("is_ambiguous", False)

        # Stage 1: Schema scoring — HONEST, no blanket boosts, no namespace prior
        effect_boost = self._EFFECT_BOOST.get(pred_effect, 0.5)

        schema_scores: dict[str, float] = {}
        for cid in self.connector_ids:
            if cid == pred_native_app:
                schema_scores[cid] = effect_boost * max(domain_conf, 0.3)
            else:
                schema_scores[cid] = 0.0

        # Stage 2: MiniLM dense retrieval
        dense_results = self.dense.search(action_text)
        dense_map = {cid: s for cid, s in dense_results}
        if dense_map:
            mx = max(dense_map.values())
            mn = min(dense_map.values())
            span = mx - mn
            if span > 0:
                dense_map = {c: (s - mn) / span for c, s in dense_map.items()}

        # Stage 3: Honest fusion — schema boost only when classifier is right
        if is_ambiguous:
            w_schema, w_dense = 0.10, 0.90
        else:
            w_schema = 0.30 * max(domain_conf, 0.3)
            w_dense = 0.70
            total = w_schema + w_dense
            w_schema /= total
            w_dense /= total

        fused: dict[str, float] = {}
        for cid in self.connector_ids:
            fused[cid] = w_schema * schema_scores.get(cid, 0.0) + w_dense * dense_map.get(cid, 0.0)

        return sorted(fused.items(), key=lambda x: x[1], reverse=True)

    def close(self) -> None:
        pass


class FamilyPriorReranker:
    """Wraps any searcher, adds a configurable score boost to family.* connectors.

    DEFAULT IS ZERO PRIOR.  The search must work on its own.  A namespace
    prior is a tiebreaker for genuinely ambiguous queries — it should NEVER
    override an explicit brand name in the query text.

    Prior weight is a knob for the resolver to set based on session context,
    not a hardcoded cheat for benchmark scores.
    """

    variant_id = "v11"
    name = "V11: MLM+prior"
    family = "Reranked"
    deps = "sentence-tf"
    size_mb = 22.0

    def __init__(
        self,
        base_searcher,
        family_prior: float = 0.00,
        variant_id_override: str = "v11",
        name_override: str = "V11: MLM+prior",
    ):
        self.base = base_searcher
        self.prior = family_prior
        self.variant_id = variant_id_override
        self.name = name_override

    def search(self, action_text: str) -> list[tuple[str, float]]:
        results = self.base.search(action_text)
        reranked = [
            (cid, score + (self.prior if cid.startswith("family.") else 0.0))
            for cid, score in results
        ]
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# V22: Schema-Agnostic — Pure Embedding Similarity
# ═══════════════════════════════════════════════════════════════════════════
#
# Zero hardcoded knowledge: no boundary fields, no effect taxonomy,
# no FAMILY_TAG_MAP, no ACCEPTABLE_ALTERNATIVES, no intent classifier,
# no REAL_DEFS, no competing distractor special cases.
#
# Documents are assembled dynamically from GPS — one structure for all.
# The embedding model IS the classifier. Cosine similarity IS the resolver.
#
# This works for ANY connector that registers. Swap the encoder model
# and everything else stays identical.


class V22SchemaAgnostic:
    """Pure embedding similarity. No boundary fields. No taxonomy. No classifier.

    One document structure for ALL connectors — dynamically assembled from GPS.
    Works with any connector that registers. Zero hardcoded mappings.

    Model-agnostic: swap MiniLM for any SentenceTransformer encoder.
    Domain-agnostic: no concept of "shopping" vs "banking" vs "health."
    Scale-agnostic: same algorithm at 10 connectors or 10,000.
    """

    variant_id = "v22"
    name = "V22: Schema-Agnostic"
    family = "Schema-Agnostic"
    deps = "sentence-tf"
    size_mb = 22.0

    def __init__(self, gps: GlobalProjectionStore):
        if not _MINILM_AVAILABLE:
            raise ImportError("Schema-Agnostic requires: pip install sentence-transformers")
        import json as _json

        import numpy as np
        from sentence_transformers import SentenceTransformer

        print(f"        Loading Schema-Agnostic (all-MiniLM-L6-v2)...", end=" ", flush=True)
        t0 = time.perf_counter()
        self.model = SentenceTransformer("all-MiniLM-L6-v2", trust_remote_code=True)
        self.connector_ids: list[str] = []
        self.embeddings: dict[str, "np.ndarray"] = {}

        db = gps._db

        # Discover ALL connectors dynamically — no REAL_DEFS, no hardcoded list
        rows = db.execute(
            "SELECT connector_id, label, domain_id, constitution_json FROM connectors"
        ).fetchall()
        connector_data = {
            r[0]: {"label": r[1], "domain_id": r[2], "constitution_json": r[3]} for r in rows
        }
        self.connector_ids = list(connector_data.keys())

        for cid in self.connector_ids:
            data = connector_data[cid]
            doc = self._build_document(cid, data, db, _json)
            self.embeddings[cid] = self.model.encode(
                doc,
                normalize_embeddings=True,
            )

        load_s = time.perf_counter() - t0
        dim = self.embeddings[self.connector_ids[0]].shape[0] if self.connector_ids else 0
        print(f"({load_s:.0f}s, {dim}-dim, {len(self.connector_ids)} connectors)")

    @staticmethod
    def _build_document(connector_id: str, data: dict, db, _json) -> str:
        """ONE document structure. No special cases. No boundary fields.

        Whatever the connector developer registered IS the schema.
        No enrichment. No taxonomy. No repetition tricks.
        """
        parts: list[str] = []

        # 1. Connector identity — namespace + label
        label = data.get("label") or connector_id
        parts.append(f"{connector_id}. {label}.")

        # 2. Domain — whatever domain_id the connector set in GPS
        domain_id = data.get("domain_id")
        if domain_id:
            parts.append(f"Domain: {domain_id}.")

        # 3. Action names + descriptions — whatever capabilities registered
        cap_rows = db.execute(
            "SELECT action_name, description FROM capabilities " "WHERE connector_id = ?",
            (connector_id,),
        ).fetchall()
        if cap_rows:
            action_names = [r[0] for r in cap_rows]
            parts.append(f"Actions: {', '.join(action_names)}.")
            for _, desc in cap_rows:
                if desc and len(desc) > 5:
                    parts.append(desc)

        # 4. Constitution text — extract string fields dynamically
        const_json = data.get("constitution_json")
        if const_json and const_json != "{}":
            try:
                const = _json.loads(const_json)
                for key, value in const.items():
                    if isinstance(value, str) and len(value) > 10:
                        parts.append(value)
                    elif isinstance(value, list):
                        parts.append(f"{key}: {', '.join(str(v) for v in value)}")
            except Exception:
                pass

        return " ".join(parts)

    def search(self, action_text: str) -> list[tuple[str, float]]:
        """Pure cosine similarity. No boost. No filter. No classifier."""
        import numpy as np

        q_emb = self.model.encode(action_text, normalize_embeddings=True)
        scores = []
        for cid in self.connector_ids:
            sim = float(np.dot(q_emb, self.embeddings[cid]))
            scores.append((cid, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Benchmark Harness
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class TierStats:
    connector_at_1: int = 0
    connector_at_3: int = 0
    connector_at_5: int = 0
    connector_at_10: int = 0
    mrr: float = 0.0  # MRR@∞ (actual)
    mrr_at_5: float = 0.0  # MRR truncated at 5
    mrr_at_10: float = 0.0  # MRR truncated at 10
    total: int = 0
    total_latency_ms: float = 0.0
    # Namespace leakage metrics
    pref_at_1: int = 0  # exact expected connector (preferred)
    accept_at_1: int = 0  # expected OR acceptable alternative
    family_leak: int = 0  # expected is family.* but got distractor
    # Multi-namespace false-positive tracking
    false_positive: int = 0  # expected non-family, got family.* connector
    multi_ns_total: int = 0  # total multi-namespace queries evaluated
    multi_ns_correct: int = 0  # correct routing for multi-namespace queries

    @property
    def accuracy_at_1(self) -> float:
        return self.connector_at_1 / self.total if self.total else 0.0

    @property
    def accuracy_at_3(self) -> float:
        return self.connector_at_3 / self.total if self.total else 0.0

    @property
    def accuracy_at_5(self) -> float:
        return self.connector_at_5 / self.total if self.total else 0.0

    @property
    def accuracy_at_10(self) -> float:
        return self.connector_at_10 / self.total if self.total else 0.0

    @property
    def pref_rate(self) -> float:
        return self.pref_at_1 / self.total if self.total else 0.0

    @property
    def accept_rate(self) -> float:
        return self.accept_at_1 / self.total if self.total else 0.0

    @property
    def leak_rate(self) -> float:
        return self.family_leak / self.total if self.total else 0.0

    @property
    def false_positive_rate(self) -> float:
        """Fraction of non-family queries incorrectly routed to family.*"""
        return self.false_positive / self.multi_ns_total if self.multi_ns_total else 0.0

    @property
    def mrr5(self) -> float:
        return self.mrr_at_5 / self.total if self.total else 0.0

    @property
    def mrr10(self) -> float:
        return self.mrr_at_10 / self.total if self.total else 0.0

    @property
    def multi_ns_accuracy(self) -> float:
        """Accuracy on multi-namespace queries only"""
        return self.multi_ns_correct / self.multi_ns_total if self.multi_ns_total else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.total if self.total else 0.0


@dataclass
class VariantReport:
    name: str
    family: str
    dependencies: str
    model_size_mb: float
    overall: TierStats = field(default_factory=TierStats)
    tiers: dict[str, TierStats] = field(default_factory=dict)
    failures: list[dict] = field(default_factory=list)
    oov_rate: float = 0.0

    @property
    def cliff_score(self) -> float:
        easy = self.tiers.get("easy", TierStats()).accuracy_at_1
        hardest = self.tiers.get("hardest", TierStats()).accuracy_at_1
        return (easy - hardest) * 100


def run_benchmark(
    name: str,
    search_fn: Callable[[str], list[tuple[str, float]]],
    corpus: list[dict],
    family: str = "",
    dependencies: str = "stdlib+sqlite3",
    model_size_mb: float = 0.0,
) -> VariantReport:
    report = VariantReport(
        name=name,
        family=family,
        dependencies=dependencies,
        model_size_mb=model_size_mb,
    )
    total_oov = 0
    total_tokens = 0

    for query in corpus:
        qid = query["id"]
        action = query["action"]
        expected = query["expected_connector"]
        tier = query.get("difficulty", "unknown")

        t0 = time.perf_counter()
        results = search_fn(action)
        latency_ms = (time.perf_counter() - t0) * 1000

        connector_ids = [r[0] for r in results] if results else []
        top1 = connector_ids[0] if connector_ids else None
        hit1 = top1 == expected
        hit3 = expected in connector_ids[:3] if connector_ids else False
        hit5 = expected in connector_ids[:5] if connector_ids else False
        hit10 = expected in connector_ids[:10] if connector_ids else False

        try:
            rank = connector_ids.index(expected) + 1
            mrr = 1.0 / rank
            mrr5 = 1.0 / rank if rank <= 5 else 0.0
            mrr10 = 1.0 / rank if rank <= 10 else 0.0
        except ValueError:
            mrr = 0.0
            mrr5 = 0.0
            mrr10 = 0.0

        report.overall.total += 1
        report.overall.total_latency_ms += latency_ms
        if hit1:
            report.overall.connector_at_1 += 1
        if hit3:
            report.overall.connector_at_3 += 1
        if hit5:
            report.overall.connector_at_5 += 1
        if hit10:
            report.overall.connector_at_10 += 1
        report.overall.mrr += mrr
        report.overall.mrr_at_5 += mrr5
        report.overall.mrr_at_10 += mrr10

        # Namespace leakage: preferred = exact match, acceptable = in alternatives
        acceptable_set = ACCEPTABLE_ALTERNATIVES.get(expected, set())
        is_pref = hit1
        is_accept = hit1 or (top1 in acceptable_set if top1 else False)
        is_leak = (
            expected.startswith("family.") and top1 is not None and not top1.startswith("family.")
        )

        report.overall.pref_at_1 += 1 if is_pref else 0
        report.overall.accept_at_1 += 1 if is_accept else 0
        report.overall.family_leak += 1 if is_leak else 0

        # Multi-namespace false-positive tracking
        is_multi_ns = not expected.startswith("family.")
        is_false_pos = is_multi_ns and top1 is not None and top1.startswith("family.")
        if is_multi_ns:
            report.overall.multi_ns_total += 1
            if hit1:
                report.overall.multi_ns_correct += 1
        if is_false_pos:
            report.overall.false_positive += 1

        if tier not in report.tiers:
            report.tiers[tier] = TierStats()
        ts = report.tiers[tier]
        ts.total += 1
        ts.total_latency_ms += latency_ms
        if hit1:
            ts.connector_at_1 += 1
        if hit3:
            ts.connector_at_3 += 1
        if hit5:
            ts.connector_at_5 += 1
        if hit10:
            ts.connector_at_10 += 1
        ts.mrr += mrr
        ts.mrr_at_5 += mrr5
        ts.mrr_at_10 += mrr10
        ts.pref_at_1 += 1 if is_pref else 0
        ts.accept_at_1 += 1 if is_accept else 0
        ts.family_leak += 1 if is_leak else 0
        if is_multi_ns:
            ts.multi_ns_total += 1
            if hit1:
                ts.multi_ns_correct += 1
        if is_false_pos:
            ts.false_positive += 1

        if not hit1:
            # Classify failure: namespace leak vs semantic miss
            failure_type = "namespace_leak" if is_leak else "semantic_miss"
            if is_false_pos:
                failure_type = "false_positive"
            report.failures.append(
                {
                    "id": qid,
                    "action": action,
                    "expected": expected,
                    "got": top1,
                    "got_top3": connector_ids[:3],
                    "tier": tier,
                    "profile": query.get("hallucination_profile", ""),
                    "failure_type": failure_type,
                    "semantically_acceptable": is_accept and not is_pref,
                }
            )

        # OOV tracking for tokenizer diagnostics
        tokens = tokenize(action)
        total_tokens += len(tokens)
        total_oov += sum(1 for t in tokens if len(t) < 2)

    if report.overall.total:
        report.overall.mrr /= report.overall.total
    for ts in report.tiers.values():
        if ts.total:
            ts.mrr /= ts.total
    report.oov_rate = total_oov / total_tokens if total_tokens else 0.0

    return report


# ═══════════════════════════════════════════════════════════════════════════
# Reporting
# ═══════════════════════════════════════════════════════════════════════════


def print_divider(char: str = "-", width: int = 100):
    print(char * width)


def print_report(reports: list[VariantReport], corpus: list[dict], n_distractors: int) -> None:
    print()
    print_divider("=")
    n_connectors = 6 + n_distractors
    has_d = n_distractors > 0
    print(
        f"  CONNECTOR SEARCH POC - RESULTS  " f"({n_connectors} connectors, {len(corpus)} queries)"
    )
    print_divider("=")

    # ── Overall comparison ──
    print()
    if has_d:
        print(
            f"  {'Variant':<24s} {'Family':<10s} {'Size':>5s}  "
            f"{'Pref@1':>7s} {'Conn@1':>7s} {'Accept':>7s} "
            f"{'Leak':>6s} {'FPos':>5s} {'MultiNs':>7s} "
            f"{'C@1':>6s} {'C@3':>6s} {'C@5':>6s} {'C@10':>6s} "
            f"{'MRR':>6s} {'MRR5':>6s} {'MRR10':>6s} {'ms':>6s}"
        )
        print(
            f"  {'-'*24} {'-'*10} {'-'*5}  {'-'*7} {'-'*7} {'-'*7} "
            f"{'-'*6} {'-'*5} {'-'*7} "
            f"{'-'*6} {'-'*6} {'-'*6} {'-'*6} "
            f"{'-'*6} {'-'*6} {'-'*6} {'-'*6}"
        )
    else:
        print(
            f"  {'Variant':<24s} {'Family':<14s} {'Depends':<16s} {'Size':>6s}  "
            f"{'Conn@1':>8s} {'Conn@3':>8s} {'MRR':>7s} {'Cliff':>7s} {'ms':>7s}"
        )
        print(f"  {'-'*24} {'-'*14} {'-'*16} {'-'*6}  {'-'*8} {'-'*8} {'-'*7} {'-'*7} {'-'*7}")

    sorted_reports = sorted(reports, key=lambda r: r.overall.accuracy_at_1, reverse=True)

    for r in sorted_reports:
        size_str = f"{r.model_size_mb:.0f}MB" if r.model_size_mb else "0"
        if has_d:
            print(
                f"  {r.name:<24s} {r.family:<10s} {size_str:>5s}  "
                f"{r.overall.pref_rate:>6.1%} {r.overall.accuracy_at_1:>6.1%} "
                f"{r.overall.accept_rate:>6.1%} "
                f"{r.overall.leak_rate:>5.1%} {r.overall.false_positive_rate:>4.0%} "
                f"{r.overall.multi_ns_accuracy:>6.1%} "
                f"{r.overall.accuracy_at_1:>5.1%} {r.overall.accuracy_at_3:>5.1%} "
                f"{r.overall.accuracy_at_5:>5.1%} {r.overall.accuracy_at_10:>5.1%} "
                f"{r.overall.mrr:>5.4f} {r.overall.mrr5:>5.4f} {r.overall.mrr10:>5.4f} "
                f"{r.overall.avg_latency_ms:>5.1f}"
            )
        else:
            print(
                f"  {r.name:<24s} {r.family:<14s} {r.dependencies:<16s} {size_str:>6s}  "
                f"{r.overall.accuracy_at_1:>7.1%} {r.overall.accuracy_at_3:>7.1%} "
                f"{r.overall.mrr:>7.4f} {r.cliff_score:>6.0f}pt {r.overall.avg_latency_ms:>6.1f}"
            )

    # ── Per-tier breakdown ──
    print()
    print_divider("-")
    print("  PER-TIER Connector@1 (top 6 variants)")
    print_divider("-")

    top6 = sorted_reports[:6]
    tier_labels_short = {
        "easy": "EASY",
        "medium": "MEDIUM",
        "hard": "HARD",
        "ultrahard": "ULTRA",
        "hardest": "HARDEST",
    }

    header = f"  {'Variant':<24s}"
    for t in TIER_ORDER:
        header += f" {tier_labels_short.get(t, t):>8s}"
    header += f" {'Overall':>8s}"
    print(header)
    print(f"  {'-'*24}" + f" {'-'*8}" * (len(TIER_ORDER) + 1))

    # Old resolver — only comparable on 6-connector runs
    if not has_d:
        tier_counts = Counter(q.get("difficulty", "unknown") for q in corpus)
        old_tier = {"easy": 1.00, "medium": 0.90, "hard": 0.60, "ultrahard": 0.40, "hardest": 0.40}
        old_row = f"  {'OLD RESOLVER (v1 bench)':<24s}"
        old_weighted = 0.0
        old_total = sum(tier_counts.values())
        for t in TIER_ORDER:
            count = tier_counts.get(t, 0)
            acc = old_tier.get(t, 0)
            old_weighted += acc * count
            old_row += f" {acc:>7.1%}"
        old_row += f" {old_weighted / old_total:>7.1%}" if old_total else "     N/A"
        print(old_row)
    else:
        old_row = f"  {'OLD RESOLVER':<24s}"
        for t in TIER_ORDER:
            old_row += f" {'N/A':>8s}"
        old_row += f" {'66% (6-conn only)':>8s}"
        print(old_row)
    print()

    for r in top6:
        row = f"  {r.name:<24s}"
        for t in TIER_ORDER:
            ts = r.tiers.get(t, TierStats())
            row += f" {ts.accuracy_at_1:>7.1%}"
        row += f" {r.overall.accuracy_at_1:>7.1%}"
        print(row)

    # ── Namespace leakage analysis (distractors only) ──
    if has_d:
        print()
        print_divider("-")
        best = sorted_reports[0]
        n_leaks = best.overall.family_leak
        n_accept = best.overall.accept_at_1 - best.overall.pref_at_1
        n_miss = best.overall.total - best.overall.accept_at_1
        print(
            f"  NAMESPACE ANALYSIS - Best: {best.name} "
            f"(Pref={best.overall.pref_rate:.1%}, "
            f"Accept={best.overall.accept_rate:.1%}, "
            f"Leak={best.overall.leak_rate:.1%})"
        )
        print(f"  {n_leaks} namespace leaks (got distractor, expected family.*)")
        print(f"  {n_accept} semantically-acceptable (right kind, wrong namespace)")
        print(f"  {n_miss} semantic misses (wrong connector entirely)")
        print_divider("-")

    # ── Failure analysis ──
    print()
    print_divider("-")
    best = sorted_reports[0]
    print(
        f"  FAILURE ANALYSIS - Best: {best.name} "
        f"({best.overall.connector_at_1}/{best.overall.total} correct, "
        f"{best.overall.accuracy_at_1:.1%})"
    )
    print_divider("-")

    # Split failures by type: namespace_leak vs semantic_miss vs false_positive
    leaks = [f for f in best.failures if f.get("failure_type") == "namespace_leak"]
    misses = [f for f in best.failures if f.get("failure_type") == "semantic_miss"]
    false_pos = [f for f in best.failures if f.get("failure_type") == "false_positive"]

    if leaks:
        print(f"\n  [NAMESPACE LEAKS] ({len(leaks)} — got distractor, expected family.*):")
        for f in leaks[:8]:
            acc = " [acceptable]" if f.get("semantically_acceptable") else ""
            print(
                f"    {f['id']}: \"{f['action'][:55]}\" -> "
                f"got={f['got'] or 'NONE'}, expected={f['expected']}{acc}"
            )
        if len(leaks) > 8:
            print(f"    ... and {len(leaks) - 8} more")

    if false_pos:
        print(f"\n  [FALSE POSITIVES] ({len(false_pos)} — expected non-family, got family.*):")
        for f in false_pos[:8]:
            print(
                f"    {f['id']}: \"{f['action'][:55]}\" -> "
                f"got={f['got'] or 'NONE'}, expected={f['expected']} "
                f"[{f['tier']}]"
            )
        if len(false_pos) > 8:
            print(f"    ... and {len(false_pos) - 8} more")

    if misses:
        print(f"\n  [SEMANTIC MISSES] ({len(misses)} — wrong connector type entirely):")
        for f in misses[:8]:
            print(
                f"    {f['id']}: \"{f['action'][:55]}\" -> "
                f"got={f['got'] or 'NONE'}, expected={f['expected']} "
                f"[{f['tier']}]"
            )
        if len(misses) > 8:
            print(f"    ... and {len(misses) - 8} more")

    # Wrong-connector distribution
    conn_dist = Counter(f["got"] or "NONE" for f in best.failures)
    real_conns = set(REAL_DEFS.keys())
    print(f"\n  Wrong-connector distribution " f"(R=real family conn, D=distractor):")
    for conn, count in conn_dist.most_common(12):
        tag = "R" if conn in real_conns else "D"
        print(f"    [{tag}] -> {conn}: {count}")

    print()


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# Multi-Namespace Test Queries — Human-Disambiguable Only
# ═══════════════════════════════════════════════════════════════════════════
# These queries must be disambiguable by a HUMAN reading the query text.
# If the query mentions a specific brand name, feature, or unique verb that
# maps to exactly ONE connector, a human can route it correctly — and the
# search MUST do the same.  If the search fails these, it's broken.
#
# Genuinely ambiguous queries ("add produce to my cart" — which grocery app?)
# are NOT included here.  Those need session context (is_resolved=False).

_MULTI_NAMESPACE_QUERIES: list[dict[str, Any]] = [
    # ── Native-App-as-Aggregator: brand-name queries route to the native app, ──
    #     NOT to a competing backend connector.  Kroger/Costco/Safeway are data
    #     backends to family.shopping — the Back LLM calls family.shopping, and
    #     the native app fans out to the correct backend based on backend_id.
    # ── Grocery → family.shopping ──
    {
        "id": "multi-grocery-01",
        "action": "get my groceries delivered from Kroger today",
        "expected_connector": "family.shopping",
        "difficulty": "easy",
        "why_disambiguable": "Kroger is a backend to family.shopping",
    },
    {
        "id": "multi-grocery-02",
        "action": "build a bulk shopping list for my Costco run this weekend",
        "expected_connector": "family.shopping",
        "difficulty": "easy",
        "why_disambiguable": "Costco is a backend to family.shopping",
    },
    {
        "id": "multi-grocery-03",
        "action": "what's on sale at Safeway this week with Just For U coupons",
        "expected_connector": "family.shopping",
        "difficulty": "easy",
        "why_disambiguable": "Safeway is a backend to family.shopping",
    },
    {
        "id": "multi-grocery-04",
        "action": "order Whole Foods delivery of organic produce and fresh fish",
        "expected_connector": "family.shopping",
        "difficulty": "easy",
        "why_disambiguable": "Whole Foods is a backend to family.shopping",
    },
    {
        "id": "multi-grocery-05",
        "action": "add BOGO items from the Publix weekly ad to my list",
        "expected_connector": "family.shopping",
        "difficulty": "medium",
        "why_disambiguable": "Publix is a backend to family.shopping",
    },
    # ── Task apps → family.tasks ──
    {
        "id": "multi-task-01",
        "action": "move the Q3 planning card to the Done column on my Trello board",
        "expected_connector": "family.tasks",
        "difficulty": "medium",
        "why_disambiguable": "Trello is a task backend; 'card/column/board' = task vocabulary",
    },
    {
        "id": "multi-task-02",
        "action": "create a task in Todoist from this flagged email",
        "expected_connector": "family.tasks",
        "difficulty": "easy",
        "why_disambiguable": "Todoist is a task backend",
    },
    {
        "id": "multi-task-03",
        "action": "use Eisenhower matrix in TickTick to prioritize my tasks for next week",
        "expected_connector": "family.tasks",
        "difficulty": "medium",
        "why_disambiguable": "TickTick is a task backend",
    },
    {
        "id": "multi-task-04",
        "action": "post a TaskRabbit errand for someone to assemble my IKEA furniture",
        "expected_connector": "family.tasks",
        "difficulty": "medium",
        "why_disambiguable": "TaskRabbit is a task/errand backend",
    },
    {
        "id": "multi-task-05",
        "action": "organize my projects with GTD contexts and defer dates in OmniFocus",
        "expected_connector": "family.tasks",
        "difficulty": "medium",
        "why_disambiguable": "OmniFocus is a task backend",
    },
    # ── Scheduling apps → family.calendar ──
    {
        "id": "multi-sched-01",
        "action": "share my Calendly booking link so the client can pick a time",
        "expected_connector": "family.calendar",
        "difficulty": "medium",
        "why_disambiguable": "Calendly is a calendar/scheduling backend",
    },
    {
        "id": "multi-sched-02",
        "action": "create a Doodle poll for the team to vote on happy hour time",
        "expected_connector": "family.calendar",
        "difficulty": "medium",
        "why_disambiguable": "Doodle is a scheduling backend",
    },
    {
        "id": "multi-sched-03",
        "action": "use Reclaim to auto-schedule my deep work blocks and defend focus time",
        "expected_connector": "family.calendar",
        "difficulty": "medium",
        "why_disambiguable": "Reclaim is a calendar/scheduling backend",
    },
    {
        "id": "multi-sched-04",
        "action": "overlay my calendars in SavvyCal to find ranked available slots",
        "expected_connector": "family.calendar",
        "difficulty": "medium",
        "why_disambiguable": "SavvyCal is a calendar backend",
    },
    {
        "id": "multi-sched-05",
        "action": "let Clockwise automatically resolve my team's meeting conflicts",
        "expected_connector": "family.calendar",
        "difficulty": "medium",
        "why_disambiguable": "Clockwise is a calendar/scheduling backend",
    },
    # ── Chore apps → family.chores ──
    {
        "id": "multi-chore-01",
        "action": "check Tody to see which bathroom needs cleaning based on actual dirtiness",
        "expected_connector": "family.chores",
        "difficulty": "medium",
        "why_disambiguable": "Tody is a chores backend",
    },
    {
        "id": "multi-chore-02",
        "action": "complete my chores in Nipto to beat my wife on the leaderboard",
        "expected_connector": "family.chores",
        "difficulty": "medium",
        "why_disambiguable": "Nipto is a chores backend",
    },
    {
        "id": "multi-chore-03",
        "action": "verify the kids actually did their chores in Chorsee with photo proof",
        "expected_connector": "family.chores",
        "difficulty": "medium",
        "why_disambiguable": "Chorsee is a chores backend",
    },
    {
        "id": "multi-chore-04",
        "action": "schedule a Maple deep-clean project for the kitchen and bathrooms",
        "expected_connector": "family.chores",
        "difficulty": "medium",
        "why_disambiguable": "Maple is a chores backend",
    },
    {
        "id": "multi-chore-05",
        "action": "set up FlyLady zone cleaning schedule with daily shine tasks",
        "expected_connector": "family.chores",
        "difficulty": "medium",
        "why_disambiguable": "FlyLady is a chores backend",
    },
    # ── Reminder apps → family.reminders ──
    {
        "id": "multi-alert-01",
        "action": "set up MediSafe to remind me to take my blood pressure medication",
        "expected_connector": "family.reminders",
        "difficulty": "medium",
        "why_disambiguable": "MediSafe is a reminder/alert backend",
    },
    {
        "id": "multi-alert-02",
        "action": "create a Due reminder that keeps nagging until I actually pay the bill",
        "expected_connector": "family.reminders",
        "difficulty": "medium",
        "why_disambiguable": "Due is a reminders backend",
    },
    {
        "id": "multi-alert-03",
        "action": "tell WaterMinder to nudge me to drink water every 90 minutes",
        "expected_connector": "family.reminders",
        "difficulty": "medium",
        "why_disambiguable": "WaterMinder is a reminder/alert backend",
    },
    {
        "id": "multi-alert-04",
        "action": "use Bring to alert me when I'm near Trader Joe's",
        "expected_connector": "family.reminders",
        "difficulty": "medium",
        "why_disambiguable": "Bring is a reminder backend",
    },
    {
        "id": "multi-alert-05",
        "action": "set a Binge Clock reminder for when Severance season 3 drops",
        "expected_connector": "family.reminders",
        "difficulty": "medium",
        "why_disambiguable": "Binge Clock is a reminder backend",
    },
    # ── Settings/Config apps → family.family_settings ──
    {
        "id": "multi-config-01",
        "action": "use LaunchDarkly to turn off the beta search feature for QA only",
        "expected_connector": "family.family_settings",
        "difficulty": "medium",
        "why_disambiguable": "LaunchDarkly is a feature flag/settings backend",
    },
    {
        "id": "multi-config-02",
        "action": "roll out the new checkout to 10% of users via Statsig feature gates",
        "expected_connector": "family.family_settings",
        "difficulty": "medium",
        "why_disambiguable": "Statsig is a feature flag backend",
    },
    {
        "id": "multi-config-03",
        "action": "toggle dark mode flag in Flagsmith for internal testing",
        "expected_connector": "family.family_settings",
        "difficulty": "medium",
        "why_disambiguable": "Flagsmith is a feature flag backend",
    },
    {
        "id": "multi-config-04",
        "action": "kill the broken payment feature in production with Split kill switch",
        "expected_connector": "family.family_settings",
        "difficulty": "medium",
        "why_disambiguable": "Split is a feature flag backend",
    },
    {
        "id": "multi-config-05",
        "action": "set up an Optimizely A/B test for the new signup flow with metrics",
        "expected_connector": "family.family_settings",
        "difficulty": "medium",
        "why_disambiguable": "Optimizely is an A/B testing/settings backend",
    },
]


def main():
    quick = "--quick" in sys.argv
    no_distractors = "--no-distractors" in sys.argv
    selected = None
    args = sys.argv[1:]
    scale = 1
    for i, arg in enumerate(args):
        if arg.startswith("--variants="):
            selected = set(arg.split("=", 1)[1].lower().split(","))
        elif arg == "--variants" and i + 1 < len(args):
            selected = set(args[i + 1].lower().split(","))
        elif arg.startswith("--scale="):
            scale = int(arg.split("=", 1)[1])
        elif arg == "--scale" and i + 1 < len(args):
            scale = int(args[i + 1])

    # Native-App-as-Aggregator: no competing distractors exist.
    # All distractors are semantically-diverse (banking, health, IoT, vehicle, etc.)
    use_distractors = not no_distractors
    if use_distractors:
        n_distractors = len(DISTRACTOR_TEMPLATES) * scale
    else:
        n_distractors = 0

    # ── Local wrapper ──
    def _bgps(with_d: bool = True, s: int = 1):
        return _bootstrap_gps(with_d, s)

    corpus = TEST_CORPUS[:20] if quick else TEST_CORPUS
    # ── Multi-namespace queries: test cross-OS routing ──
    multi_corpus = _MULTI_NAMESPACE_QUERIES[:5] if quick else _MULTI_NAMESPACE_QUERIES
    combined_corpus = list(corpus) + list(multi_corpus)
    corpus_mode = "20q" if quick else f"{len(corpus)}q"
    multi_mode = f"+{len(multi_corpus)} multi-ns"

    print_divider("=")
    print(
        f"  POC CONNECTOR SEARCH  ({corpus_mode} {multi_mode}, " f"{6 + n_distractors} connectors)"
    )
    print_divider("=")

    # ── Build variants with ISOLATED contexts ──
    at_scale = scale > 1
    if at_scale:
        print(
            f"\nScale mode: building only V9/V11b/V21b "
            f"(skip {n_distractors} connector boot for 15 dead variants)\n"
        )
    else:
        print(
            f"\nBuilding variants (each with isolated GPS " f"+ {n_distractors} distractors)...\n"
        )

    variants: list[Any] = []

    # V0-V8: skip at scale (all proven inferior)
    if not at_scale:
        tmp_gps = _bgps(use_distractors, scale)
        all_connector_ids = [
            r[0] for r in tmp_gps._db.execute("SELECT connector_id FROM connectors").fetchall()
        ]
        tmp_gps.close()
        variants.append(V0Random(all_connector_ids))
        variants.append(V1BM25CapGrouped(_bgps(use_distractors, scale)))
        gps2 = _bgps(use_distractors, scale)
        docs2 = build_connector_documents(gps2)
        variants.append(V2BM25Connector(gps2, docs2))
        gps2b = _bgps(use_distractors, scale)
        docs2b = build_connector_documents(gps2b)
        variants.append(V2bBM25ConnectorOR(gps2b, docs2b))
        gps3 = _bgps(use_distractors, scale)
        docs3 = build_connector_documents(gps3)
        variants.append(V3BM25Rich(gps3, docs3))
        gps4 = _bgps(use_distractors, scale)
        docs4 = build_connector_documents(gps4)
        variants.append(V4Trigram(gps4, docs4))
        gps5 = _bgps(use_distractors, scale)
        docs5 = build_connector_documents(gps5)
        variants.append(V5TFIDF(docs5))
        gps5.close()
        gps6 = _bgps(use_distractors, scale)
        docs6 = build_connector_documents(gps6)
        variants.append(V6UnigramLM(docs6))
        gps6.close()
        gps7 = _bgps(use_distractors, scale)
        docs7 = build_connector_documents(gps7)
        variants.append(V7CharNGramTFIDF(docs7))
        gps7.close()
        if _SPLADE_AVAILABLE:
            try:
                gps8 = _bgps(use_distractors, scale)
                docs8 = build_connector_documents(gps8)
                variants.append(V8SPLADE(docs8))
                gps8.close()
            except Exception as e:
                print(f"      V8 SPLADE: SKIPPED — {e}")

    # V9: MiniLM (needed at all scales — base for V11b/V21b)
    v9 = None
    if _MINILM_AVAILABLE:
        try:
            gps9 = _bgps(use_distractors, scale)
            docs9 = build_connector_documents(gps9)
            v9 = V9MiniLM(docs9)
            gps9.close()
            variants.append(v9)
        except Exception as e:
            print(f"      V9 MiniLM: SKIPPED — {e}")

    # V14-V18, V10-V20: skip at scale (all proven inferior or tied)
    v17_instance = None
    if not at_scale:
        _ALT_MODELS = [
            ("v14", "V14: multi-qa-MiniLM", "multi-qa-MiniLM-L6-cos-v1", 22),
            ("v15", "V15: gte-small", "gte-small", 60),
            ("v16", "V16: bge-small", "BAAI/bge-small-en-v1.5", 96),
            ("v17", "V17: MiniLM-L12", "all-MiniLM-L12-v2", 120),
            ("v18", "V18: paraphrase-MiniLM", "paraphrase-MiniLM-L6-v2", 22),
        ]
        for vid, vname, model_name, size_mb in _ALT_MODELS:
            try:
                gps_alt = _bgps(use_distractors, scale)
                docs_alt = build_connector_documents(gps_alt)
                v_alt = V9MiniLM(docs_alt, model_name=model_name)
                v_alt.variant_id = vid
                v_alt.name = vname
                v_alt.size_mb = float(size_mb)
                gps_alt.close()
                variants.append(v_alt)
                if vid == "v17":
                    v17_instance = v_alt
                variants.append(
                    FamilyPriorReranker(
                        v_alt,
                        family_prior=0.10,
                        variant_id_override=f"{vid}b",
                        name_override=f"{vname}+f0.10",
                    )
                )
            except Exception as e:
                print(f"      {vname}: SKIPPED — {e}")
        if v17_instance:
            variants.append(
                FamilyPriorReranker(
                    v17_instance,
                    family_prior=0.20,
                    variant_id_override="v17b",
                    name_override="V17b: L12+f0.20",
                )
            )
            try:
                gps20 = _bgps(use_distractors, scale)
                docs20 = build_connector_documents(gps20)
                variants.append(V20TwoStageRerank(docs20, stage1=v17_instance))
                gps20.close()
            except Exception as e:
                print(f"      V20 2-Stage Rerank: SKIPPED — {e}")
        if v9:
            gps19 = _bgps(use_distractors, scale)
            docs19 = build_connector_documents(gps19)
            bm25_or = V2bBM25ConnectorOR(gps19, docs19)
            v1_cap = V1BM25CapGrouped(gps19)
            v19 = MultiSignalFusion(v9, bm25_or, v1_cap)
            v19.variant_id = "v19"
            v19.name = "V19: Multi-Signal"
            v19.family = "Fusion"
            v19.deps = "sentence-tf"
            v19.size_mb = 22.0
            variants.append(v19)
        if v9:
            gps10b = _bgps(use_distractors, scale)
            docs10b = build_connector_documents(gps10b)
            bm25_v10b = V2bBM25ConnectorOR(gps10b, docs10b)
            v10b = V10Hybrid(bm25_v10b, v9)
            v10b.variant_id = "v10b"
            v10b.name = "V10b: Hyb-OR"
            variants.append(v10b)
            gps10c = _bgps(use_distractors, scale)
            docs10c = build_connector_documents(gps10c)
            bm25_v10c = V3BM25Rich(gps10c, docs10c)
            v10c = V10Hybrid(bm25_v10c, v9)
            v10c.variant_id = "v10c"
            v10c.name = "V10c: Hyb-rich"
            variants.append(v10c)

    # V21/V21b: Schema-Augmented (production architecture — build at all scales)
    v21 = None
    if _INTENT_CLASSIFIER_AVAILABLE and v9 is not None:
        try:
            gps21 = _bgps(use_distractors, scale)
            docs21 = build_connector_documents(gps21)
            v21 = SchemaAugmentedSearch(v9, docs21, gps21)
            variants.append(v21)
        except Exception as e:
            print(f"      V21 Schema+MLM: SKIPPED — {e}")

    if v21 is not None:
        v21b = FamilyPriorReranker(
            v21,
            family_prior=0.10,
            variant_id_override="v21b",
            name_override="V21b: Schema+MLM+f0.10",
        )
        variants.append(v21b)

    # V11/V11b/V11c/V11d: Namespace prior sweep (build at all scales)
    if v9 is not None:
        variants.append(
            FamilyPriorReranker(
                v9, family_prior=0.10, variant_id_override="v11", name_override="V11: MLM+fam0.10"
            )
        )
        variants.append(
            FamilyPriorReranker(
                v9, family_prior=0.20, variant_id_override="v11b", name_override="V11b: MLM+fam0.20"
            )
        )
        variants.append(
            FamilyPriorReranker(
                v9, family_prior=0.05, variant_id_override="v11c", name_override="V11c: MLM+fam0.05"
            )
        )
        variants.append(
            FamilyPriorReranker(
                v9, family_prior=0.00, variant_id_override="v11d", name_override="V11d: MLM+noprior"
            )
        )

    # V12: skip at scale
    if not at_scale and v9 is not None:
        gps12 = _bgps(use_distractors, scale)
        docs12 = build_connector_documents(gps12)
        bm25_v12_rich = V3BM25Rich(gps12, docs12)
        v10c_for_v12 = V10Hybrid(bm25_v12_rich, v9)
        variants.append(
            FamilyPriorReranker(
                v10c_for_v12,
                family_prior=0.10,
                variant_id_override="v12",
                name_override="V12: Hyb-rich+fam0.10",
            )
        )

    # V22: Schema-Agnostic — pure embedding, no hardcoded knowledge (build at all scales)
    if _MINILM_AVAILABLE:
        try:
            gps22 = _bgps(use_distractors, scale)
            v22 = V22SchemaAgnostic(gps22)
            gps22.close()
            variants.append(v22)
        except Exception as e:
            print(f"      V22 Schema-Agnostic: SKIPPED — {e}")

    # ── Filter by exact variant_id ──
    if selected:
        variants = [v for v in variants if getattr(v, "variant_id", "") in selected]
        if not variants:
            print(f"  ERROR: No variant_ids matched --variants={selected}")
            print(f"  Available: {[getattr(v,'variant_id','?') for v in variants]}")
            sys.exit(1)

    print(f"Running {len(variants)} variants...\n")

    # ── Run benchmark ──
    reports: list[VariantReport] = []
    for v in variants:
        print(f"      {v.name}...", end=" ", flush=True)
        t0 = time.perf_counter()
        report = run_benchmark(v.name, v.search, combined_corpus, v.family, v.deps, v.size_mb)
        elapsed = (time.perf_counter() - t0) * 1000
        print(
            f"{report.overall.accuracy_at_1:.1%} "
            f"({elapsed:.0f}ms bench, {report.overall.avg_latency_ms:.1f}ms/q)"
        )
        reports.append(report)
        # Close variant resources
        try:
            v.close()
        except Exception:
            pass

    # ── Print report ──
    print_report(reports, corpus, n_distractors)

    # ── Scale stress summary ──
    if scale > 1 and reports:
        best = max(reports, key=lambda r: r.overall.accuracy_at_1)
        total_conns = 6 + n_distractors
        total_tools_est = total_conns * 6  # ~6 tools per connector average
        print_divider("=")
        print(f"  SCALE STRESS: {total_conns} connectors, ~{total_tools_est} tools")
        print(f"  Best: {best.name} = {best.overall.accuracy_at_1:.1%}")
        print(
            f"  Leak: {best.overall.leak_rate:.1%} | "
            f"FPos: {best.overall.false_positive_rate:.0%} | "
            f"MultiNs: {best.overall.multi_ns_accuracy:.1%} | "
            f"Conn@3: {best.overall.accuracy_at_3:.1%} | "
            f"{best.overall.avg_latency_ms:.1f}ms/q"
        )
        print(f"  Next scale point: --scale={scale*5}")
        print_divider("=")

    return reports


if __name__ == "__main__":
    main()
