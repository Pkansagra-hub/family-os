"""Boot the K1 KernelService with full DEBUG logging — shows every component."""

import asyncio
import logging
import sys

# Enable ALL logging — every module, DEBUG level
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-5s %(name)s: %(message)s",
    stream=sys.stdout,
)

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService


def _t(obj):
    return type(obj).__name__ if obj is not None else "None"


async def main():
    config = KernelConfig()
    kernel = KernelService(config=config)

    print("=" * 70)
    print("  TIER 1 STARTUP — S1 through S7 + S6b")
    print("=" * 70)
    await kernel.startup()

    print()
    print("=" * 70)
    print("  HEALTH CHECK")
    print("=" * 70)
    health = await kernel.health_check()
    print(f"  Healthy: {health.healthy}")
    for comp, ok in sorted(health.components.items()):
        tag = "OK" if ok else "FAIL"
        detail = health.details.get(comp, "")
        print(f"    {comp:20s} [{tag}] {detail}")

    print()
    print("=" * 70)
    print("  TIER 1 COMPONENTS INVENTORY")
    print("=" * 70)
    bus_closed = getattr(kernel._bus, "_closed", "?")
    router_closed = getattr(kernel._router, "_closed", "?")
    task = kernel._planner_task
    task_done = task.done() if task else "N/A"

    print(f"  Bus            : {_t(kernel._bus)}  (closed={bus_closed})")
    print(f"  AsyncBusBridge : {_t(kernel._async_bus)}")
    print(f"  Router         : {_t(kernel._router)}  (closed={router_closed})")
    print(f"  ModelHub       : {_t(kernel._model_hub)}")
    print(f"  Bridge         : {_t(kernel._bridge)}")
    print(f"  SharedFabric   : {_t(kernel._shared_fabric)}")
    print(f"  Orchestrator   : {_t(kernel._orchestrator)}")
    print(f"  Planner        : {_t(kernel._planner)}")
    print(f"  PlannerTask    : {task}  done={task_done}")

    # Orchestrator internals
    orch = kernel._orchestrator
    print()
    print("  -- Orchestrator internals --")
    for attr in [
        "_dag_executor",
        "_mailbox_port",
        "_fabric_port",
        "_planner_port",
        "_state_port",
        "_delta_port",
        "_bridge_port",
        "_event_port",
        "_storage_port",
        "_workflow_scheduler",
        "_gap_detector",
        "_connector_lifecycle",
    ]:
        val = getattr(orch, attr, None)
        print(f"    {attr:30s} : {_t(val)}")

    # Planner internals
    planner = kernel._planner
    print()
    print("  -- Planner internals --")
    for attr in [
        "_mailbox",
        "_pipeline",
        "_llm_port",
        "_fabric_port",
        "_state_port",
        "_bridge_port",
        "_delta_port",
        "_event_port",
        "_running",
    ]:
        val = getattr(planner, attr, None)
        if isinstance(val, (bool, int, str, type(None))):
            print(f"    {attr:30s} : {val}")
        else:
            print(f"    {attr:30s} : {_t(val)}")

    # Fabric internals
    fabric = kernel._shared_fabric
    print()
    print("  -- Shared Fabric internals --")
    for attr in [
        "_event_port",
        "_bridge",
        "_model_gateway",
        "_prompt_system",
        "_delta_bus",
        "_health_checker",
        "_module_loader",
        "_retrieval",
    ]:
        val = getattr(fabric, attr, None)
        print(f"    {attr:30s} : {_t(val)}")

    print()
    print("=" * 70)
    print("  TIER 2 SESSION CREATE — P1 through P6")
    print("=" * 70)
    session = await kernel.create_session("demo-1")

    print()
    print(f"  Session ID     : {session.session_id}")
    print(f"  Bus            : {_t(session.bus)}")
    print(f"  Router         : {_t(session.router)}")
    print(f"  FrontMailbox   : {_t(session.front_mailbox)}")
    print(f"  BackMailbox    : {_t(session.back_mailbox)}")
    print(f"  SessionState   : {_t(session.session_state)}")
    print(f"  Fabric         : {_t(session.fabric)}")
    print(f"  Concierge      : {_t(session.concierge)}")
    print(f"  MemoryWriter   : {_t(session.memory_writer)}")
    print(f"  FrontDispatcher: {_t(session.front_dispatcher)}")
    print(f"  BackDispatcher : {_t(session.back_dispatcher)}")
    print(f"  ExperienceLayer: {_t(session.experience_layer)}")
    print(f"  DeltaAggregator: {_t(session.delta_aggregator)}")
    print(f"  HITLCoordinator: {_t(session.hitl_coordinator)}")
    print(f"  ConsumerTask   : {session.consumer_task}")
    print(f"  DeadLetterCons : {_t(session.dead_letter_consumer)}")
    print(f"  CreatedAt      : {session.created_at}")

    # Session concierge internals
    c = session.concierge
    print()
    print("  -- Concierge internals --")
    for attr in [
        "_fsm",
        "_front_dispatcher",
        "_back_dispatcher",
        "experience_layer",
        "delta_aggregator",
        "hitl_coordinator",
        "_consumer_task",
        "dead_letter_consumer",
        "_bus",
        "_router",
    ]:
        val = getattr(c, attr, None)
        print(f"    {attr:30s} : {_t(val)}")

    print()
    print("=" * 70)
    print("  SECOND SESSION")
    print("=" * 70)
    session2 = await kernel.create_session("demo-2")
    print(f"  Session count: {kernel.session_count}")
    print(f"  Sessions: {kernel.list_sessions()}")

    print()
    print("=" * 70)
    print("  DESTROY SESSIONS")
    print("=" * 70)
    await kernel.destroy_session("demo-1")
    print(f"  After destroy demo-1: count={kernel.session_count}")
    await kernel.destroy_session("demo-2")
    print(f"  After destroy demo-2: count={kernel.session_count}")

    print()
    print("=" * 70)
    print("  SHUTDOWN")
    print("=" * 70)
    await kernel.shutdown()
    print(f"  Running: {kernel.is_running}")

    print()
    print("=" * 70)
    print("  POST-SHUTDOWN HEALTH CHECK")
    print("=" * 70)
    health2 = await kernel.health_check()
    print(f"  Healthy: {health2.healthy}")
    for comp, ok in sorted(health2.components.items()):
        tag = "OK" if ok else "FAIL"
        detail = health2.details.get(comp, "")
        print(f"    {comp:20s} [{tag}] {detail}")

    print()
    print("=" * 70)
    print("  FULL LIFECYCLE COMPLETE")
    print("=" * 70)


asyncio.run(main())
