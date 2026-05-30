"""GAP-HIL-005 -- late-HIL recovery via determine_mode().

When a HIL request times out, the controller's ring buffer records the
expiry. A user message that arrives within the recovery window injects
``late_hil_recovery=True`` into routing metadata so determine_mode()
returns HITL_RESOLVE, ensuring the reply is treated as the answer to
the stranded HIL question rather than the start of a brand-new turn.
"""

from __future__ import annotations

from k1.concierge.prompt.mode import PromptMode, determine_mode


def test_late_hil_recovery_routes_to_hitl_resolve() -> None:
    mode = determine_mode(
        fsm_state="LISTENING",
        envelope_topic="k1.session.user.input.v1",
        routing_metadata={
            "late_hil_recovery": True,
            "late_hil_request_id": "abc",
            "late_hil_type": "needs_human",
        },
    )
    assert mode == PromptMode.HITL_RESOLVE


def test_no_late_hil_flag_falls_through() -> None:
    """Without the recovery flag the LISTENING + user_input path is unchanged."""
    mode = determine_mode(
        fsm_state="LISTENING",
        envelope_topic="k1.session.user.input.v1",
        routing_metadata={},
    )
    assert mode != PromptMode.HITL_RESOLVE


def test_late_hil_recovery_outranked_by_cancel() -> None:
    """Explicit FSM cancel state takes precedence over recovery flag."""
    mode = determine_mode(
        fsm_state="CANCELLING",
        envelope_topic="k1.session.user.input.v1",
        routing_metadata={"late_hil_recovery": True},
    )
    assert mode == PromptMode.CANCEL
