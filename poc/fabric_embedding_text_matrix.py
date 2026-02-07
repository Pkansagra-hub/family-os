"""
Fabric Embedding Text Matrix -- What text produces best retrieval?

Tests 8 different text-to-embed strategies for Fabric contracts
and measures Recall@5, MRR, and per-query accuracy.

Goal: Determine the optimal text format for FAB-002 ADR.

Reference:
  - k1/fabric/fabric_discussion.md Section 7: "{description} | {capabilities}"
  - poc/fabric_embedding_retrieval_poc.py: baseline results
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

# ---------------------------------------------------------------------------
# Load UltraBERT
# ---------------------------------------------------------------------------
print("Loading UltraBERT...", end=" ", flush=True)
t0 = time.perf_counter()

from k0.runtime.ultrabert_adapter import get_embedding, get_ultrabert_client, is_ultrabert_available

client = get_ultrabert_client()
if client is None or not is_ultrabert_available():
    print("FAILED")
    sys.exit(1)
print(f"v{client.VERSION} ready ({(time.perf_counter() - t0) * 1000:.0f}ms)")


# ---------------------------------------------------------------------------
# Contract definitions (same catalog as baseline PoC)
# ---------------------------------------------------------------------------
@dataclass
class Contract:
    name: str
    contract_type: str
    description: str
    capabilities: list[str]
    domain: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


CONTRACTS: list[Contract] = [
    Contract(
        "tool.execute.restaurant_booking",
        "tool",
        "Books a restaurant reservation for family dining",
        ["reserve_table", "check_availability", "cancel_reservation"],
        ["FOOD", "EVENTS"],
        ["does not handle payment", "max 20 guests"],
    ),
    Contract(
        "tool.execute.grocery_list",
        "tool",
        "Manages family grocery shopping list with items, quantities, and store preferences",
        ["add_item", "remove_item", "get_list", "suggest_recipes"],
        ["FOOD", "SHOPPING"],
        ["no delivery scheduling"],
    ),
    Contract(
        "tool.execute.calendar_event",
        "tool",
        "Creates and manages family calendar events including recurring schedules",
        ["create_event", "update_event", "delete_event", "find_free_slots", "recurring_schedule"],
        ["SCHEDULING", "FAMILY"],
        ["no cross-platform calendar sync"],
    ),
    Contract(
        "tool.execute.homework_tracker",
        "tool",
        "Tracks children homework assignments, due dates, and completion status",
        ["add_assignment", "mark_complete", "list_pending", "send_reminder"],
        ["EDUCATION", "CHILDREN"],
        ["no tutoring"],
    ),
    Contract(
        "tool.execute.medication_reminder",
        "tool",
        "Manages medication schedules and sends reminders for family members",
        ["add_medication", "set_schedule", "check_interactions", "refill_alert"],
        ["HEALTH", "FAMILY"],
        ["not medical advice"],
    ),
    Contract(
        "tool.execute.budget_tracker",
        "tool",
        "Tracks family budget with income, expenses, categories, and savings goals",
        ["log_expense", "set_budget", "generate_report", "spending_alert"],
        ["FINANCE", "FAMILY"],
        ["no tax filing"],
    ),
    Contract(
        "tool.execute.ride_booking",
        "tool",
        "Books rides and transportation for family members including school pickups",
        ["book_ride", "schedule_pickup", "track_ride", "estimate_fare"],
        ["TRANSPORT", "FAMILY"],
        ["no vehicle maintenance"],
    ),
    Contract(
        "tool.execute.weather_forecast",
        "tool",
        "Gets weather forecast for planning outdoor family activities",
        ["current_weather", "weekly_forecast", "severe_alerts", "activity_suggestions"],
        ["WEATHER", "EVENTS"],
        [],
    ),
    Contract(
        "tool.execute.recipe_finder",
        "tool",
        "Finds recipes based on available ingredients, dietary restrictions, and family preferences",
        ["search_recipes", "filter_allergies", "meal_plan", "nutrition_info"],
        ["FOOD", "HEALTH"],
        ["no cooking instructions beyond recipe"],
    ),
    Contract(
        "tool.execute.photo_album",
        "tool",
        "Organizes and manages family photo albums with tagging and sharing",
        ["upload_photo", "create_album", "tag_family_member", "share_album"],
        ["MEMORIES", "FAMILY"],
        [],
    ),
    Contract(
        "tool.execute.bedtime_story",
        "tool",
        "Generates personalized bedtime stories for children based on their interests",
        ["generate_story", "continue_story", "list_themes", "save_favorite"],
        ["CHILDREN", "ENTERTAINMENT"],
        [],
    ),
    Contract(
        "tool.execute.chore_chart",
        "tool",
        "Manages family chore assignments and tracks completion with reward points",
        ["assign_chore", "mark_done", "view_chart", "redeem_points"],
        ["FAMILY", "ORGANIZATION"],
        ["no real currency"],
    ),
    Contract(
        "tool.execute.emergency_contacts",
        "tool",
        "Manages emergency contact list and sends alerts in urgent situations",
        ["add_contact", "send_alert", "call_emergency", "share_location"],
        ["SAFETY", "FAMILY"],
        [],
    ),
    Contract(
        "tool.execute.pet_care",
        "tool",
        "Tracks pet feeding schedules, vet appointments, and medication for family pets",
        ["feeding_schedule", "vet_appointment", "medication_tracker", "grooming_reminder"],
        ["PETS", "FAMILY"],
        [],
    ),
    Contract(
        "tool.execute.travel_planner",
        "tool",
        "Plans family vacations with flights, hotels, activities, and packing lists",
        ["search_flights", "book_hotel", "plan_itinerary", "packing_list"],
        ["TRAVEL", "EVENTS"],
        [],
    ),
    Contract(
        "tool.execute.code_review",
        "tool",
        "Performs automated code review with static analysis and style checks",
        ["analyze_code", "check_style", "find_bugs", "suggest_fixes"],
        ["ENGINEERING", "CODE"],
        [],
    ),
    Contract(
        "tool.execute.stock_trading",
        "tool",
        "Executes stock market trades with real-time pricing and portfolio management",
        ["buy_stock", "sell_stock", "portfolio_view", "price_alert"],
        ["FINANCE", "TRADING"],
        [],
    ),
    Contract(
        "tool.execute.email_composer",
        "tool",
        "Composes and sends emails with templates and scheduling",
        ["compose_email", "send_email", "schedule_send", "use_template"],
        ["COMMUNICATION"],
        [],
    ),
    Contract(
        "agent.spawn.family_scheduler",
        "agent",
        "Coordinates complex family scheduling across multiple calendars and constraints",
        ["multi_calendar_sync", "conflict_resolution", "optimal_scheduling"],
        ["SCHEDULING", "FAMILY"],
        [],
    ),
    Contract(
        "agent.spawn.meal_planner",
        "agent",
        "Plans weekly family meals considering nutrition, budget, and preferences",
        ["weekly_plan", "shopping_list_generate", "nutrition_balance", "budget_aware"],
        ["FOOD", "HEALTH", "FAMILY"],
        [],
    ),
    Contract(
        "prompt.template.daily_briefing",
        "prompt",
        "Generates morning daily briefing for family with weather, events, and reminders",
        ["briefing_generate", "summarize_day", "priority_highlights"],
        ["FAMILY", "SCHEDULING"],
        [],
    ),
    Contract(
        "prompt.template.bedtime_routine",
        "prompt",
        "Guides evening bedtime routine for children with calming activities",
        ["routine_steps", "calming_activity", "sleep_timer"],
        ["CHILDREN", "HEALTH"],
        [],
    ),
]


# ---------------------------------------------------------------------------
# 8 text strategies to test
# ---------------------------------------------------------------------------
def _cap_natural(caps: list[str]) -> str:
    """Convert capability slugs to natural text: assign_chore -> assign chore."""
    return ", ".join(c.replace("_", " ") for c in caps)


def _domain_str(d: list[str]) -> str:
    return ", ".join(d).lower() if d else ""


STRATEGIES: dict[str, Callable[[Contract], str]] = {
    # S1: Original Fabric spec
    "S1: desc | caps": lambda c: f"{c.description} | {' '.join(c.capabilities)}",
    # S2: Description only (no capability list)
    "S2: desc only": lambda c: c.description,
    # S3: Natural-language capabilities (no underscores)
    "S3: desc | caps_natural": lambda c: f"{c.description} | {_cap_natural(c.capabilities)}",
    # S4: Add domain tags
    "S4: desc | caps | domain": lambda c: f"{c.description} | {' '.join(c.capabilities)} | {_domain_str(c.domain)}",
    # S5: Name + description + capabilities (slug->natural)
    "S5: name + desc + caps_natural": lambda c: f"{c.name.replace('.', ' ')}: {c.description}. Can: {_cap_natural(c.capabilities)}",
    # S6: Full contract sentence (description + caps_natural + domain + type)
    "S6: type + desc + caps_natural + domain": lambda c: (
        f"This {c.contract_type} {c.description.lower()}. "
        f"It can {_cap_natural(c.capabilities)}. "
        f"Domain: {_domain_str(c.domain)}."
    ),
    # S7: Description + domain only (no capabilities at all)
    "S7: desc + domain": lambda c: f"{c.description} [{_domain_str(c.domain)}]",
    # S8: Everything including limitations
    "S8: desc + caps_natural + domain + limits": lambda c: (
        f"{c.description}. "
        f"Capabilities: {_cap_natural(c.capabilities)}. "
        f"Domain: {_domain_str(c.domain)}. "
        + (f"Limitations: {', '.join(c.limitations)}." if c.limitations else "")
    ),
}


# ---------------------------------------------------------------------------
# Retrieval test queries (same as baseline)
# ---------------------------------------------------------------------------
TESTS: list[dict[str, Any]] = [
    {
        "id": "Q01",
        "query": "I need to book a restaurant for our family dinner this Saturday",
        "expected": ["tool.execute.restaurant_booking", "tool.execute.calendar_event"],
    },
    {
        "id": "Q02",
        "query": "what tools can help me plan weekly meals for my family with allergies",
        "expected": [
            "agent.spawn.meal_planner",
            "tool.execute.recipe_finder",
            "tool.execute.grocery_list",
        ],
    },
    {
        "id": "Q03",
        "query": "my kid has homework due tomorrow, help track it",
        "expected": ["tool.execute.homework_tracker"],
    },
    {
        "id": "Q04",
        "query": "schedule a vet appointment for our dog and set feeding reminders",
        "expected": ["tool.execute.pet_care", "tool.execute.calendar_event"],
    },
    {
        "id": "Q05",
        "query": "create a bedtime story for my 5 year old who likes dragons",
        "expected": ["tool.execute.bedtime_story", "prompt.template.bedtime_routine"],
    },
    {
        "id": "Q06",
        "query": "morning briefing for today with weather and schedule",
        "expected": ["prompt.template.daily_briefing", "tool.execute.weather_forecast"],
    },
    {
        "id": "Q07",
        "query": "track our family spending and set a monthly budget for groceries",
        "expected": ["tool.execute.budget_tracker", "tool.execute.grocery_list"],
    },
    {
        "id": "Q08",
        "query": "plan a family vacation to the beach with flights and hotel",
        "expected": ["tool.execute.travel_planner"],
    },
    {
        "id": "Q09",
        "query": "manage medication schedule for grandma and check drug interactions",
        "expected": ["tool.execute.medication_reminder"],
    },
    {
        "id": "Q10",
        "query": "assign chores to the kids and set up a reward system",
        "expected": ["tool.execute.chore_chart"],
    },
    {
        "id": "Q11",
        "query": "send emergency alert if child is not picked up from school",
        "expected": ["tool.execute.emergency_contacts", "tool.execute.ride_booking"],
    },
    {
        "id": "Q12",
        "query": "find free time slots for all family members next week",
        "expected": ["tool.execute.calendar_event", "agent.spawn.family_scheduler"],
    },
]

TOP_K = 5


# ---------------------------------------------------------------------------
# Run matrix
# ---------------------------------------------------------------------------
import faiss

# Embed queries once (same for all strategies)
print("\nEmbedding queries...", flush=True)
query_vecs: dict[str, np.ndarray] = {}
for test in TESTS:
    vec = get_embedding(test["query"])
    if vec is None:
        print(f"  FAILED to embed query: {test['id']}")
        sys.exit(1)
    q = np.array([vec], dtype=np.float32)
    faiss.normalize_L2(q)
    query_vecs[test["id"]] = q
print(f"  {len(query_vecs)} queries embedded")


# Per-strategy results
@dataclass
class StrategyResult:
    name: str
    recall_per_query: dict[str, float] = field(default_factory=dict)
    mrr_per_query: dict[str, float] = field(default_factory=dict)
    rank1_per_query: dict[str, str] = field(default_factory=dict)
    avg_embed_ms: float = 0.0

    @property
    def mean_recall(self) -> float:
        return (
            sum(self.recall_per_query.values()) / len(self.recall_per_query)
            if self.recall_per_query
            else 0
        )

    @property
    def mean_mrr(self) -> float:
        return (
            sum(self.mrr_per_query.values()) / len(self.mrr_per_query) if self.mrr_per_query else 0
        )

    @property
    def perfect_count(self) -> int:
        """Queries with 100% recall."""
        return sum(1 for r in self.recall_per_query.values() if r >= 1.0)

    @property
    def fail_count(self) -> int:
        """Queries with <50% recall."""
        return sum(1 for r in self.recall_per_query.values() if r < 0.5)


results: list[StrategyResult] = []

for strat_name, text_fn in STRATEGIES.items():
    print(f"\nTesting: {strat_name}", flush=True)
    sr = StrategyResult(name=strat_name)

    # Embed all contracts with this strategy
    embed_times: list[float] = []
    embeddings: list[np.ndarray] = []
    for c in CONTRACTS:
        text = text_fn(c)
        t = time.perf_counter()
        vec = get_embedding(text)
        embed_times.append((time.perf_counter() - t) * 1000)
        if vec is None:
            print(f"  FAILED: {c.name}")
            sys.exit(1)
        embeddings.append(np.array(vec, dtype=np.float32))

    sr.avg_embed_ms = sum(embed_times) / len(embed_times)

    # Build index
    matrix = np.vstack(embeddings)
    faiss.normalize_L2(matrix)
    idx = faiss.IndexFlatIP(768)
    idx.add(matrix)

    # Run queries
    for test in TESTS:
        expected = set(test["expected"])
        scores, indices = idx.search(query_vecs[test["id"]], TOP_K)
        retrieved = [CONTRACTS[i].name for i in indices[0]]

        found = expected & set(retrieved)
        recall = len(found) / len(expected) if expected else 0
        sr.recall_per_query[test["id"]] = recall

        mrr = 0.0
        for rank, name in enumerate(retrieved, 1):
            if name in expected:
                mrr = 1.0 / rank
                break
        sr.mrr_per_query[test["id"]] = mrr
        sr.rank1_per_query[test["id"]] = retrieved[0]

    results.append(sr)
    print(
        f"  Recall@5={sr.mean_recall:.1%}  MRR={sr.mean_mrr:.4f}  "
        f"Perfect={sr.perfect_count}  Fail={sr.fail_count}  Embed={sr.avg_embed_ms:.1f}ms"
    )


# ---------------------------------------------------------------------------
# Print full matrix
# ---------------------------------------------------------------------------
print()
print("=" * 120)
print("EMBEDDING TEXT STRATEGY MATRIX")
print("=" * 120)

# Header
query_ids = [t["id"] for t in TESTS]
header = f"{'Strategy':<38} {'Recall@5':>8} {'MRR':>6} {'OK':>3} {'FAIL':>4} {'ms':>5}"
for qid in query_ids:
    header += f" {qid:>4}"
print(header)
print("-" * 120)

# Sort by mean_recall descending
results.sort(key=lambda r: (r.mean_recall, r.mean_mrr), reverse=True)

for sr in results:
    row = f"{sr.name:<38} {sr.mean_recall:>7.1%} {sr.mean_mrr:>6.4f} {sr.perfect_count:>3} {sr.fail_count:>4} {sr.avg_embed_ms:>4.0f}ms"
    for qid in query_ids:
        r = sr.recall_per_query.get(qid, 0)
        if r >= 1.0:
            cell = "100%"
        elif r >= 0.5:
            cell = f"{r:.0%}"
        elif r > 0:
            cell = f"{r:.0%}"
        else:
            cell = " 0%"
        row += f" {cell:>4}"
    print(row)

print("-" * 120)

# Best strategy
best = results[0]
print(f"\nBEST STRATEGY: {best.name}")
print(
    f"  Recall@5: {best.mean_recall:.1%} | MRR: {best.mean_mrr:.4f} | "
    f"Perfect: {best.perfect_count}/12 | Fails: {best.fail_count}/12"
)

# ---------------------------------------------------------------------------
# Per-query detail for the failing queries across strategies
# ---------------------------------------------------------------------------
print()
print("=" * 120)
print("PER-QUERY DETAIL: Which strategies fix which queries?")
print("=" * 120)

for test in TESTS:
    qid = test["id"]
    exp = test["expected"]
    # Check if any strategy failed this query
    any_fail = any(sr.recall_per_query[qid] < 0.5 for sr in results)
    any_perfect = any(sr.recall_per_query[qid] >= 1.0 for sr in results)

    if any_fail or not any_perfect:
        print(f"\n  {qid}: \"{test['query'][:65]}\"")
        print(f"    Expected: {exp}")
        for sr in results:
            r = sr.recall_per_query[qid]
            m = sr.mrr_per_query[qid]
            mark = "PASS" if r >= 0.5 else "FAIL"
            star = " ***" if r >= 1.0 else ""
            print(
                f"    [{mark}] {sr.name:<38} Recall={r:.0%} MRR={m:.2f} Rank1={sr.rank1_per_query[qid]}{star}"
            )


# ---------------------------------------------------------------------------
# Show sample embedding text for each strategy (one contract example)
# ---------------------------------------------------------------------------
print()
print("=" * 120)
print("SAMPLE EMBEDDING TEXT (tool.execute.chore_chart -- worst case from baseline)")
print("=" * 120)

sample = next(c for c in CONTRACTS if c.name == "tool.execute.chore_chart")
for strat_name, text_fn in STRATEGIES.items():
    text = text_fn(sample)
    print(f"\n  {strat_name}:")
    print(f'    "{text}"')


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------
print()
print("=" * 120)
print("RECOMMENDATION FOR FAB-002")
print("=" * 120)
print()
print("Use these results to decide the embedding text format for Fabric'  ")
print("contracts. The best strategy should be adopted as the standard in")
print("the CapabilityRegistry.embedding_text property.")
print()
print("Winner rankings:")
for i, sr in enumerate(results[:3], 1):
    print(f"  #{i}: {sr.name} -- Recall@5={sr.mean_recall:.1%}, MRR={sr.mean_mrr:.4f}")
print()
print("Key factors:")
print("  - Natural-language capabilities (no underscores) generally help")
print("  - Domain tags add signal for domain-specific queries")
print("  - Contract type prefix helps disambiguate tools vs agents vs prompts")
print("  - Limitations add noise; rarely help retrieval")
print("=" * 120)
