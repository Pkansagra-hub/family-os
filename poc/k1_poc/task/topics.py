"""
poc.k1_poc.task.topics -- Task orchestration bus topic constants.

DEPRECATION NOTICE (V3 E0.1.4):
    This module re-exports topic constants from poc.k1_poc.bus.topics,
    which is the SINGLE SOURCE OF TRUTH for all POC topic strings.
    New code should import directly from poc.k1_poc.bus.topics.
    This module exists only for backward compatibility.

V2 Design Ref: Section 3 (Event Taxonomy table)

These topics use the k1.orchestration prefix which maps to
DeliveryMode.STRICT in the TimingConfig defaults (see
k1/bus/timing/defaults.py: "k1.orchestration": DeliveryMode.STRICT).

STRICT delivery means:
    - Causal ordering via parent_id (chained task envelopes wait for parent)
    - Sequence gap buffering (envelopes arrive in order within topic)
    - Timeout safety net (5s default, prevents permanent blocking)

Priority conventions (from k1.bus.envelope.Priority):
    URGENT=0     -- cancel, user input (latency <5ms)
    REALTIME=1   -- reserved
    INTERACTIVE=2 -- dispatch, complete, failed, suspended, resume (latency <50ms)
    BACKGROUND=3  -- affect updates, proactive fills (latency <500ms)
"""

# =========================================================================
# Re-exports from the authoritative source: poc.k1_poc.bus.topics
# (V3 E0.1.4 -- eliminate duplication)
# =========================================================================

from poc.k1_poc.bus.topics import TOPIC_DAG_COMPLETED as DAG_COMPLETED  # noqa: F401
from poc.k1_poc.bus.topics import TOPIC_ORCHESTRATION_DELTA as ORCHESTRATION_DELTA  # noqa: F401
from poc.k1_poc.bus.topics import TOPIC_TASK_ACCEPTED as TASK_ACCEPTED  # noqa: F401
from poc.k1_poc.bus.topics import TOPIC_TASK_CANCEL as TASK_CANCEL  # noqa: F401
from poc.k1_poc.bus.topics import TOPIC_TASK_COMPLETE as TASK_COMPLETE  # noqa: F401
from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH as TASK_DISPATCH  # noqa: F401
from poc.k1_poc.bus.topics import TOPIC_TASK_FAILED as TASK_FAILED  # noqa: F401
from poc.k1_poc.bus.topics import TOPIC_TASK_RESUME as TASK_RESUME  # noqa: F401
from poc.k1_poc.bus.topics import TOPIC_TASK_SUSPENDED as TASK_SUSPENDED  # noqa: F401
from poc.k1_poc.bus.topics import TOPIC_WEAVE_BATCH as WEAVE_BATCH  # noqa: F401

# =========================================================================
# All topics (for validation/iteration)
# =========================================================================

ALL_TASK_TOPICS: frozenset[str] = frozenset(
    {
        TASK_DISPATCH,
        TASK_COMPLETE,
        TASK_FAILED,
        TASK_CANCEL,
        TASK_SUSPENDED,
        TASK_RESUME,
        TASK_ACCEPTED,
        ORCHESTRATION_DELTA,
        DAG_COMPLETED,
        WEAVE_BATCH,
    }
)
