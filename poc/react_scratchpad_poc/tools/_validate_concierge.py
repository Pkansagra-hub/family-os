"""Quick validation that all 13 Concierge tools execute correctly."""

import asyncio
import json
import sys
from pathlib import Path

# Ensure paths
_POC_ROOT = Path(__file__).parent.parent
_PROJECT_ROOT = _POC_ROOT.parent.parent
for p in [str(_POC_ROOT), str(_PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from tools.concierge_tools import ConciergeToolRegistry, reset_session_state


async def test_all_tools():
    reg = ConciergeToolRegistry()
    results = []

    # 1. acknowledge
    r = await reg.execute(
        "acknowledge",
        {
            "ack_type": "commit",
            "message": "Planning birthday dinner!",
            "next_tool": "update_narrative",
        },
    )
    results.append(("acknowledge", r.ok, r.output.get("displayed")))

    # 2. update_narrative
    r = await reg.execute(
        "update_narrative",
        {
            "operation": "new_thread",
            "topic": "Birthday Dinner Planning",
            "goal": "Plan vegan dinner for Mom",
        },
    )
    results.append(("update_narrative", r.ok, r.output.get("thread_id", "")[:20]))

    # 3. refine_affect
    r = await reg.execute(
        "refine_affect",
        {
            "override_emotion": "anticipatory_stress",
            "override_intensity": 0.7,
            "override_valence": "mixed",
            "reasoning": "User excited but stressed",
        },
    )
    results.append(("refine_affect", r.ok, r.output.get("override_applied")))

    # 4. recall_memory
    r = await reg.execute("recall_memory", {"query": "Mom birthday dietary preferences"})
    payload_size = len(json.dumps(r.output))
    results.append(
        (
            "recall_memory",
            r.ok,
            f"{r.output.get('total_matched')} results, {payload_size} chars (~{payload_size//4} tokens)",
        )
    )

    # 5. update_beliefs
    r = await reg.execute(
        "update_beliefs",
        {
            "operation": "add_fact",
            "subject": "Mom",
            "predicate": "diet",
            "object_value": "vegan",
            "confidence": 0.95,
            "source": "user_stated",
        },
    )
    results.append(("update_beliefs", r.ok, r.output.get("belief_id", "")[:20]))

    # 6. update_scoreboard
    r = await reg.execute(
        "update_scoreboard",
        {"operation": "set_task", "task_name": "birthday_dinner", "task_status": "in_progress"},
    )
    results.append(("update_scoreboard", r.ok, f"{r.output.get('section_bytes')} bytes"))

    # 7. update_clarifications
    r = await reg.execute(
        "update_clarifications",
        {
            "operation": "record_gap",
            "gap_type": "CONSTRAINT_UNCLEAR",
            "description": "What is the budget?",
        },
    )
    results.append(("update_clarifications", r.ok, f"{r.output.get('open_gaps_count')} gaps"))

    # 8. discover_capabilities
    r = await reg.execute(
        "discover_capabilities", {"intent": "vegan restaurant booking", "domain": ["DINING"]}
    )
    payload_size = len(json.dumps(r.output))
    results.append(
        (
            "discover_capabilities",
            r.ok,
            f"{r.output.get('total_matched')} caps, {payload_size} chars (~{payload_size//4} tokens)",
        )
    )

    # 9. invoke_capability
    r = await reg.execute(
        "invoke_capability",
        {
            "capability": "tool.execute.restaurant_search",
            "params": {"cuisine": "vegan", "party_size": 8},
        },
    )
    payload_size = len(json.dumps(r.output))
    restaurants = len(r.output.get("data", {}).get("restaurants", []))
    results.append(
        (
            "invoke_capability",
            r.ok,
            f"{restaurants} restaurants, {payload_size} chars (~{payload_size//4} tokens)",
        )
    )

    # 10. spawn_via_fabric
    r = await reg.execute(
        "spawn_via_fabric",
        {
            "agent_name": "agent.execute.menu_planner",
            "description": "Plan vegan menu",
            "domain": ["DINING", "HEALTH"],
            "tools_granted": ["tool.execute.menu_lookup"],
        },
    )
    results.append(("spawn_via_fabric", r.ok, r.output.get("status")))

    # 11. promote_belief
    r = await reg.execute(
        "promote_belief",
        {
            "belief_id": "belief-mom-vegan",
            "direction": "hot_to_k0",
            "reason": "Durable dietary fact",
        },
    )
    results.append(("promote_belief", r.ok, r.output.get("destination")))

    # 12. execute_workflow
    r = await reg.execute(
        "execute_workflow",
        {
            "workflow_id": "workflow.birthday_party_planning",
            "params": {"event": "birthday", "guest_count": 8},
        },
    )
    results.append(("execute_workflow", r.ok, r.output.get("status")))

    # 13. summarize_context
    r = await reg.execute("summarize_context", {"strategy": "hybrid"})
    results.append(
        (
            "summarize_context",
            r.ok,
            f"ratio={r.output.get('compression_ratio')}, summary='{r.output.get('summary', '')[:60]}...'",
        )
    )

    # Print results
    print(f"\n{'='*70}")
    print(f"{'Tool':<25} {'OK':<6} {'Detail'}")
    print(f"{'='*70}")
    all_ok = True
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"{name:<25} {status:<6} {detail}")
    print(f"{'='*70}")
    print(f"\n{'ALL 13 TOOLS PASSED' if all_ok else 'SOME TOOLS FAILED'}!")

    reset_session_state()


if __name__ == "__main__":
    asyncio.run(test_all_tools())
