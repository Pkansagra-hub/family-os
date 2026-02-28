"""
tests.poc.test_m05_e53_normal_paths -- E5.3 FSM Normal Path Enrichment
======================================================================

Issue coverage:
  5.3.1 -- Wire Arbiter into _on_user_input (LISTENING/CLARIFYING_USER)
  5.3.2 -- Attach ArbiterResult to history metadata and envelope payload
  5.3.3 -- Make Front determine_mode() accept routing_metadata parameter
"""

from __future__ import annotations

import json

from poc.k1_poc.bus.builders import build_user_input
from poc.k1_poc.bus.topics import TOPIC_INTENT_ARBITRATED, TOPIC_STATE_UPDATED, TOPIC_TURN_STARTED
from poc.k1_poc.fsm.arbiter import ArbiterDecision
from poc.k1_poc.fsm.states import ConciergeState

# ===================================================================
# Helper: create FSM with capture bus
# ===================================================================


def _make_fsm():
    """Create a ConciergeController with capture bus and router."""
    from poc.k1_poc.bus.setup import create_poc_bus, create_poc_router
    from poc.k1_poc.fsm.controller import ConciergeController

    bus = create_poc_bus(capture=True)
    router = create_poc_router()
    return ConciergeController(bus=bus, router=router), bus


def _captured_topics(bus) -> list[str]:
    """Return list of topic strings from captured envelopes."""
    return [e.topic for e in bus.captured]


def _captured_by_topic(bus, topic: str) -> list:
    """Return captured envelopes matching a specific topic."""
    return [e for e in bus.captured if e.topic == topic]


def _payload(envelope) -> dict:
    """Parse JSON payload from a captured envelope."""
    try:
        return json.loads(envelope.payload) if envelope.payload else {}
    except Exception:
        return {}


# ===================================================================
# 5.3.1 -- Wire Arbiter into _on_user_input (LISTENING/CLARIFYING_USER)
# ===================================================================


class TestListeningArbiterWiring:
    """Arbiter runs for LISTENING path (inflight empty, always PARALLEL_NEW)."""

    def test_listening_user_input_emits_intent_arbitrated(self) -> None:
        """LISTENING + user input emits intent.arbitrated via Arbiter."""
        fsm, bus = _make_fsm()
        assert fsm._state == ConciergeState.LISTENING
        env = build_user_input({"text": "tell me a joke"})
        fsm._on_user_input(env)
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) == 1, "Exactly one intent.arbitrated expected"

    def test_listening_arbiter_decision_is_parallel_new(self) -> None:
        """LISTENING always yields PARALLEL_NEW (no inflight tasks)."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "what is 2+2"})
        fsm._on_user_input(env)
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) == 1
        payload = _payload(arb_events[0])
        assert payload["decision"] == ArbiterDecision.PARALLEL_NEW.value

    def test_listening_fsm_trace_unchanged(self) -> None:
        """LISTENING -> DISPATCHING trace is identical to pre-E5.3."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "hello"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.DISPATCHING

    def test_listening_turn_started_emitted(self) -> None:
        """turn.started is still emitted (no regression)."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "hi"})
        fsm._on_user_input(env)
        turn_events = _captured_by_topic(bus, TOPIC_TURN_STARTED)
        assert len(turn_events) >= 1

    def test_listening_state_updated_emitted(self) -> None:
        """state.updated is still emitted (no regression)."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "greetings"})
        fsm._on_user_input(env)
        state_events = _captured_by_topic(bus, TOPIC_STATE_UPDATED)
        assert len(state_events) >= 1

    def test_clarifying_user_emits_intent_arbitrated(self) -> None:
        """CLARIFYING_USER + user input emits intent.arbitrated."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.CLARIFYING_USER
        env = build_user_input({"text": "yes the blue one"})
        fsm._on_user_input(env)
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) == 1

    def test_clarifying_user_transitions_to_dispatching(self) -> None:
        """CLARIFYING_USER -> DISPATCHING trace unchanged."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.CLARIFYING_USER
        env = build_user_input({"text": "the second option"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.DISPATCHING

    def test_intent_arbitrated_payload_has_required_fields(self) -> None:
        """intent.arbitrated payload includes all required fields."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "book a flight"})
        fsm._on_user_input(env)
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        payload = _payload(arb_events[0])
        required = {
            "decision",
            "confidence",
            "target_task_id",
            "intent_class",
            "domain",
            "safety_band",
            "inflight_task_count",
            "routing_metadata",
        }
        assert required.issubset(payload.keys()), f"Missing fields: {required - payload.keys()}"

    def test_listening_inflight_empty(self) -> None:
        """LISTENING has zero inflight tasks in arbitrated event."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "check the news"})
        fsm._on_user_input(env)
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        payload = _payload(arb_events[0])
        assert payload["inflight_task_count"] == 0

    def test_phase1_runs_exactly_once(self) -> None:
        """Phase 1 classification runs exactly once per turn."""
        fsm, bus = _make_fsm()
        # Patch to count invocations
        original = fsm._phase1_pipeline.classify
        call_count = [0]

        def counting_classify(text):
            call_count[0] += 1
            return original(text)

        fsm._phase1_pipeline.classify = counting_classify
        env = build_user_input({"text": "plan a trip"})
        fsm._on_user_input(env)
        assert call_count[0] == 1, "Phase 1 must run exactly once"


# ===================================================================
# 5.3.2 -- Attach ArbiterResult to history and envelope
# ===================================================================


class TestArbiterMetadataAttachment:
    """Both Phase 1 and Arbiter metadata on history and envelope."""

    def test_history_has_phase1_metadata(self) -> None:
        """User history entry contains Phase 1 metadata."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "search hotels in Tokyo"})
        fsm._on_user_input(env)
        assert len(fsm._history) >= 1
        last = fsm._history[-1]
        assert last.entry_type == "user"
        # Phase 1 metadata keys (to_metadata uses 'intent' not 'intent_classification')
        assert "intent" in last.metadata
        assert "complexity_tier" in last.metadata

    def test_history_has_arbiter_metadata(self) -> None:
        """User history entry contains Arbiter metadata dict."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "show me restaurants"})
        fsm._on_user_input(env)
        last = fsm._history[-1]
        assert "arbiter" in last.metadata
        arb = last.metadata["arbiter"]
        assert "decision" in arb
        assert "confidence" in arb
        assert "routing_metadata" in arb

    def test_history_arbiter_decision_is_parallel_new(self) -> None:
        """Arbiter decision stored in history is PARALLEL_NEW for LISTENING."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "recommend a book"})
        fsm._on_user_input(env)
        last = fsm._history[-1]
        arb = last.metadata["arbiter"]
        assert arb["decision"] == ArbiterDecision.PARALLEL_NEW.value

    def test_envelope_payload_has_arbiter_decision(self) -> None:
        """Envelope delivered to Front includes arbiter_decision."""
        fsm, bus = _make_fsm()
        # Capture what gets delivered to Front
        delivered = []
        original_deliver = fsm._deliver_to_front

        def capture_deliver(envelope):
            delivered.append(envelope)
            return original_deliver(envelope)

        fsm._deliver_to_front = capture_deliver
        env = build_user_input({"text": "find a gym"})
        fsm._on_user_input(env)
        assert len(delivered) >= 1
        payload = _payload(delivered[0])
        assert "arbiter_decision" in payload
        assert payload["arbiter_decision"] == ArbiterDecision.PARALLEL_NEW.value

    def test_envelope_payload_has_routing_metadata(self) -> None:
        """Envelope delivered to Front includes routing_metadata."""
        fsm, bus = _make_fsm()
        delivered = []
        original_deliver = fsm._deliver_to_front

        def capture_deliver(envelope):
            delivered.append(envelope)
            return original_deliver(envelope)

        fsm._deliver_to_front = capture_deliver
        env = build_user_input({"text": "play some music"})
        fsm._on_user_input(env)
        assert len(delivered) >= 1
        payload = _payload(delivered[0])
        assert "routing_metadata" in payload

    def test_envelope_payload_has_complexity_tier(self) -> None:
        """Enriched envelope contains complexity_tier."""
        fsm, bus = _make_fsm()
        delivered = []
        original_deliver = fsm._deliver_to_front

        def capture_deliver(envelope):
            delivered.append(envelope)
            return original_deliver(envelope)

        fsm._deliver_to_front = capture_deliver
        env = build_user_input({"text": "set an alarm"})
        fsm._on_user_input(env)
        assert len(delivered) >= 1
        payload = _payload(delivered[0])
        assert "complexity_tier" in payload

    def test_envelope_payload_has_safety_band(self) -> None:
        """Enriched envelope contains safety_band."""
        fsm, bus = _make_fsm()
        delivered = []
        original_deliver = fsm._deliver_to_front

        def capture_deliver(envelope):
            delivered.append(envelope)
            return original_deliver(envelope)

        fsm._deliver_to_front = capture_deliver
        env = build_user_input({"text": "translate this"})
        fsm._on_user_input(env)
        assert len(delivered) >= 1
        payload = _payload(delivered[0])
        assert "safety_band" in payload

    def test_enriched_envelope_preserves_original_fields(self) -> None:
        """Enriched envelope retains original payload fields (text, etc)."""
        fsm, bus = _make_fsm()
        delivered = []
        original_deliver = fsm._deliver_to_front

        def capture_deliver(envelope):
            delivered.append(envelope)
            return original_deliver(envelope)

        fsm._deliver_to_front = capture_deliver
        env = build_user_input({"text": "hello world"})
        fsm._on_user_input(env)
        assert len(delivered) >= 1
        payload = _payload(delivered[0])
        assert payload.get("text") == "hello world"

    def test_enriched_envelope_preserves_topic(self) -> None:
        """Enriched envelope topic matches original."""
        fsm, bus = _make_fsm()
        delivered = []
        original_deliver = fsm._deliver_to_front

        def capture_deliver(envelope):
            delivered.append(envelope)
            return original_deliver(envelope)

        fsm._deliver_to_front = capture_deliver
        env = build_user_input({"text": "test topic"})
        fsm._on_user_input(env)
        assert len(delivered) >= 1
        assert delivered[0].topic == env.topic

    def test_enriched_envelope_preserves_envelope_id(self) -> None:
        """Enriched envelope ID matches original."""
        fsm, bus = _make_fsm()
        delivered = []
        original_deliver = fsm._deliver_to_front

        def capture_deliver(envelope):
            delivered.append(envelope)
            return original_deliver(envelope)

        fsm._deliver_to_front = capture_deliver
        env = build_user_input({"text": "test id"})
        fsm._on_user_input(env)
        assert len(delivered) >= 1
        assert delivered[0].envelope_id == env.envelope_id


# ===================================================================
# 5.3.3 -- Front determine_mode() accepts routing_metadata
# ===================================================================


class TestDetermineModeRoutingMetadata:
    """determine_mode() accepts routing_metadata kwarg (pass-through)."""

    def test_determine_mode_accepts_routing_metadata(self) -> None:
        """determine_mode() can be called with routing_metadata kwarg."""
        from poc.k1_poc.prompt.mode import determine_mode

        mode = determine_mode(
            fsm_state="DISPATCHING",
            envelope_topic="user.input",
            routing_metadata={"arbiter_reason": "parallel_new"},
        )
        assert mode is not None

    def test_determine_mode_routing_metadata_none(self) -> None:
        """determine_mode() works with routing_metadata=None (default)."""
        from poc.k1_poc.prompt.mode import determine_mode

        mode = determine_mode(
            fsm_state="DISPATCHING",
            envelope_topic="user.input",
        )
        assert mode is not None

    def test_determine_mode_routing_metadata_empty_dict(self) -> None:
        """determine_mode() works with routing_metadata={}."""
        from poc.k1_poc.prompt.mode import determine_mode

        mode = determine_mode(
            fsm_state="DISPATCHING",
            envelope_topic="user.input",
            routing_metadata={},
        )
        assert mode is not None

    def test_determine_mode_behavior_unchanged_with_metadata(self) -> None:
        """routing_metadata does not alter mode resolution in M5 POC."""
        from poc.k1_poc.prompt.mode import determine_mode

        mode_without = determine_mode(
            fsm_state="DISPATCHING",
            envelope_topic="user.input",
        )
        mode_with = determine_mode(
            fsm_state="DISPATCHING",
            envelope_topic="user.input",
            routing_metadata={"arbiter_reason": "parallel_new", "domain_overlap": 0.2},
        )
        assert mode_without == mode_with

    def test_determine_mode_cancelling_unaffected(self) -> None:
        """CANCELLING mode still resolves to CANCEL regardless of metadata."""
        from poc.k1_poc.prompt.mode import PromptMode, determine_mode

        mode = determine_mode(
            fsm_state="CANCELLING",
            envelope_topic="task.complete",
            routing_metadata={"arbiter_reason": "cancel"},
        )
        assert mode == PromptMode.CANCEL

    def test_determine_mode_interrupt_handling_unaffected(self) -> None:
        """INTERRUPT_HANDLING mode still resolves to INTERRUPT."""
        from poc.k1_poc.prompt.mode import PromptMode, determine_mode

        mode = determine_mode(
            fsm_state="INTERRUPT_HANDLING",
            envelope_topic="user.input",
            routing_metadata={"arbiter_reason": "parallel_new"},
        )
        assert mode == PromptMode.INTERRUPT


class TestFrontRoutingMetadataPassthrough:
    """Front extracts routing_metadata from envelope and passes to determine_mode."""

    def test_parse_routing_metadata_helper_exists(self) -> None:
        """_parse_routing_metadata helper exists in front module."""
        from poc.k1_poc.actors.front import _parse_routing_metadata

        assert callable(_parse_routing_metadata)

    def test_parse_routing_metadata_returns_dict(self) -> None:
        """_parse_routing_metadata extracts routing_metadata from payload."""
        from k1.bus.envelope import Envelope
        from poc.k1_poc.actors.front import _parse_routing_metadata

        payload = json.dumps(
            {
                "text": "hello",
                "routing_metadata": {"arbiter_reason": "parallel_new"},
            }
        ).encode()
        env = Envelope(
            topic="user.input",
            payload=payload,
            payload_format=1,
        )
        result = _parse_routing_metadata(env)
        assert result == {"arbiter_reason": "parallel_new"}

    def test_parse_routing_metadata_returns_none_when_absent(self) -> None:
        """_parse_routing_metadata returns None if no routing_metadata."""
        from k1.bus.envelope import Envelope
        from poc.k1_poc.actors.front import _parse_routing_metadata

        payload = json.dumps({"text": "hello"}).encode()
        env = Envelope(
            topic="user.input",
            payload=payload,
            payload_format=1,
        )
        result = _parse_routing_metadata(env)
        assert result is None

    def test_parse_routing_metadata_handles_empty_payload(self) -> None:
        """_parse_routing_metadata handles None/empty payload gracefully."""
        from k1.bus.envelope import Envelope
        from poc.k1_poc.actors.front import _parse_routing_metadata

        env = Envelope(topic="user.input", payload=b"", payload_format=1)
        result = _parse_routing_metadata(env)
        assert result is None

    def test_parse_routing_metadata_handles_invalid_json(self) -> None:
        """_parse_routing_metadata returns None for invalid JSON."""
        from k1.bus.envelope import Envelope
        from poc.k1_poc.actors.front import _parse_routing_metadata

        env = Envelope(topic="user.input", payload=b"not json", payload_format=1)
        result = _parse_routing_metadata(env)
        assert result is None


# ===================================================================
# Integration: end-to-end LISTENING turn with enrichment
# ===================================================================


class TestListeningEndToEnd:
    """Full LISTENING turn validates all E5.3 features together."""

    def test_full_listening_turn_with_arbiter_enrichment(self) -> None:
        """Complete LISTENING turn: Phase1 + Arbiter + enrichment + delivery."""
        fsm, bus = _make_fsm()
        env = build_user_input({"text": "plan a weekend trip to Paris"})
        fsm._on_user_input(env)

        # FSM trace: LISTENING -> DISPATCHING
        assert fsm._state == ConciergeState.DISPATCHING

        # Events emitted
        topics = _captured_topics(bus)
        assert TOPIC_TURN_STARTED in topics
        assert TOPIC_STATE_UPDATED in topics
        assert TOPIC_INTENT_ARBITRATED in topics

        # Arbiter event correct
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        arb_payload = _payload(arb_events[0])
        assert arb_payload["decision"] == ArbiterDecision.PARALLEL_NEW.value
        assert arb_payload["inflight_task_count"] == 0

        # History metadata complete
        last = fsm._history[-1]
        assert last.entry_type == "user"
        assert "intent" in last.metadata
        assert "arbiter" in last.metadata
        assert last.metadata["arbiter"]["decision"] == ArbiterDecision.PARALLEL_NEW.value

    def test_full_clarifying_turn_with_arbiter_enrichment(self) -> None:
        """Complete CLARIFYING_USER turn: Phase1 + Arbiter + enrichment."""
        fsm, bus = _make_fsm()
        fsm._state = ConciergeState.CLARIFYING_USER
        env = build_user_input({"text": "yes, the 3-star hotel"})
        fsm._on_user_input(env)

        # FSM trace: CLARIFYING_USER -> DISPATCHING
        assert fsm._state == ConciergeState.DISPATCHING

        # Arbiter event emitted
        arb_events = _captured_by_topic(bus, TOPIC_INTENT_ARBITRATED)
        assert len(arb_events) == 1
        arb_payload = _payload(arb_events[0])
        assert arb_payload["decision"] == ArbiterDecision.PARALLEL_NEW.value

        # History has arbiter metadata
        last = fsm._history[-1]
        assert "arbiter" in last.metadata

    def test_run_phase1_with_arbiter_method_exists(self) -> None:
        """Controller has _run_phase1_with_arbiter method."""
        fsm, _ = _make_fsm()
        assert hasattr(fsm, "_run_phase1_with_arbiter")
        assert callable(fsm._run_phase1_with_arbiter)

    def test_enrich_envelope_with_arbiter_method_exists(self) -> None:
        """Controller has _enrich_envelope_with_arbiter method."""
        fsm, _ = _make_fsm()
        assert hasattr(fsm, "_enrich_envelope_with_arbiter")
        assert callable(fsm._enrich_envelope_with_arbiter)

    def test_old_run_phase1_still_exists(self) -> None:
        """_run_phase1 is still present for backward compatibility (E5.2)."""
        fsm, _ = _make_fsm()
        assert hasattr(fsm, "_run_phase1")
        assert callable(fsm._run_phase1)
