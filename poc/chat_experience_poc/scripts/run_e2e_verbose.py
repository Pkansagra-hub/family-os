#!/usr/bin/env python3
"""
E2E Runner with VERBOSE output - Shows agent inputs/outputs and Writer Agent processing
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

import structlog

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(level=logging.WARNING, format="%(message)s", force=True)

from l1_input.intent_router import IntentRouter
from l4_runtime.mailbox.mailbox_manager import MailboxManager
from l4_runtime.session_state.session_state_manager import SessionStateManager
from l5_infrastructure.background_services_manager import BackgroundServicesManager
from system_coordinator import SystemCoordinator


def print_separator(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_agent_io(agent, input_text, output_text, latency_ms, intent=None):
    print(f"\n  [AGENT]   {agent}")
    print(f"  [INPUT]   {input_text}")
    print(f"  [OUTPUT]  {output_text}")  # Full output, no truncation
    print(f"  [LATENCY] {latency_ms:.2f}ms")
    if intent:
        print(f"  [INTENT]  {intent}")


def print_writer_extractions(bgm):
    """Print what Writer Agents have extracted."""
    print("\n  --- WRITER AGENT EXTRACTIONS ---")

    # Get backend storage
    backend = bgm.backend_storage
    if not backend:
        print("  [NO BACKEND STORAGE]")
        return

    stats = backend.get_stats()
    print(f"  Total deltas stored: {stats['total_deltas']}")
    print(f"  By type: {stats['by_type']}")

    # Print each stored delta
    for delta_type, deltas in backend.deltas.items():
        if deltas:
            print(f"\n  [{delta_type.upper()}] ({len(deltas)} items)")
            for delta in deltas[-3:]:  # Show last 3 of each type
                content_preview = (
                    json.dumps(delta.content, indent=2)[:300] if delta.content else "N/A"
                )
                print(f"    - ID: {delta.delta_id}")
                print(f"      Writer: {delta.writer_type}")
                print(f"      Confidence: {delta.confidence}")
                print(f"      Content: {content_preview}")


async def main():
    print_separator("K1 VERBOSE E2E - Agent I/O & Writer Tracking")

    coord = SystemCoordinator()
    ok = await coord.initialize_system()
    if not ok:
        print("[ERROR] System initialization failed")
        return

    print("\n  [SYSTEM] Ready!\n")

    deltabus = coord.deltabus
    mailbox_manager = MailboxManager()
    ssm = SessionStateManager(deltabus=deltabus)
    router = IntentRouter(session_manager=ssm, deltabus=deltabus, mailbox_manager=mailbox_manager)

    # Get BackgroundServicesManager
    bgm = await BackgroundServicesManager.get_manager()

    try:
        # PATH 1
        print_separator("PATH 1: Query Intent (Healthcare)")

        user_1 = "How's my recovery going?"
        reply_1, meta_1 = await router.route_user_input(user_input=user_1, user_id="user_demo")

        intent_1 = meta_1.get("metadata", {}).get("intent", "unknown")
        intent_subtype_1 = meta_1.get("metadata", {}).get("intent_subtype", "unknown")
        latency_1 = meta_1.get("latency_ms", 0)

        print_agent_io(
            "ConciergeAgent", user_1, reply_1, latency_1, f"{intent_1}/{intent_subtype_1}"
        )

        # Wait for Writer Agents to process
        print("\n  [WAITING] Writer Agents processing...")
        await asyncio.sleep(2)

        # Show writer statistics
        stats_1 = await bgm.get_writer_statistics()
        print(f"\n  [WRITERS] Deltas processed: {stats_1['total_deltas_processed']}")
        print(f"  [WRITERS] Commands sent: {stats_1['total_commands_sent']}")

        # Show per-agent stats
        for agent_id, agent_stats in stats_1["per_agent_stats"].items():
            print(
                f"    - {agent_stats['writer_type']}: {agent_stats['deltas_processed']} deltas, {agent_stats['commands_sent']} commands"
            )

        # Show what was extracted
        print_writer_extractions(bgm)

        # PATH 2
        print_separator("PATH 2: Planning Intent (Orchestrator)")

        user_2 = "Plan a dinner at an Italian restaurant nearby tonight"
        reply_2, meta_2 = await router.route_user_input(user_input=user_2, user_id="user_demo")

        intent_2 = meta_2.get("metadata", {}).get("intent", "unknown")
        intent_subtype_2 = meta_2.get("metadata", {}).get("intent_subtype", "unknown")
        latency_2 = meta_2.get("latency_ms", 0)

        print_agent_io(
            "ConciergeAgent", user_2, reply_2, latency_2, f"{intent_2}/{intent_subtype_2}"
        )

        print("\n  [WAITING] Writer Agents processing...")
        await asyncio.sleep(2)

        stats_2 = await bgm.get_writer_statistics()
        print(f"\n  [WRITERS] Deltas processed: {stats_2['total_deltas_processed']}")
        print(f"  [WRITERS] Commands sent: {stats_2['total_commands_sent']}")

        for agent_id, agent_stats in stats_2["per_agent_stats"].items():
            print(
                f"    - {agent_stats['writer_type']}: {agent_stats['deltas_processed']} deltas, {agent_stats['commands_sent']} commands"
            )

        print_writer_extractions(bgm)

        # PATH 3
        print_separator("PATH 3: Action Intent (Tool Use)")

        user_3 = "Send a reminder to take my medication at 8pm"
        reply_3, meta_3 = await router.route_user_input(user_input=user_3, user_id="user_demo")

        intent_3 = meta_3.get("metadata", {}).get("intent", "unknown")
        intent_subtype_3 = meta_3.get("metadata", {}).get("intent_subtype", "unknown")
        latency_3 = meta_3.get("latency_ms", 0)

        print_agent_io(
            "ConciergeAgent", user_3, reply_3, latency_3, f"{intent_3}/{intent_subtype_3}"
        )

        print("\n  [WAITING] Writer Agents processing...")
        await asyncio.sleep(2)

        stats_3 = await bgm.get_writer_statistics()
        print(f"\n  [WRITERS] Deltas processed: {stats_3['total_deltas_processed']}")
        print(f"  [WRITERS] Commands sent: {stats_3['total_commands_sent']}")

        for agent_id, agent_stats in stats_3["per_agent_stats"].items():
            print(
                f"    - {agent_stats['writer_type']}: {agent_stats['deltas_processed']} deltas, {agent_stats['commands_sent']} commands"
            )

        print_writer_extractions(bgm)

        # Summary
        print_separator("FINAL SUMMARY")
        print(f"\n  PATH 1: '{user_1}'")
        print(f"          Reply: '{reply_1}' ({latency_1:.0f}ms)")
        print(f"          Intent: {intent_1}")
        print(f"\n  PATH 2: '{user_2}'")
        print(f"          Reply: '{reply_2}' ({latency_2:.0f}ms)")
        print(f"          Intent: {intent_2}")
        print(f"\n  PATH 3: '{user_3}'")
        print(f"          Reply: '{reply_3}' ({latency_3:.0f}ms)")
        print(f"          Intent: {intent_3}")

        print(f"\n  Total Deltas Processed: {stats_3['total_deltas_processed']}")
        print(f"  Total Commands Sent:    {stats_3['total_commands_sent']}")
        print("")

    finally:
        print_separator("SHUTDOWN")
        ok = await coord.shutdown_system()
        if ok:
            print("  [OK] Shutdown complete\n")


if __name__ == "__main__":
    asyncio.run(main())
