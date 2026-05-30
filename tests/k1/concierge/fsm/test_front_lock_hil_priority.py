"""GAP-HIL-011 -- TOPIC_HIL_REQUEST must be served at INTERACTIVE priority
in the FrontLock queue, ahead of bulk task results.
"""

from __future__ import annotations

from k1.concierge.bus.topics import TOPIC_HIL_REQUEST, TOPIC_TASK_COMPLETE
from k1.concierge.fsm.front_lock import (
    PRIORITY_INTERACTIVE,
    PRIORITY_RESULT,
    TOPIC_PRIORITY,
)


def test_hil_request_is_interactive_priority() -> None:
    assert TOPIC_HIL_REQUEST in TOPIC_PRIORITY
    assert TOPIC_PRIORITY[TOPIC_HIL_REQUEST] == PRIORITY_INTERACTIVE


def test_hil_request_outranks_task_complete() -> None:
    assert TOPIC_PRIORITY[TOPIC_HIL_REQUEST] < TOPIC_PRIORITY[TOPIC_TASK_COMPLETE]
    assert TOPIC_PRIORITY[TOPIC_TASK_COMPLETE] == PRIORITY_RESULT
