"""
k1.orchestrator.adapters.test_mailbox_adapter -- TestMailboxAdapter (6.1.8).

Test/mock adapter for IMailboxPort.

Design:
  - FIFO (not WFQ) for deterministic test ordering.
  - Unbounded -- never raises MailboxFullError.
  - Logs all enqueue calls for test assertions.
  - Provides inject/drain/assert helpers for test setup and verification.

References:
  - Issue 6.1.8 in orchestrator-implementation-plan.md
  - k1/orchestrator/ports/mailbox_port.py (IMailboxPort)

Exports:
  TestMailboxAdapter
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 6.1.8 -- TestMailboxAdapter
# ---------------------------------------------------------------------------


class TestMailboxAdapter:
    """
    Test IMailboxPort adapter with FIFO ordering.

    Unbounded (never raises MailboxFullError). Logs all enqueue calls
    for assertion. No WFQ -- messages dequeue in FIFO order regardless
    of priority, giving tests deterministic ordering.

    Priority ordering tests must use the production ``MailboxAdapter``.
    """

    __slots__ = ("messages", "enqueued_log")

    def __init__(self) -> None:
        self.messages: Deque[Any] = deque()
        self.enqueued_log: List[Tuple[Any, str]] = []

    # ------------------------------------------------------------------
    # IMailboxPort.enqueue
    # ------------------------------------------------------------------

    def enqueue(self, message: Any, priority: str = "INTERACTIVE") -> int:
        """Enqueue a message. Always succeeds (unbounded). Returns 0."""
        self.messages.append(message)
        self.enqueued_log.append((message, priority))
        return 0

    # ------------------------------------------------------------------
    # IMailboxPort.dequeue
    # ------------------------------------------------------------------

    def dequeue(self) -> Optional[Any]:
        """Dequeue a message FIFO. Returns None if empty."""
        if self.messages:
            return self.messages.popleft()
        return None

    # ------------------------------------------------------------------
    # IMailboxPort.depth
    # ------------------------------------------------------------------

    def depth(self) -> int:
        """Return the current queue size."""
        return len(self.messages)

    # ------------------------------------------------------------------
    # IMailboxPort.peek_priority
    # ------------------------------------------------------------------

    def peek_priority(self) -> Optional[str]:
        """Return the priority of the next message, or None if empty.

        Since TestMailboxAdapter is FIFO, returns the priority
        recorded during enqueue for the front message.
        """
        if not self.messages:
            return None
        # Find the priority of the front message in enqueued_log
        front = self.messages[0]
        for msg, pri in self.enqueued_log:
            if msg is front:
                return pri
        return "INTERACTIVE"  # fallback

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def inject(self, message: Any, priority: str = "INTERACTIVE") -> None:
        """Enqueue a message for test setup (alias for enqueue)."""
        self.enqueue(message, priority)

    def drain(self) -> List[Any]:
        """Pop all messages and return as a list."""
        result: List[Any] = []
        while self.messages:
            result.append(self.messages.popleft())
        return result

    def assert_enqueued(self, message_type: type, count: int = 1) -> None:
        """Assert that *count* messages of *message_type* were enqueued."""
        matching = [msg for msg, _pri in self.enqueued_log if isinstance(msg, message_type)]
        actual = len(matching)
        assert actual == count, (
            f"Expected {count} enqueued messages of type {message_type.__name__}, " f"got {actual}"
        )

    def assert_empty(self) -> None:
        """Assert that no messages remain in the mailbox."""
        assert (
            len(self.messages) == 0
        ), f"Expected empty mailbox, but {len(self.messages)} messages remain"
