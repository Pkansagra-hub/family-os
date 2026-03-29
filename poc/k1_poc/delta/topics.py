"""
poc.k1_poc.delta.topics -- Delta bus topic constants for SessionState mutations.

V2 Design Ref: Section 3 (Event Taxonomy, merged topic table)
V2 Design Ref: Section 5 (DeltaAggregator Write Pipeline)

Back emits structured deltas on these topics.  The DeltaAggregator
subscribes and batches them.  FSM applies the batched deltas.

All delta topics use the k1.session prefix which maps to
DeliveryMode.STRICT in the TimingConfig defaults (see
k1/bus/timing/defaults.py: DEFAULT_RULES["k1.session"] = DeliveryMode.STRICT).
This ensures causal ordering of mutations.

Topic hierarchy (V2 Section 3):
    k1.session.artifact.created.v1  -- Back -> DeltaAggregator (INTERACTIVE)
    k1.session.task.state.v1        -- Back -> DeltaAggregator (INTERACTIVE)
    k1.session.state.updated.v1     -- DeltaAggregator -> Observability (BACKGROUND)
"""

# =========================================================================
# Delta topics (V2 Section 3 Event Taxonomy + Section 5)
# =========================================================================

# Back -> DeltaAggregator: artifact created
# (booking confirmation, search results, etc.)
ARTIFACT_CREATED = "k1.session.artifact.created.v1"

# Back -> DeltaAggregator: task state transition
# (DISPATCHED -> IN_PROGRESS -> COMPLETED/FAILED/CANCELLED)
TASK_STATE_CHANGED = "k1.session.task.state.v1"

# DeltaAggregator -> Observability: SS was updated
# (emitted after each delta batch is applied)
STATE_UPDATED = "k1.session.state.updated.v1"

# =========================================================================
# All delta topics (for validation/iteration)
# =========================================================================

ALL_DELTA_TOPICS: frozenset[str] = frozenset(
    {
        ARTIFACT_CREATED,
        TASK_STATE_CHANGED,
        STATE_UPDATED,
    }
)
