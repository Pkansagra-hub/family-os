"""
Awaiter Utilities - Event Synchronization Helpers

Provides high-level awaiter coroutines built on DeltaBus subscriptions
and asyncio Futures for coordinating asynchronous flows across K1 components.

Key Use Cases:
- Intent Router waiting for Concierge response (await_response)
- Orchestrator waiting for phase completions (await_phase)
- Runner scripts waiting for writer receipts (await_writer_receipts)
- Custom event synchronization (await_event)

Design:
- Built on DeltaBus.subscribe_once() (one-time listeners)
- Timeout handling with asyncio.TimeoutError
- Cancellation support via asyncio.CancelledError
- Structured logging with cognitive trace IDs
- Zero sleep loops - event-driven synchronization

References:
- Epic 1.3 Issue 1.3.1: Awaiter Utility Layer
- l4_runtime/deltabus/deltabus.py: DeltaBus event bus implementation
- Milestone 2: Intent Router mailbox flow integration
"""

import asyncio
from typing import Any, Dict, List, Optional

import structlog

# Configure logger (use structlog for consistency with rest of PoC)
logger = structlog.get_logger(__name__)


# ========================================================================
# CUSTOM EXCEPTIONS
# ========================================================================


class AwaiterTimeout(Exception):
    """
    Raised when awaiter times out waiting for event

    Attributes:
        event_pattern: The event pattern that was being awaited
        timeout_seconds: The timeout duration that was exceeded
    """

    def __init__(self, event_pattern: str, timeout_seconds: float):
        self.event_pattern = event_pattern
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Awaiter timeout: No event matching '{event_pattern}' within {timeout_seconds}s"
        )


class AwaiterCancelled(Exception):
    """
    Raised when awaiter is cancelled before event arrives

    Attributes:
        event_pattern: The event pattern that was being awaited
    """

    def __init__(self, event_pattern: str):
        self.event_pattern = event_pattern
        super().__init__(f"Awaiter cancelled: Waiting for '{event_pattern}' was cancelled")


# ========================================================================
# CORE AWAITER FUNCTIONS
# ========================================================================


async def await_response(
    envelope_id: str,
    deltabus: Any,
    timeout: float = 10.0,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wait for response event from Concierge or other agent

    Waits for DeltaBus event: response.{envelope_id}

    Args:
        envelope_id: Envelope ID from request (e.g., "env_abc123")
        deltabus: DeltaBus instance
        timeout: Timeout in seconds (default: 10s)
        trace_id: Optional cognitive trace ID for logging

    Returns:
        Response payload dict with 'message', 'status', 'metadata', etc.

    Raises:
        AwaiterTimeout: If response not received within timeout
        AwaiterCancelled: If wait is cancelled

    Example:
        # Send request via Intent Router
        envelope_id = "env_abc123"
        await intent_router.route_message(user_input, envelope_id=envelope_id)

        # Wait for response from Concierge
        try:
            response = await await_response(envelope_id, deltabus, timeout=5.0)
            print(f"Response: {response['message']}")
        except AwaiterTimeout:
            print("Response timeout!")

    Performance:
        - <1ms subscription overhead
        - Event-driven (no polling/sleep)
        - Auto-cleanup on completion/timeout/cancellation
    """
    event_pattern = f"response.{envelope_id}"

    logger.info(
        "Awaiter waiting for response",
        envelope_id=envelope_id,
        pattern=event_pattern,
        timeout=timeout,
        trace_id=trace_id,
    )

    try:
        # Wait for event via DeltaBus subscribe_once
        event = await deltabus.subscribe_once(event_pattern, timeout=timeout)

        logger.info(
            "Awaiter response received",
            envelope_id=envelope_id,
            event_id=event.event_id,
            trace_id=trace_id,
        )

        return event.payload

    except asyncio.TimeoutError as e:
        logger.warning(
            "Awaiter response timeout",
            envelope_id=envelope_id,
            timeout=timeout,
            trace_id=trace_id,
        )
        raise AwaiterTimeout(event_pattern, timeout) from e

    except asyncio.CancelledError:
        logger.warning(
            "Awaiter response wait cancelled",
            envelope_id=envelope_id,
            trace_id=trace_id,
        )
        raise AwaiterCancelled(event_pattern)


async def await_phase(
    task_id: str,
    phase_name: str,
    deltabus: Any,
    timeout: float = 30.0,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wait for orchestration phase completion event

    Waits for DeltaBus event: orchestration.{phase_name}.{task_id}

    Args:
        task_id: Task identifier (e.g., "task_xyz789")
        phase_name: Phase name (e.g., "negotiation", "selection", "execution")
        deltabus: DeltaBus instance
        timeout: Timeout in seconds (default: 30s)
        trace_id: Optional cognitive trace ID for logging

    Returns:
        Phase result payload dict with phase-specific data

    Raises:
        AwaiterTimeout: If phase not completed within timeout
        AwaiterCancelled: If wait is cancelled

    Example:
        # Orchestrator Phase 1: Negotiation
        task_id = "task_xyz789"
        orchestrator.start_negotiation(task_id)

        # Wait for negotiation completion
        try:
            result = await await_phase(task_id, "negotiation", deltabus, timeout=10.0)
            print(f"Negotiation complete: {result['agents_selected']}")
        except AwaiterTimeout:
            print("Negotiation timeout!")

    Performance:
        - <1ms subscription overhead
        - Event-driven coordination
        - Suitable for multi-phase workflows
    """
    event_pattern = f"orchestration.{phase_name}.{task_id}"

    logger.info(
        "[Awaiter] Waiting for orchestration phase",
        task_id=task_id,
        phase_name=phase_name,
        pattern=event_pattern,
        timeout=timeout,
        trace_id=trace_id,
    )

    try:
        # Wait for phase completion event
        event = await deltabus.subscribe_once(event_pattern, timeout=timeout)

        logger.info(
            "[Awaiter] Phase completed",
            task_id=task_id,
            phase_name=phase_name,
            event_id=event.event_id,
            trace_id=trace_id,
        )

        return event.payload

    except asyncio.TimeoutError as e:
        logger.warning(
            "[Awaiter] Phase timeout",
            task_id=task_id,
            phase_name=phase_name,
            timeout=timeout,
            trace_id=trace_id,
        )
        raise AwaiterTimeout(event_pattern, timeout) from e

    except asyncio.CancelledError:
        logger.warning(
            "[Awaiter] Phase wait cancelled",
            task_id=task_id,
            phase_name=phase_name,
            trace_id=trace_id,
        )
        raise AwaiterCancelled(event_pattern)


async def await_writer_receipts(
    delta_ids: List[str],
    deltabus: Any,
    timeout: float = 5.0,
    trace_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Wait for multiple writer agent receipts

    Waits for DeltaBus events: writer.receipt.{delta_id} (for each delta)

    Args:
        delta_ids: List of delta IDs to wait for (e.g., ["delta_001", "delta_002"])
        deltabus: DeltaBus instance
        timeout: Timeout in seconds (default: 5s)
        trace_id: Optional cognitive trace ID for logging

    Returns:
        List of receipt payload dicts (one per delta_id, in same order)

    Raises:
        AwaiterTimeout: If any receipt not received within timeout
        AwaiterCancelled: If wait is cancelled

    Example:
        # Publish deltas to DeltaBus
        delta_ids = ["delta_001", "delta_002", "delta_003"]
        for delta_id in delta_ids:
            deltabus.publish(DeltaBusEvent(
                event_type="session.delta",
                session_id="session_123",
                payload={"delta_id": delta_id, "section": "beliefs", ...}
            ))

        # Wait for writer agents to process all deltas
        try:
            receipts = await await_writer_receipts(delta_ids, deltabus, timeout=5.0)
            print(f"All receipts received: {len(receipts)}")
        except AwaiterTimeout:
            print("Writer timeout!")

    Performance:
        - Parallel waiting (all receipts awaited concurrently)
        - <5ms overhead for typical batch sizes (<10 deltas)
        - Event-driven (no polling)
    """
    logger.info(
        "[Awaiter] Waiting for writer receipts",
        delta_count=len(delta_ids),
        delta_ids=delta_ids,
        timeout=timeout,
        trace_id=trace_id,
    )

    try:
        # Create futures for all delta receipts (parallel waiting)
        receipt_futures = [
            deltabus.subscribe_once(f"writer.receipt.{delta_id}", timeout=timeout)
            for delta_id in delta_ids
        ]

        # Wait for all receipts concurrently
        events = await asyncio.gather(*receipt_futures)

        logger.info(
            "[Awaiter] All writer receipts received",
            delta_count=len(delta_ids),
            trace_id=trace_id,
        )

        # Extract payloads from events
        receipts = [event.payload for event in events]
        return receipts

    except asyncio.TimeoutError as e:
        logger.warning(
            "[Awaiter] Writer receipts timeout",
            delta_count=len(delta_ids),
            timeout=timeout,
            trace_id=trace_id,
        )
        raise AwaiterTimeout("writer.receipt.*", timeout) from e

    except asyncio.CancelledError:
        logger.warning(
            "[Awaiter] Writer receipts wait cancelled",
            delta_count=len(delta_ids),
            trace_id=trace_id,
        )
        raise AwaiterCancelled("writer.receipt.*")


async def await_event(
    event_pattern: str,
    deltabus: Any,
    timeout: float = 10.0,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wait for any DeltaBus event matching pattern (generic awaiter)

    Waits for DeltaBus event matching pattern (exact or wildcard)

    Args:
        event_pattern: Event pattern to match (e.g., "session.*", "agent.spawned")
        deltabus: DeltaBus instance
        timeout: Timeout in seconds (default: 10s)
        trace_id: Optional cognitive trace ID for logging

    Returns:
        Event payload dict

    Raises:
        AwaiterTimeout: If event not received within timeout
        AwaiterCancelled: If wait is cancelled

    Example:
        # Wait for any session event
        try:
            event = await await_event("session.*", deltabus, timeout=5.0)
            print(f"Session event: {event}")
        except AwaiterTimeout:
            print("No session events!")

        # Wait for specific agent spawned
        try:
            event = await await_event("agent.spawned", deltabus, timeout=10.0)
            print(f"Agent spawned: {event['agent_id']}")
        except AwaiterTimeout:
            print("No agent spawned!")

    Performance:
        - <1ms subscription overhead
        - Event-driven (no polling)
        - Suitable for custom synchronization patterns
    """
    logger.info(
        "[Awaiter] Waiting for event",
        pattern=event_pattern,
        timeout=timeout,
        trace_id=trace_id,
    )

    try:
        # Wait for event via DeltaBus subscribe_once
        event = await deltabus.subscribe_once(event_pattern, timeout=timeout)

        logger.info(
            "[Awaiter] Event received",
            pattern=event_pattern,
            event_type=event.event_type,
            event_id=event.event_id,
            trace_id=trace_id,
        )

        return event.payload

    except asyncio.TimeoutError as e:
        logger.warning(
            "[Awaiter] Event timeout",
            pattern=event_pattern,
            timeout=timeout,
            trace_id=trace_id,
        )
        raise AwaiterTimeout(event_pattern, timeout) from e

    except asyncio.CancelledError:
        logger.warning(
            "[Awaiter] Event wait cancelled",
            pattern=event_pattern,
            trace_id=trace_id,
        )
        raise AwaiterCancelled(event_pattern)
        raise AwaiterCancelled(event_pattern)
