"""
10 test scenarios for the ReactLoopScratchpad benchmark.

Each scenario is designed to stress a specific capability that the scratchpad
architecture handles better than naive message passing.

Scenario Index:
  1. Context Stress   - 20 sequential research topics (40-60 iterations)
  2. Sub-Agent Spawn  - Main spawns 5 sub-agents doing research
  3. Budget Inherit   - 10 tool calls shared across 3 sub-agents
  4. Recovery         - Sub-agent fails, main retries with alternative
  5. Deep Nesting     - Main -> sub -> sub-sub -> sub-sub-sub
  6. Parallel Agents  - 3 simultaneous sub-agents
  7. Budget Recovery  - Unused budget returned from failed sub-agent
  8. Fact Retention   - Facts from iteration 3 needed at iteration 28
  9. Large Payloads   - Tools return 2,000-5,000 token outputs
 10. Concierge Full   - All 13 Concierge tools in a birthday dinner scenario
"""

from __future__ import annotations

from typing import List

from core.models import Checkpoint, Scenario, Tier
from tools.response_bank import RESEARCH_TOPICS

# ---------------------------------------------------------------------------
# Shared system prompts
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_PROMPT = (
    "You are a thorough research assistant. Use the available tools to gather "
    "information on each topic the user asks about. For EACH topic:\n"
    "1. Use web_search or deep_research to find information\n"
    "2. Record what you learn\n"
    "3. Move to the next topic\n"
    "When you have researched ALL topics, use final_answer to provide a comprehensive summary.\n"
    "Be systematic -- research topics ONE AT A TIME in the order given."
)

TRAVEL_SYSTEM_PROMPT = (
    "You are a travel planning assistant. Use the available tools to plan trips. "
    "Search for flights, hotels, weather, and other travel information. "
    "When you have enough information, use final_answer to present your plan."
)

AGENT_SYSTEM_PROMPT = (
    "You are a coordination agent that delegates tasks to sub-agents. "
    "Use spawn_agent to create specialized sub-agents for different research tasks. "
    "Each sub-agent should handle one specific topic or area. "
    "Monitor their status and synthesize their results. "
    "When all sub-agents complete, use final_answer to provide the combined result."
)

RECOVERY_SYSTEM_PROMPT = (
    "You are a resilient research assistant. Some tools may fail -- that is expected. "
    "When a tool fails, try an alternative approach or different tool. "
    "Do NOT retry the exact same call that failed. "
    "Track which approaches failed and adapt your strategy. "
    "Use final_answer when you have gathered enough information."
)


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------


def get_all_scenarios() -> List[Scenario]:
    """Return all 10 benchmark scenarios."""
    return [
        scenario_01_context_stress(),
        scenario_02_sub_agent_spawn(),
        scenario_03_budget_inheritance(),
        scenario_04_recovery(),
        scenario_05_deep_nesting(),
        scenario_06_parallel_agents(),
        scenario_07_budget_recovery(),
        scenario_08_fact_retention(),
        scenario_09_large_payloads(),
        scenario_10_concierge_full(),
    ]


def get_scenario_by_id(scenario_id: int) -> Scenario:
    """Get a specific scenario by number (1-10)."""
    scenarios = get_all_scenarios()
    if 1 <= scenario_id <= len(scenarios):
        return scenarios[scenario_id - 1]
    raise ValueError(f"Scenario {scenario_id} not found. Valid: 1-{len(scenarios)}")


# ---------------------------------------------------------------------------
# Test 1: Context Limit Stress Test
# ---------------------------------------------------------------------------


def scenario_01_context_stress() -> Scenario:
    """
    Research 20 topics sequentially.
    Each topic: 1-2 tool calls. Total: 20-40 tool calls.
    Naive: context grows forever, should struggle after 15-20 iterations.
    Smart: compacts old results, maintains findings, stays bounded.
    """
    topics = list(RESEARCH_TOPICS.keys())[:20]
    topic_list = "\n".join(f"{i+1}. {t.replace('_', ' ').title()}" for i, t in enumerate(topics))

    return Scenario(
        id="test_01_context_stress",
        name="Context Limit Stress Test",
        description="Research 20 topics sequentially to stress context limits",
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        user_query=(
            f"Research each of these 20 topics one at a time. "
            f"For each topic, use web_search to find key facts. "
            f"After researching ALL 20, use final_answer to summarize your findings.\n\n"
            f"Topics:\n{topic_list}"
        ),
        tier=Tier.HIGH,
        max_iterations=50,
        max_tools=45,
        checkpoints=[
            Checkpoint(
                iteration=5,
                check_type="finding_exists",
                key="quantum_computing",
                description="Should have quantum computing facts by iteration 5",
            ),
            Checkpoint(
                iteration=30,
                check_type="task_complete",
                description="Task should complete within 30 iterations",
            ),
            Checkpoint(
                iteration=30,
                check_type="context_bounded",
                expected_value=8000,
                description="Smart context should stay under 8K tokens",
            ),
        ],
        tags=["context_stress", "long_running", "core"],
    )


# ---------------------------------------------------------------------------
# Test 2: Sub-Agent Spawning
# ---------------------------------------------------------------------------


def scenario_02_sub_agent_spawn() -> Scenario:
    """
    Main agent spawns 5 sub-agents for different research tasks.
    Each sub-agent does 2-3 tool calls.
    Tests: sub-agent tracking, finding aggregation, budget management.
    """
    return Scenario(
        id="test_02_sub_agent_spawn",
        name="Sub-Agent Spawning",
        description="Main agent spawns 5 sub-agents for parallel research",
        system_prompt=AGENT_SYSTEM_PROMPT,
        user_query=(
            "I need research on 5 different topics. Spawn a separate sub-agent for each:\n"
            "1. Quantum Computing - latest developments and market size\n"
            "2. Electric Vehicles - sales figures and top manufacturers\n"
            "3. Renewable Energy - solar and wind capacity globally\n"
            "4. Space Exploration - upcoming missions and rockets\n"
            "5. Cybersecurity - major threats and market trends\n\n"
            "Give each sub-agent 3 tool calls. Synthesize their findings into a final report."
        ),
        tier=Tier.HIGH,
        max_iterations=25,
        max_tools=25,
        checkpoints=[
            Checkpoint(
                iteration=20,
                check_type="task_complete",
                description="Should complete with all 5 sub-agent results",
            ),
        ],
        tags=["sub_agents", "coordination", "core"],
    )


# ---------------------------------------------------------------------------
# Test 3: Nested Budget Inheritance
# ---------------------------------------------------------------------------


def scenario_03_budget_inheritance() -> Scenario:
    """
    Main agent has 10 tool calls total.
    Must spawn 3 sub-agents, each needing 3 tool calls.
    Tests: budget propagation, enforcement, no overspend.
    """
    return Scenario(
        id="test_03_budget_inheritance",
        name="Nested Budget Inheritance",
        description="10 tool calls shared across 3 sub-agents",
        system_prompt=(
            "You are a budget-conscious coordinator. You have exactly 10 tool calls total. "
            "Spawn 3 sub-agents to research topics. Give each agent 3 tool calls. "
            "You keep 1 for yourself. Do NOT overspend.\n"
            "When sub-agents complete, use final_answer to report results."
        ),
        user_query=(
            "Research these 3 areas using sub-agents (3 tool calls each):\n"
            "1. AI market trends\n"
            "2. Climate change data\n"
            "3. Biotechnology advances\n"
            "Stay within the 10 tool call budget."
        ),
        tier=Tier.MEDIUM,
        max_iterations=15,
        max_tools=10,
        checkpoints=[
            Checkpoint(
                iteration=15,
                check_type="budget_remaining",
                expected_value=0,
                description="Budget should be fully or nearly used",
            ),
        ],
        tags=["budget", "sub_agents", "core"],
    )


# ---------------------------------------------------------------------------
# Test 4: Recovery from Sub-Agent Failure
# ---------------------------------------------------------------------------


def scenario_04_recovery() -> Scenario:
    """
    First attempt uses flaky_api which fails.
    Agent must recognize failure, try alternative approach.
    Tests: failure tracking, adaptive strategy, error recovery.
    """
    return Scenario(
        id="test_04_recovery",
        name="Recovery from Failure",
        description="Handle tool failures and adapt strategy",
        system_prompt=RECOVERY_SYSTEM_PROMPT,
        user_query=(
            "Find premium flight options from SFO to London.\n"
            "Try the premium_flight_search endpoint via flaky_api first.\n"
            "If that fails, use the regular flight_search tool as fallback.\n"
            "Also check the weather in London.\n"
            "Provide the final answer with flights and weather."
        ),
        tier=Tier.MEDIUM,
        max_iterations=12,
        max_tools=8,
        checkpoints=[
            Checkpoint(
                iteration=10,
                check_type="task_complete",
                description="Should recover and complete despite failures",
            ),
        ],
        tags=["recovery", "error_handling", "core"],
    )


# ---------------------------------------------------------------------------
# Test 5: Deep Nesting
# ---------------------------------------------------------------------------


def scenario_05_deep_nesting() -> Scenario:
    """
    Main -> sub-agent -> sub-sub-agent -> sub-sub-sub-agent.
    Each level does real work (research different topics).
    Results bubble back up through the hierarchy.
    """
    return Scenario(
        id="test_05_deep_nesting",
        name="Deep Nesting (4 Levels)",
        description="Main -> sub -> sub-sub -> sub-sub-sub agent hierarchy",
        system_prompt=(
            "You are a hierarchical research coordinator.\n"
            "Your task requires delegation at multiple levels:\n"
            "1. You (Level 0) coordinate the overall research\n"
            "2. Spawn a sub-agent (Level 1) for 'Technology Trends'\n"
            "3. That sub-agent should spawn its own sub-agent (Level 2) for 'AI Specifics'\n"
            "4. Level 2 should spawn Level 3 for 'LLM Market Data'\n"
            "Each level should do at least 1 tool call and pass results up.\n"
            "When all results bubble up, use final_answer."
        ),
        user_query=(
            "Research technology trends with multi-level delegation:\n"
            "- Level 1: Broad technology trends (spawn sub-agent for AI)\n"
            "- Level 2: AI specifics (spawn sub-agent for LLM data)\n"
            "- Level 3: LLM market data (use web_search)\n"
            "Synthesize all nested results into a final report."
        ),
        tier=Tier.HIGH,
        max_iterations=20,
        max_tools=20,
        checkpoints=[
            Checkpoint(
                iteration=20,
                check_type="task_complete",
                description="Should complete with nested results",
            ),
        ],
        tags=["deep_nesting", "sub_agents", "hierarchy"],
    )


# ---------------------------------------------------------------------------
# Test 6: Parallel Sub-Agents
# ---------------------------------------------------------------------------


def scenario_06_parallel_agents() -> Scenario:
    """
    Main spawns 3 sub-agents for independent research.
    Each does 2-3 tool calls independently.
    Main waits for all, then synthesizes.
    Tests: parallel state tracking, independent findings.
    """
    return Scenario(
        id="test_06_parallel_agents",
        name="Parallel Sub-Agents",
        description="3 sub-agents doing independent research simultaneously",
        system_prompt=AGENT_SYSTEM_PROMPT,
        user_query=(
            "Plan a multi-city trip. Spawn 3 sub-agents:\n"
            "1. Agent for Paris: Find weather and hotels\n"
            "2. Agent for Tokyo: Find weather and hotels\n"
            "3. Agent for New York: Find weather and hotels\n"
            "Give each 3 tool calls. Combine all results into a trip plan."
        ),
        tier=Tier.HIGH,
        max_iterations=18,
        max_tools=15,
        checkpoints=[
            Checkpoint(
                iteration=18,
                check_type="task_complete",
                description="Should synthesize all 3 city results",
            ),
        ],
        tags=["parallel", "sub_agents", "travel"],
    )


# ---------------------------------------------------------------------------
# Test 7: Budget Sharing & Recovery
# ---------------------------------------------------------------------------


def scenario_07_budget_recovery() -> Scenario:
    """
    Main has 15 tool calls.
    Spawns 3 sub-agents with 4 each (12 allocated).
    One sub-agent fails at 2 calls -- 2 should return to parent.
    Tests: budget reallocation, unused budget recovery.
    """
    return Scenario(
        id="test_07_budget_recovery",
        name="Budget Sharing & Recovery",
        description="Budget returned from failed sub-agent and reused",
        system_prompt=(
            "You coordinate 3 research sub-agents with a shared budget of 15 tool calls.\n"
            "Give each sub-agent 4 tool calls.\n"
            "One sub-agent's task will involve a flaky API that may fail.\n"
            "If a sub-agent fails, its unused budget should be recoverable.\n"
            "Use final_answer when done."
        ),
        user_query=(
            "Research with 3 sub-agents (4 tool calls each):\n"
            "1. Agent for flight research (use flight_search)\n"
            "2. Agent for weather research (use weather_api for 3 cities)\n"
            "3. Agent for premium services (use flaky_api -- may fail!)\n"
            "Report combined results."
        ),
        tier=Tier.HIGH,
        max_iterations=20,
        max_tools=15,
        checkpoints=[
            Checkpoint(
                iteration=20,
                check_type="task_complete",
                description="Should complete with partial results",
            ),
        ],
        tags=["budget", "recovery", "sub_agents"],
    )


# ---------------------------------------------------------------------------
# Test 8: Long-Term Fact Retention
# ---------------------------------------------------------------------------


def scenario_08_fact_retention() -> Scenario:
    """
    30-iteration research task.
    Facts discovered in early iterations needed at the end.
    Tests: structured findings persist across compactions.

    Key assertion: fact from iteration 3 (capital of France = Paris)
    must be available at iteration 28+ when asked to cross-reference.
    """
    topics = list(RESEARCH_TOPICS.keys())[:15]
    topic_list = "\n".join(f"{i+1}. {t.replace('_', ' ').title()}" for i, t in enumerate(topics))

    return Scenario(
        id="test_08_fact_retention",
        name="Long-Term Fact Retention",
        description="Facts from early iterations must be retained and recalled later",
        system_prompt=(
            "You are a meticulous researcher. For each topic:\n"
            "1. Use web_search to find key facts\n"
            "2. Note the most important number or fact from each topic\n"
            "3. After researching all topics, I will ask cross-reference questions\n\n"
            "CRITICAL: You must remember facts from earlier research when answering "
            "cross-reference questions later. Do NOT re-search topics you already covered."
        ),
        user_query=(
            f"Research these 15 topics one at a time:\n{topic_list}\n\n"
            "After researching all 15, answer these cross-reference questions:\n"
            "Q1: What is the market size of quantum computing by 2030?\n"
            "Q2: How many EV sales were there in 2024?\n"
            "Q3: What percentage did solar capacity grow in 2024?\n"
            "Q4: What is the current CO2 level in ppm?\n"
            "Q5: How many countries are exploring CBDCs?\n\n"
            "Use final_answer with answers to all 5 questions. "
            "Do NOT re-search -- use facts you already discovered."
        ),
        tier=Tier.HIGH,
        max_iterations=35,
        max_tools=30,
        checkpoints=[
            Checkpoint(
                iteration=5,
                check_type="finding_exists",
                key="quantum_computing",
                description="Quantum computing should be researched early",
            ),
            Checkpoint(
                iteration=30,
                check_type="task_complete",
                description="Should complete with cross-reference answers",
            ),
            Checkpoint(
                iteration=30,
                check_type="context_bounded",
                expected_value=10000,
                description="Smart context should stay under 10K tokens despite 30 iterations",
            ),
        ],
        tags=["fact_retention", "long_running", "core"],
    )


# ---------------------------------------------------------------------------
# Test 9: Large Tool Output Handling
# ---------------------------------------------------------------------------


def scenario_09_large_payloads() -> Scenario:
    """
    Tools return 2,000-5,000 tokens of structured data each.

    Three tool calls producing massive outputs:
      - search_database_large (customer_history): ~3,500 tokens (200 records)
      - analytics_report (purchase_analytics): ~4,200 tokens (segments + trends)
      - vector_search (similar documents): ~2,800 tokens (100 results)

    Naive runner: context explodes to 10,000+ tokens after just 3 tool calls,
    the LLM must process all that raw data on every subsequent turn.

    Smart runner: extracts key findings from each massive output (#5-10 facts),
    stores only the digest (~50-100 tokens) in messages, discards raw data.
    Context stays flat and bounded regardless of payload size.

    This is the scenario that proves the scratchpad's real-world value:
    production tools routinely return 2K-10K tokens of raw JSON.
    """
    return Scenario(
        id="test_09_large_payloads",
        name="Large Tool Output Handling",
        description="Tools return 2,000-5,000 tokens of structured data per call",
        system_prompt=(
            "You are a data analyst. You have access to tools that return LARGE datasets.\n"
            "Your job is to extract key insights and trends from the data.\n"
            "Do NOT repeat or echo raw data in your responses.\n"
            "Focus on: top-level metrics, key trends, actionable insights.\n"
            "When you have enough insights from all three data sources, "
            "use final_answer to provide a concise executive summary."
        ),
        user_query=(
            "Perform a comprehensive data analysis:\n"
            "1. Pull the customer_history dataset (5 years of customer records)\n"
            "2. Generate a purchase_analytics report for the last 12 months\n"
            "3. Run a vector search for 'machine learning deployment best practices'\n"
            "4. Synthesize key insights from all three data sources\n\n"
            "Provide an executive summary with:\n"
            "- Top revenue metrics\n"
            "- Key customer segments\n"
            "- Most relevant research papers\n"
            "- Actionable recommendations"
        ),
        tier=Tier.HIGH,
        max_iterations=10,
        max_tools=5,
        checkpoints=[
            Checkpoint(
                iteration=5,
                check_type="context_bounded",
                expected_value=5000,
                description=(
                    "Smart context must stay under 5K tokens despite "
                    "3 tool outputs totaling ~10,500 raw tokens"
                ),
            ),
            Checkpoint(
                iteration=8,
                check_type="task_complete",
                description="Should complete within 8 iterations",
            ),
        ],
        tags=["large_payloads", "efficiency", "core"],
    )


# ---------------------------------------------------------------------------
# Test 10: Concierge Full Tool Suite (13 tools, real SessionState)
# ---------------------------------------------------------------------------


def scenario_10_concierge_full() -> Scenario:
    """
    Birthday dinner planning exercising ALL 15 Concierge tools.

    Uses the ConciergeToolRegistry backed by real SessionState.

    Tool coverage (15 tools across 4 categories):
    - Signal:    acknowledge (commit, progress, closure)
    - Cognitive: update_scoreboard, update_beliefs, update_clarifications,
                 update_narrative, refine_affect, promote_belief
    - Read:      resolve_entity, recall_memory (~400 tokens),
                 discover_capabilities (~580 tokens), summarize_context (variable)
    - Action:    invoke_capability (~710 tokens), spawn_via_fabric, execute_workflow

    The scratchpad advantage here is multi-dimensional:
    1. Read tools return large payloads -> findings extraction saves ~1,500 tokens
    2. Cognitive write results are repetitive status updates -> compacted away
    3. ACK messages are ephemeral -> scratchpad discards them after use
    4. Context stays bounded despite 15+ tool calls across 8-10 iterations
    5. Entity resolution calls add overhead that compacts cleanly

    Expected flow (8-10 turns, 2-4 tool calls each):
    Turn 1:  acknowledge(commit) + update_narrative + refine_affect
    Turn 2:  recall_memory + resolve_entity(Mom, Sarah, Jake)
    Turn 3:  update_beliefs (per entity_id) + update_scoreboard
    Turn 4:  update_clarifications + acknowledge(progress)
    Turn 5:  discover_capabilities + invoke_capability
    Turn 6:  update_scoreboard(progress) + spawn_via_fabric
    Turn 7:  promote_belief + execute_workflow
    Turn 8:  summarize_context + acknowledge(closure)
    Turn 9:  final_answer
    """
    return Scenario(
        id="test_10_concierge_full",
        name="Concierge Full Tool Suite (15 tools)",
        description=(
            "Birthday dinner planning using all 15 Concierge tools with "
            "real SessionState mutations. Tests Signal/Cognitive/Read/Action categories "
            "including mandatory entity resolution before belief writes."
        ),
        system_prompt=(
            "You are the FamilyOS Concierge -- a warm, proactive family assistant.\n\n"
            "AUTONOMY: This is a SINGLE-TURN task. There is NO interactive user. "
            "You will NEVER receive additional input. Make reasonable assumptions "
            "for missing information and PROCEED. Never ask for clarification.\n\n"
            "EFFICIENCY: You have ~5 turns. Call 3-5 tools per turn. "
            "Every turn MUST make forward progress. Never waste a turn on a "
            "single update_beliefs or acknowledge(progress).\n\n"
            "CRITICAL RULES:\n"
            "- KNOWN FACTS already contain extracted data from previous tool calls. "
            "  Do NOT call update_beliefs to re-store data already visible there.\n"
            "- Batch ALL belief writes in ONE turn (3-5 calls). Never dedicate "
            "  multiple turns to individual update_beliefs calls.\n"
            "- Only write beliefs for KEY entities (people + dietary facts). "
            "  Restaurant data is already captured in findings -- do not re-write it.\n"
            "- Before update_beliefs: call resolve_entity for each entity, "
            "  then use the returned entity_id.\n"
            "- For complex sub-tasks (>3 tool calls), use spawn_agent to delegate. "
            "  E.g. spawn_agent(task='Compare menus across top 3 restaurants for "
            "  dietary compatibility', tool_budget=5).\n"
            "- When invoke_capability needs inputs you lack, INFER from context.\n\n"
            "WORKFLOW (complete in ~5 turns):\n"
            "Turn 1: acknowledge(commit) + update_narrative + recall_memory + resolve_entity (batch all)\n"
            "Turn 2: update_beliefs (ONLY key dietary/entity facts, batch 3-5) + update_scoreboard\n"
            "Turn 3: discover_capabilities + invoke_capability (use defaults for missing params)\n"
            "Turn 4: summarize_context + final_answer\n"
            "If a sub-task is complex, use spawn_agent in Turn 3 instead of doing it yourself.\n\n"
            "Available tools: acknowledge, update_narrative, recall_memory, resolve_entity, "
            "update_beliefs, update_scoreboard, update_clarifications, refine_affect, "
            "promote_belief, discover_capabilities, invoke_capability, spawn_via_fabric, "
            "execute_workflow, summarize_context, spawn_agent, final_answer"
        ),
        user_query=(
            "Hey, Mom's birthday is next Saturday! She mentioned she's gone vegan "
            "recently. Can you help plan a special dinner for the family? "
            "I'm excited but honestly kinda stressed about pulling it off. "
            "We'll need a restaurant that seats about 8 people and handles "
            "different dietary needs -- Sarah is vegetarian, Jake has a nut allergy. "
            "Not sure about the budget yet. Please follow all your operating rules "
            "and work through each step carefully."
        ),
        tier=Tier.HIGH,
        max_iterations=10,
        max_tools=30,
        checkpoints=[
            Checkpoint(
                iteration=6,
                check_type="context_bounded",
                expected_value=8000,
                description="Context should stay bounded despite many tool calls",
            ),
        ],
        tags=["concierge", "full_suite", "sessionstate", "core"],
        registry="concierge",
        force_tool_call=True,
        min_tool_iterations=3,
    )
