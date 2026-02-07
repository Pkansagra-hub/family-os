"""
Fabric Embedding Retrieval PoC -- UltraBERT + FAISS

Tests whether UltraBERT 768-dim embeddings can support Fabric's
semantic retrieval engine (Role 1: Intelligent Retrieval for Planner).

Scope:
  1. Load UltraBERT model
  2. Embed sample Tool/Agent/Prompt contracts using Fabric's format:
       f"{contract.description} | {' '.join(contract.capabilities)}"
  3. Build FAISS flat index (768-dim)
  4. Run retrieval queries the Planner would actually send
  5. Measure latency and retrieval quality (Top-K recall)

Reference:
  - k1/fabric/fabric_discussion.md Section 7-8 (Embedding Index, Retrieval Engine)
  - k0/runtime/ultrabert_adapter.py: get_embedding()
  - ADR: FAB-002 (Embedding Model Selection)
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# 1. Load UltraBERT
# ---------------------------------------------------------------------------
print("=" * 70)
print("STEP 1: Loading UltraBERT")
print("=" * 70)

t0 = time.perf_counter()

try:
    from k0.runtime.ultrabert_adapter import (
        get_embedding,
        get_ultrabert_client,
        is_ultrabert_available,
    )

    client = get_ultrabert_client()
    if client is None or not is_ultrabert_available():
        print("ERROR: UltraBERT not available. Exiting.")
        sys.exit(1)

    load_ms = (time.perf_counter() - t0) * 1000
    print(f"  UltraBERT loaded: version={client.VERSION}, backend={client.backend}")
    print(f"  Capabilities: {len(client.capabilities)}")
    print(f"  Load time: {load_ms:.1f}ms")
except ImportError as e:
    print(f"ERROR: Cannot import UltraBERT: {e}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 2. Sample Fabric Contracts (realistic tool/agent/prompt catalog)
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("STEP 2: Sample Fabric Contracts")
print("=" * 70)


@dataclass
class FabricContract:
    """Minimal contract for embedding test."""

    name: str
    contract_type: str  # tool, agent, prompt
    description: str
    capabilities: list[str]
    domain: list[str] = field(default_factory=list)

    @property
    def embedding_text(self) -> str:
        """Text to embed per Fabric spec (Section 7)."""
        return f"{self.description} | {' '.join(self.capabilities)}"


# -- TOOLS (22 realistic tool contracts) --
SAMPLE_CONTRACTS: list[FabricContract] = [
    # Family domain tools
    FabricContract(
        name="tool.execute.restaurant_booking",
        contract_type="tool",
        description="Books a restaurant reservation for family dining",
        capabilities=["reserve_table", "check_availability", "cancel_reservation"],
        domain=["FOOD", "EVENTS"],
    ),
    FabricContract(
        name="tool.execute.grocery_list",
        contract_type="tool",
        description="Manages family grocery shopping list with items, quantities, and store preferences",
        capabilities=["add_item", "remove_item", "get_list", "suggest_recipes"],
        domain=["FOOD", "SHOPPING"],
    ),
    FabricContract(
        name="tool.execute.calendar_event",
        contract_type="tool",
        description="Creates and manages family calendar events including recurring schedules",
        capabilities=[
            "create_event",
            "update_event",
            "delete_event",
            "find_free_slots",
            "recurring_schedule",
        ],
        domain=["SCHEDULING", "FAMILY"],
    ),
    FabricContract(
        name="tool.execute.homework_tracker",
        contract_type="tool",
        description="Tracks children homework assignments, due dates, and completion status",
        capabilities=["add_assignment", "mark_complete", "list_pending", "send_reminder"],
        domain=["EDUCATION", "CHILDREN"],
    ),
    FabricContract(
        name="tool.execute.medication_reminder",
        contract_type="tool",
        description="Manages medication schedules and sends reminders for family members",
        capabilities=["add_medication", "set_schedule", "check_interactions", "refill_alert"],
        domain=["HEALTH", "FAMILY"],
    ),
    FabricContract(
        name="tool.execute.budget_tracker",
        contract_type="tool",
        description="Tracks family budget with income, expenses, categories, and savings goals",
        capabilities=["log_expense", "set_budget", "generate_report", "spending_alert"],
        domain=["FINANCE", "FAMILY"],
    ),
    FabricContract(
        name="tool.execute.ride_booking",
        contract_type="tool",
        description="Books rides and transportation for family members including school pickups",
        capabilities=["book_ride", "schedule_pickup", "track_ride", "estimate_fare"],
        domain=["TRANSPORT", "FAMILY"],
    ),
    FabricContract(
        name="tool.execute.weather_forecast",
        contract_type="tool",
        description="Gets weather forecast for planning outdoor family activities",
        capabilities=[
            "current_weather",
            "weekly_forecast",
            "severe_alerts",
            "activity_suggestions",
        ],
        domain=["WEATHER", "EVENTS"],
    ),
    FabricContract(
        name="tool.execute.recipe_finder",
        contract_type="tool",
        description="Finds recipes based on available ingredients, dietary restrictions, and family preferences",
        capabilities=["search_recipes", "filter_allergies", "meal_plan", "nutrition_info"],
        domain=["FOOD", "HEALTH"],
    ),
    FabricContract(
        name="tool.execute.photo_album",
        contract_type="tool",
        description="Organizes and manages family photo albums with tagging and sharing",
        capabilities=["upload_photo", "create_album", "tag_family_member", "share_album"],
        domain=["MEMORIES", "FAMILY"],
    ),
    FabricContract(
        name="tool.execute.bedtime_story",
        contract_type="tool",
        description="Generates personalized bedtime stories for children based on their interests",
        capabilities=["generate_story", "continue_story", "list_themes", "save_favorite"],
        domain=["CHILDREN", "ENTERTAINMENT"],
    ),
    FabricContract(
        name="tool.execute.chore_chart",
        contract_type="tool",
        description="Manages family chore assignments and tracks completion with reward points",
        capabilities=["assign_chore", "mark_done", "view_chart", "redeem_points"],
        domain=["FAMILY", "ORGANIZATION"],
    ),
    FabricContract(
        name="tool.execute.emergency_contacts",
        contract_type="tool",
        description="Manages emergency contact list and sends alerts in urgent situations",
        capabilities=["add_contact", "send_alert", "call_emergency", "share_location"],
        domain=["SAFETY", "FAMILY"],
    ),
    FabricContract(
        name="tool.execute.pet_care",
        contract_type="tool",
        description="Tracks pet feeding schedules, vet appointments, and medication for family pets",
        capabilities=[
            "feeding_schedule",
            "vet_appointment",
            "medication_tracker",
            "grooming_reminder",
        ],
        domain=["PETS", "FAMILY"],
    ),
    FabricContract(
        name="tool.execute.travel_planner",
        contract_type="tool",
        description="Plans family vacations with flights, hotels, activities, and packing lists",
        capabilities=["search_flights", "book_hotel", "plan_itinerary", "packing_list"],
        domain=["TRAVEL", "EVENTS"],
    ),
    # Non-family domain tools (noise -- should rank lower for family queries)
    FabricContract(
        name="tool.execute.code_review",
        contract_type="tool",
        description="Performs automated code review with static analysis and style checks",
        capabilities=["analyze_code", "check_style", "find_bugs", "suggest_fixes"],
        domain=["ENGINEERING", "CODE"],
    ),
    FabricContract(
        name="tool.execute.stock_trading",
        contract_type="tool",
        description="Executes stock market trades with real-time pricing and portfolio management",
        capabilities=["buy_stock", "sell_stock", "portfolio_view", "price_alert"],
        domain=["FINANCE", "TRADING"],
    ),
    FabricContract(
        name="tool.execute.email_composer",
        contract_type="tool",
        description="Composes and sends emails with templates and scheduling",
        capabilities=["compose_email", "send_email", "schedule_send", "use_template"],
        domain=["COMMUNICATION"],
    ),
    # Agents
    FabricContract(
        name="agent.spawn.family_scheduler",
        contract_type="agent",
        description="Coordinates complex family scheduling across multiple calendars and constraints",
        capabilities=["multi_calendar_sync", "conflict_resolution", "optimal_scheduling"],
        domain=["SCHEDULING", "FAMILY"],
    ),
    FabricContract(
        name="agent.spawn.meal_planner",
        contract_type="agent",
        description="Plans weekly family meals considering nutrition, budget, and preferences",
        capabilities=["weekly_plan", "shopping_list_generate", "nutrition_balance", "budget_aware"],
        domain=["FOOD", "HEALTH", "FAMILY"],
    ),
    # Prompts
    FabricContract(
        name="prompt.template.daily_briefing",
        contract_type="prompt",
        description="Generates morning daily briefing for family with weather, events, and reminders",
        capabilities=["briefing_generate", "summarize_day", "priority_highlights"],
        domain=["FAMILY", "SCHEDULING"],
    ),
    FabricContract(
        name="prompt.template.bedtime_routine",
        contract_type="prompt",
        description="Guides evening bedtime routine for children with calming activities",
        capabilities=["routine_steps", "calming_activity", "sleep_timer"],
        domain=["CHILDREN", "HEALTH"],
    ),
]

print(f"  Loaded {len(SAMPLE_CONTRACTS)} sample contracts")
for c in SAMPLE_CONTRACTS:
    print(f"    [{c.contract_type:6s}] {c.name}")


# ---------------------------------------------------------------------------
# 3. Generate Embeddings
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("STEP 3: Generating Embeddings with UltraBERT")
print("=" * 70)

embeddings: list[np.ndarray] = []
embed_times: list[float] = []

for contract in SAMPLE_CONTRACTS:
    text = contract.embedding_text
    t = time.perf_counter()
    vec = get_embedding(text)
    elapsed = (time.perf_counter() - t) * 1000
    embed_times.append(elapsed)

    if vec is None:
        print(f"  FAILED to embed: {contract.name}")
        sys.exit(1)

    arr = np.array(vec, dtype=np.float32)
    embeddings.append(arr)

dim = embeddings[0].shape[0]
avg_ms = sum(embed_times) / len(embed_times)
p95_ms = sorted(embed_times)[int(len(embed_times) * 0.95)]

print(f"  Embedding dimension: {dim}")
print(f"  Total embeddings: {len(embeddings)}")
print(f"  Avg latency: {avg_ms:.1f}ms")
print(f"  P95 latency: {p95_ms:.1f}ms")
print(f"  Min/Max: {min(embed_times):.1f}ms / {max(embed_times):.1f}ms")
print(f"  Total time: {sum(embed_times):.1f}ms")


# ---------------------------------------------------------------------------
# 4. Build FAISS Index
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("STEP 4: Building FAISS Index")
print("=" * 70)

import faiss

# Stack all embeddings into matrix
embed_matrix = np.vstack(embeddings)

# Normalize for cosine similarity (FAISS inner product on L2-normalized = cosine)
faiss.normalize_L2(embed_matrix)

# Build flat inner-product index (cosine similarity after normalization)
index = faiss.IndexFlatIP(dim)
index.add(embed_matrix)

print("  Index type: Flat Inner Product (cosine sim via L2-normalized vectors)")
print(f"  Dimension: {dim}")
print(f"  Vectors indexed: {index.ntotal}")


# ---------------------------------------------------------------------------
# 5. Retrieval Tests -- Queries the Planner Would Actually Send
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("STEP 5: Retrieval Tests (Planner-Style Queries)")
print("=" * 70)

# Each query has expected ground-truth relevant contracts (by name)
RETRIEVAL_TESTS: list[dict[str, Any]] = [
    {
        "query": "I need to book a restaurant for our family dinner this Saturday",
        "expected": ["tool.execute.restaurant_booking", "tool.execute.calendar_event"],
        "top_k": 5,
    },
    {
        "query": "what tools can help me plan weekly meals for my family with allergies",
        "expected": [
            "agent.spawn.meal_planner",
            "tool.execute.recipe_finder",
            "tool.execute.grocery_list",
        ],
        "top_k": 5,
    },
    {
        "query": "my kid has homework due tomorrow, help track it",
        "expected": ["tool.execute.homework_tracker"],
        "top_k": 5,
    },
    {
        "query": "schedule a vet appointment for our dog and set feeding reminders",
        "expected": ["tool.execute.pet_care", "tool.execute.calendar_event"],
        "top_k": 5,
    },
    {
        "query": "create a bedtime story for my 5 year old who likes dragons",
        "expected": ["tool.execute.bedtime_story", "prompt.template.bedtime_routine"],
        "top_k": 5,
    },
    {
        "query": "morning briefing for today with weather and schedule",
        "expected": ["prompt.template.daily_briefing", "tool.execute.weather_forecast"],
        "top_k": 5,
    },
    {
        "query": "track our family spending and set a monthly budget for groceries",
        "expected": ["tool.execute.budget_tracker", "tool.execute.grocery_list"],
        "top_k": 5,
    },
    {
        "query": "plan a family vacation to the beach with flights and hotel",
        "expected": ["tool.execute.travel_planner"],
        "top_k": 5,
    },
    {
        "query": "manage medication schedule for grandma and check drug interactions",
        "expected": ["tool.execute.medication_reminder"],
        "top_k": 5,
    },
    {
        "query": "assign chores to the kids and set up a reward system",
        "expected": ["tool.execute.chore_chart"],
        "top_k": 5,
    },
    {
        "query": "send emergency alert if child is not picked up from school",
        "expected": ["tool.execute.emergency_contacts", "tool.execute.ride_booking"],
        "top_k": 5,
    },
    {
        "query": "find free time slots for all family members next week",
        "expected": ["tool.execute.calendar_event", "agent.spawn.family_scheduler"],
        "top_k": 5,
    },
]


def search(query_text: str, top_k: int = 5) -> list[tuple[str, float, float]]:
    """Search the index. Returns [(contract_name, score, latency_ms)]."""
    t = time.perf_counter()
    qvec = get_embedding(query_text)
    embed_ms = (time.perf_counter() - t) * 1000

    if qvec is None:
        return []

    q = np.array([qvec], dtype=np.float32)
    faiss.normalize_L2(q)

    t = time.perf_counter()
    scores, indices = index.search(q, top_k)
    search_ms = (time.perf_counter() - t) * 1000

    results = []
    for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
        name = SAMPLE_CONTRACTS[idx].name
        results.append((name, float(score), embed_ms + search_ms))

    return results


# Run all retrieval tests
total_recall_at_k = 0
total_mrr = 0
all_latencies: list[float] = []

for i, test in enumerate(RETRIEVAL_TESTS, 1):
    query = test["query"]
    expected = set(test["expected"])
    top_k = test["top_k"]

    results = search(query, top_k)
    retrieved_names = [r[0] for r in results]

    # Recall@K: fraction of expected items found in top-K
    found = expected & set(retrieved_names)
    recall = len(found) / len(expected) if expected else 0
    total_recall_at_k += recall

    # MRR: reciprocal rank of first relevant result
    mrr = 0
    for rank, name in enumerate(retrieved_names, 1):
        if name in expected:
            mrr = 1.0 / rank
            break
    total_mrr += mrr

    latency = results[0][2] if results else 0
    all_latencies.append(latency)

    # Print results
    status = "PASS" if recall >= 0.5 else "FAIL"
    print(f'\n  [{status}] Query {i}: "{query[:60]}..."')
    print(f"    Expected: {sorted(expected)}")
    print(f"    Recall@{top_k}: {recall:.0%} | MRR: {mrr:.2f} | Latency: {latency:.1f}ms")
    for rank, (name, score, _) in enumerate(results, 1):
        marker = " <--" if name in expected else ""
        print(f"      #{rank}: {score:.4f}  {name}{marker}")

n = len(RETRIEVAL_TESTS)
avg_recall = total_recall_at_k / n
avg_mrr = total_mrr / n
avg_lat = sum(all_latencies) / len(all_latencies)


# ---------------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("STEP 6: Summary")
print("=" * 70)
print(f"  Model: UltraBERT v{client.VERSION}")
print(f"  Embedding Dim: {dim}")
print(f"  Contracts Indexed: {len(SAMPLE_CONTRACTS)}")
print(f"  Queries Run: {n}")
print()
print(f"  Mean Recall@5:  {avg_recall:.2%}")
print(f"  Mean MRR:       {avg_mrr:.4f}")
print(f"  Avg Embed+Search Latency: {avg_lat:.1f}ms")
print("  Target: <50ms per retrieval call (Fabric spec)")
print()

if avg_recall >= 0.7:
    print("  VERDICT: UltraBERT embeddings are SUITABLE for Fabric retrieval")
elif avg_recall >= 0.5:
    print("  VERDICT: UltraBERT embeddings are MARGINAL -- needs tuning")
else:
    print("  VERDICT: UltraBERT embeddings are INSUFFICIENT -- consider alternatives")

print()
print("  ADR Impact: Results inform FAB-002 (Embedding Model Selection)")
print("=" * 70)
